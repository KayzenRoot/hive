from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

TOKEN_PATTERNS = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?token)\b\s*[:=]\s*['\"]([^'\"$]{16,})"
)
ALLOWED_VALUES = {"changeme", "replace-me", "example", "hive", "test"}


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        check=True,
        capture_output=True,
    )
    return [Path(item) for item in result.stdout.decode().split("\0") if item]


def main() -> int:
    files = tracked_files()
    findings: list[str] = []
    for path in files:
        if path.name in {".env", ".env.local"} or path.name.endswith(".pem"):
            findings.append(f"forbidden tracked secret file: {path}")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in TOKEN_PATTERNS:
            if pattern.search(text):
                findings.append(f"secret-like token in {path}")
        for match in SECRET_ASSIGNMENT.finditer(text):
            if match.group(1).lower() not in ALLOWED_VALUES:
                findings.append(f"secret assignment in {path}")
    if findings:
        print("\n".join(findings), file=sys.stderr)
        return 1
    print(f"Secret scan passed for {len(files)} tracked files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
