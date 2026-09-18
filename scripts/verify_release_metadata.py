"""Verify deterministic release metadata coherence for HIVE releases.

The verifier fails closed when the active VERSION, backend runtime identity,
dashboard package identity, release notes, CHANGELOG and README disagree.
It performs no network access and makes no publication claim of its own.
"""

from __future__ import annotations

import argparse
import hashlib
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
LOWER_HEX_SHA40 = re.compile(r"^[0-9a-f]{40}$")
LOWER_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
SECURITY_TRIAGE_PATH = Path(".engineering/release/HIVE-V{version}-SECURITY-TRIAGE.json")
RELEASE_CANDIDATE_PATH = Path(".engineering/release/HIVE-V{version}-RELEASE-CANDIDATE.json")
V100_SECURITY_PINS = {
    "fastapi": "0.133.0",
    "starlette": "1.3.1",
    "python-multipart": "0.0.31",
    "mako": "1.3.12",
}


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


def sha256_file(path: Path, failures: list[str]) -> str:
    if not path.is_file():
        failures.append(f"missing required file: {path}")
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def requirement_pins(path: Path, failures: list[str]) -> dict[str, str]:
    text = read_text(path, failures)
    pins: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", "-r ", "--requirement ")):
            continue
        if "==" not in line:
            continue
        name, version = line.split("==", 1)
        pins[name.strip().lower()] = version.strip()
    return pins


def verify_security_triage(
    root: Path,
    version: str,
    release_notes: str,
    failures: list[str],
) -> None:
    triage_rel = Path(str(SECURITY_TRIAGE_PATH).format(version=version))
    candidate_rel = Path(str(RELEASE_CANDIDATE_PATH).format(version=version))
    triage = read_json(root / triage_rel, failures)
    candidate = read_json(root / candidate_rel, failures)
    if not triage or not candidate:
        return

    if triage.get("schema_version") != 2:
        failures.append("security triage schema_version must be 2")
    if "generated_for_head" in triage:
        failures.append(
            "security triage must not use circular/ambiguous generated_for_head provenance"
        )
    inventory_head = triage.get("inventory_source_head")
    if not isinstance(inventory_head, str) or LOWER_HEX_SHA40.fullmatch(inventory_head) is None:
        failures.append("security triage inventory_source_head must be a lowercase 40-hex SHA")

    require_equal(
        "security triage release_version",
        triage.get("release_version"),
        version,
        failures,
    )
    if triage.get("release_gate") != "PASS":
        failures.append("security triage release_gate must be PASS")
    if triage.get("critical_high_applicable_open") != 0:
        failures.append("security triage must record zero applicable unresolved CRITICAL/HIGH")
    if triage.get("runtime_high_critical_remaining") is not False:
        failures.append("security triage runtime_high_critical_remaining must be false")

    dependency_state = triage.get("candidate_dependency_state")
    if not isinstance(dependency_state, dict):
        failures.append("security triage candidate_dependency_state must be an object")
        dependency_state = {}

    manifest_paths = (
        "requirements.txt",
        "requirements-dev.txt",
        "dashboard/package-lock.json",
    )
    for relative in manifest_paths:
        entry = dependency_state.get(relative)
        if not isinstance(entry, dict):
            failures.append(f"security triage is missing candidate state for {relative}")
            continue
        recorded_hash = entry.get("sha256")
        if not isinstance(recorded_hash, str) or LOWER_HEX_SHA256.fullmatch(recorded_hash) is None:
            failures.append(f"security triage {relative} sha256 must be lowercase 64-hex")
            continue
        observed_hash = sha256_file(root / relative, failures)
        if observed_hash and recorded_hash != observed_hash:
            failures.append(
                f"security triage {relative} sha256 drift: {recorded_hash!r} != {observed_hash!r}"
            )

    if version == "1.0.0":
        req_entry = dependency_state.get("requirements.txt")
        recorded_packages = req_entry.get("packages") if isinstance(req_entry, dict) else None
        if not isinstance(recorded_packages, dict):
            failures.append("security triage requirements.txt packages must be an object")
            recorded_packages = {}
        current_pins = requirement_pins(root / "requirements.txt", failures)
        for package, expected_version in V100_SECURITY_PINS.items():
            recorded_version = None
            for recorded_name, value in recorded_packages.items():
                if str(recorded_name).lower() == package:
                    recorded_version = value
                    break
            if recorded_version != expected_version:
                failures.append(
                    f"security triage recorded {package} version {recorded_version!r}; "
                    f"expected remediated v1.0.0 version {expected_version!r}"
                )
            if current_pins.get(package) != expected_version:
                failures.append(
                    f"requirements.txt {package} pin is {current_pins.get(package)!r}; "
                    f"expected remediated v1.0.0 version {expected_version!r}"
                )

    require_equal("release candidate version", candidate.get("version"), version, failures)
    dependency_security = candidate.get("dependency_security")
    if not isinstance(dependency_security, dict):
        failures.append("release candidate dependency_security must be an object")
    else:
        expected_triage_path = triage_rel.as_posix()
        if dependency_security.get("triage_receipt") != expected_triage_path:
            failures.append(
                "release candidate dependency_security.triage_receipt must point to "
                f"{expected_triage_path}"
            )
        if dependency_security.get("triage_schema_version") != 2:
            failures.append("release candidate triage_schema_version must be 2")
        if dependency_security.get("release_gate") != "PASS":
            failures.append("release candidate dependency security release_gate must be PASS")
        if dependency_security.get("runtime_high_critical_remaining") is not False:
            failures.append("release candidate runtime_high_critical_remaining must be false")
        remaining = dependency_security.get("remaining_open")
        if not isinstance(remaining, dict):
            failures.append("release candidate remaining_open must be an object")
        else:
            if remaining.get("critical") != 0 or remaining.get("high") != 0:
                failures.append(
                    "release candidate must record zero remaining CRITICAL/HIGH dependency alerts"
                )
        provenance = dependency_security.get("provenance")
        if not isinstance(provenance, dict):
            failures.append("release candidate dependency security provenance must be an object")
        elif provenance.get("inventory_source_head") != inventory_head:
            failures.append("release candidate inventory_source_head must match the triage receipt")

    if triage_rel.as_posix() not in release_notes:
        failures.append(
            f"release notes must reference security triage receipt {triage_rel.as_posix()}"
        )


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

    verify_security_triage(root, version, notes, failures)

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
