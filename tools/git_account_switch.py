#!/usr/bin/env python3
"""Safely switch GitHub authentication and commit identity for the current repository.

Git commit identity (user.name/user.email) and GitHub authentication are separate.
This utility selects a saved GitHub CLI account for HTTPS Git remotes, then sets
repository-local commit identity. It never handles or prints access tokens.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from urllib.parse import urlparse


TOKEN_ENV_VARS = ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN")


class SwitchError(RuntimeError):
    pass


def run(command: list[str], *, cwd: str | None = None, env: dict[str, str] | None = None) -> str:
    try:
        result = subprocess.run(
            command, cwd=cwd, env=env, text=True, capture_output=True,
            check=False, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SwitchError(f"could not run {command[0]}: {type(exc).__name__}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        message = detail[-1][:300] if detail else f"exit code {result.returncode}"
        raise SwitchError(f"{command[0]} failed: {message}")
    return result.stdout.strip()


def remote_details_from_url(url: str) -> tuple[str, str]:
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
            # The conventional SSH transport identity is literally "git";
            # this is not an embedded GitHub account or password.
            if parsed.username not in (None, "git") or parsed.password:
                raise SwitchError("SSH remote must use the standard git@github.com transport user")
            protocol, path = "ssh", parsed.path.lstrip("/")
        else:
            raise SwitchError(f"unsupported remote URL scheme: {parsed.scheme or '<none>'}")
    path = path.removesuffix(".git").strip("/")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", path):
        raise SwitchError("could not safely identify owner/repository from remote URL")
    return protocol, path


def repo_root() -> str:
    return run(["git", "rev-parse", "--show-toplevel"])


def remote_details(remote: str) -> tuple[str, str]:
    url = run(["git", "remote", "get-url", remote])
    return remote_details_from_url(url)


def require_gh() -> str:
    gh = shutil.which("gh")
    if not gh:
        raise SwitchError("GitHub CLI 'gh' is not installed; install it and run 'gh auth login' first")
    return gh


def gh_login(gh: str) -> str:
    login = run([gh, "api", "user", "--jq", ".login"])
    if not re.fullmatch(r"[A-Za-z0-9-]+", login):
        raise SwitchError("GitHub CLI did not return a valid active account login")
    return login


def show_status(remote: str) -> int:
    root = repo_root()
    protocol, owner_repo = remote_details(remote)
    print(f"Repository: {root}")
    print(f"Remote: {remote} -> {owner_repo} ({protocol})")
    for key in ("user.name", "user.email"):
        try:
            value = run(["git", "config", "--show-origin", "--get", key], cwd=root)
        except SwitchError:
            value = "(not configured)"
        print(f"{key}: {value}")
    gh = shutil.which("gh")
    if not gh:
        print("GitHub CLI: not installed")
        return 0
    try:
        print(f"Active GitHub account: {gh_login(gh)}")
    except SwitchError as exc:
        print(f"Active GitHub account: unavailable ({exc})")
    try:
        status = subprocess.run(
            [gh, "auth", "status", "--hostname", "github.com"],
            text=True, capture_output=True, check=False, timeout=20,
        )
        lines = (status.stdout + "\n" + status.stderr).strip()
        if lines:
            print("Saved GitHub CLI accounts:")
            print(lines)
        else:
            print("Saved GitHub CLI accounts: none reported")
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"GitHub CLI auth status unavailable ({type(exc).__name__})")
    return 0


def login() -> int:
    gh = require_gh()
    # gh auth login is interactive/device-flow; inherit the user's terminal so
    # the one-time code and browser instructions remain visible.
    try:
        result = subprocess.run(
            [gh, "auth", "login", "--hostname", "github.com", "--git-protocol", "https", "--web"],
            check=False,
        )
    except OSError as exc:
        raise SwitchError(f"could not start GitHub CLI login: {type(exc).__name__}") from exc
    if result.returncode != 0:
        raise SwitchError(f"GitHub CLI login did not complete (exit code {result.returncode})")
    run([gh, "auth", "setup-git"])
    print(f"GitHub HTTPS credential helper configured for account: {gh_login(gh)}")
    return 0


def validate_identity(name: str, email: str) -> None:
    if not name.strip() or "\n" in name or "\r" in name:
        raise SwitchError("Git author name must be non-empty and single-line")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise SwitchError("provide a valid single-line commit email address")


def set_identity(name: str, email: str, root: str) -> None:
    validate_identity(name, email)
    run(["git", "config", "--local", "user.name", name], cwd=root)
    run(["git", "config", "--local", "user.email", email], cwd=root)


def switch_account(login_name: str, name: str, email: str, remote: str, convert_ssh: bool) -> int:
    root = repo_root()
    validate_identity(name, email)
    if not re.fullmatch(r"[A-Za-z0-9-]+", login_name):
        raise SwitchError("provide a valid GitHub login name")
    if any(os.environ.get(key) for key in TOKEN_ENV_VARS):
        raise SwitchError(
            "a GitHub token environment variable is active; unset it in this shell before "
            "switching so it cannot override the selected saved account"
        )

    protocol, owner_repo = remote_details(remote)
    if protocol == "ssh" and not convert_ssh:
        raise SwitchError(
            f"{remote} uses SSH; GitHub CLI account switching controls HTTPS credentials. "
            "Re-run with --convert-ssh-to-https to change this remote to "
            f"https://github.com/{owner_repo}.git, or switch the SSH key configured for this remote."
        )

    gh = require_gh()
    run([gh, "auth", "switch", "--hostname", "github.com", "--user", login_name])
    active = gh_login(gh)
    if active.casefold() != login_name.casefold():
        raise SwitchError(f"GitHub account verification mismatch: requested {login_name!r}, active {active!r}")

    # Only convert the remote after the selected account is verified. This
    # avoids leaving a changed remote behind when account switching fails.
    if protocol == "ssh":
        run(["git", "remote", "set-url", remote, f"https://github.com/{owner_repo}.git"], cwd=root)

    # Configure gh as Git's HTTPS credential helper. No token is placed in the
    # repository, remote URL, or local Git config.
    run([gh, "auth", "setup-git"])
    set_identity(name, email, root)
    print(f"GitHub account: {active}")
    print(f"Repository-local commit identity: {name} <{email}>")
    print(f"Remote: {remote} -> https://github.com/{owner_repo}.git")
    print("No access token was read, printed, or written to the repository.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status", help="show local commit identity and GitHub CLI account")
    status.add_argument("--remote", default="origin")
    sub.add_parser("login", help="add a GitHub account using the browser/device flow")
    switch = sub.add_parser("switch", help="switch the active GitHub HTTPS account and local commit identity")
    switch.add_argument("--login", required=True, help="GitHub login already saved by 'gh auth login'")
    switch.add_argument("--name", required=True, help="Git commit author/committer display name")
    switch.add_argument("--email", required=True, help="Git commit email")
    switch.add_argument("--remote", default="origin")
    switch.add_argument("--convert-ssh-to-https", action="store_true",
                        help="explicitly convert an SSH remote to its equivalent HTTPS URL")
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
