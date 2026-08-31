from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request


def fetch(url: str) -> tuple[int, bytes, dict | None]:
    with urllib.request.urlopen(url, timeout=5) as response:
        body = response.read()
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            payload = None
        return response.status, body, payload


def main() -> int:
    api_port = os.environ.get("HIVE_API_PORT", "8000")
    dashboard_port = os.environ.get("HIVE_DASHBOARD_PORT", "3000")
    health_url = f"http://127.0.0.1:{api_port}/api/v1/health"
    dashboard_url = f"http://127.0.0.1:{dashboard_port}/"
    last_error = "unknown"
    for _ in range(30):
        try:
            status, _, payload = fetch(health_url)
            if status == 200 and payload and payload.get("status") == "ok":
                checks = payload.get("checks", {})
                assert checks["postgres"]["details"]["pgvector"] is True
                assert checks["redis"]["details"]["canonical"] is False
                dashboard_status, dashboard_body, _ = fetch(dashboard_url)
                assert dashboard_status == 200
                assert b"HIVE" in dashboard_body
                print(json.dumps(payload, indent=2))
                print("Integration health passed.")
                return 0
        except (AssertionError, KeyError, OSError, urllib.error.URLError, ValueError) as exc:
            last_error = repr(exc)
        time.sleep(2)
    print(f"Integration health failed: {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
