from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "tmp" / "validation"


@dataclass(frozen=True)
class Step:
    name: str
    command: list[str]
    cwd: Path = ROOT
    bucket: str = "tests"
    isolate_runtime_environment: bool = False


def executable(name: str) -> str:
    return shutil.which(name) or name


def repository_identity() -> dict[str, object] | None:
    """Fingerprint the exact tracked source tested by this validation run."""

    try:
        head = (
            subprocess.run(
                ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                capture_output=True,
                check=True,
            )
            .stdout.decode("utf-8")
            .strip()
        )
        diff = subprocess.run(
            ["git", "-C", str(ROOT), "diff", "--binary", "HEAD"],
            capture_output=True,
            check=True,
        ).stdout
        untracked = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "--others", "--exclude-standard", "-z"],
            capture_output=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError):
        return None
    untracked_count = len([path for path in untracked.split(b"\0") if path])
    return {
        "head_sha": head,
        "tracked_diff_sha256": hashlib.sha256(diff).hexdigest(),
        "untracked_file_count": untracked_count,
    }


def command_steps() -> list[Step]:
    python = sys.executable
    npm = executable("npm.cmd" if os.name == "nt" else "npm")
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    return [
        Step(
            "canonical source verification",
            [python, "scripts/verify_canonical_sources.py"],
            bucket="lint",
        ),
        Step(
            "release metadata verification",
            [python, "scripts/verify_release_metadata.py"],
            bucket="lint",
        ),
        Step(
            "release package dry-run",
            [
                python,
                "scripts/prepare_release.py",
                "--tag",
                f"v{version}",
                "--ref",
                "HEAD",
                "--output-dir",
                "tmp/release-dry-run",
                "--dry-run",
            ],
            bucket="build",
        ),
        Step("secret scan", [python, "scripts/check_secrets.py"], bucket="lint"),
        Step("generated maps", [python, "scripts/generate_maps.py", "--check"], bucket="lint"),
        Step(
            "adaptive token budget benchmark",
            [python, "scripts/adaptive_token_budget_benchmark.py"],
            bucket="tests",
        ),
        Step(
            "review evidence schema",
            [python, "scripts/review_evidence.py", "--work-order", "LOCAL-VALIDATION"],
            bucket="lint",
        ),
        Step(
            "ruff format",
            [python, "-m", "ruff", "format", "--check", "backend", "scripts", "migrations"],
            bucket="lint",
        ),
        Step(
            "ruff lint",
            [python, "-m", "ruff", "check", "backend", "scripts", "migrations"],
            bucket="lint",
        ),
        Step("mypy", [python, "-m", "mypy"], bucket="lint"),
        Step(
            "backend tests",
            [python, "-m", "pytest", "--junitxml", str(VALIDATION / "backend-junit.xml")],
            bucket="tests",
            isolate_runtime_environment=True,
        ),
        Step("dashboard install", [npm, "ci"], cwd=ROOT / "dashboard", bucket="build"),
        Step("dashboard lint", [npm, "run", "lint"], cwd=ROOT / "dashboard", bucket="lint"),
        Step(
            "dashboard typecheck", [npm, "run", "typecheck"], cwd=ROOT / "dashboard", bucket="lint"
        ),
        Step("dashboard tests", [npm, "run", "test:run"], cwd=ROOT / "dashboard", bucket="tests"),
        Step("dashboard build", [npm, "run", "build"], cwd=ROOT / "dashboard", bucket="build"),
        Step(
            "dashboard npm audit",
            [npm, "audit", "--audit-level=high"],
            cwd=ROOT / "dashboard",
            bucket="lint",
        ),
        Step(
            "compose config",
            ["docker", "compose", "config", "--quiet"],
            bucket="docker",
        ),
    ]


def isolated_environment(source: dict[str, str]) -> dict[str, str]:
    """Remove workstation HIVE settings before deterministic test subprocesses."""

    environment = source.copy()
    for name in tuple(environment):
        if name.startswith("HIVE_") or name in {"POSTGRES_DSN", "REDIS_URL", "CORS_ORIGINS"}:
            environment.pop(name, None)
    return environment


def run_step(step: Step) -> tuple[int, str, float]:
    environment = os.environ.copy()
    if step.isolate_runtime_environment:
        environment = isolated_environment(environment)
    environment["PYTHONUNBUFFERED"] = "1"
    started = time.monotonic()
    command_text = subprocess.list2cmdline(step.command)
    print(f"[START] {step.name} · {command_text} · cwd={step.cwd}", flush=True)
    lines: list[str] = []
    try:
        process = subprocess.Popen(
            step.command,
            cwd=step.cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=environment,
            bufsize=1,
        )
        if process.stdout is None:
            raise RuntimeError("validation subprocess stdout pipe was not created")
        for line in process.stdout:
            lines.append(line)
            print(console_safe(line.rstrip("\r\n")), flush=True)
        exit_code = process.wait()
    except OSError as exc:
        exit_code = 127
        lines.append(f"{type(exc).__name__}: {exc}\n")
        print(f"[ERROR] {type(exc).__name__}: {exc}", flush=True)
    duration = round(time.monotonic() - started, 3)
    output = (
        f"$ {command_text}\n"
        f"cwd: {step.cwd}\n"
        f"exit_code: {exit_code}\n"
        f"duration_seconds: {duration}\n\n" + "".join(lines)
    )
    print(
        f"[{('PASS' if exit_code == 0 else 'FAIL')}] {step.name} · {duration:.1f}s",
        flush=True,
    )
    return exit_code, output, duration


def console_safe(text: str, encoding: str | None = None) -> str:
    selected_encoding = encoding or sys.stdout.encoding or "utf-8"
    return text.encode(selected_encoding, errors="backslashreplace").decode(selected_encoding)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic HIVE validation.")
    parser.add_argument(
        "--only", choices=["all", "tests", "lint", "build", "docker"], default="all"
    )
    args = parser.parse_args()
    candidate_before = repository_identity()
    VALIDATION.mkdir(parents=True, exist_ok=True)
    buckets: dict[str, list[str]] = {"tests": [], "lint": [], "build": [], "docker": []}
    failures: list[str] = []
    step_results: list[dict[str, object]] = []
    validation_started = time.monotonic()
    for step in command_steps():
        if args.only != "all" and step.bucket != args.only:
            continue
        code, output, duration = run_step(step)
        buckets[step.bucket].append(output)
        step_results.append(
            {
                "name": step.name,
                "bucket": step.bucket,
                "exit_code": code,
                "duration_seconds": duration,
            }
        )
        if code:
            failures.append(step.name)
    (VALIDATION / "test-results.txt").write_text(
        "\n\n".join(buckets["tests"]) + "\n",
        encoding="utf-8",
    )
    (VALIDATION / "lint-typecheck-build-results.txt").write_text(
        "\n\n".join(buckets["lint"] + buckets["build"]) + "\n",
        encoding="utf-8",
    )
    (VALIDATION / "docker-compose-config.txt").write_text(
        "\n\n".join(buckets["docker"]) + "\n",
        encoding="utf-8",
    )
    summary = "PASS" if not failures else "FAIL: " + ", ".join(failures)
    (VALIDATION / "summary.txt").write_text(summary + "\n", encoding="utf-8")
    candidate_after = repository_identity()
    candidate_stable = (
        candidate_before is not None
        and candidate_after == candidate_before
        and candidate_before["untracked_file_count"] == 0
    )
    junit_path = VALIDATION / "backend-junit.xml"
    junit_digest = (
        hashlib.sha256(junit_path.read_bytes()).hexdigest() if junit_path.is_file() else None
    )
    (VALIDATION / "validation-summary.json").write_text(
        json.dumps(
            {
                "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "status": "PASS" if not failures else "FAIL",
                "duration_seconds": round(time.monotonic() - validation_started, 3),
                "selected_bucket": args.only,
                "failed_steps": failures,
                "steps": step_results,
                "candidate_identity": {
                    **(candidate_before or {}),
                    "stable_during_validation": candidate_stable,
                    "backend_junit_sha256": junit_digest,
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
