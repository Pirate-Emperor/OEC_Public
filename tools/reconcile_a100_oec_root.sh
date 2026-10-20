#!/usr/bin/env bash
# Reconcile the single canonical A100 checkout with the approved GitHub branch.
# Local changes are preserved in Git recovery refs/stashes; loose files are moved into
# the common Git metadata recovery area. This script never mutates model/storage reserves.
set -euo pipefail

ROOT="${OEC_LOCAL_REPO:-$HOME/OEC}"
ALT="${OEC_TEST_WORKTREE:-$HOME/OEC_feature_sync}"
EXPECTED_BRANCH="${OEC_SYNC_BRANCH:-fix/media-stack-supervision-20261019}"
CONDA="${OEC_CONDA_BIN:-$HOME/Conda/condabin/conda}"
WORKSPACE_ROOT="${GITHUB_WORKSPACE:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)}"
STORAGE_ENV="${OEC_STORAGE_PYTHON_ENV:-oec_deploy}"
RUN_ID="${GITHUB_RUN_ID:-manual}-$(date +%Y%m%d%H%M%S)"

fail() {
  printf 'OEC_CANONICAL_SYNC=BLOCKED reason=%s\n' "$1" >&2
  exit "${2:-2}"
}

[[ -d "$ROOT" && -e "$ROOT/.git" ]] || fail "canonical $HOME/OEC Git checkout is missing" 10
ROOT="$(cd -- "$ROOT" && pwd -P)"
root_top="$(git -C "$ROOT" rev-parse --show-toplevel 2>/dev/null || true)"
[[ -n "$root_top" ]] || fail "canonical path is not a Git worktree" 11
root_top="$(cd -- "$root_top" && pwd -P)"
[[ "$root_top" == "$ROOT" ]] || fail "canonical checkout top-level differs from $ROOT" 12

origin="$(git -C "$ROOT" remote get-url origin 2>/dev/null || true)"
case "$origin" in
  *github.com/CalamityStriker/OEC.git|*github.com/CalamityStriker/OEC|*github.com:CalamityStriker/OEC.git|*github.com:CalamityStriker/OEC) ;;
  *) fail "origin does not identify the approved CalamityStriker/OEC repository" 13 ;;
esac

[[ -x "$CONDA" ]] || fail "Conda executable is missing" 14
[[ -f "$WORKSPACE_ROOT/storage_manager.py" && -f "$WORKSPACE_ROOT/storage_config.json" ]] ||
  fail "candidate StorageManager/config are unavailable in the Actions workspace" 15
[[ -f "$ROOT/storage_config.json" ]] || fail "canonical checkout storage_config.json is missing" 16

# Source checkout changes are forbidden while a known OEC consumer/inference process is active.
if pgrep -f '[b]rain.py|[h]f_upload_daemon.py|[q]a_compliance_worker.py|[w]orker_ltx_video.py|[a]udio_api.py|[t]rellis_api.py|[l]tx_api.py|[p]ipeline_audiogen.py|[p]ipeline_musicgen.py' >/dev/null 2>&1; then
  fail "active OEC inference/queue process detected; stop it normally and retry" 17
fi

# Do not proceed if another worktree has the target branch checked out.
while IFS= read -r line; do
  case "$line" in
    "worktree "*) current_worktree="${line#worktree }" ;;
    "branch refs/heads/$EXPECTED_BRANCH")
      [[ "${current_worktree:-}" == "$ROOT" ]] ||
        fail "target branch is checked out in another worktree; no source mutation attempted" 18
      ;;
  esac
done < <(git -C "$ROOT" worktree list --porcelain)

# Copy the private host config to the isolated Action workspace before changing the checkout.
install -m 600 "$ROOT/storage_config.json" "$WORKSPACE_ROOT/storage_config.json"

# Fresh, read-only StorageManager admission before any source-file moves or checkout.
"$CONDA" run --no-capture-output -n "$STORAGE_ENV" python "$WORKSPACE_ROOT/storage_manager.py" \
  --preflight-path "$HOME" --required-gb 0.25 --minimum-free-gb 1.0 --require-fresh-quota

git -C "$ROOT" fetch --no-tags origin "refs/heads/$EXPECTED_BRANCH:refs/remotes/origin/$EXPECTED_BRANCH"
TARGET_SHA="$(git -C "$ROOT" rev-parse "refs/remotes/origin/$EXPECTED_BRANCH")"
[[ "$TARGET_SHA" =~ ^[0-9a-f]{40}$ ]] || fail "remote branch tip could not be resolved" 19
BEFORE_SHA="$(git -C "$ROOT" rev-parse HEAD)"

COMMON_DIR="$(git -C "$ROOT" rev-parse --git-common-dir)"
if [[ "$COMMON_DIR" != /* ]]; then COMMON_DIR="$ROOT/$COMMON_DIR"; fi
COMMON_DIR="$(cd -- "$COMMON_DIR" && pwd -P)"
[[ "$(stat -c '%d' "$ROOT")" == "$(stat -c '%d' "$COMMON_DIR")" ]] ||
  fail "canonical worktree and Git metadata are on different filesystems; refusing file moves" 20

BACKUP_ROOT="$COMMON_DIR/oec-sync-recovery/$RUN_ID"
mkdir -p -m 700 "$BACKUP_ROOT"
git -C "$ROOT" update-ref "refs/oec-sync-recovery/$RUN_ID/root-head" "$BEFORE_SHA"
git -C "$ROOT" update-ref "refs/oec-sync-recovery/$RUN_ID/target" "$TARGET_SHA"

capture_paths() {
  local worktree="$1" label="$2" kind="$3"
  local list="$BACKUP_ROOT/$label/$kind-paths.nul"
  mkdir -p "$BACKUP_ROOT/$label"
  if [[ "$kind" == "ignored" ]]; then
    git -C "$worktree" ls-files --others --ignored --exclude-standard -z > "$list"
  else
    git -C "$worktree" ls-files --others --exclude-standard -z > "$list"
  fi
  python3 -c 'import pathlib,sys; b=pathlib.Path(sys.argv[1]).read_bytes(); print(sum(1 for x in b.split(bytes([0])) if x))' "$list"
}

move_captured_paths() {
  local worktree="$1" label="$2" kind="$3"
  local list="$BACKUP_ROOT/$label/$kind-paths.nul"
  local moved=0 rel src dst
  while IFS= read -r -d '' rel; do
    [[ -n "$rel" && "$rel" != /* && "$rel" != .. && "$rel" != ../* && "$rel" != */../* ]] ||
      fail "unsafe path appeared in Git's $kind manifest" 21
    src="$worktree/$rel"
    [[ -e "$src" || -L "$src" ]] || continue
    dst="$BACKUP_ROOT/$label/$kind/$rel"
    mkdir -p "$(dirname -- "$dst")"
    mv -- "$src" "$dst"
    moved=$((moved + 1))
  done < "$list"
  printf 'OEC_SYNC_PRESERVED_FILES_%s_%s=%s\n' "$label" "$kind" "$moved"
}

stash_tracked_changes() {
  local worktree="$1" label="$2"
  local changed stash_sha
  changed="$(git -C "$worktree" diff --name-only; git -C "$worktree" diff --cached --name-only)"
  if [[ -n "$changed" ]]; then
    git -C "$worktree" stash push -m "OEC pre-sync recovery $RUN_ID ($label)"
    stash_sha="$(git -C "$worktree" rev-parse refs/stash)"
    git -C "$ROOT" update-ref "refs/oec-sync-recovery/$RUN_ID/$label-stash" "$stash_sha"
    printf 'OEC_SYNC_TRACKED_CHANGES_STASHED_%s=%s\n' "$label" "$stash_sha"
  else
    printf 'OEC_SYNC_TRACKED_CHANGES_STASHED_%s=none\n' "$label"
  fi
}

ALT_EXISTS=0
if [[ -e "$ALT" || -L "$ALT" ]]; then
  [[ ! -L "$ALT" && -d "$ALT" && -e "$ALT/.git" ]] ||
    fail "temporary path exists but is not a normal linked worktree; preserved without deletion" 22
  ALT="$(cd -- "$ALT" && pwd -P)"
  alt_top="$(git -C "$ALT" rev-parse --show-toplevel 2>/dev/null || true)"
  [[ -n "$alt_top" ]] || fail "temporary path is not a readable Git worktree; preserved" 23
  alt_top="$(cd -- "$alt_top" && pwd -P)"
  [[ "$alt_top" == "$ALT" ]] || fail "temporary checkout top-level does not match its path; preserved" 24
  git -C "$ROOT" worktree list --porcelain | grep -Fqx "worktree $ALT" ||
    fail "temporary checkout is not registered to the canonical OEC repository; preserved" 25
  ALT_EXISTS=1
  ALT_NONIGNORED_COUNT="$(capture_paths "$ALT" feature-sync nonignored)"
  ALT_IGNORED_COUNT="$(capture_paths "$ALT" feature-sync ignored)"
  (( ALT_IGNORED_COUNT <= 20000 )) ||
    fail "temporary worktree has $ALT_IGNORED_COUNT ignored files; retained for separate reviewed cleanup" 26
  git -C "$ROOT" update-ref "refs/oec-sync-recovery/$RUN_ID/feature-sync-head" "$(git -C "$ALT" rev-parse HEAD)"
  printf 'OEC_FEATURE_SYNC_NONIGNORED_FILE_COUNT=%s\n' "$ALT_NONIGNORED_COUNT"
  printf 'OEC_FEATURE_SYNC_IGNORED_FILE_COUNT=%s\n' "$ALT_IGNORED_COUNT"

  stash_tracked_changes "$ALT" feature-sync
  move_captured_paths "$ALT" feature-sync nonignored
  move_captured_paths "$ALT" feature-sync ignored
  git -C "$ROOT" worktree remove "$ALT" ||
    fail "Git refused normal removal of the verified temporary worktree; remaining path preserved" 27
  printf 'OEC_FEATURE_SYNC_PATH_REMOVED=yes\n'
else
  printf 'OEC_FEATURE_SYNC_PATH_REMOVED=already-absent\n'
fi

ROOT_NONIGNORED_COUNT="$(capture_paths "$ROOT" root nonignored)"
printf 'OEC_ROOT_PRE_SYNC_HEAD=%s\n' "$BEFORE_SHA"
printf 'OEC_REMOTE_TARGET_SHA=%s\n' "$TARGET_SHA"
printf 'OEC_ROOT_PRE_SYNC_STATUS_ENTRIES=%s\n' "$(git -C "$ROOT" status --porcelain --untracked-files=all | wc -l | tr -d '[:space:]')"
printf 'OEC_ROOT_NONIGNORED_FILES_TO_PRESERVE=%s\n' "$ROOT_NONIGNORED_COUNT"

stash_tracked_changes "$ROOT" root
move_captured_paths "$ROOT" root nonignored

# No reset or clean: the previous HEAD/stash and all loose non-ignored files are recoverable.
git -C "$ROOT" checkout -B "$EXPECTED_BRANCH" "$TARGET_SHA"
ACTUAL_SHA="$(git -C "$ROOT" rev-parse HEAD)"
[[ "$ACTUAL_SHA" == "$TARGET_SHA" ]] || fail "canonical checkout SHA differs from remote target" 28
[[ -z "$(git -C "$ROOT" status --porcelain --untracked-files=all)" ]] ||
  fail "canonical checkout not clean after synchronization; recovery data remains in place" 29

cat > "$BACKUP_ROOT/README.txt" <<EOF
OEC canonical A100 checkout reconciliation
Run: $RUN_ID
Canonical path: $ROOT
Remote branch: $EXPECTED_BRANCH
Previous HEAD: $BEFORE_SHA
Synchronized SHA: $TARGET_SHA
Tracked root changes: refs/oec-sync-recovery/$RUN_ID/root-stash (if created)
Previous root HEAD: refs/oec-sync-recovery/$RUN_ID/root-head
Previous sibling worktree HEAD: refs/oec-sync-recovery/$RUN_ID/feature-sync-head (if present)
Untracked files from each checkout are preserved under this directory with NUL-delimited path manifests.
No model cache or storage reserve file was intentionally deleted.
EOF

{
  printf 'OEC_CANONICAL_SYNC=PASS\n'
  printf 'OEC_CANONICAL_ROOT=%s\n' "$ROOT"
  printf 'OEC_CANONICAL_BRANCH=%s\n' "$EXPECTED_BRANCH"
  printf 'OEC_CANONICAL_SHA=%s\n' "$ACTUAL_SHA"
  printf 'OEC_RECOVERY_METADATA=%s\n' "$BACKUP_ROOT"
} | tee "$BACKUP_ROOT/report.txt"

if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  {
    echo "## OEC canonical A100 source reconciliation"
    echo
    printf -- '- Canonical path: %s\n' "$ROOT"
    printf -- '- Branch: %s\n' "$EXPECTED_BRANCH"
    printf -- '- Exact remote SHA: %s\n' "$ACTUAL_SHA"
    printf -- '- Previous local HEAD and recovery payloads: %s\n' "$BACKUP_ROOT"
    printf -- '- OEC_feature_sync removed only after registered-worktree verification.\n'
  } >> "$GITHUB_STEP_SUMMARY"
fi
