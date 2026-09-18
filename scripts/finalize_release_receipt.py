#!/usr/bin/env python3
"""Build the immutable post-publication HIVE release receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

HEX40 = re.compile(r"^[0-9a-f]{40}$")
SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def artifact_records(paths: list[Path]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for path in sorted(paths, key=lambda item: item.name):
        if not path.is_file():
            continue
        if path.name in seen:
            raise ValueError(f"duplicate release asset name: {path.name}")
        seen.add(path.name)
        records.append(
            {
                "name": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    if not records:
        raise ValueError("final release receipt requires at least one artifact")
    return records


def build_receipt(
    *,
    candidate_path: Path,
    publish_request_path: Path,
    tag: str,
    release_commit: str,
    tag_object: str,
    release_url: str,
    published_at: str,
    publisher_run_id: int,
    post_merge_ci_run_id: int,
    asset_paths: list[Path],
) -> dict[str, object]:
    candidate = read_json(candidate_path)
    publish_request = read_json(publish_request_path)
    version = candidate.get("version")
    if not isinstance(version, str) or SEMVER.fullmatch(version) is None:
        raise ValueError("candidate receipt must contain a stable SemVer version")
    if tag != f"v{version}" or candidate.get("tag") != tag:
        raise ValueError("release tag must match the candidate version exactly")
    if publish_request.get("version") != version or publish_request.get("tag") != tag:
        raise ValueError("publish request version/tag must match the candidate")
    if publish_request.get("status") != "armed":
        raise ValueError("publish request must be armed")
    if candidate.get("status") != "release-candidate":
        raise ValueError("candidate receipt must remain release-candidate evidence")
    if candidate.get("release_published") is not False:
        raise ValueError("candidate receipt must not pre-claim publication")
    security = candidate.get("dependency_security")
    if not isinstance(security, dict) or security.get("release_gate") != "PASS":
        raise ValueError("dependency-security release gate must be PASS")
    if security.get("runtime_high_critical_remaining") is not False:
        raise ValueError("runtime HIGH/CRITICAL dependency blocker remains")
    for label, value in (
        ("release_commit", release_commit),
        ("tag_object", tag_object),
    ):
        if HEX40.fullmatch(value) is None:
            raise ValueError(f"{label} must be a lowercase 40-hex SHA")
    if not release_url.startswith("https://github.com/KayzenRoot/hive/releases/"):
        raise ValueError("release_url must identify the canonical HIVE GitHub Release")
    if not published_at:
        raise ValueError("published_at is required")
    if publisher_run_id <= 0 or post_merge_ci_run_id <= 0:
        raise ValueError("workflow run identifiers must be positive")

    return {
        "receipt_version": 1,
        "status": "published",
        "release_published": True,
        "product": "HIVE",
        "version": version,
        "tag": tag,
        "release_commit": release_commit,
        "tag_object": tag_object,
        "release_url": release_url,
        "published_at": published_at,
        "publisher_workflow_run": publisher_run_id,
        "post_merge_ci_run": post_merge_ci_run_id,
        "candidate_receipt": {
            "path": candidate_path.as_posix(),
            "sha256": sha256_file(candidate_path),
        },
        "publish_request": {
            "path": publish_request_path.as_posix(),
            "sha256": sha256_file(publish_request_path),
            "work_order": publish_request.get("work_order"),
            "issue": publish_request.get("issue"),
            "authorized_parent": publish_request.get("authorized_parent"),
        },
        "artifacts": artifact_records(asset_paths),
        "migration_head": candidate.get("migration_head"),
        "product_baseline": candidate.get("product_baseline"),
        "wo024_lineage": candidate.get("wo024_lineage"),
        "final_promotion_lineage": candidate.get("final_promotion_lineage"),
        "dependency_security": security,
        "assurance": {
            "ruleset": candidate.get("assurance", {}).get("ruleset"),
            "required_gates": candidate.get("assurance", {}).get("required_gates"),
            "publisher": ".github/workflows/release-publisher.yml",
            "final_receipt_generator": "scripts/finalize_release_receipt.py",
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--publish-request", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--release-commit", required=True)
    parser.add_argument("--tag-object", required=True)
    parser.add_argument("--release-url", required=True)
    parser.add_argument("--published-at", required=True)
    parser.add_argument("--publisher-run-id", type=int, required=True)
    parser.add_argument("--post-merge-ci-run-id", type=int, required=True)
    parser.add_argument("--asset-dir", type=Path, required=True)
    parser.add_argument("--review-bundle-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    asset_paths = list(args.asset_dir.glob("*")) + list(args.review_bundle_dir.glob("*"))
    receipt = build_receipt(
        candidate_path=args.candidate,
        publish_request_path=args.publish_request,
        tag=args.tag,
        release_commit=args.release_commit,
        tag_object=args.tag_object,
        release_url=args.release_url,
        published_at=args.published_at,
        publisher_run_id=args.publisher_run_id,
        post_merge_ci_run_id=args.post_merge_ci_run_id,
        asset_paths=asset_paths,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
