from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "docs" / "project-brain"
MANIFEST = SOURCE_ROOT / "CANONICAL-SHA256SUMS.txt"


def read_manifest() -> dict[str, str]:
    if not MANIFEST.exists():
        raise RuntimeError(f"Canonical manifest is missing: {MANIFEST}")
    entries: dict[str, str] = {}
    for line_number, raw_line in enumerate(MANIFEST.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or len(parts[0]) != 64:
            raise RuntimeError(f"Invalid canonical manifest line {line_number}: {raw_line!r}")
        digest, name = parts
        if name in entries:
            raise RuntimeError(f"Duplicate canonical manifest entry: {name}")
        entries[name] = digest
    if not entries:
        raise RuntimeError("Canonical manifest contains no source entries.")
    return entries


def verify() -> int:
    try:
        expected = read_manifest()
    except RuntimeError as error:
        print(f"CANONICAL SOURCE ERROR: {error}")
        return 1

    failures: list[str] = []
    for name, expected_digest in expected.items():
        path = SOURCE_ROOT / name
        if not path.is_file():
            failures.append(f"MISSING {name}")
            continue
        actual_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_digest != expected_digest:
            failures.append(f"MISMATCH {name}: expected {expected_digest}, got {actual_digest}")

    if failures:
        print("Canonical source verification failed:")
        print("\n".join(failures))
        return 1

    print(f"Canonical source verification passed for {len(expected)} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(verify())
