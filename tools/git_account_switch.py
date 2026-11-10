#!/usr/bin/env python3
"""Switch this OEC checkout's GitHub account and commit identity safely.

Commit identity and GitHub authentication are separate. This tool configures
both locally in the current repository only. For HTTPS, a local Git credential
helper obtains the selected account token from GitHub CLI on demand; the token
is never stored in .git/config, the remote URL, or a plaintext credentials file.
"""
from __future__ import annotations
import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

TOKEN_ENV_VARS = ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN")
HELPER_PATH = Path(__file__).with_name("git-credential-gh-account.sh")


class SwitchError(RuntimeError):
    pass


def run(command, *, cwd=None, env=None, timeout=30):
    try:
        result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True,
                                check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SwitchError(f"could not run {command[0]}: {type(exc).__name__}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        message = detail[-1][:300] if detail else f"exit code {result.returncode}"
        raise SwitchError(f"{command[0]} failed: {message}")
    return result.stdout.strip()


def remote_details_from_url(url):
    if url.startswith("git@github.com:"):
        protocol, path = "ssh", url.split(":", 1)[1]
    else:
        parsed = urlparse(url)
        if parsed.hostname != "github.com":
            raise SwitchError("remote is not hosted on github.com")
        if parsed.scheme in ("http", "https"):
            if parsed.username or parsed.password:
                raise SwitchError("remote URL contains embedded credentials; remove them before switching accounts")
            protocol, path = "https", parsed.path.lstrip("/")
        elif parsed.scheme == "ssh":
            if parsed.username not in (None, "git") or parsed.password:
                raise SwitchError("SSH remote must use the standard git@github.com transport user")
            protocol, path = "ssh", parsed.path.lstrip("/")
        else:
            raise SwitchError(f"unsupported remote URL scheme: {parsed.scheme or '<none>'}")
    path = path.removesuffix(".git").strip("/")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", path):
        raise SwitchError("could not safely identify owner/repository from remote URL")
    return protocol, path


def repo_root():
    return run(["git", "rev-parse", "--show-toplevel"])


def remote_details(remote):
    return remote_details_from_url(run(["git", "remote", "get-url", remote]))


def require_gh():
    gh = shutil.which("gh")
    if not gh:
        raise SwitchError(
            "GitHub CLI 'gh' is not installed. Install GitHub CLI, then run "
            "python tools/git_account_switch.py login to add the new account securely."
        )
    return gh


def clean_token_env():
    env = os.environ.copy()
    for key in TOKEN_ENV_VARS + ("GH_HOST",):
        env.pop(key, None)
    return env


def validate_identity(name, email):
    if not name.strip() or "\n" in name or "\r" in name:
        raise SwitchError("Git author name must be non-empty and single-line")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise SwitchError("provide a valid single-line commit email address")


def set_identity(name, email, root):
    validate_identity(name, email)
    run(["git", "config", "--local", "user.name", name], cwd=root)
    run(["git", "config", "--local", "user.email", email], cwd=root)


def verify_saved_account(gh, login_name):
    env = clean_token_env()
    token = run([gh, "auth", "token", "--hostname", "github.com", "--user", login_name],
                env=env, timeout=20)
    if not token:
        raise SwitchError(f"GitHub CLI returned no saved token for {login_name!r}")
    api_env = dict(env)
    api_env["GH_TOKEN"] = token
    verified = run([gh, "api", "user", "--jq", ".login"], env=api_env, timeout=20)
    token = ""
    if verified.casefold() != login_name.casefold():
        raise SwitchError(f"credential mismatch: requested {login_name!r}, API returned {verified!r}")
    return verified


def credential_helper_command(login_name):
    helper = HELPER_PATH.resolve()
    if not helper.is_file():
        raise SwitchError(f"credential helper script is missing: {helper}")
    return f"!bash {shlex.quote(str(helper))} --account {shlex.quote(login_name)}"


def test_remote_access(root, remote_url, login_name):
    helper = credential_helper_command(login_name)
    command = ["git", "-C", root, "-c", "credential.helper=",
               "-c", f"credential.helper={helper}", "ls-remote", remote_url, "HEAD"]
    env = clean_token_env()
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        result = subprocess.run(command, text=True, capture_output=True, check=False,
                                timeout=30, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SwitchError(f"could not test repository access: {type(exc).__name__}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        message = detail[-1][:300] if detail else f"exit code {result.returncode}"
        raise SwitchError(f"selected account cannot read this remote: {message}")


def show_status(remote):
    root = repo_root()
    protocol, owner_repo = remote_details(remote)
    print(f"Repository: {root}")
    print(f"Remote: {remote} -> {owner_repo} ({protocol})")
    for key in ("user.name", "user.email", "credential.username"):
        try:
            value = run(["git", "config", "--show-origin", "--get", key], cwd=root)
        except SwitchError:
            value = "(not configured)"
        print(f"{key}: {value}")
    try:
        helpers = run(["git", "config", "--local", "--show-origin", "--get-all", "credential.helper"], cwd=root)
        print(f"Repository-local credential helper: {helpers}")
    except SwitchError:
        print("Repository-local credential helper: (not configured)")
    gh = shutil.which("gh")
    if not gh:
        print("GitHub CLI: not installed")
        return 0
    status = subprocess.run([gh, "auth", "status", "--hostname", "github.com"],
                            text=True, capture_output=True, check=False, timeout=20)
    print("Saved GitHub CLI accounts:")
    print((status.stdout + "\n" + status.stderr).strip() or "(none reported)")
    return 0


def login():
    gh = require_gh()
    try:
        result = subprocess.run(
            [gh, "auth", "login", "--hostname", "github.com", "--git-protocol", "https", "--web"],
            check=False,
        )
    except OSError as exc:
        raise SwitchError(f"could not start GitHub CLI login: {type(exc).__name__}") from exc
    if result.returncode != 0:
        raise SwitchError(f"GitHub CLI login did not complete (exit code {result.returncode})")
    status = subprocess.run([gh, "auth", "status", "--hostname", "github.com"],
                            text=True, capture_output=True, check=False, timeout=20)
    print((status.stdout + "\n" + status.stderr).strip())
    print("Account saved in GitHub CLI; no Git credential helper was changed globally.")
    return 0


def switch_account(login_name, name, email, remote, convert_ssh):
    root = repo_root()
    validate_identity(name, email)
    if not re.fullmatch(r"[A-Za-z0-9-]+", login_name):
        raise SwitchError("provide a valid GitHub login name")
    if any(os.environ.get(key) for key in TOKEN_ENV_VARS):
        raise SwitchError("unset GitHub token environment variables before switching accounts")

    gh = require_gh()
    protocol, owner_repo = remote_details(remote)
    target_url = f"https://github.com/{owner_repo}.git"
    if protocol == "ssh" and not convert_ssh:
        raise SwitchError(
            f"{remote} uses SSH. Pass --convert-ssh-to-https to explicitly change only this repository's remote "
            "to HTTPS, or keep using a dedicated SSH key for this repository."
        )

    verified = verify_saved_account(gh, login_name)
    test_remote_access(root, target_url, verified)

    if protocol == "ssh":
        run(["git", "remote", "set-url", remote, target_url], cwd=root)
    set_identity(name, email, root)

    helper = credential_helper_command(verified)
    subprocess.run(["git", "config", "--local", "--unset-all", "credential.helper"],
                   cwd=root, text=True, capture_output=True, check=False)
    run(["git", "config", "--local", "--add", "credential.helper", ""], cwd=root)
    run(["git", "config", "--local", "--add", "credential.helper", helper], cwd=root)
    run(["git", "config", "--local", "credential.username", "x-access-token"], cwd=root)
    run(["git", "config", "--local", "credential.useHttpPath", "false"], cwd=root)

    print(f"Verified GitHub account for this repository: {verified}")
    print(f"Repository-local commit identity: {name} <{email}>")
    print(f"Repository remote: {remote} -> {target_url}")
    print("Token is obtained on demand from GitHub CLI; it is not stored in Git config.")
    print("No global Git identity, global credential helper, or other repository was changed.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status", help="show this repository's Git identity and authentication setup")
    status.add_argument("--remote", default="origin")
    sub.add_parser("login", help="add a GitHub account with the browser/device flow")
    switch = sub.add_parser("switch", help="set this repository's GitHub account and commit identity")
    switch.add_argument("--login", required=True, help="GitHub login already saved by login")
    switch.add_argument("--name", required=True, help="Git commit author/committer display name")
    switch.add_argument("--email", required=True, help="Git commit email verified on the selected account")
    switch.add_argument("--remote", default="origin")
    switch.add_argument("--convert-ssh-to-https", action="store_true",
                        help="explicitly convert this repository's SSH remote to its equivalent HTTPS URL")
    identity = sub.add_parser("set-identity", help="change only repository-local user.name and user.email")
    identity.add_argument("--name", required=True)
    identity.add_argument("--email", required=True)

    args = parser.parse_args()
    try:
        if args.command == "status":
            return show_status(args.remote)
        if args.command == "login":
            return login()
        root = repo_root()
        if args.command == "set-identity":
            set_identity(args.name, args.email, root)
            print(f"Repository-local commit identity set to {args.name} <{args.email}>")
            return 0
        return switch_account(args.login, args.name, args.email, args.remote, args.convert_ssh_to_https)
    except SwitchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
