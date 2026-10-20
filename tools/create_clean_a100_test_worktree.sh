#!/usr/bin/env bash
# Create/update a clean, isolated test worktree without mutating the user-owned $HOME/OEC tree.
set -euo pipefail

SOURCE_REPO="${OEC_SOURCE_REPO:-$HOME/OEC}"
TARGET_WORKTREE="${OEC_TEST_WORKTREE:-$HOME/OEC_feature_sync}"
EXPECTED_BRANCH="${OEC_SYNC_BRANCH:-fix/media-stack-supervision-20261019}"
CONDA="${OEC_CONDA_BIN:-$HOME/Conda/condabin/conda}"
PREFLIGHT_PYTHON="${OEC_STORAGE_PYTHON_ENV:-oec_deploy}"
WORKSPACE_ROOT="${GITHUB_WORKSPACE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

blocked() {
  printf 'OEC_CLEAN_WORKTREE_SYNC=BLOCKED reason=%s\n' "$1" >&2
  exit "${2:-2}"
}
[[ -e "$SOURCE_REPO/.git" ]] || blocked "source checkout missing" 20
[[ ! -L "$TARGET_WORKTREE" ]] || blocked "target path is a symlink; no changes made" 21

origin="$(git -C "$SOURCE_REPO" remote get-url origin 2>/dev/null || true)"
case "$origin" in
  *github.com/CalamityStriker/OEC.git|*github.com/CalamityStriker/OEC|*github.com:CalamityStriker/OEC.git|*github.com:CalamityStriker/OEC)
    ;;
  *) blocked "source origin does not identify CalamityStriker/OEC" 22 ;;
esac
[[ -x "$CONDA" ]] || blocked "Conda executable required for StorageManager preflight is missing" 23
[[ -f "$WORKSPACE_ROOT/storage_manager.py" && -f "$WORKSPACE_ROOT/storage_config.json" ]] ||
  blocked "candidate StorageManager/config are unavailable in the isolated Actions workspace" 24

# Fetch updates Git metadata only; no working-tree checkout/change in SOURCE_REPO.
git -C "$SOURCE_REPO" fetch --no-tags origin "refs/heads/$EXPECTED_BRANCH:refs/remotes/origin/$EXPECTED_BRANCH"
TARGET_SHA="$(git -C "$SOURCE_REPO" rev-parse "refs/remotes/origin/$EXPECTED_BRANCH")"
[[ -n "$TARGET_SHA" ]] || blocked "remote branch could not be resolved" 25

# If the dedicated worktree exists, accept only a registered, clean worktree.
if [[ -e "$TARGET_WORKTREE" ]]; then
  [[ -e "$TARGET_WORKTREE/.git" ]] || blocked "target path exists but is not a Git worktree; preserving it" 26
  top="$(git -C "$TARGET_WORKTREE" rev-parse --show-toplevel 2>/dev/null || true)"
  [[ "$top" == "$TARGET_WORKTREE" ]] || blocked "existing target is not the expected worktree; preserving it" 27
  git -C "$SOURCE_REPO" worktree list --porcelain | grep -Fqx "worktree $TARGET_WORKTREE" ||
    blocked "existing target is not registered to the approved source checkout; preserving it" 28
  dirty="$(git -C "$TARGET_WORKTREE" status --porcelain --untracked-files=all)"
  [[ -z "$dirty" ]] || {
    printf 'OEC_CLEAN_WORKTREE_SYNC=BLOCKED reason=dedicated_worktree_dirty; preserving files\n%s\n' "$dirty" >&2
    exit 29
  }
  current="$(git -C "$TARGET_WORKTREE" rev-parse HEAD)"
  if [[ "$current" != "$TARGET_SHA" ]]; then
    # Refresh the dedicated, confirmed-clean worktree only after fresh quota admission.
    "$CONDA" run --no-capture-output -n "$PREFLIGHT_PYTHON" python \
      "$WORKSPACE_ROOT/storage_manager.py" --preflight-path "$HOME" \
      --required-gb 0.25 --minimum-free-gb 1.0 --require-fresh-quota
    git -C "$TARGET_WORKTREE" switch --detach "$TARGET_SHA"
  fi
else
  # Fresh quota/space admission before materializing a new source checkout.
  "$CONDA" run --no-capture-output -n "$PREFLIGHT_PYTHON" python \
    "$WORKSPACE_ROOT/storage_manager.py" --preflight-path "$HOME" \
    --required-gb 0.25 --minimum-free-gb 1.0 --require-fresh-quota
  git -C "$SOURCE_REPO" worktree add --detach "$TARGET_WORKTREE" "$TARGET_SHA"
fi

actual="$(git -C "$TARGET_WORKTREE" rev-parse HEAD)"
[[ "$actual" == "$TARGET_SHA" ]] || blocked "post-worktree SHA does not match fetched origin SHA" 30
[[ -z "$(git -C "$TARGET_WORKTREE" status --porcelain --untracked-files=all)" ]] ||
  blocked "dedicated worktree is not clean after sync" 31

printf 'OEC_CLEAN_WORKTREE_SYNC=PASS\n'
printf 'OEC_TEST_WORKTREE=%s\n' "$TARGET_WORKTREE"
printf 'OEC_SYNC_BRANCH=%s\n' "$EXPECTED_BRANCH"
printf 'OEC_SYNC_ACTUAL_SHA=%s\n' "$actual"
printf 'OEC_SYNC_TARGET_SHA=%s\n' "$TARGET_SHA"
printf 'OEC_USER_CHECKOUT_PRESERVED=%s\n' "$SOURCE_REPO"
