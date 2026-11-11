#!/usr/bin/env bash
# Account-specific Git credential helper; it never persists the returned token.
set -euo pipefail
ACCOUNT=""
ACTION=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --account)
      [[ $# -ge 2 ]] || exit 2
      ACCOUNT="$2"
      shift 2
      ;;
    get|store|erase)
      ACTION="$1"
      shift
      ;;
    *)
      shift
      ;;
  esac
done
[[ -n "$ACCOUNT" ]] || exit 2
PROTOCOL=""
HOST=""
while IFS='=' read -r key value; do
  case "$key" in
    protocol) PROTOCOL="$value" ;;
    host) HOST="$value" ;;
  esac
done
case "$ACTION" in
  store|erase)
    exit 0
    ;;
  get)
    [[ "$PROTOCOL" == "https" && "$HOST" == "github.com" ]] || exit 0
    command -v gh >/dev/null 2>&1 || exit 1
    unset GH_TOKEN GITHUB_TOKEN GH_ENTERPRISE_TOKEN GITHUB_ENTERPRISE_TOKEN
    TOKEN="$(gh auth token --hostname github.com --user "$ACCOUNT")"
    [[ -n "$TOKEN" ]] || exit 1
    printf 'username=x-access-token\npassword=%s\n\n' "$TOKEN"
    unset TOKEN
    ;;
  *)
    exit 2
    ;;
esac
