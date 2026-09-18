from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.finalize_release_receipt import build_receipt, sha256_file


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def fixture(tmp_path: Path) -> tuple[Path, Path, list[Path]]:
    candidate = tmp_path / ".engineering/release/HIVE-V1.0.0-RELEASE-CANDIDATE.json"
    request = tmp_path / ".engineering/release/HIVE-V1.0.0-PUBLISH-REQUEST.json"
    write_json(
        candidate,
        {
            "status": "release-candidate",
            "release_published": False,
            "version": "1.0.0",
            "tag": "v1.0.0",
            "migration_head": "0007_telemetry_events",
            "product_baseline": {"status": "COMPLETE"},
            "wo024_lineage": {"pull_request": 95},
            "final_promotion_lineage": {"pull_request": 98},
            "dependency_security": {
                "release_gate": "PASS",
                "runtime_high_critical_remaining": False,
            },
            "assurance": {
                "ruleset": 21934284,
                "required_gates": ["Validate", "Integration health", "Review Evidence"],
            },
        },
    )
    write_json(
        request,
        {
            "status": "armed",
            "product": "HIVE",
            "version": "1.0.0",
            "tag": "v1.0.0",
            "work_order": "HIVE-REL-002",
            "issue": 115,
            "authorized_parent": "e7d661a7547fa12c5410c4e3334286f3bdc6686c",
        },
    )
    asset = tmp_path / "release-assets/hive-v1.0.0.zip"
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_bytes(b"hive-release")
    checksum = tmp_path / "release-assets/hive-v1.0.0.zip.sha256"
    checksum.write_text("checksum\n", encoding="utf-8")
    manifest = tmp_path / "release-assets/hive-v1.0.0.manifest.json"
    manifest.write_text("{}\n", encoding="utf-8")
    review = tmp_path / "review-bundles/HIVE-REVIEW.zip"
    review.parent.mkdir(parents=True, exist_ok=True)
    review.write_bytes(b"review")
    return candidate, request, [asset, checksum, manifest, review]


def build_valid(tmp_path: Path) -> dict[str, object]:
    candidate, request, assets = fixture(tmp_path)
    return build_receipt(
        candidate_path=candidate,
        publish_request_path=request,
        tag="v1.0.0",
        release_commit="1" * 40,
        tag_object="2" * 40,
        release_url="https://github.com/KayzenRoot/hive/releases/tag/v1.0.0",
        published_at="2026-09-18T03:00:00Z",
        publisher_run_id=123,
        post_merge_ci_run_id=456,
        asset_paths=assets,
    )


def test_build_receipt_binds_publication_and_artifacts(tmp_path: Path) -> None:
    candidate, _, _ = fixture(tmp_path)
    receipt = build_valid(tmp_path)
    assert receipt["status"] == "published"
    assert receipt["release_published"] is True
    assert receipt["tag"] == "v1.0.0"
    assert receipt["release_commit"] == "1" * 40
    assert receipt["tag_object"] == "2" * 40
    assert receipt["publisher_workflow_run"] == 123
    assert receipt["post_merge_ci_run"] == 456
    assert receipt["candidate_receipt"]["sha256"] == sha256_file(candidate)
    assert {item["name"] for item in receipt["artifacts"]} == {
        "hive-v1.0.0.zip",
        "hive-v1.0.0.zip.sha256",
        "hive-v1.0.0.manifest.json",
        "HIVE-REVIEW.zip",
    }


def test_tag_must_match_candidate_version(tmp_path: Path) -> None:
    candidate, request, assets = fixture(tmp_path)
    with pytest.raises(ValueError, match="tag must match"):
        build_receipt(
            candidate_path=candidate,
            publish_request_path=request,
            tag="v1.0.1",
            release_commit="1" * 40,
            tag_object="2" * 40,
            release_url="https://github.com/KayzenRoot/hive/releases/tag/v1.0.1",
            published_at="2026-09-18T03:00:00Z",
            publisher_run_id=123,
            post_merge_ci_run_id=456,
            asset_paths=assets,
        )


def test_security_gate_fails_closed(tmp_path: Path) -> None:
    candidate, request, assets = fixture(tmp_path)
    data = json.loads(candidate.read_text(encoding="utf-8"))
    data["dependency_security"]["release_gate"] = "BLOCKED"
    write_json(candidate, data)
    with pytest.raises(ValueError, match="release gate"):
        build_receipt(
            candidate_path=candidate,
            publish_request_path=request,
            tag="v1.0.0",
            release_commit="1" * 40,
            tag_object="2" * 40,
            release_url="https://github.com/KayzenRoot/hive/releases/tag/v1.0.0",
            published_at="2026-09-18T03:00:00Z",
            publisher_run_id=123,
            post_merge_ci_run_id=456,
            asset_paths=assets,
        )


def test_invalid_sha_or_empty_assets_fail_closed(tmp_path: Path) -> None:
    candidate, request, assets = fixture(tmp_path)
    with pytest.raises(ValueError, match="release_commit"):
        build_receipt(
            candidate_path=candidate,
            publish_request_path=request,
            tag="v1.0.0",
            release_commit="not-a-sha",
            tag_object="2" * 40,
            release_url="https://github.com/KayzenRoot/hive/releases/tag/v1.0.0",
            published_at="2026-09-18T03:00:00Z",
            publisher_run_id=123,
            post_merge_ci_run_id=456,
            asset_paths=assets,
        )
    with pytest.raises(ValueError, match="at least one artifact"):
        build_receipt(
            candidate_path=candidate,
            publish_request_path=request,
            tag="v1.0.0",
            release_commit="1" * 40,
            tag_object="2" * 40,
            release_url="https://github.com/KayzenRoot/hive/releases/tag/v1.0.0",
            published_at="2026-09-18T03:00:00Z",
            publisher_run_id=123,
            post_merge_ci_run_id=456,
            asset_paths=[],
        )


def test_duplicate_asset_names_fail_closed(tmp_path: Path) -> None:
    candidate, request, assets = fixture(tmp_path)
    duplicate = tmp_path / "other" / assets[0].name
    duplicate.parent.mkdir(parents=True, exist_ok=True)
    duplicate.write_bytes(b"different")
    with pytest.raises(ValueError, match="duplicate release asset"):
        build_receipt(
            candidate_path=candidate,
            publish_request_path=request,
            tag="v1.0.0",
            release_commit="1" * 40,
            tag_object="2" * 40,
            release_url="https://github.com/KayzenRoot/hive/releases/tag/v1.0.0",
            published_at="2026-09-18T03:00:00Z",
            publisher_run_id=123,
            post_merge_ci_run_id=456,
            asset_paths=[*assets, duplicate],
        )
