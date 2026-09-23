from __future__ import annotations

import hashlib
import json
import re
import sys
from collections.abc import Callable
from itertools import permutations
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import jsonschema
import pytest
import scripts.review_evidence as review_evidence
from scripts.capture_service_logs import DEFAULT_COMMAND, capture_service_logs, redact_service_logs
from scripts.review_bundle import deterministic_zip
from scripts.review_evidence import (
    ACCE_STORAGE_POLICY_EVIDENCE_FILE,
    ACCE_STORAGE_POLICY_EVIDENCE_VERSION,
    ACCE_STORAGE_POLICY_REQUIRED_FIELDS,
    CONTEXT_MANAGER_REQUIRED_FIELDS,
    HIVE_REL_001_ALLOWED_EXACT_PATHS,
    HIVE_REL_001_BASE_SHA,
    HIVE_REL_001_WORK_ORDER,
    HIVE_REL_002_ALLOWED_PATHS,
    HIVE_REL_002_BASE_SHA,
    HIVE_REL_002_WORK_ORDER,
    HIVE_REL_003_ALLOWED_PATHS,
    HIVE_REL_003_BASE_SHA,
    HIVE_REL_003_WORK_ORDER,
    HIVE_REL_004_ALLOWED_PATHS,
    HIVE_REL_004_BASE_SHA,
    HIVE_REL_004_WORK_ORDER,
    HIVE_REL_005_ALLOWED_PATHS,
    HIVE_REL_005_BASE_SHA,
    HIVE_REL_005_WORK_ORDER,
    HIVE_REL_006_ALLOWED_PATHS,
    HIVE_REL_006_BASE_SHA,
    HIVE_REL_006_WORK_ORDER,
    HIVE_REL_007_ALLOWED_PATHS,
    HIVE_REL_007_BASE_SHA,
    HIVE_REL_007_WORK_ORDER,
    HIVE_REL_008_ALLOWED_PATHS,
    HIVE_REL_008_BASE_SHA,
    HIVE_REL_008_WORK_ORDER,
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
    require_hive_rel_001_scope,
    require_hive_rel_002_scope,
    require_hive_rel_003_scope,
    require_hive_rel_004_scope,
    require_hive_rel_005_scope,
    require_hive_rel_006_scope,
    require_hive_rel_007_scope,
    require_hive_rel_008_scope,
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
from scripts.review_pr_body import AUTHORIZED_BASE_BY_WORK_ORDER, render_body


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


def autonomous_execution_evidence_fixture() -> dict[str, object]:
    return {
        "status": "PASS",
        "evidence_file": review_evidence.AUTONOMOUS_EXECUTION_EVIDENCE_FILE,
        "autonomous_evidence_version": review_evidence.AUTONOMOUS_EXECUTION_EVIDENCE_VERSION,
        "executor_adapter_name": "deterministic-fixture-v1",
        "observed_migration_head": "0006_memory_lifecycle_provenance",
        **{field: True for field in review_evidence.AUTONOMOUS_EXECUTION_TRUE_FIELDS},
        **{field: False for field in review_evidence.AUTONOMOUS_EXECUTION_FALSE_FIELDS},
        "tool_subset_count": 2,
        "validation_commands_count": 1,
        "executor_llm_calls": 0,
        "executor_provider_calls": 0,
        "secret_leaks": 0,
        "filesystem_path_leaks": 0,
    }


def telemetry_event_bus_evidence_fixture(
    *, observed_migration_head: str = "0006_memory_lifecycle_provenance"
) -> dict[str, object]:
    return {
        "status": "PASS",
        "evidence_file": review_evidence.TELEMETRY_EVENT_BUS_EVIDENCE_FILE,
        "telemetry_evidence_version": review_evidence.TELEMETRY_EVENT_BUS_EVIDENCE_VERSION,
        "observed_migration_head": observed_migration_head,
        "migration_base_head": "0006_memory_lifecycle_provenance",
        "producer_path": "backend/app/telemetry.py",
        "migration_changed": observed_migration_head != "0006_memory_lifecycle_provenance",
        **{field: True for field in review_evidence.TELEMETRY_EVENT_BUS_TRUE_FIELDS},
        **{field: False for field in review_evidence.TELEMETRY_EVENT_BUS_FALSE_FIELDS},
        "event_type_count": 2,
        "payload_max_bytes": 65536,
        "cursor_max_bytes": 4096,
        "duplicate_canonical_events": 0,
        "cross_project_leaks": 0,
        "secret_leaks": 0,
        "filesystem_path_leaks": 0,
        "llm_calls": 0,
        "provider_calls": 0,
        "implemented_event_types": ["executor.started", "run.completed"],
    }


def control_center_core_evidence_fixture(
    *, observed_migration_head: str = "0007_telemetry_events"
) -> dict[str, object]:
    surfaces = ["fleet", "event-stream", "platform-health"]
    return {
        "status": "PASS",
        "evidence_file": review_evidence.CONTROL_CENTER_CORE_EVIDENCE_FILE,
        "control_center_evidence_version": review_evidence.CONTROL_CENTER_CORE_EVIDENCE_VERSION,
        "observed_migration_head": observed_migration_head,
        "migration_base_head": review_evidence.CONTROL_CENTER_CORE_MIGRATION_BASE_HEAD,
        "migration_changed": observed_migration_head
        != review_evidence.CONTROL_CENTER_CORE_MIGRATION_BASE_HEAD,
        "stream_transport": "sse",
        "api_path": "backend/app/control_center.py",
        "dashboard_path": "dashboard/src/control-center",
        **{field: True for field in review_evidence.CONTROL_CENTER_CORE_TRUE_FIELDS},
        **{field: False for field in review_evidence.CONTROL_CENTER_CORE_FALSE_FIELDS},
        "surface_count": len(surfaces),
        "secret_leaks": 0,
        "filesystem_path_leaks": 0,
        "cross_project_leaks": 0,
        "llm_calls": 0,
        "provider_calls": 0,
        "implemented_surfaces": surfaces,
    }


def control_center_metrics_evidence_fixture() -> dict[str, object]:
    return {
        "status": "PASS",
        "evidence_file": review_evidence.CONTROL_CENTER_METRICS_EVIDENCE_FILE,
        "metrics_evidence_version": review_evidence.CONTROL_CENTER_METRICS_EVIDENCE_VERSION,
        "observed_migration_head": review_evidence.CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD,
        "migration_base_head": review_evidence.CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD,
        "cost_provenance": "UNAVAILABLE",
        "migration_changed": False,
        **{field: True for field in review_evidence.CONTROL_CENTER_METRICS_TRUE_FIELDS},
        **{field: False for field in review_evidence.CONTROL_CENTER_METRICS_FALSE_FIELDS},
        "historical_series_max_points": 128,
        "secret_leaks": 0,
        "filesystem_path_leaks": 0,
        "cross_project_leaks": 0,
        "metrics_llm_calls": 0,
        "metrics_provider_calls": 0,
        "implemented_metric_families": list(review_evidence.CONTROL_CENTER_METRICS_FAMILIES),
        "metric_value_provenance": list(review_evidence.CONTROL_CENTER_METRICS_VALUE_PROVENANCE),
        "evidence_paths": [
            "backend/app/control_center_metrics.py",
            "dashboard/src/control-center/metrics.tsx",
        ],
    }


def control_center_full_evidence_fixture() -> dict[str, object]:
    return {
        "status": "PASS",
        "full_control_center_evidence_version": (
            review_evidence.CONTROL_CENTER_FULL_EVIDENCE_VERSION
        ),
        "evidence_file": review_evidence.CONTROL_CENTER_FULL_EVIDENCE_FILE,
        "observed_migration_head": review_evidence.CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD,
        "migration_base_head": review_evidence.CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD,
        "api_path": "backend/app/control_center.py",
        "dashboard_path": "dashboard/src/ControlCenter.tsx",
        "migration_changed": False,
        **{field: True for field in review_evidence.CONTROL_CENTER_FULL_TRUE_FIELDS},
        **{field: False for field in review_evidence.CONTROL_CENTER_FULL_FALSE_FIELDS},
        "history_max_points": 256,
        "secret_leaks": 0,
        "filesystem_path_leaks": 0,
        "cross_project_leaks": 0,
        "llm_calls": 0,
        "provider_calls": 0,
        "implemented_project_capabilities": list(
            review_evidence.CONTROL_CENTER_FULL_PROJECT_CAPABILITIES
        ),
        "implemented_charts": list(review_evidence.CONTROL_CENTER_FULL_CHARTS),
        "implemented_alerts": list(review_evidence.CONTROL_CENTER_FULL_ALERTS),
        "implemented_health_capabilities": list(
            review_evidence.CONTROL_CENTER_FULL_HEALTH_CAPABILITIES
        ),
        "evidence_paths": [
            "backend/app/control_center.py",
            "backend/tests/test_control_center.py",
            "dashboard/src/ControlCenter.tsx",
            "scripts/control_center_integration.py",
            "docs/atlas/code-atlas.md",
        ],
    }


def test_review_evidence_schema_is_validated() -> None:
    manifest = evidence_fixture()
    validate_manifest(manifest)
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["properties"]["schema_version"]["const"] == 1


def test_wo026_registration_is_exact_and_fail_closed() -> None:
    require_supported_work_order(review_evidence.WO026_WORK_ORDER)
    with pytest.raises(ValueError, match="unsupported future work order"):
        require_supported_work_order("WO-032")

    base_sha = review_evidence.WO026_BASE_SHA
    allowed = sorted(review_evidence.WO026_ALLOWED_PATHS)
    review_evidence.require_wo026_scope(
        review_evidence.WO026_WORK_ORDER,
        base_sha,
        allowed,
        authorized_base_sha=base_sha,
    )

    body = (
        f"<!-- HIVE-WORK-ORDER: {review_evidence.WO026_WORK_ORDER} -->\n"
        f"<!-- HIVE-AUTHORIZED-BASE: {base_sha} -->\n"
    )
    assert (
        review_evidence.authorized_base_marker_sha(review_evidence.WO026_WORK_ORDER, body)
        == base_sha
    )

    with pytest.raises(ValueError, match="exact base"):
        review_evidence.require_wo026_scope(
            review_evidence.WO026_WORK_ORDER,
            "f" * 40,
            allowed,
            authorized_base_sha=base_sha,
        )
    with pytest.raises(ValueError, match="protected main base branch"):
        review_evidence.require_wo026_scope(
            review_evidence.WO026_WORK_ORDER,
            base_sha,
            allowed,
            base_branch="release",
            authorized_base_sha=base_sha,
        )
    with pytest.raises(ValueError, match="bounded Apache-2.0 readiness surface"):
        review_evidence.require_wo026_scope(
            review_evidence.WO026_WORK_ORDER,
            base_sha,
            [*allowed, "backend/app/main.py"],
            authorized_base_sha=base_sha,
        )
    with pytest.raises(ValueError, match="exactly one authorized-base marker"):
        review_evidence.require_wo026_scope(
            review_evidence.WO026_WORK_ORDER,
            base_sha,
            allowed,
        )


def test_wo027_registration_is_exact_and_fail_closed() -> None:
    require_supported_work_order(review_evidence.WO027_WORK_ORDER)
    with pytest.raises(ValueError, match="unsupported future work order"):
        require_supported_work_order("WO-032")

    base_sha = review_evidence.WO027_BASE_SHA
    allowed = sorted(review_evidence.WO027_ALLOWED_PATHS)
    review_evidence.require_wo027_scope(
        review_evidence.WO027_WORK_ORDER,
        base_sha,
        allowed,
        authorized_base_sha=base_sha,
    )
    body = (
        f"<!-- HIVE-WORK-ORDER: {review_evidence.WO027_WORK_ORDER} -->\n"
        f"<!-- HIVE-AUTHORIZED-BASE: {base_sha} -->\n"
    )
    assert (
        review_evidence.authorized_base_marker_sha(review_evidence.WO027_WORK_ORDER, body)
        == base_sha
    )
    with pytest.raises(ValueError, match="exact base"):
        review_evidence.require_wo027_scope(
            review_evidence.WO027_WORK_ORDER,
            "f" * 40,
            allowed,
            authorized_base_sha=base_sha,
        )
    with pytest.raises(ValueError, match="bounded application-readiness surface"):
        review_evidence.require_wo027_scope(
            review_evidence.WO027_WORK_ORDER,
            base_sha,
            [*allowed, "backend/app/main.py"],
            authorized_base_sha=base_sha,
        )


def test_wo028_project_root_hotfix_is_exact_and_fail_closed() -> None:
    require_supported_work_order(review_evidence.WO028_WORK_ORDER)
    with pytest.raises(ValueError, match="unsupported future work order"):
        require_supported_work_order("WO-032")

    base_sha = review_evidence.WO028_BASE_SHA
    allowed = sorted(review_evidence.WO028_ALLOWED_PATHS)
    review_evidence.require_wo028_scope(
        review_evidence.WO028_WORK_ORDER,
        base_sha,
        allowed,
        authorized_base_sha=base_sha,
    )
    body = (
        f"<!-- HIVE-WORK-ORDER: {review_evidence.WO028_WORK_ORDER} -->\n"
        f"<!-- HIVE-AUTHORIZED-BASE: {base_sha} -->\n"
    )
    assert (
        review_evidence.authorized_base_marker_sha(review_evidence.WO028_WORK_ORDER, body)
        == base_sha
    )
    with pytest.raises(ValueError, match="exact base"):
        review_evidence.require_wo028_scope(
            review_evidence.WO028_WORK_ORDER,
            "f" * 40,
            allowed,
            authorized_base_sha=base_sha,
        )
    with pytest.raises(ValueError, match="bounded project-root hotfix surface"):
        review_evidence.require_wo028_scope(
            review_evidence.WO028_WORK_ORDER,
            base_sha,
            [*allowed, "backend/app/main.py"],
            authorized_base_sha=base_sha,
        )
    with pytest.raises(ValueError, match="protected main base branch"):
        review_evidence.require_wo028_scope(
            review_evidence.WO028_WORK_ORDER,
            base_sha,
            allowed,
            base_branch="release",
            authorized_base_sha=base_sha,
        )


def test_wo029_executor_correction_is_exact_and_fail_closed() -> None:
    require_supported_work_order(review_evidence.WO029_WORK_ORDER)
    with pytest.raises(ValueError, match="unsupported future work order"):
        require_supported_work_order("WO-032")

    base_sha = review_evidence.WO029_BASE_SHA
    allowed = sorted(review_evidence.WO029_ALLOWED_PATHS)
    review_evidence.require_wo029_scope(
        review_evidence.WO029_WORK_ORDER,
        base_sha,
        allowed,
        authorized_base_sha=base_sha,
    )
    body = (
        f"<!-- HIVE-WORK-ORDER: {review_evidence.WO029_WORK_ORDER} -->\n"
        f"<!-- HIVE-AUTHORIZED-BASE: {base_sha} -->\n"
    )
    assert (
        review_evidence.authorized_base_marker_sha(review_evidence.WO029_WORK_ORDER, body)
        == base_sha
    )
    with pytest.raises(ValueError, match="exact base"):
        review_evidence.require_wo029_scope(
            review_evidence.WO029_WORK_ORDER,
            "f" * 40,
            allowed,
            authorized_base_sha=base_sha,
        )
    with pytest.raises(ValueError, match="bounded executor/token corrective surface"):
        review_evidence.require_wo029_scope(
            review_evidence.WO029_WORK_ORDER,
            base_sha,
            [*allowed, "backend/app/main.py"],
            authorized_base_sha=base_sha,
        )
    with pytest.raises(ValueError, match="protected main base branch"):
        review_evidence.require_wo029_scope(
            review_evidence.WO029_WORK_ORDER,
            base_sha,
            allowed,
            base_branch="release",
            authorized_base_sha=base_sha,
        )


def test_wo029_c1_executor_test_gate_is_exact_and_fail_closed() -> None:
    require_supported_work_order(review_evidence.WO029_C1_WORK_ORDER)
    require_current_work_order_authorization(review_evidence.WO029_C1_WORK_ORDER)
    assert review_evidence.WO029_C1_WORK_ORDER in review_evidence.CORRECTIVE_GOVERNANCE_WORK_ORDERS
    assert review_evidence.WO029_C1_WORK_ORDER not in (
        review_evidence.CHECKPOINT_PROMOTION_WORK_ORDERS
    )

    base_sha = review_evidence.WO029_C1_BASE_SHA
    allowed = sorted(review_evidence.WO029_C1_ALLOWED_PATHS)
    review_evidence.require_wo029_c1_scope(
        review_evidence.WO029_C1_WORK_ORDER,
        base_sha,
        allowed,
        authorized_base_sha=base_sha,
    )
    body = (
        f"<!-- HIVE-WORK-ORDER: {review_evidence.WO029_C1_WORK_ORDER} -->\n"
        f"<!-- HIVE-AUTHORIZED-BASE: {base_sha} -->\n"
    )
    assert (
        review_evidence.authorized_base_marker_sha(review_evidence.WO029_C1_WORK_ORDER, body)
        == base_sha
    )
    with pytest.raises(ValueError, match="exact base"):
        review_evidence.require_wo029_c1_scope(
            review_evidence.WO029_C1_WORK_ORDER,
            "f" * 40,
            allowed,
            authorized_base_sha="f" * 40,
        )
    with pytest.raises(ValueError, match="bounded executor test-gate correction surface"):
        review_evidence.require_wo029_c1_scope(
            review_evidence.WO029_C1_WORK_ORDER,
            base_sha,
            [*allowed, "backend/app/main.py"],
            authorized_base_sha=base_sha,
        )
    with pytest.raises(ValueError, match="protected main base branch"):
        review_evidence.require_wo029_c1_scope(
            review_evidence.WO029_C1_WORK_ORDER,
            base_sha,
            allowed,
            base_branch="release",
            authorized_base_sha=base_sha,
        )
    with pytest.raises(ValueError, match="exactly one authorized-base marker"):
        review_evidence.require_wo029_c1_scope(
            review_evidence.WO029_C1_WORK_ORDER,
            base_sha,
            allowed,
        )


def test_wo029_c2_domain_classification_is_exact_and_fail_closed() -> None:
    require_supported_work_order(review_evidence.WO029_C2_WORK_ORDER)
    require_current_work_order_authorization(review_evidence.WO029_C2_WORK_ORDER)
    assert review_evidence.WO029_C2_WORK_ORDER in review_evidence.CORRECTIVE_GOVERNANCE_WORK_ORDERS
    assert review_evidence.WO029_C2_WORK_ORDER not in (
        review_evidence.CHECKPOINT_PROMOTION_WORK_ORDERS
    )

    base_sha = review_evidence.WO029_C2_BASE_SHA
    allowed = sorted(review_evidence.WO029_C2_ALLOWED_PATHS)
    review_evidence.require_wo029_c2_scope(
        review_evidence.WO029_C2_WORK_ORDER,
        base_sha,
        allowed,
        authorized_base_sha=base_sha,
    )
    with pytest.raises(ValueError, match="exact base"):
        review_evidence.require_wo029_c2_scope(
            review_evidence.WO029_C2_WORK_ORDER,
            "f" * 40,
            allowed,
            authorized_base_sha="f" * 40,
        )
    with pytest.raises(ValueError, match="bounded domain-classification surface"):
        review_evidence.require_wo029_c2_scope(
            review_evidence.WO029_C2_WORK_ORDER,
            base_sha,
            [*allowed, "backend/app/main.py"],
            authorized_base_sha=base_sha,
        )
    with pytest.raises(ValueError, match="protected main base branch"):
        review_evidence.require_wo029_c2_scope(
            review_evidence.WO029_C2_WORK_ORDER,
            base_sha,
            allowed,
            base_branch="release",
            authorized_base_sha=base_sha,
        )


def test_wo029_c3_production_executor_correction_is_exact_and_fail_closed() -> None:
    require_supported_work_order(review_evidence.WO029_C3_WORK_ORDER)
    require_current_work_order_authorization(review_evidence.WO029_C3_WORK_ORDER)
    assert review_evidence.WO029_C3_WORK_ORDER in review_evidence.CORRECTIVE_GOVERNANCE_WORK_ORDERS
    assert review_evidence.WO029_C3_WORK_ORDER not in (
        review_evidence.CHECKPOINT_PROMOTION_WORK_ORDERS
    )
    base_sha = review_evidence.WO029_C3_BASE_SHA
    allowed = sorted(review_evidence.WO029_C3_ALLOWED_PATHS)
    review_evidence.require_wo029_c3_scope(
        review_evidence.WO029_C3_WORK_ORDER, base_sha, allowed, authorized_base_sha=base_sha
    )
    with pytest.raises(ValueError, match="exact base"):
        review_evidence.require_wo029_c3_scope(
            review_evidence.WO029_C3_WORK_ORDER,
            "f" * 40,
            allowed,
            authorized_base_sha="f" * 40,
        )
    with pytest.raises(ValueError, match="bounded production-executor correction surface"):
        review_evidence.require_wo029_c3_scope(
            review_evidence.WO029_C3_WORK_ORDER,
            base_sha,
            [*allowed, "backend/app/main.py"],
            authorized_base_sha=base_sha,
        )
    with pytest.raises(ValueError, match="protected main base branch"):
        review_evidence.require_wo029_c3_scope(
            review_evidence.WO029_C3_WORK_ORDER,
            base_sha,
            allowed,
            base_branch="release",
            authorized_base_sha=base_sha,
        )


def test_wo030_vitest_security_correction_is_exact_and_fail_closed() -> None:
    require_supported_work_order(review_evidence.WO030_WORK_ORDER)
    with pytest.raises(ValueError, match="unsupported future work order"):
        require_supported_work_order("WO-032")

    base_sha = review_evidence.WO030_BASE_SHA
    allowed = sorted(review_evidence.WO030_ALLOWED_PATHS)
    review_evidence.require_wo030_scope(
        review_evidence.WO030_WORK_ORDER,
        base_sha,
        allowed,
        authorized_base_sha=base_sha,
    )
    body = (
        f"<!-- HIVE-WORK-ORDER: {review_evidence.WO030_WORK_ORDER} -->\n"
        f"<!-- HIVE-AUTHORIZED-BASE: {base_sha} -->\n"
    )
    assert (
        review_evidence.authorized_base_marker_sha(review_evidence.WO030_WORK_ORDER, body)
        == base_sha
    )
    with pytest.raises(ValueError, match="exact base"):
        review_evidence.require_wo030_scope(
            review_evidence.WO030_WORK_ORDER,
            "f" * 40,
            allowed,
            authorized_base_sha=base_sha,
        )
    with pytest.raises(ValueError, match="bounded Vitest security correction surface"):
        review_evidence.require_wo030_scope(
            review_evidence.WO030_WORK_ORDER,
            base_sha,
            [*allowed, "backend/app/main.py"],
            authorized_base_sha=base_sha,
        )
    with pytest.raises(ValueError, match="protected main base branch"):
        review_evidence.require_wo030_scope(
            review_evidence.WO030_WORK_ORDER,
            base_sha,
            allowed,
            base_branch="release",
            authorized_base_sha=base_sha,
        )
    with pytest.raises(ValueError, match="exactly one authorized-base marker"):
        review_evidence.require_wo030_scope(
            review_evidence.WO030_WORK_ORDER,
            base_sha,
            allowed,
        )


def test_wo030_c1_progressive_disclosure_hotfix_is_exact_and_fail_closed() -> None:
    require_supported_work_order(review_evidence.WO030_C1_WORK_ORDER)
    require_current_work_order_authorization(review_evidence.WO030_C1_WORK_ORDER)
    assert review_evidence.WO030_C1_WORK_ORDER in review_evidence.CORRECTIVE_GOVERNANCE_WORK_ORDERS
    assert review_evidence.WO030_C1_WORK_ORDER not in (
        review_evidence.CHECKPOINT_PROMOTION_WORK_ORDERS
    )
    with pytest.raises(ValueError, match="unsupported future work order"):
        require_supported_work_order("WO-032")

    base_sha = review_evidence.WO030_C1_BASE_SHA
    allowed = sorted(review_evidence.WO030_C1_ALLOWED_PATHS)
    review_evidence.require_wo030_c1_scope(
        review_evidence.WO030_C1_WORK_ORDER,
        base_sha,
        allowed,
        authorized_base_sha=base_sha,
    )
    body = (
        f"<!-- HIVE-WORK-ORDER: {review_evidence.WO030_C1_WORK_ORDER} -->\n"
        f"<!-- HIVE-AUTHORIZED-BASE: {base_sha} -->\n"
    )
    assert (
        review_evidence.authorized_base_marker_sha(review_evidence.WO030_C1_WORK_ORDER, body)
        == base_sha
    )
    with pytest.raises(ValueError, match="exact base"):
        review_evidence.require_wo030_c1_scope(
            review_evidence.WO030_C1_WORK_ORDER,
            "f" * 40,
            allowed,
            authorized_base_sha="f" * 40,
        )
    with pytest.raises(ValueError, match="bounded Progressive Disclosure correction surface"):
        review_evidence.require_wo030_c1_scope(
            review_evidence.WO030_C1_WORK_ORDER,
            base_sha,
            [*allowed, "backend/app/main.py"],
            authorized_base_sha=base_sha,
        )
    with pytest.raises(ValueError, match="protected main base branch"):
        review_evidence.require_wo030_c1_scope(
            review_evidence.WO030_C1_WORK_ORDER,
            base_sha,
            allowed,
            base_branch="release",
            authorized_base_sha=base_sha,
        )
    with pytest.raises(ValueError, match="exactly one authorized-base marker"):
        review_evidence.require_wo030_c1_scope(
            review_evidence.WO030_C1_WORK_ORDER,
            base_sha,
            allowed,
        )


def test_wo015_is_explicitly_registered_and_unknown_ids_do_not_get_memory_semantics() -> None:
    require_supported_work_order(WO015_G1_WORK_ORDER)
    require_supported_work_order(WO015_WORK_ORDER)
    require_supported_work_order(WO015P_G1_WORK_ORDER)
    require_supported_work_order(WO015P_WORK_ORDER)
    require_supported_work_order(WO016P_G1_WORK_ORDER)
    require_supported_work_order(WO016P_WORK_ORDER)
    require_supported_work_order(review_evidence.WO017P_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO017P_WORK_ORDER)
    require_supported_work_order(review_evidence.WO018P_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO018P_WORK_ORDER)
    require_supported_work_order(review_evidence.WO019P_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO019P_WORK_ORDER)
    require_supported_work_order(review_evidence.WO020P_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO020P_WORK_ORDER)
    require_supported_work_order(review_evidence.WO021P_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO021P_WORK_ORDER)
    require_supported_work_order(review_evidence.WO022P_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO022P_WORK_ORDER)
    require_supported_work_order(review_evidence.WO023P_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO023P_WORK_ORDER)
    require_supported_work_order(review_evidence.WO024_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO024_WORK_ORDER)
    require_supported_work_order(review_evidence.WO024P_WORK_ORDER)
    # WO-025-P became registered in WO-025-G3, so the unregistered-promotion negative
    # moves to the next identifier of the same class.
    require_supported_work_order("WO-025-P")
    with pytest.raises(ValueError, match="unsupported checkpoint-promotion"):
        require_supported_work_order("WO-026-P")
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
    with pytest.raises(ValueError, match="exactly the four|canonical Project Brain"):
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
    with pytest.raises(ValueError, match="exactly the four|migrations"):
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


def wo023_benchmark_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "PASS",
        "comprehensive_benchmarks_evidence_version": (
            review_evidence.COMPREHENSIVE_BENCHMARKS_EVIDENCE_VERSION
        ),
        "evidence_file": review_evidence.COMPREHENSIVE_BENCHMARKS_EVIDENCE_FILE,
        "observed_migration_head": review_evidence.COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD,
        "migration_base_head": review_evidence.COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD,
        "baseline_reference_version": "baseline-full-context-v1",
        "ground_truth_source": ("git:HEAD-blob:docs/atlas/wo022-control-center-full.md"),
        "run_digest": hashlib.sha256(b"wo023 fixture run").hexdigest(),
        "retrieval_metrics_status": "AVAILABLE",
        "token_metrics_status": "AVAILABLE",
        "storage_metrics_status": "AVAILABLE",
        "retrieval_context_measure": "final-reranked-context-bytes",
        "token_cache_status": "NOT_SUPPORTED",
        "token_output_status": "NOT_SUPPORTED",
        "provider_receipt_version": "NONE",
        "provider_receipt_artifact": "NONE",
        "provider_receipt_sha256": "NONE",
        "optional_provider_metric": "NONE",
        "benchmark_families": list(review_evidence.COMPREHENSIVE_BENCHMARKS_FAMILIES),
        "evidence_paths": ["backend/tests/test_review_evidence.py"],
        **{field: True for field in review_evidence.COMPREHENSIVE_BENCHMARKS_TRUE_FIELDS},
        **{field: False for field in review_evidence.COMPREHENSIVE_BENCHMARKS_FALSE_FIELDS},
        **{field: 0 for field in review_evidence.COMPREHENSIVE_BENCHMARKS_ZERO_FIELDS},
        "corpus_task_count": 24,
        "retrieval_recall_k": 5,
        "storage_logical_bytes": 1_000_000,
        "storage_dedup_bytes": 600_000,
        "storage_physical_bytes": 300_000,
        "token_baseline_input_tokens": 40_000,
        "token_optimized_input_tokens": 25_000,
        "optional_provider_calls": 0,
        "retrieval_context_bytes": 4096,
        "token_cached_tokens": None,
        "token_output_tokens": None,
        "provider_receipt_reconciled": False,
        "retrieval_recall_at_k": 0.95,
        "retrieval_precision": 0.8,
        "retrieval_baseline_mrr": 0.6,
        "retrieval_reranked_mrr": 0.8,
        "baseline_task_success_rate": 0.9,
        "optimized_task_success_rate": 0.9,
        "baseline_test_pass_rate": 1.0,
        "optimized_test_pass_rate": 1.0,
        "token_reduction_percentage": 37.5,
        "storage_dedup_ratio": 0.4,
        "storage_compression_ratio": 0.5,
        "storage_total_reduction_ratio": 0.7,
    }
    payload.update(overrides)
    return payload


def test_wo023_g1_scope_is_exact_and_noncanonical(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(review_evidence, "migration_head", lambda: "0007_telemetry_events")
    monkeypatch.setattr(
        review_evidence,
        "canonical_change_evidence",
        lambda _paths, _work_order: {"project_brain_changed": False, "checkpoint_changed": False},
    )
    allowed = sorted(review_evidence.WO023_G1_ALLOWED_PATHS)
    review_evidence.require_wo023_g1_scope(
        review_evidence.WO023_G1_WORK_ORDER,
        review_evidence.WO023_G1_BASE_SHA,
        allowed,
    )
    with pytest.raises(ValueError, match="exact base"):
        review_evidence.require_wo023_g1_scope(
            review_evidence.WO023_G1_WORK_ORDER, "f" * 40, allowed
        )
    with pytest.raises(ValueError, match="base branch"):
        review_evidence.require_wo023_g1_scope(
            review_evidence.WO023_G1_WORK_ORDER,
            review_evidence.WO023_G1_BASE_SHA,
            allowed,
            base_branch="release",
        )
    for extra in (
        review_evidence.CHECKPOINT_PATH,
        review_evidence.CANONICAL_MANIFEST_PATH,
        "migrations/versions/0008_next.py",
        "backend/app/retrieval.py",
        ".github/workflows/ci.yml",
    ):
        with pytest.raises(ValueError, match="exactly the four|canonical Project Brain|migrations"):
            review_evidence.require_wo023_g1_scope(
                review_evidence.WO023_G1_WORK_ORDER,
                review_evidence.WO023_G1_BASE_SHA,
                allowed + [extra],
            )


def test_wo023_scope_requires_merged_g1_support_and_bounded_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(review_evidence, "git_value", lambda *_args, **_kwargs: "a" * 40)
    monkeypatch.setattr(
        review_evidence,
        "git_blob_bytes",
        lambda *_args, **_kwargs: b"WO-023-G1",
    )
    monkeypatch.setattr(
        review_evidence,
        "canonical_change_evidence",
        lambda _paths, _work_order: {"project_brain_changed": False, "checkpoint_changed": False},
    )
    review_evidence.require_wo023_scope(
        review_evidence.WO023_WORK_ORDER,
        "a" * 40,
        ["backend/app/retrieval.py"],
        enforce_current_main=True,
    )
    monkeypatch.setattr(review_evidence, "git_blob_bytes", lambda *_args, **_kwargs: b"no g1")
    with pytest.raises(ValueError, match="merged WO-023-G1 support"):
        review_evidence.require_wo023_scope(
            review_evidence.WO023_WORK_ORDER,
            "a" * 40,
            ["backend/app/retrieval.py"],
            enforce_current_main=True,
        )
    monkeypatch.setattr(review_evidence, "git_blob_bytes", lambda *_args, **_kwargs: b"WO-023-G1")
    with pytest.raises(ValueError, match="outside the bounded"):
        review_evidence.require_wo023_scope(
            review_evidence.WO023_WORK_ORDER,
            "a" * 40,
            ["docs/project-brain/13-CHECKPOINT.md"],
            enforce_current_main=False,
        )
    with pytest.raises(ValueError, match="cannot change CI workflows"):
        review_evidence.require_wo023_scope(
            review_evidence.WO023_WORK_ORDER,
            "a" * 40,
            [".github/workflows/ci.yml"],
            enforce_current_main=False,
        )


def test_wo023_scope_authorizes_only_the_parser_correction_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(review_evidence, "git_value", lambda *_args, **_kwargs: "a" * 40)
    monkeypatch.setattr(review_evidence, "git_blob_bytes", lambda *_args, **_kwargs: b"WO-023-G1")
    monkeypatch.setattr(
        review_evidence,
        "canonical_change_evidence",
        lambda _paths, _work_order: {"project_brain_changed": False, "checkpoint_changed": False},
    )
    assert {
        "backend/tests/test_review_evidence.py",
        "scripts/review_evidence.py",
    } == set(review_evidence.WO023_AUTHORIZED_CORRECTION_PATHS)
    review_evidence.require_wo023_scope(
        review_evidence.WO023_WORK_ORDER,
        "a" * 40,
        sorted(review_evidence.WO023_AUTHORIZED_CORRECTION_PATHS),
        base_branch="main",
        enforce_current_main=False,
    )
    for forbidden in ("schemas/review-evidence-v1.schema.json", "scripts/review_pr_body.py"):
        assert forbidden in review_evidence.WO023_PRODUCT_FORBIDDEN_PATHS
        with pytest.raises(ValueError, match="outside the bounded"):
            review_evidence.require_wo023_scope(
                review_evidence.WO023_WORK_ORDER,
                "a" * 40,
                [forbidden],
                enforce_current_main=False,
            )


def test_wo023_comprehensive_benchmarks_contract_is_closed_and_truthful(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert set(wo023_benchmark_payload()) == (
        review_evidence.COMPREHENSIVE_BENCHMARKS_ALLOWED_FIELDS
    )
    monkeypatch.setattr(review_evidence, "integration_file", lambda _name: "")
    unknown = review_evidence.comprehensive_benchmarks_evidence()
    assert unknown["status"] == "UNKNOWN"
    assert set(unknown) == review_evidence.COMPREHENSIVE_BENCHMARKS_ALLOWED_FIELDS
    review_evidence.require_wo023_comprehensive_benchmarks_evidence(
        review_evidence.WO023_G1_WORK_ORDER,
        {},
    )
    with pytest.raises(ValueError, match="must not claim future"):
        review_evidence.require_wo023_comprehensive_benchmarks_evidence(
            review_evidence.WO023_G1_WORK_ORDER,
            {"comprehensive_benchmarks": wo023_benchmark_payload()},
        )
    migration = review_evidence.COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD
    with pytest.raises(ValueError, match="missing mandatory"):
        review_evidence.require_wo023_comprehensive_benchmarks_evidence(
            review_evidence.WO023_WORK_ORDER,
            {},
            migration,
        )
    review_evidence.require_wo023_comprehensive_benchmarks_evidence(
        review_evidence.WO023_WORK_ORDER,
        {"comprehensive_benchmarks": wo023_benchmark_payload()},
        migration,
    )
    mutations: tuple[tuple[str, dict[str, object], str], ...] = (
        ("empty evidence", {}, "closed contract"),
        (
            "unavailable family with numbers",
            wo023_benchmark_payload(
                token_metrics_status="NOT_SUPPORTED", token_reduction_percentage=37.5
            ),
            "core metrics",
        ),
        (
            "available family without numbers",
            wo023_benchmark_payload(token_reduction_percentage=None),
            "when reported AVAILABLE",
        ),
        ("critical miss", wo023_benchmark_payload(critical_context_misses=1), "0"),
        ("canonical loss", wo023_benchmark_payload(canonical_loss=True), "negative claims"),
        (
            "v0.1 claim",
            wo023_benchmark_payload(full_v01_complete_claimed=True),
            "negative claims",
        ),
        (
            "impossible bytes",
            wo023_benchmark_payload(storage_physical_bytes=2_000_000),
            "logical >= deduplicated",
        ),
        (
            "fabricated zero",
            wo023_benchmark_payload(
                token_metrics_status="UNAVAILABLE", token_reduction_percentage=0.0
            ),
            "core metrics",
        ),
        ("provider mismatch", wo023_benchmark_payload(optional_provider_calls=3), "provider"),
        ("bad digest", wo023_benchmark_payload(run_digest="not-a-digest"), "run digest"),
        ("extra field", {**wo023_benchmark_payload(), "unexpected": 1}, "closed contract"),
        (
            "wrong migration head",
            wo023_benchmark_payload(observed_migration_head="0006_memory_lifecycle_provenance"),
            "migration head",
        ),
        (
            "cross-project accepted",
            wo023_benchmark_payload(cross_project_retrieval_accepted=True),
            "negative claims",
        ),
        (
            "retrieval below accepted baseline",
            wo023_benchmark_payload(retrieval_recall_at_k=0.5),
            "accepted baseline",
        ),
        (
            "retrieval zero recall",
            wo023_benchmark_payload(retrieval_recall_at_k=0.0),
            "accepted baseline",
        ),
        (
            "zero precision",
            wo023_benchmark_payload(retrieval_precision=0.0),
            "strictly positive",
        ),
        (
            "contradictory token reduction",
            wo023_benchmark_payload(token_reduction_percentage=10.0),
            "contradicts the declared",
        ),
        (
            "optimized above baseline",
            wo023_benchmark_payload(token_optimized_input_tokens=50_000),
            "optimized < baseline",
        ),
        (
            "zero baseline tokens",
            wo023_benchmark_payload(token_baseline_input_tokens=0),
            "baseline",
        ),
        (
            "contradictory dedup ratio",
            wo023_benchmark_payload(storage_dedup_ratio=0.2),
            "contradicts the declared",
        ),
        (
            "contradictory compression ratio",
            wo023_benchmark_payload(storage_compression_ratio=0.9),
            "contradicts the declared",
        ),
        (
            "contradictory total reduction",
            wo023_benchmark_payload(storage_total_reduction_ratio=0.1),
            "contradicts the declared",
        ),
        ("empty evidence paths", wo023_benchmark_payload(evidence_paths=[]), "evidence paths"),
        (
            "duplicate evidence paths",
            wo023_benchmark_payload(
                evidence_paths=[
                    "backend/app/retrieval.py",
                    "backend/app/retrieval.py",
                ]
            ),
            "evidence paths",
        ),
        (
            "absolute evidence path",
            wo023_benchmark_payload(evidence_paths=["/etc/passwd"]),
            "evidence paths",
        ),
        (
            "traversal evidence path",
            wo023_benchmark_payload(evidence_paths=["scripts/../backend/app/retrieval.py"]),
            "evidence paths",
        ),
        (
            "out-of-scope evidence path",
            wo023_benchmark_payload(evidence_paths=["docs/project-brain/13-CHECKPOINT.md"]),
            "evidence paths",
        ),
        (
            "malformed ground truth prefix",
            wo023_benchmark_payload(ground_truth_source="HEAD-blob:docs/atlas/wo022.md"),
            "ground-truth source",
        ),
        (
            "arbitrary ground truth string",
            wo023_benchmark_payload(ground_truth_source="git:HEAD-blob:not a path"),
            "canonical repository-relative ground-truth path",
        ),
        (
            "traversal ground truth",
            wo023_benchmark_payload(
                ground_truth_source="git:HEAD-blob:scripts/../backend/app/retrieval.py"
            ),
            "canonical repository-relative ground-truth path",
        ),
        (
            "absolute ground truth",
            wo023_benchmark_payload(ground_truth_source="git:HEAD-blob:/etc/passwd"),
            "canonical repository-relative ground-truth path",
        ),
        (
            "missing ground truth blob",
            wo023_benchmark_payload(
                ground_truth_source="git:HEAD-blob:docs/atlas/wo023-missing-fixture.md"
            ),
            "exist at the reviewed HEAD",
        ),
        (
            "out-of-scope ground truth",
            wo023_benchmark_payload(
                ground_truth_source="git:HEAD-blob:docs/project-brain/13-CHECKPOINT.md"
            ),
            "canonical repository-relative ground-truth path",
        ),
    )
    c2_mutations: tuple[tuple[str, dict[str, object], str], ...] = (
        ("wrong recall depth k=1", wo023_benchmark_payload(retrieval_recall_k=1), "recall@5"),
        ("wrong recall depth k=10", wo023_benchmark_payload(retrieval_recall_k=10), "recall@5"),
        (
            "regressed reranking quality",
            wo023_benchmark_payload(retrieval_baseline_mrr=0.9, retrieval_reranked_mrr=0.5),
            "reranking quality",
        ),
        (
            "missing reranking baseline",
            wo023_benchmark_payload(retrieval_baseline_mrr=None),
            "reranking MRR evidence",
        ),
        (
            "zero context size",
            wo023_benchmark_payload(retrieval_context_bytes=0),
            "positive measured retrieval context size",
        ),
        (
            "unknown context measure",
            wo023_benchmark_payload(retrieval_context_measure="tokens-estimated"),
            "context-size measure",
        ),
        (
            "cache available without count",
            wo023_benchmark_payload(token_cache_status="AVAILABLE", token_cached_tokens=None),
            "token_cached_tokens",
        ),
        (
            "cache fabricated zero",
            wo023_benchmark_payload(token_cache_status="NOT_SUPPORTED", token_cached_tokens=0),
            "must not report token_cached_tokens",
        ),
        (
            "output available without count",
            wo023_benchmark_payload(token_output_status="AVAILABLE", token_output_tokens=None),
            "token_output_tokens",
        ),
        (
            "output fabricated zero",
            wo023_benchmark_payload(token_output_status="UNAVAILABLE", token_output_tokens=0),
            "must not report token_output_tokens",
        ),
        (
            "unknown cache status",
            wo023_benchmark_payload(token_cache_status="MAYBE"),
            "explicit token_cache_status",
        ),
        (
            "degraded task success",
            wo023_benchmark_payload(optimized_task_success_rate=0.5),
            "must not degrade benchmark task success",
        ),
        (
            "degraded test pass rate",
            wo023_benchmark_payload(optimized_test_pass_rate=0.9),
            "materially degrade the benchmark test pass rate",
        ),
        (
            "zero storage dataset",
            wo023_benchmark_payload(
                storage_logical_bytes=0,
                storage_dedup_bytes=0,
                storage_physical_bytes=0,
                storage_dedup_ratio=0.0,
                storage_compression_ratio=0.0,
                storage_total_reduction_ratio=0.0,
            ),
            "nonempty representative storage dataset",
        ),
    )
    for _label, candidate, expected in c2_mutations:
        with pytest.raises(ValueError, match=expected):
            review_evidence.require_wo023_comprehensive_benchmarks_evidence(
                review_evidence.WO023_WORK_ORDER,
                {"comprehensive_benchmarks": candidate},
                migration,
            )
    for placeholder in ("UNKNOWN", "unavailable", "NOT_SUPPORTED", "not-supported", "NONE", "   "):
        with pytest.raises(ValueError, match="baseline"):
            review_evidence.require_wo023_comprehensive_benchmarks_evidence(
                review_evidence.WO023_WORK_ORDER,
                {
                    "comprehensive_benchmarks": wo023_benchmark_payload(
                        baseline_reference_version=placeholder
                    )
                },
                migration,
            )
    for _family, status_field in (
        ("retrieval", "retrieval_metrics_status"),
        ("token", "token_metrics_status"),
        ("storage", "storage_metrics_status"),
    ):
        for status in ("UNAVAILABLE", "UNKNOWN", "NOT_SUPPORTED"):
            family_numbers = {
                "retrieval_metrics_status": {
                    "retrieval_recall_at_k": None,
                    "retrieval_precision": None,
                },
                "token_metrics_status": {"token_reduction_percentage": None},
                "storage_metrics_status": {
                    "storage_dedup_ratio": None,
                    "storage_compression_ratio": None,
                    "storage_total_reduction_ratio": None,
                },
            }[status_field]
            with pytest.raises(ValueError, match="core metrics"):
                review_evidence.require_wo023_comprehensive_benchmarks_evidence(
                    review_evidence.WO023_WORK_ORDER,
                    {
                        "comprehensive_benchmarks": wo023_benchmark_payload(
                            **{status_field: status}, **family_numbers
                        )
                    },
                    migration,
                )
    for _label, candidate, expected in mutations:
        with pytest.raises(ValueError, match=expected):
            review_evidence.require_wo023_comprehensive_benchmarks_evidence(
                review_evidence.WO023_WORK_ORDER,
                {"comprehensive_benchmarks": candidate},
                migration,
            )


def test_wo023_reader_rejects_invalid_evidence_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    valid = json.dumps(wo023_benchmark_payload())
    monkeypatch.setattr(review_evidence, "integration_file", lambda _name, _raw=valid: _raw)
    assert review_evidence.comprehensive_benchmarks_evidence()["status"] == "PASS"
    for bad_paths in (
        ["/etc/passwd"],
        ["scripts/../backend/app/retrieval.py"],
        [],
        ["docs/project-brain/13-CHECKPOINT.md"],
        ["backend/app/retrieval.py", "backend/app/retrieval.py"],
    ):
        raw = json.dumps(wo023_benchmark_payload(evidence_paths=bad_paths))
        monkeypatch.setattr(review_evidence, "integration_file", lambda _name, _raw=raw: _raw)
        assert review_evidence.comprehensive_benchmarks_evidence()["status"] == "FAIL"


def test_wo023_loader_keeps_literal_negative_claims_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A realistic evidence file must survive the file loader with false claims intact."""

    raw = json.dumps(wo023_benchmark_payload())
    monkeypatch.setattr(review_evidence, "integration_file", lambda _name, _raw=raw: _raw)
    loaded = review_evidence.comprehensive_benchmarks_evidence()

    for field in review_evidence.COMPREHENSIVE_BENCHMARKS_FALSE_FIELDS:
        assert loaded[field] is False, field
    for field in review_evidence.COMPREHENSIVE_BENCHMARKS_TRUE_FIELDS:
        assert loaded[field] is True, field
    assert loaded["provider_receipt_reconciled"] is False
    review_evidence.require_wo023_comprehensive_benchmarks_evidence(
        review_evidence.WO023_WORK_ORDER,
        {"comprehensive_benchmarks": loaded},
        review_evidence.COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD,
    )


def test_wo023_loader_never_normalizes_invalid_claims_into_accepted_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A true or missing negative claim must not become an accepted false claim."""

    for override in (
        {"canonical_loss": True},
        {"fabricated_metrics": True},
        {"full_v01_complete_claimed": True},
        {"provider_values_fabricated": True},
    ):
        payload = wo023_benchmark_payload(**override)
        raw = json.dumps(payload)
        monkeypatch.setattr(review_evidence, "integration_file", lambda _name, _raw=raw: _raw)
        loaded = review_evidence.comprehensive_benchmarks_evidence()
        field = next(iter(override))
        assert loaded[field] is True, field
        assert loaded["status"] == "FAIL"
        with pytest.raises(ValueError):
            review_evidence.require_wo023_comprehensive_benchmarks_evidence(
                review_evidence.WO023_WORK_ORDER,
                {"comprehensive_benchmarks": loaded},
                review_evidence.COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD,
            )

    missing = wo023_benchmark_payload()
    del missing["canonical_loss"]
    raw = json.dumps(missing)
    monkeypatch.setattr(review_evidence, "integration_file", lambda _name, _raw=raw: _raw)
    loaded = review_evidence.comprehensive_benchmarks_evidence()
    for field in review_evidence.COMPREHENSIVE_BENCHMARKS_TRUE_FIELDS:
        assert loaded[field] is False, field
    assert loaded["status"] == "FAIL"
    with pytest.raises(ValueError):
        review_evidence.require_wo023_comprehensive_benchmarks_evidence(
            review_evidence.WO023_WORK_ORDER,
            {"comprehensive_benchmarks": loaded},
            review_evidence.COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD,
        )


def test_wo023_true_claims_must_stay_true_through_the_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = wo023_benchmark_payload(benchmark_corpus_bounded=False)
    raw = json.dumps(payload)
    monkeypatch.setattr(review_evidence, "integration_file", lambda _name, _raw=raw: _raw)
    loaded = review_evidence.comprehensive_benchmarks_evidence()

    assert loaded["benchmark_corpus_bounded"] is False
    assert loaded["status"] == "FAIL"


def wo023_provider_receipt_evidence(**overrides: object) -> dict[str, object]:
    evidence: dict[str, object] = {
        "status": "PASS",
        **{
            field: True
            for field in review_evidence.COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_GUARANTEES
        },
        "provider_cache_provider_usage_sources": [
            "PROVIDER_REPORTED",
            "DERIVED_FROM_PROVIDER_REPORTED_FIELDS",
        ],
        "provider_cache_provider_total_input_tokens": 100,
        "provider_cache_provider_cached_input_tokens": 64,
        "provider_cache_provider_fresh_input_tokens": 36,
    }
    evidence.update(overrides)
    return evidence


def wo023_provider_receipt_artifact(**overrides: object) -> str:
    receipt: dict[str, object] = {
        "status": "PASS",
        "provider_usage_receipt_version": ("provider-usage-receipt-v1"),
        "provider_receipt_artifact": "provider-usage-receipt.json",
        "provider_reconciliation_state": "EXACT",
        "provider_usage_source": "PROVIDER_REPORTED",
        "provider_total_input_tokens": 100,
        "provider_cached_input_tokens": 64,
        "provider_fresh_input_tokens": 36,
        "provider_output_tokens": 12,
        "provider_calls": 1,
        "secret_leaks": 0,
        "credential_leaks": 0,
    }
    receipt.update(overrides)
    return json.dumps(receipt)


def wo023_provider_backed_payload(**overrides: object) -> dict[str, object]:
    payload = wo023_benchmark_payload()
    payload.update(
        {
            "token_cache_status": "AVAILABLE",
            "token_cached_tokens": 64,
            "token_output_status": "AVAILABLE",
            "token_output_tokens": 12,
            "provider_receipt_version": "provider-usage-receipt-v1",
            "provider_receipt_reconciled": True,
            "provider_receipt_artifact": "provider-usage-receipt.json",
            "provider_receipt_sha256": hashlib.sha256(
                wo023_provider_receipt_artifact().encode("utf-8")
            ).hexdigest(),
            "optional_provider_calls": 1,
            "optional_provider_metric": "provider.cached_input_tokens",
        }
    )
    payload.update(overrides)
    return payload


def test_wo023_provider_backed_token_claims_require_independent_provider_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = review_evidence.COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD
    provider_integration = {"context_manager": wo023_provider_receipt_evidence()}

    def load(receipt_text: str) -> None:
        def reader(name: str) -> str:
            if name == review_evidence.COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_FILE:
                return receipt_text
            return ""

        monkeypatch.setattr(review_evidence, "integration_file", reader)

    load(wo023_provider_receipt_artifact())
    review_evidence.require_wo023_comprehensive_benchmarks_evidence(
        review_evidence.WO023_WORK_ORDER,
        {"comprehensive_benchmarks": wo023_provider_backed_payload(), **provider_integration},
        migration,
    )
    # provider-independent core still passes with absent provider evidence
    load("")
    review_evidence.require_wo023_comprehensive_benchmarks_evidence(
        review_evidence.WO023_WORK_ORDER,
        {"comprehensive_benchmarks": wo023_benchmark_payload()},
        migration,
    )
    # explicit measured zero cache and zero output are valid when reconciled
    zero_receipt = wo023_provider_receipt_artifact(
        provider_cached_input_tokens=0,
        provider_fresh_input_tokens=100,
        provider_output_tokens=0,
    )
    zero_digest = hashlib.sha256(zero_receipt.encode("utf-8")).hexdigest()
    load(zero_receipt)
    review_evidence.require_wo023_comprehensive_benchmarks_evidence(
        review_evidence.WO023_WORK_ORDER,
        {
            "comprehensive_benchmarks": wo023_provider_backed_payload(
                token_cached_tokens=0,
                token_output_tokens=0,
                provider_receipt_sha256=zero_digest,
            ),
            **provider_integration,
        },
        migration,
    )
    load(wo023_provider_receipt_artifact())

    cases: tuple[tuple[str, dict[str, object], dict[str, Any], str], ...] = (
        (
            "available cache without provider evidence",
            wo023_provider_backed_payload(),
            {"__context": {}},
            "reconciled provider usage",
        ),
        (
            "independent receipt artifact missing",
            wo023_provider_backed_payload(),
            {"__receipt": ""},
            "independently loaded reconciled provider receipt",
        ),
        (
            "receipt digest mismatch",
            wo023_provider_backed_payload(provider_receipt_sha256="0" * 64),
            {},
            "identity does not match the loaded artifact",
        ),
        (
            "receipt output mismatch",
            wo023_provider_backed_payload(),
            {"__receipt": wo023_provider_receipt_artifact(provider_output_tokens=99)},
            "identity does not match the loaded artifact",
        ),
        (
            "receipt reconciliation unknown",
            wo023_provider_backed_payload(),
            {"__receipt": wo023_provider_receipt_artifact(provider_reconciliation_state="UNKNOWN")},
            "identity does not match the loaded artifact",
        ),
        (
            "receipt provider source missing",
            wo023_provider_backed_payload(),
            {"__receipt": wo023_provider_receipt_artifact(provider_usage_source="HIVE_ESTIMATE")},
            "identity does not match the loaded artifact",
        ),
        (
            "available cache with unreconciled receipt",
            wo023_provider_backed_payload(),
            {
                "context_manager": wo023_provider_receipt_evidence(
                    provider_cache_reported_usage_reconciled=False
                )
            },
            "provider usage guarantees",
        ),
        (
            "available cache with unknown provider accounting",
            wo023_provider_backed_payload(),
            {
                "context_manager": wo023_provider_receipt_evidence(
                    provider_cache_unknown_usage_not_zero=False
                )
            },
            "provider usage guarantees",
        ),
        (
            "cached count mismatch against the receipt",
            wo023_provider_backed_payload(token_cached_tokens=65),
            provider_integration,
            "contradicts the independent provider receipt",
        ),
        (
            "fresh tokens silently coerced to zero",
            wo023_provider_backed_payload(),
            {
                "context_manager": wo023_provider_receipt_evidence(
                    provider_cache_provider_fresh_input_tokens=0
                )
            },
            "reconcile with the provider total",
        ),
        (
            "fresh tokens unknown",
            wo023_provider_backed_payload(),
            {
                "context_manager": wo023_provider_receipt_evidence(
                    provider_cache_provider_fresh_input_tokens=None
                )
            },
            "reconciled provider usage",
        ),
        (
            "receipt without provider usage sources",
            wo023_provider_backed_payload(),
            {
                "context_manager": wo023_provider_receipt_evidence(
                    provider_cache_provider_usage_sources=["DERIVED_FROM_PROVIDER_REPORTED_FIELDS"]
                )
            },
            "provider usage sources",
        ),
        (
            "available output without provider evidence",
            wo023_provider_backed_payload(),
            {"__context": {}},
            "reconciled provider usage",
        ),
        (
            "output count mismatch against the receipt",
            wo023_provider_backed_payload(token_output_tokens=13),
            provider_integration,
            "contradicts the independent provider receipt",
        ),
        (
            "provider claim without recorded provider calls",
            wo023_provider_backed_payload(optional_provider_calls=0),
            provider_integration,
            "recorded provider usage",
        ),
        (
            "available cache with NONE receipt binding",
            wo023_provider_backed_payload(provider_receipt_version="NONE"),
            provider_integration,
            "provider-usage-receipt-v1",
        ),
        (
            "available cache without a reconciled receipt flag",
            wo023_provider_backed_payload(provider_receipt_reconciled=False),
            provider_integration,
            "reconciled provider usage evidence",
        ),
    )
    for _label, candidate, extra, expected in cases:
        receipt_text = cast(str, extra.pop("__receipt", wo023_provider_receipt_artifact()))
        context_evidence = extra.pop("__context", wo023_provider_receipt_evidence())
        load(receipt_text)
        with pytest.raises(ValueError, match=expected):
            review_evidence.require_wo023_comprehensive_benchmarks_evidence(
                review_evidence.WO023_WORK_ORDER,
                {
                    "comprehensive_benchmarks": candidate,
                    "context_manager": context_evidence,
                    **extra,
                },
                migration,
            )
    load(wo023_provider_receipt_artifact())
    # a receipt that matches the digest but carries contradictory output fails the cross-check
    mismatched = wo023_provider_receipt_artifact(provider_output_tokens=99)
    mismatched_digest = hashlib.sha256(mismatched.encode("utf-8")).hexdigest()
    load(mismatched)
    with pytest.raises(ValueError, match="output token count contradicts the independent"):
        review_evidence.require_wo023_comprehensive_benchmarks_evidence(
            review_evidence.WO023_WORK_ORDER,
            {
                "comprehensive_benchmarks": wo023_provider_backed_payload(
                    provider_receipt_sha256=mismatched_digest
                ),
                **provider_integration,
            },
            migration,
        )
    # a receipt with unknown reconciliation still fails when the digest matches
    unknown_receipt = wo023_provider_receipt_artifact(provider_reconciliation_state="INVALID")
    load(unknown_receipt)
    with pytest.raises(ValueError, match="EXACT"):
        review_evidence.require_wo023_comprehensive_benchmarks_evidence(
            review_evidence.WO023_WORK_ORDER,
            {
                "comprehensive_benchmarks": wo023_provider_backed_payload(
                    provider_receipt_sha256=hashlib.sha256(
                        unknown_receipt.encode("utf-8")
                    ).hexdigest()
                ),
                **provider_integration,
            },
            migration,
        )
    load(wo023_provider_receipt_artifact())
    # provider-independent payload must not carry receipt values
    for field, value in (
        ("provider_receipt_version", "provider-usage-receipt-v1"),
        ("provider_receipt_reconciled", True),
        ("provider_receipt_artifact", "provider-usage-receipt.json"),
        ("provider_receipt_sha256", "a" * 64),
    ):
        with pytest.raises(ValueError, match="provider receipt"):
            review_evidence.require_wo023_comprehensive_benchmarks_evidence(
                review_evidence.WO023_WORK_ORDER,
                {"comprehensive_benchmarks": wo023_benchmark_payload(**{field: value})},
                migration,
            )


def test_wo023_governance_contracts_and_schema_agree(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(review_evidence, "migration_head", lambda: "0007_telemetry_events")
    governance = {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}}
    integration = {"comprehensive_benchmarks": wo023_benchmark_payload()}
    g1 = review_evidence.verify_wo023_g1_governance_contract(
        review_evidence.WO023_G1_WORK_ORDER,
        review_evidence.WO023_G1_BASE_SHA,
        sorted(review_evidence.WO023_G1_ALLOWED_PATHS),
        {"project_brain_changed": False, "checkpoint_changed": False, "authorized_paths": []},
        governance,
        {},
        "0007_telemetry_events",
    )
    assert g1 is not None
    assert "future_WO-023_registered=PASS" in g1
    assert "comprehensive-benchmarks-v1_fail_closed=PASS" in g1
    assert "unknown_WO-025_WO-025-P_WO-999=REJECTED" in g1
    assert "checkpoint_promotion=False" in g1
    with pytest.raises(ValueError, match="must not claim future"):
        review_evidence.verify_wo023_g1_governance_contract(
            review_evidence.WO023_G1_WORK_ORDER,
            review_evidence.WO023_G1_BASE_SHA,
            sorted(review_evidence.WO023_G1_ALLOWED_PATHS),
            {"project_brain_changed": False, "checkpoint_changed": False, "authorized_paths": []},
            governance,
            integration,
            "0007_telemetry_events",
        )
    product = review_evidence.verify_wo023_governance_contract(
        review_evidence.WO023_WORK_ORDER,
        "a" * 40,
        ["backend/app/retrieval.py"],
        {"project_brain_changed": False, "checkpoint_changed": False, "authorized_paths": []},
        governance,
        integration,
        "0007_telemetry_events",
    )
    assert product is not None
    assert "retrieval_family=PASS; token_family=PASS; storage_family=PASS" in product
    assert "full_v01_complete_claimed=False" in product
    assert "checkpoint_promotion=False" in product
    with pytest.raises(ValueError, match="passing comprehensive benchmarks"):
        review_evidence.verify_wo023_governance_contract(
            review_evidence.WO023_WORK_ORDER,
            "a" * 40,
            ["backend/app/retrieval.py"],
            {"project_brain_changed": False, "checkpoint_changed": False, "authorized_paths": []},
            governance,
            {
                "comprehensive_benchmarks": {
                    **wo023_benchmark_payload(),
                    "status": "FAIL",
                }
            },
            "0007_telemetry_events",
        )

    schema = json.loads(
        (review_evidence.ROOT / "schemas" / "review-evidence-v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    definition = schema["$defs"]["comprehensive_benchmarks_evidence"]
    jsonschema.validate(instance=wo023_benchmark_payload(), schema=definition)
    # the provider-backed fixture must satisfy the schema coupling as well
    jsonschema.validate(instance=wo023_provider_backed_payload(), schema=definition)
    assert set(definition["required"]) == review_evidence.COMPREHENSIVE_BENCHMARKS_ALLOWED_FIELDS
    assert definition["additionalProperties"] is False
    # Cross-field non-regression (task success and test-pass rates) and the exact
    # cached/fresh arithmetic are enforced by the Python validator because JSON Schema
    # cannot compare two properties without $data.
    assert len(definition["allOf"]) == 3
    for invalid in (
        wo023_benchmark_payload(full_v01_complete_claimed=True),
        wo023_benchmark_payload(canonical_loss=True),
        {**wo023_benchmark_payload(), "unexpected": 1},
        wo023_benchmark_payload(retrieval_recall_at_k=1.5),
        wo023_benchmark_payload(retrieval_recall_at_k=0.5),
        wo023_benchmark_payload(retrieval_precision=0.0),
        wo023_benchmark_payload(token_metrics_status="NOT_SUPPORTED"),
        wo023_benchmark_payload(evidence_paths=["/etc/passwd"]),
        wo023_benchmark_payload(
            evidence_paths=["backend/app/retrieval.py", "backend/app/retrieval.py"]
        ),
        wo023_benchmark_payload(ground_truth_source="git:HEAD-blob:not a path"),
        wo023_benchmark_payload(ground_truth_source="git:HEAD-blob:/etc/passwd"),
        wo023_benchmark_payload(benchmark_families=["retrieval", "token"]),
        wo023_benchmark_payload(retrieval_recall_k=1),
        wo023_benchmark_payload(retrieval_context_bytes=0),
        wo023_benchmark_payload(token_cache_status="AVAILABLE", token_cached_tokens=None),
        wo023_benchmark_payload(token_output_status="AVAILABLE", token_output_tokens=None),
        wo023_benchmark_payload(baseline_reference_version="UNKNOWN"),
        wo023_benchmark_payload(baseline_reference_version="none"),
        wo023_benchmark_payload(storage_physical_bytes=0),
        wo023_provider_backed_payload(provider_receipt_version="NONE"),
        wo023_provider_backed_payload(provider_receipt_reconciled=False),
        wo023_provider_backed_payload(provider_receipt_artifact="NONE"),
        wo023_provider_backed_payload(provider_receipt_sha256="NONE"),
        wo023_provider_backed_payload(provider_receipt_sha256="not-a-digest"),
        wo023_benchmark_payload(provider_receipt_version="provider-usage-receipt-v1"),
        wo023_benchmark_payload(provider_receipt_reconciled=True),
        wo023_benchmark_payload(provider_receipt_artifact="provider-usage-receipt.json"),
        wo023_benchmark_payload(provider_receipt_sha256="b" * 64),
    ):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=invalid, schema=definition)


def test_wo023_renderers_are_dedicated_and_fail_closed() -> None:
    common: dict[str, Any] = {
        "pr_number": 92,
        "branch": "governance/wo023-g1-comprehensive-benchmarks",
        "base_sha": review_evidence.WO023_G1_BASE_SHA,
        "head_sha": "b" * 40,
        "artifact_name": "artifact",
        "ruleset_before": "before",
        "ruleset_after": "after",
        "merge_before": "before",
        "merge_after": "after",
    }
    g1 = render_body(work_order=review_evidence.WO023_G1_WORK_ORDER, **common)
    assert g1.startswith("<!-- HIVE-WORK-ORDER: WO-023-G1 -->")
    assert f"<!-- HIVE-AUTHORIZED-BASE: {review_evidence.WO023_G1_BASE_SHA} -->" in g1
    assert "Exatamente quatro arquivos" in g1
    assert "comprehensive-benchmarks-v1" in g1
    assert "WO-025-P" in g1 and "WO-025" in g1
    assert "AWAITING_SOL" in g1
    assert "WO-023-G1 READY FOR SOL AUDIT" in g1
    product = render_body(
        work_order=review_evidence.WO023_WORK_ORDER,
        **{**common, "base_sha": "c" * 40, "head_sha": "d" * 40},
    )
    assert product.startswith("<!-- HIVE-WORK-ORDER: WO-023 -->")
    for marker in ("Retrieval:", "Token:", "Storage:", "comprehensive-benchmarks-v1"):
        assert marker in product
    assert "WO-023 READY FOR SOL AUDIT" in product
    assert "checkpoint" in product.casefold()
    # WO-025-P and WO-1.1-01 have dedicated governance renderers; the unrenderable frontier is
    # the next unregistered promotion and the unknown future identifiers.
    for unsupported in ("WO-026-P", "WO-032", "WO-999"):
        with pytest.raises(ValueError):
            render_body(work_order=unsupported, **common)


def test_wo018_registration_and_bounded_scopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    review_evidence.require_supported_work_order(review_evidence.WO018_G1_WORK_ORDER)
    review_evidence.require_supported_work_order(review_evidence.WO018_WORK_ORDER)
    monkeypatch.setattr(
        review_evidence, "migration_head", lambda: "0006_memory_lifecycle_provenance"
    )
    review_evidence.require_wo018_g1_scope(
        review_evidence.WO018_G1_WORK_ORDER,
        review_evidence.WO018_G1_BASE_SHA,
        sorted(review_evidence.WO018_G1_ALLOWED_PATHS),
    )
    with pytest.raises(ValueError, match="exact base"):
        review_evidence.require_wo018_g1_scope(
            review_evidence.WO018_G1_WORK_ORDER,
            "a" * 40,
            sorted(review_evidence.WO018_G1_ALLOWED_PATHS),
        )
    with pytest.raises(ValueError, match="base branch"):
        review_evidence.require_wo018_g1_scope(
            review_evidence.WO018_G1_WORK_ORDER,
            review_evidence.WO018_G1_BASE_SHA,
            sorted(review_evidence.WO018_G1_ALLOWED_PATHS),
            base_branch="release",
        )
    for forbidden in (
        "docs/project-brain/13-CHECKPOINT.md",
        "migrations/versions/0007_autonomous.py",
        "backend/app/execution_orchestrator.py",
        ".github/workflows/ci.yml",
    ):
        with pytest.raises(ValueError, match="exactly the four|canonical Project Brain|migrations"):
            review_evidence.require_wo018_g1_scope(
                review_evidence.WO018_G1_WORK_ORDER,
                review_evidence.WO018_G1_BASE_SHA,
                ["scripts/review_evidence.py", forbidden],
            )

    review_evidence.require_wo018_scope(
        review_evidence.WO018_WORK_ORDER,
        "b" * 40,
        ["backend/app/execution_orchestrator.py"],
    )
    with pytest.raises(ValueError, match="canonical Project Brain"):
        review_evidence.require_wo018_scope(
            review_evidence.WO018_WORK_ORDER,
            "b" * 40,
            ["docs/project-brain/13-CHECKPOINT.md"],
        )
    with pytest.raises(ValueError, match="migrations"):
        review_evidence.require_wo018_scope(
            review_evidence.WO018_WORK_ORDER,
            "b" * 40,
            ["migrations/versions/0007_autonomous.py"],
        )
    with pytest.raises(ValueError, match="outside"):
        review_evidence.require_wo018_scope(
            review_evidence.WO018_WORK_ORDER,
            "b" * 40,
            ["backend/app/unrelated.py"],
        )


def test_wo018_autonomous_evidence_contract_is_closed() -> None:
    evidence = autonomous_execution_evidence_fixture()
    integration = {"autonomous_execution": evidence}
    review_evidence.require_wo018_autonomous_evidence(
        review_evidence.WO018_WORK_ORDER,
        integration,
        "0006_memory_lifecycle_provenance",
    )
    for field in review_evidence.AUTONOMOUS_EXECUTION_TRUE_FIELDS:
        broken = {**evidence, field: False}
        with pytest.raises(ValueError, match=field):
            review_evidence.require_wo018_autonomous_evidence(
                review_evidence.WO018_WORK_ORDER,
                {"autonomous_execution": broken},
                "0006_memory_lifecycle_provenance",
            )
    for field in review_evidence.AUTONOMOUS_EXECUTION_FALSE_FIELDS:
        broken = {**evidence, field: True}
        with pytest.raises(ValueError, match=field):
            review_evidence.require_wo018_autonomous_evidence(
                review_evidence.WO018_WORK_ORDER,
                {"autonomous_execution": broken},
                "0006_memory_lifecycle_provenance",
            )
    missing = dict(evidence)
    missing.pop("diff_captured")
    with pytest.raises(ValueError, match="shape"):
        review_evidence.require_wo018_autonomous_evidence(
            review_evidence.WO018_WORK_ORDER,
            {"autonomous_execution": missing},
            "0006_memory_lifecycle_provenance",
        )
    extra = {**evidence, "invented": True}
    with pytest.raises(ValueError, match="shape"):
        review_evidence.require_wo018_autonomous_evidence(
            review_evidence.WO018_WORK_ORDER,
            {"autonomous_execution": extra},
            "0006_memory_lifecycle_provenance",
        )


def test_wo018_future_product_requires_current_main_and_merged_g1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = "c" * 40
    monkeypatch.setattr(
        review_evidence,
        "git_value",
        lambda *args, fallback="": current if args == ("rev-parse", "origin/main") else fallback,
    )
    monkeypatch.setattr(
        review_evidence,
        "git_blob_bytes",
        lambda _revision, _path: b"merged WO-018-G1 governance support",
    )
    review_evidence.require_wo018_scope(
        review_evidence.WO018_WORK_ORDER,
        current,
        ["backend/app/execution_orchestrator.py"],
        enforce_current_main=True,
    )

    with pytest.raises(ValueError, match="current protected main"):
        review_evidence.require_wo018_scope(
            review_evidence.WO018_WORK_ORDER,
            "d" * 40,
            ["backend/app/execution_orchestrator.py"],
            enforce_current_main=True,
        )

    monkeypatch.setattr(
        review_evidence,
        "git_blob_bytes",
        lambda _revision, _path: b"governance support missing",
    )
    with pytest.raises(ValueError, match="requires merged WO-018-G1 support"):
        review_evidence.require_wo018_scope(
            review_evidence.WO018_WORK_ORDER,
            current,
            ["backend/app/execution_orchestrator.py"],
            enforce_current_main=True,
        )


def test_wo018_autonomous_evidence_rejects_identity_version_and_count_mutations() -> None:
    evidence = autonomous_execution_evidence_fixture()

    invalid_cases: tuple[tuple[str, object, str], ...] = (
        ("status", "FAIL", "must PASS"),
        ("evidence_file", "wrong.json", "file is invalid"),
        ("autonomous_evidence_version", "autonomous-execution-v0", "version is invalid"),
        ("executor_adapter_name", "UNKNOWN", "executor adapter identity"),
        ("observed_migration_head", "0005_semantic_retrieval", "migration head mismatch"),
        ("tool_subset_count", 0, "tool subset count"),
        ("validation_commands_count", 0, "validation command count"),
        ("executor_llm_calls", -1, "bounded integer"),
        ("executor_provider_calls", -1, "bounded integer"),
        ("secret_leaks", 1, "zero secret"),
        ("filesystem_path_leaks", 1, "zero secret"),
    )
    for field, value, message in invalid_cases:
        broken = {**evidence, field: value}
        with pytest.raises(ValueError, match=message):
            review_evidence.require_wo018_autonomous_evidence(
                review_evidence.WO018_WORK_ORDER,
                {"autonomous_execution": broken},
                "0006_memory_lifecycle_provenance",
            )


def test_wo018_autonomous_schema_rejects_extra_field() -> None:
    manifest = evidence_fixture()
    evidence_container = cast(dict[str, object], manifest["evidence"])
    integration = cast(dict[str, object], evidence_container["integration"])
    integration["autonomous_execution"] = {
        **autonomous_execution_evidence_fixture(),
        "invented": True,
    }
    with pytest.raises(ValueError, match="manifest schema validation failed"):
        validate_manifest(manifest)


def test_autonomous_execution_evidence_parser_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = autonomous_execution_evidence_fixture()
    monkeypatch.setattr(
        review_evidence,
        "integration_file",
        lambda name: json.dumps(evidence)
        if name == review_evidence.AUTONOMOUS_EXECUTION_EVIDENCE_FILE
        else "",
    )
    assert review_evidence.autonomous_execution_evidence() == evidence

    broken = {**evidence, "unauthorized_tool_rejected": False}
    monkeypatch.setattr(
        review_evidence,
        "integration_file",
        lambda name: json.dumps(broken)
        if name == review_evidence.AUTONOMOUS_EXECUTION_EVIDENCE_FILE
        else "",
    )
    assert review_evidence.autonomous_execution_evidence()["status"] == "FAIL"


def test_wo018_schema_and_renderers_are_explicit() -> None:
    manifest = evidence_fixture()
    evidence = cast(dict[str, object], manifest["evidence"])
    integration = cast(dict[str, object], evidence["integration"])
    integration["autonomous_execution"] = autonomous_execution_evidence_fixture()
    validate_manifest(manifest)

    g1 = render_body(
        work_order="WO-018-G1",
        pr_number=63,
        branch="governance/wo018-autonomous-evidence",
        base_sha=review_evidence.WO018_G1_BASE_SHA,
        head_sha="b" * 40,
        artifact_name="artifact",
        ruleset_before="before",
        ruleset_after="after",
        merge_before="before",
        merge_after="after",
    )
    assert "WO-018-G1 READY FOR SOL AUDIT" in g1
    product = render_body(
        work_order="WO-018",
        pr_number=64,
        branch="feature/wo018-autonomous-execution",
        base_sha="a" * 40,
        head_sha="b" * 40,
        artifact_name="artifact",
        ruleset_before="before",
        ruleset_after="after",
        merge_before="before",
        merge_after="after",
    )
    assert "WO-018 READY FOR SOL AUDIT" in product


def test_wo018_g1_governance_contract_rejects_product_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        review_evidence, "migration_head", lambda: "0006_memory_lifecycle_provenance"
    )
    governance = {
        "ruleset_unchanged": True,
        "pull_request": {"auto_merge_armed": False},
    }
    result = review_evidence.verify_wo018_g1_governance_contract(
        review_evidence.WO018_G1_WORK_ORDER,
        review_evidence.WO018_G1_BASE_SHA,
        sorted(review_evidence.WO018_G1_ALLOWED_PATHS),
        {
            "project_brain_changed": False,
            "checkpoint_changed": False,
            "authorized_paths": [],
        },
        governance,
        {},
        "0006_memory_lifecycle_provenance",
    )
    assert result is not None
    with pytest.raises(ValueError, match="must not claim"):
        review_evidence.verify_wo018_g1_governance_contract(
            review_evidence.WO018_G1_WORK_ORDER,
            review_evidence.WO018_G1_BASE_SHA,
            sorted(review_evidence.WO018_G1_ALLOWED_PATHS),
            {
                "project_brain_changed": False,
                "checkpoint_changed": False,
                "authorized_paths": [],
            },
            governance,
            {"autonomous_execution": autonomous_execution_evidence_fixture()},
            "0006_memory_lifecycle_provenance",
        )


def test_wo019_registration_and_bounded_scopes(monkeypatch: pytest.MonkeyPatch) -> None:
    review_evidence.require_supported_work_order(review_evidence.WO019_G1_WORK_ORDER)
    review_evidence.require_supported_work_order(review_evidence.WO019_WORK_ORDER)
    monkeypatch.setattr(
        review_evidence, "migration_head", lambda: "0006_memory_lifecycle_provenance"
    )
    review_evidence.require_wo019_g1_scope(
        review_evidence.WO019_G1_WORK_ORDER,
        review_evidence.WO019_G1_BASE_SHA,
        sorted(review_evidence.WO019_G1_ALLOWED_PATHS),
    )
    with pytest.raises(ValueError, match="exact base"):
        review_evidence.require_wo019_g1_scope(
            review_evidence.WO019_G1_WORK_ORDER,
            "a" * 40,
            sorted(review_evidence.WO019_G1_ALLOWED_PATHS),
        )
    with pytest.raises(ValueError, match="exactly the four|canonical Project Brain|migrations"):
        review_evidence.require_wo019_g1_scope(
            review_evidence.WO019_G1_WORK_ORDER,
            review_evidence.WO019_G1_BASE_SHA,
            ["scripts/review_evidence.py", "backend/app/telemetry.py"],
        )
    review_evidence.require_wo019_scope(
        review_evidence.WO019_WORK_ORDER,
        "b" * 40,
        ["backend/app/telemetry.py", "backend/tests/test_telemetry.py"],
    )
    with pytest.raises(ValueError, match="outside"):
        review_evidence.require_wo019_scope(
            review_evidence.WO019_WORK_ORDER,
            "b" * 40,
            [".github/workflows/ci.yml"],
        )
    with pytest.raises(ValueError, match="canonical Project Brain"):
        review_evidence.require_wo019_scope(
            review_evidence.WO019_WORK_ORDER,
            "b" * 40,
            ["docs/project-brain/13-CHECKPOINT.md"],
        )


def test_wo019_future_product_requires_current_main_and_merged_g1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = "c" * 40
    monkeypatch.setattr(
        review_evidence,
        "git_value",
        lambda *args, fallback="": current if args == ("rev-parse", "origin/main") else fallback,
    )
    monkeypatch.setattr(
        review_evidence,
        "git_blob_bytes",
        lambda _revision, _path: b"merged WO-019-G1 governance support",
    )
    review_evidence.require_wo019_scope(
        review_evidence.WO019_WORK_ORDER,
        current,
        ["backend/app/telemetry.py"],
        enforce_current_main=True,
    )
    with pytest.raises(ValueError, match="current protected main"):
        review_evidence.require_wo019_scope(
            review_evidence.WO019_WORK_ORDER,
            "d" * 40,
            ["backend/app/telemetry.py"],
            enforce_current_main=True,
        )
    monkeypatch.setattr(review_evidence, "git_blob_bytes", lambda _revision, _path: b"missing")
    with pytest.raises(ValueError, match="requires merged WO-019-G1 support"):
        review_evidence.require_wo019_scope(
            review_evidence.WO019_WORK_ORDER,
            current,
            ["backend/app/telemetry.py"],
            enforce_current_main=True,
        )


def test_wo019_telemetry_contract_is_versioned_bounded_and_fail_closed() -> None:
    evidence = telemetry_event_bus_evidence_fixture()
    review_evidence.require_wo019_telemetry_evidence(
        review_evidence.WO019_WORK_ORDER,
        {"telemetry_event_bus": evidence},
        "0006_memory_lifecycle_provenance",
    )
    with pytest.raises(ValueError, match="closed contract"):
        review_evidence.require_wo019_telemetry_evidence(
            review_evidence.WO019_WORK_ORDER,
            {"telemetry_event_bus": {**evidence, "invented": True}},
            "0006_memory_lifecycle_provenance",
        )
    invalid_cases: tuple[tuple[str, object, str], ...] = (
        ("telemetry_evidence_version", "telemetry-event-bus-v0", "version"),
        ("project_scoped", False, "missing mandatory"),
        ("implemented_event_types", ["unsupported.event"], "non-empty explicit"),
        ("payload_max_bytes", 0, "payload_max_bytes"),
        ("cross_project_leaks", 1, "cross_project_leaks=0"),
        ("llm_calls", 1, "llm_calls=0"),
        ("migration_changed", True, "truthful migration_changed"),
        ("producer_path", "C:/Users/private/telemetry.py", "sanitized relative"),
    )
    for field, value, message in invalid_cases:
        broken = {**evidence, field: value}
        with pytest.raises(ValueError, match=message):
            review_evidence.require_wo019_telemetry_evidence(
                review_evidence.WO019_WORK_ORDER,
                {"telemetry_event_bus": broken},
                "0006_memory_lifecycle_provenance",
            )
    with pytest.raises(ValueError, match="must not claim"):
        review_evidence.require_wo019_telemetry_evidence(
            review_evidence.WO019_G1_WORK_ORDER,
            {"telemetry_event_bus": evidence},
            "0006_memory_lifecycle_provenance",
        )


def test_wo019_schema_and_renderers_are_explicit() -> None:
    manifest = evidence_fixture()
    evidence = cast(dict[str, object], manifest["evidence"])
    integration = cast(dict[str, object], evidence["integration"])
    integration["telemetry_event_bus"] = {
        **telemetry_event_bus_evidence_fixture(),
        "invented": True,
    }
    with pytest.raises(ValueError, match="manifest schema validation failed"):
        validate_manifest(manifest)

    common: dict[str, Any] = {
        "pr_number": 70,
        "branch": "governance/wo019-telemetry-evidence",
        "base_sha": review_evidence.WO019_G1_BASE_SHA,
        "head_sha": "b" * 40,
        "artifact_name": "artifact",
        "ruleset_before": "before",
        "ruleset_after": "after",
        "merge_before": "before",
        "merge_after": "after",
    }
    g1 = render_body(work_order=review_evidence.WO019_G1_WORK_ORDER, **common)
    assert "telemetry-event-bus-v1" in g1
    assert "WO-019-G1 READY FOR SOL AUDIT" in g1
    product = render_body(work_order=review_evidence.WO019_WORK_ORDER, **common)
    assert "WO-019 READY FOR SOL AUDIT" in product
    assert "C:\\Users" not in product
    assert "D:\\Projeto Codexx" not in product


def test_wo020_registration_and_bounded_scopes(monkeypatch: pytest.MonkeyPatch) -> None:
    review_evidence.require_supported_work_order(review_evidence.WO020_G1_WORK_ORDER)
    review_evidence.require_supported_work_order(review_evidence.WO020_WORK_ORDER)
    monkeypatch.setattr(
        review_evidence,
        "migration_head",
        lambda: review_evidence.CONTROL_CENTER_CORE_MIGRATION_BASE_HEAD,
    )
    review_evidence.require_wo020_g1_scope(
        review_evidence.WO020_G1_WORK_ORDER,
        review_evidence.WO020_G1_BASE_SHA,
        sorted(review_evidence.WO020_G1_ALLOWED_PATHS),
    )
    with pytest.raises(ValueError, match="exact base"):
        review_evidence.require_wo020_g1_scope(
            review_evidence.WO020_G1_WORK_ORDER,
            "a" * 40,
            sorted(review_evidence.WO020_G1_ALLOWED_PATHS),
        )
    with pytest.raises(ValueError, match="exactly the four|canonical Project Brain|migrations"):
        review_evidence.require_wo020_g1_scope(
            review_evidence.WO020_G1_WORK_ORDER,
            review_evidence.WO020_G1_BASE_SHA,
            ["scripts/review_evidence.py", "dashboard/src/App.tsx"],
        )
    review_evidence.require_wo020_scope(
        review_evidence.WO020_WORK_ORDER,
        "b" * 40,
        ["dashboard/src/control-center/Fleet.tsx", "backend/app/control_center.py"],
    )
    with pytest.raises(ValueError, match="outside"):
        review_evidence.require_wo020_scope(
            review_evidence.WO020_WORK_ORDER,
            "b" * 40,
            ["backend/rogue.py"],
        )
    with pytest.raises(ValueError, match="cannot change CI workflows"):
        review_evidence.require_wo020_scope(
            review_evidence.WO020_WORK_ORDER,
            "b" * 40,
            [".github/workflows/ci.yml"],
        )
    with pytest.raises(ValueError, match="cannot change migrations"):
        review_evidence.require_wo020_scope(
            review_evidence.WO020_WORK_ORDER,
            "b" * 40,
            ["migrations/versions/0008_control_center.py"],
        )
    with pytest.raises(ValueError, match="cannot change dependencies"):
        review_evidence.require_wo020_scope(
            review_evidence.WO020_WORK_ORDER,
            "b" * 40,
            ["dashboard/package.json"],
        )
    with pytest.raises(ValueError, match="canonical Project Brain"):
        review_evidence.require_wo020_scope(
            review_evidence.WO020_WORK_ORDER,
            "b" * 40,
            ["docs/project-brain/13-CHECKPOINT.md"],
        )


def test_wo020_future_product_requires_current_main_and_merged_g1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = "c" * 40
    monkeypatch.setattr(
        review_evidence,
        "git_value",
        lambda *args, fallback="": current if args == ("rev-parse", "origin/main") else fallback,
    )
    monkeypatch.setattr(
        review_evidence,
        "git_blob_bytes",
        lambda _revision, _path: b"merged WO-020-G1 governance support",
    )
    review_evidence.require_wo020_scope(
        review_evidence.WO020_WORK_ORDER,
        current,
        ["dashboard/src/control-center/Fleet.tsx"],
        enforce_current_main=True,
    )
    with pytest.raises(ValueError, match="current protected main"):
        review_evidence.require_wo020_scope(
            review_evidence.WO020_WORK_ORDER,
            "d" * 40,
            ["dashboard/src/control-center/Fleet.tsx"],
            enforce_current_main=True,
        )
    monkeypatch.setattr(review_evidence, "git_blob_bytes", lambda _revision, _path: b"missing")
    with pytest.raises(ValueError, match="requires merged WO-020-G1 support"):
        review_evidence.require_wo020_scope(
            review_evidence.WO020_WORK_ORDER,
            current,
            ["dashboard/src/control-center/Fleet.tsx"],
            enforce_current_main=True,
        )


def test_wo020_control_center_contract_is_versioned_bounded_and_fail_closed() -> None:
    evidence = control_center_core_evidence_fixture()
    review_evidence.require_wo020_control_center_evidence(
        review_evidence.WO020_WORK_ORDER,
        {"control_center_core": evidence},
        review_evidence.CONTROL_CENTER_CORE_MIGRATION_BASE_HEAD,
    )
    with pytest.raises(ValueError, match="closed contract"):
        review_evidence.require_wo020_control_center_evidence(
            review_evidence.WO020_WORK_ORDER,
            {"control_center_core": {**evidence, "invented": True}},
            review_evidence.CONTROL_CENTER_CORE_MIGRATION_BASE_HEAD,
        )
    invalid_cases: tuple[tuple[str, object, str], ...] = (
        ("control_center_evidence_version", "control-center-core-v0", "version"),
        ("project_fleet_visible", False, "missing mandatory"),
        ("implemented_surfaces", ["unsupported-surface"], "non-empty explicit"),
        ("stream_transport", "grpc", "stream_transport"),
        ("cross_project_leaks", 1, "cross_project_leaks=0"),
        ("llm_calls", 1, "llm_calls=0"),
        ("full_control_center_claimed", True, "bounded negative"),
        ("migration_changed", True, "truthful migration_changed"),
        ("api_path", "C:/Users/private/control_center.py", "sanitized relative"),
    )
    for field, value, message in invalid_cases:
        broken = {**evidence, field: value}
        with pytest.raises(ValueError, match=message):
            review_evidence.require_wo020_control_center_evidence(
                review_evidence.WO020_WORK_ORDER,
                {"control_center_core": broken},
                review_evidence.CONTROL_CENTER_CORE_MIGRATION_BASE_HEAD,
            )
    with pytest.raises(ValueError, match="must not claim"):
        review_evidence.require_wo020_control_center_evidence(
            review_evidence.WO020_G1_WORK_ORDER,
            {"control_center_core": evidence},
            review_evidence.CONTROL_CENTER_CORE_MIGRATION_BASE_HEAD,
        )


def test_wo020_schema_and_renderers_are_explicit() -> None:
    manifest = evidence_fixture()
    evidence = cast(dict[str, object], manifest["evidence"])
    integration = cast(dict[str, object], evidence["integration"])
    integration["control_center_core"] = {
        **control_center_core_evidence_fixture(),
        "invented": True,
    }
    with pytest.raises(ValueError, match="manifest schema validation failed"):
        validate_manifest(manifest)

    common: dict[str, Any] = {
        "pr_number": 74,
        "branch": "governance/wo020-control-center-review-evidence",
        "base_sha": review_evidence.WO020_G1_BASE_SHA,
        "head_sha": "b" * 40,
        "artifact_name": "artifact",
        "ruleset_before": "before",
        "ruleset_after": "after",
        "merge_before": "before",
        "merge_after": "after",
    }
    g1 = render_body(work_order=review_evidence.WO020_G1_WORK_ORDER, **common)
    assert "control-center-core-v1" in g1
    assert "WO-020-G1 READY FOR SOL AUDIT" in g1
    product = render_body(work_order=review_evidence.WO020_WORK_ORDER, **common)
    assert "WO-020 READY FOR SOL AUDIT" in product
    assert "C:\\Users" not in product
    assert "D:\\Projeto Codexx" not in product


def test_wo020_g1_renderer_pins_validated_authorized_base_marker() -> None:
    base = review_evidence.WO020_G1_BASE_SHA
    assert AUTHORIZED_BASE_BY_WORK_ORDER[review_evidence.WO020_G1_WORK_ORDER] == base

    common: dict[str, Any] = {
        "pr_number": 74,
        "branch": "governance/wo020-control-center-review-evidence",
        "base_sha": base,
        "head_sha": "b" * 40,
        "artifact_name": "hive-review-evidence-WO-020-G1-b",
        "ruleset_before": "21934284 unchanged",
        "ruleset_after": "21934284 unchanged",
        "merge_before": "unarmed",
        "merge_after": "unarmed",
    }
    body = render_body(work_order=review_evidence.WO020_G1_WORK_ORDER, **common)
    lines = body.splitlines()
    assert lines[0] == "<!-- HIVE-WORK-ORDER: WO-020-G1 -->"
    assert lines[1] == f"<!-- HIVE-AUTHORIZED-BASE: {base} -->"
    assert sum(line.startswith("<!-- HIVE-WORK-ORDER:") for line in lines) == 1
    assert sum(line.startswith("<!-- HIVE-AUTHORIZED-BASE:") for line in lines) == 1
    assert f"- Base protegida exata: {base}." in body
    assert "WO-020-G1 READY FOR SOL AUDIT" in body
    assert "Sol Review State: AWAITING_SOL" in body
    assert "C:\\Users" not in body
    assert "D:\\Projeto Codexx" not in body
    assert "/home/" not in body
    assert "/Users/" not in body

    for rejected, expected in (
        (base.upper(), "lowercase 40-hex exact base"),
        ("b" * 39, "lowercase 40-hex exact base"),
        ("z" * 40, "lowercase 40-hex exact base"),
        ("0" * 40, "rejects the zero base"),
        ("b" * 40, "requires authorized base"),
    ):
        with pytest.raises(ValueError, match=expected):
            render_body(
                work_order=review_evidence.WO020_G1_WORK_ORDER,
                **{**common, "base_sha": rejected},
            )

    product = render_body(
        work_order=review_evidence.WO020_WORK_ORDER,
        **{**common, "base_sha": "a" * 40},
    )
    assert product.startswith("<!-- HIVE-WORK-ORDER: WO-020 -->")
    assert "WO-020 READY FOR SOL AUDIT" in product
    assert "<!-- HIVE-AUTHORIZED-BASE:" not in product

    assert (
        AUTHORIZED_BASE_BY_WORK_ORDER[review_evidence.WO020P_G1_WORK_ORDER]
        == review_evidence.WO020P_G1_BASE_SHA
    )
    marker = f"<!-- HIVE-AUTHORIZED-BASE: {review_evidence.WO020P_G1_BASE_SHA} -->"
    promotion_g1 = render_body(
        work_order=review_evidence.WO020P_G1_WORK_ORDER,
        **{**common, "base_sha": review_evidence.WO020P_G1_BASE_SHA},
    )
    assert promotion_g1.startswith("<!-- HIVE-WORK-ORDER: WO-020-P-G1 -->")
    assert marker in promotion_g1
    assert "WO-020-P-G1 READY FOR SOL AUDIT" in promotion_g1
    promotion = render_body(
        work_order=review_evidence.WO020P_WORK_ORDER,
        **{**common, "base_sha": review_evidence.WO020P_G1_BASE_SHA},
    )
    assert promotion.startswith("<!-- HIVE-WORK-ORDER: WO-020-P -->")
    assert "<!-- HIVE-AUTHORIZED-BASE:" in promotion
    assert "WO-020-P READY FOR SOL AUDIT" in promotion
    require_supported_work_order(review_evidence.WO021P_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO021P_WORK_ORDER)
    require_supported_work_order(review_evidence.WO022P_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO022P_WORK_ORDER)
    require_supported_work_order(review_evidence.WO023P_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO023P_WORK_ORDER)
    require_supported_work_order(review_evidence.WO024_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO024_WORK_ORDER)
    require_supported_work_order(review_evidence.WO024P_WORK_ORDER)
    # WO-025-P became registered in WO-025-G3, so the unregistered-promotion negative
    # moves to the next identifier of the same class.
    require_supported_work_order("WO-025-P")
    with pytest.raises(ValueError, match="unsupported checkpoint-promotion"):
        require_supported_work_order("WO-026-P")


def test_wo020_c1_evidence_paths_are_canonical_and_role_bounded() -> None:
    evidence = control_center_core_evidence_fixture()
    positive_cases = (
        ("api_path", "backend/app/control_center.py"),
        ("api_path", "backend/app/main.py"),
        ("dashboard_path", "dashboard/src/App.tsx"),
        ("dashboard_path", "dashboard/src/control-center/Fleet.tsx"),
    )
    negative_cases = (
        ("api_path", "../outside.py"),
        ("api_path", "backend/app/../outside.py"),
        ("api_path", "./backend/app/control_center.py"),
        ("api_path", "backend/app/./control_center.py"),
        ("api_path", "backend//app/control_center.py"),
        ("api_path", "/backend/app/control_center.py"),
        ("api_path", "C:/backend/app/control_center.py"),
        ("api_path", "C:\\backend\\app\\control_center.py"),
        ("api_path", "backend\\app\\control_center.py"),
        ("api_path", "backend/app/."),
        ("api_path", "backend/app/control_center.py/"),
        ("api_path", "backend/app/x/../../outside.py"),
        ("api_path", "backend/app/control_center\u0000.py"),
        ("api_path", ""),
        ("api_path", "backend/app/" + "a" * 256),
        ("api_path", "dashboard/src/App.tsx"),
        ("api_path", "backend/control_center.py"),
        ("dashboard_path", "backend/app/control_center.py"),
        ("dashboard_path", "dashboard/control-center/Fleet.tsx"),
        ("dashboard_path", "dashboard/src/../../outside.tsx"),
        ("dashboard_path", "dashboard/src/.."),
        ("dashboard_path", "./dashboard/src/App.tsx"),
        ("dashboard_path", "dashboard//src/App.tsx"),
        ("dashboard_path", "C:\\dashboard\\src\\App.tsx"),
    )
    for field, value in positive_cases:
        manifest = evidence_fixture()
        evidence_section = cast(dict[str, object], manifest["evidence"])
        integration = cast(dict[str, object], evidence_section["integration"])
        integration["control_center_core"] = {**evidence, field: value}
        validate_manifest(manifest)
        review_evidence.require_wo020_control_center_evidence(
            review_evidence.WO020_WORK_ORDER,
            {"control_center_core": {**evidence, field: value}},
            review_evidence.CONTROL_CENTER_CORE_MIGRATION_BASE_HEAD,
        )
    for field, value in negative_cases:
        manifest = evidence_fixture()
        evidence_section = cast(dict[str, object], manifest["evidence"])
        integration = cast(dict[str, object], evidence_section["integration"])
        integration["control_center_core"] = {**evidence, field: value}
        with pytest.raises(ValueError, match="manifest schema validation failed"):
            validate_manifest(manifest)
        with pytest.raises(ValueError, match=f"sanitized relative {field}"):
            review_evidence.require_wo020_control_center_evidence(
                review_evidence.WO020_WORK_ORDER,
                {"control_center_core": {**evidence, field: value}},
                review_evidence.CONTROL_CENTER_CORE_MIGRATION_BASE_HEAD,
            )


def test_wo020_c1_python_and_schema_path_parity_over_generated_corpus() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    properties = schema["$defs"]["control_center_core_evidence"]["properties"]
    fragments = (
        "a",
        "a/b",
        "a/./b",
        "a/../b",
        "./a",
        "../a",
        "a/",
        "/a",
        "a//b",
        ".hidden",
        "..a",
        "a.",
        "a b",
        "a\\b",
        "a:b",
        "a\u0001b",
        "a" * 256,
        "",
    )
    corpus = (
        *fragments,
        *(f"backend/app/{fragment}" for fragment in fragments),
        *(f"dashboard/src/{fragment}" for fragment in fragments),
        "backend/app",
        "dashboard/src",
        "backend/app/a/b.py",
        "dashboard/src/a/b.tsx",
    )
    api_schema = jsonschema.Draft202012Validator(properties["api_path"])
    dashboard_schema = jsonschema.Draft202012Validator(properties["dashboard_path"])
    for value in corpus:
        assert review_evidence.valid_control_center_core_path("api_path", value) is (
            api_schema.is_valid(value)
        ), value
        assert review_evidence.valid_control_center_core_path("dashboard_path", value) is (
            dashboard_schema.is_valid(value)
        ), value


def test_wo020_g1_governance_contract_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        review_evidence,
        "migration_head",
        lambda: review_evidence.CONTROL_CENTER_CORE_MIGRATION_BASE_HEAD,
    )
    governance = {
        "ruleset_unchanged": True,
        "pull_request": {"auto_merge_armed": False},
    }
    evidence = review_evidence.verify_wo020_g1_governance_contract(
        review_evidence.WO020_G1_WORK_ORDER,
        review_evidence.WO020_G1_BASE_SHA,
        sorted(review_evidence.WO020_G1_ALLOWED_PATHS),
        {
            "project_brain_changed": False,
            "checkpoint_changed": False,
            "authorized_paths": [],
        },
        governance,
        {},
        review_evidence.CONTROL_CENTER_CORE_MIGRATION_BASE_HEAD,
    )
    assert evidence is not None
    assert "unknown_WO-025-P_WO-999-P=REJECTED" in evidence
    with pytest.raises(ValueError, match="exactly the four"):
        review_evidence.verify_wo020_g1_governance_contract(
            review_evidence.WO020_G1_WORK_ORDER,
            review_evidence.WO020_G1_BASE_SHA,
            ["scripts/review_evidence.py"],
            {
                "project_brain_changed": False,
                "checkpoint_changed": False,
                "authorized_paths": [],
            },
            governance,
            {},
            review_evidence.CONTROL_CENTER_CORE_MIGRATION_BASE_HEAD,
        )


def test_gef_adoption_registration_markers_base_and_scope_are_fail_closed() -> None:
    work_order = review_evidence.GEF_ADOPTION_WORK_ORDER
    base = review_evidence.GEF_ADOPTION_BASE_SHA
    paths = sorted(review_evidence.GEF_ADOPTION_ALLOWED_PATHS)
    body = f"<!-- HIVE-WORK-ORDER: {work_order} -->\n<!-- HIVE-AUTHORIZED-BASE: {base} -->"

    assert review_evidence.parse_work_order_marker(body) == work_order
    assert review_evidence.parse_authorized_base_marker(body) == base
    review_evidence.require_current_work_order_authorization(work_order)
    review_evidence.require_gef_adoption_scope(
        work_order,
        base,
        paths,
        authorized_base_sha=base,
    )

    with pytest.raises(ValueError, match="unsupported GEF adoption"):
        review_evidence.require_supported_work_order("GEF-ADOPTION-002")
    with pytest.raises(ValueError, match="missing exactly one work-order marker"):
        review_evidence.parse_work_order_marker(f"<!-- HIVE-AUTHORIZED-BASE: {base} -->")
    with pytest.raises(ValueError, match="multiple conflicting"):
        review_evidence.parse_work_order_marker(
            f"<!-- HIVE-WORK-ORDER: {work_order} -->\n<!-- HIVE-WORK-ORDER: {work_order} -->"
        )
    with pytest.raises(ValueError, match="exact authorized-base marker"):
        review_evidence.require_gef_adoption_scope(
            work_order,
            base,
            paths,
            authorized_base_sha="a" * 40,
        )
    with pytest.raises(ValueError, match="exact base"):
        review_evidence.require_gef_adoption_scope(
            work_order,
            "b" * 40,
            paths,
            authorized_base_sha=base,
        )
    with pytest.raises(ValueError, match="exactly the ten GEF artifacts"):
        review_evidence.require_gef_adoption_scope(
            work_order,
            base,
            [*paths, "backend/app/unrelated.py"],
            authorized_base_sha=base,
        )


def test_wo021_registration_and_bounded_scopes(monkeypatch: pytest.MonkeyPatch) -> None:
    require_supported_work_order(review_evidence.WO021_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO021_WORK_ORDER)
    require_supported_work_order(review_evidence.WO021P_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO021P_WORK_ORDER)
    require_supported_work_order(review_evidence.WO022P_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO022P_WORK_ORDER)
    require_supported_work_order(review_evidence.WO022_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO022_WORK_ORDER)
    require_supported_work_order(review_evidence.WO023_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO023_WORK_ORDER)
    require_supported_work_order(review_evidence.WO023P_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO023P_WORK_ORDER)
    require_supported_work_order(review_evidence.WO024_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO024_WORK_ORDER)
    require_supported_work_order(review_evidence.WO024P_WORK_ORDER)
    # WO-025-P became registered in WO-025-G3, so the unregistered-promotion negative
    # moves to the next identifier of the same class.
    require_supported_work_order("WO-025-P")
    with pytest.raises(ValueError, match="unsupported checkpoint-promotion"):
        require_supported_work_order("WO-026-P")
    with pytest.raises(ValueError, match="unsupported future"):
        require_supported_work_order("WO-032")

    monkeypatch.setattr(review_evidence, "migration_head", lambda: "0007_telemetry_events")
    g1_paths = sorted(review_evidence.WO021_G1_ALLOWED_PATHS)
    review_evidence.require_wo021_g1_scope(
        review_evidence.WO021_G1_WORK_ORDER,
        review_evidence.WO021_G1_BASE_SHA,
        g1_paths,
    )
    with pytest.raises(ValueError, match="exact base"):
        review_evidence.require_wo021_g1_scope(
            review_evidence.WO021_G1_WORK_ORDER,
            "a" * 40,
            g1_paths,
        )
    with pytest.raises(ValueError, match="base branch"):
        review_evidence.require_wo021_g1_scope(
            review_evidence.WO021_G1_WORK_ORDER,
            review_evidence.WO021_G1_BASE_SHA,
            g1_paths,
            base_branch="release",
        )
    with pytest.raises(ValueError, match="exactly the four"):
        review_evidence.require_wo021_g1_scope(
            review_evidence.WO021_G1_WORK_ORDER,
            review_evidence.WO021_G1_BASE_SHA,
            g1_paths[:-1],
        )
    with pytest.raises(ValueError, match="exactly the four|canonical Project Brain"):
        review_evidence.require_wo021_g1_scope(
            review_evidence.WO021_G1_WORK_ORDER,
            review_evidence.WO021_G1_BASE_SHA,
            ["docs/project-brain/13-CHECKPOINT.md"],
        )
    with pytest.raises(ValueError, match="exactly the four|migrations"):
        review_evidence.require_wo021_g1_scope(
            review_evidence.WO021_G1_WORK_ORDER,
            review_evidence.WO021_G1_BASE_SHA,
            ["migrations/versions/0008_metrics.py"],
        )

    review_evidence.require_wo021_scope(
        review_evidence.WO021_WORK_ORDER,
        "b" * 40,
        [
            "backend/app/control_center_metrics.py",
            "dashboard/src/control-center/metrics.tsx",
            "docs/atlas/wo021-metrics.md",
        ],
    )
    scoped_failures = (
        (["docs/project-brain/13-CHECKPOINT.md"], "canonical Project Brain"),
        (["scripts/review_evidence.py"], "outside"),
        ([".github/workflows/ci.yml"], "cannot change CI workflows"),
        (["migrations/versions/0008_metrics.py"], "cannot change migrations"),
        (["requirements-dev.txt"], "cannot change dependencies"),
        (["VERSION"], "cannot change release files"),
        (["backend/unrelated.py"], "outside"),
    )
    for paths, message in scoped_failures:
        with pytest.raises(ValueError, match=message):
            review_evidence.require_wo021_scope(review_evidence.WO021_WORK_ORDER, "b" * 40, paths)


def test_wo021_product_scope_requires_current_main_and_merged_g1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = "c" * 40
    monkeypatch.setattr(
        review_evidence,
        "git_value",
        lambda *args, fallback="": current if args == ("rev-parse", "origin/main") else fallback,
    )
    monkeypatch.setattr(
        review_evidence,
        "git_blob_bytes",
        lambda _revision, _path: b"merged WO-021-G1 governance support",
    )
    review_evidence.require_wo021_scope(
        review_evidence.WO021_WORK_ORDER,
        current,
        ["backend/app/control_center_metrics.py"],
        enforce_current_main=True,
    )
    with pytest.raises(ValueError, match="current protected main"):
        review_evidence.require_wo021_scope(
            review_evidence.WO021_WORK_ORDER,
            "d" * 40,
            ["backend/app/control_center_metrics.py"],
            enforce_current_main=True,
        )
    monkeypatch.setattr(review_evidence, "git_blob_bytes", lambda _revision, _path: b"missing")
    with pytest.raises(ValueError, match="requires merged WO-021-G1 support"):
        review_evidence.require_wo021_scope(
            review_evidence.WO021_WORK_ORDER,
            current,
            ["backend/app/control_center_metrics.py"],
            enforce_current_main=True,
        )


def test_wo021_control_center_metrics_contract_is_bounded_and_fail_closed() -> None:
    evidence = control_center_metrics_evidence_fixture()
    review_evidence.require_wo021_control_center_metrics_evidence(
        review_evidence.WO021_WORK_ORDER,
        {"control_center_metrics": evidence},
        review_evidence.CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD,
    )
    with pytest.raises(ValueError, match="closed contract"):
        review_evidence.require_wo021_control_center_metrics_evidence(
            review_evidence.WO021_WORK_ORDER,
            {"control_center_metrics": {**evidence, "invented": True}},
            review_evidence.CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD,
        )

    for field in review_evidence.CONTROL_CENTER_METRICS_TRUE_FIELDS:
        broken = {**evidence, field: False}
        with pytest.raises(ValueError, match="missing mandatory"):
            review_evidence.require_wo021_control_center_metrics_evidence(
                review_evidence.WO021_WORK_ORDER,
                {"control_center_metrics": broken},
                review_evidence.CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD,
            )
    for field in review_evidence.CONTROL_CENTER_METRICS_FALSE_FIELDS:
        broken = {**evidence, field: True}
        with pytest.raises(ValueError, match="bounded negative"):
            review_evidence.require_wo021_control_center_metrics_evidence(
                review_evidence.WO021_WORK_ORDER,
                {"control_center_metrics": broken},
                review_evidence.CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD,
            )
    for field in (
        "secret_leaks",
        "filesystem_path_leaks",
        "cross_project_leaks",
        "metrics_llm_calls",
        "metrics_provider_calls",
    ):
        broken = {**evidence, field: 1}
        with pytest.raises(ValueError, match=f"{field}=0"):
            review_evidence.require_wo021_control_center_metrics_evidence(
                review_evidence.WO021_WORK_ORDER,
                {"control_center_metrics": broken},
                review_evidence.CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD,
            )

    invalid_cases: tuple[tuple[str, object, str], ...] = (
        ("status", "UNKNOWN", "passing"),
        ("evidence_file", "wrong.json", "control-center-metrics.json"),
        ("metrics_evidence_version", "control-center-metrics-v0", "evidence version"),
        ("observed_migration_head", "0006_memory_lifecycle_provenance", "observed migration"),
        ("migration_base_head", "0006_memory_lifecycle_provenance", "migration_base_head"),
        ("cost_provenance", "EXACT", "cost UNAVAILABLE"),
        ("migration_changed", True, "migration_changed=false"),
        ("historical_series_max_points", 0, "historical series"),
        ("historical_series_max_points", 513, "historical series"),
        ("implemented_metric_families", ["token", "context", "cache", "cache"], "families"),
        (
            "metric_value_provenance",
            ["EXACT", "ESTIMATED", "UNKNOWN", "UNKNOWN"],
            "distinct",
        ),
        ("metric_value_provenance", ["EXACT", "ESTIMATED", "UNAVAILABLE", "OTHER"], "distinct"),
        ("evidence_paths", [None], "normalized"),
        ("evidence_paths", ["C:/Users/private/metrics.py"], "normalized"),
        ("evidence_paths", ["backend/app/../private.py"], "normalized"),
    )
    for field, value, message in invalid_cases:
        broken = {**evidence, field: value}
        with pytest.raises(ValueError, match=message):
            review_evidence.require_wo021_control_center_metrics_evidence(
                review_evidence.WO021_WORK_ORDER,
                {"control_center_metrics": broken},
                review_evidence.CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD,
            )
    with pytest.raises(ValueError, match="closed contract|mandatory"):
        missing = dict(evidence)
        missing.pop("token_telemetry_visible")
        review_evidence.require_wo021_control_center_metrics_evidence(
            review_evidence.WO021_WORK_ORDER,
            {"control_center_metrics": missing},
            review_evidence.CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD,
        )
    review_evidence.require_wo021_control_center_metrics_evidence(
        review_evidence.WO021_G1_WORK_ORDER,
        {},
        review_evidence.CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD,
    )
    with pytest.raises(ValueError, match="must not claim"):
        review_evidence.require_wo021_control_center_metrics_evidence(
            review_evidence.WO021_G1_WORK_ORDER,
            {"control_center_metrics": evidence},
            review_evidence.CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD,
        )


def test_wo021_closed_metric_arrays_have_schema_python_permutation_parity() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    metrics_schema = schema["$defs"]["control_center_metrics_evidence"]
    schema_validator = jsonschema.Draft202012Validator(metrics_schema)
    evidence = control_center_metrics_evidence_fixture()

    family_permutations = tuple(permutations(review_evidence.CONTROL_CENTER_METRICS_FAMILIES))
    assert len(family_permutations) == 24
    for value in family_permutations:
        candidate = {**evidence, "implemented_metric_families": list(value)}
        assert schema_validator.is_valid(candidate)
        review_evidence.require_wo021_control_center_metrics_evidence(
            review_evidence.WO021_WORK_ORDER,
            {"control_center_metrics": candidate},
            review_evidence.CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD,
        )

    provenance_permutations = tuple(
        permutations(review_evidence.CONTROL_CENTER_METRICS_VALUE_PROVENANCE)
    )
    assert len(provenance_permutations) == 24
    for value in provenance_permutations:
        candidate = {**evidence, "metric_value_provenance": list(value)}
        assert schema_validator.is_valid(candidate)
        review_evidence.require_wo021_control_center_metrics_evidence(
            review_evidence.WO021_WORK_ORDER,
            {"control_center_metrics": candidate},
            review_evidence.CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD,
        )

    invalid_values: dict[str, tuple[object, ...]] = {
        "implemented_metric_families": (
            ["token", "context", "cache", "cache"],
            ["token", "context", "cache"],
            ["token", "context", "cache", "storage", "other"],
            "token",
        ),
        "metric_value_provenance": (
            ["EXACT", "ESTIMATED", "UNKNOWN", "UNKNOWN"],
            ["EXACT", "ESTIMATED", "UNKNOWN"],
            ["EXACT", "ESTIMATED", "UNAVAILABLE", "UNKNOWN", "OTHER"],
            "EXACT",
        ),
    }
    for field, values in invalid_values.items():
        for invalid_value in values:
            candidate = {**evidence, field: invalid_value}
            assert not schema_validator.is_valid(candidate)
            with pytest.raises(ValueError):
                review_evidence.require_wo021_control_center_metrics_evidence(
                    review_evidence.WO021_WORK_ORDER,
                    {"control_center_metrics": candidate},
                    review_evidence.CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD,
                )


def test_wo021_metrics_evidence_status_accepts_noncanonical_permutations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    integration_logs = tmp_path / "integration-logs"
    integration_logs.mkdir()
    monkeypatch.setattr(review_evidence, "INTEGRATION_LOGS", integration_logs)
    evidence = control_center_metrics_evidence_fixture()
    evidence["implemented_metric_families"] = ["storage", "cache", "context", "token"]
    evidence["metric_value_provenance"] = ["UNKNOWN", "UNAVAILABLE", "EXACT", "ESTIMATED"]
    (integration_logs / review_evidence.CONTROL_CENTER_METRICS_EVIDENCE_FILE).write_text(
        json.dumps(evidence), encoding="utf-8"
    )

    parsed = review_evidence.control_center_metrics_evidence()

    assert parsed["status"] == "PASS"
    assert parsed["implemented_metric_families"] == evidence["implemented_metric_families"]
    assert parsed["metric_value_provenance"] == evidence["metric_value_provenance"]

    for field, values in (
        (
            "implemented_metric_families",
            permutations(review_evidence.CONTROL_CENTER_METRICS_FAMILIES),
        ),
        (
            "metric_value_provenance",
            permutations(review_evidence.CONTROL_CENTER_METRICS_VALUE_PROVENANCE),
        ),
    ):
        for value in values:
            candidate = {**evidence, field: list(value)}
            (integration_logs / review_evidence.CONTROL_CENTER_METRICS_EVIDENCE_FILE).write_text(
                json.dumps(candidate), encoding="utf-8"
            )
            assert review_evidence.control_center_metrics_evidence()["status"] == "PASS"


def test_wo021_schema_and_renderers_are_explicit() -> None:
    manifest = evidence_fixture()
    evidence_section = cast(dict[str, object], manifest["evidence"])
    integration = cast(dict[str, object], evidence_section["integration"])
    metrics = control_center_metrics_evidence_fixture()
    integration["control_center_metrics"] = metrics
    validate_manifest(manifest)
    integration["control_center_metrics"] = {**metrics, "invented": True}
    with pytest.raises(ValueError, match="manifest schema validation failed"):
        validate_manifest(manifest)

    common: dict[str, Any] = {
        "pr_number": 78,
        "branch": "governance/wo021-control-center-metrics-review-evidence",
        "base_sha": review_evidence.WO021_G1_BASE_SHA,
        "head_sha": "b" * 40,
        "artifact_name": "hive-review-evidence-WO-021-G1-b",
        "ruleset_before": "21934284 unchanged",
        "ruleset_after": "21934284 unchanged",
        "merge_before": "unarmed",
        "merge_after": "unarmed",
    }
    assert AUTHORIZED_BASE_BY_WORK_ORDER[review_evidence.WO021_G1_WORK_ORDER] == (
        review_evidence.WO021_G1_BASE_SHA
    )
    g1 = render_body(work_order=review_evidence.WO021_G1_WORK_ORDER, **common)
    assert g1.splitlines()[0] == "<!-- HIVE-WORK-ORDER: WO-021-G1 -->"
    assert g1.splitlines()[1] == (
        f"<!-- HIVE-AUTHORIZED-BASE: {review_evidence.WO021_G1_BASE_SHA} -->"
    )
    assert "control-center-metrics-v1" in g1
    assert "WO-021-G1 READY FOR SOL AUDIT" in g1
    assert "WO-021" in g1
    assert "C:\\Users" not in g1
    assert "D:\\Projeto Codexx" not in g1
    assert "/home/" not in g1
    for rejected in ("a" * 40, "0" * 40, "z" * 40):
        with pytest.raises(ValueError):
            render_body(
                work_order=review_evidence.WO021_G1_WORK_ORDER,
                **{**common, "base_sha": rejected},
            )
    product = render_body(
        work_order=review_evidence.WO021_WORK_ORDER,
        **{**common, "base_sha": "a" * 40, "artifact_name": "artifact"},
    )
    assert product.startswith("<!-- HIVE-WORK-ORDER: WO-021 -->")
    assert "token, context, cache e storage" in product
    assert "WO-021 READY FOR SOL AUDIT" in product
    assert "<!-- HIVE-AUTHORIZED-BASE:" not in product
    assert "C:\\Users" not in product
    assert "D:\\Projeto Codexx" not in product


def test_wo021_metrics_paths_match_schema_over_generated_corpus() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    item_schema = schema["$defs"]["control_center_metrics_evidence"]["properties"][
        "evidence_paths"
    ]["items"]
    fragments = (
        "a",
        "a/b",
        "a/./b",
        "a/../b",
        "./a",
        "../a",
        "a/",
        "/a",
        "a//b",
        ".hidden",
        "..a",
        "a.",
        "a b",
        "a\\b",
        "a:b",
        "a\u0001b",
        "a" * 256,
        "",
    )
    roots = review_evidence.CONTROL_CENTER_METRICS_PATH_ROOTS
    corpus = (*fragments, *(f"{root}{fragment}" for root in roots for fragment in fragments))
    item_validator = jsonschema.Draft202012Validator(item_schema)
    for value in corpus:
        assert review_evidence.valid_control_center_metrics_path(value) is (
            item_validator.is_valid(value)
        ), value
    for root in roots:
        value = f"{root}valid.py"
        assert review_evidence.valid_control_center_metrics_path(value)
        assert item_validator.is_valid(value)


def test_wo021_governance_contract_and_manifest_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(review_evidence, "migration_head", lambda: "0007_telemetry_events")
    governance = {
        "ruleset_unchanged": True,
        "pull_request": {"auto_merge_armed": False},
    }
    canonical = {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }
    integration = {"control_center_metrics": control_center_metrics_evidence_fixture()}
    g1_evidence = review_evidence.verify_wo021_g1_governance_contract(
        review_evidence.WO021_G1_WORK_ORDER,
        review_evidence.WO021_G1_BASE_SHA,
        sorted(review_evidence.WO021_G1_ALLOWED_PATHS),
        canonical,
        governance,
        {},
        "0007_telemetry_events",
    )
    assert g1_evidence is not None
    assert "future_WO-021_registered=PASS" in g1_evidence
    assert "control-center-metrics-v1_fail_closed=PASS" in g1_evidence
    product_evidence = review_evidence.verify_wo021_governance_contract(
        review_evidence.WO021_WORK_ORDER,
        "b" * 40,
        ["backend/app/control_center_metrics.py"],
        canonical,
        governance,
        integration,
        "0007_telemetry_events",
    )
    assert product_evidence is not None
    assert "full_control_center_claimed=False" in product_evidence

    manifest = evidence_fixture()
    manifest["work_order"] = review_evidence.WO021_WORK_ORDER
    cast(dict[str, object], manifest["pull_request"])["number"] = None
    cast(dict[str, object], manifest["base"])["sha"] = "b" * 40
    cast(dict[str, object], manifest["changed_files"])["count"] = 1
    cast(dict[str, object], manifest["changed_files"])["paths"] = [
        "backend/app/control_center_metrics.py"
    ]
    cast(dict[str, object], manifest["migrations"])["head"] = "0007_telemetry_events"
    manifest_governance = cast(dict[str, object], manifest["governance"])
    cast(dict[str, object], manifest_governance["pull_request"])["auto_merge_armed"] = False
    manifest_integration = cast(
        dict[str, object], cast(dict[str, object], manifest["evidence"])["integration"]
    )
    manifest_integration["control_center_metrics"] = control_center_metrics_evidence_fixture()
    monkeypatch.setattr(
        review_evidence,
        "git_value",
        lambda *args, fallback="": "b" * 40 if args == ("rev-parse", "origin/main") else fallback,
    )
    monkeypatch.setattr(
        review_evidence,
        "git_blob_bytes",
        lambda _revision, _path: b"merged WO-021-G1 governance support",
    )
    cast(list[object], manifest["negative_scope"]).append(
        f"WO-021 governance evidence: {product_evidence}"
    )
    validate_manifest(manifest)


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
    require_wo017_scope(
        review_evidence.WO017P_G1_WORK_ORDER,
        "a" * 40,
        ["scripts/review_evidence.py"],
    )
    require_wo017_scope(
        review_evidence.WO017P_WORK_ORDER,
        "a" * 40,
        ["docs/project-brain/13-CHECKPOINT.md"],
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


def test_wo017_promotion_integration_evidence_carries_mcp_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    benchmark: dict[str, object] = {
        "status": "PASS",
        "redis_restart": True,
        "api_restart": True,
        "rerank": {"status": "PASS"},
        "query_count": 1,
        "recall_at_1": 1.0,
        "recall_at_5": 1.0,
        "mrr": 1.0,
        "critical_context_misses": 0,
        "two_run_reproducibility": True,
        "cross_project_isolation": True,
        "semantic": {"status": "PASS"},
        "hybrid": {"status": "PASS"},
        "hybrid_recall_at_5_gte_extended_lexical": True,
        "semantic_challenge_recovered": True,
        "semantic_integrity": {},
        "fallback": {},
    }
    monkeypatch.setattr(
        review_evidence,
        "integration_file",
        lambda _name: "retrieval corpus/lexical integration passed",
    )
    monkeypatch.setattr(
        review_evidence,
        "context_manager_evidence",
        lambda: {"status": "PASS"},
    )
    monkeypatch.setattr(
        review_evidence,
        "memory_lifecycle_evidence",
        lambda: {"status": "PASS"},
    )
    monkeypatch.setattr(
        review_evidence,
        "acce_storage_policy_evidence",
        lambda: {"status": "PASS"},
    )
    monkeypatch.setattr(
        review_evidence,
        "retrieval_integrity",
        lambda _retrieval: {},
    )
    monkeypatch.setattr(
        review_evidence,
        "integration_result",
        lambda _name, _needles: {"status": "PASS"},
    )
    mcp = mcp_surface_evidence_fixture()
    monkeypatch.setattr(review_evidence, "mcp_surface_evidence", lambda: mcp)

    for work_order in (
        WO017_WORK_ORDER,
        review_evidence.WO017P_G1_WORK_ORDER,
        review_evidence.WO017P_WORK_ORDER,
    ):
        observed = review_evidence.integration_evidence(
            benchmark,
            work_order=work_order,
        )
        assert observed["mcp_surface"] == mcp

    monkeypatch.setattr(
        review_evidence,
        "mcp_surface_evidence",
        lambda: {**mcp, "status": "FAIL"},
    )
    failed = review_evidence.integration_evidence(
        benchmark,
        work_order=review_evidence.WO017P_G1_WORK_ORDER,
    )
    assert failed["status"] == "FAIL"


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
    for promotion_work_order in (
        review_evidence.WO017P_G1_WORK_ORDER,
        review_evidence.WO017P_WORK_ORDER,
    ):
        with pytest.raises(ValueError, match="missing mandatory"):
            require_wo017_mcp_evidence(
                promotion_work_order,
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


def wo018p_checkpoint_fixture(*, include_evidence: bool = True) -> tuple[str, str]:
    base = review_evidence.git_blob_bytes(
        review_evidence.WO018P_G1_BASE_SHA,
        review_evidence.CHECKPOINT_PATH,
    ).decode("utf-8")
    candidate = replace_checkpoint_section(
        base,
        "STATUS",
        review_evidence.EXPECTED_WO018P_STATUS,
    )
    for pending_item in review_evidence.EXPECTED_WO018P_PENDING_ITEMS:
        candidate = candidate.replace(f"- {pending_item}\n", "")
    candidate = replace_checkpoint_section(
        candidate,
        "IN PROGRESS",
        f"- {review_evidence.EXPECTED_WO018P_IN_PROGRESS}",
    )
    candidate = replace_checkpoint_section(
        candidate,
        "BLOCKERS",
        review_evidence.EXPECTED_WO018P_BLOCKERS,
    )
    candidate = replace_checkpoint_section(
        candidate,
        "NEXT STEP",
        review_evidence.EXPECTED_WO018P_NEXT_STEP,
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
                for item in completed + list(review_evidence.WO018P_CANONICAL_COMPLETION_BULLETS)
            ),
        )
    return base, candidate


def test_wo018p_g1_scope_is_exact_and_noncanonical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        review_evidence, "migration_head", lambda: "0006_memory_lifecycle_provenance"
    )
    review_evidence.require_wo018p_g1_scope(
        review_evidence.WO018P_G1_WORK_ORDER,
        review_evidence.WO018P_G1_BASE_SHA,
        sorted(review_evidence.WO018P_G1_ALLOWED_PATHS),
    )
    with pytest.raises(ValueError, match="exact base"):
        review_evidence.require_wo018p_g1_scope(
            review_evidence.WO018P_G1_WORK_ORDER,
            "a" * 40,
            sorted(review_evidence.WO018P_G1_ALLOWED_PATHS),
        )
    with pytest.raises(ValueError, match="base branch"):
        review_evidence.require_wo018p_g1_scope(
            review_evidence.WO018P_G1_WORK_ORDER,
            review_evidence.WO018P_G1_BASE_SHA,
            sorted(review_evidence.WO018P_G1_ALLOWED_PATHS),
            base_branch="release",
        )
    for forbidden in (
        "docs/project-brain/13-CHECKPOINT.md",
        "docs/project-brain/CANONICAL-SHA256SUMS.txt",
        "migrations/versions/0007_telemetry.py",
        "backend/app/execution_orchestrator.py",
        ".github/workflows/ci.yml",
    ):
        with pytest.raises(
            ValueError,
            match="exactly the three|canonical Project Brain|migrations",
        ):
            review_evidence.require_wo018p_g1_scope(
                review_evidence.WO018P_G1_WORK_ORDER,
                review_evidence.WO018P_G1_BASE_SHA,
                ["scripts/review_evidence.py", forbidden],
            )


def test_wo018p_checkpoint_semantics_are_closed_and_exact() -> None:
    base, candidate = wo018p_checkpoint_fixture()
    review_evidence.require_wo018p_checkpoint_semantics(base, candidate)
    completed = review_evidence.checkpoint_bullets(
        review_evidence.checkpoint_sections(candidate), "COMPLETED"
    )
    assert completed[-5:] == list(review_evidence.WO018P_CANONICAL_COMPLETION_BULLETS)
    pending = review_evidence.checkpoint_bullets(
        review_evidence.checkpoint_sections(candidate), "PENDING"
    )
    for item in review_evidence.EXPECTED_WO018P_PENDING_ITEMS:
        assert item not in pending

    with pytest.raises(ValueError):
        review_evidence.require_wo018p_checkpoint_semantics(
            base,
            candidate.replace(
                review_evidence.EXPECTED_WO018P_NEXT_STEP,
                "Prepare the full Control Center first.",
                1,
            ),
        )
    with pytest.raises(ValueError):
        review_evidence.require_wo018p_checkpoint_semantics(
            base,
            candidate.replace("pr #65", "pr #64", 1),
        )
    missing_pending_removal = candidate.replace(
        "## PENDING\n",
        f"## PENDING\n- {review_evidence.EXPECTED_WO018P_PENDING_ITEMS[0]}\n",
        1,
    )
    with pytest.raises(ValueError):
        review_evidence.require_wo018p_checkpoint_semantics(base, missing_pending_removal)


def test_wo018p_manifest_contract_only_changes_checkpoint_hash() -> None:
    manifest_path = review_evidence.ROOT / review_evidence.CANONICAL_MANIFEST_PATH
    base_manifest = manifest_path.read_text(encoding="utf-8")
    _, candidate_checkpoint = wo018p_checkpoint_fixture()
    candidate_bytes = candidate_checkpoint.encode("utf-8")
    digest = hashlib.sha256(candidate_bytes).hexdigest()
    candidate_lines: list[str] = []
    changed = 0
    for line in base_manifest.splitlines(keepends=True):
        stripped = line.strip().split(maxsplit=1)
        if len(stripped) == 2 and stripped[1] == review_evidence.CANONICAL_MANIFEST_CHECKPOINT_NAME:
            prefix = line.index(stripped[0])
            line = line[:prefix] + digest + line[prefix + len(stripped[0]) :]
            changed += 1
        candidate_lines.append(line)
    assert changed == 1
    review_evidence.require_wo018p_manifest_contract(
        base_manifest,
        "".join(candidate_lines),
        candidate_bytes,
    )


def test_wo018p_renderers_are_explicit_and_exact_head() -> None:
    common: dict[str, Any] = {
        "pr_number": 66,
        "branch": "governance/wo018p-review-evidence-support",
        "base_sha": review_evidence.WO018P_G1_BASE_SHA,
        "head_sha": "b" * 40,
        "artifact_name": "artifact",
        "ruleset_before": "before",
        "ruleset_after": "after",
        "merge_before": "before",
        "merge_after": "after",
    }
    g1 = render_body(work_order=review_evidence.WO018P_G1_WORK_ORDER, **common)
    assert "WO-018-P-G1 READY FOR SOL AUDIT" in g1
    assert review_evidence.WO018P_G1_BASE_SHA in g1
    promotion = render_body(work_order=review_evidence.WO018P_WORK_ORDER, **common)
    assert "<!-- HIVE-AUTHORIZED-BASE:" in promotion
    assert "Telemetry/Event Bus" in promotion
    assert "WO-018-P READY FOR SOL AUDIT" in promotion
    for work_order in (
        review_evidence.WO018P_G1_WORK_ORDER,
        review_evidence.WO018P_WORK_ORDER,
    ):
        with pytest.raises(ValueError, match="40-hex exact HEAD"):
            render_body(work_order=work_order, **{**common, "head_sha": "abc123"})


def test_wo018p_autonomous_evidence_applies_to_promotion_pair() -> None:
    fixture = autonomous_execution_evidence_fixture()
    for work_order in (
        review_evidence.WO018P_G1_WORK_ORDER,
        review_evidence.WO018P_WORK_ORDER,
    ):
        review_evidence.require_wo018_autonomous_evidence(
            work_order,
            {"autonomous_execution": fixture},
            "0006_memory_lifecycle_provenance",
        )
        with pytest.raises(ValueError, match="missing mandatory"):
            review_evidence.require_wo018_autonomous_evidence(
                work_order,
                {},
                "0006_memory_lifecycle_provenance",
            )


def test_wo018p_g1_governance_contract_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        review_evidence, "migration_head", lambda: "0006_memory_lifecycle_provenance"
    )
    governance = {
        "ruleset_unchanged": True,
        "pull_request": {"auto_merge_armed": False},
    }
    integration = {"autonomous_execution": autonomous_execution_evidence_fixture()}
    evidence = review_evidence.verify_wo018p_g1_governance_contract(
        review_evidence.WO018P_G1_WORK_ORDER,
        review_evidence.WO018P_G1_BASE_SHA,
        sorted(review_evidence.WO018P_G1_ALLOWED_PATHS),
        {
            "project_brain_changed": False,
            "checkpoint_changed": False,
            "authorized_paths": [],
        },
        governance,
        integration,
        "0006_memory_lifecycle_provenance",
    )
    assert evidence is not None
    assert "future_two_file_scope=PASS" in evidence
    assert "autonomous_evidence=PASS" in evidence
    with pytest.raises(ValueError, match="auto-merge"):
        review_evidence.verify_wo018p_g1_governance_contract(
            review_evidence.WO018P_G1_WORK_ORDER,
            review_evidence.WO018P_G1_BASE_SHA,
            sorted(review_evidence.WO018P_G1_ALLOWED_PATHS),
            {
                "project_brain_changed": False,
                "checkpoint_changed": False,
                "authorized_paths": [],
            },
            {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": True}},
            integration,
            "0006_memory_lifecycle_provenance",
        )


def wo019p_checkpoint_fixture(*, include_evidence: bool = True) -> tuple[str, str]:
    base = review_evidence.git_blob_bytes(
        review_evidence.WO019P_G1_BASE_SHA,
        review_evidence.CHECKPOINT_PATH,
    ).decode("utf-8")
    candidate = replace_checkpoint_section(
        base,
        "STATUS",
        review_evidence.EXPECTED_WO019P_STATUS,
    )
    for pending_item in review_evidence.EXPECTED_WO019P_PENDING_ITEMS:
        candidate = candidate.replace(f"- {pending_item}\n", "")
    candidate = replace_checkpoint_section(
        candidate,
        "IN PROGRESS",
        f"- {review_evidence.EXPECTED_WO019P_IN_PROGRESS}",
    )
    candidate = replace_checkpoint_section(
        candidate,
        "BLOCKERS",
        review_evidence.EXPECTED_WO019P_BLOCKERS,
    )
    candidate = replace_checkpoint_section(
        candidate,
        "NEXT STEP",
        review_evidence.EXPECTED_WO019P_NEXT_STEP,
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
                for item in completed + list(review_evidence.WO019P_CANONICAL_COMPLETION_BULLETS)
            ),
        )
    return base, candidate


def test_wo019p_g1_scope_is_exact_and_noncanonical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(review_evidence, "migration_head", lambda: "0007_telemetry_events")
    review_evidence.require_wo019p_g1_scope(
        review_evidence.WO019P_G1_WORK_ORDER,
        review_evidence.WO019P_G1_BASE_SHA,
        sorted(review_evidence.WO019P_G1_ALLOWED_PATHS),
    )
    with pytest.raises(ValueError, match="exact base"):
        review_evidence.require_wo019p_g1_scope(
            review_evidence.WO019P_G1_WORK_ORDER,
            "a" * 40,
            sorted(review_evidence.WO019P_G1_ALLOWED_PATHS),
        )
    with pytest.raises(ValueError, match="base branch"):
        review_evidence.require_wo019p_g1_scope(
            review_evidence.WO019P_G1_WORK_ORDER,
            review_evidence.WO019P_G1_BASE_SHA,
            sorted(review_evidence.WO019P_G1_ALLOWED_PATHS),
            base_branch="release",
        )
    for forbidden in (
        "docs/project-brain/13-CHECKPOINT.md",
        "docs/project-brain/CANONICAL-SHA256SUMS.txt",
        "migrations/versions/0008_control_center.py",
        "backend/app/execution_orchestrator.py",
        ".github/workflows/ci.yml",
    ):
        with pytest.raises(
            ValueError,
            match="exactly the three|canonical Project Brain|migrations",
        ):
            review_evidence.require_wo019p_g1_scope(
                review_evidence.WO019P_G1_WORK_ORDER,
                review_evidence.WO019P_G1_BASE_SHA,
                ["scripts/review_evidence.py", forbidden],
            )


def test_wo019p_checkpoint_semantics_are_closed_and_exact() -> None:
    base, candidate = wo019p_checkpoint_fixture()
    review_evidence.require_wo019p_checkpoint_semantics(base, candidate)
    completed = review_evidence.checkpoint_bullets(
        review_evidence.checkpoint_sections(candidate), "COMPLETED"
    )
    assert completed[-5:] == list(review_evidence.WO019P_CANONICAL_COMPLETION_BULLETS)
    pending = review_evidence.checkpoint_bullets(
        review_evidence.checkpoint_sections(candidate), "PENDING"
    )
    for item in review_evidence.EXPECTED_WO019P_PENDING_ITEMS:
        assert item not in pending
    assert "full Control Center." in pending

    with pytest.raises(ValueError):
        review_evidence.require_wo019p_checkpoint_semantics(
            base,
            candidate.replace(
                review_evidence.EXPECTED_WO019P_NEXT_STEP,
                "Prepare the full Control Center first.",
                1,
            ),
        )
    with pytest.raises(ValueError):
        review_evidence.require_wo019p_checkpoint_semantics(
            base,
            candidate.replace(
                review_evidence.EXPECTED_WO019P_STATUS,
                "CONTROL CENTER FOUNDATION APPROVED / V0.1 IMPLEMENTATION ACTIVE",
                1,
            ),
        )
    with pytest.raises(ValueError):
        review_evidence.require_wo019p_checkpoint_semantics(
            base,
            candidate.replace("pr #70", "pr #69", 1),
        )
    missing_pending_removal = candidate.replace(
        "## PENDING\n",
        f"## PENDING\n- {review_evidence.EXPECTED_WO019P_PENDING_ITEMS[0]}\n",
        1,
    )
    with pytest.raises(ValueError):
        review_evidence.require_wo019p_checkpoint_semantics(base, missing_pending_removal)
    unrelated = replace_checkpoint_section(candidate, "OBJECTIVE", "Unrelated rewrite.")
    with pytest.raises(ValueError):
        review_evidence.require_wo019p_checkpoint_semantics(base, unrelated)


def test_wo019p_manifest_contract_only_changes_checkpoint_hash() -> None:
    manifest_path = review_evidence.ROOT / review_evidence.CANONICAL_MANIFEST_PATH
    base_manifest = manifest_path.read_text(encoding="utf-8")
    _, candidate_checkpoint = wo019p_checkpoint_fixture()
    candidate_bytes = candidate_checkpoint.encode("utf-8")
    digest = hashlib.sha256(candidate_bytes).hexdigest()
    candidate_lines: list[str] = []
    changed = 0
    for line in base_manifest.splitlines(keepends=True):
        stripped = line.strip().split(maxsplit=1)
        if len(stripped) == 2 and stripped[1] == review_evidence.CANONICAL_MANIFEST_CHECKPOINT_NAME:
            prefix = line.index(stripped[0])
            line = line[:prefix] + digest + line[prefix + len(stripped[0]) :]
            changed += 1
        candidate_lines.append(line)
    assert changed == 1
    review_evidence.require_wo019p_manifest_contract(
        base_manifest,
        "".join(candidate_lines),
        candidate_bytes,
    )


def test_wo019p_renderers_are_explicit_and_exact_head() -> None:
    common: dict[str, Any] = {
        "pr_number": 71,
        "branch": "governance/wo019-promotion-evidence",
        "base_sha": review_evidence.WO019P_G1_BASE_SHA,
        "head_sha": "b" * 40,
        "artifact_name": "artifact",
        "ruleset_before": "before",
        "ruleset_after": "after",
        "merge_before": "before",
        "merge_after": "after",
    }
    g1 = render_body(work_order=review_evidence.WO019P_G1_WORK_ORDER, **common)
    assert "WO-019-P-G1 READY FOR SOL AUDIT" in g1
    assert review_evidence.WO019P_G1_BASE_SHA in g1
    assert "<!-- HIVE-AUTHORIZED-BASE:" not in g1
    promotion = render_body(work_order=review_evidence.WO019P_WORK_ORDER, **common)
    assert "<!-- HIVE-AUTHORIZED-BASE:" in promotion
    assert "Control Center" in promotion
    assert "WO-019-P READY FOR SOL AUDIT" in promotion
    for work_order in (
        review_evidence.WO019P_G1_WORK_ORDER,
        review_evidence.WO019P_WORK_ORDER,
    ):
        with pytest.raises(ValueError, match="40-hex exact HEAD"):
            render_body(work_order=work_order, **{**common, "head_sha": "abc123"})


def test_wo019p_telemetry_evidence_applies_to_promotion_pair() -> None:
    fixture = telemetry_event_bus_evidence_fixture(observed_migration_head="0007_telemetry_events")
    for work_order in (
        review_evidence.WO019P_G1_WORK_ORDER,
        review_evidence.WO019P_WORK_ORDER,
    ):
        review_evidence.require_wo019_telemetry_evidence(
            work_order,
            {"telemetry_event_bus": fixture},
            "0007_telemetry_events",
        )
        with pytest.raises(ValueError, match="missing mandatory"):
            review_evidence.require_wo019_telemetry_evidence(
                work_order,
                {},
                "0007_telemetry_events",
            )


def test_wo019p_g1_governance_contract_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(review_evidence, "migration_head", lambda: "0007_telemetry_events")
    governance = {
        "ruleset_unchanged": True,
        "pull_request": {"auto_merge_armed": False},
    }
    integration = {
        "telemetry_event_bus": telemetry_event_bus_evidence_fixture(
            observed_migration_head="0007_telemetry_events"
        )
    }
    evidence = review_evidence.verify_wo019p_g1_governance_contract(
        review_evidence.WO019P_G1_WORK_ORDER,
        review_evidence.WO019P_G1_BASE_SHA,
        sorted(review_evidence.WO019P_G1_ALLOWED_PATHS),
        {
            "project_brain_changed": False,
            "checkpoint_changed": False,
            "authorized_paths": [],
        },
        governance,
        integration,
        "0007_telemetry_events",
    )
    assert evidence is not None
    assert "future_two_file_scope=PASS" in evidence
    assert "telemetry_evidence=PASS" in evidence
    assert "historical_WO-018-P-G1_WO-018-P=REJECTED" in evidence
    assert "unknown_WO-025-P_WO-999-P=REJECTED" in evidence
    with pytest.raises(ValueError, match="auto-merge"):
        review_evidence.verify_wo019p_g1_governance_contract(
            review_evidence.WO019P_G1_WORK_ORDER,
            review_evidence.WO019P_G1_BASE_SHA,
            sorted(review_evidence.WO019P_G1_ALLOWED_PATHS),
            {
                "project_brain_changed": False,
                "checkpoint_changed": False,
                "authorized_paths": [],
            },
            {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": True}},
            integration,
            "0007_telemetry_events",
        )


def test_wo019p_future_scope_is_fail_closed_without_promoted_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = sorted(review_evidence.WO019P_PROMOTION_ALLOWED_PATHS)
    with pytest.raises(ValueError, match="base branch"):
        review_evidence.require_wo019p_scope(
            review_evidence.WO019P_WORK_ORDER,
            "c" * 40,
            paths,
            registered_base_sha="c" * 40,
            authorized_base_sha="c" * 40,
            base_branch="release",
        )
    with pytest.raises(ValueError, match="current protected main base"):
        review_evidence.require_wo019p_scope(
            review_evidence.WO019P_WORK_ORDER,
            "a" * 40,
            paths,
            registered_base_sha="c" * 40,
            authorized_base_sha="a" * 40,
        )
    with pytest.raises(ValueError, match="exactly the checkpoint"):
        review_evidence.require_wo019p_scope(
            review_evidence.WO019P_WORK_ORDER,
            "c" * 40,
            [review_evidence.CHECKPOINT_PATH],
            registered_base_sha="c" * 40,
            authorized_base_sha="c" * 40,
        )
    with pytest.raises(ValueError, match="authorized-base"):
        review_evidence.require_wo019p_scope(
            review_evidence.WO019P_WORK_ORDER,
            "c" * 40,
            paths,
            registered_base_sha="c" * 40,
            authorized_base_sha=None,
        )
    with pytest.raises(ValueError, match="authorized-base"):
        review_evidence.require_wo019p_scope(
            review_evidence.WO019P_WORK_ORDER,
            "c" * 40,
            paths,
            registered_base_sha="c" * 40,
            authorized_base_sha="d" * 40,
        )
    monkeypatch.setattr(
        review_evidence,
        "git_value",
        lambda *args, fallback="": "e" * 40 if args == ("rev-parse", "origin/main") else fallback,
    )
    with pytest.raises(ValueError, match="must target current protected main"):
        review_evidence.require_wo019p_scope(
            review_evidence.WO019P_WORK_ORDER,
            "c" * 40,
            paths,
            registered_base_sha="c" * 40,
            authorized_base_sha="c" * 40,
            enforce_current_main=True,
        )
    monkeypatch.setattr(review_evidence, "git_blob_bytes", lambda *_args, **_kwargs: b"missing")
    with pytest.raises(ValueError, match="merged WO-019-P-G1"):
        review_evidence.require_wo019p_scope(
            review_evidence.WO019P_WORK_ORDER,
            "c" * 40,
            paths,
            registered_base_sha="c" * 40,
            authorized_base_sha="c" * 40,
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


def wo020p_checkpoint_fixture(*, include_evidence: bool = True) -> tuple[str, str]:
    base = review_evidence.git_blob_bytes(
        review_evidence.WO020P_G1_BASE_SHA,
        review_evidence.CHECKPOINT_PATH,
    ).decode("utf-8")
    candidate = replace_checkpoint_section(
        base,
        "STATUS",
        review_evidence.EXPECTED_WO020P_STATUS,
    )
    candidate = replace_checkpoint_section(
        candidate,
        "IN PROGRESS",
        f"- {review_evidence.EXPECTED_WO020P_IN_PROGRESS}",
    )
    candidate = replace_checkpoint_section(
        candidate,
        "BLOCKERS",
        review_evidence.EXPECTED_WO020P_BLOCKERS,
    )
    candidate = replace_checkpoint_section(
        candidate,
        "NEXT STEP",
        review_evidence.EXPECTED_WO020P_NEXT_STEP,
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
                for item in completed + list(review_evidence.WO020P_CANONICAL_COMPLETION_BULLETS)
            ),
        )
    return base, candidate


def wo021p_checkpoint_fixture(*, include_evidence: bool = True) -> tuple[str, str]:
    base = review_evidence.git_blob_bytes(
        review_evidence.WO021P_G1_BASE_SHA,
        review_evidence.CHECKPOINT_PATH,
    ).decode("utf-8")
    candidate = replace_checkpoint_section(
        base,
        "STATUS",
        review_evidence.EXPECTED_WO021P_STATUS,
    )
    candidate = replace_checkpoint_section(
        candidate,
        "IN PROGRESS",
        f"- {review_evidence.EXPECTED_WO021P_IN_PROGRESS}",
    )
    candidate = replace_checkpoint_section(
        candidate,
        "BLOCKERS",
        review_evidence.EXPECTED_WO021P_BLOCKERS,
    )
    candidate = replace_checkpoint_section(
        candidate,
        "NEXT STEP",
        review_evidence.EXPECTED_WO021P_NEXT_STEP,
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
                for item in completed + list(review_evidence.WO021P_CANONICAL_COMPLETION_BULLETS)
            ),
        )
    return base, candidate


def test_wo020p_g1_scope_is_exact_and_noncanonical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(review_evidence, "migration_head", lambda: "0007_telemetry_events")
    review_evidence.require_wo020p_g1_scope(
        review_evidence.WO020P_G1_WORK_ORDER,
        review_evidence.WO020P_G1_BASE_SHA,
        sorted(review_evidence.WO020P_G1_ALLOWED_PATHS),
    )
    with pytest.raises(ValueError, match="exact base"):
        review_evidence.require_wo020p_g1_scope(
            review_evidence.WO020P_G1_WORK_ORDER,
            "a" * 40,
            sorted(review_evidence.WO020P_G1_ALLOWED_PATHS),
        )
    with pytest.raises(ValueError, match="base branch"):
        review_evidence.require_wo020p_g1_scope(
            review_evidence.WO020P_G1_WORK_ORDER,
            review_evidence.WO020P_G1_BASE_SHA,
            sorted(review_evidence.WO020P_G1_ALLOWED_PATHS),
            base_branch="release",
        )
    for extra in (
        "docs/project-brain/13-CHECKPOINT.md",
        "docs/project-brain/CANONICAL-SHA256SUMS.txt",
        "migrations/versions/0008_control_center_metrics.py",
        "backend/app/control_center.py",
        "dashboard/src/App.tsx",
        "pyproject.toml",
        ".github/workflows/ci.yml",
    ):
        with pytest.raises(
            ValueError,
            match="exactly the three|canonical Project Brain|migrations",
        ):
            review_evidence.require_wo020p_g1_scope(
                review_evidence.WO020P_G1_WORK_ORDER,
                review_evidence.WO020P_G1_BASE_SHA,
                ["scripts/review_evidence.py", extra],
            )
    with pytest.raises(ValueError, match="exactly the three"):
        review_evidence.require_wo020p_g1_scope(
            review_evidence.WO020P_G1_WORK_ORDER,
            review_evidence.WO020P_G1_BASE_SHA,
            [
                "backend/tests/test_review_evidence.py",
                "scripts/review_evidence.py",
                "scripts/review_pr_body.py",
                "pyproject.toml",
            ],
        )


def test_wo020p_checkpoint_semantics_are_closed_and_exact() -> None:
    base, candidate = wo020p_checkpoint_fixture()
    review_evidence.require_wo020p_checkpoint_semantics(base, candidate)
    completed = review_evidence.checkpoint_bullets(
        review_evidence.checkpoint_sections(candidate), "COMPLETED"
    )
    assert completed[-6:] == list(review_evidence.WO020P_CANONICAL_COMPLETION_BULLETS)
    pending = review_evidence.checkpoint_bullets(
        review_evidence.checkpoint_sections(candidate), "PENDING"
    )
    assert pending == list(review_evidence.WO020P_REQUIRED_RETAINED_PENDING_ITEMS)
    assert "full Control Center." in pending

    for mutated in (
        candidate.replace("- full Control Center.\n", "", 1),
        candidate.replace(
            review_evidence.EXPECTED_WO020P_STATUS,
            "FULL CONTROL CENTER APPROVED / V0.1 IMPLEMENTATION ACTIVE",
            1,
        ),
        candidate.replace(
            review_evidence.EXPECTED_WO020P_NEXT_STEP,
            "Prepare the full Control Center first.",
            1,
        ),
        replace_checkpoint_section(candidate, "VERSION", "HIVE V0.2 - Total"),
        replace_checkpoint_section(candidate, "PHASE", "6 - Closure"),
        candidate.replace("pr #75", "pr #74", 1),
        candidate.replace("sol review 5180295002", "sol review 5180295003", 1),
        candidate.replace("post-merge ci 34615046572", "post-merge ci 34615046573", 1),
        candidate.replace(
            "squash merge 2e322095936f2a508f36563699e464d301f89ced",
            "squash merge " + "0" * 40,
            1,
        ),
        candidate.replace(
            "e52da09fafb7d4e17671225f09796b4613d18e3c751bff3c27e2e532d280ca10",
            "e52da09fafb7d4e17671225f09796b4613d18e3c751bff3c27e2e532d280ca11",
            1,
        ),
        replace_checkpoint_section(candidate, "OBJECTIVE", "Unrelated rewrite."),
    ):
        with pytest.raises(ValueError):
            review_evidence.require_wo020p_checkpoint_semantics(base, mutated)

    with pytest.raises(ValueError):
        review_evidence.require_wo020p_checkpoint_semantics(
            *wo020p_checkpoint_fixture(include_evidence=False)
        )

    reordered = candidate.replace(
        "- full Control Center.\n- comprehensive retrieval/token/storage benchmarks.",
        "- comprehensive retrieval/token/storage benchmarks.\n- full Control Center.",
        1,
    )
    with pytest.raises(ValueError):
        review_evidence.require_wo020p_checkpoint_semantics(base, reordered)
    deleted = candidate.replace("- stabilization.\n", "", 1)
    with pytest.raises(ValueError):
        review_evidence.require_wo020p_checkpoint_semantics(base, deleted)


def test_wo020p_manifest_contract_only_changes_checkpoint_hash() -> None:
    manifest_path = review_evidence.ROOT / review_evidence.CANONICAL_MANIFEST_PATH
    base_manifest = manifest_path.read_text(encoding="utf-8")
    _, candidate_checkpoint = wo020p_checkpoint_fixture()
    candidate_bytes = candidate_checkpoint.encode("utf-8")
    digest = hashlib.sha256(candidate_bytes).hexdigest()
    candidate_lines: list[str] = []
    changed = 0
    for line in base_manifest.splitlines(keepends=True):
        stripped = line.strip().split(maxsplit=1)
        if len(stripped) == 2 and stripped[1] == review_evidence.CANONICAL_MANIFEST_CHECKPOINT_NAME:
            prefix = line.index(stripped[0])
            line = line[:prefix] + digest + line[prefix + len(stripped[0]) :]
            changed += 1
        candidate_lines.append(line)
    assert changed == 1
    candidate_manifest = "".join(candidate_lines)
    review_evidence.require_wo020p_manifest_contract(
        base_manifest,
        candidate_manifest,
        candidate_bytes,
    )
    with pytest.raises(ValueError, match="does not match candidate bytes"):
        review_evidence.require_wo020p_manifest_contract(
            base_manifest,
            candidate_manifest,
            candidate_bytes + b"\n",
        )
    unrelated_lines = candidate_manifest.splitlines(keepends=True)
    for index, line in enumerate(unrelated_lines):
        parts = line.strip().split(maxsplit=1)
        if (
            len(parts) == 2
            and parts[1] != review_evidence.CANONICAL_MANIFEST_CHECKPOINT_NAME
            and re.fullmatch(r"[0-9a-f]{64}", parts[0])
        ):
            prefix = line.index(parts[0])
            flipped = "0" if parts[0][0] != "0" else "1"
            unrelated_lines[index] = (
                line[:prefix] + flipped + parts[0][1:] + line[prefix + len(parts[0]) :]
            )
            break
    else:
        raise AssertionError("canonical manifest lacks a second hash line")
    with pytest.raises(ValueError, match="unauthorized canonical hash"):
        review_evidence.require_wo020p_manifest_contract(
            base_manifest,
            "".join(unrelated_lines),
            candidate_bytes,
        )


def test_wo020p_renderers_are_explicit_and_exact_head() -> None:
    common: dict[str, Any] = {
        "pr_number": 76,
        "branch": "governance/wo020-p-g1-control-center-promotion",
        "base_sha": review_evidence.WO020P_G1_BASE_SHA,
        "head_sha": "b" * 40,
        "artifact_name": "artifact",
        "ruleset_before": "before",
        "ruleset_after": "after",
        "merge_before": "before",
        "merge_after": "after",
    }
    g1 = render_body(work_order=review_evidence.WO020P_G1_WORK_ORDER, **common)
    assert review_evidence.WO020P_G1_BASE_SHA in g1
    assert "WO-020-P-G1 READY FOR SOL AUDIT" in g1
    assert "<!-- HIVE-AUTHORIZED-BASE:" in g1
    assert "C:\\Users" not in g1
    assert "D:\\Projeto Codexx" not in g1
    assert "/home/" not in g1
    promotion = render_body(work_order=review_evidence.WO020P_WORK_ORDER, **common)
    assert "<!-- HIVE-AUTHORIZED-BASE:" in promotion
    assert "Control Center" in promotion
    assert "WO-020-P READY FOR SOL AUDIT" in promotion
    assert "C:\\Users" not in promotion
    assert "/home/" not in promotion
    for work_order in (
        review_evidence.WO020P_G1_WORK_ORDER,
        review_evidence.WO020P_WORK_ORDER,
    ):
        with pytest.raises(ValueError, match="40-hex exact HEAD"):
            render_body(work_order=work_order, **{**common, "head_sha": "abc123"})


def test_wo020p_control_center_evidence_applies_to_promotion_pair() -> None:
    fixture = control_center_core_evidence_fixture(observed_migration_head="0007_telemetry_events")
    for work_order in (
        review_evidence.WO020P_G1_WORK_ORDER,
        review_evidence.WO020P_WORK_ORDER,
    ):
        review_evidence.require_wo020_control_center_evidence(
            work_order,
            {"control_center_core": fixture},
            "0007_telemetry_events",
        )
        with pytest.raises(ValueError, match="missing mandatory"):
            review_evidence.require_wo020_control_center_evidence(
                work_order,
                {},
                "0007_telemetry_events",
            )
        failing = {**fixture, "status": "FAIL"}
        with pytest.raises(ValueError, match="passing Control Center evidence"):
            review_evidence.require_wo020_control_center_evidence(
                work_order,
                {"control_center_core": failing},
                "0007_telemetry_events",
            )
    with pytest.raises(ValueError, match="must not claim"):
        review_evidence.require_wo020_control_center_evidence(
            review_evidence.WO020_G1_WORK_ORDER,
            {"control_center_core": fixture},
            "0007_telemetry_events",
        )


def test_wo020p_g1_governance_contract_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(review_evidence, "migration_head", lambda: "0007_telemetry_events")
    governance = {
        "ruleset_unchanged": True,
        "pull_request": {"auto_merge_armed": False},
    }
    integration = {
        "control_center_core": control_center_core_evidence_fixture(
            observed_migration_head="0007_telemetry_events"
        )
    }
    evidence = review_evidence.verify_wo020p_g1_governance_contract(
        review_evidence.WO020P_G1_WORK_ORDER,
        review_evidence.WO020P_G1_BASE_SHA,
        sorted(review_evidence.WO020P_G1_ALLOWED_PATHS),
        {
            "project_brain_changed": False,
            "checkpoint_changed": False,
            "authorized_paths": [],
        },
        governance,
        integration,
        "0007_telemetry_events",
    )
    assert evidence is not None
    assert "exact_base=PASS" in evidence
    assert "active_promotions=WO-020-P-G1,WO-020-P" in evidence
    assert "historical_WO-019-P-G1_WO-019-P=REJECTED" in evidence
    assert "unknown_WO-025-P_WO-999-P=REJECTED" in evidence
    assert "control_center_evidence=PASS" in evidence
    assert "checkpoint_promotion=False" in evidence
    with pytest.raises(ValueError, match="auto-merge"):
        review_evidence.verify_wo020p_g1_governance_contract(
            review_evidence.WO020P_G1_WORK_ORDER,
            review_evidence.WO020P_G1_BASE_SHA,
            sorted(review_evidence.WO020P_G1_ALLOWED_PATHS),
            {
                "project_brain_changed": False,
                "checkpoint_changed": False,
                "authorized_paths": [],
            },
            {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": True}},
            integration,
            "0007_telemetry_events",
        )
    with pytest.raises(ValueError, match="missing mandatory Control Center evidence"):
        review_evidence.verify_wo020p_g1_governance_contract(
            review_evidence.WO020P_G1_WORK_ORDER,
            review_evidence.WO020P_G1_BASE_SHA,
            sorted(review_evidence.WO020P_G1_ALLOWED_PATHS),
            {
                "project_brain_changed": False,
                "checkpoint_changed": False,
                "authorized_paths": [],
            },
            governance,
            {},
            "0007_telemetry_events",
        )


def test_wo020p_future_scope_is_fail_closed_without_promoted_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = sorted(review_evidence.WO020P_PROMOTION_ALLOWED_PATHS)
    with pytest.raises(ValueError, match="base branch"):
        review_evidence.require_wo020p_scope(
            review_evidence.WO020P_WORK_ORDER,
            "c" * 40,
            paths,
            registered_base_sha="c" * 40,
            authorized_base_sha="c" * 40,
            base_branch="release",
        )
    with pytest.raises(ValueError, match="current protected main base"):
        review_evidence.require_wo020p_scope(
            review_evidence.WO020P_WORK_ORDER,
            "a" * 40,
            paths,
            registered_base_sha="c" * 40,
            authorized_base_sha="a" * 40,
        )
    with pytest.raises(ValueError, match="exactly the checkpoint"):
        review_evidence.require_wo020p_scope(
            review_evidence.WO020P_WORK_ORDER,
            "c" * 40,
            [review_evidence.CHECKPOINT_PATH],
            registered_base_sha="c" * 40,
            authorized_base_sha="c" * 40,
        )
    for extra in (
        "docs/project-brain/03-SCOPE.md",
        "migrations/versions/0008_control_center_metrics.py",
        "pyproject.toml",
        ".github/workflows/ci.yml",
        "backend/app/control_center.py",
    ):
        with pytest.raises(ValueError, match="exactly the checkpoint"):
            review_evidence.require_wo020p_scope(
                review_evidence.WO020P_WORK_ORDER,
                "c" * 40,
                [*paths, extra],
                registered_base_sha="c" * 40,
                authorized_base_sha="c" * 40,
            )
    with pytest.raises(ValueError, match="authorized-base"):
        review_evidence.require_wo020p_scope(
            review_evidence.WO020P_WORK_ORDER,
            "c" * 40,
            paths,
            registered_base_sha="c" * 40,
            authorized_base_sha=None,
        )
    with pytest.raises(ValueError, match="authorized-base"):
        review_evidence.require_wo020p_scope(
            review_evidence.WO020P_WORK_ORDER,
            "c" * 40,
            paths,
            registered_base_sha="c" * 40,
            authorized_base_sha="d" * 40,
        )
    monkeypatch.setattr(
        review_evidence,
        "git_value",
        lambda *args, fallback="": "e" * 40 if args == ("rev-parse", "origin/main") else fallback,
    )
    with pytest.raises(ValueError, match="must target current protected main"):
        review_evidence.require_wo020p_scope(
            review_evidence.WO020P_WORK_ORDER,
            "c" * 40,
            paths,
            registered_base_sha="c" * 40,
            authorized_base_sha="c" * 40,
            enforce_current_main=True,
        )
    monkeypatch.setattr(review_evidence, "git_blob_bytes", lambda *_args, **_kwargs: b"missing")
    with pytest.raises(ValueError, match="merged WO-020-P-G1"):
        review_evidence.require_wo020p_scope(
            review_evidence.WO020P_WORK_ORDER,
            "c" * 40,
            paths,
            registered_base_sha="c" * 40,
            authorized_base_sha="c" * 40,
        )


def test_wo021p_g1_scope_is_exact_and_noncanonical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(review_evidence, "migration_head", lambda: "0007_telemetry_events")
    paths = sorted(review_evidence.WO021P_G1_ALLOWED_PATHS)
    review_evidence.require_wo021p_g1_scope(
        review_evidence.WO021P_G1_WORK_ORDER,
        review_evidence.WO021P_G1_BASE_SHA,
        paths,
    )
    with pytest.raises(ValueError, match="exact base"):
        review_evidence.require_wo021p_g1_scope(
            review_evidence.WO021P_G1_WORK_ORDER,
            "a" * 40,
            paths,
        )
    with pytest.raises(ValueError, match="base branch"):
        review_evidence.require_wo021p_g1_scope(
            review_evidence.WO021P_G1_WORK_ORDER,
            review_evidence.WO021P_G1_BASE_SHA,
            paths,
            base_branch="release",
        )
    for extra in (
        "docs/project-brain/13-CHECKPOINT.md",
        "docs/project-brain/CANONICAL-SHA256SUMS.txt",
        "migrations/versions/0008_control_center_metrics.py",
        "backend/app/control_center_metrics.py",
        ".github/workflows/ci.yml",
    ):
        with pytest.raises(
            ValueError, match="exactly the three|canonical Project Brain|migrations"
        ):
            review_evidence.require_wo021p_g1_scope(
                review_evidence.WO021P_G1_WORK_ORDER,
                review_evidence.WO021P_G1_BASE_SHA,
                [*paths, extra],
            )


def test_wo021p_checkpoint_semantics_are_closed_and_retain_pending() -> None:
    base, candidate = wo021p_checkpoint_fixture()
    review_evidence.require_wo021p_checkpoint_semantics(base, candidate)
    completed = review_evidence.checkpoint_bullets(
        review_evidence.checkpoint_sections(candidate), "COMPLETED"
    )
    assert completed[-6:] == list(review_evidence.WO021P_CANONICAL_COMPLETION_BULLETS)
    pending = review_evidence.checkpoint_bullets(
        review_evidence.checkpoint_sections(candidate), "PENDING"
    )
    assert pending == list(review_evidence.WO021P_REQUIRED_RETAINED_PENDING_ITEMS)
    assert "full Control Center." in pending
    for mutated in (
        candidate.replace("- full Control Center.\n", "", 1),
        candidate.replace(
            review_evidence.EXPECTED_WO021P_STATUS,
            "FULL CONTROL CENTER APPROVED / V0.1 IMPLEMENTATION ACTIVE",
            1,
        ),
        candidate.replace(
            review_evidence.EXPECTED_WO021P_NEXT_STEP,
            "Prepare the full Control Center first.",
            1,
        ),
        candidate.replace(
            f"- {review_evidence.EXPECTED_WO021P_IN_PROGRESS}",
            "- Preparing the smallest necessary Control Center stabilization increment.",
            1,
        ).replace(
            review_evidence.EXPECTED_WO021P_NEXT_STEP,
            "Prepare the smallest necessary Control Center stabilization increment.",
            1,
        ),
        candidate.replace(
            review_evidence.WO021P_CANONICAL_COMPLETION_BULLETS[-1],
            "full HIVE V0.1 is complete.",
            1,
        ),
        replace_checkpoint_section(candidate, "VERSION", "HIVE V0.2 - Total"),
        candidate.replace("pr #82", "pr #81", 1),
    ):
        with pytest.raises(ValueError):
            review_evidence.require_wo021p_checkpoint_semantics(base, mutated)
    with pytest.raises(ValueError):
        review_evidence.require_wo021p_checkpoint_semantics(
            *wo021p_checkpoint_fixture(include_evidence=False)
        )


def test_wo021p_checkpoint_semantics_keep_the_historical_unrelated_section_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, candidate = wo021p_checkpoint_fixture()
    review_evidence.require_wo021p_checkpoint_semantics(base, candidate)
    controlled = {
        "STATUS",
        "COMPLETED",
        "IN PROGRESS",
        "PENDING",
        "BLOCKERS",
        "NEXT STEP",
    }
    unrelated = sorted(set(review_evidence.checkpoint_sections(base)) - controlled)
    assert {"VERSION", "PHASE", "OBJECTIVE"}.issubset(unrelated)

    for name in unrelated:
        mutated = replace_checkpoint_section(candidate, name, "WO-021-P unrelated rewrite")
        with pytest.raises(
            ValueError, match=f"WO-021-P changed unrelated checkpoint section: {name}"
        ):
            review_evidence.require_wo021p_checkpoint_semantics(base, mutated)

    monkeypatch.setattr(
        review_evidence,
        "_require_wo021p_strict_raw_checkpoint_grammar",
        lambda _base_text, _candidate_text: None,
    )
    for name in unrelated:
        mutated = replace_checkpoint_section(candidate, name, "WO-021-P unrelated rewrite")
        with pytest.raises(
            ValueError, match=f"WO-021-P changed unrelated checkpoint section: {name}"
        ):
            review_evidence.require_wo021p_checkpoint_semantics(base, mutated)


def test_wo022p_checkpoint_semantics_guard_unrelated_sections_independently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, candidate = wo022p_checkpoint_fixture()
    review_evidence.require_wo022p_checkpoint_semantics(base, candidate)
    monkeypatch.setattr(
        review_evidence,
        "_require_wo022p_strict_raw_checkpoint_grammar",
        lambda _base_text, _candidate_text: None,
    )
    for name in ("VERSION", "PHASE", "OBJECTIVE"):
        mutated = replace_checkpoint_section(candidate, name, "WO-022-P unrelated rewrite")
        with pytest.raises(
            ValueError, match=f"WO-022-P changed unrelated checkpoint section: {name}"
        ):
            review_evidence.require_wo022p_checkpoint_semantics(base, mutated)


def test_wo021p_manifest_contract_only_changes_checkpoint_hash() -> None:
    manifest_path = review_evidence.ROOT / review_evidence.CANONICAL_MANIFEST_PATH
    base_manifest = manifest_path.read_text(encoding="utf-8")
    _, candidate_checkpoint = wo021p_checkpoint_fixture()
    candidate_bytes = candidate_checkpoint.encode("utf-8")
    digest = hashlib.sha256(candidate_bytes).hexdigest()
    candidate_lines: list[str] = []
    changed = 0
    for line in base_manifest.splitlines(keepends=True):
        stripped = line.strip().split(maxsplit=1)
        if len(stripped) == 2 and stripped[1] == review_evidence.CANONICAL_MANIFEST_CHECKPOINT_NAME:
            prefix = line.index(stripped[0])
            line = line[:prefix] + digest + line[prefix + len(stripped[0]) :]
            changed += 1
        candidate_lines.append(line)
    assert changed == 1
    review_evidence.require_wo021p_manifest_contract(
        base_manifest,
        "".join(candidate_lines),
        candidate_bytes,
    )
    with pytest.raises(ValueError, match="does not match candidate bytes"):
        review_evidence.require_wo021p_manifest_contract(
            base_manifest,
            "".join(candidate_lines),
            candidate_bytes + b"\n",
        )


def test_wo021p_renderers_are_bounded_and_exact_head() -> None:
    common: dict[str, Any] = {
        "pr_number": 83,
        "branch": "governance/wo021-p-g1-control-center-metrics-promotion",
        "base_sha": review_evidence.WO021P_G1_BASE_SHA,
        "head_sha": "b" * 40,
        "artifact_name": "artifact",
        "ruleset_before": "before",
        "ruleset_after": "after",
        "merge_before": "before",
        "merge_after": "after",
    }
    g1 = render_body(work_order=review_evidence.WO021P_G1_WORK_ORDER, **common)
    assert g1.startswith("<!-- HIVE-WORK-ORDER: WO-021-P-G1 -->")
    assert "Exatamente três arquivos" in g1
    assert "WO-021-P-G1 READY FOR SOL AUDIT" in g1
    assert "control-center-metrics-v1" in g1
    promotion = render_body(work_order=review_evidence.WO021P_WORK_ORDER, **common)
    assert "WO-021-P READY FOR SOL AUDIT" in promotion
    assert "Full Control Center" in promotion
    assert "HIVE V0.1 completos" in promotion
    for work_order in (
        review_evidence.WO021P_G1_WORK_ORDER,
        review_evidence.WO021P_WORK_ORDER,
    ):
        with pytest.raises(ValueError, match="40-hex exact HEAD"):
            render_body(work_order=work_order, **{**common, "head_sha": "abc123"})


def test_wo021_approved_lineage_and_promotion_pair_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources = approved_wo021_lineage_sources_fixture()
    result = review_evidence.verify_wo021_approved_lineage(sources)
    review_evidence.require_wo021_approved_lineage_result(result)
    statement = review_evidence.wo021_approved_lineage_statement(result)
    assert review_evidence.parse_wo021_approved_lineage_statement(statement) == result

    mutations: tuple[Callable[[dict[str, Any]], object], ...] = (
        lambda value: value["product_pr"].update(number=81),
        lambda value: value["product_reviews"].__setitem__(
            0, {**value["product_reviews"][0], "id": 1}
        ),
        lambda value: value["post_merge_run"].update(conclusion="failure"),
        lambda value: value["prior_review_comments"].__setitem__(
            0,
            {"body": value["prior_review_comments"][0]["body"].replace("568 passed", "567 passed")},
        ),
    )
    for mutate in mutations:
        broken = json.loads(json.dumps(sources))
        mutate(broken)
        with pytest.raises(ValueError, match="WO-021"):
            review_evidence.verify_wo021_approved_lineage(broken)

    monkeypatch.setattr(review_evidence, "migration_head", lambda: "0007_telemetry_events")
    governance = {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}}
    integration = {"control_center_metrics": control_center_metrics_evidence_fixture()}
    g1 = review_evidence.verify_wo021p_g1_governance_contract(
        review_evidence.WO021P_G1_WORK_ORDER,
        review_evidence.WO021P_G1_BASE_SHA,
        sorted(review_evidence.WO021P_G1_ALLOWED_PATHS),
        {"project_brain_changed": False, "checkpoint_changed": False, "authorized_paths": []},
        governance,
        integration,
        "0007_telemetry_events",
        result,
    )
    assert g1 is not None
    assert "active_promotions=WO-021-P-G1,WO-021-P" in g1
    assert "control_center_metrics_evidence=PASS" in g1
    assert "checkpoint_promotion=False" in g1
    with pytest.raises(ValueError, match="approved product lineage"):
        review_evidence.verify_wo021p_g1_governance_contract(
            review_evidence.WO021P_G1_WORK_ORDER,
            review_evidence.WO021P_G1_BASE_SHA,
            sorted(review_evidence.WO021P_G1_ALLOWED_PATHS),
            {"project_brain_changed": False, "checkpoint_changed": False, "authorized_paths": []},
            governance,
            integration,
            "0007_telemetry_events",
            None,
        )
    with pytest.raises(ValueError, match="passing Control Center metrics"):
        review_evidence.verify_wo021p_g1_governance_contract(
            review_evidence.WO021P_G1_WORK_ORDER,
            review_evidence.WO021P_G1_BASE_SHA,
            sorted(review_evidence.WO021P_G1_ALLOWED_PATHS),
            {"project_brain_changed": False, "checkpoint_changed": False, "authorized_paths": []},
            governance,
            {"control_center_metrics": {**integration["control_center_metrics"], "status": "FAIL"}},
            "0007_telemetry_events",
            result,
        )


def wo022p_checkpoint_fixture(*, include_evidence: bool = True) -> tuple[str, str]:
    base = review_evidence.git_blob_bytes(
        review_evidence.WO022P_G1_BASE_SHA,
        review_evidence.CHECKPOINT_PATH,
    ).decode("utf-8")
    base_sections = review_evidence.checkpoint_sections(base)
    candidate = replace_checkpoint_section(
        base,
        "STATUS",
        review_evidence.EXPECTED_WO022P_STATUS,
    )
    candidate = replace_checkpoint_section(
        candidate,
        "IN PROGRESS",
        f"- {review_evidence.EXPECTED_WO022P_IN_PROGRESS}",
    )
    candidate = replace_checkpoint_section(
        candidate,
        "BLOCKERS",
        review_evidence.EXPECTED_WO022P_BLOCKERS,
    )
    candidate = replace_checkpoint_section(
        candidate,
        "NEXT STEP",
        review_evidence.EXPECTED_WO022P_NEXT_STEP,
    )
    if include_evidence:
        completed = review_evidence.checkpoint_bullets(base_sections, "COMPLETED")
        candidate = replace_checkpoint_section(
            candidate,
            "COMPLETED",
            "\n".join(
                f"- {item}"
                for item in completed + list(review_evidence.WO022P_CANONICAL_COMPLETION_BULLETS)
            ),
        )
    pending = [
        item
        for item in review_evidence.checkpoint_bullets(base_sections, "PENDING")
        if item != review_evidence.WO022P_COMPLETED_PENDING_ITEM
    ]
    candidate = replace_checkpoint_section(
        candidate,
        "PENDING",
        "\n".join(f"- {item}" for item in pending),
    )
    return base, candidate


def test_wo022p_checkpoint_semantics_are_closed_and_remove_only_completed_pending() -> None:
    base, candidate = wo022p_checkpoint_fixture()

    review_evidence.require_wo022p_checkpoint_semantics(base, candidate)

    candidate_sections = review_evidence.checkpoint_sections(candidate)
    completed = review_evidence.checkpoint_bullets(candidate_sections, "COMPLETED")
    assert completed[-6:] == list(review_evidence.WO022P_CANONICAL_COMPLETION_BULLETS)
    pending = review_evidence.checkpoint_bullets(candidate_sections, "PENDING")
    assert pending == list(review_evidence.WO022P_REQUIRED_RETAINED_PENDING_ITEMS)
    assert review_evidence.WO022P_COMPLETED_PENDING_ITEM not in pending
    assert review_evidence.WO022P_COMPLETED_PENDING_ITEM in review_evidence.checkpoint_bullets(
        review_evidence.checkpoint_sections(base), "PENDING"
    )

    _, without_evidence = wo022p_checkpoint_fixture(include_evidence=False)
    with pytest.raises(ValueError, match="WO-022-P"):
        review_evidence.require_wo022p_checkpoint_semantics(base, without_evidence)

    mutations: tuple[Callable[[str], str], ...] = (
        lambda text: replace_checkpoint_section(text, "STATUS", "FULL CONTROL CENTER APPROVED"),
        lambda text: replace_checkpoint_section(
            text,
            "NEXT STEP",
            review_evidence.EXPECTED_WO021P_NEXT_STEP,
        ),
        lambda text: replace_checkpoint_section(
            text,
            "BLOCKERS",
            (
                "None known after Control Center Metrics Foundation approval "
                "and post-merge validation."
            ),
        ),
        lambda text: replace_checkpoint_section(
            text,
            "COMPLETED",
            "\n".join(
                [
                    f"- {item}"
                    for item in review_evidence.checkpoint_bullets(
                        review_evidence.checkpoint_sections(text), "COMPLETED"
                    )[:-1]
                ]
                + ["- full HIVE V0.1 is complete."]
            ),
        ),
        lambda text: replace_checkpoint_section(
            text,
            "PENDING",
            f"- {review_evidence.WO022P_COMPLETED_PENDING_ITEM}\n"
            + "\n".join(
                f"- {item}" for item in review_evidence.WO022P_REQUIRED_RETAINED_PENDING_ITEMS
            ),
        ),
        lambda text: replace_checkpoint_section(
            text,
            "PENDING",
            "\n".join(
                f"- {item}"
                for item in reversed(review_evidence.WO022P_REQUIRED_RETAINED_PENDING_ITEMS)
            ),
        ),
        lambda text: text.replace(
            "pr #86 with audited head a870275b3ad738b789e30169d5b1fac00e2e4ae3",
            "pr #85 with audited head a870275b3ad738b789e30169d5b1fac00e2e4ae3",
        ),
        lambda text: replace_checkpoint_section(text, "VERSION", "WO-022-P rewrite"),
    )
    for mutate in mutations:
        with pytest.raises(ValueError, match="WO-022-P"):
            review_evidence.require_wo022p_checkpoint_semantics(base, mutate(candidate))


def test_wo022p_manifest_contract_only_changes_checkpoint_hash() -> None:
    manifest_path = review_evidence.ROOT / review_evidence.CANONICAL_MANIFEST_PATH
    base_manifest = manifest_path.read_text(encoding="utf-8")
    _, candidate_checkpoint = wo022p_checkpoint_fixture()
    candidate_bytes = candidate_checkpoint.encode("utf-8")
    digest = hashlib.sha256(candidate_bytes).hexdigest()
    candidate_lines: list[str] = []
    changed = 0
    for line in base_manifest.splitlines(keepends=True):
        stripped = line.strip().split(maxsplit=1)
        if len(stripped) == 2 and stripped[1] == review_evidence.CANONICAL_MANIFEST_CHECKPOINT_NAME:
            prefix = line.index(stripped[0])
            line = line[:prefix] + digest + line[prefix + len(stripped[0]) :]
            changed += 1
        candidate_lines.append(line)
    assert changed == 1
    review_evidence.require_wo022p_manifest_contract(
        base_manifest,
        "".join(candidate_lines),
        candidate_bytes,
    )
    with pytest.raises(ValueError, match="does not match candidate bytes"):
        review_evidence.require_wo022p_manifest_contract(
            base_manifest,
            "".join(candidate_lines),
            candidate_bytes + b"\n",
        )


def test_wo022p_scope_and_renderers_are_exact_and_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(review_evidence, "migration_head", lambda: "0007_telemetry_events")
    monkeypatch.setattr(
        review_evidence,
        "canonical_change_evidence",
        lambda _paths, _work_order: {"project_brain_changed": False, "checkpoint_changed": False},
    )
    allowed = sorted(review_evidence.WO022P_G1_ALLOWED_PATHS)
    review_evidence.require_wo022p_g1_scope(
        review_evidence.WO022P_G1_WORK_ORDER,
        review_evidence.WO022P_G1_BASE_SHA,
        allowed,
    )
    with pytest.raises(ValueError, match="exact base"):
        review_evidence.require_wo022p_g1_scope(
            review_evidence.WO022P_G1_WORK_ORDER,
            "f" * 40,
            allowed,
        )
    with pytest.raises(ValueError, match="base branch"):
        review_evidence.require_wo022p_g1_scope(
            review_evidence.WO022P_G1_WORK_ORDER,
            review_evidence.WO022P_G1_BASE_SHA,
            allowed,
            base_branch="release",
        )
    for extra in (
        review_evidence.CHECKPOINT_PATH,
        review_evidence.CANONICAL_MANIFEST_PATH,
        "migrations/versions/0008_next.py",
        "backend/app/control_center_full.py",
        ".github/workflows/ci.yml",
    ):
        with pytest.raises(ValueError, match="exactly the four|canonical Project Brain|migrations"):
            review_evidence.require_wo022p_g1_scope(
                review_evidence.WO022P_G1_WORK_ORDER,
                review_evidence.WO022P_G1_BASE_SHA,
                allowed + [extra],
            )

    body = render_body(
        work_order=review_evidence.WO022P_G1_WORK_ORDER,
        pr_number=90,
        branch="governance/wo022-p-g1",
        base_sha=review_evidence.WO022P_G1_BASE_SHA,
        head_sha="a" * 40,
        artifact_name="hive-review-evidence-WO-022-P-G1",
        ruleset_before="21934284",
        ruleset_after="21934284",
        merge_before="squash",
        merge_after="squash",
    )
    assert body.startswith("<!-- HIVE-WORK-ORDER: WO-022-P-G1 -->")
    assert f"<!-- HIVE-AUTHORIZED-BASE: {review_evidence.WO022P_G1_BASE_SHA} -->" in body
    assert "Exatamente quatro arquivos" in body
    assert "control-center-full-v1" in body
    assert "a870275b3ad738b789e30169d5b1fac00e2e4ae3" in body
    assert "WO-024-P" in body
    assert "WO-022-P-G1 READY FOR SOL AUDIT" in body
    promotion = render_body(
        work_order=review_evidence.WO022P_WORK_ORDER,
        pr_number=91,
        branch="governance/wo022-p",
        base_sha="b" * 40,
        head_sha="c" * 40,
        artifact_name="hive-review-evidence-WO-022-P",
        ruleset_before="21934284",
        ruleset_after="21934284",
        merge_before="squash",
        merge_after="squash",
    )
    assert promotion.startswith("<!-- HIVE-WORK-ORDER: WO-022-P -->")
    assert "WO-022-P READY FOR SOL AUDIT" in promotion
    assert "FULL CONTROL CENTER APPROVED / V0.1 IMPLEMENTATION ACTIVE" in promotion
    assert "HIVE V0.1 completo" in promotion
    for work_order in (review_evidence.WO022P_G1_WORK_ORDER, review_evidence.WO022P_WORK_ORDER):
        with pytest.raises(ValueError, match="40-hex exact HEAD"):
            render_body(
                work_order=work_order,
                pr_number=90,
                branch="governance/wo022-p",
                base_sha=review_evidence.WO022P_G1_BASE_SHA
                if work_order == review_evidence.WO022P_G1_WORK_ORDER
                else "b" * 40,
                head_sha="not-a-sha",
                artifact_name="hive-review-evidence",
                ruleset_before="21934284",
                ruleset_after="21934284",
                merge_before="squash",
                merge_after="squash",
            )


def approved_wo022_lineage_sources_fixture() -> dict[str, Any]:
    head = review_evidence.WO022_APPROVED_PRODUCT_HEAD
    squash = review_evidence.WO022_APPROVED_SQUASH_MERGE_SHA
    return {
        "product_pr": {
            "number": review_evidence.WO022_APPROVED_PRODUCT_PR,
            "state": "closed",
            "merged": True,
            "merge_commit_sha": squash,
            "base": {"ref": "main", "sha": review_evidence.WO022_APPROVED_PRODUCT_BASE_SHA},
            "head": {"sha": head},
            "body": "<!-- HIVE-WORK-ORDER: WO-022 -->\n\nWO-022 Full HIVE Control Center.",
        },
        "product_reviews": [
            {
                "id": review_evidence.WO022_APPROVED_SOL_REVIEW_ID,
                "state": "COMMENTED",
                "commit_id": head,
                "body": f"Verdict: APPROVED. Merge authorization is limited to {head}.",
            }
        ],
        "merge_commit": {
            "sha": squash,
            "parents": [{"sha": review_evidence.WO022_APPROVED_PRODUCT_BASE_SHA}],
        },
        "post_merge_run": {
            "id": review_evidence.WO022_APPROVED_POST_MERGE_CI_RUN,
            "event": "push",
            "head_sha": squash,
            "status": "completed",
            "conclusion": "success",
        },
        "post_merge_jobs": [
            {"name": "Validate", "status": "completed", "conclusion": "success"},
            {"name": "Integration health", "status": "completed", "conclusion": "success"},
            {"name": "Review Evidence", "status": "completed", "conclusion": "skipped"},
        ],
        "prior_review_comments": [
            {
                "body": "\n".join(
                    [
                        "<!-- hive-review-evidence:WO-022 -->",
                        f"- Exact HEAD SHA: `{head}`",
                        "- Backend tests: `606 passed, 0 failed, 0 skipped`",
                        "- Dashboard tests: `34 passed, 0 failed`",
                        "- Validate result: **PASS**",
                        "- Integration health result: **PASS**",
                        "- Review Evidence result: **PASS**",
                        "- Full Control Center evidence: `PASS`; version `control-center-full-v1`",
                        "- Migration head: `0007_telemetry_events`",
                        "- Canonical verifier: **PASS**",
                        "- Canonical changes: project_brain_changed `False`, "
                        "checkpoint_changed `False`, authorized paths `none`",
                        "- leaks/calls `0/0/0/0/0`",
                    ]
                )
            }
        ],
    }


def test_wo022_approved_lineage_and_promotion_pair_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources = approved_wo022_lineage_sources_fixture()
    result = review_evidence.verify_wo022_approved_lineage(sources)
    review_evidence.require_wo022_approved_lineage_result(result)
    statement = review_evidence.wo022_approved_lineage_statement(result)
    assert review_evidence.parse_wo022_approved_lineage_statement(statement) == result
    assert (
        review_evidence.parse_wo022_approved_lineage_statement(statement)["prior_backend_passed"]
        == review_evidence.WO022_APPROVED_BACKEND_PASSED
    )

    mutations: tuple[Callable[[dict[str, Any]], object], ...] = (
        lambda value: value["product_pr"].update(number=85),
        lambda value: value["product_reviews"].__setitem__(
            0, {**value["product_reviews"][0], "id": 1}
        ),
        lambda value: value["post_merge_run"].update(conclusion="failure"),
        lambda value: value["merge_commit"].update(parents=[{"sha": "d" * 40}]),
        lambda value: value["prior_review_comments"].__setitem__(
            0,
            {"body": value["prior_review_comments"][0]["body"].replace("606 passed", "605 passed")},
        ),
    )
    for mutate in mutations:
        broken = json.loads(json.dumps(sources))
        mutate(broken)
        with pytest.raises(ValueError, match="WO-022"):
            review_evidence.verify_wo022_approved_lineage(broken)

    assert (
        review_evidence.approved_lineage_definition("control_center_full_approved_lineage")[
            "additionalProperties"
        ]
        is False
    )
    with pytest.raises(ValueError, match="closed contract"):
        review_evidence.require_wo022_approved_lineage_result({**result, "extra": True})

    monkeypatch.setattr(review_evidence, "migration_head", lambda: "0007_telemetry_events")
    governance = {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}}
    integration = {"control_center_full": control_center_full_evidence_fixture()}
    for promotion_work_order in (
        review_evidence.WO022P_G1_WORK_ORDER,
        review_evidence.WO022P_WORK_ORDER,
    ):
        review_evidence.require_wo022_full_control_center_evidence(
            promotion_work_order,
            integration,
            "0007_telemetry_events",
        )
    with pytest.raises(ValueError, match="must not claim future Full Control Center"):
        review_evidence.require_wo022_full_control_center_evidence(
            review_evidence.WO022_G1_WORK_ORDER,
            integration,
            "0007_telemetry_events",
        )
    with pytest.raises(ValueError, match="missing mandatory Full Control Center"):
        review_evidence.require_wo022_full_control_center_evidence(
            review_evidence.WO022P_G1_WORK_ORDER,
            {},
            "0007_telemetry_events",
        )
    g1 = review_evidence.verify_wo022p_g1_governance_contract(
        review_evidence.WO022P_G1_WORK_ORDER,
        review_evidence.WO022P_G1_BASE_SHA,
        sorted(review_evidence.WO022P_G1_ALLOWED_PATHS),
        {"project_brain_changed": False, "checkpoint_changed": False, "authorized_paths": []},
        governance,
        integration,
        "0007_telemetry_events",
        result,
    )
    assert g1 is not None
    assert "active_promotions=WO-022-P-G1,WO-022-P" in g1
    assert "full_control_center_evidence=PASS" in g1
    assert "historical_WO-021-P-G1_WO-021-P=REJECTED" in g1
    assert "unknown_WO-025-P_WO-999-P=REJECTED" in g1
    assert "checkpoint_promotion=False" in g1
    with pytest.raises(ValueError, match="approved product lineage"):
        review_evidence.verify_wo022p_g1_governance_contract(
            review_evidence.WO022P_G1_WORK_ORDER,
            review_evidence.WO022P_G1_BASE_SHA,
            sorted(review_evidence.WO022P_G1_ALLOWED_PATHS),
            {"project_brain_changed": False, "checkpoint_changed": False, "authorized_paths": []},
            governance,
            integration,
            "0007_telemetry_events",
            None,
        )
    with pytest.raises(ValueError, match="passing Full Control Center"):
        review_evidence.verify_wo022p_g1_governance_contract(
            review_evidence.WO022P_G1_WORK_ORDER,
            review_evidence.WO022P_G1_BASE_SHA,
            sorted(review_evidence.WO022P_G1_ALLOWED_PATHS),
            {"project_brain_changed": False, "checkpoint_changed": False, "authorized_paths": []},
            governance,
            {"control_center_full": {**integration["control_center_full"], "status": "FAIL"}},
            "0007_telemetry_events",
            result,
        )

    promotion = review_evidence.verify_wo022p_governance_contract(
        review_evidence.WO022P_WORK_ORDER,
        "b" * 40,
        sorted(review_evidence.WO022P_PROMOTION_ALLOWED_PATHS),
        {
            "project_brain_changed": True,
            "checkpoint_changed": True,
            "authorized_paths": sorted(review_evidence.WO022P_PROMOTION_ALLOWED_PATHS),
        },
        governance,
        integration,
        "0007_telemetry_events",
        result,
    )
    assert promotion is not None
    assert "checkpoint_promotion=True" in promotion
    assert "full_v01_complete_claimed=False" in promotion
    with pytest.raises(ValueError, match="checkpoint and manifest canonical changes"):
        review_evidence.verify_wo022p_governance_contract(
            review_evidence.WO022P_WORK_ORDER,
            "b" * 40,
            sorted(review_evidence.WO022P_PROMOTION_ALLOWED_PATHS),
            {"project_brain_changed": True, "checkpoint_changed": True, "authorized_paths": []},
            governance,
            integration,
            "0007_telemetry_events",
            result,
        )

    assert frozenset(
        {review_evidence.WO022P_G1_WORK_ORDER, review_evidence.WO022P_WORK_ORDER}
    ).issubset(review_evidence.HISTORICAL_CHECKPOINT_PROMOTION_WORK_ORDERS)
    assert {
        review_evidence.WO021P_G1_WORK_ORDER,
        review_evidence.WO021P_WORK_ORDER,
    }.issubset(review_evidence.HISTORICAL_CHECKPOINT_PROMOTION_WORK_ORDERS)
    assert (
        AUTHORIZED_BASE_BY_WORK_ORDER[review_evidence.WO022P_G1_WORK_ORDER]
        == review_evidence.WO022P_G1_BASE_SHA
    )


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
    with pytest.raises(ValueError, match="unsupported future"):
        render_body(work_order="WO-999", **common)
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


def test_hive_rel_001_marker_is_bounded_and_registered() -> None:
    marker = f"<!-- HIVE-WORK-ORDER: {HIVE_REL_001_WORK_ORDER} -->"
    assert parse_work_order_marker(marker) == HIVE_REL_001_WORK_ORDER
    require_supported_work_order(HIVE_REL_001_WORK_ORDER)
    require_current_work_order_authorization(HIVE_REL_001_WORK_ORDER)
    assert HIVE_REL_001_WORK_ORDER in review_evidence.AUTHORIZED_BASE_MARKER_WORK_ORDERS
    assert (
        parse_authorized_base_marker(f"<!-- HIVE-AUTHORIZED-BASE: {HIVE_REL_001_BASE_SHA} -->")
        == HIVE_REL_001_BASE_SHA
    )
    require_supported_work_order(HIVE_REL_002_WORK_ORDER)
    require_current_work_order_authorization(HIVE_REL_002_WORK_ORDER)
    require_supported_work_order(HIVE_REL_003_WORK_ORDER)
    require_current_work_order_authorization(HIVE_REL_003_WORK_ORDER)
    require_supported_work_order(HIVE_REL_004_WORK_ORDER)
    require_current_work_order_authorization(HIVE_REL_004_WORK_ORDER)
    require_supported_work_order(HIVE_REL_005_WORK_ORDER)
    require_current_work_order_authorization(HIVE_REL_005_WORK_ORDER)
    assert HIVE_REL_005_WORK_ORDER in review_evidence.AUTHORIZED_BASE_MARKER_WORK_ORDERS
    require_supported_work_order(HIVE_REL_006_WORK_ORDER)
    require_current_work_order_authorization(HIVE_REL_006_WORK_ORDER)
    assert HIVE_REL_006_WORK_ORDER in review_evidence.AUTHORIZED_BASE_MARKER_WORK_ORDERS
    require_supported_work_order(HIVE_REL_007_WORK_ORDER)
    require_current_work_order_authorization(HIVE_REL_007_WORK_ORDER)
    assert HIVE_REL_007_WORK_ORDER in review_evidence.AUTHORIZED_BASE_MARKER_WORK_ORDERS
    require_supported_work_order(HIVE_REL_008_WORK_ORDER)
    require_current_work_order_authorization(HIVE_REL_008_WORK_ORDER)
    assert HIVE_REL_008_WORK_ORDER in review_evidence.AUTHORIZED_BASE_MARKER_WORK_ORDERS
    with pytest.raises(ValueError, match="unsupported release-engineering"):
        require_supported_work_order("HIVE-REL-009")
    with pytest.raises(ValueError, match="unsupported release-engineering"):
        require_supported_work_order("HIVE-REL-999")
    with pytest.raises(ValueError, match="invalid or unbounded"):
        parse_work_order_marker("<!-- HIVE-WORK-ORDER: HIVE-OTHER-001 -->")


def test_hive_rel_001_scope_requires_exact_base_authorization_and_registered_paths() -> None:
    allowed_paths = sorted(HIVE_REL_001_ALLOWED_EXACT_PATHS)
    require_hive_rel_001_scope(
        HIVE_REL_001_WORK_ORDER,
        HIVE_REL_001_BASE_SHA,
        allowed_paths,
        authorized_base_sha=HIVE_REL_001_BASE_SHA,
    )
    require_hive_rel_001_scope(
        HIVE_REL_001_WORK_ORDER,
        HIVE_REL_001_BASE_SHA,
        [
            "docs/VERSIONING.md",
            ".github/workflows/codeql.yml",
            ".engineering/release/HIVE-V1.0.0-RELEASE-CANDIDATE.json",
            "backend/tests/test_verify_release_metadata.py",
        ],
        authorized_base_sha=HIVE_REL_001_BASE_SHA,
    )
    require_hive_rel_001_scope(
        "WO-024-P",
        "f" * 40,
        ["backend/app/main.py"],
        authorized_base_sha=None,
    )
    with pytest.raises(ValueError, match="protected main base branch"):
        require_hive_rel_001_scope(
            HIVE_REL_001_WORK_ORDER,
            HIVE_REL_001_BASE_SHA,
            allowed_paths,
            base_branch="release",
            authorized_base_sha=HIVE_REL_001_BASE_SHA,
        )
    with pytest.raises(ValueError, match="exact base"):
        require_hive_rel_001_scope(
            HIVE_REL_001_WORK_ORDER,
            "a" * 40,
            allowed_paths,
            authorized_base_sha=HIVE_REL_001_BASE_SHA,
        )
    with pytest.raises(ValueError, match="authorized-base marker"):
        require_hive_rel_001_scope(
            HIVE_REL_001_WORK_ORDER,
            HIVE_REL_001_BASE_SHA,
            allowed_paths,
            authorized_base_sha=None,
        )
    with pytest.raises(ValueError, match="registered release scope"):
        require_hive_rel_001_scope(
            HIVE_REL_001_WORK_ORDER,
            HIVE_REL_001_BASE_SHA,
            [*allowed_paths, "backend/app/main.py"],
            authorized_base_sha=HIVE_REL_001_BASE_SHA,
        )
    with pytest.raises(ValueError, match="immutable or local-only"):
        require_hive_rel_001_scope(
            HIVE_REL_001_WORK_ORDER,
            HIVE_REL_001_BASE_SHA,
            ["docs/project-brain/13-CHECKPOINT.md"],
            authorized_base_sha=HIVE_REL_001_BASE_SHA,
        )
    with pytest.raises(ValueError, match="immutable or local-only"):
        require_hive_rel_001_scope(
            HIVE_REL_001_WORK_ORDER,
            HIVE_REL_001_BASE_SHA,
            ["docs/releases/v0.0.1-bootstrap.md"],
            authorized_base_sha=HIVE_REL_001_BASE_SHA,
        )
    with pytest.raises(ValueError, match="non-empty change set"):
        require_hive_rel_001_scope(
            HIVE_REL_001_WORK_ORDER,
            HIVE_REL_001_BASE_SHA,
            [],
            authorized_base_sha=HIVE_REL_001_BASE_SHA,
        )


def test_hive_rel_002_marker_is_registered_and_requires_authorized_base() -> None:
    marker = f"<!-- HIVE-WORK-ORDER: {HIVE_REL_002_WORK_ORDER} -->"
    assert parse_work_order_marker(marker) == HIVE_REL_002_WORK_ORDER
    require_supported_work_order(HIVE_REL_002_WORK_ORDER)
    require_current_work_order_authorization(HIVE_REL_002_WORK_ORDER)
    assert HIVE_REL_002_WORK_ORDER in review_evidence.AUTHORIZED_BASE_MARKER_WORK_ORDERS
    body = (
        f"<!-- HIVE-WORK-ORDER: {HIVE_REL_002_WORK_ORDER} -->\n"
        f"<!-- HIVE-AUTHORIZED-BASE: {HIVE_REL_002_BASE_SHA} -->\n"
    )
    assert (
        review_evidence.authorized_base_marker_sha(HIVE_REL_002_WORK_ORDER, body)
        == HIVE_REL_002_BASE_SHA
    )


def test_hive_rel_002_scope_is_exact_and_fails_closed() -> None:
    allowed = sorted(HIVE_REL_002_ALLOWED_PATHS)
    require_hive_rel_002_scope(
        HIVE_REL_002_WORK_ORDER,
        HIVE_REL_002_BASE_SHA,
        allowed,
        authorized_base_sha=HIVE_REL_002_BASE_SHA,
    )
    require_hive_rel_002_scope(
        HIVE_REL_001_WORK_ORDER,
        HIVE_REL_001_BASE_SHA,
        ["README.md"],
        authorized_base_sha=HIVE_REL_001_BASE_SHA,
    )
    with pytest.raises(ValueError, match="protected main"):
        require_hive_rel_002_scope(
            HIVE_REL_002_WORK_ORDER,
            HIVE_REL_002_BASE_SHA,
            allowed,
            base_branch="release",
            authorized_base_sha=HIVE_REL_002_BASE_SHA,
        )
    with pytest.raises(ValueError, match="exact base"):
        require_hive_rel_002_scope(
            HIVE_REL_002_WORK_ORDER,
            "a" * 40,
            allowed,
            authorized_base_sha=HIVE_REL_002_BASE_SHA,
        )
    with pytest.raises(ValueError, match="authorized-base marker"):
        require_hive_rel_002_scope(
            HIVE_REL_002_WORK_ORDER,
            HIVE_REL_002_BASE_SHA,
            allowed,
            authorized_base_sha=None,
        )
    with pytest.raises(ValueError, match="bounded publisher scope"):
        require_hive_rel_002_scope(
            HIVE_REL_002_WORK_ORDER,
            HIVE_REL_002_BASE_SHA,
            [*allowed, "requirements.txt"],
            authorized_base_sha=HIVE_REL_002_BASE_SHA,
        )
    with pytest.raises(ValueError, match="bounded publisher scope"):
        require_hive_rel_002_scope(
            HIVE_REL_002_WORK_ORDER,
            HIVE_REL_002_BASE_SHA,
            [*allowed, "docs/project-brain/13-CHECKPOINT.md"],
            authorized_base_sha=HIVE_REL_002_BASE_SHA,
        )
    with pytest.raises(ValueError, match="non-empty"):
        require_hive_rel_002_scope(
            HIVE_REL_002_WORK_ORDER,
            HIVE_REL_002_BASE_SHA,
            [],
            authorized_base_sha=HIVE_REL_002_BASE_SHA,
        )


def test_hive_rel_003_marker_is_registered_and_requires_authorized_base() -> None:
    marker = f"<!-- HIVE-WORK-ORDER: {HIVE_REL_003_WORK_ORDER} -->"
    assert parse_work_order_marker(marker) == HIVE_REL_003_WORK_ORDER
    require_supported_work_order(HIVE_REL_003_WORK_ORDER)
    require_current_work_order_authorization(HIVE_REL_003_WORK_ORDER)
    assert HIVE_REL_003_WORK_ORDER in review_evidence.AUTHORIZED_BASE_MARKER_WORK_ORDERS
    body = (
        f"<!-- HIVE-WORK-ORDER: {HIVE_REL_003_WORK_ORDER} -->\n"
        f"<!-- HIVE-AUTHORIZED-BASE: {HIVE_REL_003_BASE_SHA} -->\n"
    )
    assert (
        review_evidence.authorized_base_marker_sha(HIVE_REL_003_WORK_ORDER, body)
        == HIVE_REL_003_BASE_SHA
    )


def test_hive_rel_003_scope_is_exact_and_fails_closed() -> None:
    allowed = sorted(HIVE_REL_003_ALLOWED_PATHS)
    require_hive_rel_003_scope(
        HIVE_REL_003_WORK_ORDER,
        HIVE_REL_003_BASE_SHA,
        allowed,
        authorized_base_sha=HIVE_REL_003_BASE_SHA,
    )
    require_hive_rel_003_scope(
        HIVE_REL_002_WORK_ORDER,
        HIVE_REL_002_BASE_SHA,
        [".github/workflows/release-publisher.yml"],
        authorized_base_sha=HIVE_REL_002_BASE_SHA,
    )
    with pytest.raises(ValueError, match="protected main"):
        require_hive_rel_003_scope(
            HIVE_REL_003_WORK_ORDER,
            HIVE_REL_003_BASE_SHA,
            allowed,
            base_branch="release",
            authorized_base_sha=HIVE_REL_003_BASE_SHA,
        )
    with pytest.raises(ValueError, match="exact base"):
        require_hive_rel_003_scope(
            HIVE_REL_003_WORK_ORDER,
            "a" * 40,
            allowed,
            authorized_base_sha=HIVE_REL_003_BASE_SHA,
        )
    with pytest.raises(ValueError, match="authorized-base marker"):
        require_hive_rel_003_scope(
            HIVE_REL_003_WORK_ORDER,
            HIVE_REL_003_BASE_SHA,
            allowed,
            authorized_base_sha=None,
        )
    with pytest.raises(ValueError, match="bounded correction scope"):
        require_hive_rel_003_scope(
            HIVE_REL_003_WORK_ORDER,
            HIVE_REL_003_BASE_SHA,
            [*allowed, "requirements.txt"],
            authorized_base_sha=HIVE_REL_003_BASE_SHA,
        )
    with pytest.raises(ValueError, match="bounded correction scope"):
        require_hive_rel_003_scope(
            HIVE_REL_003_WORK_ORDER,
            HIVE_REL_003_BASE_SHA,
            [*allowed, "docs/project-brain/13-CHECKPOINT.md"],
            authorized_base_sha=HIVE_REL_003_BASE_SHA,
        )
    with pytest.raises(ValueError, match="non-empty"):
        require_hive_rel_003_scope(
            HIVE_REL_003_WORK_ORDER,
            HIVE_REL_003_BASE_SHA,
            [],
            authorized_base_sha=HIVE_REL_003_BASE_SHA,
        )


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


def approved_wo021_lineage_sources_fixture() -> dict[str, object]:
    review_body = (
        "Sol audit — WO-021-C1\n"
        "VERDICT: APPROVED.\n"
        f"Audited exact HEAD: {review_evidence.WO021_APPROVED_PRODUCT_HEAD}\n"
        "Authorized base: 2ccbf09c193ba30e78d768bb32a4e78a4f209812"
    )
    prior_body = (
        "<!-- hive-review-evidence:WO-021 -->\n"
        f"Exact HEAD SHA: `{review_evidence.WO021_APPROVED_PRODUCT_HEAD}`\n"
        "Base SHA: `2ccbf09c193ba30e78d768bb32a4e78a4f209812`\n"
        "PR state: **READY**\n"
        "Canonical changes: project_brain_changed `False`, checkpoint_changed `False`, "
        "authorized paths `none`\n"
        "Validate result: **PASS**\n"
        "Integration health result: **PASS**\n"
        "Review Evidence result: **PASS**\n"
        "Migration head: `0007_telemetry_events`\n"
        "Backend tests: `568 passed, 0 failed, 0 skipped`\n"
        "Dashboard tests: `30 passed, 0 failed`\n"
        "Control Center Metrics evidence: `PASS`; version `control-center-metrics-v1`, "
        "PostgreSQL/Redis canonicality `True/False`, leaks/calls `0/0/0/0/0`"
    )
    return {
        "product_pr": {
            "number": 82,
            "state": "closed",
            "merged": True,
            "base": {
                "ref": "main",
                "sha": review_evidence.WO021_APPROVED_PRODUCT_BASE_SHA,
            },
            "head": {"sha": review_evidence.WO021_APPROVED_PRODUCT_HEAD},
            "merge_commit_sha": review_evidence.WO021_APPROVED_SQUASH_MERGE_SHA,
            "body": "<!-- HIVE-WORK-ORDER: WO-021 -->",
        },
        "product_reviews": [
            {
                "id": review_evidence.WO021_APPROVED_SOL_REVIEW_ID,
                "state": "COMMENTED",
                "commit_id": review_evidence.WO021_APPROVED_PRODUCT_HEAD,
                "body": review_body,
            }
        ],
        "merge_commit": {
            "sha": review_evidence.WO021_APPROVED_SQUASH_MERGE_SHA,
            "parents": [{"sha": review_evidence.WO021_APPROVED_PRODUCT_BASE_SHA}],
        },
        "post_merge_run": {
            "id": review_evidence.WO021_APPROVED_POST_MERGE_CI_RUN,
            "event": "push",
            "head_sha": review_evidence.WO021_APPROVED_SQUASH_MERGE_SHA,
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
    require_supported_work_order(review_evidence.WO017P_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO017P_WORK_ORDER)
    require_supported_work_order(review_evidence.WO018P_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO018P_WORK_ORDER)
    require_supported_work_order(review_evidence.WO019P_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO019P_WORK_ORDER)
    require_supported_work_order(review_evidence.WO020P_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO020P_WORK_ORDER)
    require_supported_work_order(review_evidence.WO021P_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO021P_WORK_ORDER)
    require_supported_work_order(review_evidence.WO022P_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO022P_WORK_ORDER)
    require_supported_work_order(review_evidence.WO023P_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO023P_WORK_ORDER)
    require_supported_work_order(review_evidence.WO024_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO024_WORK_ORDER)
    require_supported_work_order(review_evidence.WO024P_WORK_ORDER)
    # WO-025-P became registered in WO-025-G3, so the unregistered-promotion negative
    # moves to the next identifier of the same class.
    require_supported_work_order("WO-025-P")
    with pytest.raises(ValueError, match="unsupported checkpoint-promotion"):
        require_supported_work_order("WO-026-P")


def test_current_checkpoint_promotion_authorization_separates_history() -> None:
    with pytest.raises(ValueError, match="historical checkpoint-promotion"):
        require_current_work_order_authorization(review_evidence.WO020P_G1_WORK_ORDER)
    with pytest.raises(ValueError, match="historical checkpoint-promotion"):
        require_current_work_order_authorization(review_evidence.WO020P_WORK_ORDER)
    with pytest.raises(ValueError, match="historical checkpoint-promotion"):
        require_current_work_order_authorization(review_evidence.WO021P_G1_WORK_ORDER)
    with pytest.raises(ValueError, match="historical checkpoint-promotion"):
        require_current_work_order_authorization(review_evidence.WO021P_WORK_ORDER)
    with pytest.raises(ValueError, match="historical checkpoint-promotion"):
        require_current_work_order_authorization(review_evidence.WO022P_G1_WORK_ORDER)
    with pytest.raises(ValueError, match="historical checkpoint-promotion"):
        require_current_work_order_authorization(review_evidence.WO022P_WORK_ORDER)
    for historical_current in (
        review_evidence.WO023P_G1_WORK_ORDER,
        review_evidence.WO023P_WORK_ORDER,
        review_evidence.WO023P_G1_C1_WORK_ORDER,
    ):
        with pytest.raises(ValueError, match="historical checkpoint-promotion"):
            require_current_work_order_authorization(historical_current)
    require_current_work_order_authorization(review_evidence.WO024_G1_WORK_ORDER)
    require_current_work_order_authorization(review_evidence.WO024_WORK_ORDER)
    require_current_work_order_authorization(review_evidence.WO024P_WORK_ORDER)
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
        review_evidence.WO017P_G1_WORK_ORDER,
        review_evidence.WO017P_WORK_ORDER,
        review_evidence.WO018P_G1_WORK_ORDER,
        review_evidence.WO018P_WORK_ORDER,
        review_evidence.WO019P_G1_WORK_ORDER,
        review_evidence.WO019P_WORK_ORDER,
    ):
        with pytest.raises(ValueError, match="historical checkpoint-promotion"):
            require_current_work_order_authorization(historical)
    # WO-025-G3 separates promotion history from the current frontier, so WO-025-P is the
    # registered current promotion and genuinely unregistered promotions keep the unsupported
    # rejection.
    require_current_work_order_authorization("WO-025-P")
    for unknown in ("WO-026-P", "WO-999-P"):
        with pytest.raises(ValueError, match="unsupported checkpoint-promotion"):
            require_current_work_order_authorization(unknown)


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


def test_wo022_registration_and_scopes_are_exact_and_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require_supported_work_order(review_evidence.WO022_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO022_WORK_ORDER)
    require_supported_work_order(review_evidence.WO022P_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO022P_WORK_ORDER)
    require_supported_work_order(review_evidence.WO023_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO023_WORK_ORDER)
    require_supported_work_order(review_evidence.WO023P_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO023P_WORK_ORDER)
    require_supported_work_order(review_evidence.WO024_G1_WORK_ORDER)
    require_supported_work_order(review_evidence.WO024_WORK_ORDER)
    require_supported_work_order(review_evidence.WO024P_WORK_ORDER)
    # WO-025-P became registered in WO-025-G3, so the unregistered-promotion negative
    # moves to the next identifier of the same class.
    require_supported_work_order("WO-025-P")
    with pytest.raises(ValueError, match="unsupported checkpoint-promotion"):
        require_supported_work_order("WO-026-P")
    with pytest.raises(ValueError, match="unsupported future"):
        require_supported_work_order("WO-032")

    monkeypatch.setattr(
        review_evidence,
        "migration_head",
        lambda: review_evidence.CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD,
    )
    g1_paths = sorted(review_evidence.WO022_G1_ALLOWED_PATHS)
    review_evidence.require_wo022_g1_scope(
        review_evidence.WO022_G1_WORK_ORDER,
        review_evidence.WO022_G1_BASE_SHA,
        g1_paths,
    )
    with pytest.raises(ValueError, match="exact base"):
        review_evidence.require_wo022_g1_scope(
            review_evidence.WO022_G1_WORK_ORDER,
            "a" * 40,
            g1_paths,
        )
    with pytest.raises(ValueError, match="exactly the four"):
        review_evidence.require_wo022_g1_scope(
            review_evidence.WO022_G1_WORK_ORDER,
            review_evidence.WO022_G1_BASE_SHA,
            g1_paths[:-1],
        )
    with pytest.raises(ValueError, match="migration head"):
        monkeypatch.setattr(review_evidence, "migration_head", lambda: "0008_future")
        review_evidence.require_wo022_g1_scope(
            review_evidence.WO022_G1_WORK_ORDER,
            review_evidence.WO022_G1_BASE_SHA,
            g1_paths,
        )

    current = "b" * 40
    monkeypatch.setattr(
        review_evidence,
        "git_value",
        lambda *args, fallback="": current if args == ("rev-parse", "origin/main") else fallback,
    )
    monkeypatch.setattr(
        review_evidence,
        "git_blob_bytes",
        lambda _revision, _path: b"merged WO-022-G1 governance support",
    )
    review_evidence.require_wo022_scope(
        review_evidence.WO022_WORK_ORDER,
        current,
        ["dashboard/src/ControlCenter.tsx"],
        enforce_current_main=True,
    )
    with pytest.raises(ValueError, match="cannot change migrations"):
        review_evidence.require_wo022_scope(
            review_evidence.WO022_WORK_ORDER,
            current,
            ["migrations/versions/0008_full_control_center.py"],
        )


def test_wo022_full_control_center_contract_is_closed_and_schema_aligned() -> None:
    evidence = control_center_full_evidence_fixture()
    review_evidence.require_wo022_full_control_center_evidence(
        review_evidence.WO022_WORK_ORDER,
        {"control_center_full": evidence},
        review_evidence.CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD,
    )
    with pytest.raises(ValueError, match="closed contract"):
        review_evidence.require_wo022_full_control_center_evidence(
            review_evidence.WO022_WORK_ORDER,
            {"control_center_full": {**evidence, "invented": True}},
            review_evidence.CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD,
        )
    for field, value, message in (
        ("implemented_charts", ["unknown-chart"], "closed implemented_charts"),
        ("implemented_alerts", [], "closed implemented_alerts"),
        ("full_v01_complete_claimed", True, "bounded negative"),
        ("api_path", "C:/private/control_center.py", "sanitized relative api_path"),
        ("history_max_points", 513, "bounded history"),
    ):
        with pytest.raises(ValueError, match=message):
            review_evidence.require_wo022_full_control_center_evidence(
                review_evidence.WO022_WORK_ORDER,
                {"control_center_full": {**evidence, field: value}},
                review_evidence.CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD,
            )
    with pytest.raises(ValueError, match="must not claim"):
        review_evidence.require_wo022_full_control_center_evidence(
            review_evidence.WO022_G1_WORK_ORDER,
            {"control_center_full": evidence},
            review_evidence.CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD,
        )

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema["$defs"]["control_center_full_evidence"])
    for field in (
        "implemented_project_capabilities",
        "implemented_charts",
        "implemented_alerts",
        "implemented_health_capabilities",
    ):
        candidate = {**evidence, field: list(reversed(cast(list[str], evidence[field])))}
        assert validator.is_valid(candidate)
        review_evidence.require_wo022_full_control_center_evidence(
            review_evidence.WO022_WORK_ORDER,
            {"control_center_full": candidate},
            review_evidence.CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD,
        )
        invalid = {**candidate, field: [*cast(list[str], candidate[field]), "unknown"]}
        assert not validator.is_valid(invalid)
        with pytest.raises(ValueError, match=f"closed {field}"):
            review_evidence.require_wo022_full_control_center_evidence(
                review_evidence.WO022_WORK_ORDER,
                {"control_center_full": invalid},
                review_evidence.CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD,
            )


def test_wo022_schema_and_renderers_are_explicit() -> None:
    manifest = evidence_fixture()
    manifest["work_order"] = review_evidence.WO022_G1_WORK_ORDER
    manifest["base"] = {"branch": "main", "sha": review_evidence.WO022_G1_BASE_SHA}
    manifest["changed_files"] = {
        "count": len(review_evidence.WO022_G1_ALLOWED_PATHS),
        "paths": sorted(review_evidence.WO022_G1_ALLOWED_PATHS),
    }
    cast(dict[str, object], manifest["migrations"])["head"] = (
        review_evidence.CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD
    )
    governance = cast(dict[str, object], manifest["governance"])
    governance["ruleset_unchanged"] = True
    cast(dict[str, object], governance["pull_request"])["auto_merge_armed"] = False
    canonical = canonical_change_evidence(
        sorted(review_evidence.WO022_G1_ALLOWED_PATHS), review_evidence.WO022_G1_WORK_ORDER
    )
    evidence = review_evidence.verify_wo022_g1_governance_contract(
        review_evidence.WO022_G1_WORK_ORDER,
        review_evidence.WO022_G1_BASE_SHA,
        sorted(review_evidence.WO022_G1_ALLOWED_PATHS),
        canonical,
        governance,
        cast(dict[str, object], cast(dict[str, object], manifest["evidence"])["integration"]),
        review_evidence.CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD,
    )
    assert evidence is not None
    assert "future_WO-022_registered=PASS" in evidence
    assert "control-center-full-v1_fail_closed=PASS" in evidence
    cast(list[object], manifest["negative_scope"]).append(
        f"WO-022-G1 governance evidence: {evidence}"
    )
    validate_manifest(manifest)

    common: dict[str, Any] = {
        "pr_number": 85,
        "branch": "governance/wo022-g1-full-control-center-review-evidence",
        "base_sha": review_evidence.WO022_G1_BASE_SHA,
        "head_sha": "b" * 40,
        "artifact_name": "hive-review-evidence-WO-022-G1-b",
        "ruleset_before": "unchanged",
        "ruleset_after": "unchanged",
        "merge_before": "unarmed",
        "merge_after": "unarmed",
    }
    g1 = render_body(work_order=review_evidence.WO022_G1_WORK_ORDER, **common)
    assert g1.startswith("<!-- HIVE-WORK-ORDER: WO-022-G1 -->")
    assert g1.splitlines()[1] == (
        f"<!-- HIVE-AUTHORIZED-BASE: {review_evidence.WO022_G1_BASE_SHA} -->"
    )
    assert "control-center-full-v1" in g1
    assert "WO-022-G1 READY FOR SOL AUDIT" in g1
    assert "HIVE V0.1 completo" in g1
    product = render_body(work_order=review_evidence.WO022_WORK_ORDER, **common)
    assert product.startswith("<!-- HIVE-WORK-ORDER: WO-022 -->")
    assert "WO-022 READY FOR SOL AUDIT" in product
    assert "C:\\Users" not in product
    assert "D:\\Projeto Codexx" not in product
    with pytest.raises(ValueError, match="authorized base"):
        render_body(
            work_order=review_evidence.WO022_G1_WORK_ORDER,
            **{**common, "base_sha": "a" * 40},
        )


def approved_wo023_lineage_sources_fixture() -> dict[str, Any]:
    head = review_evidence.WO023_APPROVED_PRODUCT_HEAD
    squash = review_evidence.WO023_APPROVED_SQUASH_MERGE_SHA
    return {
        "product_pr": {
            "number": review_evidence.WO023_APPROVED_PRODUCT_PR,
            "state": "closed",
            "merged": True,
            "merge_commit_sha": squash,
            "base": {"ref": "main", "sha": review_evidence.WO023_APPROVED_PRODUCT_BASE_SHA},
            "head": {"sha": head},
            "body": "<!-- HIVE-WORK-ORDER: WO-023 -->\n\nWO-023 comprehensive benchmarks.",
        },
        "product_reviews": [
            {
                "id": review_evidence.WO023_APPROVED_SOL_REVIEW_ID,
                "state": "COMMENTED",
                "commit_id": head,
                "body": (
                    f"SOL EXACT-HEAD AUDIT - WO-023\n\n"
                    f"VERDICT: WO-023 APPROVED on exact HEAD {head}."
                ),
            }
        ],
        "merge_commit": {
            "sha": squash,
            "parents": [{"sha": review_evidence.WO023_APPROVED_PRODUCT_BASE_SHA}],
        },
        "post_merge_run": {
            "id": review_evidence.WO023_APPROVED_POST_MERGE_CI_RUN,
            "event": "push",
            "head_sha": squash,
            "status": "completed",
            "conclusion": "success",
        },
        "post_merge_jobs": [
            {"name": "Validate", "status": "completed", "conclusion": "success"},
            {"name": "Integration health", "status": "completed", "conclusion": "success"},
            {"name": "Review Evidence", "status": "completed", "conclusion": "skipped"},
        ],
        "prior_review_comments": [
            {
                "body": "\n".join(
                    [
                        "<!-- hive-review-evidence:WO-023 -->",
                        f"- Exact HEAD SHA: `{head}`",
                        "- Backend tests: `638 passed, 0 failed, 0 skipped`",
                        "- Dashboard tests: `34 passed, 0 failed`",
                        "- Validate result: **PASS**",
                        "- Integration health result: **PASS**",
                        "- Review Evidence result: **PASS**",
                        "- Migration head: `0007_telemetry_events`",
                        "- Canonical verifier: **PASS**",
                        "- Canonical changes: project_brain_changed `False`, "
                        "checkpoint_changed `False`, authorized paths `none`",
                        "- leaks/calls `0/0/0/0/0`",
                    ]
                )
            }
        ],
    }


def wo023p_checkpoint_fixture(*, include_evidence: bool = True) -> tuple[str, str]:
    base = review_evidence.git_blob_bytes(
        review_evidence.WO023P_G1_BASE_SHA,
        review_evidence.CHECKPOINT_PATH,
    ).decode("utf-8")
    base_sections = review_evidence.checkpoint_sections(base)
    candidate = replace_checkpoint_section(
        base,
        "STATUS",
        review_evidence.EXPECTED_WO023P_STATUS,
    )
    candidate = replace_checkpoint_section(
        candidate,
        "IN PROGRESS",
        f"- {review_evidence.EXPECTED_WO023P_IN_PROGRESS}",
    )
    candidate = replace_checkpoint_section(
        candidate,
        "BLOCKERS",
        review_evidence.EXPECTED_WO023P_BLOCKERS,
    )
    candidate = replace_checkpoint_section(
        candidate,
        "NEXT STEP",
        review_evidence.EXPECTED_WO023P_NEXT_STEP,
    )
    if include_evidence:
        completed = review_evidence.checkpoint_bullets(base_sections, "COMPLETED")
        candidate = replace_checkpoint_section(
            candidate,
            "COMPLETED",
            "\n".join(
                f"- {item}"
                for item in completed + list(review_evidence.WO023P_CANONICAL_COMPLETION_BULLETS)
            ),
        )
    pending = [
        item
        for item in review_evidence.checkpoint_bullets(base_sections, "PENDING")
        if item != review_evidence.WO023P_COMPLETED_PENDING_ITEM
    ]
    candidate = replace_checkpoint_section(
        candidate,
        "PENDING",
        "\n".join(f"- {item}" for item in pending),
    )
    return base, candidate


def test_wo023p_checkpoint_semantics_are_closed_and_remove_only_benchmark_pending() -> None:
    base, candidate = wo023p_checkpoint_fixture()

    review_evidence.require_wo023p_checkpoint_semantics(base, candidate)

    candidate_sections = review_evidence.checkpoint_sections(candidate)
    completed = review_evidence.checkpoint_bullets(candidate_sections, "COMPLETED")
    appended = completed[-len(review_evidence.WO023P_CANONICAL_COMPLETION_BULLETS) :]
    assert appended == list(review_evidence.WO023P_CANONICAL_COMPLETION_BULLETS)
    pending = review_evidence.checkpoint_bullets(candidate_sections, "PENDING")
    assert pending == list(review_evidence.WO023P_REQUIRED_RETAINED_PENDING_ITEMS)
    assert review_evidence.WO023P_COMPLETED_PENDING_ITEM not in pending
    assert "stabilization." in pending
    assert review_evidence.WO023P_COMPLETED_PENDING_ITEM in review_evidence.checkpoint_bullets(
        review_evidence.checkpoint_sections(base), "PENDING"
    )

    _, without_evidence = wo023p_checkpoint_fixture(include_evidence=False)
    with pytest.raises(ValueError, match="WO-023-P"):
        review_evidence.require_wo023p_checkpoint_semantics(base, without_evidence)

    bullet_count = len(review_evidence.WO023P_CANONICAL_COMPLETION_BULLETS)
    mutations: tuple[Callable[[str], str], ...] = (
        lambda text: replace_checkpoint_section(
            text, "STATUS", review_evidence.EXPECTED_WO022P_STATUS
        ),
        lambda text: replace_checkpoint_section(text, "STATUS", "HIVE V0.1 COMPLETE"),
        lambda text: replace_checkpoint_section(
            text,
            "NEXT STEP",
            review_evidence.EXPECTED_WO022P_NEXT_STEP,
        ),
        lambda text: replace_checkpoint_section(
            text,
            "IN PROGRESS",
            f"- {review_evidence.EXPECTED_WO022P_IN_PROGRESS}",
        ),
        lambda text: replace_checkpoint_section(
            text,
            "BLOCKERS",
            review_evidence.EXPECTED_WO022P_BLOCKERS,
        ),
        lambda text: replace_checkpoint_section(
            text,
            "COMPLETED",
            "\n".join(
                [
                    f"- {item}"
                    for item in review_evidence.checkpoint_bullets(
                        review_evidence.checkpoint_sections(text), "COMPLETED"
                    )[:-bullet_count]
                ]
                + ["- hive v0.1 is complete."]
            ),
        ),
        lambda text: replace_checkpoint_section(
            text,
            "PENDING",
            f"- {review_evidence.WO023P_COMPLETED_PENDING_ITEM}\n"
            + "\n".join(
                f"- {item}" for item in review_evidence.WO023P_REQUIRED_RETAINED_PENDING_ITEMS
            ),
        ),
        lambda text: replace_checkpoint_section(
            text,
            "PENDING",
            "\n".join(
                f"- {item}"
                for item in reversed(review_evidence.WO023P_REQUIRED_RETAINED_PENDING_ITEMS)
            ),
        ),
        lambda text: replace_checkpoint_section(
            text,
            "PENDING",
            "\n".join(
                f"- {item}"
                for item in (
                    *review_evidence.WO023P_REQUIRED_RETAINED_PENDING_ITEMS,
                    "unrelated promotion.",
                )
            ),
        ),
        lambda text: text.replace(
            "pr #90 with audited head 270929c2e1428335ea9c98337c29a31d5682686d",
            "pr #89 with audited head 270929c2e1428335ea9c98337c29a31d5682686d",
        ),
        lambda text: replace_checkpoint_section(text, "VERSION", "WO-023-P rewrite"),
    )
    for mutate in mutations:
        with pytest.raises(ValueError, match="WO-023-P"):
            review_evidence.require_wo023p_checkpoint_semantics(base, mutate(candidate))


def test_wo023p_manifest_contract_only_changes_checkpoint_hash() -> None:
    manifest_path = review_evidence.ROOT / review_evidence.CANONICAL_MANIFEST_PATH
    base_manifest = manifest_path.read_text(encoding="utf-8")
    _, candidate_checkpoint = wo023p_checkpoint_fixture()
    candidate_bytes = candidate_checkpoint.encode("utf-8")
    digest = hashlib.sha256(candidate_bytes).hexdigest()
    candidate_lines: list[str] = []
    changed = 0
    for line in base_manifest.splitlines(keepends=True):
        stripped = line.strip().split(maxsplit=1)
        if len(stripped) == 2 and stripped[1] == review_evidence.CANONICAL_MANIFEST_CHECKPOINT_NAME:
            prefix = line.index(stripped[0])
            line = line[:prefix] + digest + line[prefix + len(stripped[0]) :]
            changed += 1
        candidate_lines.append(line)
    assert changed == 1
    review_evidence.require_wo023p_manifest_contract(
        base_manifest,
        "".join(candidate_lines),
        candidate_bytes,
    )
    with pytest.raises(ValueError, match="does not match candidate bytes"):
        review_evidence.require_wo023p_manifest_contract(
            base_manifest,
            "".join(candidate_lines),
            candidate_bytes + b"\n",
        )


def test_wo023p_scope_and_renderers_are_exact_and_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(review_evidence, "migration_head", lambda: "0007_telemetry_events")
    monkeypatch.setattr(
        review_evidence,
        "canonical_change_evidence",
        lambda _paths, _work_order: {"project_brain_changed": False, "checkpoint_changed": False},
    )
    allowed = sorted(review_evidence.WO023P_G1_ALLOWED_PATHS)
    review_evidence.require_wo023p_g1_scope(
        review_evidence.WO023P_G1_WORK_ORDER,
        review_evidence.WO023P_G1_BASE_SHA,
        allowed,
    )
    with pytest.raises(ValueError, match="exact base"):
        review_evidence.require_wo023p_g1_scope(
            review_evidence.WO023P_G1_WORK_ORDER,
            "f" * 40,
            allowed,
        )
    with pytest.raises(ValueError, match="base branch"):
        review_evidence.require_wo023p_g1_scope(
            review_evidence.WO023P_G1_WORK_ORDER,
            review_evidence.WO023P_G1_BASE_SHA,
            allowed,
            base_branch="release",
        )
    for extra in (
        review_evidence.CHECKPOINT_PATH,
        review_evidence.CANONICAL_MANIFEST_PATH,
        "migrations/versions/0008_next.py",
        "backend/app/retrieval.py",
        ".github/workflows/ci.yml",
        "scripts/comprehensive_benchmarks.py",
    ):
        with pytest.raises(ValueError, match="exactly the four|canonical Project Brain|migrations"):
            review_evidence.require_wo023p_g1_scope(
                review_evidence.WO023P_G1_WORK_ORDER,
                review_evidence.WO023P_G1_BASE_SHA,
                allowed + [extra],
            )
    with pytest.raises(ValueError, match="exactly the four"):
        review_evidence.require_wo023p_g1_scope(
            review_evidence.WO023P_G1_WORK_ORDER,
            review_evidence.WO023P_G1_BASE_SHA,
            allowed[:-1],
        )

    body = render_body(
        work_order=review_evidence.WO023P_G1_WORK_ORDER,
        pr_number=93,
        branch="governance/wo023-p-g1",
        base_sha=review_evidence.WO023P_G1_BASE_SHA,
        head_sha="a" * 40,
        artifact_name="hive-review-evidence-WO-023-P-G1",
        ruleset_before="21934284",
        ruleset_after="21934284",
        merge_before="squash",
        merge_after="squash",
    )
    assert body.startswith("<!-- HIVE-WORK-ORDER: WO-023-P-G1 -->")
    assert f"<!-- HIVE-AUTHORIZED-BASE: {review_evidence.WO023P_G1_BASE_SHA} -->" in body
    assert "Exatamente quatro arquivos" in body
    assert "comprehensive-benchmarks-v1" in body
    assert review_evidence.WO023_APPROVED_PRODUCT_HEAD in body
    assert "WO-023-P-G1 READY FOR SOL AUDIT" in body
    assert "WO-022" in body
    promotion = render_body(
        work_order=review_evidence.WO023P_WORK_ORDER,
        pr_number=94,
        branch="governance/wo023-p",
        base_sha="b" * 40,
        head_sha="c" * 40,
        artifact_name="hive-review-evidence-WO-023-P",
        ruleset_before="21934284",
        ruleset_after="21934284",
        merge_before="squash",
        merge_after="squash",
    )
    assert promotion.startswith("<!-- HIVE-WORK-ORDER: WO-023-P -->")
    assert "COMPREHENSIVE BENCHMARKS APPROVED" in promotion
    assert "V0.1 IMPLEMENTATION ACTIVE" in promotion
    assert review_evidence.WO023P_COMPLETED_PENDING_ITEM in promotion
    assert "WO-023-P READY FOR SOL AUDIT" in promotion
    with pytest.raises(ValueError, match="authorized base"):
        render_body(
            work_order=review_evidence.WO023P_G1_WORK_ORDER,
            pr_number=93,
            branch="governance/wo023-p-g1",
            base_sha="d" * 40,
            head_sha="a" * 40,
            artifact_name="hive-review-evidence-WO-023-P-G1",
            ruleset_before="21934284",
            ruleset_after="21934284",
            merge_before="squash",
            merge_after="squash",
        )
    with pytest.raises(ValueError, match="exact HEAD"):
        render_body(
            work_order=review_evidence.WO023P_WORK_ORDER,
            pr_number=94,
            branch="governance/wo023-p",
            base_sha="b" * 40,
            head_sha="not-a-sha",
            artifact_name="hive-review-evidence-WO-023-P",
            ruleset_before="21934284",
            ruleset_after="21934284",
            merge_before="squash",
            merge_after="squash",
        )


def test_wo023p_governance_contract_binds_merged_benchmarks_and_lineage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The historical WO-023 promotion family stays auditable but is never current work."""

    monkeypatch.setattr(review_evidence, "migration_head", lambda: "0007_telemetry_events")
    monkeypatch.setattr(
        review_evidence,
        "canonical_change_evidence",
        lambda _paths, _work_order: {"project_brain_changed": False, "checkpoint_changed": False},
    )
    evidence = review_evidence.verify_wo023p_g1_c1_governance_contract(
        review_evidence.WO023P_G1_C1_WORK_ORDER,
        review_evidence.WO023P_G1_C1_BASE_SHA,
        sorted(review_evidence.WO023P_G1_C1_ALLOWED_PATHS),
        {
            "project_brain_changed": False,
            "checkpoint_changed": False,
            "authorized_paths": [],
        },
        {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}},
        {"comprehensive_benchmarks": wo023_benchmark_payload()},
        "0007_telemetry_events",
        review_evidence.WO023P_G1_C1_BASE_SHA,
    )
    assert evidence is not None
    assert "correction_scope=PASS" in evidence
    assert "canonical_promotion_untouched=True" in evidence
    assert "checkpoint_promotion=False" in evidence
    assert (
        frozenset({review_evidence.WO024_G1_WORK_ORDER, review_evidence.WO024P_WORK_ORDER})
        == review_evidence.ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS
    )
    assert {
        review_evidence.WO023P_G1_WORK_ORDER,
        review_evidence.WO023P_WORK_ORDER,
        review_evidence.WO023P_G1_C1_WORK_ORDER,
    }.issubset(review_evidence.HISTORICAL_CHECKPOINT_PROMOTION_WORK_ORDERS)
    for historical in (
        review_evidence.WO023P_G1_WORK_ORDER,
        review_evidence.WO023P_WORK_ORDER,
    ):
        with pytest.raises(ValueError, match="historical checkpoint-promotion"):
            review_evidence.require_current_work_order_authorization(historical)
    for authorized in (
        review_evidence.WO024_G1_WORK_ORDER,
        review_evidence.WO024_WORK_ORDER,
        review_evidence.WO024P_WORK_ORDER,
    ):
        review_evidence.require_current_work_order_authorization(authorized)


class _ManifestScopeReached(Exception):
    """Sentinel raised to stop a driven manifest build at the promotion scope check."""


def wo023p_manifest_harness(
    monkeypatch: pytest.MonkeyPatch,
    pr_body: str,
    *,
    delegate: bool = False,
) -> tuple[dict[str, object], dict[str, object]]:
    """Drive the real build_manifest path up to the WO-023-P promotion scope check."""

    base_sha = "3ca2109175b7c6842c6578c237ff798d5ce8916f"
    head_sha = "f" * 40
    seen: dict[str, object] = {"scope_calls": []}
    real_scope = review_evidence.require_wo023p_scope

    def fake_git_value(*args: object, **kwargs: object) -> str:
        if args[:2] == ("rev-parse", review_evidence.WO012P_PROMOTION_BASE_REF):
            return base_sha
        return head_sha

    def spy(work_order: str, scope_base: str, paths: list[str], **kwargs: object) -> None:
        cast(list[object], seen["scope_calls"]).append((work_order, kwargs))
        seen["work_order"] = work_order
        seen["base_sha"] = scope_base
        seen["paths"] = list(paths)
        seen["authorized_base_sha"] = kwargs.get("authorized_base_sha")
        if delegate:
            real_scope(work_order, scope_base, paths, **kwargs)  # type: ignore[arg-type]
            return
        raise _ManifestScopeReached

    monkeypatch.setattr(review_evidence, "pull_request_body", lambda repository, number: pr_body)
    monkeypatch.setattr(review_evidence, "read_text", lambda path: "")
    monkeypatch.setattr(review_evidence, "git_value", fake_git_value)
    monkeypatch.setattr(
        review_evidence,
        "changed_paths",
        lambda *args: sorted(review_evidence.WO023P_PROMOTION_ALLOWED_PATHS),
    )
    monkeypatch.setattr(review_evidence, "require_wo023p_scope", spy)
    args = SimpleNamespace(
        repository="KayzenRoot/hive",
        pr_number=92,
        work_order=review_evidence.WO023P_WORK_ORDER,
        base_branch="main",
        base_sha=base_sha,
        head_branch="governance/wo023-p-checkpoint-promotion",
        head_sha=head_sha,
        server_url="https://github.com",
        run_id="35040299812",
        integration_status="PASS",
        ready=True,
        draft=False,
    )
    return seen, vars(args)


def wo023p_pr_body(marker: str | None) -> str:
    body = f"<!-- HIVE-WORK-ORDER: {review_evidence.WO023P_WORK_ORDER} -->\n"
    if marker is not None:
        body += f"<!-- HIVE-AUTHORIZED-BASE: {marker} -->\n"
    return body


def test_wo023p_build_manifest_reads_its_authorized_base_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A merged historical work order is rejected as current work by the real manifest path."""

    seen, args = wo023p_manifest_harness(
        monkeypatch,
        wo023p_pr_body("3ca2109175b7c6842c6578c237ff798d5ce8916f"),
    )
    with pytest.raises(ValueError, match="historical checkpoint-promotion"):
        review_evidence.build_manifest(SimpleNamespace(**args))  # type: ignore[arg-type]
    assert seen.get("scope_calls", []) == []
    assert "authorized_base_sha" not in seen


def test_wo023p_build_manifest_fails_closed_on_bad_authorized_base_markers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The live promotion work order owns the authorized-base marker matrix."""

    _ = monkeypatch
    base_sha = review_evidence.WO024_G1_BASE_SHA
    preferred = review_evidence.WO024P_WORK_ORDER
    header = f"<!-- HIVE-WORK-ORDER: {preferred} -->" + chr(10)
    marker_cases = (
        ("missing marker", header, "missing exactly one authorized-base marker"),
        (
            "duplicate markers",
            header
            + f"<!-- HIVE-AUTHORIZED-BASE: {base_sha} -->"
            + chr(10)
            + f"<!-- HIVE-AUTHORIZED-BASE: {base_sha} -->"
            + chr(10),
            "multiple conflicting authorized-base markers",
        ),
        (
            "malformed marker",
            header + f"<!-- HIVE-AUTHORIZED-BASE: {base_sha.upper()} -->" + chr(10),
            "lowercase 40-hex",
        ),
        (
            "truncated marker",
            header + f"<!-- HIVE-AUTHORIZED-BASE: {base_sha[:39]} -->" + chr(10),
            "lowercase 40-hex",
        ),
    )
    for _label, body, expected in marker_cases:
        with pytest.raises(ValueError, match=expected):
            review_evidence.authorized_base_marker_sha(preferred, body)
    valid = header + f"<!-- HIVE-AUTHORIZED-BASE: {base_sha} -->" + chr(10)
    assert review_evidence.authorized_base_marker_sha(preferred, valid) == base_sha


def test_wo023p_g1_c1_registration_is_exact_and_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(review_evidence, "migration_head", lambda: "0007_telemetry_events")
    monkeypatch.setattr(
        review_evidence,
        "canonical_change_evidence",
        lambda _paths, _work_order: {"project_brain_changed": False, "checkpoint_changed": False},
    )
    base_sha = review_evidence.WO023P_G1_C1_BASE_SHA
    allowed = sorted(review_evidence.WO023P_G1_C1_ALLOWED_PATHS)
    review_evidence.require_wo023p_g1_c1_scope(
        review_evidence.WO023P_G1_C1_WORK_ORDER,
        base_sha,
        allowed,
        authorized_base_sha=base_sha,
    )
    with pytest.raises(ValueError, match="exact base"):
        review_evidence.require_wo023p_g1_c1_scope(
            review_evidence.WO023P_G1_C1_WORK_ORDER,
            "f" * 40,
            allowed,
            authorized_base_sha=base_sha,
        )
    with pytest.raises(ValueError, match="protected main base branch"):
        review_evidence.require_wo023p_g1_c1_scope(
            review_evidence.WO023P_G1_C1_WORK_ORDER,
            base_sha,
            allowed,
            base_branch="release",
            authorized_base_sha=base_sha,
        )
    with pytest.raises(ValueError, match="exactly the review evidence tooling"):
        review_evidence.require_wo023p_g1_c1_scope(
            review_evidence.WO023P_G1_C1_WORK_ORDER,
            base_sha,
            [*allowed, review_evidence.CHECKPOINT_PATH],
            authorized_base_sha=base_sha,
        )
    with pytest.raises(ValueError, match="exactly one authorized-base marker"):
        review_evidence.require_wo023p_g1_c1_scope(
            review_evidence.WO023P_G1_C1_WORK_ORDER,
            base_sha,
            allowed,
        )
    with pytest.raises(ValueError, match="lowercase 40-hex"):
        review_evidence.require_wo023p_g1_c1_scope(
            review_evidence.WO023P_G1_C1_WORK_ORDER,
            base_sha,
            allowed,
            authorized_base_sha=base_sha.upper(),
        )
    with pytest.raises(ValueError, match="must match the pull request base SHA"):
        review_evidence.require_wo023p_g1_c1_scope(
            review_evidence.WO023P_G1_C1_WORK_ORDER,
            base_sha,
            allowed,
            authorized_base_sha="b" * 40,
        )

    governance = {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}}
    integration = {"comprehensive_benchmarks": wo023_benchmark_payload()}
    no_canonical = {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }
    evidence = review_evidence.verify_wo023p_g1_c1_governance_contract(
        review_evidence.WO023P_G1_C1_WORK_ORDER,
        base_sha,
        allowed,
        no_canonical,
        governance,
        integration,
        "0007_telemetry_events",
        base_sha,
    )
    assert evidence is not None
    assert "authorized_base_parser_covers_WO-023-P=PASS" in evidence
    assert "canonical_promotion_untouched=True" in evidence
    assert "unknown_WO-025_WO-025-P_WO-999-P=REJECTED" in evidence
    assert "checkpoint_promotion=False" in evidence
    with pytest.raises(ValueError, match="forbids canonical changes"):
        review_evidence.verify_wo023p_g1_c1_governance_contract(
            review_evidence.WO023P_G1_C1_WORK_ORDER,
            base_sha,
            allowed,
            {
                "project_brain_changed": True,
                "checkpoint_changed": True,
                "authorized_paths": [review_evidence.CHECKPOINT_PATH],
            },
            governance,
            integration,
            "0007_telemetry_events",
            base_sha,
        )
    with pytest.raises(ValueError, match="auto-merge to remain unarmed"):
        review_evidence.verify_wo023p_g1_c1_governance_contract(
            review_evidence.WO023P_G1_C1_WORK_ORDER,
            base_sha,
            allowed,
            no_canonical,
            {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": True}},
            integration,
            "0007_telemetry_events",
            base_sha,
        )
    with pytest.raises(ValueError, match="mandatory comprehensive benchmarks"):
        review_evidence.verify_wo023p_g1_c1_governance_contract(
            review_evidence.WO023P_G1_C1_WORK_ORDER,
            base_sha,
            allowed,
            no_canonical,
            governance,
            {},
            "0007_telemetry_events",
            base_sha,
        )
    with pytest.raises(ValueError, match="authorized-base marker parser"):
        monkeypatch.setattr(
            review_evidence,
            "AUTHORIZED_BASE_MARKER_WORK_ORDERS",
            frozenset({review_evidence.GEF_ADOPTION_WORK_ORDER}),
        )
        review_evidence.verify_wo023p_g1_c1_governance_contract(
            review_evidence.WO023P_G1_C1_WORK_ORDER,
            base_sha,
            allowed,
            no_canonical,
            governance,
            integration,
            "0007_telemetry_events",
            base_sha,
        )
    monkeypatch.undo()

    assert (
        AUTHORIZED_BASE_BY_WORK_ORDER[review_evidence.WO023P_G1_C1_WORK_ORDER]
        == review_evidence.WO023P_G1_C1_BASE_SHA
    )
    with pytest.raises(ValueError, match="historical checkpoint-promotion"):
        review_evidence.require_current_work_order_authorization(
            review_evidence.WO023P_G1_C1_WORK_ORDER
        )
    for rejected in ("WO-032", "WO-026-P", "WO-999-P"):
        with pytest.raises(ValueError, match="unsupported|historical"):
            review_evidence.require_current_work_order_authorization(rejected)
    for historical in (
        review_evidence.WO022P_G1_WORK_ORDER,
        review_evidence.WO022P_WORK_ORDER,
    ):
        with pytest.raises(ValueError, match="historical checkpoint-promotion"):
            review_evidence.require_current_work_order_authorization(historical)

    body = render_body(
        work_order=review_evidence.WO023P_G1_C1_WORK_ORDER,
        pr_number=93,
        branch="governance/wo023-p-g1-c1-authorized-base-parser",
        base_sha=base_sha,
        head_sha="a" * 40,
        artifact_name="hive-review-evidence-WO-023-P-G1-C1",
        ruleset_before="21934284",
        ruleset_after="21934284",
        merge_before="squash",
        merge_after="squash",
    )
    assert body.startswith("<!-- HIVE-WORK-ORDER: WO-023-P-G1-C1 -->")
    assert f"<!-- HIVE-AUTHORIZED-BASE: {base_sha} -->" in body
    assert "WO-023-P-G1-C1 READY FOR SOL AUDIT" in body
    assert "#92" in body
    with pytest.raises(ValueError, match="authorized base"):
        render_body(
            work_order=review_evidence.WO023P_G1_C1_WORK_ORDER,
            pr_number=93,
            branch="governance/wo023-p-g1-c1-authorized-base-parser",
            base_sha="d" * 40,
            head_sha="a" * 40,
            artifact_name="hive-review-evidence-WO-023-P-G1-C1",
            ruleset_before="21934284",
            ruleset_after="21934284",
            merge_before="squash",
            merge_after="squash",
        )


def v01_closure_evidence_fixture(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": "PASS",
        "v01_closure_sprint_evidence_version": review_evidence.V01_CLOSURE_SPRINT_EVIDENCE_VERSION,
        "evidence_file": review_evidence.V01_CLOSURE_SPRINT_EVIDENCE_FILE,
        "observed_migration_head": review_evidence.V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD,
        "migration_base_head": review_evidence.V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD,
        "reviewed_base_sha": "a" * 40,
        "reviewed_head_sha": "b" * 40,
        "fixture_identity": "closure-fixture-v1",
        "corpus_identity": "closure-corpus-v1",
        "run_digest": hashlib.sha256(b"closure").hexdigest(),
        "deployment_persistent_root_identity": "host-persistence-root-v1",
        "backup_artifact_sha256": hashlib.sha256(b"backup").hexdigest(),
        "dod_definition_of_done_sha256": hashlib.sha256(b"dod").hexdigest(),
        **{field: True for field in review_evidence.V01_CLOSURE_SPRINT_TRUE_FIELDS},
        **{field: False for field in review_evidence.V01_CLOSURE_SPRINT_FALSE_FIELDS},
        **{field: 0 for field in review_evidence.V01_CLOSURE_SPRINT_ZERO_FIELDS},
        "stabilization_defects_discovered": 4,
        "stabilization_defects_fixed": 4,
        "deployment_service_count": 4,
        "backup_artifact_count": 2,
        "e2e_stage_count": len(review_evidence.V01_CLOSURE_SPRINT_E2E_STAGES),
        "dod_total_count": 12,
        "dod_pass_count": 12,
        "changed_paths": ["backend/app/retrieval.py", "docs/atlas/V0.1-CLOSURE-GAP-REPORT.md"],
        "stabilization_evidence_paths": ["docs/atlas/V0.1-CLOSURE-GAP-REPORT.md"],
        "deployment_evidence_paths": ["docker-compose.yml"],
        "backup_evidence_paths": ["scripts/backup_restore.py"],
        "orchestration_evidence_paths": ["backend/app/execution_orchestrator.py"],
        "e2e_evidence_paths": ["scripts/closure_integration.py"],
        "orchestration_authority_order": list(review_evidence.V01_CLOSURE_SPRINT_AUTHORITY_ORDER),
        "orchestration_negative_matrix": list(review_evidence.V01_CLOSURE_SPRINT_NEGATIVE_CASES),
        "e2e_completed_stages": list(review_evidence.V01_CLOSURE_SPRINT_E2E_STAGES),
        "documentation_entries": [
            {
                "name": name,
                "path": "docs/atlas/V0.1-CLOSURE-GAP-REPORT.md",
                "sha256": hashlib.sha256(name.encode()).hexdigest(),
                "status": "PASS",
            }
            for name in review_evidence.V01_CLOSURE_SPRINT_DOCUMENTATION_ENTRIES
        ],
        "dod_items": [
            {
                "item": f"Definition of Done requirement {index}",
                "status": "PASS",
                "evidence_path": "docs/atlas/V0.1-CLOSURE-GAP-REPORT.md",
                "sha256": hashlib.sha256(f"dod-{index}".encode()).hexdigest(),
            }
            for index in range(12)
        ],
        "closure_candidate": True,
    }
    payload.update(overrides)
    return payload


def test_wo024_manifest_stays_schema_valid_without_closure_property() -> None:
    """The closure artifact is a gating input, never an undeclared manifest property."""

    import inspect

    source = inspect.getsource(review_evidence.integration_evidence)
    assert 'evidence["v01_closure_sprint"]' not in source
    schema_text = review_evidence.SCHEMA_PATH.read_text(encoding="utf-8")
    assert '"v01_closure_sprint": {' not in schema_text
    # the approved lineage definition stays declared and closed
    assert '"v01_closure_sprint_approved_lineage": {' in schema_text


def test_wo024_g1_scope_and_renderers_are_exact_and_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(review_evidence, "migration_head", lambda: "0007_telemetry_events")
    monkeypatch.setattr(
        review_evidence,
        "canonical_change_evidence",
        lambda _paths, _work_order: {"project_brain_changed": False, "checkpoint_changed": False},
    )
    base_sha = review_evidence.WO024_G1_BASE_SHA
    allowed = sorted(review_evidence.WO024_G1_ALLOWED_PATHS)
    review_evidence.require_wo024_g1_scope(
        review_evidence.WO024_G1_WORK_ORDER, base_sha, allowed, authorized_base_sha=base_sha
    )
    with pytest.raises(ValueError, match="exact base"):
        review_evidence.require_wo024_g1_scope(
            review_evidence.WO024_G1_WORK_ORDER, "f" * 40, allowed, authorized_base_sha=base_sha
        )
    with pytest.raises(ValueError, match="exactly the four governance files"):
        review_evidence.require_wo024_g1_scope(
            review_evidence.WO024_G1_WORK_ORDER,
            base_sha,
            [*allowed, review_evidence.CHECKPOINT_PATH],
            authorized_base_sha=base_sha,
        )
    with pytest.raises(ValueError, match="exactly one authorized-base marker"):
        review_evidence.require_wo024_g1_scope(
            review_evidence.WO024_G1_WORK_ORDER, base_sha, allowed
        )

    governance = {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}}
    monkeypatch.setattr(review_evidence, "integration_file", lambda name: "")
    evidence = review_evidence.verify_wo024_g1_governance_contract(
        review_evidence.WO024_G1_WORK_ORDER,
        base_sha,
        allowed,
        {
            "project_brain_changed": False,
            "checkpoint_changed": False,
            "authorized_paths": [],
        },
        governance,
        {},
        "0007_telemetry_events",
        base_sha,
    )
    assert evidence is not None
    assert "future_WO-024=REGISTERED" in evidence and "future_WO-024-P=REGISTERED" in evidence
    assert "checkpoint_promotion=False" in evidence
    monkeypatch.setattr(review_evidence, "integration_file", lambda name: '{"status": "PASS"}')
    with pytest.raises(ValueError, match="must not claim future v01 closure"):
        review_evidence.verify_wo024_g1_governance_contract(
            review_evidence.WO024_G1_WORK_ORDER,
            base_sha,
            allowed,
            {
                "project_brain_changed": False,
                "checkpoint_changed": False,
                "authorized_paths": [],
            },
            governance,
            {},
            "0007_telemetry_events",
            base_sha,
        )
    monkeypatch.undo()
    monkeypatch.setattr(review_evidence, "migration_head", lambda: "0007_telemetry_events")
    monkeypatch.setattr(
        review_evidence,
        "canonical_change_evidence",
        lambda _paths, _work_order: {"project_brain_changed": False, "checkpoint_changed": False},
    )

    body = render_body(
        work_order=review_evidence.WO024_G1_WORK_ORDER,
        pr_number=95,
        branch="governance/wo024-g1-v01-closure-sprint",
        base_sha=base_sha,
        head_sha="a" * 40,
        artifact_name="hive-review-evidence-WO-024-G1",
        ruleset_before="21934284",
        ruleset_after="21934284",
        merge_before="squash",
        merge_after="squash",
    )
    assert body.startswith("<!-- HIVE-WORK-ORDER: WO-024-G1 -->")
    assert f"<!-- HIVE-AUTHORIZED-BASE: {base_sha} -->" in body
    assert "WO-024-G1 READY FOR SOL AUDIT" in body
    with pytest.raises(ValueError, match="authorized base"):
        render_body(
            work_order=review_evidence.WO024_G1_WORK_ORDER,
            pr_number=95,
            branch="governance/wo024-g1-v01-closure-sprint",
            base_sha="d" * 40,
            head_sha="a" * 40,
            artifact_name="hive-review-evidence-WO-024-G1",
            ruleset_before="21934284",
            ruleset_after="21934284",
            merge_before="squash",
            merge_after="squash",
        )


_original_closure_reader = review_evidence.closure_sprint_evidence


def test_wo024_closure_contract_fails_closed_on_incomplete_closure() -> None:
    integration: dict[str, object] = {}
    payload = v01_closure_evidence_fixture()
    review_evidence.closure_sprint_evidence = lambda: payload
    review_evidence.require_wo024_v01_closure_sprint_evidence(
        review_evidence.WO024_WORK_ORDER, integration, "0007_telemetry_events"
    )
    review_evidence.closure_sprint_evidence = lambda: {}
    with pytest.raises(ValueError, match="missing mandatory v01 closure sprint evidence"):
        review_evidence.require_wo024_v01_closure_sprint_evidence(
            review_evidence.WO024_WORK_ORDER, integration, "0007_telemetry_events"
        )
    review_evidence.closure_sprint_evidence = lambda: v01_closure_evidence_fixture()

    dod_items = cast(list[dict[str, object]], payload["dod_items"])
    failing_items = [dict(item) for item in dod_items]
    failing_items[0] = {**failing_items[0], "status": "FAIL"}
    unknown_items = [dict(item) for item in dod_items]
    unknown_items[1] = {**unknown_items[1], "status": "UNKNOWN"}
    documented = cast(list[dict[str, object]], payload["documentation_entries"])
    stale_docs = [dict(entry) for entry in documented]
    stale_docs[0] = {**stale_docs[0], "status": "FAIL"}
    negative_cases = (
        ("remaining high defect", {"stabilization_remaining_high": 1}),
        ("remaining critical defect", {"stabilization_remaining_critical": 1}),
        (
            "deployment persistence failure",
            {"deployment_postgres_persistence_after_recreation": False},
        ),
        ("deployment cas integrity failure", {"deployment_cas_persistence_integrity": False}),
        ("backup mismatch", {"backup_row_equivalence": False}),
        ("backup cas mismatch", {"backup_cas_hash_equivalence": False}),
        ("redis canonical", {"redis_canonical_truth": True}),
        ("checkpoint not first", {"orchestration_checkpoint_first": False}),
        ("cross-project authority", {"orchestration_negative_matrix": ["missing_authority"]}),
        (
            "missing e2e stage",
            {"e2e_completed_stages": list(review_evidence.V01_CLOSURE_SPRINT_E2E_STAGES[:-1])},
        ),
        ("stale docs", {"documentation_entries": stale_docs}),
        ("dod fail", {"dod_items": failing_items}),
        ("dod unknown", {"dod_items": unknown_items}),
        ("completion claim in product", {"full_v01_complete_claimed": True}),
        ("fabricated metrics", {"fabricated_metrics": True}),
        ("secret leak", {"secret_leaks": 2}),
        ("unbounded changed path", {"changed_paths": ["C:\\Windows\\system32"]}),
        ("absolute evidence path", {"stabilization_evidence_paths": ["/var/lib/hive/cas"]}),
        ("wrong dod total", {"dod_total_count": 11}),
        ("stabilization regression", {"stabilization_regression_suite_pass": False}),
    )
    for label, override in negative_cases:
        mutation = v01_closure_evidence_fixture(**override)

        def _closure_reader(mutation: dict[str, object] = mutation) -> dict[str, object]:
            return mutation

        review_evidence.closure_sprint_evidence = _closure_reader
        broken: dict[str, object] = {}
        if label == "completion claim in product":
            fixture = v01_closure_evidence_fixture(**override)
            assert fixture["full_v01_complete_claimed"] is True
        with pytest.raises(ValueError, match="WO-024"):
            review_evidence.require_wo024_v01_closure_sprint_evidence(
                review_evidence.WO024_WORK_ORDER, broken, "0007_telemetry_events"
            )
    review_evidence.closure_sprint_evidence = _original_closure_reader


def test_wo024_product_scope_boundaries_are_bounded() -> None:
    allowed = (
        "backend/app/retrieval.py",
        "backend/tests/test_retrieval.py",
        "scripts/closure_integration.py",
        "docs/atlas/V0.1-CLOSURE-GAP-REPORT.md",
        "dashboard/src/main.tsx",
        "dashboard/tests/app.test.tsx",
        "docker-compose.yml",
        ".env.example",
        "README.md",
        "Dockerfile",
    )
    assert review_evidence.closure_product_scope(list(allowed)) == []
    for forbidden in (
        "docs/project-brain/13-CHECKPOINT.md",
        "docs/project-brain/CANONICAL-SHA256SUMS.txt",
        "migrations/versions/0008_closure.py",
        ".github/workflows/ci.yml",
        "release-assets/notes.md",
        "requirements.txt",
        "dashboard/package-lock.json",
    ):
        assert review_evidence.closure_product_scope([forbidden]) == [forbidden]


def wo024_approved_lineage_sources(**overrides: object) -> dict[str, object]:
    """Bounded GitHub sources shaped like the approved WO-024 product run.

    ``product_pr`` carries the full pull-request resource, which is the payload
    that exposes ``merged``; the commit-associated payload does not.
    """

    payload: dict[str, object] = {
        "product_pr": {
            "number": review_evidence.WO024_APPROVED_PRODUCT_PR,
            "state": "closed",
            "merged": True,
            "merge_commit_sha": review_evidence.WO024_APPROVED_SQUASH_MERGE_SHA,
            "base": {"ref": "main", "sha": review_evidence.WO024_APPROVED_PRODUCT_BASE_SHA},
            "head": {"sha": review_evidence.WO024_APPROVED_PRODUCT_HEAD_SHA},
            "body": f"<!-- HIVE-WORK-ORDER: {review_evidence.WO024_WORK_ORDER} -->",
        },
        "product_reviews": [
            {
                "id": review_evidence.WO024_APPROVED_SOL_REVIEW_ID,
                "state": "COMMENTED",
                "commit_id": review_evidence.WO024_APPROVED_PRODUCT_HEAD_SHA,
                "body": (
                    "**VERDICT: APPROVED**\n"
                    f"Exact HEAD audited: `{review_evidence.WO024_APPROVED_PRODUCT_HEAD_SHA}`\n"
                    f"Authorized base: `{review_evidence.WO024_APPROVED_PRODUCT_BASE_SHA}`\n"
                    "- Backend: 676 passed\n"
                    "- Dashboard: 34 passed\n"
                ),
            }
        ],
        "ancestry": {
            "status": "ahead",
            "merge_base_commit": {"sha": review_evidence.WO024_APPROVED_SQUASH_MERGE_SHA},
        },
        "merge_commit": {
            "sha": review_evidence.WO024_APPROVED_SQUASH_MERGE_SHA,
            "parents": [{"sha": "0" * 40}],
        },
        "post_merge_run": {
            "id": review_evidence.WO024_APPROVED_POST_MERGE_CI_RUN,
            "event": "push",
            "head_sha": review_evidence.WO024_APPROVED_SQUASH_MERGE_SHA,
            "status": "completed",
            "conclusion": "success",
        },
        "post_merge_jobs": [
            {"name": "Validate", "status": "completed", "conclusion": "success"},
            {"name": "Integration health", "status": "completed", "conclusion": "success"},
            {"name": "Review Evidence", "status": "completed", "conclusion": "skipped"},
        ],
        "prior_review_comments": [
            {
                "body": (
                    f"<!-- hive-review-evidence:{review_evidence.WO024_WORK_ORDER.casefold()} -->\n"
                    f"Exact HEAD SHA: `{review_evidence.WO024_APPROVED_PRODUCT_HEAD_SHA}`\n"
                    "Validate result: **PASS**\n"
                    "Integration health result: **PASS**\n"
                    "Review Evidence result: **PASS**\n"
                    f"Migration head: `{review_evidence.V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}`\n"
                    "Canonical verifier: **PASS**\n"
                    "Canonical changes: project_brain_changed `False`, checkpoint_changed `False`\n"
                    "Thread resolution `True`\n"
                    "Auto-merge armed: `False` / `none`\n"
                )
            }
        ],
        "closure_evidence": v01_closure_evidence_fixture(),
    }
    payload.update(overrides)
    return payload


def test_wo024_approved_lineage_uses_full_pr_and_audited_test_counts() -> None:
    result = review_evidence.verify_wo024_approved_lineage(wo024_approved_lineage_sources())
    assert result["status"] == "PASS"
    assert result["product_pr"] == review_evidence.WO024_APPROVED_PRODUCT_PR
    assert result["sol_review_id"] == review_evidence.WO024_APPROVED_SOL_REVIEW_ID
    assert result["squash_merge_sha"] == review_evidence.WO024_APPROVED_SQUASH_MERGE_SHA
    assert result["post_merge_ci_run"] == review_evidence.WO024_APPROVED_POST_MERGE_CI_RUN
    assert result["prior_backend_passed"] == 676
    assert result["prior_dashboard_passed"] == 34
    assert review_evidence.wo024_approved_lineage_statement(result).startswith(
        "Approved WO-024 product lineage: "
    )


def wo024_lineage_endpoints(current_main: str) -> dict[str, object]:
    """Bounded API fixtures addressed only by immutable approved identity."""

    sources = wo024_approved_lineage_sources()
    squash = review_evidence.WO024_APPROVED_SQUASH_MERGE_SHA
    number = review_evidence.WO024_APPROVED_PRODUCT_PR
    run_id = review_evidence.WO024_APPROVED_POST_MERGE_CI_RUN
    return {
        f"pulls/{number}": sources["product_pr"],
        f"pulls/{number}/reviews": sources["product_reviews"],
        f"issues/{number}/comments": sources["prior_review_comments"],
        f"commits/{squash}": sources["merge_commit"],
        f"compare/{squash}...{current_main}": sources["ancestry"],
        f"actions/runs/{run_id}": sources["post_merge_run"],
        f"actions/runs/{run_id}/jobs": {"jobs": sources["post_merge_jobs"]},
    }


def wo024_lineage_overrides(case: str, current_main: str) -> dict[str, object]:
    """Return the divergent payload for one fetch-layer negative case."""

    endpoints = wo024_lineage_endpoints(current_main)
    number = review_evidence.WO024_APPROVED_PRODUCT_PR
    squash = review_evidence.WO024_APPROVED_SQUASH_MERGE_SHA
    run_id = review_evidence.WO024_APPROVED_POST_MERGE_CI_RUN
    product_pr = cast("dict[str, object]", endpoints[f"pulls/{number}"])
    compare_key = f"compare/{squash}...{current_main}"
    if case == "wrong-pull-request":
        return {f"pulls/{number}": {**product_pr, "number": 94}}
    if case == "unmerged-pull-request":
        return {f"pulls/{number}": {**product_pr, "merged": False, "state": "open"}}
    if case == "wrong-audited-head":
        return {f"pulls/{number}": {**product_pr, "head": {"sha": "1" * 40}}}
    if case == "wrong-authorized-base":
        return {f"pulls/{number}": {**product_pr, "base": {"ref": "main", "sha": "2" * 40}}}
    if case == "wrong-squash-merge":
        return {f"pulls/{number}": {**product_pr, "merge_commit_sha": "5" * 40}}
    if case == "diverged-ancestry":
        return {compare_key: {"status": "diverged", "merge_base_commit": {"sha": "3" * 40}}}
    if case == "different-merge-base":
        return {compare_key: {"status": "ahead", "merge_base_commit": {"sha": "4" * 40}}}
    if case == "divergent-sol-review":
        review = cast("list[dict[str, object]]", endpoints[f"pulls/{number}/reviews"])[0]
        return {f"pulls/{number}/reviews": [{**review, "id": 42}]}
    if case == "divergent-post-merge-run":
        run = cast("dict[str, object]", endpoints[f"actions/runs/{run_id}"])
        return {f"actions/runs/{run_id}": {**run, "id": 42}}
    raise AssertionError(f"unknown divergence case: {case}")


def wo024_lineage_fetch_fake(
    current_main: str, overrides: dict[str, object] | None = None
) -> tuple[Callable[[str, str], object], list[str]]:
    endpoints = wo024_lineage_endpoints(current_main)
    replacements = overrides or {}
    calls: list[str] = []

    def fake(_repository: str, endpoint: str) -> object:
        calls.append(endpoint)
        if endpoint not in endpoints:
            raise AssertionError(f"unexpected lineage endpoint: {endpoint}")
        return replacements.get(endpoint, endpoints[endpoint])

    return fake, calls


def test_wo024_lineage_fetch_is_direct_and_survives_a_later_correction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A later governance correction moves main; the fetch must stay identity addressed."""

    later_main = "d" * 40
    fake, calls = wo024_lineage_fetch_fake(later_main)
    monkeypatch.setattr(review_evidence, "git_value", lambda *_args, **_kwargs: later_main)
    monkeypatch.setattr(review_evidence, "_gh_json", fake)

    result = review_evidence.fetch_wo024_approved_lineage(
        "KayzenRoot/hive", v01_closure_evidence_fixture()
    )

    assert result["status"] == "PASS"
    assert result["prior_backend_passed"] == 676
    assert result["prior_dashboard_passed"] == 34
    assert result["squash_merge_sha"] == review_evidence.WO024_APPROVED_SQUASH_MERGE_SHA
    assert f"pulls/{review_evidence.WO024_APPROVED_PRODUCT_PR}" in calls
    assert f"compare/{review_evidence.WO024_APPROVED_SQUASH_MERGE_SHA}...{later_main}" in calls
    assert f"actions/runs/{review_evidence.WO024_APPROVED_POST_MERGE_CI_RUN}" in calls
    assert f"commits/{review_evidence.WO024_APPROVED_SQUASH_MERGE_SHA}" in calls
    # the product is never discovered through the pull request associated with main
    assert not any(endpoint.startswith(f"commits/{later_main}") for endpoint in calls)
    assert not any("actions/runs?" in endpoint for endpoint in calls)


@pytest.mark.parametrize(
    "case",
    (
        "wrong-pull-request",
        "unmerged-pull-request",
        "wrong-audited-head",
        "wrong-authorized-base",
        "wrong-squash-merge",
        "diverged-ancestry",
        "different-merge-base",
        "divergent-sol-review",
        "divergent-post-merge-run",
    ),
)
def test_wo024_lineage_fetch_fails_closed_on_divergent_sources(
    monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    later_main = "d" * 40
    fake, _calls = wo024_lineage_fetch_fake(later_main, wo024_lineage_overrides(case, later_main))
    monkeypatch.setattr(review_evidence, "git_value", lambda *_args, **_kwargs: later_main)
    monkeypatch.setattr(review_evidence, "_gh_json", fake)
    with pytest.raises(ValueError):
        review_evidence.fetch_wo024_approved_lineage(
            "KayzenRoot/hive", v01_closure_evidence_fixture()
        )


def test_wo024_approved_squash_may_be_an_ancestor_of_a_later_correction() -> None:
    for status in ("ahead", "identical"):
        sources = wo024_approved_lineage_sources(
            ancestry={
                "status": status,
                "merge_base_commit": {"sha": review_evidence.WO024_APPROVED_SQUASH_MERGE_SHA},
            }
        )
        assert review_evidence.verify_wo024_approved_lineage(sources)["status"] == "PASS"


@pytest.mark.parametrize(
    "mutate",
    (
        pytest.param(
            lambda sources: sources["product_pr"].__setitem__("number", 94),
            id="wrong-product-pr",
        ),
        pytest.param(
            lambda sources: sources["product_pr"]["base"].__setitem__("sha", "0" * 40),
            id="wrong-authorized-base",
        ),
        pytest.param(
            lambda sources: sources["product_pr"]["head"].__setitem__("sha", "1" * 40),
            id="wrong-audited-head",
        ),
        pytest.param(
            lambda sources: sources["product_reviews"][0].__setitem__("id", 42),
            id="wrong-sol-review",
        ),
        pytest.param(
            lambda sources: sources["product_pr"].__setitem__("merge_commit_sha", "2" * 40),
            id="wrong-squash-merge",
        ),
        pytest.param(
            lambda sources: sources["post_merge_run"].__setitem__("id", 42),
            id="wrong-post-merge-run",
        ),
        pytest.param(
            lambda sources: sources.__setitem__(
                "ancestry", {"status": "diverged", "merge_base_commit": {"sha": "3" * 40}}
            ),
            id="non-ancestor-lineage",
        ),
        pytest.param(
            lambda sources: sources["product_pr"].__setitem__("merged", None),
            id="association-payload-without-merged",
        ),
        pytest.param(
            lambda sources: sources["product_reviews"][0].__setitem__(
                "body", "**VERDICT: APPROVED**\nno audited counts here\n"
            ),
            id="malformed-audited-counts",
        ),
    ),
)
def test_wo024_approved_lineage_fails_closed(
    mutate: Callable[[dict[str, object]], None],
) -> None:
    sources = wo024_approved_lineage_sources()
    mutate(sources)
    with pytest.raises(ValueError):
        review_evidence.verify_wo024_approved_lineage(sources)


def test_wo024_sol_review_counts_fail_closed_without_zero_substitution() -> None:
    with pytest.raises(ValueError):
        review_evidence._sol_review_test_counts("**verdict: approved**")
    with pytest.raises(ValueError):
        review_evidence._sol_review_test_counts("- backend: 0 passed\n- dashboard: 34 passed")
    assert review_evidence._sol_review_test_counts(
        "- backend: 676 passed\n- dashboard: 34 passed"
    ) == (
        676,
        34,
    )


def test_wo024p_promotion_base_registry_tracks_current_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert review_evidence.WO024P_PROMOTION_REGISTRY == {
        review_evidence.WO024P_WORK_ORDER: review_evidence.WO012P_PROMOTION_BASE_REF
    }
    monkeypatch.setattr(review_evidence, "git_value", lambda *_args, **_kwargs: "c" * 40)
    assert review_evidence.registered_promotion_base_sha(review_evidence.WO024P_WORK_ORDER) == (
        "c" * 40
    )
    with pytest.raises(ValueError):
        review_evidence.registered_promotion_base_sha("WO-024-P-G1-C1")


def test_closure_sprint_scope_is_promotion_aware() -> None:
    pair = sorted(review_evidence.WO024P_PROMOTION_ALLOWED_PATHS)
    assert review_evidence.closure_sprint_scope(list(pair)) == []
    assert review_evidence.closure_sprint_scope(pair + ["scripts/v01_closure_sprint.py"]) == pair
    for single in pair:
        assert review_evidence.closure_sprint_scope([single]) == [single]
    assert review_evidence.closure_sprint_scope(["backend/app/context_manager.py"]) == []
    assert review_evidence.closure_product_scope(list(pair)) == pair


def test_closure_sprint_scope_admits_registered_release_engineering_surface() -> None:
    release_paths = [
        "VERSION",
        "README.md",
        "CHANGELOG.md",
        "LICENSE",
        "AGENTS.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "SUPPORT.md",
        "dashboard/package.json",
        "dashboard/package-lock.json",
        "docs/VERSIONING.md",
        "docs/releases/v1.0.0.md",
        ".github/workflows/release.yml",
        ".github/ISSUE_TEMPLATE/maintenance.yml",
        ".engineering/release/HIVE-V1.0.0-RELEASE-CANDIDATE.json",
    ]
    assert review_evidence.release_engineering_scope(release_paths) == []
    assert review_evidence.closure_sprint_scope(release_paths) == []
    assert (
        review_evidence.closure_sprint_scope([*release_paths, "backend/app/context_manager.py"])
        == []
    )
    for rejected in (
        "docs/project-brain/13-CHECKPOINT.md",
        "docs/project-brain/CANONICAL-SHA256SUMS.txt",
        ".engineering/gef/GEF-POLICY.md",
        "migrations/versions/0008_release.py",
        "backend/app.py",
        "secrets/credentials.txt",
        "tmp/release-dry-run/hive-v1.0.0.zip",
        "release-assets/hive-v1.0.0.zip",
    ):
        assert review_evidence.release_engineering_scope([rejected]) == [rejected]
        assert review_evidence.closure_sprint_scope([rejected]) == [rejected]


def test_wo024p_g1_c1_scope_is_bounded_and_fails_closed() -> None:
    allowed = sorted(review_evidence.WO024P_G1_C1_ALLOWED_PATHS)
    review_evidence.require_wo024p_g1_c1_scope(
        review_evidence.WO024P_G1_C1_WORK_ORDER,
        review_evidence.WO024P_G1_C1_BASE_SHA,
        allowed,
        authorized_base_sha=review_evidence.WO024P_G1_C1_BASE_SHA,
    )
    for paths in (
        ["docs/project-brain/13-CHECKPOINT.md"],
        ["docs/project-brain/CANONICAL-SHA256SUMS.txt"],
        ["migrations/versions/0008_correction.py"],
        [".github/workflows/ci.yml"],
        ["schemas/review-evidence-v1.schema.json"],
        ["requirements.txt"],
        ["dashboard/package-lock.json"],
        ["VERSION"],
        ["CHANGELOG.md"],
        ["backend/app/context_manager.py"],
        [],
    ):
        with pytest.raises(ValueError):
            review_evidence.require_wo024p_g1_c1_scope(
                review_evidence.WO024P_G1_C1_WORK_ORDER,
                review_evidence.WO024P_G1_C1_BASE_SHA,
                paths,
                authorized_base_sha=review_evidence.WO024P_G1_C1_BASE_SHA,
            )
    for base_sha, marker in (
        ("c" * 40, review_evidence.WO024P_G1_C1_BASE_SHA),
        (review_evidence.WO024P_G1_C1_BASE_SHA, None),
        (review_evidence.WO024P_G1_C1_BASE_SHA, "not-a-sha"),
    ):
        with pytest.raises(ValueError):
            review_evidence.require_wo024p_g1_c1_scope(
                review_evidence.WO024P_G1_C1_WORK_ORDER,
                base_sha,
                allowed,
                authorized_base_sha=marker,
            )


def test_wo024p_g1_c1_is_self_hosted_with_governance_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # the closure gate reads the integration artifact from disk; inject the
    # contract fixture so the regression holds without any local evidence file
    closure_text = json.dumps(v01_closure_evidence_fixture())
    monkeypatch.setattr(
        review_evidence,
        "integration_file",
        lambda name: (
            closure_text if name == review_evidence.V01_CLOSURE_SPRINT_EVIDENCE_FILE else ""
        ),
    )
    assert review_evidence.WO024P_G1_C1_WORK_ORDER in (
        review_evidence.AUTHORIZED_BASE_MARKER_WORK_ORDERS
    )
    assert review_evidence.WO024P_G1_C1_WORK_ORDER not in (
        review_evidence.ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS
    )
    assert (
        frozenset({review_evidence.WO024_G1_WORK_ORDER, review_evidence.WO024P_WORK_ORDER})
        == review_evidence.ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS
    )
    review_evidence.require_supported_work_order(review_evidence.WO024P_G1_C1_WORK_ORDER)
    evidence = review_evidence.verify_wo024p_g1_c1_governance_contract(
        review_evidence.WO024P_G1_C1_WORK_ORDER,
        review_evidence.WO024P_G1_C1_BASE_SHA,
        sorted(review_evidence.WO024P_G1_C1_ALLOWED_PATHS),
        {
            "project_brain_changed": False,
            "checkpoint_changed": False,
            "authorized_paths": [],
        },
        {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}},
        {"v01_closure_sprint": v01_closure_evidence_fixture()},
        review_evidence.V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD,
        review_evidence.WO024P_G1_C1_BASE_SHA,
    )
    assert evidence is not None
    assert "work_order=WO-024-P-G1-C1" in evidence
    assert "corrective_outside_active_pair=True" in evidence
    assert "promotion_pair_plus_extra_path=REJECTED" in evidence
    assert "squash_merge_ancestry=REQUIRED" in evidence
    assert "v0.1_completion_claim=False" in evidence
    assert (
        review_evidence.verify_wo024p_g1_c1_governance_contract(
            review_evidence.WO024_WORK_ORDER,
            review_evidence.WO024P_G1_C1_BASE_SHA,
            sorted(review_evidence.WO024P_G1_C1_ALLOWED_PATHS),
            {
                "project_brain_changed": False,
                "checkpoint_changed": False,
                "authorized_paths": [],
            },
            {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}},
            {"v01_closure_sprint": v01_closure_evidence_fixture()},
            review_evidence.V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD,
            None,
        )
        is None
    )


def test_wo024p_g1_c1_is_the_current_work_order_and_stays_bounded() -> None:
    review_evidence.require_current_work_order_authorization(
        review_evidence.WO024P_G1_C1_WORK_ORDER
    )
    for rejected in (
        review_evidence.WO023P_G1_C1_WORK_ORDER,
        review_evidence.WO023P_WORK_ORDER,
        review_evidence.WO023P_G1_WORK_ORDER,
        "WO-032",
        "WO-028-P",
        "WO-999",
    ):
        with pytest.raises(ValueError):
            review_evidence.require_current_work_order_authorization(rejected)
    body = (
        "<!-- HIVE-WORK-ORDER: WO-024-P-G1-C1 -->\n"
        f"<!-- HIVE-AUTHORIZED-BASE: {review_evidence.WO024P_G1_C1_BASE_SHA} -->\n"
    )
    assert review_evidence.parse_work_order_marker(body) == (
        review_evidence.WO024P_G1_C1_WORK_ORDER
    )
    assert (
        review_evidence.authorized_base_marker_sha(review_evidence.WO024P_G1_C1_WORK_ORDER, body)
        == review_evidence.WO024P_G1_C1_BASE_SHA
    )


def test_wo024p_g1_c2_scope_is_bounded_and_fails_closed() -> None:
    allowed = sorted(review_evidence.WO024P_G1_C2_ALLOWED_PATHS)
    review_evidence.require_wo024p_g1_c2_scope(
        review_evidence.WO024P_G1_C2_WORK_ORDER,
        review_evidence.WO024P_G1_C2_BASE_SHA,
        allowed,
        authorized_base_sha=review_evidence.WO024P_G1_C2_BASE_SHA,
    )
    for paths in (
        [],
        ["docs/project-brain/13-CHECKPOINT.md"],
        ["docs/project-brain/CANONICAL-SHA256SUMS.txt"],
        ["migrations/versions/0008_stateful.py"],
        [".github/workflows/ci.yml"],
        ["schemas/review-evidence-v1.schema.json"],
        ["requirements.txt"],
        ["dashboard/package-lock.json"],
        ["VERSION"],
        ["CHANGELOG.md"],
        ["backend/app/context_manager.py"],
        allowed + ["docs/project-brain/CANONICAL-SHA256SUMS.txt"],
    ):
        with pytest.raises(ValueError):
            review_evidence.require_wo024p_g1_c2_scope(
                review_evidence.WO024P_G1_C2_WORK_ORDER,
                review_evidence.WO024P_G1_C2_BASE_SHA,
                paths,
                authorized_base_sha=review_evidence.WO024P_G1_C2_BASE_SHA,
            )
    for base_sha, marker in (
        ("f" * 40, review_evidence.WO024P_G1_C2_BASE_SHA),
        (review_evidence.WO024P_G1_C2_BASE_SHA, None),
        (review_evidence.WO024P_G1_C2_BASE_SHA, "not-a-sha"),
    ):
        with pytest.raises(ValueError):
            review_evidence.require_wo024p_g1_c2_scope(
                review_evidence.WO024P_G1_C2_WORK_ORDER,
                base_sha,
                allowed,
                authorized_base_sha=marker,
            )


def test_wo024p_g1_c2_is_self_hosted_and_never_promotes() -> None:
    assert review_evidence.WO024P_G1_C2_WORK_ORDER in (
        review_evidence.AUTHORIZED_BASE_MARKER_WORK_ORDERS
    )
    assert review_evidence.WO024P_G1_C2_WORK_ORDER not in (
        review_evidence.ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS
    )
    assert (
        frozenset({review_evidence.WO024_G1_WORK_ORDER, review_evidence.WO024P_WORK_ORDER})
        == review_evidence.ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS
    )
    review_evidence.require_current_work_order_authorization(
        review_evidence.WO024P_G1_C2_WORK_ORDER
    )
    review_evidence.require_supported_work_order(review_evidence.WO024P_G1_C2_WORK_ORDER)
    body = (
        "<!-- HIVE-WORK-ORDER: WO-024-P-G1-C2 -->\n"
        f"<!-- HIVE-AUTHORIZED-BASE: {review_evidence.WO024P_G1_C2_BASE_SHA} -->\n"
    )
    assert review_evidence.parse_work_order_marker(body) == (
        review_evidence.WO024P_G1_C2_WORK_ORDER
    )
    assert (
        review_evidence.authorized_base_marker_sha(review_evidence.WO024P_G1_C2_WORK_ORDER, body)
        == review_evidence.WO024P_G1_C2_BASE_SHA
    )
    for malformed in (
        "<!-- HIVE-WORK-ORDER: WO-024-P-G1-C2 -->\n",
        body + f"<!-- HIVE-AUTHORIZED-BASE: {review_evidence.WO024P_G1_C2_BASE_SHA} -->\n",
        "<!-- HIVE-WORK-ORDER: WO-024-P-G1-C2 -->\n<!-- HIVE-AUTHORIZED-BASE: nope -->\n",
    ):
        with pytest.raises(ValueError):
            review_evidence.authorized_base_marker_sha(
                review_evidence.WO024P_G1_C2_WORK_ORDER, malformed
            )


def test_wo024p_g1_c2_governance_evidence_is_emitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closure_text = json.dumps(v01_closure_evidence_fixture())
    monkeypatch.setattr(
        review_evidence,
        "integration_file",
        lambda name: (
            closure_text if name == review_evidence.V01_CLOSURE_SPRINT_EVIDENCE_FILE else ""
        ),
    )
    evidence = review_evidence.verify_wo024p_g1_c2_governance_contract(
        review_evidence.WO024P_G1_C2_WORK_ORDER,
        review_evidence.WO024P_G1_C2_BASE_SHA,
        sorted(review_evidence.WO024P_G1_C2_ALLOWED_PATHS),
        {
            "project_brain_changed": False,
            "checkpoint_changed": False,
            "authorized_paths": [],
        },
        {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}},
        {"v01_closure_sprint": v01_closure_evidence_fixture()},
        review_evidence.V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD,
        review_evidence.WO024P_G1_C2_BASE_SHA,
    )
    assert evidence is not None
    assert "work_order=WO-024-P-G1-C2" in evidence
    assert "checkpoint_regressions_state_independent=True" in evidence
    assert "live_checkpoint_never_a_promotion_base=True" in evidence
    assert "guards_unchanged=require_wo024p_checkpoint_semantics,checkpoint_current" in evidence
    assert "active_promotion_pair_unchanged=True" in evidence
    assert "corrective_outside_active_pair=True" in evidence
    assert "v0.1_promotion_performed=False" in evidence
    assert "v0.1_completion_claim=False" in evidence
    # A different work order is not this contract's business.
    assert (
        review_evidence.verify_wo024p_g1_c2_governance_contract(
            review_evidence.WO024_WORK_ORDER,
            review_evidence.WO024P_G1_C2_BASE_SHA,
            sorted(review_evidence.WO024P_G1_C2_ALLOWED_PATHS),
            {
                "project_brain_changed": False,
                "checkpoint_changed": False,
                "authorized_paths": [],
            },
            {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}},
            {"v01_closure_sprint": v01_closure_evidence_fixture()},
            review_evidence.V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD,
            None,
        )
        is None
    )


def wo024p_benchmark_fixture() -> dict[str, object]:
    """Minimal benchmark mapping sufficient for integration_evidence()."""

    return {
        "status": "PASS",
        "redis_restart": True,
        "api_restart": True,
        "rerank": {"status": "PASS"},
        "query_count": 4,
        "recall_at_1": 1.0,
        "recall_at_5": 1.0,
        "mrr": 1.0,
        "critical_context_misses": 0,
        "two_run_reproducibility": True,
        "cross_project_isolation": True,
        "semantic": {"status": "PASS"},
        "hybrid": {"status": "PASS"},
        "hybrid_recall_at_5_gte_extended_lexical": True,
        "semantic_challenge_recovered": True,
        "semantic_integrity": {},
        "fallback": {},
    }


def measured_closure_fixture() -> dict[str, object]:
    """The measured v01 closure payload consumed by the final-promotion lineage.

    The DoD matrix must agree with its declared counts, so the fixture is built with a
    consistent 46/46 all-pass matrix rather than a declared-only override.
    """

    return v01_closure_evidence_fixture(
        dod_total_count=46,
        dod_pass_count=46,
        dod_items=[
            {
                "item": f"Definition of Done requirement {index}",
                "status": "PASS",
                "evidence_path": "docs/atlas/V0.1-CLOSURE-GAP-REPORT.md",
                "sha256": hashlib.sha256(f"dod-{index}".encode()).hexdigest(),
            }
            for index in range(46)
        ],
    )


class _ClosureSeamReached(Exception):
    """Sentinel raised when the driven manifest build reaches the WO-024-P lineage seam."""

    def __init__(self, payload: object) -> None:
        super().__init__("closure seam reached")
        self.payload = payload


def wo024p_final_promotion_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    closure_payload: object,
) -> dict[str, object]:
    """Drive the real build_manifest path to the WO-024-P closure-to-lineage seam.

    The integration manifest mapping is deliberately left as the real (closure-free) evidence
    mapping, so the regression proves the lineage payload cannot come from it.
    """

    base_sha = review_evidence.WO024P_G1_C3_BASE_SHA
    head_sha = "a" * 40
    seen: dict[str, object] = {}
    monkeypatch.setattr(review_evidence, "read_text", lambda path: "")
    monkeypatch.setattr(
        review_evidence,
        "pull_request_body",
        lambda repository, number: (
            f"<!-- HIVE-WORK-ORDER: {review_evidence.WO024P_WORK_ORDER} -->\n"
            f"<!-- HIVE-AUTHORIZED-BASE: {base_sha} -->\n"
        ),
    )
    monkeypatch.setattr(
        review_evidence,
        "git_value",
        lambda *args, **kwargs: (
            base_sha
            if args[:2] == ("rev-parse", review_evidence.WO012P_PROMOTION_BASE_REF)
            else head_sha
        ),
    )
    monkeypatch.setattr(
        review_evidence,
        "changed_paths",
        lambda *args: sorted(review_evidence.WO024P_PROMOTION_ALLOWED_PATHS),
    )
    monkeypatch.setattr(
        review_evidence,
        "governance_evidence",
        lambda repository, number: {
            "ruleset_unchanged": True,
            "pull_request": {"auto_merge_armed": False},
        },
    )
    monkeypatch.setattr(
        review_evidence, "benchmark_fields", lambda *args, **kwargs: wo024p_benchmark_fixture()
    )
    monkeypatch.setattr(review_evidence, "closure_sprint_evidence", lambda: closure_payload)

    def seam(repository: str, payload: object) -> object:
        seen["payload"] = payload
        seen["repository"] = repository
        raise _ClosureSeamReached(payload)

    monkeypatch.setattr(review_evidence, "fetch_wo024_approved_lineage", seam)
    seen["args"] = {
        "repository": "KayzenRoot/hive",
        "pr_number": 98,
        "work_order": review_evidence.WO024P_WORK_ORDER,
        "base_branch": "main",
        "base_sha": base_sha,
        "head_branch": "governance/wo024-p-final-canonical-promotion",
        "head_sha": head_sha,
        "server_url": "https://github.com",
        "run_id": "35246912961",
        "integration_status": "PASS",
        "ready": True,
        "draft": False,
    }
    return seen


def test_wo024p_final_promotion_lineage_receives_validated_closure_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The final-promotion seam must consume the validated closure payload, not the manifest."""

    payload = measured_closure_fixture()
    seen = wo024p_final_promotion_harness(monkeypatch, closure_payload=payload)
    args = cast(dict[str, object], seen["args"])
    with pytest.raises(_ClosureSeamReached) as reached:
        review_evidence.build_manifest(SimpleNamespace(**args))  # type: ignore[arg-type]
    received = cast(dict[str, object], reached.value.payload)
    assert received["dod_pass_count"] == 46
    assert received["dod_total_count"] == 46
    assert received["status"] == "PASS"
    assert received is payload, "the lineage must receive the validated payload itself"

    # The schema-bound integration manifest still must not expose the closure family.
    integration = review_evidence.integration_evidence(
        wo024p_benchmark_fixture(), work_order=review_evidence.WO024P_WORK_ORDER
    )
    assert "v01_closure_sprint" not in integration
    schema_text = review_evidence.SCHEMA_PATH.read_text(encoding="utf-8")
    assert '"v01_closure_sprint": {' not in schema_text


def test_wo024p_closure_payload_fails_closed_before_any_conversion_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing, failing or incomplete closure evidence must raise a governance error."""

    cases: tuple[tuple[str, object, str], ...] = (
        ("empty payload", {}, "requires validated v01 closure"),
        ("not passing", {"status": "FAIL", "dod_pass_count": 46, "dod_total_count": 46}, "passing"),
        ("unknown", {"status": "UNKNOWN"}, "passing"),
        ("missing counts", {"status": "PASS"}, "measured v01 closure dod_pass_count"),
        (
            "non-integer counts",
            {"status": "PASS", "dod_pass_count": "46", "dod_total_count": "46"},
            "measured v01 closure dod_pass_count",
        ),
        (
            "boolean counts",
            {"status": "PASS", "dod_pass_count": True, "dod_total_count": 46},
            "measured v01 closure dod_pass_count",
        ),
    )
    for _label, payload, expected in cases:
        monkeypatch.setattr(review_evidence, "closure_sprint_evidence", lambda value=payload: value)
        # pytest.raises(ValueError) already proves no raw TypeError can escape.
        with pytest.raises(ValueError, match=expected):
            review_evidence.wo024p_closure_payload()
        # ...and through the whole manifest seam, never as a raw TypeError.
        seen = wo024p_final_promotion_harness(monkeypatch, closure_payload=payload)
        args = cast(dict[str, object], seen["args"])
        with pytest.raises(ValueError, match=expected):
            review_evidence.build_manifest(SimpleNamespace(**args))  # type: ignore[arg-type]


def test_wo024p_lineage_verifier_fails_closed_on_incomplete_closure_payload() -> None:
    """The verifier itself must reject an incomplete closure payload by design."""

    for _label, payload in (
        ("empty", {}),
        ("status only", {"status": "PASS"}),
        ("counts without status", {"dod_pass_count": 46, "dod_total_count": 46}),
    ):
        sources = wo024_approved_lineage_sources(closure_evidence=payload)
        # pytest.raises(ValueError) already proves no raw TypeError can escape.
        with pytest.raises(ValueError):
            review_evidence.verify_wo024_approved_lineage(sources)


def test_wo024p_g1_c3_scope_is_bounded_and_fails_closed() -> None:
    allowed = sorted(review_evidence.WO024P_G1_C3_ALLOWED_PATHS)
    review_evidence.require_wo024p_g1_c3_scope(
        review_evidence.WO024P_G1_C3_WORK_ORDER,
        review_evidence.WO024P_G1_C3_BASE_SHA,
        allowed,
        authorized_base_sha=review_evidence.WO024P_G1_C3_BASE_SHA,
    )
    for paths in (
        [],
        ["docs/project-brain/13-CHECKPOINT.md"],
        ["docs/project-brain/CANONICAL-SHA256SUMS.txt"],
        ["schemas/review-evidence-v1.schema.json"],
        ["migrations/versions/0009_wiring.py"],
        [".github/workflows/ci.yml"],
        ["requirements.txt"],
        ["VERSION"],
        ["backend/app/context_manager.py"],
        ["backend/tests/test_v01_closure_sprint.py"],
        allowed + ["docs/project-brain/13-CHECKPOINT.md"],
    ):
        with pytest.raises(ValueError):
            review_evidence.require_wo024p_g1_c3_scope(
                review_evidence.WO024P_G1_C3_WORK_ORDER,
                review_evidence.WO024P_G1_C3_BASE_SHA,
                paths,
                authorized_base_sha=review_evidence.WO024P_G1_C3_BASE_SHA,
            )
    for base_sha, marker in (
        ("b" * 40, review_evidence.WO024P_G1_C3_BASE_SHA),
        (review_evidence.WO024P_G1_C3_BASE_SHA, None),
        (review_evidence.WO024P_G1_C3_BASE_SHA, "nope"),
    ):
        with pytest.raises(ValueError):
            review_evidence.require_wo024p_g1_c3_scope(
                review_evidence.WO024P_G1_C3_WORK_ORDER,
                base_sha,
                allowed,
                authorized_base_sha=marker,
            )


def test_wo024p_g1_c3_is_self_hosted_and_never_promotes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert review_evidence.WO024P_G1_C3_WORK_ORDER in (
        review_evidence.AUTHORIZED_BASE_MARKER_WORK_ORDERS
    )
    assert review_evidence.WO024P_G1_C3_WORK_ORDER not in (
        review_evidence.ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS
    )
    assert (
        frozenset({review_evidence.WO024_G1_WORK_ORDER, review_evidence.WO024P_WORK_ORDER})
        == review_evidence.ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS
    )
    review_evidence.require_current_work_order_authorization(
        review_evidence.WO024P_G1_C3_WORK_ORDER
    )
    review_evidence.require_supported_work_order(review_evidence.WO024P_G1_C3_WORK_ORDER)
    body = (
        "<!-- HIVE-WORK-ORDER: WO-024-P-G1-C3 -->\n"
        f"<!-- HIVE-AUTHORIZED-BASE: {review_evidence.WO024P_G1_C3_BASE_SHA} -->\n"
    )
    assert review_evidence.parse_work_order_marker(body) == (
        review_evidence.WO024P_G1_C3_WORK_ORDER
    )
    assert (
        review_evidence.authorized_base_marker_sha(review_evidence.WO024P_G1_C3_WORK_ORDER, body)
        == review_evidence.WO024P_G1_C3_BASE_SHA
    )
    for malformed in (
        "<!-- HIVE-WORK-ORDER: WO-024-P-G1-C3 -->\n",
        body + f"<!-- HIVE-AUTHORIZED-BASE: {review_evidence.WO024P_G1_C3_BASE_SHA} -->\n",
        "<!-- HIVE-WORK-ORDER: WO-024-P-G1-C3 -->\n<!-- HIVE-AUTHORIZED-BASE: nope -->\n",
    ):
        with pytest.raises(ValueError):
            review_evidence.authorized_base_marker_sha(
                review_evidence.WO024P_G1_C3_WORK_ORDER, malformed
            )
    # The contract proves the schema-bound manifest keeps the closure family out and that the
    # lineage source is the validated reader.
    monkeypatch.setattr(review_evidence, "closure_sprint_evidence", measured_closure_fixture)
    evidence = review_evidence.verify_wo024p_g1_c3_governance_contract(
        review_evidence.WO024P_G1_C3_WORK_ORDER,
        review_evidence.WO024P_G1_C3_BASE_SHA,
        sorted(review_evidence.WO024P_G1_C3_ALLOWED_PATHS),
        {
            "project_brain_changed": False,
            "checkpoint_changed": False,
            "authorized_paths": [],
        },
        {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}},
        {"comprehensive_benchmarks": {}},
        review_evidence.V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD,
        review_evidence.WO024P_G1_C3_BASE_SHA,
    )
    assert evidence is not None
    assert "work_order=WO-024-P-G1-C3" in evidence
    assert "closure_lineage_wiring_source=closure_sprint_evidence" in evidence
    assert "closure_payload_dod=46/46" in evidence
    assert "incomplete_closure_fails_closed=ValueError" in evidence
    assert "schema_bound_manifest_omits_v01_closure_sprint=True" in evidence
    assert "current_main_association_rediscovery=False" in evidence
    assert "active_promotion_pair_unchanged=True" in evidence
    assert "v0.1_promotion_performed=False" in evidence
    assert "auto_merge=UNARMED" in evidence
    # A manifest integration mapping that (wrongly) exposes the family is refused.
    with pytest.raises(ValueError, match="schema-bound manifest"):
        review_evidence.verify_wo024p_g1_c3_governance_contract(
            review_evidence.WO024P_G1_C3_WORK_ORDER,
            review_evidence.WO024P_G1_C3_BASE_SHA,
            sorted(review_evidence.WO024P_G1_C3_ALLOWED_PATHS),
            {
                "project_brain_changed": False,
                "checkpoint_changed": False,
                "authorized_paths": [],
            },
            {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}},
            {"v01_closure_sprint": v01_closure_evidence_fixture()},
            review_evidence.V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD,
            review_evidence.WO024P_G1_C3_BASE_SHA,
        )
    assert (
        review_evidence.verify_wo024p_g1_c3_governance_contract(
            review_evidence.WO024_WORK_ORDER,
            review_evidence.WO024P_G1_C3_BASE_SHA,
            sorted(review_evidence.WO024P_G1_C3_ALLOWED_PATHS),
            {
                "project_brain_changed": False,
                "checkpoint_changed": False,
                "authorized_paths": [],
            },
            {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}},
            {"comprehensive_benchmarks": {}},
            review_evidence.V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD,
            None,
        )
        is None
    )


def wo024p_governance_harness(
    monkeypatch: pytest.MonkeyPatch,
    pr_body: str,
    *,
    base_sha: str | None = None,
    changed: list[str] | None = None,
    closure_payload: object | None = None,
    stub_checkpoint_semantics: bool = False,
) -> dict[str, object]:
    """Drive the real build_manifest path through the WO-024-P governance contract.

    The contract is exercised unchanged; only its inputs are bounded. A spy around
    require_wo024p_scope records the authorized-base value the contract forwards and then
    delegates to the real guard, so fail-closed behaviour is preserved.
    """

    resolved_base = base_sha or review_evidence.WO024P_G1_C4_BASE_SHA
    head_sha = "a" * 40
    seen: dict[str, object] = {"scope_calls": []}
    real_scope = review_evidence.require_wo024p_scope
    payload = closure_payload if closure_payload is not None else measured_closure_fixture()

    def spy_scope(
        work_order: str, scope_base: str, scope_paths: list[str], **kwargs: object
    ) -> None:
        cast("list[object]", seen["scope_calls"]).append(
            (work_order, scope_base, list(scope_paths), kwargs)
        )
        real_scope(work_order, scope_base, scope_paths, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(review_evidence, "read_text", lambda path: "")
    monkeypatch.setattr(review_evidence, "pull_request_body", lambda repository, number: pr_body)
    monkeypatch.setattr(
        review_evidence,
        "git_value",
        lambda *args, **kwargs: (
            resolved_base
            if args[:2] == ("rev-parse", review_evidence.WO012P_PROMOTION_BASE_REF)
            else head_sha
        ),
    )
    monkeypatch.setattr(
        review_evidence,
        "changed_paths",
        lambda *args: (
            changed
            if changed is not None
            else sorted(review_evidence.WO024P_PROMOTION_ALLOWED_PATHS)
        ),
    )
    monkeypatch.setattr(
        review_evidence,
        "governance_evidence",
        lambda repository, number: {
            "ruleset_unchanged": True,
            "pull_request": {"auto_merge_armed": False},
        },
    )
    monkeypatch.setattr(
        review_evidence, "benchmark_fields", lambda *args, **kwargs: wo024p_benchmark_fixture()
    )
    monkeypatch.setattr(review_evidence, "closure_sprint_evidence", lambda: payload)
    monkeypatch.setattr(
        review_evidence,
        "fetch_wo024_approved_lineage",
        # the real verifier produces the complete closed-contract lineage statement
        lambda repository, closure: review_evidence.verify_wo024_approved_lineage(
            wo024_approved_lineage_sources(closure_evidence=payload)
        ),
    )
    monkeypatch.setattr(review_evidence, "require_wo024p_scope", spy_scope)
    if stub_checkpoint_semantics:
        # The checkpoint grammar is state-dependent (the working tree holds either the
        # pre-promotion or the promoted checkpoint); it is covered by the closure-sprint
        # regressions. This harness isolates the authorized-base propagation path.
        monkeypatch.setattr(
            review_evidence, "require_wo024p_checkpoint_semantics", lambda *args, **kwargs: None
        )
    seen["args"] = {
        "repository": "KayzenRoot/hive",
        "pr_number": 98,
        "work_order": review_evidence.WO024P_WORK_ORDER,
        "base_branch": "main",
        "base_sha": resolved_base,
        "head_branch": "governance/wo024-p-final-canonical-promotion",
        "head_sha": head_sha,
        "server_url": "https://github.com",
        "run_id": "35262112726",
        "integration_status": "PASS",
        "ready": True,
        "draft": False,
    }
    return seen


def wo024p_promotion_body(marker: str | None, *, extra_marker: str | None = None) -> str:
    body = f"<!-- HIVE-WORK-ORDER: {review_evidence.WO024P_WORK_ORDER} -->\n"
    if marker is not None:
        body += f"<!-- HIVE-AUTHORIZED-BASE: {marker} -->\n"
    if extra_marker is not None:
        body += f"<!-- HIVE-AUTHORIZED-BASE: {extra_marker} -->\n"
    return body


def test_wo024p_governance_contract_receives_the_parsed_authorized_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid final-promotion body must not be rejected for a dropped marker value."""

    base_sha = review_evidence.WO024P_G1_C4_BASE_SHA
    seen = wo024p_governance_harness(
        monkeypatch, wo024p_promotion_body(base_sha), stub_checkpoint_semantics=True
    )
    args = cast(dict[str, object], seen["args"])
    # The valid promotion body must no longer die on the dropped marker value. Any later,
    # state-dependent failure is unrelated to this contract.
    try:
        review_evidence.build_manifest(SimpleNamespace(**args))  # type: ignore[arg-type]
    except ValueError as exc:
        assert "authorized-base marker" not in str(exc), exc

    calls = cast(list[tuple[str, str, list[str], dict[str, object]]], seen["scope_calls"])
    assert calls, "the WO-024-P scope guard must be reached"
    _work_order, scope_base, scope_paths, kwargs = calls[0]
    assert scope_base == base_sha
    assert kwargs.get("authorized_base_sha") == base_sha, "the parsed marker must be forwarded"
    assert kwargs.get("enforce_authorized_base") is True, "marker enforcement stays on"
    assert sorted(scope_paths) == sorted(review_evidence.WO024P_PROMOTION_ALLOWED_PATHS)

    # With the checkpoint grammar in place the contract reaches its success evidence.
    evidence = review_evidence.verify_wo024p_governance_contract(
        review_evidence.WO024P_WORK_ORDER,
        base_sha,
        sorted(review_evidence.WO024P_PROMOTION_ALLOWED_PATHS),
        {
            "project_brain_changed": True,
            "checkpoint_changed": True,
            "authorized_paths": sorted(review_evidence.WO024P_PROMOTION_ALLOWED_PATHS),
        },
        {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}},
        {},
        review_evidence.V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD,
        review_evidence.verify_wo024_approved_lineage(
            wo024_approved_lineage_sources(closure_evidence=measured_closure_fixture())
        ),
        base_sha,
    )
    assert evidence is not None
    assert "promotion_scope=PASS" in evidence
    assert "checkpoint_semantics=PASS" in evidence
    assert "manifest_contract=PASS" in evidence
    assert "closure_evidence=PASS" in evidence
    assert "approved_lineage=PASS" in evidence
    assert "dod_matrix=PASS" in evidence


@pytest.mark.parametrize(
    "case",
    (
        pytest.param("missing", id="missing-marker"),
        pytest.param("duplicate", id="duplicate-marker"),
        pytest.param("uppercase", id="uppercase-marker"),
        pytest.param("short", id="malformed-marker"),
        pytest.param("different", id="marker-not-the-base"),
        pytest.param("drifted-base", id="wrong-protected-main"),
        pytest.param("extra-path", id="extra-changed-path"),
    ),
)
def test_wo024p_final_promotion_marker_matrix_fails_closed(
    monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    """Every divergent marker, base or scope case stays fail closed."""

    base_sha = review_evidence.WO024P_G1_C4_BASE_SHA
    resolved_base: str | None = None
    changed: list[str] | None = None
    if case == "missing":
        body = wo024p_promotion_body(None)
    elif case == "duplicate":
        body = wo024p_promotion_body(base_sha, extra_marker=base_sha)
    elif case == "uppercase":
        body = wo024p_promotion_body(base_sha.upper())
    elif case == "short":
        body = wo024p_promotion_body("0df7bb1")
    elif case == "different":
        body = wo024p_promotion_body("f" * 40)
    else:
        body = wo024p_promotion_body(base_sha)
    if case == "drifted-base":
        resolved_base = "a5cc341375a0cc067edc52db4ff2dc36b66a8c00"
    if case == "extra-path":
        changed = sorted(review_evidence.WO024P_PROMOTION_ALLOWED_PATHS) + [
            "scripts/review_evidence.py"
        ]
    seen = wo024p_governance_harness(monkeypatch, body, base_sha=resolved_base, changed=changed)
    args = cast(dict[str, object], seen["args"])
    with pytest.raises(ValueError):
        review_evidence.build_manifest(SimpleNamespace(**args))  # type: ignore[arg-type]


def test_wo024p_g1_c4_scope_is_bounded_and_fails_closed() -> None:
    allowed = sorted(review_evidence.WO024P_G1_C4_ALLOWED_PATHS)
    review_evidence.require_wo024p_g1_c4_scope(
        review_evidence.WO024P_G1_C4_WORK_ORDER,
        review_evidence.WO024P_G1_C4_BASE_SHA,
        allowed,
        authorized_base_sha=review_evidence.WO024P_G1_C4_BASE_SHA,
    )
    for paths in (
        [],
        ["docs/project-brain/13-CHECKPOINT.md"],
        ["docs/project-brain/CANONICAL-SHA256SUMS.txt"],
        ["schemas/review-evidence-v1.schema.json"],
        ["migrations/versions/0010_marker.py"],
        [".github/workflows/ci.yml"],
        ["requirements.txt"],
        ["VERSION"],
        ["backend/tests/test_v01_closure_sprint.py"],
        ["backend/app/context_manager.py"],
        allowed + ["docs/project-brain/13-CHECKPOINT.md"],
    ):
        with pytest.raises(ValueError):
            review_evidence.require_wo024p_g1_c4_scope(
                review_evidence.WO024P_G1_C4_WORK_ORDER,
                review_evidence.WO024P_G1_C4_BASE_SHA,
                paths,
                authorized_base_sha=review_evidence.WO024P_G1_C4_BASE_SHA,
            )
    for base_sha, marker in (
        ("9" * 40, review_evidence.WO024P_G1_C4_BASE_SHA),
        (review_evidence.WO024P_G1_C4_BASE_SHA, None),
        (review_evidence.WO024P_G1_C4_BASE_SHA, "nope"),
        (review_evidence.WO024P_G1_C4_BASE_SHA, review_evidence.WO024P_G1_C4_BASE_SHA.upper()),
    ):
        with pytest.raises(ValueError):
            review_evidence.require_wo024p_g1_c4_scope(
                review_evidence.WO024P_G1_C4_WORK_ORDER,
                base_sha,
                allowed,
                authorized_base_sha=marker,
            )


def test_wo024p_g1_c4_is_self_hosted_and_never_promotes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert review_evidence.WO024P_G1_C4_WORK_ORDER in (
        review_evidence.AUTHORIZED_BASE_MARKER_WORK_ORDERS
    )
    assert review_evidence.WO024P_G1_C4_WORK_ORDER not in (
        review_evidence.ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS
    )
    assert (
        frozenset({review_evidence.WO024_G1_WORK_ORDER, review_evidence.WO024P_WORK_ORDER})
        == review_evidence.ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS
    )
    review_evidence.require_current_work_order_authorization(
        review_evidence.WO024P_G1_C4_WORK_ORDER
    )
    review_evidence.require_supported_work_order(review_evidence.WO024P_G1_C4_WORK_ORDER)
    body = (
        "<!-- HIVE-WORK-ORDER: WO-024-P-G1-C4 -->\n"
        f"<!-- HIVE-AUTHORIZED-BASE: {review_evidence.WO024P_G1_C4_BASE_SHA} -->\n"
    )
    assert review_evidence.parse_work_order_marker(body) == (
        review_evidence.WO024P_G1_C4_WORK_ORDER
    )
    assert (
        review_evidence.authorized_base_marker_sha(review_evidence.WO024P_G1_C4_WORK_ORDER, body)
        == review_evidence.WO024P_G1_C4_BASE_SHA
    )
    for malformed in (
        "<!-- HIVE-WORK-ORDER: WO-024-P-G1-C4 -->\n",
        body + f"<!-- HIVE-AUTHORIZED-BASE: {review_evidence.WO024P_G1_C4_BASE_SHA} -->\n",
        "<!-- HIVE-WORK-ORDER: WO-024-P-G1-C4 -->\n<!-- HIVE-AUTHORIZED-BASE: nope -->\n",
    ):
        with pytest.raises(ValueError):
            review_evidence.authorized_base_marker_sha(
                review_evidence.WO024P_G1_C4_WORK_ORDER, malformed
            )
    evidence = review_evidence.verify_wo024p_g1_c4_governance_contract(
        review_evidence.WO024P_G1_C4_WORK_ORDER,
        review_evidence.WO024P_G1_C4_BASE_SHA,
        sorted(review_evidence.WO024P_G1_C4_ALLOWED_PATHS),
        {
            "project_brain_changed": False,
            "checkpoint_changed": False,
            "authorized_paths": [],
        },
        {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}},
        {},
        review_evidence.V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD,
        review_evidence.WO024P_G1_C4_BASE_SHA,
    )
    assert evidence is not None
    assert "work_order=WO-024-P-G1-C4" in evidence
    assert "authorized_base_marker_forwarded_into_require_wo024p_scope=True" in evidence
    assert "marker_reparsed_from_body=False" in evidence
    assert "enforce_authorized_base_preserved_in_build=True" in evidence
    assert "active_promotion_pair_unchanged=True" in evidence
    assert "v0.1_promotion_performed=False" in evidence
    assert "auto_merge=UNARMED" in evidence
    with pytest.raises(ValueError, match="schema-bound manifest"):
        review_evidence.verify_wo024p_g1_c4_governance_contract(
            review_evidence.WO024P_G1_C4_WORK_ORDER,
            review_evidence.WO024P_G1_C4_BASE_SHA,
            sorted(review_evidence.WO024P_G1_C4_ALLOWED_PATHS),
            {
                "project_brain_changed": False,
                "checkpoint_changed": False,
                "authorized_paths": [],
            },
            {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}},
            {"v01_closure_sprint": {}},
            review_evidence.V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD,
            review_evidence.WO024P_G1_C4_BASE_SHA,
        )
    assert (
        review_evidence.verify_wo024p_g1_c4_governance_contract(
            review_evidence.WO024_WORK_ORDER,
            review_evidence.WO024P_G1_C4_BASE_SHA,
            sorted(review_evidence.WO024P_G1_C4_ALLOWED_PATHS),
            {
                "project_brain_changed": False,
                "checkpoint_changed": False,
                "authorized_paths": [],
            },
            {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}},
            {},
            review_evidence.V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD,
            None,
        )
        is None
    )


def wo025_planning_paths_fixture() -> list[str]:
    """Representative post-1.0 planning documentation paths from the planning frontier."""

    return [
        "docs/project-brain/17-POST-1.0-EVOLUTION-ROADMAP.md",
        "docs/project-brain/19-DECISION-FABRIC-1.1-SPEC.md",
        "docs/project-brain/21-DECISION-FABRIC-CONTRACTS-BENCHMARKS.md",
        "docs/project-brain/49-DECISION-FABRIC-1.1-PLANNING-FREEZE.md",
        "docs/project-brain/work-orders/WO-1.1-01-DECISION-CONTRACT-DETERMINISTIC-RESOLVER.md",
    ]


def test_wo025_g1_scope_is_bounded_and_base_bound() -> None:
    allowed = sorted(review_evidence.WO025_G1_ALLOWED_PATHS)
    review_evidence.require_wo025_g1_scope(
        review_evidence.WO025_G1_WORK_ORDER,
        review_evidence.WO025_G1_BASE_SHA,
        allowed,
        authorized_base_sha=review_evidence.WO025_G1_BASE_SHA,
    )
    for paths in (
        [],
        ["docs/project-brain/13-CHECKPOINT.md"],
        ["docs/project-brain/CANONICAL-SHA256SUMS.txt"],
        ["migrations/versions/0010_bridge.py"],
        [".github/workflows/ci.yml"],
        ["requirements.txt"],
        ["VERSION"],
        ["backend/app/decision_resolver.py"],
        allowed + ["backend/app/main.py"],
    ):
        with pytest.raises(ValueError):
            review_evidence.require_wo025_g1_scope(
                review_evidence.WO025_G1_WORK_ORDER,
                review_evidence.WO025_G1_BASE_SHA,
                paths,
                authorized_base_sha=review_evidence.WO025_G1_BASE_SHA,
            )
    for base_sha, marker in (
        ("f" * 40, review_evidence.WO025_G1_BASE_SHA),
        (review_evidence.WO025_G1_BASE_SHA, None),
        (review_evidence.WO025_G1_BASE_SHA, "nope"),
    ):
        with pytest.raises(ValueError):
            review_evidence.require_wo025_g1_scope(
                review_evidence.WO025_G1_WORK_ORDER,
                base_sha,
                allowed,
                authorized_base_sha=marker,
            )


def test_wo025_g1_is_self_hosted_and_keeps_the_historical_pair() -> None:
    assert review_evidence.WO025_G1_WORK_ORDER in (
        review_evidence.AUTHORIZED_BASE_MARKER_WORK_ORDERS
    )
    assert review_evidence.WO025_G1_WORK_ORDER not in (
        review_evidence.ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS
    )
    assert (
        frozenset({review_evidence.WO024_G1_WORK_ORDER, review_evidence.WO024P_WORK_ORDER})
        == review_evidence.ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS
    )
    review_evidence.require_current_work_order_authorization(review_evidence.WO025_G1_WORK_ORDER)
    review_evidence.require_supported_work_order(review_evidence.WO025_G1_WORK_ORDER)
    body = (
        "<!-- HIVE-WORK-ORDER: WO-025-G1 -->\n"
        f"<!-- HIVE-AUTHORIZED-BASE: {review_evidence.WO025_G1_BASE_SHA} -->\n"
    )
    assert review_evidence.parse_work_order_marker(body) == (review_evidence.WO025_G1_WORK_ORDER)
    assert (
        review_evidence.authorized_base_marker_sha(review_evidence.WO025_G1_WORK_ORDER, body)
        == review_evidence.WO025_G1_BASE_SHA
    )


def test_wo025_planning_scope_accepts_planning_documentation_only() -> None:
    planning = wo025_planning_paths_fixture()
    assert review_evidence.wo025_planning_scope(planning) == []
    rejected = (
        "backend/app/retrieval.py",
        "dashboard/src/App.tsx",
        "migrations/versions/0008_planning.py",
        "requirements.txt",
        "pyproject.toml",
        ".github/workflows/ci.yml",
        "VERSION",
        "CHANGELOG.md",
        "docs/project-brain/13-CHECKPOINT.md",
        "docs/project-brain/16-DECISIONS-LEDGER.md",
        "docs/project-brain/CANONICAL-SHA256SUMS.txt",
        "docs/project-brain/50-future-plan.md",
        "docs/project-brain/work-orders/notes.txt",
    )
    for path in rejected:
        assert review_evidence.wo025_planning_scope([path]) == [path], path


def test_wo025_is_registered_as_planning_only_promotion() -> None:
    assert review_evidence.WO025_WORK_ORDER in review_evidence.AUTHORIZED_BASE_MARKER_WORK_ORDERS
    review_evidence.require_supported_work_order(review_evidence.WO025_WORK_ORDER)
    assert review_evidence.WO025_WORK_ORDER not in (
        review_evidence.ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS
    )
    assert review_evidence.registered_promotion_base_sha(review_evidence.WO025_WORK_ORDER)
    planning = wo025_planning_paths_fixture()
    base_sha = review_evidence.registered_promotion_base_sha(review_evidence.WO025_WORK_ORDER)
    review_evidence.require_wo025_scope(
        review_evidence.WO025_WORK_ORDER,
        base_sha,
        planning,
        registered_base_sha=base_sha,
        authorized_base_sha=base_sha,
    )
    with pytest.raises(ValueError, match="outside the post-1.0 planning surface"):
        review_evidence.require_wo025_scope(
            review_evidence.WO025_WORK_ORDER,
            base_sha,
            planning + ["backend/app/main.py"],
            registered_base_sha=base_sha,
            authorized_base_sha=base_sha,
        )
    with pytest.raises(ValueError):
        review_evidence.require_wo025_scope(
            review_evidence.WO025_WORK_ORDER,
            "0" * 40,
            planning,
            registered_base_sha=base_sha,
            authorized_base_sha="0" * 40,
        )
    for overrides in ({"ruleset_unchanged": False}, {"pull_request": {"auto_merge_armed": True}}):
        governance = {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}}
        governance.update(overrides)
        with pytest.raises(ValueError):
            review_evidence.verify_wo025_governance_contract(
                review_evidence.WO025_WORK_ORDER,
                base_sha,
                planning,
                {
                    "project_brain_changed": True,
                    "checkpoint_changed": False,
                    "authorized_paths": [],
                },
                governance,
                {},
                review_evidence.V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD,
                base_sha,
            )


def test_unknown_future_work_orders_stay_fail_closed() -> None:
    # WO-025 became current-authorized in WO-025-G2; the unknown frontier stays rejected.
    review_evidence.require_supported_work_order(review_evidence.WO025_WORK_ORDER)
    for unknown in ("WO-032", "WO-028-P", "WO-999-P"):
        with pytest.raises(ValueError):
            review_evidence.require_current_work_order_authorization(unknown)


def test_pull_request_work_order_resolves_from_the_event_payload(
    tmp_path: Path,
) -> None:
    payload = tmp_path / "event.json"
    payload.write_text(
        json.dumps({"pull_request": {"body": "<!-- HIVE-WORK-ORDER: WO-025 -->"}}),
        encoding="utf-8",
    )
    assert review_evidence.pull_request_work_order_from_event(str(payload)) == (
        review_evidence.WO025_WORK_ORDER
    )

    missing_marker = tmp_path / "missing.json"
    missing_marker.write_text(
        json.dumps({"pull_request": {"body": "no marker here"}}), encoding="utf-8"
    )
    assert review_evidence.pull_request_work_order_from_event(str(missing_marker)) is None

    non_pr = tmp_path / "push.json"
    non_pr.write_text(json.dumps({"ref": "refs/heads/main"}), encoding="utf-8")
    assert review_evidence.pull_request_work_order_from_event(str(non_pr)) is None

    duplicated = tmp_path / "duplicated.json"
    duplicated.write_text(
        json.dumps(
            {
                "pull_request": {
                    "body": "<!-- HIVE-WORK-ORDER: WO-025 -->\n<!-- HIVE-WORK-ORDER: WO-025-G1 -->"
                }
            }
        ),
        encoding="utf-8",
    )
    assert review_evidence.pull_request_work_order_from_event(str(duplicated)) is None

    assert review_evidence.pull_request_work_order_from_event(str(tmp_path / "absent.json")) is None


def test_wo025_g2_scope_is_bounded_and_base_bound() -> None:
    allowed = sorted(review_evidence.WO025_G2_ALLOWED_PATHS)
    review_evidence.require_wo025_g2_scope(
        review_evidence.WO025_G2_WORK_ORDER,
        review_evidence.WO025_G2_BASE_SHA,
        allowed,
        authorized_base_sha=review_evidence.WO025_G2_BASE_SHA,
    )
    for paths in (
        [],
        ["docs/project-brain/13-CHECKPOINT.md"],
        ["docs/project-brain/CANONICAL-SHA256SUMS.txt"],
        ["docs/project-brain/17-POST-1.0-EVOLUTION-ROADMAP.md"],
        ["migrations/versions/0010_planning.py"],
        [".github/workflows/ci.yml"],
        ["requirements.txt"],
        ["VERSION"],
        ["backend/app/decision_resolver.py"],
        allowed + ["backend/app/main.py"],
    ):
        with pytest.raises(ValueError):
            review_evidence.require_wo025_g2_scope(
                review_evidence.WO025_G2_WORK_ORDER,
                review_evidence.WO025_G2_BASE_SHA,
                paths,
                authorized_base_sha=review_evidence.WO025_G2_BASE_SHA,
            )
    for base_sha, marker in (
        ("f" * 40, review_evidence.WO025_G2_BASE_SHA),
        (review_evidence.WO025_G2_BASE_SHA, None),
        (review_evidence.WO025_G2_BASE_SHA, "nope"),
        (review_evidence.WO025_G2_BASE_SHA, review_evidence.WO025_G2_BASE_SHA.upper()),
    ):
        with pytest.raises(ValueError):
            review_evidence.require_wo025_g2_scope(
                review_evidence.WO025_G2_WORK_ORDER,
                base_sha,
                allowed,
                authorized_base_sha=marker,
            )


def test_wo025_is_now_current_authorized_and_wo029_stays_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WO-025-G2 authorizes the planning promotion; the unknown frontier stays rejected."""

    review_evidence.require_current_work_order_authorization(review_evidence.WO025_WORK_ORDER)
    review_evidence.require_supported_work_order(review_evidence.WO025_G2_WORK_ORDER)
    review_evidence.require_current_work_order_authorization(review_evidence.WO025_G2_WORK_ORDER)
    assert frozenset() == review_evidence.PENDING_PLANNING_PROMOTION_WORK_ORDERS
    assert (
        frozenset({review_evidence.WO024_G1_WORK_ORDER, review_evidence.WO024P_WORK_ORDER})
        == review_evidence.ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS
    )
    for unknown in ("WO-032", "WO-028-P", "WO-999-P"):
        with pytest.raises(ValueError):
            review_evidence.require_current_work_order_authorization(unknown)
        with pytest.raises(ValueError):
            review_evidence.require_supported_work_order(unknown)

    # The pending registry still fails closed for a registered-but-not-yet-authorized promotion.
    monkeypatch.setattr(
        review_evidence,
        "PENDING_PLANNING_PROMOTION_WORK_ORDERS",
        frozenset({review_evidence.WO025_WORK_ORDER}),
    )
    with pytest.raises(ValueError, match="not authorized as a current work order"):
        review_evidence.require_current_work_order_authorization(review_evidence.WO025_WORK_ORDER)


def test_wo025_g2_governance_evidence_is_emitted(monkeypatch: pytest.MonkeyPatch) -> None:
    closure_text = json.dumps(v01_closure_evidence_fixture())
    monkeypatch.setattr(
        review_evidence,
        "integration_file",
        lambda name: (
            closure_text if name == review_evidence.V01_CLOSURE_SPRINT_EVIDENCE_FILE else ""
        ),
    )
    evidence = review_evidence.verify_wo025_g2_governance_contract(
        review_evidence.WO025_G2_WORK_ORDER,
        review_evidence.WO025_G2_BASE_SHA,
        sorted(review_evidence.WO025_G2_ALLOWED_PATHS),
        {
            "project_brain_changed": False,
            "checkpoint_changed": False,
            "authorized_paths": [],
        },
        {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}},
        {"v01_closure_sprint": v01_closure_evidence_fixture()},
        review_evidence.V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD,
        review_evidence.WO025_G2_BASE_SHA,
    )
    assert evidence is not None
    assert "work_order=WO-025-G2" in evidence
    assert "wo025_current_authorized=True" in evidence
    assert "unknown_WO-028_WO-028-P_WO-999-P=REJECTED" in evidence
    assert "wo025_renderer=dedicated_planning_only" in evidence
    assert "stale_semantic_retrieval_fallback_reachable_for_WO-025=False" in evidence
    assert "historical_promotion_pair_unchanged=True" in evidence
    assert "planning_documents_promoted=False" in evidence
    assert "auto_merge=UNARMED" in evidence
    assert (
        review_evidence.verify_wo025_g2_governance_contract(
            review_evidence.WO024_WORK_ORDER,
            review_evidence.WO025_G2_BASE_SHA,
            sorted(review_evidence.WO025_G2_ALLOWED_PATHS),
            {
                "project_brain_changed": False,
                "checkpoint_changed": False,
                "authorized_paths": [],
            },
            {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}},
            {"v01_closure_sprint": v01_closure_evidence_fixture()},
            review_evidence.V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD,
            None,
        )
        is None
    )


STALE_WO025_RENDERER_PHRASES = (
    "0005_semantic_retrieval",
    "pgvector",
    "reranking",
    "retrieval semântico",
    "fusão híbrida",
    "embeddings",
    "WO-006",
)


def wo025_render_arguments() -> dict[str, object]:
    return {
        "pr_number": 125,
        "branch": "governance/wo025-planning-promotion",
        "artifact_name": "hive-review-evidence-WO-025-fixture",
        "ruleset_before": "21934284",
        "ruleset_after": "21934284",
        "merge_before": "squash",
        "merge_after": "squash",
    }


def test_wo025_renderer_is_dedicated_planning_only() -> None:
    import scripts.review_pr_body as renderer

    body = renderer.render_body(
        work_order=review_evidence.WO025_WORK_ORDER,
        base_sha="a" * 40,
        head_sha="b" * 40,
        **cast(dict[str, Any], wo025_render_arguments()),
    )
    assert body.startswith("<!-- HIVE-WORK-ORDER: WO-025 -->")
    assert f"<!-- HIVE-AUTHORIZED-BASE: {'a' * 40} -->" in body
    assert "AWAITING_SOL" in body
    assert "WO-025 READY FOR SOL AUDIT" in body
    assert "promove somente documentação de planejamento pós-1.0" in body
    for phrase in (
        "sem implementação de produto",
        "sem promoção de checkpoint",
        "sem merge",
        "auto-merge desarmado",
    ):
        assert phrase.casefold() in body.casefold(), phrase
    for stale in STALE_WO025_RENDERER_PHRASES:
        assert stale not in body, f"WO-025 renderer must not emit stale text: {stale}"


def test_wo025_g2_renderer_is_dedicated_governance_only() -> None:
    import scripts.review_pr_body as renderer

    body = renderer.render_body(
        work_order=review_evidence.WO025_G2_WORK_ORDER,
        base_sha=review_evidence.WO025_G2_BASE_SHA,
        head_sha="b" * 40,
        **cast(dict[str, Any], wo025_render_arguments()),
    )
    assert body.startswith("<!-- HIVE-WORK-ORDER: WO-025-G2 -->")
    assert f"<!-- HIVE-AUTHORIZED-BASE: {review_evidence.WO025_G2_BASE_SHA} -->" in body
    assert "AWAITING_SOL" in body
    assert "WO-025-G2 READY FOR SOL AUDIT" in body
    assert "WO-025" in body
    for stale in STALE_WO025_RENDERER_PHRASES:
        assert stale not in body, f"WO-025-G2 renderer must not emit stale text: {stale}"
    # The renderer base pin is exact and fails closed for a stale base.
    with pytest.raises(ValueError):
        renderer.render_body(
            work_order=review_evidence.WO025_G2_WORK_ORDER,
            base_sha="f" * 40,
            head_sha="b" * 40,
            **cast(dict[str, Any], wo025_render_arguments()),
        )


# WO-025-G3: work-order namespace governance. These regressions pin the deny-by-default registry,
# the release-train grammar, the registered-but-pending release-train order, and the dedicated
# renderers that must never fall back to the legacy semantic-retrieval boilerplate.
WO025_G3_STALE_RENDERER_PHRASES = (
    "0005_semantic_retrieval",
    "pgvector",
    "reranking",
    "retrieval semântico",
    "fusão híbrida",
    "embeddings",
    "WO-006",
)


def wo025_g3_render_arguments() -> dict[str, object]:
    return {
        "pr_number": 126,
        "branch": "governance/wo025-g3-work-order-namespace",
        "artifact_name": "hive-review-evidence-WO-025-G3-fixture",
        "ruleset_before": "21934284",
        "ruleset_after": "21934284",
        "merge_before": "squash",
        "merge_after": "squash",
    }


def test_work_order_registry_is_deny_by_default_and_closed() -> None:
    """Every registered identifier is accepted and the unregistered frontier fails closed."""

    assert isinstance(review_evidence.REGISTERED_WORK_ORDERS, frozenset)
    # The registrations made by the governance increments covered by this regression.
    for registered in (
        review_evidence.WO025_G3_WORK_ORDER,
        review_evidence.WO025P_WORK_ORDER,
        review_evidence.WO11_01_WORK_ORDER,
        review_evidence.WO030_WORK_ORDER,
    ):
        assert registered in review_evidence.REGISTERED_WORK_ORDERS
        require_supported_work_order(registered)

    # Near-miss identifiers that the old numeric fallthrough silently accepted.
    for rejected in ("WO-11-01", "WO-12-99", "WO-22-01", "WO-11-01-EXTRA"):
        assert rejected not in review_evidence.REGISTERED_WORK_ORDERS
        with pytest.raises(ValueError, match="unsupported"):
            require_supported_work_order(rejected)

    # The unknown future frontier and malformed identifiers keep failing closed.
    for rejected in ("WO-027-P", "WO-032", "WO-999", "WO-999-P", "WO-1.1-02", ""):
        with pytest.raises(ValueError):
            require_supported_work_order(rejected)

    # The historical registry is preserved: a broad sample of merged work orders still resolves.
    for historical in (
        review_evidence.WO024_WORK_ORDER,
        review_evidence.WO024_G1_WORK_ORDER,
        review_evidence.WO024P_WORK_ORDER,
        review_evidence.WO023P_G1_C1_WORK_ORDER,
        review_evidence.WO025_WORK_ORDER,
        review_evidence.WO025_G1_WORK_ORDER,
        review_evidence.WO025_G2_WORK_ORDER,
        "WO-007-P",
        "WO-012-P-G1",
        "WO-019",
        "WO-020-G1",
    ):
        assert historical in review_evidence.REGISTERED_WORK_ORDERS
        require_supported_work_order(historical)

    # The local validation sentinel stays accepted without becoming a work order.
    require_supported_work_order("LOCAL-VALIDATION")
    assert "LOCAL-VALIDATION" not in review_evidence.REGISTERED_WORK_ORDERS
    assert frozenset({"LOCAL-VALIDATION"}) == review_evidence.WORK_ORDER_SENTINELS


def test_release_train_grammar_parses_the_first_1_1_order() -> None:
    """The dotted release-train namespace parses WO-1.1-01 and rejects malformed variants."""

    assert (
        review_evidence.parse_work_order_marker(
            f"<!-- HIVE-WORK-ORDER: {review_evidence.WO11_01_WORK_ORDER} -->"
        )
        == review_evidence.WO11_01_WORK_ORDER
    )
    assert review_evidence.RELEASE_TRAIN_WORK_ORDER_IDENTIFIER.fullmatch("WO-1.1-01") is not None
    # The legacy grammar still cannot express the dotted form, which is why the new one exists.
    assert review_evidence.WORK_ORDER_IDENTIFIER.fullmatch("WO-1.1-01") is None

    # Malformed and ambiguous dotted spellings fail closed at the grammar boundary.
    for malformed in (
        "WO-1.1-1",
        "WO-1.1-001",
        "WO-1.1-01-EXTRA",
        "WO-1.1",
        "WO-01.1-01",
        "WO-1.01-01",
        "WO-1.1-01.1",
    ):
        with pytest.raises(ValueError, match="invalid or unbounded"):
            review_evidence.parse_work_order_marker(f"<!-- HIVE-WORK-ORDER: {malformed} -->")
    # A well-formed but unregistered dotted identifier parses yet fails closed on registration.
    assert (
        review_evidence.parse_work_order_marker("<!-- HIVE-WORK-ORDER: WO-1.2-01 -->")
        == "WO-1.2-01"
    )
    with pytest.raises(ValueError, match="unsupported release-train"):
        require_supported_work_order("WO-1.2-01")


def test_registered_release_train_order_is_pending_and_cannot_authorize_yet() -> None:
    """STATE A: WO-1.1-01 is registered but blocked by canonical checkpoint evidence, not a flag."""

    assert review_evidence.RELEASE_TRAIN_PROMOTING_WORK_ORDERS == {
        review_evidence.WO11_01_WORK_ORDER: review_evidence.WO025P_WORK_ORDER
    }
    # The working tree still carries the V0.1 closure status, so the gate stays closed and names the
    # promotion that has to land instead of failing through to a generic rejection.
    assert (
        review_evidence.normalized_checkpoint_value(
            review_evidence.checkpoint_sections(
                (review_evidence.ROOT / review_evidence.CHECKPOINT_PATH)
                .read_bytes()
                .decode("utf-8")
            ),
            "STATUS",
        )
        == review_evidence.EXPECTED_WO025P_PREVIOUS_STATUS
    )
    with pytest.raises(
        ValueError,
        match="not authorized as a current work order.*promotion by WO-025-P",
    ):
        require_current_work_order_authorization(review_evidence.WO11_01_WORK_ORDER)
    # A later 1.1 step is not registered at all and therefore fails closed as unsupported.
    assert "WO-1.1-02" not in review_evidence.REGISTERED_WORK_ORDERS
    with pytest.raises(ValueError, match="unsupported release-train"):
        require_current_work_order_authorization("WO-1.1-02")


def test_next_checkpoint_promotion_is_registered_without_joining_the_active_pair() -> None:
    """WO-025-P is the current promotion frontier and never displaces the WO-024 history."""

    require_supported_work_order(review_evidence.WO025P_WORK_ORDER)
    assert (
        review_evidence.WO025P_PROMOTION_REGISTRY[review_evidence.WO025P_WORK_ORDER]
        == review_evidence.WO012P_PROMOTION_BASE_REF
    )
    assert review_evidence.WO025P_WORK_ORDER not in (
        review_evidence.ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS
    )
    assert (
        frozenset({review_evidence.WO024_G1_WORK_ORDER, review_evidence.WO024P_WORK_ORDER})
        == review_evidence.ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS
    )
    # T1/T2: registered and current-authorized after WO-025-G3, without a further commit.
    assert (
        frozenset({review_evidence.WO025P_WORK_ORDER})
        == review_evidence.CURRENT_CHECKPOINT_PROMOTION_WORK_ORDERS
    )
    require_current_work_order_authorization(review_evidence.WO025P_WORK_ORDER)


def test_wo025_g3_self_hosting_scope_and_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    """WO-025-G3 is base-bound, governance-only, and emits its own bounded evidence."""

    require_supported_work_order(review_evidence.WO025_G3_WORK_ORDER)
    require_current_work_order_authorization(review_evidence.WO025_G3_WORK_ORDER)
    assert review_evidence.WO025_G3_WORK_ORDER in review_evidence.AUTHORIZED_BASE_MARKER_WORK_ORDERS

    allowed = sorted(review_evidence.WO025_G3_ALLOWED_PATHS)
    review_evidence.require_wo025_g3_scope(
        review_evidence.WO025_G3_WORK_ORDER,
        review_evidence.WO025_G3_BASE_SHA,
        allowed,
        authorized_base_sha=review_evidence.WO025_G3_BASE_SHA,
    )
    # The base is exact: a different base fails closed.
    with pytest.raises(ValueError, match="exact base"):
        review_evidence.require_wo025_g3_scope(
            review_evidence.WO025_G3_WORK_ORDER,
            "f" * 40,
            allowed,
            authorized_base_sha="f" * 40,
        )
    # Governance-only: product, canonical and workflow paths stay rejected.
    for unauthorized in (
        ["backend/app/main.py"],
        ["docs/project-brain/13-CHECKPOINT.md"],
        ["docs/project-brain/CANONICAL-SHA256SUMS.txt"],
        [".github/workflows/ci.yml"],
        ["requirements.txt"],
        ["VERSION"],
    ):
        with pytest.raises(ValueError):
            review_evidence.require_wo025_g3_scope(
                review_evidence.WO025_G3_WORK_ORDER,
                review_evidence.WO025_G3_BASE_SHA,
                unauthorized,
                authorized_base_sha=review_evidence.WO025_G3_BASE_SHA,
            )

    closure_text = json.dumps(v01_closure_evidence_fixture())
    monkeypatch.setattr(
        review_evidence,
        "integration_file",
        lambda name: (
            closure_text if name == review_evidence.V01_CLOSURE_SPRINT_EVIDENCE_FILE else ""
        ),
    )
    evidence = review_evidence.verify_wo025_g3_governance_contract(
        review_evidence.WO025_G3_WORK_ORDER,
        review_evidence.WO025_G3_BASE_SHA,
        allowed,
        {
            "project_brain_changed": False,
            "checkpoint_changed": False,
            "authorized_paths": [],
        },
        {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}},
        {"v01_closure_sprint": v01_closure_evidence_fixture()},
        review_evidence.V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD,
        review_evidence.WO025_G3_BASE_SHA,
    )
    assert evidence is not None
    assert "work_order=WO-025-G3" in evidence
    assert "deny_by_default=True" in evidence
    assert "fallthrough_removed=True" in evidence
    assert "release_train_grammar=PASS" in evidence
    assert "wo_1_1_01_pending_blocked=True" in evidence
    assert "wo_1_1_02_rejected=True" in evidence
    assert "near_miss_WO-11-01_WO-12-99_WO-22-01=REJECTED" in evidence
    assert "unknown_WO-027-P_WO-028=REJECTED" in evidence
    assert "malformed_identifier=REJECTED" in evidence
    assert "empty_identifier=REJECTED" in evidence
    assert "wo_025_p_promotion_executed=False" in evidence
    assert "wo_025_p_current_authorized=True" in evidence
    assert f"current_promotion_frontier={review_evidence.WO025P_WORK_ORDER}" in evidence
    assert "promotion_history_separated=True" in evidence
    assert "wo_1_1_01_gate=canonical_checkpoint_evidence" in evidence
    assert "wo_1_1_01_release_needs_no_governance_commit=True" in evidence
    assert "historical_promotion_pair_unchanged=True" in evidence
    assert "historical_work_orders_preserved=True" in evidence
    assert "wo024_strict_behavior_unchanged=True" in evidence
    assert "product_implementation=False" in evidence
    assert "checkpoint_promoted=False" in evidence
    assert "auto_merge=UNARMED" in evidence
    # The contract is inert for every other work order.
    assert (
        review_evidence.verify_wo025_g3_governance_contract(
            review_evidence.WO024_WORK_ORDER,
            review_evidence.WO025_G3_BASE_SHA,
            allowed,
            {
                "project_brain_changed": False,
                "checkpoint_changed": False,
                "authorized_paths": [],
            },
            {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}},
            {"v01_closure_sprint": v01_closure_evidence_fixture()},
            review_evidence.V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD,
            None,
        )
        is None
    )


def test_wo025_g3_renderer_is_dedicated_and_has_no_legacy_fallback() -> None:
    import scripts.review_pr_body as renderer

    body = renderer.render_body(
        work_order=review_evidence.WO025_G3_WORK_ORDER,
        base_sha=review_evidence.WO025_G3_BASE_SHA,
        head_sha="b" * 40,
        **cast(dict[str, Any], wo025_g3_render_arguments()),
    )
    assert body.startswith("<!-- HIVE-WORK-ORDER: WO-025-G3 -->")
    assert f"<!-- HIVE-AUTHORIZED-BASE: {review_evidence.WO025_G3_BASE_SHA} -->" in body
    assert "AWAITING_SOL" in body
    assert "WO-025-G3 READY FOR SOL AUDIT" in body
    assert "deny-by-default" in body
    # The corrected transition is stated for the reviewer: history stays separate and the
    # release-train gate reads canonical evidence instead of waiting for another commit.
    assert "fronteira corrente de promoção é" in body
    assert "evidência canônica" in body
    assert "sem nenhum incremento de governança adicional" in body
    for stale in WO025_G3_STALE_RENDERER_PHRASES:
        assert stale not in body, f"WO-025-G3 renderer must not emit stale text: {stale}"
    # The base pin is exact and fails closed for a stale base.
    with pytest.raises(ValueError):
        renderer.render_body(
            work_order=review_evidence.WO025_G3_WORK_ORDER,
            base_sha="f" * 40,
            head_sha="b" * 40,
            **cast(dict[str, Any], wo025_g3_render_arguments()),
        )


def test_wo025_p_and_wo11_01_renderers_are_dedicated_and_have_no_legacy_fallback() -> None:
    import scripts.review_pr_body as renderer

    for work_order, ready_marker in (
        (review_evidence.WO025P_WORK_ORDER, "WO-025-P READY FOR SOL AUDIT"),
        (review_evidence.WO11_01_WORK_ORDER, "WO-1.1-01 READY FOR SOL AUDIT"),
    ):
        body = renderer.render_body(
            work_order=work_order,
            base_sha=review_evidence.WO025_G3_BASE_SHA,
            head_sha="b" * 40,
            **cast(dict[str, Any], wo025_g3_render_arguments()),
        )
        assert body.startswith(f"<!-- HIVE-WORK-ORDER: {work_order} -->")
        assert f"<!-- HIVE-AUTHORIZED-BASE: {review_evidence.WO025_G3_BASE_SHA} -->" in body
        assert "AWAITING_SOL" in body
        assert ready_marker in body
        for stale in WO025_G3_STALE_RENDERER_PHRASES:
            assert stale not in body, f"{work_order} renderer must not emit stale text: {stale}"

    # A renderer exists for the registered order, but rendering is not authorization.
    with pytest.raises(ValueError, match="not authorized as a current work order"):
        require_current_work_order_authorization(review_evidence.WO11_01_WORK_ORDER)


def test_wo025_g4_self_hosting_scope_and_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    """WO-025-G4 is base-bound, governance/test-only, and emits its own bounded evidence."""

    require_supported_work_order(review_evidence.WO025_G4_WORK_ORDER)
    require_current_work_order_authorization(review_evidence.WO025_G4_WORK_ORDER)
    assert review_evidence.WO025_G4_WORK_ORDER in review_evidence.AUTHORIZED_BASE_MARKER_WORK_ORDERS
    assert review_evidence.WO025_G4_WORK_ORDER in review_evidence.CORRECTIVE_GOVERNANCE_WORK_ORDERS
    assert review_evidence.WO025_G4_WORK_ORDER not in (
        review_evidence.CHECKPOINT_PROMOTION_WORK_ORDERS
    )
    assert review_evidence.WO025_G4_WORK_ORDER not in (
        review_evidence.CURRENT_CHECKPOINT_PROMOTION_WORK_ORDERS
    )
    assert review_evidence.WO025_G4_BASE_SHA == "b4b7b0a10976e2bc4eb220318664e802e4bd41bc"

    allowed = sorted(review_evidence.WO025_G4_ALLOWED_PATHS)
    review_evidence.require_wo025_g4_scope(
        review_evidence.WO025_G4_WORK_ORDER,
        review_evidence.WO025_G4_BASE_SHA,
        allowed,
        authorized_base_sha=review_evidence.WO025_G4_BASE_SHA,
    )
    # The base is exact: a different base fails closed, including the WO-025-G3 base.
    for stale_base in ("f" * 40, review_evidence.WO025_G3_BASE_SHA):
        with pytest.raises(ValueError, match="exact base"):
            review_evidence.require_wo025_g4_scope(
                review_evidence.WO025_G4_WORK_ORDER,
                stale_base,
                allowed,
                authorized_base_sha=stale_base,
            )
    # Governance and tests only: product, canonical, workflow and release paths stay rejected.
    for unauthorized in (
        ["backend/app/main.py"],
        ["docs/project-brain/13-CHECKPOINT.md"],
        ["docs/project-brain/CANONICAL-SHA256SUMS.txt"],
        ["docs/project-brain/16-DECISIONS-LEDGER.md"],
        [".github/workflows/ci.yml"],
        ["requirements.txt"],
        ["VERSION"],
        ["backend/app/services/decision_resolver.py"],
    ):
        with pytest.raises(ValueError):
            review_evidence.require_wo025_g4_scope(
                review_evidence.WO025_G4_WORK_ORDER,
                review_evidence.WO025_G4_BASE_SHA,
                unauthorized,
                authorized_base_sha=review_evidence.WO025_G4_BASE_SHA,
            )
    # The authorized-base marker has to be a lowercase 40-hex SHA matching the base.
    with pytest.raises(ValueError, match="authorized-base marker"):
        review_evidence.require_wo025_g4_scope(
            review_evidence.WO025_G4_WORK_ORDER,
            review_evidence.WO025_G4_BASE_SHA,
            allowed,
        )

    closure_text = json.dumps(v01_closure_evidence_fixture())
    monkeypatch.setattr(
        review_evidence,
        "integration_file",
        lambda name: (
            closure_text if name == review_evidence.V01_CLOSURE_SPRINT_EVIDENCE_FILE else ""
        ),
    )
    evidence = review_evidence.verify_wo025_g4_governance_contract(
        review_evidence.WO025_G4_WORK_ORDER,
        review_evidence.WO025_G4_BASE_SHA,
        allowed,
        {
            "project_brain_changed": False,
            "checkpoint_changed": False,
            "authorized_paths": [],
        },
        {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}},
        {"v01_closure_sprint": v01_closure_evidence_fixture()},
        review_evidence.V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD,
        review_evidence.WO025_G4_BASE_SHA,
    )
    assert evidence is not None
    assert f"work_order={review_evidence.WO025_G4_WORK_ORDER}" in evidence
    assert "exact_base=PASS" in evidence
    assert "closure_checkpoint_families=3" in evidence
    assert "strict_promotion_grammar=True" in evidence
    assert "in_process_promotion_proof=PASS" in evidence
    assert "mutations_rejected=5" in evidence
    assert "status_swap_only=REJECTED" in evidence
    assert "missing_section=REJECTED" in evidence
    assert "active_closure_pending_items=" in evidence
    assert "controlled_sections=BLOCKERS,IN PROGRESS,NEXT STEP,PENDING,STATUS" in evidence
    assert "post_wo025p_state=PASS" in evidence
    assert "v01_closure_state=PASS" in evidence
    assert "unrelated_section_drift=REJECTED" in evidence
    assert "wo_025_p_promotion_executed=False" in evidence
    assert f"current_promotion_frontier={review_evidence.WO025P_WORK_ORDER}" in evidence
    assert "checkpoint_changed=False" in evidence
    assert "canonical_manifest_changed=False" in evidence
    assert "historical_promotion_pair_unchanged=True" in evidence
    assert "wo024_strict_behavior_unchanged=True" in evidence
    assert "integration_health_closure_regression=EXECUTABLE" in evidence
    assert "renderers=dedicated_wo025_g4" in evidence
    assert "product_implementation=False" in evidence
    assert "checkpoint_promoted=False" in evidence
    assert "deny_by_default=True" in evidence
    assert "auto_merge=UNARMED" in evidence
    # The contract is inert for every other work order, including its sibling corrections.
    for other in (
        review_evidence.WO025_G3_WORK_ORDER,
        review_evidence.WO024_WORK_ORDER,
        review_evidence.WO025P_WORK_ORDER,
    ):
        assert (
            review_evidence.verify_wo025_g4_governance_contract(
                other,
                review_evidence.WO025_G4_BASE_SHA,
                allowed,
                {
                    "project_brain_changed": False,
                    "checkpoint_changed": False,
                    "authorized_paths": [],
                },
                {"ruleset_unchanged": True, "pull_request": {"auto_merge_armed": False}},
                {"v01_closure_sprint": v01_closure_evidence_fixture()},
                review_evidence.V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD,
                None,
            )
            is None
        )


def test_wo025_g4_registration_does_not_widen_the_namespace() -> None:
    """Registering the correction must leave every unregistered identifier denied."""

    assert review_evidence.WO025_G4_WORK_ORDER in review_evidence.REGISTERED_WORK_ORDERS
    for rejected in (
        "WO-025-G6",
        "WO-025-G10",
        "WO-025-G4-P",
        "WO-026-P",
        "WO-032",
        "WO-1.1-02",
        "WO-12-99",
        "WO-11-01",
    ):
        assert rejected not in review_evidence.REGISTERED_WORK_ORDERS
        with pytest.raises(ValueError, match="unsupported"):
            require_supported_work_order(rejected)
        with pytest.raises(ValueError, match="unsupported"):
            require_current_work_order_authorization(rejected)
    # The historical WO-024 promotion pair and the current frontier are exactly as G3 froze them.
    assert (
        frozenset({review_evidence.WO024_G1_WORK_ORDER, review_evidence.WO024P_WORK_ORDER})
        == review_evidence.ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS
    )
    assert (
        frozenset({review_evidence.WO025P_WORK_ORDER})
        == review_evidence.CURRENT_CHECKPOINT_PROMOTION_WORK_ORDERS
    )


def test_wo025_g4_keeps_the_historical_v01_closure_contract() -> None:
    """AC19: the WO-024-P constants and grammar this increment has to coexist with are unchanged."""

    assert review_evidence.EXPECTED_WO024P_STATUS == (
        "HIVE V0.1 COMPLETE / CLOSURE SPRINT APPROVED"
    )
    assert review_evidence.EXPECTED_WO024P_IN_PROGRESS == (
        "None. V0.1 closure is complete and promoted."
    )
    assert review_evidence.EXPECTED_WO025P_PREVIOUS_STATUS == (
        review_evidence.EXPECTED_WO024P_STATUS
    )
    assert "COMPLETED" in review_evidence._WO016P_RAW_CONTROLLED_SECTIONS
    assert "COMPLETED" not in review_evidence.WO025P_RAW_PROMOTION_CONTROLLED_SECTIONS
    # The real checkpoint and its manifest are untouched by this increment.
    checkpoint = review_evidence.ROOT / review_evidence.CHECKPOINT_PATH
    before = checkpoint.read_bytes()
    assert (
        review_evidence.normalized_checkpoint_value(
            review_evidence.checkpoint_sections(before.decode("utf-8")), "STATUS"
        )
        == review_evidence.EXPECTED_WO024P_STATUS
    )
    review_evidence.require_canonical_manifest_digests(
        review_evidence.ROOT,
        (review_evidence.ROOT / review_evidence.CANONICAL_MANIFEST_PATH).read_text(
            encoding="utf-8"
        ),
    )
    assert checkpoint.read_bytes() == before


def test_wo025_g4_renderer_is_dedicated_and_binds_the_exact_base() -> None:
    import scripts.review_pr_body as renderer

    arguments = cast(dict[str, Any], wo025_g3_render_arguments())
    body = renderer.render_body(
        work_order=review_evidence.WO025_G4_WORK_ORDER,
        base_sha=review_evidence.WO025_G4_BASE_SHA,
        head_sha="b" * 40,
        **arguments,
    )
    assert body.startswith(f"<!-- HIVE-WORK-ORDER: {review_evidence.WO025_G4_WORK_ORDER} -->")
    assert f"<!-- HIVE-AUTHORIZED-BASE: {review_evidence.WO025_G4_BASE_SHA} -->" in body
    assert "AWAITING_SOL" in body
    assert "WO-025-G4 READY FOR SOL AUDIT" in body
    # The reviewer is told the exact root cause and the three legitimate families.
    assert "checkpoint_current()" in body
    assert "POST-1.0 PLANNING PROMOTED" in body
    assert "## 4. Contrato dos três estados legítimos" in body
    assert "Sem implementação de produto, sem promoção de checkpoint, sem merge" in body
    for stale in WO025_G3_STALE_RENDERER_PHRASES:
        assert stale not in body, f"WO-025-G4 renderer must not emit stale text: {stale}"
    # A stale base or a malformed HEAD never renders.
    for base_sha in ("f" * 40, review_evidence.WO025_G3_BASE_SHA):
        with pytest.raises(ValueError):
            renderer.render_body(
                work_order=review_evidence.WO025_G4_WORK_ORDER,
                base_sha=base_sha,
                head_sha="b" * 40,
                **arguments,
            )
    with pytest.raises(ValueError, match="40-hex"):
        renderer.render_body(
            work_order=review_evidence.WO025_G4_WORK_ORDER,
            base_sha=review_evidence.WO025_G4_BASE_SHA,
            head_sha="not-a-sha",
            **arguments,
        )

    # The unregistered next step cannot be rendered at all.
    with pytest.raises(ValueError, match="unsupported release-train"):
        renderer.render_body(
            work_order="WO-1.1-02",
            base_sha=review_evidence.WO025_G3_BASE_SHA,
            head_sha="b" * 40,
            **cast(dict[str, Any], wo025_g3_render_arguments()),
        )


def test_wo11_01_future_scope_is_bounded_and_rejects_opportunistic_paths() -> None:
    """The registered 1.1-01 contract is frozen now and rejects anything outside its surface."""

    allowed = sorted(review_evidence.WO11_01_ALLOWED_PATHS)
    review_evidence.require_wo11_01_scope(
        review_evidence.WO11_01_WORK_ORDER,
        review_evidence.WO025_G3_BASE_SHA,
        allowed,
        authorized_base_sha=review_evidence.WO025_G3_BASE_SHA,
    )
    # Decision Fabric surface only: unrelated product, canonical and CI paths stay rejected.
    for unauthorized in (
        ["backend/app/main.py"],
        ["backend/app/telemetry.py"],
        ["docs/project-brain/13-CHECKPOINT.md"],
        [".github/workflows/ci.yml"],
        ["requirements.txt"],
        ["VERSION"],
        ["backend/migrations/versions/0008_next.py"],
    ):
        with pytest.raises(ValueError):
            review_evidence.require_wo11_01_scope(
                review_evidence.WO11_01_WORK_ORDER,
                review_evidence.WO025_G3_BASE_SHA,
                unauthorized,
                authorized_base_sha=review_evidence.WO025_G3_BASE_SHA,
            )


def test_wo025p_scope_is_bounded_to_the_canonical_promotion_surface(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """STATE B: the promotion is bounded to the canonical surface and obeys the exact contract."""

    base = review_evidence.WO025_G3_BASE_SHA
    monkeypatch.setattr(review_evidence, "registered_promotion_base_sha", lambda wo: base)
    monkeypatch.setattr(
        review_evidence,
        "migration_head",
        lambda: review_evidence.V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD,
    )
    stage_promotion_base_blob(monkeypatch)
    # WO-025-G4 made the promotion grammar strict, so a bare status swap is no longer a valid
    # promotion: the staged candidate has to carry the whole controlled-section state.
    stage_canonical_promotion(
        tmp_path,
        monkeypatch,
        status=review_evidence.EXPECTED_WO025P_STATUS,
        full_promotion=True,
    )
    allowed = sorted(review_evidence.WO025P_ALLOWED_PATHS)
    review_evidence.require_wo025p_scope(
        review_evidence.WO025P_WORK_ORDER,
        base,
        allowed,
        authorized_base_sha=base,
    )
    # A candidate that only swapped STATUS is rejected even on the canonical surface.
    swap_root = tmp_path / "status-swap"
    stage_canonical_promotion(swap_root, monkeypatch, status=review_evidence.EXPECTED_WO025P_STATUS)
    with pytest.raises(ValueError, match="outside the strict raw grammar"):
        review_evidence.require_wo025p_scope(
            review_evidence.WO025P_WORK_ORDER,
            base,
            allowed,
            authorized_base_sha=base,
        )
    monkeypatch.setattr(review_evidence, "ROOT", tmp_path)
    for unauthorized in (
        ["backend/app/main.py"],
        ["scripts/validate.py"],
        [".github/workflows/ci.yml"],
        ["requirements.txt"],
        ["VERSION"],
    ):
        with pytest.raises(ValueError):
            review_evidence.require_wo025p_scope(
                review_evidence.WO025P_WORK_ORDER,
                base,
                unauthorized,
                authorized_base_sha=base,
            )


def canonical_source_brain() -> Path:
    """The real Project Brain tree, independent of any patched ``ROOT``."""

    return Path(review_evidence.__file__).resolve().parents[1] / "docs" / "project-brain"


def stage_canonical_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    status: str,
    refresh_digest: bool = True,
    tamper_other_source: bool = False,
    full_promotion: bool = False,
) -> Path:
    """Stage a canonical Project Brain tree whose checkpoint carries ``status``.

    Only the checkpoint digest line is refreshed, so the tree is canonical-coherent exactly when the
    promotion landed completely. ``full_promotion`` writes the whole controlled-section state that
    WO-025-P leaves behind instead of a bare status swap.
    """

    source_brain = canonical_source_brain()
    brain = tmp_path / "docs" / "project-brain"
    brain.mkdir(parents=True, exist_ok=True)
    manifest_text = (source_brain / "CANONICAL-SHA256SUMS.txt").read_text(encoding="utf-8")
    for name, _ in review_evidence.parse_canonical_manifest(manifest_text, "manifest"):
        (brain / name).write_bytes((source_brain / name).read_bytes())
    checkpoint_text = replace_checkpoint_section(
        (source_brain / "13-CHECKPOINT.md").read_text(encoding="utf-8"),
        "STATUS",
        status,
    )
    if full_promotion:
        checkpoint_text = post_1_0_promotion(
            (source_brain / "13-CHECKPOINT.md").read_text(encoding="utf-8"), status=status
        )
    checkpoint_path = brain / review_evidence.CANONICAL_MANIFEST_CHECKPOINT_NAME
    checkpoint_path.write_text(checkpoint_text, encoding="utf-8", newline="\n")
    if refresh_digest:
        digest = hashlib.sha256(checkpoint_path.read_bytes()).hexdigest()
        manifest_text = re.sub(
            rf"^[0-9a-f]{{64}}(  {re.escape(review_evidence.CANONICAL_MANIFEST_CHECKPOINT_NAME)}$)",
            digest + r"\1",
            manifest_text,
            count=1,
            flags=re.M,
        )
    (brain / "CANONICAL-SHA256SUMS.txt").write_text(manifest_text, encoding="utf-8", newline="\n")
    if tamper_other_source:
        other = next(
            name
            for name, _ in review_evidence.parse_canonical_manifest(manifest_text, "manifest")
            if name != review_evidence.CANONICAL_MANIFEST_CHECKPOINT_NAME
        )
        path = brain / other
        path.write_bytes(path.read_bytes() + b"\n<!-- unauthorized canonical edit -->\n")
    monkeypatch.setattr(review_evidence, "ROOT", tmp_path)
    return tmp_path


def stage_promotion_base_blob(monkeypatch: pytest.MonkeyPatch) -> None:
    """Serve the V0.1 closure checkpoint and its manifest as the promotion base revision."""

    source_brain = canonical_source_brain()
    blobs = {
        review_evidence.CHECKPOINT_PATH: (source_brain / "13-CHECKPOINT.md").read_bytes(),
        review_evidence.CANONICAL_MANIFEST_PATH: (
            source_brain / "CANONICAL-SHA256SUMS.txt"
        ).read_bytes(),
    }
    monkeypatch.setattr(
        review_evidence,
        "git_blob_bytes",
        lambda revision, path: blobs[path],
    )


def checkpoint_status(root: Path) -> str:
    text = (root / review_evidence.CHECKPOINT_PATH).read_bytes().decode("utf-8")
    return review_evidence.normalized_checkpoint_value(
        review_evidence.checkpoint_sections(text), "STATUS"
    )


def post_1_0_promotion(base: str, *, status: str | None = None) -> str:
    """Rewrite the real checkpoint into the exact state WO-025-P must leave behind.

    Only the controlled promotion sections move, in the raw grammar the contract itself defines, so
    the positive case proves the declared constants and not a conveniently edited fixture.
    """

    newline = "\n"
    bodies = {
        "STATUS": f"{status or review_evidence.EXPECTED_WO025P_STATUS}{newline}{newline}",
        "IN PROGRESS": f"- {review_evidence.EXPECTED_WO025P_IN_PROGRESS}{newline}{newline}",
        "BLOCKERS": f"{review_evidence.EXPECTED_WO025P_BLOCKERS}{newline}{newline}",
        "NEXT STEP": f"{review_evidence.EXPECTED_WO025P_NEXT_STEP}{newline}{newline}",
        "PENDING": newline,
    }
    preamble, ordered, _sections = review_evidence._raw_checkpoint_structure(base, "base")
    return preamble + "".join(
        section.heading + bodies.get(section.name, section.body) for section in ordered
    )


def checkpoint_section_bodies(text: str) -> dict[str, str]:
    _preamble, _ordered, bodies = review_evidence._raw_checkpoint_structure(text, "candidate")
    return dict(bodies)


def rebuild_with_bodies(text: str, bodies: dict[str, str]) -> str:
    preamble, ordered, _current = review_evidence._raw_checkpoint_structure(text, "candidate")
    return preamble + "".join(section.heading + bodies[section.name] for section in ordered)


def wo025p_negative_matrix() -> dict[str, tuple[str, str]]:
    """Every narrower post-1.0 candidate with the rejection it must produce.

    Each case isolates one section so a passing test proves the specific guard fired, not that some
    unrelated check happened to reject the same text.
    """

    base = (review_evidence.ROOT / review_evidence.CHECKPOINT_PATH).read_bytes().decode("utf-8")
    promoted = post_1_0_promotion(base)
    bodies = checkpoint_section_bodies(promoted)
    grammar = "section is outside the strict raw grammar"
    drift = "changed unrelated checkpoint section"

    def variant(name: str, body: str) -> str:
        return rebuild_with_bodies(promoted, {**bodies, name: body})

    return {
        "status swap only": (
            replace_checkpoint_section(base, "STATUS", review_evidence.EXPECTED_WO025P_STATUS),
            "IN PROGRESS section is outside the strict raw grammar",
        ),
        "near-miss status": (
            variant("STATUS", f"{review_evidence.EXPECTED_WO025P_STATUS} / partial\n\n"),
            "STATUS " + grammar,
        ),
        "stale IN PROGRESS": (
            variant("IN PROGRESS", f"- {review_evidence.EXPECTED_WO024P_IN_PROGRESS}\n\n"),
            "IN PROGRESS " + grammar,
        ),
        "stale BLOCKERS": (
            variant("BLOCKERS", f"{review_evidence.EXPECTED_WO024P_BLOCKERS}\n\n"),
            "BLOCKERS " + grammar,
        ),
        "stale NEXT STEP": (
            variant("NEXT STEP", f"{review_evidence.EXPECTED_WO024P_NEXT_STEP}\n\n"),
            "NEXT STEP " + grammar,
        ),
        "undue PENDING": (
            variant("PENDING", "- retained closure item\n\n"),
            "PENDING " + grammar,
        ),
        "unrelated section drift": (
            variant("GOVERNANCE", f"{bodies['GOVERNANCE']}drift\n"),
            drift + ": GOVERNANCE",
        ),
        "completed drift": (
            variant("COMPLETED", f"{bodies['COMPLETED']}\n- later closure claim.\n\n"),
            drift + ": COMPLETED",
        ),
        "version drift": (
            variant("VERSION", "HIVE V1.1 Kernel\n\n"),
            drift + ": VERSION",
        ),
        "promoted status with pending work": (
            promoted.replace("## PENDING\n\n", "## PENDING\n- leftover.\n\n"),
            "PENDING " + grammar,
        ),
    }


def test_state_transition_releases_wo11_01_without_another_governance_commit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """AC09: the same code releases WO-1.1-01 once only the canonical promotion data changes.

    STATE A blocks the order and STATE C authorizes it with no further governance commit, which is
    what removes the release-train deadlock.
    """

    # STATE A: WO-025-P is current-authorized and WO-1.1-01 is registered but blocked.
    require_supported_work_order(review_evidence.WO025P_WORK_ORDER)
    require_current_work_order_authorization(review_evidence.WO025P_WORK_ORDER)
    require_supported_work_order(review_evidence.WO11_01_WORK_ORDER)
    with pytest.raises(ValueError, match="not authorized as a current work order"):
        require_current_work_order_authorization(review_evidence.WO11_01_WORK_ORDER)

    # STATE C: only the checkpoint and its digest manifest changed. WO-025-G4 makes the promoted
    # state the full controlled-section contract, so the fixture has to write that whole state.
    stage_canonical_promotion(
        tmp_path,
        monkeypatch,
        status=review_evidence.EXPECTED_WO025P_STATUS,
        full_promotion=True,
    )
    assert checkpoint_status(tmp_path) == review_evidence.EXPECTED_WO025P_STATUS
    require_current_work_order_authorization(review_evidence.WO11_01_WORK_ORDER)
    # The operational fields are part of the promoted state, not an incidental side effect.
    promoted_sections = review_evidence.checkpoint_sections(
        (tmp_path / review_evidence.CHECKPOINT_PATH).read_bytes().decode("utf-8")
    )

    def controlled(name: str) -> str:
        value = review_evidence.normalized_checkpoint_value(promoted_sections, name)
        return value[2:].strip() if value.startswith("- ") else value

    assert controlled("IN PROGRESS") == review_evidence.EXPECTED_WO025P_IN_PROGRESS
    assert controlled("BLOCKERS") == review_evidence.EXPECTED_WO025P_BLOCKERS
    assert controlled("NEXT STEP") == review_evidence.EXPECTED_WO025P_NEXT_STEP
    assert review_evidence.checkpoint_bullets(promoted_sections, "PENDING") == []
    # No unknown identifier gains authorization from the promoted state.
    for rejected in ("WO-1.1-02", "WO-1.2-01", "WO-11-01", "WO-22-01", "WO-025-P-G1", ""):
        with pytest.raises(ValueError):
            require_current_work_order_authorization(rejected)


def test_wo025p_candidate_checkpoint_contract_is_exact() -> None:
    """T5: the promotion candidate must obey the declared contract and nothing looser.

    WO-025-G4 narrowed this grammar: swapping STATUS is no longer a promotion, and every section
    outside the controlled set is preserved byte-for-byte.
    """

    base = (review_evidence.ROOT / review_evidence.CHECKPOINT_PATH).read_bytes().decode("utf-8")
    promoted = post_1_0_promotion(base)
    review_evidence.require_wo025p_checkpoint_semantics(base, promoted)
    assert promoted != base
    assert checkpoint_section_bodies(promoted)["PENDING"] == "\n"

    # A status swap alone is exactly the fabricated promotion this grammar exists to reject.
    with pytest.raises(ValueError, match="IN PROGRESS section is outside"):
        review_evidence.require_wo025p_checkpoint_semantics(
            base,
            replace_checkpoint_section(base, "STATUS", review_evidence.EXPECTED_WO025P_STATUS),
        )
    for candidate, reason in wo025p_negative_matrix().values():
        with pytest.raises(ValueError, match=reason):
            review_evidence.require_wo025p_checkpoint_semantics(base, candidate)

    # A stale base that already carries the promoted state cannot promote twice.
    with pytest.raises(ValueError, match="promotion base is not the V0.1 closure"):
        review_evidence.require_wo025p_checkpoint_semantics(promoted, promoted)

    # Dropping a section is a sequence change, not a licence to rewrite whatever is left.
    removed = re.sub(r"## PHASE\n.*?\n\n", "", base, count=1, flags=re.S)
    with pytest.raises(ValueError, match="checkpoint section sequence changed"):
        review_evidence.require_wo025p_checkpoint_semantics(removed, promoted)
    # A heading that still parses to the same name but differs byte-for-byte stays rejected.
    reheaded = promoted.replace("## NEXT STEP\n", "## next step\n", 1)
    assert reheaded != promoted
    with pytest.raises(ValueError, match="heading changed byte-for-byte"):
        review_evidence.require_wo025p_checkpoint_semantics(base, reheaded)


def test_canonical_promotion_evidence_rejects_near_miss_stale_partial_and_fabricated_states(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """T13: the release-train gate reads content and digests, never a derived or vague signal."""

    expected = review_evidence.EXPECTED_WO025P_STATUS

    def assert_blocked(
        case: str,
        *,
        status: str,
        reason: str,
        refresh_digest: bool = True,
        tamper_other_source: bool = False,
    ) -> None:
        root = tmp_path / case
        root.mkdir()
        stage_canonical_promotion(
            root,
            monkeypatch,
            status=status,
            refresh_digest=refresh_digest,
            tamper_other_source=tamper_other_source,
        )
        with pytest.raises(ValueError, match=reason):
            require_current_work_order_authorization(review_evidence.WO11_01_WORK_ORDER)
        monkeypatch.undo()

    assert_blocked("near-miss", status=expected + " / partial", reason="not authorized")
    assert_blocked(
        "stale",
        status=review_evidence.EXPECTED_WO025P_PREVIOUS_STATUS,
        reason="not authorized",
    )
    assert_blocked(
        "partial",
        status=expected,
        reason="canonical digest does not match",
        refresh_digest=False,
    )
    assert_blocked(
        "fabricated",
        status=expected,
        reason="canonical digest does not match",
        tamper_other_source=True,
    )


def test_release_train_gate_fails_closed_without_a_registered_promotion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """T14: authorization is reachable only through the explicit mapping plus canonical evidence."""

    # A missing canonical tree is a rejection, never a fallthrough to success.
    monkeypatch.setattr(review_evidence, "ROOT", tmp_path / "nowhere")
    with pytest.raises(ValueError, match="not authorized as a current work order"):
        require_current_work_order_authorization(review_evidence.WO11_01_WORK_ORDER)
    # Deny-by-default: without an explicit promoting order even a fully promoted state stays closed.
    stage_canonical_promotion(tmp_path, monkeypatch, status=review_evidence.EXPECTED_WO025P_STATUS)
    require_current_work_order_authorization(review_evidence.WO11_01_WORK_ORDER)
    monkeypatch.setattr(review_evidence, "RELEASE_TRAIN_PROMOTING_WORK_ORDERS", {})
    with pytest.raises(ValueError, match="no canonical promotion that releases it"):
        require_current_work_order_authorization(review_evidence.WO11_01_WORK_ORDER)


def test_wo025_g5_review_self_healing_policy_is_bounded_and_registered() -> None:
    """The Sol self-healing review rule is explicit, low-risk, and deny-by-default."""

    require_supported_work_order(review_evidence.WO025_G5_WORK_ORDER)
    require_current_work_order_authorization(review_evidence.WO025_G5_WORK_ORDER)
    assert review_evidence.WO025_G5_WORK_ORDER in (
        review_evidence.CORRECTIVE_GOVERNANCE_WORK_ORDERS
    )
    assert review_evidence.WO025_G5_WORK_ORDER in (
        review_evidence.AUTHORIZED_BASE_MARKER_WORK_ORDERS
    )
    assert review_evidence.WO025_G5_WORK_ORDER not in (
        review_evidence.CHECKPOINT_PROMOTION_WORK_ORDERS
    )
    assert review_evidence.WO025_G5_BASE_SHA == "82bb5e9d6fb22046e95eb532b499884adaeae6c3"

    allowed = sorted(review_evidence.WO025_G5_ALLOWED_PATHS)
    review_evidence.require_wo025_g5_scope(
        review_evidence.WO025_G5_WORK_ORDER,
        review_evidence.WO025_G5_BASE_SHA,
        allowed,
        authorized_base_sha=review_evidence.WO025_G5_BASE_SHA,
    )

    for unauthorized in (
        ["backend/app/main.py"],
        ["docs/project-brain/13-CHECKPOINT.md"],
        ["docs/project-brain/16-DECISIONS-LEDGER.md"],
        [".github/workflows/ci.yml"],
        ["requirements.txt"],
        ["VERSION"],
        ["migrations/9999_forbidden.py"],
    ):
        with pytest.raises(ValueError):
            review_evidence.require_wo025_g5_scope(
                review_evidence.WO025_G5_WORK_ORDER,
                review_evidence.WO025_G5_BASE_SHA,
                unauthorized,
                authorized_base_sha=review_evidence.WO025_G5_BASE_SHA,
            )

    with pytest.raises(ValueError, match="exact base"):
        review_evidence.require_wo025_g5_scope(
            review_evidence.WO025_G5_WORK_ORDER,
            "f" * 40,
            allowed,
            authorized_base_sha="f" * 40,
        )
    with pytest.raises(ValueError, match="authorized-base marker"):
        review_evidence.require_wo025_g5_scope(
            review_evidence.WO025_G5_WORK_ORDER,
            review_evidence.WO025_G5_BASE_SHA,
            allowed,
        )


def test_hive_rel_004_scope_and_completed_release_noop_order_are_bounded() -> None:
    """HIVE-REL-004 fixes only stale completed-release publication retries."""

    require_supported_work_order(HIVE_REL_004_WORK_ORDER)
    require_current_work_order_authorization(HIVE_REL_004_WORK_ORDER)
    allowed = sorted(HIVE_REL_004_ALLOWED_PATHS)
    require_hive_rel_004_scope(
        HIVE_REL_004_WORK_ORDER,
        HIVE_REL_004_BASE_SHA,
        allowed,
        authorized_base_sha=HIVE_REL_004_BASE_SHA,
    )
    for unauthorized in (
        ["VERSION"],
        [".engineering/release/HIVE-V1.0.0-PUBLISH-REQUEST.json"],
        ["docs/project-brain/13-CHECKPOINT.md"],
        ["backend/app/main.py"],
    ):
        with pytest.raises(ValueError):
            require_hive_rel_004_scope(
                HIVE_REL_004_WORK_ORDER,
                HIVE_REL_004_BASE_SHA,
                unauthorized,
                authorized_base_sha=HIVE_REL_004_BASE_SHA,
            )

    workflow_path = review_evidence.ROOT / ".github/workflows/release-publisher.yml"
    workflow = workflow_path.read_text(encoding="utf-8")
    terminal_check = workflow.index(
        "is already fully published with final receipt; publisher will no-op"
    )
    parent_check = workflow.index('python - "$request" "$candidate" "$version"')
    assert terminal_check < parent_check


def test_hive_rel_005_preparation_scope_is_exact_and_fail_closed() -> None:
    allowed = sorted(HIVE_REL_005_ALLOWED_PATHS)
    require_hive_rel_005_scope(
        HIVE_REL_005_WORK_ORDER,
        HIVE_REL_005_BASE_SHA,
        allowed,
        authorized_base_sha=HIVE_REL_005_BASE_SHA,
    )
    with pytest.raises(ValueError, match="protected main"):
        require_hive_rel_005_scope(
            HIVE_REL_005_WORK_ORDER,
            HIVE_REL_005_BASE_SHA,
            allowed,
            base_branch="release",
            authorized_base_sha=HIVE_REL_005_BASE_SHA,
        )
    with pytest.raises(ValueError, match="exact base"):
        require_hive_rel_005_scope(
            HIVE_REL_005_WORK_ORDER,
            "a" * 40,
            allowed,
            authorized_base_sha=HIVE_REL_005_BASE_SHA,
        )
    with pytest.raises(ValueError, match="authorized-base marker"):
        require_hive_rel_005_scope(
            HIVE_REL_005_WORK_ORDER,
            HIVE_REL_005_BASE_SHA,
            allowed,
        )
    with pytest.raises(ValueError, match="bounded preparation scope"):
        require_hive_rel_005_scope(
            HIVE_REL_005_WORK_ORDER,
            HIVE_REL_005_BASE_SHA,
            [*allowed, "backend/app/main.py"],
            authorized_base_sha=HIVE_REL_005_BASE_SHA,
        )
    with pytest.raises(ValueError, match="canonical or local-only"):
        require_hive_rel_005_scope(
            HIVE_REL_005_WORK_ORDER,
            HIVE_REL_005_BASE_SHA,
            ["docs/project-brain/13-CHECKPOINT.md"],
            authorized_base_sha=HIVE_REL_005_BASE_SHA,
        )
    with pytest.raises(ValueError, match="non-empty"):
        require_hive_rel_005_scope(
            HIVE_REL_005_WORK_ORDER,
            HIVE_REL_005_BASE_SHA,
            [],
            authorized_base_sha=HIVE_REL_005_BASE_SHA,
        )


def test_hive_rel_006_publication_scope_is_exact_and_fail_closed() -> None:
    allowed = sorted(HIVE_REL_006_ALLOWED_PATHS)
    require_hive_rel_006_scope(
        HIVE_REL_006_WORK_ORDER,
        HIVE_REL_006_BASE_SHA,
        allowed,
        authorized_base_sha=HIVE_REL_006_BASE_SHA,
    )
    release_dir = review_evidence.ROOT / ".engineering" / "release"
    request_path = release_dir / "HIVE-V1.0.1-PUBLISH-REQUEST.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    assert request["status"] == "armed"
    assert request["product"] == "HIVE"
    assert request["version"] == "1.0.1"
    assert request["tag"] == "v1.0.1"
    assert request["work_order"] == HIVE_REL_006_WORK_ORDER
    assert request["issue"] == 137
    assert request["authorized_parent"] == HIVE_REL_006_BASE_SHA
    receipt_asset = request["publication"]["final_receipt_asset"]
    assert receipt_asset == "hive-v1.0.1.release-receipt.json"

    with pytest.raises(ValueError, match="protected main"):
        require_hive_rel_006_scope(
            HIVE_REL_006_WORK_ORDER,
            HIVE_REL_006_BASE_SHA,
            allowed,
            base_branch="release",
            authorized_base_sha=HIVE_REL_006_BASE_SHA,
        )
    with pytest.raises(ValueError, match="exact base"):
        require_hive_rel_006_scope(
            HIVE_REL_006_WORK_ORDER,
            "a" * 40,
            allowed,
            authorized_base_sha=HIVE_REL_006_BASE_SHA,
        )
    with pytest.raises(ValueError, match="authorized-base marker"):
        require_hive_rel_006_scope(
            HIVE_REL_006_WORK_ORDER,
            HIVE_REL_006_BASE_SHA,
            allowed,
        )
    with pytest.raises(ValueError, match="bounded publication scope"):
        require_hive_rel_006_scope(
            HIVE_REL_006_WORK_ORDER,
            HIVE_REL_006_BASE_SHA,
            [*allowed, "backend/app/main.py"],
            authorized_base_sha=HIVE_REL_006_BASE_SHA,
        )
    with pytest.raises(ValueError, match="canonical or local-only"):
        require_hive_rel_006_scope(
            HIVE_REL_006_WORK_ORDER,
            HIVE_REL_006_BASE_SHA,
            ["docs/project-brain/13-CHECKPOINT.md"],
            authorized_base_sha=HIVE_REL_006_BASE_SHA,
        )
    with pytest.raises(ValueError, match="non-empty"):
        require_hive_rel_006_scope(
            HIVE_REL_006_WORK_ORDER,
            HIVE_REL_006_BASE_SHA,
            [],
            authorized_base_sha=HIVE_REL_006_BASE_SHA,
        )


def test_hive_rel_007_v102_preparation_scope_is_exact_and_fail_closed() -> None:
    allowed = sorted(HIVE_REL_007_ALLOWED_PATHS)
    require_hive_rel_007_scope(
        HIVE_REL_007_WORK_ORDER,
        HIVE_REL_007_BASE_SHA,
        allowed,
        authorized_base_sha=HIVE_REL_007_BASE_SHA,
    )
    with pytest.raises(ValueError, match="protected main"):
        require_hive_rel_007_scope(
            HIVE_REL_007_WORK_ORDER,
            HIVE_REL_007_BASE_SHA,
            allowed,
            base_branch="release",
            authorized_base_sha=HIVE_REL_007_BASE_SHA,
        )
    with pytest.raises(ValueError, match="exact base"):
        require_hive_rel_007_scope(
            HIVE_REL_007_WORK_ORDER,
            "a" * 40,
            allowed,
            authorized_base_sha=HIVE_REL_007_BASE_SHA,
        )
    with pytest.raises(ValueError, match="authorized-base marker"):
        require_hive_rel_007_scope(
            HIVE_REL_007_WORK_ORDER,
            HIVE_REL_007_BASE_SHA,
            allowed,
        )
    with pytest.raises(ValueError, match="bounded preparation scope"):
        require_hive_rel_007_scope(
            HIVE_REL_007_WORK_ORDER,
            HIVE_REL_007_BASE_SHA,
            [*allowed, "backend/app/main.py"],
            authorized_base_sha=HIVE_REL_007_BASE_SHA,
        )
    with pytest.raises(ValueError, match="canonical or local-only"):
        require_hive_rel_007_scope(
            HIVE_REL_007_WORK_ORDER,
            HIVE_REL_007_BASE_SHA,
            ["docs/project-brain/13-CHECKPOINT.md"],
            authorized_base_sha=HIVE_REL_007_BASE_SHA,
        )
    with pytest.raises(ValueError, match="non-empty"):
        require_hive_rel_007_scope(
            HIVE_REL_007_WORK_ORDER,
            HIVE_REL_007_BASE_SHA,
            [],
            authorized_base_sha=HIVE_REL_007_BASE_SHA,
        )


def test_hive_rel_008_v102_publication_scope_is_exact_and_fail_closed() -> None:
    allowed = sorted(HIVE_REL_008_ALLOWED_PATHS)
    require_hive_rel_008_scope(
        HIVE_REL_008_WORK_ORDER,
        HIVE_REL_008_BASE_SHA,
        allowed,
        authorized_base_sha=HIVE_REL_008_BASE_SHA,
    )
    release_dir = review_evidence.ROOT / ".engineering" / "release"
    request_path = release_dir / "HIVE-V1.0.2-PUBLISH-REQUEST.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    assert request["status"] == "armed"
    assert request["product"] == "HIVE"
    assert request["version"] == "1.0.2"
    assert request["tag"] == "v1.0.2"
    assert request["work_order"] == HIVE_REL_008_WORK_ORDER
    assert request["authorized_parent"] == HIVE_REL_008_BASE_SHA
    receipt_asset = request["publication"]["final_receipt_asset"]
    assert receipt_asset == "hive-v1.0.2.release-receipt.json"

    with pytest.raises(ValueError, match="protected main"):
        require_hive_rel_008_scope(
            HIVE_REL_008_WORK_ORDER,
            HIVE_REL_008_BASE_SHA,
            allowed,
            base_branch="release",
            authorized_base_sha=HIVE_REL_008_BASE_SHA,
        )
    with pytest.raises(ValueError, match="exact base"):
        require_hive_rel_008_scope(
            HIVE_REL_008_WORK_ORDER,
            "a" * 40,
            allowed,
            authorized_base_sha=HIVE_REL_008_BASE_SHA,
        )
    with pytest.raises(ValueError, match="authorized-base marker"):
        require_hive_rel_008_scope(
            HIVE_REL_008_WORK_ORDER,
            HIVE_REL_008_BASE_SHA,
            allowed,
        )
    with pytest.raises(ValueError, match="bounded publication scope"):
        require_hive_rel_008_scope(
            HIVE_REL_008_WORK_ORDER,
            HIVE_REL_008_BASE_SHA,
            [*allowed, "backend/app/main.py"],
            authorized_base_sha=HIVE_REL_008_BASE_SHA,
        )
    with pytest.raises(ValueError, match="canonical or local-only"):
        require_hive_rel_008_scope(
            HIVE_REL_008_WORK_ORDER,
            HIVE_REL_008_BASE_SHA,
            ["docs/project-brain/13-CHECKPOINT.md"],
            authorized_base_sha=HIVE_REL_008_BASE_SHA,
        )
    with pytest.raises(ValueError, match="non-empty"):
        require_hive_rel_008_scope(
            HIVE_REL_008_WORK_ORDER,
            HIVE_REL_008_BASE_SHA,
            [],
            authorized_base_sha=HIVE_REL_008_BASE_SHA,
        )


def test_wo031_corrective_scope_is_exact_and_base_bound() -> None:
    paths = sorted(review_evidence.WO031_ALLOWED_PATHS)
    review_evidence.require_wo031_scope(
        review_evidence.WO031_WORK_ORDER,
        review_evidence.WO031_BASE_SHA,
        paths,
        base_branch="main",
        authorized_base_sha=review_evidence.WO031_BASE_SHA,
        enforce_current_main=False,
    )

    with pytest.raises(ValueError, match="exactly the bounded corrective surface"):
        review_evidence.require_wo031_scope(
            review_evidence.WO031_WORK_ORDER,
            review_evidence.WO031_BASE_SHA,
            paths + ["README.md"],
            base_branch="main",
            authorized_base_sha=review_evidence.WO031_BASE_SHA,
            enforce_current_main=False,
        )

    with pytest.raises(ValueError, match="requires exact base"):
        review_evidence.require_wo031_scope(
            review_evidence.WO031_WORK_ORDER,
            "0" * 40,
            paths,
            base_branch="main",
            authorized_base_sha="0" * 40,
            enforce_current_main=False,
        )


def test_wo031_is_registered_and_requires_authorized_base_marker() -> None:
    review_evidence.require_supported_work_order(review_evidence.WO031_WORK_ORDER)
    assert review_evidence.WO031_WORK_ORDER in review_evidence.AUTHORIZED_BASE_MARKER_WORK_ORDERS
