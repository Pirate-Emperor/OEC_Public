#!/usr/bin/env python3
"""Wait for a supervised OEC media service and report fatal startup errors promptly."""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any


def classify_health(http_status: int | None, health: dict[str, Any]) -> str:
    """Classify one health response without treating HTTP 503 as opaque."""
    if http_status == 200 and health.get("ready") and health.get("model_loaded"):
        return "READY"
    if health.get("error") and not health.get("loading"):
        return "FATAL"
    return "WAITING"


def read_health(url: str, request_timeout: float = 4.0) -> tuple[int | None, dict[str, Any]]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        response = opener.open(url, timeout=request_timeout)
        status = int(response.status)
        body = response.read()
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        body = exc.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, {"error": f"{type(exc).__name__}: {exc}", "loading": True}

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return status, {
            "error": f"invalid JSON health response: {type(exc).__name__}",
            "loading": False,
            "body_excerpt": body[:240].decode("utf-8", errors="replace"),
        }
    if not isinstance(payload, dict):
        return status, {"error": "health response was not a JSON object", "loading": False}
    return status, payload


def wait_for_service(url: str, timeout_seconds: float, interval_seconds: float) -> int:
    deadline = time.monotonic() + timeout_seconds
    last_status: int | None = None
    last_health: dict[str, Any] = {}
    while True:
        last_status, last_health = read_health(url)
        print(json.dumps({"http_status": last_status, **last_health}, sort_keys=True), flush=True)
        state = classify_health(last_status, last_health)
        if state == "READY":
            print("MEDIA_SERVICE_READINESS=PASS", flush=True)
            return 0
        if state == "FATAL":
            print("MEDIA_SERVICE_READINESS=FATAL_STARTUP_ERROR", file=sys.stderr, flush=True)
            return 2
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            print(json.dumps({
                "MEDIA_SERVICE_READINESS": "TIMEOUT",
                "last_http_status": last_status,
                "last_health": last_health,
            }, sort_keys=True), file=sys.stderr, flush=True)
            return 1
        time.sleep(min(interval_seconds, remaining))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="Loopback /health endpoint for a supervised OEC service")
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    parser.add_argument("--interval-seconds", type=float, default=5.0)
    args = parser.parse_args()
    if args.timeout_seconds <= 0 or args.interval_seconds <= 0:
        parser.error("timeouts and polling interval must be positive")
    return wait_for_service(args.url, args.timeout_seconds, args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
