#!/usr/bin/env python3
"""Create safe backwards-compatible aliases for OEC's singular path names.

Default is report-only. With --apply, creates a symlink only when the alias does
not exist and the configured canonical directory exists. It never renames,
deletes, overwrites, or copies a directory.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


DEFAULT_ALIASES = {
    "datasets": "aireos_datasets",
    "inputs": "aireos_inputs",
    "outputs": "aireos_outputs",
}


def ensure_alias(alias: Path, target: Path, *, apply: bool = False) -> str:
    alias = alias.expanduser().absolute()
    target = target.expanduser().resolve()
    if not target.is_dir():
        return f"REFUSED target_not_directory target={target} alias={alias}"
    if alias.resolve(strict=False) == target:
        return f"REFUSED alias_equals_target alias={alias}"
    if alias.is_symlink():
        try:
            current = alias.resolve(strict=True)
        except FileNotFoundError:
            return f"REFUSED dangling_symlink alias={alias}"
        if current == target:
            return f"ALIAS_OK alias={alias} target={target}"
        return f"REFUSED wrong_symlink alias={alias} current={current} target={target}"
    if alias.exists():
        return f"REFUSED existing_non_symlink alias={alias} type={'directory' if alias.is_dir() else 'file'}"
    if not apply:
        return f"PLAN_CREATE alias={alias} target={target}"
    if not alias.parent.is_dir():
        return f"REFUSED alias_parent_missing parent={alias.parent}"
    os.symlink(str(target), str(alias), target_is_directory=True)
    if not alias.is_symlink() or alias.resolve(strict=True) != target:
        return f"ERROR post_create_verification_failed alias={alias} target={target}"
    return f"ALIAS_CREATED alias={alias} target={target}"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually create missing symlink aliases; default is report-only.")
    parser.add_argument("--base-dir", type=Path, help="Alias parent directory. Defaults to core_config.BASE_DIR.")
    parser.add_argument("--datasets", type=Path, help="Canonical datasets directory. Defaults to core_config.SYSTEM_DIRS['datasets'].")
    parser.add_argument("--inputs", type=Path, help="Canonical inputs directory. Defaults to core_config.SYSTEM_DIRS['inputs'].")
    parser.add_argument("--outputs", type=Path, help="Canonical outputs directory. Defaults to core_config.SYSTEM_DIRS['outputs'].")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.base_dir is None or args.datasets is None or args.inputs is None or args.outputs is None:
            from core_config import BASE_DIR, SYSTEM_DIRS
            base = args.base_dir or Path(BASE_DIR)
            targets = {
                "datasets": args.datasets or Path(SYSTEM_DIRS["datasets"]),
                "inputs": args.inputs or Path(SYSTEM_DIRS["inputs"]),
                "outputs": args.outputs or Path(SYSTEM_DIRS["outputs"]),
            }
        else:
            base = args.base_dir
            targets = {"datasets": args.datasets, "inputs": args.inputs, "outputs": args.outputs}
        base = base.expanduser().resolve()
        if not base.is_dir():
            print(f"REFUSED base_directory_missing path={base}", file=sys.stderr)
            return 2
        failures = 0
        for key, alias_name in DEFAULT_ALIASES.items():
            result = ensure_alias(base / alias_name, targets[key], apply=args.apply)
            print(f"PATH_ALIAS_{key.upper()} {result}")
            if result.startswith(("REFUSED", "ERROR")):
                failures += 1
        print("PATH_ALIAS_REPAIR=" + ("FAIL" if failures else ("APPLIED" if args.apply else "REPORT_ONLY")))
        return 1 if failures else 0
    except Exception as exc:
        print(f"PATH_ALIAS_REPAIR=ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
