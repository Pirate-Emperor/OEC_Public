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
BACKUP_ROOT=""

finish_recovery_record() {
  local rc=$?
  if [[ -n "${BACKUP_ROOT:-}" && -d "$BACKUP_ROOT" && ! -f "$BACKUP_ROOT/README.txt" ]]; then
    {
      printf "OEC sync recovery record\\nRun: %s\\nCanonical root: %s\\nBranch: %s\\nPrevious HEAD: %s\\nTarget SHA: %s\\nExit code: %s\\n" \
        "${RUN_ID:-unknown}" "${ROOT:-unknown}" "${EXPECTED_BRANCH:-unknown}" "${BEFORE_SHA:-unknown}" "${TARGET_SHA:-unknown}" "$rc"
      echo "Preserved files are identified by the NUL-delimited manifests under this directory."
      echo "Tracked changes are held under refs/oec-sync-recovery/<run-id>/*-stash; prior HEAD is under *-head."
    } > "$BACKUP_ROOT/README.txt" 2>/dev/null || true
  fi
}
trap finish_recovery_record EXIT

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

# Serialize every entry point that reconciles this persistent shared checkout.
EARLY_COMMON_DIR="$(git -C "$ROOT" rev-parse --git-common-dir)"
if [[ "$EARLY_COMMON_DIR" != /* ]]; then EARLY_COMMON_DIR="$ROOT/$EARLY_COMMON_DIR"; fi
EARLY_COMMON_DIR="$(cd -- "$EARLY_COMMON_DIR" && pwd -P)"
SYNC_LOCK="$EARLY_COMMON_DIR/oec-sync-reconcile.lock"
[[ ! -L "$SYNC_LOCK" ]] || fail "sync lock path is a symlink; refusing to follow it" 29
exec 9>"$SYNC_LOCK"
command -v flock >/dev/null 2>&1 || fail "flock is required to serialize persistent checkout reconciliation" 29
flock -n 9 || fail "another reconciliation process currently owns the persistent OEC sync lock" 29
printf 'OEC_SYNC_MUTEX=ACQUIRED path=%s\\n' "$SYNC_LOCK"

origin="$(git -C "$ROOT" remote get-url origin 2>/dev/null || true)"
case "$origin" in
  *github.com/CalamityStriker/OEC.git|*github.com/CalamityStriker/OEC|*github.com:CalamityStriker/OEC.git|*github.com:CalamityStriker/OEC) ;;
  *github.com/xflexwork/OEC.git|*github.com/xflexwork/OEC|*github.com:xflexwork/OEC.git|*github.com:xflexwork/OEC) ;;
  *) fail "origin does not identify an approved CalamityStriker/OEC or xflexwork/OEC repository" 13 ;;
esac

[[ -x "$CONDA" ]] || fail "Conda executable is missing" 14
[[ -f "$WORKSPACE_ROOT/storage_manager.py" && -f "$WORKSPACE_ROOT/storage_config.json" ]] ||
  fail "candidate StorageManager/config are unavailable in the Actions workspace" 15
[[ -f "$ROOT/storage_config.json" ]] || fail "canonical checkout storage_config.json is missing" 16

# Source checkout changes are forbidden while a known OEC consumer/inference process is active.
if pgrep -f '[b]rain.py|[h]f_upload_daemon.py|[q]a_compliance_worker.py|[w]orker_ltx_video.py|[a]udio_api.py|[t]rellis_api.py|[l]tx_api.py|[f]lux_api.py|[a]udiocraft_api.py|[p]ipeline_audiogen.py|[p]ipeline_musicgen.py|[p]ipeline_flux_image.py|[p]ipeline_flux_trellis.py|[p]ipeline_trellis_3d.py|[p]ipeline_flux_only.py|asset_factory[.]worker' >/dev/null 2>&1; then
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

# Recover a demonstrably stale Git index lock only by moving it into the
# timestamped recovery area. Never unlink it and never move one held by a live PID.
INDEX_LOCK="$COMMON_DIR/index.lock"
if [[ -L "$INDEX_LOCK" ]]; then
  fail "Git index.lock is a symlink; preserved for manual inspection" 29
fi
if [[ -e "$INDEX_LOCK" ]]; then
  LOCK_OWNERS=""
  if command -v fuser >/dev/null 2>&1; then
    LOCK_OWNERS="$(fuser "$INDEX_LOCK" 2>/dev/null | tr -s '[:space:]' ' ' | sed 's/^ *//;s/ *$//' || true)"
  elif command -v lsof >/dev/null 2>&1; then
    LOCK_OWNERS="$(lsof -t -- "$INDEX_LOCK" 2>/dev/null | tr -s '[:space:]' ' ' | sed 's/^ *//;s/ *$//' || true)"
  else
    fail "Git index.lock exists but neither fuser nor lsof is available to identify an owner" 29
  fi
  [[ -z "$LOCK_OWNERS" ]] || fail "Git index.lock is still open by PID(s) $LOCK_OWNERS; preserved without mutation" 29
  LOCK_AGE_SECONDS=$(( $(date +%s) - $(stat -c '%Y' "$INDEX_LOCK") ))
  (( LOCK_AGE_SECONDS >= 600 )) || fail "Git index.lock is only $LOCK_AGE_SECONDS seconds old; preserved for safety" 29
  mv -- "$INDEX_LOCK" "$BACKUP_ROOT/stale-index.lock"
  chmod 600 "$BACKUP_ROOT/stale-index.lock"
  printf 'OEC_STALE_INDEX_LOCK_PRESERVED path=%s age_seconds=%s recovery=%s\\n' "$INDEX_LOCK" "$LOCK_AGE_SECONDS" "$BACKUP_ROOT/stale-index.lock"
fi

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
  local changed stash_sha entry mode type sha path
  local -a stash_pathspec=(-- .)

  # A changed child HEAD is not an OEC-root source edit. In particular, a dirty
  # OEC-Deploy submodule must not make the parent stash try to capture its gitlink;
  # the parent synchronizes its own files while sync_pinned_submodules preserves
  # the child-local server-components sources under the explicit exception below.
  if [[ "$label" == "root" ]]; then
    changed="$(git -C "$worktree" diff --ignore-submodules=all --name-only; git -C "$worktree" diff --cached --ignore-submodules=all --name-only)"
    while read -r mode type sha path; do
      [[ "$mode" == "160000" && -n "$path" ]] || continue
      stash_pathspec+=(":(exclude)$path")
    done < <(git -C "$worktree" ls-tree HEAD)
  else
    changed="$(git -C "$worktree" diff --name-only; git -C "$worktree" diff --cached --name-only)"
  fi

  if [[ -n "$changed" ]]; then
    if [[ "$label" == "root" ]]; then
      git -C "$worktree" stash push -m "OEC pre-sync recovery $RUN_ID ($label)" -- "${stash_pathspec[@]}"
    else
      git -C "$worktree" stash push -m "OEC pre-sync recovery $RUN_ID ($label)"
    fi
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

# Recursively align initialized submodules to the exact gitlink pins.
# Before each checkout, protect tracked source and loose files; ignored model caches remain in place.
archive_submodule_residual() {
  local wt="$1" label="$2"
  local list="$BACKUP_ROOT/$label-nonignored-paths.nul"
  local status changed stash_sha rel src dst
  status="$(git -C "$wt" status --porcelain --untracked-files=all)"
  [[ -n "$status" ]] || return 0

  printf 'OEC_SUBMODULE_POST_CHECKOUT_STATUS_BEGIN path=%s\n' "$label"
  git -C "$wt" status --short --untracked-files=all
  printf 'OEC_SUBMODULE_POST_CHECKOUT_STATUS_END path=%s\n' "$label"

  changed="$(git -C "$wt" diff --name-only HEAD; git -C "$wt" diff --cached --name-only)"
  if [[ -n "$changed" ]]; then
    git -C "$wt" stash push -m "OEC post-checkout recovery $RUN_ID ($label)"
    stash_sha="$(git -C "$wt" rev-parse refs/stash)"
    git -C "$wt" update-ref "refs/oec-sync-recovery/$RUN_ID/post-checkout-stash" "$stash_sha"
    printf 'OEC_SUBMODULE_POST_CHECKOUT_TRACKED_STASH path=%s sha=%s\n' "$label" "$stash_sha"
    printf '%s\t%s\n' "$label" "$stash_sha" >> "$BACKUP_ROOT/submodule-stashes.tsv"
  fi

  git -C "$wt" ls-files --others --exclude-standard -z > "$list"
  while IFS= read -r -d '' rel; do
    [[ -n "$rel" && "$rel" != /* && "$rel" != .. && "$rel" != ../* && "$rel" != */../* ]] ||
      fail "unsafe untracked path appeared in submodule recovery manifest" 40
    src="$wt/$rel"
    [[ -e "$src" || -L "$src" ]] || continue
    dst="$BACKUP_ROOT/submodule-loose/$label/$rel"
    mkdir -p "$(dirname -- "$dst")"
    mv -- "$src" "$dst"
  done < "$list"

  [[ -z "$(git -C "$wt" status --porcelain --untracked-files=all)" ]] ||
    fail "submodule residual content remains after tracked stash and loose-file backup: $label" 41
  printf 'OEC_SUBMODULE_POST_CHECKOUT_PRESERVED_AND_CLEAN path=%s\n' "$label"
}

sync_pinned_submodules() {
  local parent="$1" parent_label="$2"
  local meta rel mode type expected child current safe_label nonignored
  while IFS=$'\t' read -r meta rel; do
    [[ -n "$rel" ]] || continue
    read -r mode type expected <<< "$meta"
    [[ "$mode" == "160000" && "$type" == "commit" ]] || continue
    child="$parent/$rel"
    safe_label="${parent_label//\//__}__${rel//\//__}"

    [[ -e "$child/.git" ]] ||
      fail "submodule $parent_label/$rel is not initialized; refusing an unbounded clone" 42

    # Changes outside nested gitlinks indicate real local source; keep and block on those.
    if ! git -C "$child" diff --quiet --ignore-submodules=all HEAD -- . ||
       ! git -C "$child" diff --cached --quiet --ignore-submodules=all HEAD -- .; then
      printf 'OEC_SUBMODULE_LOCAL_SOURCE_CHANGES path=%s/%s\n' "$parent_label" "$rel" >&2
      git -C "$child" status --short --untracked-files=all >&2 || true
      fail "submodule has local tracked edits; preserving them and refusing checkout: $parent_label/$rel" 43
    fi
    nonignored="$(git -C "$child" ls-files --others --exclude-standard | wc -l | tr -d '[:space:]')"
    if [[ "$nonignored" != "0" ]]; then
      local loose_list="$BACKUP_ROOT/$safe_label-nonignored-paths.nul"
      git -C "$child" ls-files --others --exclude-standard -z > "$loose_list"
      # OEC-Deploy's packaged server-components tree is user/runtime work until
      # it is committed and the parent gitlink is deliberately advanced. Preserve
      # it in place and allow the parent OEC checkout to sync independently.
      if [[ "$parent_label" == "root" && "$rel" == "oec_deploy" ]] &&
         python3 - "$loose_list" <<'PYLOOSE'
import pathlib, sys
paths = pathlib.Path(sys.argv[1]).read_bytes().split(b"\0")
paths = [p for p in paths if p]
sys.exit(0 if paths and all(p.startswith(b"v1/Biome/build/packaging/server-components/") for p in paths) else 1)
PYLOOSE
      then
        printf 'OEC_DEPLOY_SUBMODULE_SYNC=DEFERRED_LOCAL_WORK_PRESERVED count=%s path=v1/Biome/build/packaging/server-components/\n' "$nonignored"
        printf 'OEC_SUBMODULE_LOCAL_LOOSE_FILES_PRESERVED path=%s/%s count=%s\n' "$parent_label" "$rel" "$nonignored"
        git -C "$child" status --short --untracked-files=all >&2 || true
        continue
      fi
      printf 'OEC_SUBMODULE_LOCAL_LOOSE_FILES path=%s/%s count=%s\n' "$parent_label" "$rel" "$nonignored" >&2
      git -C "$child" status --short --untracked-files=all >&2 || true
      fail "submodule has non-ignored loose files outside the approved preserved OEC-Deploy packaging directory; preserving and refusing checkout: $parent_label/$rel" 44
    fi

    current="$(git -C "$child" rev-parse HEAD)"
    if [[ "$current" != "$expected" ]]; then
      git -C "$parent" submodule sync -- "$rel"
      git -C "$child" update-ref "refs/oec-sync-recovery/$RUN_ID/pre-sync-head" "$current"
      printf 'OEC_SUBMODULE_SYNC_START path=%s/%s current=%s expected=%s\n' "$parent_label" "$rel" "$current" "$expected"
      git -C "$parent" submodule update --checkout -- "$rel"
      current="$(git -C "$child" rev-parse HEAD)"
    fi
    [[ "$current" == "$expected" ]] ||
      fail "submodule SHA does not match the OEC gitlink: $parent_label/$rel" 45

    # Match nested submodules before judging whether the containing checkout is clean.
    sync_pinned_submodules "$child" "$safe_label"
    archive_submodule_residual "$child" "$safe_label"
    printf 'OEC_SUBMODULE_SYNC_PASS path=%s/%s sha=%s\n' "$parent_label" "$rel" "$current"
  done < <(git -C "$parent" ls-tree -r HEAD)
}

sync_pinned_submodules "$ROOT" "root"

[[ -z "$(git -C "$ROOT" status --porcelain --untracked-files=all --ignore-submodules=all)" ]] ||
  fail "canonical OEC parent checkout not clean after source synchronization; recovery data remains in place" 46

if [[ -d "$ROOT/oec_deploy/.git" || -f "$ROOT/oec_deploy/.git" ]]; then
  child_head="$(git -C "$ROOT/oec_deploy" rev-parse HEAD 2>/dev/null || true)"
  parent_pin="$(git -C "$ROOT" ls-tree HEAD -- oec_deploy | awk '{print $3}')"
  if [[ -n "$child_head" && "$child_head" != "$parent_pin" ]]; then
    printf 'OEC_DEPLOY_GITLINK_MISMATCH=WARNING parent_pin=%s child_head=%s\n' "$parent_pin" "$child_head"
  else
    printf 'OEC_DEPLOY_GITLINK=%s\n' "$parent_pin"
  fi
  if [[ "$(git -C "$ROOT/oec_deploy" ls-files --others --exclude-standard | wc -l | tr -d '[:space:]')" != "0" ]]; then
    printf 'OEC_DEPLOY_LOOSE_FILES=WARNING preserved=yes\n'
  else
    printf 'OEC_DEPLOY_LOOSE_FILES=NONE\n'
  fi
fi

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
Post-checkout submodule residual tracked edits are held in per-submodule Git recovery refs/stashes; non-ignored loose files are moved into this recovery directory.
Ignored model caches remain in place; no storage reserve file was intentionally deleted.
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
