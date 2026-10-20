#!/usr/bin/env bash
# Fail-closed fast-forward sync for the persistent OEC A100 checkout.
set -euo pipefail

LOCAL_REPO="${OEC_LOCAL_REPO:-$HOME/OEC}"
EXPECTED_BRANCH="${OEC_SYNC_BRANCH:-fix/media-stack-supervision-20261019}"

fail() {
  printf 'OEC_A100_SYNC=BLOCKED reason=%s\n' "$1" >&2
  exit "${2:-2}"
}

if [[ ! -e "$LOCAL_REPO/.git" ]]; then
  fail "persistent checkout missing; no clone or replacement was attempted" 10
fi

origin="$(git -C "$LOCAL_REPO" remote get-url origin 2>/dev/null || true)"
case "$origin" in
  *github.com/CalamityStriker/OEC.git|*github.com/CalamityStriker/OEC|*github.com:CalamityStriker/OEC.git|*github.com:CalamityStriker/OEC)
    ;;
  *)
    fail "origin does not identify the approved CalamityStriker/OEC repository; URL intentionally not printed" 11
    ;;
esac

local_branch="$(git -C "$LOCAL_REPO" branch --show-current 2>/dev/null || true)"
[[ "$local_branch" == "$EXPECTED_BRANCH" ]] ||
  fail "local branch '$local_branch' is not expected branch '$EXPECTED_BRANCH'; no checkout/switch attempted" 12

dirty="$(git -C "$LOCAL_REPO" status --porcelain --untracked-files=all)"
if [[ -n "$dirty" ]]; then
  printf 'OEC_A100_SYNC=BLOCKED reason=working_tree_dirty\n%s\n' "$dirty" >&2
  exit 13
fi

before="$(git -C "$LOCAL_REPO" rev-parse HEAD)"
git -C "$LOCAL_REPO" fetch --no-tags origin "refs/heads/$EXPECTED_BRANCH:refs/remotes/origin/$EXPECTED_BRANCH"
target="$(git -C "$LOCAL_REPO" rev-parse "refs/remotes/origin/$EXPECTED_BRANCH")"

if ! git -C "$LOCAL_REPO" merge-base --is-ancestor "$before" "$target"; then
  fail "remote branch is not a fast-forward descendant; local history preserved" 14
fi

git -C "$LOCAL_REPO" merge --ff-only "$target"
after="$(git -C "$LOCAL_REPO" rev-parse HEAD)"
[[ "$after" == "$target" ]] || fail "post-sync SHA differs from fetched origin SHA" 15
[[ -z "$(git -C "$LOCAL_REPO" status --porcelain --untracked-files=all)" ]] ||
  fail "working tree is not clean after fast-forward" 16

printf 'OEC_A100_SYNC=PASS\n'
printf 'OEC_LOCAL_REPO=%s\n' "$LOCAL_REPO"
printf 'OEC_SYNC_BRANCH=%s\n' "$EXPECTED_BRANCH"
printf 'OEC_SYNC_BEFORE=%s\n' "$before"
printf 'OEC_SYNC_AFTER=%s\n' "$after"
printf 'OEC_SYNC_TARGET=%s\n' "$target"
