from __future__ import annotations

import json
from pathlib import Path

from scripts.review_bundle import deterministic_zip
from scripts.review_evidence import (
    SCHEMA_PATH,
    manifest_log,
    summary_markdown,
    validate_manifest,
    write_consolidated_artifact,
)
from scripts.review_pr_body import render_body


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
            "validation": "PASS",
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
            "two_run_reproducibility": True,
            "cross_project_isolation": True,
            "redis_restart": True,
            "api_restart": True,
        },
        "evidence": {
            "tests": {
                "status": "PASS",
                "backend": {"status": "PASS", "passed": 72, "failed": 0, "skipped": 0, "errors": 0},
                "dashboard": {"status": "PASS", "passed": 7, "failed": 0, "skipped": 0},
            },
            "integration": {
                "status": "PASS",
                "project_registry": {"status": "PASS", "evidence_file": "project-registry.log"},
                "task_intake_cas": {"status": "PASS", "evidence_file": "task-intake.log"},
                "repository_indexing": {
                    "status": "PASS",
                    "evidence_file": "repository-indexing.log",
                },
                "retrieval": {"status": "PASS", "evidence_file": "retrieval.log"},
                "redis_restart": {"status": "PASS"},
                "api_restart": {"status": "PASS"},
                "benchmark_gate": {
                    "status": "PASS",
                    "query_count": 4,
                    "recall_at_1": 1.0,
                    "recall_at_5": 1.0,
                    "mrr": 1.0,
                    "critical_context_misses": 0,
                    "two_run_reproducibility": True,
                },
                "cross_project_retrieval": {"status": "PASS"},
                "integrity_tests": {
                    "head_race_rejected": True,
                    "inventory_race_rejected": True,
                    "prior_corpus_preserved": True,
                    "duplicate_task_candidate_collapsed": True,
                    "task_provenance_preserved": True,
                    "cross_project_duplicate_isolation": True,
                },
            },
            "security": {
                "status": "PASS",
                "canonical_verifier": {"status": "PASS"},
                "secret_scan": {"status": "PASS"},
                "project_isolation": {"status": "PASS"},
                "cross_project_retrieval": {"status": "PASS"},
                "sql_query_parameterization": {"status": "PASS", "basis": "test"},
                "source_staleness_fail_closed": {"status": "PASS"},
            },
            "warnings": {"status": "NONE", "count": 0, "items": []},
        },
        "governance": {
            "status": "PASS",
            "ruleset": {
                "id": 21934284,
                "name": "Protect main",
                "enforcement": "active",
                "required_contexts": ["Validate", "Integration health", "Review Evidence"],
                "required_review_thread_resolution": True,
                "allowed_merge_methods": ["squash"],
                "bypass_actors": [],
                "deletion_protection": True,
                "non_fast_forward_protection": True,
                "pull_request_required": True,
                "strict_required_status_checks": True,
            },
            "repository_merge_settings": {
                "allow_squash_merge": True,
                "allow_merge_commit": False,
                "allow_rebase_merge": False,
                "delete_branch_on_merge": True,
                "allow_auto_merge": False,
            },
        },
        "artifact": {
            "name": "hive-review-evidence-WO-006-head",
            "format": "consolidated-directory",
            "bounded": True,
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


def test_review_manifest_is_emitted_between_stable_log_delimiters() -> None:
    rendered = manifest_log(evidence_fixture())
    begin, payload, end = rendered.split("\n", 2)[0], rendered.split("\n", 1)[1], ""
    assert begin == "HIVE_REVIEW_MANIFEST_BEGIN"
    json_payload, end = payload.rsplit("\nHIVE_REVIEW_MANIFEST_END", 1)
    assert end == ""
    assert json.loads(json_payload)["evidence"]["tests"]["backend"]["passed"] == 72


def test_review_bundle_has_only_generic_fallback_implementation() -> None:
    source = (Path(__file__).parents[2] / "scripts" / "review_bundle.py").read_text(
        encoding="utf-8"
    )
    assert "legacy_main" not in source
    assert "Prompt #001" not in source
    assert "Prompt #002" not in source
    assert "Prompt #003" not in source


def test_pr_body_template_contains_work_order_marker_and_sol_state() -> None:
    body = render_body(
        work_order="WO-006",
        pr_number=25,
        branch="feature/wo006-retrieval-lexical",
        base_sha="a" * 40,
        head_sha="b" * 40,
        artifact_name="hive-review-evidence-WO-006-b",
        ruleset_before="old",
        ruleset_after="new",
        merge_before="old",
        merge_after="new",
    )
    assert body.startswith("<!-- HIVE-WORK-ORDER: WO-006 -->")
    assert body.count("Sol Review State: AWAITING_SOL") == 1
    assert body.count("## ") == 20


def test_consolidated_artifact_contains_the_required_audit_inputs(tmp_path: Path) -> None:
    manifest = evidence_fixture()
    write_consolidated_artifact(tmp_path, manifest, "summary\n")
    expected = {
        "changed-files.txt",
        "migration-head.txt",
        "validation-summary.txt",
        "validation-results.txt",
        "integration-summary.json",
        "integration-results.txt",
        "benchmark.json",
        "failure-diagnostics.txt",
        "review-manifest.json",
        "review-summary.md",
        "github-governance.json",
    }
    assert expected <= {path.name for path in tmp_path.iterdir()}


def test_sticky_summary_has_required_review_fields() -> None:
    summary = summary_markdown(evidence_fixture(), "https://example.invalid/run/1")
    for field in (
        "Work Order",
        "Exact HEAD SHA",
        "Validate result",
        "Integration health result",
        "Review Evidence result",
        "Migration head",
        "Backend tests",
        "Dashboard tests",
        "Canonical verifier",
        "Secret scan",
        "Consolidated artifact",
        "Workflow run URL",
        "Sol Review State: AWAITING_SOL",
    ):
        assert field in summary


def test_generic_bundle_zip_is_byte_deterministic(tmp_path: Path) -> None:
    files = {"z.txt": "last\n", "a.txt": "first\n"}
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    assert deterministic_zip(first, files) == deterministic_zip(second, files)
    assert first.read_bytes() == second.read_bytes()
