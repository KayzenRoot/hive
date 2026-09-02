from __future__ import annotations

import json

from scripts.review_evidence import SCHEMA_PATH, validate_manifest


def evidence_fixture() -> dict[str, object]:
    return {
        "schema_version": 1,
        "work_order": "WO-006",
        "repository": "KayzenRoot/hive",
        "pull_request": {"number": 42, "is_draft": True},
        "base": {"branch": "main", "sha": "a" * 40},
        "head": {"branch": "feature/wo006", "sha": "b" * 40},
        "generated_at": "2026-09-02T00:00:00Z",
        "changed_files": {"count": 1, "paths": ["backend/app/retrieval.py"]},
        "migrations": {"head": "0004_retrieval_lexical"},
        "checks": {
            "canonical": "PASS",
            "secrets": "PASS",
            "lint": "PASS",
            "typecheck": "PASS",
            "tests": "PASS",
            "build": "PASS",
            "integration": "PASS",
            "review_evidence": "PASS",
        },
        "benchmark": {
            "status": "PASS",
            "query_count": 4,
            "recall_at_1": 1.0,
            "recall_at_5": 1.0,
            "mrr": 1.0,
            "critical_context_misses": 0,
        },
        "review_state": {"status": "DRAFT", "merge_performed": False},
        "negative_scope": ["No merge or release was performed."],
    }


def test_review_evidence_schema_is_validated() -> None:
    manifest = evidence_fixture()
    validate_manifest(manifest)
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["properties"]["schema_version"]["const"] == 1


def test_review_evidence_rejects_merge_claim() -> None:
    manifest = evidence_fixture()
    manifest["review_state"] = {"status": "MERGED", "merge_performed": True}
    try:
        validate_manifest(manifest)
    except ValueError as error:
        assert "merge" in str(error)
    else:
        raise AssertionError("merged evidence must be rejected")
