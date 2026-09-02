"""Capture bounded, secret-free Docker Compose service logs."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

DEFAULT_COMMAND = ("docker", "compose", "logs", "--no-color", "--tail=200")
_URL_CREDENTIALS = re.compile(r"(?i)(://[^:/\s]+:)[^@\s]+(@)")
_SENSITIVE_VALUE = re.compile(
    r"""(?i)(["']?(?:password|passwd|token|secret|api[_-]?key|authorization|database_url|postgres_password|redis_password)["']?\s*[:=]\s*)("[^"]*"|'[^']*'|\S+)"""
)
_GITHUB_TOKEN = re.compile(r"(?i)\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)\b")


def redact_service_logs(text: str) -> str:
    """Redact common URL, key/value, and GitHub token credentials."""

    text = _URL_CREDENTIALS.sub(r"\1[REDACTED]\2", text)
    text = _SENSITIVE_VALUE.sub(r"\1[REDACTED]", text)
    return _GITHUB_TOKEN.sub("[REDACTED]", text)


def capture_service_logs(output_path: Path, command: tuple[str, ...] = DEFAULT_COMMAND) -> int:
    """Run the bounded log command, print redacted output, and preserve its status."""

    try:
        result = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        captured = result.stdout or ""
        return_code = result.returncode
    except OSError as error:
        captured = f"{type(error).__name__}: {error}\n"
        return_code = 127

    safe_output = redact_service_logs(captured)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(safe_output, encoding="utf-8", newline="\n")
    print(safe_output, end="")
    return return_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tmp/integration-logs/service-logs.log"),
    )
    args = parser.parse_args()
    return capture_service_logs(args.output)


if __name__ == "__main__":
    raise SystemExit(main())
