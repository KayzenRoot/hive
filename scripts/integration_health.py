from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION_LOG_DIR = ROOT / "tmp" / "integration-logs"
CLOSURE_EVIDENCE = INTEGRATION_LOG_DIR / "v01-closure-sprint.json"
HEALTH_EVIDENCE = INTEGRATION_LOG_DIR / "integration-health.json"


def isolated_environment_error(
    environment: Mapping[str, str] | None = None, *, repo_root: Path = ROOT
) -> str | None:
    """Refuse integration against an implicit or non-WO-031 data environment."""

    values = os.environ if environment is None else environment
    marker = values.get("HIVE_WO031_ISOLATED_E2E", "").strip().casefold()
    data_root = values.get("HIVE_DATA_ROOT", "").strip()
    projects_root = values.get("HIVE_PROJECTS_ROOT", "").strip()
    compose_project = values.get("COMPOSE_PROJECT_NAME", "").strip()
    if marker not in {"1", "true", "yes", "on"}:
        return "HIVE_WO031_ISOLATED_E2E=true is required"
    if not data_root or not projects_root or not compose_project:
        return "explicit data, projects, and Compose project roots are required"

    try:
        root = repo_root.resolve()
        resolved_data = Path(data_root).resolve()
        resolved_projects = Path(projects_root).resolve()
    except OSError:
        return "isolated roots could not be resolved"

    if "wo031" not in resolved_data.as_posix().casefold():
        return "HIVE_DATA_ROOT must be a WO-031 test root"
    if "wo031" not in resolved_projects.as_posix().casefold():
        return "HIVE_PROJECTS_ROOT must be a WO-031 test root"
    if "wo031" not in compose_project.casefold():
        return "COMPOSE_PROJECT_NAME must identify the isolated WO-031 stack"
    if (
        resolved_data == root
        or resolved_projects == root
        or not resolved_data.is_relative_to(root)
        or not resolved_projects.is_relative_to(root)
    ):
        return "integration roots must remain inside the checked-out repository workspace"
    if (
        resolved_data == resolved_projects
        or resolved_data in resolved_projects.parents
        or resolved_projects in resolved_data.parents
    ):
        return "data and projects roots must be distinct, non-overlapping directories"
    return None


def fetch(url: str) -> tuple[int, bytes, dict[str, Any] | None]:
    with urllib.request.urlopen(url, timeout=5) as response:
        body = response.read()
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            payload = None
        if not isinstance(payload, dict):
            payload = None
        return response.status, body, payload


def run_integration_script(label: str, path: str) -> dict[str, object]:
    started = time.monotonic()
    print(f"[integration] START {label} · {path}", flush=True)
    environment = os.environ.copy()
    if label == "Automatic project discovery":
        environment["HIVE_AUTO_DISCOVERY_ENABLED"] = "true"
    process = subprocess.Popen(
        [sys.executable, path],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=environment,
    )
    lines: queue.Queue[str | None] = queue.Queue()

    def collect_output() -> None:
        if process.stdout is None:
            lines.put(None)
            return
        for line in process.stdout:
            lines.put(line)
        lines.put(None)

    reader = threading.Thread(target=collect_output, name="integration-output", daemon=True)
    reader.start()
    stream_closed = False
    while not stream_closed or process.poll() is None:
        try:
            line = lines.get(timeout=5)
            if line is None:
                stream_closed = True
            else:
                print(line.rstrip("\r\n"), flush=True)
        except queue.Empty:
            print(
                f"[integration] RUNNING {label} · {time.monotonic() - started:.0f}s",
                flush=True,
            )
    exit_code = process.wait()
    duration = round(time.monotonic() - started, 3)
    print(
        f"[integration] {'PASS' if exit_code == 0 else 'FAIL'} {label} · "
        f"{duration:.1f}s · exit={exit_code}",
        flush=True,
    )
    return {"name": label, "script": path, "exit_code": exit_code, "duration_seconds": duration}


def enable_isolated_auto_discovery() -> dict[str, object]:
    """Recreate only the isolated API after legacy manual-registration fixtures finish."""

    started = time.monotonic()
    marker = os.environ.get("HIVE_WO031_ISOLATED_E2E", "").strip().lower()
    data_root = os.environ.get("HIVE_DATA_ROOT", "")
    projects_root = os.environ.get("HIVE_PROJECTS_ROOT", "")
    if (
        marker not in {"1", "true", "yes", "on"}
        or not data_root
        or not projects_root
        or "wo031" not in data_root.casefold()
        or "wo031" not in projects_root.casefold()
    ):
        return {
            "name": "Enable automatic discovery in isolated API",
            "exit_code": 1,
            "duration_seconds": round(time.monotonic() - started, 3),
            "diagnostic": "explicit isolated WO-031 roots and marker are required",
        }

    environment = os.environ.copy()
    environment["HIVE_AUTO_DISCOVERY_ENABLED"] = "true"
    try:
        process = subprocess.run(
            ["docker", "compose", "up", "-d", "--no-deps", "--force-recreate", "api"],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            check=False,
            timeout=180,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "name": "Enable automatic discovery in isolated API",
            "exit_code": 1,
            "duration_seconds": round(time.monotonic() - started, 3),
            "diagnostic": type(exc).__name__,
        }
    if process.returncode != 0:
        return {
            "name": "Enable automatic discovery in isolated API",
            "exit_code": process.returncode,
            "duration_seconds": round(time.monotonic() - started, 3),
            "diagnostic": "isolated_api_recreation_failed",
        }

    api_port = os.environ.get("HIVE_API_PORT", "8000")
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            status, _, payload = fetch(f"http://127.0.0.1:{api_port}/api/v1/health")
            if status == 200 and payload and payload.get("status") == "ok":
                return {
                    "name": "Enable automatic discovery in isolated API",
                    "exit_code": 0,
                    "duration_seconds": round(time.monotonic() - started, 3),
                    "api_health": "PASS",
                    "discovery_enabled_for_e2e": True,
                }
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(2)
    return {
        "name": "Enable automatic discovery in isolated API",
        "exit_code": 1,
        "duration_seconds": round(time.monotonic() - started, 3),
        "diagnostic": "isolated_api_health_timeout",
    }


def read_closure_evidence(started_at: float) -> dict[str, object]:
    if not CLOSURE_EVIDENCE.is_file():
        raise ValueError("closure sprint did not produce its evidence file")
    if CLOSURE_EVIDENCE.stat().st_mtime < started_at:
        raise ValueError("closure sprint evidence is stale from an earlier run")
    try:
        payload = json.loads(CLOSURE_EVIDENCE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("closure sprint evidence is unreadable or malformed") from exc
    if not isinstance(payload, dict):
        raise ValueError("closure sprint evidence must be a JSON object")
    if str(payload.get("status", "")).upper() != "PASS":
        raise ValueError("closure sprint evidence status is not PASS")
    candidate = payload.get("closure_candidate")
    full_claim = payload.get("full_v01_complete_claimed")
    if not isinstance(candidate, bool) or full_claim is not False:
        raise ValueError("closure sprint evidence has invalid candidate/claim fields")
    return {
        "evidence_file": CLOSURE_EVIDENCE.name,
        "status": "PASS",
        "closure_candidate": candidate,
        "full_v01_complete_claimed": False,
        "dod_pass_count": payload.get("dod_pass_count"),
        "dod_total_count": payload.get("dod_total_count"),
        "dod_fail_count": payload.get("dod_fail_count"),
        "dod_unknown_count": payload.get("dod_unknown_count"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run HIVE container integration checks against an isolated WO-031 stack."
    )
    parser.parse_args(argv)
    isolation_error = isolated_environment_error()
    if isolation_error:
        print(f"[integration] REFUSED: {isolation_error}", file=sys.stderr, flush=True)
        return 2

    api_port = os.environ.get("HIVE_API_PORT", "8000")
    dashboard_port = os.environ.get("HIVE_DASHBOARD_PORT", "3000")
    health_url = f"http://127.0.0.1:{api_port}/api/v1/health"
    dashboard_url = f"http://127.0.0.1:{dashboard_port}/"
    started = time.monotonic()
    started_wall = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    last_error = "unknown"
    for attempt in range(1, 31):
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
                integrations = (
                    ("Control Center", "scripts/control_center_integration.py"),
                    ("Control Center metrics", "scripts/control_center_metrics_integration.py"),
                    ("Full Control Center", "scripts/control_center_full_integration.py"),
                    ("Comprehensive benchmarks", "scripts/comprehensive_benchmarks.py"),
                    ("V0.1 backup/restore", "scripts/v01_backup_restore.py"),
                    ("V0.1 closure sprint", "scripts/v01_closure_sprint.py"),
                    ("MCP read-only core surface", "scripts/mcp_integration.py"),
                    ("Automatic project discovery", "scripts/auto_discovery_integration.py"),
                )
                results: list[dict[str, object]] = []
                closure_started_at: float | None = None
                for label, path in integrations:
                    if label == "V0.1 closure sprint":
                        closure_started_at = time.time()
                    if label == "Automatic project discovery":
                        activation = enable_isolated_auto_discovery()
                        results.append(activation)
                        if activation["exit_code"] != 0:
                            evidence = {
                                "schema_version": 1,
                                "status": "FAIL",
                                "started_at": started_wall,
                                "duration_seconds": round(time.monotonic() - started, 3),
                                "failed_stage": activation["name"],
                                "stages": results,
                            }
                            INTEGRATION_LOG_DIR.mkdir(parents=True, exist_ok=True)
                            HEALTH_EVIDENCE.write_text(
                                json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                                encoding="utf-8",
                            )
                            print(
                                "Automatic discovery could not be enabled in the isolated API.",
                                file=sys.stderr,
                                flush=True,
                            )
                            return 1
                    result = run_integration_script(label, path)
                    results.append(result)
                    if result["exit_code"] != 0:
                        evidence = {
                            "schema_version": 1,
                            "status": "FAIL",
                            "started_at": started_wall,
                            "duration_seconds": round(time.monotonic() - started, 3),
                            "failed_stage": label,
                            "stages": results,
                        }
                        INTEGRATION_LOG_DIR.mkdir(parents=True, exist_ok=True)
                        HEALTH_EVIDENCE.write_text(
                            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8",
                        )
                        print(
                            f"{label} integration failed with exit code {result['exit_code']}",
                            file=sys.stderr,
                        )
                        return 1
                if closure_started_at is None:
                    raise ValueError("closure sprint stage did not run")
                try:
                    closure = read_closure_evidence(closure_started_at)
                except ValueError as exc:
                    evidence = {
                        "schema_version": 1,
                        "status": "FAIL",
                        "started_at": started_wall,
                        "duration_seconds": round(time.monotonic() - started, 3),
                        "failed_stage": "V0.1 closure evidence",
                        "failure_type": type(exc).__name__,
                        "stages": results,
                    }
                    INTEGRATION_LOG_DIR.mkdir(parents=True, exist_ok=True)
                    HEALTH_EVIDENCE.write_text(
                        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    print(
                        f"Integration health failed while validating closure evidence: {exc}",
                        file=sys.stderr,
                    )
                    return 1
                evidence = {
                    "schema_version": 1,
                    "status": "PASS",
                    "started_at": started_wall,
                    "duration_seconds": round(time.monotonic() - started, 3),
                    "api_health": "PASS",
                    "dashboard_health": "PASS",
                    "stages": results,
                    "legacy_v01_closure": closure,
                }
                INTEGRATION_LOG_DIR.mkdir(parents=True, exist_ok=True)
                HEALTH_EVIDENCE.write_text(
                    json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                print(
                    "Integration health PASS; "
                    f"legacy closure_candidate={str(closure['closure_candidate']).lower()} "
                    "(separate from service/integration health; no V0.1 completion claim).",
                    flush=True,
                )
                return 0
        except (AssertionError, KeyError, OSError, urllib.error.URLError, ValueError) as exc:
            last_error = repr(exc)
        if attempt == 1 or attempt % 5 == 0:
            print(
                f"[integration] WAITING for healthy API/dashboard · "
                f"attempt {attempt}/30 · {last_error}",
                flush=True,
            )
        time.sleep(2)
    print(f"Integration health failed: {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
