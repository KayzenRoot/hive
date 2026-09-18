"""Verify deterministic release metadata coherence for HIVE releases.

The verifier fails closed when the active VERSION, backend runtime identity,
dashboard package identity, release notes, CHANGELOG and README disagree.
It performs no network access and makes no publication claim of its own.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STABLE_SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
BACKEND_INIT_VERSION = re.compile(r'^__version__ = "([^"]+)"\s*$', re.MULTILINE)
BACKEND_CONFIG_VERSION = re.compile(r'^\s*version: str = "([^"]+)"\s*$', re.MULTILINE)
RELEASE_NOTE_STATUS = re.compile(r"^Status:\s*(.+?)\s*$", re.MULTILINE)
CANDIDATE_STATUS = re.compile(r"^release candidate\b", re.IGNORECASE)
PUBLISHED_STATUS = re.compile(r"^published\b", re.IGNORECASE)
README_TARGET_PREFIX = "Target stable release: "
README_LATEST_PREFIX = "Latest stable release: "
STALE_BOOTSTRAP_IDENTITY = "0.0.1-bootstrap"


def read_text(path: Path, failures: list[str]) -> str:
    if not path.is_file():
        failures.append(f"missing required file: {path}")
        return ""
    return path.read_text(encoding="utf-8")


def read_json(path: Path, failures: list[str]) -> dict[str, object]:
    text = read_text(path, failures)
    if not text:
        return {}
    try:
        document = json.loads(text)
    except json.JSONDecodeError as error:
        failures.append(f"invalid JSON in {path}: {error}")
        return {}
    if not isinstance(document, dict):
        failures.append(f"expected a JSON object in {path}")
        return {}
    return document


def extract_version(pattern: re.Pattern[str], text: str, path: Path, failures: list[str]) -> str:
    match = pattern.search(text)
    if match is None:
        failures.append(f"{path} does not expose a parseable active version")
        return ""
    return match.group(1)


def require_equal(surface: str, observed: object, expected: str, failures: list[str]) -> None:
    if observed != expected:
        failures.append(f"{surface} is {observed!r} but VERSION is {expected!r}")


def verify_release_metadata(root: Path) -> list[str]:
    failures: list[str] = []
    version = read_text(root / "VERSION", failures).strip()
    if STABLE_SEMVER.fullmatch(version) is None:
        failures.append(f"VERSION must be strict stable SemVer X.Y.Z, observed {version!r}")
        return failures
    tag = f"v{version}"

    backend_init = read_text(root / "backend" / "app" / "__init__.py", failures)
    if backend_init:
        require_equal(
            "backend/app/__init__.py __version__",
            extract_version(
                BACKEND_INIT_VERSION,
                backend_init,
                Path("backend/app/__init__.py"),
                failures,
            ),
            version,
            failures,
        )

    backend_config = read_text(root / "backend" / "app" / "config.py", failures)
    if backend_config:
        require_equal(
            "backend/app/config.py version",
            extract_version(
                BACKEND_CONFIG_VERSION,
                backend_config,
                Path("backend/app/config.py"),
                failures,
            ),
            version,
            failures,
        )

    package = read_json(root / "dashboard" / "package.json", failures)
    if package:
        require_equal("dashboard/package.json version", package.get("version"), version, failures)

    lock = read_json(root / "dashboard" / "package-lock.json", failures)
    if lock:
        require_equal(
            "dashboard/package-lock.json root version", lock.get("version"), version, failures
        )
        packages = lock.get("packages")
        root_package = packages.get("") if isinstance(packages, dict) else None
        lock_root = root_package.get("version") if isinstance(root_package, dict) else None
        require_equal(
            "dashboard/package-lock.json packages root version", lock_root, version, failures
        )

    notes_path = root / "docs" / "releases" / f"{tag}.md"
    notes = read_text(notes_path, failures)
    published = False
    if notes:
        status_match = RELEASE_NOTE_STATUS.search(notes)
        if status_match is None:
            failures.append(f"docs/releases/{tag}.md must declare an explicit Status line")
        else:
            status = status_match.group(1)
            if PUBLISHED_STATUS.match(status):
                published = True
                receipt_path = (
                    root / ".engineering" / "release" / f"HIVE-V{version}-RELEASE-RECEIPT.json"
                )
                receipt = read_json(receipt_path, failures)
                if receipt:
                    if receipt.get("release_published") is not True:
                        failures.append(
                            f"docs/releases/{tag}.md claims Published without a final release "
                            "receipt recording release_published=true"
                        )
                    require_equal("release receipt tag", receipt.get("tag"), tag, failures)
                    release_url = receipt.get("release_url")
                    if not isinstance(release_url, str) or not release_url.strip():
                        failures.append(
                            "release receipt must record a non-empty release_url for a "
                            "published release"
                        )
            elif CANDIDATE_STATUS.match(status):
                pass
            else:
                failures.append(
                    f"docs/releases/{tag}.md Status must be 'Release candidate' or 'Published', "
                    f"observed {status!r}"
                )

    changelog = read_text(root / "CHANGELOG.md", failures)
    if changelog:
        heading = f"## [{version}]"
        occurrences = changelog.count(heading)
        if occurrences == 0:
            failures.append(f"CHANGELOG.md is missing the release heading {heading!r}")
        elif occurrences > 1:
            failures.append(f"CHANGELOG.md has {occurrences} duplicate {heading!r} headings")

    readme = read_text(root / "README.md", failures)
    if readme:
        target = f"{README_TARGET_PREFIX}v{version}"
        latest = f"{README_LATEST_PREFIX}v{version}"
        if published:
            if latest not in readme:
                failures.append(f"README.md must contain the published stable identity {latest!r}")
        else:
            if target not in readme:
                failures.append(f"README.md must contain the target stable identity {target!r}")
            if latest in readme:
                failures.append(
                    "README.md must not claim a latest stable published identity before publication"
                )
        if STALE_BOOTSTRAP_IDENTITY in readme:
            failures.append(
                "README.md still presents the stale bootstrap identity "
                f"{STALE_BOOTSTRAP_IDENTITY!r} as current"
            )

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify deterministic release metadata coherence.")
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root to verify")
    args = parser.parse_args()
    failures = verify_release_metadata(args.root)
    if failures:
        print("Release metadata verification failed:")
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    version = (args.root / "VERSION").read_text(encoding="utf-8").strip()
    print(f"Release metadata verification passed for {version}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
