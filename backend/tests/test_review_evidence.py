from __future__ import annotations

import hashlib
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
import scripts.review_evidence as review_evidence
from scripts.capture_service_logs import DEFAULT_COMMAND, capture_service_logs, redact_service_logs
from scripts.review_bundle import deterministic_zip
from scripts.review_evidence import (
    ACCE_STORAGE_POLICY_EVIDENCE_FILE,
    ACCE_STORAGE_POLICY_EVIDENCE_VERSION,
    ACCE_STORAGE_POLICY_REQUIRED_FIELDS,
    CONTEXT_MANAGER_REQUIRED_FIELDS,
    MCP_CORE_SURFACE_EVIDENCE_FILE,
    MCP_CORE_SURFACE_EVIDENCE_VERSION,
    MCP_CORE_SURFACE_FALSE_FIELDS,
    MCP_CORE_SURFACE_INTEGER_FIELDS,
    MCP_CORE_SURFACE_MAX_REGISTERED_PROJECT_COUNT,
    MCP_CORE_SURFACE_REGISTERED_PROJECT_COUNT,
    MCP_CORE_SURFACE_TOOLS,
    MCP_CORE_SURFACE_TRUE_FIELDS,
    SCHEMA_PATH,
    WO008_G1_ALLOWED_PATHS,
    WO008_G1_BASE_SHA,
    WO009_BASE_SHA,
    WO010_BASE_SHA,
    WO010_G1_ALLOWED_PATHS,
    WO010_G1_BASE_SHA,
    WO012P_G1_ALLOWED_PATHS,
    WO012P_G1_BASE_SHA,
    WO012P_PROMOTION_ALLOWED_PATHS,
    WO013_ALLOWED_PATHS,
    WO013_BASE_SHA,
    WO013P_G1_ALLOWED_PATHS,
    WO013P_G1_BASE_SHA,
    WO013P_PROMOTION_ALLOWED_PATHS,
    WO014_ALLOWED_PATHS,
    WO014_BASE_SHA,
    WO014_C1_CORRECTED_HEAD,
    WO014_C2_ALLOWED_PATHS,
    WO014_C2_BASE_SHA,
    WO014_C2_WORK_ORDER,
    WO014P_G1_ALLOWED_PATHS,
    WO014P_G1_BASE_SHA,
    WO014P_G1_WORK_ORDER,
    WO014P_PROMOTION_ALLOWED_PATHS,
    WO014P_WORK_ORDER,
    WO015_G1_ALLOWED_PATHS,
    WO015_G1_BASE_SHA,
    WO015_G1_WORK_ORDER,
    WO015_MEMORY_EVIDENCE_FILE,
    WO015_MEMORY_INTEGER_FIELDS,
    WO015_MEMORY_REQUIRED_FIELDS,
    WO015_WORK_ORDER,
    WO015P_G1_ALLOWED_PATHS,
    WO015P_G1_BASE_SHA,
    WO015P_G1_WORK_ORDER,
    WO015P_PROMOTION_ALLOWED_PATHS,
    WO015P_WORK_ORDER,
    WO016_APPROVED_LINEAGE_STATEMENT_PREFIX,
    WO016_APPROVED_POST_MERGE_CI_RUN,
    WO016_APPROVED_PRODUCT_BASE_SHA,
    WO016_APPROVED_PRODUCT_HEAD,
    WO016_APPROVED_SOL_REVIEW_ID,
    WO016_APPROVED_SQUASH_MERGE_SHA,
    WO016_G1_ALLOWED_PATHS,
    WO016_G1_BASE_SHA,
    WO016_G1_WORK_ORDER,
    WO016_PRODUCT_ALLOWED_PATHS,
    WO016_WORK_ORDER,
    WO016P_G1_ALLOWED_PATHS,
    WO016P_G1_BASE_SHA,
    WO016P_G1_WORK_ORDER,
    WO016P_PROMOTION_ALLOWED_PATHS,
    WO016P_WORK_ORDER,
    WO017_G1_ALLOWED_PATHS,
    WO017_G1_BASE_SHA,
    WO017_G1_WORK_ORDER,
    WO017_PRODUCT_ALLOWED_PATHS,
    WO017_WORK_ORDER,
    acce_storage_policy_evidence,
    authorize_merge_action,
    auto_merge_evidence,
    canonical_change_evidence,
    canonical_change_statement,
    context_manager_evidence,
    dashboard_counts,
    governance_evidence,
    junit_counts,
    manifest_log,
    mcp_surface_evidence,
    memory_lifecycle_evidence,
    parse_authorized_base_marker,
    parse_wo016_approved_lineage_statement,
    parse_work_order_marker,
    require_current_work_order_authorization,
    require_hive_final_handoff,
    require_supported_work_order,
    require_wo008_c1_evidence,
    require_wo008_g1_scope,
    require_wo009_context_manager_evidence,
    require_wo009_scope,
    require_wo010_g1_scope,
    require_wo010_progressive_disclosure_evidence,
    require_wo010_scope,
    require_wo011_context_manager_evidence,
    require_wo012_context_manager_evidence,
    require_wo012p_checkpoint_semantics,
    require_wo012p_g1_scope,
    require_wo012p_manifest_contract,
    require_wo012p_scope,
    require_wo013_context_manager_evidence,
    require_wo013_scope,
    require_wo013p_checkpoint_semantics,
    require_wo013p_g1_scope,
    require_wo013p_scope,
    require_wo014_c2_scope,
    require_wo014_provider_prompt_cache_evidence,
    require_wo014_scope,
    require_wo014p_checkpoint_semantics,
    require_wo014p_g1_scope,
    require_wo014p_scope,
    require_wo015_g1_scope,
    require_wo015_memory_evidence,
    require_wo015_scope,
    require_wo015p_checkpoint_semantics,
    require_wo015p_g1_scope,
    require_wo015p_scope,
    require_wo016_approved_lineage_result,
    require_wo016_g1_scope,
    require_wo016_scope,
    require_wo016_storage_evidence,
    require_wo016p_checkpoint_semantics,
    require_wo016p_g1_scope,
    require_wo016p_manifest_contract,
    require_wo016p_scope,
    require_wo017_g1_scope,
    require_wo017_mcp_evidence,
    require_wo017_scope,
    summary_markdown,
    validate_manifest,
    verify_native_auto_merge,
    verify_wo014_c2_governance_contract,
    verify_wo014p_g1_governance_contract,
    verify_wo015_g1_governance_contract,
    verify_wo015p_g1_governance_contract,
    verify_wo016_approved_lineage,
    verify_wo016_g1_governance_contract,
    verify_wo016p_g1_governance_contract,
    verify_wo016p_governance_contract,
    verify_wo017_g1_governance_contract,
    verify_wo017_governance_contract,
    warnings_evidence,
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
                "context_manager": {
                    "status": "PASS",
                    "evidence_file": "context-manager.json",
                    "checkpoint_first": True,
                    "governance_project_scoped": True,
                    "task_project_scoped": True,
                    "reranked_retrieval_used": True,
                    "provenance_preserved": True,
                    "deterministic_two_run": True,
                    "bounded": True,
                    "cross_project_isolation": True,
                    "missing_governance_fail_closed": True,
                    "head_race_fail_closed": True,
                    "redis_restart_rebuild": True,
                    "api_restart_rebuild": True,
                    "mandatory_governance_coverage": True,
                    "mandatory_governance_kind_sequence": [
                        "CHECKPOINT",
                        "SCOPE",
                        "DEFINITION_OF_DONE",
                        "ARCHITECTURE",
                        "DECISIONS",
                    ],
                    "llm_calls": 0,
                },
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
            "ruleset_unchanged": True,
            "pull_request": {
                "number": 42,
                "state": "open",
                "is_draft": True,
                "head_sha": "b" * 40,
                "base_sha": "a" * 40,
                "auto_merge_armed": True,
                "auto_merge_method": "squash",
                "auto_merge": {
                    "armed": True,
                    "method": "squash",
                    "enabled_by_login": "KayzenRoot",
                    "enabled_by_type": "User",
                    "user_owned": True,
                },
            },
        },
        "artifact": {
            "name": "hive-review-evidence-WO-006-head",
            "format": "consolidated-directory",
            "bounded": True,
        },
        "review_state": {
            "status": "DRAFT",
            "merge_performed": False,
            "auto_merge_owner_login": "KayzenRoot",
            "auto_merge_owner_type": "User",
            "auto_merge_user_owned": True,
        },
        "negative_scope": [
            "No merge or release was performed.",
            canonical_change_statement(canonical_change_evidence(["backend/app/main.py"])),
        ],
    }


def memory_evidence_fixture(
    migration_head: str = "0006_memory_lifecycle_provenance",
) -> dict[str, object]:
    evidence: dict[str, object] = {
        "status": "PASS",
        "evidence_file": WO015_MEMORY_EVIDENCE_FILE,
        **{field: True for field in WO015_MEMORY_REQUIRED_FIELDS},
        **{field: 1 for field in WO015_MEMORY_INTEGER_FIELDS},
        "memory_project_count": 2,
        "memory_history_versions": 2,
        "memory_secret_leaks": 0,
        "memory_llm_calls": 0,
        "memory_provider_calls": 0,
        "memory_evidence_version": "memory-lifecycle-provenance-v1",
        "memory_migration_head": migration_head,
    }
    return evidence


def acce_storage_evidence_fixture() -> dict[str, object]:
    return {
        "status": "PASS",
        "evidence_file": ACCE_STORAGE_POLICY_EVIDENCE_FILE,
        "acce_evidence_version": ACCE_STORAGE_POLICY_EVIDENCE_VERSION,
        "storage_policy_version": "acce-policy-v1",
        **{field: True for field in ACCE_STORAGE_POLICY_REQUIRED_FIELDS},
        "canonical_source_loss_count": 0,
        "llm_calls": 0,
        "provider_calls": 0,
        "dedup_logical_bytes": 300,
        "dedup_unique_logical_bytes": 200,
        "dedup_savings_bytes": 100,
        "zstd_supported_level_min": 1,
        "zstd_supported_level_max": 22,
        "policy_mapping": {"HOT": "hot-fast", "WARM": "warm-balanced", "COLD": "cold-dense"},
        "selection_rationale": (
            "Measured bounded matrix selects profiles by observed compression and access policy."
        ),
        "benchmark_matrix": [
            {
                "tier": "HOT",
                "profile_id": "hot-fast",
                "zstd_level": 1,
                "logical_input_bytes": 100,
                "physical_bytes": 50,
                "compression_ratio": 0.5,
                "compression_savings_bytes": 50,
                "compression_expands": False,
                "round_trip_identity": True,
                "measurement_samples": 3,
                "benchmark_measured": True,
                "compression_mib_per_s": 250.0,
                "decompression_mib_per_s": 400.0,
            },
            {
                "tier": "WARM",
                "profile_id": "warm-balanced",
                "zstd_level": 5,
                "logical_input_bytes": 100,
                "physical_bytes": 60,
                "compression_ratio": 0.6,
                "compression_savings_bytes": 40,
                "compression_expands": False,
                "round_trip_identity": True,
                "measurement_samples": 3,
                "benchmark_measured": True,
                "compression_mib_per_s": 180.0,
                "decompression_mib_per_s": 320.0,
            },
            {
                "tier": "COLD",
                "profile_id": "cold-dense",
                "zstd_level": 12,
                "logical_input_bytes": 100,
                "physical_bytes": 80,
                "compression_ratio": 0.8,
                "compression_savings_bytes": 20,
                "compression_expands": False,
                "round_trip_identity": True,
                "measurement_samples": 3,
                "benchmark_measured": True,
                "compression_mib_per_s": 90.0,
                "decompression_mib_per_s": 220.0,
            },
        ],
    }


def mcp_surface_evidence_fixture() -> dict[str, object]:
    return {
        "status": "PASS",
        "evidence_file": MCP_CORE_SURFACE_EVIDENCE_FILE,
        "mcp_evidence_version": MCP_CORE_SURFACE_EVIDENCE_VERSION,
        MCP_CORE_SURFACE_REGISTERED_PROJECT_COUNT: 2,
        **{field: True for field in MCP_CORE_SURFACE_TRUE_FIELDS},
        **{field: False for field in MCP_CORE_SURFACE_FALSE_FIELDS},
        "tool_list_exact": list(MCP_CORE_SURFACE_TOOLS),
        "observed_migration_head": "0006_memory_lifecycle_provenance",
        **{field: 0 for field in MCP_CORE_SURFACE_INTEGER_FIELDS},
    }


def test_review_evidence_schema_is_validated() -> None:
    manifest = evidence_fixture()
    validate_manifest(manifest)
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["properties"]["schema_version"]["const"] == 1


def test_wo015_is_explicitly_registered_and_unknown_ids_do_not_get_memory_semantics() -> None:
    require_supported_work_order(WO015_G1_WORK_ORDER)
    require_supported_work_order(WO015_WORK_ORDER)
    require_supported_work_order(WO015P_G1_WORK_ORDER)
    require_supported_work_order(WO015P_WORK_ORDER)
    require_supported_work_order(WO016P_G1_WORK_ORDER)
    require_supported_work_order(WO016P_WORK_ORDER)
    require_supported_work_order(review_evidence.WO017P_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO017P_WORK_ORDER)
    with pytest.raises(ValueError, match="unsupported checkpoint-promotion"):
        require_supported_work_order("WO-018-P")
    require_wo015_memory_evidence("WO-999", {})


def test_wo015_g1_scope_is_exact_and_future_scope_stays_noncanonical() -> None:
    require_wo015_g1_scope(
        WO015_G1_WORK_ORDER,
        WO015_G1_BASE_SHA,
        sorted(WO015_G1_ALLOWED_PATHS),
    )
    with pytest.raises(ValueError, match="exact base"):
        require_wo015_g1_scope(WO015_G1_WORK_ORDER, "a" * 40, sorted(WO015_G1_ALLOWED_PATHS))
    with pytest.raises(ValueError, match="outside the approved governance scope"):
        require_wo015_g1_scope(
            WO015_G1_WORK_ORDER,
            WO015_G1_BASE_SHA,
            [*sorted(WO015_G1_ALLOWED_PATHS), "backend/app/memory.py"],
        )
    require_wo015_scope(WO015_WORK_ORDER, "b" * 40, ["backend/app/memory.py"])
    with pytest.raises(ValueError, match="base branch"):
        require_wo015_scope(
            WO015_WORK_ORDER,
            "b" * 40,
            ["backend/app/memory.py"],
            base_branch="release",
        )
    with pytest.raises(ValueError, match="canonical Project Brain"):
        require_wo015_scope(
            WO015_WORK_ORDER,
            "b" * 40,
            ["docs/project-brain/13-CHECKPOINT.md"],
        )


def test_wo016_registration_and_bounded_scopes(monkeypatch: pytest.MonkeyPatch) -> None:
    require_supported_work_order(WO016_G1_WORK_ORDER)
    require_supported_work_order(WO016_WORK_ORDER)
    monkeypatch.setattr(
        review_evidence, "migration_head", lambda: "0006_memory_lifecycle_provenance"
    )
    require_wo016_g1_scope(WO016_G1_WORK_ORDER, WO016_G1_BASE_SHA, sorted(WO016_G1_ALLOWED_PATHS))
    with pytest.raises(ValueError, match="exact base"):
        require_wo016_g1_scope(WO016_G1_WORK_ORDER, "a" * 40, sorted(WO016_G1_ALLOWED_PATHS))
    with pytest.raises(ValueError, match="outside"):
        require_wo016_g1_scope(
            WO016_G1_WORK_ORDER,
            WO016_G1_BASE_SHA,
            [*sorted(WO016_G1_ALLOWED_PATHS), "backend/app/cas.py"],
        )
    with pytest.raises(ValueError, match="canonical Project Brain"):
        require_wo016_g1_scope(
            WO016_G1_WORK_ORDER,
            WO016_G1_BASE_SHA,
            ["docs/project-brain/13-CHECKPOINT.md"],
        )
    with pytest.raises(ValueError, match="migrations"):
        require_wo016_g1_scope(
            WO016_G1_WORK_ORDER,
            WO016_G1_BASE_SHA,
            ["migrations/versions/0007_acce.py"],
        )

    product_paths = sorted(WO016_PRODUCT_ALLOWED_PATHS) + ["migrations/versions/0007_acce.py"]
    require_wo016_scope(WO016_WORK_ORDER, "a" * 40, product_paths)
    with pytest.raises(ValueError, match="canonical Project Brain"):
        require_wo016_scope(WO016_WORK_ORDER, "a" * 40, ["docs/project-brain/13-CHECKPOINT.md"])
    with pytest.raises(ValueError, match="at most one"):
        require_wo016_scope(
            WO016_WORK_ORDER,
            "a" * 40,
            ["migrations/versions/0007_acce.py", "migrations/versions/0007_other.py"],
        )
    with pytest.raises(ValueError, match="outside"):
        require_wo016_scope(WO016_WORK_ORDER, "a" * 40, ["backend/app/unrelated.py"])


def test_wo017_registration_and_bounded_scopes(monkeypatch: pytest.MonkeyPatch) -> None:
    require_supported_work_order(WO017_G1_WORK_ORDER)
    require_supported_work_order(WO017_WORK_ORDER)
    monkeypatch.setattr(
        review_evidence, "migration_head", lambda: "0006_memory_lifecycle_provenance"
    )
    require_wo017_g1_scope(
        WO017_G1_WORK_ORDER,
        WO017_G1_BASE_SHA,
        sorted(WO017_G1_ALLOWED_PATHS),
    )
    with pytest.raises(ValueError, match="exact base"):
        require_wo017_g1_scope(
            WO017_G1_WORK_ORDER,
            "a" * 40,
            sorted(WO017_G1_ALLOWED_PATHS),
        )
    with pytest.raises(ValueError, match="base branch"):
        require_wo017_g1_scope(
            WO017_G1_WORK_ORDER,
            WO017_G1_BASE_SHA,
            sorted(WO017_G1_ALLOWED_PATHS),
            base_branch="release",
        )
    with pytest.raises(ValueError, match="canonical Project Brain"):
        require_wo017_g1_scope(
            WO017_G1_WORK_ORDER,
            WO017_G1_BASE_SHA,
            ["docs/project-brain/13-CHECKPOINT.md"],
        )
    with pytest.raises(ValueError, match="migrations"):
        require_wo017_g1_scope(
            WO017_G1_WORK_ORDER,
            WO017_G1_BASE_SHA,
            ["migrations/versions/0007_mcp.py"],
        )
    for forbidden in (
        "backend/app/mcp_server.py",
        ".github/workflows/ci.yml",
        "requirements.txt",
        "backend/app/unrelated.py",
    ):
        with pytest.raises(ValueError, match="outside"):
            require_wo017_g1_scope(
                WO017_G1_WORK_ORDER,
                WO017_G1_BASE_SHA,
                [forbidden],
            )

    require_wo017_scope(
        WO017_WORK_ORDER,
        "a" * 40,
        sorted(WO017_PRODUCT_ALLOWED_PATHS),
    )
    with pytest.raises(ValueError, match="base branch"):
        require_wo017_scope(
            WO017_WORK_ORDER,
            "a" * 40,
            ["backend/app/mcp_server.py"],
            base_branch="release",
        )
    with pytest.raises(ValueError, match="resolved"):
        require_wo017_scope(
            WO017_WORK_ORDER,
            "0" * 40,
            ["backend/app/mcp_server.py"],
        )
    with pytest.raises(ValueError, match="canonical Project Brain"):
        require_wo017_scope(
            WO017_WORK_ORDER,
            "a" * 40,
            ["docs/project-brain/13-CHECKPOINT.md"],
        )
    with pytest.raises(ValueError, match="migrations"):
        require_wo017_scope(
            WO017_WORK_ORDER,
            "a" * 40,
            ["migrations/versions/0007_mcp.py"],
        )
    with pytest.raises(ValueError, match="outside"):
        require_wo017_scope(WO017_WORK_ORDER, "a" * 40, ["backend/app/unrelated.py"])


def test_wo017_mcp_evidence_is_versioned_exact_and_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    logs = tmp_path / "integration-logs"
    logs.mkdir()
    monkeypatch.setattr(review_evidence, "VALIDATION", tmp_path / "validation")
    monkeypatch.setattr(review_evidence, "INTEGRATION_LOGS", logs)
    evidence_path = logs / MCP_CORE_SURFACE_EVIDENCE_FILE
    fixture = mcp_surface_evidence_fixture()
    evidence_path.write_text(json.dumps(fixture), encoding="utf-8")
    parsed = mcp_surface_evidence()
    assert parsed["status"] == "PASS"
    require_wo017_mcp_evidence(
        WO017_WORK_ORDER,
        {"mcp_surface": parsed},
        "0006_memory_lifecycle_provenance",
    )
    require_wo017_mcp_evidence(
        review_evidence.WO017P_G1_WORK_ORDER,
        {"mcp_surface": parsed},
        "0006_memory_lifecycle_provenance",
    )
    require_wo017_mcp_evidence(
        review_evidence.WO017P_WORK_ORDER,
        {"mcp_surface": parsed},
        "0006_memory_lifecycle_provenance",
    )

    with pytest.raises(ValueError, match="missing mandatory"):
        require_wo017_mcp_evidence(
            WO017_WORK_ORDER,
            {},
            "0006_memory_lifecycle_provenance",
        )
    for field in MCP_CORE_SURFACE_TRUE_FIELDS:
        broken_true_field: dict[str, object] = dict(fixture)
        broken_true_field[field] = False
        evidence_path.write_text(json.dumps(broken_true_field), encoding="utf-8")
        with pytest.raises(ValueError, match="missing mandatory|passing"):
            require_wo017_mcp_evidence(
                WO017_WORK_ORDER,
                {"mcp_surface": mcp_surface_evidence()},
                "0006_memory_lifecycle_provenance",
            )
    for field in MCP_CORE_SURFACE_FALSE_FIELDS:
        broken_false_field = dict(fixture)
        broken_false_field[field] = True
        evidence_path.write_text(json.dumps(broken_false_field), encoding="utf-8")
        with pytest.raises(ValueError, match="negative|passing"):
            require_wo017_mcp_evidence(
                WO017_WORK_ORDER,
                {"mcp_surface": mcp_surface_evidence()},
                "0006_memory_lifecycle_provenance",
            )
    for field, value in (
        ("mcp_evidence_version", "mcp-core-surface-v0"),
        ("evidence_file", "wrong.json"),
        ("observed_migration_head", "0005_semantic_retrieval"),
        ("tool_list_exact", [*MCP_CORE_SURFACE_TOOLS, "memory.write"]),
        ("mcp_llm_calls", 1),
        ("mcp_provider_calls", 1),
        ("secret_leaks", 1),
        ("filesystem_path_leaks", 1),
    ):
        broken_contract: dict[str, object] = dict(fixture)
        broken_contract[field] = value
        evidence_path.write_text(json.dumps(broken_contract), encoding="utf-8")
        with pytest.raises(ValueError, match="versioned|bounded|requires|exact|observed"):
            require_wo017_mcp_evidence(
                WO017_WORK_ORDER,
                {"mcp_surface": mcp_surface_evidence()},
                "0006_memory_lifecycle_provenance",
            )
    for project_count_value in (
        None,
        True,
        False,
        0,
        1,
        -1,
        MCP_CORE_SURFACE_MAX_REGISTERED_PROJECT_COUNT + 1,
        10**9,
    ):
        broken_count: dict[str, object] = dict(fixture)
        if project_count_value is None:
            broken_count.pop(MCP_CORE_SURFACE_REGISTERED_PROJECT_COUNT)
        else:
            broken_count[MCP_CORE_SURFACE_REGISTERED_PROJECT_COUNT] = project_count_value
        evidence_path.write_text(json.dumps(broken_count), encoding="utf-8")
        parsed = mcp_surface_evidence()
        assert parsed["status"] == "FAIL"
        with pytest.raises(ValueError, match="passing|registered_project_count"):
            require_wo017_mcp_evidence(
                WO017_WORK_ORDER,
                {"mcp_surface": parsed},
                "0006_memory_lifecycle_provenance",
            )

    bounded = dict(fixture)
    bounded[MCP_CORE_SURFACE_REGISTERED_PROJECT_COUNT] = (
        MCP_CORE_SURFACE_MAX_REGISTERED_PROJECT_COUNT
    )
    evidence_path.write_text(json.dumps(bounded), encoding="utf-8")
    assert mcp_surface_evidence()["status"] == "PASS"
    with pytest.raises(ValueError, match="migration head"):
        evidence_path.write_text(json.dumps(fixture), encoding="utf-8")
        require_wo017_mcp_evidence(
            WO017_WORK_ORDER,
            {"mcp_surface": mcp_surface_evidence()},
            "0005_semantic_retrieval",
        )

    evidence_path.write_text(json.dumps({**fixture, "unexpected": True}), encoding="utf-8")
    assert mcp_surface_evidence()["status"] == "FAIL"
    evidence_path.write_text("not-json", encoding="utf-8")
    assert mcp_surface_evidence()["status"] == "FAIL"


def test_wo017_governance_contracts_are_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        review_evidence, "migration_head", lambda: "0006_memory_lifecycle_provenance"
    )
    g1 = verify_wo017_g1_governance_contract(
        WO017_G1_WORK_ORDER,
        WO017_G1_BASE_SHA,
        sorted(WO017_G1_ALLOWED_PATHS),
        {"project_brain_changed": False, "checkpoint_changed": False, "authorized_paths": []},
        {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}},
        {},
        "0006_memory_lifecycle_provenance",
    )
    assert g1 is not None
    assert "future_WO-017_registered=PASS" in g1
    assert "mcp-core-surface-v1" in g1
    assert "mcp_implementation=False" in g1
    with pytest.raises(ValueError, match="auto-merge"):
        verify_wo017_g1_governance_contract(
            WO017_G1_WORK_ORDER,
            WO017_G1_BASE_SHA,
            sorted(WO017_G1_ALLOWED_PATHS),
            {"project_brain_changed": False, "checkpoint_changed": False, "authorized_paths": []},
            {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": True}},
            {},
            "0006_memory_lifecycle_provenance",
        )

    future = verify_wo017_governance_contract(
        WO017_WORK_ORDER,
        "a" * 40,
        ["backend/app/mcp_server.py"],
        {"project_brain_changed": False, "checkpoint_changed": False, "authorized_paths": []},
        {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}},
        {"mcp_surface": mcp_surface_evidence_fixture()},
        "0006_memory_lifecycle_provenance",
    )
    assert future is not None
    assert "tool_list_exact=project.list,project.status" in future
    assert "canonical_write_tools=False" in future


def test_wo017_manifests_validate_with_g1_optional_and_future_required_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        review_evidence, "migration_head", lambda: "0006_memory_lifecycle_provenance"
    )

    g1 = evidence_fixture()
    g1["work_order"] = WO017_G1_WORK_ORDER
    g1["base"] = {"branch": "main", "sha": WO017_G1_BASE_SHA}
    g1["changed_files"] = {
        "count": len(WO017_G1_ALLOWED_PATHS),
        "paths": sorted(WO017_G1_ALLOWED_PATHS),
    }
    cast(dict[str, Any], g1["migrations"])["head"] = "0006_memory_lifecycle_provenance"
    governance = cast(dict[str, Any], g1["governance"])
    governance["ruleset_unchanged"] = True
    cast(dict[str, Any], governance["pull_request"])["auto_merge_armed"] = False
    g1["negative_scope"] = [
        "No merge or release was performed.",
        canonical_change_statement(
            canonical_change_evidence(sorted(WO017_G1_ALLOWED_PATHS), WO017_G1_WORK_ORDER)
        ),
        "No implementation outside the approved work-order scope was added.",
        "WO-017-G1 governance evidence: "
        + cast(
            str,
            verify_wo017_g1_governance_contract(
                WO017_G1_WORK_ORDER,
                WO017_G1_BASE_SHA,
                sorted(WO017_G1_ALLOWED_PATHS),
                canonical_change_evidence(sorted(WO017_G1_ALLOWED_PATHS), WO017_G1_WORK_ORDER),
                governance,
                cast(dict[str, Any], cast(dict[str, Any], g1["evidence"])["integration"]),
                "0006_memory_lifecycle_provenance",
            ),
        ),
    ]
    validate_manifest(g1)

    future_base = "a" * 40
    monkeypatch.setattr(
        review_evidence,
        "git_value",
        lambda *args, fallback="": (
            future_base if args == ("rev-parse", "origin/main") else fallback
        ),
    )
    monkeypatch.setattr(
        review_evidence,
        "git_blob_bytes",
        lambda *_args: b"WO-017-G1 merged support",
    )
    future = evidence_fixture()
    future["work_order"] = WO017_WORK_ORDER
    future["base"] = {"branch": "main", "sha": future_base}
    future["changed_files"] = {"count": 1, "paths": ["backend/app/mcp_server.py"]}
    cast(dict[str, Any], future["migrations"])["head"] = "0006_memory_lifecycle_provenance"
    future_integration = cast(
        dict[str, Any], cast(dict[str, Any], future["evidence"])["integration"]
    )
    future_integration["mcp_surface"] = mcp_surface_evidence_fixture()
    future_governance = cast(dict[str, Any], future["governance"])
    future_governance["ruleset_unchanged"] = True
    cast(dict[str, Any], future_governance["pull_request"])["auto_merge_armed"] = False
    future_canonical = canonical_change_evidence(["backend/app/mcp_server.py"], WO017_WORK_ORDER)
    future_evidence = verify_wo017_governance_contract(
        WO017_WORK_ORDER,
        future_base,
        ["backend/app/mcp_server.py"],
        future_canonical,
        future_governance,
        future_integration,
        "0006_memory_lifecycle_provenance",
    )
    future["negative_scope"] = [
        "No merge or release was performed.",
        canonical_change_statement(future_canonical),
        "No implementation outside the approved work-order scope was added.",
        "WO-017 governance evidence: " + cast(str, future_evidence),
    ]
    validate_manifest(future)


def test_wo016_storage_evidence_is_versioned_and_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    validation = tmp_path / "validation"
    logs = tmp_path / "integration-logs"
    validation.mkdir()
    logs.mkdir()
    monkeypatch.setattr(review_evidence, "VALIDATION", validation)
    monkeypatch.setattr(review_evidence, "INTEGRATION_LOGS", logs)
    evidence_path = logs / ACCE_STORAGE_POLICY_EVIDENCE_FILE
    fixture = acce_storage_evidence_fixture()
    evidence_path.write_text(json.dumps(fixture), encoding="utf-8")
    parsed = acce_storage_policy_evidence()
    assert parsed["status"] == "PASS"
    require_wo016_storage_evidence(
        WO016_WORK_ORDER,
        {"acce_storage": parsed},
        "0007_acce_storage_policy",
    )
    with pytest.raises(ValueError, match="missing mandatory"):
        require_wo016_storage_evidence(WO016_WORK_ORDER, {}, "0007_acce_storage_policy")
    for field in (
        "acce_evidence_version",
        "hot_warm_cold_policy_defined",
        "zstd_lossless_codec",
        "content_identity_sha256_preserved",
        "corruption_fail_closed",
        "dedup_measurements_truthful",
    ):
        broken = dict(parsed)
        broken[field] = "wrong" if field == "acce_evidence_version" else False
        with pytest.raises(ValueError, match="passing|missing mandatory|versioned"):
            require_wo016_storage_evidence(
                WO016_WORK_ORDER, {"acce_storage": broken}, "0007_acce_storage_policy"
            )
    for field, value in (
        ("canonical_source_loss_count", 1),
        ("llm_calls", 1),
        ("provider_calls", 1),
        ("dedup_savings_bytes", 99),
    ):
        broken = dict(parsed)
        broken[field] = value
        with pytest.raises(ValueError, match="requires"):
            require_wo016_storage_evidence(
                WO016_WORK_ORDER, {"acce_storage": broken}, "0007_acce_storage_policy"
            )

    malformed = dict(fixture)
    benchmark_matrix = cast(list[dict[str, object]], fixture["benchmark_matrix"])
    malformed["benchmark_matrix"] = [{**benchmark_matrix[0], "zstd_level": 23}]
    evidence_path.write_text(json.dumps(malformed), encoding="utf-8")
    assert acce_storage_policy_evidence()["status"] == "FAIL"


def test_wo016_storage_evidence_rejects_tier_binding_and_performance_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    logs = tmp_path / "integration-logs"
    logs.mkdir()
    monkeypatch.setattr(review_evidence, "VALIDATION", tmp_path / "validation")
    monkeypatch.setattr(review_evidence, "INTEGRATION_LOGS", logs)
    fixture = acce_storage_evidence_fixture()
    matrix = cast(list[dict[str, object]], fixture["benchmark_matrix"])
    evidence_path = logs / ACCE_STORAGE_POLICY_EVIDENCE_FILE
    mutations: list[tuple[str, dict[str, object]]] = []

    for tier, profile in (("HOT", "cold-dense"), ("COLD", "hot-fast")):
        swapped = json.loads(json.dumps(fixture))
        cast(dict[str, str], swapped["policy_mapping"])[tier] = profile
        mutations.append((f"swapped-{tier}", swapped))

    missing_profile = json.loads(json.dumps(fixture))
    cast(dict[str, str], missing_profile["policy_mapping"])["HOT"] = "not-measured"
    mutations.append(("missing-profile", missing_profile))

    for field in ("compression_mib_per_s", "decompression_mib_per_s"):
        missing_performance = json.loads(json.dumps(fixture))
        for row in cast(list[dict[str, object]], missing_performance["benchmark_matrix"]):
            row.pop(field)
        mutations.append((f"missing-{field}", missing_performance))

    for value in (0, -1, float("nan"), float("inf"), True, 1_000_001):
        for field in ("compression_mib_per_s", "decompression_mib_per_s"):
            invalid_performance = json.loads(json.dumps(fixture))
            cast(list[dict[str, object]], invalid_performance["benchmark_matrix"])[0][field] = value
            mutations.append((f"invalid-{field}-{value}", invalid_performance))

    duplicate = json.loads(json.dumps(fixture))
    cast(list[dict[str, object]], duplicate["benchmark_matrix"]).append(dict(matrix[0]))
    mutations.append(("duplicate-selected-pair", duplicate))

    for _, mutation in mutations:
        evidence_path.write_text(json.dumps(mutation), encoding="utf-8")
        assert acce_storage_policy_evidence()["status"] == "FAIL"

    evidence_path.write_text(json.dumps(fixture), encoding="utf-8")
    assert acce_storage_policy_evidence()["status"] == "PASS"


def test_wo016_g1_governance_contract_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        review_evidence, "migration_head", lambda: "0006_memory_lifecycle_provenance"
    )
    evidence = verify_wo016_g1_governance_contract(
        WO016_G1_WORK_ORDER,
        WO016_G1_BASE_SHA,
        sorted(WO016_G1_ALLOWED_PATHS),
        {"project_brain_changed": False, "checkpoint_changed": False, "authorized_paths": []},
        {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}},
        {},
        "0006_memory_lifecycle_provenance",
    )
    assert evidence is not None
    assert "future_WO-016_registered=PASS" in evidence
    assert "acce-storage-policy-v1" in evidence
    with pytest.raises(ValueError, match="auto-merge"):
        verify_wo016_g1_governance_contract(
            WO016_G1_WORK_ORDER,
            WO016_G1_BASE_SHA,
            sorted(WO016_G1_ALLOWED_PATHS),
            {"project_brain_changed": False, "checkpoint_changed": False, "authorized_paths": []},
            {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": True}},
            {},
            "0006_memory_lifecycle_provenance",
        )


def wo017p_checkpoint_fixture(*, include_evidence: bool = True) -> tuple[str, str]:
    base = review_evidence.git_blob_bytes(
        review_evidence.WO017P_G1_BASE_SHA,
        review_evidence.CHECKPOINT_PATH,
    ).decode("utf-8")
    candidate = replace_checkpoint_section(
        base,
        "STATUS",
        review_evidence.EXPECTED_WO017P_STATUS,
    )
    candidate = candidate.replace(
        f"- {review_evidence.EXPECTED_WO017P_PENDING_ITEM}\n",
        "",
    )
    candidate = replace_checkpoint_section(
        candidate,
        "IN PROGRESS",
        f"- {review_evidence.EXPECTED_WO017P_IN_PROGRESS}",
    )
    candidate = replace_checkpoint_section(
        candidate,
        "BLOCKERS",
        review_evidence.EXPECTED_WO017P_BLOCKERS,
    )
    candidate = replace_checkpoint_section(
        candidate,
        "NEXT STEP",
        review_evidence.EXPECTED_WO017P_NEXT_STEP,
    )
    if include_evidence:
        completed = review_evidence.checkpoint_bullets(
            review_evidence.checkpoint_sections(base), "COMPLETED"
        )
        completion_bullets = list(review_evidence.WO017P_CANONICAL_COMPLETION_BULLETS)
        candidate = replace_checkpoint_section(
            candidate,
            "COMPLETED",
            "\n".join(f"- {item}" for item in completed + completion_bullets),
        )
    return base, candidate


def test_wo017p_g1_scope_is_exact_and_noncanonical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        review_evidence, "migration_head", lambda: "0006_memory_lifecycle_provenance"
    )
    review_evidence.require_wo017p_g1_scope(
        review_evidence.WO017P_G1_WORK_ORDER,
        review_evidence.WO017P_G1_BASE_SHA,
        sorted(review_evidence.WO017P_G1_ALLOWED_PATHS),
    )
    with pytest.raises(ValueError, match="exact base"):
        review_evidence.require_wo017p_g1_scope(
            review_evidence.WO017P_G1_WORK_ORDER,
            "a" * 40,
            sorted(review_evidence.WO017P_G1_ALLOWED_PATHS),
        )
    for unauthorized in (
        "docs/project-brain/13-CHECKPOINT.md",
        "docs/project-brain/CANONICAL-SHA256SUMS.txt",
        "migrations/versions/0007_mcp.py",
        "backend/app/mcp_server.py",
        ".github/workflows/ci.yml",
    ):
        scope_error = "outside|canonical Project Brain|migrations"
        with pytest.raises(ValueError, match=scope_error):
            review_evidence.require_wo017p_g1_scope(
                review_evidence.WO017P_G1_WORK_ORDER,
                review_evidence.WO017P_G1_BASE_SHA,
                ["scripts/review_evidence.py", unauthorized],
            )


def test_wo017p_checkpoint_semantics_are_closed_and_exact() -> None:
    base, candidate = wo017p_checkpoint_fixture()
    review_evidence.require_wo017p_checkpoint_semantics(base, candidate)
    completed = review_evidence.checkpoint_bullets(
        review_evidence.checkpoint_sections(candidate), "COMPLETED"
    )
    assert completed[-5:] == list(review_evidence.WO017P_CANONICAL_COMPLETION_BULLETS)
    with pytest.raises(ValueError):
        review_evidence.require_wo017p_checkpoint_semantics(
            base,
            candidate.replace(
                review_evidence.EXPECTED_WO017P_NEXT_STEP,
                "Prepare telemetry first.",
                1,
            ),
        )
    with pytest.raises(ValueError):
        review_evidence.require_wo017p_checkpoint_semantics(
            base,
            candidate.replace("pr #59", "pr #58", 1),
        )


def test_wo017p_manifest_contract_only_changes_checkpoint_hash() -> None:
    manifest_path = review_evidence.ROOT / review_evidence.CANONICAL_MANIFEST_PATH
    base_manifest = manifest_path.read_text(encoding="utf-8")
    _, candidate_checkpoint = wo017p_checkpoint_fixture()
    candidate_bytes = candidate_checkpoint.encode("utf-8")
    digest = hashlib.sha256(candidate_bytes).hexdigest()
    lines = base_manifest.splitlines(keepends=True)
    candidate_lines = []
    changed = 0
    for line in lines:
        stripped = line.strip().split(maxsplit=1)
        checkpoint_name = review_evidence.CANONICAL_MANIFEST_CHECKPOINT_NAME
        if len(stripped) == 2 and stripped[1] == checkpoint_name:
            prefix = line.index(stripped[0])
            line = line[:prefix] + digest + line[prefix + len(stripped[0]) :]
            changed += 1
        candidate_lines.append(line)
    assert changed == 1
    review_evidence.require_wo017p_manifest_contract(
        base_manifest,
        "".join(candidate_lines),
        candidate_bytes,
    )


def test_wo017p_renderers_are_explicit() -> None:
    g1 = render_body(
        work_order="WO-017-P-G1",
        pr_number=61,
        branch="governance/wo017p-review-evidence-support",
        base_sha=review_evidence.WO017P_G1_BASE_SHA,
        head_sha="b" * 40,
        artifact_name="artifact",
        ruleset_before="before",
        ruleset_after="after",
        merge_before="before",
        merge_after="after",
    )
    assert "WO-017-P-G1 READY FOR SOL AUDIT" in g1
    promotion = render_body(
        work_order="WO-017-P",
        pr_number=62,
        branch="checkpoint/wo017-mcp-close",
        base_sha="a" * 40,
        head_sha="b" * 40,
        artifact_name="artifact",
        ruleset_before="before",
        ruleset_after="after",
        merge_before="before",
        merge_after="after",
    )
    assert "<!-- HIVE-AUTHORIZED-BASE: " + "a" * 40 + " -->" in promotion
    assert "WO-017-P READY FOR SOL AUDIT" in promotion


def test_wo016p_g1_scope_is_exact_and_noncanonical(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        review_evidence, "migration_head", lambda: "0006_memory_lifecycle_provenance"
    )
    require_wo016p_g1_scope(
        WO016P_G1_WORK_ORDER,
        WO016P_G1_BASE_SHA,
        sorted(WO016P_G1_ALLOWED_PATHS),
    )
    with pytest.raises(ValueError, match="exact base"):
        require_wo016p_g1_scope(
            WO016P_G1_WORK_ORDER,
            "a" * 40,
            sorted(WO016P_G1_ALLOWED_PATHS),
        )
    with pytest.raises(ValueError, match="base branch"):
        require_wo016p_g1_scope(
            WO016P_G1_WORK_ORDER,
            WO016P_G1_BASE_SHA,
            sorted(WO016P_G1_ALLOWED_PATHS),
            base_branch="release",
        )
    for unauthorized in (
        "docs/project-brain/13-CHECKPOINT.md",
        "docs/project-brain/CANONICAL-SHA256SUMS.txt",
        "migrations/versions/0007_acce.py",
        "backend/app/cas.py",
        "unexpected.txt",
    ):
        with pytest.raises(ValueError, match="outside|canonical Project Brain|migrations"):
            require_wo016p_g1_scope(
                WO016P_G1_WORK_ORDER,
                WO016P_G1_BASE_SHA,
                ["scripts/review_evidence.py", unauthorized],
            )


def test_wo016p_checkpoint_semantics_are_closed_and_exact() -> None:
    base, candidate = wo016p_checkpoint_fixture()
    require_wo016p_checkpoint_semantics(base, candidate)

    completed = review_evidence.checkpoint_bullets(
        review_evidence.checkpoint_sections(candidate), "COMPLETED"
    )
    historical = completed[:-5]
    evidence = completed[-5:]
    pending = review_evidence.checkpoint_bullets(
        review_evidence.checkpoint_sections(candidate), "PENDING"
    )
    strict_mutations = [
        (
            "duplicate NEXT STEP with unauthorized first body",
            duplicate_checkpoint_section(
                candidate,
                "NEXT STEP",
                "Unauthorized MCP implementation instructions.",
                review_evidence.EXPECTED_WO016P_NEXT_STEP,
            ),
        ),
        (
            "duplicate STATUS",
            duplicate_checkpoint_section(
                candidate,
                "STATUS",
                "Unauthorized status prose.",
                review_evidence.EXPECTED_WO016P_STATUS,
            ),
        ),
        (
            "modified top-level checkpoint title",
            candidate.replace(
                "# 13 — CHECKPOINT",
                "# 13 — CHECKPOINT TAMPERED",
                1,
            ),
        ),
        (
            "arbitrary preamble text",
            candidate.replace("## STATUS", "Unauthorized preamble.\n\n## STATUS", 1),
        ),
        (
            "non-bullet COMPLETED prose",
            replace_checkpoint_section(
                candidate,
                "COMPLETED",
                "\n".join(f"- {item}" for item in completed) + "\nUnauthorized completed prose",
            ),
        ),
        (
            "non-bullet PENDING prose",
            replace_checkpoint_section(
                candidate,
                "PENDING",
                "\n".join(f"- {item}" for item in pending) + "\nUnauthorized pending prose",
            ),
        ),
        (
            "historical COMPLETED indentation mutation",
            candidate.replace(
                "- Product objective defined.",
                "  - Product objective defined.",
                1,
            ),
        ),
        (
            "historical COMPLETED trailing whitespace mutation",
            candidate.replace(
                "- Product objective defined.\n",
                "- Product objective defined. \n",
                1,
            ),
        ),
        (
            "untouched PENDING formatting mutation",
            candidate.replace("- telemetry.\n", "- telemetry. \n", 1),
        ),
        (
            "hidden line between ACCE completion bullets",
            candidate.replace(
                f"- {evidence[0]}\n- {evidence[1]}",
                f"- {evidence[0]}\n\n- {evidence[1]}",
                1,
            ),
        ),
        (
            "sixth ACCE completion bullet",
            replace_checkpoint_section(
                candidate,
                "COMPLETED",
                "\n".join(f"- {item}" for item in completed + [evidence[0]]),
            ),
        ),
        (
            "extra NEXT STEP line",
            replace_checkpoint_section(
                candidate,
                "NEXT STEP",
                f"{review_evidence.EXPECTED_WO016P_NEXT_STEP}\n- Extra intent.",
            ),
        ),
        (
            "arbitrary NEXT STEP trailing text",
            replace_checkpoint_section(
                candidate,
                "NEXT STEP",
                f"{review_evidence.EXPECTED_WO016P_NEXT_STEP}\nImplement MCP transport.",
            ),
        ),
        (
            "unrelated section raw mutation",
            replace_checkpoint_section(
                candidate,
                "VERSION",
                "HIVE V0.1 — Foundation changed",
            ),
        ),
    ]
    assert len(strict_mutations) == 14
    with pytest.raises(ValueError, match="duplicate section heading"):
        require_wo016p_checkpoint_semantics(
            duplicate_checkpoint_section(
                base,
                "NEXT STEP",
                "Unauthorized base heading.",
                review_evidence.EXPECTED_WO016P_NEXT_STEP,
            ),
            candidate,
        )
    for _, malformed in strict_mutations:
        with pytest.raises(ValueError):
            require_wo016p_checkpoint_semantics(base, malformed)

    heading_mutations = [
        (
            "case-only STATUS heading mutation",
            candidate.replace("## STATUS\n", "## status\n", 1),
        ),
        (
            "leading-space STATUS heading mutation",
            candidate.replace("## STATUS\n", "##  STATUS\n", 1),
        ),
        (
            "trailing-space NEXT STEP heading mutation",
            candidate.replace("## NEXT STEP\n", "## NEXT STEP \n", 1),
        ),
        (
            "tab-based BLOCKERS heading mutation",
            candidate.replace("## BLOCKERS\n", "##\tBLOCKERS\n", 1),
        ),
        (
            "unrelated VERSION heading mutation",
            candidate.replace("## VERSION\n", "##  VERSION\n", 1),
        ),
    ]
    assert len(heading_mutations) == 5
    for _, malformed in heading_mutations:
        with pytest.raises(ValueError, match="heading changed byte-for-byte"):
            require_wo016p_checkpoint_semantics(base, malformed)

    duplicate_case_variant = candidate.replace(
        "## STATUS\n",
        "## STATUS\nUnauthorized duplicate heading body.\n\n## status\n",
        1,
    )
    with pytest.raises(ValueError, match="duplicate section heading: STATUS"):
        require_wo016p_checkpoint_semantics(base, duplicate_case_variant)

    mutations = [
        replace_checkpoint_section(candidate, "STATUS", "WRONG STATUS"),
        replace_checkpoint_section(
            candidate,
            "COMPLETED",
            "\n".join(f"- {item}" for item in historical + evidence[:4]),
        ),
        replace_checkpoint_section(
            candidate,
            "COMPLETED",
            "\n".join(f"- {item}" for item in completed + [evidence[0]]),
        ),
        replace_checkpoint_section(
            candidate,
            "COMPLETED",
            "\n".join(
                f"- {item}" for item in historical + [evidence[1], evidence[0], *evidence[2:]]
            ),
        ),
        candidate.replace("- Product objective defined.", "- Product objective changed.", 1),
        candidate.replace(
            "- MCP server product surface.\n",
            "",
            1,
        ),
        candidate.replace(
            f"- {review_evidence.EXPECTED_WO016P_IN_PROGRESS}",
            f"- {review_evidence.EXPECTED_WO016P_IN_PROGRESS}\n- Extra intent.",
            1,
        ),
        replace_checkpoint_section(
            candidate,
            "BLOCKERS",
            f"{review_evidence.EXPECTED_WO016P_BLOCKERS} extra",
        ),
        replace_checkpoint_section(
            candidate,
            "NEXT STEP",
            f"{review_evidence.EXPECTED_WO016P_NEXT_STEP}\nImplement MCP transport.",
        ),
    ]
    for malformed in mutations:
        with pytest.raises(ValueError):
            require_wo016p_checkpoint_semantics(base, malformed)


def test_wo016p_scope_binds_future_base_manifest_and_merged_g1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_checkpoint, candidate_checkpoint = wo016p_checkpoint_fixture()
    base_manifest = review_evidence.git_blob_bytes(
        WO016P_G1_BASE_SHA,
        review_evidence.CANONICAL_MANIFEST_PATH,
    ).decode("utf-8")
    candidate_bytes = candidate_checkpoint.encode("utf-8")
    candidate_manifest = "".join(
        line.replace(
            line.strip().split(maxsplit=1)[0],
            hashlib.sha256(candidate_bytes).hexdigest(),
            1,
        )
        if (
            len(line.strip().split(maxsplit=1)) == 2
            and line.strip().split(maxsplit=1)[1]
            == review_evidence.CANONICAL_MANIFEST_CHECKPOINT_NAME
        )
        else line
        for line in base_manifest.splitlines(keepends=True)
    )
    checkpoint_path = tmp_path / review_evidence.CHECKPOINT_PATH
    manifest_path = tmp_path / review_evidence.CANONICAL_MANIFEST_PATH
    checkpoint_path.parent.mkdir(parents=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_bytes(candidate_bytes)
    manifest_path.write_text(candidate_manifest, encoding="utf-8", newline="\n")
    monkeypatch.setattr(review_evidence, "ROOT", tmp_path)

    def fake_git_blob_bytes(revision: str, path: str) -> bytes:
        assert revision == "d" * 40
        if path == "scripts/review_evidence.py":
            return WO016P_G1_WORK_ORDER.encode("utf-8")
        if path == review_evidence.CHECKPOINT_PATH:
            return base_checkpoint.encode("utf-8")
        return base_manifest.encode("utf-8")

    monkeypatch.setattr(review_evidence, "git_blob_bytes", fake_git_blob_bytes)
    require_wo016p_scope(
        WO016P_WORK_ORDER,
        "d" * 40,
        sorted(WO016P_PROMOTION_ALLOWED_PATHS),
        registered_base_sha="d" * 40,
        authorized_base_sha="d" * 40,
    )
    with pytest.raises(ValueError, match="authorized-base"):
        require_wo016p_scope(
            WO016P_WORK_ORDER,
            "d" * 40,
            sorted(WO016P_PROMOTION_ALLOWED_PATHS),
            registered_base_sha="d" * 40,
            authorized_base_sha="e" * 40,
        )
    with pytest.raises(ValueError, match="manifest"):
        require_wo016p_manifest_contract(
            base_manifest,
            candidate_manifest + "# unexpected\n",
            candidate_bytes,
        )


def test_wo016p_governance_requires_six_row_acce_lineage() -> None:
    common = {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }
    approved_lineage = verify_wo016_approved_lineage(approved_wo016_lineage_sources_fixture())
    evidence = verify_wo016p_g1_governance_contract(
        WO016P_G1_WORK_ORDER,
        WO016P_G1_BASE_SHA,
        sorted(WO016P_G1_ALLOWED_PATHS),
        common,
        {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}},
        {"acce_storage": acce_storage_promotion_evidence_fixture()},
        "0006_memory_lifecycle_provenance",
        approved_lineage,
    )
    assert evidence is not None
    assert "active_promotions=WO-016-P-G1,WO-016-P" in evidence
    assert "benchmark_rows=6" in evidence
    assert "PR#55" in evidence
    broken = acce_storage_promotion_evidence_fixture()
    cast(list[dict[str, object]], broken["benchmark_matrix"]).pop()
    with pytest.raises(ValueError, match="exactly six"):
        verify_wo016p_g1_governance_contract(
            WO016P_G1_WORK_ORDER,
            WO016P_G1_BASE_SHA,
            sorted(WO016P_G1_ALLOWED_PATHS),
            common,
            {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}},
            {"acce_storage": broken},
            "0006_memory_lifecycle_provenance",
            approved_lineage,
        )


def test_wo016_approved_lineage_is_objective_and_fail_closed() -> None:
    sources = approved_wo016_lineage_sources_fixture()
    result = verify_wo016_approved_lineage(sources)
    require_wo016_approved_lineage_result(result)
    statement = review_evidence.wo016_approved_lineage_statement(result)
    assert statement.startswith(WO016_APPROVED_LINEAGE_STATEMENT_PREFIX)
    assert parse_wo016_approved_lineage_statement(statement) == result

    mutations: list[tuple[str, Callable[[dict[str, Any]], object]]] = [
        ("wrong product PR number", lambda value: value["product_pr"].update(number=56)),
        (
            "wrong audited HEAD",
            lambda value: value["product_pr"]["head"].update(sha="a" * 40),
        ),
        ("missing Sol review", lambda value: value.update(product_reviews=[])),
        (
            "wrong Sol review ID",
            lambda value: value["product_reviews"][0].update(id=5135618101),
        ),
        (
            "Sol review bound to another commit",
            lambda value: value["product_reviews"][0].update(commit_id="b" * 40),
        ),
        (
            "review does not express approval",
            lambda value: value["product_reviews"][0].update(body="COMMENTED"),
        ),
        (
            "wrong merge SHA",
            lambda value: value["product_pr"].update(merge_commit_sha="c" * 40),
        ),
        ("product PR not merged", lambda value: value["product_pr"].update(merged=False)),
        (
            "wrong post-merge CI run ID",
            lambda value: value["post_merge_run"].update(id=34168038155),
        ),
        (
            "post-merge CI event not push",
            lambda value: value["post_merge_run"].update(event="pull_request"),
        ),
        (
            "post-merge CI head SHA wrong",
            lambda value: value["post_merge_run"].update(head_sha="d" * 40),
        ),
        (
            "post-merge CI conclusion failed",
            lambda value: value["post_merge_run"].update(conclusion="failure"),
        ),
        (
            "Validate missing",
            lambda value: value["post_merge_jobs"].pop(0),
        ),
        (
            "Integration health failed",
            lambda value: value["post_merge_jobs"][1].update(conclusion="failure"),
        ),
        (
            "post-push Review Evidence not skipped",
            lambda value: value["post_merge_jobs"][2].update(conclusion="success"),
        ),
        (
            "prior exact-head Review Evidence missing",
            lambda value: value.update(prior_review_comments=[]),
        ),
        (
            "prior exact-head evidence HEAD mismatch",
            lambda value: value["prior_review_comments"][0].update(
                body=value["prior_review_comments"][0]["body"].replace(
                    WO016_APPROVED_PRODUCT_HEAD, "e" * 40
                )
            ),
        ),
        (
            "backend count not 418",
            lambda value: value["prior_review_comments"][0].update(
                body=value["prior_review_comments"][0]["body"].replace("418 passed", "417 passed")
            ),
        ),
        (
            "dashboard count not 7",
            lambda value: value["prior_review_comments"][0].update(
                body=value["prior_review_comments"][0]["body"].replace("7 passed", "6 passed")
            ),
        ),
        (
            "ACCE evidence not PASS",
            lambda value: value["prior_review_comments"][0].update(
                body=value["prior_review_comments"][0]["body"].replace("`PASS`", "`FAIL`")
            ),
        ),
        (
            "wrong ACCE evidence version",
            lambda value: value["prior_review_comments"][0].update(
                body=value["prior_review_comments"][0]["body"].replace(
                    "acce-storage-policy-v1", "acce-storage-policy-v0"
                )
            ),
        ),
        (
            "wrong storage policy version",
            lambda value: value["prior_review_comments"][0].update(
                body=value["prior_review_comments"][0]["body"].replace(
                    "acce-policy-v1", "acce-policy-v0"
                )
            ),
        ),
        (
            "canonical source loss above zero",
            lambda value: value["prior_review_comments"][0].update(
                body=value["prior_review_comments"][0]["body"].replace("loss `0`", "loss `1`")
            ),
        ),
        (
            "LLM calls above zero",
            lambda value: value["prior_review_comments"][0].update(
                body=value["prior_review_comments"][0]["body"].replace("0/0", "1/0")
            ),
        ),
        (
            "provider calls above zero",
            lambda value: value["prior_review_comments"][0].update(
                body=value["prior_review_comments"][0]["body"].replace("0/0", "0/1")
            ),
        ),
        ("unavailable lineage data", lambda value: value.update(product_pr=None)),
    ]
    for _label, mutate in mutations:
        broken = json.loads(json.dumps(sources))
        mutate(broken)
        with pytest.raises(ValueError, match="WO-016"):
            verify_wo016_approved_lineage(broken)


def test_wo016p_future_governance_reuses_approved_lineage_validator() -> None:
    approved_lineage = verify_wo016_approved_lineage(approved_wo016_lineage_sources_fixture())
    evidence = verify_wo016p_governance_contract(
        WO016P_WORK_ORDER,
        "d" * 40,
        sorted(WO016P_PROMOTION_ALLOWED_PATHS),
        {
            "project_brain_changed": True,
            "checkpoint_changed": True,
            "authorized_paths": sorted(WO016P_PROMOTION_ALLOWED_PATHS),
        },
        {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}},
        {"acce_storage": acce_storage_promotion_evidence_fixture()},
        "0006_memory_lifecycle_provenance",
        approved_lineage,
    )
    assert evidence is not None
    broken = dict(approved_lineage)
    broken["sol_review_id"] = WO016_APPROVED_SOL_REVIEW_ID + 1
    with pytest.raises(ValueError, match="approved lineage"):
        verify_wo016p_governance_contract(
            WO016P_WORK_ORDER,
            "d" * 40,
            sorted(WO016P_PROMOTION_ALLOWED_PATHS),
            {
                "project_brain_changed": True,
                "checkpoint_changed": True,
                "authorized_paths": sorted(WO016P_PROMOTION_ALLOWED_PATHS),
            },
            {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}},
            {"acce_storage": acce_storage_promotion_evidence_fixture()},
            "0006_memory_lifecycle_provenance",
            broken,
        )


def test_wo015_memory_evidence_is_bounded_and_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    integration_logs = tmp_path / "integration-logs"
    integration_logs.mkdir()
    monkeypatch.setattr(review_evidence, "INTEGRATION_LOGS", integration_logs)
    evidence_path = integration_logs / WO015_MEMORY_EVIDENCE_FILE
    evidence_path.write_text(json.dumps(memory_evidence_fixture()), encoding="utf-8")
    parsed = memory_lifecycle_evidence()
    assert parsed["status"] == "PASS"
    require_wo015_memory_evidence(
        WO015_WORK_ORDER,
        {"memory": parsed},
        "0006_memory_lifecycle_provenance",
    )
    with pytest.raises(ValueError, match="missing mandatory Memory evidence"):
        require_wo015_memory_evidence(WO015_WORK_ORDER, {}, "0006_memory_lifecycle_provenance")
    incomplete = dict(parsed)
    incomplete["memory_invalid_promotion_rejected"] = False
    with pytest.raises(ValueError, match="missing mandatory Memory evidence"):
        require_wo015_memory_evidence(
            WO015_WORK_ORDER,
            {"memory": incomplete},
            "0006_memory_lifecycle_provenance",
        )
    with pytest.raises(ValueError, match="migration head"):
        require_wo015_memory_evidence(
            WO015_WORK_ORDER,
            {"memory": parsed},
            "0005_semantic_retrieval",
        )


def test_wo015_g1_governance_contract_proves_negative_scope() -> None:
    evidence = verify_wo015_g1_governance_contract(
        WO015_G1_WORK_ORDER,
        WO015_G1_BASE_SHA,
        sorted(WO015_G1_ALLOWED_PATHS),
        {
            "project_brain_changed": False,
            "checkpoint_changed": False,
            "authorized_paths": [],
        },
        {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}},
        {"context_manager": {"memory_lifecycle_implemented": False}},
        "0005_semantic_retrieval",
    )
    assert evidence is not None
    assert "future_WO-015_registered=PASS" in evidence
    assert "future_memory_evidence_fail_closed=PASS" in evidence
    with pytest.raises(ValueError, match="must not implement Memory"):
        verify_wo015_g1_governance_contract(
            WO015_G1_WORK_ORDER,
            WO015_G1_BASE_SHA,
            sorted(WO015_G1_ALLOWED_PATHS),
            {
                "project_brain_changed": False,
                "checkpoint_changed": False,
                "authorized_paths": [],
            },
            {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}},
            {"context_manager": {"memory_lifecycle_implemented": True}},
            "0005_semantic_retrieval",
        )


def test_wo015_renderers_are_dedicated_and_unknown_ids_do_not_fall_through_to_memory() -> None:
    common: dict[str, Any] = {
        "pr_number": 50,
        "branch": "governance/wo015-g1-review-evidence-enablement",
        "base_sha": "a" * 40,
        "head_sha": "b" * 40,
        "artifact_name": "hive-review-evidence-WO-015-b",
        "ruleset_before": "unchanged",
        "ruleset_after": "unchanged",
        "merge_before": "unarmed",
        "merge_after": "unarmed",
    }
    g1 = render_body(work_order=WO015_G1_WORK_ORDER, **common)
    future = render_body(work_order=WO015_WORK_ORDER, **common)
    promotion_g1 = render_body(work_order=WO015P_G1_WORK_ORDER, **common)
    promotion = render_body(work_order=WO015P_WORK_ORDER, **common)
    unknown = render_body(work_order="WO-999", **common)
    assert g1.startswith("<!-- HIVE-WORK-ORDER: WO-015-G1 -->")
    assert "não implementa Memory" in g1
    assert "memory-lifecycle-provenance-v1" in g1
    assert "memory-lifecycle-provenance-v1" in future
    assert "PostgreSQL" in future
    assert promotion_g1.startswith("<!-- HIVE-WORK-ORDER: WO-015-P-G1 -->")
    assert "2c701d221e481913d2cbe9c0b8f3504632042306" in promotion_g1
    assert "WO-015-P-G1 READY FOR SOL AUDIT" in promotion_g1
    assert promotion.startswith("<!-- HIVE-WORK-ORDER: WO-015-P -->")
    assert "<!-- HIVE-AUTHORIZED-BASE: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa -->" in promotion
    assert "WO-015-P READY FOR SOL AUDIT" in promotion
    assert "memory-lifecycle-provenance-v1" not in unknown


def test_wo016_renderers_are_dedicated_and_explicit() -> None:
    common: dict[str, Any] = {
        "pr_number": 60,
        "branch": "governance/wo016-acce-storage-review-evidence",
        "base_sha": WO016_G1_BASE_SHA,
        "head_sha": "b" * 40,
        "artifact_name": "hive-review-evidence-WO-016-G1-b",
        "ruleset_before": "unchanged",
        "ruleset_after": "unchanged",
        "merge_before": "unarmed",
        "merge_after": "unarmed",
    }
    g1 = render_body(work_order=WO016_G1_WORK_ORDER, **common)
    future = render_body(work_order=WO016_WORK_ORDER, **common)
    assert g1.startswith("<!-- HIVE-WORK-ORDER: WO-016-G1 -->")
    assert "acce-storage-policy-v1" in g1
    assert "comportamento de produto ACCE" in g1
    assert future.startswith("<!-- HIVE-WORK-ORDER: WO-016 -->")
    assert "matriz" in future
    assert "LLM/provider calls" in future
    assert "WO-016 READY FOR SOL AUDIT" in future
    for work_order in (WO016_G1_WORK_ORDER, WO016_WORK_ORDER):
        abbreviated = {**common, "head_sha": "ae0a3e6"}
        with pytest.raises(ValueError, match="40-hex exact HEAD"):
            render_body(work_order=work_order, **abbreviated)
        exact = render_body(work_order=work_order, **{**common, "head_sha": "a" * 40})
        assert "a" * 40 in exact


def test_wo017_renderers_are_dedicated_and_explicit() -> None:
    common: dict[str, Any] = {
        "pr_number": 70,
        "branch": "governance/wo017-mcp-review-evidence-support",
        "base_sha": WO017_G1_BASE_SHA,
        "head_sha": "b" * 40,
        "artifact_name": "hive-review-evidence-WO-017-G1-b",
        "ruleset_before": "unchanged",
        "ruleset_after": "unchanged",
        "merge_before": "unarmed",
        "merge_after": "unarmed",
    }
    g1 = render_body(work_order=WO017_G1_WORK_ORDER, **common)
    future = render_body(work_order=WO017_WORK_ORDER, **common)
    assert g1.startswith("<!-- HIVE-WORK-ORDER: WO-017-G1 -->")
    assert "não implementa MCP" in g1
    assert "mcp-core-surface-v1" in g1
    assert "checkpoint.read" in g1
    assert "WO-017-G1 READY FOR SOL AUDIT" in g1
    assert future.startswith("<!-- HIVE-WORK-ORDER: WO-017 -->")
    assert "initialize" in future
    assert "REST loopback" in future
    assert "PostgreSQL" in future
    assert "mcp_llm_calls=0" in future
    assert "registered_project_count >= 2" in future
    assert "arbitrary_filesystem_access_rejected=true" in future
    assert "checkpoint_missing_fail_closed=true" in future
    assert "checkpoint_untracked_fail_closed=true" in future
    assert "checkpoint_stale_fail_closed=true" in future
    assert "checkpoint_hive_substitution_absent=true" in future
    assert "context_search_provenance_preserved=true" in future
    assert "context_search_result_bound_enforced=true" in future
    assert "memory_status_visibility_preserved=true" in future
    assert "structured_errors_enforced=true" in future
    assert "bounded_errors_enforced=true" in future
    assert "WO-017 READY FOR SOL AUDIT" in future
    for work_order in (WO017_G1_WORK_ORDER, WO017_WORK_ORDER):
        with pytest.raises(ValueError, match="40-hex exact HEAD"):
            render_body(work_order=work_order, **{**common, "head_sha": "ae0a3e6"})
        exact = render_body(work_order=work_order, **{**common, "head_sha": "a" * 40})
        assert "a" * 40 in exact


def test_wo016p_renderers_are_dedicated_and_explicit() -> None:
    common: dict[str, Any] = {
        "pr_number": 61,
        "branch": "governance/wo016p-review-evidence-support",
        "base_sha": WO016P_G1_BASE_SHA,
        "head_sha": "b" * 40,
        "artifact_name": "hive-review-evidence-WO-016-P-G1-b",
        "ruleset_before": "unchanged",
        "ruleset_after": "unchanged",
        "merge_before": "unarmed",
        "merge_after": "unarmed",
    }
    g1 = render_body(work_order=WO016P_G1_WORK_ORDER, **common)
    future = render_body(work_order=WO016P_WORK_ORDER, **common)
    assert g1.startswith("<!-- HIVE-WORK-ORDER: WO-016-P-G1 -->")
    assert "54c32e939c7be6d505727df24d3ce2ad48af5518" in g1
    assert "acce-storage-policy-v1" in g1
    assert "WO-016-P-G1 READY FOR SOL AUDIT" in g1
    assert future.startswith("<!-- HIVE-WORK-ORDER: WO-016-P -->")
    assert "<!-- HIVE-AUTHORIZED-BASE:" in future
    assert "canonical-sha256sums.txt" in future.casefold()
    assert "seis" in future.casefold()
    assert "WO-016-P READY FOR SOL AUDIT" in future
    for work_order in (WO016P_G1_WORK_ORDER, WO016P_WORK_ORDER):
        with pytest.raises(ValueError, match="40-hex exact HEAD"):
            render_body(work_order=work_order, **{**common, "head_sha": "ae0a3e6"})


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("<!-- HIVE-WORK-ORDER: WO-007-P -->", "WO-007-P"),
        ("<!-- HIVE-WORK-ORDER: WO-008 -->", "WO-008"),
        ("<!-- HIVE-WORK-ORDER: WO-007-P-C1 -->", "WO-007-P-C1"),
    ],
)
def test_work_order_marker_parser_accepts_bounded_future_and_corrective_ids(
    body: str, expected: str
) -> None:
    assert parse_work_order_marker(body) == expected


def test_work_order_marker_parser_rejects_missing_conflicting_and_untrusted_ids() -> None:
    with pytest.raises(ValueError, match="missing exactly one"):
        parse_work_order_marker("ordinary product pull request")
    with pytest.raises(ValueError, match="multiple conflicting"):
        parse_work_order_marker(
            "<!-- HIVE-WORK-ORDER: WO-007-P -->\n<!-- HIVE-WORK-ORDER: WO-008 -->"
        )
    with pytest.raises(ValueError, match="invalid or unbounded"):
        parse_work_order_marker("<!-- HIVE-WORK-ORDER: WO-007-P; rm -rf / -->")
    with pytest.raises(ValueError, match="invalid or unbounded"):
        parse_work_order_marker(f"<!-- HIVE-WORK-ORDER: {'WO-' + '9' * 70} -->")


def test_canonical_change_evidence_distinguishes_promotion_from_product_changes() -> None:
    promotion = canonical_change_evidence(
        [
            "docs/project-brain/13-CHECKPOINT.md",
            "docs/project-brain/CANONICAL-SHA256SUMS.txt",
        ]
    )
    assert promotion == {
        "project_brain_changed": True,
        "checkpoint_changed": True,
        "authorized_paths": [
            "docs/project-brain/13-CHECKPOINT.md",
            "docs/project-brain/CANONICAL-SHA256SUMS.txt",
        ],
    }
    assert canonical_change_evidence(["backend/app/main.py"]) == {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }


def test_promotion_evidence_does_not_emit_false_canonical_negative_scope() -> None:
    manifest = evidence_fixture()
    manifest["changed_files"] = {
        "count": 2,
        "paths": [
            "docs/project-brain/13-CHECKPOINT.md",
            "docs/project-brain/CANONICAL-SHA256SUMS.txt",
        ],
    }
    manifest["negative_scope"] = [
        canonical_change_statement(
            canonical_change_evidence(
                [
                    "docs/project-brain/13-CHECKPOINT.md",
                    "docs/project-brain/CANONICAL-SHA256SUMS.txt",
                ]
            )
        )
    ]
    validate_manifest(manifest)
    summary = summary_markdown(manifest, "https://example.invalid/run/1")
    assert "project_brain_changed `True`" in summary
    assert "checkpoint_changed `True`" in summary
    assert "No canonical Project Brain checkpoint was modified" not in summary


def handoff_governance(
    *,
    auto_merge_armed: bool = True,
    auto_merge_method: str | None = "squash",
    head_sha: str = "b" * 40,
    base_sha: str = "a" * 40,
    independent_approval_count: int = 0,
) -> dict[str, object]:
    return {
        "ruleset_unchanged": True,
        "pull_request": {
            "state": "open",
            "is_draft": False,
            "head_sha": head_sha,
            "base_sha": base_sha,
            "auto_merge_armed": auto_merge_armed,
            "auto_merge_method": auto_merge_method,
            "auto_merge": {
                "armed": auto_merge_armed,
                "method": auto_merge_method,
                "enabled_by_login": "KayzenRoot" if auto_merge_armed else "",
                "enabled_by_type": "User" if auto_merge_armed else "",
                "user_owned": auto_merge_armed,
            },
        },
        "approval_gate": {"independent_approval_count": independent_approval_count},
    }


def test_hive_final_handoff_requires_unarmed_auto_merge_before_sol() -> None:
    with pytest.raises(ValueError, match="unarmed"):
        require_hive_final_handoff(
            "WO-007-P", 28, "a" * 40, "b" * 40, handoff_governance(auto_merge_armed=True)
        )
    require_hive_final_handoff(
        "WO-007-P",
        28,
        "a" * 40,
        "b" * 40,
        handoff_governance(auto_merge_armed=False, independent_approval_count=1),
    )
    require_hive_final_handoff(
        "WO-007-P", 28, "a" * 40, "b" * 40, handoff_governance(auto_merge_armed=False)
    )


def test_hive_final_handoff_rejects_manifest_pr_head_mismatch() -> None:
    with pytest.raises(ValueError, match="does not match PR head"):
        require_hive_final_handoff("WO-007-P", 28, "a" * 40, "c" * 40, handoff_governance())


def test_g1_handoff_requires_exact_base_ruleset_and_user_owned_auto_merge() -> None:
    governance = handoff_governance(base_sha=WO008_G1_BASE_SHA)
    require_hive_final_handoff("WO-008-G1", 30, WO008_G1_BASE_SHA, "b" * 40, governance)

    wrong_base = handoff_governance(base_sha="a" * 40)
    with pytest.raises(ValueError, match="exact base"):
        require_hive_final_handoff("WO-008-G1", 30, "a" * 40, "b" * 40, wrong_base)

    bot_owned = handoff_governance(base_sha=WO008_G1_BASE_SHA)
    bot_pull_request = cast(dict[str, object], bot_owned["pull_request"])
    bot_auto_merge = cast(dict[str, object], bot_pull_request["auto_merge"])
    bot_auto_merge["user_owned"] = False
    with pytest.raises(ValueError, match="user-owned"):
        require_hive_final_handoff("WO-008-G1", 30, WO008_G1_BASE_SHA, "b" * 40, bot_owned)

    changed_ruleset = handoff_governance(base_sha=WO008_G1_BASE_SHA)
    changed_ruleset["ruleset_unchanged"] = False
    with pytest.raises(ValueError, match="ruleset"):
        require_hive_final_handoff("WO-008-G1", 30, WO008_G1_BASE_SHA, "b" * 40, changed_ruleset)


def test_g1_scope_rejects_non_governance_files() -> None:
    require_wo008_g1_scope("WO-008-G1", WO008_G1_BASE_SHA, sorted(WO008_G1_ALLOWED_PATHS))
    with pytest.raises(ValueError, match="outside"):
        require_wo008_g1_scope(
            "WO-008-G1",
            WO008_G1_BASE_SHA,
            [".github/workflows/ci.yml", "backend/app/reranking.py"],
        )


def replace_checkpoint_section(text: str, name: str, body: str) -> str:
    pattern = rf"(?ms)^## {re.escape(name)}\n.*?(?=^## |\Z)"
    replacement = f"## {name}\n{body.rstrip()}\n\n"
    updated, count = re.subn(pattern, replacement, text, count=1)
    assert count == 1
    return updated


def duplicate_checkpoint_section(text: str, name: str, first_body: str, second_body: str) -> str:
    return replace_checkpoint_section(
        text,
        name,
        f"{first_body}\n\n## {name}\n{second_body}",
    )


def wo012p_checkpoint_fixture(*, include_evidence: bool = True) -> tuple[str, str]:
    base = review_evidence.git_blob_bytes(
        WO012P_G1_BASE_SHA,
        review_evidence.CHECKPOINT_PATH,
    ).decode("utf-8")
    candidate = replace_checkpoint_section(
        base,
        "STATUS",
        review_evidence.EXPECTED_WO012P_STATUS,
    )
    candidate = candidate.replace("- context fingerprints.\n", "")
    candidate = replace_checkpoint_section(
        candidate,
        "IN PROGRESS",
        f"- {review_evidence.EXPECTED_WO012P_IN_PROGRESS}",
    )
    candidate = replace_checkpoint_section(
        candidate,
        "BLOCKERS",
        review_evidence.EXPECTED_WO012P_BLOCKERS,
    )
    candidate = replace_checkpoint_section(
        candidate,
        "NEXT STEP",
        review_evidence.EXPECTED_WO012P_NEXT_STEP_PREFIX
        + "\n\nDo not prescribe code unnecessarily.",
    )
    if include_evidence:
        completion_evidence = [
            "Context Fingerprints Foundation approval is recorded with policy "
            "context-fingerprint-v2, input context-input-v2, output context-output-v2 "
            "and cache context-fingerprint-cache-v2.",
            "The implementation uses SHA-256; Redis TTL 300 seconds remains "
            "non-canonical; transient reranker failure is not cached; transient "
            "semantic provider failure is not cached; provider recovery is retried; "
            "equivalent rebuild is stable.",
            "The context-fingerprint benchmark records false cache hits 0, critical "
            "context misses 0, exact repeat work avoidance, fingerprint LLM calls 0 "
            "and fingerprint provider calls 0.",
            "Evidence references migration 0005_semantic_retrieval, PR #40, audited "
            "HEAD 2a128dfcdeb97a45f174cf2dfa529826354f95ad, Sol review 5119310904, "
            "merge 743253ef079596370a7ff1102faf03b3a603b585, post-merge CI "
            "33937782195, backend 275/dashboard 7.",
            "Delta Context not implemented; provider/prompt cache not implemented; "
            "memory lifecycle not implemented.",
        ]
        completed = review_evidence.checkpoint_bullets(
            review_evidence.checkpoint_sections(base), "COMPLETED"
        )
        candidate = replace_checkpoint_section(
            candidate,
            "COMPLETED",
            "\n".join(f"- {item}" for item in completed + completion_evidence),
        )
    return base, candidate


def wo013p_checkpoint_fixture(*, include_evidence: bool = True) -> tuple[str, str]:
    base = review_evidence.git_blob_bytes(
        WO013P_G1_BASE_SHA,
        review_evidence.CHECKPOINT_PATH,
    ).decode("utf-8")
    candidate = replace_checkpoint_section(
        base,
        "STATUS",
        review_evidence.EXPECTED_WO013P_STATUS,
    )
    candidate = candidate.replace("- delta context.\n", "")
    candidate = replace_checkpoint_section(
        candidate,
        "IN PROGRESS",
        f"- {review_evidence.EXPECTED_WO013P_IN_PROGRESS}",
    )
    candidate = replace_checkpoint_section(
        candidate,
        "BLOCKERS",
        review_evidence.EXPECTED_WO013P_BLOCKERS,
    )
    next_step = review_evidence.EXPECTED_WO013P_NEXT_STEP_PREFIX + (
        "\n\nContinue with bounded intent:\n"
        "- provider independence;\n"
        "- stable prompt-prefix/provider-cache adapters only where supported;\n"
        "- deterministic HIVE context identity remains canonical;\n"
        "- provider cache never becomes canonical truth;\n"
        "- cached-provider accounting is measured and reconciled, not guessed;\n"
        "- no Memory lifecycle;\n"
        "- no MCP product surface;\n"
        "- no autonomous executor dispatch;\n"
        "- no full telemetry expansion beyond what is strictly necessary for objective evidence;\n"
        "- no user-managed cache mode required."
    )
    candidate = replace_checkpoint_section(candidate, "NEXT STEP", next_step)
    if include_evidence:
        completed = review_evidence.checkpoint_bullets(
            review_evidence.checkpoint_sections(base), "COMPLETED"
        )
        candidate = replace_checkpoint_section(
            candidate,
            "COMPLETED",
            "\n".join(
                f"- {item}"
                for item in completed + list(review_evidence.WO013P_CANONICAL_COMPLETION_BULLETS)
            ),
        )
    return base, candidate


def wo014p_checkpoint_fixture(*, include_evidence: bool = True) -> tuple[str, str]:
    base = review_evidence.git_blob_bytes(
        WO014P_G1_BASE_SHA,
        review_evidence.CHECKPOINT_PATH,
    ).decode("utf-8")
    candidate = replace_checkpoint_section(
        base,
        "STATUS",
        review_evidence.EXPECTED_WO014P_STATUS,
    )
    candidate = candidate.replace("- provider/prompt cache adapter layer.\n", "")
    candidate = replace_checkpoint_section(
        candidate,
        "IN PROGRESS",
        f"- {review_evidence.EXPECTED_WO014P_IN_PROGRESS}",
    )
    candidate = replace_checkpoint_section(
        candidate,
        "BLOCKERS",
        review_evidence.EXPECTED_WO014P_BLOCKERS,
    )
    next_step = review_evidence.EXPECTED_WO014P_IN_PROGRESS.replace("Preparing", "Prepare", 1)
    next_step += "\n\nContinue with the following bounded intent:\n"
    next_step += "\n".join(
        f"- {intent};" for intent in review_evidence.WO014P_NEXT_STEP_REQUIRED_INTENTS
    )
    next_step += "\n\nDo not implement Memory in the promotion PR."
    candidate = replace_checkpoint_section(candidate, "NEXT STEP", next_step)
    if include_evidence:
        completed = review_evidence.checkpoint_bullets(
            review_evidence.checkpoint_sections(base), "COMPLETED"
        )
        candidate = replace_checkpoint_section(
            candidate,
            "COMPLETED",
            "\n".join(
                f"- {item}"
                for item in completed + list(review_evidence.WO014P_CANONICAL_COMPLETION_BULLETS)
            ),
        )
    return base, candidate


def wo015p_checkpoint_fixture(*, include_evidence: bool = True) -> tuple[str, str]:
    base = review_evidence.git_blob_bytes(
        WO015P_G1_BASE_SHA,
        review_evidence.CHECKPOINT_PATH,
    ).decode("utf-8")
    candidate = replace_checkpoint_section(
        base,
        "STATUS",
        review_evidence.EXPECTED_WO015P_STATUS,
    )
    candidate = candidate.replace("- memory.\n", "")
    candidate = replace_checkpoint_section(
        candidate,
        "IN PROGRESS",
        f"- {review_evidence.EXPECTED_WO015P_IN_PROGRESS}",
    )
    candidate = replace_checkpoint_section(
        candidate,
        "BLOCKERS",
        review_evidence.EXPECTED_WO015P_BLOCKERS,
    )
    candidate = replace_checkpoint_section(
        candidate,
        "NEXT STEP",
        review_evidence.EXPECTED_WO015P_NEXT_STEP_PREFIX,
    )
    if include_evidence:
        completed = review_evidence.checkpoint_bullets(
            review_evidence.checkpoint_sections(base), "COMPLETED"
        )
        candidate = replace_checkpoint_section(
            candidate,
            "COMPLETED",
            "\n".join(
                f"- {item}"
                for item in completed + list(review_evidence.WO015P_CANONICAL_COMPLETION_BULLETS)
            ),
        )
    return base, candidate


def acce_storage_promotion_evidence_fixture() -> dict[str, object]:
    fixture = cast(
        dict[str, object],
        json.loads(json.dumps(acce_storage_evidence_fixture())),
    )
    matrix = cast(list[dict[str, object]], fixture["benchmark_matrix"])
    second_rows: list[dict[str, object]] = []
    for row in matrix:
        logical = cast(int, row["logical_input_bytes"])
        physical = cast(int, row["physical_bytes"])
        zstd_level = cast(int, row["zstd_level"])
        second_rows.append(
            {
                **row,
                "profile_id": f"{row['profile_id']}-candidate2",
                "zstd_level": zstd_level + 1,
                "physical_bytes": physical + 1,
                "compression_ratio": (physical + 1) / logical,
                "compression_savings_bytes": logical - physical - 1,
            }
        )
    matrix.extend(second_rows)
    return fixture


def approved_wo016_lineage_sources_fixture() -> dict[str, object]:
    review_body = (
        "APPROVED — WO-016\n"
        f"Sol review exact HEAD: {WO016_APPROVED_PRODUCT_HEAD}\n"
        "Verdict: APPROVED for exact-head SQUASH merge under HIVE-ADR-019."
    )
    prior_body = (
        "<!-- hive-review-evidence:WO-016 -->\n"
        f"Exact HEAD SHA: `{WO016_APPROVED_PRODUCT_HEAD}`\n"
        "Backend tests: `418 passed, 0 failed, 0 skipped`\n"
        "Dashboard tests: `7 passed, 0 failed`\n"
        "Validate result: **PASS**\n"
        "Integration health result: **PASS**\n"
        "Review Evidence result: **PASS**\n"
        "ACCE Storage Policy evidence: `PASS`; version `acce-storage-policy-v1`, "
        "policy `acce-policy-v1`, canonical loss `0`, LLM/provider calls `0/0`"
    )
    return {
        "product_pr": {
            "number": 55,
            "state": "closed",
            "merged": True,
            "base": {"ref": "main", "sha": WO016_APPROVED_PRODUCT_BASE_SHA},
            "head": {"sha": WO016_APPROVED_PRODUCT_HEAD},
            "merge_commit_sha": WO016_APPROVED_SQUASH_MERGE_SHA,
            "body": "<!-- HIVE-WORK-ORDER: WO-016 -->\nWO-016 READY FOR SOL AUDIT",
        },
        "product_reviews": [
            {
                "id": WO016_APPROVED_SOL_REVIEW_ID,
                "state": "COMMENTED",
                "commit_id": WO016_APPROVED_PRODUCT_HEAD,
                "body": review_body,
            }
        ],
        "merge_commit": {
            "sha": WO016_APPROVED_SQUASH_MERGE_SHA,
            "parents": [{"sha": WO016_APPROVED_PRODUCT_BASE_SHA}],
        },
        "post_merge_run": {
            "id": WO016_APPROVED_POST_MERGE_CI_RUN,
            "event": "push",
            "head_sha": WO016_APPROVED_SQUASH_MERGE_SHA,
            "status": "completed",
            "conclusion": "success",
        },
        "post_merge_jobs": [
            {"name": "Validate", "status": "completed", "conclusion": "success"},
            {
                "name": "Integration health",
                "status": "completed",
                "conclusion": "success",
            },
            {
                "name": "Review Evidence",
                "status": "completed",
                "conclusion": "skipped",
            },
        ],
        "prior_review_comments": [{"body": prior_body}],
    }


def wo016p_checkpoint_fixture(*, include_evidence: bool = True) -> tuple[str, str]:
    base = review_evidence.git_blob_bytes(
        WO016P_G1_BASE_SHA,
        review_evidence.CHECKPOINT_PATH,
    ).decode("utf-8")
    candidate = replace_checkpoint_section(
        base,
        "STATUS",
        review_evidence.EXPECTED_WO016P_STATUS,
    )
    candidate = candidate.replace(
        f"- {review_evidence.EXPECTED_WO016P_PENDING_ITEM}\n",
        "",
    )
    candidate = replace_checkpoint_section(
        candidate,
        "IN PROGRESS",
        f"- {review_evidence.EXPECTED_WO016P_IN_PROGRESS}",
    )
    candidate = replace_checkpoint_section(
        candidate,
        "BLOCKERS",
        review_evidence.EXPECTED_WO016P_BLOCKERS,
    )
    candidate = replace_checkpoint_section(
        candidate,
        "NEXT STEP",
        review_evidence.EXPECTED_WO016P_NEXT_STEP,
    )
    if include_evidence:
        completed = review_evidence.checkpoint_bullets(
            review_evidence.checkpoint_sections(base), "COMPLETED"
        )
        candidate = replace_checkpoint_section(
            candidate,
            "COMPLETED",
            "\n".join(
                f"- {item}"
                for item in completed + list(review_evidence.WO016P_CANONICAL_COMPLETION_BULLETS)
            ),
        )
    return base, candidate


def test_wo012p_g1_scope_is_explicit_and_fail_closed() -> None:
    require_wo012p_g1_scope(
        "WO-012-P-G1",
        WO012P_G1_BASE_SHA,
        sorted(WO012P_G1_ALLOWED_PATHS),
    )
    with pytest.raises(ValueError, match="exact base"):
        require_wo012p_g1_scope(
            "WO-012-P-G1",
            "a" * 40,
            sorted(WO012P_G1_ALLOWED_PATHS),
        )
    for unauthorized in (
        "docs/project-brain/13-CHECKPOINT.md",
        "migrations/0006_bad.py",
        "backend/app/main.py",
    ):
        with pytest.raises(ValueError, match="outside"):
            require_wo012p_g1_scope(
                "WO-012-P-G1",
                WO012P_G1_BASE_SHA,
                ["scripts/review_evidence.py", unauthorized],
            )


def test_wo013p_g1_scope_is_explicit_and_fail_closed() -> None:
    require_wo013p_g1_scope(
        "WO-013-P-G1",
        WO013P_G1_BASE_SHA,
        sorted(WO013P_G1_ALLOWED_PATHS),
    )
    with pytest.raises(ValueError, match="exact base"):
        require_wo013p_g1_scope("WO-013-P-G1", "a" * 40, sorted(WO013P_G1_ALLOWED_PATHS))
    for unauthorized in (
        "docs/project-brain/13-CHECKPOINT.md",
        "docs/project-brain/CANONICAL-SHA256SUMS.txt",
        "migrations/0006_bad.py",
        "backend/app/main.py",
        "dashboard/src/App.tsx",
        ".github/workflows/ci.yml",
    ):
        with pytest.raises(ValueError, match="outside"):
            require_wo013p_g1_scope(
                "WO-013-P-G1",
                WO013P_G1_BASE_SHA,
                ["scripts/review_evidence.py", unauthorized],
            )


def test_unknown_checkpoint_promotions_fail_closed_without_rejecting_history() -> None:
    for historical in (
        "WO-007-P",
        "WO-007-P-C1",
        "WO-008-P",
        "WO-009-P",
        "WO-010-P",
        "WO-011-P",
        "WO-012-P",
        "WO-012-P-G1",
        "WO-013-P",
        "WO-013-P-G1",
    ):
        require_supported_work_order(historical)
    require_supported_work_order(WO014P_G1_WORK_ORDER)
    require_supported_work_order(WO014P_WORK_ORDER)
    require_supported_work_order(WO015P_G1_WORK_ORDER)
    require_supported_work_order(WO015P_WORK_ORDER)
    require_supported_work_order(WO016P_G1_WORK_ORDER)
    require_supported_work_order(WO016P_WORK_ORDER)
    with pytest.raises(ValueError, match="unsupported checkpoint-promotion"):
        require_supported_work_order("WO-018-P")


def test_current_checkpoint_promotion_authorization_separates_history() -> None:
    require_current_work_order_authorization(review_evidence.WO017P_G1_WORK_ORDER)
    require_current_work_order_authorization(review_evidence.WO017P_WORK_ORDER)
    for historical in (
        "WO-010-P",
        "WO-011-P",
        "WO-012-P",
        "WO-012-P-G1",
        "WO-013-P",
        "WO-013-P-G1",
        "WO-007-P-C1",
        WO014P_G1_WORK_ORDER,
        WO014P_WORK_ORDER,
        WO015P_G1_WORK_ORDER,
        WO015P_WORK_ORDER,
        WO016P_G1_WORK_ORDER,
        WO016P_WORK_ORDER,
    ):
        with pytest.raises(ValueError, match="historical checkpoint-promotion"):
            require_current_work_order_authorization(historical)


def test_authorized_base_marker_requires_one_lowercase_exact_sha() -> None:
    base = "a" * 40
    assert parse_authorized_base_marker(f"<!-- HIVE-AUTHORIZED-BASE: {base} -->") == base
    for body, message in (
        ("no marker", "missing exactly one"),
        (
            f"<!-- HIVE-AUTHORIZED-BASE: {base} -->\n<!-- HIVE-AUTHORIZED-BASE: {base} -->",
            "multiple conflicting",
        ),
        ("<!-- HIVE-AUTHORIZED-BASE: not-a-sha -->", "lowercase 40-hex"),
        (f"<!-- HIVE-AUTHORIZED-BASE: {base.upper()} -->", "lowercase 40-hex"),
    ):
        with pytest.raises(ValueError, match=message):
            parse_authorized_base_marker(body)


def test_wo012p_checkpoint_semantics_accept_exact_transition() -> None:
    base, candidate = wo012p_checkpoint_fixture()
    require_wo012p_checkpoint_semantics(base, candidate)
    normalized_whitespace = candidate.replace(
        "Context Fingerprints Foundation approval",
        "Context   Fingerprints   Foundation approval",
        1,
    )
    require_wo012p_checkpoint_semantics(base, normalized_whitespace)


def test_wo013p_checkpoint_semantics_accept_exact_transition() -> None:
    base, candidate = wo013p_checkpoint_fixture()
    require_wo013p_checkpoint_semantics(base, candidate)
    completed = review_evidence.checkpoint_bullets(
        review_evidence.checkpoint_sections(candidate), "COMPLETED"
    )
    assert completed[-5:] == list(review_evidence.WO013P_CANONICAL_COMPLETION_BULLETS)


def test_wo013p_checkpoint_semantics_rejects_closed_grammar_changes() -> None:
    base, candidate = wo013p_checkpoint_fixture()
    completed = review_evidence.checkpoint_bullets(
        review_evidence.checkpoint_sections(candidate), "COMPLETED"
    )
    historical = completed[:-5]
    evidence = completed[-5:]
    malformed = replace_checkpoint_section(
        candidate,
        "COMPLETED",
        "\n".join(
            f"- {item}" for item in historical + [evidence[0] + " extra claim", *evidence[1:]]
        ),
    )
    with pytest.raises(ValueError, match="closed grammar"):
        require_wo013p_checkpoint_semantics(base, malformed)
    missing = replace_checkpoint_section(
        candidate,
        "COMPLETED",
        "\n".join(f"- {item}" for item in historical + evidence[:4]),
    )
    with pytest.raises(ValueError, match="exactly 5"):
        require_wo013p_checkpoint_semantics(base, missing)
    sixth = replace_checkpoint_section(
        candidate,
        "COMPLETED",
        "\n".join(f"- {item}" for item in completed + [evidence[0]]),
    )
    with pytest.raises(ValueError, match="exactly 5"):
        require_wo013p_checkpoint_semantics(base, sixth)


def test_wo012p_checkpoint_semantics_rejects_unrelated_content_inside_each_class() -> None:
    base, candidate = wo012p_checkpoint_fixture()
    completed = review_evidence.checkpoint_bullets(
        review_evidence.checkpoint_sections(candidate), "COMPLETED"
    )
    historical = completed[:-5]
    evidence = completed[-5:]
    extra_clauses = (
        "MCP server is now available.",
        "Telemetry is operational.",
        "Backup/recovery validated.",
        "Unrelated subsystem state recorded.",
        "Documentation note.",
    )

    for index, extra_clause in enumerate(extra_clauses):
        malformed_evidence = evidence[:]
        malformed_evidence[index] = f"{malformed_evidence[index]} {extra_clause}"
        malformed = replace_checkpoint_section(
            candidate,
            "COMPLETED",
            "\n".join(f"- {item}" for item in historical + malformed_evidence),
        )
        with pytest.raises(ValueError, match="closed grammar"):
            require_wo012p_checkpoint_semantics(base, malformed)

    unrelated_prefix = evidence[:]
    unrelated_prefix[0] = f"MCP server is now available. {unrelated_prefix[0]}"
    prefixed = replace_checkpoint_section(
        candidate,
        "COMPLETED",
        "\n".join(f"- {item}" for item in historical + unrelated_prefix),
    )
    with pytest.raises(ValueError, match="closed grammar"):
        require_wo012p_checkpoint_semantics(base, prefixed)

    unrelated_parenthetical = evidence[:]
    unrelated_parenthetical[1] = unrelated_parenthetical[1].replace(
        "Redis TTL 300 seconds",
        "Redis TTL 300 seconds (telemetry is operational)",
        1,
    )
    parenthetical = replace_checkpoint_section(
        candidate,
        "COMPLETED",
        "\n".join(f"- {item}" for item in historical + unrelated_parenthetical),
    )
    with pytest.raises(ValueError, match="closed grammar"):
        require_wo012p_checkpoint_semantics(base, parenthetical)


def test_wo012p_checkpoint_semantics_rejects_missing_or_unrelated_completion_evidence() -> None:
    base, candidate_without_evidence = wo012p_checkpoint_fixture(include_evidence=False)
    with pytest.raises(ValueError, match="exactly 5 authorized"):
        require_wo012p_checkpoint_semantics(base, candidate_without_evidence)

    _, candidate = wo012p_checkpoint_fixture()
    missing_pr = candidate.replace("PR #40", "PR #41", 1)
    with pytest.raises(ValueError, match="completion evidence class 4"):
        require_wo012p_checkpoint_semantics(base, missing_pr)
    completed = review_evidence.checkpoint_bullets(
        review_evidence.checkpoint_sections(candidate), "COMPLETED"
    )
    for unrelated_item in (
        "MCP server is now available.",
        "Telemetry is operational.",
        "Backup/recovery validated.",
        "Unrelated subsystem state recorded.",
        "Documentation note.",
    ):
        unrelated = replace_checkpoint_section(
            candidate,
            "COMPLETED",
            "\n".join(f"- {item}" for item in completed + [unrelated_item]),
        )
        with pytest.raises(ValueError, match="exactly 5 authorized"):
            require_wo012p_checkpoint_semantics(base, unrelated)


def test_wo012p_checkpoint_semantics_rejects_suffix_structure_changes() -> None:
    base, candidate = wo012p_checkpoint_fixture()
    completed = review_evidence.checkpoint_bullets(
        review_evidence.checkpoint_sections(candidate), "COMPLETED"
    )
    historical = completed[:-5]
    evidence = completed[-5:]

    for suffix in (
        evidence[:4],
        evidence + [evidence[0]],
        [evidence[0], evidence[0], evidence[2], evidence[3], evidence[4]],
        evidence + [evidence[3]],
        [evidence[0], evidence[1], evidence[2], "Historical item inserted", *evidence[3:]],
    ):
        malformed = replace_checkpoint_section(
            candidate,
            "COMPLETED",
            "\n".join(f"- {item}" for item in historical + suffix),
        )
        with pytest.raises(ValueError, match="exactly 5|completion evidence class"):
            require_wo012p_checkpoint_semantics(base, malformed)


def test_wo012p_checkpoint_semantics_requires_exact_history_prefix_and_order() -> None:
    base, candidate = wo012p_checkpoint_fixture()
    completed = review_evidence.checkpoint_bullets(
        review_evidence.checkpoint_sections(candidate), "COMPLETED"
    )
    history = completed[:-5]
    evidence = completed[-5:]
    inserted = history[:2] + [evidence[0]] + history[2:] + evidence[1:]
    inserted_candidate = replace_checkpoint_section(
        candidate,
        "COMPLETED",
        "\n".join(f"- {item}" for item in inserted),
    )
    with pytest.raises(ValueError, match="historical COMPLETED"):
        require_wo012p_checkpoint_semantics(base, inserted_candidate)

    reordered = history[:]
    reordered[0], reordered[1] = reordered[1], reordered[0]
    reordered_candidate = replace_checkpoint_section(
        candidate,
        "COMPLETED",
        "\n".join(f"- {item}" for item in reordered + evidence),
    )
    with pytest.raises(ValueError, match="historical COMPLETED"):
        require_wo012p_checkpoint_semantics(base, reordered_candidate)


def test_wo012p_checkpoint_semantics_rejects_wrong_status_pending_or_next_step() -> None:
    base, candidate = wo012p_checkpoint_fixture()
    with pytest.raises(ValueError, match="unexpected checkpoint status"):
        require_wo012p_checkpoint_semantics(
            base,
            candidate.replace(
                review_evidence.EXPECTED_WO012P_STATUS,
                review_evidence.EXPECTED_WO012P_PREVIOUS_STATUS,
                1,
            ),
        )
    with pytest.raises(ValueError, match="remove only"):
        require_wo012p_checkpoint_semantics(base, candidate.replace("- memory.\n", "", 1))
    with pytest.raises(ValueError, match="NEXT STEP"):
        require_wo012p_checkpoint_semantics(
            base,
            candidate.replace(
                review_evidence.EXPECTED_WO012P_NEXT_STEP_PREFIX,
                "Implement Delta Context Foundation",
                1,
            ),
        )


def test_wo012p_manifest_contract_accepts_only_checkpoint_hash_change() -> None:
    base_manifest = review_evidence.git_blob_bytes(
        WO012P_G1_BASE_SHA,
        review_evidence.CANONICAL_MANIFEST_PATH,
    ).decode("utf-8")
    _, candidate_checkpoint = wo012p_checkpoint_fixture()
    candidate_bytes = candidate_checkpoint.encode("utf-8")
    candidate_digest = hashlib.sha256(candidate_bytes).hexdigest()
    candidate_manifest = base_manifest.replace(
        "19cc7371d9219c516f2d42915e4a9512e333aa2469c3647c0673d881513f9c2e",
        candidate_digest,
        1,
    )
    require_wo012p_manifest_contract(base_manifest, candidate_manifest, candidate_bytes)


def test_wo012p_manifest_contract_rejects_hash_path_and_order_changes() -> None:
    base_manifest = review_evidence.git_blob_bytes(
        WO012P_G1_BASE_SHA,
        review_evidence.CANONICAL_MANIFEST_PATH,
    ).decode("utf-8")
    _, candidate_checkpoint = wo012p_checkpoint_fixture()
    candidate_bytes = candidate_checkpoint.encode("utf-8")
    digest = hashlib.sha256(candidate_bytes).hexdigest()
    candidate_manifest = base_manifest.replace(
        "19cc7371d9219c516f2d42915e4a9512e333aa2469c3647c0673d881513f9c2e",
        digest,
        1,
    )
    with pytest.raises(ValueError, match="unauthorized canonical hash"):
        require_wo012p_manifest_contract(
            base_manifest,
            candidate_manifest.replace(
                "f0b384e8e3326821a58fc180d7ab1b81017b14cd689793463731f161b7512ca1",
                "0" * 64,
                1,
            ),
            candidate_bytes,
        )
    with pytest.raises(ValueError, match="path set or order"):
        require_wo012p_manifest_contract(
            base_manifest,
            "\n".join(reversed(candidate_manifest.splitlines())) + "\n",
            candidate_bytes,
        )
    with pytest.raises(ValueError, match="does not match"):
        require_wo012p_manifest_contract(
            base_manifest,
            base_manifest.replace(
                "19cc7371d9219c516f2d42915e4a9512e333aa2469c3647c0673d881513f9c2e",
                "0" * 64,
                1,
            ),
            candidate_bytes,
        )
    with pytest.raises(ValueError, match="duplicate"):
        require_wo012p_manifest_contract(
            base_manifest,
            candidate_manifest + "\n" + candidate_manifest.splitlines()[-1] + "\n",
            candidate_bytes,
        )
    with pytest.raises(ValueError, match="malformed"):
        require_wo012p_manifest_contract(
            base_manifest,
            candidate_manifest.replace("7d0077e4", "z" * 8, 1),
            candidate_bytes,
        )
    with pytest.raises(ValueError, match="path set or order"):
        require_wo012p_manifest_contract(
            base_manifest,
            candidate_manifest.replace("16-DECISIONS-LEDGER.md", "17-UNEXPECTED.md", 1),
            candidate_bytes,
        )


def test_wo012p_scope_requires_exact_two_files_and_registered_base() -> None:
    with pytest.raises(ValueError, match="exact base"):
        require_wo012p_scope(
            "WO-012-P",
            "a" * 40,
            sorted(WO012P_PROMOTION_ALLOWED_PATHS),
            registered_base_sha="b" * 40,
        )
    with pytest.raises(ValueError, match="exactly"):
        require_wo012p_scope(
            "WO-012-P",
            "b" * 40,
            [review_evidence.CHECKPOINT_PATH],
            registered_base_sha="b" * 40,
        )


def test_wo012p_scope_accepts_registered_base_and_exact_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_checkpoint, candidate_checkpoint = wo012p_checkpoint_fixture()
    base_manifest = review_evidence.git_blob_bytes(
        WO012P_G1_BASE_SHA,
        review_evidence.CANONICAL_MANIFEST_PATH,
    ).decode("utf-8")
    candidate_bytes = candidate_checkpoint.encode("utf-8")
    candidate_manifest = base_manifest.replace(
        "19cc7371d9219c516f2d42915e4a9512e333aa2469c3647c0673d881513f9c2e",
        hashlib.sha256(candidate_bytes).hexdigest(),
        1,
    )
    checkpoint_path = tmp_path / review_evidence.CHECKPOINT_PATH
    manifest_path = tmp_path / review_evidence.CANONICAL_MANIFEST_PATH
    checkpoint_path.parent.mkdir(parents=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_bytes(candidate_bytes)
    manifest_path.write_text(candidate_manifest, encoding="utf-8", newline="\n")
    monkeypatch.setattr(review_evidence, "ROOT", tmp_path)

    def fake_git_blob_bytes(revision: str, path: str) -> bytes:
        assert revision == "c" * 40
        return (
            base_checkpoint.encode("utf-8")
            if path == review_evidence.CHECKPOINT_PATH
            else base_manifest.encode("utf-8")
        )

    monkeypatch.setattr(review_evidence, "git_blob_bytes", fake_git_blob_bytes)
    require_wo012p_scope(
        "WO-012-P",
        "c" * 40,
        sorted(WO012P_PROMOTION_ALLOWED_PATHS),
        registered_base_sha="c" * 40,
        authorized_base_sha="c" * 40,
    )


def test_wo012p_scope_requires_authorized_base_to_match_pr_base() -> None:
    for marker in (None, "d" * 40, "A" * 40):
        with pytest.raises(ValueError, match="authorized-base"):
            require_wo012p_scope(
                "WO-012-P",
                "c" * 40,
                sorted(WO012P_PROMOTION_ALLOWED_PATHS),
                registered_base_sha="c" * 40,
                authorized_base_sha=marker,
            )


def test_wo013p_scope_requires_exact_two_files_and_authorized_base() -> None:
    with pytest.raises(ValueError, match="exact base"):
        require_wo013p_scope(
            "WO-013-P",
            "a" * 40,
            sorted(WO013P_PROMOTION_ALLOWED_PATHS),
            registered_base_sha="b" * 40,
            authorized_base_sha="a" * 40,
        )
    with pytest.raises(ValueError, match="exactly"):
        require_wo013p_scope(
            "WO-013-P",
            "b" * 40,
            [review_evidence.CHECKPOINT_PATH],
            registered_base_sha="b" * 40,
            authorized_base_sha="b" * 40,
        )
    with pytest.raises(ValueError, match="authorized-base"):
        require_wo013p_scope(
            "WO-013-P",
            "b" * 40,
            sorted(WO013P_PROMOTION_ALLOWED_PATHS),
            registered_base_sha="b" * 40,
            authorized_base_sha=None,
        )


def test_wo013p_scope_accepts_registered_base_and_exact_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_checkpoint, candidate_checkpoint = wo013p_checkpoint_fixture()
    base_manifest = review_evidence.git_blob_bytes(
        WO013P_G1_BASE_SHA,
        review_evidence.CANONICAL_MANIFEST_PATH,
    ).decode("utf-8")
    candidate_bytes = candidate_checkpoint.encode("utf-8")
    manifest_lines = []
    for line in base_manifest.splitlines(keepends=True):
        parts = line.strip().split(maxsplit=1)
        if len(parts) == 2 and parts[1] == review_evidence.CANONICAL_MANIFEST_CHECKPOINT_NAME:
            line = line.replace(parts[0], hashlib.sha256(candidate_bytes).hexdigest(), 1)
        manifest_lines.append(line)
    candidate_manifest = "".join(manifest_lines)
    checkpoint_path = tmp_path / review_evidence.CHECKPOINT_PATH
    manifest_path = tmp_path / review_evidence.CANONICAL_MANIFEST_PATH
    checkpoint_path.parent.mkdir(parents=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_bytes(candidate_bytes)
    manifest_path.write_text(candidate_manifest, encoding="utf-8", newline="\n")
    monkeypatch.setattr(review_evidence, "ROOT", tmp_path)

    def fake_git_blob_bytes(revision: str, path: str) -> bytes:
        assert revision == "c" * 40
        return (
            base_checkpoint.encode("utf-8")
            if path == review_evidence.CHECKPOINT_PATH
            else base_manifest.encode("utf-8")
        )

    monkeypatch.setattr(review_evidence, "git_blob_bytes", fake_git_blob_bytes)
    require_wo013p_scope(
        "WO-013-P",
        "c" * 40,
        sorted(WO013P_PROMOTION_ALLOWED_PATHS),
        registered_base_sha="c" * 40,
        authorized_base_sha="c" * 40,
    )


def test_wo014p_g1_scope_is_exact_and_fail_closed() -> None:
    require_wo014p_g1_scope(
        WO014P_G1_WORK_ORDER,
        WO014P_G1_BASE_SHA,
        sorted(WO014P_G1_ALLOWED_PATHS),
    )
    with pytest.raises(ValueError, match="exact base"):
        require_wo014p_g1_scope(
            WO014P_G1_WORK_ORDER,
            "a" * 40,
            sorted(WO014P_G1_ALLOWED_PATHS),
        )
    for unauthorized in (
        "docs/project-brain/13-CHECKPOINT.md",
        "migrations/0006_bad.py",
        "backend/app/main.py",
        ".github/workflows/ci.yml",
    ):
        with pytest.raises(ValueError, match="outside"):
            require_wo014p_g1_scope(
                WO014P_G1_WORK_ORDER,
                WO014P_G1_BASE_SHA,
                ["scripts/review_evidence.py", unauthorized],
            )


def test_wo014p_checkpoint_semantics_accept_exact_transition() -> None:
    base, candidate = wo014p_checkpoint_fixture()
    require_wo014p_checkpoint_semantics(base, candidate)


def test_wo014p_checkpoint_semantics_rejects_unrelated_or_incomplete_claims() -> None:
    base, candidate = wo014p_checkpoint_fixture()
    completed = review_evidence.checkpoint_bullets(
        review_evidence.checkpoint_sections(candidate), "COMPLETED"
    )
    history = completed[:-5]
    evidence = completed[-5:]
    malformed = replace_checkpoint_section(
        candidate,
        "COMPLETED",
        "\n".join(
            f"- {item}" for item in history + [evidence[0] + " MCP is complete.", *evidence[1:]]
        ),
    )
    with pytest.raises(ValueError, match="closed grammar"):
        require_wo014p_checkpoint_semantics(base, malformed)
    missing = replace_checkpoint_section(
        candidate,
        "COMPLETED",
        "\n".join(f"- {item}" for item in history + evidence[:4]),
    )
    with pytest.raises(ValueError, match="exactly 5"):
        require_wo014p_checkpoint_semantics(base, missing)
    pending_changed = candidate.replace("- memory.\n", "", 1)
    with pytest.raises(ValueError, match="remove only"):
        require_wo014p_checkpoint_semantics(base, pending_changed)


def test_wo014p_scope_binds_marker_base_current_main_and_g1_support(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_checkpoint, candidate_checkpoint = wo014p_checkpoint_fixture()
    base_manifest = review_evidence.git_blob_bytes(
        WO014P_G1_BASE_SHA,
        review_evidence.CANONICAL_MANIFEST_PATH,
    ).decode("utf-8")
    candidate_bytes = candidate_checkpoint.encode("utf-8")
    candidate_manifest = "".join(
        line.replace(
            line.strip().split(maxsplit=1)[0],
            hashlib.sha256(candidate_bytes).hexdigest(),
            1,
        )
        if (
            len(line.strip().split(maxsplit=1)) == 2
            and line.strip().split(maxsplit=1)[1]
            == review_evidence.CANONICAL_MANIFEST_CHECKPOINT_NAME
        )
        else line
        for line in base_manifest.splitlines(keepends=True)
    )
    checkpoint_path = tmp_path / review_evidence.CHECKPOINT_PATH
    manifest_path = tmp_path / review_evidence.CANONICAL_MANIFEST_PATH
    checkpoint_path.parent.mkdir(parents=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_bytes(candidate_bytes)
    manifest_path.write_text(candidate_manifest, encoding="utf-8", newline="\n")
    monkeypatch.setattr(review_evidence, "ROOT", tmp_path)

    def fake_git_blob_bytes(revision: str, path: str) -> bytes:
        assert revision == "c" * 40
        if path == "scripts/review_evidence.py":
            return b"WO014P_G1_WORK_ORDER"
        if path == review_evidence.CHECKPOINT_PATH:
            return base_checkpoint.encode("utf-8")
        return base_manifest.encode("utf-8")

    monkeypatch.setattr(review_evidence, "git_blob_bytes", fake_git_blob_bytes)
    require_wo014p_scope(
        WO014P_WORK_ORDER,
        "c" * 40,
        sorted(WO014P_PROMOTION_ALLOWED_PATHS),
        registered_base_sha="c" * 40,
        authorized_base_sha="c" * 40,
    )
    with pytest.raises(ValueError, match="authorized-base"):
        require_wo014p_scope(
            WO014P_WORK_ORDER,
            "c" * 40,
            sorted(WO014P_PROMOTION_ALLOWED_PATHS),
            registered_base_sha="c" * 40,
            authorized_base_sha="d" * 40,
        )
    with pytest.raises(ValueError, match="base branch"):
        require_wo014p_scope(
            WO014P_WORK_ORDER,
            "c" * 40,
            sorted(WO014P_PROMOTION_ALLOWED_PATHS),
            base_branch="release",
            registered_base_sha="c" * 40,
            authorized_base_sha="c" * 40,
        )


def test_wo015p_g1_scope_is_exact_and_noncanonical() -> None:
    require_wo015p_g1_scope(
        WO015P_G1_WORK_ORDER,
        WO015P_G1_BASE_SHA,
        sorted(WO015P_G1_ALLOWED_PATHS),
    )
    with pytest.raises(ValueError, match="exact base"):
        require_wo015p_g1_scope(
            WO015P_G1_WORK_ORDER,
            "a" * 40,
            sorted(WO015P_G1_ALLOWED_PATHS),
        )
    for unauthorized in (
        "docs/project-brain/13-CHECKPOINT.md",
        "docs/project-brain/CANONICAL-SHA256SUMS.txt",
        "migrations/0006_memory_lifecycle_provenance.py",
        "backend/app/memory.py",
    ):
        with pytest.raises(ValueError, match="outside|migrations"):
            require_wo015p_g1_scope(
                WO015P_G1_WORK_ORDER,
                WO015P_G1_BASE_SHA,
                ["scripts/review_evidence.py", unauthorized],
            )


def test_wo015p_checkpoint_semantics_accept_only_memory_transition() -> None:
    base, candidate = wo015p_checkpoint_fixture()
    require_wo015p_checkpoint_semantics(base, candidate)
    with pytest.raises(ValueError, match="remove only"):
        altered_pending = candidate.replace(
            "- MCP server product surface",
            "- altered MCP server product surface",
            1,
        )
        require_wo015p_checkpoint_semantics(base, altered_pending)


@pytest.mark.parametrize(
    "suffix",
    [
        "Then prepare the MCP server product surface.",
        "Then add telemetry for the next increment.",
        "Then implement the full Control Center.",
        "Then expand autonomous execution.",
        "Then add arbitrary free text.",
        "Then implement ACCE token scheduling details.",
        "- Add one more bounded intent bullet.",
    ],
)
def test_wo015p_next_step_rejects_all_trailing_content(suffix: str) -> None:
    base, candidate = wo015p_checkpoint_fixture()
    malformed = replace_checkpoint_section(
        candidate,
        "NEXT STEP",
        f"{review_evidence.EXPECTED_WO015P_NEXT_STEP}\n{suffix}",
    )
    with pytest.raises(ValueError, match="exact closed ACCE grammar"):
        require_wo015p_checkpoint_semantics(base, malformed)


def test_wo015p_scope_binds_markers_manifest_and_merged_g1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_checkpoint, candidate_checkpoint = wo015p_checkpoint_fixture()
    base_manifest = review_evidence.git_blob_bytes(
        WO015P_G1_BASE_SHA,
        review_evidence.CANONICAL_MANIFEST_PATH,
    ).decode("utf-8")
    candidate_bytes = candidate_checkpoint.encode("utf-8")
    candidate_manifest = "".join(
        line.replace(
            line.strip().split(maxsplit=1)[0],
            hashlib.sha256(candidate_bytes).hexdigest(),
            1,
        )
        if (
            len(line.strip().split(maxsplit=1)) == 2
            and line.strip().split(maxsplit=1)[1]
            == review_evidence.CANONICAL_MANIFEST_CHECKPOINT_NAME
        )
        else line
        for line in base_manifest.splitlines(keepends=True)
    )
    checkpoint_path = tmp_path / review_evidence.CHECKPOINT_PATH
    manifest_path = tmp_path / review_evidence.CANONICAL_MANIFEST_PATH
    checkpoint_path.parent.mkdir(parents=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_bytes(candidate_bytes)
    manifest_path.write_text(candidate_manifest, encoding="utf-8", newline="\n")
    monkeypatch.setattr(review_evidence, "ROOT", tmp_path)

    def fake_git_blob_bytes(revision: str, path: str) -> bytes:
        assert revision == "d" * 40
        if path == "scripts/review_evidence.py":
            return WO015P_G1_WORK_ORDER.encode("utf-8")
        if path == review_evidence.CHECKPOINT_PATH:
            return base_checkpoint.encode("utf-8")
        return base_manifest.encode("utf-8")

    monkeypatch.setattr(review_evidence, "git_blob_bytes", fake_git_blob_bytes)
    require_wo015p_scope(
        WO015P_WORK_ORDER,
        "d" * 40,
        sorted(WO015P_PROMOTION_ALLOWED_PATHS),
        registered_base_sha="d" * 40,
        authorized_base_sha="d" * 40,
    )
    with pytest.raises(ValueError, match="authorized-base"):
        require_wo015p_scope(
            WO015P_WORK_ORDER,
            "d" * 40,
            sorted(WO015P_PROMOTION_ALLOWED_PATHS),
            registered_base_sha="d" * 40,
            authorized_base_sha="e" * 40,
        )


def test_wo015p_g1_governance_contract_requires_memory_evidence() -> None:
    common = {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }
    evidence = verify_wo015p_g1_governance_contract(
        WO015P_G1_WORK_ORDER,
        WO015P_G1_BASE_SHA,
        sorted(WO015P_G1_ALLOWED_PATHS),
        common,
        {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}},
        {"memory": memory_evidence_fixture()},
        "0006_memory_lifecycle_provenance",
    )
    assert evidence is not None
    assert "active_promotions=WO-015-P-G1,WO-015-P" in evidence
    assert "memory_evidence=PASS" in evidence
    with pytest.raises(ValueError, match="missing mandatory Memory evidence"):
        verify_wo015p_g1_governance_contract(
            WO015P_G1_WORK_ORDER,
            WO015P_G1_BASE_SHA,
            sorted(WO015P_G1_ALLOWED_PATHS),
            common,
            {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}},
            {},
            "0006_memory_lifecycle_provenance",
        )


def test_wo014p_g1_governance_contract_is_self_validating() -> None:
    evidence = verify_wo014p_g1_governance_contract(
        WO014P_G1_WORK_ORDER,
        WO014P_G1_BASE_SHA,
        sorted(WO014P_G1_ALLOWED_PATHS),
        {
            "project_brain_changed": False,
            "checkpoint_changed": False,
            "authorized_paths": [],
        },
        {
            "ruleset_unchanged": True,
            "pull_request": {"auto_merge_armed": False},
        },
        {"context_manager": {"memory_lifecycle_implemented": False}},
        "0005_semantic_retrieval",
    )
    assert evidence is not None
    assert "active_promotions=WO-014-P-G1,WO-014-P" in evidence
    assert "stale_WO-011-P_WO-012-P_WO-013-P=REJECTED" in evidence
    assert "current_WO-017-P=SUPPORTED; unknown_WO-999-P=REJECTED" in evidence
    assert "auto_merge=UNARMED" in evidence

    with pytest.raises(ValueError, match="ruleset"):
        verify_wo014p_g1_governance_contract(
            WO014P_G1_WORK_ORDER,
            WO014P_G1_BASE_SHA,
            sorted(WO014P_G1_ALLOWED_PATHS),
            {
                "project_brain_changed": False,
                "checkpoint_changed": False,
                "authorized_paths": [],
            },
            {
                "ruleset_unchanged": False,
                "pull_request": {"auto_merge_armed": False},
            },
            {"context_manager": {"memory_lifecycle_implemented": False}},
            "0005_semantic_retrieval",
        )


def protect_main_ruleset(
    *,
    required_approving_review_count: int = 0,
    require_last_push_approval: bool = False,
    require_extra_approval_for_unattributed_changes: bool = False,
) -> dict[str, object]:
    return {
        "id": 21934284,
        "name": "Protect main",
        "enforcement": "active",
        "bypass_actors": [],
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {
                "type": "pull_request",
                "parameters": {
                    "required_approving_review_count": required_approving_review_count,
                    "dismiss_stale_reviews_on_push": True,
                    "require_last_push_approval": require_last_push_approval,
                    "required_review_thread_resolution": True,
                    "require_extra_approval_for_unattributed_changes": (
                        require_extra_approval_for_unattributed_changes
                    ),
                    "allowed_merge_methods": ["squash"],
                },
            },
            {
                "type": "required_status_checks",
                "parameters": {
                    "strict_required_status_checks_policy": True,
                    "required_status_checks": [
                        {"context": "Validate"},
                        {"context": "Integration health"},
                        {"context": "Review Evidence"},
                    ],
                },
            },
        ],
    }


def fake_github_governance(
    *,
    ruleset: dict[str, object] | None = None,
    reviews: list[dict[str, object]] | None = None,
    auto_merge: dict[str, object] | None = None,
) -> object:
    selected_ruleset = ruleset if ruleset is not None else protect_main_ruleset()

    def _gh_json(_repository: str, endpoint: str) -> object:
        if "kayzenweb3" in endpoint:
            raise AssertionError("kayzenweb3 collaborator permission must not be queried")
        if endpoint.startswith("rulesets"):
            if endpoint.startswith("rulesets/"):
                return selected_ruleset
            return [{"id": 21934284, "name": "Protect main"}]
        if endpoint == "":
            return {
                "allow_squash_merge": True,
                "allow_merge_commit": False,
                "allow_rebase_merge": False,
                "delete_branch_on_merge": True,
                "allow_auto_merge": True,
            }
        if endpoint.endswith("/reviews"):
            return reviews if reviews is not None else []
        if endpoint.startswith("pulls/"):
            return {
                "state": "open",
                "draft": False,
                "user": {"login": "KayzenRoot"},
                "head": {"sha": "b" * 40},
                "base": {"sha": "a" * 40},
                "auto_merge": auto_merge,
            }
        return None

    return _gh_json


def test_single_account_ruleset_baseline_and_no_kayzenweb3_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(review_evidence, "_gh_json", fake_github_governance())
    evidence = governance_evidence("KayzenRoot/hive", 35)
    ruleset = cast(dict[str, object], evidence["ruleset"])
    approval_gate = cast(dict[str, object], evidence["approval_gate"])
    sol_reviewer = cast(dict[str, object], evidence["sol_reviewer"])
    pull_request = cast(dict[str, object], evidence["pull_request"])

    assert evidence["ruleset_unchanged"] is True
    assert ruleset["required_approving_review_count"] == 0
    assert ruleset["require_last_push_approval"] is False
    assert ruleset["require_extra_approval_for_unattributed_changes"] is False
    assert ruleset["required_contexts"] == [
        "Integration health",
        "Review Evidence",
        "Validate",
    ]
    assert ruleset["allowed_merge_methods"] == ["squash"]
    assert ruleset["bypass_actors"] == []
    assert approval_gate["independent_approval_count"] == 0
    assert sol_reviewer["login"] == "KayzenRoot"
    assert sol_reviewer["can_satisfy_required_approval"] is False
    assert pull_request["auto_merge_armed"] is False


def test_legacy_two_account_ruleset_is_not_the_current_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        review_evidence,
        "_gh_json",
        fake_github_governance(
            ruleset=protect_main_ruleset(
                required_approving_review_count=1,
                require_last_push_approval=True,
                require_extra_approval_for_unattributed_changes=True,
            )
        ),
    )
    evidence = governance_evidence("KayzenRoot/hive", 35)
    assert evidence["ruleset_unchanged"] is False


def test_historical_independent_reviews_do_not_block_pre_sol_handoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        review_evidence,
        "_gh_json",
        fake_github_governance(
            reviews=[
                {
                    "user": {"login": "kayzenweb3"},
                    "state": "APPROVED",
                    "submitted_at": "2026-09-01T00:00:00Z",
                }
            ]
        ),
    )
    evidence = governance_evidence("KayzenRoot/hive", 35)
    approval_gate = cast(dict[str, object], evidence["approval_gate"])
    assert approval_gate["independent_approvers"] == ["kayzenweb3"]
    assert approval_gate["independent_approval_count"] == 1
    require_hive_final_handoff(
        "WO-010-G1",
        35,
        "a" * 40,
        "b" * 40,
        {
            "ruleset_unchanged": True,
            "pull_request": evidence["pull_request"],
            "approval_gate": approval_gate,
        },
    )


def test_wo010_g1_scope_and_manifest_require_unarmed_auto_merge() -> None:
    require_wo010_g1_scope("WO-010-G1", WO010_G1_BASE_SHA, sorted(WO010_G1_ALLOWED_PATHS))
    with pytest.raises(ValueError, match="outside"):
        require_wo010_g1_scope(
            "WO-010-G1",
            WO010_G1_BASE_SHA,
            ["docs/project-brain/13-CHECKPOINT.md", "backend/app/progressive_disclosure.py"],
        )
    manifest = evidence_fixture()
    manifest["work_order"] = "WO-010-G1"
    manifest["base"] = {"branch": "main", "sha": WO010_G1_BASE_SHA}
    manifest["changed_files"] = {
        "count": 1,
        "paths": ["docs/project-brain/16-DECISIONS-LEDGER.md"],
    }
    review_state = cast(dict[str, object], manifest["review_state"])
    review_state["auto_merge_armed"] = False
    review_state["sol_review_state"] = "AWAITING_SOL"
    governance = cast(dict[str, object], manifest["governance"])
    pull_request = cast(dict[str, object], governance["pull_request"])
    pull_request["auto_merge_armed"] = False
    pull_request["auto_merge_method"] = None
    pull_request["auto_merge"] = {
        "armed": False,
        "method": None,
        "enabled_by_login": "",
        "enabled_by_type": "",
        "user_owned": False,
    }
    validate_manifest(manifest)
    review_state["auto_merge_armed"] = True
    with pytest.raises(ValueError, match="unarmed"):
        validate_manifest(manifest)
    review_state["auto_merge_armed"] = False
    review_state["sol_review_state"] = "APPROVED"
    with pytest.raises(ValueError, match="Sol approval"):
        validate_manifest(manifest)


def test_wo010_g1_canonical_change_evidence_is_work_order_aware() -> None:
    intended = [
        "docs/project-brain/13-CHECKPOINT.md",
        "docs/project-brain/16-DECISIONS-LEDGER.md",
        "docs/project-brain/CANONICAL-SHA256SUMS.txt",
    ]
    evidence = canonical_change_evidence(intended, "WO-010-G1")
    assert evidence["authorized_paths"] == intended

    unrelated = canonical_change_evidence(
        intended + ["docs/project-brain/04-ARCHITECTURE.md"], "WO-010-G1"
    )
    assert unrelated["authorized_paths"] == intended

    non_g1 = canonical_change_evidence(intended, "WO-011")
    assert non_g1["authorized_paths"] == [
        "docs/project-brain/13-CHECKPOINT.md",
        "docs/project-brain/CANONICAL-SHA256SUMS.txt",
    ]


def test_wo010_g1_summary_prints_all_authorized_canonical_paths() -> None:
    manifest = evidence_fixture()
    manifest["work_order"] = "WO-010-G1"
    manifest["changed_files"] = {
        "count": 3,
        "paths": [
            "docs/project-brain/13-CHECKPOINT.md",
            "docs/project-brain/16-DECISIONS-LEDGER.md",
            "docs/project-brain/CANONICAL-SHA256SUMS.txt",
        ],
    }
    summary = summary_markdown(manifest, "https://example.invalid/run/1")
    assert "docs/project-brain/13-CHECKPOINT.md" in summary
    assert "docs/project-brain/16-DECISIONS-LEDGER.md" in summary
    assert "docs/project-brain/CANONICAL-SHA256SUMS.txt" in summary


def test_g1_manifest_records_user_owned_identity_and_scope() -> None:
    manifest = evidence_fixture()
    manifest["work_order"] = "WO-008-G1"
    manifest["base"] = {"branch": "main", "sha": WO008_G1_BASE_SHA}
    manifest["changed_files"] = {
        "count": 1,
        "paths": ["scripts/review_evidence.py"],
    }

    validate_manifest(manifest)
    review_state = cast(dict[str, object], manifest["review_state"])
    assert review_state["auto_merge_owner_login"] == "KayzenRoot"
    assert review_state["auto_merge_owner_type"] == "User"
    assert review_state["auto_merge_user_owned"] is True


def test_wo009_scope_rejects_wrong_base_and_canonical_changes() -> None:
    require_wo009_scope("WO-009", WO009_BASE_SHA, ["backend/app/context_manager.py"])
    with pytest.raises(ValueError, match="exact base"):
        require_wo009_scope("WO-009", "a" * 40, ["backend/app/context_manager.py"])
    with pytest.raises(ValueError, match="canonical Project Brain"):
        require_wo009_scope("WO-009", WO009_BASE_SHA, ["docs/project-brain/13-CHECKPOINT.md"])


def test_wo010_scope_rejects_wrong_base_canonical_and_migrations() -> None:
    require_wo010_scope("WO-010", WO010_BASE_SHA, ["backend/app/progressive_disclosure.py"])
    with pytest.raises(ValueError, match="exact base"):
        require_wo010_scope("WO-010", "a" * 40, ["backend/app/progressive_disclosure.py"])
    with pytest.raises(ValueError, match="canonical Project Brain"):
        require_wo010_scope("WO-010", WO010_BASE_SHA, ["docs/project-brain/13-CHECKPOINT.md"])
    with pytest.raises(ValueError, match="migrations"):
        require_wo010_scope(
            "WO-010",
            WO010_BASE_SHA,
            ["migrations/versions/0006_progressive_disclosure.py"],
        )


def native_auto_merge_pull_request(auto_merge: object) -> dict[str, object]:
    return {
        "state": "open",
        "draft": False,
        "head": {"sha": "b" * 40},
        "auto_merge": auto_merge,
    }


def merge_authorization_state(**overrides: object) -> dict[str, object]:
    state: dict[str, object] = {
        "sol_approved": True,
        "auto_merge_armed": False,
        "pr_state": "open",
        "is_draft": False,
        "head_sha": "b" * 40,
        "base_sha": "a" * 40,
        "base_branch": "main",
        "ruleset_valid": True,
        "unresolved_threads": 0,
        "merge_method": "squash",
        "mergeable": True,
        "mergeable_state": "clean",
        "required_checks": {
            "Validate": "success",
            "Integration health": "success",
            "Review Evidence": "success",
        },
    }
    state.update(overrides)
    return state


def test_clean_post_sol_state_authorizes_direct_squash_without_auto_merge() -> None:
    decision = authorize_merge_action(
        merge_authorization_state(),
        expected_head_sha="b" * 40,
        expected_base_sha="a" * 40,
    )

    assert decision == {
        "authorized": True,
        "action": "DIRECT_SQUASH_MERGE",
        "merge_method": "squash",
        "expected_head_sha": "b" * 40,
        "reason": "all safety gates are green on the exact audited HEAD",
    }


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"head_sha": "c" * 40}, "HEAD moved"),
        ({"base_sha": "c" * 40}, "base"),
        (
            {
                "required_checks": {
                    "Validate": "success",
                    "Integration health": "success",
                    "Review Evidence": "failure",
                }
            },
            "not green",
        ),
        (
            {
                "required_checks": {
                    "Validate": "success",
                    "Integration health": "success",
                }
            },
            "missing",
        ),
        ({"mergeable": False, "mergeable_state": "dirty"}, "mergeability"),
        ({"is_draft": True}, "Ready"),
        ({"unresolved_threads": 1}, "threads"),
        ({"ruleset_valid": False}, "ruleset"),
        ({"merge_method": "merge"}, "SQUASH"),
        ({"auto_merge_armed": True}, "unarmed"),
    ],
)
def test_post_sol_direct_merge_fails_closed(overrides: dict[str, object], message: str) -> None:
    decision = authorize_merge_action(
        merge_authorization_state(**overrides),
        expected_head_sha="b" * 40,
        expected_base_sha="a" * 40,
    )

    assert decision["authorized"] is False
    assert decision["action"] == "REJECT"
    assert message.casefold() in str(decision["reason"]).casefold()


def test_pending_required_checks_allow_only_conditional_auto_merge() -> None:
    decision = authorize_merge_action(
        merge_authorization_state(
            mergeable_state="blocked",
            required_checks={
                "Validate": "success",
                "Integration health": "pending",
                "Review Evidence": "success",
            },
        ),
        expected_head_sha="b" * 40,
        expected_base_sha="a" * 40,
    )

    assert decision["authorized"] is True
    assert decision["action"] == "ARM_SQUASH_AUTO_MERGE"
    assert decision["pending_checks"] == ["Integration health"]


def test_sol_approval_is_required_for_any_post_sol_merge_action() -> None:
    decision = authorize_merge_action(
        merge_authorization_state(sol_approved=False),
        expected_head_sha="b" * 40,
        expected_base_sha="a" * 40,
    )

    assert decision["authorized"] is False
    assert decision["action"] == "REJECT"


def test_user_owned_squash_auto_merge_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pull_request = native_auto_merge_pull_request(
        {
            "merge_method": "squash",
            "enabled_by": {"login": "KayzenRoot", "type": "User"},
        }
    )
    monkeypatch.setattr(review_evidence, "_gh_json", lambda _repository, _endpoint: pull_request)

    assert verify_native_auto_merge("KayzenRoot/hive", 42, "b" * 40) == {
        "armed": True,
        "method": "squash",
        "enabled_by_login": "KayzenRoot",
        "enabled_by_type": "User",
        "user_owned": True,
    }


@pytest.mark.parametrize(
    ("auto_merge", "message"),
    [
        (
            {
                "merge_method": "squash",
                "enabled_by": {"login": "github-actions[bot]", "type": "Bot"},
            },
            "github-actions",
        ),
        (
            {
                "merge_method": "squash",
                "enabled_by": {"login": "automation-app", "type": "App"},
            },
            "user-owned",
        ),
        (
            {
                "merge_method": "squash",
                "enabled_by": {"login": "automation", "type": "Bot"},
            },
            "user-owned",
        ),
        (None, "not armed"),
        (
            {
                "merge_method": "merge",
                "enabled_by": {"login": "KayzenRoot", "type": "User"},
            },
            "SQUASH",
        ),
    ],
)
def test_native_auto_merge_verification_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    auto_merge: object,
    message: str,
) -> None:
    pull_request = native_auto_merge_pull_request(auto_merge)
    monkeypatch.setattr(review_evidence, "_gh_json", lambda _repository, _endpoint: pull_request)

    with pytest.raises(ValueError, match=message):
        verify_native_auto_merge("KayzenRoot/hive", 42, "b" * 40)


def test_native_auto_merge_verification_rejects_draft_and_moved_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pull_request = native_auto_merge_pull_request(
        {
            "merge_method": "squash",
            "enabled_by": {"login": "KayzenRoot", "type": "User"},
        }
    )
    monkeypatch.setattr(review_evidence, "_gh_json", lambda _repository, _endpoint: pull_request)
    pull_request["draft"] = True
    with pytest.raises(ValueError, match="Ready"):
        verify_native_auto_merge("KayzenRoot/hive", 42, "b" * 40)

    pull_request["draft"] = False
    cast(dict[str, object], pull_request["head"])["sha"] = "c" * 40
    with pytest.raises(ValueError, match="head moved"):
        verify_native_auto_merge("KayzenRoot/hive", 42, "b" * 40)


def test_auto_merge_identity_is_recorded_without_secret_fields() -> None:
    evidence = auto_merge_evidence(
        {
            "merge_method": "squash",
            "enabled_by": {
                "login": "KayzenRoot",
                "type": "User",
                "token": "must-not-be-copied",
            },
        }
    )

    assert evidence == {
        "armed": True,
        "method": "squash",
        "enabled_by_login": "KayzenRoot",
        "enabled_by_type": "User",
        "user_owned": True,
    }
    assert "must-not-be-copied" not in json.dumps(evidence)


def test_review_evidence_rejects_merge_claim() -> None:
    manifest = evidence_fixture()
    manifest["review_state"] = {"status": "MERGED", "merge_performed": True}
    try:
        validate_manifest(manifest)
    except ValueError as error:
        assert "merge" in str(error)
    else:
        raise AssertionError("merged evidence must be rejected")


def test_review_evidence_aggregates_wrapped_junit_and_strips_dashboard_ansi(
    tmp_path: Path,
) -> None:
    junit = tmp_path / "backend-junit.xml"
    junit.write_text(
        '<testsuites><testsuite tests="81" failures="0" errors="0" skipped="0" /></testsuites>',
        encoding="utf-8",
    )
    assert junit_counts(junit) == {"passed": 81, "failed": 0, "skipped": 0, "errors": 0}
    assert dashboard_counts("\x1b[2m Tests 7 passed (7)\x1b[0m") == {
        "passed": 7,
        "failed": 0,
        "skipped": 0,
    }


def test_warning_evidence_is_deterministic_deduplicated_and_rendered() -> None:
    evidence = "\n".join(
        [
            "WARNING Memory overcommit must be enabled for Redis / vm.overcommit_memory.",
            "WARNING Memory overcommit must be enabled for Redis / vm.overcommit_memory.",
            "npm warn deprecated whatwg-encoding@3.1.1",
            "npm warn deprecated whatwg-encoding@3.1.1",
            "Node 20 is being deprecated for an action runtime.",
            "Node 20 is being deprecated for an action runtime.",
        ]
    )
    warnings = warnings_evidence(evidence)
    assert warnings == {
        "status": "RECORDED",
        "count": 3,
        "items": [
            "Redis host warning observed: vm.overcommit_memory is disabled.",
            "npm dependency deprecation warning observed.",
            "GitHub Actions Node runtime deprecation warning observed.",
        ],
    }
    manifest = evidence_fixture()
    cast(dict[str, object], manifest["evidence"])["warnings"] = warnings
    summary = summary_markdown(manifest, "https://example.invalid/run/1")
    assert "Known warnings: `3` recorded" in summary
    for item in cast(list[str], warnings["items"]):
        assert item in summary


def test_service_log_redaction_preserves_warning_without_credentials() -> None:
    captured = (
        "redis | WARNING Memory overcommit must be enabled for vm.overcommit_memory.\n"
        "api | DATABASE_URL=postgres://hive:secret@postgres:5432/hive\n"
        "api | token=ghp_1234567890abcdef\n"
    )
    safe = redact_service_logs(captured)
    assert "vm.overcommit_memory" in safe
    assert "secret" not in safe
    assert "ghp_1234567890abcdef" not in safe
    assert "[REDACTED]" in safe


def test_service_log_capture_preserves_command_failure_status(tmp_path: Path) -> None:
    output = tmp_path / "integration-logs" / "service-logs.log"
    status = capture_service_logs(
        output,
        (sys.executable, "-c", "print('bounded service output'); raise SystemExit(7)"),
    )
    assert status == 7
    assert output.read_text(encoding="utf-8") == "bounded service output\n"


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


def test_future_work_order_template_uses_single_account_stage_gate() -> None:
    body = render_body(
        work_order="WO-011",
        pr_number=36,
        branch="feature/wo011-future",
        base_sha="a" * 40,
        head_sha="b" * 40,
        artifact_name="hive-review-evidence-WO-011-b",
        ruleset_before="baseline",
        ruleset_after="unchanged",
        merge_before="unarmed",
        merge_after="unarmed",
    )
    folded = body.casefold()
    assert "kayzenroot" in folded
    assert "awaiting_sol" in folded
    assert "auto-merge nativo desarmado" in folded
    assert "sol merge authorization" in folded
    assert "squash direto" in folded
    assert "auto-merge nativo squash" in folded
    assert "push ci" in folded
    assert "sol arms auto-merge" not in folded
    assert "kayzenweb3" not in folded
    assert "aprovação independente elegível" not in folded
    assert "independent native approval" not in folded


def test_g1_pr_body_describes_identity_correction() -> None:
    body = render_body(
        work_order="WO-008-G1",
        pr_number=30,
        branch="fix/wo008-postmerge-ci-automerge-identity",
        base_sha="a" * 40,
        head_sha="b" * 40,
        artifact_name="hive-review-evidence-WO-008-G1-b",
        ruleset_before="old",
        ruleset_after="unchanged",
        merge_before="old",
        merge_after="unchanged",
    )

    assert body.startswith("<!-- HIVE-WORK-ORDER: WO-008-G1 -->")
    assert "GITHUB_TOKEN" in body
    assert "gh pr merge --auto" in body
    assert "python -m pytest" in body
    assert "Riscos conhecidos" in body
    assert "docs/project-brain/13-CHECKPOINT.md" in body
    assert "WO-008-G1 READY FOR SOL GITHUB AUDIT" in body
    assert "fundação de reranking" not in body


def test_wo009_pr_body_describes_context_manager_handoff() -> None:
    body = render_body(
        work_order="WO-009",
        pr_number=32,
        branch="feature/wo009-context-manager-foundation",
        base_sha="a" * 40,
        head_sha="b" * 40,
        artifact_name="hive-review-evidence-WO-009-b",
        ruleset_before="old",
        ruleset_after="unchanged",
        merge_before="old",
        merge_after="unchanged",
        auto_merge_owner_login="KayzenRoot",
        auto_merge_owner_type="User",
    )

    assert body.startswith("<!-- HIVE-WORK-ORDER: WO-009 -->")
    assert "/projects/{project_id}/tasks/{task_id}/context" in body
    assert "Auto-merge owner: `KayzenRoot` (User)" in body
    assert "context-capsule-v1" in body
    assert "CHECKPOINT -> SCOPE -> DEFINITION_OF_DONE -> ARCHITECTURE -> DECISIONS" in body
    assert "mandatory_governance_coverage" in body
    assert "WO-009 READY FOR SOL GITHUB AUDIT" in body


def test_wo010_g1_pr_body_describes_single_account_governance() -> None:
    body = render_body(
        work_order="WO-010-G1",
        pr_number=35,
        branch="governance/wo010-g1-single-account",
        base_sha="a" * 40,
        head_sha="b" * 40,
        artifact_name="hive-review-evidence-WO-010-G1-b",
        ruleset_before="approvals=1",
        ruleset_after="approvals=0",
        merge_before="old",
        merge_after="unchanged",
    )

    assert body.startswith("<!-- HIVE-WORK-ORDER: WO-010-G1 -->")
    assert "KayzenRoot" in body
    assert "kayzenweb3" in body
    assert "auto-merge desarmado" in body
    assert "SOL MERGE AUTHORIZATION" in body
    assert "SQUASH no HEAD" in body
    assert "checks obrigatórios legítimos estiverem pendentes" in body
    assert "WO-010-G1 READY FOR SOL AUDIT" in body
    assert "21934284" in body


def test_wo010_pr_body_describes_progressive_disclosure_handoff() -> None:
    body = render_body(
        work_order="WO-010",
        pr_number=34,
        branch="feature/wo010-progressive-disclosure-foundation",
        base_sha="a" * 40,
        head_sha="b" * 40,
        artifact_name="hive-review-evidence-WO-010-b",
        ruleset_before="old",
        ruleset_after="unchanged",
        merge_before="old",
        merge_after="unchanged",
        auto_merge_owner_login="KayzenRoot",
        auto_merge_owner_type="User",
    )

    assert body.startswith("<!-- HIVE-WORK-ORDER: WO-010 -->")
    assert "L0 Project capsule" in body
    assert "disclosure_level" in body
    assert "adaptive_token_budget_implemented: false" in body
    assert "Auto-merge permanece desarmado" in body
    assert "WO-010 READY FOR SOL GITHUB AUDIT" in body
    assert "## 27. Proposta de checkpoint para WO-010-P" in body


def test_wo012_pr_body_describes_fingerprint_handoff() -> None:
    body = render_body(
        work_order="WO-012",
        pr_number=40,
        branch="feature/wo012-context-fingerprints-foundation",
        base_sha="a" * 40,
        head_sha="b" * 40,
        artifact_name="hive-review-evidence-WO-012-b",
        ruleset_before="unchanged",
        ruleset_after="unchanged",
        merge_before="unarmed",
        merge_after="unarmed",
    )

    assert body.startswith("<!-- HIVE-WORK-ORDER: WO-012 -->")
    assert "context_fingerprint" in body
    assert "SHA-256" in body
    assert "FLUSHDB" in body
    assert "Auto-merge permanece desarmado" in body
    assert "Sol Review State: AWAITING_SOL" in body


def test_wo013_pr_body_describes_delta_context_handoff() -> None:
    body = render_body(
        work_order="WO-013",
        pr_number=43,
        branch="feature/wo013-delta-context-foundation",
        base_sha=WO013_BASE_SHA,
        head_sha="b" * 40,
        artifact_name="hive-review-evidence-WO-013-b",
        ruleset_before="unchanged",
        ruleset_after="unchanged",
        merge_before="unarmed",
        merge_after="unarmed",
    )

    assert body.startswith("<!-- HIVE-WORK-ORDER: WO-013 -->")
    assert "delta-context-v1" in body
    assert "context-output-v2" in body
    assert "context/delta" in body
    assert "WO-013 READY FOR SOL AUDIT" in body
    assert "Sol Review State: AWAITING_SOL" in body


def test_wo012p_g1_pr_body_is_explicit_and_noncanonical() -> None:
    body = render_body(
        work_order="WO-012-P-G1",
        pr_number=41,
        branch="governance/wo012p-review-evidence-support",
        base_sha=WO012P_G1_BASE_SHA,
        head_sha="b" * 40,
        artifact_name="hive-review-evidence-WO-012-P-G1-b",
        ruleset_before="21934284 unchanged",
        ruleset_after="21934284 unchanged",
        merge_before="unarmed",
        merge_after="unarmed",
    )
    assert body.startswith("<!-- HIVE-WORK-ORDER: WO-012-P-G1 -->")
    assert body.count("HIVE-WORK-ORDER") == 1
    assert "Arquivos canônicos alterados: nenhum" in body
    assert "WO-013-P" in body
    assert "nenhum checkpoint foi promovido" in body
    assert "Sol Review State: AWAITING_SOL" in body


def test_wo012p_pr_body_is_promotion_specific() -> None:
    body = render_body(
        work_order="WO-012-P",
        pr_number=42,
        branch="checkpoint/wo012-context-fingerprints-close",
        base_sha="a" * 40,
        head_sha="b" * 40,
        artifact_name="hive-review-evidence-WO-012-P-b",
        ruleset_before="21934284 unchanged",
        ruleset_after="21934284 unchanged",
        merge_before="unarmed",
        merge_after="unarmed",
    )
    folded = body.casefold()
    assert body.startswith("<!-- HIVE-WORK-ORDER: WO-012-P -->")
    assert body.splitlines()[1] == f"<!-- HIVE-AUTHORIZED-BASE: {'a' * 40} -->"
    assert body.count("HIVE-WORK-ORDER") == 1
    assert body.splitlines().count(f"<!-- HIVE-AUTHORIZED-BASE: {'a' * 40} -->") == 1
    assert "docs/project-brain/13-checkpoint.md" in folded
    assert "canonical-sha256sums.txt" in folded
    assert "delta context" in folded
    assert "não implementa delta context" in folded
    assert "auto-merge fica" in folded
    assert "awaiting_sol" in folded


def test_wo013p_g1_pr_body_is_governance_only_and_noncanonical() -> None:
    body = render_body(
        work_order="WO-013-P-G1",
        pr_number=44,
        branch="governance/wo013p-review-evidence-support",
        base_sha=WO013P_G1_BASE_SHA,
        head_sha="b" * 40,
        artifact_name="hive-review-evidence-WO-013-P-G1-b",
        ruleset_before="21934284 unchanged",
        ruleset_after="21934284 unchanged",
        merge_before="unarmed",
        merge_after="unarmed",
    )
    folded = body.casefold()
    assert body.startswith("<!-- HIVE-WORK-ORDER: WO-013-P-G1 -->")
    assert body.count("HIVE-WORK-ORDER") == 1
    assert "project brain" in folded
    assert "nenhum checkpoint foi promovido" in folded
    assert "provider/prompt cache" in folded
    assert "auto-merge: unarmed" in folded
    assert "sol review state: awaiting_sol" in folded


def test_wo013p_pr_body_is_exact_two_file_promotion_specific() -> None:
    base = "d" * 40
    body = render_body(
        work_order="WO-013-P",
        pr_number=45,
        branch="checkpoint/wo013-delta-context-close",
        base_sha=base,
        head_sha="e" * 40,
        artifact_name="hive-review-evidence-WO-013-P-e",
        ruleset_before="21934284 unchanged",
        ruleset_after="21934284 unchanged",
        merge_before="unarmed",
        merge_after="unarmed",
    )
    folded = body.casefold()
    assert body.startswith("<!-- HIVE-WORK-ORDER: WO-013-P -->")
    assert body.splitlines()[1] == f"<!-- HIVE-AUTHORIZED-BASE: {base} -->"
    assert body.count("HIVE-WORK-ORDER") == 1
    assert body.splitlines().count(f"<!-- HIVE-AUTHORIZED-BASE: {base} -->") == 1
    assert "docs/project-brain/13-checkpoint.md" in folded
    assert "canonical-sha256sums.txt" in folded
    assert "delta context foundation approved" in folded
    assert "exactly five bullets" in folded
    assert "auto-merge permanece unarmed" in folded
    assert "awaiting_sol" in folded


def test_wo014p_g1_pr_body_is_governance_only_and_noncanonical() -> None:
    body = render_body(
        work_order=WO014P_G1_WORK_ORDER,
        pr_number=48,
        branch="governance/wo014p-review-evidence-support",
        base_sha=WO014P_G1_BASE_SHA,
        head_sha="b" * 40,
        artifact_name="hive-review-evidence-WO-014-P-G1-b",
        ruleset_before="21934284 unchanged",
        ruleset_after="21934284 unchanged",
        merge_before="unarmed",
        merge_after="unarmed",
    )
    folded = body.casefold()
    assert body.startswith("<!-- HIVE-WORK-ORDER: WO-014-P-G1 -->")
    assert body.count("HIVE-WORK-ORDER") == 1
    assert not any(line.startswith("<!-- HIVE-AUTHORIZED-BASE:") for line in body.splitlines())
    assert "project brain" in folded
    assert "checkpoint" in folded
    assert "memory" in folded
    assert "auto-merge permanece unarmed" in folded
    assert "sol review state: awaiting_sol" in folded
    assert "wo-014-p-g1 ready for sol audit" in folded


def test_wo014p_pr_body_emits_runtime_two_marker_promotion_contract() -> None:
    base = "c" * 40
    body = render_body(
        work_order=WO014P_WORK_ORDER,
        pr_number=49,
        branch="checkpoint/wo014-provider-prompt-cache-close",
        base_sha=base,
        head_sha="d" * 40,
        artifact_name="hive-review-evidence-WO-014-P-d",
        ruleset_before="21934284 unchanged",
        ruleset_after="21934284 unchanged",
        merge_before="unarmed",
        merge_after="unarmed",
    )
    folded = body.casefold()
    assert body.startswith(f"<!-- HIVE-WORK-ORDER: {WO014P_WORK_ORDER} -->")
    assert body.splitlines()[1] == f"<!-- HIVE-AUTHORIZED-BASE: {base} -->"
    assert body.count("HIVE-WORK-ORDER") == 1
    assert sum(line.startswith("<!-- HIVE-AUTHORIZED-BASE:") for line in body.splitlines()) == 1
    assert "runtime" in folded
    assert "marker == pr base == current origin/main" in folded
    assert "docs/project-brain/13-checkpoint.md" in folded
    assert "canonical-sha256sums.txt" in folded
    assert "exatamente cinco bullets" in folded
    assert "awaiting_sol" in folded


def test_consolidated_artifact_contains_the_required_audit_inputs(tmp_path: Path) -> None:
    manifest = evidence_fixture()
    manifest["large_audit_field"] = "x" * review_evidence.MAX_EVIDENCE_CHARS
    write_consolidated_artifact(tmp_path, manifest, "summary\n")
    expected = {
        "changed-files.txt",
        "migration-head.txt",
        "validation-summary.txt",
        "validation-results.txt",
        "integration-summary.json",
        "integration-results.txt",
        "service-logs.log",
        "warnings-evidence.json",
        "benchmark.json",
        "failure-diagnostics.txt",
        "review-manifest.json",
        "review-summary.md",
        "github-governance.json",
    }
    assert expected <= {path.name for path in tmp_path.iterdir()}
    assert json.loads((tmp_path / "review-manifest.json").read_text(encoding="utf-8")) == manifest


def test_consolidated_artifact_contains_captured_service_warning_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    integration_logs = tmp_path / "integration-logs"
    integration_logs.mkdir()
    service_log = (
        "redis-1 | WARNING Memory overcommit must be enabled for Redis / vm.overcommit_memory.\n"
    )
    (integration_logs / "service-logs.log").write_text(service_log, encoding="utf-8")
    monkeypatch.setattr(review_evidence, "INTEGRATION_LOGS", integration_logs)
    output = tmp_path / "review-evidence"

    write_consolidated_artifact(output, evidence_fixture(), "summary\n")

    assert (output / "service-logs.log").read_text(encoding="utf-8") == service_log
    warnings = json.loads((output / "warnings-evidence.json").read_text(encoding="utf-8"))
    assert warnings == {"status": "NONE", "count": 0, "items": []}


def test_ci_persists_bounded_service_logs_and_uses_supported_action_majors() -> None:
    workflow = (Path(__file__).parents[2] / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert DEFAULT_COMMAND == ("docker", "compose", "logs", "--no-color", "--tail=200")
    assert "on:\n  push:\n    branches:\n      - main" in workflow
    assert "--verify-auto-merge" not in workflow
    assert "gh pr merge" not in workflow
    assert "tmp/integration-logs/service-logs.log" in workflow
    assert "path: |\n            tmp/validation\n            tmp/integration-logs" in workflow
    assert "actions/upload-artifact@v7" in workflow
    assert "actions/download-artifact@v8" in workflow


def test_context_manager_review_evidence_fails_closed_when_missing_or_incomplete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    integration_logs = tmp_path / "integration-logs"
    integration_logs.mkdir()
    payload = {
        "status": "PASS",
        **{field: True for field in CONTEXT_MANAGER_REQUIRED_FIELDS},
        "mandatory_governance_kind_sequence": [
            "CHECKPOINT",
            "SCOPE",
            "DEFINITION_OF_DONE",
            "ARCHITECTURE",
            "DECISIONS",
        ],
        "llm_calls": 0,
    }
    (integration_logs / "context-manager.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    monkeypatch.setattr(review_evidence, "INTEGRATION_LOGS", integration_logs)

    evidence = context_manager_evidence()
    assert evidence["status"] == "PASS"
    require_wo009_context_manager_evidence("WO-009", {"context_manager": evidence})

    incomplete = dict(payload)
    incomplete["checkpoint_first"] = False
    (integration_logs / "context-manager.json").write_text(
        json.dumps(incomplete),
        encoding="utf-8",
    )
    failed = context_manager_evidence()
    assert failed["status"] == "FAIL"
    with pytest.raises(ValueError, match="Context Manager evidence"):
        require_wo009_context_manager_evidence("WO-009", {"context_manager": failed})

    (integration_logs / "context-manager.json").write_text("{malformed", encoding="utf-8")
    assert context_manager_evidence()["status"] == "UNKNOWN"

    missing_coverage = dict(payload)
    del missing_coverage["mandatory_governance_coverage"]
    (integration_logs / "context-manager.json").write_text(
        json.dumps(missing_coverage),
        encoding="utf-8",
    )
    assert context_manager_evidence()["status"] == "UNKNOWN"
    with pytest.raises(ValueError, match="Context Manager evidence"):
        require_wo009_context_manager_evidence(
            "WO-009",
            {"context_manager": context_manager_evidence()},
        )

    false_coverage = dict(payload)
    false_coverage["mandatory_governance_coverage"] = False
    (integration_logs / "context-manager.json").write_text(
        json.dumps(false_coverage),
        encoding="utf-8",
    )
    false_evidence = context_manager_evidence()
    assert false_evidence["status"] == "FAIL"
    with pytest.raises(ValueError, match="mandatory_governance_coverage"):
        require_wo009_context_manager_evidence("WO-009", {"context_manager": false_evidence})

    wrong_sequence = dict(payload)
    wrong_sequence["mandatory_governance_kind_sequence"] = ["CHECKPOINT", "SCOPE"]
    (integration_logs / "context-manager.json").write_text(
        json.dumps(wrong_sequence),
        encoding="utf-8",
    )
    sequence_evidence = context_manager_evidence()
    assert sequence_evidence["status"] == "FAIL"
    with pytest.raises(ValueError, match="mandatory governance kinds"):
        require_wo009_context_manager_evidence("WO-009", {"context_manager": sequence_evidence})


def test_wo010_progressive_disclosure_review_evidence_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    integration_logs = tmp_path / "integration-logs"
    integration_logs.mkdir()
    payload = {
        "status": "PASS",
        **{field: True for field in CONTEXT_MANAGER_REQUIRED_FIELDS},
        "mandatory_governance_kind_sequence": [
            "CHECKPOINT",
            "SCOPE",
            "DEFINITION_OF_DONE",
            "ARCHITECTURE",
            "DECISIONS",
        ],
        "llm_calls": 0,
        **{field: True for field in review_evidence.PROGRESSIVE_DISCLOSURE_REQUIRED_FIELDS},
        **{field: True for field in review_evidence.PROGRESSIVE_DISCLOSURE_C1_FIELDS},
        **{field: True for field in review_evidence.PROGRESSIVE_DISCLOSURE_C2_FIELDS},
        "disclosure_llm_calls": 0,
        "adaptive_token_budget_implemented": False,
    }
    (integration_logs / "context-manager.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    monkeypatch.setattr(review_evidence, "INTEGRATION_LOGS", integration_logs)

    evidence = context_manager_evidence()
    assert evidence["status"] == "PASS"
    require_wo010_progressive_disclosure_evidence(
        "WO-010",
        {"context_manager": evidence},
        "0005_semantic_retrieval",
    )

    missing = dict(payload)
    del missing["smallest_sufficient"]
    (integration_logs / "context-manager.json").write_text(
        json.dumps(missing),
        encoding="utf-8",
    )
    missing_evidence = context_manager_evidence()
    with pytest.raises(ValueError, match="Progressive Disclosure evidence"):
        require_wo010_progressive_disclosure_evidence(
            "WO-010",
            {"context_manager": missing_evidence},
            "0005_semantic_retrieval",
        )

    false_payload = dict(payload)
    false_payload["no_unnecessary_escalation"] = False
    (integration_logs / "context-manager.json").write_text(
        json.dumps(false_payload),
        encoding="utf-8",
    )
    false_evidence = context_manager_evidence()
    assert false_evidence["no_unnecessary_escalation"] is False
    with pytest.raises(ValueError, match="Progressive Disclosure evidence"):
        require_wo010_progressive_disclosure_evidence(
            "WO-010",
            {"context_manager": false_evidence},
            "0005_semantic_retrieval",
        )

    llm_payload = dict(payload)
    llm_payload["disclosure_llm_calls"] = 1
    (integration_logs / "context-manager.json").write_text(
        json.dumps(llm_payload),
        encoding="utf-8",
    )
    llm_evidence = context_manager_evidence()
    assert llm_evidence["disclosure_llm_calls"] == 1
    with pytest.raises(ValueError, match="zero disclosure LLM calls"):
        require_wo010_progressive_disclosure_evidence(
            "WO-010",
            {"context_manager": llm_evidence},
            "0005_semantic_retrieval",
        )

    adaptive_payload = dict(payload)
    adaptive_payload["adaptive_token_budget_implemented"] = True
    (integration_logs / "context-manager.json").write_text(
        json.dumps(adaptive_payload),
        encoding="utf-8",
    )
    adaptive_evidence = context_manager_evidence()
    assert adaptive_evidence["adaptive_token_budget_implemented"] is True
    with pytest.raises(ValueError, match="adaptive_token_budget_implemented"):
        require_wo010_progressive_disclosure_evidence(
            "WO-010",
            {"context_manager": adaptive_evidence},
            "0005_semantic_retrieval",
        )

    with pytest.raises(ValueError, match="migration head"):
        require_wo010_progressive_disclosure_evidence(
            "WO-010",
            {"context_manager": evidence},
            "0006_adaptive_token_budget",
        )


def test_wo011_adaptive_token_budget_review_evidence_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    integration_logs = tmp_path / "integration-logs"
    integration_logs.mkdir()
    payload = {
        "status": "PASS",
        **{field: True for field in CONTEXT_MANAGER_REQUIRED_FIELDS},
        "mandatory_governance_kind_sequence": [
            "CHECKPOINT",
            "SCOPE",
            "DEFINITION_OF_DONE",
            "ARCHITECTURE",
            "DECISIONS",
        ],
        "llm_calls": 0,
        "disclosure_llm_calls": 0,
        **{field: True for field in review_evidence.PROGRESSIVE_DISCLOSURE_REQUIRED_FIELDS},
        **{field: True for field in review_evidence.PROGRESSIVE_DISCLOSURE_C1_FIELDS},
        **{field: True for field in review_evidence.PROGRESSIVE_DISCLOSURE_C2_FIELDS},
        **{field: True for field in review_evidence.TOKEN_BUDGET_REQUIRED_FIELDS},
        "token_budget_user_mode_required": False,
        "adaptive_token_budget_migration_changed": False,
        "token_budget_llm_calls": 0,
        "token_budget_provider_calls": 0,
        "token_budget_benchmark_status": "PASS",
        "token_budget_benchmark_critical_context_misses": 0,
        "token_budget_benchmark_strict_reduction_fixture": True,
    }
    (integration_logs / "context-manager.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    monkeypatch.setattr(review_evidence, "INTEGRATION_LOGS", integration_logs)

    evidence = context_manager_evidence()
    require_wo011_context_manager_evidence(
        "WO-011",
        {"context_manager": evidence},
        "0005_semantic_retrieval",
    )
    assert evidence["token_budget_benchmark_status"] == "PASS"

    missing = dict(payload)
    missing["retained_rerank_order_preserved"] = False
    (integration_logs / "context-manager.json").write_text(
        json.dumps(missing),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="adaptive token-budget evidence"):
        require_wo011_context_manager_evidence(
            "WO-011",
            {"context_manager": context_manager_evidence()},
            "0005_semantic_retrieval",
        )

    review_evidence.require_wo011_scope(
        "WO-011",
        review_evidence.WO011_BASE_SHA,
        ["backend/app/adaptive_token_budget.py"],
    )
    with pytest.raises(ValueError, match="canonical Project Brain"):
        review_evidence.require_wo011_scope(
            "WO-011",
            review_evidence.WO011_BASE_SHA,
            ["docs/project-brain/13-CHECKPOINT.md"],
        )


def test_wo012_context_fingerprint_review_evidence_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    integration_logs = tmp_path / "integration-logs"
    integration_logs.mkdir()
    payload = {
        "status": "PASS",
        **{field: True for field in CONTEXT_MANAGER_REQUIRED_FIELDS},
        "mandatory_governance_kind_sequence": [
            "CHECKPOINT",
            "SCOPE",
            "DEFINITION_OF_DONE",
            "ARCHITECTURE",
            "DECISIONS",
        ],
        "llm_calls": 0,
        **{field: True for field in review_evidence.WO012_CONTEXT_FINGERPRINT_REQUIRED_FIELDS},
        **{field: 0 for field in review_evidence.WO012_CONTEXT_FINGERPRINT_INTEGER_FIELDS},
        "context_fingerprint_benchmark_status": "PASS",
        "context_fingerprint_migration_changed": False,
        "delta_context_implemented": False,
        "provider_prompt_cache_implemented": False,
        "memory_lifecycle_implemented": False,
    }
    (integration_logs / "context-manager.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    monkeypatch.setattr(review_evidence, "INTEGRATION_LOGS", integration_logs)

    evidence = context_manager_evidence()
    require_wo012_context_manager_evidence(
        "WO-012",
        {"context_manager": evidence},
        "0005_semantic_retrieval",
    )
    assert evidence["context_fingerprint_benchmark_status"] == "PASS"

    missing = dict(payload)
    missing["context_fingerprint_valid_hit_avoids_rebuild"] = False
    (integration_logs / "context-manager.json").write_text(
        json.dumps(missing),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="context-fingerprint evidence"):
        require_wo012_context_manager_evidence(
            "WO-012",
            {"context_manager": context_manager_evidence()},
            "0005_semantic_retrieval",
        )

    disconnected = dict(payload)
    disconnected["context_fingerprint_input_material_inputs_bound"] = False
    (integration_logs / "context-manager.json").write_text(
        json.dumps(disconnected),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="context-fingerprint evidence"):
        require_wo012_context_manager_evidence(
            "WO-012",
            {"context_manager": context_manager_evidence()},
            "0005_semantic_retrieval",
        )

    review_evidence.require_wo012_scope(
        "WO-012",
        review_evidence.WO012_BASE_SHA,
        ["backend/app/context_fingerprints.py"],
    )
    with pytest.raises(ValueError, match="canonical Project Brain"):
        review_evidence.require_wo012_scope(
            "WO-012",
            review_evidence.WO012_BASE_SHA,
            ["docs/project-brain/13-CHECKPOINT.md"],
        )


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
        "Context Manager evidence",
        "Progressive Disclosure evidence",
        "Ruleset unchanged",
        "Auto-merge owner: KayzenRoot (User)",
        "Sol Review State: AWAITING_SOL",
    ):
        assert field in summary


def test_wo013_scope_and_delta_evidence_fail_closed() -> None:
    require_wo013_scope("WO-013", WO013_BASE_SHA, sorted(WO013_ALLOWED_PATHS))
    with pytest.raises(ValueError, match="exact base"):
        require_wo013_scope("WO-013", "a" * 40, sorted(WO013_ALLOWED_PATHS))
    with pytest.raises(ValueError, match="canonical Project Brain or migrations"):
        require_wo013_scope("WO-013", WO013_BASE_SHA, ["docs/project-brain/13-CHECKPOINT.md"])
    with pytest.raises(ValueError, match="outside"):
        require_wo013_scope("WO-013", WO013_BASE_SHA, ["backend/app/unrelated.py"])


def test_wo014_scope_requires_exact_base_and_allows_only_foundation_files() -> None:
    require_wo014_scope("WO-014", WO014_BASE_SHA, sorted(WO014_ALLOWED_PATHS))
    with pytest.raises(ValueError, match="exact base"):
        require_wo014_scope("WO-014", "a" * 40, sorted(WO014_ALLOWED_PATHS))
    with pytest.raises(ValueError, match="Project Brain"):
        require_wo014_scope("WO-014", WO014_BASE_SHA, ["docs/project-brain/13-CHECKPOINT.md"])
    with pytest.raises(ValueError, match="outside the approved Provider/Prompt Cache scope"):
        require_wo014_scope("WO-014", WO014_BASE_SHA, ["backend/app/unrelated.py"])

    evidence = {
        "status": "PASS",
        **{field: True for field in review_evidence.CONTEXT_MANAGER_REQUIRED_FIELDS},
        "mandatory_governance_kind_sequence": [
            "CHECKPOINT",
            "SCOPE",
            "DEFINITION_OF_DONE",
            "ARCHITECTURE",
            "DECISIONS",
        ],
        "llm_calls": 0,
        **{field: True for field in review_evidence.WO013_DELTA_REQUIRED_FIELDS},
        **{field: 0 for field in review_evidence.WO013_DELTA_INTEGER_FIELDS},
        **{field: False for field in review_evidence.WO013_DELTA_NEGATIVE_FIELDS},
        "delta_context_benchmark_status": "PASS",
        "delta_context_delivery_estimate_version": "delta-delivery-estimate-v1",
        "delta_context_small_change_delta_estimated_tokens": 10,
        "delta_context_small_change_final_delta_estimated_tokens": 10,
        "delta_context_small_change_full_estimated_tokens": 20,
        "delta_context_small_change_fresh_context_tokens_avoided": 10,
        "delta_context_full_savings_zero": True,
        "delta_context_threshold_old_metadata_estimated_tokens": 1,
        "delta_context_threshold_final_delta_estimated_tokens": 3,
        "delta_context_threshold_full_estimated_tokens": 2,
        "delta_context_threshold_old_gate_would_emit_delta": True,
        "delta_context_threshold_final_gate_rejected_delta": True,
    }
    require_wo013_context_manager_evidence(
        "WO-013",
        {"context_manager": evidence},
        "0005_semantic_retrieval",
    )
    missing = dict(evidence)
    missing["delta_context_new_dependency_preserved"] = False
    with pytest.raises(ValueError, match="Delta Context evidence"):
        require_wo013_context_manager_evidence(
            "WO-013",
            {"context_manager": missing},
            "0005_semantic_retrieval",
        )


def test_wo014_c1_candidate_lineage_is_explicit_and_squash_safe() -> None:
    assert review_evidence.WO014_REJECTED_HEAD == ("184821d3cb5743d06c856f29895ceaa58c76ee0d")
    assert WO014_C1_CORRECTED_HEAD == "dfb6bcb21e6646bc2c056c014ba211245bd64e77"
    evidence = verify_wo014_c2_governance_contract()
    assert "explicit_c1_lineage=PASS" in evidence
    assert "replacement_skipping_c1=REJECTED" in evidence


def test_wo014_c2_scope_is_explicit_and_fail_closed() -> None:
    require_wo014_c2_scope(
        WO014_C2_WORK_ORDER,
        WO014_C2_BASE_SHA,
        sorted(WO014_C2_ALLOWED_PATHS),
    )
    with pytest.raises(ValueError, match="post-squash base"):
        require_wo014_c2_scope(WO014_C2_WORK_ORDER, "a" * 40, sorted(WO014_C2_ALLOWED_PATHS))
    with pytest.raises(ValueError, match="Project Brain"):
        require_wo014_c2_scope(
            WO014_C2_WORK_ORDER,
            WO014_C2_BASE_SHA,
            ["docs/project-brain/13-CHECKPOINT.md"],
        )
    with pytest.raises(ValueError, match="Project Brain"):
        require_wo014_c2_scope(
            WO014_C2_WORK_ORDER,
            WO014_C2_BASE_SHA,
            ["migrations/0006_unrelated.sql"],
        )
    with pytest.raises(ValueError, match="explicit governance/test scope"):
        require_wo014_c2_scope(
            WO014_C2_WORK_ORDER,
            WO014_C2_BASE_SHA,
            ["backend/app/provider_prompt_cache.py"],
        )
    with pytest.raises(ValueError, match="explicit governance/test scope"):
        require_wo014_c2_scope(
            WO014_C2_WORK_ORDER,
            WO014_C2_BASE_SHA,
            ["backend/app/unrelated.py"],
        )


def test_wo014_c2_governance_contract_proves_post_squash_semantics() -> None:
    evidence = verify_wo014_c2_governance_contract()
    assert "post_squash_scope=PASS" in evidence
    assert "explicit_c1_lineage=PASS" in evidence
    assert "replacement_skipping_c1=REJECTED" in evidence
    assert "squash_without_source_ancestry=PASS" in evidence


def test_wo014_c1_evidence_requires_computed_provider_cache_fixtures() -> None:
    evidence = {
        "status": "PASS",
        **{field: True for field in review_evidence.WO014_PROVIDER_CACHE_REQUIRED_FIELDS},
        **{field: 0 for field in review_evidence.WO014_PROVIDER_CACHE_INTEGER_FIELDS},
        **{field: "" for field in review_evidence.WO014_PROVIDER_CACHE_STRING_FIELDS},
        **{field: [] for field in review_evidence.WO014_PROVIDER_CACHE_LIST_FIELDS},
        **{field: False for field in review_evidence.WO014_PROVIDER_CACHE_NEGATIVE_FIELDS},
        "provider_cache_semantic_composition_fixture_count": 5,
        "provider_cache_semantic_composition_mismatch_detection_count": 5,
        "provider_cache_accepted_semantic_composition_mismatches": 0,
        "provider_cache_invalid_accounting_matrix_size": 8,
        "provider_cache_invalid_accounting_acceptances": 0,
        "provider_cache_provider_usage_sources": ["UNKNOWN"],
        "provider_cache_independent_canonical_input_version": "provider-canonical-input-v1",
        "provider_cache_benchmark_status": "PASS",
    }
    require_wo014_provider_prompt_cache_evidence(
        "WO-014",
        {"context_manager": evidence},
        "0005_semantic_retrieval",
    )
    require_wo014_provider_prompt_cache_evidence(
        WO014_C2_WORK_ORDER,
        {"context_manager": evidence},
        "0005_semantic_retrieval",
    )
    require_wo014_provider_prompt_cache_evidence(
        WO014P_G1_WORK_ORDER,
        {"context_manager": evidence},
        "0005_semantic_retrieval",
    )
    require_wo014_provider_prompt_cache_evidence(
        WO014P_WORK_ORDER,
        {"context_manager": evidence},
        "0005_semantic_retrieval",
    )

    mutated = dict(evidence)
    mutated["provider_cache_accepted_semantic_composition_mismatches"] = 1
    with pytest.raises(ValueError, match="computed semantic mutation"):
        require_wo014_provider_prompt_cache_evidence(
            "WO-014",
            {"context_manager": mutated},
            "0005_semantic_retrieval",
        )

    invalid_accounting = dict(evidence)
    invalid_accounting["provider_cache_invalid_accounting_acceptances"] = 1
    with pytest.raises(ValueError, match="zero accepted invalid accounting"):
        require_wo014_provider_prompt_cache_evidence(
            "WO-014",
            {"context_manager": invalid_accounting},
            "0005_semantic_retrieval",
        )


@pytest.mark.parametrize("work_order", ["WO-008", "WO-008-G1"])
def test_wo008_c1_evidence_fails_closed_on_missing_safety_proof(work_order: str) -> None:
    required = {field: True for field in review_evidence.RERANK_C1_REQUIRED_FIELDS}
    benchmark = {"status": "PASS", "rerank": {"status": "PASS", **required}}
    integration = {"integrity_tests": required}
    security = {"reranking": {"status": "PASS"}}

    require_wo008_c1_evidence(
        work_order, benchmark, integration, security, "bounded evidence", "review text"
    )

    failed_benchmark = {
        "status": "PASS",
        "rerank": {"status": "PASS", **required, "rerank_ordering_reproducible": False},
    }
    with pytest.raises(ValueError, match="mandatory rerank C1 evidence"):
        require_wo008_c1_evidence(
            work_order,
            failed_benchmark,
            integration,
            security,
            "bounded evidence",
            "review text",
        )


def test_generic_bundle_zip_is_byte_deterministic(tmp_path: Path) -> None:
    files = {"z.txt": "last\n", "a.txt": "first\n"}
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    assert deterministic_zip(first, files) == deterministic_zip(second, files)
    assert first.read_bytes() == second.read_bytes()
