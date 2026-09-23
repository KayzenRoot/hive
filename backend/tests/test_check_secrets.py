from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_wo031_runtime_roots_are_excluded_from_untracked_secret_scan() -> None:
    runtime_paths = (
        ".hive-wo031-data/cas/sha256/92/example.zst",
        ".hive-wo031-projects/wo020-cc-fixture/src/service.py",
    )
    for path in runtime_paths:
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "--quiet", path],
            cwd=ROOT,
            check=False,
        )
        assert result.returncode == 0, f"runtime data path is not ignored: {path}"
