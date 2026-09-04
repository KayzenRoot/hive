from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "tmp" / "validation"


@dataclass(frozen=True)
class Step:
    name: str
    command: list[str]
    cwd: Path = ROOT
    bucket: str = "tests"


def executable(name: str) -> str:
    return shutil.which(name) or name


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


def run_step(step: Step) -> tuple[int, str]:
    result = subprocess.run(
        step.command,
        cwd=step.cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        env=os.environ.copy(),
    )
    output = (
        f"$ {' '.join(step.command)}\n"
        f"cwd: {step.cwd}\n"
        f"exit_code: {result.returncode}\n\n"
        f"{result.stdout}{result.stderr}"
    )
    return result.returncode, output


def console_safe(text: str, encoding: str | None = None) -> str:
    selected_encoding = encoding or sys.stdout.encoding or "utf-8"
    return text.encode(selected_encoding, errors="backslashreplace").decode(selected_encoding)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic HIVE validation.")
    parser.add_argument(
        "--only", choices=["all", "tests", "lint", "build", "docker"], default="all"
    )
    args = parser.parse_args()
    VALIDATION.mkdir(parents=True, exist_ok=True)
    buckets: dict[str, list[str]] = {"tests": [], "lint": [], "build": [], "docker": []}
    failures: list[str] = []
    for step in command_steps():
        if args.only != "all" and step.bucket != args.only:
            continue
        code, output = run_step(step)
        buckets[step.bucket].append(output)
        print(console_safe(output))
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
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
