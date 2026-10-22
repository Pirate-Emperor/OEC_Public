#!/usr/bin/env python3
"""Verify a public OEC chunked ciphertext object and a user-supplied local decryptor.

This tool downloads but never uploads. It never reads/prints private-key contents.
Ciphertext and plaintext live in a private temporary directory removed at exit.
Both expected SHA-256 values must be provided independently.
"""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, stat, subprocess, tempfile
from pathlib import Path, PurePosixPath
from typing import Any

PROTOCOL = "oec-asset-chunks-v1"

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def safe_remote_path(raw: str) -> str:
    if not raw or "\\" in raw:
        raise ValueError("remote manifest path must be a safe relative POSIX path")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"unsafe remote manifest path: {raw!r}")
    return str(path)

def assemble_chunks_to_file(manifest: dict[str, Any], chunks_by_path: dict[str, Path],
                            output_path: Path) -> dict[str, Any]:
    if manifest.get("protocol") != PROTOCOL or manifest.get("status") != "complete":
        raise ValueError("remote manifest must be complete and use oec-asset-chunks-v1")
    expected_bytes, expected_sha = manifest.get("asset_bytes"), manifest.get("asset_sha256")
    if isinstance(expected_bytes, bool) or not isinstance(expected_bytes, int) or expected_bytes < 1:
        raise ValueError("manifest asset_bytes must be a positive integer")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64 or any(c not in "0123456789abcdefABCDEF" for c in expected_sha):
        raise ValueError("manifest asset_sha256 must be a SHA-256 hex digest")
    parts = manifest.get("parts")
    if not isinstance(parts, list) or not parts or len(parts) > 100000:
        raise ValueError("manifest parts must be a non-empty list of at most 100000 parts")
    whole, total = hashlib.sha256(), 0
    with output_path.open("xb") as output:
        os.chmod(output_path, stat.S_IRUSR | stat.S_IWUSR)
        for expected_index, part in enumerate(parts):
            if not isinstance(part, dict):
                raise ValueError(f"part {expected_index} must be an object")
            if part.get("index") != expected_index or part.get("offset_bytes") != total:
                raise ValueError(f"part {expected_index} has a non-contiguous index or offset")
            remote_path = safe_remote_path(str(part.get("path", "")))
            source_path = chunks_by_path.get(remote_path)
            if source_path is None or not source_path.is_file() or source_path.is_symlink():
                raise ValueError(f"missing/non-regular downloaded chunk: {remote_path}")
            size, expected_part_sha = part.get("size_bytes"), part.get("sha256")
            if isinstance(size, bool) or not isinstance(size, int) or size < 0:
                raise ValueError(f"part {expected_index} size_bytes must be a non-negative integer")
            part_digest, part_size = hashlib.sha256(), 0
            with source_path.open("rb") as source:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    output.write(block); whole.update(block); part_digest.update(block)
                    part_size += len(block); total += len(block)
            if part_size != size or part_digest.hexdigest().lower() != str(expected_part_sha).lower():
                raise ValueError(f"part {expected_index} size/SHA-256 mismatch")
        output.flush(); os.fsync(output.fileno())
    whole_sha = whole.hexdigest()
    if total != expected_bytes or whole_sha.lower() != expected_sha.lower():
        raise ValueError("assembled ciphertext size/SHA-256 does not match the remote manifest")
    return {"bytes": total, "sha256": whole_sha, "parts_verified": len(parts)}

def run() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument("--expected-ciphertext-sha256", required=True)
    parser.add_argument("--expected-plaintext-sha256", required=True)
    parser.add_argument("--private-key-path", required=True)
    parser.add_argument("--decrypt-command-json", required=True,
                        help='JSON argv array with "{input}", "{output}", and "{keyfile}" placeholders')
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args()
    for name in ("expected_ciphertext_sha256", "expected_plaintext_sha256"):
        value = getattr(args, name)
        if len(value) != 64 or any(c not in "0123456789abcdefABCDEF" for c in value):
            parser.error(f"--{name.replace('_','-')} must be a SHA-256 hex digest")
    if not 1 <= args.timeout_seconds <= 7200:
        parser.error("--timeout-seconds must be between 1 and 7200")
    try:
        manifest_path = safe_remote_path(args.manifest_path)
    except ValueError as exc:
        parser.error(str(exc))
    key_path = Path(args.private_key_path).expanduser()
    if key_path.is_symlink() or not key_path.is_file():
        parser.error("--private-key-path must be an existing regular non-symlink file")
    try:
        decrypt_argv = json.loads(args.decrypt_command_json)
    except json.JSONDecodeError as exc:
        parser.error(f"--decrypt-command-json is invalid JSON: {exc}")
    if not isinstance(decrypt_argv, list) or not decrypt_argv or any(not isinstance(v, str) for v in decrypt_argv):
        parser.error("--decrypt-command-json must be a non-empty JSON string array")
    for token in ("{input}", "{output}", "{keyfile}"):
        if not any(token in value for value in decrypt_argv):
            parser.error(f"decrypt argv must contain {token}")
    temp = Path(tempfile.mkdtemp(prefix="oec-hf-cipher-verify-")); temp.chmod(stat.S_IRWXU)
    try:
        from huggingface_hub import hf_hub_download
        cache = temp / "hub-cache"; cache.mkdir(mode=0o700)
        downloaded_manifest = Path(hf_hub_download(repo_id=args.repo_id, filename=manifest_path,
                                                    repo_type="dataset", local_dir=str(cache)))
        manifest = json.loads(downloaded_manifest.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("remote manifest must be a JSON object")
        parts = manifest.get("parts")
        if not isinstance(parts, list) or not parts:
            raise ValueError("remote manifest contains no parts")
        chunk_paths = {}
        for part in parts:
            if not isinstance(part, dict):
                raise ValueError("remote manifest has a malformed part")
            path = safe_remote_path(str(part.get("path", "")))
            if path in chunk_paths:
                raise ValueError("remote manifest contains duplicate chunk paths")
            chunk_paths[path] = Path(hf_hub_download(repo_id=args.repo_id, filename=path,
                                                    repo_type="dataset", local_dir=str(cache)))
        cipher_path = temp / "asset.ciphertext"
        cipher = assemble_chunks_to_file(manifest, chunk_paths, cipher_path)
        if cipher["sha256"].lower() != args.expected_ciphertext_sha256.lower():
            raise ValueError("ciphertext hash differs from independently recorded local expected hash")
        plain_path = temp / "asset.plaintext"
        stdout_log, stderr_log = temp / "decryptor.stdout.log", temp / "decryptor.stderr.log"
        argv = [value.replace("{input}", str(cipher_path)).replace("{output}", str(plain_path))
                     .replace("{keyfile}", str(key_path.resolve())) for value in decrypt_argv]
        with stdout_log.open("wb") as stdout, stderr_log.open("wb") as stderr:
            result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                    timeout=args.timeout_seconds, check=False, shell=False)
        if result.returncode != 0:
            raise RuntimeError(f"local decryptor failed with exit code {result.returncode}; output suppressed")
        if plain_path.is_symlink() or not plain_path.is_file():
            raise RuntimeError("local decryptor did not create the requested regular output file")
        plain_sha = sha256_file(plain_path); plain_bytes = plain_path.stat().st_size
        if plain_sha.lower() != args.expected_plaintext_sha256.lower():
            raise ValueError("decrypted plaintext hash differs from independently recorded original hash")
        print(json.dumps({"status":"PASS","repo_id":args.repo_id,"manifest_path":manifest_path,
            "ciphertext_bytes":cipher["bytes"],"ciphertext_sha256":cipher["sha256"],
            "parts_verified":cipher["parts_verified"],"plaintext_bytes":plain_bytes,
            "plaintext_sha256":plain_sha,"upload_performed":False,
            "private_key_contents_logged":False,"temporary_plaintext_removed_after_check":True},
            indent=2,sort_keys=True))
        return 0
    except subprocess.TimeoutExpired:
        print("ENCRYPTED_HF_READBACK=FAIL reason=local decryptor timed out; output suppressed", file=__import__("sys").stderr)
        return 1
    except Exception as exc:
        print(f"ENCRYPTED_HF_READBACK=FAIL type={type(exc).__name__} reason={str(exc)[:400]}", file=__import__("sys").stderr)
        return 1
    finally:
        shutil.rmtree(temp, ignore_errors=True)

if __name__ == "__main__":
    raise SystemExit(run())
