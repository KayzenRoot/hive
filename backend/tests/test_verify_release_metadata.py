from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.verify_release_metadata import verify_release_metadata

CANDIDATE_STATUS = "Release candidate (not published)."
HISTORICAL_NOTE = """# HIVE v0.0.1-bootstrap draft release notes

Status: draft pre-release. Do not publish before Sol approval.

## Included

- Historical bootstrap evidence retained unchanged.
"""


def write_text(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(root: Path, relative: str, document: dict[str, object]) -> None:
    write_text(root, relative, json.dumps(document, indent=2) + "\n")


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_release_tree(
    root: Path,
    *,
    version: str = "1.0.0",
    status: str = CANDIDATE_STATUS,
) -> None:
    tag = f"v{version}"
    write_text(root, "VERSION", f"{version}\n")
    write_text(
        root,
        "backend/app/__init__.py",
        f'"""HIVE API package."""\n\n__version__ = "{version}"\n',
    )
    write_text(
        root,
        "backend/app/config.py",
        f'class Settings:\n    version: str = "{version}"\n',
    )
    write_json(
        root,
        "dashboard/package.json",
        {"name": "hive-dashboard", "version": version},
    )
    write_json(
        root,
        "dashboard/package-lock.json",
        {
            "name": "hive-dashboard",
            "version": version,
            "packages": {"": {"name": "hive-dashboard", "version": version}},
        },
    )
    write_text(
        root,
        "requirements.txt",
        "\n".join(
            (
                "fastapi==0.133.0",
                "starlette==1.3.1",
                "python-multipart==0.0.31",
                "Mako==1.3.12",
                "",
            )
        ),
    )
    write_text(root, "requirements-dev.txt", "-r requirements.txt\npytest==8.3.4\n")
    triage_path = f".engineering/release/HIVE-V{version}-SECURITY-TRIAGE.json"
    triage = {
        "schema_version": 2,
        "inventory_source_head": "3" * 40,
        "repository": "KayzenRoot/hive",
        "release_version": version,
        "critical_high_applicable_open": 0,
        "runtime_high_critical_remaining": False,
        "release_gate": "PASS",
        "candidate_dependency_state": {
            "requirements.txt": {
                "sha256": sha256_path(root / "requirements.txt"),
                "packages": {
                    "fastapi": "0.133.0",
                    "starlette": "1.3.1",
                    "python-multipart": "0.0.31",
                    "Mako": "1.3.12",
                },
            },
            "requirements-dev.txt": {
                "sha256": sha256_path(root / "requirements-dev.txt"),
            },
            "dashboard/package-lock.json": {
                "sha256": sha256_path(root / "dashboard/package-lock.json"),
            },
        },
    }
    write_json(root, triage_path, triage)
    write_json(
        root,
        f".engineering/release/HIVE-V{version}-RELEASE-CANDIDATE.json",
        {
            "version": version,
            "release_published": False,
            "dependency_security": {
                "triage_receipt": triage_path,
                "triage_schema_version": 2,
                "release_gate": "PASS",
                "runtime_high_critical_remaining": False,
                "remaining_open": {"critical": 0, "high": 0, "moderate": 3, "low": 0},
                "provenance": {"inventory_source_head": "3" * 40},
            },
        },
    )
    write_text(
        root,
        f"docs/releases/{tag}.md",
        f"# HIVE {tag} release\n\nStatus: {status}\n\nSecurity: {triage_path}\n",
    )
    write_text(root, "docs/releases/v0.0.1-bootstrap.md", HISTORICAL_NOTE)
    write_text(
        root,
        "CHANGELOG.md",
        f"# Changelog\n\n## [Unreleased]\n\n## [{version}] - 2026-09-17\n\n- Stable release.\n\n"
        "## 0.0.1-bootstrap - Released 2026-08-31\n\n- Historical bootstrap entry.\n",
    )
    write_text(root, "README.md", f"# HIVE\n\nTarget stable release: v{version}\n")


def test_coherent_release_tree_passes(tmp_path: Path) -> None:
    build_release_tree(tmp_path)
    assert verify_release_metadata(tmp_path) == []


def test_v101_release_candidate_metadata_is_supported(tmp_path: Path) -> None:
    build_release_tree(tmp_path, version="1.0.1")
    assert verify_release_metadata(tmp_path) == []


def test_non_stable_version_fails_closed(tmp_path: Path) -> None:
    build_release_tree(tmp_path)
    write_text(tmp_path, "VERSION", "1.0.0-rc.1\n")
    failures = verify_release_metadata(tmp_path)
    assert any("strict stable SemVer" in failure for failure in failures)


def test_backend_dashboard_and_lock_version_drift_fails(tmp_path: Path) -> None:
    build_release_tree(tmp_path)
    write_text(
        tmp_path,
        "backend/app/config.py",
        'class Settings:\n    version: str = "0.0.1-bootstrap"\n',
    )
    write_json(tmp_path, "dashboard/package.json", {"name": "hive-dashboard", "version": "0.9.9"})
    write_json(
        tmp_path,
        "dashboard/package-lock.json",
        {
            "name": "hive-dashboard",
            "version": "1.0.0",
            "packages": {"": {"name": "hive-dashboard", "version": "0.9.9"}},
        },
    )
    failures = verify_release_metadata(tmp_path)
    assert any("backend/app/config.py version" in failure for failure in failures)
    assert any("dashboard/package.json version" in failure for failure in failures)
    assert any("packages root version" in failure for failure in failures)


def test_missing_release_notes_and_changelog_drift_fail_closed(tmp_path: Path) -> None:
    build_release_tree(tmp_path)
    (tmp_path / "docs/releases/v1.0.0.md").unlink()
    write_text(
        tmp_path,
        "CHANGELOG.md",
        "# Changelog\n\n## [1.0.0]\n\n- First.\n\n## [1.0.0]\n\n- Duplicate.\n",
    )
    failures = verify_release_metadata(tmp_path)
    assert any("missing required file" in failure for failure in failures)
    assert any("duplicate" in failure for failure in failures)


def test_missing_changelog_heading_fails_closed(tmp_path: Path) -> None:
    build_release_tree(tmp_path)
    write_text(tmp_path, "CHANGELOG.md", "# Changelog\n\n## [Unreleased]\n\n- Only unreleased.\n")
    failures = verify_release_metadata(tmp_path)
    assert any("missing the release heading" in failure for failure in failures)


def test_readme_identity_drift_and_stale_bootstrap_fail_closed(tmp_path: Path) -> None:
    build_release_tree(tmp_path)
    write_text(
        tmp_path,
        "README.md",
        "# HIVE\n\nLatest stable release: v1.0.0\n\nThe bootstrap target is v0.0.1-bootstrap.\n",
    )
    failures = verify_release_metadata(tmp_path)
    assert any("target stable identity" in failure for failure in failures)
    assert any("before publication" in failure for failure in failures)
    assert any("stale bootstrap identity" in failure for failure in failures)


def test_release_note_must_declare_explicit_candidate_or_published_status(tmp_path: Path) -> None:
    build_release_tree(tmp_path, status="draft pre-release.")
    failures = verify_release_metadata(tmp_path)
    assert any("must be 'Release candidate' or 'Published'" in failure for failure in failures)


def test_published_claim_requires_final_receipt_evidence(tmp_path: Path) -> None:
    build_release_tree(tmp_path, status="Published.")
    failures = verify_release_metadata(tmp_path)
    assert any("missing required file" in failure for failure in failures)

    write_json(
        tmp_path,
        ".engineering/release/HIVE-V1.0.0-RELEASE-RECEIPT.json",
        {"release_published": True, "tag": "v1.0.0", "release_url": "https://example.invalid"},
    )
    assert any(
        "published stable identity" in failure for failure in verify_release_metadata(tmp_path)
    )

    write_text(tmp_path, "README.md", "# HIVE\n\nLatest stable release: v1.0.0\n")
    assert verify_release_metadata(tmp_path) == []


def test_historical_bootstrap_notes_remain_historical_and_are_not_current(
    tmp_path: Path,
) -> None:
    build_release_tree(tmp_path)
    historical = (tmp_path / "docs/releases/v0.0.1-bootstrap.md").read_text(encoding="utf-8")
    assert "draft pre-release" in historical
    assert verify_release_metadata(tmp_path) == []

    write_text(tmp_path, "docs/releases/v0.0.1-bootstrap.md", "# HIVE v0.0.1-bootstrap\n")
    (tmp_path / "docs/releases/v1.0.0.md").unlink()
    failures = verify_release_metadata(tmp_path)
    assert any("v1.0.0.md" in failure for failure in failures)


def test_security_triage_manifest_hash_drift_fails_closed(tmp_path: Path) -> None:
    build_release_tree(tmp_path)
    write_text(
        tmp_path,
        "requirements.txt",
        "fastapi==0.133.0\nstarlette==1.3.1\npython-multipart==0.0.31\nMako==1.3.12\n# drift\n",
    )
    failures = verify_release_metadata(tmp_path)
    assert any("requirements.txt sha256 drift" in failure for failure in failures)


def test_security_triage_wrong_remediated_version_fails_closed(tmp_path: Path) -> None:
    build_release_tree(tmp_path)
    triage_path = tmp_path / ".engineering/release/HIVE-V1.0.0-SECURITY-TRIAGE.json"
    triage = json.loads(triage_path.read_text(encoding="utf-8"))
    triage["candidate_dependency_state"]["requirements.txt"]["packages"]["starlette"] = "0.45.3"
    write_json(tmp_path, ".engineering/release/HIVE-V1.0.0-SECURITY-TRIAGE.json", triage)
    failures = verify_release_metadata(tmp_path)
    assert any("expected remediated v1.0.0 version" in failure for failure in failures)


def test_security_triage_release_gate_and_high_state_fail_closed(tmp_path: Path) -> None:
    build_release_tree(tmp_path)
    triage_path = tmp_path / ".engineering/release/HIVE-V1.0.0-SECURITY-TRIAGE.json"
    triage = json.loads(triage_path.read_text(encoding="utf-8"))
    triage["release_gate"] = "BLOCKED"
    triage["critical_high_applicable_open"] = 1
    triage["runtime_high_critical_remaining"] = True
    write_json(tmp_path, ".engineering/release/HIVE-V1.0.0-SECURITY-TRIAGE.json", triage)
    failures = verify_release_metadata(tmp_path)
    assert any("release_gate must be PASS" in failure for failure in failures)
    assert any("zero applicable unresolved CRITICAL/HIGH" in failure for failure in failures)
    assert any("runtime_high_critical_remaining must be false" in failure for failure in failures)


def test_security_triage_missing_or_wrong_candidate_binding_fails_closed(tmp_path: Path) -> None:
    build_release_tree(tmp_path)
    (tmp_path / ".engineering/release/HIVE-V1.0.0-SECURITY-TRIAGE.json").unlink()
    failures = verify_release_metadata(tmp_path)
    assert any("HIVE-V1.0.0-SECURITY-TRIAGE.json" in failure for failure in failures)

    build_release_tree(tmp_path)
    candidate_path = tmp_path / ".engineering/release/HIVE-V1.0.0-RELEASE-CANDIDATE.json"
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate["dependency_security"]["triage_receipt"] = ".engineering/release/wrong.json"
    write_json(tmp_path, ".engineering/release/HIVE-V1.0.0-RELEASE-CANDIDATE.json", candidate)
    failures = verify_release_metadata(tmp_path)
    assert any("triage_receipt must point" in failure for failure in failures)


def test_security_triage_rejects_ambiguous_generated_for_head(tmp_path: Path) -> None:
    build_release_tree(tmp_path)
    triage_path = tmp_path / ".engineering/release/HIVE-V1.0.0-SECURITY-TRIAGE.json"
    triage = json.loads(triage_path.read_text(encoding="utf-8"))
    triage["generated_for_head"] = "3" * 40
    write_json(tmp_path, ".engineering/release/HIVE-V1.0.0-SECURITY-TRIAGE.json", triage)
    failures = verify_release_metadata(tmp_path)
    assert any("generated_for_head" in failure for failure in failures)


def test_security_triage_inventory_source_must_match_candidate_receipt(tmp_path: Path) -> None:
    build_release_tree(tmp_path)
    candidate_path = tmp_path / ".engineering/release/HIVE-V1.0.0-RELEASE-CANDIDATE.json"
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate["dependency_security"]["provenance"]["inventory_source_head"] = "4" * 40
    write_json(tmp_path, ".engineering/release/HIVE-V1.0.0-RELEASE-CANDIDATE.json", candidate)
    failures = verify_release_metadata(tmp_path)
    assert any("inventory_source_head must match" in failure for failure in failures)
