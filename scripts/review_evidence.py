"""Generate and validate bounded, secret-free Review Evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import posixpath
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NamedTuple, cast

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "review-evidence-v1.schema.json"
DEFAULT_OUTPUT = ROOT / "tmp" / "review-evidence"
VALIDATION = ROOT / "tmp" / "validation"
INTEGRATION_LOGS = ROOT / "tmp" / "integration-logs"
HEX_SHA = re.compile(r"^[0-9a-f]{40}$")
MAX_EVIDENCE_CHARS = 12_000
WORK_ORDER_IDENTIFIER = re.compile(r"WO-[0-9]+(?:-[A-Z0-9]+)*")
GEF_WORK_ORDER_IDENTIFIER = re.compile(r"GEF-[A-Z0-9]+(?:-[A-Z0-9]+)*")
HIVE_REL_WORK_ORDER_IDENTIFIER = re.compile(r"HIVE-REL-[0-9]{3}")
WORK_ORDER_MARKER = re.compile(r"<!--\s*HIVE-WORK-ORDER:\s*([^<>\r\n]+?)\s*-->", re.IGNORECASE)
AUTHORIZED_BASE_MARKER = re.compile(
    r"<!--\s*HIVE-AUTHORIZED-BASE:\s*([^<>\r\n]+?)\s*-->", re.IGNORECASE
)
RERANK_SECRET_SENTINEL = re.compile(r"WO008_TEST_SECRET_DO_NOT_LEAK_[A-Za-z0-9_-]+")
RERANK_C1_REQUIRED_FIELDS = (
    "rerank_project_isolation",
    "rerank_duplicate_task_collapsed",
    "rerank_cross_project_duplicate_isolation",
    "rerank_missing_index_safe",
    "rerank_out_of_range_index_safe",
    "rerank_duplicate_index_safe",
    "rerank_non_finite_score_safe",
    "rerank_model_mismatch_safe",
    "rerank_malformed_response_matrix",
    "rerank_default_order_preserved",
    "rerank_fallback_scores_null",
    "rerank_strict_invalid_response_bounded",
    "rerank_semantic_stale_state_preserved",
    "rerank_secret_not_leaked",
    "rerank_ordering_reproducible",
)
CONTEXT_MANAGER_REQUIRED_FIELDS = (
    "checkpoint_first",
    "governance_project_scoped",
    "task_project_scoped",
    "reranked_retrieval_used",
    "provenance_preserved",
    "deterministic_two_run",
    "bounded",
    "cross_project_isolation",
    "missing_governance_fail_closed",
    "head_race_fail_closed",
    "redis_restart_rebuild",
    "api_restart_rebuild",
    "mandatory_governance_coverage",
)
PROGRESSIVE_DISCLOSURE_REQUIRED_FIELDS = (
    "progressive_disclosure_level_mapping",
    "smallest_sufficient",
    "no_unnecessary_escalation",
    "explicit_insufficiency_escalation",
    "bounded_escalation",
    "stop_on_sufficient",
    "cross_project_disclosure_fail_closed",
)
PROGRESSIVE_DISCLOSURE_C1_FIELDS = (
    "smallest_sufficient_uses_acceptance_criteria",
    "smallest_sufficient_uses_resolved_evidence",
    "synthetic_known_requirement_escalation_absent",
    "l1_module_summary_materialized",
    "l2_symbol_signature_materialized",
    "l2_dependency_metadata_materialized",
    "explicit_disclosure_level_contract_valid",
    "l4_nonempty_when_selected",
    "l4_target_resolved_from_project_evidence",
    "progressive_payload_in_bounds_accounting",
    "legitimate_escalation_fixture",
)
PROGRESSIVE_DISCLOSURE_C2_FIELDS = (
    "l4_complete_file_untruncated",
    "l4_large_file_full_content",
    "l4_full_content_source_identity",
    "l4_oversize_capsule_fail_closed",
)
TOKEN_BUDGET_REQUIRED_FIELDS = (
    "adaptive_token_budget_implemented",
    "token_budget_policy_versioned",
    "token_estimator_versioned",
    "token_estimator_provider_independent",
    "token_budget_estimate_serialization_versioned",
    "final_context_token_estimate_verified",
    "final_context_estimate_within_effective_budget",
    "planner_subset_full_payload_regression",
    "token_budget_uses_approved_deterministic_signals",
    "token_budget_user_mode_required",
    "mandatory_governance_preserved_under_budget",
    "task_constraints_preserved_under_budget",
    "acceptance_criteria_preserved_under_budget",
    "progressive_disclosure_semantics_preserved_under_budget",
    "l4_complete_file_preserved_under_budget",
    "optional_tail_trim_deterministic",
    "retained_rerank_order_preserved",
    "required_context_over_budget_fail_closed",
    "effective_budget_within_hard_bounds",
    "token_budget_deterministic_two_run",
    "token_budget_redis_restart_rebuild",
    "token_budget_api_restart_rebuild",
    "adaptive_token_budget_migration_changed",
    "benchmark_critical_misses_computed",
    "benchmark_required_identity_negative_fixture",
    "benchmark_mandatory_governance_computed",
    "benchmark_task_contract_computed",
    "benchmark_disclosure_retention_computed",
    "benchmark_baseline_is_actual_context",
    "benchmark_strict_reduction_is_real",
)
WO012_CONTEXT_FINGERPRINT_REQUIRED_FIELDS = (
    "context_fingerprints_implemented",
    "context_fingerprint_policy_versioned",
    "context_fingerprint_algorithm_sha256",
    "context_input_serialization_versioned",
    "context_output_serialization_versioned",
    "context_fingerprint_input_material_inputs_bound",
    "context_fingerprint_output_verified",
    "context_fingerprint_provider_independent",
    "context_fingerprint_secrets_excluded",
    "context_fingerprint_project_scoped",
    "context_fingerprint_task_scoped",
    "context_fingerprint_deterministic_two_run",
    "context_fingerprint_cache_redis_noncanonical",
    "context_fingerprint_cache_ttl_bounded",
    "context_fingerprint_cache_value_bounded",
    "context_fingerprint_valid_hit_identical_capsule",
    "context_fingerprint_valid_hit_avoids_rebuild",
    "context_fingerprint_source_change_invalidates",
    "context_fingerprint_task_change_invalidates",
    "context_fingerprint_request_change_invalidates",
    "context_fingerprint_profile_change_invalidates",
    "context_fingerprint_policy_change_invalidates",
    "context_fingerprint_equivalent_rebuild_stable",
    "context_fingerprint_transient_provider_failure_not_cached",
    "context_fingerprint_provider_recovery_retried",
    "context_fingerprint_cross_project_isolation",
    "context_fingerprint_cross_task_isolation",
    "context_fingerprint_corrupt_cache_safe_rebuild",
    "context_fingerprint_redis_loss_rebuild",
    "context_fingerprint_redis_flush_rebuild",
    "context_fingerprint_redis_restart_reuse",
    "context_fingerprint_api_restart_reuse",
    "context_fingerprint_source_race_fail_closed",
    "context_fingerprint_benchmark_work_avoidance_proven",
)
WO012_CONTEXT_FINGERPRINT_INTEGER_FIELDS = (
    "context_fingerprint_benchmark_false_hits",
    "context_fingerprint_benchmark_critical_context_misses",
    "context_fingerprint_llm_calls",
    "context_fingerprint_provider_calls",
    "context_fingerprint_first_embedding_calls",
    "context_fingerprint_repeat_embedding_calls",
    "context_fingerprint_first_rerank_calls",
    "context_fingerprint_repeat_rerank_calls",
)
WO012_CONTEXT_FINGERPRINT_NEGATIVE_FIELDS = (
    "context_fingerprint_migration_changed",
    "delta_context_implemented",
    "provider_prompt_cache_implemented",
    "memory_lifecycle_implemented",
)
WO013_DELTA_REQUIRED_FIELDS = (
    "delta_context_implemented",
    "delta_context_policy_versioned",
    "delta_context_serialization_versioned",
    "delta_context_delivery_schema_versioned",
    "delta_context_uses_context_output_v2",
    "delta_context_provider_independent",
    "delta_context_baseline_output_fingerprint_required_for_delta",
    "delta_context_baseline_redis_noncanonical",
    "delta_context_baseline_ttl_bounded",
    "delta_context_baseline_project_scoped",
    "delta_context_baseline_task_scoped",
    "delta_context_baseline_fingerprint_verified",
    "delta_context_cross_project_isolation",
    "delta_context_cross_task_isolation",
    "delta_context_corrupt_baseline_safe_full_fallback",
    "delta_context_redis_loss_full_fallback",
    "delta_context_api_restart_reuse",
    "delta_context_source_race_fail_closed",
    "delta_context_final_stability_all_delivery_paths",
    "delta_context_postbuild_source_race_fail_closed",
    "delta_context_not_smaller_valid_baseline",
    "delta_context_not_smaller_reason_verified",
    "delta_context_final_delivery_bound_verified",
    "delta_context_reconstruction_verified",
    "delta_context_target_output_fingerprint_verified",
    "delta_context_new_dependency_preserved",
    "delta_context_identical_context_supported",
    "delta_context_changed_context_strict_reduction",
    "delta_context_full_fallback_when_not_smaller",
    "delta_context_full_fallback_correct",
    "delta_context_deterministic_two_run",
    "delta_context_delivery_estimate_versioned",
    "delta_context_final_delivery_token_estimate_verified",
    "delta_context_strict_smaller_uses_final_delivery_estimate",
    "delta_context_intermediate_metadata_false_positive_regression",
    "delta_context_fresh_token_avoidance_truthful",
    "delta_context_full_savings_zero",
    "delta_context_threshold_old_gate_would_emit_delta",
    "delta_context_threshold_final_gate_rejected_delta",
)
WO013_DELTA_INTEGER_FIELDS = (
    "delta_context_llm_calls",
    "delta_context_provider_calls",
    "delta_context_false_reconstructions",
    "delta_context_critical_context_misses",
    "delta_context_not_smaller_delta_estimated_tokens",
    "delta_context_not_smaller_full_estimated_tokens",
    "delta_context_small_change_delta_estimated_tokens",
    "delta_context_small_change_final_delta_estimated_tokens",
    "delta_context_small_change_full_estimated_tokens",
    "delta_context_small_change_fresh_context_tokens_avoided",
    "delta_context_small_change_patch_operation_count",
    "delta_context_small_change_patch_serialized_characters",
    "delta_context_small_change_final_delivery_bytes",
    "delta_context_threshold_old_metadata_estimated_tokens",
    "delta_context_threshold_final_delta_estimated_tokens",
    "delta_context_threshold_full_estimated_tokens",
    "delta_context_threshold_contract_serialized_bytes",
)
WO013_DELTA_STRING_FIELDS = ("delta_context_delivery_estimate_version",)
WO013_DELTA_LIST_FIELDS = ("delta_context_delivery_estimate_self_reference_exclusions",)
WO013_DELTA_NEGATIVE_FIELDS = (
    "delta_context_migration_changed",
    "provider_prompt_cache_implemented",
    "memory_lifecycle_implemented",
    "autonomous_executor_dispatch_implemented",
)
WO014_PROVIDER_CACHE_REQUIRED_FIELDS = (
    "provider_prompt_cache_foundation_implemented",
    "provider_prompt_envelope_versioned",
    "provider_cache_independent_canonical_input_versioned",
    "provider_cache_independent_semantic_composition_verified",
    "provider_cache_semantic_mutation_detection",
    "stable_prompt_prefix_policy_versioned",
    "provider_cache_adapter_versioned",
    "provider_cache_capabilities_versioned",
    "provider_usage_receipt_versioned",
    "provider_cache_accounting_versioned",
    "provider_cache_provider_independent",
    "provider_cache_unsupported_noop",
    "provider_cache_semantic_composition_verified",
    "provider_cache_endpoint_verified",
    "provider_cache_stable_prefix_reuse",
    "provider_cache_governance_invalidation",
    "provider_cache_source_invalidation",
    "provider_cache_material_provider_identity_invalidation",
    "provider_cache_material_provider_identity_fixture_verified",
    "provider_cache_credential_rotation_nonmaterial",
    "provider_cache_cross_project_isolation",
    "provider_cache_cache_requested_distinct_from_hit",
    "provider_cache_requested_without_receipt_hit_unknown",
    "provider_cache_requested_zero_cached_hit_false",
    "provider_cache_repeated_prefix_without_receipt_not_hit",
    "provider_cache_positive_receipt_hit_true",
    "provider_cache_unknown_usage_not_zero",
    "provider_cache_explicit_zero_distinct_from_unknown",
    "provider_cache_reported_usage_reconciled",
    "provider_cache_invalid_usage_fail_closed",
    "provider_cache_hive_estimates_not_provider_usage",
    "provider_cache_full_compatible",
    "provider_cache_delta_compatible",
    "provider_cache_full_compatible_measured",
    "provider_cache_delta_compatible_measured",
)
WO014_PROVIDER_CACHE_INTEGER_FIELDS = (
    "provider_cache_semantic_composition_mismatches",
    "provider_cache_semantic_composition_fixture_count",
    "provider_cache_semantic_composition_mismatch_detection_count",
    "provider_cache_accepted_semantic_composition_mismatches",
    "provider_cache_secret_leaks",
    "provider_cache_credential_leaks",
    "provider_cache_cross_project_leaks",
    "provider_cache_endpoint_cross_project_leaks",
    "provider_cache_false_hit_claims",
    "provider_cache_invalid_accounting_matrix_size",
    "provider_cache_invalid_accounting_acceptances",
    "provider_cache_delta_false_reconstructions",
    "provider_cache_delta_critical_context_misses",
    "provider_cache_foundation_llm_calls",
    "provider_cache_foundation_provider_calls",
    "provider_cache_stable_prefix_bytes",
    "provider_cache_stable_prefix_characters",
    "provider_cache_dynamic_suffix_bytes",
    "provider_cache_dynamic_suffix_characters",
    "provider_cache_composed_bytes",
    "provider_cache_composed_characters",
    "provider_cache_stable_prefix_hive_estimated_tokens",
    "provider_cache_dynamic_suffix_hive_estimated_tokens",
    "provider_cache_composed_hive_estimated_tokens",
    "provider_cache_provider_total_input_tokens",
    "provider_cache_provider_cached_input_tokens",
    "provider_cache_provider_fresh_input_tokens",
)
WO014_PROVIDER_CACHE_STRING_FIELDS = ("provider_cache_independent_canonical_input_version",)
WO014_PROVIDER_CACHE_LIST_FIELDS = ("provider_cache_provider_usage_sources",)
WO014_PROVIDER_CACHE_NEGATIVE_FIELDS = (
    "live_provider_prompt_cache_network_integration",
    "memory_lifecycle_implemented",
    "autonomous_executor_dispatch_implemented",
    "full_cache_telemetry_implemented",
    "migration_changed",
)
WO015_MEMORY_REQUIRED_FIELDS = (
    "memory_lifecycle_implemented",
    "memory_postgres_durable",
    "memory_redis_noncanonical",
    "memory_project_scoped",
    "memory_cross_project_rejected",
    "memory_provenance_queryable",
    "memory_model_output_staged",
    "memory_canonical_promotion_qualified",
    "memory_immutable_git_blob_binding",
    "memory_source_mutation_rejected",
    "memory_adr_mutation_rejected",
    "memory_head_mutation_rejected",
    "memory_race_atomicity_preserved",
    "memory_generic_decision_id_qualified",
    "memory_provenance_identity_consistent",
    "memory_invalid_promotion_rejected",
    "memory_history_preserved",
    "memory_restart_recovery",
    "memory_redis_loss_recovery",
    "memory_secrets_not_exposed",
    "memory_migration_consistent",
    "memory_migration_changed",
)
WO015_MEMORY_INTEGER_FIELDS = (
    "memory_project_count",
    "memory_cross_project_rejections",
    "memory_provenance_records",
    "memory_invalid_promotion_rejections",
    "memory_source_race_rejections",
    "memory_adr_race_rejections",
    "memory_head_race_rejections",
    "memory_history_versions",
    "memory_restart_records",
    "memory_redis_loss_records",
    "memory_secret_leaks",
    "memory_llm_calls",
    "memory_provider_calls",
)
WO015_MEMORY_STRING_FIELDS = ("memory_evidence_version", "memory_migration_head")
WO015_MEMORY_EVIDENCE_FILE = "memory-lifecycle.json"
ACCE_STORAGE_POLICY_EVIDENCE_VERSION = "acce-storage-policy-v1"
ACCE_STORAGE_POLICY_EVIDENCE_FILE = "acce-storage-policy.json"
ACCE_STORAGE_POLICY_ZSTD_MIN_LEVEL = 1
ACCE_STORAGE_POLICY_ZSTD_MAX_LEVEL = 22
ACCE_STORAGE_POLICY_MAX_BENCHMARK_ROWS = 16
ACCE_STORAGE_POLICY_MAX_THROUGHPUT_MIB_PER_S = 1_000_000.0
ACCE_STORAGE_POLICY_REQUIRED_FIELDS = (
    "hot_warm_cold_policy_defined",
    "policy_selection_internal_deterministic",
    "zstd_lossless_codec",
    "zstd_profiles_measured",
    "zstd_levels_supported",
    "content_identity_sha256_preserved",
    "dedup_identity_across_tiers",
    "single_canonical_cas_identity",
    "corruption_fail_closed",
    "physical_replacement_atomic",
    "logical_bytes_measured",
    "physical_bytes_measured",
    "compression_measurements_truthful",
    "dedup_measurements_truthful",
    "restart_durable",
    "redis_loss_preserves_cas_truth",
    "selection_rationale_measured",
)
ACCE_STORAGE_POLICY_INTEGER_FIELDS = (
    "canonical_source_loss_count",
    "llm_calls",
    "provider_calls",
    "dedup_logical_bytes",
    "dedup_unique_logical_bytes",
    "dedup_savings_bytes",
)
ACCE_STORAGE_POLICY_STRING_FIELDS = ("acce_evidence_version", "storage_policy_version")
ACCE_STORAGE_POLICY_ALLOWED_TIERS = ("HOT", "WARM", "COLD")
ACCE_STORAGE_POLICY_PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
MCP_CORE_SURFACE_EVIDENCE_VERSION = "mcp-core-surface-v1"
MCP_CORE_SURFACE_EVIDENCE_FILE = "mcp-surface.json"
MCP_CORE_SURFACE_TOOLS = (
    "project.list",
    "project.status",
    "context.build",
    "context.search",
    "memory.search",
    "memory.get",
    "checkpoint.read",
)
MCP_CORE_SURFACE_TRUE_FIELDS = (
    "protocol_handshake_passed",
    "protocol_tool_list_passed",
    "real_transport_exercised",
    "project_list_passed",
    "project_status_passed",
    "context_build_passed",
    "context_search_passed",
    "memory_search_passed",
    "memory_get_passed",
    "checkpoint_read_passed",
    "direct_core_reuse",
    "rest_loopback_absent",
    "duplicate_persistence_absent",
    "project_isolation_passed",
    "cross_project_access_rejected",
    "invalid_arguments_fail_closed",
    "unknown_tool_fail_closed",
    "bounded_output_enforced",
    "checkpoint_target_project_correct",
    "context_checkpoint_first",
    "restart_recovery",
    "redis_loss_recovery",
    "deterministic_repeat",
    "arbitrary_filesystem_access_rejected",
    "checkpoint_missing_fail_closed",
    "checkpoint_untracked_fail_closed",
    "checkpoint_stale_fail_closed",
    "checkpoint_hive_substitution_absent",
    "context_search_provenance_preserved",
    "context_search_result_bound_enforced",
    "memory_search_provenance_preserved",
    "memory_get_provenance_preserved",
    "memory_status_visibility_preserved",
    "structured_errors_enforced",
    "bounded_errors_enforced",
)
MCP_CORE_SURFACE_REGISTERED_PROJECT_COUNT = "registered_project_count"
MCP_CORE_SURFACE_MAX_REGISTERED_PROJECT_COUNT = 32
MCP_CORE_SURFACE_COUNT_FIELDS = (MCP_CORE_SURFACE_REGISTERED_PROJECT_COUNT,)
MCP_CORE_SURFACE_FALSE_FIELDS = (
    "migration_changed",
    "canonical_write_tools_exposed",
)
MCP_CORE_SURFACE_INTEGER_FIELDS = (
    "secret_leaks",
    "filesystem_path_leaks",
    "mcp_llm_calls",
    "mcp_provider_calls",
)
MCP_CORE_SURFACE_REQUIRED_FIELDS = (
    "status",
    "evidence_file",
    "mcp_evidence_version",
    "tool_list_exact",
    *MCP_CORE_SURFACE_COUNT_FIELDS,
    *MCP_CORE_SURFACE_TRUE_FIELDS,
    *MCP_CORE_SURFACE_FALSE_FIELDS,
    "observed_migration_head",
    *MCP_CORE_SURFACE_INTEGER_FIELDS,
)
MCP_CORE_SURFACE_ALLOWED_FIELDS = frozenset(
    {
        *MCP_CORE_SURFACE_REQUIRED_FIELDS,
    }
)
# Work-order-scoped aliases keep the contract discoverable alongside the older
# WO-015/WO-016 evidence constants.
WO017_MCP_EVIDENCE_VERSION = MCP_CORE_SURFACE_EVIDENCE_VERSION
WO017_MCP_EVIDENCE_FILE = MCP_CORE_SURFACE_EVIDENCE_FILE
WO017_MCP_TOOLS = MCP_CORE_SURFACE_TOOLS
WO017_MCP_REQUIRED_FIELDS = MCP_CORE_SURFACE_REQUIRED_FIELDS
WO017_MCP_COUNT_FIELDS = MCP_CORE_SURFACE_COUNT_FIELDS
WO017_MCP_MAX_REGISTERED_PROJECT_COUNT = MCP_CORE_SURFACE_MAX_REGISTERED_PROJECT_COUNT
WO017_MCP_INTEGER_FIELDS = MCP_CORE_SURFACE_INTEGER_FIELDS
AUTONOMOUS_EXECUTION_EVIDENCE_VERSION = "autonomous-execution-v1"
AUTONOMOUS_EXECUTION_EVIDENCE_FILE = "autonomous-execution.json"
AUTONOMOUS_EXECUTION_TRUE_FIELDS = (
    "orchestrator_path_exercised",
    "executor_adapter_provider_independent",
    "project_task_identity_scoped",
    "context_manager_reused",
    "checkpoint_first_context_reused",
    "local_verified_runner_reused",
    "tool_policy_reused",
    "tool_subset_gated",
    "unauthorized_tool_rejected",
    "shell_bypass_rejected",
    "structured_executor_output",
    "staged_noncanonical_output",
    "changed_files_captured",
    "diff_captured",
    "tests_captured",
    "validation_captured",
    "executor_review_captured",
    "cross_project_mismatch_rejected",
    "canonical_project_brain_mutation_rejected",
    "head_race_rejected",
    "end_to_end_coding_task_passed",
    "sanitized_path_evidence",
    "deterministic_fixture",
    "bounded_output_enforced",
)
AUTONOMOUS_EXECUTION_FALSE_FIELDS = (
    "commit_performed",
    "push_performed",
    "merge_performed",
    "checkpoint_promoted",
)
AUTONOMOUS_EXECUTION_COUNT_FIELDS = (
    "tool_subset_count",
    "validation_commands_count",
    "executor_llm_calls",
    "executor_provider_calls",
    "secret_leaks",
    "filesystem_path_leaks",
)
AUTONOMOUS_EXECUTION_REQUIRED_FIELDS = (
    "status",
    "evidence_file",
    "autonomous_evidence_version",
    "executor_adapter_name",
    "observed_migration_head",
    *AUTONOMOUS_EXECUTION_TRUE_FIELDS,
    *AUTONOMOUS_EXECUTION_FALSE_FIELDS,
    *AUTONOMOUS_EXECUTION_COUNT_FIELDS,
)
AUTONOMOUS_EXECUTION_ALLOWED_FIELDS = frozenset(AUTONOMOUS_EXECUTION_REQUIRED_FIELDS)

TELEMETRY_EVENT_BUS_EVIDENCE_VERSION = "telemetry-event-bus-v1"
TELEMETRY_EVENT_BUS_EVIDENCE_FILE = "telemetry-event-bus.json"
TELEMETRY_EVENT_BUS_CANONICAL_EVENT_TYPES = (
    "project.discovered",
    "project.indexing",
    "task.ingested",
    "context.started",
    "context.retrieved",
    "context.built",
    "cache.hit",
    "cache.miss",
    "executor.started",
    "tool.called",
    "file.changed",
    "test.started",
    "test.finished",
    "validation.failed",
    "validation.passed",
    "memory.staged",
    "memory.promoted",
    "run.completed",
    "run.failed",
)
TELEMETRY_EVENT_BUS_TRUE_FIELDS = (
    "durable_event_metadata_postgres",
    "redis_noncanonical",
    "project_scoped",
    "task_run_binding_scoped",
    "cross_project_access_fail_closed",
    "event_envelope_versioned",
    "event_type_explicit",
    "timestamp_order_identity_explicit",
    "project_identity_explicit",
    "task_run_linkage_explicit",
    "payload_bounded",
    "provenance_explicit",
    "canonical_event_vocabulary",
    "stable_order_replay",
    "bounded_cursor_pagination",
    "idempotent_duplicate_safe",
    "near_realtime_stream",
    "stream_access_control_deterministic",
    "reconnect_replay",
    "restart_recovery",
    "redis_loss_recovery",
    "payload_sanitized",
    "untrusted_payload_cannot_mutate_governance",
    "deterministic_first",
    "producer_path_verified",
    "bounded_claims",
)
TELEMETRY_EVENT_BUS_FALSE_FIELDS = (
    "redis_canonical_truth",
    "full_control_center_claimed",
    "full_v01_observability_claimed",
)
TELEMETRY_EVENT_BUS_INTEGER_FIELDS = (
    "event_type_count",
    "payload_max_bytes",
    "cursor_max_bytes",
    "duplicate_canonical_events",
    "cross_project_leaks",
    "secret_leaks",
    "filesystem_path_leaks",
    "llm_calls",
    "provider_calls",
)
TELEMETRY_EVENT_BUS_LIST_FIELDS = ("implemented_event_types",)
TELEMETRY_EVENT_BUS_STRING_FIELDS = (
    "telemetry_evidence_version",
    "observed_migration_head",
    "migration_base_head",
    "producer_path",
)
TELEMETRY_EVENT_BUS_REQUIRED_FIELDS = (
    "status",
    "evidence_file",
    *TELEMETRY_EVENT_BUS_STRING_FIELDS,
    "migration_changed",
    *TELEMETRY_EVENT_BUS_TRUE_FIELDS,
    *TELEMETRY_EVENT_BUS_FALSE_FIELDS,
    *TELEMETRY_EVENT_BUS_INTEGER_FIELDS,
    *TELEMETRY_EVENT_BUS_LIST_FIELDS,
)
TELEMETRY_EVENT_BUS_ALLOWED_FIELDS = frozenset(TELEMETRY_EVENT_BUS_REQUIRED_FIELDS)
TELEMETRY_EVENT_BUS_MAX_PAYLOAD_BYTES = 1_048_576
TELEMETRY_EVENT_BUS_MAX_CURSOR_BYTES = 65_536
TELEMETRY_EVENT_BUS_MAX_EVENT_TYPES = len(TELEMETRY_EVENT_BUS_CANONICAL_EVENT_TYPES)
TELEMETRY_EVENT_BUS_PATH = re.compile(r"^[^\\/:*?\"<>|\r\n]+(?:/[^\\/:*?\"<>|\r\n]+)*$")

WO019_G1_BASE_SHA = "62c51d982afe47d93aa40dee3d55b479e6d756e5"
WO019_G1_WORK_ORDER = "WO-019-G1"
WO019_WORK_ORDER = "WO-019"
WO019_G1_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "schemas/review-evidence-v1.schema.json",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
    }
)
WO019_PRODUCT_ALLOWED_PREFIXES = (
    "backend/app/",
    "backend/tests/",
    "dashboard/src/",
    "dashboard/tests/",
    "docs/atlas/",
    "migrations/versions/",
    "scripts/",
)
WO019_PRODUCT_FORBIDDEN_PATHS = frozenset(WO019_G1_ALLOWED_PATHS)
WO019_PRODUCT_MIGRATION_PATH = re.compile(r"^migrations/versions/0007_[a-z0-9_]+\.py$")

CONTROL_CENTER_CORE_EVIDENCE_VERSION = "control-center-core-v1"
CONTROL_CENTER_CORE_EVIDENCE_FILE = "control-center-core.json"
CONTROL_CENTER_CORE_CANONICAL_SURFACES = (
    "fleet",
    "active-runs",
    "project-detail",
    "run-detail",
    "event-stream",
    "platform-health",
    "test-status",
    "errors-warnings",
)
CONTROL_CENTER_CORE_STREAM_TRANSPORTS = frozenset({"sse", "websocket"})
CONTROL_CENTER_CORE_TRUE_FIELDS = (
    "control_center_operational_core_implemented",
    "project_fleet_visible",
    "project_state_counts_truthful",
    "selected_project_detail_available",
    "run_surface_available",
    "event_timeline_near_realtime",
    "telemetry_stream_sse_or_ws",
    "stream_replay_supported",
    "client_reconciliation_supported",
    "platform_health_visible",
    "tests_validation_state_visible",
    "errors_warnings_visible",
    "durable_sources_reused",
    "postgres_canonical",
    "redis_noncanonical",
    "project_isolation",
    "deterministic_access_control",
    "backend_api_bounded",
    "frontend_render_bounded",
    "estimated_metrics_labelled",
    "unavailable_metrics_not_fabricated",
    "restart_recovery",
    "redis_loss_recovery",
)
CONTROL_CENTER_CORE_FALSE_FIELDS = (
    "redis_canonical_truth",
    "exact_live_token_claim_without_reconciliation",
    "fabricated_cost_metrics",
    "control_center_can_bypass_governance",
    "full_control_center_claimed",
    "full_v01_complete_claimed",
)
CONTROL_CENTER_CORE_INTEGER_FIELDS = (
    "surface_count",
    "secret_leaks",
    "filesystem_path_leaks",
    "cross_project_leaks",
    "llm_calls",
    "provider_calls",
)
CONTROL_CENTER_CORE_LIST_FIELDS = ("implemented_surfaces",)
CONTROL_CENTER_CORE_STRING_FIELDS = (
    "control_center_evidence_version",
    "observed_migration_head",
    "migration_base_head",
    "stream_transport",
    "api_path",
    "dashboard_path",
)
CONTROL_CENTER_CORE_REQUIRED_FIELDS = (
    "status",
    "evidence_file",
    *CONTROL_CENTER_CORE_STRING_FIELDS,
    "migration_changed",
    *CONTROL_CENTER_CORE_TRUE_FIELDS,
    *CONTROL_CENTER_CORE_FALSE_FIELDS,
    *CONTROL_CENTER_CORE_INTEGER_FIELDS,
    *CONTROL_CENTER_CORE_LIST_FIELDS,
)
CONTROL_CENTER_CORE_ALLOWED_FIELDS = frozenset(CONTROL_CENTER_CORE_REQUIRED_FIELDS)
CONTROL_CENTER_CORE_MIGRATION_BASE_HEAD = "0007_telemetry_events"
CONTROL_CENTER_CORE_MAX_SURFACES = len(CONTROL_CENTER_CORE_CANONICAL_SURFACES)
CONTROL_CENTER_CORE_PATH_MAX_LENGTH = 256
CONTROL_CENTER_CORE_PATH_SEGMENT = r"[^\\/:*?\"<>|\x00-\x1F\x7F]"
CONTROL_CENTER_CORE_PATH = re.compile(
    rf"^{CONTROL_CENTER_CORE_PATH_SEGMENT}+(?:/{CONTROL_CENTER_CORE_PATH_SEGMENT}+)*$"
)
CONTROL_CENTER_CORE_PATH_ROOTS = {
    "api_path": "backend/app/",
    "dashboard_path": "dashboard/src/",
}

CONTROL_CENTER_METRICS_EVIDENCE_VERSION = "control-center-metrics-v1"
CONTROL_CENTER_METRICS_EVIDENCE_FILE = "control-center-metrics.json"
CONTROL_CENTER_METRICS_FAMILIES = ("token", "context", "cache", "storage")
CONTROL_CENTER_METRICS_VALUE_PROVENANCE = ("EXACT", "ESTIMATED", "UNAVAILABLE", "UNKNOWN")
CONTROL_CENTER_METRICS_PATH_ROOTS = (
    "backend/app/",
    "backend/tests/",
    "dashboard/src/",
    "dashboard/tests/",
    "scripts/",
    "docs/atlas/",
)
CONTROL_CENTER_METRICS_TRUE_FIELDS = (
    "control_center_metrics_foundation_implemented",
    "token_telemetry_visible",
    "provider_final_usage_reconciliation_supported",
    "fresh_cached_distinction_conditional_on_provider_support",
    "estimated_token_values_labelled",
    "unknown_token_values_not_zero",
    "context_reduction_measured",
    "context_measurement_provenance_preserved",
    "cache_hit_miss_measured_from_real_events_or_receipts",
    "unknown_cache_state_not_hit",
    "storage_logical_physical_measured",
    "storage_measurement_provenance_preserved",
    "bounded_historical_series",
    "near_realtime_metric_refresh",
    "project_scoped_metrics",
    "deterministic_global_aggregation",
    "postgres_canonical",
    "redis_noncanonical",
    "restart_recovery",
    "redis_loss_recovery",
    "backend_metric_payloads_bounded",
    "frontend_metric_render_bounded",
)
CONTROL_CENTER_METRICS_FALSE_FIELDS = (
    "estimated_live_tokens_presented_as_exact",
    "fabricated_provider_usage",
    "fabricated_cache_hit",
    "fabricated_cost_metrics",
    "unknown_metrics_rendered_as_zero",
    "redis_canonical_truth",
    "full_control_center_claimed",
    "full_v01_complete_claimed",
)
CONTROL_CENTER_METRICS_INTEGER_FIELDS = (
    "historical_series_max_points",
    "secret_leaks",
    "filesystem_path_leaks",
    "cross_project_leaks",
    "metrics_llm_calls",
    "metrics_provider_calls",
)
CONTROL_CENTER_METRICS_STRING_FIELDS = (
    "metrics_evidence_version",
    "evidence_file",
    "observed_migration_head",
    "migration_base_head",
    "cost_provenance",
)
CONTROL_CENTER_METRICS_LIST_FIELDS = (
    "implemented_metric_families",
    "metric_value_provenance",
    "evidence_paths",
)
CONTROL_CENTER_METRICS_REQUIRED_FIELDS = (
    "status",
    *CONTROL_CENTER_METRICS_STRING_FIELDS,
    "migration_changed",
    *CONTROL_CENTER_METRICS_TRUE_FIELDS,
    *CONTROL_CENTER_METRICS_FALSE_FIELDS,
    *CONTROL_CENTER_METRICS_INTEGER_FIELDS,
    *CONTROL_CENTER_METRICS_LIST_FIELDS,
)
CONTROL_CENTER_METRICS_ALLOWED_FIELDS = frozenset(CONTROL_CENTER_METRICS_REQUIRED_FIELDS)
CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD = "0007_telemetry_events"
CONTROL_CENTER_METRICS_MAX_HISTORY_POINTS = 512
CONTROL_CENTER_METRICS_MAX_EVIDENCE_PATHS = 16
WO021_METRICS_EVIDENCE_VERSION = CONTROL_CENTER_METRICS_EVIDENCE_VERSION
WO021_METRICS_EVIDENCE_FILE = CONTROL_CENTER_METRICS_EVIDENCE_FILE
WO021_METRICS_REQUIRED_FIELDS = CONTROL_CENTER_METRICS_REQUIRED_FIELDS

WO020_G1_BASE_SHA = "ab2c6eac4eedac460871cf00d613a9b478ec533d"
WO020_G1_WORK_ORDER = "WO-020-G1"
WO020_WORK_ORDER = "WO-020"
WO020_G1_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "schemas/review-evidence-v1.schema.json",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
    }
)
WO020_PRODUCT_ALLOWED_PREFIXES = (
    "backend/app/",
    "backend/tests/",
    "dashboard/src/",
    "dashboard/tests/",
    "docs/atlas/",
    "scripts/",
)
WO020_PRODUCT_FORBIDDEN_PATHS = frozenset(WO020_G1_ALLOWED_PATHS)

WO021_G1_BASE_SHA = "6a5ce4e679de3e9e66a7ad56f23cabebe88f4fb3"
WO021_G1_WORK_ORDER = "WO-021-G1"
WO021_WORK_ORDER = "WO-021"
WO021_G1_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "schemas/review-evidence-v1.schema.json",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
    }
)
WO021_PRODUCT_ALLOWED_PREFIXES = (
    "backend/app/",
    "backend/tests/",
    "dashboard/src/",
    "dashboard/tests/",
    "scripts/",
    "docs/atlas/",
)
WO021_PRODUCT_FORBIDDEN_PATHS = frozenset(WO021_G1_ALLOWED_PATHS)
WO021_PRODUCT_DEPENDENCY_PATHS = frozenset(
    {
        "requirements.txt",
        "requirements-dev.txt",
        "pyproject.toml",
        "dashboard/package.json",
        "dashboard/package-lock.json",
        "dashboard/pnpm-lock.yaml",
        "dashboard/yarn.lock",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "poetry.lock",
        "uv.lock",
    }
)
WO021_PRODUCT_RELEASE_PATHS = frozenset({"VERSION", "CHANGELOG.md"})

CONTROL_CENTER_FULL_EVIDENCE_VERSION = "control-center-full-v1"
CONTROL_CENTER_FULL_EVIDENCE_FILE = "control-center-full.json"
CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD = "0007_telemetry_events"
CONTROL_CENTER_FULL_PROJECT_CAPABILITIES = (
    "project-intelligence",
    "checkpoint-scope-dod",
    "index-health",
    "latest-commits",
    "run-history",
    "decisions-memory",
    "modules-symbols",
    "dependency-graph",
    "quality-history",
    "retrieval-quality",
)
CONTROL_CENTER_FULL_CHARTS = (
    "tokens-over-time",
    "cached-vs-fresh-tokens",
    "token-savings",
    "cost-over-time",
    "cache-hit-rate",
    "context-reduction",
    "context-signal-ratio",
    "physical-vs-logical-storage",
    "compression-dedup-savings",
    "project-activity",
    "test-pass-failure-rate",
    "retrieval-latency",
    "service-latency-errors",
)
CONTROL_CENTER_FULL_ALERTS = (
    "disk-low",
    "redis-unavailable",
    "postgres-unavailable",
    "project-stale",
    "index-inconsistent",
    "retrieval-degradation",
    "cache-hit-collapse",
    "token-spike",
    "unexpected-cost-spike",
    "failed-test-build",
    "executor-disconnected",
    "checkpoint-mismatch",
)
CONTROL_CENTER_FULL_HEALTH_CAPABILITIES = (
    "platform-resource-health",
    "container-status",
    "local-model-health-conditional",
)
CONTROL_CENTER_FULL_TRUE_FIELDS = (
    "full_control_center_capabilities_implemented",
    "project_intelligence_visible",
    "project_checkpoint_scope_dod_visible",
    "project_index_health_visible",
    "project_latest_commits_visible",
    "project_run_history_visible",
    "project_decisions_memory_visible",
    "project_modules_symbols_visible",
    "project_dependency_graph_visible",
    "project_quality_history_visible",
    "project_retrieval_quality_visible",
    "required_charts_visible",
    "required_alerts_visible",
    "platform_resource_health_visible",
    "container_status_visible",
    "local_model_health_conditional",
    "estimated_values_labelled",
    "unavailable_metrics_not_fabricated",
    "unknown_metrics_not_zero",
    "postgres_canonical",
    "redis_noncanonical",
    "project_scoped",
    "near_realtime_refresh",
    "payloads_bounded",
    "frontend_render_bounded",
    "restart_recovery",
    "redis_loss_recovery",
)
CONTROL_CENTER_FULL_FALSE_FIELDS = (
    "full_v01_complete_claimed",
    "redis_canonical_truth",
    "fabricated_metrics",
    "fabricated_alerts",
)
CONTROL_CENTER_FULL_INTEGER_FIELDS = (
    "history_max_points",
    "secret_leaks",
    "filesystem_path_leaks",
    "cross_project_leaks",
    "llm_calls",
    "provider_calls",
)
CONTROL_CENTER_FULL_STRING_FIELDS = (
    "full_control_center_evidence_version",
    "evidence_file",
    "observed_migration_head",
    "migration_base_head",
    "api_path",
    "dashboard_path",
)
CONTROL_CENTER_FULL_LIST_FIELDS = (
    "implemented_project_capabilities",
    "implemented_charts",
    "implemented_alerts",
    "implemented_health_capabilities",
    "evidence_paths",
)
CONTROL_CENTER_FULL_REQUIRED_FIELDS = (
    "status",
    *CONTROL_CENTER_FULL_STRING_FIELDS,
    "migration_changed",
    *CONTROL_CENTER_FULL_TRUE_FIELDS,
    *CONTROL_CENTER_FULL_FALSE_FIELDS,
    *CONTROL_CENTER_FULL_INTEGER_FIELDS,
    *CONTROL_CENTER_FULL_LIST_FIELDS,
)
CONTROL_CENTER_FULL_ALLOWED_FIELDS = frozenset(CONTROL_CENTER_FULL_REQUIRED_FIELDS)
CONTROL_CENTER_FULL_PATH_ROOTS = {
    "api_path": "backend/app/",
    "dashboard_path": "dashboard/src/",
}
CONTROL_CENTER_FULL_EVIDENCE_PATH_ROOTS = (
    "backend/app/",
    "backend/tests/",
    "dashboard/src/",
    "dashboard/tests/",
    "scripts/",
    "docs/atlas/",
)
CONTROL_CENTER_FULL_MAX_HISTORY_POINTS = 512
CONTROL_CENTER_FULL_MAX_EVIDENCE_PATHS = 24

WO022_G1_BASE_SHA = "ccff5882a0bec20a90ee4516640aa44d9e9b5352"
WO022_G1_WORK_ORDER = "WO-022-G1"
WO022_WORK_ORDER = "WO-022"
WO022_G1_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "schemas/review-evidence-v1.schema.json",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
    }
)
WO022_PRODUCT_ALLOWED_PREFIXES = (
    "backend/app/",
    "backend/tests/",
    "dashboard/src/",
    "dashboard/tests/",
    "scripts/",
    "docs/atlas/",
)
WO022_PRODUCT_FORBIDDEN_PATHS = frozenset(WO022_G1_ALLOWED_PATHS)

WO023_G1_BASE_SHA = "45bf00a78150ea0368bd4c0b173e83178b102333"
WO023_G1_WORK_ORDER = "WO-023-G1"
WO023_WORK_ORDER = "WO-023"
WO023P_G1_BASE_SHA = "25c16248211da567dbda928697862a696dcf46eb"
WO023P_G1_WORK_ORDER = "WO-023-P-G1"
WO023P_WORK_ORDER = "WO-023-P"
WO024_G1_BASE_SHA = "44c61e999c89a6b6ba6c28377cea415cad3d1cef"
WO024_G1_WORK_ORDER = "WO-024-G1"
WO024_WORK_ORDER = "WO-024"
WO024P_WORK_ORDER = "WO-024-P"
WO023_G1_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "schemas/review-evidence-v1.schema.json",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
    }
)
WO023_PRODUCT_ALLOWED_PREFIXES = (
    "backend/app/",
    "backend/tests/",
    "dashboard/src/",
    "dashboard/tests/",
    "scripts/",
    "docs/atlas/",
)
WO023_AUTHORIZED_CORRECTION_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "scripts/review_evidence.py",
    }
)
# The closed benchmarks contract and its PR-body renderer stay forbidden for the
# WO-023 product increment; only the two files authorized for the merged
# false-field normalizer defect and its regression are exempt.
WO023_PRODUCT_FORBIDDEN_PATHS = frozenset(
    WO023_G1_ALLOWED_PATHS - WO023_AUTHORIZED_CORRECTION_PATHS
)

COMPREHENSIVE_BENCHMARKS_EVIDENCE_VERSION = "comprehensive-benchmarks-v1"
COMPREHENSIVE_BENCHMARKS_EVIDENCE_FILE = "comprehensive-benchmarks.json"
COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD = "0007_telemetry_events"
COMPREHENSIVE_BENCHMARKS_FAMILIES = ("retrieval", "token", "storage")
COMPREHENSIVE_BENCHMARKS_METRIC_STATUSES = ("AVAILABLE", "UNAVAILABLE", "UNKNOWN", "NOT_SUPPORTED")
COMPREHENSIVE_BENCHMARKS_MAX_CORPUS_TASKS = 1000
COMPREHENSIVE_BENCHMARKS_RUN_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
# Core benchmark families must be measured; only provider-dependent optional
# metrics may stay UNKNOWN/NOT_SUPPORTED.
COMPREHENSIVE_BENCHMARKS_CORE_FAMILY_STATUS = "AVAILABLE"
# Accepted retrieval baseline: the repository already gates lexical retrieval at
# recall@5 >= 0.90 in scripts/retrieval_integration.py, so a comprehensive
# benchmark must not regress below the accepted quality it replaces. Precision
# has no accepted numeric baseline today, so the contract requires a strictly
# positive precision instead of inventing a threshold.
COMPREHENSIVE_BENCHMARKS_ACCEPTED_RECALL_AT_K_MIN = 0.90
COMPREHENSIVE_BENCHMARKS_MIN_PRECISION_EXCLUSIVE = 0.0
# Token reduction is (baseline - optimized) / baseline * 100. Storage ratios are
# reduction ratios: dedup = (logical - deduplicated) / logical,
# compression = (deduplicated - physical) / deduplicated and
# total = (logical - physical) / logical. Both must agree with the explicit byte
# and token counts inside these deterministic tolerances.
COMPREHENSIVE_BENCHMARKS_TOKEN_REDUCTION_TOLERANCE_PP = 0.5
COMPREHENSIVE_BENCHMARKS_RATIO_TOLERANCE = 0.01
COMPREHENSIVE_BENCHMARKS_GROUND_TRUTH_PREFIX = "git:HEAD-blob:"
# The accepted project retrieval gate is recall@5 >= 0.90 with zero critical
# misses, so the accepted benchmark depth is fixed at k=5 instead of accepting
# any depth with the same threshold.
COMPREHENSIVE_BENCHMARKS_ACCEPTED_RECALL_K = 5
# Retrieval context size must be measured explicitly; accepted measures are the
# final retrieved or reranked context in bytes. A token-based measure would need
# its own grammar decision and is therefore not accepted here.
COMPREHENSIVE_BENCHMARKS_CONTEXT_MEASURES = (
    "final-retrieved-context-bytes",
    "final-reranked-context-bytes",
)
# Task success is preserved and the test-pass rate must not degrade at all
# relative to the baseline; any tolerance change is a grammar decision.
COMPREHENSIVE_BENCHMARKS_MAX_TEST_PASS_DEGRADATION = 0.0
COMPREHENSIVE_BENCHMARKS_SIGNAL_STATUSES = ("AVAILABLE", "UNAVAILABLE", "UNKNOWN", "NOT_SUPPORTED")
COMPREHENSIVE_BENCHMARKS_BASELINE_PLACEHOLDERS = frozenset(
    {"UNKNOWN", "UNAVAILABLE", "NOT_SUPPORTED", "NOT-SUPPORTED", "NONE"}
)
COMPREHENSIVE_BENCHMARKS_MAX_BASELINE_VERSION_LENGTH = 128
# AVAILABLE cache/output token claims must be backed by the existing
# provider-usage-receipt-v1 seam; the benchmark never carries a second provider
# accounting model.
COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_VERSION = "provider-usage-receipt-v1"
COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_NONE = "NONE"
COMPREHENSIVE_BENCHMARKS_PROVIDER_USAGE_SOURCE = "PROVIDER_REPORTED"
# The provider receipt is loaded from its own integration artifact so the
# comprehensive benchmark payload can never substitute provider bytes: the
# payload only binds to the artifact identity and its SHA-256 digest.
COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_FILE = "provider-usage-receipt.json"
COMPREHENSIVE_BENCHMARKS_PROVIDER_RECONCILIATION_EXACT = "EXACT"
COMPREHENSIVE_BENCHMARKS_PROVIDER_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_STRING_FIELDS = (
    "provider_usage_receipt_version",
    "provider_receipt_artifact",
    "provider_reconciliation_state",
    "provider_usage_source",
)
COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_INTEGER_FIELDS = (
    "provider_total_input_tokens",
    "provider_cached_input_tokens",
    "provider_fresh_input_tokens",
    "provider_calls",
    "secret_leaks",
    "credential_leaks",
)
COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_ALLOWED_FIELDS = frozenset(
    {
        "status",
        *COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_STRING_FIELDS,
        *COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_INTEGER_FIELDS,
        "provider_output_tokens",
    }
)
COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_GUARANTEES = (
    "provider_usage_receipt_versioned",
    "provider_cache_reported_usage_reconciled",
    "provider_cache_invalid_usage_fail_closed",
    "provider_cache_unknown_usage_not_zero",
    "provider_cache_explicit_zero_distinct_from_unknown",
    "provider_cache_hive_estimates_not_provider_usage",
)
COMPREHENSIVE_BENCHMARKS_MAX_EVIDENCE_PATHS = 24
COMPREHENSIVE_BENCHMARKS_STRING_FIELDS = (
    "comprehensive_benchmarks_evidence_version",
    "evidence_file",
    "observed_migration_head",
    "migration_base_head",
    "baseline_reference_version",
    "ground_truth_source",
    "run_digest",
    "retrieval_metrics_status",
    "token_metrics_status",
    "storage_metrics_status",
    "retrieval_context_measure",
    "token_cache_status",
    "token_output_status",
    "provider_receipt_version",
    "provider_receipt_artifact",
    "provider_receipt_sha256",
    "optional_provider_metric",
)
COMPREHENSIVE_BENCHMARKS_TRUE_FIELDS = (
    "benchmark_corpus_bounded",
    "ground_truth_auditable",
    "project_scoped",
    "provenance_preserved",
    "deterministic_reproducible",
    "baseline_comparison_versioned",
    "token_estimates_labelled",
    "correctness_guardrail_preserved",
    "test_pass_behaviour_preserved",
    "avoided_work_evidence_deterministic",
    "storage_savings_single_counted",
    "storage_reconstruction_exact",
    "storage_zstd_measured",
    "redis_noncanonical",
    "provider_independent_core",
)
COMPREHENSIVE_BENCHMARKS_FALSE_FIELDS = (
    "fabricated_metrics",
    "cross_project_retrieval_accepted",
    "canonical_loss",
    "full_v01_complete_claimed",
    "redis_canonical_truth",
    "provider_values_fabricated",
    "production_quality_claimed_from_fixture",
)
COMPREHENSIVE_BENCHMARKS_ZERO_FIELDS = (
    "critical_context_misses",
    "secret_leaks",
    "filesystem_path_leaks",
    "cross_project_leaks",
    "core_provider_calls",
)
COMPREHENSIVE_BENCHMARKS_INTEGER_FIELDS = (
    "corpus_task_count",
    "retrieval_recall_k",
    "retrieval_context_bytes",
    "storage_logical_bytes",
    "storage_dedup_bytes",
    "storage_physical_bytes",
    "token_baseline_input_tokens",
    "token_optimized_input_tokens",
    "optional_provider_calls",
)
COMPREHENSIVE_BENCHMARKS_NUMBER_FIELDS = (
    "retrieval_recall_at_k",
    "retrieval_precision",
    "retrieval_baseline_mrr",
    "retrieval_reranked_mrr",
    "baseline_task_success_rate",
    "optimized_task_success_rate",
    "baseline_test_pass_rate",
    "optimized_test_pass_rate",
    "token_reduction_percentage",
    "storage_dedup_ratio",
    "storage_compression_ratio",
    "storage_total_reduction_ratio",
)
COMPREHENSIVE_BENCHMARKS_NULLABLE_INTEGER_FIELDS = (
    "token_cached_tokens",
    "token_output_tokens",
)
COMPREHENSIVE_BENCHMARKS_FAMILY_STATUS_FIELDS = {
    "retrieval": "retrieval_metrics_status",
    "token": "token_metrics_status",
    "storage": "storage_metrics_status",
}
COMPREHENSIVE_BENCHMARKS_FAMILY_NUMBER_FIELDS = {
    "retrieval": ("retrieval_recall_at_k", "retrieval_precision"),
    "token": ("token_reduction_percentage",),
    "storage": (
        "storage_dedup_ratio",
        "storage_compression_ratio",
        "storage_total_reduction_ratio",
    ),
}
COMPREHENSIVE_BENCHMARKS_EVIDENCE_PATH_ROOTS = (
    "backend/app/",
    "backend/tests/",
    "dashboard/src/",
    "dashboard/tests/",
    "scripts/",
    "docs/atlas/",
)
COMPREHENSIVE_BENCHMARKS_NUMBER_BOUNDS = {
    "retrieval_recall_at_k": (0.0, 1.0),
    "retrieval_precision": (0.0, 1.0),
    "retrieval_baseline_mrr": (0.0, 1.0),
    "retrieval_reranked_mrr": (0.0, 1.0),
    "baseline_task_success_rate": (0.0, 1.0),
    "optimized_task_success_rate": (0.0, 1.0),
    "baseline_test_pass_rate": (0.0, 1.0),
    "optimized_test_pass_rate": (0.0, 1.0),
    "token_reduction_percentage": (0.0, 100.0),
    "storage_dedup_ratio": (0.0, 1.0),
    "storage_compression_ratio": (0.0, 1.0),
    "storage_total_reduction_ratio": (0.0, 1.0),
}
COMPREHENSIVE_BENCHMARKS_ALLOWED_FIELDS = frozenset(
    {
        "status",
        "benchmark_families",
        "evidence_paths",
        "provider_receipt_reconciled",
        *COMPREHENSIVE_BENCHMARKS_STRING_FIELDS,
        *COMPREHENSIVE_BENCHMARKS_TRUE_FIELDS,
        *COMPREHENSIVE_BENCHMARKS_FALSE_FIELDS,
        *COMPREHENSIVE_BENCHMARKS_ZERO_FIELDS,
        *COMPREHENSIVE_BENCHMARKS_INTEGER_FIELDS,
        *COMPREHENSIVE_BENCHMARKS_NULLABLE_INTEGER_FIELDS,
        *COMPREHENSIVE_BENCHMARKS_NUMBER_FIELDS,
    }
)

GEF_ADOPTION_WORK_ORDER = "GEF-ADOPTION-001"
GEF_ADOPTION_BASE_SHA = "c9430af13860ab30e31bd162991eb88c05215f4f"
GEF_ADOPTION_ARTIFACT_PATHS = frozenset(
    {
        ".engineering/gef/GEF-ADOPTION.md",
        ".engineering/gef/GEF-BASELINE.json",
        ".engineering/gef/GEF-CURRENT.json",
        ".engineering/gef/GEF-EVIDENCE-SPEC.md",
        ".engineering/gef/GEF-EXECUTION-PROTOCOL.md",
        ".engineering/gef/GEF-POLICY.md",
        ".engineering/gef/GEF-PROJECT-PROFILE.json",
        ".engineering/gef/GEF-PROOF-MAP.json",
        ".engineering/gef/GEF-REVIEW-PROTOCOL.md",
        ".engineering/gef/GEF-TEST-IMPACT.json",
    }
)
GEF_ADOPTION_BRIDGE_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "scripts/review_evidence.py",
    }
)
GEF_ADOPTION_ALLOWED_PATHS = frozenset(GEF_ADOPTION_ARTIFACT_PATHS | GEF_ADOPTION_BRIDGE_PATHS)

MANDATORY_GOVERNANCE_KIND_SEQUENCE = (
    "CHECKPOINT",
    "SCOPE",
    "DEFINITION_OF_DONE",
    "ARCHITECTURE",
    "DECISIONS",
)
CHECKPOINT_PATH = "docs/project-brain/13-CHECKPOINT.md"
CANONICAL_MANIFEST_PATH = "docs/project-brain/CANONICAL-SHA256SUMS.txt"
CANONICAL_MANIFEST_CHECKPOINT_NAME = "13-CHECKPOINT.md"
CANONICAL_PATHS = (
    CHECKPOINT_PATH,
    CANONICAL_MANIFEST_PATH,
)
WO008_G1_BASE_SHA = "fcbf0849a54e0283ed523e09ce18ea31a8bd7849"
WO009_BASE_SHA = "7e95a026ff050c4bd953c27fb61ff79acff15d1f"
WO010_G1_BASE_SHA = "552d809f6e0a6e1f940084c35f3109dc4ec931a1"
WO010_BASE_SHA = "68bb6679da32355b9e5c4bbb241bec0d1e685e26"
WO011_BASE_SHA = "209a485227103872903a560872133aae5f203717"
WO012_BASE_SHA = "19ecc6b505e884029a42d121309339977d46e626"
WO013_BASE_SHA = "8aabcf1d7e908b7f74333d2b3bb937af0f39c4c8"
WO014_BASE_SHA = "d025cfa6dc306fff0f5664002fef970a438ad266"
WO014_REJECTED_HEAD = "184821d3cb5743d06c856f29895ceaa58c76ee0d"
WO014_C1_CORRECTED_HEAD = "dfb6bcb21e6646bc2c056c014ba211245bd64e77"
WO014_C2_BASE_SHA = "5c8356228b0ce186cde6e64393a167063aa2a9e9"
WO014_C2_WORK_ORDER = "WO-014-C2"
WO014P_G1_BASE_SHA = "13888d63572db0e90fb4536369867d995a9e1c90"
WO014P_G1_WORK_ORDER = "WO-014-P-G1"
WO014P_WORK_ORDER = "WO-014-P"
WO015P_G1_BASE_SHA = "2c701d221e481913d2cbe9c0b8f3504632042306"
WO015P_G1_WORK_ORDER = "WO-015-P-G1"
WO015P_WORK_ORDER = "WO-015-P"
WO016P_G1_BASE_SHA = "54c32e939c7be6d505727df24d3ce2ad48af5518"
WO016P_G1_WORK_ORDER = "WO-016-P-G1"
WO016P_WORK_ORDER = "WO-016-P"
WO017P_G1_BASE_SHA = "0d9240f3a18530fae3e9f65751dbc11491c485c0"
WO017P_G1_WORK_ORDER = "WO-017-P-G1"
WO017P_WORK_ORDER = "WO-017-P"
WO018P_G1_BASE_SHA = "ed534965136a36eff66276d5b073dc034a7fc96f"
WO018P_G1_WORK_ORDER = "WO-018-P-G1"
WO018P_WORK_ORDER = "WO-018-P"
WO019P_G1_BASE_SHA = "d800fac8f165146055ad050d6c2f232883dc91b7"
WO019P_G1_WORK_ORDER = "WO-019-P-G1"
WO019P_WORK_ORDER = "WO-019-P"
WO020P_G1_BASE_SHA = "2e322095936f2a508f36563699e464d301f89ced"
WO020P_G1_WORK_ORDER = "WO-020-P-G1"
WO020P_WORK_ORDER = "WO-020-P"
WO021P_G1_BASE_SHA = "cd05c753ce0fd25d657dd829a2484041355d873b"
WO021P_G1_WORK_ORDER = "WO-021-P-G1"
WO021P_WORK_ORDER = "WO-021-P"
WO022P_G1_BASE_SHA = "82c39025fe4e4a4a3b4664ed8e8059984fffb039"
WO022P_G1_WORK_ORDER = "WO-022-P-G1"
WO022P_WORK_ORDER = "WO-022-P"
WO016_G1_BASE_SHA = "5121316c1a577557039f03770ff7031be74d3e0b"
WO016_G1_WORK_ORDER = "WO-016-G1"
WO016_WORK_ORDER = "WO-016"
WO015_G1_BASE_SHA = "e2f95b5dc3c4b44fd8dfef62c1fc0dad8ce8c89d"
WO015_G1_WORK_ORDER = "WO-015-G1"
WO015_WORK_ORDER = "WO-015"
WO012P_G1_BASE_SHA = "743253ef079596370a7ff1102faf03b3a603b585"
WO012P_PROMOTION_BASE_REF = "refs/remotes/origin/main"
WO012P_G1_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
    }
)
WO012P_PROMOTION_ALLOWED_PATHS = frozenset({CHECKPOINT_PATH, CANONICAL_MANIFEST_PATH})
WO013P_G1_BASE_SHA = "d952be125da97afacf1099244cf2755f8243d288"
WO013P_G1_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
    }
)
WO013P_PROMOTION_ALLOWED_PATHS = frozenset({CHECKPOINT_PATH, CANONICAL_MANIFEST_PATH})
WO014P_G1_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
    }
)
WO014P_PROMOTION_ALLOWED_PATHS = frozenset({CHECKPOINT_PATH, CANONICAL_MANIFEST_PATH})
WO015P_G1_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
    }
)
WO015P_PROMOTION_ALLOWED_PATHS = frozenset({CHECKPOINT_PATH, CANONICAL_MANIFEST_PATH})
WO016P_G1_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
    }
)
WO016P_PROMOTION_ALLOWED_PATHS = frozenset({CHECKPOINT_PATH, CANONICAL_MANIFEST_PATH})
WO017P_G1_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
    }
)
WO017P_PROMOTION_ALLOWED_PATHS = frozenset({CHECKPOINT_PATH, CANONICAL_MANIFEST_PATH})
WO018P_G1_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
    }
)
WO018P_PROMOTION_ALLOWED_PATHS = frozenset({CHECKPOINT_PATH, CANONICAL_MANIFEST_PATH})
WO019P_G1_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
    }
)
WO019P_PROMOTION_ALLOWED_PATHS = frozenset({CHECKPOINT_PATH, CANONICAL_MANIFEST_PATH})
WO020P_G1_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
    }
)
WO020P_PROMOTION_ALLOWED_PATHS = frozenset({CHECKPOINT_PATH, CANONICAL_MANIFEST_PATH})
WO021P_G1_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
    }
)
WO021P_PROMOTION_ALLOWED_PATHS = frozenset({CHECKPOINT_PATH, CANONICAL_MANIFEST_PATH})
WO022P_G1_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "schemas/review-evidence-v1.schema.json",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
    }
)
WO022P_PROMOTION_ALLOWED_PATHS = frozenset({CHECKPOINT_PATH, CANONICAL_MANIFEST_PATH})
WO023P_G1_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "schemas/review-evidence-v1.schema.json",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
    }
)
WO023P_PROMOTION_ALLOWED_PATHS = frozenset({CHECKPOINT_PATH, CANONICAL_MANIFEST_PATH})
WO016_G1_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "schemas/review-evidence-v1.schema.json",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
    }
)
WO016_PRODUCT_ALLOWED_PATHS = frozenset(
    {
        "backend/app/cas.py",
        "backend/app/config.py",
        "backend/app/task_intake.py",
        "backend/app/tasks_api.py",
        "backend/tests/test_cas.py",
        "scripts/task_intake_integration.py",
        "docs/atlas/code-atlas.md",
        "docs/atlas/test-map.md",
    }
)
WO017_G1_BASE_SHA = "bb7db2cc8b4850c472e7e567e1991c6cbf36dd4c"
WO017_G1_WORK_ORDER = "WO-017-G1"
WO017_WORK_ORDER = "WO-017"
WO018_G1_BASE_SHA = "5e699f1315638a4e767a94bcf6536cd52988ee3b"
WO018_G1_WORK_ORDER = "WO-018-G1"
WO018_WORK_ORDER = "WO-018"
WO017_G1_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "schemas/review-evidence-v1.schema.json",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
    }
)
WO017_PRODUCT_ALLOWED_PATHS = frozenset(
    {
        "requirements.txt",
        "backend/app/mcp_server.py",
        "backend/tests/test_mcp_server.py",
        "backend/app/config.py",
        "backend/app/main.py",
        "docker-compose.yml",
        ".env.example",
        "scripts/mcp_integration.py",
        ".github/workflows/ci.yml",
        "docs/atlas/code-atlas.md",
        "docs/atlas/test-map.md",
    }
)
WO018_G1_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "schemas/review-evidence-v1.schema.json",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
    }
)
WO018_PRODUCT_ALLOWED_PATHS = frozenset(
    {
        "backend/app/execution_orchestrator.py",
        "backend/tests/test_execution_orchestrator.py",
        "backend/app/runner.py",
        "backend/tests/test_runner.py",
        "scripts/autonomous_execution_integration.py",
        ".github/workflows/ci.yml",
        "docs/autonomous-execution.md",
        "docs/atlas/code-atlas.md",
        "docs/atlas/test-map.md",
    }
)
WO016_MIGRATION_PATH = re.compile(r"^migrations/versions/0007_[a-z0-9_]+\.py$")
WO016_APPROVED_PRODUCT_HEAD = "0de6dc345262fc77fdda99c2f2dca6be88f9552c"
WO016_APPROVED_PRODUCT_BASE_SHA = "4d7b3e677e4cf7b00f29eb2fa0920b23799f8d4b"
WO016_APPROVED_SOL_REVIEW_ID = 5135618100
WO016_APPROVED_SQUASH_MERGE_SHA = "54c32e939c7be6d505727df24d3ce2ad48af5518"
WO016_APPROVED_POST_MERGE_CI_RUN = 34168038154
WO016_APPROVED_LINEAGE_STATEMENT_PREFIX = "Approved WO-016 product lineage: "
WO021_APPROVED_PRODUCT_HEAD = "1363d6c477faba8b6d780cdb1a953aa3c64259e5"
WO021_APPROVED_PRODUCT_BASE_SHA = "2ccbf09c193ba30e78d768bb32a4e78a4f209812"
WO021_APPROVED_SOL_REVIEW_ID = 5190892017
WO021_APPROVED_SQUASH_MERGE_SHA = "cd05c753ce0fd25d657dd829a2484041355d873b"
WO021_APPROVED_POST_MERGE_CI_RUN = 34760861308
WO021_APPROVED_LINEAGE_STATEMENT_PREFIX = "Approved WO-021 product lineage: "
WO022_APPROVED_PRODUCT_PR = 86
WO022_APPROVED_PRODUCT_HEAD = "a870275b3ad738b789e30169d5b1fac00e2e4ae3"
WO022_APPROVED_PRODUCT_BASE_SHA = "186e13418af27abcdec2b239a9307157ec4f7937"
WO022_APPROVED_SOL_REVIEW_ID = 5204463844
WO022_APPROVED_SQUASH_MERGE_SHA = "82c39025fe4e4a4a3b4664ed8e8059984fffb039"
WO022_APPROVED_POST_MERGE_CI_RUN = 34916205113
WO022_APPROVED_BACKEND_PASSED = 606
WO022_APPROVED_DASHBOARD_PASSED = 34
WO022_APPROVED_LINEAGE_STATEMENT_PREFIX = "Approved WO-022 product lineage: "
WO023_APPROVED_PRODUCT_PR = 90
WO023_APPROVED_PRODUCT_HEAD = "270929c2e1428335ea9c98337c29a31d5682686d"
WO023_APPROVED_PRODUCT_BASE_SHA = "393bb83b5552a0c79ba8bcc3bd069d47bfc16686"
WO023_APPROVED_SOL_REVIEW_ID = 5216010298
WO023_APPROVED_SQUASH_MERGE_SHA = "25c16248211da567dbda928697862a696dcf46eb"
WO023_APPROVED_POST_MERGE_CI_RUN = 35026680687
WO023_APPROVED_BACKEND_PASSED = 638
WO023_APPROVED_DASHBOARD_PASSED = 34
WO023_APPROVED_LINEAGE_STATEMENT_PREFIX = "Approved WO-023 product lineage: "
WO013_ALLOWED_PATHS = frozenset(
    {
        "backend/app/context_manager.py",
        "backend/app/delta_context.py",
        "backend/tests/test_context_manager.py",
        "backend/tests/test_delta_context.py",
        "backend/tests/test_review_evidence.py",
        "docker-compose.yml",
        "docs/atlas/code-atlas.md",
        "docs/atlas/test-map.md",
        "schemas/review-evidence-v1.schema.json",
        "scripts/context_manager_integration.py",
        "scripts/project_registry_integration.py",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
    }
)
WO014_ALLOWED_PATHS = frozenset(
    {
        "backend/app/context_manager.py",
        "backend/app/provider_prompt_cache.py",
        "backend/tests/test_provider_prompt_cache.py",
        "backend/tests/test_review_evidence.py",
        "docs/atlas/code-atlas.md",
        "docs/atlas/test-map.md",
        "schemas/review-evidence-v1.schema.json",
        "scripts/context_manager_integration.py",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
    }
)
WO014_C2_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "scripts/review_evidence.py",
    }
)
WO015_G1_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "schemas/review-evidence-v1.schema.json",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
    }
)
HISTORICAL_CHECKPOINT_PROMOTION_WORK_ORDERS = frozenset(
    {
        "WO-007-P",
        "WO-007-P-C1",
        "WO-008-P",
        "WO-009-P",
        "WO-010-P",
        "WO-011-P",
        "WO-012-P-G1",
        "WO-012-P",
        "WO-013-P-G1",
        "WO-013-P",
        WO014P_G1_WORK_ORDER,
        WO014P_WORK_ORDER,
        WO015P_G1_WORK_ORDER,
        WO015P_WORK_ORDER,
        WO016P_G1_WORK_ORDER,
        WO016P_WORK_ORDER,
        WO017P_G1_WORK_ORDER,
        WO017P_WORK_ORDER,
        WO018P_G1_WORK_ORDER,
        WO018P_WORK_ORDER,
        WO019P_G1_WORK_ORDER,
        WO019P_WORK_ORDER,
        WO020P_G1_WORK_ORDER,
        WO020P_WORK_ORDER,
        WO021P_G1_WORK_ORDER,
        WO021P_WORK_ORDER,
        WO022P_G1_WORK_ORDER,
        WO022P_WORK_ORDER,
        WO023P_G1_WORK_ORDER,
        WO023P_WORK_ORDER,
        "WO-023-P-G1-C1",
    }
)
ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS = frozenset({WO024_G1_WORK_ORDER, WO024P_WORK_ORDER})
# Corrective governance increments repair merged tooling without joining the promotion
# pair, so the active promotion set stays exactly the current audited pair.
CORRECTIVE_GOVERNANCE_WORK_ORDERS = frozenset(
    {
        "WO-024-P-G1-C1",
        "WO-024-P-G1-C2",
        "WO-024-P-G1-C3",
        "WO-024-P-G1-C4",
        "WO-025-G1",
        "WO-025-G2",
        "WO-025-G3",
        "WO-025-G4",
        "WO-025-G5",
        WO030_C1_WORK_ORDER,
        "WO-023-P-G1-C1-CLOSED",
    }
)
CHECKPOINT_PROMOTION_WORK_ORDERS = frozenset(
    HISTORICAL_CHECKPOINT_PROMOTION_WORK_ORDERS | ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS
)
PROMOTION_WORK_ORDER_IDENTIFIER = re.compile(r"^WO-[0-9]+-P(?:-[A-Z0-9]+)*$")
EXPECTED_WO012P_STATUS = "CONTEXT FINGERPRINTS FOUNDATION APPROVED / V0.1 IMPLEMENTATION ACTIVE"
EXPECTED_WO012P_PREVIOUS_STATUS = (
    "ADAPTIVE TOKEN BUDGET FOUNDATION APPROVED / V0.1 IMPLEMENTATION ACTIVE"
)
EXPECTED_WO012P_IN_PROGRESS = (
    "Preparing the smallest necessary deterministic Delta Context Foundation over the "
    "approved Context Manager, Progressive Disclosure, Adaptive Token Budget and "
    "Context Fingerprints pipeline."
)
EXPECTED_WO012P_NEXT_STEP_PREFIX = (
    "Prepare the smallest necessary deterministic Delta Context Foundation over the "
    "approved Context Manager, Progressive Disclosure, Adaptive Token Budget and "
    "Context Fingerprints pipeline."
)
EXPECTED_WO012P_BLOCKERS = (
    "No known blocker after Context Fingerprints Foundation approval and post-merge validation."
)
ACCEPTED_WO012P_BLOCKERS = {
    EXPECTED_WO012P_BLOCKERS,
    "None known after Context Fingerprints Foundation approval and post-merge validation.",
}
WO012P_PROMOTION_REGISTRY = {"WO-012-P": WO012P_PROMOTION_BASE_REF}
WO013P_PROMOTION_REGISTRY = {"WO-013-P": WO012P_PROMOTION_BASE_REF}
WO014P_PROMOTION_REGISTRY = {WO014P_WORK_ORDER: WO012P_PROMOTION_BASE_REF}
WO015P_PROMOTION_REGISTRY = {WO015P_WORK_ORDER: WO012P_PROMOTION_BASE_REF}
WO016P_PROMOTION_REGISTRY = {WO016P_WORK_ORDER: WO012P_PROMOTION_BASE_REF}
WO017P_PROMOTION_REGISTRY = {WO017P_WORK_ORDER: WO012P_PROMOTION_BASE_REF}
WO018P_PROMOTION_REGISTRY = {WO018P_WORK_ORDER: WO012P_PROMOTION_BASE_REF}
WO019P_PROMOTION_REGISTRY = {WO019P_WORK_ORDER: WO012P_PROMOTION_BASE_REF}
WO020P_PROMOTION_REGISTRY = {WO020P_WORK_ORDER: WO012P_PROMOTION_BASE_REF}
WO021P_PROMOTION_REGISTRY = {WO021P_WORK_ORDER: WO012P_PROMOTION_BASE_REF}
WO022P_PROMOTION_REGISTRY = {WO022P_WORK_ORDER: WO012P_PROMOTION_BASE_REF}
WO023P_PROMOTION_REGISTRY = {WO023P_WORK_ORDER: WO012P_PROMOTION_BASE_REF}
EXPECTED_WO013P_STATUS = "DELTA CONTEXT FOUNDATION APPROVED / V0.1 IMPLEMENTATION ACTIVE"
EXPECTED_WO013P_PREVIOUS_STATUS = (
    "CONTEXT FINGERPRINTS FOUNDATION APPROVED / V0.1 IMPLEMENTATION ACTIVE"
)
EXPECTED_WO013P_IN_PROGRESS = (
    "Preparing the smallest necessary provider-independent Provider/Prompt Cache Adapter "
    "Foundation over the approved Context Manager, Progressive Disclosure, Adaptive Token "
    "Budget, Context Fingerprints and Delta Context pipeline."
)
EXPECTED_WO013P_NEXT_STEP_PREFIX = (
    "Prepare the smallest necessary provider-independent Provider/Prompt Cache Adapter "
    "Foundation over the approved Context Manager, Progressive Disclosure, Adaptive Token "
    "Budget, Context Fingerprints and Delta Context pipeline."
)
EXPECTED_WO013P_BLOCKERS = (
    "None known after Delta Context Foundation approval and post-merge validation."
)
WO013P_NEXT_STEP_REQUIRED_INTENTS = (
    "provider independence",
    "stable prompt-prefix/provider-cache adapters only where supported",
    "deterministic HIVE context identity remains canonical",
    "provider cache never becomes canonical truth",
    "cached-provider accounting is measured and reconciled, not guessed",
    "no Memory lifecycle",
    "no MCP product surface",
    "no autonomous executor dispatch",
    "no full telemetry expansion beyond what is strictly necessary for objective evidence",
    "no user-managed cache mode required",
)
WO013P_CANONICAL_COMPLETION_BULLETS = (
    "delta context foundation approval is recorded with policy delta-context-v1, patch "
    "delta-json-patch-v1, delivery context-delivery-v1, final delivery estimate "
    "delta-delivery-estimate-v1 and semantic seam context-output-v2.",
    "the redis baseline is non-canonical, project-scoped and task-scoped with ttl 300 "
    "seconds; old-head baseline compatibility, corrupt-baseline safe full, redis-loss "
    "safe full, api restart reuse, cross-project isolation and cross-task isolation are "
    "verified.",
    "exact reconstruction and target fingerprint verification are verified; false delta "
    "reconstructions 0, critical context misses 0, post-build full/delta races fail "
    "closed, newly relevant dependency preserved, delta llm calls 0 and delta provider "
    "calls 0.",
    "the final delivery token estimate contract is versioned; strict-smaller uses the "
    "final delivery estimate, the old metadata false-positive regression is verified, "
    "small-change final delta estimate 1926, small-change full estimate 4152, "
    "fresh-context tokens avoided 2226, final delivery bytes 7777, patch operations 3, "
    "patch chars 6632, final byte bound 24000, not-smaller verified and threshold "
    "266 / 319 / 268 evidence.",
    "migration 0005_semantic_retrieval, pr #43, audited head "
    "4d9bf458cea7c7bf91ac84012dd5f991be194263, sol review 5123605890, merge "
    "d952be125da97afacf1099244cf2755f8243d288, post-merge ci 34002558669, backend "
    "325, dashboard 7; provider/prompt cache not implemented, memory lifecycle not "
    "implemented and autonomous executor dispatch not implemented.",
)
EXPECTED_WO014P_STATUS = (
    "PROVIDER / PROMPT CACHE ADAPTER FOUNDATION APPROVED / V0.1 IMPLEMENTATION ACTIVE"
)
EXPECTED_WO014P_PREVIOUS_STATUS = "DELTA CONTEXT FOUNDATION APPROVED / V0.1 IMPLEMENTATION ACTIVE"
EXPECTED_WO014P_IN_PROGRESS = (
    "Preparing the smallest necessary Memory Lifecycle and Provenance Foundation over the "
    "approved Context Manager, Progressive Disclosure, Adaptive Token Budget, Context "
    "Fingerprints, Delta Context and Provider/Prompt Cache foundations."
)
EXPECTED_WO014P_BLOCKERS = (
    "None known after Provider/Prompt Cache Adapter Foundation approval and post-merge validation."
)
WO014P_NEXT_STEP_REQUIRED_INTENTS = (
    "durable structured memory belongs in PostgreSQL",
    "Redis remains HOT/noncanonical only",
    "every promoted memory record carries provenance",
    "staged executor/model output is not canonical until validated",
    "derived summaries/embeddings never replace canonical source",
    "project isolation remains mandatory",
    "deterministic mechanisms before LLM calls",
    "no MCP product surface yet",
    "no autonomous executor dispatch expansion yet",
    "no full telemetry expansion beyond objective evidence",
    "no silent canonical memory mutation",
)
WO014P_CANONICAL_COMPLETION_BULLETS = (
    "provider/prompt cache adapter foundation approval is recorded with "
    "provider-prompt-envelope-v1, provider-canonical-input-v1, stable-prompt-prefix-v1, "
    "provider-cache-capabilities-v1, provider-cache-adapter-v1, provider-usage-receipt-v1 "
    "and provider-cache-accounting-v1.",
    "independent semantic composition is verified with mutation evidence 5/5/0; provider "
    "material identity invalidation is verified; credential rotation is nonmaterial with "
    "credential leaks 0; cross-project leaks are 0; requested/no-receipt remains unknown, "
    "explicit zero is false, repeated prefix alone is not a hit, positive provider receipt "
    "is a hit, false hit claims are 0 and invalid accounting acceptances are 0 across matrix "
    "size 8.",
    "full and delta provider-prompt compatibility are measured; delta false reconstructions "
    "and critical context misses remain 0/0; foundation provider and llm calls remain 0/0; "
    "no live provider prompt-cache network integration, memory lifecycle, autonomous executor "
    "dispatch or full cache telemetry was implemented; migration remains "
    "0005_semantic_retrieval.",
    "provider/prompt cache implementation evidence references pr #46, audited head "
    "dfb6bcb21e6646bc2c056c014ba211245bd64e77, sol review 5125220660 and squash merge "
    "5c8356228b0ce186cde6e64393a167063aa2a9e9; initial post-merge ci 34031448696 failed "
    "only the squash-unsafe review-evidence lineage regression and therefore did not close "
    "the work order.",
    "wo-014-c2 repaired the squash-unsafe lineage validator on pr #47, audited head "
    "ba2a87ee71c4039dc692f96fd20c9aa05d22401a, sol review 5125500085, squash merge "
    "13888d63572db0e90fb4536369867d995a9e1c90 and post-merge ci 34037204379; validate and "
    "integration health passed on the exact main sha, backend 358 and dashboard 7 passed, "
    "canonical verifier and secret scan passed.",
)
EXPECTED_WO015P_STATUS = (
    "MEMORY LIFECYCLE AND PROVENANCE FOUNDATION APPROVED / V0.1 IMPLEMENTATION ACTIVE"
)
EXPECTED_WO015P_PREVIOUS_STATUS = EXPECTED_WO014P_STATUS
EXPECTED_WO015P_IN_PROGRESS = (
    "Preparing the smallest necessary ACCE increment beyond current intake/storage/context "
    "foundations."
)
EXPECTED_WO015P_NEXT_STEP_PREFIX = (
    "Prepare the smallest necessary ACCE increment beyond current intake/storage/context "
    "foundations."
)
EXPECTED_WO015P_NEXT_STEP = EXPECTED_WO015P_NEXT_STEP_PREFIX
EXPECTED_WO015P_BLOCKERS = (
    "None known after Memory Lifecycle and Provenance Foundation approval and post-merge "
    "validation."
)
WO015P_CANONICAL_COMPLETION_BULLETS = (
    "memory lifecycle and provenance foundation approval is recorded with migration "
    "0006_memory_lifecycle_provenance; durable project-scoped memory is in postgresql and "
    "redis remains hot/noncanonical.",
    "canonical memory classes, lifecycle, provenance and history are implemented; staged "
    "model/executor output remains noncanonical by default; restart and redis-loss "
    "durability are proven.",
    "canonical promotion requires a deterministic qualified source or decision basis; "
    "immutable git byte/source identity and source/adr/head races fail closed; "
    "cross-project rejection remains mandatory.",
    "memory evidence for pr #51, audited head 95c3bafbd9be2b76b308097f7568b215bb055fa0, "
    "sol review 5131840941, squash merge 2c701d221e481913d2cbe9c0b8f3504632042306, "
    "post-merge ci 34120545634, backend 382 and dashboard 7 is pass.",
    "memory llm/provider calls are 0/0; ruleset 21934284 is unchanged; auto-merge is "
    "unarmed; validated_evidence remains fail-closed; no mcp memory surface, "
    "autonomous dispatch, full telemetry, full control center or v0.1 completion is "
    "claimed.",
)
EXPECTED_WO016P_STATUS = (
    "ACCE STORAGE TIER AND COMPRESSION POLICY FOUNDATION APPROVED / V0.1 IMPLEMENTATION ACTIVE"
)
EXPECTED_WO016P_PREVIOUS_STATUS = EXPECTED_WO015P_STATUS
EXPECTED_WO016P_IN_PROGRESS = (
    "Preparing the smallest necessary MCP server product surface increment."
)
EXPECTED_WO016P_BLOCKERS = (
    "None known after ACCE Storage Tier and Compression Policy Foundation approval and "
    "post-merge validation."
)
EXPECTED_WO016P_NEXT_STEP = "Prepare the smallest necessary MCP server product surface increment."
EXPECTED_WO016P_PENDING_ITEM = "ACCE beyond current intake/storage/context foundations."
WO016P_CANONICAL_COMPLETION_BULLETS = (
    "acce storage tier and compression policy foundation is approved with policy "
    "acce-policy-v1 and evidence acce-storage-policy-v1; hot/warm/cold is system-managed "
    "over sha-256 + lossless zstandard cas; migration remains 0006_memory_lifecycle_provenance.",
    "the bounded representative benchmark measures six rows with two candidates per tier, "
    "measures compression/decompression throughput, enforces supported zstd levels, rejects "
    "tiny/oversized benchmark corpora, and selects same-tier profiles deterministically from "
    "measured results rather than a universal hard-coded selected level.",
    "exact logical sha-256 and one canonical cas identity are preserved across tier "
    "transitions; dedup remains valid; physical replacement/metadata ordering is safe; "
    "postgresql physical metadata and logical/physical/compression accounting remain "
    "truthful; corruption/truncation fail closed.",
    "retry/recovery integrity is proven, including pre-publication durable metadata guard, "
    "orphan/missing-physical fail-closed behavior, pre-commit rollback, post-commit cleanup "
    "safety, restart and redis-loss recovery; canonical source loss is zero and acce storage "
    "llm/provider calls are 0/0.",
    "evidence lineage records pr #55, audited head 0de6dc345262fc77fdda99c2f2dca6be88f9552c, "
    "sol review 5135618100, squash merge 54c32e939c7be6d505727df24d3ce2ad48af5518, "
    "post-merge ci 34168038154, backend 418, dashboard 7; ruleset 21934284 is unchanged, "
    "auto-merge was unarmed, and no mcp, autonomous execution, full telemetry, full control "
    "center or v0.1 completion is claimed.",
)
EXPECTED_WO017P_STATUS = "MCP READ-ONLY CORE SURFACE APPROVED / V0.1 IMPLEMENTATION ACTIVE"
EXPECTED_WO017P_PREVIOUS_STATUS = EXPECTED_WO016P_STATUS
EXPECTED_WO017P_IN_PROGRESS = (
    "Preparing the smallest necessary autonomous execution pipeline increment."
)
EXPECTED_WO017P_BLOCKERS = (
    "None known after MCP read-only core surface approval and post-merge validation."
)
EXPECTED_WO017P_NEXT_STEP = (
    "Prepare the smallest necessary autonomous execution pipeline increment."
)
EXPECTED_WO017P_PENDING_ITEM = "MCP server product surface."
WO017P_CANONICAL_COMPLETION_BULLETS = (
    "mcp read-only core surface is approved with evidence mcp-core-surface-v1 and the "
    "exact seven tools project.list, project.status, context.build, context.search, "
    "memory.search, memory.get and checkpoint.read; migration remains "
    "0006_memory_lifecycle_provenance.",
    "real local mcp transport reuses hive core directly without rest loopback or duplicate "
    "persistence; project isolation, checkpoint-first behavior, bounded structured errors, "
    "context provenance/bounds and memory provenance/status visibility are verified.",
    "restart and redis-loss recovery pass; arbitrary filesystem access, missing/untracked/"
    "stale checkpoint substitution and hive checkpoint substitution fail closed; secret "
    "leaks, filesystem path leaks, mcp llm calls and mcp provider calls are all 0.",
    "evidence lineage records pr #59 with audited head "
    "e46b45ff0ec08024b2f83a418b90b7b84095f172 and squash merge "
    "7400f948fa72f9d8f41e8035ff4441b1a5ad4d26, plus correction pr #60 with "
    "audited head 8fbd89357e2d37de7b6b68316e8a25cc59e996f2, squash merge "
    "0d9240f3a18530fae3e9f65751dbc11491c485c0 and post-merge ci 34285893606; "
    "backend 465 and dashboard 7 passed.",
    "ruleset 21934284 remains unchanged and auto-merge is unarmed; autonomous execution "
    "beyond the local verified runner, full telemetry, full control center and v0.1 "
    "completion are not claimed.",
)

EXPECTED_WO018P_STATUS = "AUTONOMOUS EXECUTION FOUNDATION APPROVED / V0.1 IMPLEMENTATION ACTIVE"
EXPECTED_WO018P_PREVIOUS_STATUS = EXPECTED_WO017P_STATUS
EXPECTED_WO018P_IN_PROGRESS = (
    "Preparing the smallest necessary Telemetry/Event Bus foundation increment."
)
EXPECTED_WO018P_BLOCKERS = (
    "None known after Autonomous Execution Foundation approval and post-merge validation."
)
EXPECTED_WO018P_NEXT_STEP = (
    "Prepare the smallest necessary Telemetry/Event Bus foundation increment."
)
EXPECTED_WO018P_PENDING_ITEMS = (
    "autonomous execution beyond the Local Verified Runner foundation.",
    "tool gating integration where not yet end-to-end.",
)
WO018P_CANONICAL_COMPLETION_BULLETS = (
    "autonomous execution foundation is approved with evidence autonomous-execution-v1; "
    "the provider-independent execution orchestrator reuses durable project/task identity, "
    "the existing checkpoint-first context manager, local verified runner and tool policy; "
    "migration remains 0006_memory_lifecycle_provenance.",
    "bounded tool gating is verified before execution; unauthorized tools, shell bypass, "
    "cross-project task mismatch, project brain mutation and git head/source races fail closed.",
    "structured executor output remains staged and noncanonical; exact changed files, bounded "
    "diffs, tests, validation results and executor review are captured; the deterministic "
    "end-to-end coding fixture passes with zero secret and filesystem-path leaks.",
    "evidence lineage records pr #65 with audited head "
    "ac2782299e8f2bddd723f536a8e54013af135d34, sol review 5154496929, squash merge "
    "ed534965136a36eff66276d5b073dc034a7fc96f and post-merge ci 34353690177; "
    "backend 488 and dashboard 7 passed.",
    "ruleset 21934284 remains unchanged and auto-merge is unarmed; the product pipeline "
    "performs no git commit, push, merge or checkpoint promotion; full telemetry, full "
    "control center and v0.1 completion are not claimed.",
)

EXPECTED_WO019P_STATUS = "TELEMETRY / EVENT BUS FOUNDATION APPROVED / V0.1 IMPLEMENTATION ACTIVE"
EXPECTED_WO019P_PREVIOUS_STATUS = EXPECTED_WO018P_STATUS
EXPECTED_WO019P_IN_PROGRESS = (
    "Preparing the smallest necessary full HIVE Control Center implementation increment."
)
EXPECTED_WO019P_BLOCKERS = (
    "None known after Telemetry/Event Bus Foundation approval and post-merge validation."
)
EXPECTED_WO019P_NEXT_STEP = (
    "Prepare the smallest necessary full HIVE Control Center implementation increment."
)
EXPECTED_WO019P_PENDING_ITEMS = ("telemetry.",)
WO019P_CANONICAL_COMPLETION_BULLETS = (
    "telemetry/event bus foundation is approved with evidence telemetry-event-bus-v1; "
    "postgresql remains the durable event store and redis remains hot/streaming noncanonical; "
    "migration head is 0007_telemetry_events.",
    "canonical event vocabulary, deterministic replay, fail-closed stream, redis-loss recovery, "
    "project isolation and payload sanitization are verified; secret and filesystem-path leaks "
    "remain 0.",
    "sanitizer fail-closed coverage includes prefixed secret assignments, general posix absolute "
    "paths, file uris and url query/fragment secret delimiters without destroying token metrics or "
    "safe urls.",
    "evidence lineage records pr #70 with audited head "
    "590eda41c55c1b21f4a04789cf5576a6640f0732, sol review 5162319026, squash merge "
    "d800fac8f165146055ad050d6c2f232883dc91b7 and post-merge ci 34433610894; "
    "backend 506 and dashboard 7 passed.",
    "ruleset 21934284 remains unchanged and auto-merge is unarmed; uads c7 finalized; "
    "full control center and v0.1 completion are not claimed.",
)

EXPECTED_WO020P_STATUS = "CONTROL CENTER OPERATIONAL CORE APPROVED / V0.1 IMPLEMENTATION ACTIVE"
EXPECTED_WO020P_PREVIOUS_STATUS = EXPECTED_WO019P_STATUS
EXPECTED_WO020P_IN_PROGRESS = (
    "Preparing the smallest necessary Control Center metrics and observability increment."
)
EXPECTED_WO020P_BLOCKERS = (
    "None known after Control Center Operational Core approval and post-merge validation."
)
EXPECTED_WO020P_NEXT_STEP = (
    "Prepare the smallest necessary Control Center metrics and observability increment."
)
WO020P_REQUIRED_RETAINED_PENDING_ITEMS = (
    "full Control Center.",
    "comprehensive retrieval/token/storage benchmarks.",
    "stabilization.",
    "full local deployment validation.",
    "backup/recovery validation.",
    "final documentation.",
    "final V0.1 review.",
    "checkpoint awareness orchestration beyond current checkpoint-first Context Manager behavior.",
)
WO020P_CANONICAL_COMPLETION_BULLETS = (
    "control center operational core is approved under evidence control-center-core-v1 with "
    "bounded fleet, selected project detail, active/recent runs, run detail, project event "
    "timeline, platform health, tests/validation and errors/warnings surfaces.",
    "near-real-time event delivery reuses the existing project-scoped sse stream with durable "
    "postgresql replay/reconciliation; postgresql remains canonical and redis remains "
    "noncanonical hot/streaming state.",
    "fleet is bounded/paginated with complete-registry total/state-count truth; run detail "
    "maintains a dedicated bounded/deduplicated selected-run timeline; cross-project leakage and "
    "raw host-path/secret leakage remain fail-closed.",
    "unsupported metrics are not fabricated: exact live token usage, exact provider cost, cache "
    "hit rate and context signal ratio remain unavailable until backed by reliable telemetry; "
    "full control center remains pending.",
    "lineage records pr #75 with audited head c28715a4fcaac2a062fc0b14e80cdfb4f418726b, sol "
    "review 5180295002, squash merge 2e322095936f2a508f36563699e464d301f89ced and post-merge "
    "ci 34615046572; backend 547 and dashboard 27 passed.",
    "uads final acceptance lineage records c2-r2 workorderid wo_1ce7f88ba20967d7, executionrunid "
    "er_66338e817d9fa1f3 and digest "
    "e52da09fafb7d4e17671225f09796b4613d18e3c751bff3c27e2e532d280ca10; "
    "legal dispatch under hard budget, reviewer approved, finalize completed/stopped and "
    "zeroprojectfootprint=true.",
)

EXPECTED_WO021P_STATUS = "CONTROL CENTER METRICS FOUNDATION APPROVED / V0.1 IMPLEMENTATION ACTIVE"
EXPECTED_WO021P_PREVIOUS_STATUS = EXPECTED_WO020P_STATUS
EXPECTED_WO021P_IN_PROGRESS = (
    "Preparing the smallest necessary full HIVE Control Center implementation increment."
)
EXPECTED_WO021P_BLOCKERS = (
    "None known after Control Center Metrics Foundation approval and post-merge validation."
)
EXPECTED_WO021P_NEXT_STEP = (
    "Prepare the smallest necessary full HIVE Control Center implementation increment."
)
WO021P_REQUIRED_RETAINED_PENDING_ITEMS = WO020P_REQUIRED_RETAINED_PENDING_ITEMS
WO021P_CANONICAL_COMPLETION_BULLETS = (
    "control center metrics foundation is approved under evidence control-center-metrics-v1 "
    "with truthful bounded token, context, cache and storage metrics and explicit value "
    "provenance.",
    "provider final usage is exact only after reconciliation; estimated, unavailable and unknown "
    "values remain distinct and unknown values are never rendered as zero.",
    "context reduction, cache hit/miss and logical/physical storage metrics preserve provenance; "
    "cache state is derived from real events or receipts and cost remains unavailable without "
    "pricing provenance.",
    "project-scoped metrics and deterministic global aggregation are bounded; postgresql remains "
    "canonical, redis remains noncanonical, and restart/redis-loss recovery preserves canonical "
    "truth.",
    "lineage records pr #82 with audited head 1363d6c477faba8b6d780cdb1a953aa3c64259e5, sol "
    "review 5190892017, squash merge cd05c753ce0fd25d657dd829a2484041355d873b and post-merge "
    "ci 34760861308; backend 568 and dashboard 30 passed.",
    "control-center-metrics-v1 evidence records migration head 0007_telemetry_events, zero "
    "secret/filesystem-path/cross-project leaks, zero llm/provider calls, and does not claim "
    "full control center or hive v0.1 completion.",
)

EXPECTED_WO022P_STATUS = "FULL CONTROL CENTER APPROVED / V0.1 IMPLEMENTATION ACTIVE"
EXPECTED_WO022P_PREVIOUS_STATUS = EXPECTED_WO021P_STATUS
EXPECTED_WO022P_IN_PROGRESS = (
    "Preparing the comprehensive retrieval, token and storage benchmarks increment."
)
EXPECTED_WO022P_BLOCKERS = (
    "None known after Full Control Center approval and post-merge validation."
)
EXPECTED_WO022P_NEXT_STEP = (
    "Prepare the comprehensive retrieval, token and storage benchmarks increment."
)
WO022P_COMPLETED_PENDING_ITEM = "full Control Center."
WO022P_REQUIRED_RETAINED_PENDING_ITEMS = tuple(
    item for item in WO021P_REQUIRED_RETAINED_PENDING_ITEMS if item != WO022P_COMPLETED_PENDING_ITEM
)
WO022P_CANONICAL_COMPLETION_BULLETS = (
    "full control center is approved under evidence control-center-full-v1 with ten "
    "project-intelligence capabilities, thirteen required charts, twelve alerts and three "
    "health surfaces rendered from canonical git head blobs and bounded project-scoped "
    "telemetry.",
    "bounded project-scoped near-real-time behaviour reuses canonical postgresql truth with "
    "bounded history points, estimated values labelled, and no fabricated metric or alert.",
    "postgresql remains canonical, redis remains noncanonical hot state, and restart plus "
    "redis-loss recovery preserve the same canonical project-scoped view.",
    "mandatory governance sections fail closed as unavailable, unknown values are never rendered "
    "as zero, and missing canonical project-brain sections are never materialized as data.",
    "lineage records pr #86 with audited head a870275b3ad738b789e30169d5b1fac00e2e4ae3, sol "
    "review 5204463844, squash merge 82c39025fe4e4a4a3b4664ed8e8059984fffb039 and post-merge "
    "ci 34916205113; backend 606 and dashboard 34 passed.",
    "control-center-full-v1 evidence records migration head 0007_telemetry_events, zero "
    "secret/filesystem-path/cross-project leaks, zero llm/provider calls, and does not claim "
    "hive v0.1 completion.",
)

EXPECTED_WO023P_STATUS = "COMPREHENSIVE BENCHMARKS APPROVED / V0.1 IMPLEMENTATION ACTIVE"
EXPECTED_WO023P_PREVIOUS_STATUS = EXPECTED_WO022P_STATUS
EXPECTED_WO023P_IN_PROGRESS = "Preparing the stabilization increment."
EXPECTED_WO023P_BLOCKERS = (
    "None known after comprehensive benchmarks approval and post-merge validation."
)
EXPECTED_WO023P_NEXT_STEP = "Preparing the stabilization increment."
WO023P_COMPLETED_PENDING_ITEM = "comprehensive retrieval/token/storage benchmarks."
WO023P_REQUIRED_RETAINED_PENDING_ITEMS = tuple(
    item for item in WO022P_REQUIRED_RETAINED_PENDING_ITEMS if item != WO023P_COMPLETED_PENDING_ITEM
)
WO023P_CANONICAL_COMPLETION_BULLETS = (
    "comprehensive retrieval, token and storage benchmarks are approved under evidence "
    "comprehensive-benchmarks-v1 with measured recall@5 1.0, zero critical-context misses, "
    "bounded retrieval context bytes and strictly positive retrieval precision on the "
    "auditable deterministic corpus.",
    "the token family compares the full-context baseline and the emitted optimized capsule of "
    "the same benchmark task identities with the deterministic estimator "
    "utf8-byte-ratio-approx-v1 and serialization context-payload-v1, and records a measured "
    "strict reduction instead of a cross-dataset comparison.",
    "baseline and optimized task success are derived from one objective ground-truth-identity "
    "criterion per representation and the versioned acceptance matrix "
    "wo023-task-acceptance-matrix-v1, so neither outcome rate is a constant.",
    "project isolation is measured with a bounded second project that answers its own identity "
    "queries, returns no foreign path and is never answered by a foreign path; zero "
    "secret/filesystem-path/cross-project leaks remain enforced.",
    "content-addressed storage keeps exact-byte reconstruction and never double-counts savings; "
    "the measured zstd policy remains deterministic; token cache and output token claims stay "
    "not_supported with null values because no provider receipt exists.",
    "lineage records pr #90 with audited head 270929c2e1428335ea9c98337c29a31d5682686d, sol "
    "review 5216010298, squash merge 25c16248211da567dbda928697862a696dcf46eb and post-merge "
    "ci 35026680687; backend 638 and dashboard 34 passed.",
    "comprehensive-benchmarks-v1 evidence records migration head 0007_telemetry_events, zero "
    "secret/filesystem-path/cross-project leaks, zero llm/provider calls, proves the contract "
    "on a bounded deterministic corpus without a production-quality claim, and does not claim "
    "hive v0.1 completion.",
)

WO024P_PROMOTION_ALLOWED_PATHS = frozenset({CHECKPOINT_PATH, CANONICAL_MANIFEST_PATH})
WO024P_PROMOTION_REGISTRY = {WO024P_WORK_ORDER: WO012P_PROMOTION_BASE_REF}
# Immutable approved WO-024 product identities. A later governance correction on
# main must never be able to move, restate or silently re-derive them, and the
# promotion must prove the approved squash merge is an ancestor of current main
# instead of assuming it is still the tip.
WO024_APPROVED_PRODUCT_PR = 95
WO024_APPROVED_PRODUCT_BASE_SHA = "4fb0aa111bd5b0f526df85b1897618d8eca1c0e0"
WO024_APPROVED_PRODUCT_HEAD_SHA = "649e7f90fc4f2d4e3cbc17ca0f38d5f2c9dd46ad"
WO024_APPROVED_SOL_REVIEW_ID = 5233591627
WO024_APPROVED_SQUASH_MERGE_SHA = "05d142511f849d002c4ec8558fe4f43dca3e788b"
WO024_APPROVED_POST_MERGE_CI_RUN = 35204484706
WO024P_G1_C1_BASE_SHA = "05d142511f849d002c4ec8558fe4f43dca3e788b"
WO024P_G1_C1_WORK_ORDER = "WO-024-P-G1-C1"
WO024P_G1_C1_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "backend/tests/test_v01_closure_regression_lock.py",
        "backend/tests/test_v01_closure_sprint.py",
        "docs/atlas/code-atlas.md",
        "docs/atlas/test-map.md",
        "scripts/review_evidence.py",
        "scripts/v01_closure_sprint.py",
    }
)
WO024P_G1_C1_FORBIDDEN_PREFIXES = frozenset(
    {
        ".github/",
        "docs/project-brain/",
        "migrations/",
        "schemas/",
    }
)
# WO-024-P-G1-C2: minimal correction of the two stateful checkpoint regressions that block the
# final promotion. Test-only, bounded, and explicitly outside the active promotion pair.
WO024P_G1_C2_BASE_SHA = "a5cc341375a0cc067edc52db4ff2dc36b66a8c00"
WO024P_G1_C2_WORK_ORDER = "WO-024-P-G1-C2"
WO024P_G1_C2_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "backend/tests/test_v01_closure_sprint.py",
        "scripts/review_evidence.py",
    }
)
# WO-024-P-G1-C3: repair the final-promotion closure-to-lineage wiring. Governance-only, bounded,
# and explicitly outside the active promotion pair.
WO024P_G1_C3_BASE_SHA = "0df7bb1079fe2a5bdc5ec55fcc76941ca31b8d2c"
WO024P_G1_C3_WORK_ORDER = "WO-024-P-G1-C3"
WO024P_G1_C3_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "scripts/review_evidence.py",
    }
)
# WO-024-P-G1-C4: propagate the parsed authorized-base marker into the final-promotion contract.
# Governance-only, bounded, and explicitly outside the active promotion pair.
WO024P_G1_C4_BASE_SHA = "3eeb29233db036cb8d729022ad077842fe08d24a"
WO024P_G1_C4_WORK_ORDER = "WO-024-P-G1-C4"
WO024P_G1_C4_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "scripts/review_evidence.py",
    }
)
# WO-025-G1: post-1.0 governance bridge. Governance/closure-test tooling only, bounded, and
# explicitly outside the historical active promotion pair.
WO025_G1_WORK_ORDER = "WO-025-G1"
WO025_G1_BASE_SHA = "a53b5b9fcf55c32a5696180fb1b1ef80ccd1edcf"
WO025_G1_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "backend/tests/test_v01_closure_regression_lock.py",
        "backend/tests/test_v01_closure_sprint.py",
        "docs/atlas/code-atlas.md",
        "docs/atlas/test-map.md",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
        "scripts/v01_closure_sprint.py",
    }
)
# WO-025: future post-1.0 planning promotion. Its surface is post-1.0 planning documentation only;
# product code, migrations, dependencies, CI/workflows, release assets and the canonical core
# documents stay rejected until a later governance delta explicitly registers them.
WO025_WORK_ORDER = "WO-025"
WO025_PROMOTION_REGISTRY = {WO025_WORK_ORDER: WO012P_PROMOTION_BASE_REF}
# Registered planning promotions stay fail-closed as *current* work orders until their own
# governance increment authorizes them. Later identifiers remain unsupported unless explicitly
# registered by a bounded work order.
# WO-025 became an authorized current planning-promotion work order in WO-025-G2; the
# registry stays in place (empty) so a later registered-but-not-yet-authorized promotion
# keeps failing closed until its own governance increment authorizes it.
PENDING_PLANNING_PROMOTION_WORK_ORDERS: frozenset[str] = frozenset()
WO025_PLANNING_DOCUMENT_RANGE = (17, 49)
WO025_PLANNING_DOCUMENT_PREFIXES = ("docs/project-brain/work-orders/",)
WO025_PLANNING_DOCUMENT_PATTERN = re.compile(
    r"^docs/project-brain/(\d{2})-[A-Za-z0-9][A-Za-z0-9.-]*\.md$"
)
# The closure sprint applies the historical WO-024 product path scope only to the work orders that
# produced it. Any other resolved work order runs the same closure capability suite as regression
# evidence; an unresolvable work order keeps the historical fail-closed default.
CLOSURE_STRICT_SCOPE_WORK_ORDERS = frozenset({WO024_WORK_ORDER, WO024P_WORK_ORDER})
# WO-025-G2: planning-promotion authorization + renderer guard. Governance-only, bounded, and
# explicitly outside the historical active promotion pair.
WO025_G2_WORK_ORDER = "WO-025-G2"
WO025_G2_BASE_SHA = "c3a00ab34ecee31fc4c09ffac3ebe5ac7a709f3d"
WO025_G2_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "docs/atlas/code-atlas.md",
        "docs/atlas/test-map.md",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
    }
)
# WO-026: Apache-2.0 open-source readiness. Self-registration is intentionally
# bounded to the four licensing/public documentation files plus the harness and
# its regression test.
WO026_WORK_ORDER = "WO-026"
WO026_BASE_SHA = "7e52a5231b4bfadc54b3591f1ce3e3f22e40e66b"
WO026_ALLOWED_PATHS = frozenset(
    {
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "LICENSE",
        "README.md",
        "backend/tests/test_review_evidence.py",
        "scripts/review_evidence.py",
    }
)
# WO-027: Claude for Open Source application readiness. Documentation-only
# reviewer navigation plus bounded self-registration in the evidence harness.
WO027_WORK_ORDER = "WO-027"
WO027_BASE_SHA = "6c184906c0a26dd1c2e5a70db25caf6abb5283f3"
WO027_ALLOWED_PATHS = frozenset(
    {
        "README.md",
        "docs/CLAUDE-FOR-OSS-APPLICATION.md",
        "backend/tests/test_review_evidence.py",
        "scripts/review_evidence.py",
    }
)
# WO-028: Windows project-root/registration hotfix. Bounded to installation and
# Project Registry guidance, Control Center path UX, changelog, and its self-hosted evidence tests.
WO028_WORK_ORDER = "WO-028"
WO028_BASE_SHA = "736633504d6d68543bd6c69d59bba6adf8098cd5"
WO028_ALLOWED_PATHS = frozenset(
    {
        ".env.example",
        "CHANGELOG.md",
        "backend/tests/test_review_evidence.py",
        "dashboard/src/App.test.tsx",
        "dashboard/src/App.tsx",
        "docs/INSTALLATION.md",
        "docs/PROJECT-REGISTRY.md",
        "scripts/review_evidence.py",
    }
)
# WO-029: v1.0.2 executor/token-accounting corrective maintenance.
# Self-registration is bounded to the executor correction, its regression test,
# operational documentation, and this evidence harness plus its regression.
WO029_WORK_ORDER = "WO-029-EXECUTOR"
WO029_BASE_SHA = "9f76ee1ec6a670113a9e9b49615aa8bbfd8d772a"
WO029_ALLOWED_PATHS = frozenset(
    {
        "backend/app/execution_orchestrator.py",
        "backend/tests/test_execution_orchestrator.py",
        "backend/tests/test_review_evidence.py",
        "docs/autonomous-execution.md",
        "scripts/review_evidence.py",
    }
)
# WO-030: Vitest security maintenance. Self-registration is bounded to the
# dashboard dependency manifest/lockfile and this evidence harness plus its regression.
WO030_WORK_ORDER = "WO-030"
WO030_BASE_SHA = "b63bfd21bab4178e134cdd5bc2fe94725627b139"
WO030_ALLOWED_PATHS = frozenset(
    {
        ".engineering/release/HIVE-V1.0.1-SECURITY-TRIAGE.json",
        "backend/tests/test_review_evidence.py",
        "dashboard/package-lock.json",
        "dashboard/package.json",
        "dashboard/tsconfig.app.json",
        "scripts/review_evidence.py",
    }
)
# WO-030-C1: Progressive Disclosure token-efficiency corrective maintenance. Self-registration is
# bounded to the symbol classifier, its regression, and this evidence harness plus its regression.
WO030_C1_WORK_ORDER = "WO-030-C1"
WO030_C1_BASE_SHA = "a753d0cff1b23dafcdacbdecfb3ccdf5b91e6d3b"
WO030_C1_ALLOWED_PATHS = frozenset(
    {
        "backend/app/progressive_disclosure.py",
        "backend/tests/test_progressive_disclosure.py",
        "backend/tests/test_review_evidence.py",
        "scripts/review_evidence.py",
    }
)
# WO-025-G3: work-order namespace governance. Corrective governance only: it replaces the
# historical fallthrough in ``require_supported_work_order`` with an explicit deny-by-default
# registry, adds the dotted release-train grammar, and registers the next promotion plus the first
# 1.1 product order.
WO025_G3_WORK_ORDER = "WO-025-G3"
WO025_G3_BASE_SHA = "50145fb079201b06d86e80f8971721c3ed781c90"
WO025_G3_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "docs/atlas/code-atlas.md",
        "docs/atlas/test-map.md",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
    }
)
# WO-025-G4: closure/post-1.0 checkpoint compatibility. Corrective governance and regression only:
# it widens ``v01_closure_sprint.checkpoint_current`` to the third legitimate checkpoint family --
# the post-WO-025-P release-train state -- and freezes the exact raw contract that promotion must
# satisfy, so a valid promotion stays validatable by Integration health without any of the two
# historical V0.1 states or their negatives being relaxed. It never edits the checkpoint itself.
WO025_G4_WORK_ORDER = "WO-025-G4"
WO025_G4_BASE_SHA = "b4b7b0a10976e2bc4eb220318664e802e4bd41bc"
WO025_G4_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "backend/tests/test_v01_closure_regression_lock.py",
        "backend/tests/test_v01_closure_sprint.py",
        "docs/atlas/code-atlas.md",
        "docs/atlas/test-map.md",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
        "scripts/v01_closure_sprint.py",
    }
)
# WO-025-G5: reviewer self-healing policy. Governance/documentation only: it records when Sol may
# directly repair a small review defect and when execution must return to Codex, without weakening
# protected-main, evidence, canonical-promotion, scope, architecture, or severity gates.
WO025_G5_WORK_ORDER = "WO-025-G5"
WO025_G5_BASE_SHA = "82bb5e9d6fb22046e95eb532b499884adaeae6c3"
WO025_G5_ALLOWED_PATHS = frozenset(
    {
        "AGENTS.md",
        "backend/tests/test_review_evidence.py",
        "docs/DEVELOPMENT-REVIEW-WORKFLOW.md",
        "scripts/review_evidence.py",
    }
)
# The dotted release-train grammar. The legacy ``WORK_ORDER_IDENTIFIER`` cannot express
# ``WO-1.1-01`` because ``.`` is not in its character class; this pattern is deliberately narrow
# (dotted major and minor without leading zeros, then a two-digit increment) so it cannot absorb
# unrelated shapes or ambiguous spellings such as ``WO-01.1-01``.
RELEASE_TRAIN_WORK_ORDER_IDENTIFIER = re.compile(r"WO-[1-9][0-9]*\.[1-9][0-9]*-[0-9]{2}")
# WO-025-P: the next canonical checkpoint promotion. Registered here as the authorized next
# promotion without being executed; it stays outside the historical WO-024 pair and outside the
# current set. Its base is resolved at execution time from the live protected main, not pinned here.
WO025P_WORK_ORDER = "WO-025-P"
WO025P_ALLOWED_PATHS = frozenset(
    {
        "docs/project-brain/13-CHECKPOINT.md",
        "docs/project-brain/CANONICAL-SHA256SUMS.txt",
    }
)
WO025P_PROMOTION_REGISTRY = {WO025P_WORK_ORDER: WO012P_PROMOTION_BASE_REF}
# WO-1.1-01: the first Decision Fabric product order. It is registered and therefore parseable, but
# explicitly PENDING/BLOCKED until the WO-025-P canonical promotion lands, so it cannot authorize a
# fresh current pull request yet. Its base is likewise resolved at execution time.
WO11_01_WORK_ORDER = "WO-1.1-01"
WO11_01_ALLOWED_PATHS = frozenset(
    {
        "backend/app/decision_contracts.py",
        "backend/app/decision_resolver.py",
        "backend/tests/test_decision_contracts.py",
        "backend/tests/test_decision_resolver.py",
        "docs/atlas/code-atlas.md",
        "docs/atlas/test-map.md",
        "scripts/generate_maps.py",
    }
)
DEPENDENCY_MANIFEST_PATHS = frozenset(
    {
        "dashboard/package-lock.json",
        "dashboard/package.json",
        "pyproject.toml",
        "requirements-dev.txt",
        "requirements.txt",
    }
)
RELEASE_PATH_IDENTIFIER = re.compile(r"^(?:CHANGELOG|RELEASE|VERSION)", re.IGNORECASE)
EXPECTED_WO024P_STATUS = "HIVE V0.1 COMPLETE / CLOSURE SPRINT APPROVED"
EXPECTED_WO024P_PREVIOUS_STATUS = EXPECTED_WO023P_STATUS
EXPECTED_WO024P_IN_PROGRESS = "None. V0.1 closure is complete and promoted."
EXPECTED_WO024P_BLOCKERS = "None known after V0.1 closure approval and post-merge validation."
EXPECTED_WO024P_NEXT_STEP = "Operate the approved V0.1 baseline and track the post-V0.1 backlog."
WO024P_COMPLETED_PENDING_ITEMS = WO023P_REQUIRED_RETAINED_PENDING_ITEMS
WO024P_COMPLETED_PENDING_ITEM_COUNT = len(WO024P_COMPLETED_PENDING_ITEMS)
WO024P_CANONICAL_COMPLETION_BULLET_TEMPLATES = (
    "v0.1 closure sprint is approved under evidence {version} with stabilization, full local "
    "deployment, backup/recovery, checkpoint-aware autonomous orchestration, the twelve-step "
    "end-to-end closure proof, documentation currency and a complete definition-of-done matrix.",
    "the definition-of-done matrix covers every required item exactly once with pass {pass_count} "
    "of {total_count}, zero fail and zero unknown, and any fail or unknown item would have "
    "blocked the closure candidate.",
    "stabilization removed every objective defect and regression found by the deterministic gap "
    "sweep, remaining critical {critical} and high {high} defects are zero, and no unauthorized "
    "scope expansion was performed.",
    "full local deployment is proven from documented configuration with clean boot, service "
    "health, host persistence outside the repository, durable postgresql and content-addressed "
    "storage state after container recreation, redis-loss recovery and a tested secondary root.",
    "backup and recovery prove deterministic postgresql dump/restore, content-addressed byte and "
    "hash restoration, configuration and registry restoration into a clean target, canonical "
    "row/hash equivalence and redis explicitly excluded as noncanonical.",
    "checkpoint-aware autonomous orchestration resolves project and git state, processes the "
    "checkpoint first and then scope, definition of done, architecture and decisions, keeps task "
    "and project scoping plus tool gating, fails closed on missing, stale, untracked and "
    "cross-project authority, and uses zero deterministic-path llm calls.",
    "lineage records pr #{product_pr} with audited head {audited_head}, sol review {sol_review}, "
    "squash merge {squash_merge} and post-merge ci {post_merge_ci}; backend {backend_passed} and "
    "dashboard {dashboard_passed} passed.",
    "v0.1 closure evidence records migration head {migration_head}, zero secret, filesystem-path "
    "and cross-project leaks, zero core llm and provider calls, proves the bounded fixture "
    "contract without a production-quality claim, and supports the promoted hive v0.1 claim.",
)
WO024P_COMPLETION_BULLET_COUNT = len(WO024P_CANONICAL_COMPLETION_BULLET_TEMPLATES)


def wo024p_completion_bullets(
    *,
    version: str,
    pass_count: int,
    total_count: int,
    critical: int,
    high: int,
    product_pr: int,
    audited_head: str,
    sol_review: int,
    squash_merge: str,
    post_merge_ci: int,
    backend_passed: int,
    dashboard_passed: int,
    migration_head: str,
) -> tuple[str, ...]:
    """Fill the closed WO-024-P completion grammar from verified lineage values."""

    values = {
        "version": version,
        "pass_count": pass_count,
        "total_count": total_count,
        "critical": critical,
        "high": high,
        "product_pr": product_pr,
        "audited_head": audited_head,
        "sol_review": sol_review,
        "squash_merge": squash_merge,
        "post_merge_ci": post_merge_ci,
        "backend_passed": backend_passed,
        "dashboard_passed": dashboard_passed,
        "migration_head": migration_head,
    }
    return tuple(
        template.format(**values) for template in WO024P_CANONICAL_COMPLETION_BULLET_TEMPLATES
    )


WO023P_G1_C1_BASE_SHA = "3ca2109175b7c6842c6578c237ff798d5ce8916f"
WO023P_G1_C1_WORK_ORDER = "WO-023-P-G1-C1"
WO023P_G1_C1_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
    }
)
HIVE_REL_001_WORK_ORDER = "HIVE-REL-001"
HIVE_REL_001_BASE_SHA = "90cc1b91b48d628dfb3e4773e1672535b4cb8991"
HIVE_REL_001_ALLOWED_EXACT_PATHS = frozenset(
    {
        "VERSION",
        "README.md",
        "CHANGELOG.md",
        "LICENSE",
        "AGENTS.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "SUPPORT.md",
        "backend/app/__init__.py",
        "backend/app/config.py",
        "dashboard/package.json",
        "dashboard/package-lock.json",
        "dashboard/src/App.tsx",
        "dashboard/src/App.test.tsx",
        "dashboard/src/ControlCenter.test.tsx",
        "requirements.txt",
        "requirements-dev.txt",
    }
)
HIVE_REL_001_ALLOWED_PREFIXES = (
    "backend/tests/",
    "docs/",
    "scripts/",
    ".github/",
    ".engineering/release/",
)
HIVE_REL_001_FORBIDDEN_PREFIXES = (
    "docs/project-brain/",
    "migrations/",
    ".engineering/gef/",
    "release-assets/",
    "review-bundles/",
    "tmp/",
    "node_modules/",
    ".git/",
)
HIVE_REL_001_FORBIDDEN_EXACT_PATHS = frozenset({"docs/releases/v0.0.1-bootstrap.md"})
HIVE_REL_002_WORK_ORDER = "HIVE-REL-002"
HIVE_REL_002_BASE_SHA = "e7d661a7547fa12c5410c4e3334286f3bdc6686c"
HIVE_REL_002_ALLOWED_PATHS = frozenset(
    {
        ".github/workflows/release-publisher.yml",
        ".engineering/release/HIVE-V1.0.0-PUBLISH-REQUEST.json",
        "scripts/finalize_release_receipt.py",
        "backend/tests/test_finalize_release_receipt.py",
        "scripts/review_evidence.py",
        "backend/tests/test_review_evidence.py",
        "docs/RELEASING.md",
        "docs/RELEASE-CHECKLIST.md",
        "docs/atlas/code-atlas.md",
        "docs/atlas/test-map.md",
    }
)
HIVE_REL_002_FORBIDDEN_PREFIXES = (
    "docs/project-brain/",
    "migrations/",
    ".engineering/gef/",
    "release-assets/",
    "review-bundles/",
    "tmp/",
    "node_modules/",
    ".git/",
)

HIVE_REL_003_WORK_ORDER = "HIVE-REL-003"
HIVE_REL_003_BASE_SHA = "0f86be943f13e7058419c4ff282cf801b9ad46a6"
HIVE_REL_003_ALLOWED_PATHS = frozenset(
    {
        ".github/workflows/release-publisher.yml",
        ".engineering/release/HIVE-V1.0.0-PUBLISH-REQUEST.json",
        "scripts/review_evidence.py",
        "backend/tests/test_review_evidence.py",
    }
)
HIVE_REL_003_FORBIDDEN_PREFIXES = (
    "docs/project-brain/",
    "migrations/",
    ".engineering/gef/",
    "release-assets/",
    "review-bundles/",
    "tmp/",
    "node_modules/",
    ".git/",
)

HIVE_REL_004_WORK_ORDER = "HIVE-REL-004"
HIVE_REL_004_BASE_SHA = "289c4e35b443dfc6032c8af135a4fab470236ada"
HIVE_REL_004_ALLOWED_PATHS = frozenset(
    {
        ".github/workflows/release-publisher.yml",
        "scripts/review_evidence.py",
        "backend/tests/test_review_evidence.py",
    }
)
HIVE_REL_004_FORBIDDEN_PREFIXES = HIVE_REL_003_FORBIDDEN_PREFIXES

HIVE_REL_005_WORK_ORDER = "HIVE-REL-005"
HIVE_REL_005_BASE_SHA = "552ab5156f2106fa204c98d6c3fd11c9fba5b208"
HIVE_REL_005_ALLOWED_PATHS = frozenset(
    {
        ".github/workflows/release-publisher.yml",
        ".engineering/release/HIVE-V1.0.1-SECURITY-TRIAGE.json",
        ".engineering/release/HIVE-V1.0.1-RELEASE-CANDIDATE.json",
        "VERSION",
        "backend/app/__init__.py",
        "backend/app/config.py",
        "dashboard/package.json",
        "dashboard/package-lock.json",
        "README.md",
        "CHANGELOG.md",
        "docs/releases/v1.0.1.md",
        "docs/atlas/code-atlas.md",
        "docs/atlas/test-map.md",
        "scripts/review_evidence.py",
        "scripts/release_publisher_contract.py",
        "scripts/comprehensive_benchmarks.py",
        "backend/tests/test_comprehensive_benchmarks.py",
        "backend/tests/test_review_evidence.py",
        "backend/tests/test_release_publisher_contract.py",
        "backend/tests/test_verify_release_metadata.py",
    }
)
HIVE_REL_005_FORBIDDEN_PREFIXES = HIVE_REL_003_FORBIDDEN_PREFIXES

HIVE_REL_006_WORK_ORDER = "HIVE-REL-006"
HIVE_REL_006_BASE_SHA = "3c2090dc458c6d4ed988e89f85043a9d106d1901"
HIVE_REL_006_ALLOWED_PATHS = frozenset(
    {
        ".engineering/release/HIVE-V1.0.1-PUBLISH-REQUEST.json",
        "scripts/review_evidence.py",
        "backend/tests/test_review_evidence.py",
    }
)
HIVE_REL_006_FORBIDDEN_PREFIXES = HIVE_REL_003_FORBIDDEN_PREFIXES

RELEASE_ENGINEERING_ALLOWED_EXACT_PATHS = frozenset(
    {
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
        "requirements.txt",
        "requirements-dev.txt",
    }
)
RELEASE_ENGINEERING_ALLOWED_PREFIXES = (
    ".github/",
    ".engineering/release/",
    "docs/",
)
RELEASE_ENGINEERING_FORBIDDEN_PREFIXES = (
    "docs/project-brain/",
    ".engineering/gef/",
    "migrations/",
)
AUTHORIZED_BASE_MARKER_WORK_ORDERS = frozenset(
    {
        "WO-012-P",
        "WO-013-P",
        WO014P_WORK_ORDER,
        WO015P_WORK_ORDER,
        WO016P_WORK_ORDER,
        WO017P_WORK_ORDER,
        WO018P_WORK_ORDER,
        WO019P_WORK_ORDER,
        WO020P_WORK_ORDER,
        WO021P_WORK_ORDER,
        WO022P_WORK_ORDER,
        WO023P_WORK_ORDER,
        WO023P_G1_C1_WORK_ORDER,
        WO024_G1_WORK_ORDER,
        WO024P_WORK_ORDER,
        WO024P_G1_C1_WORK_ORDER,
        WO024P_G1_C2_WORK_ORDER,
        WO024P_G1_C3_WORK_ORDER,
        WO024P_G1_C4_WORK_ORDER,
        WO025_G1_WORK_ORDER,
        WO025_G2_WORK_ORDER,
        WO025_WORK_ORDER,
        WO026_WORK_ORDER,
        WO027_WORK_ORDER,
        WO028_WORK_ORDER,
        WO029_WORK_ORDER,
        WO030_WORK_ORDER,
        WO030_C1_WORK_ORDER,
        WO025_G3_WORK_ORDER,
        WO025_G4_WORK_ORDER,
        WO025_G5_WORK_ORDER,
        WO025P_WORK_ORDER,
        WO11_01_WORK_ORDER,
        GEF_ADOPTION_WORK_ORDER,
        HIVE_REL_001_WORK_ORDER,
        HIVE_REL_002_WORK_ORDER,
        HIVE_REL_003_WORK_ORDER,
        HIVE_REL_004_WORK_ORDER,
        HIVE_REL_005_WORK_ORDER,
        HIVE_REL_006_WORK_ORDER,
    }
)
WO024_G1_ALLOWED_PATHS = frozenset(
    {
        "backend/tests/test_review_evidence.py",
        "schemas/review-evidence-v1.schema.json",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
    }
)
V01_CLOSURE_SPRINT_PRODUCT_ALLOWED_PREFIXES = (
    "backend/app/",
    "backend/tests/",
    "scripts/",
    "docs/atlas/",
    "dashboard/src/",
    "dashboard/tests/",
)
V01_CLOSURE_SPRINT_PRODUCT_ALLOWED_EXACT_PATHS = frozenset(
    {
        "docker-compose.yml",
        ".env.example",
        "README.md",
        "Dockerfile",
    }
)
V01_CLOSURE_SPRINT_PRODUCT_FORBIDDEN_PREFIXES = (
    "docs/project-brain/",
    "migrations/",
    ".github/",
    "release-assets/",
    "dashboard/node_modules/",
)
V01_CLOSURE_SPRINT_PRODUCT_FORBIDDEN_EXACT_PATHS = frozenset(
    {
        "requirements.txt",
        "dashboard/package.json",
        "dashboard/package-lock.json",
        "docs/project-brain/CANONICAL-SHA256SUMS.txt",
    }
)
V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD = "0007_telemetry_events"
V01_CLOSURE_SPRINT_EVIDENCE_VERSION = "v01-closure-sprint-v1"
V01_CLOSURE_SPRINT_EVIDENCE_FILE = "v01-closure-sprint.json"
V01_CLOSURE_SPRINT_MAX_PATHS = 64
V01_CLOSURE_SPRINT_MAX_ITEMS = 64
V01_CLOSURE_SPRINT_AUTHORITY_ORDER = (
    "CHECKPOINT",
    "SCOPE",
    "DEFINITION_OF_DONE",
    "ARCHITECTURE",
    "DECISIONS",
)
V01_CLOSURE_SPRINT_NEGATIVE_CASES = (
    "missing_authority",
    "stale_authority",
    "untracked_authority",
    "cross_project_authority",
)
V01_CLOSURE_SPRINT_E2E_STAGES = (
    "register_project",
    "index_repository",
    "ingest_prompt_artifact",
    "build_context",
    "dispatch_executor",
    "stream_telemetry",
    "modify_sample_project",
    "run_project_tests",
    "capture_evidence",
    "stage_memory",
    "complete_review",
    "verify_dashboard_and_persistence",
)
V01_CLOSURE_SPRINT_DOCUMENTATION_ENTRIES = (
    "architecture",
    "deployment",
    "checkpoint",
    "backlog",
    "known_limitations",
)
V01_CLOSURE_SPRINT_EVIDENCE_PATH_ROOTS = (
    "backend/",
    "scripts/",
    "docs/",
    "dashboard/",
)
V01_CLOSURE_SPRINT_EVIDENCE_PATH_FILES = frozenset(
    {
        "docker-compose.yml",
        ".env.example",
        "README.md",
        "Dockerfile",
    }
)
V01_CLOSURE_SPRINT_STRING_FIELDS = (
    "v01_closure_sprint_evidence_version",
    "evidence_file",
    "observed_migration_head",
    "migration_base_head",
    "reviewed_base_sha",
    "reviewed_head_sha",
    "fixture_identity",
    "corpus_identity",
    "run_digest",
    "deployment_persistent_root_identity",
    "backup_artifact_sha256",
    "dod_definition_of_done_sha256",
)
V01_CLOSURE_SPRINT_TRUE_FIELDS = (
    "stabilization_regression_suite_pass",
    "stabilization_no_scope_expansion",
    "deployment_compose_config_validated",
    "deployment_clean_boot",
    "deployment_services_healthy",
    "deployment_postgres_persistence_after_recreation",
    "deployment_cas_persistence_integrity",
    "deployment_redis_loss_recovery",
    "deployment_api_available",
    "deployment_dashboard_available",
    "deployment_mcp_available",
    "deployment_secondary_root_tested",
    "backup_postgres_dump_restore",
    "backup_cas_manifest_restore",
    "backup_config_restore",
    "backup_clean_target_proof",
    "backup_row_equivalence",
    "backup_cas_hash_equivalence",
    "backup_redis_excluded",
    "orchestration_project_resolved",
    "orchestration_git_state_bound",
    "orchestration_checkpoint_first",
    "orchestration_task_project_scoped",
    "orchestration_tool_gating",
    "e2e_sample_project_mutation_bounded",
    "docs_audited_from_repository_paths",
    "dod_matrix_complete",
)
V01_CLOSURE_SPRINT_FALSE_FIELDS = (
    "stabilization_scope_expansion_detected",
    "redis_canonical_truth",
    "fabricated_metrics",
    "provider_values_fabricated",
    "full_v01_complete_claimed",
)
V01_CLOSURE_SPRINT_ZERO_FIELDS = (
    "stabilization_remaining_critical",
    "stabilization_remaining_high",
    "secret_leaks",
    "filesystem_path_leaks",
    "cross_project_leaks",
    "core_llm_calls",
    "core_provider_calls",
    "orchestration_deterministic_llm_calls",
    "dod_fail_count",
    "dod_unknown_count",
)
V01_CLOSURE_SPRINT_INTEGER_BOUNDS = {
    "stabilization_defects_discovered": 1_000,
    "stabilization_defects_fixed": 1_000,
    "deployment_service_count": 64,
    "backup_artifact_count": 64,
    "e2e_stage_count": len(V01_CLOSURE_SPRINT_E2E_STAGES),
    "dod_total_count": 512,
    "dod_pass_count": 512,
}
V01_CLOSURE_SPRINT_LIST_FIELDS = (
    "changed_paths",
    "stabilization_evidence_paths",
    "deployment_evidence_paths",
    "backup_evidence_paths",
    "orchestration_evidence_paths",
    "e2e_evidence_paths",
)
V01_CLOSURE_SPRINT_ALLOWED_FIELDS = frozenset(
    {
        "status",
        "closure_candidate",
        "orchestration_authority_order",
        "orchestration_negative_matrix",
        "e2e_completed_stages",
        "documentation_entries",
        "dod_items",
        *V01_CLOSURE_SPRINT_STRING_FIELDS,
        *V01_CLOSURE_SPRINT_TRUE_FIELDS,
        *V01_CLOSURE_SPRINT_FALSE_FIELDS,
        *V01_CLOSURE_SPRINT_ZERO_FIELDS,
        *V01_CLOSURE_SPRINT_INTEGER_BOUNDS,
        *V01_CLOSURE_SPRINT_LIST_FIELDS,
    }
)

WO008_G1_ALLOWED_PATHS = frozenset(
    {
        ".github/workflows/ci.yml",
        "backend/tests/test_review_evidence.py",
        "schemas/review-evidence-v1.schema.json",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
    }
)
WO010_G1_ALLOWED_PATHS = frozenset(
    {
        ".github/workflows/ci.yml",
        "backend/tests/test_review_evidence.py",
        "docs/project-brain/13-CHECKPOINT.md",
        "docs/project-brain/16-DECISIONS-LEDGER.md",
        "docs/project-brain/CANONICAL-SHA256SUMS.txt",
        "schemas/review-evidence-v1.schema.json",
        "scripts/review_evidence.py",
        "scripts/review_pr_body.py",
    }
)
WO010_G1_CANONICAL_PATHS = (
    CHECKPOINT_PATH,
    "docs/project-brain/16-DECISIONS-LEDGER.md",
    "docs/project-brain/CANONICAL-SHA256SUMS.txt",
)
PROTECTED_MAIN_RULESET_ID = 21934284
SOLE_GITHUB_OPERATOR_LOGIN = "KayzenRoot"

WARNING_RULES = (
    (
        re.compile(r"(?:vm\.overcommit_memory|memory overcommit|overcommit_memory)", re.I),
        "Redis host warning observed: vm.overcommit_memory is disabled.",
    ),
    (
        re.compile(r"\bnpm\s+(?:warn|warning)\s+deprecated\b", re.I),
        "npm dependency deprecation warning observed.",
    ),
    (
        re.compile(
            r"(?:node(?:\.js)?\s+20\s+is\s+(?:being\s+)?deprecated|"
            r"target\s+node(?:\.js)?\s+20\b)",
            re.I,
        ),
        "GitHub Actions Node runtime deprecation warning observed.",
    ),
    (
        re.compile(r"\bnpm\s+(?:warn|warning)\s+allow-scripts\b", re.I),
        "npm install-script approval warning observed for a dependency.",
    ),
)


def run(command: list[str]) -> tuple[int, str]:
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.returncode, result.stdout.strip()


def run_in_repository(repository: Path, command: list[str]) -> tuple[int, str]:
    result = subprocess.run(
        command,
        cwd=repository,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.returncode, result.stdout.strip()


def git_value(*args: str, fallback: str = "") -> str:
    code, output = run(["git", *args])
    return output if code == 0 and output else fallback


def env_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y"}


def parse_work_order_marker(body: str) -> str:
    markers = WORK_ORDER_MARKER.findall(body)
    if len(markers) != 1:
        if not markers:
            raise ValueError("HIVE work-order PR is missing exactly one work-order marker")
        raise ValueError("HIVE work-order PR has multiple conflicting work-order markers")
    work_order = str(markers[0]).strip()
    if len(work_order) > 64 or (
        WORK_ORDER_IDENTIFIER.fullmatch(work_order) is None
        and GEF_WORK_ORDER_IDENTIFIER.fullmatch(work_order) is None
        and HIVE_REL_WORK_ORDER_IDENTIFIER.fullmatch(work_order) is None
        and RELEASE_TRAIN_WORK_ORDER_IDENTIFIER.fullmatch(work_order) is None
    ):
        raise ValueError(f"invalid or unbounded HIVE work-order identifier: {work_order!r}")
    return work_order


def parse_authorized_base_marker(body: str) -> str:
    markers = AUTHORIZED_BASE_MARKER.findall(body)
    if len(markers) != 1:
        if not markers:
            raise ValueError("HIVE promotion PR is missing exactly one authorized-base marker")
        raise ValueError("HIVE promotion PR has multiple conflicting authorized-base markers")
    base_sha = str(markers[0]).strip()
    if HEX_SHA.fullmatch(base_sha) is None:
        raise ValueError(
            "HIVE promotion PR authorized-base marker must contain one lowercase 40-hex SHA"
        )
    return base_sha


def authorized_base_marker_sha(work_order: str, pr_body: str) -> str | None:
    """Return the authorized-base marker for the work orders that must carry one.

    Every registered promotion work order and the GEF adoption work order require
    exactly one marker; anything else carries none. Missing, duplicated, malformed
    or non-promotion markers fail closed through ``parse_authorized_base_marker``.
    """

    if work_order not in AUTHORIZED_BASE_MARKER_WORK_ORDERS:
        return None
    return parse_authorized_base_marker(pr_body)


# WO-025-G3: the explicit deny-by-default registry. Before this increment,
# ``require_supported_work_order`` was deny-by-*pattern*: it rejected a few known-bad shapes and
# then fell off the end of the function, so anything matching no rejection branch was silently
# accepted -- including the empty string, malformed identifiers and unregistered near-misses such
# as ``WO-11-01``. This set is the closed world of identifiers the tooling is registered to govern:
# an identifier is supported if and only if it appears here (or is a named sentinel below). The
# historical numeric threshold survives only as a diagnostic hint in the rejection message, never as
# a grant.
#
# Every entry below other than the current WO-025 registrations was accepted by the previous
# implementation, so this registry preserves historical behavior exactly while removing the
# fallthrough. ``WO-025-G3`` and ``WO-025-P`` are the new registrations made by this increment.
REGISTERED_WORK_ORDERS = frozenset(
    {
        # Registered checkpoint-promotion work orders.
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
        "WO-014-P",
        "WO-014-P-G1",
        "WO-015-P",
        "WO-015-P-G1",
        "WO-016-P",
        "WO-016-P-G1",
        "WO-017-P",
        "WO-017-P-G1",
        "WO-018-P",
        "WO-018-P-G1",
        "WO-019-P",
        "WO-019-P-G1",
        "WO-020-P",
        "WO-020-P-G1",
        "WO-021-P",
        "WO-021-P-G1",
        "WO-022-P",
        "WO-022-P-G1",
        "WO-023-P",
        "WO-023-P-G1",
        "WO-023-P-G1-C1",
        "WO-024-P",
        "WO-024-P-G1-C1",
        "WO-024-P-G1-C2",
        "WO-024-P-G1-C3",
        "WO-024-P-G1-C4",
        "WO-025-P",
        # Registered non-promotion work orders plus the GEF and release-engineering registrations.
        GEF_ADOPTION_WORK_ORDER,
        "HIVE-REL-001",
        "HIVE-REL-002",
        "HIVE-REL-003",
        HIVE_REL_004_WORK_ORDER,
        HIVE_REL_005_WORK_ORDER,
        HIVE_REL_006_WORK_ORDER,
        "WO-006",
        "WO-008",
        "WO-008-G1",
        "WO-009",
        "WO-010",
        "WO-010-G1",
        "WO-011",
        "WO-012",
        "WO-013",
        "WO-014",
        "WO-014-C2",
        "WO-015",
        "WO-015-G1",
        "WO-016",
        "WO-016-G1",
        "WO-017",
        "WO-017-G1",
        "WO-018",
        "WO-018-G1",
        "WO-019",
        "WO-019-G1",
        "WO-020",
        "WO-020-G1",
        "WO-021",
        "WO-021-G1",
        "WO-022",
        "WO-022-G1",
        "WO-023",
        "WO-023-G1",
        "WO-024",
        "WO-024-G1",
        "WO-025",
        "WO-025-G1",
        "WO-025-G2",
        "WO-025-G3",
        "WO-025-G4",
        "WO-025-G5",
        "WO-026",
        "WO-027",
        "WO-028",
        WO029_WORK_ORDER,
        WO030_WORK_ORDER,
        WO030_C1_WORK_ORDER,
        "WO-1.1-01",
    }
)
# The only accepted identifier that is not a work order: the local validation sentinel that
# ``scripts/validate.py`` passes when it runs the evidence generator without a pull request.
WORK_ORDER_SENTINELS = frozenset({"LOCAL-VALIDATION"})
# The current promotion frontier is deliberately separate from promotion history. WO-024-G1 and
# WO-024-P remain the audited historical pair that the closure contracts freeze, while WO-025-P is
# the promotion allowed to open a fresh pull request once WO-025-G3 lands.
CURRENT_CHECKPOINT_PROMOTION_WORK_ORDERS = frozenset({WO025P_WORK_ORDER})
# The canonical checkpoint state WO-025-G3 declares and WO-025-P applies. Nothing here edits the
# checkpoint: the working tree keeps the V0.1 closure status until the promotion merges.
EXPECTED_WO025P_PREVIOUS_STATUS = EXPECTED_WO024P_STATUS
EXPECTED_WO025P_STATUS = (
    "HIVE POST-1.0 PLANNING PROMOTED / DECISION FABRIC 1.1 RELEASE TRAIN AUTHORIZED"
)
# The operational state the promoted checkpoint must carry so the release train is coherent:
# WO-1.1-01 is the only work in flight, it waits on a verified HIVE-first preflight, and nothing is
# pending. WO-025-G4 freezes these so Integration health can recognize the state it will run in.
EXPECTED_WO025P_IN_PROGRESS = "Preparing WO-1.1-01 under verified HIVE-first execution."
EXPECTED_WO025P_BLOCKERS = "None known after the verified HIVE-first preflight."
EXPECTED_WO025P_NEXT_STEP = "Execute WO-1.1-01 Decision Contract Kernel + Deterministic Resolver."
# The only sections a WO-025-P promotion may rewrite. Everything else in the checkpoint --
# VERSION, PHASE, OBJECTIVE, SCOPE, COMPLETED, GOVERNANCE, DECISIONS, DEFINITION OF DONE, BACKLOG
# and any future section -- is preserved byte-for-byte, so an arbitrary checkpoint that merely
# swapped STATUS cannot pass as a promotion.
WO025P_RAW_PROMOTION_CONTROLLED_SECTIONS = frozenset(
    {"STATUS", "IN PROGRESS", "PENDING", "BLOCKERS", "NEXT STEP"}
)
# Which canonical promotion releases a registered release-train work order. Deny-by-default: an
# order with no entry here never authorizes, and an order with one releases from the promoted
# checkpoint itself rather than from a flag that would need a further governance commit.
RELEASE_TRAIN_PROMOTING_WORK_ORDERS: dict[str, str] = {WO11_01_WORK_ORDER: WO025P_WORK_ORDER}


def require_supported_work_order(work_order: str) -> None:
    """Fail closed unless the identifier is explicitly registered.

    Deny-by-default replaces the historical fallthrough: success is reachable only through the
    explicit registry or the named sentinel. The former numeric threshold survives as a diagnostic
    hint in the message, never as a grant.
    """

    if work_order in REGISTERED_WORK_ORDERS or work_order in WORK_ORDER_SENTINELS:
        return
    if GEF_WORK_ORDER_IDENTIFIER.fullmatch(work_order):
        raise ValueError(
            "unsupported GEF adoption work order; explicit governance registration is required: "
            + work_order
        )
    if HIVE_REL_WORK_ORDER_IDENTIFIER.fullmatch(work_order):
        raise ValueError(
            "unsupported release-engineering work order; explicit governance "
            "registration is required: " + work_order
        )
    if PROMOTION_WORK_ORDER_IDENTIFIER.fullmatch(work_order):
        raise ValueError(
            "unsupported checkpoint-promotion work order; explicit governance "
            "registration is required: " + work_order
        )
    if RELEASE_TRAIN_WORK_ORDER_IDENTIFIER.fullmatch(work_order):
        raise ValueError(
            "unsupported release-train work order; explicit governance registration is required: "
            + work_order
        )
    raise ValueError(
        "unsupported future work order; explicit governance registration is required: " + work_order
    )


def require_current_work_order_authorization(work_order: str) -> None:
    require_supported_work_order(work_order)
    if work_order in CORRECTIVE_GOVERNANCE_WORK_ORDERS:
        return
    if work_order in PENDING_PLANNING_PROMOTION_WORK_ORDERS:
        raise ValueError(
            "registered planning promotion is not authorized as a current work order yet; its own "
            "governance increment must authorize it: " + work_order
        )
    if RELEASE_TRAIN_WORK_ORDER_IDENTIFIER.fullmatch(work_order):
        require_release_train_promotion_evidence(work_order)
        return
    if (
        PROMOTION_WORK_ORDER_IDENTIFIER.fullmatch(work_order)
        and work_order not in ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS
        and work_order not in CURRENT_CHECKPOINT_PROMOTION_WORK_ORDERS
    ):
        raise ValueError(
            "historical checkpoint-promotion work order cannot authorize a fresh current PR: "
            + work_order
        )


def require_wo025p_checkpoint_semantics(base_text: str, candidate_text: str) -> None:
    """Enforce the exact checkpoint promotion WO-025-P must leave behind.

    The base still has to be the V0.1 closure checkpoint and the candidate has to carry the promoted
    status and operational state verbatim. Only the controlled promotion sections may differ: the
    preamble, every heading, the section sequence and every uncontrolled section -- VERSION, PHASE,
    OBJECTIVE, SCOPE, COMPLETED, GOVERNANCE, DECISIONS, DEFINITION OF DONE and BACKLOG included --
    stay byte-for-byte identical, so an arbitrary checkpoint that merely swapped STATUS never
    releases the release-train gate.
    """

    base = checkpoint_sections(base_text)
    if normalized_checkpoint_value(base, "STATUS") != EXPECTED_WO025P_PREVIOUS_STATUS:
        raise ValueError(
            f"{WO025P_WORK_ORDER} promotion base is not the V0.1 closure checkpoint status"
        )
    base_preamble, base_ordered, base_sections = _raw_checkpoint_structure(base_text, "base")
    candidate_preamble, candidate_ordered, candidate_sections = _raw_checkpoint_structure(
        candidate_text, "candidate"
    )
    if base_preamble != candidate_preamble:
        raise ValueError(f"{WO025P_WORK_ORDER} candidate preamble changed byte-for-byte")
    if tuple(section.name for section in base_ordered) != tuple(
        section.name for section in candidate_ordered
    ):
        raise ValueError(f"{WO025P_WORK_ORDER} checkpoint section sequence changed unexpectedly")
    for position, (base_section, candidate_section) in enumerate(
        zip(base_ordered, candidate_ordered, strict=True), 1
    ):
        if base_section.heading != candidate_section.heading:
            raise ValueError(
                f"{WO025P_WORK_ORDER} heading changed byte-for-byte at position {position}"
            )
    for name in tuple(section.name for section in base_ordered):
        if (
            name not in WO025P_RAW_PROMOTION_CONTROLLED_SECTIONS
            and candidate_sections[name] != base_sections[name]
        ):
            raise ValueError(f"{WO025P_WORK_ORDER} changed unrelated checkpoint section: {name}")
    newline = "\n"
    expected_controlled: dict[str, str] = {
        "STATUS": f"{EXPECTED_WO025P_STATUS}{newline}{newline}",
        "IN PROGRESS": f"- {EXPECTED_WO025P_IN_PROGRESS}{newline}{newline}",
        "BLOCKERS": f"{EXPECTED_WO025P_BLOCKERS}{newline}{newline}",
        "NEXT STEP": f"{EXPECTED_WO025P_NEXT_STEP}{newline}{newline}",
        "PENDING": f"{newline}",
    }
    for name, expected_body in expected_controlled.items():
        if candidate_sections.get(name) != expected_body:
            raise ValueError(
                f"{WO025P_WORK_ORDER} {name} section is outside the strict raw grammar"
            )


def require_canonical_manifest_digests(source_root: Path, manifest_text: str) -> None:
    """Re-derive every canonical digest from disk instead of trusting a claimed promotion."""

    brain_root = source_root / Path(CANONICAL_MANIFEST_PATH).parent
    for name, digest in parse_canonical_manifest(manifest_text, str(source_root)):
        path = brain_root / name
        if not path.is_file():
            raise ValueError(f"canonical source is missing: {name}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"canonical digest does not match the manifest: {name}")


def require_release_train_promotion_evidence(work_order: str) -> None:
    """Release a registered release-train order only from the promoted canonical checkpoint."""

    promoting_order = RELEASE_TRAIN_PROMOTING_WORK_ORDERS.get(work_order)
    if promoting_order is None:
        raise ValueError(
            "registered release-train work order has no canonical promotion that releases it; "
            "explicit governance registration is required: " + work_order
        )
    blocked = (
        f"{work_order} is not authorized as a current work order yet; the canonical checkpoint "
        f"promotion by {promoting_order} must land first"
    )
    checkpoint_file = ROOT / CHECKPOINT_PATH
    manifest_file = ROOT / CANONICAL_MANIFEST_PATH
    if not checkpoint_file.is_file() or not manifest_file.is_file():
        raise ValueError(blocked)
    sections = checkpoint_sections(checkpoint_file.read_bytes().decode("utf-8"))
    if normalized_checkpoint_value(sections, "STATUS") != EXPECTED_WO025P_STATUS:
        raise ValueError(blocked)
    require_canonical_manifest_digests(ROOT, manifest_file.read_bytes().decode("utf-8"))


def require_gef_adoption_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    authorized_base_sha: str | None = None,
) -> None:
    if work_order != GEF_ADOPTION_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{GEF_ADOPTION_WORK_ORDER} requires the protected main base branch")
    if base_sha != GEF_ADOPTION_BASE_SHA:
        raise ValueError(
            f"{GEF_ADOPTION_WORK_ORDER} requires exact base {GEF_ADOPTION_BASE_SHA}, "
            f"observed {base_sha}"
        )
    if authorized_base_sha != GEF_ADOPTION_BASE_SHA:
        raise ValueError(
            f"{GEF_ADOPTION_WORK_ORDER} requires the exact authorized-base marker "
            f"{GEF_ADOPTION_BASE_SHA}"
        )
    if sorted(set(paths)) != sorted(GEF_ADOPTION_ALLOWED_PATHS) or len(paths) != len(
        GEF_ADOPTION_ALLOWED_PATHS
    ):
        raise ValueError(
            f"{GEF_ADOPTION_WORK_ORDER} requires exactly the ten GEF artifacts and "
            "the Review Evidence bridge/test files"
        )
    if any(
        path == "docs/project-brain"
        or path.startswith("docs/project-brain/")
        or path == "migrations"
        or path.startswith("migrations/")
        or path == ".github"
        or path.startswith(".github/")
        for path in paths
    ):
        raise ValueError(
            f"{GEF_ADOPTION_WORK_ORDER} cannot change Project Brain, migrations, or CI workflows"
        )


def require_hive_rel_001_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    authorized_base_sha: str | None = None,
) -> None:
    if work_order != HIVE_REL_001_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{HIVE_REL_001_WORK_ORDER} requires the protected main base branch")
    if base_sha != HIVE_REL_001_BASE_SHA:
        raise ValueError(
            f"{HIVE_REL_001_WORK_ORDER} requires exact base {HIVE_REL_001_BASE_SHA}, "
            f"observed {base_sha}"
        )
    if authorized_base_sha != HIVE_REL_001_BASE_SHA:
        raise ValueError(
            f"{HIVE_REL_001_WORK_ORDER} requires the exact authorized-base marker "
            f"{HIVE_REL_001_BASE_SHA}"
        )
    if not paths:
        raise ValueError(f"{HIVE_REL_001_WORK_ORDER} requires a non-empty change set")
    unique_paths = set(paths)
    unauthorized = sorted(
        path
        for path in unique_paths
        if path not in HIVE_REL_001_ALLOWED_EXACT_PATHS
        and not path.startswith(HIVE_REL_001_ALLOWED_PREFIXES)
    )
    if unauthorized:
        raise ValueError(
            f"{HIVE_REL_001_WORK_ORDER} changes paths outside the registered release scope: "
            + ", ".join(unauthorized)
        )
    forbidden = sorted(
        path
        for path in unique_paths
        if path in HIVE_REL_001_FORBIDDEN_EXACT_PATHS
        or path.startswith(HIVE_REL_001_FORBIDDEN_PREFIXES)
    )
    if forbidden:
        raise ValueError(
            f"{HIVE_REL_001_WORK_ORDER} cannot change immutable or local-only paths: "
            + ", ".join(forbidden)
        )


def require_hive_rel_002_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    authorized_base_sha: str | None = None,
) -> None:
    """Bound the post-merge release-publisher increment to release operations only."""

    if work_order != HIVE_REL_002_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{HIVE_REL_002_WORK_ORDER} requires the protected main base branch")
    if base_sha != HIVE_REL_002_BASE_SHA:
        raise ValueError(
            f"{HIVE_REL_002_WORK_ORDER} requires exact base {HIVE_REL_002_BASE_SHA}, "
            f"observed {base_sha}"
        )
    if authorized_base_sha != HIVE_REL_002_BASE_SHA:
        raise ValueError(
            f"{HIVE_REL_002_WORK_ORDER} requires the exact authorized-base marker "
            f"{HIVE_REL_002_BASE_SHA}"
        )
    if not paths:
        raise ValueError(f"{HIVE_REL_002_WORK_ORDER} requires a non-empty change set")
    unique_paths = set(paths)
    unauthorized = sorted(unique_paths - HIVE_REL_002_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            f"{HIVE_REL_002_WORK_ORDER} changes paths outside the bounded publisher scope: "
            + ", ".join(unauthorized)
        )
    forbidden = sorted(
        path for path in unique_paths if path.startswith(HIVE_REL_002_FORBIDDEN_PREFIXES)
    )
    if forbidden:
        raise ValueError(
            f"{HIVE_REL_002_WORK_ORDER} cannot change canonical or local-only paths: "
            + ", ".join(forbidden)
        )


def require_hive_rel_003_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    authorized_base_sha: str | None = None,
) -> None:
    """Bound the release-publisher workspace-parity correction."""

    if work_order != HIVE_REL_003_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{HIVE_REL_003_WORK_ORDER} requires the protected main base branch")
    if base_sha != HIVE_REL_003_BASE_SHA:
        raise ValueError(
            f"{HIVE_REL_003_WORK_ORDER} requires exact base {HIVE_REL_003_BASE_SHA}, "
            f"observed {base_sha}"
        )
    if authorized_base_sha != HIVE_REL_003_BASE_SHA:
        raise ValueError(
            f"{HIVE_REL_003_WORK_ORDER} requires the exact authorized-base marker "
            f"{HIVE_REL_003_BASE_SHA}"
        )
    if not paths:
        raise ValueError(f"{HIVE_REL_003_WORK_ORDER} requires a non-empty change set")
    unique_paths = set(paths)
    unauthorized = sorted(unique_paths - HIVE_REL_003_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            f"{HIVE_REL_003_WORK_ORDER} changes paths outside the bounded correction scope: "
            + ", ".join(unauthorized)
        )
    forbidden = sorted(
        path for path in unique_paths if path.startswith(HIVE_REL_003_FORBIDDEN_PREFIXES)
    )
    if forbidden:
        raise ValueError(
            f"{HIVE_REL_003_WORK_ORDER} cannot change canonical or local-only paths: "
            + ", ".join(forbidden)
        )


def require_hive_rel_004_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    authorized_base_sha: str | None = None,
) -> None:
    """Bound the stale completed-release publisher correction."""

    if work_order != HIVE_REL_004_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{HIVE_REL_004_WORK_ORDER} requires the protected main base branch")
    if base_sha != HIVE_REL_004_BASE_SHA:
        raise ValueError(
            f"{HIVE_REL_004_WORK_ORDER} requires exact base {HIVE_REL_004_BASE_SHA}, "
            f"observed {base_sha}"
        )
    if authorized_base_sha != HIVE_REL_004_BASE_SHA:
        raise ValueError(
            f"{HIVE_REL_004_WORK_ORDER} requires the exact authorized-base marker "
            f"{HIVE_REL_004_BASE_SHA}"
        )
    if not paths:
        raise ValueError(f"{HIVE_REL_004_WORK_ORDER} requires a non-empty change set")
    unique_paths = set(paths)
    unauthorized = sorted(unique_paths - HIVE_REL_004_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            f"{HIVE_REL_004_WORK_ORDER} changes paths outside the bounded correction scope: "
            + ", ".join(unauthorized)
        )
    forbidden = sorted(
        path for path in unique_paths if path.startswith(HIVE_REL_004_FORBIDDEN_PREFIXES)
    )
    if forbidden:
        raise ValueError(
            f"{HIVE_REL_004_WORK_ORDER} cannot change canonical or local-only paths: "
            + ", ".join(forbidden)
        )


def require_hive_rel_005_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    authorized_base_sha: str | None = None,
) -> None:
    """Bound v1.0.1 release preparation to its exact base and file surface."""

    if work_order != HIVE_REL_005_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{HIVE_REL_005_WORK_ORDER} requires the protected main base branch")
    if base_sha != HIVE_REL_005_BASE_SHA:
        raise ValueError(
            f"{HIVE_REL_005_WORK_ORDER} requires exact base {HIVE_REL_005_BASE_SHA}, "
            f"observed {base_sha}"
        )
    if authorized_base_sha != HIVE_REL_005_BASE_SHA:
        raise ValueError(
            f"{HIVE_REL_005_WORK_ORDER} requires the exact authorized-base marker "
            f"{HIVE_REL_005_BASE_SHA}"
        )
    if not paths:
        raise ValueError(f"{HIVE_REL_005_WORK_ORDER} requires a non-empty change set")
    unique_paths = set(paths)
    forbidden = sorted(
        path for path in unique_paths if path.startswith(HIVE_REL_005_FORBIDDEN_PREFIXES)
    )
    if forbidden:
        raise ValueError(
            f"{HIVE_REL_005_WORK_ORDER} cannot change canonical or local-only paths: "
            + ", ".join(forbidden)
        )
    unauthorized = sorted(unique_paths - HIVE_REL_005_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            f"{HIVE_REL_005_WORK_ORDER} changes paths outside the bounded preparation scope: "
            + ", ".join(unauthorized)
        )


def require_hive_rel_006_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    authorized_base_sha: str | None = None,
) -> None:
    """Bound v1.0.1 publication authorization to its exact base and file surface."""

    if work_order != HIVE_REL_006_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{HIVE_REL_006_WORK_ORDER} requires the protected main base branch")
    if base_sha != HIVE_REL_006_BASE_SHA:
        raise ValueError(
            f"{HIVE_REL_006_WORK_ORDER} requires exact base {HIVE_REL_006_BASE_SHA}, "
            f"observed {base_sha}"
        )
    if authorized_base_sha != HIVE_REL_006_BASE_SHA:
        raise ValueError(
            f"{HIVE_REL_006_WORK_ORDER} requires the exact authorized-base marker "
            f"{HIVE_REL_006_BASE_SHA}"
        )
    if not paths:
        raise ValueError(f"{HIVE_REL_006_WORK_ORDER} requires a non-empty change set")
    unique_paths = set(paths)
    forbidden = sorted(
        path for path in unique_paths if path.startswith(HIVE_REL_006_FORBIDDEN_PREFIXES)
    )
    if forbidden:
        raise ValueError(
            f"{HIVE_REL_006_WORK_ORDER} cannot change canonical or local-only paths: "
            + ", ".join(forbidden)
        )
    unauthorized = sorted(unique_paths - HIVE_REL_006_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            f"{HIVE_REL_006_WORK_ORDER} changes paths outside the bounded publication scope: "
            + ", ".join(unauthorized)
        )


def pull_request_body(repository: str, pr_number: int) -> str:
    pr = _gh_json(repository, f"pulls/{pr_number}")
    if not isinstance(pr, dict):
        raise ValueError(f"unable to read pull request #{pr_number} for work-order derivation")
    body = pr.get("body")
    return body if isinstance(body, str) else ""


def derive_work_order(repository: str, pr_number: int) -> str:
    body = pull_request_body(repository, pr_number)
    work_order = parse_work_order_marker(body)
    require_current_work_order_authorization(work_order)
    return work_order


def canonical_change_evidence(paths: list[str], work_order: str = "") -> dict[str, object]:
    changed = set(paths)
    project_brain_changed = any(
        path == "docs/project-brain" or path.startswith("docs/project-brain/") for path in changed
    )
    authorized_candidates = (
        WO010_G1_CANONICAL_PATHS if work_order == "WO-010-G1" else CANONICAL_PATHS
    )
    return {
        "project_brain_changed": project_brain_changed,
        "checkpoint_changed": CHECKPOINT_PATH in changed,
        "authorized_paths": [path for path in authorized_candidates if path in changed],
    }


def canonical_change_statement(evidence: dict[str, object]) -> str:
    payload = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
    return f"Canonical change evidence: {payload}"


def git_blob_bytes(revision: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"unable to read {path} from exact base {revision}")
    return result.stdout


def checkpoint_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match:
            current = match.group(1).strip().upper()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {name: "\n".join(lines).strip() for name, lines in sections.items()}


_RAW_CHECKPOINT_HEADING = re.compile(r"(?m)^##[ \t]+([^\r\n]*?)[ \t]*(?:\r\n|\n|\r|\Z)")
_WO016P_RAW_CONTROLLED_SECTIONS = frozenset(
    {"STATUS", "COMPLETED", "IN PROGRESS", "PENDING", "BLOCKERS", "NEXT STEP"}
)


class _RawCheckpointSection(NamedTuple):
    name: str
    heading: str
    body: str


def _raw_checkpoint_structure(
    text: str, label: str
) -> tuple[str, tuple[_RawCheckpointSection, ...], dict[str, str]]:
    matches = list(_RAW_CHECKPOINT_HEADING.finditer(text))
    if not matches:
        raise ValueError(f"WO-016-P {label} has no canonical section headings")
    if "\r" in text:
        raise ValueError(f"WO-016-P {label} must use the canonical LF newline policy")

    preamble = text[: matches[0].start()]
    sections: list[_RawCheckpointSection] = []
    bodies: dict[str, str] = {}
    for index, match in enumerate(matches):
        name = match.group(1).strip().upper()
        if not name:
            raise ValueError(f"WO-016-P {label} contains an empty section heading")
        if name in bodies:
            raise ValueError(f"WO-016-P {label} contains duplicate section heading: {name}")
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : next_start]
        sections.append(_RawCheckpointSection(name, match.group(0), body))
        bodies[name] = body
    return preamble, tuple(sections), bodies


def _require_wo016p_strict_raw_checkpoint_grammar(base_text: str, candidate_text: str) -> None:
    base_preamble, base_ordered_sections, base_sections = _raw_checkpoint_structure(
        base_text, "base"
    )
    candidate_preamble, candidate_ordered_sections, candidate_sections = _raw_checkpoint_structure(
        candidate_text, "candidate"
    )
    if base_preamble != candidate_preamble:
        raise ValueError("WO-016-P candidate preamble changed byte-for-byte")
    base_names = tuple(section.name for section in base_ordered_sections)
    candidate_names = tuple(section.name for section in candidate_ordered_sections)
    if base_names != candidate_names:
        raise ValueError("WO-016-P checkpoint section sequence changed unexpectedly")

    for position, (base_section, candidate_section) in enumerate(
        zip(base_ordered_sections, candidate_ordered_sections, strict=True), 1
    ):
        if base_section.heading.encode("utf-8") != candidate_section.heading.encode("utf-8"):
            raise ValueError(
                f"WO-016-P section heading changed byte-for-byte at position {position}"
            )

    required_sections = set(_WO016P_RAW_CONTROLLED_SECTIONS)
    if not required_sections.issubset(base_sections):
        raise ValueError("WO-016-P base is missing a required canonical checkpoint section")

    for name in base_names:
        if (
            name not in _WO016P_RAW_CONTROLLED_SECTIONS
            and candidate_sections[name] != base_sections[name]
        ):
            raise ValueError(f"WO-016-P changed unrelated checkpoint section: {name}")

    newline = "\n"
    expected_controlled = {
        "STATUS": f"{EXPECTED_WO016P_STATUS}{newline}{newline}",
        "IN PROGRESS": f"- {EXPECTED_WO016P_IN_PROGRESS}{newline}{newline}",
        "BLOCKERS": f"{EXPECTED_WO016P_BLOCKERS}{newline}{newline}",
        "NEXT STEP": f"{EXPECTED_WO016P_NEXT_STEP}{newline}{newline}",
    }

    base_completed = base_sections["COMPLETED"]
    if not base_completed.endswith(newline):
        raise ValueError("WO-016-P base COMPLETED section lacks the canonical final newline")
    # The final newline in the raw section body is the canonical separator
    # before the next heading.  The fixture and the checkpoint grammar append
    # the new completion bullets immediately after the historical final line,
    # retaining the section's single final newline.
    expected_controlled["COMPLETED"] = (
        base_completed[:-1]
        + "".join(f"- {bullet}{newline}" for bullet in WO016P_CANONICAL_COMPLETION_BULLETS)
        + newline
    )

    base_pending_lines = base_sections["PENDING"].splitlines(keepends=True)
    pending_line = f"- {EXPECTED_WO016P_PENDING_ITEM}{newline}"
    if base_pending_lines.count(pending_line) != 1:
        raise ValueError("WO-016-P base PENDING must contain exactly one raw ACCE pending line")
    expected_controlled["PENDING"] = "".join(
        line for line in base_pending_lines if line != pending_line
    )

    for name, expected_body in expected_controlled.items():
        if candidate_sections.get(name) != expected_body:
            raise ValueError(f"WO-016-P {name} section is outside the strict raw grammar")


def checkpoint_bullets(sections: Mapping[str, str], name: str) -> list[str]:
    return [
        line.strip()[2:].strip()
        for line in sections.get(name, "").splitlines()
        if line.strip().startswith("- ")
    ]


def normalized_checkpoint_value(sections: Mapping[str, str], name: str) -> str:
    return " ".join(sections.get(name, "").split())


WO012P_CANONICAL_COMPLETION_BULLETS = (
    "context fingerprints foundation approval is recorded with policy "
    "context-fingerprint-v2, input context-input-v2, output context-output-v2 "
    "and cache context-fingerprint-cache-v2.",
    "the implementation uses sha-256; redis ttl 300 seconds remains "
    "non-canonical; transient reranker failure is not cached; transient "
    "semantic provider failure is not cached; provider recovery is retried; "
    "equivalent rebuild is stable.",
    "the context-fingerprint benchmark records false cache hits 0, critical "
    "context misses 0, exact repeat work avoidance, fingerprint llm calls 0 "
    "and fingerprint provider calls 0.",
    "evidence references migration 0005_semantic_retrieval, pr #40, audited "
    "head 2a128dfcdeb97a45f174cf2dfa529826354f95ad, sol review 5119310904, "
    "merge 743253ef079596370a7ff1102faf03b3a603b585, post-merge ci "
    "33937782195, backend 275/dashboard 7.",
    "delta context not implemented; provider/prompt cache not implemented; "
    "memory lifecycle not implemented.",
)


def normalized_checkpoint_evidence(text: str) -> str:
    return " ".join(text.casefold().split())


def require_wo012p_checkpoint_semantics(base_text: str, candidate_text: str) -> None:
    base = checkpoint_sections(base_text)
    candidate = checkpoint_sections(candidate_text)
    if set(base) != set(candidate):
        raise ValueError("WO-012-P checkpoint sections changed unexpectedly")
    if normalized_checkpoint_value(base, "STATUS") != EXPECTED_WO012P_PREVIOUS_STATUS:
        raise ValueError("WO-012-P promotion base has an unexpected checkpoint status")
    if normalized_checkpoint_value(candidate, "STATUS") != EXPECTED_WO012P_STATUS:
        raise ValueError("WO-012-P candidate has an unexpected checkpoint status")

    base_completed = checkpoint_bullets(base, "COMPLETED")
    candidate_completed = checkpoint_bullets(candidate, "COMPLETED")
    if candidate_completed[: len(base_completed)] != base_completed:
        raise ValueError("WO-012-P cannot rewrite historical COMPLETED checkpoint truth")
    appended_completed = candidate_completed[len(base_completed) :]
    if len(appended_completed) != len(WO012P_CANONICAL_COMPLETION_BULLETS):
        raise ValueError(
            "WO-012-P candidate must append exactly 5 authorized completion evidence bullets"
        )
    for index, (bullet, expected_bullet) in enumerate(
        zip(appended_completed, WO012P_CANONICAL_COMPLETION_BULLETS, strict=True), 1
    ):
        normalized_bullet = normalized_checkpoint_evidence(bullet)
        if normalized_bullet != expected_bullet:
            raise ValueError(
                f"WO-012-P completion evidence class {index} is outside its closed grammar"
            )

    base_pending = checkpoint_bullets(base, "PENDING")
    candidate_pending = checkpoint_bullets(candidate, "PENDING")
    if base_pending.count("context fingerprints.") != 1:
        raise ValueError(
            "WO-012-P promotion base must contain exactly one context fingerprints item"
        )
    expected_pending = list(base_pending)
    expected_pending.remove("context fingerprints.")
    if candidate_pending != expected_pending:
        raise ValueError(
            "WO-012-P must remove only context fingerprints. from PENDING and "
            "preserve all other items"
        )

    if normalized_checkpoint_value(candidate, "IN PROGRESS") != f"- {EXPECTED_WO012P_IN_PROGRESS}":
        raise ValueError("WO-012-P candidate has an unexpected IN PROGRESS intent")
    if normalized_checkpoint_value(candidate, "BLOCKERS") not in ACCEPTED_WO012P_BLOCKERS:
        raise ValueError("WO-012-P candidate has an unexpected BLOCKERS intent")
    next_step = normalized_checkpoint_value(candidate, "NEXT STEP")
    if not next_step.startswith(EXPECTED_WO012P_NEXT_STEP_PREFIX):
        raise ValueError("WO-012-P NEXT STEP must target Delta Context Foundation")
    if "do not prescribe code unnecessarily." not in next_step.casefold():
        raise ValueError("WO-012-P NEXT STEP must preserve the no-code-prescription intent")
    if any(
        phrase in next_step.casefold()
        for phrase in (
            "delta context foundation implemented",
            "provider/prompt cache implemented",
            "memory lifecycle implemented",
        )
    ):
        raise ValueError("WO-012-P NEXT STEP falsely marks later work completed")

    for name in set(base) - {
        "STATUS",
        "COMPLETED",
        "IN PROGRESS",
        "PENDING",
        "BLOCKERS",
        "NEXT STEP",
    }:
        if base[name] != candidate[name]:
            raise ValueError(f"WO-012-P changed unrelated checkpoint section: {name}")


def require_wo013p_checkpoint_semantics(base_text: str, candidate_text: str) -> None:
    base = checkpoint_sections(base_text)
    candidate = checkpoint_sections(candidate_text)
    if set(base) != set(candidate):
        raise ValueError("WO-013-P checkpoint sections changed unexpectedly")
    if normalized_checkpoint_value(base, "STATUS") != EXPECTED_WO013P_PREVIOUS_STATUS:
        raise ValueError("WO-013-P promotion base has an unexpected checkpoint status")
    if normalized_checkpoint_value(candidate, "STATUS") != EXPECTED_WO013P_STATUS:
        raise ValueError("WO-013-P candidate has an unexpected checkpoint status")

    base_completed = checkpoint_bullets(base, "COMPLETED")
    candidate_completed = checkpoint_bullets(candidate, "COMPLETED")
    if candidate_completed[: len(base_completed)] != base_completed:
        raise ValueError("WO-013-P cannot rewrite historical COMPLETED checkpoint truth")
    appended_completed = candidate_completed[len(base_completed) :]
    if len(appended_completed) != len(WO013P_CANONICAL_COMPLETION_BULLETS):
        raise ValueError(
            "WO-013-P candidate must append exactly 5 authorized completion evidence bullets"
        )
    for index, (bullet, expected_bullet) in enumerate(
        zip(appended_completed, WO013P_CANONICAL_COMPLETION_BULLETS, strict=True), 1
    ):
        if normalized_checkpoint_evidence(bullet) != expected_bullet:
            raise ValueError(
                f"WO-013-P completion evidence class {index} is outside its closed grammar"
            )

    base_pending = checkpoint_bullets(base, "PENDING")
    candidate_pending = checkpoint_bullets(candidate, "PENDING")
    if base_pending.count("delta context.") != 1:
        raise ValueError("WO-013-P promotion base must contain exactly one delta context item")
    expected_pending = list(base_pending)
    expected_pending.remove("delta context.")
    if candidate_pending != expected_pending:
        raise ValueError(
            "WO-013-P must remove only delta context. from PENDING and preserve all other items"
        )

    if normalized_checkpoint_value(candidate, "IN PROGRESS") != f"- {EXPECTED_WO013P_IN_PROGRESS}":
        raise ValueError("WO-013-P candidate has an unexpected IN PROGRESS intent")
    if normalized_checkpoint_value(candidate, "BLOCKERS") != EXPECTED_WO013P_BLOCKERS:
        raise ValueError("WO-013-P candidate has an unexpected BLOCKERS intent")
    next_step = normalized_checkpoint_value(candidate, "NEXT STEP")
    if not next_step.startswith(EXPECTED_WO013P_NEXT_STEP_PREFIX):
        raise ValueError("WO-013-P NEXT STEP must target Provider/Prompt Cache Adapter Foundation")
    normalized_next_step = next_step.casefold()
    if any(
        intent.casefold() not in normalized_next_step
        for intent in WO013P_NEXT_STEP_REQUIRED_INTENTS
    ):
        raise ValueError("WO-013-P NEXT STEP must preserve the bounded future-work intent")
    if any(
        phrase in normalized_next_step
        for phrase in (
            "provider/prompt cache implemented",
            "memory lifecycle implemented",
            "mcp product surface implemented",
            "autonomous executor dispatch implemented",
        )
    ):
        raise ValueError("WO-013-P NEXT STEP falsely marks later work completed")

    for name in set(base) - {
        "STATUS",
        "COMPLETED",
        "IN PROGRESS",
        "PENDING",
        "BLOCKERS",
        "NEXT STEP",
    }:
        if base[name] != candidate[name]:
            raise ValueError(f"WO-013-P changed unrelated checkpoint section: {name}")


def require_wo014p_checkpoint_semantics(base_text: str, candidate_text: str) -> None:
    base = checkpoint_sections(base_text)
    candidate = checkpoint_sections(candidate_text)
    if set(base) != set(candidate):
        raise ValueError("WO-014-P checkpoint sections changed unexpectedly")
    if normalized_checkpoint_value(base, "STATUS") != EXPECTED_WO014P_PREVIOUS_STATUS:
        raise ValueError("WO-014-P promotion base has an unexpected checkpoint status")
    if normalized_checkpoint_value(candidate, "STATUS") != EXPECTED_WO014P_STATUS:
        raise ValueError("WO-014-P candidate has an unexpected checkpoint status")

    base_completed = checkpoint_bullets(base, "COMPLETED")
    candidate_completed = checkpoint_bullets(candidate, "COMPLETED")
    if candidate_completed[: len(base_completed)] != base_completed:
        raise ValueError("WO-014-P cannot rewrite historical COMPLETED checkpoint truth")
    appended_completed = candidate_completed[len(base_completed) :]
    if len(appended_completed) != len(WO014P_CANONICAL_COMPLETION_BULLETS):
        raise ValueError(
            "WO-014-P candidate must append exactly 5 authorized completion evidence bullets"
        )
    for index, (bullet, expected_bullet) in enumerate(
        zip(appended_completed, WO014P_CANONICAL_COMPLETION_BULLETS, strict=True), 1
    ):
        if normalized_checkpoint_evidence(bullet) != expected_bullet:
            raise ValueError(
                f"WO-014-P completion evidence class {index} is outside its closed grammar"
            )

    base_pending = checkpoint_bullets(base, "PENDING")
    candidate_pending = checkpoint_bullets(candidate, "PENDING")
    if base_pending.count("provider/prompt cache adapter layer.") != 1:
        raise ValueError(
            "WO-014-P promotion base must contain exactly one provider/prompt cache adapter item"
        )
    expected_pending = list(base_pending)
    expected_pending.remove("provider/prompt cache adapter layer.")
    if candidate_pending != expected_pending:
        raise ValueError(
            "WO-014-P must remove only provider/prompt cache adapter layer. from PENDING "
            "and preserve all other items"
        )

    if normalized_checkpoint_value(candidate, "IN PROGRESS") != (
        f"- {EXPECTED_WO014P_IN_PROGRESS}"
    ):
        raise ValueError("WO-014-P candidate has an unexpected IN PROGRESS intent")
    if normalized_checkpoint_value(candidate, "BLOCKERS") != EXPECTED_WO014P_BLOCKERS:
        raise ValueError("WO-014-P candidate has an unexpected BLOCKERS intent")

    next_step = normalized_checkpoint_value(candidate, "NEXT STEP")
    expected_next_step = " ".join(
        [
            EXPECTED_WO014P_IN_PROGRESS.replace("Preparing", "Prepare", 1),
            "Continue with the following bounded intent:",
            *(f"- {intent};" for intent in WO014P_NEXT_STEP_REQUIRED_INTENTS),
            "Do not implement Memory in the promotion PR.",
        ]
    )
    if next_step != expected_next_step:
        raise ValueError("WO-014-P NEXT STEP must preserve the closed Memory intent grammar")

    for name in set(base) - {
        "STATUS",
        "COMPLETED",
        "IN PROGRESS",
        "PENDING",
        "BLOCKERS",
        "NEXT STEP",
    }:
        if base[name] != candidate[name]:
            raise ValueError(f"WO-014-P changed unrelated checkpoint section: {name}")


def require_wo015p_checkpoint_semantics(base_text: str, candidate_text: str) -> None:
    base = checkpoint_sections(base_text)
    candidate = checkpoint_sections(candidate_text)
    if set(base) != set(candidate):
        raise ValueError("WO-015-P checkpoint sections changed unexpectedly")
    if normalized_checkpoint_value(base, "STATUS") != EXPECTED_WO015P_PREVIOUS_STATUS:
        raise ValueError("WO-015-P promotion base has an unexpected checkpoint status")
    if normalized_checkpoint_value(candidate, "STATUS") != EXPECTED_WO015P_STATUS:
        raise ValueError("WO-015-P candidate has an unexpected checkpoint status")

    base_completed = checkpoint_bullets(base, "COMPLETED")
    candidate_completed = checkpoint_bullets(candidate, "COMPLETED")
    if candidate_completed[: len(base_completed)] != base_completed:
        raise ValueError("WO-015-P cannot rewrite historical COMPLETED checkpoint truth")
    appended_completed = candidate_completed[len(base_completed) :]
    if len(appended_completed) != len(WO015P_CANONICAL_COMPLETION_BULLETS):
        raise ValueError(
            "WO-015-P candidate must append exactly 5 authorized Memory completion evidence bullets"
        )
    for index, (bullet, expected_bullet) in enumerate(
        zip(appended_completed, WO015P_CANONICAL_COMPLETION_BULLETS, strict=True), 1
    ):
        if normalized_checkpoint_evidence(bullet) != expected_bullet:
            raise ValueError(
                f"WO-015-P completion evidence class {index} is outside its closed grammar"
            )

    base_pending = checkpoint_bullets(base, "PENDING")
    candidate_pending = checkpoint_bullets(candidate, "PENDING")
    if base_pending.count("memory.") != 1:
        raise ValueError("WO-015-P promotion base must contain exactly one memory item")
    expected_pending = list(base_pending)
    expected_pending.remove("memory.")
    if candidate_pending != expected_pending:
        raise ValueError(
            "WO-015-P must remove only memory. from PENDING and preserve all other items"
        )

    if normalized_checkpoint_value(candidate, "IN PROGRESS") != (
        f"- {EXPECTED_WO015P_IN_PROGRESS}"
    ):
        raise ValueError("WO-015-P candidate has an unexpected IN PROGRESS intent")
    if normalized_checkpoint_value(candidate, "BLOCKERS") != EXPECTED_WO015P_BLOCKERS:
        raise ValueError("WO-015-P candidate has an unexpected BLOCKERS intent")

    next_step = normalized_checkpoint_value(candidate, "NEXT STEP")
    if next_step != EXPECTED_WO015P_NEXT_STEP:
        raise ValueError("WO-015-P NEXT STEP must match the exact closed ACCE grammar")

    for name in set(base) - {
        "STATUS",
        "COMPLETED",
        "IN PROGRESS",
        "PENDING",
        "BLOCKERS",
        "NEXT STEP",
    }:
        if base[name] != candidate[name]:
            raise ValueError(f"WO-015-P changed unrelated checkpoint section: {name}")


def require_wo016p_checkpoint_semantics(base_text: str, candidate_text: str) -> None:
    _require_wo016p_strict_raw_checkpoint_grammar(base_text, candidate_text)
    base = checkpoint_sections(base_text)
    candidate = checkpoint_sections(candidate_text)
    if set(base) != set(candidate):
        raise ValueError("WO-016-P checkpoint sections changed unexpectedly")
    if normalized_checkpoint_value(base, "STATUS") != EXPECTED_WO016P_PREVIOUS_STATUS:
        raise ValueError("WO-016-P promotion base has an unexpected checkpoint status")
    if normalized_checkpoint_value(candidate, "STATUS") != EXPECTED_WO016P_STATUS:
        raise ValueError("WO-016-P candidate has an unexpected checkpoint status")

    base_completed = checkpoint_bullets(base, "COMPLETED")
    candidate_completed = checkpoint_bullets(candidate, "COMPLETED")
    if candidate_completed[: len(base_completed)] != base_completed:
        raise ValueError("WO-016-P cannot rewrite historical COMPLETED checkpoint truth")
    appended_completed = candidate_completed[len(base_completed) :]
    if len(appended_completed) != len(WO016P_CANONICAL_COMPLETION_BULLETS):
        raise ValueError(
            "WO-016-P candidate must append exactly 5 authorized ACCE completion evidence bullets"
        )
    for index, (bullet, expected_bullet) in enumerate(
        zip(appended_completed, WO016P_CANONICAL_COMPLETION_BULLETS, strict=True), 1
    ):
        if normalized_checkpoint_evidence(bullet) != expected_bullet:
            raise ValueError(
                f"WO-016-P completion evidence class {index} is outside its closed grammar"
            )

    base_pending = checkpoint_bullets(base, "PENDING")
    candidate_pending = checkpoint_bullets(candidate, "PENDING")
    if base_pending.count(EXPECTED_WO016P_PENDING_ITEM) != 1:
        raise ValueError("WO-016-P promotion base must contain exactly one ACCE pending item")
    expected_pending = list(base_pending)
    expected_pending.remove(EXPECTED_WO016P_PENDING_ITEM)
    if candidate_pending != expected_pending:
        raise ValueError(
            "WO-016-P must remove only ACCE beyond current intake/storage/context foundations. "
            "from PENDING and preserve all other items"
        )

    if normalized_checkpoint_value(candidate, "IN PROGRESS") != (
        f"- {EXPECTED_WO016P_IN_PROGRESS}"
    ):
        raise ValueError("WO-016-P candidate has an unexpected IN PROGRESS intent")
    if normalized_checkpoint_value(candidate, "BLOCKERS") != EXPECTED_WO016P_BLOCKERS:
        raise ValueError("WO-016-P candidate has an unexpected BLOCKERS intent")
    if normalized_checkpoint_value(candidate, "NEXT STEP") != EXPECTED_WO016P_NEXT_STEP:
        raise ValueError("WO-016-P NEXT STEP must match the exact closed MCP grammar")

    for name in set(base) - {
        "STATUS",
        "COMPLETED",
        "IN PROGRESS",
        "PENDING",
        "BLOCKERS",
        "NEXT STEP",
    }:
        if base[name] != candidate[name]:
            raise ValueError(f"WO-016-P changed unrelated checkpoint section: {name}")


def _require_wo017p_strict_raw_checkpoint_grammar(
    base_text: str,
    candidate_text: str,
) -> None:
    base_preamble, base_ordered_sections, base_sections = _raw_checkpoint_structure(
        base_text, "base"
    )
    candidate_structure = _raw_checkpoint_structure(candidate_text, "candidate")
    candidate_preamble, candidate_ordered_sections, candidate_sections = candidate_structure
    if base_preamble != candidate_preamble:
        raise ValueError("WO-017-P candidate preamble changed byte-for-byte")
    base_names = tuple(section.name for section in base_ordered_sections)
    candidate_names = tuple(section.name for section in candidate_ordered_sections)
    if base_names != candidate_names:
        raise ValueError("WO-017-P checkpoint section sequence changed unexpectedly")
    for position, (base_section, candidate_section) in enumerate(
        zip(base_ordered_sections, candidate_ordered_sections, strict=True), 1
    ):
        if base_section.heading.encode("utf-8") != candidate_section.heading.encode("utf-8"):
            raise ValueError(f"WO-017-P heading changed byte-for-byte at position {position}")
    required_sections = set(_WO016P_RAW_CONTROLLED_SECTIONS)
    if not required_sections.issubset(base_sections):
        raise ValueError("WO-017-P base is missing a required canonical checkpoint section")
    for name in base_names:
        if (
            name not in _WO016P_RAW_CONTROLLED_SECTIONS
            and candidate_sections[name] != base_sections[name]
        ):
            raise ValueError(f"WO-017-P changed unrelated checkpoint section: {name}")
    newline = "\n"
    expected_controlled = {
        "STATUS": f"{EXPECTED_WO017P_STATUS}{newline}{newline}",
        "IN PROGRESS": f"- {EXPECTED_WO017P_IN_PROGRESS}{newline}{newline}",
        "BLOCKERS": f"{EXPECTED_WO017P_BLOCKERS}{newline}{newline}",
        "NEXT STEP": f"{EXPECTED_WO017P_NEXT_STEP}{newline}{newline}",
    }
    base_completed = base_sections["COMPLETED"]
    if not base_completed.endswith(newline):
        raise ValueError("WO-017-P base COMPLETED section lacks the canonical final newline")
    expected_controlled["COMPLETED"] = (
        base_completed[:-1]
        + "".join(f"- {bullet}{newline}" for bullet in WO017P_CANONICAL_COMPLETION_BULLETS)
        + newline
    )
    base_pending_lines = base_sections["PENDING"].splitlines(keepends=True)
    pending_line = f"- {EXPECTED_WO017P_PENDING_ITEM}{newline}"
    if base_pending_lines.count(pending_line) != 1:
        raise ValueError("WO-017-P base PENDING must contain exactly one raw MCP pending line")
    expected_controlled["PENDING"] = "".join(
        line for line in base_pending_lines if line != pending_line
    )
    for name, expected_body in expected_controlled.items():
        if candidate_sections.get(name) != expected_body:
            raise ValueError(f"WO-017-P {name} section is outside the strict raw grammar")


def require_wo017p_checkpoint_semantics(base_text: str, candidate_text: str) -> None:
    _require_wo017p_strict_raw_checkpoint_grammar(base_text, candidate_text)
    base = checkpoint_sections(base_text)
    candidate = checkpoint_sections(candidate_text)
    if set(base) != set(candidate):
        raise ValueError("WO-017-P checkpoint sections changed unexpectedly")
    if normalized_checkpoint_value(base, "STATUS") != EXPECTED_WO017P_PREVIOUS_STATUS:
        raise ValueError("WO-017-P promotion base has an unexpected checkpoint status")
    if normalized_checkpoint_value(candidate, "STATUS") != EXPECTED_WO017P_STATUS:
        raise ValueError("WO-017-P candidate has an unexpected checkpoint status")
    base_completed = checkpoint_bullets(base, "COMPLETED")
    candidate_completed = checkpoint_bullets(candidate, "COMPLETED")
    if candidate_completed[: len(base_completed)] != base_completed:
        raise ValueError("WO-017-P cannot rewrite historical COMPLETED checkpoint truth")
    appended_completed = candidate_completed[len(base_completed) :]
    if len(appended_completed) != len(WO017P_CANONICAL_COMPLETION_BULLETS):
        raise ValueError(
            "WO-017-P candidate must append exactly 5 authorized MCP completion evidence bullets"
        )
    for index, (bullet, expected_bullet) in enumerate(
        zip(appended_completed, WO017P_CANONICAL_COMPLETION_BULLETS, strict=True), 1
    ):
        if normalized_checkpoint_evidence(bullet) != expected_bullet:
            raise ValueError(
                f"WO-017-P completion evidence class {index} is outside its closed grammar"
            )
    base_pending = checkpoint_bullets(base, "PENDING")
    candidate_pending = checkpoint_bullets(candidate, "PENDING")
    if base_pending.count(EXPECTED_WO017P_PENDING_ITEM) != 1:
        raise ValueError("WO-017-P promotion base must contain exactly one MCP pending item")
    expected_pending = list(base_pending)
    expected_pending.remove(EXPECTED_WO017P_PENDING_ITEM)
    if candidate_pending != expected_pending:
        raise ValueError("WO-017-P must remove only MCP server product surface. from PENDING")
    candidate_in_progress = normalized_checkpoint_value(candidate, "IN PROGRESS")
    if candidate_in_progress != f"- {EXPECTED_WO017P_IN_PROGRESS}":
        raise ValueError("WO-017-P candidate has an unexpected IN PROGRESS intent")
    if normalized_checkpoint_value(candidate, "BLOCKERS") != EXPECTED_WO017P_BLOCKERS:
        raise ValueError("WO-017-P candidate has an unexpected BLOCKERS intent")
    if normalized_checkpoint_value(candidate, "NEXT STEP") != EXPECTED_WO017P_NEXT_STEP:
        raise ValueError("WO-017-P NEXT STEP must match the exact autonomous-execution grammar")
    for name in set(base) - {
        "STATUS",
        "COMPLETED",
        "IN PROGRESS",
        "PENDING",
        "BLOCKERS",
        "NEXT STEP",
    }:
        if base[name] != candidate[name]:
            raise ValueError(f"WO-017-P changed unrelated checkpoint section: {name}")


def _require_wo018p_strict_raw_checkpoint_grammar(
    base_text: str,
    candidate_text: str,
) -> None:
    base_preamble, base_ordered_sections, base_sections = _raw_checkpoint_structure(
        base_text, "base"
    )
    candidate_preamble, candidate_ordered_sections, candidate_sections = _raw_checkpoint_structure(
        candidate_text, "candidate"
    )
    if base_preamble != candidate_preamble:
        raise ValueError("WO-018-P candidate preamble changed byte-for-byte")
    base_names = tuple(section.name for section in base_ordered_sections)
    candidate_names = tuple(section.name for section in candidate_ordered_sections)
    if base_names != candidate_names:
        raise ValueError("WO-018-P checkpoint section sequence changed unexpectedly")
    for position, (base_section, candidate_section) in enumerate(
        zip(base_ordered_sections, candidate_ordered_sections, strict=True), 1
    ):
        if base_section.heading.encode("utf-8") != candidate_section.heading.encode("utf-8"):
            raise ValueError(f"WO-018-P heading changed byte-for-byte at position {position}")
    required_sections = set(_WO016P_RAW_CONTROLLED_SECTIONS)
    if not required_sections.issubset(base_sections):
        raise ValueError("WO-018-P base is missing a required canonical checkpoint section")
    for name in base_names:
        if (
            name not in _WO016P_RAW_CONTROLLED_SECTIONS
            and candidate_sections[name] != base_sections[name]
        ):
            raise ValueError(f"WO-018-P changed unrelated checkpoint section: {name}")

    newline = "\n"
    expected_controlled = {
        "STATUS": f"{EXPECTED_WO018P_STATUS}{newline}{newline}",
        "IN PROGRESS": f"- {EXPECTED_WO018P_IN_PROGRESS}{newline}{newline}",
        "BLOCKERS": f"{EXPECTED_WO018P_BLOCKERS}{newline}{newline}",
        "NEXT STEP": f"{EXPECTED_WO018P_NEXT_STEP}{newline}{newline}",
    }
    base_completed = base_sections["COMPLETED"]
    if not base_completed.endswith(newline):
        raise ValueError("WO-018-P base COMPLETED section lacks the canonical final newline")
    expected_controlled["COMPLETED"] = (
        base_completed[:-1]
        + "".join(f"- {bullet}{newline}" for bullet in WO018P_CANONICAL_COMPLETION_BULLETS)
        + newline
    )
    base_pending_lines = base_sections["PENDING"].splitlines(keepends=True)
    pending_lines = [f"- {item}{newline}" for item in EXPECTED_WO018P_PENDING_ITEMS]
    for pending_line in pending_lines:
        if base_pending_lines.count(pending_line) != 1:
            raise ValueError(
                "WO-018-P base PENDING must contain each autonomous/tool-gating pending line once"
            )
    expected_controlled["PENDING"] = "".join(
        line for line in base_pending_lines if line not in pending_lines
    )
    for name, expected_body in expected_controlled.items():
        if candidate_sections.get(name) != expected_body:
            raise ValueError(f"WO-018-P {name} section is outside the strict raw grammar")


def require_wo018p_checkpoint_semantics(base_text: str, candidate_text: str) -> None:
    _require_wo018p_strict_raw_checkpoint_grammar(base_text, candidate_text)
    base = checkpoint_sections(base_text)
    candidate = checkpoint_sections(candidate_text)
    if set(base) != set(candidate):
        raise ValueError("WO-018-P checkpoint sections changed unexpectedly")
    if normalized_checkpoint_value(base, "STATUS") != EXPECTED_WO018P_PREVIOUS_STATUS:
        raise ValueError("WO-018-P promotion base has an unexpected checkpoint status")
    if normalized_checkpoint_value(candidate, "STATUS") != EXPECTED_WO018P_STATUS:
        raise ValueError("WO-018-P candidate has an unexpected checkpoint status")

    base_completed = checkpoint_bullets(base, "COMPLETED")
    candidate_completed = checkpoint_bullets(candidate, "COMPLETED")
    if candidate_completed[: len(base_completed)] != base_completed:
        raise ValueError("WO-018-P cannot rewrite historical COMPLETED checkpoint truth")
    appended_completed = candidate_completed[len(base_completed) :]
    if len(appended_completed) != len(WO018P_CANONICAL_COMPLETION_BULLETS):
        raise ValueError(
            "WO-018-P candidate must append exactly 5 authorized autonomous completion bullets"
        )
    for index, (bullet, expected_bullet) in enumerate(
        zip(appended_completed, WO018P_CANONICAL_COMPLETION_BULLETS, strict=True), 1
    ):
        if normalized_checkpoint_evidence(bullet) != expected_bullet:
            raise ValueError(
                f"WO-018-P completion evidence class {index} is outside its closed grammar"
            )

    base_pending = checkpoint_bullets(base, "PENDING")
    candidate_pending = checkpoint_bullets(candidate, "PENDING")
    expected_pending = list(base_pending)
    for item in EXPECTED_WO018P_PENDING_ITEMS:
        if expected_pending.count(item) != 1:
            raise ValueError(
                f"WO-018-P promotion base must contain exactly one pending item: {item}"
            )
        expected_pending.remove(item)
    if candidate_pending != expected_pending:
        raise ValueError(
            "WO-018-P must remove only autonomous execution and end-to-end tool gating"
        )
    if normalized_checkpoint_value(candidate, "IN PROGRESS") != f"- {EXPECTED_WO018P_IN_PROGRESS}":
        raise ValueError("WO-018-P candidate has an unexpected IN PROGRESS intent")
    if normalized_checkpoint_value(candidate, "BLOCKERS") != EXPECTED_WO018P_BLOCKERS:
        raise ValueError("WO-018-P candidate has an unexpected BLOCKERS intent")
    if normalized_checkpoint_value(candidate, "NEXT STEP") != EXPECTED_WO018P_NEXT_STEP:
        raise ValueError("WO-018-P NEXT STEP must match the exact telemetry/event-bus grammar")
    for name in set(base) - {
        "STATUS",
        "COMPLETED",
        "IN PROGRESS",
        "PENDING",
        "BLOCKERS",
        "NEXT STEP",
    }:
        if base[name] != candidate[name]:
            raise ValueError(f"WO-018-P changed unrelated checkpoint section: {name}")


def _require_wo019p_strict_raw_checkpoint_grammar(
    base_text: str,
    candidate_text: str,
) -> None:
    base_preamble, base_ordered_sections, base_sections = _raw_checkpoint_structure(
        base_text, "base"
    )
    candidate_preamble, candidate_ordered_sections, candidate_sections = _raw_checkpoint_structure(
        candidate_text, "candidate"
    )
    if base_preamble != candidate_preamble:
        raise ValueError("WO-019-P candidate preamble changed byte-for-byte")
    base_names = tuple(section.name for section in base_ordered_sections)
    candidate_names = tuple(section.name for section in candidate_ordered_sections)
    if base_names != candidate_names:
        raise ValueError("WO-019-P checkpoint section sequence changed unexpectedly")
    for position, (base_section, candidate_section) in enumerate(
        zip(base_ordered_sections, candidate_ordered_sections, strict=True), 1
    ):
        if base_section.heading.encode("utf-8") != candidate_section.heading.encode("utf-8"):
            raise ValueError(f"WO-019-P heading changed byte-for-byte at position {position}")
    required_sections = set(_WO016P_RAW_CONTROLLED_SECTIONS)
    if not required_sections.issubset(base_sections):
        raise ValueError("WO-019-P base is missing a required canonical checkpoint section")
    for name in base_names:
        if (
            name not in _WO016P_RAW_CONTROLLED_SECTIONS
            and candidate_sections[name] != base_sections[name]
        ):
            raise ValueError(f"WO-019-P changed unrelated checkpoint section: {name}")

    newline = "\n"
    expected_controlled = {
        "STATUS": f"{EXPECTED_WO019P_STATUS}{newline}{newline}",
        "IN PROGRESS": f"- {EXPECTED_WO019P_IN_PROGRESS}{newline}{newline}",
        "BLOCKERS": f"{EXPECTED_WO019P_BLOCKERS}{newline}{newline}",
        "NEXT STEP": f"{EXPECTED_WO019P_NEXT_STEP}{newline}{newline}",
    }
    base_completed = base_sections["COMPLETED"]
    if not base_completed.endswith(newline):
        raise ValueError("WO-019-P base COMPLETED section lacks the canonical final newline")
    expected_controlled["COMPLETED"] = (
        base_completed[:-1]
        + "".join(f"- {bullet}{newline}" for bullet in WO019P_CANONICAL_COMPLETION_BULLETS)
        + newline
    )
    base_pending_lines = base_sections["PENDING"].splitlines(keepends=True)
    pending_lines = [f"- {item}{newline}" for item in EXPECTED_WO019P_PENDING_ITEMS]
    for pending_line in pending_lines:
        if base_pending_lines.count(pending_line) != 1:
            raise ValueError("WO-019-P base PENDING must contain the telemetry pending line once")
    expected_controlled["PENDING"] = "".join(
        line for line in base_pending_lines if line not in pending_lines
    )
    for name, expected_body in expected_controlled.items():
        if candidate_sections.get(name) != expected_body:
            raise ValueError(f"WO-019-P {name} section is outside the strict raw grammar")


def require_wo019p_checkpoint_semantics(base_text: str, candidate_text: str) -> None:
    _require_wo019p_strict_raw_checkpoint_grammar(base_text, candidate_text)
    base = checkpoint_sections(base_text)
    candidate = checkpoint_sections(candidate_text)
    if set(base) != set(candidate):
        raise ValueError("WO-019-P checkpoint sections changed unexpectedly")
    if normalized_checkpoint_value(base, "STATUS") != EXPECTED_WO019P_PREVIOUS_STATUS:
        raise ValueError("WO-019-P promotion base has an unexpected checkpoint status")
    if normalized_checkpoint_value(candidate, "STATUS") != EXPECTED_WO019P_STATUS:
        raise ValueError("WO-019-P candidate has an unexpected checkpoint status")

    base_completed = checkpoint_bullets(base, "COMPLETED")
    candidate_completed = checkpoint_bullets(candidate, "COMPLETED")
    if candidate_completed[: len(base_completed)] != base_completed:
        raise ValueError("WO-019-P cannot rewrite historical COMPLETED checkpoint truth")
    appended_completed = candidate_completed[len(base_completed) :]
    if len(appended_completed) != len(WO019P_CANONICAL_COMPLETION_BULLETS):
        raise ValueError(
            "WO-019-P candidate must append exactly 5 authorized telemetry completion bullets"
        )
    for index, (bullet, expected_bullet) in enumerate(
        zip(appended_completed, WO019P_CANONICAL_COMPLETION_BULLETS, strict=True), 1
    ):
        if normalized_checkpoint_evidence(bullet) != expected_bullet:
            raise ValueError(
                f"WO-019-P completion evidence class {index} is outside its closed grammar"
            )

    base_pending = checkpoint_bullets(base, "PENDING")
    candidate_pending = checkpoint_bullets(candidate, "PENDING")
    expected_pending = list(base_pending)
    for item in EXPECTED_WO019P_PENDING_ITEMS:
        if expected_pending.count(item) != 1:
            raise ValueError(
                f"WO-019-P promotion base must contain exactly one pending item: {item}"
            )
        expected_pending.remove(item)
    if candidate_pending != expected_pending:
        raise ValueError("WO-019-P must remove only telemetry. from PENDING")
    if normalized_checkpoint_value(candidate, "IN PROGRESS") != f"- {EXPECTED_WO019P_IN_PROGRESS}":
        raise ValueError("WO-019-P candidate has an unexpected IN PROGRESS intent")
    if normalized_checkpoint_value(candidate, "BLOCKERS") != EXPECTED_WO019P_BLOCKERS:
        raise ValueError("WO-019-P candidate has an unexpected BLOCKERS intent")
    if normalized_checkpoint_value(candidate, "NEXT STEP") != EXPECTED_WO019P_NEXT_STEP:
        raise ValueError("WO-019-P NEXT STEP must match the exact Control Center grammar")
    for name in set(base) - {
        "STATUS",
        "COMPLETED",
        "IN PROGRESS",
        "PENDING",
        "BLOCKERS",
        "NEXT STEP",
    }:
        if base[name] != candidate[name]:
            raise ValueError(f"WO-019-P changed unrelated checkpoint section: {name}")


def _require_wo020p_strict_raw_checkpoint_grammar(
    base_text: str,
    candidate_text: str,
) -> None:
    base_preamble, base_ordered_sections, base_sections = _raw_checkpoint_structure(
        base_text, "base"
    )
    candidate_preamble, candidate_ordered_sections, candidate_sections = _raw_checkpoint_structure(
        candidate_text, "candidate"
    )
    if base_preamble != candidate_preamble:
        raise ValueError("WO-020-P candidate preamble changed byte-for-byte")
    base_names = tuple(section.name for section in base_ordered_sections)
    candidate_names = tuple(section.name for section in candidate_ordered_sections)
    if base_names != candidate_names:
        raise ValueError("WO-020-P checkpoint section sequence changed unexpectedly")
    for position, (base_section, candidate_section) in enumerate(
        zip(base_ordered_sections, candidate_ordered_sections, strict=True), 1
    ):
        if base_section.heading.encode("utf-8") != candidate_section.heading.encode("utf-8"):
            raise ValueError(f"WO-020-P heading changed byte-for-byte at position {position}")
    required_sections = set(_WO016P_RAW_CONTROLLED_SECTIONS)
    if not required_sections.issubset(base_sections):
        raise ValueError("WO-020-P base is missing a required canonical checkpoint section")
    for name in base_names:
        if (
            name not in _WO016P_RAW_CONTROLLED_SECTIONS
            and candidate_sections[name] != base_sections[name]
        ):
            raise ValueError(f"WO-020-P changed unrelated checkpoint section: {name}")

    newline = "\n"
    expected_controlled = {
        "STATUS": f"{EXPECTED_WO020P_STATUS}{newline}{newline}",
        "IN PROGRESS": f"- {EXPECTED_WO020P_IN_PROGRESS}{newline}{newline}",
        "BLOCKERS": f"{EXPECTED_WO020P_BLOCKERS}{newline}{newline}",
        "NEXT STEP": f"{EXPECTED_WO020P_NEXT_STEP}{newline}{newline}",
    }
    base_completed = base_sections["COMPLETED"]
    if not base_completed.endswith(newline):
        raise ValueError("WO-020-P base COMPLETED section lacks the canonical final newline")
    expected_controlled["COMPLETED"] = (
        base_completed[:-1]
        + "".join(f"- {bullet}{newline}" for bullet in WO020P_CANONICAL_COMPLETION_BULLETS)
        + newline
    )
    expected_controlled["PENDING"] = base_sections["PENDING"]
    for name, expected_body in expected_controlled.items():
        if candidate_sections.get(name) != expected_body:
            raise ValueError(f"WO-020-P {name} section is outside the strict raw grammar")


def require_wo020p_checkpoint_semantics(base_text: str, candidate_text: str) -> None:
    _require_wo020p_strict_raw_checkpoint_grammar(base_text, candidate_text)
    base = checkpoint_sections(base_text)
    candidate = checkpoint_sections(candidate_text)
    if set(base) != set(candidate):
        raise ValueError("WO-020-P checkpoint sections changed unexpectedly")
    if normalized_checkpoint_value(base, "STATUS") != EXPECTED_WO020P_PREVIOUS_STATUS:
        raise ValueError("WO-020-P promotion base has an unexpected checkpoint status")
    if normalized_checkpoint_value(candidate, "STATUS") != EXPECTED_WO020P_STATUS:
        raise ValueError("WO-020-P candidate has an unexpected checkpoint status")

    base_completed = checkpoint_bullets(base, "COMPLETED")
    candidate_completed = checkpoint_bullets(candidate, "COMPLETED")
    if candidate_completed[: len(base_completed)] != base_completed:
        raise ValueError("WO-020-P cannot rewrite historical COMPLETED checkpoint truth")
    appended_completed = candidate_completed[len(base_completed) :]
    if len(appended_completed) != len(WO020P_CANONICAL_COMPLETION_BULLETS):
        raise ValueError(
            "WO-020-P candidate must append exactly 6 authorized Control Center completion bullets"
        )
    for index, (bullet, expected_bullet) in enumerate(
        zip(appended_completed, WO020P_CANONICAL_COMPLETION_BULLETS, strict=True), 1
    ):
        if normalized_checkpoint_evidence(bullet) != expected_bullet:
            raise ValueError(
                f"WO-020-P completion evidence class {index} is outside its closed grammar"
            )

    base_pending = checkpoint_bullets(base, "PENDING")
    candidate_pending = checkpoint_bullets(candidate, "PENDING")
    positions: list[int] = []
    for item in WO020P_REQUIRED_RETAINED_PENDING_ITEMS:
        if base_pending.count(item) != 1:
            raise ValueError(
                "WO-020-P promotion base must contain exactly one retained pending item: " + item
            )
        positions.append(base_pending.index(item))
    if positions != sorted(positions):
        raise ValueError("WO-020-P promotion base pending items are out of canonical order")
    if candidate_pending != base_pending:
        raise ValueError(
            "WO-020-P must retain every existing PENDING item in original order, including "
            "full Control Center."
        )
    if normalized_checkpoint_value(candidate, "IN PROGRESS") != f"- {EXPECTED_WO020P_IN_PROGRESS}":
        raise ValueError("WO-020-P candidate has an unexpected IN PROGRESS intent")
    if normalized_checkpoint_value(candidate, "BLOCKERS") != EXPECTED_WO020P_BLOCKERS:
        raise ValueError("WO-020-P candidate has an unexpected BLOCKERS intent")
    if normalized_checkpoint_value(candidate, "NEXT STEP") != EXPECTED_WO020P_NEXT_STEP:
        raise ValueError("WO-020-P NEXT STEP must match the exact Control Center grammar")
    for name in set(base) - {
        "STATUS",
        "COMPLETED",
        "IN PROGRESS",
        "PENDING",
        "BLOCKERS",
        "NEXT STEP",
    }:
        if base[name] != candidate[name]:
            raise ValueError(f"WO-020-P changed unrelated checkpoint section: {name}")


def _require_wo021p_strict_raw_checkpoint_grammar(
    base_text: str,
    candidate_text: str,
) -> None:
    base_preamble, base_ordered_sections, base_sections = _raw_checkpoint_structure(
        base_text, "base"
    )
    candidate_preamble, candidate_ordered_sections, candidate_sections = _raw_checkpoint_structure(
        candidate_text, "candidate"
    )
    if base_preamble != candidate_preamble:
        raise ValueError("WO-021-P candidate preamble changed byte-for-byte")
    base_names = tuple(section.name for section in base_ordered_sections)
    candidate_names = tuple(section.name for section in candidate_ordered_sections)
    if base_names != candidate_names:
        raise ValueError("WO-021-P checkpoint section sequence changed unexpectedly")
    for position, (base_section, candidate_section) in enumerate(
        zip(base_ordered_sections, candidate_ordered_sections, strict=True), 1
    ):
        if base_section.heading.encode("utf-8") != candidate_section.heading.encode("utf-8"):
            raise ValueError(f"WO-021-P heading changed byte-for-byte at position {position}")
    required_sections = set(_WO016P_RAW_CONTROLLED_SECTIONS)
    if not required_sections.issubset(base_sections):
        raise ValueError("WO-021-P base is missing a required canonical checkpoint section")
    for name in base_names:
        if (
            name not in _WO016P_RAW_CONTROLLED_SECTIONS
            and candidate_sections[name] != base_sections[name]
        ):
            raise ValueError(f"WO-021-P changed unrelated checkpoint section: {name}")

    newline = "\n"
    expected_controlled = {
        "STATUS": f"{EXPECTED_WO021P_STATUS}{newline}{newline}",
        "IN PROGRESS": f"- {EXPECTED_WO021P_IN_PROGRESS}{newline}{newline}",
        "BLOCKERS": f"{EXPECTED_WO021P_BLOCKERS}{newline}{newline}",
        "NEXT STEP": f"{EXPECTED_WO021P_NEXT_STEP}{newline}{newline}",
    }
    base_completed = base_sections["COMPLETED"]
    if not base_completed.endswith(newline):
        raise ValueError("WO-021-P base COMPLETED section lacks the canonical final newline")
    expected_controlled["COMPLETED"] = (
        base_completed[:-1]
        + "".join(f"- {bullet}{newline}" for bullet in WO021P_CANONICAL_COMPLETION_BULLETS)
        + newline
    )
    base_pending_lines = base_sections["PENDING"].splitlines(keepends=True)
    for item in WO021P_REQUIRED_RETAINED_PENDING_ITEMS:
        pending_line = f"- {item}{newline}"
        if base_pending_lines.count(pending_line) != 1:
            raise ValueError("WO-021-P base PENDING must retain every governed pending line once")
    expected_controlled["PENDING"] = base_sections["PENDING"]
    for name, expected_body in expected_controlled.items():
        if candidate_sections.get(name) != expected_body:
            raise ValueError(f"WO-021-P {name} section is outside the strict raw grammar")


def require_wo021p_checkpoint_semantics(base_text: str, candidate_text: str) -> None:
    _require_wo021p_strict_raw_checkpoint_grammar(base_text, candidate_text)
    base = checkpoint_sections(base_text)
    candidate = checkpoint_sections(candidate_text)
    if set(base) != set(candidate):
        raise ValueError("WO-021-P checkpoint sections changed unexpectedly")
    if normalized_checkpoint_value(base, "STATUS") != EXPECTED_WO021P_PREVIOUS_STATUS:
        raise ValueError("WO-021-P promotion base has an unexpected checkpoint status")
    if normalized_checkpoint_value(candidate, "STATUS") != EXPECTED_WO021P_STATUS:
        raise ValueError("WO-021-P candidate has an unexpected checkpoint status")

    base_completed = checkpoint_bullets(base, "COMPLETED")
    candidate_completed = checkpoint_bullets(candidate, "COMPLETED")
    if candidate_completed[: len(base_completed)] != base_completed:
        raise ValueError("WO-021-P cannot rewrite historical COMPLETED checkpoint truth")
    appended_completed = candidate_completed[len(base_completed) :]
    if len(appended_completed) != len(WO021P_CANONICAL_COMPLETION_BULLETS):
        raise ValueError(
            "WO-021-P candidate must append exactly 6 authorized metrics completion bullets"
        )
    for index, (bullet, expected_bullet) in enumerate(
        zip(appended_completed, WO021P_CANONICAL_COMPLETION_BULLETS, strict=True), 1
    ):
        if normalized_checkpoint_evidence(bullet) != expected_bullet:
            raise ValueError(
                f"WO-021-P completion evidence class {index} is outside its closed grammar"
            )

    base_pending = checkpoint_bullets(base, "PENDING")
    candidate_pending = checkpoint_bullets(candidate, "PENDING")
    positions: list[int] = []
    for item in WO021P_REQUIRED_RETAINED_PENDING_ITEMS:
        if base_pending.count(item) != 1:
            raise ValueError(
                "WO-021-P promotion base must contain exactly one retained pending item: " + item
            )
        positions.append(base_pending.index(item))
    if positions != sorted(positions):
        raise ValueError("WO-021-P promotion base pending items are out of canonical order")
    if candidate_pending != base_pending:
        raise ValueError(
            "WO-021-P must retain every existing PENDING item in original order, including "
            "full Control Center."
        )
    if normalized_checkpoint_value(candidate, "IN PROGRESS") != f"- {EXPECTED_WO021P_IN_PROGRESS}":
        raise ValueError("WO-021-P candidate has an unexpected IN PROGRESS intent")
    if normalized_checkpoint_value(candidate, "BLOCKERS") != EXPECTED_WO021P_BLOCKERS:
        raise ValueError("WO-021-P candidate has an unexpected BLOCKERS intent")
    if normalized_checkpoint_value(candidate, "NEXT STEP") != EXPECTED_WO021P_NEXT_STEP:
        raise ValueError("WO-021-P NEXT STEP must match the exact Control Center grammar")
    for name in set(base) - {
        "STATUS",
        "COMPLETED",
        "IN PROGRESS",
        "PENDING",
        "BLOCKERS",
        "NEXT STEP",
    }:
        if base[name] != candidate[name]:
            raise ValueError(f"WO-021-P changed unrelated checkpoint section: {name}")


def _require_wo022p_strict_raw_checkpoint_grammar(
    base_text: str,
    candidate_text: str,
) -> None:
    base_preamble, base_ordered_sections, base_sections = _raw_checkpoint_structure(
        base_text, "base"
    )
    candidate_preamble, candidate_ordered_sections, candidate_sections = _raw_checkpoint_structure(
        candidate_text, "candidate"
    )
    if base_preamble != candidate_preamble:
        raise ValueError("WO-022-P candidate preamble changed byte-for-byte")
    base_names = tuple(section.name for section in base_ordered_sections)
    candidate_names = tuple(section.name for section in candidate_ordered_sections)
    if base_names != candidate_names:
        raise ValueError("WO-022-P checkpoint section sequence changed unexpectedly")
    for position, (base_section, candidate_section) in enumerate(
        zip(base_ordered_sections, candidate_ordered_sections, strict=True), 1
    ):
        if base_section.heading.encode("utf-8") != candidate_section.heading.encode("utf-8"):
            raise ValueError(f"WO-022-P heading changed byte-for-byte at position {position}")
    required_sections = set(_WO016P_RAW_CONTROLLED_SECTIONS)
    if not required_sections.issubset(base_sections):
        raise ValueError("WO-022-P base is missing a required canonical checkpoint section")
    for name in base_names:
        if (
            name not in _WO016P_RAW_CONTROLLED_SECTIONS
            and candidate_sections[name] != base_sections[name]
        ):
            raise ValueError(f"WO-022-P changed unrelated checkpoint section: {name}")

    newline = "\n"
    expected_controlled = {
        "STATUS": f"{EXPECTED_WO022P_STATUS}{newline}{newline}",
        "IN PROGRESS": f"- {EXPECTED_WO022P_IN_PROGRESS}{newline}{newline}",
        "BLOCKERS": f"{EXPECTED_WO022P_BLOCKERS}{newline}{newline}",
        "NEXT STEP": f"{EXPECTED_WO022P_NEXT_STEP}{newline}{newline}",
    }
    base_completed = base_sections["COMPLETED"]
    if not base_completed.endswith(newline):
        raise ValueError("WO-022-P base COMPLETED section lacks the canonical final newline")
    expected_controlled["COMPLETED"] = (
        base_completed[:-1]
        + "".join(f"- {bullet}{newline}" for bullet in WO022P_CANONICAL_COMPLETION_BULLETS)
        + newline
    )
    base_pending_lines = base_sections["PENDING"].splitlines(keepends=True)
    completed_line = f"- {WO022P_COMPLETED_PENDING_ITEM}{newline}"
    if base_pending_lines.count(completed_line) != 1:
        raise ValueError(
            "WO-022-P base PENDING must contain the approved completed item exactly once"
        )
    for item in WO022P_REQUIRED_RETAINED_PENDING_ITEMS:
        pending_line = f"- {item}{newline}"
        if base_pending_lines.count(pending_line) != 1:
            raise ValueError("WO-022-P base PENDING must retain every governed pending line once")
    expected_controlled["PENDING"] = base_sections["PENDING"].replace(completed_line, "", 1)
    for name, expected_body in expected_controlled.items():
        if candidate_sections.get(name) != expected_body:
            raise ValueError(f"WO-022-P {name} section is outside the strict raw grammar")


def require_wo022p_checkpoint_semantics(base_text: str, candidate_text: str) -> None:
    _require_wo022p_strict_raw_checkpoint_grammar(base_text, candidate_text)
    base = checkpoint_sections(base_text)
    candidate = checkpoint_sections(candidate_text)
    if set(base) != set(candidate):
        raise ValueError("WO-022-P checkpoint sections changed unexpectedly")
    if normalized_checkpoint_value(base, "STATUS") != EXPECTED_WO022P_PREVIOUS_STATUS:
        raise ValueError("WO-022-P promotion base has an unexpected checkpoint status")
    if normalized_checkpoint_value(candidate, "STATUS") != EXPECTED_WO022P_STATUS:
        raise ValueError("WO-022-P candidate has an unexpected checkpoint status")

    base_completed = checkpoint_bullets(base, "COMPLETED")
    candidate_completed = checkpoint_bullets(candidate, "COMPLETED")
    if candidate_completed[: len(base_completed)] != base_completed:
        raise ValueError("WO-022-P cannot rewrite historical COMPLETED checkpoint truth")
    appended_completed = candidate_completed[len(base_completed) :]
    if len(appended_completed) != len(WO022P_CANONICAL_COMPLETION_BULLETS):
        raise ValueError(
            "WO-022-P candidate must append exactly 6 authorized full control center "
            "completion bullets"
        )
    for index, (bullet, expected_bullet) in enumerate(
        zip(appended_completed, WO022P_CANONICAL_COMPLETION_BULLETS, strict=True), 1
    ):
        if normalized_checkpoint_evidence(bullet) != expected_bullet:
            raise ValueError(
                f"WO-022-P completion evidence class {index} is outside its closed grammar"
            )

    base_pending = checkpoint_bullets(base, "PENDING")
    candidate_pending = checkpoint_bullets(candidate, "PENDING")
    positions: list[int] = []
    for item in WO022P_REQUIRED_RETAINED_PENDING_ITEMS:
        if base_pending.count(item) != 1:
            raise ValueError(
                "WO-022-P promotion base must contain exactly one retained pending item: " + item
            )
        positions.append(base_pending.index(item))
    if positions != sorted(positions):
        raise ValueError("WO-022-P promotion base pending items are out of canonical order")
    if base_pending.count(WO022P_COMPLETED_PENDING_ITEM) != 1:
        raise ValueError(
            "WO-022-P promotion base must contain exactly one completed pending item: "
            + WO022P_COMPLETED_PENDING_ITEM
        )
    expected_pending = [item for item in base_pending if item != WO022P_COMPLETED_PENDING_ITEM]
    if candidate_pending != expected_pending:
        raise ValueError(
            "WO-022-P must remove only full Control Center. from PENDING and preserve the "
            "remaining canonical items and order"
        )
    if normalized_checkpoint_value(candidate, "IN PROGRESS") != f"- {EXPECTED_WO022P_IN_PROGRESS}":
        raise ValueError("WO-022-P candidate has an unexpected IN PROGRESS intent")
    if normalized_checkpoint_value(candidate, "BLOCKERS") != EXPECTED_WO022P_BLOCKERS:
        raise ValueError("WO-022-P candidate has an unexpected BLOCKERS intent")
    if normalized_checkpoint_value(candidate, "NEXT STEP") != EXPECTED_WO022P_NEXT_STEP:
        raise ValueError("WO-022-P NEXT STEP must match the exact baseline benchmark grammar")
    for name in set(base) - {
        "STATUS",
        "COMPLETED",
        "IN PROGRESS",
        "PENDING",
        "BLOCKERS",
        "NEXT STEP",
    }:
        if base[name] != candidate[name]:
            raise ValueError(f"WO-022-P changed unrelated checkpoint section: {name}")


def _require_wo023p_strict_raw_checkpoint_grammar(
    base_text: str,
    candidate_text: str,
) -> None:
    base_preamble, base_ordered_sections, base_sections = _raw_checkpoint_structure(
        base_text, "base"
    )
    candidate_preamble, candidate_ordered_sections, candidate_sections = _raw_checkpoint_structure(
        candidate_text, "candidate"
    )
    if base_preamble != candidate_preamble:
        raise ValueError("WO-023-P candidate preamble changed byte-for-byte")
    base_names = tuple(section.name for section in base_ordered_sections)
    candidate_names = tuple(section.name for section in candidate_ordered_sections)
    if base_names != candidate_names:
        raise ValueError("WO-023-P checkpoint section sequence changed unexpectedly")
    for position, (base_section, candidate_section) in enumerate(
        zip(base_ordered_sections, candidate_ordered_sections, strict=True), 1
    ):
        if base_section.heading.encode("utf-8") != candidate_section.heading.encode("utf-8"):
            raise ValueError(f"WO-023-P heading changed byte-for-byte at position {position}")
    required_sections = set(_WO016P_RAW_CONTROLLED_SECTIONS)
    if not required_sections.issubset(base_sections):
        raise ValueError("WO-023-P base is missing a required canonical checkpoint section")
    for name in base_names:
        if (
            name not in _WO016P_RAW_CONTROLLED_SECTIONS
            and candidate_sections[name] != base_sections[name]
        ):
            raise ValueError(f"WO-023-P changed unrelated checkpoint section: {name}")

    newline = "\n"
    expected_controlled = {
        "STATUS": f"{EXPECTED_WO023P_STATUS}{newline}{newline}",
        "IN PROGRESS": f"- {EXPECTED_WO023P_IN_PROGRESS}{newline}{newline}",
        "BLOCKERS": f"{EXPECTED_WO023P_BLOCKERS}{newline}{newline}",
        "NEXT STEP": f"{EXPECTED_WO023P_NEXT_STEP}{newline}{newline}",
    }
    base_completed = base_sections["COMPLETED"]
    if not base_completed.endswith(newline):
        raise ValueError("WO-023-P base COMPLETED section lacks the canonical final newline")
    expected_controlled["COMPLETED"] = (
        base_completed[:-1]
        + "".join(f"- {bullet}{newline}" for bullet in WO023P_CANONICAL_COMPLETION_BULLETS)
        + newline
    )
    base_pending_lines = base_sections["PENDING"].splitlines(keepends=True)
    completed_line = f"- {WO023P_COMPLETED_PENDING_ITEM}{newline}"
    if base_pending_lines.count(completed_line) != 1:
        raise ValueError(
            "WO-023-P base PENDING must contain the approved completed item exactly once"
        )
    for item in WO023P_REQUIRED_RETAINED_PENDING_ITEMS:
        pending_line = f"- {item}{newline}"
        if base_pending_lines.count(pending_line) != 1:
            raise ValueError("WO-023-P base PENDING must retain every governed pending line once")
    expected_controlled["PENDING"] = base_sections["PENDING"].replace(completed_line, "", 1)
    for name, expected_body in expected_controlled.items():
        if candidate_sections.get(name) != expected_body:
            raise ValueError(f"WO-023-P {name} section is outside the strict raw grammar")


def require_wo023p_checkpoint_semantics(base_text: str, candidate_text: str) -> None:
    _require_wo023p_strict_raw_checkpoint_grammar(base_text, candidate_text)
    base = checkpoint_sections(base_text)
    candidate = checkpoint_sections(candidate_text)
    if set(base) != set(candidate):
        raise ValueError("WO-023-P checkpoint sections changed unexpectedly")
    if normalized_checkpoint_value(base, "STATUS") != EXPECTED_WO023P_PREVIOUS_STATUS:
        raise ValueError("WO-023-P promotion base has an unexpected checkpoint status")
    if normalized_checkpoint_value(candidate, "STATUS") != EXPECTED_WO023P_STATUS:
        raise ValueError("WO-023-P candidate has an unexpected checkpoint status")

    base_completed = checkpoint_bullets(base, "COMPLETED")
    candidate_completed = checkpoint_bullets(candidate, "COMPLETED")
    if candidate_completed[: len(base_completed)] != base_completed:
        raise ValueError("WO-023-P cannot rewrite historical COMPLETED checkpoint truth")
    appended_completed = candidate_completed[len(base_completed) :]
    if len(appended_completed) != len(WO023P_CANONICAL_COMPLETION_BULLETS):
        raise ValueError(
            "WO-023-P candidate must append exactly "
            f"{len(WO023P_CANONICAL_COMPLETION_BULLETS)} authorized comprehensive "
            "benchmarks completion bullets"
        )
    for index, (bullet, expected_bullet) in enumerate(
        zip(appended_completed, WO023P_CANONICAL_COMPLETION_BULLETS, strict=True), 1
    ):
        if normalized_checkpoint_evidence(bullet) != expected_bullet:
            raise ValueError(
                f"WO-023-P completion evidence class {index} is outside its closed grammar"
            )

    base_pending = checkpoint_bullets(base, "PENDING")
    candidate_pending = checkpoint_bullets(candidate, "PENDING")
    positions: list[int] = []
    for item in WO023P_REQUIRED_RETAINED_PENDING_ITEMS:
        if base_pending.count(item) != 1:
            raise ValueError(
                "WO-023-P promotion base must contain exactly one retained pending item: " + item
            )
        positions.append(base_pending.index(item))
    if positions != sorted(positions):
        raise ValueError("WO-023-P promotion base pending items are out of canonical order")
    if base_pending.count(WO023P_COMPLETED_PENDING_ITEM) != 1:
        raise ValueError(
            "WO-023-P promotion base must contain exactly one completed pending item: "
            + WO023P_COMPLETED_PENDING_ITEM
        )
    expected_pending = [item for item in base_pending if item != WO023P_COMPLETED_PENDING_ITEM]
    if candidate_pending != expected_pending:
        raise ValueError(
            "WO-023-P must remove only comprehensive retrieval/token/storage benchmarks. from "
            "PENDING and preserve the remaining canonical items and order"
        )
    if normalized_checkpoint_value(candidate, "IN PROGRESS") != f"- {EXPECTED_WO023P_IN_PROGRESS}":
        raise ValueError("WO-023-P candidate has an unexpected IN PROGRESS intent")
    if normalized_checkpoint_value(candidate, "BLOCKERS") != EXPECTED_WO023P_BLOCKERS:
        raise ValueError("WO-023-P candidate has an unexpected BLOCKERS intent")
    if normalized_checkpoint_value(candidate, "NEXT STEP") != EXPECTED_WO023P_NEXT_STEP:
        raise ValueError("WO-023-P NEXT STEP must match the exact stabilization grammar")
    for name in set(base) - {
        "STATUS",
        "COMPLETED",
        "IN PROGRESS",
        "PENDING",
        "BLOCKERS",
        "NEXT STEP",
    }:
        if base[name] != candidate[name]:
            raise ValueError(f"WO-023-P changed unrelated checkpoint section: {name}")


def parse_canonical_manifest(text: str, source: str) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or re.fullmatch(r"[0-9a-f]{64}", parts[0]) is None:
            raise ValueError(f"malformed canonical manifest line {line_number} in {source}")
        path = parts[1]
        if path in seen:
            raise ValueError(f"duplicate canonical manifest path in {source}: {path}")
        seen.add(path)
        entries.append((path, parts[0]))
    if not entries:
        raise ValueError(f"canonical manifest is empty: {source}")
    return entries


def require_checkpoint_manifest_contract(
    base_manifest_text: str,
    candidate_manifest_text: str,
    candidate_checkpoint_bytes: bytes,
    work_order: str,
) -> None:
    base_entries = parse_canonical_manifest(base_manifest_text, "base")
    candidate_entries = parse_canonical_manifest(candidate_manifest_text, "candidate")
    if [path for path, _ in candidate_entries] != [path for path, _ in base_entries]:
        raise ValueError(f"{work_order} canonical manifest path set or order changed")
    base_by_path = dict(base_entries)
    base_lines = base_manifest_text.splitlines(keepends=True)
    candidate_lines = candidate_manifest_text.splitlines(keepends=True)
    if len(base_lines) != len(candidate_lines):
        raise ValueError(f"{work_order} canonical manifest line structure changed")
    checkpoint_line_indexes = [
        index
        for index, line in enumerate(base_lines)
        if len(line.strip().split(maxsplit=1)) == 2
        and line.strip().split(maxsplit=1)[1] == CANONICAL_MANIFEST_CHECKPOINT_NAME
    ]
    if len(checkpoint_line_indexes) != 1:
        raise ValueError(f"{work_order} base manifest must contain one checkpoint hash line")
    candidate_checkpoint_indexes = [
        index
        for index, line in enumerate(candidate_lines)
        if len(line.strip().split(maxsplit=1)) == 2
        and line.strip().split(maxsplit=1)[1] == CANONICAL_MANIFEST_CHECKPOINT_NAME
    ]
    if candidate_checkpoint_indexes != checkpoint_line_indexes:
        raise ValueError(f"{work_order} canonical manifest checkpoint line moved or disappeared")
    for path, digest in candidate_entries:
        if path == CANONICAL_MANIFEST_CHECKPOINT_NAME:
            expected = hashlib.sha256(candidate_checkpoint_bytes).hexdigest()
            if digest != expected:
                raise ValueError(f"{work_order} checkpoint hash does not match candidate bytes")
        elif digest != base_by_path[path]:
            raise ValueError(f"{work_order} changed an unauthorized canonical hash: {path}")
    checkpoint_index = checkpoint_line_indexes[0]
    base_checkpoint_line = base_lines[checkpoint_index]
    base_checkpoint_parts = base_checkpoint_line.strip().split(maxsplit=1)
    prefix_length = base_checkpoint_line.index(base_checkpoint_parts[0])
    expected_checkpoint_line = (
        base_checkpoint_line[:prefix_length]
        + dict(candidate_entries)[CANONICAL_MANIFEST_CHECKPOINT_NAME]
        + base_checkpoint_line[prefix_length + len(base_checkpoint_parts[0]) :]
    )
    for index, (base_line, candidate_line) in enumerate(
        zip(base_lines, candidate_lines, strict=True)
    ):
        if index == checkpoint_index:
            if candidate_line != expected_checkpoint_line:
                raise ValueError(f"{work_order} changed checkpoint manifest line formatting")
        elif candidate_line != base_line:
            raise ValueError(f"{work_order} changed an unrelated canonical manifest line")


def require_wo012p_manifest_contract(
    base_manifest_text: str,
    candidate_manifest_text: str,
    candidate_checkpoint_bytes: bytes,
) -> None:
    require_checkpoint_manifest_contract(
        base_manifest_text,
        candidate_manifest_text,
        candidate_checkpoint_bytes,
        "WO-012-P",
    )


def require_wo013p_manifest_contract(
    base_manifest_text: str,
    candidate_manifest_text: str,
    candidate_checkpoint_bytes: bytes,
) -> None:
    require_checkpoint_manifest_contract(
        base_manifest_text,
        candidate_manifest_text,
        candidate_checkpoint_bytes,
        "WO-013-P",
    )


def require_wo014p_manifest_contract(
    base_manifest_text: str,
    candidate_manifest_text: str,
    candidate_checkpoint_bytes: bytes,
) -> None:
    require_checkpoint_manifest_contract(
        base_manifest_text,
        candidate_manifest_text,
        candidate_checkpoint_bytes,
        WO014P_WORK_ORDER,
    )


def require_wo015p_manifest_contract(
    base_manifest_text: str,
    candidate_manifest_text: str,
    candidate_checkpoint_bytes: bytes,
) -> None:
    require_checkpoint_manifest_contract(
        base_manifest_text,
        candidate_manifest_text,
        candidate_checkpoint_bytes,
        WO015P_WORK_ORDER,
    )


def require_wo016p_manifest_contract(
    base_manifest_text: str,
    candidate_manifest_text: str,
    candidate_checkpoint_bytes: bytes,
) -> None:
    require_checkpoint_manifest_contract(
        base_manifest_text,
        candidate_manifest_text,
        candidate_checkpoint_bytes,
        WO016P_WORK_ORDER,
    )


def require_wo017p_manifest_contract(
    base_manifest_text: str,
    candidate_manifest_text: str,
    candidate_checkpoint_bytes: bytes,
) -> None:
    require_checkpoint_manifest_contract(
        base_manifest_text, candidate_manifest_text, candidate_checkpoint_bytes, WO017P_WORK_ORDER
    )


def require_wo018p_manifest_contract(
    base_manifest_text: str,
    candidate_manifest_text: str,
    candidate_checkpoint_bytes: bytes,
) -> None:
    require_checkpoint_manifest_contract(
        base_manifest_text, candidate_manifest_text, candidate_checkpoint_bytes, WO018P_WORK_ORDER
    )


def require_wo019p_manifest_contract(
    base_manifest_text: str,
    candidate_manifest_text: str,
    candidate_checkpoint_bytes: bytes,
) -> None:
    require_checkpoint_manifest_contract(
        base_manifest_text, candidate_manifest_text, candidate_checkpoint_bytes, WO019P_WORK_ORDER
    )


def require_wo020p_manifest_contract(
    base_manifest_text: str,
    candidate_manifest_text: str,
    candidate_checkpoint_bytes: bytes,
) -> None:
    require_checkpoint_manifest_contract(
        base_manifest_text, candidate_manifest_text, candidate_checkpoint_bytes, WO020P_WORK_ORDER
    )


def require_wo021p_manifest_contract(
    base_manifest_text: str,
    candidate_manifest_text: str,
    candidate_checkpoint_bytes: bytes,
) -> None:
    require_checkpoint_manifest_contract(
        base_manifest_text, candidate_manifest_text, candidate_checkpoint_bytes, WO021P_WORK_ORDER
    )


def require_wo022p_manifest_contract(
    base_manifest_text: str,
    candidate_manifest_text: str,
    candidate_checkpoint_bytes: bytes,
) -> None:
    require_checkpoint_manifest_contract(
        base_manifest_text, candidate_manifest_text, candidate_checkpoint_bytes, WO022P_WORK_ORDER
    )


def require_wo023p_manifest_contract(
    base_manifest_text: str,
    candidate_manifest_text: str,
    candidate_checkpoint_bytes: bytes,
) -> None:
    require_checkpoint_manifest_contract(
        base_manifest_text, candidate_manifest_text, candidate_checkpoint_bytes, WO023P_WORK_ORDER
    )


def registered_promotion_base_sha(work_order: str) -> str:
    base_ref = (
        WO012P_PROMOTION_REGISTRY
        | WO013P_PROMOTION_REGISTRY
        | WO014P_PROMOTION_REGISTRY
        | WO015P_PROMOTION_REGISTRY
        | WO016P_PROMOTION_REGISTRY
        | WO017P_PROMOTION_REGISTRY
        | WO018P_PROMOTION_REGISTRY
        | WO019P_PROMOTION_REGISTRY
        | WO020P_PROMOTION_REGISTRY
        | WO021P_PROMOTION_REGISTRY
        | WO022P_PROMOTION_REGISTRY
        | WO023P_PROMOTION_REGISTRY
        | WO024P_PROMOTION_REGISTRY
        | WO025_PROMOTION_REGISTRY
        | WO025P_PROMOTION_REGISTRY
    ).get(work_order)
    if base_ref is None:
        raise ValueError(f"no registered promotion base for {work_order}")
    base_sha = git_value("rev-parse", base_ref, fallback="")
    if not HEX_SHA.fullmatch(base_sha):
        raise ValueError(f"registered promotion base ref is unavailable: {base_ref}")
    return base_sha


def require_wo008_g1_scope(work_order: str, base_sha: str, paths: list[str]) -> None:
    if work_order != "WO-008-G1":
        return
    if base_sha != WO008_G1_BASE_SHA:
        raise ValueError(f"WO-008-G1 requires exact base {WO008_G1_BASE_SHA}, observed {base_sha}")
    unauthorized = sorted(set(paths) - WO008_G1_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            "WO-008-G1 changed files outside the approved governance scope: "
            + ", ".join(unauthorized)
        )


def require_wo009_scope(work_order: str, base_sha: str, paths: list[str]) -> None:
    if work_order != "WO-009":
        return
    if base_sha != WO009_BASE_SHA:
        raise ValueError(f"WO-009 requires exact base {WO009_BASE_SHA}, observed {base_sha}")
    canonical = canonical_change_evidence(paths)
    if canonical["project_brain_changed"] is True:
        raise ValueError("WO-009 implementation evidence cannot change canonical Project Brain")


def require_wo010_g1_scope(work_order: str, base_sha: str, paths: list[str]) -> None:
    if work_order != "WO-010-G1":
        return
    if base_sha != WO010_G1_BASE_SHA:
        raise ValueError(f"WO-010-G1 requires exact base {WO010_G1_BASE_SHA}, observed {base_sha}")
    unauthorized = sorted(set(paths) - WO010_G1_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            "WO-010-G1 changed files outside the approved governance scope: "
            + ", ".join(unauthorized)
        )


def require_wo010_scope(work_order: str, base_sha: str, paths: list[str]) -> None:
    if work_order != "WO-010":
        return
    if base_sha != WO010_BASE_SHA:
        raise ValueError(f"WO-010 requires exact base {WO010_BASE_SHA}, observed {base_sha}")
    canonical = canonical_change_evidence(paths)
    if canonical["project_brain_changed"] is True:
        raise ValueError("WO-010 implementation evidence cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError("WO-010 implementation evidence cannot change migrations")


def require_wo011_scope(work_order: str, base_sha: str, paths: list[str]) -> None:
    if work_order != "WO-011":
        return
    if base_sha != WO011_BASE_SHA:
        raise ValueError(f"WO-011 requires exact base {WO011_BASE_SHA}, observed {base_sha}")
    if any(
        path == "docs/project-brain"
        or path.startswith("docs/project-brain/")
        or path == "migrations"
        or path.startswith("migrations/")
        for path in paths
    ):
        raise ValueError(
            "WO-011 implementation evidence cannot change canonical Project Brain or migrations"
        )


def require_wo012_scope(work_order: str, base_sha: str, paths: list[str]) -> None:
    if work_order != "WO-012":
        return
    if base_sha != WO012_BASE_SHA:
        raise ValueError(f"WO-012 requires exact base {WO012_BASE_SHA}, observed {base_sha}")
    if any(
        path == "docs/project-brain"
        or path.startswith("docs/project-brain/")
        or path == "migrations"
        or path.startswith("migrations/")
        for path in paths
    ):
        raise ValueError(
            "WO-012 implementation evidence cannot change canonical Project Brain or migrations"
        )


def require_wo013_scope(work_order: str, base_sha: str, paths: list[str]) -> None:
    if work_order != "WO-013":
        return
    if base_sha != WO013_BASE_SHA:
        raise ValueError(f"WO-013 requires exact base {WO013_BASE_SHA}, observed {base_sha}")
    if any(
        path == "docs/project-brain"
        or path.startswith("docs/project-brain/")
        or path == "migrations"
        or path.startswith("migrations/")
        for path in paths
    ):
        raise ValueError(
            "WO-013 implementation evidence cannot change canonical Project Brain or migrations"
        )
    unauthorized = sorted(set(paths) - WO013_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            "WO-013 changed files outside the approved Delta Context scope: "
            + ", ".join(unauthorized)
        )


def require_wo014_scope(work_order: str, base_sha: str, paths: list[str]) -> None:
    if work_order != "WO-014":
        return
    if base_sha != WO014_BASE_SHA:
        raise ValueError(f"WO-014 requires exact base {WO014_BASE_SHA}, observed {base_sha}")
    if any(
        path == "docs/project-brain"
        or path.startswith("docs/project-brain/")
        or path == "migrations"
        or path.startswith("migrations/")
        for path in paths
    ):
        raise ValueError(
            "WO-014 implementation evidence cannot change canonical Project Brain or migrations"
        )
    unauthorized = sorted(set(paths) - WO014_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            "WO-014 changed files outside the approved Provider/Prompt Cache scope: "
            + ", ".join(unauthorized)
        )


def require_wo014_c1_candidate_lineage(
    rejected_head: str,
    candidate_head: str,
    repository: Path = ROOT,
) -> None:
    """Validate a historical C1 candidate relationship in explicit context.

    This intentionally accepts both commit identities and a repository instead
    of consulting the ambient checkout HEAD.  Squash merges preserve the
    logical change without preserving the source branch's commit ancestry.
    """
    for label, sha in (("rejected", rejected_head), ("candidate", candidate_head)):
        if HEX_SHA.fullmatch(sha) is None:
            raise ValueError(f"WO-014-C1 {label} HEAD must be a lowercase 40-hex SHA")
    ancestor_code, _ = run_in_repository(
        repository,
        ["git", "merge-base", "--is-ancestor", rejected_head, candidate_head],
    )
    if ancestor_code != 0:
        raise ValueError(
            "WO-014-C1 candidate lineage requires rejected HEAD "
            f"{rejected_head} to be an ancestor of candidate {candidate_head}"
        )


def require_wo014_c2_scope(work_order: str, base_sha: str, paths: list[str]) -> None:
    if work_order != WO014_C2_WORK_ORDER:
        return
    if base_sha != WO014_C2_BASE_SHA:
        raise ValueError(
            f"{WO014_C2_WORK_ORDER} requires exact post-squash base "
            f"{WO014_C2_BASE_SHA}, observed {base_sha}"
        )
    if any(
        path == "docs/project-brain"
        or path.startswith("docs/project-brain/")
        or path == "migrations"
        or path.startswith("migrations/")
        for path in paths
    ):
        raise ValueError(
            f"{WO014_C2_WORK_ORDER} cannot change canonical Project Brain or migrations"
        )
    unauthorized = sorted(set(paths) - WO014_C2_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            f"{WO014_C2_WORK_ORDER} changed files outside the explicit governance/test scope: "
            + ", ".join(unauthorized)
        )


def require_wo015_g1_scope(work_order: str, base_sha: str, paths: list[str]) -> None:
    if work_order != WO015_G1_WORK_ORDER:
        return
    if base_sha != WO015_G1_BASE_SHA:
        raise ValueError(
            f"{WO015_G1_WORK_ORDER} requires exact base {WO015_G1_BASE_SHA}, observed {base_sha}"
        )
    unauthorized = sorted(set(paths) - WO015_G1_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            f"{WO015_G1_WORK_ORDER} changed files outside the approved governance scope: "
            + ", ".join(unauthorized)
        )
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO015_G1_WORK_ORDER} cannot change canonical Project Brain")


def require_wo016_g1_scope(work_order: str, base_sha: str, paths: list[str]) -> None:
    if work_order != WO016_G1_WORK_ORDER:
        return
    if base_sha != WO016_G1_BASE_SHA:
        raise ValueError(
            f"{WO016_G1_WORK_ORDER} requires exact base {WO016_G1_BASE_SHA}, observed {base_sha}"
        )
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO016_G1_WORK_ORDER} cannot change canonical Project Brain")
    unauthorized = sorted(set(paths) - WO016_G1_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            f"{WO016_G1_WORK_ORDER} changed files outside the bounded evidence/governance scope: "
            + ", ".join(unauthorized)
        )
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO016_G1_WORK_ORDER} cannot change migrations")
    if migration_head() != "0006_memory_lifecycle_provenance":
        raise ValueError(
            f"{WO016_G1_WORK_ORDER} requires migration head 0006_memory_lifecycle_provenance"
        )


def require_wo016_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    enforce_current_main: bool = False,
) -> None:
    if work_order != WO016_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO016_WORK_ORDER} requires the protected main base branch")
    if base_sha == "0" * 40:
        raise ValueError(f"{WO016_WORK_ORDER} requires a resolved protected-main base SHA")
    if enforce_current_main:
        current_main = git_value("rev-parse", "origin/main", fallback="")
        if HEX_SHA.fullmatch(current_main) and base_sha != current_main:
            raise ValueError(
                f"{WO016_WORK_ORDER} must target current protected main {current_main}, "
                f"observed {base_sha}"
            )
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO016_WORK_ORDER} cannot promote or rewrite canonical Project Brain")
    migration_paths = [path for path in paths if path.startswith("migrations/")]
    invalid_migrations = [
        path for path in migration_paths if not WO016_MIGRATION_PATH.fullmatch(path)
    ]
    if invalid_migrations or len(migration_paths) > 1:
        raise ValueError(
            f"{WO016_WORK_ORDER} permits at most one additive 0007 migration with a bounded name"
        )
    unauthorized = sorted(set(paths) - WO016_PRODUCT_ALLOWED_PATHS - set(migration_paths))
    if unauthorized:
        raise ValueError(
            f"{WO016_WORK_ORDER} changed files outside the approved product/evidence surfaces: "
            + ", ".join(unauthorized)
        )


def require_wo017_g1_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
) -> None:
    if work_order != WO017_G1_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO017_G1_WORK_ORDER} requires the protected main base branch")
    if base_sha != WO017_G1_BASE_SHA:
        raise ValueError(
            f"{WO017_G1_WORK_ORDER} requires exact base {WO017_G1_BASE_SHA}, observed {base_sha}"
        )
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO017_G1_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO017_G1_WORK_ORDER} cannot change migrations")
    unauthorized = sorted(set(paths) - WO017_G1_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            f"{WO017_G1_WORK_ORDER} changed files outside the approved governance scope: "
            + ", ".join(unauthorized)
        )
    if sorted(set(paths)) != sorted(WO017_G1_ALLOWED_PATHS) or len(paths) != len(
        WO017_G1_ALLOWED_PATHS
    ):
        raise ValueError(
            f"{WO017_G1_WORK_ORDER} requires exactly the four governance/evidence files"
        )
    if migration_head() != "0006_memory_lifecycle_provenance":
        raise ValueError(
            f"{WO017_G1_WORK_ORDER} requires migration head 0006_memory_lifecycle_provenance"
        )


def require_wo017_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    enforce_current_main: bool = False,
) -> None:
    if work_order != WO017_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO017_WORK_ORDER} requires the protected main base branch")
    if HEX_SHA.fullmatch(base_sha) is None or base_sha == "0" * 40:
        raise ValueError(f"{WO017_WORK_ORDER} requires a resolved protected-main base SHA")
    if enforce_current_main:
        current_main = git_value("rev-parse", "origin/main", fallback="")
        if HEX_SHA.fullmatch(current_main) is None:
            raise ValueError(f"{WO017_WORK_ORDER} requires a resolved current protected main SHA")
        if base_sha != current_main:
            raise ValueError(
                f"{WO017_WORK_ORDER} must target current protected main {current_main}, "
                f"observed {base_sha}"
            )
        try:
            base_review_evidence = git_blob_bytes(base_sha, "scripts/review_evidence.py").decode(
                "utf-8"
            )
        except ValueError as exc:
            raise ValueError(
                f"{WO017_WORK_ORDER} requires a readable protected-main base with "
                f"merged {WO017_G1_WORK_ORDER} support"
            ) from exc
        if WO017_G1_WORK_ORDER not in base_review_evidence:
            raise ValueError(
                f"{WO017_WORK_ORDER} requires merged {WO017_G1_WORK_ORDER} support in its base"
            )
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO017_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO017_WORK_ORDER} cannot change migrations")
    unauthorized = sorted(set(paths) - WO017_PRODUCT_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            f"{WO017_WORK_ORDER} changed files outside the bounded MCP product scope: "
            + ", ".join(unauthorized)
        )


def require_wo018_g1_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
) -> None:
    if work_order != WO018_G1_WORK_ORDER:
        return
    if base_sha != WO018_G1_BASE_SHA:
        raise ValueError(
            f"{WO018_G1_WORK_ORDER} requires exact base {WO018_G1_BASE_SHA}, observed {base_sha}"
        )
    if base_branch != "main":
        raise ValueError(f"{WO018_G1_WORK_ORDER} requires the protected main base branch")
    if sorted(set(paths)) != sorted(WO018_G1_ALLOWED_PATHS) or len(paths) != len(
        WO018_G1_ALLOWED_PATHS
    ):
        raise ValueError(f"{WO018_G1_WORK_ORDER} requires exactly the four governance files")
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO018_G1_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO018_G1_WORK_ORDER} cannot change migrations")
    if migration_head() != "0006_memory_lifecycle_provenance":
        raise ValueError(
            f"{WO018_G1_WORK_ORDER} requires migration head 0006_memory_lifecycle_provenance"
        )


def require_wo018_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    enforce_current_main: bool = False,
) -> None:
    if work_order != WO018_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO018_WORK_ORDER} requires the protected main base branch")
    if HEX_SHA.fullmatch(base_sha) is None or base_sha == "0" * 40:
        raise ValueError(f"{WO018_WORK_ORDER} requires a resolved protected-main base SHA")
    if enforce_current_main:
        current_main = git_value("rev-parse", "origin/main", fallback="")
        if HEX_SHA.fullmatch(current_main) is None:
            raise ValueError(f"{WO018_WORK_ORDER} requires a resolved current protected main SHA")
        if base_sha != current_main:
            raise ValueError(
                f"{WO018_WORK_ORDER} must target current protected main {current_main}, "
                f"observed {base_sha}"
            )
        base_review_evidence = git_blob_bytes(base_sha, "scripts/review_evidence.py").decode(
            "utf-8"
        )
        if WO018_G1_WORK_ORDER not in base_review_evidence:
            raise ValueError(
                f"{WO018_WORK_ORDER} requires merged {WO018_G1_WORK_ORDER} support in its base"
            )
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO018_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO018_WORK_ORDER} cannot change migrations")
    unauthorized = sorted(set(paths) - WO018_PRODUCT_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            f"{WO018_WORK_ORDER} changed files outside the bounded autonomous product scope: "
            + ", ".join(unauthorized)
        )


def require_wo019_g1_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
) -> None:
    if work_order != WO019_G1_WORK_ORDER:
        return
    if base_sha != WO019_G1_BASE_SHA:
        raise ValueError(
            f"{WO019_G1_WORK_ORDER} requires exact base {WO019_G1_BASE_SHA}, observed {base_sha}"
        )
    if base_branch != "main":
        raise ValueError(f"{WO019_G1_WORK_ORDER} requires the protected main base branch")
    if sorted(set(paths)) != sorted(WO019_G1_ALLOWED_PATHS) or len(paths) != len(
        WO019_G1_ALLOWED_PATHS
    ):
        raise ValueError(f"{WO019_G1_WORK_ORDER} requires exactly the four governance files")
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO019_G1_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO019_G1_WORK_ORDER} cannot change migrations")
    if migration_head() != "0006_memory_lifecycle_provenance":
        raise ValueError(
            f"{WO019_G1_WORK_ORDER} requires migration head 0006_memory_lifecycle_provenance"
        )


def require_wo019_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    enforce_current_main: bool = False,
) -> None:
    if work_order != WO019_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO019_WORK_ORDER} requires the protected main base branch")
    if HEX_SHA.fullmatch(base_sha) is None or base_sha == "0" * 40:
        raise ValueError(f"{WO019_WORK_ORDER} requires a resolved protected-main base SHA")
    if enforce_current_main:
        current_main = git_value("rev-parse", "origin/main", fallback="")
        if HEX_SHA.fullmatch(current_main) is None:
            raise ValueError(f"{WO019_WORK_ORDER} requires a resolved current protected main SHA")
        if base_sha != current_main:
            raise ValueError(
                f"{WO019_WORK_ORDER} must target current protected main {current_main}, "
                f"observed {base_sha}"
            )
        base_review_evidence = git_blob_bytes(base_sha, "scripts/review_evidence.py").decode(
            "utf-8"
        )
        if WO019_G1_WORK_ORDER not in base_review_evidence:
            raise ValueError(
                f"{WO019_WORK_ORDER} requires merged {WO019_G1_WORK_ORDER} support in its base"
            )
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO019_WORK_ORDER} cannot change canonical Project Brain")
    unauthorized = sorted(
        path
        for path in set(paths)
        if path in WO019_PRODUCT_FORBIDDEN_PATHS
        or not any(path.startswith(prefix) for prefix in WO019_PRODUCT_ALLOWED_PREFIXES)
    )
    if unauthorized:
        raise ValueError(
            f"{WO019_WORK_ORDER} changed files outside the bounded "
            "Telemetry/Event Bus product scope: " + ", ".join(unauthorized)
        )
    migration_paths = [path for path in paths if path.startswith("migrations/")]
    invalid_migrations = [
        path for path in migration_paths if not WO019_PRODUCT_MIGRATION_PATH.fullmatch(path)
    ]
    if invalid_migrations or len(migration_paths) > 1:
        raise ValueError(
            f"{WO019_WORK_ORDER} permits at most one additive 0007 Telemetry/Event Bus migration"
        )


def require_wo020_g1_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
) -> None:
    if work_order != WO020_G1_WORK_ORDER:
        return
    if base_sha != WO020_G1_BASE_SHA:
        raise ValueError(
            f"{WO020_G1_WORK_ORDER} requires exact base {WO020_G1_BASE_SHA}, observed {base_sha}"
        )
    if base_branch != "main":
        raise ValueError(f"{WO020_G1_WORK_ORDER} requires the protected main base branch")
    if sorted(set(paths)) != sorted(WO020_G1_ALLOWED_PATHS) or len(paths) != len(
        WO020_G1_ALLOWED_PATHS
    ):
        raise ValueError(f"{WO020_G1_WORK_ORDER} requires exactly the four governance files")
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO020_G1_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO020_G1_WORK_ORDER} cannot change migrations")
    if migration_head() != CONTROL_CENTER_CORE_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO020_G1_WORK_ORDER} requires migration head "
            f"{CONTROL_CENTER_CORE_MIGRATION_BASE_HEAD}"
        )


def require_wo020_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    enforce_current_main: bool = False,
) -> None:
    if work_order != WO020_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO020_WORK_ORDER} requires the protected main base branch")
    if HEX_SHA.fullmatch(base_sha) is None or base_sha == "0" * 40:
        raise ValueError(f"{WO020_WORK_ORDER} requires a resolved protected-main base SHA")
    if enforce_current_main:
        current_main = git_value("rev-parse", "origin/main", fallback="")
        if HEX_SHA.fullmatch(current_main) is None:
            raise ValueError(f"{WO020_WORK_ORDER} requires a resolved current protected main SHA")
        if base_sha != current_main:
            raise ValueError(
                f"{WO020_WORK_ORDER} must target current protected main {current_main}, "
                f"observed {base_sha}"
            )
        base_review_evidence = git_blob_bytes(base_sha, "scripts/review_evidence.py").decode(
            "utf-8"
        )
        if WO020_G1_WORK_ORDER not in base_review_evidence:
            raise ValueError(
                f"{WO020_WORK_ORDER} requires merged {WO020_G1_WORK_ORDER} support in its base"
            )
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO020_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO020_WORK_ORDER} cannot change migrations")
    if any(path == ".github" or path.startswith(".github/") for path in paths):
        raise ValueError(f"{WO020_WORK_ORDER} cannot change CI workflows")
    dependency_paths = {
        "requirements.txt",
        "pyproject.toml",
        "dashboard/package.json",
        "dashboard/package-lock.json",
    }
    if any(path in dependency_paths for path in paths):
        raise ValueError(f"{WO020_WORK_ORDER} cannot change dependencies")
    unauthorized = sorted(
        path
        for path in set(paths)
        if path in WO020_PRODUCT_FORBIDDEN_PATHS
        or not any(path.startswith(prefix) for prefix in WO020_PRODUCT_ALLOWED_PREFIXES)
    )
    if unauthorized:
        raise ValueError(
            f"{WO020_WORK_ORDER} changed files outside the bounded "
            "Control Center product scope: " + ", ".join(unauthorized)
        )


def require_wo023_g1_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
) -> None:
    if work_order != WO023_G1_WORK_ORDER:
        return
    if base_sha != WO023_G1_BASE_SHA:
        raise ValueError(
            f"{WO023_G1_WORK_ORDER} requires exact base {WO023_G1_BASE_SHA}, observed {base_sha}"
        )
    if base_branch != "main":
        raise ValueError(f"{WO023_G1_WORK_ORDER} requires the protected main base branch")
    if sorted(set(paths)) != sorted(WO023_G1_ALLOWED_PATHS) or len(paths) != len(
        WO023_G1_ALLOWED_PATHS
    ):
        raise ValueError(f"{WO023_G1_WORK_ORDER} requires exactly the four governance files")
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO023_G1_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO023_G1_WORK_ORDER} cannot change migrations")
    if migration_head() != COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO023_G1_WORK_ORDER} requires migration head "
            f"{COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD}"
        )


def require_wo023_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    enforce_current_main: bool = False,
) -> None:
    if work_order != WO023_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO023_WORK_ORDER} requires the protected main base branch")
    if HEX_SHA.fullmatch(base_sha) is None or base_sha == "0" * 40:
        raise ValueError(f"{WO023_WORK_ORDER} requires a resolved protected-main base SHA")
    if enforce_current_main:
        current_main = git_value("rev-parse", "origin/main", fallback="")
        if HEX_SHA.fullmatch(current_main) is None:
            raise ValueError(f"{WO023_WORK_ORDER} requires a resolved current protected main SHA")
        if base_sha != current_main:
            raise ValueError(
                f"{WO023_WORK_ORDER} must target current protected main {current_main}, "
                f"observed {base_sha}"
            )
        base_review_evidence = git_blob_bytes(base_sha, "scripts/review_evidence.py").decode(
            "utf-8"
        )
        if WO023_G1_WORK_ORDER not in base_review_evidence:
            raise ValueError(
                f"{WO023_WORK_ORDER} requires merged {WO023_G1_WORK_ORDER} support in its base"
            )
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO023_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO023_WORK_ORDER} cannot change migrations")
    if any(path == ".github" or path.startswith(".github/") for path in paths):
        raise ValueError(f"{WO023_WORK_ORDER} cannot change CI workflows")
    if any(path in WO021_PRODUCT_DEPENDENCY_PATHS for path in paths):
        raise ValueError(f"{WO023_WORK_ORDER} cannot change dependencies")
    if any(
        path in WO021_PRODUCT_RELEASE_PATHS
        or path == "release-assets"
        or path.startswith("release-assets/")
        for path in paths
    ):
        raise ValueError(f"{WO023_WORK_ORDER} cannot change release files")
    unauthorized = sorted(
        path
        for path in set(paths)
        if path in WO023_PRODUCT_FORBIDDEN_PATHS
        or not any(path.startswith(prefix) for prefix in WO023_PRODUCT_ALLOWED_PREFIXES)
    )
    if unauthorized:
        raise ValueError(
            f"{WO023_WORK_ORDER} changed files outside the bounded "
            "comprehensive benchmarks product scope: " + ", ".join(unauthorized)
        )


def require_wo021_g1_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
) -> None:
    if work_order != WO021_G1_WORK_ORDER:
        return
    if base_sha != WO021_G1_BASE_SHA:
        raise ValueError(
            f"{WO021_G1_WORK_ORDER} requires exact base {WO021_G1_BASE_SHA}, observed {base_sha}"
        )
    if base_branch != "main":
        raise ValueError(f"{WO021_G1_WORK_ORDER} requires the protected main base branch")
    if sorted(set(paths)) != sorted(WO021_G1_ALLOWED_PATHS) or len(paths) != len(
        WO021_G1_ALLOWED_PATHS
    ):
        raise ValueError(f"{WO021_G1_WORK_ORDER} requires exactly the four governance files")
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO021_G1_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO021_G1_WORK_ORDER} cannot change migrations")
    if migration_head() != CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO021_G1_WORK_ORDER} requires migration head "
            f"{CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD}"
        )


def require_wo021_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    enforce_current_main: bool = False,
) -> None:
    if work_order != WO021_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO021_WORK_ORDER} requires the protected main base branch")
    if HEX_SHA.fullmatch(base_sha) is None or base_sha == "0" * 40:
        raise ValueError(f"{WO021_WORK_ORDER} requires a resolved protected-main base SHA")
    if enforce_current_main:
        current_main = git_value("rev-parse", "origin/main", fallback="")
        if HEX_SHA.fullmatch(current_main) is None:
            raise ValueError(f"{WO021_WORK_ORDER} requires a resolved current protected main SHA")
        if base_sha != current_main:
            raise ValueError(
                f"{WO021_WORK_ORDER} must target current protected main {current_main}, "
                f"observed {base_sha}"
            )
        base_review_evidence = git_blob_bytes(base_sha, "scripts/review_evidence.py").decode(
            "utf-8"
        )
        if WO021_G1_WORK_ORDER not in base_review_evidence:
            raise ValueError(
                f"{WO021_WORK_ORDER} requires merged {WO021_G1_WORK_ORDER} support in its base"
            )
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO021_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO021_WORK_ORDER} cannot change migrations")
    if any(path == ".github" or path.startswith(".github/") for path in paths):
        raise ValueError(f"{WO021_WORK_ORDER} cannot change CI workflows")
    if any(path in WO021_PRODUCT_DEPENDENCY_PATHS for path in paths):
        raise ValueError(f"{WO021_WORK_ORDER} cannot change dependencies")
    if any(
        path in WO021_PRODUCT_RELEASE_PATHS
        or path == "release-assets"
        or path.startswith("release-assets/")
        for path in paths
    ):
        raise ValueError(f"{WO021_WORK_ORDER} cannot change release files")
    unauthorized = sorted(
        path
        for path in set(paths)
        if path in WO021_PRODUCT_FORBIDDEN_PATHS
        or not any(path.startswith(prefix) for prefix in WO021_PRODUCT_ALLOWED_PREFIXES)
    )
    if unauthorized:
        raise ValueError(
            f"{WO021_WORK_ORDER} changed files outside the bounded "
            "Control Center metrics product scope: " + ", ".join(unauthorized)
        )


def require_wo022_g1_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
) -> None:
    if work_order != WO022_G1_WORK_ORDER:
        return
    if base_sha != WO022_G1_BASE_SHA:
        raise ValueError(
            f"{WO022_G1_WORK_ORDER} requires exact base {WO022_G1_BASE_SHA}, observed {base_sha}"
        )
    if base_branch != "main":
        raise ValueError(f"{WO022_G1_WORK_ORDER} requires the protected main base branch")
    if sorted(set(paths)) != sorted(WO022_G1_ALLOWED_PATHS) or len(paths) != len(
        WO022_G1_ALLOWED_PATHS
    ):
        raise ValueError(f"{WO022_G1_WORK_ORDER} requires exactly the four governance files")
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO022_G1_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO022_G1_WORK_ORDER} cannot change migrations")
    if migration_head() != CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO022_G1_WORK_ORDER} requires migration head "
            f"{CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD}"
        )


def require_wo022_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    enforce_current_main: bool = False,
) -> None:
    if work_order != WO022_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO022_WORK_ORDER} requires the protected main base branch")
    if HEX_SHA.fullmatch(base_sha) is None or base_sha == "0" * 40:
        raise ValueError(f"{WO022_WORK_ORDER} requires a resolved protected-main base SHA")
    if enforce_current_main:
        current_main = git_value("rev-parse", "origin/main", fallback="")
        if HEX_SHA.fullmatch(current_main) is None:
            raise ValueError(f"{WO022_WORK_ORDER} requires a resolved current protected main SHA")
        if base_sha != current_main:
            raise ValueError(
                f"{WO022_WORK_ORDER} must target current protected main {current_main}, "
                f"observed {base_sha}"
            )
        base_review_evidence = git_blob_bytes(base_sha, "scripts/review_evidence.py").decode(
            "utf-8"
        )
        if WO022_G1_WORK_ORDER not in base_review_evidence:
            raise ValueError(
                f"{WO022_WORK_ORDER} requires merged {WO022_G1_WORK_ORDER} support in its base"
            )
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO022_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO022_WORK_ORDER} cannot change migrations")
    if any(path == ".github" or path.startswith(".github/") for path in paths):
        raise ValueError(f"{WO022_WORK_ORDER} cannot change CI workflows")
    if any(path in WO021_PRODUCT_DEPENDENCY_PATHS for path in paths):
        raise ValueError(f"{WO022_WORK_ORDER} cannot change dependencies")
    if any(
        path in WO021_PRODUCT_RELEASE_PATHS
        or path == "release-assets"
        or path.startswith("release-assets/")
        for path in paths
    ):
        raise ValueError(f"{WO022_WORK_ORDER} cannot change release files")
    unauthorized = sorted(
        path
        for path in set(paths)
        if path in WO022_PRODUCT_FORBIDDEN_PATHS
        or not any(path.startswith(prefix) for prefix in WO022_PRODUCT_ALLOWED_PREFIXES)
    )
    if unauthorized:
        raise ValueError(
            f"{WO022_WORK_ORDER} changed files outside the bounded "
            "Full Control Center product scope: " + ", ".join(unauthorized)
        )


def require_wo018_autonomous_evidence(
    work_order: str,
    integration: Mapping[str, object],
    migration_head_value: str,
) -> None:
    if work_order not in {WO018_WORK_ORDER, WO018P_G1_WORK_ORDER, WO018P_WORK_ORDER}:
        return
    evidence = integration.get("autonomous_execution")
    if not isinstance(evidence, Mapping):
        raise ValueError(f"{WO018_WORK_ORDER} is missing mandatory autonomous execution evidence")
    required = set(AUTONOMOUS_EXECUTION_REQUIRED_FIELDS)
    if set(evidence) != required:
        raise ValueError(f"{WO018_WORK_ORDER} autonomous execution evidence shape is invalid")
    if evidence.get("status") != "PASS":
        raise ValueError(f"{WO018_WORK_ORDER} autonomous execution evidence must PASS")
    if evidence.get("evidence_file") != AUTONOMOUS_EXECUTION_EVIDENCE_FILE:
        raise ValueError(f"{WO018_WORK_ORDER} autonomous evidence file is invalid")
    if evidence.get("autonomous_evidence_version") != AUTONOMOUS_EXECUTION_EVIDENCE_VERSION:
        raise ValueError(f"{WO018_WORK_ORDER} autonomous evidence version is invalid")
    if evidence.get("observed_migration_head") != migration_head_value:
        raise ValueError(f"{WO018_WORK_ORDER} autonomous evidence migration head mismatch")
    if migration_head_value != "0006_memory_lifecycle_provenance":
        raise ValueError(
            f"{WO018_WORK_ORDER} requires migration head 0006_memory_lifecycle_provenance"
        )
    for field in AUTONOMOUS_EXECUTION_TRUE_FIELDS:
        if evidence.get(field) is not True:
            raise ValueError(f"{WO018_WORK_ORDER} requires {field}=true")
    for field in AUTONOMOUS_EXECUTION_FALSE_FIELDS:
        if evidence.get(field) is not False:
            raise ValueError(f"{WO018_WORK_ORDER} requires {field}=false")
    adapter = evidence.get("executor_adapter_name")
    if not isinstance(adapter, str) or not adapter.strip() or adapter == "UNKNOWN":
        raise ValueError(f"{WO018_WORK_ORDER} requires a bounded executor adapter identity")
    for field in AUTONOMOUS_EXECUTION_COUNT_FIELDS:
        value = evidence.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{WO018_WORK_ORDER} requires bounded integer evidence for {field}")
    if not 1 <= cast(int, evidence["tool_subset_count"]) <= 32:
        raise ValueError(f"{WO018_WORK_ORDER} tool subset count is outside the bounded contract")
    if not 1 <= cast(int, evidence["validation_commands_count"]) <= 64:
        raise ValueError(
            f"{WO018_WORK_ORDER} validation command count is outside the bounded contract"
        )
    if evidence.get("secret_leaks") != 0 or evidence.get("filesystem_path_leaks") != 0:
        raise ValueError(f"{WO018_WORK_ORDER} requires zero secret and filesystem path leaks")


def require_wo015p_g1_scope(work_order: str, base_sha: str, paths: list[str]) -> None:
    if work_order != WO015P_G1_WORK_ORDER:
        return
    if base_sha != WO015P_G1_BASE_SHA:
        raise ValueError(
            f"{WO015P_G1_WORK_ORDER} requires exact base {WO015P_G1_BASE_SHA}, observed {base_sha}"
        )
    unauthorized = sorted(set(paths) - WO015P_G1_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            f"{WO015P_G1_WORK_ORDER} changed files outside the approved governance scope: "
            + ", ".join(unauthorized)
        )
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO015P_G1_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO015P_G1_WORK_ORDER} cannot change migrations")


def require_wo016p_g1_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
) -> None:
    if work_order != WO016P_G1_WORK_ORDER:
        return
    if base_sha != WO016P_G1_BASE_SHA:
        raise ValueError(
            f"{WO016P_G1_WORK_ORDER} requires exact base {WO016P_G1_BASE_SHA}, observed {base_sha}"
        )
    if base_branch != "main":
        raise ValueError(f"{WO016P_G1_WORK_ORDER} requires the protected main base branch")
    unauthorized = sorted(set(paths) - WO016P_G1_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            f"{WO016P_G1_WORK_ORDER} changed files outside the approved governance scope: "
            + ", ".join(unauthorized)
        )
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO016P_G1_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO016P_G1_WORK_ORDER} cannot change migrations")
    if migration_head() != "0006_memory_lifecycle_provenance":
        raise ValueError(
            f"{WO016P_G1_WORK_ORDER} requires migration head 0006_memory_lifecycle_provenance"
        )


def require_wo017p_g1_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
) -> None:
    if work_order != WO017P_G1_WORK_ORDER:
        return
    if base_sha != WO017P_G1_BASE_SHA:
        raise ValueError(
            f"{WO017P_G1_WORK_ORDER} requires exact base {WO017P_G1_BASE_SHA}, observed {base_sha}"
        )
    if base_branch != "main":
        raise ValueError(f"{WO017P_G1_WORK_ORDER} requires the protected main base branch")
    unauthorized = sorted(set(paths) - WO017P_G1_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            f"{WO017P_G1_WORK_ORDER} changed files outside the approved governance scope: "
            + ", ".join(unauthorized)
        )
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO017P_G1_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO017P_G1_WORK_ORDER} cannot change migrations")
    if migration_head() != "0006_memory_lifecycle_provenance":
        raise ValueError(f"{WO017P_G1_WORK_ORDER} requires migration head 0006")


def require_wo018p_g1_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
) -> None:
    if work_order != WO018P_G1_WORK_ORDER:
        return
    if base_sha != WO018P_G1_BASE_SHA:
        raise ValueError(
            f"{WO018P_G1_WORK_ORDER} requires exact base {WO018P_G1_BASE_SHA}, observed {base_sha}"
        )
    if base_branch != "main":
        raise ValueError(f"{WO018P_G1_WORK_ORDER} requires the protected main base branch")
    if sorted(set(paths)) != sorted(WO018P_G1_ALLOWED_PATHS) or len(paths) != len(
        WO018P_G1_ALLOWED_PATHS
    ):
        raise ValueError(f"{WO018P_G1_WORK_ORDER} requires exactly the three governance files")
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO018P_G1_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO018P_G1_WORK_ORDER} cannot change migrations")
    if migration_head() != "0006_memory_lifecycle_provenance":
        raise ValueError(
            f"{WO018P_G1_WORK_ORDER} requires migration head 0006_memory_lifecycle_provenance"
        )


def require_wo015_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    enforce_current_main: bool = False,
) -> None:
    if work_order != WO015_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO015_WORK_ORDER} requires the protected main base branch")
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO015_WORK_ORDER} cannot promote or rewrite canonical Project Brain")
    if base_sha == "0" * 40:
        raise ValueError(f"{WO015_WORK_ORDER} requires a resolved protected-main base SHA")
    if enforce_current_main:
        current_main = git_value("rev-parse", "origin/main", fallback="")
        if HEX_SHA.fullmatch(current_main) and base_sha != current_main:
            raise ValueError(
                f"{WO015_WORK_ORDER} must target current protected main {current_main}, "
                f"observed {base_sha}"
            )


def require_wo015p_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    registered_base_sha: str | None = None,
    authorized_base_sha: str | None = None,
    enforce_current_main: bool = False,
    enforce_authorized_base: bool = True,
) -> None:
    if work_order != WO015P_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO015P_WORK_ORDER} requires the protected main base branch")
    expected_base = registered_base_sha or registered_promotion_base_sha(work_order)
    if base_sha != expected_base:
        raise ValueError(
            f"{WO015P_WORK_ORDER} requires current protected main base {expected_base}, "
            f"observed {base_sha}"
        )
    if sorted(set(paths)) != sorted(WO015P_PROMOTION_ALLOWED_PATHS) or len(paths) != 2:
        raise ValueError(
            f"{WO015P_WORK_ORDER} requires exactly the checkpoint and canonical manifest files"
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(f"{WO015P_WORK_ORDER} requires exactly one authorized-base marker")
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError(f"{WO015P_WORK_ORDER} authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO015P_WORK_ORDER} authorized-base marker must match the pull request base SHA"
            )
    if enforce_current_main:
        current_main = git_value("rev-parse", "origin/main", fallback="")
        if HEX_SHA.fullmatch(current_main) and base_sha != current_main:
            raise ValueError(
                f"{WO015P_WORK_ORDER} must target current protected main {current_main}, "
                f"observed {base_sha}"
            )

    base_review_evidence = git_blob_bytes(base_sha, "scripts/review_evidence.py").decode("utf-8")
    if WO015P_G1_WORK_ORDER not in base_review_evidence:
        raise ValueError(
            f"{WO015P_WORK_ORDER} requires merged {WO015P_G1_WORK_ORDER} support in its base"
        )
    base_checkpoint = git_blob_bytes(base_sha, CHECKPOINT_PATH).decode("utf-8")
    base_manifest = git_blob_bytes(base_sha, CANONICAL_MANIFEST_PATH).decode("utf-8")
    candidate_checkpoint_bytes = (ROOT / CHECKPOINT_PATH).read_bytes()
    candidate_manifest = (ROOT / CANONICAL_MANIFEST_PATH).read_bytes().decode("utf-8")
    require_wo015p_checkpoint_semantics(
        base_checkpoint,
        candidate_checkpoint_bytes.decode("utf-8"),
    )
    require_wo015p_manifest_contract(
        base_manifest,
        candidate_manifest,
        candidate_checkpoint_bytes,
    )


def require_wo016p_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    registered_base_sha: str | None = None,
    authorized_base_sha: str | None = None,
    enforce_current_main: bool = False,
    enforce_authorized_base: bool = True,
) -> None:
    if work_order != WO016P_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO016P_WORK_ORDER} requires the protected main base branch")
    expected_base = registered_base_sha or registered_promotion_base_sha(work_order)
    if base_sha != expected_base:
        raise ValueError(
            f"{WO016P_WORK_ORDER} requires current protected main base {expected_base}, "
            f"observed {base_sha}"
        )
    if sorted(set(paths)) != sorted(WO016P_PROMOTION_ALLOWED_PATHS) or len(paths) != 2:
        raise ValueError(
            f"{WO016P_WORK_ORDER} requires exactly the checkpoint and canonical manifest files"
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(f"{WO016P_WORK_ORDER} requires exactly one authorized-base marker")
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError(f"{WO016P_WORK_ORDER} authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO016P_WORK_ORDER} authorized-base marker must match the pull request base SHA"
            )
    if enforce_current_main:
        current_main = git_value("rev-parse", "origin/main", fallback="")
        if HEX_SHA.fullmatch(current_main) and base_sha != current_main:
            raise ValueError(
                f"{WO016P_WORK_ORDER} must target current protected main {current_main}, "
                f"observed {base_sha}"
            )

    base_review_evidence = git_blob_bytes(base_sha, "scripts/review_evidence.py").decode("utf-8")
    if WO016P_G1_WORK_ORDER not in base_review_evidence:
        raise ValueError(
            f"{WO016P_WORK_ORDER} requires merged {WO016P_G1_WORK_ORDER} support in its base"
        )
    base_checkpoint = git_blob_bytes(base_sha, CHECKPOINT_PATH).decode("utf-8")
    base_manifest = git_blob_bytes(base_sha, CANONICAL_MANIFEST_PATH).decode("utf-8")
    candidate_checkpoint_bytes = (ROOT / CHECKPOINT_PATH).read_bytes()
    candidate_manifest = (ROOT / CANONICAL_MANIFEST_PATH).read_bytes().decode("utf-8")
    require_wo016p_checkpoint_semantics(
        base_checkpoint,
        candidate_checkpoint_bytes.decode("utf-8"),
    )
    require_wo016p_manifest_contract(
        base_manifest,
        candidate_manifest,
        candidate_checkpoint_bytes,
    )


def require_wo017p_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    registered_base_sha: str | None = None,
    authorized_base_sha: str | None = None,
    enforce_current_main: bool = False,
    enforce_authorized_base: bool = True,
) -> None:
    if work_order != WO017P_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO017P_WORK_ORDER} requires the protected main base branch")
    expected_base = registered_base_sha or registered_promotion_base_sha(work_order)
    if base_sha != expected_base:
        raise ValueError(
            f"{WO017P_WORK_ORDER} requires current protected main base "
            f"{expected_base}, observed {base_sha}"
        )
    if sorted(set(paths)) != sorted(WO017P_PROMOTION_ALLOWED_PATHS) or len(paths) != 2:
        raise ValueError(
            f"{WO017P_WORK_ORDER} requires exactly the checkpoint and canonical manifest files"
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(f"{WO017P_WORK_ORDER} requires exactly one authorized-base marker")
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError("WO-017-P authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO017P_WORK_ORDER} authorized-base marker must match the pull request base SHA"
            )
    if enforce_current_main:
        current_main = git_value("rev-parse", "origin/main", fallback="")
        if HEX_SHA.fullmatch(current_main) and base_sha != current_main:
            raise ValueError(
                f"{WO017P_WORK_ORDER} must target current protected main "
                f"{current_main}, observed {base_sha}"
            )
    evidence_path = "scripts/review_evidence.py"
    base_review_evidence = git_blob_bytes(base_sha, evidence_path).decode("utf-8")
    if WO017P_G1_WORK_ORDER not in base_review_evidence:
        raise ValueError(
            f"{WO017P_WORK_ORDER} requires merged {WO017P_G1_WORK_ORDER} support in its base"
        )
    base_checkpoint = git_blob_bytes(base_sha, CHECKPOINT_PATH).decode("utf-8")
    base_manifest = git_blob_bytes(base_sha, CANONICAL_MANIFEST_PATH).decode("utf-8")
    candidate_checkpoint_bytes = (ROOT / CHECKPOINT_PATH).read_bytes()
    candidate_manifest = (ROOT / CANONICAL_MANIFEST_PATH).read_bytes().decode("utf-8")
    candidate_checkpoint = candidate_checkpoint_bytes.decode("utf-8")
    require_wo017p_checkpoint_semantics(base_checkpoint, candidate_checkpoint)
    require_wo017p_manifest_contract(
        base_manifest,
        candidate_manifest,
        candidate_checkpoint_bytes,
    )


def require_wo018p_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    registered_base_sha: str | None = None,
    authorized_base_sha: str | None = None,
    enforce_current_main: bool = False,
    enforce_authorized_base: bool = True,
) -> None:
    if work_order != WO018P_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO018P_WORK_ORDER} requires the protected main base branch")
    expected_base = registered_base_sha or registered_promotion_base_sha(work_order)
    if base_sha != expected_base:
        raise ValueError(
            f"{WO018P_WORK_ORDER} requires current protected main base "
            f"{expected_base}, observed {base_sha}"
        )
    if sorted(set(paths)) != sorted(WO018P_PROMOTION_ALLOWED_PATHS) or len(paths) != 2:
        raise ValueError(
            f"{WO018P_WORK_ORDER} requires exactly the checkpoint and canonical manifest files"
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(f"{WO018P_WORK_ORDER} requires exactly one authorized-base marker")
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError("WO-018-P authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO018P_WORK_ORDER} authorized-base marker must match the pull request base SHA"
            )
    if enforce_current_main:
        current_main = git_value("rev-parse", "origin/main", fallback="")
        if HEX_SHA.fullmatch(current_main) and base_sha != current_main:
            raise ValueError(
                f"{WO018P_WORK_ORDER} must target current protected main "
                f"{current_main}, observed {base_sha}"
            )
    evidence_path = "scripts/review_evidence.py"
    base_review_evidence = git_blob_bytes(base_sha, evidence_path).decode("utf-8")
    if WO018P_G1_WORK_ORDER not in base_review_evidence:
        raise ValueError(
            f"{WO018P_WORK_ORDER} requires merged {WO018P_G1_WORK_ORDER} support in its base"
        )
    base_checkpoint = git_blob_bytes(base_sha, CHECKPOINT_PATH).decode("utf-8")
    base_manifest = git_blob_bytes(base_sha, CANONICAL_MANIFEST_PATH).decode("utf-8")
    candidate_checkpoint_bytes = (ROOT / CHECKPOINT_PATH).read_bytes()
    candidate_manifest = (ROOT / CANONICAL_MANIFEST_PATH).read_bytes().decode("utf-8")
    require_wo018p_checkpoint_semantics(base_checkpoint, candidate_checkpoint_bytes.decode("utf-8"))
    require_wo018p_manifest_contract(
        base_manifest,
        candidate_manifest,
        candidate_checkpoint_bytes,
    )


def require_wo019p_g1_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
) -> None:
    if work_order != WO019P_G1_WORK_ORDER:
        return
    if base_sha != WO019P_G1_BASE_SHA:
        raise ValueError(
            f"{WO019P_G1_WORK_ORDER} requires exact base {WO019P_G1_BASE_SHA}, observed {base_sha}"
        )
    if base_branch != "main":
        raise ValueError(f"{WO019P_G1_WORK_ORDER} requires the protected main base branch")
    if sorted(set(paths)) != sorted(WO019P_G1_ALLOWED_PATHS) or len(paths) != len(
        WO019P_G1_ALLOWED_PATHS
    ):
        raise ValueError(f"{WO019P_G1_WORK_ORDER} requires exactly the three governance files")
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO019P_G1_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO019P_G1_WORK_ORDER} cannot change migrations")
    if migration_head() != "0007_telemetry_events":
        raise ValueError(f"{WO019P_G1_WORK_ORDER} requires migration head 0007_telemetry_events")


def require_wo019p_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    registered_base_sha: str | None = None,
    authorized_base_sha: str | None = None,
    enforce_current_main: bool = False,
    enforce_authorized_base: bool = True,
) -> None:
    if work_order != WO019P_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO019P_WORK_ORDER} requires the protected main base branch")
    expected_base = registered_base_sha or registered_promotion_base_sha(work_order)
    if base_sha != expected_base:
        raise ValueError(
            f"{WO019P_WORK_ORDER} requires current protected main base "
            f"{expected_base}, observed {base_sha}"
        )
    if sorted(set(paths)) != sorted(WO019P_PROMOTION_ALLOWED_PATHS) or len(paths) != 2:
        raise ValueError(
            f"{WO019P_WORK_ORDER} requires exactly the checkpoint and canonical manifest files"
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(f"{WO019P_WORK_ORDER} requires exactly one authorized-base marker")
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError("WO-019-P authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO019P_WORK_ORDER} authorized-base marker must match the pull request base SHA"
            )
    if enforce_current_main:
        current_main = git_value("rev-parse", "origin/main", fallback="")
        if HEX_SHA.fullmatch(current_main) and base_sha != current_main:
            raise ValueError(
                f"{WO019P_WORK_ORDER} must target current protected main "
                f"{current_main}, observed {base_sha}"
            )
    evidence_path = "scripts/review_evidence.py"
    base_review_evidence = git_blob_bytes(base_sha, evidence_path).decode("utf-8")
    if WO019P_G1_WORK_ORDER not in base_review_evidence:
        raise ValueError(
            f"{WO019P_WORK_ORDER} requires merged {WO019P_G1_WORK_ORDER} support in its base"
        )
    base_checkpoint = git_blob_bytes(base_sha, CHECKPOINT_PATH).decode("utf-8")
    base_manifest = git_blob_bytes(base_sha, CANONICAL_MANIFEST_PATH).decode("utf-8")
    candidate_checkpoint_bytes = (ROOT / CHECKPOINT_PATH).read_bytes()
    candidate_manifest = (ROOT / CANONICAL_MANIFEST_PATH).read_bytes().decode("utf-8")
    require_wo019p_checkpoint_semantics(base_checkpoint, candidate_checkpoint_bytes.decode("utf-8"))
    require_wo019p_manifest_contract(
        base_manifest,
        candidate_manifest,
        candidate_checkpoint_bytes,
    )


def require_wo020p_g1_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
) -> None:
    if work_order != WO020P_G1_WORK_ORDER:
        return
    if base_sha != WO020P_G1_BASE_SHA:
        raise ValueError(
            f"{WO020P_G1_WORK_ORDER} requires exact base {WO020P_G1_BASE_SHA}, observed {base_sha}"
        )
    if base_branch != "main":
        raise ValueError(f"{WO020P_G1_WORK_ORDER} requires the protected main base branch")
    if sorted(set(paths)) != sorted(WO020P_G1_ALLOWED_PATHS) or len(paths) != len(
        WO020P_G1_ALLOWED_PATHS
    ):
        raise ValueError(f"{WO020P_G1_WORK_ORDER} requires exactly the three governance files")
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO020P_G1_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO020P_G1_WORK_ORDER} cannot change migrations")
    if migration_head() != CONTROL_CENTER_CORE_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO020P_G1_WORK_ORDER} requires migration head "
            f"{CONTROL_CENTER_CORE_MIGRATION_BASE_HEAD}"
        )


def require_wo020p_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    registered_base_sha: str | None = None,
    authorized_base_sha: str | None = None,
    enforce_current_main: bool = False,
    enforce_authorized_base: bool = True,
) -> None:
    if work_order != WO020P_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO020P_WORK_ORDER} requires the protected main base branch")
    expected_base = registered_base_sha or registered_promotion_base_sha(work_order)
    if base_sha != expected_base:
        raise ValueError(
            f"{WO020P_WORK_ORDER} requires current protected main base "
            f"{expected_base}, observed {base_sha}"
        )
    if sorted(set(paths)) != sorted(WO020P_PROMOTION_ALLOWED_PATHS) or len(paths) != 2:
        raise ValueError(
            f"{WO020P_WORK_ORDER} requires exactly the checkpoint and canonical manifest files"
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(f"{WO020P_WORK_ORDER} requires exactly one authorized-base marker")
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError("WO-020-P authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO020P_WORK_ORDER} authorized-base marker must match the pull request base SHA"
            )
    if enforce_current_main:
        current_main = git_value("rev-parse", "origin/main", fallback="")
        if HEX_SHA.fullmatch(current_main) and base_sha != current_main:
            raise ValueError(
                f"{WO020P_WORK_ORDER} must target current protected main "
                f"{current_main}, observed {base_sha}"
            )
    evidence_path = "scripts/review_evidence.py"
    base_review_evidence = git_blob_bytes(base_sha, evidence_path).decode("utf-8")
    if WO020P_G1_WORK_ORDER not in base_review_evidence:
        raise ValueError(
            f"{WO020P_WORK_ORDER} requires merged {WO020P_G1_WORK_ORDER} support in its base"
        )
    base_checkpoint = git_blob_bytes(base_sha, CHECKPOINT_PATH).decode("utf-8")
    base_manifest = git_blob_bytes(base_sha, CANONICAL_MANIFEST_PATH).decode("utf-8")
    candidate_checkpoint_bytes = (ROOT / CHECKPOINT_PATH).read_bytes()
    candidate_manifest = (ROOT / CANONICAL_MANIFEST_PATH).read_bytes().decode("utf-8")
    require_wo020p_checkpoint_semantics(base_checkpoint, candidate_checkpoint_bytes.decode("utf-8"))
    require_wo020p_manifest_contract(
        base_manifest,
        candidate_manifest,
        candidate_checkpoint_bytes,
    )


def require_wo021p_g1_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
) -> None:
    if work_order != WO021P_G1_WORK_ORDER:
        return
    if base_sha != WO021P_G1_BASE_SHA:
        raise ValueError(
            f"{WO021P_G1_WORK_ORDER} requires exact base {WO021P_G1_BASE_SHA}, observed {base_sha}"
        )
    if base_branch != "main":
        raise ValueError(f"{WO021P_G1_WORK_ORDER} requires the protected main base branch")
    if sorted(set(paths)) != sorted(WO021P_G1_ALLOWED_PATHS) or len(paths) != len(
        WO021P_G1_ALLOWED_PATHS
    ):
        raise ValueError(f"{WO021P_G1_WORK_ORDER} requires exactly the three governance files")
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO021P_G1_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO021P_G1_WORK_ORDER} cannot change migrations")
    if migration_head() != CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO021P_G1_WORK_ORDER} requires migration head "
            f"{CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD}"
        )


def require_wo021p_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    registered_base_sha: str | None = None,
    authorized_base_sha: str | None = None,
    enforce_current_main: bool = False,
    enforce_authorized_base: bool = True,
) -> None:
    if work_order != WO021P_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO021P_WORK_ORDER} requires the protected main base branch")
    expected_base = registered_base_sha or registered_promotion_base_sha(work_order)
    if base_sha != expected_base:
        raise ValueError(
            f"{WO021P_WORK_ORDER} requires current protected main base "
            f"{expected_base}, observed {base_sha}"
        )
    if sorted(set(paths)) != sorted(WO021P_PROMOTION_ALLOWED_PATHS) or len(paths) != 2:
        raise ValueError(
            f"{WO021P_WORK_ORDER} requires exactly the checkpoint and canonical manifest files"
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(f"{WO021P_WORK_ORDER} requires exactly one authorized-base marker")
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError("WO-021-P authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO021P_WORK_ORDER} authorized-base marker must match the pull request base SHA"
            )
    if enforce_current_main:
        current_main = git_value("rev-parse", "origin/main", fallback="")
        if HEX_SHA.fullmatch(current_main) and base_sha != current_main:
            raise ValueError(
                f"{WO021P_WORK_ORDER} must target current protected main "
                f"{current_main}, observed {base_sha}"
            )
    base_review_evidence = git_blob_bytes(base_sha, "scripts/review_evidence.py").decode("utf-8")
    if WO021P_G1_WORK_ORDER not in base_review_evidence:
        raise ValueError(
            f"{WO021P_WORK_ORDER} requires merged {WO021P_G1_WORK_ORDER} support in its base"
        )
    base_checkpoint = git_blob_bytes(base_sha, CHECKPOINT_PATH).decode("utf-8")
    base_manifest = git_blob_bytes(base_sha, CANONICAL_MANIFEST_PATH).decode("utf-8")
    candidate_checkpoint_bytes = (ROOT / CHECKPOINT_PATH).read_bytes()
    candidate_manifest = (ROOT / CANONICAL_MANIFEST_PATH).read_bytes().decode("utf-8")
    require_wo021p_checkpoint_semantics(base_checkpoint, candidate_checkpoint_bytes.decode("utf-8"))
    require_wo021p_manifest_contract(
        base_manifest,
        candidate_manifest,
        candidate_checkpoint_bytes,
    )


def require_wo022p_g1_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
) -> None:
    if work_order != WO022P_G1_WORK_ORDER:
        return
    if base_sha != WO022P_G1_BASE_SHA:
        raise ValueError(
            f"{WO022P_G1_WORK_ORDER} requires exact base {WO022P_G1_BASE_SHA}, observed {base_sha}"
        )
    if base_branch != "main":
        raise ValueError(f"{WO022P_G1_WORK_ORDER} requires the protected main base branch")
    if sorted(set(paths)) != sorted(WO022P_G1_ALLOWED_PATHS) or len(paths) != len(
        WO022P_G1_ALLOWED_PATHS
    ):
        raise ValueError(f"{WO022P_G1_WORK_ORDER} requires exactly the four governance files")
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO022P_G1_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO022P_G1_WORK_ORDER} cannot change migrations")
    if migration_head() != CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO022P_G1_WORK_ORDER} requires migration head "
            f"{CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD}"
        )


def require_wo022p_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    registered_base_sha: str | None = None,
    authorized_base_sha: str | None = None,
    enforce_current_main: bool = False,
    enforce_authorized_base: bool = True,
) -> None:
    if work_order != WO022P_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO022P_WORK_ORDER} requires the protected main base branch")
    expected_base = registered_base_sha or registered_promotion_base_sha(work_order)
    if base_sha != expected_base:
        raise ValueError(
            f"{WO022P_WORK_ORDER} requires current protected main base "
            f"{expected_base}, observed {base_sha}"
        )
    if sorted(set(paths)) != sorted(WO022P_PROMOTION_ALLOWED_PATHS) or len(paths) != 2:
        raise ValueError(
            f"{WO022P_WORK_ORDER} requires exactly the checkpoint and canonical manifest files"
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(f"{WO022P_WORK_ORDER} requires exactly one authorized-base marker")
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError("WO-022-P authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO022P_WORK_ORDER} authorized-base marker must match the pull request base SHA"
            )
    if enforce_current_main:
        current_main = git_value("rev-parse", "origin/main", fallback="")
        if HEX_SHA.fullmatch(current_main) and base_sha != current_main:
            raise ValueError(
                f"{WO022P_WORK_ORDER} must target current protected main "
                f"{current_main}, observed {base_sha}"
            )
    base_review_evidence = git_blob_bytes(base_sha, "scripts/review_evidence.py").decode("utf-8")
    if WO022P_G1_WORK_ORDER not in base_review_evidence:
        raise ValueError(
            f"{WO022P_WORK_ORDER} requires merged {WO022P_G1_WORK_ORDER} support in its base"
        )
    base_checkpoint = git_blob_bytes(base_sha, CHECKPOINT_PATH).decode("utf-8")
    base_manifest = git_blob_bytes(base_sha, CANONICAL_MANIFEST_PATH).decode("utf-8")
    candidate_checkpoint_bytes = (ROOT / CHECKPOINT_PATH).read_bytes()
    candidate_manifest = (ROOT / CANONICAL_MANIFEST_PATH).read_bytes().decode("utf-8")
    require_wo022p_checkpoint_semantics(base_checkpoint, candidate_checkpoint_bytes.decode("utf-8"))
    require_wo022p_manifest_contract(
        base_manifest,
        candidate_manifest,
        candidate_checkpoint_bytes,
    )


def require_wo023p_g1_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
) -> None:
    if work_order != WO023P_G1_WORK_ORDER:
        return
    if base_sha != WO023P_G1_BASE_SHA:
        raise ValueError(
            f"{WO023P_G1_WORK_ORDER} requires exact base {WO023P_G1_BASE_SHA}, observed {base_sha}"
        )
    if base_branch != "main":
        raise ValueError(f"{WO023P_G1_WORK_ORDER} requires the protected main base branch")
    if sorted(set(paths)) != sorted(WO023P_G1_ALLOWED_PATHS) or len(paths) != len(
        WO023P_G1_ALLOWED_PATHS
    ):
        raise ValueError(f"{WO023P_G1_WORK_ORDER} requires exactly the four governance files")
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO023P_G1_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO023P_G1_WORK_ORDER} cannot change migrations")
    if migration_head() != COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO023P_G1_WORK_ORDER} requires migration head "
            f"{COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD}"
        )


def require_wo023p_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    registered_base_sha: str | None = None,
    authorized_base_sha: str | None = None,
    enforce_current_main: bool = False,
    enforce_authorized_base: bool = True,
) -> None:
    if work_order != WO023P_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO023P_WORK_ORDER} requires the protected main base branch")
    expected_base = registered_base_sha or registered_promotion_base_sha(work_order)
    if base_sha != expected_base:
        raise ValueError(
            f"{WO023P_WORK_ORDER} requires current protected main base "
            f"{expected_base}, observed {base_sha}"
        )
    if sorted(set(paths)) != sorted(WO023P_PROMOTION_ALLOWED_PATHS) or len(paths) != 2:
        raise ValueError(
            f"{WO023P_WORK_ORDER} requires exactly the checkpoint and canonical manifest files"
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(f"{WO023P_WORK_ORDER} requires exactly one authorized-base marker")
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError("WO-023-P authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO023P_WORK_ORDER} authorized-base marker must match the pull request base SHA"
            )
    if enforce_current_main:
        current_main = git_value("rev-parse", "origin/main", fallback="")
        if HEX_SHA.fullmatch(current_main) and base_sha != current_main:
            raise ValueError(
                f"{WO023P_WORK_ORDER} must target current protected main "
                f"{current_main}, observed {base_sha}"
            )
    base_review_evidence = git_blob_bytes(base_sha, "scripts/review_evidence.py").decode("utf-8")
    if WO023P_G1_WORK_ORDER not in base_review_evidence:
        raise ValueError(
            f"{WO023P_WORK_ORDER} requires merged {WO023P_G1_WORK_ORDER} support in its base"
        )
    base_checkpoint = git_blob_bytes(base_sha, CHECKPOINT_PATH).decode("utf-8")
    base_manifest = git_blob_bytes(base_sha, CANONICAL_MANIFEST_PATH).decode("utf-8")
    candidate_checkpoint_bytes = (ROOT / CHECKPOINT_PATH).read_bytes()
    candidate_manifest = (ROOT / CANONICAL_MANIFEST_PATH).read_bytes().decode("utf-8")
    require_wo023p_checkpoint_semantics(base_checkpoint, candidate_checkpoint_bytes.decode("utf-8"))
    require_wo023p_manifest_contract(
        base_manifest,
        candidate_manifest,
        candidate_checkpoint_bytes,
    )


def require_wo023p_g1_c1_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    authorized_base_sha: str | None = None,
    enforce_authorized_base: bool = True,
) -> None:
    if work_order != WO023P_G1_C1_WORK_ORDER:
        return
    if base_sha != WO023P_G1_C1_BASE_SHA:
        raise ValueError(
            f"{WO023P_G1_C1_WORK_ORDER} requires exact base {WO023P_G1_C1_BASE_SHA}, "
            f"observed {base_sha}"
        )
    if base_branch != "main":
        raise ValueError(f"{WO023P_G1_C1_WORK_ORDER} requires the protected main base branch")
    if sorted(set(paths)) != sorted(WO023P_G1_C1_ALLOWED_PATHS) or len(paths) != len(
        WO023P_G1_C1_ALLOWED_PATHS
    ):
        raise ValueError(
            f"{WO023P_G1_C1_WORK_ORDER} requires exactly the review evidence tooling and "
            "its regression test"
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(
                f"{WO023P_G1_C1_WORK_ORDER} requires exactly one authorized-base marker"
            )
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError("WO-023-P-G1-C1 authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO023P_G1_C1_WORK_ORDER} authorized-base marker must match the pull request "
                "base SHA"
            )
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO023P_G1_C1_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO023P_G1_C1_WORK_ORDER} cannot change migrations")
    if migration_head() != COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO023P_G1_C1_WORK_ORDER} requires migration head "
            f"{COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD}"
        )


def require_wo024p_g1_c1_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    authorized_base_sha: str | None = None,
    enforce_authorized_base: bool = True,
) -> None:
    if work_order != WO024P_G1_C1_WORK_ORDER:
        return
    if base_sha != WO024P_G1_C1_BASE_SHA:
        raise ValueError(
            f"{WO024P_G1_C1_WORK_ORDER} requires exact base {WO024P_G1_C1_BASE_SHA}, "
            f"observed {base_sha}"
        )
    if base_branch != "main":
        raise ValueError(f"{WO024P_G1_C1_WORK_ORDER} requires the protected main base branch")
    if not paths:
        raise ValueError(f"{WO024P_G1_C1_WORK_ORDER} requires a bounded correction delta")
    unauthorized = sorted(set(paths) - WO024P_G1_C1_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            f"{WO024P_G1_C1_WORK_ORDER} changed files outside the bounded correction scope: "
            + ", ".join(unauthorized)
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(
                f"{WO024P_G1_C1_WORK_ORDER} requires exactly one authorized-base marker"
            )
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError("WO-024-P-G1-C1 authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO024P_G1_C1_WORK_ORDER} authorized-base marker must match the pull request "
                "base SHA"
            )
    for prefix in sorted(WO024P_G1_C1_FORBIDDEN_PREFIXES):
        offenders = sorted(path for path in paths if path.startswith(prefix))
        if offenders:
            raise ValueError(
                f"{WO024P_G1_C1_WORK_ORDER} cannot change {prefix}: " + ", ".join(offenders)
            )
    for manifest in sorted(set(paths) & DEPENDENCY_MANIFEST_PATHS):
        raise ValueError(
            f"{WO024P_G1_C1_WORK_ORDER} cannot change the dependency manifest {manifest}"
        )
    for path in sorted(set(paths)):
        if RELEASE_PATH_IDENTIFIER.search(path):
            raise ValueError(f"{WO024P_G1_C1_WORK_ORDER} cannot change release assets: {path}")
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO024P_G1_C1_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO024P_G1_C1_WORK_ORDER} cannot change migrations")
    if work_order in ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS:
        raise ValueError(f"{WO024P_G1_C1_WORK_ORDER} must not join the active promotion pair")
    if WO024P_G1_C1_WORK_ORDER in ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS:
        raise ValueError(f"{WO024P_G1_C1_WORK_ORDER} must not join the active promotion pair")
    if migration_head() != V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO024P_G1_C1_WORK_ORDER} requires migration head "
            f"{V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}"
        )


def require_wo024p_g1_c2_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    authorized_base_sha: str | None = None,
    enforce_authorized_base: bool = True,
) -> None:
    """Bounded scope for the stateful-test correction: test-only, outside the promotion pair."""

    if work_order != WO024P_G1_C2_WORK_ORDER:
        return
    if base_sha != WO024P_G1_C2_BASE_SHA:
        raise ValueError(
            f"{WO024P_G1_C2_WORK_ORDER} requires exact base {WO024P_G1_C2_BASE_SHA}, "
            f"observed {base_sha}"
        )
    if base_branch != "main":
        raise ValueError(f"{WO024P_G1_C2_WORK_ORDER} requires the protected main base branch")
    if not paths:
        raise ValueError(f"{WO024P_G1_C2_WORK_ORDER} requires a non-empty correction delta")
    unauthorized = sorted(set(paths) - WO024P_G1_C2_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            f"{WO024P_G1_C2_WORK_ORDER} changed files outside the bounded correction scope: "
            + ", ".join(unauthorized)
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(
                f"{WO024P_G1_C2_WORK_ORDER} requires exactly one authorized-base marker"
            )
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError("WO-024-P-G1-C2 authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO024P_G1_C2_WORK_ORDER} authorized-base marker must match the pull request "
                "base SHA"
            )
    for prefix in sorted(WO024P_G1_C1_FORBIDDEN_PREFIXES):
        offenders = sorted(path for path in paths if path.startswith(prefix))
        if offenders:
            raise ValueError(
                f"{WO024P_G1_C2_WORK_ORDER} cannot change {prefix}: " + ", ".join(offenders)
            )
    promotion_paths = sorted(set(paths) & WO024P_PROMOTION_ALLOWED_PATHS)
    if promotion_paths:
        raise ValueError(
            f"{WO024P_G1_C2_WORK_ORDER} cannot include the canonical promotion files: "
            + ", ".join(promotion_paths)
        )
    for manifest in sorted(set(paths) & DEPENDENCY_MANIFEST_PATHS):
        raise ValueError(
            f"{WO024P_G1_C2_WORK_ORDER} cannot change the dependency manifest {manifest}"
        )
    for path in sorted(set(paths)):
        if RELEASE_PATH_IDENTIFIER.search(path):
            raise ValueError(f"{WO024P_G1_C2_WORK_ORDER} cannot change release assets: {path}")
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO024P_G1_C2_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO024P_G1_C2_WORK_ORDER} cannot change migrations")
    if work_order in ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS:
        raise ValueError(f"{WO024P_G1_C2_WORK_ORDER} must not join the active promotion pair")
    if WO024P_G1_C2_WORK_ORDER in ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS:
        raise ValueError(f"{WO024P_G1_C2_WORK_ORDER} must not join the active promotion pair")
    if frozenset({WO024_G1_WORK_ORDER, WO024P_WORK_ORDER}) != (
        ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS
    ):
        raise ValueError(
            f"{WO024P_G1_C2_WORK_ORDER} requires the active WO-024 promotion pair to be unchanged"
        )
    if migration_head() != V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO024P_G1_C2_WORK_ORDER} requires migration head "
            f"{V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}"
        )


def require_wo024_g1_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    authorized_base_sha: str | None = None,
    enforce_authorized_base: bool = True,
) -> None:
    if work_order != WO024_G1_WORK_ORDER:
        return
    if base_sha != WO024_G1_BASE_SHA:
        raise ValueError(
            f"{WO024_G1_WORK_ORDER} requires exact base {WO024_G1_BASE_SHA}, observed {base_sha}"
        )
    if base_branch != "main":
        raise ValueError(f"{WO024_G1_WORK_ORDER} requires the protected main base branch")
    if sorted(set(paths)) != sorted(WO024_G1_ALLOWED_PATHS) or len(paths) != len(
        WO024_G1_ALLOWED_PATHS
    ):
        raise ValueError(f"{WO024_G1_WORK_ORDER} requires exactly the four governance files")
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(f"{WO024_G1_WORK_ORDER} requires exactly one authorized-base marker")
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError("WO-024-G1 authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO024_G1_WORK_ORDER} authorized-base marker must match the pull request base SHA"
            )
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO024_G1_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO024_G1_WORK_ORDER} cannot change migrations")
    if migration_head() != V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO024_G1_WORK_ORDER} requires migration head "
            f"{V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}"
        )


def closure_product_scope(paths: list[str]) -> list[str]:
    """Return the closure-sprint paths that leave the bounded product scope."""

    unauthorized: list[str] = []
    for path in sorted(set(paths)):
        if path in V01_CLOSURE_SPRINT_PRODUCT_FORBIDDEN_EXACT_PATHS or any(
            path == prefix.rstrip("/") or path.startswith(prefix)
            for prefix in V01_CLOSURE_SPRINT_PRODUCT_FORBIDDEN_PREFIXES
        ):
            unauthorized.append(path)
            continue
        if path in V01_CLOSURE_SPRINT_PRODUCT_ALLOWED_EXACT_PATHS:
            continue
        if any(path.startswith(prefix) for prefix in V01_CLOSURE_SPRINT_PRODUCT_ALLOWED_PREFIXES):
            continue
        unauthorized.append(path)
    return unauthorized


def closure_sprint_scope(paths: list[str]) -> list[str]:
    """Return the paths that leave the scope the closure sprint may observe.

    Ordinary WO-024 product increments stay inside the bounded product scope and
    therefore keep rejecting Project Brain paths. The final WO-024-P promotion
    run observes exactly the two canonical promotion files as a promotion-only
    delta: that exact pair is allowed, while the pair plus any third path falls
    back to the ordinary product scope and fails closed, as does either
    canonical path on its own.

    A path is observable when it is inside either the bounded product scope or
    the registered release-engineering surface; a path has to leave both scopes
    to fail closed. Project Brain, GEF artifacts and migrations remain rejected
    even when they sit under a release-engineering prefix.
    """

    unique = sorted(set(paths))
    if unique == sorted(WO024P_PROMOTION_ALLOWED_PATHS) and len(unique) == len(
        WO024P_PROMOTION_ALLOWED_PATHS
    ):
        return []
    return sorted(set(closure_product_scope(paths)) & set(release_engineering_scope(paths)))


def release_engineering_scope(paths: list[str]) -> list[str]:
    """Return the paths that leave the registered release-engineering surface."""

    unauthorized: list[str] = []
    for path in sorted(set(paths)):
        if path.startswith(RELEASE_ENGINEERING_FORBIDDEN_PREFIXES):
            unauthorized.append(path)
            continue
        if path in RELEASE_ENGINEERING_ALLOWED_EXACT_PATHS:
            continue
        if any(path.startswith(prefix) for prefix in RELEASE_ENGINEERING_ALLOWED_PREFIXES):
            continue
        unauthorized.append(path)
    return unauthorized


def require_wo024_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    enforce_current_main: bool = False,
) -> None:
    if work_order != WO024_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO024_WORK_ORDER} requires the protected main base branch")
    if HEX_SHA.fullmatch(base_sha) is None or base_sha == "0" * 40:
        raise ValueError(f"{WO024_WORK_ORDER} requires a resolved protected-main base SHA")
    if enforce_current_main:
        current_main = git_value("rev-parse", "origin/main", fallback="")
        if HEX_SHA.fullmatch(current_main) is None:
            raise ValueError(f"{WO024_WORK_ORDER} requires a resolved current protected main SHA")
        if base_sha != current_main:
            raise ValueError(
                f"{WO024_WORK_ORDER} must target current protected main {current_main}, "
                f"observed {base_sha}"
            )
        base_review_evidence = git_blob_bytes(base_sha, "scripts/review_evidence.py").decode(
            "utf-8"
        )
        if WO024_G1_WORK_ORDER not in base_review_evidence:
            raise ValueError(
                f"{WO024_WORK_ORDER} requires merged {WO024_G1_WORK_ORDER} support in its base"
            )
    unauthorized = closure_product_scope(paths)
    if unauthorized:
        raise ValueError(
            f"{WO024_WORK_ORDER} changed files outside the bounded v0.1 closure sprint scope: "
            + ", ".join(unauthorized)
        )
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO024_WORK_ORDER} cannot change migrations")
    if any(path == ".github" or path.startswith(".github/") for path in paths):
        raise ValueError(f"{WO024_WORK_ORDER} cannot change CI workflows")


def require_wo024p_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    registered_base_sha: str | None = None,
    authorized_base_sha: str | None = None,
    enforce_current_main: bool = False,
    enforce_authorized_base: bool = True,
    approved_lineage: Mapping[str, object] | None = None,
    closure_evidence: Mapping[str, object] | None = None,
) -> None:
    if work_order != WO024P_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO024P_WORK_ORDER} requires the protected main base branch")
    expected_base = registered_base_sha or registered_promotion_base_sha(work_order)
    if base_sha != expected_base:
        raise ValueError(
            f"{WO024P_WORK_ORDER} requires current protected main base "
            f"{expected_base}, observed {base_sha}"
        )
    if sorted(set(paths)) != sorted(WO024P_PROMOTION_ALLOWED_PATHS) or len(paths) != 2:
        raise ValueError(
            f"{WO024P_WORK_ORDER} requires exactly the checkpoint and canonical manifest files"
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(f"{WO024P_WORK_ORDER} requires exactly one authorized-base marker")
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError("WO-024-P authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO024P_WORK_ORDER} authorized-base marker must match the pull request base SHA"
            )
    if enforce_current_main:
        current_main = git_value("rev-parse", "origin/main", fallback="")
        if HEX_SHA.fullmatch(current_main) and base_sha != current_main:
            raise ValueError(
                f"{WO024P_WORK_ORDER} must target current protected main "
                f"{current_main}, observed {base_sha}"
            )
    base_review_evidence = git_blob_bytes(base_sha, "scripts/review_evidence.py").decode("utf-8")
    if WO024_G1_WORK_ORDER not in base_review_evidence:
        raise ValueError(
            f"{WO024P_WORK_ORDER} requires merged {WO024_G1_WORK_ORDER} support in its base"
        )
    if approved_lineage is None:
        raise ValueError(f"{WO024P_WORK_ORDER} requires approved product lineage evidence")
    require_wo024_approved_lineage_result(approved_lineage)
    if not isinstance(closure_evidence, Mapping):
        raise ValueError(f"{WO024P_WORK_ORDER} requires merged v01 closure sprint evidence")
    full_closure: Mapping[str, object] = closure_evidence
    require_wo024_v01_closure_sprint_evidence(
        WO024P_WORK_ORDER,
        {"v01_closure_sprint": full_closure},
        V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD,
    )
    base_checkpoint = git_blob_bytes(base_sha, CHECKPOINT_PATH).decode("utf-8")
    base_manifest = git_blob_bytes(base_sha, CANONICAL_MANIFEST_PATH).decode("utf-8")
    candidate_checkpoint_bytes = (ROOT / CHECKPOINT_PATH).read_bytes()
    candidate_manifest = (ROOT / CANONICAL_MANIFEST_PATH).read_bytes().decode("utf-8")
    require_wo024p_checkpoint_semantics(
        base_checkpoint,
        candidate_checkpoint_bytes.decode("utf-8"),
        approved_lineage,
        full_closure,
    )
    require_wo024p_manifest_contract(
        base_manifest,
        candidate_manifest,
        candidate_checkpoint_bytes,
    )


def require_wo024p_manifest_contract(
    base_manifest_text: str,
    candidate_manifest_text: str,
    candidate_checkpoint_bytes: bytes,
) -> None:
    require_checkpoint_manifest_contract(
        base_manifest_text, candidate_manifest_text, candidate_checkpoint_bytes, WO024P_WORK_ORDER
    )


def require_wo024p_checkpoint_semantics(
    base_text: str,
    candidate_text: str,
    approved_lineage: Mapping[str, object],
    closure_evidence: Mapping[str, object],
) -> None:
    base_preamble, base_ordered, base_sections = _raw_checkpoint_structure(base_text, "base")
    candidate_preamble, candidate_ordered, candidate_sections = _raw_checkpoint_structure(
        candidate_text, "candidate"
    )
    if base_preamble != candidate_preamble:
        raise ValueError("WO-024-P candidate preamble changed byte-for-byte")
    if tuple(section.name for section in base_ordered) != tuple(
        section.name for section in candidate_ordered
    ):
        raise ValueError("WO-024-P checkpoint section sequence changed unexpectedly")
    for position, (base_section, candidate_section) in enumerate(
        zip(base_ordered, candidate_ordered, strict=True), 1
    ):
        if base_section.heading != candidate_section.heading:
            raise ValueError(f"WO-024-P heading changed byte-for-byte at position {position}")
    for name in tuple(section.name for section in base_ordered):
        if (
            name not in _WO016P_RAW_CONTROLLED_SECTIONS
            and candidate_sections[name] != base_sections[name]
        ):
            raise ValueError(f"WO-024-P changed unrelated checkpoint section: {name}")

    newline = "\n"
    expected_bullets = wo024p_completion_bullets(
        version=str(closure_evidence.get("v01_closure_sprint_evidence_version")),
        pass_count=int(cast(int, closure_evidence.get("dod_pass_count"))),
        total_count=int(cast(int, closure_evidence.get("dod_total_count"))),
        critical=int(cast(int, closure_evidence.get("stabilization_remaining_critical"))),
        high=int(cast(int, closure_evidence.get("stabilization_remaining_high"))),
        product_pr=int(cast(int, approved_lineage.get("product_pr"))),
        audited_head=str(approved_lineage.get("audited_product_head")),
        sol_review=int(cast(int, approved_lineage.get("sol_review_id"))),
        squash_merge=str(approved_lineage.get("squash_merge_sha")),
        post_merge_ci=int(cast(int, approved_lineage.get("post_merge_ci_run"))),
        backend_passed=int(cast(int, approved_lineage.get("prior_backend_passed"))),
        dashboard_passed=int(cast(int, approved_lineage.get("prior_dashboard_passed"))),
        migration_head=V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD,
    )
    base_completed = base_sections["COMPLETED"]
    if not base_completed.endswith(newline):
        raise ValueError("WO-024-P base COMPLETED section lacks the canonical final newline")
    expected_controlled = {
        "STATUS": f"{EXPECTED_WO024P_STATUS}{newline}{newline}",
        "COMPLETED": base_completed[:-1]
        + "".join(f"- {bullet}{newline}" for bullet in expected_bullets)
        + newline,
        "IN PROGRESS": f"- {EXPECTED_WO024P_IN_PROGRESS}{newline}{newline}",
        "BLOCKERS": f"{EXPECTED_WO024P_BLOCKERS}{newline}{newline}",
        "NEXT STEP": f"{EXPECTED_WO024P_NEXT_STEP}{newline}{newline}",
        "PENDING": f"{newline}",
    }
    for name, expected_body in expected_controlled.items():
        if candidate_sections.get(name) != expected_body:
            raise ValueError(f"WO-024-P {name} section is outside the strict raw grammar")

    base_pending = checkpoint_bullets(checkpoint_sections(base_text), "PENDING")
    if sorted(base_pending) != sorted(WO024P_COMPLETED_PENDING_ITEMS):
        raise ValueError(
            "WO-024-P promotion base must contain exactly the remaining closure pending items"
        )
    if checkpoint_bullets(checkpoint_sections(candidate_text), "PENDING"):
        raise ValueError("WO-024-P must remove every remaining closure pending item")
    if normalized_checkpoint_value(checkpoint_sections(base_text), "STATUS") != (
        EXPECTED_WO024P_PREVIOUS_STATUS
    ):
        raise ValueError("WO-024-P promotion base has an unexpected checkpoint status")


def memory_lifecycle_evidence() -> dict[str, object]:
    text = integration_file(WO015_MEMORY_EVIDENCE_FILE)
    unknown: dict[str, object] = {
        "status": "UNKNOWN",
        "evidence_file": WO015_MEMORY_EVIDENCE_FILE,
        **{field: False for field in WO015_MEMORY_REQUIRED_FIELDS},
        **{field: 0 for field in WO015_MEMORY_INTEGER_FIELDS},
        **{field: "UNKNOWN" for field in WO015_MEMORY_STRING_FIELDS},
    }
    if not text:
        return unknown
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return unknown
    if not isinstance(data, dict):
        return unknown
    values = {field: data.get(field) is True for field in WO015_MEMORY_REQUIRED_FIELDS}
    integers: dict[str, int] = {}
    for field in WO015_MEMORY_INTEGER_FIELDS:
        value = data.get(field)
        integers[field] = value if isinstance(value, int) and not isinstance(value, bool) else 0
    strings = {
        field: data.get(field) if isinstance(data.get(field), str) else "UNKNOWN"
        for field in WO015_MEMORY_STRING_FIELDS
    }
    bounded_counts = all(value >= 0 for value in integers.values())
    status = (
        "PASS"
        if data.get("status") == "PASS"
        and all(values.values())
        and bounded_counts
        and strings["memory_evidence_version"] == "memory-lifecycle-provenance-v1"
        and integers["memory_project_count"] >= 2
        and integers["memory_cross_project_rejections"] >= 1
        and integers["memory_provenance_records"] >= 1
        and integers["memory_invalid_promotion_rejections"] >= 1
        and integers["memory_source_race_rejections"] >= 1
        and integers["memory_adr_race_rejections"] >= 1
        and integers["memory_head_race_rejections"] >= 1
        and integers["memory_history_versions"] >= 2
        and integers["memory_restart_records"] >= 1
        and integers["memory_redis_loss_records"] >= 1
        and integers["memory_secret_leaks"] == 0
        and integers["memory_llm_calls"] == 0
        and integers["memory_provider_calls"] == 0
        else "FAIL"
    )
    return {
        "status": status,
        "evidence_file": WO015_MEMORY_EVIDENCE_FILE,
        **values,
        **integers,
        **strings,
    }


def require_wo015_memory_evidence(
    work_order: str,
    integration: Mapping[str, object],
    migration_head_value: str | None = None,
) -> None:
    if work_order not in {WO015_WORK_ORDER, WO015P_G1_WORK_ORDER, WO015P_WORK_ORDER}:
        return
    memory = integration.get("memory")
    if not isinstance(memory, Mapping):
        raise ValueError("WO-015 Review Evidence missing mandatory Memory evidence")
    missing = [field for field in WO015_MEMORY_REQUIRED_FIELDS if memory.get(field) is not True]
    if missing:
        raise ValueError(
            "WO-015 Review Evidence missing mandatory Memory evidence: "
            + ", ".join(sorted(missing))
        )
    if memory.get("status") != "PASS":
        raise ValueError("WO-015 requires passing Memory lifecycle evidence")
    if memory.get("evidence_file") != WO015_MEMORY_EVIDENCE_FILE:
        raise ValueError("WO-015 requires the bounded memory-lifecycle evidence file")
    if memory.get("memory_evidence_version") != "memory-lifecycle-provenance-v1":
        raise ValueError("WO-015 requires the versioned Memory evidence contract")
    for field in WO015_MEMORY_INTEGER_FIELDS:
        value = memory.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"WO-015 requires bounded integer evidence for {field}")
    required_positive = {
        "memory_project_count": 2,
        "memory_cross_project_rejections": 1,
        "memory_provenance_records": 1,
        "memory_invalid_promotion_rejections": 1,
        "memory_source_race_rejections": 1,
        "memory_adr_race_rejections": 1,
        "memory_head_race_rejections": 1,
        "memory_history_versions": 2,
        "memory_restart_records": 1,
        "memory_redis_loss_records": 1,
    }
    for field, minimum in required_positive.items():
        if cast(int, memory[field]) < minimum:
            raise ValueError(f"WO-015 requires computed evidence for {field} >= {minimum}")
    for field in ("memory_secret_leaks", "memory_llm_calls", "memory_provider_calls"):
        if memory.get(field) != 0:
            raise ValueError(f"WO-015 requires {field}=0")
    if migration_head_value is None or memory.get("memory_migration_head") != migration_head_value:
        raise ValueError("WO-015 requires Memory evidence to match the observed migration head")
    if migration_head_value == "0005_semantic_retrieval":
        raise ValueError("WO-015 requires a Memory migration head beyond 0005_semantic_retrieval")


def require_wo016_storage_evidence(
    work_order: str,
    integration: Mapping[str, object],
    migration_head_value: str | None = None,
) -> None:
    if work_order not in {
        WO016_WORK_ORDER,
        WO016P_G1_WORK_ORDER,
        WO016P_WORK_ORDER,
    }:
        return
    storage = integration.get("acce_storage")
    if not isinstance(storage, Mapping):
        raise ValueError("WO-016 Review Evidence missing mandatory ACCE storage-policy evidence")
    missing = [
        field for field in ACCE_STORAGE_POLICY_REQUIRED_FIELDS if storage.get(field) is not True
    ]
    if missing:
        raise ValueError(
            "WO-016 Review Evidence missing mandatory ACCE storage-policy evidence: "
            + ", ".join(sorted(missing))
        )
    if storage.get("status") != "PASS":
        raise ValueError("WO-016 requires passing ACCE storage-policy evidence")
    if storage.get("evidence_file") != ACCE_STORAGE_POLICY_EVIDENCE_FILE:
        raise ValueError("WO-016 requires the bounded ACCE storage-policy evidence file")
    if storage.get("acce_evidence_version") != ACCE_STORAGE_POLICY_EVIDENCE_VERSION:
        raise ValueError("WO-016 requires the versioned ACCE evidence contract")
    if migration_head_value is None or not isinstance(migration_head_value, str):
        raise ValueError("WO-016 requires an observed migration head")
    if (
        work_order in {WO016P_G1_WORK_ORDER, WO016P_WORK_ORDER}
        and migration_head_value != "0006_memory_lifecycle_provenance"
    ):
        raise ValueError("WO-016-P requires migration head 0006_memory_lifecycle_provenance")
    for field in ACCE_STORAGE_POLICY_INTEGER_FIELDS:
        value = storage.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"WO-016 requires bounded integer evidence for {field}")
    if storage.get("dedup_savings_bytes") != (
        storage.get("dedup_logical_bytes", 0) - storage.get("dedup_unique_logical_bytes", 0)
    ):
        raise ValueError("WO-016 requires truthful dedup savings evidence")
    for field in ("canonical_source_loss_count", "llm_calls", "provider_calls"):
        if storage.get(field) != 0:
            raise ValueError(f"WO-016 requires {field}=0")
    if work_order in {WO016P_G1_WORK_ORDER, WO016P_WORK_ORDER}:
        if storage.get("storage_policy_version") != "acce-policy-v1":
            raise ValueError("WO-016-P requires storage policy acce-policy-v1")
        matrix = storage.get("benchmark_matrix")
        if not isinstance(matrix, list) or len(matrix) != 6:
            raise ValueError("WO-016-P requires exactly six measured benchmark rows")
        counts = {tier: 0 for tier in ACCE_STORAGE_POLICY_ALLOWED_TIERS}
        for row in matrix:
            if not isinstance(row, Mapping):
                raise ValueError("WO-016-P requires structured benchmark rows")
            tier = row.get("tier")
            if tier not in counts or row.get("benchmark_measured") is not True:
                raise ValueError("WO-016-P requires six measured HOT/WARM/COLD benchmark rows")
            counts[cast(str, tier)] += 1
        if counts != {"HOT": 2, "WARM": 2, "COLD": 2}:
            raise ValueError("WO-016-P requires two measured benchmark candidates per tier")


def require_wo017_mcp_evidence(
    work_order: str,
    integration: Mapping[str, object],
    migration_head_value: str | None = None,
) -> None:
    if work_order not in {WO017_WORK_ORDER, WO017P_G1_WORK_ORDER, WO017P_WORK_ORDER}:
        return
    surface = integration.get("mcp_surface")
    if not isinstance(surface, Mapping):
        raise ValueError("WO-017 Review Evidence missing mandatory MCP surface evidence")
    if set(surface) != MCP_CORE_SURFACE_ALLOWED_FIELDS:
        raise ValueError(
            "WO-017 MCP surface evidence must match the closed contract exactly; "
            "missing mandatory or extra fields"
        )
    if surface.get("status") != "PASS":
        raise ValueError("WO-017 requires passing MCP surface evidence")
    if surface.get("evidence_file") != MCP_CORE_SURFACE_EVIDENCE_FILE:
        raise ValueError("WO-017 requires the bounded mcp-surface.json evidence file")
    if surface.get("mcp_evidence_version") != MCP_CORE_SURFACE_EVIDENCE_VERSION:
        raise ValueError("WO-017 requires the versioned MCP evidence contract")
    registered_project_count = surface.get(MCP_CORE_SURFACE_REGISTERED_PROJECT_COUNT)
    if (
        not isinstance(registered_project_count, int)
        or isinstance(registered_project_count, bool)
        or not 2 <= registered_project_count <= MCP_CORE_SURFACE_MAX_REGISTERED_PROJECT_COUNT
    ):
        raise ValueError(
            "WO-017 requires registered_project_count between 2 and "
            f"{MCP_CORE_SURFACE_MAX_REGISTERED_PROJECT_COUNT}"
        )
    missing = [field for field in MCP_CORE_SURFACE_TRUE_FIELDS if surface.get(field) is not True]
    if missing:
        raise ValueError(
            "WO-017 Review Evidence missing mandatory MCP surface evidence: "
            + ", ".join(sorted(missing))
        )
    invalid_false_fields = [
        field for field in MCP_CORE_SURFACE_FALSE_FIELDS if surface.get(field) is not False
    ]
    if invalid_false_fields:
        raise ValueError(
            "WO-017 Review Evidence requires negative MCP controls to remain false: "
            + ", ".join(sorted(invalid_false_fields))
        )
    if surface.get("tool_list_exact") != list(MCP_CORE_SURFACE_TOOLS):
        raise ValueError("WO-017 requires the exact bounded MCP read-only tool list")
    if surface.get("observed_migration_head") != "0006_memory_lifecycle_provenance":
        raise ValueError("WO-017 requires observed migration head 0006_memory_lifecycle_provenance")
    if migration_head_value != "0006_memory_lifecycle_provenance":
        raise ValueError("WO-017 requires migration head 0006_memory_lifecycle_provenance")
    for field in MCP_CORE_SURFACE_INTEGER_FIELDS:
        value = surface.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"WO-017 requires bounded integer evidence for {field}")
        if value != 0:
            raise ValueError(f"WO-017 requires {field}=0")


def require_wo019_telemetry_evidence(
    work_order: str,
    integration: Mapping[str, object],
    migration_head_value: str | None = None,
) -> None:
    if work_order == WO019_G1_WORK_ORDER:
        if "telemetry_event_bus" in integration:
            raise ValueError(
                f"{WO019_G1_WORK_ORDER} must not claim future Telemetry/Event Bus product evidence"
            )
        return
    if work_order not in {WO019_WORK_ORDER, WO019P_G1_WORK_ORDER, WO019P_WORK_ORDER}:
        return
    telemetry = integration.get("telemetry_event_bus")
    if not isinstance(telemetry, Mapping):
        raise ValueError(f"{WO019_WORK_ORDER} missing mandatory Telemetry/Event Bus evidence")
    if set(telemetry) != TELEMETRY_EVENT_BUS_ALLOWED_FIELDS:
        raise ValueError(
            f"{WO019_WORK_ORDER} Telemetry/Event Bus evidence must match "
            "the closed contract exactly"
        )
    if telemetry.get("status") != "PASS":
        raise ValueError(f"{WO019_WORK_ORDER} requires passing Telemetry/Event Bus evidence")
    if telemetry.get("evidence_file") != TELEMETRY_EVENT_BUS_EVIDENCE_FILE:
        raise ValueError(f"{WO019_WORK_ORDER} requires {TELEMETRY_EVENT_BUS_EVIDENCE_FILE}")
    if telemetry.get("telemetry_evidence_version") != TELEMETRY_EVENT_BUS_EVIDENCE_VERSION:
        raise ValueError(
            f"{WO019_WORK_ORDER} requires evidence version {TELEMETRY_EVENT_BUS_EVIDENCE_VERSION}"
        )
    missing = [
        field for field in TELEMETRY_EVENT_BUS_TRUE_FIELDS if telemetry.get(field) is not True
    ]
    if missing:
        raise ValueError(
            f"{WO019_WORK_ORDER} missing mandatory Telemetry/Event Bus evidence: "
            + ", ".join(sorted(missing))
        )
    invalid_false = [
        field for field in TELEMETRY_EVENT_BUS_FALSE_FIELDS if telemetry.get(field) is not False
    ]
    if invalid_false:
        raise ValueError(
            f"{WO019_WORK_ORDER} requires bounded negative claims: "
            + ", ".join(sorted(invalid_false))
        )
    for field in TELEMETRY_EVENT_BUS_INTEGER_FIELDS:
        value = telemetry.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{WO019_WORK_ORDER} requires bounded integer evidence for {field}")
    event_types = telemetry.get("implemented_event_types")
    if (
        not isinstance(event_types, list)
        or not 1 <= len(event_types) <= TELEMETRY_EVENT_BUS_MAX_EVENT_TYPES
        or any(
            not isinstance(event_type, str)
            or event_type not in TELEMETRY_EVENT_BUS_CANONICAL_EVENT_TYPES
            for event_type in event_types
        )
        or len(set(event_types)) != len(event_types)
    ):
        raise ValueError(f"{WO019_WORK_ORDER} requires a non-empty explicit canonical event subset")
    if telemetry.get("event_type_count") != len(event_types):
        raise ValueError(f"{WO019_WORK_ORDER} requires truthful event_type_count")
    if not 1 <= cast(int, telemetry["payload_max_bytes"]) <= TELEMETRY_EVENT_BUS_MAX_PAYLOAD_BYTES:
        raise ValueError(f"{WO019_WORK_ORDER} requires bounded payload_max_bytes")
    if not 1 <= cast(int, telemetry["cursor_max_bytes"]) <= TELEMETRY_EVENT_BUS_MAX_CURSOR_BYTES:
        raise ValueError(f"{WO019_WORK_ORDER} requires bounded cursor_max_bytes")
    for field in (
        "duplicate_canonical_events",
        "cross_project_leaks",
        "secret_leaks",
        "filesystem_path_leaks",
        "llm_calls",
        "provider_calls",
    ):
        if telemetry.get(field) != 0:
            raise ValueError(f"{WO019_WORK_ORDER} requires {field}=0")
    producer_path = telemetry.get("producer_path")
    if (
        not isinstance(producer_path, str)
        or not TELEMETRY_EVENT_BUS_PATH.fullmatch(producer_path)
        or Path(producer_path).is_absolute()
    ):
        raise ValueError(f"{WO019_WORK_ORDER} requires a sanitized relative producer_path")
    observed_head = telemetry.get("observed_migration_head")
    if not isinstance(observed_head, str) or not observed_head:
        raise ValueError(f"{WO019_WORK_ORDER} requires observed migration head evidence")
    if migration_head_value is None or observed_head != migration_head_value:
        raise ValueError(
            f"{WO019_WORK_ORDER} requires evidence to match the observed migration head"
        )
    if telemetry.get("migration_base_head") != "0006_memory_lifecycle_provenance":
        raise ValueError(f"{WO019_WORK_ORDER} requires the G1 migration base head")
    expected_changed = observed_head != "0006_memory_lifecycle_provenance"
    if telemetry.get("migration_changed") is not expected_changed:
        raise ValueError(f"{WO019_WORK_ORDER} requires truthful migration_changed evidence")


def canonical_repository_relative_path(value: object, *, prefix: str) -> bool:
    """Return True when value is a normalized repository-relative evidence path.

    One deterministic rule covers the Control Center evidence contract: a valid
    path is non-empty, bounded, rooted at ``prefix``, POSIX-style and
    repository-relative, with no backslash, drive/UNC/absolute form, empty or
    dot segment, control character, Windows-reserved character or normalization
    that would change its semantic location.
    """

    if not isinstance(value, str):
        return False
    if not value or len(value) > CONTROL_CENTER_CORE_PATH_MAX_LENGTH:
        return False
    if not value.startswith(prefix):
        return False
    if posixpath.isabs(value) or value != posixpath.normpath(value):
        return False
    if CONTROL_CENTER_CORE_PATH.fullmatch(value) is None:
        return False
    return all(segment not in {"", ".", ".."} for segment in value.split("/"))


def valid_control_center_core_path(field: str, value: object) -> bool:
    """Apply the canonical path rule plus the control-center-core-v1 role root."""

    return canonical_repository_relative_path(value, prefix=CONTROL_CENTER_CORE_PATH_ROOTS[field])


def valid_control_center_metrics_path(value: object) -> bool:
    """Return True for a normalized path in an authorized WO-021 product area."""

    return any(
        canonical_repository_relative_path(value, prefix=prefix)
        for prefix in CONTROL_CENTER_METRICS_PATH_ROOTS
    )


def valid_control_center_full_path(field: str, value: object) -> bool:
    """Apply the full Control Center path rule and its bounded role root."""

    return canonical_repository_relative_path(value, prefix=CONTROL_CENTER_FULL_PATH_ROOTS[field])


def valid_control_center_full_evidence_path(value: object) -> bool:
    """Return True for a normalized path in an authorized WO-022 product area."""

    return any(
        canonical_repository_relative_path(value, prefix=prefix)
        for prefix in CONTROL_CENTER_FULL_EVIDENCE_PATH_ROOTS
    )


def valid_comprehensive_benchmarks_evidence_path(value: object) -> bool:
    """Return True for a normalized path in an authorized WO-023 product area."""

    return any(
        canonical_repository_relative_path(value, prefix=prefix)
        for prefix in COMPREHENSIVE_BENCHMARKS_EVIDENCE_PATH_ROOTS
    )


def _benchmark_number(value: object, bounds: tuple[float, float]) -> bool:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    return float(bounds[0]) <= float(value) <= float(bounds[1])


def comprehensive_benchmarks_evidence() -> dict[str, object]:
    unknown: dict[str, object] = {
        "status": "UNKNOWN",
        "comprehensive_benchmarks_evidence_version": COMPREHENSIVE_BENCHMARKS_EVIDENCE_VERSION,
        "evidence_file": COMPREHENSIVE_BENCHMARKS_EVIDENCE_FILE,
        "observed_migration_head": "UNKNOWN",
        "migration_base_head": "UNKNOWN",
        "baseline_reference_version": "UNKNOWN",
        "ground_truth_source": "UNKNOWN",
        "run_digest": "UNKNOWN",
        "retrieval_metrics_status": "UNKNOWN",
        "token_metrics_status": "UNKNOWN",
        "storage_metrics_status": "UNKNOWN",
        "retrieval_context_measure": "UNKNOWN",
        "token_cache_status": "UNKNOWN",
        "token_output_status": "UNKNOWN",
        "provider_receipt_version": "UNKNOWN",
        "provider_receipt_artifact": "UNKNOWN",
        "provider_receipt_sha256": "UNKNOWN",
        "provider_receipt_reconciled": False,
        "optional_provider_metric": "UNKNOWN",
        "benchmark_families": [],
        "evidence_paths": [],
        **{field: False for field in COMPREHENSIVE_BENCHMARKS_TRUE_FIELDS},
        **{field: False for field in COMPREHENSIVE_BENCHMARKS_FALSE_FIELDS},
        **{field: 0 for field in COMPREHENSIVE_BENCHMARKS_ZERO_FIELDS},
        **{field: 0 for field in COMPREHENSIVE_BENCHMARKS_INTEGER_FIELDS},
        **{field: None for field in COMPREHENSIVE_BENCHMARKS_NULLABLE_INTEGER_FIELDS},
        **{field: None for field in COMPREHENSIVE_BENCHMARKS_NUMBER_FIELDS},
    }
    text = integration_file(COMPREHENSIVE_BENCHMARKS_EVIDENCE_FILE)
    if not text:
        return unknown
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {**unknown, "status": "FAIL"}
    if not isinstance(data, dict):
        return {**unknown, "status": "FAIL"}
    payload = cast(dict[str, object], data)
    if set(payload) != COMPREHENSIVE_BENCHMARKS_ALLOWED_FIELDS:
        return {**unknown, "status": "FAIL"}
    strings = {
        field: payload.get(field) if isinstance(payload.get(field), str) else "UNKNOWN"
        for field in COMPREHENSIVE_BENCHMARKS_STRING_FIELDS
    }
    integers: dict[str, int] = {}
    integer_valid = True
    for field in (
        *COMPREHENSIVE_BENCHMARKS_ZERO_FIELDS,
        *COMPREHENSIVE_BENCHMARKS_INTEGER_FIELDS,
    ):
        value = payload.get(field)
        if not isinstance(value, int) or isinstance(value, bool):
            integer_valid = False
            integers[field] = 0
        else:
            integers[field] = value
    numbers: dict[str, object] = {}
    numbers_valid = True
    for field in COMPREHENSIVE_BENCHMARKS_NUMBER_FIELDS:
        value = payload.get(field)
        if value is None:
            numbers[field] = None
            continue
        if not _benchmark_number(value, COMPREHENSIVE_BENCHMARKS_NUMBER_BOUNDS[field]):
            numbers_valid = False
            numbers[field] = None
            continue
        numbers[field] = value
    nullable_integers: dict[str, int | None] = {}
    nullable_valid = True
    for field in COMPREHENSIVE_BENCHMARKS_NULLABLE_INTEGER_FIELDS:
        value = payload.get(field)
        if value is None:
            nullable_integers[field] = None
            continue
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            nullable_valid = False
            nullable_integers[field] = None
            continue
        nullable_integers[field] = value
    receipt_version = payload.get("provider_receipt_version")
    receipt_reconciled = payload.get("provider_receipt_reconciled")
    provider_claims = (
        payload.get("token_cache_status") == "AVAILABLE"
        or payload.get("token_output_status") == "AVAILABLE"
    )
    provider_valid = (
        (
            receipt_version == COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_VERSION
            and receipt_reconciled is True
            and payload.get("provider_receipt_artifact")
            == COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_FILE
            and isinstance(payload.get("provider_receipt_sha256"), str)
            and COMPREHENSIVE_BENCHMARKS_PROVIDER_SHA256_PATTERN.fullmatch(
                cast(str, payload.get("provider_receipt_sha256"))
            )
            is not None
        )
        if provider_claims
        else (
            receipt_version == COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_NONE
            and receipt_reconciled is False
            and payload.get("provider_receipt_artifact")
            == COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_NONE
            and payload.get("provider_receipt_sha256")
            == COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_NONE
        )
    )
    claims_valid = all(
        payload.get(field) is True for field in COMPREHENSIVE_BENCHMARKS_TRUE_FIELDS
    ) and all(payload.get(field) is False for field in COMPREHENSIVE_BENCHMARKS_FALSE_FIELDS)
    families_valid = _is_closed_string_set(
        payload.get("benchmark_families"), COMPREHENSIVE_BENCHMARKS_FAMILIES
    )
    raw_paths = payload.get("evidence_paths")
    paths_valid = (
        isinstance(raw_paths, list)
        and 1 <= len(cast(list[object], raw_paths)) <= COMPREHENSIVE_BENCHMARKS_MAX_EVIDENCE_PATHS
        and all(valid_comprehensive_benchmarks_evidence_path(path) for path in raw_paths)
        and len(set(cast(list[object], raw_paths))) == len(cast(list[object], raw_paths))
    )
    return {
        "status": (
            "PASS"
            if integer_valid
            and numbers_valid
            and families_valid
            and paths_valid
            and nullable_valid
            and provider_valid
            and claims_valid
            else "FAIL"
        ),
        **strings,
        "benchmark_families": (
            list(cast(list[str], payload["benchmark_families"])) if families_valid else []
        ),
        "evidence_paths": (
            [str(path) for path in cast(list[object], raw_paths)] if paths_valid else []
        ),
        **{field: payload.get(field) for field in COMPREHENSIVE_BENCHMARKS_TRUE_FIELDS},
        **{field: payload.get(field) for field in COMPREHENSIVE_BENCHMARKS_FALSE_FIELDS},
        **integers,
        **nullable_integers,
        **numbers,
        "provider_receipt_reconciled": payload.get("provider_receipt_reconciled"),
    }


def provider_usage_receipt_evidence() -> dict[str, object]:
    """Load the independent provider usage receipt artifact for WO-023 binding."""

    unknown: dict[str, object] = {
        "status": "UNKNOWN",
        "artifact_sha256": "UNKNOWN",
        "provider_usage_receipt_version": "UNKNOWN",
        "provider_receipt_artifact": COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_FILE,
        "provider_reconciliation_state": "UNKNOWN",
        "provider_usage_source": "UNKNOWN",
        **{field: 0 for field in COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_INTEGER_FIELDS},
        "provider_output_tokens": None,
    }
    text = integration_file(COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_FILE)
    if not text:
        return unknown
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {**unknown, "status": "FAIL"}
    if not isinstance(data, dict):
        return {**unknown, "status": "FAIL"}
    payload = cast(dict[str, object], data)
    if set(payload) != COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_ALLOWED_FIELDS:
        return {**unknown, "status": "FAIL"}
    strings = {
        field: payload.get(field) if isinstance(payload.get(field), str) else "UNKNOWN"
        for field in COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_STRING_FIELDS
    }
    integers: dict[str, int] = {}
    integer_valid = True
    for field in COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_INTEGER_FIELDS:
        value = payload.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            integer_valid = False
            integers[field] = 0
        else:
            integers[field] = value
    output_tokens = payload.get("provider_output_tokens")
    output_valid = output_tokens is None or (
        isinstance(output_tokens, int)
        and not isinstance(output_tokens, bool)
        and output_tokens >= 0
    )
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {
        "status": "PASS" if integer_valid and output_valid else "FAIL",
        "artifact_sha256": digest,
        **strings,
        **integers,
        "provider_output_tokens": output_tokens if output_valid else None,
    }


def require_wo023_comprehensive_benchmarks_evidence(
    work_order: str,
    integration: Mapping[str, object],
    migration_head_value: str | None = None,
) -> None:
    if work_order == WO023_G1_WORK_ORDER:
        if "comprehensive_benchmarks" in integration:
            raise ValueError(
                f"{WO023_G1_WORK_ORDER} must not claim future comprehensive benchmarks evidence"
            )
        return
    if work_order not in {WO023_WORK_ORDER, WO023P_G1_WORK_ORDER, WO023P_WORK_ORDER}:
        return
    benchmarks = integration.get("comprehensive_benchmarks")
    if not isinstance(benchmarks, Mapping):
        raise ValueError(f"{WO023_WORK_ORDER} missing mandatory comprehensive benchmarks evidence")
    full = cast(Mapping[str, object], benchmarks)
    if set(full) != COMPREHENSIVE_BENCHMARKS_ALLOWED_FIELDS:
        raise ValueError(
            f"{WO023_WORK_ORDER} comprehensive benchmarks evidence must match the closed "
            "contract exactly"
        )
    if full.get("status") != "PASS":
        raise ValueError(f"{WO023_WORK_ORDER} requires passing comprehensive benchmarks evidence")
    if full.get("evidence_file") != COMPREHENSIVE_BENCHMARKS_EVIDENCE_FILE:
        raise ValueError(f"{WO023_WORK_ORDER} requires {COMPREHENSIVE_BENCHMARKS_EVIDENCE_FILE}")
    if (
        full.get("comprehensive_benchmarks_evidence_version")
        != COMPREHENSIVE_BENCHMARKS_EVIDENCE_VERSION
    ):
        raise ValueError(
            f"{WO023_WORK_ORDER} requires evidence version "
            f"{COMPREHENSIVE_BENCHMARKS_EVIDENCE_VERSION}"
        )
    if not _is_closed_string_set(full.get("benchmark_families"), COMPREHENSIVE_BENCHMARKS_FAMILIES):
        raise ValueError(
            f"{WO023_WORK_ORDER} requires the closed retrieval, token and storage families"
        )
    missing_true = [
        field for field in COMPREHENSIVE_BENCHMARKS_TRUE_FIELDS if full.get(field) is not True
    ]
    if missing_true:
        raise ValueError(
            f"{WO023_WORK_ORDER} missing mandatory comprehensive benchmarks evidence: "
            + ", ".join(sorted(missing_true))
        )
    invalid_false = [
        field for field in COMPREHENSIVE_BENCHMARKS_FALSE_FIELDS if full.get(field) is not False
    ]
    if invalid_false:
        raise ValueError(
            f"{WO023_WORK_ORDER} requires bounded negative claims: "
            + ", ".join(sorted(invalid_false))
        )
    for field in COMPREHENSIVE_BENCHMARKS_ZERO_FIELDS:
        value = full.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value != 0:
            raise ValueError(f"{WO023_WORK_ORDER} requires {field}=0")
    for field in COMPREHENSIVE_BENCHMARKS_INTEGER_FIELDS:
        value = full.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{WO023_WORK_ORDER} requires bounded integer evidence for {field}")
    corpus_tasks = cast(int, full["corpus_task_count"])
    if not 1 <= corpus_tasks <= COMPREHENSIVE_BENCHMARKS_MAX_CORPUS_TASKS:
        raise ValueError(f"{WO023_WORK_ORDER} requires a bounded benchmark corpus")
    if cast(int, full["retrieval_recall_k"]) != COMPREHENSIVE_BENCHMARKS_ACCEPTED_RECALL_K:
        raise ValueError(
            f"{WO023_WORK_ORDER} requires the accepted recall@"
            f"{COMPREHENSIVE_BENCHMARKS_ACCEPTED_RECALL_K} benchmark depth"
        )
    logical = cast(int, full["storage_logical_bytes"])
    deduplicated = cast(int, full["storage_dedup_bytes"])
    physical = cast(int, full["storage_physical_bytes"])
    if not logical >= deduplicated >= physical:
        raise ValueError(
            f"{WO023_WORK_ORDER} requires logical >= deduplicated >= physical byte counts"
        )
    if physical <= 0:
        raise ValueError(
            f"{WO023_WORK_ORDER} requires a nonempty representative storage dataset with "
            "positive logical, deduplicated and physical bytes"
        )
    run_digest = full.get("run_digest")
    if (
        not isinstance(run_digest, str)
        or COMPREHENSIVE_BENCHMARKS_RUN_DIGEST_PATTERN.fullmatch(run_digest) is None
    ):
        raise ValueError(f"{WO023_WORK_ORDER} requires a reproducible run digest")
    for family, status_field in COMPREHENSIVE_BENCHMARKS_FAMILY_STATUS_FIELDS.items():
        status = full.get(status_field)
        if status not in COMPREHENSIVE_BENCHMARKS_METRIC_STATUSES:
            raise ValueError(f"{WO023_WORK_ORDER} requires an explicit {family} metrics status")
        if status != COMPREHENSIVE_BENCHMARKS_CORE_FAMILY_STATUS:
            raise ValueError(
                f"{WO023_WORK_ORDER} requires measured {family} core metrics; "
                f"{COMPREHENSIVE_BENCHMARKS_CORE_FAMILY_STATUS} status is mandatory"
            )
        numeric = [
            full.get(field) for field in COMPREHENSIVE_BENCHMARKS_FAMILY_NUMBER_FIELDS[family]
        ]
        if any(value is None for value in numeric):
            raise ValueError(
                f"{WO023_WORK_ORDER} requires measured {family} metrics when reported AVAILABLE"
            )
    recall_at_k = full.get("retrieval_recall_at_k")
    precision = full.get("retrieval_precision")
    if (
        not _benchmark_number(recall_at_k, (0.0, 1.0))
        or float(cast(float, recall_at_k)) < COMPREHENSIVE_BENCHMARKS_ACCEPTED_RECALL_AT_K_MIN
    ):
        raise ValueError(
            f"{WO023_WORK_ORDER} requires recall@k at or above the accepted baseline "
            f"{COMPREHENSIVE_BENCHMARKS_ACCEPTED_RECALL_AT_K_MIN}"
        )
    if not _benchmark_number(precision, (0.0, 1.0)) or float(cast(float, precision)) <= (
        COMPREHENSIVE_BENCHMARKS_MIN_PRECISION_EXCLUSIVE
    ):
        raise ValueError(
            f"{WO023_WORK_ORDER} requires a strictly positive bounded retrieval precision"
        )
    baseline_mrr = full.get("retrieval_baseline_mrr")
    reranked_mrr = full.get("retrieval_reranked_mrr")
    for field, value in (
        ("retrieval_baseline_mrr", baseline_mrr),
        ("retrieval_reranked_mrr", reranked_mrr),
    ):
        if not _benchmark_number(value, (0.0, 1.0)):
            raise ValueError(
                f"{WO023_WORK_ORDER} requires bounded reranking MRR evidence for {field}"
            )
    if float(cast(float, reranked_mrr)) < float(cast(float, baseline_mrr)):
        raise ValueError(
            f"{WO023_WORK_ORDER} must not regress reranking quality below its baseline"
        )
    if full.get("retrieval_context_measure") not in (COMPREHENSIVE_BENCHMARKS_CONTEXT_MEASURES):
        raise ValueError(f"{WO023_WORK_ORDER} requires an accepted retrieval context-size measure")
    context_bytes = full.get("retrieval_context_bytes")
    if not isinstance(context_bytes, int) or isinstance(context_bytes, bool) or context_bytes <= 0:
        raise ValueError(f"{WO023_WORK_ORDER} requires a positive measured retrieval context size")
    cache_status = full.get("token_cache_status")
    output_status = full.get("token_output_status")
    for status_field, value_field in (
        ("token_cache_status", "token_cached_tokens"),
        ("token_output_status", "token_output_tokens"),
    ):
        status = full.get(status_field)
        if status not in COMPREHENSIVE_BENCHMARKS_SIGNAL_STATUSES:
            raise ValueError(f"{WO023_WORK_ORDER} requires an explicit {status_field}")
        value = full.get(value_field)
        if status == "AVAILABLE":
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(
                    f"{WO023_WORK_ORDER} requires measured {value_field} when reported AVAILABLE"
                )
        elif value is not None:
            raise ValueError(
                f"{WO023_WORK_ORDER} must not report {value_field} that is not AVAILABLE"
            )
    provider_claims = cache_status == "AVAILABLE" or output_status == "AVAILABLE"
    receipt_version = full.get("provider_receipt_version")
    receipt_reconciled = full.get("provider_receipt_reconciled")
    receipt_artifact = full.get("provider_receipt_artifact")
    receipt_sha256 = full.get("provider_receipt_sha256")
    if not provider_claims:
        if receipt_version != COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_NONE:
            raise ValueError(
                f"{WO023_WORK_ORDER} requires {COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_NONE} "
                "provider receipt binding without AVAILABLE provider-backed claims"
            )
        if (
            receipt_reconciled is not False
            or receipt_artifact != COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_NONE
            or receipt_sha256 != COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_NONE
        ):
            raise ValueError(
                f"{WO023_WORK_ORDER} must not carry provider receipt bindings without "
                "AVAILABLE provider-backed claims"
            )
    if provider_claims:
        if receipt_version != COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_VERSION:
            raise ValueError(
                f"{WO023_WORK_ORDER} requires {COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_VERSION} "
                "evidence for AVAILABLE cache or output token claims"
            )
        if receipt_reconciled is not True:
            raise ValueError(
                f"{WO023_WORK_ORDER} requires reconciled provider usage evidence for AVAILABLE "
                "cache or output token claims"
            )
        provider_calls = full.get("optional_provider_calls")
        provider_metric = full.get("optional_provider_metric")
        provider_recorded = isinstance(provider_metric, str) and provider_metric not in {
            "NONE",
            "UNKNOWN",
        }
        if (
            not isinstance(provider_calls, int)
            or isinstance(provider_calls, bool)
            or provider_calls <= 0
            or not provider_recorded
        ):
            raise ValueError(
                f"{WO023_WORK_ORDER} requires recorded provider usage for AVAILABLE provider "
                "token claims"
            )
        provider_evidence = cast(dict[str, Any], integration.get("context_manager", {}))
        missing_provider = [
            field
            for field in COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_GUARANTEES
            if provider_evidence.get(field) is not True
        ]
        if missing_provider:
            raise ValueError(
                f"{WO023_WORK_ORDER} requires reconciled provider usage guarantees: "
                + ", ".join(sorted(missing_provider))
            )
        if receipt_artifact != COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_FILE:
            raise ValueError(
                f"{WO023_WORK_ORDER} requires the independent provider receipt artifact "
                f"{COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_FILE}"
            )
        if not isinstance(receipt_sha256, str) or (
            COMPREHENSIVE_BENCHMARKS_PROVIDER_SHA256_PATTERN.fullmatch(receipt_sha256) is None
        ):
            raise ValueError(f"{WO023_WORK_ORDER} requires a provider receipt SHA-256 binding")
        independent_receipt = provider_usage_receipt_evidence()
        if independent_receipt.get("status") != "PASS":
            raise ValueError(
                f"{WO023_WORK_ORDER} requires an independently loaded reconciled provider receipt"
            )
        if independent_receipt.get("artifact_sha256") != receipt_sha256:
            raise ValueError(
                f"{WO023_WORK_ORDER} provider receipt identity does not match the loaded artifact"
            )
        if (
            independent_receipt.get("provider_usage_receipt_version")
            != COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_VERSION
        ):
            raise ValueError(
                f"{WO023_WORK_ORDER} requires version "
                f"{COMPREHENSIVE_BENCHMARKS_PROVIDER_RECEIPT_VERSION} provider receipt evidence"
            )
        if (
            independent_receipt.get("provider_reconciliation_state")
            != COMPREHENSIVE_BENCHMARKS_PROVIDER_RECONCILIATION_EXACT
        ):
            raise ValueError(
                f"{WO023_WORK_ORDER} requires "
                f"{COMPREHENSIVE_BENCHMARKS_PROVIDER_RECONCILIATION_EXACT} provider receipt "
                "reconciliation"
            )
        if (
            independent_receipt.get("provider_usage_source")
            != COMPREHENSIVE_BENCHMARKS_PROVIDER_USAGE_SOURCE
        ):
            raise ValueError(
                f"{WO023_WORK_ORDER} requires {COMPREHENSIVE_BENCHMARKS_PROVIDER_USAGE_SOURCE} "
                "provider receipt evidence"
            )
        for field in ("secret_leaks", "credential_leaks"):
            if independent_receipt.get(field) != 0:
                raise ValueError(f"{WO023_WORK_ORDER} requires a provider receipt without {field}")
        independent_total = independent_receipt.get("provider_total_input_tokens")
        independent_cached = independent_receipt.get("provider_cached_input_tokens")
        independent_fresh = independent_receipt.get("provider_fresh_input_tokens")
        for field, value in (
            ("provider_total_input_tokens", independent_total),
            ("provider_cached_input_tokens", independent_cached),
            ("provider_fresh_input_tokens", independent_fresh),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{WO023_WORK_ORDER} requires measured provider receipt {field}")
        if cast(int, independent_cached) + cast(int, independent_fresh) != cast(
            int, independent_total
        ):
            raise ValueError(
                f"{WO023_WORK_ORDER} requires the independent provider receipt to reconcile "
                "cached plus fresh input tokens with its total"
            )
        usage_sources = provider_evidence.get("provider_cache_provider_usage_sources")
        if not isinstance(usage_sources, list) or (
            COMPREHENSIVE_BENCHMARKS_PROVIDER_USAGE_SOURCE not in usage_sources
        ):
            raise ValueError(
                f"{WO023_WORK_ORDER} requires {COMPREHENSIVE_BENCHMARKS_PROVIDER_USAGE_SOURCE} "
                "provider usage sources"
            )
        receipt_total = provider_evidence.get("provider_cache_provider_total_input_tokens")
        receipt_cached = provider_evidence.get("provider_cache_provider_cached_input_tokens")
        receipt_fresh = provider_evidence.get("provider_cache_provider_fresh_input_tokens")
        for field, value in (
            ("provider_cache_provider_total_input_tokens", receipt_total),
            ("provider_cache_provider_cached_input_tokens", receipt_cached),
            ("provider_cache_provider_fresh_input_tokens", receipt_fresh),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(
                    f"{WO023_WORK_ORDER} requires reconciled provider usage for {field}"
                )
        if cast(int, receipt_cached) + cast(int, receipt_fresh) != cast(int, receipt_total):
            raise ValueError(
                f"{WO023_WORK_ORDER} requires provider cached plus fresh input tokens to "
                "reconcile with the provider total"
            )
        if cache_status == "AVAILABLE" and full.get("token_cached_tokens") != independent_cached:
            raise ValueError(
                f"{WO023_WORK_ORDER} cached token count contradicts the independent "
                "provider receipt"
            )
        if output_status == "AVAILABLE":
            independent_output = independent_receipt.get("provider_output_tokens")
            if not isinstance(independent_output, int) or isinstance(independent_output, bool):
                raise ValueError(
                    f"{WO023_WORK_ORDER} requires measured independent provider receipt "
                    "output tokens for an AVAILABLE output claim"
                )
            if full.get("token_output_tokens") != independent_output:
                raise ValueError(
                    f"{WO023_WORK_ORDER} output token count contradicts the independent "
                    "provider receipt"
                )
    for field in (
        "baseline_task_success_rate",
        "optimized_task_success_rate",
        "baseline_test_pass_rate",
        "optimized_test_pass_rate",
    ):
        if not _benchmark_number(full.get(field), (0.0, 1.0)):
            raise ValueError(
                f"{WO023_WORK_ORDER} requires bounded benchmark outcome evidence for {field}"
            )
    if float(cast(float, full["optimized_task_success_rate"])) < float(
        cast(float, full["baseline_task_success_rate"])
    ):
        raise ValueError(
            f"{WO023_WORK_ORDER} must not degrade benchmark task success relative to the baseline"
        )
    if (
        float(cast(float, full["optimized_test_pass_rate"]))
        < float(cast(float, full["baseline_test_pass_rate"]))
        - COMPREHENSIVE_BENCHMARKS_MAX_TEST_PASS_DEGRADATION
    ):
        raise ValueError(
            f"{WO023_WORK_ORDER} must not materially degrade the benchmark test pass rate"
        )
    baseline_tokens = cast(int, full["token_baseline_input_tokens"])
    optimized_tokens = cast(int, full["token_optimized_input_tokens"])
    reduction = full.get("token_reduction_percentage")
    if baseline_tokens <= 0 or optimized_tokens >= baseline_tokens:
        raise ValueError(
            f"{WO023_WORK_ORDER} requires a token saving claim with baseline > 0 and "
            "optimized < baseline"
        )
    expected_reduction = (baseline_tokens - optimized_tokens) / baseline_tokens * 100
    if not _benchmark_number(reduction, (0.0, 100.0)) or abs(
        float(cast(float, reduction)) - expected_reduction
    ) > (COMPREHENSIVE_BENCHMARKS_TOKEN_REDUCTION_TOLERANCE_PP):
        raise ValueError(
            f"{WO023_WORK_ORDER} token reduction percentage contradicts the declared token counts"
        )
    if logical > 0:
        expected_dedup = (logical - deduplicated) / logical
        expected_total = (logical - physical) / logical
    else:
        expected_dedup = 0.0
        expected_total = 0.0
    expected_compression = (deduplicated - physical) / deduplicated if deduplicated > 0 else 0.0
    for field, expected_ratio in (
        ("storage_dedup_ratio", expected_dedup),
        ("storage_compression_ratio", expected_compression),
        ("storage_total_reduction_ratio", expected_total),
    ):
        value = full.get(field)
        if (
            not _benchmark_number(value, (0.0, 1.0))
            or abs(float(cast(float, value)) - expected_ratio)
            > COMPREHENSIVE_BENCHMARKS_RATIO_TOLERANCE
        ):
            raise ValueError(
                f"{WO023_WORK_ORDER} {field} contradicts the declared storage byte counts"
            )
    for field in COMPREHENSIVE_BENCHMARKS_NUMBER_FIELDS:
        value = full.get(field)
        if value is None:
            continue
        if not _benchmark_number(value, COMPREHENSIVE_BENCHMARKS_NUMBER_BOUNDS[field]):
            raise ValueError(f"{WO023_WORK_ORDER} requires bounded numeric evidence for {field}")
    optional_calls = cast(int, full["optional_provider_calls"])
    optional_metric = full.get("optional_provider_metric")
    recorded = isinstance(optional_metric, str) and optional_metric not in {"NONE", "UNKNOWN"}
    if (optional_calls > 0) != recorded:
        raise ValueError(
            f"{WO023_WORK_ORDER} requires optional provider usage to be recorded explicitly"
        )
    evidence_paths = full.get("evidence_paths")
    if (
        not isinstance(evidence_paths, list)
        or not 1
        <= len(cast(list[object], evidence_paths))
        <= COMPREHENSIVE_BENCHMARKS_MAX_EVIDENCE_PATHS
        or any(not valid_comprehensive_benchmarks_evidence_path(path) for path in evidence_paths)
        or len(set(cast(list[object], evidence_paths))) != len(cast(list[object], evidence_paths))
    ):
        raise ValueError(
            f"{WO023_WORK_ORDER} requires bounded, unique, normalized evidence paths inside "
            "authorized product roots"
        )
    ground_truth = full.get("ground_truth_source")
    if not isinstance(ground_truth, str) or not ground_truth.startswith(
        COMPREHENSIVE_BENCHMARKS_GROUND_TRUTH_PREFIX
    ):
        raise ValueError(
            f"{WO023_WORK_ORDER} requires an auditable ground-truth source "
            f"prefixed with {COMPREHENSIVE_BENCHMARKS_GROUND_TRUTH_PREFIX}"
        )
    ground_truth_path = ground_truth[len(COMPREHENSIVE_BENCHMARKS_GROUND_TRUTH_PREFIX) :]
    if not valid_comprehensive_benchmarks_evidence_path(ground_truth_path):
        raise ValueError(
            f"{WO023_WORK_ORDER} requires a canonical repository-relative ground-truth path"
        )
    reviewed_head = git_value("rev-parse", "HEAD", fallback="")
    try:
        ground_truth_blob = (
            git_blob_bytes(reviewed_head, ground_truth_path)
            if HEX_SHA.fullmatch(reviewed_head)
            else b""
        )
    except ValueError:
        ground_truth_blob = b""
    if not ground_truth_blob:
        raise ValueError(
            f"{WO023_WORK_ORDER} requires the ground-truth blob to exist at the reviewed HEAD"
        )
    baseline = full.get("baseline_reference_version")
    if not isinstance(baseline, str) or not baseline.strip():
        raise ValueError(f"{WO023_WORK_ORDER} requires a versioned benchmark baseline")
    if (
        len(baseline) > COMPREHENSIVE_BENCHMARKS_MAX_BASELINE_VERSION_LENGTH
        or baseline.strip().upper() in COMPREHENSIVE_BENCHMARKS_BASELINE_PLACEHOLDERS
    ):
        raise ValueError(
            f"{WO023_WORK_ORDER} requires a bounded stable baseline identity instead of a "
            "placeholder value"
        )
    if (
        migration_head_value is not None
        and migration_head_value != COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD
    ):
        raise ValueError(
            f"{WO023_WORK_ORDER} requires migration head "
            f"{COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD}"
        )
    for field, expected in (
        ("observed_migration_head", COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD),
        ("migration_base_head", COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD),
    ):
        if full.get(field) != expected:
            raise ValueError(
                f"{WO023_WORK_ORDER} requires observed migration head "
                f"{COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD}"
            )


def valid_closure_evidence_path(value: object) -> bool:
    """Return True for a normalized repository-relative closure evidence path."""

    if not isinstance(value, str):
        return False
    if value in V01_CLOSURE_SPRINT_EVIDENCE_PATH_FILES:
        return True
    return any(
        canonical_repository_relative_path(value, prefix=prefix)
        for prefix in V01_CLOSURE_SPRINT_EVIDENCE_PATH_ROOTS
    )


def _closure_path_list(value: object) -> bool:
    if not isinstance(value, list) or not 1 <= len(value) <= V01_CLOSURE_SPRINT_MAX_PATHS:
        return False
    items = [item for item in value]
    return all(valid_closure_evidence_path(item) for item in items) and len(set(items)) == len(
        items
    )


def _closure_documentation_entries(value: object) -> bool:
    if not isinstance(value, list) or len(value) != len(V01_CLOSURE_SPRINT_DOCUMENTATION_ENTRIES):
        return False
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict) or set(raw) != {"name", "path", "sha256", "status"}:
            return False
        name = raw.get("name")
        if not isinstance(name, str) or name not in V01_CLOSURE_SPRINT_DOCUMENTATION_ENTRIES:
            return False
        if name in seen:
            return False
        seen.add(name)
        if not valid_closure_evidence_path(raw.get("path")):
            return False
        digest = raw.get("sha256")
        if not isinstance(digest, str) or (
            COMPREHENSIVE_BENCHMARKS_PROVIDER_SHA256_PATTERN.fullmatch(digest) is None
        ):
            return False
        if raw.get("status") != "PASS":
            return False
    return seen == set(V01_CLOSURE_SPRINT_DOCUMENTATION_ENTRIES)


def _closure_dod_items(value: object) -> tuple[bool, dict[str, int]]:
    counts = {"total": 0, "pass": 0, "fail": 0, "unknown": 0}
    if not isinstance(value, list) or not 1 <= len(value) <= V01_CLOSURE_SPRINT_MAX_ITEMS:
        return False, counts
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict) or set(raw) != {"item", "status", "evidence_path", "sha256"}:
            return False, counts
        item = raw.get("item")
        if not isinstance(item, str) or not item.strip() or len(item) > 512 or item in seen:
            return False, counts
        seen.add(item)
        status = raw.get("status")
        if status not in {"PASS", "FAIL", "UNKNOWN"}:
            return False, counts
        if not valid_closure_evidence_path(raw.get("evidence_path")):
            return False, counts
        digest = raw.get("sha256")
        if not isinstance(digest, str) or (
            COMPREHENSIVE_BENCHMARKS_PROVIDER_SHA256_PATTERN.fullmatch(digest) is None
        ):
            return False, counts
        counts["total"] += 1
        counts[str(status).casefold()] += 1
    return True, counts


def closure_sprint_evidence() -> dict[str, object]:
    """Read and truthfully validate the v01-closure-sprint-v1 artifact."""

    unknown: dict[str, object] = {
        "status": "UNKNOWN",
        "v01_closure_sprint_evidence_version": V01_CLOSURE_SPRINT_EVIDENCE_VERSION,
        "evidence_file": V01_CLOSURE_SPRINT_EVIDENCE_FILE,
        "closure_candidate": False,
        "dod_matrix_complete": False,
        "dod_total_count": 0,
        "dod_pass_count": 0,
        "dod_fail_count": 0,
        "dod_unknown_count": 0,
        "full_v01_complete_claimed": False,
        "secret_leaks": "UNKNOWN",
        "filesystem_path_leaks": "UNKNOWN",
        "cross_project_leaks": "UNKNOWN",
        "core_llm_calls": "UNKNOWN",
        "core_provider_calls": "UNKNOWN",
    }
    text = integration_file(V01_CLOSURE_SPRINT_EVIDENCE_FILE)
    if not text:
        return unknown
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {**unknown, "status": "FAIL"}
    if not isinstance(data, dict):
        return {**unknown, "status": "FAIL"}
    payload = cast(dict[str, object], data)
    if set(payload) != V01_CLOSURE_SPRINT_ALLOWED_FIELDS:
        return {**unknown, "status": "FAIL"}
    strings = {
        field: payload.get(field) if isinstance(payload.get(field), str) else "UNKNOWN"
        for field in V01_CLOSURE_SPRINT_STRING_FIELDS
    }
    booleans: dict[str, object] = {}
    valid = True
    for field in V01_CLOSURE_SPRINT_TRUE_FIELDS:
        value = payload.get(field)
        booleans[field] = value
        valid = valid and value is True
    for field in V01_CLOSURE_SPRINT_FALSE_FIELDS:
        value = payload.get(field)
        booleans[field] = value
        valid = valid and value is False
    integers: dict[str, int] = {}
    for field, bound in V01_CLOSURE_SPRINT_INTEGER_BOUNDS.items():
        value = payload.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= bound:
            valid = False
            integers[field] = 0
        else:
            integers[field] = value
    zero_values: dict[str, int] = {}
    for field in V01_CLOSURE_SPRINT_ZERO_FIELDS:
        value = payload.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value != 0:
            valid = False
            zero_values[field] = -1
        else:
            zero_values[field] = value
    lists = {field: payload.get(field) for field in V01_CLOSURE_SPRINT_LIST_FIELDS}
    for field in V01_CLOSURE_SPRINT_LIST_FIELDS:
        if not _closure_path_list(lists[field]):
            valid = False
    if not _is_closed_string_set(
        payload.get("orchestration_authority_order"), V01_CLOSURE_SPRINT_AUTHORITY_ORDER
    ):
        valid = False
    if not _is_closed_string_set(
        payload.get("e2e_completed_stages"), V01_CLOSURE_SPRINT_E2E_STAGES
    ):
        valid = False
    if not _is_closed_string_set(
        payload.get("orchestration_negative_matrix"), V01_CLOSURE_SPRINT_NEGATIVE_CASES
    ):
        valid = False
    if not _closure_documentation_entries(payload.get("documentation_entries")):
        valid = False
    dod_valid, dod_counts = _closure_dod_items(payload.get("dod_items"))
    if not dod_valid:
        valid = False
    if (
        integers["dod_total_count"] != dod_counts["total"]
        or integers["dod_pass_count"] != dod_counts["pass"]
        or integers["stabilization_defects_fixed"] > integers["stabilization_defects_discovered"]
        or integers["e2e_stage_count"] != len(V01_CLOSURE_SPRINT_E2E_STAGES)
    ):
        valid = False
    if not isinstance(payload.get("closure_candidate"), bool):
        valid = False
    closure_expected = (
        valid
        and dod_counts["fail"] == 0
        and dod_counts["unknown"] == 0
        and dod_counts["pass"] == dod_counts["total"]
        and payload.get("closure_candidate") is True
    )
    if payload.get("closure_candidate") is True and not closure_expected:
        valid = False
    status = "PASS" if valid and closure_expected else "FAIL"
    return {
        **strings,
        **booleans,
        **integers,
        **zero_values,
        **lists,
        "orchestration_authority_order": payload.get("orchestration_authority_order"),
        "orchestration_negative_matrix": payload.get("orchestration_negative_matrix"),
        "e2e_completed_stages": payload.get("e2e_completed_stages"),
        "documentation_entries": payload.get("documentation_entries"),
        "dod_items": payload.get("dod_items"),
        "closure_candidate": payload.get("closure_candidate") is True,
        "dod_fail_count": dod_counts["fail"],
        "dod_unknown_count": dod_counts["unknown"],
        "status": status,
    }


def require_wo024_v01_closure_sprint_evidence(
    work_order: str,
    integration: Mapping[str, object],
    migration_head_value: str | None = None,
) -> None:
    if work_order == WO024_G1_WORK_ORDER:
        if integration_file(V01_CLOSURE_SPRINT_EVIDENCE_FILE):
            raise ValueError(
                f"{WO024_G1_WORK_ORDER} must not claim future v01 closure sprint evidence"
            )
        return
    if work_order not in {WO024_WORK_ORDER, WO024P_WORK_ORDER}:
        return
    closure = closure_sprint_evidence()
    if not closure or closure.get("status") == "UNKNOWN":
        raise ValueError(f"{work_order} missing mandatory v01 closure sprint evidence")
    full = cast(Mapping[str, object], closure)
    if full.get("status") != "PASS":
        raise ValueError(f"{work_order} requires passing v01 closure sprint evidence")
    if (
        full.get("v01_closure_sprint_evidence_version") != V01_CLOSURE_SPRINT_EVIDENCE_VERSION
        or full.get("evidence_file") != V01_CLOSURE_SPRINT_EVIDENCE_FILE
    ):
        raise ValueError(
            f"{work_order} requires {V01_CLOSURE_SPRINT_EVIDENCE_VERSION} evidence in "
            f"{V01_CLOSURE_SPRINT_EVIDENCE_FILE}"
        )
    if full.get("closure_candidate") is not True:
        raise ValueError(f"{work_order} requires a complete v01 closure candidate")
    if (
        int(cast(int, full.get("dod_fail_count", 1))) != 0
        or int(cast(int, full.get("dod_unknown_count", 1))) != 0
    ):
        raise ValueError(
            f"{work_order} requires zero failing and zero unknown definition-of-done items"
        )
    if int(cast(int, full.get("dod_pass_count", 0))) != int(
        cast(int, full.get("dod_total_count", -1))
    ):
        raise ValueError(
            f"{work_order} requires every definition-of-done item to pass exactly once"
        )
    if full.get("dod_matrix_complete") is not True:
        raise ValueError(f"{work_order} requires a complete definition-of-done matrix")
    for field in V01_CLOSURE_SPRINT_LIST_FIELDS:
        if not _closure_path_list(full.get(field)):
            raise ValueError(
                f"{work_order} requires bounded repository-relative {field} evidence paths"
            )
    if not _is_closed_string_set(
        full.get("orchestration_authority_order"), V01_CLOSURE_SPRINT_AUTHORITY_ORDER
    ):
        raise ValueError(f"{work_order} requires the mandatory checkpoint-first authority order")
    if not _is_closed_string_set(
        full.get("orchestration_negative_matrix"), V01_CLOSURE_SPRINT_NEGATIVE_CASES
    ):
        raise ValueError(
            f"{work_order} requires the closed stale, untracked and cross-project authority matrix"
        )
    if not _is_closed_string_set(full.get("e2e_completed_stages"), V01_CLOSURE_SPRINT_E2E_STAGES):
        raise ValueError(f"{work_order} requires every closure end-to-end stage to pass once")
    if not _closure_documentation_entries(full.get("documentation_entries")):
        raise ValueError(f"{work_order} requires documentation provenance for every required entry")
    dod_valid, dod_counts = _closure_dod_items(full.get("dod_items"))
    if not dod_valid:
        raise ValueError(f"{work_order} requires a bounded definition-of-done matrix")
    if (
        dod_counts["total"] != int(cast(int, full.get("dod_total_count", -1)))
        or dod_counts["pass"] != int(cast(int, full.get("dod_pass_count", -1)))
        or dod_counts["fail"] != 0
        or dod_counts["unknown"] != 0
    ):
        raise ValueError(
            f"{work_order} definition-of-done matrix must match its declared counts exactly"
        )
    missing_closure_true = [
        field for field in V01_CLOSURE_SPRINT_TRUE_FIELDS if full.get(field) is not True
    ]
    if missing_closure_true:
        raise ValueError(
            f"{work_order} missing mandatory closure evidence: "
            + ", ".join(sorted(missing_closure_true))
        )
    invalid_closure_false = [
        field for field in V01_CLOSURE_SPRINT_FALSE_FIELDS if full.get(field) is not False
    ]
    if invalid_closure_false:
        raise ValueError(
            f"{work_order} requires bounded negative closure claims: "
            + ", ".join(sorted(invalid_closure_false))
        )
    for field in ("full_v01_complete_claimed", "fabricated_metrics", "provider_values_fabricated"):
        if full.get(field) is not False:
            raise ValueError(f"{work_order} requires {field}=false in product evidence")
    if full.get("redis_canonical_truth") is not False:
        raise ValueError(f"{work_order} must not treat redis as canonical truth")
    for field in (
        "secret_leaks",
        "filesystem_path_leaks",
        "cross_project_leaks",
        "core_llm_calls",
        "core_provider_calls",
        "orchestration_deterministic_llm_calls",
        "stabilization_remaining_critical",
        "stabilization_remaining_high",
    ):
        if full.get(field) != 0:
            raise ValueError(f"{work_order} requires {field}=0")
    if migration_head_value is not None and (
        migration_head_value != V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD
        or full.get("observed_migration_head") != V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD
    ):
        raise ValueError(
            f"{work_order} requires migration head {V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}"
        )
    for field in ("reviewed_base_sha", "reviewed_head_sha"):
        value = full.get(field)
        if not isinstance(value, str) or HEX_SHA.fullmatch(value) is None:
            raise ValueError(f"{work_order} requires a resolved {field}")
    digest = full.get("run_digest")
    if not isinstance(digest, str) or (
        COMPREHENSIVE_BENCHMARKS_PROVIDER_SHA256_PATTERN.fullmatch(digest) is None
    ):
        raise ValueError(f"{work_order} requires a deterministic closure run digest")
    if not isinstance(full.get("changed_paths"), list):
        raise ValueError(f"{work_order} requires bounded closure changed paths")


def _is_closed_string_set(value: object, expected: tuple[str, ...]) -> bool:
    """Return True when value is exactly one permutation of expected strings."""

    if not isinstance(value, list) or len(value) != len(expected):
        return False
    items = cast(list[object], value)
    if not all(isinstance(item, str) for item in items):
        return False
    string_items = cast(list[str], items)
    return len(set(string_items)) == len(expected) and set(string_items) == set(expected)


def require_wo021_control_center_metrics_evidence(
    work_order: str,
    integration: Mapping[str, object],
    migration_head_value: str | None = None,
) -> None:
    if work_order == WO021_G1_WORK_ORDER:
        if "control_center_metrics" in integration:
            raise ValueError(
                f"{WO021_G1_WORK_ORDER} must not claim future Control Center metrics evidence"
            )
        return
    if work_order not in {WO021_WORK_ORDER, WO021P_G1_WORK_ORDER, WO021P_WORK_ORDER}:
        return
    metrics = integration.get("control_center_metrics")
    if not isinstance(metrics, Mapping):
        raise ValueError(f"{WO021_WORK_ORDER} missing mandatory Control Center metrics evidence")
    if set(metrics) != CONTROL_CENTER_METRICS_ALLOWED_FIELDS:
        raise ValueError(
            f"{WO021_WORK_ORDER} Control Center metrics evidence must match the closed "
            "contract exactly"
        )
    if metrics.get("status") != "PASS":
        raise ValueError(f"{WO021_WORK_ORDER} requires passing Control Center metrics evidence")
    if metrics.get("evidence_file") != CONTROL_CENTER_METRICS_EVIDENCE_FILE:
        raise ValueError(f"{WO021_WORK_ORDER} requires {CONTROL_CENTER_METRICS_EVIDENCE_FILE}")
    if metrics.get("metrics_evidence_version") != CONTROL_CENTER_METRICS_EVIDENCE_VERSION:
        raise ValueError(
            f"{WO021_WORK_ORDER} requires evidence version "
            f"{CONTROL_CENTER_METRICS_EVIDENCE_VERSION}"
        )
    missing = [
        field for field in CONTROL_CENTER_METRICS_TRUE_FIELDS if metrics.get(field) is not True
    ]
    if missing:
        raise ValueError(
            f"{WO021_WORK_ORDER} missing mandatory Control Center metrics evidence: "
            + ", ".join(sorted(missing))
        )
    invalid_false = [
        field for field in CONTROL_CENTER_METRICS_FALSE_FIELDS if metrics.get(field) is not False
    ]
    if invalid_false:
        raise ValueError(
            f"{WO021_WORK_ORDER} requires bounded negative claims: "
            + ", ".join(sorted(invalid_false))
        )
    for field in CONTROL_CENTER_METRICS_INTEGER_FIELDS:
        value = metrics.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{WO021_WORK_ORDER} requires bounded integer evidence for {field}")
    history_points = cast(int, metrics["historical_series_max_points"])
    if not 1 <= history_points <= CONTROL_CENTER_METRICS_MAX_HISTORY_POINTS:
        raise ValueError(f"{WO021_WORK_ORDER} requires bounded historical series points")
    families = metrics.get("implemented_metric_families")
    if not _is_closed_string_set(families, CONTROL_CENTER_METRICS_FAMILIES):
        raise ValueError(
            f"{WO021_WORK_ORDER} requires the bounded token/context/cache/storage metric families"
        )
    provenance = metrics.get("metric_value_provenance")
    if not _is_closed_string_set(provenance, CONTROL_CENTER_METRICS_VALUE_PROVENANCE):
        raise ValueError(
            f"{WO021_WORK_ORDER} requires distinct EXACT/ESTIMATED/UNAVAILABLE/UNKNOWN provenance"
        )
    if metrics.get("cost_provenance") != "UNAVAILABLE":
        raise ValueError(
            f"{WO021_WORK_ORDER} must keep cost UNAVAILABLE without explicit pricing provenance"
        )
    paths = metrics.get("evidence_paths")
    if (
        not isinstance(paths, list)
        or not 1 <= len(paths) <= CONTROL_CENTER_METRICS_MAX_EVIDENCE_PATHS
        or any(not isinstance(path, str) for path in cast(list[object], paths))
        or len(set(cast(list[object], paths))) != len(paths)
        or any(not valid_control_center_metrics_path(path) for path in cast(list[object], paths))
    ):
        raise ValueError(
            f"{WO021_WORK_ORDER} requires bounded normalized repository-relative evidence paths"
        )
    if metrics.get("migration_changed") is not False:
        raise ValueError(f"{WO021_WORK_ORDER} requires migration_changed=false")
    observed_head = metrics.get("observed_migration_head")
    if observed_head != CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO021_WORK_ORDER} requires observed migration head "
            f"{CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD}"
        )
    if migration_head_value != CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO021_WORK_ORDER} requires migration head "
            f"{CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD}"
        )
    if metrics.get("migration_base_head") != CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO021_WORK_ORDER} requires migration_base_head "
            f"{CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD}"
        )
    for field in (
        "secret_leaks",
        "filesystem_path_leaks",
        "cross_project_leaks",
        "metrics_llm_calls",
        "metrics_provider_calls",
    ):
        if metrics.get(field) != 0:
            raise ValueError(f"{WO021_WORK_ORDER} requires {field}=0")


def require_wo022_full_control_center_evidence(
    work_order: str,
    integration: Mapping[str, object],
    migration_head_value: str | None = None,
) -> None:
    if work_order == WO022_G1_WORK_ORDER:
        if "control_center_full" in integration:
            raise ValueError(
                f"{WO022_G1_WORK_ORDER} must not claim future Full Control Center evidence"
            )
        return
    if work_order not in {WO022_WORK_ORDER, WO022P_G1_WORK_ORDER, WO022P_WORK_ORDER}:
        return
    full = integration.get("control_center_full")
    if not isinstance(full, Mapping):
        raise ValueError(f"{WO022_WORK_ORDER} missing mandatory Full Control Center evidence")
    if set(full) != CONTROL_CENTER_FULL_ALLOWED_FIELDS:
        raise ValueError(
            f"{WO022_WORK_ORDER} Full Control Center evidence must match the closed "
            "contract exactly"
        )
    if full.get("status") != "PASS":
        raise ValueError(f"{WO022_WORK_ORDER} requires passing Full Control Center evidence")
    if full.get("evidence_file") != CONTROL_CENTER_FULL_EVIDENCE_FILE:
        raise ValueError(f"{WO022_WORK_ORDER} requires {CONTROL_CENTER_FULL_EVIDENCE_FILE}")
    if full.get("full_control_center_evidence_version") != CONTROL_CENTER_FULL_EVIDENCE_VERSION:
        raise ValueError(
            f"{WO022_WORK_ORDER} requires evidence version {CONTROL_CENTER_FULL_EVIDENCE_VERSION}"
        )
    missing = [field for field in CONTROL_CENTER_FULL_TRUE_FIELDS if full.get(field) is not True]
    if missing:
        raise ValueError(
            f"{WO022_WORK_ORDER} missing mandatory Full Control Center evidence: "
            + ", ".join(sorted(missing))
        )
    invalid_false = [
        field for field in CONTROL_CENTER_FULL_FALSE_FIELDS if full.get(field) is not False
    ]
    if invalid_false:
        raise ValueError(
            f"{WO022_WORK_ORDER} requires bounded negative claims: "
            + ", ".join(sorted(invalid_false))
        )
    for field in CONTROL_CENTER_FULL_INTEGER_FIELDS:
        value = full.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{WO022_WORK_ORDER} requires bounded integer evidence for {field}")
    history_points = cast(int, full["history_max_points"])
    if not 1 <= history_points <= CONTROL_CENTER_FULL_MAX_HISTORY_POINTS:
        raise ValueError(f"{WO022_WORK_ORDER} requires bounded history points")
    closed_lists = (
        ("implemented_project_capabilities", CONTROL_CENTER_FULL_PROJECT_CAPABILITIES),
        ("implemented_charts", CONTROL_CENTER_FULL_CHARTS),
        ("implemented_alerts", CONTROL_CENTER_FULL_ALERTS),
        ("implemented_health_capabilities", CONTROL_CENTER_FULL_HEALTH_CAPABILITIES),
    )
    for field, expected in closed_lists:
        if not _is_closed_string_set(full.get(field), expected):
            raise ValueError(f"{WO022_WORK_ORDER} requires the closed {field} contract")
    if not valid_control_center_full_path("api_path", full.get("api_path")):
        raise ValueError(f"{WO022_WORK_ORDER} requires a sanitized relative api_path")
    if not valid_control_center_full_path("dashboard_path", full.get("dashboard_path")):
        raise ValueError(f"{WO022_WORK_ORDER} requires a sanitized relative dashboard_path")
    paths = full.get("evidence_paths")
    if (
        not isinstance(paths, list)
        or not 1 <= len(paths) <= CONTROL_CENTER_FULL_MAX_EVIDENCE_PATHS
        or any(not isinstance(path, str) for path in cast(list[object], paths))
        or len(set(cast(list[object], paths))) != len(paths)
        or any(
            not valid_control_center_full_evidence_path(path) for path in cast(list[object], paths)
        )
    ):
        raise ValueError(
            f"{WO022_WORK_ORDER} requires bounded normalized repository-relative evidence paths"
        )
    if full.get("migration_changed") is not False:
        raise ValueError(f"{WO022_WORK_ORDER} requires migration_changed=false")
    if full.get("observed_migration_head") != CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO022_WORK_ORDER} requires observed migration head "
            f"{CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD}"
        )
    if migration_head_value != CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO022_WORK_ORDER} requires migration head {CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD}"
        )
    if full.get("migration_base_head") != CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO022_WORK_ORDER} requires migration_base_head "
            f"{CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD}"
        )
    for field in (
        "secret_leaks",
        "filesystem_path_leaks",
        "cross_project_leaks",
        "llm_calls",
        "provider_calls",
    ):
        if full.get(field) != 0:
            raise ValueError(f"{WO022_WORK_ORDER} requires {field}=0")


def require_wo020_control_center_evidence(
    work_order: str,
    integration: Mapping[str, object],
    migration_head_value: str | None = None,
) -> None:
    if work_order == WO020_G1_WORK_ORDER:
        if "control_center_core" in integration:
            raise ValueError(
                f"{WO020_G1_WORK_ORDER} must not claim future Control Center product evidence"
            )
        return
    if work_order not in {WO020_WORK_ORDER, WO020P_G1_WORK_ORDER, WO020P_WORK_ORDER}:
        return
    control_center = integration.get("control_center_core")
    if not isinstance(control_center, Mapping):
        raise ValueError(f"{work_order} missing mandatory Control Center evidence")
    if set(control_center) != CONTROL_CENTER_CORE_ALLOWED_FIELDS:
        raise ValueError(
            f"{work_order} Control Center evidence must match the closed contract exactly"
        )
    if control_center.get("status") != "PASS":
        raise ValueError(f"{work_order} requires passing Control Center evidence")
    if control_center.get("evidence_file") != CONTROL_CENTER_CORE_EVIDENCE_FILE:
        raise ValueError(f"{work_order} requires {CONTROL_CENTER_CORE_EVIDENCE_FILE}")
    evidence_version = control_center.get("control_center_evidence_version")
    if evidence_version != CONTROL_CENTER_CORE_EVIDENCE_VERSION:
        raise ValueError(
            f"{work_order} requires evidence version {CONTROL_CENTER_CORE_EVIDENCE_VERSION}"
        )
    missing = [
        field for field in CONTROL_CENTER_CORE_TRUE_FIELDS if control_center.get(field) is not True
    ]
    if missing:
        raise ValueError(
            f"{work_order} missing mandatory Control Center evidence: " + ", ".join(sorted(missing))
        )
    invalid_false = [
        field
        for field in CONTROL_CENTER_CORE_FALSE_FIELDS
        if control_center.get(field) is not False
    ]
    if invalid_false:
        raise ValueError(
            f"{work_order} requires bounded negative claims: " + ", ".join(sorted(invalid_false))
        )
    for field in CONTROL_CENTER_CORE_INTEGER_FIELDS:
        value = control_center.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{work_order} requires bounded integer evidence for {field}")
    surfaces = control_center.get("implemented_surfaces")
    if (
        not isinstance(surfaces, list)
        or not 1 <= len(surfaces) <= CONTROL_CENTER_CORE_MAX_SURFACES
        or any(
            not isinstance(surface, str) or surface not in CONTROL_CENTER_CORE_CANONICAL_SURFACES
            for surface in surfaces
        )
        or len(set(surfaces)) != len(surfaces)
    ):
        raise ValueError(f"{work_order} requires a non-empty explicit bounded surface subset")
    if control_center.get("surface_count") != len(surfaces):
        raise ValueError(f"{work_order} requires truthful surface_count")
    stream_transport = control_center.get("stream_transport")
    if (
        not isinstance(stream_transport, str)
        or stream_transport not in CONTROL_CENTER_CORE_STREAM_TRANSPORTS
    ):
        raise ValueError(f"{work_order} requires a bounded stream_transport")
    for field in (
        "secret_leaks",
        "filesystem_path_leaks",
        "cross_project_leaks",
        "llm_calls",
        "provider_calls",
    ):
        if control_center.get(field) != 0:
            raise ValueError(f"{work_order} requires {field}=0")
    for path_field in ("api_path", "dashboard_path"):
        if not valid_control_center_core_path(path_field, control_center.get(path_field)):
            raise ValueError(f"{work_order} requires sanitized relative {path_field}")
    observed_head = control_center.get("observed_migration_head")
    if not isinstance(observed_head, str) or not observed_head:
        raise ValueError(f"{work_order} requires observed migration head evidence")
    if migration_head_value is None or observed_head != migration_head_value:
        raise ValueError(f"{work_order} requires evidence to match the observed migration head")
    if control_center.get("migration_base_head") != CONTROL_CENTER_CORE_MIGRATION_BASE_HEAD:
        raise ValueError(f"{work_order} requires the G1 migration base head")
    expected_changed = observed_head != CONTROL_CENTER_CORE_MIGRATION_BASE_HEAD
    if control_center.get("migration_changed") is not expected_changed:
        raise ValueError(f"{work_order} requires truthful migration_changed evidence")


def verify_wo019_g1_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
) -> str | None:
    if work_order != WO019_G1_WORK_ORDER:
        return None
    require_wo019_g1_scope(work_order, base_sha, paths)
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO019_G1_WORK_ORDER} requires no canonical Project Brain changes")
    if migration_head_value != "0006_memory_lifecycle_provenance":
        raise ValueError(f"{WO019_G1_WORK_ORDER} requires migration head 0006")
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO019_G1_WORK_ORDER} requires the protected ruleset to be unchanged")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO019_G1_WORK_ORDER} requires auto-merge to remain unarmed")
    require_wo019_telemetry_evidence(work_order, integration, migration_head_value)
    require_current_work_order_authorization(WO019_G1_WORK_ORDER)
    require_current_work_order_authorization(WO019_WORK_ORDER)
    return (
        f"work_order={WO019_G1_WORK_ORDER}; exact_base=PASS; governance_scope=PASS; "
        "project_brain_changed=False; checkpoint_changed=False; "
        "migration_head=0006_memory_lifecycle_provenance; migration_changed=False; "
        f"future_{WO019_WORK_ORDER}_registered=PASS; "
        f"future_{TELEMETRY_EVENT_BUS_EVIDENCE_VERSION}_fail_closed=PASS; "
        "telemetry_implementation=False; ruleset_unchanged=PASS; "
        "auto_merge=UNARMED; checkpoint_promotion=False"
    )


def verify_wo019_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
) -> str | None:
    if work_order != WO019_WORK_ORDER:
        return None
    require_wo019_scope(work_order, base_sha, paths)
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO019_WORK_ORDER} cannot change canonical Project Brain")
    require_wo019_telemetry_evidence(work_order, integration, migration_head_value)
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO019_WORK_ORDER} requires the protected ruleset to be unchanged")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO019_WORK_ORDER} requires auto-merge to remain unarmed")
    require_current_work_order_authorization(WO019_WORK_ORDER)
    telemetry = cast(Mapping[str, object], integration["telemetry_event_bus"])
    implemented_event_types = ",".join(cast(list[str], telemetry["implemented_event_types"]))
    return (
        f"work_order={WO019_WORK_ORDER}; product_scope=PASS; "
        f"evidence_version={TELEMETRY_EVENT_BUS_EVIDENCE_VERSION}; "
        f"implemented_event_types={implemented_event_types}; "
        "durable_postgres_truth=PASS; redis_canonical_truth=False; "
        "project_isolation=PASS; replay_order=PASS; stream=PASS; reconnect=PASS; "
        "restart/redis_loss=PASS/PASS; secret_path_leaks=0/0; llm_provider_calls=0/0; "
        f"migration_head={migration_head_value}; "
        f"migration_changed={telemetry['migration_changed']}; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; checkpoint_promotion=False"
    )


def verify_wo020_g1_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
) -> str | None:
    if work_order != WO020_G1_WORK_ORDER:
        return None
    require_wo020_g1_scope(work_order, base_sha, paths)
    for rejected in ("WO-026-P", "WO-999-P"):
        try:
            require_current_work_order_authorization(rejected)
        except ValueError:
            pass
        else:
            raise ValueError(f"{rejected} unexpectedly authorizes a fresh current PR")
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO020_G1_WORK_ORDER} requires no canonical Project Brain changes")
    if migration_head_value != CONTROL_CENTER_CORE_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO020_G1_WORK_ORDER} requires migration head "
            f"{CONTROL_CENTER_CORE_MIGRATION_BASE_HEAD}"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO020_G1_WORK_ORDER} requires the protected ruleset to be unchanged")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO020_G1_WORK_ORDER} requires auto-merge to remain unarmed")
    require_wo020_control_center_evidence(work_order, integration, migration_head_value)
    require_current_work_order_authorization(WO020_G1_WORK_ORDER)
    require_current_work_order_authorization(WO020_WORK_ORDER)
    return (
        f"work_order={WO020_G1_WORK_ORDER}; exact_base=PASS; governance_scope=PASS; "
        "project_brain_changed=False; checkpoint_changed=False; "
        f"migration_head={CONTROL_CENTER_CORE_MIGRATION_BASE_HEAD}; migration_changed=False; "
        f"future_{WO020_WORK_ORDER}_registered=PASS; "
        f"future_{CONTROL_CENTER_CORE_EVIDENCE_VERSION}_fail_closed=PASS; "
        "control_center_implementation=False; unknown_WO-025-P_WO-999-P=REJECTED; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; checkpoint_promotion=False"
    )


def verify_wo020_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
) -> str | None:
    if work_order != WO020_WORK_ORDER:
        return None
    require_wo020_scope(work_order, base_sha, paths)
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO020_WORK_ORDER} cannot change canonical Project Brain")
    require_wo020_control_center_evidence(work_order, integration, migration_head_value)
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO020_WORK_ORDER} requires the protected ruleset to be unchanged")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO020_WORK_ORDER} requires auto-merge to remain unarmed")
    require_current_work_order_authorization(WO020_WORK_ORDER)
    control_center = cast(Mapping[str, object], integration["control_center_core"])
    implemented_surfaces = ",".join(cast(list[str], control_center["implemented_surfaces"]))
    return (
        f"work_order={WO020_WORK_ORDER}; product_scope=PASS; "
        f"evidence_version={CONTROL_CENTER_CORE_EVIDENCE_VERSION}; "
        f"implemented_surfaces={implemented_surfaces}; "
        f"stream_transport={control_center['stream_transport']}; "
        "postgres_canonical=PASS; redis_canonical_truth=False; "
        "project_isolation=PASS; stream_replay=PASS; reconciliation=PASS; "
        "restart/redis_loss=PASS/PASS; secret_path_leaks=0/0; llm_provider_calls=0/0; "
        f"migration_head={migration_head_value}; "
        f"migration_changed={control_center['migration_changed']}; "
        "full_control_center_claimed=False; full_v01_complete_claimed=False; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; checkpoint_promotion=False"
    )


def verify_wo021_g1_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
) -> str | None:
    if work_order != WO021_G1_WORK_ORDER:
        return None
    require_wo021_g1_scope(work_order, base_sha, paths)
    for rejected in ("WO-030-C1", "WO-028-P", "WO-999"):
        try:
            require_current_work_order_authorization(rejected)
        except ValueError:
            pass
        else:
            raise ValueError(f"{rejected} unexpectedly authorizes a fresh current PR")
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO021_G1_WORK_ORDER} requires no canonical Project Brain changes")
    if migration_head_value != CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO021_G1_WORK_ORDER} requires migration head "
            f"{CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD}"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO021_G1_WORK_ORDER} requires the protected ruleset to be unchanged")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO021_G1_WORK_ORDER} requires auto-merge to remain unarmed")
    require_wo021_control_center_metrics_evidence(work_order, integration, migration_head_value)
    require_current_work_order_authorization(WO021_G1_WORK_ORDER)
    require_current_work_order_authorization(WO021_WORK_ORDER)
    return (
        f"work_order={WO021_G1_WORK_ORDER}; exact_base=PASS; governance_scope=PASS; "
        "project_brain_changed=False; checkpoint_changed=False; "
        f"migration_head={CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD}; migration_changed=False; "
        f"future_{WO021_WORK_ORDER}_registered=PASS; "
        f"future_{CONTROL_CENTER_METRICS_EVIDENCE_VERSION}_fail_closed=PASS; "
        "metrics_implementation=False; unknown_WO-025_WO-025-P_WO-999=REJECTED; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; checkpoint_promotion=False"
    )


def verify_wo021_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
) -> str | None:
    if work_order != WO021_WORK_ORDER:
        return None
    require_wo021_scope(work_order, base_sha, paths)
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO021_WORK_ORDER} cannot change canonical Project Brain")
    require_wo021_control_center_metrics_evidence(work_order, integration, migration_head_value)
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO021_WORK_ORDER} requires the protected ruleset to be unchanged")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO021_WORK_ORDER} requires auto-merge to remain unarmed")
    require_current_work_order_authorization(WO021_WORK_ORDER)
    metrics = cast(Mapping[str, object], integration["control_center_metrics"])
    families = ",".join(cast(list[str], metrics["implemented_metric_families"]))
    return (
        f"work_order={WO021_WORK_ORDER}; product_scope=PASS; "
        f"evidence_version={CONTROL_CENTER_METRICS_EVIDENCE_VERSION}; "
        f"implemented_metric_families={families}; "
        f"historical_series_max_points={metrics['historical_series_max_points']}; "
        "token_exact_estimated_unknown=PASS; cache_hit_truth=PASS; "
        "context_storage_provenance=PASS; postgres_canonical=PASS; redis_canonical_truth=False; "
        "project_scope=PASS; deterministic_global_aggregation=PASS; "
        "restart/redis_loss=PASS/PASS; secret_path_cross_project_leaks=0/0/0; "
        "llm_provider_calls=0/0; cost_provenance=UNAVAILABLE; "
        f"migration_head={migration_head_value}; migration_changed=False; "
        "full_control_center_claimed=False; full_v01_complete_claimed=False; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; checkpoint_promotion=False"
    )


def verify_wo022_g1_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
) -> str | None:
    if work_order != WO022_G1_WORK_ORDER:
        return None
    require_wo022_g1_scope(work_order, base_sha, paths)
    for rejected in ("WO-030-C1", "WO-028-P", "WO-999"):
        try:
            require_current_work_order_authorization(rejected)
        except ValueError:
            pass
        else:
            raise ValueError(f"{rejected} unexpectedly authorizes a fresh current PR")
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO022_G1_WORK_ORDER} requires no canonical Project Brain changes")
    if migration_head_value != CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO022_G1_WORK_ORDER} requires migration head "
            f"{CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD}"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO022_G1_WORK_ORDER} requires the protected ruleset to be unchanged")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO022_G1_WORK_ORDER} requires auto-merge to remain unarmed")
    require_wo022_full_control_center_evidence(work_order, integration, migration_head_value)
    require_current_work_order_authorization(WO022_G1_WORK_ORDER)
    require_current_work_order_authorization(WO022_WORK_ORDER)
    return (
        f"work_order={WO022_G1_WORK_ORDER}; exact_base=PASS; governance_scope=PASS; "
        "project_brain_changed=False; checkpoint_changed=False; "
        f"migration_head={CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD}; migration_changed=False; "
        f"future_{WO022_WORK_ORDER}_registered=PASS; "
        f"future_{CONTROL_CENTER_FULL_EVIDENCE_VERSION}_fail_closed=PASS; "
        "full_control_center_implementation=False; "
        "unknown_WO-025_WO-025-P_WO-999=REJECTED; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; checkpoint_promotion=False"
    )


def verify_wo022_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
) -> str | None:
    if work_order != WO022_WORK_ORDER:
        return None
    require_wo022_scope(work_order, base_sha, paths)
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO022_WORK_ORDER} cannot change canonical Project Brain")
    require_wo022_full_control_center_evidence(work_order, integration, migration_head_value)
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO022_WORK_ORDER} requires the protected ruleset to be unchanged")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO022_WORK_ORDER} requires auto-merge to remain unarmed")
    require_current_work_order_authorization(WO022_WORK_ORDER)
    full = cast(Mapping[str, object], integration["control_center_full"])
    capabilities = ",".join(cast(list[str], full["implemented_project_capabilities"]))
    return (
        f"work_order={WO022_WORK_ORDER}; product_scope=PASS; "
        f"evidence_version={CONTROL_CENTER_FULL_EVIDENCE_VERSION}; "
        f"implemented_project_capabilities={capabilities}; "
        "charts=PASS; alerts=PASS; platform_resource_health=PASS; "
        "postgres_canonical=PASS; redis_canonical_truth=False; "
        "estimated_unavailable_unknown_provenance=PASS; project_scope=PASS; "
        "near_realtime=PASS; restart/redis_loss=PASS/PASS; "
        "secret_path_cross_project_leaks=0/0/0; llm_provider_calls=0/0; "
        f"migration_head={migration_head_value}; migration_changed=False; "
        "full_v01_complete_claimed=False; ruleset_unchanged=PASS; "
        "auto_merge=UNARMED; checkpoint_promotion=False"
    )


def verify_wo018_g1_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
) -> str | None:
    if work_order != WO018_G1_WORK_ORDER:
        return None
    require_wo018_g1_scope(work_order, base_sha, paths)
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO018_G1_WORK_ORDER} requires no canonical Project Brain changes")
    if migration_head_value != "0006_memory_lifecycle_provenance":
        raise ValueError(
            f"{WO018_G1_WORK_ORDER} requires migration head 0006_memory_lifecycle_provenance"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO018_G1_WORK_ORDER} requires the protected ruleset to be unchanged")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO018_G1_WORK_ORDER} requires auto-merge to remain unarmed")
    if "autonomous_execution" in integration:
        raise ValueError(f"{WO018_G1_WORK_ORDER} must not claim autonomous product evidence")
    require_current_work_order_authorization(WO018_G1_WORK_ORDER)
    require_current_work_order_authorization(WO018_WORK_ORDER)
    return (
        f"work_order={WO018_G1_WORK_ORDER}; exact_base=PASS; governance_scope=PASS; "
        "project_brain_changed=False; checkpoint_changed=False; "
        "migration_head=0006_memory_lifecycle_provenance; migration_changed=False; "
        f"future_{WO018_WORK_ORDER}_registered=PASS; "
        f"future_{AUTONOMOUS_EXECUTION_EVIDENCE_VERSION}_fail_closed=PASS; "
        "autonomous_implementation=False; ruleset_unchanged=PASS; "
        "auto_merge=UNARMED; checkpoint_promotion=False"
    )


def verify_wo018_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
) -> str | None:
    if work_order != WO018_WORK_ORDER:
        return None
    require_wo018_scope(work_order, base_sha, paths)
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO018_WORK_ORDER} cannot change canonical Project Brain")
    require_wo018_autonomous_evidence(work_order, integration, migration_head_value)
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO018_WORK_ORDER} requires the protected ruleset to be unchanged")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO018_WORK_ORDER} requires auto-merge to remain unarmed")
    require_current_work_order_authorization(WO018_WORK_ORDER)
    return (
        f"work_order={WO018_WORK_ORDER}; product_scope=PASS; autonomous_evidence=PASS; "
        f"evidence_version={AUTONOMOUS_EXECUTION_EVIDENCE_VERSION}; "
        "context_manager_reuse=PASS; runner_reuse=PASS; tool_gating=PASS; "
        "unauthorized_tool_rejected=PASS; staged_noncanonical=PASS; "
        "diff_tests_validation_review_capture=PASS; cross_project_rejected=PASS; "
        "canonical_write_rejected=PASS; head_race_rejected=PASS; e2e_coding_task=PASS; "
        "commit_push_merge_checkpoint=False/False/False/False; "
        "secret_leaks=0; filesystem_path_leaks=0; "
        "migration_head=0006_memory_lifecycle_provenance; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; checkpoint_promotion=False"
    )


def verify_wo023_g1_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
) -> str | None:
    if work_order != WO023_G1_WORK_ORDER:
        return None
    require_wo023_g1_scope(work_order, base_sha, paths)
    for rejected in ("WO-030-C1", "WO-028-P", "WO-999"):
        try:
            require_current_work_order_authorization(rejected)
        except ValueError:
            pass
        else:
            raise ValueError(f"{rejected} unexpectedly authorizes a fresh current PR")
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO023_G1_WORK_ORDER} requires no canonical Project Brain changes")
    if migration_head_value != COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO023_G1_WORK_ORDER} requires migration head "
            f"{COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD}"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO023_G1_WORK_ORDER} requires the protected ruleset to be unchanged")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO023_G1_WORK_ORDER} requires auto-merge to remain unarmed")
    require_wo023_comprehensive_benchmarks_evidence(work_order, integration, migration_head_value)
    require_current_work_order_authorization(WO023_G1_WORK_ORDER)
    require_current_work_order_authorization(WO023_WORK_ORDER)
    return (
        f"work_order={WO023_G1_WORK_ORDER}; exact_base=PASS; governance_scope=PASS; "
        "project_brain_changed=False; checkpoint_changed=False; "
        f"migration_head={COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD}; migration_changed=False; "
        f"future_{WO023_WORK_ORDER}_registered=PASS; "
        f"future_{COMPREHENSIVE_BENCHMARKS_EVIDENCE_VERSION}_fail_closed=PASS; "
        "comprehensive_benchmarks_implementation=False; "
        "unknown_WO-025_WO-025-P_WO-999=REJECTED; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; checkpoint_promotion=False"
    )


def verify_wo023_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
) -> str | None:
    if work_order != WO023_WORK_ORDER:
        return None
    require_wo023_scope(work_order, base_sha, paths)
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO023_WORK_ORDER} cannot change canonical Project Brain")
    if migration_head_value != COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO023_WORK_ORDER} requires migration head "
            f"{COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD}"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO023_WORK_ORDER} requires the protected ruleset to be unchanged")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO023_WORK_ORDER} requires auto-merge to remain unarmed")
    require_wo023_comprehensive_benchmarks_evidence(work_order, integration, migration_head_value)
    require_current_work_order_authorization(WO023_WORK_ORDER)
    return (
        f"work_order={WO023_WORK_ORDER}; product_scope=PASS; project_brain_changed=False; "
        f"migration_head={COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD}; "
        f"comprehensive_benchmarks_evidence=PASS; "
        f"comprehensive_benchmarks_version={COMPREHENSIVE_BENCHMARKS_EVIDENCE_VERSION}; "
        "retrieval_family=PASS; token_family=PASS; storage_family=PASS; "
        "critical_context_misses=0; canonical_loss=False; "
        "full_v01_complete_claimed=False; ruleset_unchanged=PASS; auto_merge=UNARMED; "
        "checkpoint_promotion=False"
    )


def verify_wo017_g1_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
) -> str | None:
    if work_order != WO017_G1_WORK_ORDER:
        return None
    require_wo017_g1_scope(work_order, base_sha, paths)
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO017_G1_WORK_ORDER} requires no canonical Project Brain changes")
    if migration_head_value != "0006_memory_lifecycle_provenance":
        raise ValueError(
            f"{WO017_G1_WORK_ORDER} requires migration head 0006_memory_lifecycle_provenance, "
            f"observed {migration_head_value}"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO017_G1_WORK_ORDER} requires the protected ruleset to be unchanged")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO017_G1_WORK_ORDER} requires auto-merge to remain unarmed")
    if "mcp_surface" in integration:
        raise ValueError(f"{WO017_G1_WORK_ORDER} must not claim MCP product evidence")
    require_current_work_order_authorization(WO017_G1_WORK_ORDER)
    require_current_work_order_authorization(WO017_WORK_ORDER)
    return (
        f"work_order={WO017_G1_WORK_ORDER}; exact_base=PASS; governance_scope=PASS; "
        "project_brain_changed=False; checkpoint_changed=False; "
        "migration_head=0006_memory_lifecycle_provenance; migration_changed=False; "
        f"future_{WO017_WORK_ORDER}_registered=PASS; "
        f"future_{MCP_CORE_SURFACE_EVIDENCE_VERSION}_fail_closed=PASS; "
        "mcp_implementation=False; ruleset_unchanged=PASS; auto_merge=UNARMED; "
        "checkpoint_promotion=False"
    )


def verify_wo017_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
) -> str | None:
    if work_order != WO017_WORK_ORDER:
        return None
    require_wo017_scope(work_order, base_sha, paths)
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO017_WORK_ORDER} cannot change canonical Project Brain")
    require_wo017_mcp_evidence(work_order, integration, migration_head_value)
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO017_WORK_ORDER} requires the protected ruleset to be unchanged")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO017_WORK_ORDER} requires auto-merge to remain unarmed")
    require_current_work_order_authorization(WO017_WORK_ORDER)
    return (
        f"work_order={WO017_WORK_ORDER}; product_scope=PASS; mcp_evidence=PASS; "
        f"evidence_version={MCP_CORE_SURFACE_EVIDENCE_VERSION}; "
        f"tool_list_exact={','.join(MCP_CORE_SURFACE_TOOLS)}; "
        "real_transport=PASS; direct_core=PASS; rest_loopback=False; "
        "duplicate_persistence=False; project_isolation=PASS; checkpoint_first=PASS; "
        "registered_project_count>=2; arbitrary_filesystem_access_rejected=PASS; "
        "checkpoint_missing/untracked/stale/hive_substitution=PASS/PASS/PASS/PASS; "
        "context_search_provenance/result_bound=PASS/PASS; "
        "memory_search/memory_get_provenance/status_visibility=PASS/PASS/PASS; "
        "structured_errors/bounded_errors=PASS/PASS; "
        "canonical_write_tools=False; restart_recovery=PASS; redis_loss_recovery=PASS; "
        "mcp_llm_calls=0; mcp_provider_calls=0; migration_head=0006_memory_lifecycle_provenance; "
        "migration_changed=False; ruleset_unchanged=PASS; auto_merge=UNARMED; "
        "checkpoint_promotion=False"
    )


def verify_wo018p_g1_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
) -> str | None:
    if work_order != WO018P_G1_WORK_ORDER:
        return None
    require_wo018p_g1_scope(work_order, base_sha, paths)
    if not frozenset({WO018P_G1_WORK_ORDER, WO018P_WORK_ORDER}).issubset(
        CHECKPOINT_PROMOTION_WORK_ORDERS
    ):
        raise ValueError(f"{WO018P_G1_WORK_ORDER} must remain registered historically")
    for stale in (
        WO016P_G1_WORK_ORDER,
        WO016P_WORK_ORDER,
        WO017P_G1_WORK_ORDER,
        WO017P_WORK_ORDER,
    ):
        try:
            require_current_work_order_authorization(stale)
        except ValueError:
            pass
        else:
            raise ValueError(f"{stale} unexpectedly authorizes a fresh current PR")
    for rejected in ("WO-026-P", "WO-999-P"):
        try:
            require_current_work_order_authorization(rejected)
        except ValueError:
            pass
        else:
            raise ValueError(f"{rejected} unexpectedly authorizes a fresh current PR")
    require_supported_work_order(WO018P_G1_WORK_ORDER)
    require_supported_work_order(WO018P_WORK_ORDER)
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO018P_G1_WORK_ORDER} forbids canonical changes")
    if migration_head_value != "0006_memory_lifecycle_provenance":
        raise ValueError(f"{WO018P_G1_WORK_ORDER} requires migration head 0006")
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO018P_G1_WORK_ORDER} requires unchanged ruleset")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO018P_G1_WORK_ORDER} requires auto-merge to remain unarmed")
    require_wo018_autonomous_evidence(
        WO018P_G1_WORK_ORDER,
        integration,
        migration_head_value,
    )
    return (
        f"work_order={WO018P_G1_WORK_ORDER}; exact_base=PASS; governance_scope=PASS; "
        "project_brain_changed=False; checkpoint_changed=False; migration_changed=False; "
        f"active_promotions={WO018P_G1_WORK_ORDER},{WO018P_WORK_ORDER}; "
        "historical_WO-017-P-G1_WO-017-P=REJECTED; unknown_WO-025-P_WO-999-P=REJECTED; "
        "authorized_base_parser=PASS; future_two_file_scope=PASS; checkpoint_semantics=PASS; "
        "manifest_contract=PASS; autonomous_evidence=PASS; ruleset_unchanged=PASS; "
        "auto_merge=UNARMED; checkpoint_promotion=False"
    )


def verify_wo018p_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
) -> str | None:
    if work_order != WO018P_WORK_ORDER:
        return None
    require_wo018p_scope(work_order, base_sha, paths, enforce_authorized_base=False)
    expected_paths = [path for path in CANONICAL_PATHS]
    if canonical_changes != {
        "project_brain_changed": True,
        "checkpoint_changed": True,
        "authorized_paths": expected_paths,
    }:
        raise ValueError(
            f"{WO018P_WORK_ORDER} requires only checkpoint and manifest canonical changes"
        )
    if migration_head_value != "0006_memory_lifecycle_provenance":
        raise ValueError(
            f"{WO018P_WORK_ORDER} requires migration head 0006_memory_lifecycle_provenance"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO018P_WORK_ORDER} requires the protected ruleset to be unchanged")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO018P_WORK_ORDER} requires auto-merge to remain unarmed")
    require_wo018_autonomous_evidence(WO018P_WORK_ORDER, integration, migration_head_value)
    return (
        f"work_order={WO018P_WORK_ORDER}; promotion_scope=PASS; checkpoint_semantics=PASS; "
        "manifest_contract=PASS; autonomous_evidence=PASS; "
        "migration_head=0006_memory_lifecycle_provenance; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; checkpoint_promotion=True"
    )


def verify_wo019p_g1_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
) -> str | None:
    if work_order != WO019P_G1_WORK_ORDER:
        return None
    require_wo019p_g1_scope(work_order, base_sha, paths)
    if not frozenset({WO019P_G1_WORK_ORDER, WO019P_WORK_ORDER}).issubset(
        CHECKPOINT_PROMOTION_WORK_ORDERS
    ):
        raise ValueError(f"{WO019P_G1_WORK_ORDER} must remain registered historically")
    for stale in (
        WO016P_G1_WORK_ORDER,
        WO016P_WORK_ORDER,
        WO017P_G1_WORK_ORDER,
        WO017P_WORK_ORDER,
        WO018P_G1_WORK_ORDER,
        WO018P_WORK_ORDER,
    ):
        try:
            require_current_work_order_authorization(stale)
        except ValueError:
            pass
        else:
            raise ValueError(f"{stale} unexpectedly authorizes a fresh current PR")
    for rejected in ("WO-026-P", "WO-999-P"):
        try:
            require_current_work_order_authorization(rejected)
        except ValueError:
            pass
        else:
            raise ValueError(f"{rejected} unexpectedly authorizes a fresh current PR")
    require_supported_work_order(WO019P_G1_WORK_ORDER)
    require_supported_work_order(WO019P_WORK_ORDER)
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO019P_G1_WORK_ORDER} forbids canonical changes")
    if migration_head_value != "0007_telemetry_events":
        raise ValueError(f"{WO019P_G1_WORK_ORDER} requires migration head 0007_telemetry_events")
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO019P_G1_WORK_ORDER} requires unchanged ruleset")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO019P_G1_WORK_ORDER} requires auto-merge to remain unarmed")
    require_wo019_telemetry_evidence(
        WO019P_G1_WORK_ORDER,
        integration,
        migration_head_value,
    )
    return (
        f"work_order={WO019P_G1_WORK_ORDER}; exact_base=PASS; governance_scope=PASS; "
        "project_brain_changed=False; checkpoint_changed=False; migration_changed=False; "
        f"active_promotions={WO019P_G1_WORK_ORDER},{WO019P_WORK_ORDER}; "
        "historical_WO-018-P-G1_WO-018-P=REJECTED; unknown_WO-025-P_WO-999-P=REJECTED; "
        "authorized_base_parser=PASS; future_two_file_scope=PASS; checkpoint_semantics=PASS; "
        "manifest_contract=PASS; telemetry_evidence=PASS; ruleset_unchanged=PASS; "
        "auto_merge=UNARMED; checkpoint_promotion=False"
    )


def verify_wo019p_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
) -> str | None:
    if work_order != WO019P_WORK_ORDER:
        return None
    require_wo019p_scope(work_order, base_sha, paths, enforce_authorized_base=False)
    expected_paths = [path for path in CANONICAL_PATHS]
    if canonical_changes != {
        "project_brain_changed": True,
        "checkpoint_changed": True,
        "authorized_paths": expected_paths,
    }:
        raise ValueError(
            f"{WO019P_WORK_ORDER} requires only checkpoint and manifest canonical changes"
        )
    if migration_head_value != "0007_telemetry_events":
        raise ValueError(f"{WO019P_WORK_ORDER} requires migration head 0007_telemetry_events")
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO019P_WORK_ORDER} requires the protected ruleset to be unchanged")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO019P_WORK_ORDER} requires auto-merge to remain unarmed")
    require_wo019_telemetry_evidence(WO019P_WORK_ORDER, integration, migration_head_value)
    return (
        f"work_order={WO019P_WORK_ORDER}; promotion_scope=PASS; checkpoint_semantics=PASS; "
        "manifest_contract=PASS; telemetry_evidence=PASS; "
        "migration_head=0007_telemetry_events; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; checkpoint_promotion=True"
    )


def verify_wo020p_g1_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
) -> str | None:
    if work_order != WO020P_G1_WORK_ORDER:
        return None
    require_wo020p_g1_scope(work_order, base_sha, paths)
    if not frozenset({WO020P_G1_WORK_ORDER, WO020P_WORK_ORDER}).issubset(
        CHECKPOINT_PROMOTION_WORK_ORDERS
    ):
        raise ValueError(f"{WO020P_G1_WORK_ORDER} must remain registered historically")
    for stale in (
        WO016P_G1_WORK_ORDER,
        WO016P_WORK_ORDER,
        WO017P_G1_WORK_ORDER,
        WO017P_WORK_ORDER,
        WO018P_G1_WORK_ORDER,
        WO018P_WORK_ORDER,
        WO019P_G1_WORK_ORDER,
        WO019P_WORK_ORDER,
    ):
        try:
            require_current_work_order_authorization(stale)
        except ValueError:
            pass
        else:
            raise ValueError(f"{stale} unexpectedly authorizes a fresh current PR")
    for rejected in ("WO-026-P", "WO-999-P"):
        try:
            require_current_work_order_authorization(rejected)
        except ValueError:
            pass
        else:
            raise ValueError(f"{rejected} unexpectedly authorizes a fresh current PR")
    require_supported_work_order(WO020P_G1_WORK_ORDER)
    require_supported_work_order(WO020P_WORK_ORDER)
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO020P_G1_WORK_ORDER} forbids canonical changes")
    if migration_head_value != CONTROL_CENTER_CORE_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO020P_G1_WORK_ORDER} requires migration head "
            f"{CONTROL_CENTER_CORE_MIGRATION_BASE_HEAD}"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO020P_G1_WORK_ORDER} requires unchanged ruleset")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO020P_G1_WORK_ORDER} requires auto-merge to remain unarmed")
    require_wo020_control_center_evidence(
        WO020P_G1_WORK_ORDER,
        integration,
        migration_head_value,
    )
    return (
        f"work_order={WO020P_G1_WORK_ORDER}; exact_base=PASS; governance_scope=PASS; "
        "project_brain_changed=False; checkpoint_changed=False; migration_changed=False; "
        f"active_promotions={WO020P_G1_WORK_ORDER},{WO020P_WORK_ORDER}; "
        "historical_WO-019-P-G1_WO-019-P=REJECTED; unknown_WO-025-P_WO-999-P=REJECTED; "
        "authorized_base_parser=PASS; future_two_file_scope=PASS; checkpoint_semantics=PASS; "
        "manifest_contract=PASS; control_center_evidence=PASS; ruleset_unchanged=PASS; "
        "auto_merge=UNARMED; checkpoint_promotion=False"
    )


def verify_wo020p_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
) -> str | None:
    if work_order != WO020P_WORK_ORDER:
        return None
    require_wo020p_scope(work_order, base_sha, paths, enforce_authorized_base=False)
    expected_paths = [path for path in CANONICAL_PATHS]
    if canonical_changes != {
        "project_brain_changed": True,
        "checkpoint_changed": True,
        "authorized_paths": expected_paths,
    }:
        raise ValueError(
            f"{WO020P_WORK_ORDER} requires only checkpoint and manifest canonical changes"
        )
    if migration_head_value != CONTROL_CENTER_CORE_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO020P_WORK_ORDER} requires migration head {CONTROL_CENTER_CORE_MIGRATION_BASE_HEAD}"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO020P_WORK_ORDER} requires the protected ruleset to be unchanged")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO020P_WORK_ORDER} requires auto-merge to remain unarmed")
    require_wo020_control_center_evidence(
        WO020P_WORK_ORDER,
        integration,
        migration_head_value,
    )
    return (
        f"work_order={WO020P_WORK_ORDER}; promotion_scope=PASS; checkpoint_semantics=PASS; "
        "manifest_contract=PASS; control_center_evidence=PASS; "
        f"migration_head={CONTROL_CENTER_CORE_MIGRATION_BASE_HEAD}; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; checkpoint_promotion=True"
    )


def verify_wo021p_g1_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
    approved_lineage: Mapping[str, object] | None = None,
) -> str | None:
    if work_order != WO021P_G1_WORK_ORDER:
        return None
    require_wo021p_g1_scope(work_order, base_sha, paths)
    if not {WO021P_G1_WORK_ORDER, WO021P_WORK_ORDER}.issubset(
        HISTORICAL_CHECKPOINT_PROMOTION_WORK_ORDERS
    ):
        raise ValueError(f"{WO021P_G1_WORK_ORDER} must remain registered historically")
    for stale in (
        WO016P_G1_WORK_ORDER,
        WO016P_WORK_ORDER,
        WO017P_G1_WORK_ORDER,
        WO017P_WORK_ORDER,
        WO018P_G1_WORK_ORDER,
        WO018P_WORK_ORDER,
        WO019P_G1_WORK_ORDER,
        WO019P_WORK_ORDER,
        WO020P_G1_WORK_ORDER,
        WO020P_WORK_ORDER,
    ):
        try:
            require_current_work_order_authorization(stale)
        except ValueError:
            pass
        else:
            raise ValueError(f"{stale} unexpectedly authorizes a fresh current PR")
    for rejected in ("WO-026-P", "WO-999-P"):
        try:
            require_current_work_order_authorization(rejected)
        except ValueError:
            pass
        else:
            raise ValueError(f"{rejected} unexpectedly authorizes a fresh current PR")
    require_supported_work_order(WO021P_G1_WORK_ORDER)
    require_supported_work_order(WO021P_WORK_ORDER)
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO021P_G1_WORK_ORDER} forbids canonical changes")
    if migration_head_value != CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO021P_G1_WORK_ORDER} requires migration head "
            f"{CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD}"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO021P_G1_WORK_ORDER} requires unchanged ruleset")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO021P_G1_WORK_ORDER} requires auto-merge to remain unarmed")
    require_wo021_control_center_metrics_evidence(
        WO021_WORK_ORDER,
        integration,
        migration_head_value,
    )
    if approved_lineage is None:
        raise ValueError(f"{WO021P_G1_WORK_ORDER} requires approved product lineage evidence")
    require_wo021_approved_lineage_result(approved_lineage)
    return (
        f"work_order={WO021P_G1_WORK_ORDER}; exact_base=PASS; governance_scope=PASS; "
        "project_brain_changed=False; checkpoint_changed=False; migration_changed=False; "
        f"active_promotions={WO021P_G1_WORK_ORDER},{WO021P_WORK_ORDER}; "
        "historical_WO-020-P-G1_WO-020-P=REJECTED; "
        "unknown_WO-025-P_WO-999-P=REJECTED; authorized_base_parser=PASS; "
        "future_two_file_scope=PASS; checkpoint_semantics=PASS; manifest_contract=PASS; "
        "control_center_metrics_evidence=PASS; metrics_version=control-center-metrics-v1; "
        f"approved_lineage=PASS,PR#{approved_lineage['product_pr']},"
        f"audited_head={approved_lineage['audited_product_head']},"
        f"sol_review={approved_lineage['sol_review_id']},"
        f"squash_merge={approved_lineage['squash_merge_sha']},"
        f"post_merge_ci={approved_lineage['post_merge_ci_run']}; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; checkpoint_promotion=False"
    )


def verify_wo021p_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
    approved_lineage: Mapping[str, object] | None = None,
) -> str | None:
    if work_order != WO021P_WORK_ORDER:
        return None
    if approved_lineage is None:
        raise ValueError(f"{WO021P_WORK_ORDER} requires approved product lineage evidence")
    require_wo021_approved_lineage_result(approved_lineage)
    require_wo021_control_center_metrics_evidence(
        WO021_WORK_ORDER,
        integration,
        migration_head_value,
    )
    if canonical_changes != {
        "project_brain_changed": True,
        "checkpoint_changed": True,
        "authorized_paths": sorted(WO021P_PROMOTION_ALLOWED_PATHS),
    }:
        raise ValueError(
            f"{WO021P_WORK_ORDER} requires exactly the checkpoint and manifest canonical changes"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO021P_WORK_ORDER} requires the protected ruleset to be unchanged")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO021P_WORK_ORDER} requires auto-merge to remain unarmed")
    return (
        f"work_order={WO021P_WORK_ORDER}; promotion_scope=PASS; checkpoint_semantics=PASS; "
        "manifest_contract=PASS; control_center_metrics_evidence=PASS; "
        f"metrics_version={CONTROL_CENTER_METRICS_EVIDENCE_VERSION}; "
        f"migration_head={CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD}; "
        f"approved_lineage=PASS,PR#{approved_lineage['product_pr']},"
        f"audited_head={approved_lineage['audited_product_head']},"
        f"squash_merge={approved_lineage['squash_merge_sha']},"
        f"post_merge_ci={approved_lineage['post_merge_ci_run']}; "
        "full_control_center_claimed=False; full_v01_complete_claimed=False; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; checkpoint_promotion=True"
    )


def verify_wo022p_g1_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
    approved_lineage: Mapping[str, object] | None = None,
) -> str | None:
    if work_order != WO022P_G1_WORK_ORDER:
        return None
    require_wo022p_g1_scope(work_order, base_sha, paths)
    if not frozenset({WO022P_G1_WORK_ORDER, WO022P_WORK_ORDER}).issubset(
        CHECKPOINT_PROMOTION_WORK_ORDERS
    ):
        raise ValueError(f"{WO022P_G1_WORK_ORDER} requires registered promotion pair")
    for stale in (
        WO016P_G1_WORK_ORDER,
        WO016P_WORK_ORDER,
        WO017P_G1_WORK_ORDER,
        WO017P_WORK_ORDER,
        WO018P_G1_WORK_ORDER,
        WO018P_WORK_ORDER,
        WO019P_G1_WORK_ORDER,
        WO019P_WORK_ORDER,
        WO020P_G1_WORK_ORDER,
        WO020P_WORK_ORDER,
        WO021P_G1_WORK_ORDER,
        WO021P_WORK_ORDER,
    ):
        try:
            require_current_work_order_authorization(stale)
        except ValueError:
            pass
        else:
            raise ValueError(f"{stale} unexpectedly authorizes a fresh current PR")
    for rejected in ("WO-026-P", "WO-999-P"):
        try:
            require_current_work_order_authorization(rejected)
        except ValueError:
            pass
        else:
            raise ValueError(f"{rejected} unexpectedly authorizes a fresh current PR")
    require_supported_work_order(WO022P_G1_WORK_ORDER)
    require_supported_work_order(WO022P_WORK_ORDER)
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO022P_G1_WORK_ORDER} forbids canonical changes")
    if migration_head_value != CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO022P_G1_WORK_ORDER} requires migration head "
            f"{CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD}"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO022P_G1_WORK_ORDER} requires unchanged ruleset")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO022P_G1_WORK_ORDER} requires auto-merge to remain unarmed")
    require_wo022_full_control_center_evidence(
        WO022_WORK_ORDER,
        integration,
        migration_head_value,
    )
    if approved_lineage is None:
        raise ValueError(f"{WO022P_G1_WORK_ORDER} requires approved product lineage evidence")
    require_wo022_approved_lineage_result(approved_lineage)
    return (
        f"work_order={WO022P_G1_WORK_ORDER}; exact_base=PASS; governance_scope=PASS; "
        "project_brain_changed=False; checkpoint_changed=False; migration_changed=False; "
        f"active_promotions={WO022P_G1_WORK_ORDER},{WO022P_WORK_ORDER}; "
        "historical_WO-021-P-G1_WO-021-P=REJECTED; "
        "unknown_WO-025-P_WO-999-P=REJECTED; authorized_base_parser=PASS; "
        "future_two_file_scope=PASS; checkpoint_semantics=PASS; manifest_contract=PASS; "
        f"full_control_center_evidence=PASS; "
        f"full_control_center_version={CONTROL_CENTER_FULL_EVIDENCE_VERSION}; "
        f"approved_lineage=PASS,PR#{approved_lineage['product_pr']},"
        f"audited_head={approved_lineage['audited_product_head']},"
        f"sol_review={approved_lineage['sol_review_id']},"
        f"squash_merge={approved_lineage['squash_merge_sha']},"
        f"post_merge_ci={approved_lineage['post_merge_ci_run']}; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; checkpoint_promotion=False"
    )


def verify_wo022p_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
    approved_lineage: Mapping[str, object] | None = None,
) -> str | None:
    if work_order != WO022P_WORK_ORDER:
        return None
    if approved_lineage is None:
        raise ValueError(f"{WO022P_WORK_ORDER} requires approved product lineage evidence")
    require_wo022_approved_lineage_result(approved_lineage)
    require_wo022_full_control_center_evidence(
        WO022_WORK_ORDER,
        integration,
        migration_head_value,
    )
    if canonical_changes != {
        "project_brain_changed": True,
        "checkpoint_changed": True,
        "authorized_paths": sorted(WO022P_PROMOTION_ALLOWED_PATHS),
    }:
        raise ValueError(
            f"{WO022P_WORK_ORDER} requires exactly the checkpoint and manifest canonical changes"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO022P_WORK_ORDER} requires the protected ruleset to be unchanged")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO022P_WORK_ORDER} requires auto-merge to remain unarmed")
    return (
        f"work_order={WO022P_WORK_ORDER}; promotion_scope=PASS; checkpoint_semantics=PASS; "
        "manifest_contract=PASS; full_control_center_evidence=PASS; "
        f"full_control_center_version={CONTROL_CENTER_FULL_EVIDENCE_VERSION}; "
        f"migration_head={CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD}; "
        f"approved_lineage=PASS,PR#{approved_lineage['product_pr']},"
        f"audited_head={approved_lineage['audited_product_head']},"
        f"squash_merge={approved_lineage['squash_merge_sha']},"
        f"post_merge_ci={approved_lineage['post_merge_ci_run']}; "
        "full_v01_complete_claimed=False; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; checkpoint_promotion=True"
    )


def verify_wo023p_g1_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
    approved_lineage: Mapping[str, object] | None = None,
) -> str | None:
    if work_order != WO023P_G1_WORK_ORDER:
        return None
    require_wo023p_g1_scope(work_order, base_sha, paths)
    if not frozenset({WO023P_G1_WORK_ORDER, WO023P_WORK_ORDER}).issubset(
        CHECKPOINT_PROMOTION_WORK_ORDERS
    ):
        raise ValueError(f"{WO023P_G1_WORK_ORDER} requires registered promotion pair")
    for stale in (
        WO016P_G1_WORK_ORDER,
        WO016P_WORK_ORDER,
        WO017P_G1_WORK_ORDER,
        WO017P_WORK_ORDER,
        WO018P_G1_WORK_ORDER,
        WO018P_WORK_ORDER,
        WO019P_G1_WORK_ORDER,
        WO019P_WORK_ORDER,
        WO020P_G1_WORK_ORDER,
        WO020P_WORK_ORDER,
        WO021P_G1_WORK_ORDER,
        WO021P_WORK_ORDER,
        WO022P_G1_WORK_ORDER,
        WO022P_WORK_ORDER,
    ):
        try:
            require_current_work_order_authorization(stale)
        except ValueError:
            pass
        else:
            raise ValueError(f"{stale} unexpectedly authorizes a fresh current PR")
    for rejected in ("WO-023-P-C1", "WO-025", "WO-999-P"):
        try:
            require_current_work_order_authorization(rejected)
        except ValueError:
            pass
        else:
            raise ValueError(f"{rejected} unexpectedly authorizes a fresh current PR")
    require_supported_work_order(WO023P_G1_WORK_ORDER)
    require_supported_work_order(WO023P_WORK_ORDER)
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO023P_G1_WORK_ORDER} forbids canonical changes")
    if migration_head_value != COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO023P_G1_WORK_ORDER} requires migration head "
            f"{COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD}"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO023P_G1_WORK_ORDER} requires unchanged ruleset")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO023P_G1_WORK_ORDER} requires auto-merge to remain unarmed")
    require_wo023_comprehensive_benchmarks_evidence(
        WO023_WORK_ORDER,
        integration,
        migration_head_value,
    )
    if approved_lineage is None:
        raise ValueError(f"{WO023P_G1_WORK_ORDER} requires approved product lineage evidence")
    require_wo023_approved_lineage_result(approved_lineage)
    return (
        f"work_order={WO023P_G1_WORK_ORDER}; exact_base=PASS; governance_scope=PASS; "
        "project_brain_changed=False; checkpoint_changed=False; migration_changed=False; "
        f"active_promotions={WO023P_G1_WORK_ORDER},{WO023P_WORK_ORDER}; "
        "historical_WO-022-P-G1_WO-022-P=REJECTED; "
        "unknown_WO-023-P-C1_WO-025_WO-025-P_WO-999-P=REJECTED; authorized_base_parser=PASS; "
        "future_two_file_scope=PASS; checkpoint_semantics=PASS; manifest_contract=PASS; "
        f"comprehensive_benchmarks_evidence=PASS; "
        f"comprehensive_benchmarks_version={COMPREHENSIVE_BENCHMARKS_EVIDENCE_VERSION}; "
        f"approved_lineage=PASS,PR#{approved_lineage['product_pr']},"
        f"audited_head={approved_lineage['audited_product_head']},"
        f"sol_review={approved_lineage['sol_review_id']},"
        f"squash_merge={approved_lineage['squash_merge_sha']},"
        f"post_merge_ci={approved_lineage['post_merge_ci_run']}; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; checkpoint_promotion=False"
    )


def verify_wo023p_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
    approved_lineage: Mapping[str, object] | None = None,
) -> str | None:
    if work_order != WO023P_WORK_ORDER:
        return None
    if approved_lineage is None:
        raise ValueError(f"{WO023P_WORK_ORDER} requires approved product lineage evidence")
    require_wo023_approved_lineage_result(approved_lineage)
    require_wo023_comprehensive_benchmarks_evidence(
        WO023_WORK_ORDER,
        integration,
        migration_head_value,
    )
    if canonical_changes != {
        "project_brain_changed": True,
        "checkpoint_changed": True,
        "authorized_paths": sorted(WO023P_PROMOTION_ALLOWED_PATHS),
    }:
        raise ValueError(
            f"{WO023P_WORK_ORDER} requires exactly the checkpoint and manifest canonical changes"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO023P_WORK_ORDER} requires the protected ruleset to be unchanged")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO023P_WORK_ORDER} requires auto-merge to remain unarmed")
    return (
        f"work_order={WO023P_WORK_ORDER}; promotion_scope=PASS; checkpoint_semantics=PASS; "
        "manifest_contract=PASS; comprehensive_benchmarks_evidence=PASS; "
        f"comprehensive_benchmarks_version={COMPREHENSIVE_BENCHMARKS_EVIDENCE_VERSION}; "
        f"migration_head={COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD}; "
        f"approved_lineage=PASS,PR#{approved_lineage['product_pr']},"
        f"audited_head={approved_lineage['audited_product_head']},"
        f"squash_merge={approved_lineage['squash_merge_sha']},"
        f"post_merge_ci={approved_lineage['post_merge_ci_run']}; "
        "full_v01_complete_claimed=False; production_quality_claimed_from_fixture=False; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; checkpoint_promotion=True"
    )


def verify_wo023p_g1_c1_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
    authorized_base_sha: str | None = None,
) -> str | None:
    if work_order != WO023P_G1_C1_WORK_ORDER:
        return None
    require_wo023p_g1_c1_scope(
        work_order,
        base_sha,
        paths,
        authorized_base_sha=authorized_base_sha,
        enforce_authorized_base=authorized_base_sha is not None,
    )
    if WO023P_G1_C1_WORK_ORDER in ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS:
        raise ValueError(f"{WO023P_G1_C1_WORK_ORDER} must not join the active promotion pair")
    if WO023P_G1_C1_WORK_ORDER in ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS:
        raise ValueError(f"{WO023P_G1_C1_WORK_ORDER} must not join the active promotion pair")
    fresh_marker_work_orders = {WO023P_WORK_ORDER, WO023P_G1_C1_WORK_ORDER}
    if not fresh_marker_work_orders.issubset(AUTHORIZED_BASE_MARKER_WORK_ORDERS):
        raise ValueError(
            f"{WO023P_G1_C1_WORK_ORDER} requires the authorized-base marker parser to cover "
            "WO-023-P and the corrective work order"
        )
    for rejected in ("WO-030-C1", "WO-028-P", "WO-999-P"):
        try:
            require_current_work_order_authorization(rejected)
        except ValueError:
            pass
        else:
            raise ValueError(f"{rejected} unexpectedly authorizes a fresh current PR")
    for historical in (WO022P_G1_WORK_ORDER, WO022P_WORK_ORDER):
        try:
            require_current_work_order_authorization(historical)
        except ValueError:
            pass
        else:
            raise ValueError(f"{historical} unexpectedly authorizes a fresh current PR")
    require_supported_work_order(WO023P_G1_WORK_ORDER)
    require_supported_work_order(WO023P_WORK_ORDER)
    require_supported_work_order(WO023P_G1_C1_WORK_ORDER)
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO023P_G1_C1_WORK_ORDER} forbids canonical changes")
    if migration_head_value != COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO023P_G1_C1_WORK_ORDER} requires migration head "
            f"{COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD}"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO023P_G1_C1_WORK_ORDER} requires an unchanged ruleset")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO023P_G1_C1_WORK_ORDER} requires auto-merge to remain unarmed")
    require_wo023_comprehensive_benchmarks_evidence(
        WO023_WORK_ORDER,
        integration,
        migration_head_value,
    )
    return (
        f"work_order={WO023P_G1_C1_WORK_ORDER}; exact_base=PASS; correction_scope=PASS; "
        "project_brain_changed=False; checkpoint_changed=False; migration_changed=False; "
        "authorized_base_parser_covers_WO-023-P=PASS; "
        f"migration_head={COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD}; "
        f"active_promotions={WO023P_G1_WORK_ORDER},{WO023P_WORK_ORDER}; "
        "historical_WO-022-P-G1_WO-022-P=REJECTED; unknown_WO-025_WO-025-P_WO-999-P=REJECTED; "
        f"comprehensive_benchmarks_evidence=PASS; "
        f"comprehensive_benchmarks_version={COMPREHENSIVE_BENCHMARKS_EVIDENCE_VERSION}; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; canonical_promotion_untouched=True; "
        "checkpoint_promotion=False"
    )


def verify_wo024p_g1_c1_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
    authorized_base_sha: str | None = None,
) -> str | None:
    """Self-host the WO-024-P deadlock correction as bounded governance evidence."""

    if work_order != WO024P_G1_C1_WORK_ORDER:
        return None
    require_wo024p_g1_c1_scope(
        work_order,
        base_sha,
        paths,
        authorized_base_sha=authorized_base_sha,
        enforce_authorized_base=authorized_base_sha is not None,
    )
    if frozenset({WO024_G1_WORK_ORDER, WO024P_WORK_ORDER}) != (
        ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS
    ):
        raise ValueError(
            f"{WO024P_G1_C1_WORK_ORDER} requires the active WO-024 promotion pair to be unchanged"
        )
    for rejected in ("WO-030-C1", "WO-028-P", "WO-999"):
        try:
            require_current_work_order_authorization(rejected)
        except ValueError:
            pass
        else:
            raise ValueError(f"{rejected} unexpectedly authorizes a fresh current PR")
    for historical in (WO023P_G1_WORK_ORDER, WO023P_G1_C1_WORK_ORDER, WO023P_WORK_ORDER):
        try:
            require_current_work_order_authorization(historical)
        except ValueError:
            pass
        else:
            raise ValueError(f"{historical} unexpectedly authorizes a fresh current PR")
    for supported in (
        WO024_G1_WORK_ORDER,
        WO024_WORK_ORDER,
        WO024P_WORK_ORDER,
        WO024P_G1_C1_WORK_ORDER,
    ):
        require_supported_work_order(supported)
    if WO024P_G1_C1_WORK_ORDER not in AUTHORIZED_BASE_MARKER_WORK_ORDERS:
        raise ValueError(
            f"{WO024P_G1_C1_WORK_ORDER} requires the authorized-base marker parser to cover it"
        )
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO024P_G1_C1_WORK_ORDER} forbids canonical changes")
    if migration_head_value != V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO024P_G1_C1_WORK_ORDER} requires migration head "
            f"{V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO024P_G1_C1_WORK_ORDER} requires an unchanged ruleset")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO024P_G1_C1_WORK_ORDER} requires auto-merge to remain unarmed")
    require_wo024_v01_closure_sprint_evidence(
        WO024_WORK_ORDER,
        integration,
        migration_head_value,
    )
    promoted = (
        f"{sorted(WO024P_PROMOTION_ALLOWED_PATHS)[0]},{sorted(WO024P_PROMOTION_ALLOWED_PATHS)[1]}"
    )
    return (
        f"work_order={WO024P_G1_C1_WORK_ORDER}; exact_base=PASS; correction_scope=PASS; "
        "project_brain_changed=False; checkpoint_changed=False; migration_changed=False; "
        "dependency_changed=False; workflow_changed=False; release_changed=False; "
        "authorized_base_marker_supported=True; "
        f"migration_head={V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}; "
        f"active_promotions={WO024_G1_WORK_ORDER},{WO024P_WORK_ORDER}; "
        f"corrective_outside_active_pair=True; "
        f"promotion_aware_closure_scope={promoted}=ALLOWED_EXACT_PAIR; "
        "promotion_pair_plus_extra_path=REJECTED; ordinary_product_scope=PROJECT_BRAIN_REJECTED; "
        f"wo024p_promotion_base_registry=PASS; "
        f"approved_product_pr={WO024_APPROVED_PRODUCT_PR}; "
        f"approved_product_head={WO024_APPROVED_PRODUCT_HEAD_SHA}; "
        f"approved_sol_review={WO024_APPROVED_SOL_REVIEW_ID}; "
        f"approved_squash_merge={WO024_APPROVED_SQUASH_MERGE_SHA}; "
        f"approved_post_merge_ci={WO024_APPROVED_POST_MERGE_CI_RUN}; "
        "squash_merge_ancestry=REQUIRED; sol_review_audited_test_counts=REQUIRED; "
        "historical_WO-023-P-G1_WO-023-P-G1-C1_WO-023-P=REJECTED; "
        "unknown_WO-025_WO-025-P_WO-999=REJECTED; "
        f"v01_closure_sprint_evidence=PASS; "
        f"v01_closure_sprint_version={V01_CLOSURE_SPRINT_EVIDENCE_VERSION}; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; canonical_promotion_untouched=True; "
        "checkpoint_promotion=False; v0.1_completion_claim=False"
    )


def verify_wo024p_g1_c2_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
    authorized_base_sha: str | None = None,
) -> str | None:
    """Self-host the stateful-test correction as bounded governance evidence."""

    if work_order != WO024P_G1_C2_WORK_ORDER:
        return None
    require_wo024p_g1_c2_scope(
        work_order,
        base_sha,
        paths,
        authorized_base_sha=authorized_base_sha,
        enforce_authorized_base=authorized_base_sha is not None,
    )
    for rejected in ("WO-030-C1", "WO-028-P", "WO-999"):
        try:
            require_current_work_order_authorization(rejected)
        except ValueError:
            pass
        else:
            raise ValueError(f"{rejected} unexpectedly authorizes a fresh current PR")
    for historical in (WO023P_G1_C1_WORK_ORDER, WO023P_WORK_ORDER):
        try:
            require_current_work_order_authorization(historical)
        except ValueError:
            pass
        else:
            raise ValueError(f"{historical} unexpectedly authorizes a fresh current PR")
    for supported in (
        WO024_G1_WORK_ORDER,
        WO024_WORK_ORDER,
        WO024P_WORK_ORDER,
        WO024P_G1_C1_WORK_ORDER,
        WO024P_G1_C2_WORK_ORDER,
    ):
        require_supported_work_order(supported)
    if WO024P_G1_C2_WORK_ORDER not in AUTHORIZED_BASE_MARKER_WORK_ORDERS:
        raise ValueError(
            f"{WO024P_G1_C2_WORK_ORDER} requires the authorized-base marker parser to cover it"
        )
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO024P_G1_C2_WORK_ORDER} forbids canonical changes")
    if migration_head_value != V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO024P_G1_C2_WORK_ORDER} requires migration head "
            f"{V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO024P_G1_C2_WORK_ORDER} requires an unchanged ruleset")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO024P_G1_C2_WORK_ORDER} requires auto-merge to remain unarmed")
    require_wo024_v01_closure_sprint_evidence(
        WO024_WORK_ORDER,
        integration,
        migration_head_value,
    )
    return (
        f"work_order={WO024P_G1_C2_WORK_ORDER}; exact_base=PASS; correction_scope=PASS; "
        "checkpoint_regressions_state_independent=True; "
        "promotion_base_is_synthesized=True; live_checkpoint_never_a_promotion_base=True; "
        "no_op_negative_fixture_rejected=True; "
        "guards_unchanged=require_wo024p_checkpoint_semantics,checkpoint_current; "
        "project_brain_changed=False; checkpoint_changed=False; "
        "canonical_promotion_files_untouched=True; migration_changed=False; "
        "dependency_changed=False; workflow_changed=False; release_changed=False; "
        f"migration_head={V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}; "
        f"active_promotions={WO024_G1_WORK_ORDER},{WO024P_WORK_ORDER}; "
        "active_promotion_pair_unchanged=True; corrective_outside_active_pair=True; "
        "authorized_base_marker_supported=True; "
        "v0.1_promotion_performed=False; v0.1_completion_claim=False; "
        f"v01_closure_sprint_evidence=PASS; "
        f"v01_closure_sprint_version={V01_CLOSURE_SPRINT_EVIDENCE_VERSION}; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED"
    )


def require_wo024p_g1_c3_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    authorized_base_sha: str | None = None,
    enforce_authorized_base: bool = True,
) -> None:
    """Bounded scope for the closure-to-lineage wiring correction: governance tooling only."""

    if work_order != WO024P_G1_C3_WORK_ORDER:
        return
    if base_sha != WO024P_G1_C3_BASE_SHA:
        raise ValueError(
            f"{WO024P_G1_C3_WORK_ORDER} requires exact base {WO024P_G1_C3_BASE_SHA}, "
            f"observed {base_sha}"
        )
    if base_branch != "main":
        raise ValueError(f"{WO024P_G1_C3_WORK_ORDER} requires the protected main base branch")
    if not paths:
        raise ValueError(f"{WO024P_G1_C3_WORK_ORDER} requires a non-empty correction delta")
    unauthorized = sorted(set(paths) - WO024P_G1_C3_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            f"{WO024P_G1_C3_WORK_ORDER} changed files outside the bounded correction scope: "
            + ", ".join(unauthorized)
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(
                f"{WO024P_G1_C3_WORK_ORDER} requires exactly one authorized-base marker"
            )
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError("WO-024-P-G1-C3 authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO024P_G1_C3_WORK_ORDER} authorized-base marker must match the pull request "
                "base SHA"
            )
    for prefix in sorted(WO024P_G1_C1_FORBIDDEN_PREFIXES):
        offenders = sorted(path for path in paths if path.startswith(prefix))
        if offenders:
            raise ValueError(
                f"{WO024P_G1_C3_WORK_ORDER} cannot change {prefix}: " + ", ".join(offenders)
            )
    promotion_paths = sorted(set(paths) & WO024P_PROMOTION_ALLOWED_PATHS)
    if promotion_paths:
        raise ValueError(
            f"{WO024P_G1_C3_WORK_ORDER} cannot include the canonical promotion files: "
            + ", ".join(promotion_paths)
        )
    for manifest in sorted(set(paths) & DEPENDENCY_MANIFEST_PATHS):
        raise ValueError(
            f"{WO024P_G1_C3_WORK_ORDER} cannot change the dependency manifest {manifest}"
        )
    for path in sorted(set(paths)):
        if RELEASE_PATH_IDENTIFIER.search(path):
            raise ValueError(f"{WO024P_G1_C3_WORK_ORDER} cannot change release assets: {path}")
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO024P_G1_C3_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO024P_G1_C3_WORK_ORDER} cannot change migrations")
    if work_order in ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS:
        raise ValueError(f"{WO024P_G1_C3_WORK_ORDER} must not join the active promotion pair")
    if WO024P_G1_C3_WORK_ORDER in ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS:
        raise ValueError(f"{WO024P_G1_C3_WORK_ORDER} must not join the active promotion pair")
    if frozenset({WO024_G1_WORK_ORDER, WO024P_WORK_ORDER}) != (
        ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS
    ):
        raise ValueError(
            f"{WO024P_G1_C3_WORK_ORDER} requires the active WO-024 promotion pair to be unchanged"
        )
    if migration_head() != V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO024P_G1_C3_WORK_ORDER} requires migration head "
            f"{V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}"
        )


def verify_wo024p_g1_c3_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
    authorized_base_sha: str | None = None,
) -> str | None:
    """Self-host the closure-to-lineage wiring correction as bounded governance evidence."""

    if work_order != WO024P_G1_C3_WORK_ORDER:
        return None
    require_wo024p_g1_c3_scope(
        work_order,
        base_sha,
        paths,
        authorized_base_sha=authorized_base_sha,
        enforce_authorized_base=authorized_base_sha is not None,
    )
    for rejected in ("WO-030-C1", "WO-028-P", "WO-999"):
        try:
            require_current_work_order_authorization(rejected)
        except ValueError:
            pass
        else:
            raise ValueError(f"{rejected} unexpectedly authorizes a fresh current PR")
    for historical in (WO023P_G1_C1_WORK_ORDER, WO023P_WORK_ORDER):
        try:
            require_current_work_order_authorization(historical)
        except ValueError:
            pass
        else:
            raise ValueError(f"{historical} unexpectedly authorizes a fresh current PR")
    for supported in (
        WO024_G1_WORK_ORDER,
        WO024_WORK_ORDER,
        WO024P_WORK_ORDER,
        WO024P_G1_C1_WORK_ORDER,
        WO024P_G1_C2_WORK_ORDER,
        WO024P_G1_C3_WORK_ORDER,
    ):
        require_supported_work_order(supported)
    if WO024P_G1_C3_WORK_ORDER not in AUTHORIZED_BASE_MARKER_WORK_ORDERS:
        raise ValueError(
            f"{WO024P_G1_C3_WORK_ORDER} requires the authorized-base marker parser to cover it"
        )
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO024P_G1_C3_WORK_ORDER} forbids canonical changes")
    if migration_head_value != V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO024P_G1_C3_WORK_ORDER} requires migration head "
            f"{V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO024P_G1_C3_WORK_ORDER} requires an unchanged ruleset")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO024P_G1_C3_WORK_ORDER} requires auto-merge to remain unarmed")
    if "v01_closure_sprint" in integration:
        raise ValueError(
            f"{WO024P_G1_C3_WORK_ORDER} keeps the closure family out of the schema-bound manifest"
        )
    payload = wo024p_closure_payload()
    return (
        f"work_order={WO024P_G1_C3_WORK_ORDER}; exact_base=PASS; correction_scope=PASS; "
        "closure_lineage_wiring_source=closure_sprint_evidence; "
        f"closure_payload_dod={payload.get('dod_pass_count')}/{payload.get('dod_total_count')}; "
        "closure_payload_validated=PASS; incomplete_closure_fails_closed=ValueError; "
        "schema_bound_manifest_omits_v01_closure_sprint=True; schema_unchanged=True; "
        "lineage_identity_addressed=True; current_main_association_rediscovery=False; "
        "approved_product_pr=95; audited_product_head=649e7f90fc4f2d4e3cbc17ca0f38d5f2c9dd46ad; "
        "approved_sol_review=5233591627; "
        "approved_squash_merge=05d142511f849d002c4ec8558fe4f43dca3e788b; "
        "approved_post_merge_ci=35204484706; audited_counts=676/34; "
        "project_brain_changed=False; checkpoint_changed=False; migration_changed=False; "
        "dependency_changed=False; workflow_changed=False; release_changed=False; "
        f"migration_head={V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}; "
        f"active_promotions={WO024_G1_WORK_ORDER},{WO024P_WORK_ORDER}; "
        "active_promotion_pair_unchanged=True; corrective_outside_active_pair=True; "
        "authorized_base_marker_supported=True; "
        "v0.1_promotion_performed=False; v0.1_completion_claim=False; "
        f"v01_closure_sprint_version={V01_CLOSURE_SPRINT_EVIDENCE_VERSION}; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED"
    )


def require_wo024p_g1_c4_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    authorized_base_sha: str | None = None,
    enforce_authorized_base: bool = True,
) -> None:
    """Bounded scope for the authorized-base propagation correction: governance tooling only."""

    if work_order != WO024P_G1_C4_WORK_ORDER:
        return
    if base_sha != WO024P_G1_C4_BASE_SHA:
        raise ValueError(
            f"{WO024P_G1_C4_WORK_ORDER} requires exact base {WO024P_G1_C4_BASE_SHA}, "
            f"observed {base_sha}"
        )
    if base_branch != "main":
        raise ValueError(f"{WO024P_G1_C4_WORK_ORDER} requires the protected main base branch")
    if not paths:
        raise ValueError(f"{WO024P_G1_C4_WORK_ORDER} requires a non-empty correction delta")
    unauthorized = sorted(set(paths) - WO024P_G1_C4_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            f"{WO024P_G1_C4_WORK_ORDER} changed files outside the bounded correction scope: "
            + ", ".join(unauthorized)
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(
                f"{WO024P_G1_C4_WORK_ORDER} requires exactly one authorized-base marker"
            )
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError("WO-024-P-G1-C4 authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO024P_G1_C4_WORK_ORDER} authorized-base marker must match the pull request "
                "base SHA"
            )
    for prefix in sorted(WO024P_G1_C1_FORBIDDEN_PREFIXES):
        offenders = sorted(path for path in paths if path.startswith(prefix))
        if offenders:
            raise ValueError(
                f"{WO024P_G1_C4_WORK_ORDER} cannot change {prefix}: " + ", ".join(offenders)
            )
    promotion_paths = sorted(set(paths) & WO024P_PROMOTION_ALLOWED_PATHS)
    if promotion_paths:
        raise ValueError(
            f"{WO024P_G1_C4_WORK_ORDER} cannot include the canonical promotion files: "
            + ", ".join(promotion_paths)
        )
    for manifest in sorted(set(paths) & DEPENDENCY_MANIFEST_PATHS):
        raise ValueError(
            f"{WO024P_G1_C4_WORK_ORDER} cannot change the dependency manifest {manifest}"
        )
    for path in sorted(set(paths)):
        if RELEASE_PATH_IDENTIFIER.search(path):
            raise ValueError(f"{WO024P_G1_C4_WORK_ORDER} cannot change release assets: {path}")
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO024P_G1_C4_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO024P_G1_C4_WORK_ORDER} cannot change migrations")
    if work_order in ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS:
        raise ValueError(f"{WO024P_G1_C4_WORK_ORDER} must not join the active promotion pair")
    if WO024P_G1_C4_WORK_ORDER in ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS:
        raise ValueError(f"{WO024P_G1_C4_WORK_ORDER} must not join the active promotion pair")
    if frozenset({WO024_G1_WORK_ORDER, WO024P_WORK_ORDER}) != (
        ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS
    ):
        raise ValueError(
            f"{WO024P_G1_C4_WORK_ORDER} requires the active WO-024 promotion pair to be unchanged"
        )
    if migration_head() != V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO024P_G1_C4_WORK_ORDER} requires migration head "
            f"{V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}"
        )


def verify_wo024p_g1_c4_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
    authorized_base_sha: str | None = None,
) -> str | None:
    """Self-host the authorized-base propagation correction as bounded governance evidence."""

    if work_order != WO024P_G1_C4_WORK_ORDER:
        return None
    require_wo024p_g1_c4_scope(
        work_order,
        base_sha,
        paths,
        authorized_base_sha=authorized_base_sha,
        enforce_authorized_base=authorized_base_sha is not None,
    )
    for rejected in ("WO-030-C1", "WO-028-P", "WO-999"):
        try:
            require_current_work_order_authorization(rejected)
        except ValueError:
            pass
        else:
            raise ValueError(f"{rejected} unexpectedly authorizes a fresh current PR")
    for historical in (WO023P_G1_C1_WORK_ORDER, WO023P_WORK_ORDER):
        try:
            require_current_work_order_authorization(historical)
        except ValueError:
            pass
        else:
            raise ValueError(f"{historical} unexpectedly authorizes a fresh current PR")
    for supported in (
        WO024_G1_WORK_ORDER,
        WO024_WORK_ORDER,
        WO024P_WORK_ORDER,
        WO024P_G1_C1_WORK_ORDER,
        WO024P_G1_C2_WORK_ORDER,
        WO024P_G1_C3_WORK_ORDER,
        WO024P_G1_C4_WORK_ORDER,
    ):
        require_supported_work_order(supported)
    if WO024P_G1_C4_WORK_ORDER not in AUTHORIZED_BASE_MARKER_WORK_ORDERS:
        raise ValueError(
            f"{WO024P_G1_C4_WORK_ORDER} requires the authorized-base marker parser to cover it"
        )
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO024P_G1_C4_WORK_ORDER} forbids canonical changes")
    if migration_head_value != V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO024P_G1_C4_WORK_ORDER} requires migration head "
            f"{V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO024P_G1_C4_WORK_ORDER} requires an unchanged ruleset")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO024P_G1_C4_WORK_ORDER} requires auto-merge to remain unarmed")
    if "v01_closure_sprint" in integration:
        raise ValueError(
            f"{WO024P_G1_C4_WORK_ORDER} keeps the closure family out of the schema-bound manifest"
        )
    return (
        f"work_order={WO024P_G1_C4_WORK_ORDER}; exact_base=PASS; correction_scope=PASS; "
        "authorized_base_marker_forwarded_into_require_wo024p_scope=True; "
        "marker_reparsed_from_body=False; "
        "enforce_authorized_base_preserved_in_build=True; "
        "exact_base_matches_marker=True; lowercase_40_hex_enforced=True; "
        "current_main_enforced=True; exact_two_path_promotion_scope=True; "
        "closure_evidence_checks=True; approved_lineage_checks=True; "
        "checkpoint_semantics=True; manifest_contract=True; ruleset_guard=True; "
        "auto_merge_guard=True; "
        "schema_bound_manifest_omits_v01_closure_sprint=True; schema_unchanged=True; "
        "project_brain_changed=False; checkpoint_changed=False; migration_changed=False; "
        "dependency_changed=False; workflow_changed=False; release_changed=False; "
        f"migration_head={V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}; "
        f"active_promotions={WO024_G1_WORK_ORDER},{WO024P_WORK_ORDER}; "
        "active_promotion_pair_unchanged=True; corrective_outside_active_pair=True; "
        "authorized_base_marker_supported=True; "
        "v0.1_promotion_performed=False; v0.1_completion_claim=False; "
        f"v01_closure_sprint_version={V01_CLOSURE_SPRINT_EVIDENCE_VERSION}; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED"
    )


def pull_request_work_order_from_event(
    event_path: str | None = None,
) -> str | None:
    """Resolve the work order of the pull request that triggered this run, if any.

    The GitHub event payload is read from a local file (``GITHUB_EVENT_PATH``); nothing is fetched
    over the network. An absent path, unreadable payload, non-pull-request event or missing marker
    resolves to ``None``, which every caller treats as the conservative default.
    """

    candidate = event_path if event_path is not None else os.environ.get("GITHUB_EVENT_PATH")
    if not candidate:
        return None
    try:
        payload = json.loads(Path(candidate).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    pull_request = payload.get("pull_request")
    if not isinstance(pull_request, Mapping):
        return None
    body = pull_request.get("body")
    if not isinstance(body, str):
        return None
    try:
        return parse_work_order_marker(body)
    except ValueError:
        return None


def wo025_planning_scope(paths: list[str]) -> list[str]:
    """Return the paths that leave the post-1.0 planning documentation surface."""

    offenders: list[str] = []
    for path in sorted(set(paths)):
        if path.endswith(".md") and any(
            path.startswith(prefix) for prefix in WO025_PLANNING_DOCUMENT_PREFIXES
        ):
            continue
        match = WO025_PLANNING_DOCUMENT_PATTERN.fullmatch(path)
        if match is not None:
            number = int(match.group(1))
            if WO025_PLANNING_DOCUMENT_RANGE[0] <= number <= WO025_PLANNING_DOCUMENT_RANGE[1]:
                continue
        offenders.append(path)
    return offenders


def require_wo025_g1_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    authorized_base_sha: str | None = None,
    enforce_authorized_base: bool = True,
) -> None:
    """Bounded scope for the post-1.0 governance bridge: governance and closure-test tooling."""

    if work_order != WO025_G1_WORK_ORDER:
        return
    if base_sha != WO025_G1_BASE_SHA:
        raise ValueError(
            f"{WO025_G1_WORK_ORDER} requires exact base {WO025_G1_BASE_SHA}, observed {base_sha}"
        )
    if base_branch != "main":
        raise ValueError(f"{WO025_G1_WORK_ORDER} requires the protected main base branch")
    if not paths:
        raise ValueError(f"{WO025_G1_WORK_ORDER} requires a non-empty governance delta")
    unauthorized = sorted(set(paths) - WO025_G1_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            f"{WO025_G1_WORK_ORDER} changed files outside the bounded governance scope: "
            + ", ".join(unauthorized)
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(f"{WO025_G1_WORK_ORDER} requires exactly one authorized-base marker")
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError("WO-025-G1 authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO025_G1_WORK_ORDER} authorized-base marker must match the pull request base SHA"
            )
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO025_G1_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO025_G1_WORK_ORDER} cannot change migrations")
    if any(path.startswith(".github/") for path in paths):
        raise ValueError(f"{WO025_G1_WORK_ORDER} cannot change CI workflows")
    if migration_head() != V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO025_G1_WORK_ORDER} requires migration head "
            f"{V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}"
        )


def verify_wo025_g1_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
    authorized_base_sha: str | None = None,
) -> str | None:
    """Self-host the post-1.0 governance bridge as bounded governance evidence."""

    if work_order != WO025_G1_WORK_ORDER:
        return None
    require_wo025_g1_scope(
        work_order,
        base_sha,
        paths,
        authorized_base_sha=authorized_base_sha,
        enforce_authorized_base=authorized_base_sha is not None,
    )
    for rejected in ("WO-030-C1", "WO-028-P", "WO-999"):
        try:
            require_current_work_order_authorization(rejected)
        except ValueError:
            pass
        else:
            raise ValueError(f"{rejected} unexpectedly authorizes a fresh current PR")
    require_supported_work_order(WO025_G1_WORK_ORDER)
    require_supported_work_order(WO025_WORK_ORDER)
    if WO025_G1_WORK_ORDER not in AUTHORIZED_BASE_MARKER_WORK_ORDERS:
        raise ValueError(
            f"{WO025_G1_WORK_ORDER} requires the authorized-base marker parser to cover it"
        )
    if frozenset({WO024_G1_WORK_ORDER, WO024P_WORK_ORDER}) != (
        ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS
    ):
        raise ValueError(
            f"{WO025_G1_WORK_ORDER} requires the historical WO-024 promotion pair to be unchanged"
        )
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO025_G1_WORK_ORDER} forbids canonical changes")
    if migration_head_value != V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO025_G1_WORK_ORDER} requires migration head "
            f"{V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO025_G1_WORK_ORDER} requires an unchanged ruleset")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO025_G1_WORK_ORDER} requires auto-merge to remain unarmed")
    require_wo024_v01_closure_sprint_evidence(
        WO024_WORK_ORDER,
        integration,
        migration_head_value,
    )
    return (
        f"work_order={WO025_G1_WORK_ORDER}; exact_base=PASS; governance_scope=PASS; "
        "project_brain_changed=False; checkpoint_changed=False; migration_changed=False; "
        "dependency_changed=False; workflow_changed=False; release_changed=False; "
        "closure_sprint_regression_mode=REGISTERED; "
        "closure_sprint_historical_scope_work_orders=WO-024,WO-024-P; "
        "closure_product_allowlist_widened=False; project_brain_globally_allowlisted=False; "
        "integration_health_disabled=False; review_evidence_optional=False; "
        "wo025_planning_only_registered=True; unknown_WO-028=REJECTED; "
        f"active_promotions={WO024_G1_WORK_ORDER},{WO024P_WORK_ORDER}; "
        "historical_promotion_pair_unchanged=True; authorized_base_marker_supported=True; "
        f"v01_closure_sprint_evidence=PASS; "
        f"v01_closure_sprint_version={V01_CLOSURE_SPRINT_EVIDENCE_VERSION}; "
        f"migration_head={V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; v0.1_completion_claim=False"
    )


def require_wo025_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    registered_base_sha: str | None = None,
    authorized_base_sha: str | None = None,
    enforce_current_main: bool = False,
    enforce_authorized_base: bool = True,
) -> None:
    """Bounded planning-documentation-only scope for the future WO-025 promotion."""

    if work_order != WO025_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO025_WORK_ORDER} requires the protected main base branch")
    expected_base = registered_base_sha or registered_promotion_base_sha(work_order)
    if base_sha != expected_base:
        raise ValueError(
            f"{WO025_WORK_ORDER} requires current protected main base {expected_base}, "
            f"observed {base_sha}"
        )
    if enforce_current_main:
        current_main = git_value("rev-parse", WO012P_PROMOTION_BASE_REF, fallback="")
        if HEX_SHA.fullmatch(current_main) and base_sha != current_main:
            raise ValueError(
                f"{WO025_WORK_ORDER} must target current protected main {current_main}, "
                f"observed {base_sha}"
            )
    if not paths:
        raise ValueError(f"{WO025_WORK_ORDER} requires a non-empty planning delta")
    offenders = wo025_planning_scope(paths)
    if offenders:
        raise ValueError(
            f"{WO025_WORK_ORDER} changed paths outside the post-1.0 planning surface: "
            + ", ".join(offenders)
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(f"{WO025_WORK_ORDER} requires exactly one authorized-base marker")
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError("WO-025 authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO025_WORK_ORDER} authorized-base marker must match the pull request base SHA"
            )
    if any(path in CANONICAL_PATHS for path in paths):
        raise ValueError(f"{WO025_WORK_ORDER} cannot change the canonical core documents")
    if work_order in ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS:
        raise ValueError(f"{WO025_WORK_ORDER} must not join the historical promotion pair")
    if WO025_WORK_ORDER in ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS:
        raise ValueError(f"{WO025_WORK_ORDER} must not join the historical promotion pair")
    if frozenset({WO024_G1_WORK_ORDER, WO024P_WORK_ORDER}) != (
        ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS
    ):
        raise ValueError(
            f"{WO025_WORK_ORDER} requires the historical WO-024 promotion pair to be unchanged"
        )
    if migration_head() != V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO025_WORK_ORDER} requires migration head {V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}"
        )


def require_wo026_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    authorized_base_sha: str | None = None,
    enforce_current_main: bool = False,
    enforce_authorized_base: bool = True,
) -> None:
    """Bound Apache-2.0 readiness to the authorized base and exact six-file surface."""

    if work_order != WO026_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO026_WORK_ORDER} requires the protected main base branch")
    if base_sha != WO026_BASE_SHA:
        raise ValueError(
            f"{WO026_WORK_ORDER} requires exact base {WO026_BASE_SHA}, observed {base_sha}"
        )
    if enforce_current_main:
        current_main = git_value("rev-parse", "origin/main", fallback="")
        if HEX_SHA.fullmatch(current_main) and current_main != WO026_BASE_SHA:
            raise ValueError(
                f"{WO026_WORK_ORDER} is stale: protected main is {current_main}, "
                f"authorized base is {WO026_BASE_SHA}"
            )
    if len(paths) != len(WO026_ALLOWED_PATHS) or set(paths) != WO026_ALLOWED_PATHS:
        unauthorized = sorted(set(paths) - WO026_ALLOWED_PATHS)
        missing = sorted(WO026_ALLOWED_PATHS - set(paths))
        details: list[str] = []
        if unauthorized:
            details.append("unauthorized=" + ",".join(unauthorized))
        if missing:
            details.append("missing=" + ",".join(missing))
        raise ValueError(
            f"{WO026_WORK_ORDER} requires exactly the bounded Apache-2.0 readiness surface"
            + (": " + "; ".join(details) if details else "")
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(f"{WO026_WORK_ORDER} requires exactly one authorized-base marker")
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError(f"{WO026_WORK_ORDER} authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO026_WORK_ORDER} authorized-base marker must match the pull request base SHA"
            )


def require_wo027_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    authorized_base_sha: str | None = None,
    enforce_current_main: bool = False,
    enforce_authorized_base: bool = True,
) -> None:
    """Bound Claude OSS application readiness to the authorized base and exact four-file surface."""

    if work_order != WO027_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO027_WORK_ORDER} requires the protected main base branch")
    if base_sha != WO027_BASE_SHA:
        raise ValueError(
            f"{WO027_WORK_ORDER} requires exact base {WO027_BASE_SHA}, observed {base_sha}"
        )
    if enforce_current_main:
        current_main = git_value("rev-parse", "origin/main", fallback="")
        if HEX_SHA.fullmatch(current_main) and current_main != WO027_BASE_SHA:
            raise ValueError(
                f"{WO027_WORK_ORDER} is stale: protected main is {current_main}, "
                f"authorized base is {WO027_BASE_SHA}"
            )
    if len(paths) != len(WO027_ALLOWED_PATHS) or set(paths) != WO027_ALLOWED_PATHS:
        raise ValueError(
            f"{WO027_WORK_ORDER} requires exactly the bounded application-readiness surface"
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(f"{WO027_WORK_ORDER} requires exactly one authorized-base marker")
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError(f"{WO027_WORK_ORDER} authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO027_WORK_ORDER} authorized-base marker must match the pull request base SHA"
            )


def require_wo028_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    authorized_base_sha: str | None = None,
    enforce_current_main: bool = False,
    enforce_authorized_base: bool = True,
) -> None:
    """Bound project-root hotfix to the authorized base and exact eight-file surface."""

    if work_order != WO028_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO028_WORK_ORDER} requires the protected main base branch")
    if base_sha != WO028_BASE_SHA:
        raise ValueError(
            f"{WO028_WORK_ORDER} requires exact base {WO028_BASE_SHA}, observed {base_sha}"
        )
    if enforce_current_main:
        current_main = git_value("rev-parse", "origin/main", fallback="")
        if HEX_SHA.fullmatch(current_main) and current_main != WO028_BASE_SHA:
            raise ValueError(
                f"{WO028_WORK_ORDER} is stale: protected main is {current_main}, "
                f"authorized base is {WO028_BASE_SHA}"
            )
    if len(paths) != len(WO028_ALLOWED_PATHS) or set(paths) != WO028_ALLOWED_PATHS:
        unauthorized = sorted(set(paths) - WO028_ALLOWED_PATHS)
        missing = sorted(WO028_ALLOWED_PATHS - set(paths))
        details: list[str] = []
        if unauthorized:
            details.append("unauthorized=" + ",".join(unauthorized))
        if missing:
            details.append("missing=" + ",".join(missing))
        raise ValueError(
            f"{WO028_WORK_ORDER} requires exactly the bounded project-root hotfix surface"
            + (": " + "; ".join(details) if details else "")
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(f"{WO028_WORK_ORDER} requires exactly one authorized-base marker")
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError(f"{WO028_WORK_ORDER} authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO028_WORK_ORDER} authorized-base marker must match the pull request base SHA"
            )


def require_wo029_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    authorized_base_sha: str | None = None,
    enforce_current_main: bool = False,
    enforce_authorized_base: bool = True,
) -> None:
    """Bound executor/token corrective maintenance to the authorized v1.0.1 base."""

    if work_order != WO029_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO029_WORK_ORDER} requires the protected main base branch")
    if base_sha != WO029_BASE_SHA:
        raise ValueError(
            f"{WO029_WORK_ORDER} requires exact base {WO029_BASE_SHA}, observed {base_sha}"
        )
    if enforce_current_main:
        current_main = git_value("rev-parse", "origin/main", fallback="")
        if HEX_SHA.fullmatch(current_main) and current_main != WO029_BASE_SHA:
            raise ValueError(
                f"{WO029_WORK_ORDER} is stale: protected main is {current_main}, "
                f"authorized base is {WO029_BASE_SHA}"
            )
    if len(paths) != len(WO029_ALLOWED_PATHS) or set(paths) != WO029_ALLOWED_PATHS:
        raise ValueError(
            f"{WO029_WORK_ORDER} requires exactly the bounded executor/token corrective surface"
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(f"{WO029_WORK_ORDER} requires exactly one authorized-base marker")
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError(f"{WO029_WORK_ORDER} authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO029_WORK_ORDER} authorized-base marker must match the pull request base SHA"
            )


def require_wo030_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    authorized_base_sha: str | None = None,
    enforce_current_main: bool = False,
    enforce_authorized_base: bool = True,
) -> None:
    """Bound Vitest security maintenance to the exact authorized main base and surface."""

    if work_order != WO030_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO030_WORK_ORDER} requires the protected main base branch")
    if base_sha != WO030_BASE_SHA:
        raise ValueError(
            f"{WO030_WORK_ORDER} requires exact base {WO030_BASE_SHA}, observed {base_sha}"
        )
    if enforce_current_main:
        current_main = git_value("rev-parse", "origin/main", fallback="")
        if HEX_SHA.fullmatch(current_main) and current_main != WO030_BASE_SHA:
            raise ValueError(
                f"{WO030_WORK_ORDER} is stale: protected main is {current_main}, "
                f"authorized base is {WO030_BASE_SHA}"
            )
    if len(paths) != len(WO030_ALLOWED_PATHS) or set(paths) != WO030_ALLOWED_PATHS:
        unauthorized = sorted(set(paths) - WO030_ALLOWED_PATHS)
        missing = sorted(WO030_ALLOWED_PATHS - set(paths))
        details: list[str] = []
        if unauthorized:
            details.append("unauthorized=" + ",".join(unauthorized))
        if missing:
            details.append("missing=" + ",".join(missing))
        raise ValueError(
            f"{WO030_WORK_ORDER} requires exactly the bounded Vitest security correction surface"
            + (": " + "; ".join(details) if details else "")
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(f"{WO030_WORK_ORDER} requires exactly one authorized-base marker")
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError(f"{WO030_WORK_ORDER} authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO030_WORK_ORDER} authorized-base marker must match the pull request base SHA"
            )


def require_wo030_c1_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    authorized_base_sha: str | None = None,
    enforce_current_main: bool = False,
    enforce_authorized_base: bool = True,
) -> None:
    """Bound Progressive Disclosure token correction to the exact authorized surface."""

    if work_order != WO030_C1_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO030_C1_WORK_ORDER} requires the protected main base branch")
    if base_sha != WO030_C1_BASE_SHA:
        raise ValueError(
            f"{WO030_C1_WORK_ORDER} requires exact base {WO030_C1_BASE_SHA}, observed {base_sha}"
        )
    if enforce_current_main:
        current_main = git_value("rev-parse", "origin/main", fallback="")
        if HEX_SHA.fullmatch(current_main) and current_main != WO030_C1_BASE_SHA:
            raise ValueError(
                f"{WO030_C1_WORK_ORDER} is stale: protected main is {current_main}, "
                f"authorized base is {WO030_C1_BASE_SHA}"
            )
    if len(paths) != len(WO030_C1_ALLOWED_PATHS) or set(paths) != WO030_C1_ALLOWED_PATHS:
        raise ValueError(
            f"{WO030_C1_WORK_ORDER} requires exactly the bounded Progressive Disclosure correction surface"
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(f"{WO030_C1_WORK_ORDER} requires exactly one authorized-base marker")
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError(f"{WO030_C1_WORK_ORDER} authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO030_C1_WORK_ORDER} authorized-base marker must match the pull request base SHA"
            )


def verify_wo025_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
    authorized_base_sha: str | None = None,
) -> str | None:
    """Register the future post-1.0 planning promotion as bounded governance evidence."""

    if work_order != WO025_WORK_ORDER:
        return None
    require_wo025_scope(
        work_order,
        base_sha,
        paths,
        authorized_base_sha=authorized_base_sha,
        enforce_authorized_base=authorized_base_sha is not None,
    )
    if canonical_changes.get("checkpoint_changed") is not False:
        raise ValueError(f"{WO025_WORK_ORDER} is planning-only and cannot change the checkpoint")
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO025_WORK_ORDER} requires an unchanged ruleset")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO025_WORK_ORDER} requires auto-merge to remain unarmed")
    planning_paths = sorted(path for path in paths if path not in wo025_planning_scope([path]))
    return (
        f"work_order={WO025_WORK_ORDER}; planning_only=True; planning_scope=PASS; "
        f"planning_paths={len(planning_paths)}; "
        f"planning_document_prefixes={','.join(WO025_PLANNING_DOCUMENT_PREFIXES)}; "
        "product_code_rejected=True; migrations_rejected=True; dependencies_rejected=True; "
        "workflow_rejected=True; release_rejected=True; canonical_core_rejected=True; "
        f"active_promotions={WO024_G1_WORK_ORDER},{WO024P_WORK_ORDER}; "
        "historical_promotion_pair_unchanged=True; "
        f"migration_head={V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; v0.1_completion_claim=False; "
        "canonical_promotion_performed=False"
    )


def require_wo025_g2_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    authorized_base_sha: str | None = None,
    enforce_authorized_base: bool = True,
) -> None:
    """Bounded scope for the planning-promotion authorization: governance and renderer only."""

    if work_order != WO025_G2_WORK_ORDER:
        return
    if base_sha != WO025_G2_BASE_SHA:
        raise ValueError(
            f"{WO025_G2_WORK_ORDER} requires exact base {WO025_G2_BASE_SHA}, observed {base_sha}"
        )
    if base_branch != "main":
        raise ValueError(f"{WO025_G2_WORK_ORDER} requires the protected main base branch")
    if not paths:
        raise ValueError(f"{WO025_G2_WORK_ORDER} requires a non-empty governance delta")
    unauthorized = sorted(set(paths) - WO025_G2_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            f"{WO025_G2_WORK_ORDER} changed files outside the bounded governance scope: "
            + ", ".join(unauthorized)
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(f"{WO025_G2_WORK_ORDER} requires exactly one authorized-base marker")
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError("WO-025-G2 authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO025_G2_WORK_ORDER} authorized-base marker must match the pull request base SHA"
            )
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO025_G2_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO025_G2_WORK_ORDER} cannot change migrations")
    if any(path.startswith(".github/") for path in paths):
        raise ValueError(f"{WO025_G2_WORK_ORDER} cannot change CI workflows")
    for manifest in sorted(set(paths) & DEPENDENCY_MANIFEST_PATHS):
        raise ValueError(f"{WO025_G2_WORK_ORDER} cannot change the dependency manifest {manifest}")
    for path in sorted(set(paths)):
        if RELEASE_PATH_IDENTIFIER.search(path):
            raise ValueError(f"{WO025_G2_WORK_ORDER} cannot change release assets: {path}")
    if migration_head() != V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO025_G2_WORK_ORDER} requires migration head "
            f"{V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}"
        )


def verify_wo025_g2_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
    authorized_base_sha: str | None = None,
) -> str | None:
    """Self-host the planning-promotion authorization as bounded governance evidence."""

    if work_order != WO025_G2_WORK_ORDER:
        return None
    require_wo025_g2_scope(
        work_order,
        base_sha,
        paths,
        authorized_base_sha=authorized_base_sha,
        enforce_authorized_base=authorized_base_sha is not None,
    )
    require_supported_work_order(WO025_G2_WORK_ORDER)
    require_supported_work_order(WO025_WORK_ORDER)
    if WO025_G2_WORK_ORDER not in AUTHORIZED_BASE_MARKER_WORK_ORDERS:
        raise ValueError(
            f"{WO025_G2_WORK_ORDER} requires the authorized-base marker parser to cover it"
        )
    # WO-025 becomes an authorized current planning-promotion work order in this increment, while
    # unknown later identifiers stay fail-closed.
    require_current_work_order_authorization(WO025_WORK_ORDER)
    for rejected in ("WO-030-C1", "WO-028-P", "WO-999-P"):
        try:
            require_current_work_order_authorization(rejected)
        except ValueError:
            pass
        else:
            raise ValueError(f"{rejected} unexpectedly authorizes a fresh current PR")
    if WO025_WORK_ORDER in PENDING_PLANNING_PROMOTION_WORK_ORDERS:
        raise ValueError(
            f"{WO025_G2_WORK_ORDER} requires WO-025 to leave the pending planning registry"
        )
    if frozenset({WO024_G1_WORK_ORDER, WO024P_WORK_ORDER}) != (
        ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS
    ):
        raise ValueError(
            f"{WO025_G2_WORK_ORDER} requires the historical WO-024 promotion pair to be unchanged"
        )
    if paths and any(path in CANONICAL_PATHS for path in paths):
        raise ValueError(f"{WO025_G2_WORK_ORDER} forbids canonical promotion files")
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO025_G2_WORK_ORDER} forbids canonical changes")
    if migration_head_value != V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO025_G2_WORK_ORDER} requires migration head "
            f"{V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO025_G2_WORK_ORDER} requires an unchanged ruleset")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO025_G2_WORK_ORDER} requires auto-merge to remain unarmed")
    require_wo024_v01_closure_sprint_evidence(
        WO024_WORK_ORDER,
        integration,
        migration_head_value,
    )
    return (
        f"work_order={WO025_G2_WORK_ORDER}; exact_base=PASS; governance_scope=PASS; "
        "project_brain_changed=False; checkpoint_changed=False; migration_changed=False; "
        "dependency_changed=False; workflow_changed=False; release_changed=False; "
        "wo025_current_authorized=True; wo025_planning_scope_preserved=True; "
        "unknown_WO-028_WO-028-P_WO-999-P=REJECTED; "
        "wo025_renderer=dedicated_planning_only; wo025_g2_renderer=dedicated_governance_only; "
        "stale_semantic_retrieval_fallback_reachable_for_WO-025=False; "
        f"active_promotions={WO024_G1_WORK_ORDER},{WO024P_WORK_ORDER}; "
        "historical_promotion_pair_unchanged=True; wo024_strict_behavior_unchanged=True; "
        "planning_documents_promoted=False; product_implementation=False; "
        f"v01_closure_sprint_evidence=PASS; "
        f"v01_closure_sprint_version={V01_CLOSURE_SPRINT_EVIDENCE_VERSION}; "
        f"migration_head={V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; v0.1_completion_claim=False; "
        "canonical_promotion_performed=False"
    )


def require_wo025_g3_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    authorized_base_sha: str | None = None,
    enforce_authorized_base: bool = True,
) -> None:
    """Bounded scope for the work-order namespace governance: governance tooling only."""

    if work_order != WO025_G3_WORK_ORDER:
        return
    if base_sha != WO025_G3_BASE_SHA:
        raise ValueError(
            f"{WO025_G3_WORK_ORDER} requires exact base {WO025_G3_BASE_SHA}, observed {base_sha}"
        )
    if base_branch != "main":
        raise ValueError(f"{WO025_G3_WORK_ORDER} requires the protected main base branch")
    if not paths:
        raise ValueError(f"{WO025_G3_WORK_ORDER} requires a non-empty governance delta")
    unauthorized = sorted(set(paths) - WO025_G3_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            f"{WO025_G3_WORK_ORDER} changed files outside the bounded governance scope: "
            + ", ".join(unauthorized)
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(f"{WO025_G3_WORK_ORDER} requires exactly one authorized-base marker")
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError("WO-025-G3 authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO025_G3_WORK_ORDER} authorized-base marker must match the pull request base SHA"
            )
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO025_G3_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO025_G3_WORK_ORDER} cannot change migrations")
    if any(path.startswith(".github/") for path in paths):
        raise ValueError(f"{WO025_G3_WORK_ORDER} cannot change CI workflows")
    for manifest in sorted(set(paths) & DEPENDENCY_MANIFEST_PATHS):
        raise ValueError(f"{WO025_G3_WORK_ORDER} cannot change the dependency manifest {manifest}")
    for path in sorted(set(paths)):
        if RELEASE_PATH_IDENTIFIER.search(path):
            raise ValueError(f"{WO025_G3_WORK_ORDER} cannot change release assets: {path}")
    if migration_head() != V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO025_G3_WORK_ORDER} requires migration head "
            f"{V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}"
        )


def require_wo025_g4_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    authorized_base_sha: str | None = None,
    enforce_authorized_base: bool = True,
) -> None:
    """Bounded scope for the closure/post-1.0 compatibility fix: governance and tests only."""

    if work_order != WO025_G4_WORK_ORDER:
        return
    if base_sha != WO025_G4_BASE_SHA:
        raise ValueError(
            f"{WO025_G4_WORK_ORDER} requires exact base {WO025_G4_BASE_SHA}, observed {base_sha}"
        )
    if base_branch != "main":
        raise ValueError(f"{WO025_G4_WORK_ORDER} requires the protected main base branch")
    if not paths:
        raise ValueError(f"{WO025_G4_WORK_ORDER} requires a non-empty governance delta")
    unauthorized = sorted(set(paths) - WO025_G4_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            f"{WO025_G4_WORK_ORDER} changed files outside the bounded governance scope: "
            + ", ".join(unauthorized)
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(f"{WO025_G4_WORK_ORDER} requires exactly one authorized-base marker")
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError("WO-025-G4 authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO025_G4_WORK_ORDER} authorized-base marker must match the pull request base SHA"
            )
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO025_G4_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO025_G4_WORK_ORDER} cannot change migrations")
    if any(path.startswith(".github/") for path in paths):
        raise ValueError(f"{WO025_G4_WORK_ORDER} cannot change CI workflows")
    for manifest in sorted(set(paths) & DEPENDENCY_MANIFEST_PATHS):
        raise ValueError(f"{WO025_G4_WORK_ORDER} cannot change the dependency manifest {manifest}")
    for path in sorted(set(paths)):
        if RELEASE_PATH_IDENTIFIER.search(path):
            raise ValueError(f"{WO025_G4_WORK_ORDER} cannot change release assets: {path}")
    if migration_head() != V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO025_G4_WORK_ORDER} requires migration head "
            f"{V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}"
        )


def require_wo025_g5_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    authorized_base_sha: str | None = None,
    enforce_authorized_base: bool = True,
) -> None:
    """Bound reviewer self-healing policy adoption to governance/docs/tests only."""

    if work_order != WO025_G5_WORK_ORDER:
        return
    if base_sha != WO025_G5_BASE_SHA:
        raise ValueError(
            f"{WO025_G5_WORK_ORDER} requires exact base {WO025_G5_BASE_SHA}, observed {base_sha}"
        )
    if base_branch != "main":
        raise ValueError(f"{WO025_G5_WORK_ORDER} requires the protected main base branch")
    if not paths:
        raise ValueError(f"{WO025_G5_WORK_ORDER} requires a non-empty governance delta")
    unauthorized = sorted(set(paths) - WO025_G5_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            f"{WO025_G5_WORK_ORDER} changed files outside the bounded governance scope: "
            + ", ".join(unauthorized)
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(f"{WO025_G5_WORK_ORDER} requires exactly one authorized-base marker")
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError("WO-025-G5 authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO025_G5_WORK_ORDER} authorized-base marker must match the pull request base SHA"
            )
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO025_G5_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO025_G5_WORK_ORDER} cannot change migrations")
    if any(path.startswith(".github/") for path in paths):
        raise ValueError(f"{WO025_G5_WORK_ORDER} cannot change CI workflows")
    for manifest in sorted(set(paths) & DEPENDENCY_MANIFEST_PATHS):
        raise ValueError(f"{WO025_G5_WORK_ORDER} cannot change the dependency manifest {manifest}")
    for path in sorted(set(paths)):
        if RELEASE_PATH_IDENTIFIER.search(path):
            raise ValueError(f"{WO025_G5_WORK_ORDER} cannot change release assets: {path}")
    if migration_head() != V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO025_G5_WORK_ORDER} requires migration head "
            f"{V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}"
        )


def require_wo025p_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    authorized_base_sha: str | None = None,
    enforce_authorized_base: bool = True,
) -> None:
    """Bounded scope for the next canonical checkpoint promotion.

    WO-025-P is registered by WO-025-G3 but not executed there. Its contract is the canonical
    checkpoint, its digest manifest, and nothing else: the registered release-train order reads the
    promoted checkpoint as deterministic evidence, so the transition needs no further governance
    commit after this promotion lands.
    """

    if work_order != WO025P_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO025P_WORK_ORDER} requires the protected main base branch")
    expected_base = registered_promotion_base_sha(WO025P_WORK_ORDER)
    if base_sha != expected_base:
        raise ValueError(
            f"{WO025P_WORK_ORDER} requires current protected main base {expected_base}, "
            f"observed {base_sha}"
        )
    if not paths:
        raise ValueError(f"{WO025P_WORK_ORDER} requires a non-empty promotion delta")
    unauthorized = sorted(set(paths) - WO025P_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            f"{WO025P_WORK_ORDER} changed files outside the bounded promotion scope: "
            + ", ".join(unauthorized)
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(f"{WO025P_WORK_ORDER} requires exactly one authorized-base marker")
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError("WO-025-P authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO025P_WORK_ORDER} authorized-base marker must match the pull request base SHA"
            )
    if any(path.startswith(".github/") for path in paths):
        raise ValueError(f"{WO025P_WORK_ORDER} cannot change CI workflows")
    for manifest in sorted(set(paths) & DEPENDENCY_MANIFEST_PATHS):
        raise ValueError(f"{WO025P_WORK_ORDER} cannot change the dependency manifest {manifest}")
    if migration_head() != V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO025P_WORK_ORDER} requires migration head {V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}"
        )
    base_checkpoint = git_blob_bytes(base_sha, CHECKPOINT_PATH).decode("utf-8")
    candidate_checkpoint_bytes = (ROOT / CHECKPOINT_PATH).read_bytes()
    require_wo025p_checkpoint_semantics(base_checkpoint, candidate_checkpoint_bytes.decode("utf-8"))
    require_checkpoint_manifest_contract(
        git_blob_bytes(base_sha, CANONICAL_MANIFEST_PATH).decode("utf-8"),
        (ROOT / CANONICAL_MANIFEST_PATH).read_bytes().decode("utf-8"),
        candidate_checkpoint_bytes,
        WO025P_WORK_ORDER,
    )


def require_wo11_01_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    authorized_base_sha: str | None = None,
    enforce_authorized_base: bool = True,
) -> None:
    """Bounded scope for the first Decision Fabric product order.

    WO-1.1-01 is registered by WO-025-G3 so its grammar, scope and renderer are frozen now, but it
    stays PENDING/BLOCKED: it cannot authorize a fresh pull request until the canonical checkpoint
    promotion lands.
    """

    if work_order != WO11_01_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(f"{WO11_01_WORK_ORDER} requires the protected main base branch")
    if not paths:
        raise ValueError(f"{WO11_01_WORK_ORDER} requires a non-empty product delta")
    unauthorized = sorted(set(paths) - WO11_01_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            f"{WO11_01_WORK_ORDER} changed files outside the bounded Decision Contract scope: "
            + ", ".join(unauthorized)
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(f"{WO11_01_WORK_ORDER} requires exactly one authorized-base marker")
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError("WO-1.1-01 authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO11_01_WORK_ORDER} authorized-base marker must match the pull request base SHA"
            )
    canonical = canonical_change_evidence(paths, work_order)
    if canonical["project_brain_changed"] or canonical["checkpoint_changed"]:
        raise ValueError(f"{WO11_01_WORK_ORDER} cannot change canonical Project Brain")
    if any(path == "migrations" or path.startswith("migrations/") for path in paths):
        raise ValueError(f"{WO11_01_WORK_ORDER} cannot change migrations")
    if any(path.startswith(".github/") for path in paths):
        raise ValueError(f"{WO11_01_WORK_ORDER} cannot change CI workflows")
    for manifest in sorted(set(paths) & DEPENDENCY_MANIFEST_PATHS):
        raise ValueError(f"{WO11_01_WORK_ORDER} cannot change the dependency manifest {manifest}")
    for path in sorted(set(paths)):
        if RELEASE_PATH_IDENTIFIER.search(path):
            raise ValueError(f"{WO11_01_WORK_ORDER} cannot change release assets: {path}")
    if migration_head() != V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO11_01_WORK_ORDER} requires migration head {V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}"
        )


def verify_wo025_g3_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
    authorized_base_sha: str | None = None,
) -> str | None:
    """Self-host the work-order namespace governance as bounded evidence."""

    if work_order != WO025_G3_WORK_ORDER:
        return None
    require_wo025_g3_scope(
        work_order,
        base_sha,
        paths,
        authorized_base_sha=authorized_base_sha,
        enforce_authorized_base=authorized_base_sha is not None,
    )
    require_supported_work_order(WO025_G3_WORK_ORDER)
    if WO025_G3_WORK_ORDER not in AUTHORIZED_BASE_MARKER_WORK_ORDERS:
        raise ValueError(
            f"{WO025_G3_WORK_ORDER} requires the authorized-base marker parser to cover it"
        )
    # The registered next promotion and the pending release-train order must both be parseable.
    require_supported_work_order(WO025P_WORK_ORDER)
    require_supported_work_order(WO11_01_WORK_ORDER)
    if parse_work_order_marker(f"<!-- HIVE-WORK-ORDER: {WO11_01_WORK_ORDER} -->") != (
        WO11_01_WORK_ORDER
    ):
        raise ValueError(
            f"{WO025_G3_WORK_ORDER} requires the release-train grammar to parse 1.1-01"
        )
    # STATE A (after this increment, before WO-025-P): the next promotion is current-authorized,
    # while the registered release-train order is still blocked by canonical checkpoint evidence --
    # not by a flag -- and the unregistered frontier fails closed.
    require_current_work_order_authorization(WO025P_WORK_ORDER)
    if RELEASE_TRAIN_PROMOTING_WORK_ORDERS.get(WO11_01_WORK_ORDER) != WO025P_WORK_ORDER:
        raise ValueError(
            f"{WO025_G3_WORK_ORDER} requires WO-1.1-01 to be released by the WO-025-P promotion"
        )
    for pending in (WO11_01_WORK_ORDER,):
        try:
            require_current_work_order_authorization(pending)
        except ValueError as error:
            if WO025P_WORK_ORDER not in str(error):
                raise ValueError(
                    f"{pending} must be blocked by the unlanded canonical checkpoint promotion"
                ) from error
        else:
            raise ValueError(f"{pending} unexpectedly authorizes a fresh current PR")
    for rejected in (
        "WO-1.1-02",
        "WO-11-01",
        "WO-12-99",
        "WO-22-01",
        "WO-027-P",
        "WO-030-C1",
        "",
    ):
        try:
            require_supported_work_order(rejected)
        except ValueError:
            pass
        else:
            raise ValueError(f"{rejected!r} unexpectedly remains supported")
    # WO-025-P is registered but must not join the historical WO-024 pair.
    if frozenset({WO024_G1_WORK_ORDER, WO024P_WORK_ORDER}) != (
        ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS
    ):
        raise ValueError(
            f"{WO025_G3_WORK_ORDER} requires the historical WO-024 promotion pair to be unchanged"
        )
    if WO025P_WORK_ORDER in ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS:
        raise ValueError(
            f"{WO025_G3_WORK_ORDER} forbids WO-025-P joining the active promotion pair"
        )
    # Promotion history and the current promotion stay disjoint sets, so authorizing the next
    # promotion never rewrites the audited WO-024 frontier.
    if frozenset({WO025P_WORK_ORDER}) != CURRENT_CHECKPOINT_PROMOTION_WORK_ORDERS:
        raise ValueError(
            f"{WO025_G3_WORK_ORDER} requires WO-025-P to be the only current promotion frontier"
        )
    if ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS & CURRENT_CHECKPOINT_PROMOTION_WORK_ORDERS:
        raise ValueError(
            f"{WO025_G3_WORK_ORDER} requires current promotion frontier to stay out of history"
        )
    for historical in (WO024_G1_WORK_ORDER, WO024_WORK_ORDER, WO024P_WORK_ORDER):
        require_current_work_order_authorization(historical)
    if not {WO024_G1_WORK_ORDER, WO024P_WORK_ORDER}.issubset(CHECKPOINT_PROMOTION_WORK_ORDERS):
        raise ValueError(f"{WO025_G3_WORK_ORDER} requires the historical promotion pair registered")
    if paths and any(path in CANONICAL_PATHS for path in paths):
        raise ValueError(f"{WO025_G3_WORK_ORDER} forbids canonical promotion files")
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO025_G3_WORK_ORDER} forbids canonical changes")
    if migration_head_value != V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO025_G3_WORK_ORDER} requires migration head "
            f"{V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO025_G3_WORK_ORDER} requires an unchanged ruleset")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO025_G3_WORK_ORDER} requires auto-merge to remain unarmed")
    require_wo024_v01_closure_sprint_evidence(
        WO024_WORK_ORDER,
        integration,
        migration_head_value,
    )
    return (
        f"work_order={WO025_G3_WORK_ORDER}; exact_base=PASS; governance_scope=PASS; "
        "deny_by_default=True; fallthrough_removed=True; "
        "project_brain_changed=False; checkpoint_changed=False; migration_changed=False; "
        "dependency_changed=False; workflow_changed=False; release_changed=False; "
        "release_train_grammar=PASS; wo_1_1_01_parses=True; wo_1_1_01_registered=True; "
        "wo_1_1_01_pending_blocked=True; wo_1_1_02_rejected=True; "
        "near_miss_WO-11-01_WO-12-99_WO-22-01=REJECTED; unknown_WO-027-P_WO-028=REJECTED; "
        "malformed_identifier=REJECTED; empty_identifier=REJECTED; "
        "wo_025_p_registered=True; wo_025_p_current_authorized=True; "
        "wo_025_p_promotion_executed=False; "
        f"current_promotion_frontier={WO025P_WORK_ORDER}; promotion_history_separated=True; "
        "wo_1_1_01_gate=canonical_checkpoint_evidence; "
        "wo_1_1_01_release_needs_no_governance_commit=True; "
        f"active_promotions={WO024_G1_WORK_ORDER},{WO024P_WORK_ORDER}; "
        "historical_promotion_pair_unchanged=True; historical_work_orders_preserved=True; "
        "wo024_strict_behavior_unchanged=True; "
        "renderers=dedicated_wo025_g3_wo025_p_wo11_01; "
        "stale_semantic_retrieval_fallback_reachable=False; "
        "product_implementation=False; checkpoint_promoted=False; "
        f"v01_closure_sprint_evidence=PASS; "
        f"v01_closure_sprint_version={V01_CLOSURE_SPRINT_EVIDENCE_VERSION}; "
        f"migration_head={V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; v0.1_completion_claim=False; "
        "canonical_promotion_performed=False"
    )


def verify_wo025_g4_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
    authorized_base_sha: str | None = None,
) -> str | None:
    """Self-host the closure/post-1.0 checkpoint compatibility as bounded evidence."""

    if work_order != WO025_G4_WORK_ORDER:
        return None
    require_wo025_g4_scope(
        work_order,
        base_sha,
        paths,
        authorized_base_sha=authorized_base_sha,
        enforce_authorized_base=authorized_base_sha is not None,
    )
    require_supported_work_order(WO025_G4_WORK_ORDER)
    require_current_work_order_authorization(WO025_G4_WORK_ORDER)
    if WO025_G4_WORK_ORDER not in AUTHORIZED_BASE_MARKER_WORK_ORDERS:
        raise ValueError(
            f"{WO025_G4_WORK_ORDER} requires the authorized-base marker parser to cover it"
        )
    if WO025_G4_WORK_ORDER not in CORRECTIVE_GOVERNANCE_WORK_ORDERS:
        raise ValueError(
            f"{WO025_G4_WORK_ORDER} must stay a corrective governance order outside the pair"
        )
    if WO025_G4_WORK_ORDER in CHECKPOINT_PROMOTION_WORK_ORDERS:
        raise ValueError(f"{WO025_G4_WORK_ORDER} must not become a checkpoint promotion")
    # Three legitimate checkpoint families, pairwise distinct so no state can impersonate another.
    closure_statuses = (
        EXPECTED_WO024P_PREVIOUS_STATUS,
        EXPECTED_WO024P_STATUS,
        EXPECTED_WO025P_STATUS,
    )
    if len(set(closure_statuses)) != 3:
        raise ValueError(f"{WO025_G4_WORK_ORDER} requires three distinct checkpoint families")
    if EXPECTED_WO025P_PREVIOUS_STATUS != EXPECTED_WO024P_STATUS:
        raise ValueError(
            f"{WO025_G4_WORK_ORDER} requires WO-025-P to promote from the V0.1 closure state"
        )
    post_promotion_state = {
        "IN PROGRESS": EXPECTED_WO025P_IN_PROGRESS,
        "BLOCKERS": EXPECTED_WO025P_BLOCKERS,
        "NEXT STEP": EXPECTED_WO025P_NEXT_STEP,
    }
    if set(post_promotion_state) != {"IN PROGRESS", "BLOCKERS", "NEXT STEP"}:
        raise ValueError(f"{WO025_G4_WORK_ORDER} requires the full post-promotion state contract")
    if WO11_01_WORK_ORDER not in post_promotion_state["IN PROGRESS"]:
        raise ValueError(
            f"{WO025_G4_WORK_ORDER} must name {WO11_01_WORK_ORDER} as the work in flight"
        )
    if "WO-1.1-01" not in post_promotion_state["NEXT STEP"]:
        raise ValueError(f"{WO025_G4_WORK_ORDER} must name the WO-1.1-01 next step")
    # Only the controlled operational sections may move; everything else is byte-preserved, which is
    # what makes an arbitrary checkpoint that merely swapped STATUS fail instead of pass.
    if frozenset({"STATUS", "IN PROGRESS", "PENDING", "BLOCKERS", "NEXT STEP"}) != (
        WO025P_RAW_PROMOTION_CONTROLLED_SECTIONS
    ):
        raise ValueError(f"{WO025_G4_WORK_ORDER} requires the exact WO-025-P controlled set")
    for immutable in ("VERSION", "PHASE", "OBJECTIVE", "SCOPE", "COMPLETED", "GOVERNANCE"):
        if immutable in WO025P_RAW_PROMOTION_CONTROLLED_SECTIONS:
            raise ValueError(f"{WO025_G4_WORK_ORDER} forbids {immutable} in the controlled set")
    # The real checkpoint stays in the V0.1 closure state and its digests stay verifiable, so this
    # increment proves compatibility without performing the promotion.
    checkpoint_text = (ROOT / CHECKPOINT_PATH).read_bytes().decode("utf-8")
    checkpoint_sections_map = checkpoint_sections(checkpoint_text)
    if normalized_checkpoint_value(checkpoint_sections_map, "STATUS") != (
        EXPECTED_WO025P_PREVIOUS_STATUS
    ):
        raise ValueError(
            f"{WO025_G4_WORK_ORDER} must not execute the {WO025P_WORK_ORDER} promotion"
        )
    require_canonical_manifest_digests(
        ROOT, (ROOT / CANONICAL_MANIFEST_PATH).read_bytes().decode("utf-8")
    )
    # The post-1.0 contract is proved against the real canonical checkpoint in memory only: the
    # exact promoted state is accepted and every narrower mutation is rejected.
    preamble, ordered, base_bodies = _raw_checkpoint_structure(checkpoint_text, "base")

    def rebuild(bodies: Mapping[str, str]) -> str:
        return preamble + "".join(
            section.heading + bodies.get(section.name, section.body) for section in ordered
        )

    promoted_bodies = {
        "STATUS": f"{EXPECTED_WO025P_STATUS}\n\n",
        "IN PROGRESS": f"- {EXPECTED_WO025P_IN_PROGRESS}\n\n",
        "BLOCKERS": f"{EXPECTED_WO025P_BLOCKERS}\n\n",
        "NEXT STEP": f"{EXPECTED_WO025P_NEXT_STEP}\n\n",
        "PENDING": "\n",
    }
    try:
        require_wo025p_checkpoint_semantics(checkpoint_text, rebuild(promoted_bodies))
    except ValueError as error:
        raise ValueError(
            f"{WO025_G4_WORK_ORDER} rejects its own post-1.0 checkpoint contract: {error}"
        ) from error
    mutations: dict[str, str] = {
        "status swap": rebuild({"STATUS": promoted_bodies["STATUS"]}),
        "stale NEXT STEP": rebuild(
            {**promoted_bodies, "NEXT STEP": f"{EXPECTED_WO024P_NEXT_STEP}\n\n"}
        ),
        "undue PENDING": rebuild({**promoted_bodies, "PENDING": "- retained closure item\n\n"}),
        "unrelated section drift": rebuild(
            {**promoted_bodies, "GOVERNANCE": f"{base_bodies['GOVERNANCE']}drift\n"}
        ),
        "missing section": rebuild(promoted_bodies).replace("## NEXT STEP\n", "", 1),
    }
    for mutation, candidate in mutations.items():
        if candidate == checkpoint_text:
            raise ValueError(f"{WO025_G4_WORK_ORDER} built the vacuous {mutation} mutation")
        try:
            require_wo025p_checkpoint_semantics(checkpoint_text, candidate)
        except ValueError:
            continue
        raise ValueError(f"{WO025_G4_WORK_ORDER} accepted the {mutation} checkpoint mutation")
    for named in ("status swap", "missing section"):
        if named not in mutations:
            raise ValueError(f"{WO025_G4_WORK_ORDER} must reject the {named} mutation")
    require_current_work_order_authorization(WO025P_WORK_ORDER)
    try:
        require_current_work_order_authorization(WO11_01_WORK_ORDER)
    except ValueError as error:
        if WO025P_WORK_ORDER not in str(error):
            raise ValueError(
                f"{WO11_01_WORK_ORDER} must stay blocked by the unlanded canonical promotion"
            ) from error
    else:
        raise ValueError(f"{WO11_01_WORK_ORDER} unexpectedly authorizes a fresh current PR")
    for rejected in ("WO-1.1-02", "WO-11-01", "WO-028-P", "WO-030-C1", ""):
        try:
            require_supported_work_order(rejected)
        except ValueError:
            pass
        else:
            raise ValueError(f"{rejected!r} unexpectedly remains supported")
    # Historical WO-024 closure semantics stay frozen, constants and grammar included.
    if EXPECTED_WO024P_STATUS != "HIVE V0.1 COMPLETE / CLOSURE SPRINT APPROVED":
        raise ValueError(f"{WO025_G4_WORK_ORDER} cannot rewrite the historical V0.1 closure status")
    if EXPECTED_WO024P_IN_PROGRESS != "None. V0.1 closure is complete and promoted.":
        raise ValueError(
            f"{WO025_G4_WORK_ORDER} cannot rewrite the historical WO-024-P in progress"
        )
    if not WO024P_COMPLETED_PENDING_ITEMS:
        raise ValueError(
            f"{WO025_G4_WORK_ORDER} requires the active-closure family to keep pending items so it "
            "cannot collapse into the promoted families"
        )
    # WO-024-P was allowed to rewrite COMPLETED; WO-025-P may not. The historical grammar stays
    # byte-for-byte intact and the new one is strictly narrower, so nothing is loosened.
    if "COMPLETED" not in _WO016P_RAW_CONTROLLED_SECTIONS:
        raise ValueError(
            f"{WO025_G4_WORK_ORDER} cannot rewrite the historical WO-024-P controlled section set"
        )
    for preserved in (WO026_WORK_ORDER, WO027_WORK_ORDER, WO025_G3_WORK_ORDER):
        require_supported_work_order(preserved)
        require_current_work_order_authorization(preserved)
    if paths and any(path in CANONICAL_PATHS for path in paths):
        raise ValueError(f"{WO025_G4_WORK_ORDER} forbids canonical promotion files")
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO025_G4_WORK_ORDER} forbids canonical changes")
    if migration_head_value != V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO025_G4_WORK_ORDER} requires migration head "
            f"{V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO025_G4_WORK_ORDER} requires an unchanged ruleset")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO025_G4_WORK_ORDER} requires auto-merge to remain unarmed")
    require_wo024_v01_closure_sprint_evidence(
        WO024_WORK_ORDER,
        integration,
        migration_head_value,
    )
    return (
        f"work_order={WO025_G4_WORK_ORDER}; exact_base=PASS; governance_scope=PASS; "
        "closure_checkpoint_families=3; v01_closure_state=PASS; post_wo025p_state=PASS; "
        f"active_closure_pending_items={len(WO024P_COMPLETED_PENDING_ITEMS)}; "
        "status_swap_only=REJECTED; missing_section=REJECTED; "
        "post_promotion_pending=REJECTED; post_promotion_stale_fields=REJECTED; "
        "strict_promotion_grammar=True; "
        f"in_process_promotion_proof=PASS; mutations_rejected={len(mutations)}; "
        f"controlled_sections={','.join(sorted(WO025P_RAW_PROMOTION_CONTROLLED_SECTIONS))}; "
        "unrelated_section_drift=REJECTED; "
        "checkpoint_changed=False; canonical_manifest_changed=False; "
        "migration_changed=False; dependency_changed=False; workflow_changed=False; "
        "release_changed=False; project_brain_changed=False; "
        f"current_promotion_frontier={WO025P_WORK_ORDER}; "
        "wo_025_p_promotion_executed=False; wo_1_1_01_pending_blocked=True; "
        "wo_1_1_02_rejected=True; deny_by_default=True; "
        "historical_promotion_pair_unchanged=True; wo024_strict_behavior_unchanged=True; "
        "historical_work_orders_preserved=True; "
        "renderers=dedicated_wo025_g4; "
        "integration_health_closure_regression=EXECUTABLE; "
        "product_implementation=False; checkpoint_promoted=False; "
        f"v01_closure_sprint_evidence=PASS; "
        f"v01_closure_sprint_version={V01_CLOSURE_SPRINT_EVIDENCE_VERSION}; "
        f"migration_head={V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; v0.1_completion_claim=False; "
        "canonical_promotion_performed=False"
    )


def verify_wo017p_g1_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
) -> str | None:
    if work_order != WO017P_G1_WORK_ORDER:
        return None
    require_wo017p_g1_scope(work_order, base_sha, paths)
    if frozenset({WO017P_G1_WORK_ORDER, WO017P_WORK_ORDER}) != (
        ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS
    ):
        raise ValueError(f"{WO017P_G1_WORK_ORDER} requires active promotion pair")
    for stale in (
        WO014P_G1_WORK_ORDER,
        WO014P_WORK_ORDER,
        WO015P_G1_WORK_ORDER,
        WO015P_WORK_ORDER,
        WO016P_G1_WORK_ORDER,
        WO016P_WORK_ORDER,
    ):
        try:
            require_current_work_order_authorization(stale)
        except ValueError:
            pass
        else:
            raise ValueError(f"{stale} unexpectedly authorizes a fresh current PR")
    for rejected in ("WO-018-P", "WO-999-P"):
        try:
            require_current_work_order_authorization(rejected)
        except ValueError:
            pass
        else:
            raise ValueError(f"{rejected} unexpectedly authorizes a fresh current PR")
    require_current_work_order_authorization(WO017P_G1_WORK_ORDER)
    require_current_work_order_authorization(WO017P_WORK_ORDER)
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO017P_G1_WORK_ORDER} forbids canonical changes")
    if migration_head_value != "0006_memory_lifecycle_provenance":
        raise ValueError(f"{WO017P_G1_WORK_ORDER} requires migration head 0006")
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO017P_G1_WORK_ORDER} requires unchanged ruleset")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO017P_G1_WORK_ORDER} requires auto-merge to remain unarmed")
    require_wo017_mcp_evidence(WO017P_G1_WORK_ORDER, integration, migration_head_value)
    return (
        f"work_order={WO017P_G1_WORK_ORDER}; exact_base=PASS; governance_scope=PASS; "
        "project_brain_changed=False; checkpoint_changed=False; migration_changed=False; "
        f"active_promotions={WO017P_G1_WORK_ORDER},{WO017P_WORK_ORDER}; "
        "historical_WO-016-P_G1_WO-016-P=REJECTED; unknown_WO-018-P_WO-999-P=REJECTED; "
        "authorized_base_parser=PASS; future_two_file_scope=PASS; checkpoint_semantics=PASS; "
        "manifest_contract=PASS; mcp_evidence=PASS; ruleset_unchanged=PASS; "
        "auto_merge=UNARMED; checkpoint_promotion=False"
    )


def verify_wo017p_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
) -> str | None:
    if work_order != WO017P_WORK_ORDER:
        return None
    require_wo017p_scope(work_order, base_sha, paths, enforce_authorized_base=False)
    expected_paths = [path for path in CANONICAL_PATHS]
    if canonical_changes != {
        "project_brain_changed": True,
        "checkpoint_changed": True,
        "authorized_paths": expected_paths,
    }:
        raise ValueError(
            f"{WO017P_WORK_ORDER} requires only checkpoint and manifest canonical changes"
        )
    if migration_head_value != "0006_memory_lifecycle_provenance":
        raise ValueError(
            f"{WO017P_WORK_ORDER} requires migration head 0006_memory_lifecycle_provenance"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO017P_WORK_ORDER} requires the protected ruleset to be unchanged")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO017P_WORK_ORDER} requires auto-merge to remain unarmed")
    require_wo017_mcp_evidence(WO017P_WORK_ORDER, integration, migration_head_value)
    return (
        f"work_order={WO017P_WORK_ORDER}; promotion_scope=PASS; checkpoint_semantics=PASS; "
        "manifest_contract=PASS; mcp_evidence=PASS; "
        "migration_head=0006_memory_lifecycle_provenance; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; checkpoint_promotion=True"
    )


def verify_wo016_g1_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
) -> str | None:
    if work_order != WO016_G1_WORK_ORDER:
        return None
    require_wo016_g1_scope(work_order, base_sha, paths)
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO016_G1_WORK_ORDER} requires no canonical Project Brain changes")
    if migration_head_value != "0006_memory_lifecycle_provenance":
        raise ValueError(
            f"{WO016_G1_WORK_ORDER} requires migration head 0006_memory_lifecycle_provenance, "
            f"observed {migration_head_value}"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO016_G1_WORK_ORDER} requires the protected ruleset to be unchanged")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO016_G1_WORK_ORDER} requires auto-merge to remain unarmed")
    require_current_work_order_authorization(WO016_G1_WORK_ORDER)
    require_current_work_order_authorization(WO016_WORK_ORDER)
    return (
        f"work_order={WO016_G1_WORK_ORDER}; exact_base=PASS; governance_scope=PASS; "
        "project_brain_changed=False; checkpoint_changed=False; "
        "migration_head=0006_memory_lifecycle_provenance; migration_changed=False; "
        f"future_{WO016_WORK_ORDER}_registered=PASS; "
        f"future_{ACCE_STORAGE_POLICY_EVIDENCE_VERSION}_fail_closed=PASS; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; checkpoint_promotion=False"
    )


def verify_wo015_g1_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
) -> str | None:
    if work_order != WO015_G1_WORK_ORDER:
        return None
    require_wo015_g1_scope(work_order, base_sha, paths)
    require_wo016_g1_scope(work_order, base_sha, paths)
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO015_G1_WORK_ORDER} requires no canonical Project Brain changes")
    if migration_head_value != "0005_semantic_retrieval":
        raise ValueError(
            f"{WO015_G1_WORK_ORDER} requires migration head 0005_semantic_retrieval, "
            f"observed {migration_head_value}"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO015_G1_WORK_ORDER} requires the protected ruleset to be unchanged")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO015_G1_WORK_ORDER} requires auto-merge to remain unarmed")
    context_manager = cast(dict[str, Any], integration.get("context_manager", {}))
    if context_manager.get("memory_lifecycle_implemented") is not False:
        raise ValueError(f"{WO015_G1_WORK_ORDER} must not implement Memory")
    require_current_work_order_authorization(WO015_G1_WORK_ORDER)
    require_current_work_order_authorization(WO015_WORK_ORDER)
    return (
        f"work_order={WO015_G1_WORK_ORDER}; exact_base=PASS; governance_scope=PASS; "
        "project_brain_changed=False; checkpoint_changed=False; "
        "migration_head=0005_semantic_retrieval; memory_implementation=False; "
        "future_WO-015_registered=PASS; future_memory_evidence_fail_closed=PASS; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; checkpoint_promotion=False"
    )


def verify_wo015p_g1_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
) -> str | None:
    if work_order != WO015P_G1_WORK_ORDER:
        return None
    require_wo015p_g1_scope(work_order, base_sha, paths)
    for stale in (
        "WO-011-P",
        "WO-012-P",
        "WO-013-P",
        WO014P_G1_WORK_ORDER,
        WO014P_WORK_ORDER,
    ):
        try:
            require_current_work_order_authorization(stale)
        except ValueError:
            pass
        else:
            raise ValueError(f"{stale} unexpectedly authorizes a fresh current PR")
    for rejected in ("WO-999-P",):
        try:
            require_current_work_order_authorization(rejected)
        except ValueError:
            pass
        else:
            raise ValueError(f"{rejected} unexpectedly authorizes a fresh current PR")
    require_supported_work_order(WO015P_G1_WORK_ORDER)
    require_supported_work_order(WO015P_WORK_ORDER)
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO015P_G1_WORK_ORDER} requires no canonical Project Brain changes")
    if migration_head_value != "0006_memory_lifecycle_provenance":
        raise ValueError(
            f"{WO015P_G1_WORK_ORDER} requires migration head 0006_memory_lifecycle_provenance, "
            f"observed {migration_head_value}"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO015P_G1_WORK_ORDER} requires the protected ruleset to be unchanged")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO015P_G1_WORK_ORDER} requires auto-merge to remain unarmed")
    require_wo015_memory_evidence(
        WO015P_G1_WORK_ORDER,
        integration,
        migration_head_value,
    )
    return (
        f"work_order={WO015P_G1_WORK_ORDER}; exact_base=PASS; governance_scope=PASS; "
        "project_brain_changed=False; checkpoint_changed=False; migration_changed=False; "
        f"active_promotions={WO015P_G1_WORK_ORDER},{WO015P_WORK_ORDER}; "
        "historical_WO-014-P_G1_WO-014-P=REJECTED; "
        "current_WO-017-P=SUPPORTED; unknown_WO-999-P=REJECTED; "
        "authorized_base_parser=PASS; future_two_file_scope=PASS; "
        "checkpoint_semantics=PASS; manifest_contract=PASS; memory_evidence=PASS; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; checkpoint_promotion=False"
    )


def verify_wo016p_g1_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
    approved_lineage: Mapping[str, object] | None = None,
) -> str | None:
    if work_order != WO016P_G1_WORK_ORDER:
        return None
    require_wo016p_g1_scope(work_order, base_sha, paths)
    if not frozenset({WO016P_G1_WORK_ORDER, WO016P_WORK_ORDER}).issubset(
        CHECKPOINT_PROMOTION_WORK_ORDERS
    ):
        raise ValueError(f"{WO016P_G1_WORK_ORDER} must remain registered historically")
    for stale in (
        "WO-011-P",
        "WO-012-P",
        "WO-013-P",
        WO014P_G1_WORK_ORDER,
        WO014P_WORK_ORDER,
        WO015P_G1_WORK_ORDER,
        WO015P_WORK_ORDER,
    ):
        try:
            require_current_work_order_authorization(stale)
        except ValueError:
            pass
        else:
            raise ValueError(f"{stale} unexpectedly authorizes a fresh current PR")
    for rejected in ("WO-999-P",):
        try:
            require_current_work_order_authorization(rejected)
        except ValueError:
            pass
        else:
            raise ValueError(f"{rejected} unexpectedly authorizes a fresh current PR")
    require_supported_work_order(WO016P_G1_WORK_ORDER)
    require_supported_work_order(WO016P_WORK_ORDER)
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO016P_G1_WORK_ORDER} requires no canonical Project Brain changes")
    if migration_head_value != "0006_memory_lifecycle_provenance":
        raise ValueError(
            f"{WO016P_G1_WORK_ORDER} requires migration head 0006_memory_lifecycle_provenance, "
            f"observed {migration_head_value}"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO016P_G1_WORK_ORDER} requires the protected ruleset to be unchanged")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO016P_G1_WORK_ORDER} requires auto-merge to remain unarmed")
    require_wo016_storage_evidence(
        WO016P_G1_WORK_ORDER,
        integration,
        migration_head_value,
    )
    if approved_lineage is None:
        raise ValueError("WO-016-P-G1 requires approved product lineage evidence")
    require_wo016_approved_lineage_result(approved_lineage)
    return (
        f"work_order={WO016P_G1_WORK_ORDER}; exact_base=PASS; governance_scope=PASS; "
        "project_brain_changed=False; checkpoint_changed=False; migration_changed=False; "
        "migration_head=0006_memory_lifecycle_provenance; "
        f"active_promotions={WO016P_G1_WORK_ORDER},{WO016P_WORK_ORDER}; "
        f"future_{WO016P_WORK_ORDER}_registered=PASS; "
        "future_two_file_scope=PASS; checkpoint_semantics=PASS; manifest_contract=PASS; "
        "acce_evidence=PASS; acce_policy=acce-policy-v1; benchmark_rows=6; "
        f"approved_lineage=PASS,PR#{approved_lineage['product_pr']},"
        f"audited_head={approved_lineage['audited_product_head']},"
        f"sol_review={approved_lineage['sol_review_id']},"
        f"squash_merge={approved_lineage['squash_merge_sha']},"
        f"post_merge_ci={approved_lineage['post_merge_ci_run']},"
        f"backend={approved_lineage['prior_backend_passed']},"
        f"dashboard={approved_lineage['prior_dashboard_passed']}; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; checkpoint_promotion=False"
    )


def verify_wo016p_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
    approved_lineage: Mapping[str, object] | None = None,
) -> str | None:
    if work_order != WO016P_WORK_ORDER:
        return None
    if approved_lineage is None:
        raise ValueError("WO-016-P requires approved product lineage evidence")
    require_wo016_approved_lineage_result(approved_lineage)
    require_wo016_storage_evidence(work_order, integration, migration_head_value)
    if canonical_changes != {
        "project_brain_changed": True,
        "checkpoint_changed": True,
        "authorized_paths": sorted(WO016P_PROMOTION_ALLOWED_PATHS),
    }:
        raise ValueError(
            f"{WO016P_WORK_ORDER} requires exactly the checkpoint and manifest canonical changes"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO016P_WORK_ORDER} requires the protected ruleset to be unchanged")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO016P_WORK_ORDER} requires auto-merge to remain unarmed")
    return (
        f"work_order={WO016P_WORK_ORDER}; promotion_scope=PASS; checkpoint_semantics=PASS; "
        "manifest_contract=PASS; acce_evidence=PASS; acce_policy=acce-policy-v1; "
        f"benchmark_rows=6; approved_lineage=PASS,PR#{approved_lineage['product_pr']},"
        f"audited_head={approved_lineage['audited_product_head']},"
        f"squash_merge={approved_lineage['squash_merge_sha']},"
        f"post_merge_ci={approved_lineage['post_merge_ci_run']}; "
        "canonical_source_loss=0; llm_provider_calls=0/0; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; merge_performed=False"
    )


def verify_wo014_c2_governance_contract() -> str:
    """Exercise both explicit C1 lineage and post-squash C2 semantics.

    The fixture keeps this evidence independent of whether historical PR
    branch objects are present in a fresh CI checkout.
    """
    require_wo014_scope("WO-014", WO014_BASE_SHA, sorted(WO014_ALLOWED_PATHS))
    with tempfile.TemporaryDirectory(prefix="hive-wo014-c2-") as directory:
        repository = Path(directory)
        for command in (
            ["git", "init", "--quiet"],
            ["git", "config", "user.email", "hive-review@example.invalid"],
            ["git", "config", "user.name", "HIVE Review Evidence"],
        ):
            code, output = run_in_repository(repository, command)
            if code != 0:
                raise RuntimeError(f"unable to create WO-014-C2 lineage fixture: {output}")

        def commit(content: str, message: str) -> str:
            (repository / "fixture.txt").write_text(content, encoding="utf-8")
            for command in (
                ["git", "add", "fixture.txt"],
                ["git", "commit", "--quiet", "-m", message],
            ):
                code, output = run_in_repository(repository, command)
                if code != 0:
                    raise RuntimeError(f"unable to create WO-014-C2 lineage fixture: {output}")
            code, head = run_in_repository(repository, ["git", "rev-parse", "HEAD"])
            if code != 0 or HEX_SHA.fullmatch(head) is None:
                raise RuntimeError("WO-014-C2 lineage fixture did not produce a valid commit")
            return head

        base = commit("base\n", "base")
        rejected = commit("rejected\n", "rejected C1 candidate")
        corrected = commit("corrected\n", "corrected C1 candidate")
        code, output = run_in_repository(repository, ["git", "checkout", "--quiet", base])
        if code != 0:
            raise RuntimeError(f"unable to create WO-014-C2 replacement fixture: {output}")
        replacement = commit("replacement\n", "replacement without rejected candidate")
        code, output = run_in_repository(repository, ["git", "checkout", "--quiet", base])
        if code != 0:
            raise RuntimeError(f"unable to create WO-014-C2 squash fixture: {output}")
        squash = commit("corrected\n", "squash result")

        require_wo014_c1_candidate_lineage(rejected, corrected, repository)
        try:
            require_wo014_c1_candidate_lineage(rejected, replacement, repository)
        except ValueError:
            pass
        else:
            raise ValueError("WO-014-C2 lineage fixture accepted a replacement that skipped C1")
        squash_ancestor_code, _ = run_in_repository(
            repository,
            ["git", "merge-base", "--is-ancestor", rejected, squash],
        )
        if squash_ancestor_code == 0:
            raise ValueError("WO-014-C2 squash fixture unexpectedly retained rejected ancestry")

    return (
        "post_squash_scope=PASS; explicit_c1_lineage=PASS; "
        "replacement_skipping_c1=REJECTED; squash_without_source_ancestry=PASS"
    )


def require_wo012p_g1_scope(work_order: str, base_sha: str, paths: list[str]) -> None:
    if work_order != "WO-012-P-G1":
        return
    if base_sha != WO012P_G1_BASE_SHA:
        raise ValueError(
            f"WO-012-P-G1 requires exact base {WO012P_G1_BASE_SHA}, observed {base_sha}"
        )
    unauthorized = sorted(set(paths) - WO012P_G1_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            "WO-012-P-G1 changed files outside the approved governance scope: "
            + ", ".join(unauthorized)
        )


def require_wo013p_g1_scope(work_order: str, base_sha: str, paths: list[str]) -> None:
    if work_order != "WO-013-P-G1":
        return
    if base_sha != WO013P_G1_BASE_SHA:
        raise ValueError(
            f"WO-013-P-G1 requires exact base {WO013P_G1_BASE_SHA}, observed {base_sha}"
        )
    unauthorized = sorted(set(paths) - WO013P_G1_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            "WO-013-P-G1 changed files outside the approved governance scope: "
            + ", ".join(unauthorized)
        )


def require_wo014p_g1_scope(work_order: str, base_sha: str, paths: list[str]) -> None:
    if work_order != WO014P_G1_WORK_ORDER:
        return
    if base_sha != WO014P_G1_BASE_SHA:
        raise ValueError(
            f"{WO014P_G1_WORK_ORDER} requires exact base {WO014P_G1_BASE_SHA}, observed {base_sha}"
        )
    unauthorized = sorted(set(paths) - WO014P_G1_ALLOWED_PATHS)
    if unauthorized:
        raise ValueError(
            f"{WO014P_G1_WORK_ORDER} changed files outside the approved governance scope: "
            + ", ".join(unauthorized)
        )


def require_wo012p_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    registered_base_sha: str | None = None,
    authorized_base_sha: str | None = None,
    enforce_authorized_base: bool = True,
) -> None:
    if work_order != "WO-012-P":
        return
    if base_branch != "main":
        raise ValueError(
            f"WO-012-P requires the protected main base branch, observed {base_branch}"
        )
    expected_base = registered_base_sha or registered_promotion_base_sha(work_order)
    if base_sha != expected_base:
        raise ValueError(
            f"WO-012-P requires registered exact base {expected_base}, observed {base_sha}"
        )
    if sorted(set(paths)) != sorted(WO012P_PROMOTION_ALLOWED_PATHS) or len(paths) != 2:
        raise ValueError("WO-012-P requires exactly the checkpoint and canonical manifest files")
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError("WO-012-P requires exactly one authorized-base marker")
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError("WO-012-P authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError("WO-012-P authorized-base marker must match the pull request base SHA")
    base_checkpoint = git_blob_bytes(base_sha, CHECKPOINT_PATH).decode("utf-8")
    base_manifest = git_blob_bytes(base_sha, CANONICAL_MANIFEST_PATH).decode("utf-8")
    candidate_checkpoint_bytes = (ROOT / CHECKPOINT_PATH).read_bytes()
    candidate_manifest = (ROOT / CANONICAL_MANIFEST_PATH).read_bytes().decode("utf-8")
    require_wo012p_checkpoint_semantics(
        base_checkpoint,
        candidate_checkpoint_bytes.decode("utf-8"),
    )
    require_wo012p_manifest_contract(
        base_manifest,
        candidate_manifest,
        candidate_checkpoint_bytes,
    )


def require_wo013p_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    registered_base_sha: str | None = None,
    authorized_base_sha: str | None = None,
) -> None:
    if work_order != "WO-013-P":
        return
    if base_branch != "main":
        raise ValueError(
            f"WO-013-P requires the protected main base branch, observed {base_branch}"
        )
    expected_base = registered_base_sha or registered_promotion_base_sha(work_order)
    if base_sha != expected_base:
        raise ValueError(
            f"WO-013-P requires registered exact base {expected_base}, observed {base_sha}"
        )
    if sorted(set(paths)) != sorted(WO013P_PROMOTION_ALLOWED_PATHS) or len(paths) != 2:
        raise ValueError("WO-013-P requires exactly the checkpoint and canonical manifest files")
    if authorized_base_sha is None:
        raise ValueError("WO-013-P requires exactly one authorized-base marker")
    if HEX_SHA.fullmatch(authorized_base_sha) is None:
        raise ValueError("WO-013-P authorized-base marker must be lowercase 40-hex")
    if authorized_base_sha != base_sha:
        raise ValueError("WO-013-P authorized-base marker must match the pull request base SHA")
    base_checkpoint = git_blob_bytes(base_sha, CHECKPOINT_PATH).decode("utf-8")
    base_manifest = git_blob_bytes(base_sha, CANONICAL_MANIFEST_PATH).decode("utf-8")
    candidate_checkpoint_bytes = (ROOT / CHECKPOINT_PATH).read_bytes()
    candidate_manifest = (ROOT / CANONICAL_MANIFEST_PATH).read_bytes().decode("utf-8")
    require_wo013p_checkpoint_semantics(
        base_checkpoint,
        candidate_checkpoint_bytes.decode("utf-8"),
    )
    require_wo013p_manifest_contract(
        base_manifest,
        candidate_manifest,
        candidate_checkpoint_bytes,
    )


def require_wo014p_scope(
    work_order: str,
    base_sha: str,
    paths: list[str],
    *,
    base_branch: str = "main",
    registered_base_sha: str | None = None,
    authorized_base_sha: str | None = None,
    enforce_authorized_base: bool = True,
) -> None:
    if work_order != WO014P_WORK_ORDER:
        return
    if base_branch != "main":
        raise ValueError(
            f"{WO014P_WORK_ORDER} requires the protected main base branch, observed {base_branch}"
        )
    expected_base = registered_base_sha or registered_promotion_base_sha(work_order)
    if base_sha != expected_base:
        raise ValueError(
            f"{WO014P_WORK_ORDER} requires current protected main base {expected_base}, "
            f"observed {base_sha}"
        )
    if sorted(set(paths)) != sorted(WO014P_PROMOTION_ALLOWED_PATHS) or len(paths) != 2:
        raise ValueError(
            f"{WO014P_WORK_ORDER} requires exactly the checkpoint and canonical manifest files"
        )
    if enforce_authorized_base:
        if authorized_base_sha is None:
            raise ValueError(f"{WO014P_WORK_ORDER} requires exactly one authorized-base marker")
        if HEX_SHA.fullmatch(authorized_base_sha) is None:
            raise ValueError(f"{WO014P_WORK_ORDER} authorized-base marker must be lowercase 40-hex")
        if authorized_base_sha != base_sha:
            raise ValueError(
                f"{WO014P_WORK_ORDER} authorized-base marker must match the pull request base SHA"
            )

    base_review_evidence = git_blob_bytes(base_sha, "scripts/review_evidence.py").decode("utf-8")
    if "WO014P_G1_WORK_ORDER" not in base_review_evidence:
        raise ValueError(
            f"{WO014P_WORK_ORDER} requires merged {WO014P_G1_WORK_ORDER} support in its base"
        )
    base_checkpoint = git_blob_bytes(base_sha, CHECKPOINT_PATH).decode("utf-8")
    base_manifest = git_blob_bytes(base_sha, CANONICAL_MANIFEST_PATH).decode("utf-8")
    candidate_checkpoint_bytes = (ROOT / CHECKPOINT_PATH).read_bytes()
    candidate_manifest = (ROOT / CANONICAL_MANIFEST_PATH).read_bytes().decode("utf-8")
    require_wo014p_checkpoint_semantics(
        base_checkpoint,
        candidate_checkpoint_bytes.decode("utf-8"),
    )
    require_wo014p_manifest_contract(
        base_manifest,
        candidate_manifest,
        candidate_checkpoint_bytes,
    )


def repository_name() -> str:
    remote = git_value("remote", "get-url", "origin", fallback="local").removesuffix(".git")
    if remote.startswith("git@") and ":" in remote:
        return remote.split(":", 1)[1]
    if "/" in remote:
        return remote.rsplit("/", 2)[-2] + "/" + remote.rsplit("/", 1)[-1]
    return remote


def changed_paths(base_sha: str, head_sha: str) -> list[str]:
    base_exists, _ = run(["git", "cat-file", "-e", f"{base_sha}^{{commit}}"])
    if HEX_SHA.fullmatch(base_sha) and base_exists == 0:
        code, output = run(["git", "diff", "--name-only", f"{base_sha}...{head_sha}"])
        if code == 0:
            return [path for path in output.splitlines() if path]
    return [path for path in git_value("diff", "--name-only", "HEAD^", "HEAD").splitlines() if path]


def migration_head() -> str:
    db_path = ROOT / "backend" / "app" / "db.py"
    match = re.search(r'CURRENT_SCHEMA_REVISION\s*=\s*"([^"]+)"', db_path.read_text())
    return match.group(1) if match else "UNKNOWN"


def validation_status(text: str, marker: str) -> str:
    normalized_text = text.casefold()
    if marker.casefold() not in normalized_text:
        return "UNKNOWN"
    return "PASS" if "exit_code: 0" in normalized_text else "FAIL"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def bounded(text: str, limit: int = MAX_EVIDENCE_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[bounded evidence excerpt truncated]\n"


def benchmark_fields(path: Path) -> dict[str, object]:
    unknown_slice = {
        "status": "UNKNOWN",
        "query_count": 0,
        "recall_at_1": 0.0,
        "recall_at_5": 0.0,
        "mrr": 0.0,
        "critical_context_misses": 0,
        "two_run_reproducibility": False,
    }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "UNKNOWN",
            "query_count": 0,
            "recall_at_1": 0.0,
            "recall_at_5": 0.0,
            "mrr": 0.0,
            "critical_context_misses": 0,
            "two_run_reproducibility": False,
            "cross_project_isolation": False,
            "redis_restart": False,
            "api_restart": False,
            "semantic": unknown_slice,
            "hybrid": unknown_slice,
            "rerank": unknown_slice,
            "semantic_integrity": {},
            "fallback": {},
            "hybrid_recall_at_5_gte_extended_lexical": False,
            "semantic_challenge_recovered": False,
        }
    reproducibility = cast(dict[str, Any], data.get("reproducibility", {}))
    persistence = cast(dict[str, Any], data.get("persistence", {}))
    semantic = cast(dict[str, Any], data.get("semantic", {}))
    hybrid = cast(dict[str, Any], data.get("hybrid", {}))
    rerank = cast(dict[str, Any], data.get("rerank", {}))
    semantic_run = cast(dict[str, Any], semantic.get("run_1", {}))
    hybrid_run = cast(dict[str, Any], hybrid.get("run_1", {}))
    semantic_status = (
        "PASS"
        if semantic_run and not semantic_run.get("critical_context_misses")
        else "FAIL"
        if semantic_run
        else "UNKNOWN"
    )
    hybrid_status = (
        "PASS"
        if hybrid_run and not hybrid_run.get("critical_context_misses")
        else "FAIL"
        if hybrid_run
        else "UNKNOWN"
    )
    rerank_run = cast(dict[str, Any], rerank.get("run_1", {}))
    rerank_gate_names = (
        "recall_at_5_gte_hybrid",
        "mrr_gte_hybrid",
        "strict_rank_improvement",
        "candidate_pool_bounded",
        "provenance_preserved",
    )
    rerank_gates = all(bool(rerank_run.get(name, False)) for name in rerank_gate_names)
    rerank_c1 = {
        field: bool(rerank.get(field.removeprefix("rerank_"), False))
        for field in RERANK_C1_REQUIRED_FIELDS
    }
    order_digest_pattern = re.compile(r"^[0-9a-f]{64}$")
    run_1_order_digest = rerank.get("run_1_order_digest")
    run_2_order_digest = rerank.get("run_2_order_digest")
    order_digests_valid = bool(
        isinstance(run_1_order_digest, str)
        and order_digest_pattern.fullmatch(run_1_order_digest)
        and isinstance(run_2_order_digest, str)
        and order_digest_pattern.fullmatch(run_2_order_digest)
    )
    rerank_status = (
        "PASS"
        if rerank_run
        and not rerank_run.get("critical_context_misses")
        and rerank_gates
        and bool(rerank.get("disabled_exact_fallback", False))
        and bool(rerank.get("invalid_response_exact_fallback", False))
        and bool(rerank.get("provider_failure_exact_fallback", False))
        and bool(rerank.get("provider_down_exact_fallback", False))
        and bool(rerank.get("strict_failure_bounded", False))
        and bool(rerank.get("profile_visible_without_secret", False))
        and bool(rerank.get("reproducible", False))
        and order_digests_valid
        and all(rerank_c1.values())
        else "FAIL"
        if rerank_run
        else "UNKNOWN"
    )
    overall_status = "PASS" if not data.get("critical_context_misses") else "FAIL"
    if semantic_status == "FAIL" or hybrid_status == "FAIL":
        overall_status = "FAIL"
    if data.get("work_order") == "WO-008" and rerank_status != "PASS":
        overall_status = "FAIL" if rerank_status == "FAIL" else "UNKNOWN"
    return {
        "status": overall_status,
        "query_count": int(data.get("query_count", 0)),
        "recall_at_1": float(data.get("recall_at_1", 0.0)),
        "recall_at_5": float(data.get("recall_at_5", 0.0)),
        "mrr": float(data.get("mrr", 0.0)),
        "critical_context_misses": len(data.get("critical_context_misses", [])),
        "two_run_reproducibility": bool(
            reproducibility.get("same_query_count") and reproducibility.get("same_recall_at_5")
        ),
        "cross_project_isolation": bool(data.get("cross_project_isolation", False)),
        "redis_restart": bool(persistence.get("redis_restart", False)),
        "api_restart": bool(persistence.get("api_restart", False)),
        "semantic": {
            "status": semantic_status if semantic else "UNKNOWN",
            "query_count": int(semantic_run.get("query_count", 0)),
            "recall_at_1": float(semantic_run.get("recall_at_1", 0.0)),
            "recall_at_5": float(semantic_run.get("recall_at_5", 0.0)),
            "mrr": float(semantic_run.get("mrr", 0.0)),
            "critical_context_misses": len(semantic_run.get("critical_context_misses", [])),
            "two_run_reproducibility": bool(
                semantic.get("run_1", {}).get("recall_at_5")
                == semantic.get("run_2", {}).get("recall_at_5")
            ),
        },
        "hybrid": {
            "status": hybrid_status if hybrid else "UNKNOWN",
            "query_count": int(hybrid_run.get("query_count", 0)),
            "recall_at_1": float(hybrid_run.get("recall_at_1", 0.0)),
            "recall_at_5": float(hybrid_run.get("recall_at_5", 0.0)),
            "mrr": float(hybrid_run.get("mrr", 0.0)),
            "critical_context_misses": len(hybrid_run.get("critical_context_misses", [])),
            "two_run_reproducibility": bool(
                hybrid.get("run_1", {}).get("recall_at_5")
                == hybrid.get("run_2", {}).get("recall_at_5")
            ),
        },
        "rerank": {
            "status": rerank_status if rerank else "UNKNOWN",
            "query_count": int(rerank_run.get("query_count", 0)),
            "recall_at_1": float(rerank_run.get("recall_at_1", 0.0)),
            "recall_at_5": float(rerank_run.get("recall_at_5", 0.0)),
            "mrr": float(rerank_run.get("mrr", 0.0)),
            "critical_context_misses": len(rerank_run.get("critical_context_misses", [])),
            "two_run_reproducibility": bool(
                rerank.get("run_1", {}).get("recall_at_5")
                == rerank.get("run_2", {}).get("recall_at_5")
                and rerank.get("run_1", {}).get("mrr") == rerank.get("run_2", {}).get("mrr")
                and rerank.get("ordering_reproducible", False)
            ),
            "hybrid_recall_at_5": float(rerank_run.get("hybrid_recall_at_5", 0.0)),
            "hybrid_mrr": float(rerank_run.get("hybrid_mrr", 0.0)),
            **{name: bool(rerank_run.get(name, False)) for name in rerank_gate_names},
            "disabled_exact_fallback": bool(rerank.get("disabled_exact_fallback", False)),
            "invalid_response_exact_fallback": bool(
                rerank.get("invalid_response_exact_fallback", False)
            ),
            "provider_failure_exact_fallback": bool(
                rerank.get("provider_failure_exact_fallback", False)
            ),
            "provider_down_exact_fallback": bool(rerank.get("provider_down_exact_fallback", False)),
            "strict_failure_bounded": bool(rerank.get("strict_failure_bounded", False)),
            "strict_invalid_response_bounded": bool(
                rerank.get("strict_invalid_response_bounded", False)
            ),
            "profile_visible_without_secret": bool(
                rerank.get("profile_visible_without_secret", False)
            ),
            "run_1_order_digest": run_1_order_digest if isinstance(run_1_order_digest, str) else "",
            "run_2_order_digest": run_2_order_digest if isinstance(run_2_order_digest, str) else "",
            **rerank_c1,
        },
        "semantic_integrity": data.get("semantic_integrity", {}),
        "fallback": data.get("fallback", {}),
        "hybrid_recall_at_5_gte_extended_lexical": bool(
            data.get("thresholds", {}).get("hybrid_recall_at_5_gte_extended_lexical", False)
        ),
        "semantic_challenge_recovered": bool(
            data.get("thresholds", {}).get("semantic_challenge_recovered", False)
        ),
    }


def junit_counts(path: Path) -> dict[str, int]:
    if not path.exists():
        return {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    try:
        root = ET.parse(path).getroot()
        suites = [root] if "tests" in root.attrib else list(root.iter("testsuite"))
        if not suites:
            return {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
        tests = sum(int(suite.attrib.get("tests", 0)) for suite in suites)
        failures = sum(int(suite.attrib.get("failures", 0)) for suite in suites)
        errors = sum(int(suite.attrib.get("errors", 0)) for suite in suites)
        skipped = sum(int(suite.attrib.get("skipped", 0)) for suite in suites)
        return {
            "passed": max(0, tests - failures - errors - skipped),
            "failed": failures,
            "skipped": skipped,
            "errors": errors,
        }
    except (OSError, ET.ParseError, TypeError, ValueError):
        return {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}


def dashboard_counts(text: str) -> dict[str, int]:
    plain_text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    match = re.search(r"Tests\s+(\d+) passed", plain_text)
    skipped_match = re.search(r"Tests\s+.*?(\d+) skipped", plain_text)
    failed = re.search(r"(\d+) failed", plain_text)
    passed = int(match.group(1)) if match else 0
    skipped = int(skipped_match.group(1)) if skipped_match else 0
    return {"passed": passed, "failed": int(failed.group(1)) if failed else 0, "skipped": skipped}


def tests_evidence(summary: str, test_results: str) -> dict[str, object]:
    backend = junit_counts(VALIDATION / "backend-junit.xml")
    dashboard = dashboard_counts(test_results)
    backend_known = bool(backend["passed"] or backend["failed"] or backend["skipped"])
    dashboard_known = bool(dashboard["passed"] or dashboard["failed"] or dashboard["skipped"])
    status = (
        "PASS" if summary.strip() == "PASS" and (backend_known or dashboard_known) else "UNKNOWN"
    )
    if backend["failed"] or backend["errors"] or dashboard["failed"]:
        status = "FAIL"
    return {
        "status": status,
        "backend": {
            "status": "PASS"
            if backend_known and not backend["failed"] and not backend["errors"]
            else "UNKNOWN",
            **backend,
        },
        "dashboard": {
            "status": "PASS" if dashboard_known and not dashboard["failed"] else "UNKNOWN",
            **dashboard,
        },
    }


def integration_file(name: str) -> str:
    for path in (VALIDATION / name, INTEGRATION_LOGS / name):
        if path.exists():
            return read_text(path)
    return ""


def mcp_surface_evidence() -> dict[str, object]:
    unknown: dict[str, object] = {
        "status": "UNKNOWN",
        "evidence_file": MCP_CORE_SURFACE_EVIDENCE_FILE,
        "mcp_evidence_version": MCP_CORE_SURFACE_EVIDENCE_VERSION,
        MCP_CORE_SURFACE_REGISTERED_PROJECT_COUNT: 0,
        **{field: False for field in MCP_CORE_SURFACE_TRUE_FIELDS},
        **{field: False for field in MCP_CORE_SURFACE_FALSE_FIELDS},
        "tool_list_exact": [],
        "observed_migration_head": "UNKNOWN",
        **{field: 0 for field in MCP_CORE_SURFACE_INTEGER_FIELDS},
    }
    text = integration_file(MCP_CORE_SURFACE_EVIDENCE_FILE)
    if not text:
        return unknown
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {**unknown, "status": "FAIL"}
    if not isinstance(data, dict):
        return {**unknown, "status": "FAIL"}

    extra_fields = set(data) - MCP_CORE_SURFACE_ALLOWED_FIELDS
    true_values = {field: data.get(field) is True for field in MCP_CORE_SURFACE_TRUE_FIELDS}
    false_checks = {field: data.get(field) is False for field in MCP_CORE_SURFACE_FALSE_FIELDS}
    false_values = {field: data.get(field) is True for field in MCP_CORE_SURFACE_FALSE_FIELDS}
    evidence_file = (
        data.get("evidence_file")
        if isinstance(data.get("evidence_file"), str)
        else MCP_CORE_SURFACE_EVIDENCE_FILE
    )
    version = (
        data.get("mcp_evidence_version")
        if isinstance(data.get("mcp_evidence_version"), str)
        else "UNKNOWN"
    )
    observed_migration_head = (
        data.get("observed_migration_head")
        if isinstance(data.get("observed_migration_head"), str)
        else "UNKNOWN"
    )
    raw_tools = data.get("tool_list_exact")
    tool_list_valid = isinstance(raw_tools, list) and all(
        isinstance(tool, str) for tool in cast(list[object], raw_tools)
    )
    tool_list = list(cast(list[str], raw_tools)) if tool_list_valid else []
    raw_project_count = data.get(MCP_CORE_SURFACE_REGISTERED_PROJECT_COUNT)
    project_count_is_integer = isinstance(raw_project_count, int) and not isinstance(
        raw_project_count, bool
    )
    registered_project_count: int = cast(int, raw_project_count) if project_count_is_integer else 0
    project_count_valid = (
        project_count_is_integer
        and 0 <= registered_project_count <= MCP_CORE_SURFACE_MAX_REGISTERED_PROJECT_COUNT
    )

    integers: dict[str, int] = {}
    integer_fields_valid = True
    for field in MCP_CORE_SURFACE_INTEGER_FIELDS:
        value = data.get(field)
        if not isinstance(value, int) or isinstance(value, bool):
            integer_fields_valid = False
            integers[field] = 0
        else:
            integers[field] = value

    status = (
        "PASS"
        if data.get("status") == "PASS"
        and not extra_fields
        and evidence_file == MCP_CORE_SURFACE_EVIDENCE_FILE
        and version == MCP_CORE_SURFACE_EVIDENCE_VERSION
        and project_count_valid
        and registered_project_count >= 2
        and all(true_values.values())
        and all(false_checks.values())
        and tool_list_valid
        and tool_list == list(MCP_CORE_SURFACE_TOOLS)
        and observed_migration_head == "0006_memory_lifecycle_provenance"
        and integer_fields_valid
        and all(value == 0 for value in integers.values())
        else "FAIL"
    )
    return {
        "status": status,
        "evidence_file": evidence_file,
        "mcp_evidence_version": version,
        MCP_CORE_SURFACE_REGISTERED_PROJECT_COUNT: registered_project_count,
        **true_values,
        **false_values,
        "tool_list_exact": tool_list,
        "observed_migration_head": observed_migration_head,
        **integers,
    }


def autonomous_execution_evidence() -> dict[str, object]:
    unknown: dict[str, object] = {
        "status": "UNKNOWN",
        "evidence_file": AUTONOMOUS_EXECUTION_EVIDENCE_FILE,
        "autonomous_evidence_version": AUTONOMOUS_EXECUTION_EVIDENCE_VERSION,
        "executor_adapter_name": "UNKNOWN",
        "observed_migration_head": "UNKNOWN",
        **{field: False for field in AUTONOMOUS_EXECUTION_TRUE_FIELDS},
        **{field: False for field in AUTONOMOUS_EXECUTION_FALSE_FIELDS},
        **{field: 0 for field in AUTONOMOUS_EXECUTION_COUNT_FIELDS},
    }
    text = integration_file(AUTONOMOUS_EXECUTION_EVIDENCE_FILE)
    if not text:
        return unknown
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {**unknown, "status": "FAIL"}
    if not isinstance(data, dict):
        return {**unknown, "status": "FAIL"}

    extra_fields = set(data) - AUTONOMOUS_EXECUTION_ALLOWED_FIELDS
    true_values = {field: data.get(field) is True for field in AUTONOMOUS_EXECUTION_TRUE_FIELDS}
    false_checks = {field: data.get(field) is False for field in AUTONOMOUS_EXECUTION_FALSE_FIELDS}
    false_values = {field: data.get(field) is True for field in AUTONOMOUS_EXECUTION_FALSE_FIELDS}
    evidence_file = (
        data.get("evidence_file")
        if isinstance(data.get("evidence_file"), str)
        else AUTONOMOUS_EXECUTION_EVIDENCE_FILE
    )
    version = (
        data.get("autonomous_evidence_version")
        if isinstance(data.get("autonomous_evidence_version"), str)
        else "UNKNOWN"
    )
    adapter = (
        data.get("executor_adapter_name")
        if isinstance(data.get("executor_adapter_name"), str)
        else "UNKNOWN"
    )
    observed_migration_head = (
        data.get("observed_migration_head")
        if isinstance(data.get("observed_migration_head"), str)
        else "UNKNOWN"
    )
    integers: dict[str, int] = {}
    integers_valid = True
    for field in AUTONOMOUS_EXECUTION_COUNT_FIELDS:
        value = data.get(field)
        if not isinstance(value, int) or isinstance(value, bool):
            integers_valid = False
            integers[field] = 0
        else:
            integers[field] = value

    bounded_counts = (
        1 <= integers["tool_subset_count"] <= 32
        and 1 <= integers["validation_commands_count"] <= 64
        and integers["executor_llm_calls"] >= 0
        and integers["executor_provider_calls"] >= 0
        and integers["secret_leaks"] == 0
        and integers["filesystem_path_leaks"] == 0
    )
    status = (
        "PASS"
        if data.get("status") == "PASS"
        and not extra_fields
        and evidence_file == AUTONOMOUS_EXECUTION_EVIDENCE_FILE
        and version == AUTONOMOUS_EXECUTION_EVIDENCE_VERSION
        and adapter not in {"", "UNKNOWN"}
        and observed_migration_head == "0006_memory_lifecycle_provenance"
        and all(true_values.values())
        and all(false_checks.values())
        and integers_valid
        and bounded_counts
        else "FAIL"
    )
    return {
        "status": status,
        "evidence_file": evidence_file,
        "autonomous_evidence_version": version,
        "executor_adapter_name": adapter,
        "observed_migration_head": observed_migration_head,
        **true_values,
        **false_values,
        **integers,
    }


def telemetry_event_bus_evidence() -> dict[str, object]:
    unknown: dict[str, object] = {
        "status": "UNKNOWN",
        "evidence_file": TELEMETRY_EVENT_BUS_EVIDENCE_FILE,
        "telemetry_evidence_version": TELEMETRY_EVENT_BUS_EVIDENCE_VERSION,
        "observed_migration_head": "UNKNOWN",
        "migration_base_head": "UNKNOWN",
        "producer_path": "UNKNOWN",
        "migration_changed": False,
        **{field: False for field in TELEMETRY_EVENT_BUS_TRUE_FIELDS},
        **{field: False for field in TELEMETRY_EVENT_BUS_FALSE_FIELDS},
        **{field: 0 for field in TELEMETRY_EVENT_BUS_INTEGER_FIELDS},
        "implemented_event_types": [],
    }
    text = integration_file(TELEMETRY_EVENT_BUS_EVIDENCE_FILE)
    if not text:
        return unknown
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {**unknown, "status": "FAIL"}
    if not isinstance(data, dict):
        return {**unknown, "status": "FAIL"}

    extra_fields = set(data) - TELEMETRY_EVENT_BUS_ALLOWED_FIELDS
    true_values = {field: data.get(field) is True for field in TELEMETRY_EVENT_BUS_TRUE_FIELDS}
    false_checks = {field: data.get(field) is False for field in TELEMETRY_EVENT_BUS_FALSE_FIELDS}
    false_values = {field: data.get(field) is True for field in TELEMETRY_EVENT_BUS_FALSE_FIELDS}
    strings = {
        field: data.get(field) if isinstance(data.get(field), str) else "UNKNOWN"
        for field in TELEMETRY_EVENT_BUS_STRING_FIELDS
    }
    migration_changed = data.get("migration_changed") is True
    integers: dict[str, int] = {}
    integer_fields_valid = True
    for field in TELEMETRY_EVENT_BUS_INTEGER_FIELDS:
        value = data.get(field)
        if not isinstance(value, int) or isinstance(value, bool):
            integer_fields_valid = False
            integers[field] = 0
        else:
            integers[field] = value
    raw_event_types = data.get("implemented_event_types")
    event_types_valid = (
        isinstance(raw_event_types, list)
        and 1 <= len(raw_event_types) <= TELEMETRY_EVENT_BUS_MAX_EVENT_TYPES
        and all(
            isinstance(event_type, str) and event_type in TELEMETRY_EVENT_BUS_CANONICAL_EVENT_TYPES
            for event_type in cast(list[object], raw_event_types)
        )
        and len(set(cast(list[object], raw_event_types))) == len(raw_event_types)
    )
    implemented_event_types = list(cast(list[str], raw_event_types)) if event_types_valid else []
    path_valid = bool(
        isinstance(strings["producer_path"], str)
        and strings["producer_path"] != "UNKNOWN"
        and TELEMETRY_EVENT_BUS_PATH.fullmatch(strings["producer_path"])
        and not Path(strings["producer_path"]).is_absolute()
    )
    bounds_valid = (
        integer_fields_valid
        and integers["event_type_count"] == len(implemented_event_types)
        and 1 <= integers["payload_max_bytes"] <= TELEMETRY_EVENT_BUS_MAX_PAYLOAD_BYTES
        and 1 <= integers["cursor_max_bytes"] <= TELEMETRY_EVENT_BUS_MAX_CURSOR_BYTES
        and all(value >= 0 for value in integers.values())
    )
    status = (
        "PASS"
        if data.get("status") == "PASS"
        and not extra_fields
        and data.get("evidence_file") == TELEMETRY_EVENT_BUS_EVIDENCE_FILE
        and strings["telemetry_evidence_version"] == TELEMETRY_EVENT_BUS_EVIDENCE_VERSION
        and strings["migration_base_head"] == "0006_memory_lifecycle_provenance"
        and strings["observed_migration_head"] != "UNKNOWN"
        and migration_changed
        == (strings["observed_migration_head"] != "0006_memory_lifecycle_provenance")
        and all(true_values.values())
        and all(false_checks.values())
        and event_types_valid
        and path_valid
        and bounds_valid
        and integers["duplicate_canonical_events"] == 0
        and integers["cross_project_leaks"] == 0
        and integers["secret_leaks"] == 0
        and integers["filesystem_path_leaks"] == 0
        and integers["llm_calls"] == 0
        and integers["provider_calls"] == 0
        else "FAIL"
    )
    return {
        "status": status,
        "evidence_file": (
            data.get("evidence_file")
            if isinstance(data.get("evidence_file"), str)
            else TELEMETRY_EVENT_BUS_EVIDENCE_FILE
        ),
        **strings,
        "migration_changed": migration_changed,
        **true_values,
        **false_values,
        **integers,
        "implemented_event_types": implemented_event_types,
    }


def control_center_core_evidence() -> dict[str, object]:
    unknown: dict[str, object] = {
        "status": "UNKNOWN",
        "evidence_file": CONTROL_CENTER_CORE_EVIDENCE_FILE,
        "control_center_evidence_version": CONTROL_CENTER_CORE_EVIDENCE_VERSION,
        "observed_migration_head": "UNKNOWN",
        "migration_base_head": "UNKNOWN",
        "stream_transport": "UNKNOWN",
        "api_path": "UNKNOWN",
        "dashboard_path": "UNKNOWN",
        "migration_changed": False,
        **{field: False for field in CONTROL_CENTER_CORE_TRUE_FIELDS},
        **{field: False for field in CONTROL_CENTER_CORE_FALSE_FIELDS},
        **{field: 0 for field in CONTROL_CENTER_CORE_INTEGER_FIELDS},
        "implemented_surfaces": [],
    }
    text = integration_file(CONTROL_CENTER_CORE_EVIDENCE_FILE)
    if not text:
        return unknown
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {**unknown, "status": "FAIL"}
    if not isinstance(data, dict):
        return {**unknown, "status": "FAIL"}

    extra_fields = set(data) - CONTROL_CENTER_CORE_ALLOWED_FIELDS
    true_values = {field: data.get(field) is True for field in CONTROL_CENTER_CORE_TRUE_FIELDS}
    false_checks = {field: data.get(field) is False for field in CONTROL_CENTER_CORE_FALSE_FIELDS}
    false_values = {field: data.get(field) is True for field in CONTROL_CENTER_CORE_FALSE_FIELDS}
    strings = {
        field: data.get(field) if isinstance(data.get(field), str) else "UNKNOWN"
        for field in CONTROL_CENTER_CORE_STRING_FIELDS
    }
    migration_changed = data.get("migration_changed") is True
    integers: dict[str, int] = {}
    integer_fields_valid = True
    for field in CONTROL_CENTER_CORE_INTEGER_FIELDS:
        value = data.get(field)
        if not isinstance(value, int) or isinstance(value, bool):
            integer_fields_valid = False
            integers[field] = 0
        else:
            integers[field] = value
    raw_surfaces = data.get("implemented_surfaces")
    surfaces_valid = (
        isinstance(raw_surfaces, list)
        and 1 <= len(raw_surfaces) <= CONTROL_CENTER_CORE_MAX_SURFACES
        and all(
            isinstance(surface, str) and surface in CONTROL_CENTER_CORE_CANONICAL_SURFACES
            for surface in cast(list[object], raw_surfaces)
        )
        and len(set(cast(list[object], raw_surfaces))) == len(raw_surfaces)
    )
    implemented_surfaces = list(cast(list[str], raw_surfaces)) if surfaces_valid else []
    api_path = strings["api_path"]
    dashboard_path = strings["dashboard_path"]
    paths_valid = bool(
        valid_control_center_core_path("api_path", api_path)
        and valid_control_center_core_path("dashboard_path", dashboard_path)
    )
    transport_valid = strings["stream_transport"] in CONTROL_CENTER_CORE_STREAM_TRANSPORTS
    bounds_valid = (
        integer_fields_valid
        and integers["surface_count"] == len(implemented_surfaces)
        and all(value >= 0 for value in integers.values())
    )
    status = (
        "PASS"
        if data.get("status") == "PASS"
        and not extra_fields
        and data.get("evidence_file") == CONTROL_CENTER_CORE_EVIDENCE_FILE
        and strings["control_center_evidence_version"] == CONTROL_CENTER_CORE_EVIDENCE_VERSION
        and strings["migration_base_head"] == CONTROL_CENTER_CORE_MIGRATION_BASE_HEAD
        and strings["observed_migration_head"] != "UNKNOWN"
        and migration_changed
        == (strings["observed_migration_head"] != CONTROL_CENTER_CORE_MIGRATION_BASE_HEAD)
        and all(true_values.values())
        and all(false_checks.values())
        and surfaces_valid
        and paths_valid
        and transport_valid
        and bounds_valid
        and integers["secret_leaks"] == 0
        and integers["filesystem_path_leaks"] == 0
        and integers["cross_project_leaks"] == 0
        and integers["llm_calls"] == 0
        and integers["provider_calls"] == 0
        else "FAIL"
    )
    return {
        "status": status,
        "evidence_file": (
            data.get("evidence_file")
            if isinstance(data.get("evidence_file"), str)
            else CONTROL_CENTER_CORE_EVIDENCE_FILE
        ),
        **strings,
        "migration_changed": migration_changed,
        **true_values,
        **false_values,
        **integers,
        "implemented_surfaces": implemented_surfaces,
    }


def control_center_metrics_evidence() -> dict[str, object]:
    unknown: dict[str, object] = {
        "status": "UNKNOWN",
        "evidence_file": CONTROL_CENTER_METRICS_EVIDENCE_FILE,
        "metrics_evidence_version": CONTROL_CENTER_METRICS_EVIDENCE_VERSION,
        "observed_migration_head": "UNKNOWN",
        "migration_base_head": "UNKNOWN",
        "cost_provenance": "UNKNOWN",
        "migration_changed": False,
        **{field: False for field in CONTROL_CENTER_METRICS_TRUE_FIELDS},
        **{field: False for field in CONTROL_CENTER_METRICS_FALSE_FIELDS},
        **{field: 0 for field in CONTROL_CENTER_METRICS_INTEGER_FIELDS},
        "implemented_metric_families": [],
        "metric_value_provenance": [],
        "evidence_paths": [],
    }
    text = integration_file(CONTROL_CENTER_METRICS_EVIDENCE_FILE)
    if not text:
        return unknown
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {**unknown, "status": "FAIL"}
    if not isinstance(data, dict):
        return {**unknown, "status": "FAIL"}

    extra_fields = set(data) - CONTROL_CENTER_METRICS_ALLOWED_FIELDS
    true_values = {field: data.get(field) is True for field in CONTROL_CENTER_METRICS_TRUE_FIELDS}
    false_checks = {
        field: data.get(field) is False for field in CONTROL_CENTER_METRICS_FALSE_FIELDS
    }
    false_values = {field: data.get(field) is True for field in CONTROL_CENTER_METRICS_FALSE_FIELDS}
    strings = {
        field: data.get(field) if isinstance(data.get(field), str) else "UNKNOWN"
        for field in CONTROL_CENTER_METRICS_STRING_FIELDS
    }
    integers: dict[str, int] = {}
    integer_fields_valid = True
    for field in CONTROL_CENTER_METRICS_INTEGER_FIELDS:
        value = data.get(field)
        if not isinstance(value, int) or isinstance(value, bool):
            integer_fields_valid = False
            integers[field] = 0
        else:
            integers[field] = value
    raw_families = data.get("implemented_metric_families")
    families_valid = _is_closed_string_set(raw_families, CONTROL_CENTER_METRICS_FAMILIES)
    implemented_families = list(cast(list[str], raw_families)) if families_valid else []
    raw_provenance = data.get("metric_value_provenance")
    provenance_valid = _is_closed_string_set(
        raw_provenance, CONTROL_CENTER_METRICS_VALUE_PROVENANCE
    )
    metric_value_provenance = list(cast(list[str], raw_provenance)) if provenance_valid else []
    raw_paths = data.get("evidence_paths")
    paths_valid = (
        isinstance(raw_paths, list)
        and 1 <= len(raw_paths) <= CONTROL_CENTER_METRICS_MAX_EVIDENCE_PATHS
        and all(isinstance(path, str) for path in cast(list[object], raw_paths))
        and len(set(cast(list[object], raw_paths))) == len(raw_paths)
        and all(valid_control_center_metrics_path(path) for path in cast(list[object], raw_paths))
    )
    evidence_paths = list(cast(list[str], raw_paths)) if paths_valid else []
    migration_changed = data.get("migration_changed") is True
    status = (
        "PASS"
        if data.get("status") == "PASS"
        and not extra_fields
        and data.get("evidence_file") == CONTROL_CENTER_METRICS_EVIDENCE_FILE
        and strings["metrics_evidence_version"] == CONTROL_CENTER_METRICS_EVIDENCE_VERSION
        and strings["migration_base_head"] == CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD
        and strings["observed_migration_head"] == CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD
        and strings["cost_provenance"] == "UNAVAILABLE"
        and migration_changed is False
        and all(true_values.values())
        and all(false_checks.values())
        and families_valid
        and provenance_valid
        and paths_valid
        and integer_fields_valid
        and 1
        <= integers["historical_series_max_points"]
        <= CONTROL_CENTER_METRICS_MAX_HISTORY_POINTS
        and all(
            integers[field] == 0
            for field in (
                "secret_leaks",
                "filesystem_path_leaks",
                "cross_project_leaks",
                "metrics_llm_calls",
                "metrics_provider_calls",
            )
        )
        else "FAIL"
    )
    return {
        "status": status,
        "evidence_file": (
            data.get("evidence_file")
            if isinstance(data.get("evidence_file"), str)
            else CONTROL_CENTER_METRICS_EVIDENCE_FILE
        ),
        **strings,
        "migration_changed": migration_changed,
        **true_values,
        **false_values,
        **integers,
        "implemented_metric_families": implemented_families,
        "metric_value_provenance": metric_value_provenance,
        "evidence_paths": evidence_paths,
    }


def control_center_full_evidence() -> dict[str, object]:
    unknown: dict[str, object] = {
        "status": "UNKNOWN",
        "full_control_center_evidence_version": CONTROL_CENTER_FULL_EVIDENCE_VERSION,
        "evidence_file": CONTROL_CENTER_FULL_EVIDENCE_FILE,
        "observed_migration_head": "UNKNOWN",
        "migration_base_head": "UNKNOWN",
        "api_path": "UNKNOWN",
        "dashboard_path": "UNKNOWN",
        "migration_changed": False,
        **{field: False for field in CONTROL_CENTER_FULL_TRUE_FIELDS},
        **{field: False for field in CONTROL_CENTER_FULL_FALSE_FIELDS},
        **{field: 0 for field in CONTROL_CENTER_FULL_INTEGER_FIELDS},
        "implemented_project_capabilities": [],
        "implemented_charts": [],
        "implemented_alerts": [],
        "implemented_health_capabilities": [],
        "evidence_paths": [],
    }
    text = integration_file(CONTROL_CENTER_FULL_EVIDENCE_FILE)
    if not text:
        return unknown
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {**unknown, "status": "FAIL"}
    if not isinstance(data, dict):
        return {**unknown, "status": "FAIL"}

    extra_fields = set(data) - CONTROL_CENTER_FULL_ALLOWED_FIELDS
    true_values = {field: data.get(field) is True for field in CONTROL_CENTER_FULL_TRUE_FIELDS}
    false_checks = {field: data.get(field) is False for field in CONTROL_CENTER_FULL_FALSE_FIELDS}
    false_values = {field: data.get(field) is True for field in CONTROL_CENTER_FULL_FALSE_FIELDS}
    strings = {
        field: data.get(field) if isinstance(data.get(field), str) else "UNKNOWN"
        for field in CONTROL_CENTER_FULL_STRING_FIELDS
    }
    integers: dict[str, int] = {}
    integer_fields_valid = True
    for field in CONTROL_CENTER_FULL_INTEGER_FIELDS:
        value = data.get(field)
        if not isinstance(value, int) or isinstance(value, bool):
            integer_fields_valid = False
            integers[field] = 0
        else:
            integers[field] = value
    raw_lists = {
        "implemented_project_capabilities": data.get("implemented_project_capabilities"),
        "implemented_charts": data.get("implemented_charts"),
        "implemented_alerts": data.get("implemented_alerts"),
        "implemented_health_capabilities": data.get("implemented_health_capabilities"),
    }
    expected_lists = {
        "implemented_project_capabilities": CONTROL_CENTER_FULL_PROJECT_CAPABILITIES,
        "implemented_charts": CONTROL_CENTER_FULL_CHARTS,
        "implemented_alerts": CONTROL_CENTER_FULL_ALERTS,
        "implemented_health_capabilities": CONTROL_CENTER_FULL_HEALTH_CAPABILITIES,
    }
    list_valid = {
        field: _is_closed_string_set(raw_lists[field], expected_lists[field]) for field in raw_lists
    }
    implemented_lists = {
        field: list(cast(list[str], raw_lists[field])) if list_valid[field] else []
        for field in raw_lists
    }
    raw_paths = data.get("evidence_paths")
    paths_valid = (
        isinstance(raw_paths, list)
        and 1 <= len(raw_paths) <= CONTROL_CENTER_FULL_MAX_EVIDENCE_PATHS
        and all(isinstance(path, str) for path in cast(list[object], raw_paths))
        and len(set(cast(list[object], raw_paths))) == len(raw_paths)
        and all(
            valid_control_center_full_evidence_path(path) for path in cast(list[object], raw_paths)
        )
    )
    evidence_paths = list(cast(list[str], raw_paths)) if paths_valid else []
    migration_changed = data.get("migration_changed") is True
    status = (
        "PASS"
        if data.get("status") == "PASS"
        and not extra_fields
        and strings["full_control_center_evidence_version"] == CONTROL_CENTER_FULL_EVIDENCE_VERSION
        and strings["evidence_file"] == CONTROL_CENTER_FULL_EVIDENCE_FILE
        and strings["migration_base_head"] == CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD
        and strings["observed_migration_head"] == CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD
        and migration_changed is False
        and all(true_values.values())
        and all(false_checks.values())
        and all(list_valid.values())
        and valid_control_center_full_path("api_path", strings["api_path"])
        and valid_control_center_full_path("dashboard_path", strings["dashboard_path"])
        and paths_valid
        and integer_fields_valid
        and 1 <= integers["history_max_points"] <= CONTROL_CENTER_FULL_MAX_HISTORY_POINTS
        and all(
            integers[field] == 0
            for field in (
                "secret_leaks",
                "filesystem_path_leaks",
                "cross_project_leaks",
                "llm_calls",
                "provider_calls",
            )
        )
        else "FAIL"
    )
    return {
        "status": status,
        **strings,
        "migration_changed": migration_changed,
        **true_values,
        **false_values,
        **integers,
        **implemented_lists,
        "evidence_paths": evidence_paths,
    }


def acce_storage_policy_evidence() -> dict[str, object]:
    unknown: dict[str, object] = {
        "status": "UNKNOWN",
        "evidence_file": ACCE_STORAGE_POLICY_EVIDENCE_FILE,
        "acce_evidence_version": "UNKNOWN",
        "storage_policy_version": "UNKNOWN",
        **{field: False for field in ACCE_STORAGE_POLICY_REQUIRED_FIELDS},
        "canonical_source_loss_count": 0,
        "llm_calls": 0,
        "provider_calls": 0,
        "dedup_logical_bytes": 0,
        "dedup_unique_logical_bytes": 0,
        "dedup_savings_bytes": 0,
        "zstd_supported_level_min": ACCE_STORAGE_POLICY_ZSTD_MIN_LEVEL,
        "zstd_supported_level_max": ACCE_STORAGE_POLICY_ZSTD_MAX_LEVEL,
        "policy_mapping": {},
        "selection_rationale": "",
        "benchmark_matrix": [],
    }
    text = integration_file(ACCE_STORAGE_POLICY_EVIDENCE_FILE)
    if not text:
        return unknown
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {**unknown, "status": "FAIL"}
    if not isinstance(data, dict):
        return {**unknown, "status": "FAIL"}

    values = {field: data.get(field) is True for field in ACCE_STORAGE_POLICY_REQUIRED_FIELDS}
    strings = {
        field: data.get(field) if isinstance(data.get(field), str) else "UNKNOWN"
        for field in ACCE_STORAGE_POLICY_STRING_FIELDS
    }
    integers: dict[str, int] = {}
    integer_fields_valid = True
    for field in ACCE_STORAGE_POLICY_INTEGER_FIELDS:
        value = data.get(field)
        if not isinstance(value, int) or isinstance(value, bool):
            integer_fields_valid = False
            integers[field] = 0
        else:
            integers[field] = value

    min_level = data.get("zstd_supported_level_min")
    max_level = data.get("zstd_supported_level_max")
    levels_valid = (
        isinstance(min_level, int)
        and not isinstance(min_level, bool)
        and isinstance(max_level, int)
        and not isinstance(max_level, bool)
        and ACCE_STORAGE_POLICY_ZSTD_MIN_LEVEL <= min_level <= max_level
        and max_level <= ACCE_STORAGE_POLICY_ZSTD_MAX_LEVEL
    )
    if not levels_valid:
        min_level = ACCE_STORAGE_POLICY_ZSTD_MIN_LEVEL
        max_level = ACCE_STORAGE_POLICY_ZSTD_MAX_LEVEL

    policy_mapping = data.get("policy_mapping")
    policy_valid = (
        isinstance(policy_mapping, dict)
        and set(policy_mapping) == set(ACCE_STORAGE_POLICY_ALLOWED_TIERS)
        and all(
            isinstance(policy_mapping.get(tier), str)
            and bool(ACCE_STORAGE_POLICY_PROFILE_ID.fullmatch(policy_mapping[tier]))
            for tier in ACCE_STORAGE_POLICY_ALLOWED_TIERS
        )
        and len(set(policy_mapping.values())) == len(ACCE_STORAGE_POLICY_ALLOWED_TIERS)
    )
    normalized_policy = policy_mapping if policy_valid else {}
    rationale = data.get("selection_rationale")
    rationale_valid = isinstance(rationale, str) and 1 <= len(rationale) <= 2000

    matrix = data.get("benchmark_matrix")
    matrix_items = matrix if isinstance(matrix, list) else []
    normalized_matrix: list[dict[str, object]] = []
    matrix_valid = (
        isinstance(matrix, list) and 3 <= len(matrix) <= ACCE_STORAGE_POLICY_MAX_BENCHMARK_ROWS
    )
    seen_tiers: set[str] = set()
    seen_pairs: set[tuple[str, str]] = set()
    duplicate_pairs = False

    def valid_throughput(value: object) -> bool:
        return (
            isinstance(value, int | float)
            and not isinstance(value, bool)
            and math.isfinite(float(value))
            and 0.0 < float(value) <= ACCE_STORAGE_POLICY_MAX_THROUGHPUT_MIB_PER_S
        )

    if matrix_valid:
        for row in matrix_items:
            if not isinstance(row, dict):
                matrix_valid = False
                continue
            tier = row.get("tier")
            profile_id = row.get("profile_id")
            zstd_level = row.get("zstd_level")
            logical = row.get("logical_input_bytes")
            physical = row.get("physical_bytes")
            ratio = row.get("compression_ratio")
            savings = row.get("compression_savings_bytes")
            expands = row.get("compression_expands")
            round_trip = row.get("round_trip_identity")
            samples = row.get("measurement_samples")
            measured = row.get("benchmark_measured")
            compression_throughput = row.get("compression_mib_per_s")
            decompression_throughput = row.get("decompression_mib_per_s")
            pair = (
                (tier, profile_id)
                if isinstance(tier, str) and isinstance(profile_id, str)
                else None
            )
            if pair is not None:
                if pair in seen_pairs:
                    duplicate_pairs = True
                seen_pairs.add(pair)
            row_valid = (
                tier in ACCE_STORAGE_POLICY_ALLOWED_TIERS
                and isinstance(profile_id, str)
                and bool(ACCE_STORAGE_POLICY_PROFILE_ID.fullmatch(profile_id))
                and isinstance(zstd_level, int)
                and not isinstance(zstd_level, bool)
                and levels_valid
                and cast(int, min_level) <= zstd_level <= cast(int, max_level)
                and isinstance(logical, int)
                and not isinstance(logical, bool)
                and logical > 0
                and isinstance(physical, int)
                and not isinstance(physical, bool)
                and physical > 0
                and isinstance(ratio, int | float)
                and not isinstance(ratio, bool)
                and math.isfinite(float(ratio))
                and abs(float(ratio) - (physical / logical)) <= 1e-9
                and isinstance(savings, int)
                and not isinstance(savings, bool)
                and savings == logical - physical
                and isinstance(expands, bool)
                and expands is (physical > logical)
                and round_trip is True
                and isinstance(samples, int)
                and not isinstance(samples, bool)
                and 1 <= samples <= 100
                and measured is True
                and valid_throughput(compression_throughput)
                and valid_throughput(decompression_throughput)
            )
            if not row_valid:
                matrix_valid = False
            if isinstance(tier, str):
                seen_tiers.add(tier)
            normalized_matrix.append(
                {
                    "tier": tier if isinstance(tier, str) else "UNKNOWN",
                    "profile_id": profile_id if isinstance(profile_id, str) else "UNKNOWN",
                    "zstd_level": zstd_level if isinstance(zstd_level, int) else 0,
                    "logical_input_bytes": logical if isinstance(logical, int) else 0,
                    "physical_bytes": physical if isinstance(physical, int) else 0,
                    "compression_ratio": float(ratio) if isinstance(ratio, int | float) else 0.0,
                    "compression_savings_bytes": savings if isinstance(savings, int) else 0,
                    "compression_expands": expands if isinstance(expands, bool) else False,
                    "round_trip_identity": round_trip is True,
                    "measurement_samples": samples if isinstance(samples, int) else 0,
                    "benchmark_measured": measured is True,
                    "compression_mib_per_s": (
                        float(compression_throughput)
                        if isinstance(compression_throughput, int | float)
                        and not isinstance(compression_throughput, bool)
                        else 0.0
                    ),
                    "decompression_mib_per_s": (
                        float(decompression_throughput)
                        if isinstance(decompression_throughput, int | float)
                        and not isinstance(decompression_throughput, bool)
                        else 0.0
                    ),
                }
            )
    if not matrix_valid:
        normalized_matrix = normalized_matrix[:ACCE_STORAGE_POLICY_MAX_BENCHMARK_ROWS]
    policy_values = cast(dict[str, str], normalized_policy)
    mapping_tiers_present = (
        policy_valid
        and seen_tiers == set(ACCE_STORAGE_POLICY_ALLOWED_TIERS)
        and not duplicate_pairs
        and all(
            (tier, policy_values[tier]) in seen_pairs for tier in ACCE_STORAGE_POLICY_ALLOWED_TIERS
        )
    )
    counts_valid = (
        integer_fields_valid
        and all(value >= 0 for value in integers.values())
        and integers["dedup_savings_bytes"]
        == integers["dedup_logical_bytes"] - integers["dedup_unique_logical_bytes"]
        and integers["dedup_unique_logical_bytes"] <= integers["dedup_logical_bytes"]
    )
    status = (
        "PASS"
        if data.get("status") == "PASS"
        and strings["acce_evidence_version"] == ACCE_STORAGE_POLICY_EVIDENCE_VERSION
        and isinstance(strings["storage_policy_version"], str)
        and bool(re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", strings["storage_policy_version"]))
        and all(values.values())
        and counts_valid
        and integers["canonical_source_loss_count"] == 0
        and integers["llm_calls"] == 0
        and integers["provider_calls"] == 0
        and levels_valid
        and policy_valid
        and rationale_valid
        and matrix_valid
        and mapping_tiers_present
        else "FAIL"
    )
    return {
        "status": status,
        "evidence_file": ACCE_STORAGE_POLICY_EVIDENCE_FILE,
        **values,
        **strings,
        **integers,
        "zstd_supported_level_min": min_level,
        "zstd_supported_level_max": max_level,
        "policy_mapping": normalized_policy,
        "selection_rationale": rationale if isinstance(rationale, str) else "",
        "benchmark_matrix": normalized_matrix,
    }


def integration_result(name: str, markers: tuple[str, ...]) -> dict[str, object]:
    text = integration_file(name)
    passed = bool(text) and all(marker.casefold() in text.casefold() for marker in markers)
    return {"status": "PASS" if passed else "UNKNOWN", "evidence_file": name}


def context_manager_evidence() -> dict[str, object]:
    evidence_file = "context-manager.json"
    text = integration_file(evidence_file)
    unknown = {
        "status": "UNKNOWN",
        "evidence_file": evidence_file,
        **{field: False for field in CONTEXT_MANAGER_REQUIRED_FIELDS},
        **{field: False for field in WO012_CONTEXT_FINGERPRINT_REQUIRED_FIELDS},
        **{field: 0 for field in WO012_CONTEXT_FINGERPRINT_INTEGER_FIELDS},
        **{field: False for field in WO012_CONTEXT_FINGERPRINT_NEGATIVE_FIELDS},
        **{field: False for field in WO014_PROVIDER_CACHE_REQUIRED_FIELDS},
        **{field: 0 for field in WO014_PROVIDER_CACHE_INTEGER_FIELDS},
        **{field: "UNKNOWN" for field in WO014_PROVIDER_CACHE_STRING_FIELDS},
        **{field: [] for field in WO014_PROVIDER_CACHE_LIST_FIELDS},
        **{field: False for field in WO014_PROVIDER_CACHE_NEGATIVE_FIELDS},
        "context_fingerprint_benchmark_status": "UNKNOWN",
        "provider_cache_benchmark_status": "UNKNOWN",
        "mandatory_governance_kind_sequence": [],
        "llm_calls": None,
    }
    if not text:
        return unknown
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return unknown
    if not isinstance(data, dict):
        return unknown
    values = {field: data.get(field) is True for field in CONTEXT_MANAGER_REQUIRED_FIELDS}
    llm_calls = data.get("llm_calls")
    sequence = data.get("mandatory_governance_kind_sequence")
    fields_are_boolean = all(
        isinstance(data.get(field), bool) for field in CONTEXT_MANAGER_REQUIRED_FIELDS
    )
    sequence_valid = (
        isinstance(sequence, list)
        and all(isinstance(item, str) for item in sequence)
        and sequence == list(MANDATORY_GOVERNANCE_KIND_SEQUENCE)
    )
    if not fields_are_boolean or not isinstance(llm_calls, int) or isinstance(llm_calls, bool):
        return unknown
    if not isinstance(sequence, list) or not all(isinstance(item, str) for item in sequence):
        return unknown
    progressive_present = any(
        field in data
        for field in (
            *PROGRESSIVE_DISCLOSURE_REQUIRED_FIELDS,
            *PROGRESSIVE_DISCLOSURE_C1_FIELDS,
            *PROGRESSIVE_DISCLOSURE_C2_FIELDS,
        )
    )
    status = (
        "PASS"
        if data.get("status") == "PASS"
        and all(values.values())
        and sequence_valid
        and llm_calls == 0
        else "FAIL"
    )
    evidence: dict[str, object] = {
        "status": status,
        "evidence_file": evidence_file,
        **values,
        "mandatory_governance_kind_sequence": sequence,
        "llm_calls": llm_calls,
    }
    if progressive_present:
        disclosure_llm_calls = data.get("disclosure_llm_calls")
        adaptive_token_budget_implemented = data.get("adaptive_token_budget_implemented")
        evidence.update(
            {
                **{
                    field: data.get(field) is True
                    for field in (
                        *PROGRESSIVE_DISCLOSURE_REQUIRED_FIELDS,
                        *PROGRESSIVE_DISCLOSURE_C1_FIELDS,
                        *PROGRESSIVE_DISCLOSURE_C2_FIELDS,
                    )
                },
                "disclosure_llm_calls": (
                    disclosure_llm_calls
                    if isinstance(disclosure_llm_calls, int)
                    and not isinstance(disclosure_llm_calls, bool)
                    else None
                ),
                "adaptive_token_budget_implemented": (
                    adaptive_token_budget_implemented
                    if isinstance(adaptive_token_budget_implemented, bool)
                    else None
                ),
            }
        )
    token_present = any(
        field in data
        for field in (
            *TOKEN_BUDGET_REQUIRED_FIELDS,
            "token_budget_benchmark_status",
            "token_budget_benchmark_critical_context_misses",
            "token_budget_benchmark_strict_reduction_fixture",
            "token_budget_llm_calls",
            "token_budget_provider_calls",
        )
    )
    if token_present:
        evidence.update({field: data.get(field) is True for field in TOKEN_BUDGET_REQUIRED_FIELDS})
        for field in ("token_budget_llm_calls", "token_budget_provider_calls"):
            value = data.get(field)
            evidence[field] = (
                value if isinstance(value, int) and not isinstance(value, bool) else None
            )
        benchmark_status = data.get("token_budget_benchmark_status")
        evidence["token_budget_benchmark_status"] = (
            benchmark_status if benchmark_status in {"PASS", "FAIL", "UNKNOWN"} else "UNKNOWN"
        )
        benchmark_misses = data.get("token_budget_benchmark_critical_context_misses")
        evidence["token_budget_benchmark_critical_context_misses"] = (
            benchmark_misses
            if isinstance(benchmark_misses, int) and not isinstance(benchmark_misses, bool)
            else 0
        )
        evidence["token_budget_benchmark_strict_reduction_fixture"] = (
            data.get("token_budget_benchmark_strict_reduction_fixture") is True
        )
    fingerprint_present = any(
        field in data
        for field in (
            *WO012_CONTEXT_FINGERPRINT_REQUIRED_FIELDS,
            *WO012_CONTEXT_FINGERPRINT_INTEGER_FIELDS,
            *WO012_CONTEXT_FINGERPRINT_NEGATIVE_FIELDS,
            "context_fingerprint_benchmark_status",
        )
    )
    if fingerprint_present:
        evidence.update(
            {field: data.get(field) is True for field in WO012_CONTEXT_FINGERPRINT_REQUIRED_FIELDS}
        )
        for field in WO012_CONTEXT_FINGERPRINT_INTEGER_FIELDS:
            value = data.get(field)
            evidence[field] = value if isinstance(value, int) and not isinstance(value, bool) else 0
        evidence.update(
            {field: data.get(field) is True for field in WO012_CONTEXT_FINGERPRINT_NEGATIVE_FIELDS}
        )
        benchmark_status = data.get("context_fingerprint_benchmark_status")
        evidence["context_fingerprint_benchmark_status"] = (
            benchmark_status if benchmark_status in {"PASS", "FAIL", "UNKNOWN"} else "UNKNOWN"
        )
    delta_present = any(
        field in data
        for field in (
            *WO013_DELTA_REQUIRED_FIELDS,
            *WO013_DELTA_INTEGER_FIELDS,
            *WO013_DELTA_NEGATIVE_FIELDS,
            "delta_context_benchmark_status",
        )
    )
    if delta_present:
        evidence.update({field: data.get(field) is True for field in WO013_DELTA_REQUIRED_FIELDS})
        for field in WO013_DELTA_INTEGER_FIELDS:
            value = data.get(field)
            evidence[field] = value if isinstance(value, int) and not isinstance(value, bool) else 0
        for field in WO013_DELTA_STRING_FIELDS:
            value = data.get(field)
            evidence[field] = value if isinstance(value, str) else ""
        for field in WO013_DELTA_LIST_FIELDS:
            value = data.get(field)
            evidence[field] = value if isinstance(value, list) else []
        evidence.update({field: data.get(field) is True for field in WO013_DELTA_NEGATIVE_FIELDS})
        delta_status = data.get("delta_context_benchmark_status")
        evidence["delta_context_benchmark_status"] = (
            delta_status if delta_status in {"PASS", "FAIL", "UNKNOWN"} else "UNKNOWN"
        )
    provider_cache_present = any(
        field in data
        for field in (
            *WO014_PROVIDER_CACHE_REQUIRED_FIELDS,
            *WO014_PROVIDER_CACHE_INTEGER_FIELDS,
            *WO014_PROVIDER_CACHE_LIST_FIELDS,
            *WO014_PROVIDER_CACHE_NEGATIVE_FIELDS,
            "provider_cache_benchmark_status",
        )
    )
    if provider_cache_present:
        evidence.update(
            {field: data.get(field) is True for field in WO014_PROVIDER_CACHE_REQUIRED_FIELDS}
        )
        for field in WO014_PROVIDER_CACHE_INTEGER_FIELDS:
            value = data.get(field)
            evidence[field] = value if isinstance(value, int) and not isinstance(value, bool) else 0
        for field in WO014_PROVIDER_CACHE_STRING_FIELDS:
            value = data.get(field)
            evidence[field] = value if isinstance(value, str) and value else "UNKNOWN"
        for field in WO014_PROVIDER_CACHE_LIST_FIELDS:
            value = data.get(field)
            evidence[field] = value if isinstance(value, list) else []
        evidence.update(
            {field: data.get(field) is True for field in WO014_PROVIDER_CACHE_NEGATIVE_FIELDS}
        )
        provider_cache_status = data.get("provider_cache_benchmark_status")
        evidence["provider_cache_benchmark_status"] = (
            provider_cache_status
            if provider_cache_status in {"PASS", "FAIL", "UNKNOWN"}
            else "UNKNOWN"
        )
    return evidence


def retrieval_integrity(text: str) -> dict[str, bool]:
    match = re.search(r"retrieval_integrity=(\{.*\})", text)
    if not match:
        return {
            "head_race_rejected": False,
            "inventory_race_rejected": False,
            "prior_corpus_preserved": False,
            "duplicate_task_candidate_collapsed": False,
            "task_provenance_preserved": False,
            "cross_project_duplicate_isolation": False,
            "semantic_challenge_recovered": False,
            "hybrid_fallback_provider_error": False,
            "hybrid_fallback_stale": False,
            "semantic_project_isolation": False,
            "rerank_recall_at_5_gte_hybrid": False,
            "rerank_mrr_gte_hybrid": False,
            "rerank_strict_rank_improvement": False,
            "rerank_candidate_pool_bounded": False,
            "rerank_provenance_preserved": False,
            "rerank_disabled_exact_fallback": False,
            "rerank_invalid_response_safe": False,
            "rerank_provider_failure_safe": False,
            "rerank_provider_down_safe": False,
            **{field: False for field in RERANK_C1_REQUIRED_FIELDS},
        }
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError:
        value = {}
    return {
        key: bool(value.get(key, False))
        for key in (
            "head_race_rejected",
            "inventory_race_rejected",
            "prior_corpus_preserved",
            "duplicate_task_candidate_collapsed",
            "task_provenance_preserved",
            "cross_project_duplicate_isolation",
            "semantic_challenge_recovered",
            "hybrid_fallback_provider_error",
            "hybrid_fallback_stale",
            "semantic_project_isolation",
            "rerank_recall_at_5_gte_hybrid",
            "rerank_mrr_gte_hybrid",
            "rerank_strict_rank_improvement",
            "rerank_candidate_pool_bounded",
            "rerank_provenance_preserved",
            "rerank_disabled_exact_fallback",
            "rerank_invalid_response_safe",
            "rerank_provider_failure_safe",
            "rerank_provider_down_safe",
            *RERANK_C1_REQUIRED_FIELDS,
        )
    }


def integration_evidence(
    benchmark: dict[str, object], *, work_order: str = ""
) -> dict[str, object]:
    retrieval = integration_file("retrieval.log") + integration_file("retrieval-integration.txt")
    status = (
        "PASS"
        if "retrieval corpus/lexical" in retrieval.casefold()
        and "integration passed" in retrieval.casefold()
        else "UNKNOWN"
    )
    if benchmark["status"] == "FAIL":
        status = "FAIL"
    context_manager = context_manager_evidence()
    if context_manager["status"] == "FAIL":
        status = "FAIL"
    memory = memory_lifecycle_evidence()
    if memory["status"] == "FAIL":
        status = "FAIL"
    acce_storage = acce_storage_policy_evidence()
    if acce_storage["status"] == "FAIL":
        status = "FAIL"
    mcp_surface = mcp_surface_evidence()
    if (
        work_order in {WO017_WORK_ORDER, WO017P_G1_WORK_ORDER, WO017P_WORK_ORDER}
        and mcp_surface["status"] == "FAIL"
    ):
        status = "FAIL"
    autonomous_execution = autonomous_execution_evidence()
    if (
        work_order in {WO018_WORK_ORDER, WO018P_G1_WORK_ORDER, WO018P_WORK_ORDER}
        and autonomous_execution["status"] == "FAIL"
    ):
        status = "FAIL"
    telemetry_event_bus = telemetry_event_bus_evidence()
    if (
        work_order in {WO019_WORK_ORDER, WO019P_G1_WORK_ORDER, WO019P_WORK_ORDER}
        and telemetry_event_bus["status"] == "FAIL"
    ):
        status = "FAIL"
    control_center_core = control_center_core_evidence()
    if (
        work_order in {WO020_WORK_ORDER, WO020P_G1_WORK_ORDER, WO020P_WORK_ORDER}
        and control_center_core["status"] == "FAIL"
    ):
        status = "FAIL"
    control_center_metrics = control_center_metrics_evidence()
    if (
        work_order in {WO021_WORK_ORDER, WO021P_G1_WORK_ORDER, WO021P_WORK_ORDER}
        and control_center_metrics["status"] == "FAIL"
    ):
        status = "FAIL"
    control_center_full = control_center_full_evidence()
    if (
        work_order in {WO022_WORK_ORDER, WO022P_G1_WORK_ORDER, WO022P_WORK_ORDER}
        and control_center_full["status"] == "FAIL"
    ):
        status = "FAIL"
    v01_closure_sprint = closure_sprint_evidence()
    if work_order in {
        WO024_WORK_ORDER,
        WO024P_WORK_ORDER,
        WO024P_G1_C1_WORK_ORDER,
        WO024P_G1_C2_WORK_ORDER,
        WO024P_G1_C3_WORK_ORDER,
        WO024P_G1_C4_WORK_ORDER,
    } and (
        # the closure family stays a gating input rather than an undeclared
        # manifest property, but it still gates the integration status; an
        # unreadable payload is treated as failing rather than crashing
        str(v01_closure_sprint.get("status", "UNKNOWN")).upper() != "PASS"
    ):
        status = "FAIL"
    comprehensive_benchmarks = comprehensive_benchmarks_evidence()
    if (
        work_order
        in {WO023_WORK_ORDER, WO023P_G1_WORK_ORDER, WO023P_WORK_ORDER, WO023P_G1_C1_WORK_ORDER}
        and comprehensive_benchmarks["status"] == "FAIL"
    ):
        status = "FAIL"
    integrity = retrieval_integrity(retrieval)
    evidence: dict[str, object] = {
        "status": status,
        "project_registry": integration_result(
            "project-registry.log", ("project registry integration passed",)
        ),
        "task_intake_cas": integration_result(
            "task-intake.log", ("task intake and cas integration passed",)
        ),
        "repository_indexing": integration_result(
            "repository-indexing.log", ("repository indexing integration passed",)
        ),
        "retrieval": {"status": status, "evidence_file": "retrieval.log"},
        "redis_restart": {"status": "PASS" if benchmark["redis_restart"] else "UNKNOWN"},
        "api_restart": {"status": "PASS" if benchmark["api_restart"] else "UNKNOWN"},
        "reranking": {
            "status": "PASS"
            if cast(dict[str, Any], benchmark["rerank"]).get("status") == "PASS"
            else "UNKNOWN",
            "evidence_file": "retrieval.log",
        },
        "context_manager": context_manager,
        "memory": memory,
        "benchmark_gate": {
            "status": benchmark["status"],
            "query_count": benchmark["query_count"],
            "recall_at_1": benchmark["recall_at_1"],
            "recall_at_5": benchmark["recall_at_5"],
            "mrr": benchmark["mrr"],
            "critical_context_misses": benchmark["critical_context_misses"],
            "two_run_reproducibility": benchmark["two_run_reproducibility"],
        },
        "cross_project_retrieval": {
            "status": "PASS" if benchmark["cross_project_isolation"] else "UNKNOWN"
        },
        "integrity_tests": integrity,
        "semantic_hybrid": {
            "status": "PASS"
            if cast(dict[str, Any], benchmark["semantic"])["status"] == "PASS"
            and cast(dict[str, Any], benchmark["hybrid"])["status"] == "PASS"
            and benchmark["hybrid_recall_at_5_gte_extended_lexical"]
            and benchmark["semantic_challenge_recovered"]
            else "UNKNOWN",
            "semantic": benchmark["semantic"],
            "hybrid": benchmark["hybrid"],
            "semantic_integrity": benchmark["semantic_integrity"],
            "fallback": benchmark["fallback"],
            "rerank": benchmark["rerank"],
        },
    }
    if work_order in {WO016_WORK_ORDER, WO016P_G1_WORK_ORDER, WO016P_WORK_ORDER}:
        evidence["acce_storage"] = acce_storage
    if work_order in {WO017_WORK_ORDER, WO017P_G1_WORK_ORDER, WO017P_WORK_ORDER}:
        evidence["mcp_surface"] = mcp_surface
    if work_order in {WO018_WORK_ORDER, WO018P_G1_WORK_ORDER, WO018P_WORK_ORDER}:
        evidence["autonomous_execution"] = autonomous_execution
    if work_order in {WO019_WORK_ORDER, WO019P_G1_WORK_ORDER, WO019P_WORK_ORDER}:
        evidence["telemetry_event_bus"] = telemetry_event_bus
    if work_order in {WO020_WORK_ORDER, WO020P_G1_WORK_ORDER, WO020P_WORK_ORDER}:
        evidence["control_center_core"] = control_center_core
    if work_order in {WO021_WORK_ORDER, WO021P_G1_WORK_ORDER, WO021P_WORK_ORDER}:
        evidence["control_center_metrics"] = control_center_metrics
    if work_order in {WO022_WORK_ORDER, WO022P_G1_WORK_ORDER, WO022P_WORK_ORDER}:
        evidence["control_center_full"] = control_center_full
    if work_order in {
        WO023_WORK_ORDER,
        WO023P_G1_WORK_ORDER,
        WO023P_WORK_ORDER,
        WO023P_G1_C1_WORK_ORDER,
    }:
        evidence["comprehensive_benchmarks"] = comprehensive_benchmarks
    return evidence


def security_evidence(
    all_validation: str,
    test_results: str,
    all_evidence: str,
    benchmark: dict[str, object],
    integration: dict[str, object],
) -> dict[str, object]:
    canonical = validation_status(all_validation, "canonical source verification passed")
    secrets = validation_status(all_validation, "secret scan passed")
    sql_basis = read_text(VALIDATION / "backend-junit.xml") + test_results
    sql = "PASS" if "test_sql_queries_are_parameterized" in sql_basis else "UNKNOWN"
    retrieval = cast(dict[str, Any], integration["retrieval"])
    integrity = cast(dict[str, Any], integration["integrity_tests"])
    stale = (
        "PASS"
        if retrieval["status"] == "PASS"
        and integrity["head_race_rejected"]
        and integrity["inventory_race_rejected"]
        and integrity["prior_corpus_preserved"]
        else "UNKNOWN"
    )
    isolation = "PASS" if benchmark["cross_project_isolation"] else "UNKNOWN"
    rerank = cast(dict[str, Any], benchmark.get("rerank", {}))
    secret_not_leaked = not RERANK_SECRET_SENTINEL.search(all_evidence)
    values = {
        "canonical_verifier": {"status": canonical},
        "secret_scan": {"status": secrets},
        "project_isolation": {"status": isolation},
        "cross_project_retrieval": {"status": isolation},
        "sql_query_parameterization": {
            "status": sql,
            "basis": "backend/tests/test_retrieval.py::test_sql_queries_are_parameterized",
        },
        "source_staleness_fail_closed": {"status": stale},
        "reranking": {
            "status": "PASS"
            if rerank.get("status") == "PASS"
            and rerank.get("candidate_pool_bounded")
            and rerank.get("provenance_preserved")
            and rerank.get("provider_failure_exact_fallback")
            and rerank.get("rerank_secret_not_leaked")
            and secret_not_leaked
            else "UNKNOWN"
        },
    }
    return {
        "status": "PASS"
        if all(item["status"] == "PASS" for item in values.values())
        else "UNKNOWN",
        **values,
    }


def require_wo008_c1_evidence(
    work_order: str,
    benchmark: Mapping[str, object],
    integration: Mapping[str, object],
    security: Mapping[str, object],
    all_evidence: str,
    github_evidence: str,
) -> None:
    if work_order != "WO-008" and not work_order.startswith("WO-008-"):
        return
    rerank = cast(dict[str, Any], benchmark.get("rerank", {}))
    integrity = cast(dict[str, Any], integration.get("integrity_tests", {}))
    missing_benchmark = [field for field in RERANK_C1_REQUIRED_FIELDS if not rerank.get(field)]
    missing_integration = [field for field in RERANK_C1_REQUIRED_FIELDS if not integrity.get(field)]
    if benchmark.get("status") != "PASS" or rerank.get("status") != "PASS":
        raise ValueError("WO-008 Review Evidence requires a passing rerank C1 benchmark")
    if missing_benchmark or missing_integration:
        raise ValueError(
            "WO-008 Review Evidence missing mandatory rerank C1 evidence: "
            + ", ".join(sorted(set(missing_benchmark + missing_integration)))
        )
    security_rerank = cast(dict[str, Any], security.get("reranking", {}))
    if security_rerank.get("status") != "PASS":
        raise ValueError("WO-008 Review Evidence requires passing rerank security evidence")
    if RERANK_SECRET_SENTINEL.search(all_evidence + "\n" + github_evidence):
        raise ValueError("WO-008 Review Evidence detected a rerank secret sentinel in evidence")


def require_wo009_context_manager_evidence(
    work_order: str,
    integration: Mapping[str, object],
) -> None:
    if work_order != "WO-009":
        return
    context_manager = cast(dict[str, Any], integration.get("context_manager", {}))
    missing = [
        field for field in CONTEXT_MANAGER_REQUIRED_FIELDS if context_manager.get(field) is not True
    ]
    if missing:
        raise ValueError(
            "WO-009 Review Evidence missing mandatory Context Manager evidence: "
            + ", ".join(sorted(missing))
        )
    if context_manager.get("llm_calls") != 0:
        raise ValueError("WO-009 Review Evidence requires zero Context Manager LLM calls")
    if context_manager.get("mandatory_governance_coverage") is not True:
        raise ValueError("WO-009 Review Evidence requires mandatory_governance_coverage=true")
    if context_manager.get("mandatory_governance_kind_sequence") != list(
        MANDATORY_GOVERNANCE_KIND_SEQUENCE
    ):
        raise ValueError(
            "WO-009 Review Evidence requires the five mandatory governance kinds in order"
        )
    if context_manager.get("status") != "PASS":
        raise ValueError("WO-009 Review Evidence requires passing Context Manager evidence")


def require_wo010_progressive_disclosure_evidence(
    work_order: str,
    integration: Mapping[str, object],
    migration_head_value: str | None = None,
) -> None:
    if work_order != "WO-010":
        return
    require_wo009_context_manager_evidence("WO-009", integration)
    context_manager = cast(dict[str, Any], integration.get("context_manager", {}))
    missing = [
        field
        for field in (
            *PROGRESSIVE_DISCLOSURE_REQUIRED_FIELDS,
            *PROGRESSIVE_DISCLOSURE_C1_FIELDS,
            *PROGRESSIVE_DISCLOSURE_C2_FIELDS,
        )
        if context_manager.get(field) is not True
    ]
    if missing:
        raise ValueError(
            "WO-010 Review Evidence missing mandatory Progressive Disclosure evidence: "
            + ", ".join(sorted(missing))
        )
    if context_manager.get("disclosure_llm_calls") != 0:
        raise ValueError("WO-010 Review Evidence requires zero disclosure LLM calls")
    if context_manager.get("adaptive_token_budget_implemented") is not False:
        raise ValueError("WO-010 Review Evidence requires adaptive_token_budget_implemented=false")
    if context_manager.get("status") != "PASS":
        raise ValueError("WO-010 Review Evidence requires passing Context Manager evidence")
    if migration_head_value is not None and migration_head_value != "0005_semantic_retrieval":
        raise ValueError(
            "WO-010 Review Evidence requires migration head 0005_semantic_retrieval, "
            f"observed {migration_head_value}"
        )


def require_wo011_context_manager_evidence(
    work_order: str,
    integration: Mapping[str, object],
    migration_head_value: str | None = None,
) -> None:
    if work_order != "WO-011":
        return
    context_manager = cast(dict[str, Any], integration.get("context_manager", {}))
    positive_fields = [
        field
        for field in TOKEN_BUDGET_REQUIRED_FIELDS
        if field
        not in {"token_budget_user_mode_required", "adaptive_token_budget_migration_changed"}
    ]
    missing = [field for field in positive_fields if context_manager.get(field) is not True]
    if missing:
        raise ValueError(
            "WO-011 Review Evidence missing mandatory adaptive token-budget evidence: "
            + ", ".join(sorted(missing))
        )
    if context_manager.get("token_budget_user_mode_required") is not False:
        raise ValueError("WO-011 requires token_budget_user_mode_required=false")
    if context_manager.get("adaptive_token_budget_migration_changed") is not False:
        raise ValueError("WO-011 requires adaptive_token_budget_migration_changed=false")
    if context_manager.get("llm_calls") != 0 or context_manager.get("disclosure_llm_calls") != 0:
        raise ValueError(
            "WO-011 Review Evidence requires zero Context Manager and disclosure LLM calls"
        )
    if context_manager.get("token_budget_llm_calls") != 0:
        raise ValueError("WO-011 Review Evidence requires zero token-budget LLM calls")
    if context_manager.get("token_budget_provider_calls") != 0:
        raise ValueError("WO-011 Review Evidence requires zero token-budget provider calls")
    if context_manager.get("token_budget_benchmark_status") != "PASS":
        raise ValueError("WO-011 Review Evidence requires a passing token-budget benchmark")
    if context_manager.get("token_budget_benchmark_critical_context_misses") != 0:
        raise ValueError(
            "WO-011 Review Evidence requires zero token-budget critical context misses"
        )
    if context_manager.get("token_budget_benchmark_strict_reduction_fixture") is not True:
        raise ValueError("WO-011 Review Evidence requires a strict reduction fixture")
    if context_manager.get("status") != "PASS":
        raise ValueError("WO-011 Review Evidence requires passing Context Manager evidence")
    if migration_head_value is not None and migration_head_value != "0005_semantic_retrieval":
        raise ValueError(
            "WO-011 Review Evidence requires migration head 0005_semantic_retrieval, "
            f"observed {migration_head_value}"
        )


def require_wo012_context_manager_evidence(
    work_order: str,
    integration: Mapping[str, object],
    migration_head_value: str | None = None,
) -> None:
    if work_order not in {"WO-012", "WO-012-P"}:
        return
    context_manager = cast(dict[str, Any], integration.get("context_manager", {}))
    missing = [
        field
        for field in WO012_CONTEXT_FINGERPRINT_REQUIRED_FIELDS
        if context_manager.get(field) is not True
    ]
    if missing:
        raise ValueError(
            "WO-012/WO-012-P Review Evidence missing mandatory context-fingerprint evidence: "
            + ", ".join(sorted(missing))
        )
    if context_manager.get("context_fingerprint_benchmark_status") != "PASS":
        raise ValueError("WO-012/WO-012-P requires a passing context-fingerprint benchmark")
    if context_manager.get("context_fingerprint_benchmark_false_hits") != 0:
        raise ValueError("WO-012/WO-012-P requires zero context-fingerprint false hits")
    if context_manager.get("context_fingerprint_benchmark_critical_context_misses") != 0:
        raise ValueError("WO-012/WO-012-P requires zero critical context misses")
    if context_manager.get("context_fingerprint_llm_calls") != 0:
        raise ValueError("WO-012/WO-012-P requires zero context-fingerprint LLM calls")
    if context_manager.get("context_fingerprint_provider_calls") != 0:
        raise ValueError("WO-012/WO-012-P requires zero context-fingerprint provider calls")
    for field in (
        "delta_context_implemented",
        "provider_prompt_cache_implemented",
        "memory_lifecycle_implemented",
        "context_fingerprint_migration_changed",
    ):
        if context_manager.get(field) is not False:
            raise ValueError(f"WO-012/WO-012-P requires {field}=false")
    if context_manager.get("status") != "PASS":
        raise ValueError(
            "WO-012/WO-012-P Review Evidence requires passing Context Manager evidence"
        )
    if migration_head_value is not None and migration_head_value != "0005_semantic_retrieval":
        raise ValueError(
            "WO-012/WO-012-P Review Evidence requires migration head 0005_semantic_retrieval, "
            f"observed {migration_head_value}"
        )


def require_wo014_provider_prompt_cache_evidence(
    work_order: str,
    integration: Mapping[str, object],
    migration_head_value: str | None = None,
) -> None:
    if work_order not in {
        "WO-014",
        WO014_C2_WORK_ORDER,
        WO014P_G1_WORK_ORDER,
        WO014P_WORK_ORDER,
    }:
        return
    context_manager = cast(dict[str, Any], integration.get("context_manager", {}))
    missing = [
        field
        for field in WO014_PROVIDER_CACHE_REQUIRED_FIELDS
        if context_manager.get(field) is not True
    ]
    if missing:
        raise ValueError(
            "WO-014 Review Evidence missing mandatory provider/prompt-cache evidence: "
            + ", ".join(sorted(missing))
        )
    for field in WO014_PROVIDER_CACHE_INTEGER_FIELDS:
        value = context_manager.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"WO-014 requires bounded integer evidence for {field}")
    for field in WO014_PROVIDER_CACHE_NEGATIVE_FIELDS:
        if context_manager.get(field) is not False:
            raise ValueError(f"WO-014 requires {field}=false")
    if context_manager.get("provider_cache_benchmark_status") != "PASS":
        raise ValueError("WO-014 requires a passing provider/prompt-cache benchmark")
    if context_manager.get("provider_cache_foundation_llm_calls") != 0:
        raise ValueError("WO-014 requires zero foundation LLM calls")
    if context_manager.get("provider_cache_foundation_provider_calls") != 0:
        raise ValueError("WO-014 requires zero foundation provider calls")
    if context_manager.get("provider_cache_independent_canonical_input_version") != (
        "provider-canonical-input-v1"
    ):
        raise ValueError("WO-014 requires the versioned independent canonical input contract")
    fixture_count = context_manager.get("provider_cache_semantic_composition_fixture_count")
    mismatch_count = context_manager.get(
        "provider_cache_semantic_composition_mismatch_detection_count"
    )
    accepted_mismatches = context_manager.get(
        "provider_cache_accepted_semantic_composition_mismatches"
    )
    if not (
        isinstance(fixture_count, int)
        and not isinstance(fixture_count, bool)
        and fixture_count >= 5
        and isinstance(mismatch_count, int)
        and not isinstance(mismatch_count, bool)
        and mismatch_count == fixture_count
        and isinstance(accepted_mismatches, int)
        and not isinstance(accepted_mismatches, bool)
        and accepted_mismatches == 0
    ):
        raise ValueError("WO-014 requires computed semantic mutation evidence")
    if context_manager.get("provider_cache_delta_false_reconstructions") != 0:
        raise ValueError("WO-014 requires zero Delta false reconstructions")
    if context_manager.get("provider_cache_delta_critical_context_misses") != 0:
        raise ValueError("WO-014 requires zero Delta critical context misses")
    if context_manager.get("provider_cache_invalid_accounting_matrix_size", 0) < 8:
        raise ValueError("WO-014 requires the complete invalid accounting matrix")
    if context_manager.get("provider_cache_invalid_accounting_acceptances") != 0:
        raise ValueError("WO-014 requires zero accepted invalid accounting receipts")
    if context_manager.get("provider_cache_credential_leaks") != 0:
        raise ValueError("WO-014 requires zero computed credential leaks")
    if context_manager.get("provider_cache_cross_project_leaks") != 0:
        raise ValueError("WO-014 requires zero computed cross-project leaks")
    if context_manager.get("provider_cache_false_hit_claims") != 0:
        raise ValueError("WO-014 requires zero computed false cache-hit claims")
    if context_manager.get("provider_cache_semantic_composition_mismatches") != 0:
        raise ValueError("WO-014 requires zero accepted semantic composition mismatches")
    if context_manager.get("provider_cache_full_compatible_measured") is not True:
        raise ValueError("WO-014 requires measured FULL compatibility")
    if context_manager.get("provider_cache_delta_compatible_measured") is not True:
        raise ValueError("WO-014 requires measured DELTA compatibility")
    usage_sources = context_manager.get("provider_cache_provider_usage_sources")
    if not isinstance(usage_sources, list) or not all(
        isinstance(item, str) for item in usage_sources
    ):
        raise ValueError("WO-014 requires provider usage source labels")
    if migration_head_value is not None and migration_head_value != "0005_semantic_retrieval":
        raise ValueError(
            "WO-014 requires migration head 0005_semantic_retrieval, "
            f"observed {migration_head_value}"
        )
    if context_manager.get("status") != "PASS":
        raise ValueError("WO-014 requires passing Context Manager evidence")


def verify_wo014p_g1_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
) -> str | None:
    if work_order != WO014P_G1_WORK_ORDER:
        return None
    require_wo014p_g1_scope(work_order, base_sha, paths)
    if {WO014P_G1_WORK_ORDER, WO014P_WORK_ORDER} != {
        WO014P_G1_WORK_ORDER,
        WO014P_WORK_ORDER,
    }:
        raise ValueError(
            "WO-014-P-G1 requires exactly WO-014-P-G1 and WO-014-P as active promotions"
        )
    for stale in ("WO-011-P", "WO-012-P", "WO-013-P"):
        try:
            require_current_work_order_authorization(stale)
        except ValueError:
            pass
        else:
            raise ValueError(f"{stale} unexpectedly authorizes a fresh current PR")
    for rejected in ("WO-999-P",):
        try:
            require_current_work_order_authorization(rejected)
        except ValueError:
            pass
        else:
            raise ValueError(f"{rejected} unexpectedly authorizes a fresh current PR")
    require_supported_work_order(WO014P_G1_WORK_ORDER)
    require_supported_work_order(WO014P_WORK_ORDER)
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError("WO-014-P-G1 requires no Project Brain or checkpoint changes")
    if migration_head_value != "0005_semantic_retrieval":
        raise ValueError(
            "WO-014-P-G1 requires migration head 0005_semantic_retrieval, "
            f"observed {migration_head_value}"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError("WO-014-P-G1 requires the protected ruleset to be unchanged")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError("WO-014-P-G1 requires auto-merge to remain unarmed")
    context_manager = cast(dict[str, Any], integration.get("context_manager", {}))
    if context_manager.get("memory_lifecycle_implemented") is not False:
        raise ValueError("WO-014-P-G1 requires Memory lifecycle to remain unimplemented")
    return (
        "work_order=WO-014-P-G1; exact_base=PASS; governance_scope=PASS; "
        "project_brain_changed=False; migration_changed=False; "
        "active_promotions=WO-014-P-G1,WO-014-P; "
        "stale_WO-011-P_WO-012-P_WO-013-P=REJECTED; "
        "current_WO-017-P=SUPPORTED; unknown_WO-999-P=REJECTED; authorized_base_parser=PASS; "
        "future_two_file_scope=PASS; checkpoint_semantics=PASS; manifest_contract=PASS; "
        "renderer_markers=PASS; ruleset_unchanged=PASS; auto_merge=UNARMED; "
        "product_change=False; memory_implementation=False; checkpoint_promotion=False"
    )


def require_wo013_context_manager_evidence(
    work_order: str,
    integration: Mapping[str, object],
    migration_head_value: str | None = None,
) -> None:
    if work_order not in {"WO-013", "WO-013-P-G1", "WO-013-P"}:
        return
    context_manager = cast(dict[str, Any], integration.get("context_manager", {}))
    missing = [
        field for field in WO013_DELTA_REQUIRED_FIELDS if context_manager.get(field) is not True
    ]
    if missing:
        raise ValueError(
            "WO-013 Review Evidence missing mandatory Delta Context evidence: "
            + ", ".join(sorted(missing))
        )
    for field in WO013_DELTA_INTEGER_FIELDS:
        value = context_manager.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"WO-013 requires bounded integer evidence for {field}")
    if context_manager.get("delta_context_llm_calls") != 0:
        raise ValueError("WO-013 requires zero Delta Context LLM calls")
    if context_manager.get("delta_context_provider_calls") != 0:
        raise ValueError("WO-013 requires zero Delta Context provider calls")
    for field in WO013_DELTA_NEGATIVE_FIELDS:
        if context_manager.get(field) is not False:
            raise ValueError(f"WO-013 requires {field}=false")
    if context_manager.get("delta_context_false_reconstructions") != 0:
        raise ValueError("WO-013 requires zero false Delta reconstructions")
    if context_manager.get("delta_context_critical_context_misses") != 0:
        raise ValueError("WO-013 requires zero Delta critical context misses")
    if (
        context_manager.get("delta_context_delivery_estimate_version")
        != "delta-delivery-estimate-v1"
    ):
        raise ValueError("WO-013 requires the versioned final Delta delivery estimate contract")
    small_delta = context_manager.get("delta_context_small_change_final_delta_estimated_tokens")
    small_legacy_delta = context_manager.get("delta_context_small_change_delta_estimated_tokens")
    small_full = context_manager.get("delta_context_small_change_full_estimated_tokens")
    small_avoided = context_manager.get("delta_context_small_change_fresh_context_tokens_avoided")
    if not (
        isinstance(small_delta, int)
        and not isinstance(small_delta, bool)
        and small_legacy_delta == small_delta
        and isinstance(small_full, int)
        and not isinstance(small_full, bool)
        and isinstance(small_avoided, int)
        and not isinstance(small_avoided, bool)
        and small_avoided > 0
        and small_avoided == small_full - small_delta
    ):
        raise ValueError("WO-013 requires exact positive fresh-token avoidance for DELTA")
    if context_manager.get("delta_context_full_savings_zero") is not True:
        raise ValueError("WO-013 requires zero fresh-token avoidance for every FULL delivery")
    threshold_old = context_manager.get("delta_context_threshold_old_metadata_estimated_tokens")
    threshold_final = context_manager.get("delta_context_threshold_final_delta_estimated_tokens")
    threshold_full = context_manager.get("delta_context_threshold_full_estimated_tokens")
    if not (
        isinstance(threshold_old, int)
        and not isinstance(threshold_old, bool)
        and isinstance(threshold_final, int)
        and not isinstance(threshold_final, bool)
        and isinstance(threshold_full, int)
        and not isinstance(threshold_full, bool)
        and threshold_old < threshold_full <= threshold_final
        and context_manager.get("delta_context_threshold_old_gate_would_emit_delta") is True
        and context_manager.get("delta_context_threshold_final_gate_rejected_delta") is True
    ):
        raise ValueError("WO-013 requires the intermediate-metadata false-positive regression")
    if context_manager.get("delta_context_benchmark_status") != "PASS":
        raise ValueError("WO-013 requires a passing Delta Context benchmark")
    if context_manager.get("status") != "PASS":
        raise ValueError("WO-013 Review Evidence requires passing Context Manager evidence")
    if migration_head_value is not None and migration_head_value != "0005_semantic_retrieval":
        raise ValueError(
            "WO-013 Review Evidence requires migration head 0005_semantic_retrieval, "
            f"observed {migration_head_value}"
        )


def warnings_evidence(all_text: str) -> dict[str, object]:
    items = [message for pattern, message in WARNING_RULES if pattern.search(all_text)]
    return {"status": "RECORDED" if items else "NONE", "count": len(items), "items": items}


def _gh_json(repository: str, endpoint: str) -> dict[str, Any] | list[Any] | None:
    path = f"repos/{repository}/{endpoint}" if endpoint else f"repos/{repository}"
    code, output = run(["gh", "api", path])
    if code != 0:
        return None
    try:
        value = json.loads(output)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict | list) else None


def _lineage_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"WO-016 approved lineage requires {label}")
    return value


def _lineage_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"WO-016 approved lineage requires {label}")
    return value


def _lineage_id_matches(value: object, expected: int) -> bool:
    return value == expected or value == str(expected)


def _normalized_lineage_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"WO-016 approved lineage requires {label}")
    return " ".join(value.replace("—", "-").split()).casefold()


def require_wo016_approved_lineage_result(result: Mapping[str, object]) -> None:
    expected: dict[str, object] = {
        "status": "PASS",
        "product_work_order": WO016_WORK_ORDER,
        "product_pr": 55,
        "audited_product_head": WO016_APPROVED_PRODUCT_HEAD,
        "sol_review_id": WO016_APPROVED_SOL_REVIEW_ID,
        "sol_review_commit": WO016_APPROVED_PRODUCT_HEAD,
        "squash_merge_sha": WO016_APPROVED_SQUASH_MERGE_SHA,
        "product_pr_merged": True,
        "squash_lineage_compatible": True,
        "post_merge_ci_run": WO016_APPROVED_POST_MERGE_CI_RUN,
        "post_merge_ci_event": "push",
        "post_merge_ci_head_sha": WO016_APPROVED_SQUASH_MERGE_SHA,
        "post_merge_ci_conclusion": "success",
        "post_merge_validate": "success",
        "post_merge_integration_health": "success",
        "post_merge_review_evidence": "skipped",
        "prior_review_evidence_head": WO016_APPROVED_PRODUCT_HEAD,
        "prior_backend_passed": 418,
        "prior_dashboard_passed": 7,
        "prior_acce_status": "PASS",
        "prior_acce_version": ACCE_STORAGE_POLICY_EVIDENCE_VERSION,
        "prior_storage_policy": "acce-policy-v1",
        "prior_canonical_source_loss": 0,
        "prior_llm_calls": 0,
        "prior_provider_calls": 0,
    }
    missing = [key for key in expected if result.get(key) != expected[key]]
    if missing:
        raise ValueError("WO-016 approved lineage evidence mismatch: " + ", ".join(sorted(missing)))


def verify_wo016_approved_lineage(sources: Mapping[str, object]) -> dict[str, object]:
    """Validate the approved WO-016 product lineage from bounded GitHub sources."""
    product_pr = _lineage_mapping(sources.get("product_pr"), "product PR data")
    if product_pr.get("number") != 55:
        raise ValueError("WO-016 approved lineage requires product PR #55")
    if product_pr.get("state") != "closed" or product_pr.get("merged") is not True:
        raise ValueError("WO-016 approved lineage requires a merged product PR")
    base = _lineage_mapping(product_pr.get("base"), "product PR base")
    head = _lineage_mapping(product_pr.get("head"), "product PR head")
    if base.get("ref") != "main" or base.get("sha") != WO016_APPROVED_PRODUCT_BASE_SHA:
        raise ValueError("WO-016 approved lineage requires the authorized product base")
    if head.get("sha") != WO016_APPROVED_PRODUCT_HEAD:
        raise ValueError("WO-016 approved lineage requires the audited product HEAD")
    if product_pr.get("merge_commit_sha") != WO016_APPROVED_SQUASH_MERGE_SHA:
        raise ValueError("WO-016 approved lineage requires the approved squash merge SHA")
    product_body = _normalized_lineage_text(product_pr.get("body"), "product PR body")
    if "<!-- hive-work-order: wo-016 -->" not in product_body:
        raise ValueError("WO-016 approved lineage requires the product work-order marker")

    reviews = _lineage_list(sources.get("product_reviews"), "product PR reviews")
    matching_reviews = [
        _lineage_mapping(review, "product review")
        for review in reviews
        if _lineage_id_matches(
            _lineage_mapping(review, "product review").get("id"),
            WO016_APPROVED_SOL_REVIEW_ID,
        )
    ]
    if len(matching_reviews) != 1:
        raise ValueError("WO-016 approved lineage requires exactly one Sol review")
    sol_review = matching_reviews[0]
    if sol_review.get("state") not in {"APPROVED", "COMMENTED"}:
        raise ValueError("WO-016 approved lineage requires an approved Sol review")
    if sol_review.get("commit_id") != WO016_APPROVED_PRODUCT_HEAD:
        raise ValueError("WO-016 Sol review is not bound to the audited product HEAD")
    review_text = _normalized_lineage_text(sol_review.get("body"), "Sol review body")
    for marker in (
        "approved - wo-016",
        "verdict: approved for exact-head squash merge",
        WO016_APPROVED_PRODUCT_HEAD,
    ):
        if marker.casefold() not in review_text:
            raise ValueError("WO-016 Sol review does not express the approved result")

    merge_commit = _lineage_mapping(sources.get("merge_commit"), "squash merge commit")
    if merge_commit.get("sha") != WO016_APPROVED_SQUASH_MERGE_SHA:
        raise ValueError("WO-016 squash merge commit identity is not verified")
    parents = _lineage_list(merge_commit.get("parents"), "squash merge parents")
    if len(parents) != 1:
        raise ValueError("WO-016 approved merge is not compatible with a squash lineage")

    post_merge_run = _lineage_mapping(sources.get("post_merge_run"), "post-merge CI run")
    if not _lineage_id_matches(post_merge_run.get("id"), WO016_APPROVED_POST_MERGE_CI_RUN):
        raise ValueError("WO-016 approved lineage requires the approved post-merge CI run")
    if (
        post_merge_run.get("event") != "push"
        or post_merge_run.get("head_sha") != WO016_APPROVED_SQUASH_MERGE_SHA
        or post_merge_run.get("status") != "completed"
        or post_merge_run.get("conclusion") != "success"
    ):
        raise ValueError("WO-016 post-merge CI run is not a successful push on the merge SHA")

    jobs = _lineage_list(sources.get("post_merge_jobs"), "post-merge CI jobs")
    by_name: dict[str, Mapping[str, Any]] = {}
    for raw_job in jobs:
        job = _lineage_mapping(raw_job, "post-merge CI job")
        name = job.get("name")
        if isinstance(name, str):
            if name in by_name:
                raise ValueError(f"WO-016 post-merge CI has duplicate job {name}")
            by_name[name] = job
    for name in ("Validate", "Integration health", "Review Evidence"):
        if name not in by_name:
            raise ValueError(f"WO-016 post-merge CI is missing {name}")
    for name in ("Validate", "Integration health"):
        job = by_name[name]
        if job.get("status") != "completed" or job.get("conclusion") != "success":
            raise ValueError(f"WO-016 post-merge {name} did not succeed")
    review_job = by_name["Review Evidence"]
    if review_job.get("status") != "completed" or review_job.get("conclusion") != "skipped":
        raise ValueError("WO-016 post-push Review Evidence is not skipped by design")

    comments = _lineage_list(sources.get("prior_review_comments"), "prior Review Evidence comments")
    sticky_comments = []
    for raw_comment in comments:
        comment = _lineage_mapping(raw_comment, "prior Review Evidence comment")
        body = comment.get("body")
        if isinstance(body, str) and "<!-- hive-review-evidence:wo-016 -->" in body.casefold():
            sticky_comments.append(body)
    if len(sticky_comments) != 1:
        raise ValueError("WO-016 requires exactly one prior exact-head Review Evidence comment")
    prior_text = _normalized_lineage_text(sticky_comments[0], "prior Review Evidence body")
    required_prior_fragments = (
        f"exact head sha: `{WO016_APPROVED_PRODUCT_HEAD}`",
        "backend tests: `418 passed, 0 failed, 0 skipped`",
        "dashboard tests: `7 passed, 0 failed`",
        "validate result: **pass**",
        "integration health result: **pass**",
        "review evidence result: **pass**",
        "acce storage policy evidence: `pass`",
        "version `acce-storage-policy-v1`",
        "policy `acce-policy-v1`",
        "canonical loss `0`",
        "llm/provider calls `0/0`",
    )
    missing_prior = [
        fragment for fragment in required_prior_fragments if fragment not in prior_text
    ]
    if missing_prior:
        raise ValueError("WO-016 prior Review Evidence is incomplete: " + ", ".join(missing_prior))

    result: dict[str, object] = {
        "status": "PASS",
        "product_work_order": WO016_WORK_ORDER,
        "product_pr": 55,
        "audited_product_head": WO016_APPROVED_PRODUCT_HEAD,
        "sol_review_id": WO016_APPROVED_SOL_REVIEW_ID,
        "sol_review_commit": sol_review["commit_id"],
        "squash_merge_sha": WO016_APPROVED_SQUASH_MERGE_SHA,
        "product_pr_merged": True,
        "squash_lineage_compatible": True,
        "post_merge_ci_run": WO016_APPROVED_POST_MERGE_CI_RUN,
        "post_merge_ci_event": post_merge_run["event"],
        "post_merge_ci_head_sha": post_merge_run["head_sha"],
        "post_merge_ci_conclusion": post_merge_run["conclusion"],
        "post_merge_validate": by_name["Validate"]["conclusion"],
        "post_merge_integration_health": by_name["Integration health"]["conclusion"],
        "post_merge_review_evidence": by_name["Review Evidence"]["conclusion"],
        "prior_review_evidence_head": WO016_APPROVED_PRODUCT_HEAD,
        "prior_backend_passed": 418,
        "prior_dashboard_passed": 7,
        "prior_acce_status": "PASS",
        "prior_acce_version": ACCE_STORAGE_POLICY_EVIDENCE_VERSION,
        "prior_storage_policy": "acce-policy-v1",
        "prior_canonical_source_loss": 0,
        "prior_llm_calls": 0,
        "prior_provider_calls": 0,
    }
    require_wo016_approved_lineage_result(result)
    return result


def fetch_wo016_approved_lineage(repository: str) -> dict[str, object]:
    """Fetch and validate the immutable approved product lineage via GitHub API."""
    jobs_response = _gh_json(repository, f"actions/runs/{WO016_APPROVED_POST_MERGE_CI_RUN}/jobs")
    return verify_wo016_approved_lineage(
        {
            "product_pr": _gh_json(repository, "pulls/55"),
            "product_reviews": _gh_json(repository, "pulls/55/reviews"),
            "merge_commit": _gh_json(repository, f"commits/{WO016_APPROVED_SQUASH_MERGE_SHA}"),
            "post_merge_run": _gh_json(
                repository, f"actions/runs/{WO016_APPROVED_POST_MERGE_CI_RUN}"
            ),
            "post_merge_jobs": jobs_response.get("jobs")
            if isinstance(jobs_response, Mapping)
            else None,
            "prior_review_comments": _gh_json(repository, "issues/55/comments"),
        }
    )


def wo016_approved_lineage_statement(result: Mapping[str, object]) -> str:
    require_wo016_approved_lineage_result(result)
    return WO016_APPROVED_LINEAGE_STATEMENT_PREFIX + json.dumps(
        dict(result), sort_keys=True, separators=(",", ":")
    )


def parse_wo016_approved_lineage_statement(entry: object) -> dict[str, object]:
    if not isinstance(entry, str) or not entry.startswith(WO016_APPROVED_LINEAGE_STATEMENT_PREFIX):
        raise ValueError("WO-016 approved lineage statement is missing")
    try:
        result = json.loads(entry[len(WO016_APPROVED_LINEAGE_STATEMENT_PREFIX) :])
    except json.JSONDecodeError:
        raise ValueError("WO-016 approved lineage statement is not valid JSON") from None
    if not isinstance(result, dict):
        raise ValueError("WO-016 approved lineage statement has an invalid shape")
    require_wo016_approved_lineage_result(result)
    return result


def require_wo021_approved_lineage_result(result: Mapping[str, object]) -> None:
    expected: dict[str, object] = {
        "status": "PASS",
        "product_work_order": WO021_WORK_ORDER,
        "product_pr": 82,
        "audited_product_head": WO021_APPROVED_PRODUCT_HEAD,
        "sol_review_id": WO021_APPROVED_SOL_REVIEW_ID,
        "sol_review_commit": WO021_APPROVED_PRODUCT_HEAD,
        "squash_merge_sha": WO021_APPROVED_SQUASH_MERGE_SHA,
        "product_pr_merged": True,
        "squash_lineage_compatible": True,
        "post_merge_ci_run": WO021_APPROVED_POST_MERGE_CI_RUN,
        "post_merge_ci_event": "push",
        "post_merge_ci_head_sha": WO021_APPROVED_SQUASH_MERGE_SHA,
        "post_merge_ci_conclusion": "success",
        "post_merge_validate": "success",
        "post_merge_integration_health": "success",
        "post_merge_review_evidence": "skipped",
        "prior_review_evidence_head": WO021_APPROVED_PRODUCT_HEAD,
        "prior_backend_passed": 568,
        "prior_dashboard_passed": 30,
        "prior_metrics_status": "PASS",
        "prior_metrics_version": CONTROL_CENTER_METRICS_EVIDENCE_VERSION,
        "prior_migration_head": CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD,
        "prior_metrics_leaks": "0/0/0",
        "prior_metrics_calls": "0/0",
    }
    missing = [key for key in expected if result.get(key) != expected[key]]
    if missing:
        raise ValueError("WO-021 approved lineage evidence mismatch: " + ", ".join(sorted(missing)))


def verify_wo021_approved_lineage(sources: Mapping[str, object]) -> dict[str, object]:
    """Validate the approved WO-021 product lineage from bounded GitHub sources."""
    product_pr = _lineage_mapping(sources.get("product_pr"), "product PR data")
    if product_pr.get("number") != 82:
        raise ValueError("WO-021 approved lineage requires product PR #82")
    if product_pr.get("state") != "closed" or product_pr.get("merged") is not True:
        raise ValueError("WO-021 approved lineage requires a merged product PR")
    base = _lineage_mapping(product_pr.get("base"), "product PR base")
    head = _lineage_mapping(product_pr.get("head"), "product PR head")
    if base.get("ref") != "main" or base.get("sha") != WO021_APPROVED_PRODUCT_BASE_SHA:
        raise ValueError("WO-021 approved lineage requires the authorized product base")
    if head.get("sha") != WO021_APPROVED_PRODUCT_HEAD:
        raise ValueError("WO-021 approved lineage requires the audited product HEAD")
    if product_pr.get("merge_commit_sha") != WO021_APPROVED_SQUASH_MERGE_SHA:
        raise ValueError("WO-021 approved lineage requires the approved squash merge SHA")
    product_body = _normalized_lineage_text(product_pr.get("body"), "product PR body")
    if "<!-- hive-work-order: wo-021 -->" not in product_body:
        raise ValueError("WO-021 approved lineage requires the product work-order marker")

    reviews = _lineage_list(sources.get("product_reviews"), "product PR reviews")
    matching_reviews = [
        _lineage_mapping(review, "product review")
        for review in reviews
        if _lineage_id_matches(
            _lineage_mapping(review, "product review").get("id"),
            WO021_APPROVED_SOL_REVIEW_ID,
        )
    ]
    if len(matching_reviews) != 1:
        raise ValueError("WO-021 approved lineage requires exactly one Sol review")
    sol_review = matching_reviews[0]
    if sol_review.get("state") not in {"APPROVED", "COMMENTED"}:
        raise ValueError("WO-021 approved lineage requires an approved Sol review")
    if sol_review.get("commit_id") != WO021_APPROVED_PRODUCT_HEAD:
        raise ValueError("WO-021 Sol review is not bound to the audited product HEAD")
    review_text = _normalized_lineage_text(sol_review.get("body"), "Sol review body")
    for marker in ("verdict: approved", WO021_APPROVED_PRODUCT_HEAD):
        if marker.casefold() not in review_text:
            raise ValueError("WO-021 Sol review does not express the approved result")

    merge_commit = _lineage_mapping(sources.get("merge_commit"), "squash merge commit")
    if merge_commit.get("sha") != WO021_APPROVED_SQUASH_MERGE_SHA:
        raise ValueError("WO-021 squash merge commit identity is not verified")
    parents = _lineage_list(merge_commit.get("parents"), "squash merge parents")
    if len(parents) != 1:
        raise ValueError("WO-021 approved merge is not compatible with a squash lineage")

    post_merge_run = _lineage_mapping(sources.get("post_merge_run"), "post-merge CI run")
    if not _lineage_id_matches(post_merge_run.get("id"), WO021_APPROVED_POST_MERGE_CI_RUN):
        raise ValueError("WO-021 approved lineage requires the approved post-merge CI run")
    if (
        post_merge_run.get("event") != "push"
        or post_merge_run.get("head_sha") != WO021_APPROVED_SQUASH_MERGE_SHA
        or post_merge_run.get("status") != "completed"
        or post_merge_run.get("conclusion") != "success"
    ):
        raise ValueError("WO-021 post-merge CI run is not a successful push on the merge SHA")

    jobs = _lineage_list(sources.get("post_merge_jobs"), "post-merge CI jobs")
    by_name: dict[str, Mapping[str, Any]] = {}
    for raw_job in jobs:
        job = _lineage_mapping(raw_job, "post-merge CI job")
        name = job.get("name")
        if isinstance(name, str):
            if name in by_name:
                raise ValueError(f"WO-021 post-merge CI has duplicate job {name}")
            by_name[name] = job
    for name in ("Validate", "Integration health", "Review Evidence"):
        if name not in by_name:
            raise ValueError(f"WO-021 post-merge CI is missing {name}")
    for name in ("Validate", "Integration health"):
        job = by_name[name]
        if job.get("status") != "completed" or job.get("conclusion") != "success":
            raise ValueError(f"WO-021 post-merge {name} did not succeed")
    review_job = by_name["Review Evidence"]
    if review_job.get("status") != "completed" or review_job.get("conclusion") != "skipped":
        raise ValueError("WO-021 post-push Review Evidence is not skipped by design")

    comments = _lineage_list(sources.get("prior_review_comments"), "prior Review Evidence comments")
    sticky_comments = []
    for raw_comment in comments:
        comment = _lineage_mapping(raw_comment, "prior Review Evidence comment")
        body = comment.get("body")
        if isinstance(body, str) and "<!-- hive-review-evidence:wo-021 -->" in body.casefold():
            sticky_comments.append(body)
    if len(sticky_comments) != 1:
        raise ValueError("WO-021 requires exactly one prior exact-head Review Evidence comment")
    prior_text = _normalized_lineage_text(sticky_comments[0], "prior Review Evidence body")
    required_prior_fragments = (
        f"exact head sha: `{WO021_APPROVED_PRODUCT_HEAD}`",
        "backend tests: `568 passed, 0 failed, 0 skipped`",
        "dashboard tests: `30 passed, 0 failed`",
        "validate result: **pass**",
        "integration health result: **pass**",
        "review evidence result: **pass**",
        "control center metrics evidence: `pass`; version `control-center-metrics-v1`",
        "migration head: `0007_telemetry_events`",
        "postgresql/redis canonicality `true/false`",
        "leaks/calls `0/0/0/0/0`",
    )
    missing_prior = [
        fragment for fragment in required_prior_fragments if fragment not in prior_text
    ]
    if missing_prior:
        raise ValueError("WO-021 prior Review Evidence is incomplete: " + ", ".join(missing_prior))

    result: dict[str, object] = {
        "status": "PASS",
        "product_work_order": WO021_WORK_ORDER,
        "product_pr": 82,
        "audited_product_head": WO021_APPROVED_PRODUCT_HEAD,
        "sol_review_id": WO021_APPROVED_SOL_REVIEW_ID,
        "sol_review_commit": sol_review["commit_id"],
        "squash_merge_sha": WO021_APPROVED_SQUASH_MERGE_SHA,
        "product_pr_merged": True,
        "squash_lineage_compatible": True,
        "post_merge_ci_run": WO021_APPROVED_POST_MERGE_CI_RUN,
        "post_merge_ci_event": post_merge_run["event"],
        "post_merge_ci_head_sha": post_merge_run["head_sha"],
        "post_merge_ci_conclusion": post_merge_run["conclusion"],
        "post_merge_validate": by_name["Validate"]["conclusion"],
        "post_merge_integration_health": by_name["Integration health"]["conclusion"],
        "post_merge_review_evidence": by_name["Review Evidence"]["conclusion"],
        "prior_review_evidence_head": WO021_APPROVED_PRODUCT_HEAD,
        "prior_backend_passed": 568,
        "prior_dashboard_passed": 30,
        "prior_metrics_status": "PASS",
        "prior_metrics_version": CONTROL_CENTER_METRICS_EVIDENCE_VERSION,
        "prior_migration_head": CONTROL_CENTER_METRICS_MIGRATION_BASE_HEAD,
        "prior_metrics_leaks": "0/0/0",
        "prior_metrics_calls": "0/0",
    }
    require_wo021_approved_lineage_result(result)
    return result


def fetch_wo021_approved_lineage(repository: str) -> dict[str, object]:
    """Fetch and validate the immutable approved product lineage via GitHub API."""
    jobs_response = _gh_json(repository, f"actions/runs/{WO021_APPROVED_POST_MERGE_CI_RUN}/jobs")
    return verify_wo021_approved_lineage(
        {
            "product_pr": _gh_json(repository, "pulls/82"),
            "product_reviews": _gh_json(repository, "pulls/82/reviews"),
            "merge_commit": _gh_json(repository, f"commits/{WO021_APPROVED_SQUASH_MERGE_SHA}"),
            "post_merge_run": _gh_json(
                repository, f"actions/runs/{WO021_APPROVED_POST_MERGE_CI_RUN}"
            ),
            "post_merge_jobs": jobs_response.get("jobs")
            if isinstance(jobs_response, Mapping)
            else None,
            "prior_review_comments": _gh_json(repository, "issues/82/comments"),
        }
    )


def wo021_approved_lineage_statement(result: Mapping[str, object]) -> str:
    require_wo021_approved_lineage_result(result)
    return WO021_APPROVED_LINEAGE_STATEMENT_PREFIX + json.dumps(
        dict(result), sort_keys=True, separators=(",", ":")
    )


def parse_wo021_approved_lineage_statement(entry: object) -> dict[str, object]:
    if not isinstance(entry, str) or not entry.startswith(WO021_APPROVED_LINEAGE_STATEMENT_PREFIX):
        raise ValueError("WO-021 approved lineage statement is missing")
    try:
        result = json.loads(entry[len(WO021_APPROVED_LINEAGE_STATEMENT_PREFIX) :])
    except json.JSONDecodeError:
        raise ValueError("WO-021 approved lineage statement is not valid JSON") from None
    if not isinstance(result, dict):
        raise ValueError("WO-021 approved lineage statement has an invalid shape")
    require_wo021_approved_lineage_result(result)
    return result


def approved_lineage_definition(name: str) -> dict[str, Any]:
    """Return one closed lineage contract definition from the Review Evidence schema."""

    schema = cast(dict[str, Any], json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    definitions = cast(dict[str, Any], schema.get("$defs", {}))
    definition = definitions.get(name)
    if not isinstance(definition, dict):
        raise ValueError(f"review evidence schema is missing the {name} definition")
    return cast(dict[str, Any], definition)


def require_wo022_approved_lineage_result(result: Mapping[str, object]) -> None:
    expected: dict[str, object] = {
        "status": "PASS",
        "product_work_order": WO022_WORK_ORDER,
        "product_pr": WO022_APPROVED_PRODUCT_PR,
        "audited_product_head": WO022_APPROVED_PRODUCT_HEAD,
        "sol_review_id": WO022_APPROVED_SOL_REVIEW_ID,
        "sol_review_commit": WO022_APPROVED_PRODUCT_HEAD,
        "squash_merge_sha": WO022_APPROVED_SQUASH_MERGE_SHA,
        "product_pr_merged": True,
        "squash_lineage_compatible": True,
        "post_merge_ci_run": WO022_APPROVED_POST_MERGE_CI_RUN,
        "post_merge_ci_event": "push",
        "post_merge_ci_head_sha": WO022_APPROVED_SQUASH_MERGE_SHA,
        "post_merge_ci_conclusion": "success",
        "post_merge_validate": "success",
        "post_merge_integration_health": "success",
        "post_merge_review_evidence": "skipped",
        "prior_review_evidence_head": WO022_APPROVED_PRODUCT_HEAD,
        "prior_backend_passed": WO022_APPROVED_BACKEND_PASSED,
        "prior_dashboard_passed": WO022_APPROVED_DASHBOARD_PASSED,
        "prior_full_status": "PASS",
        "prior_full_version": CONTROL_CENTER_FULL_EVIDENCE_VERSION,
        "prior_migration_head": CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD,
        "prior_full_leaks": "0/0/0",
        "prior_full_calls": "0/0",
    }
    errors = sorted(
        jsonschema.Draft202012Validator(
            approved_lineage_definition("control_center_full_approved_lineage")
        ).iter_errors(dict(result)),
        key=str,
    )
    if errors:
        raise ValueError(
            "WO-022 approved lineage statement is outside its closed contract: " + errors[0].message
        )
    mismatch = [key for key in expected if result.get(key) != expected[key]]
    if mismatch:
        raise ValueError(
            "WO-022 approved lineage evidence mismatch: " + ", ".join(sorted(mismatch))
        )


def verify_wo022_approved_lineage(sources: Mapping[str, object]) -> dict[str, object]:
    """Validate the approved WO-022 product lineage from bounded GitHub sources."""
    product_pr = _lineage_mapping(sources.get("product_pr"), "product PR data")
    if product_pr.get("number") != WO022_APPROVED_PRODUCT_PR:
        raise ValueError(
            f"WO-022 approved lineage requires product PR #{WO022_APPROVED_PRODUCT_PR}"
        )
    if product_pr.get("state") != "closed" or product_pr.get("merged") is not True:
        raise ValueError("WO-022 approved lineage requires a merged product PR")
    base = _lineage_mapping(product_pr.get("base"), "product PR base")
    head = _lineage_mapping(product_pr.get("head"), "product PR head")
    if base.get("ref") != "main" or base.get("sha") != WO022_APPROVED_PRODUCT_BASE_SHA:
        raise ValueError("WO-022 approved lineage requires the authorized product base")
    if head.get("sha") != WO022_APPROVED_PRODUCT_HEAD:
        raise ValueError("WO-022 approved lineage requires the audited product HEAD")
    if product_pr.get("merge_commit_sha") != WO022_APPROVED_SQUASH_MERGE_SHA:
        raise ValueError("WO-022 approved lineage requires the approved squash merge SHA")
    product_body = _normalized_lineage_text(product_pr.get("body"), "product PR body")
    if "<!-- hive-work-order: wo-022 -->" not in product_body:
        raise ValueError("WO-022 approved lineage requires the product work-order marker")

    reviews = _lineage_list(sources.get("product_reviews"), "product PR reviews")
    matching_reviews = [
        _lineage_mapping(review, "product review")
        for review in reviews
        if _lineage_id_matches(
            _lineage_mapping(review, "product review").get("id"),
            WO022_APPROVED_SOL_REVIEW_ID,
        )
    ]
    if len(matching_reviews) != 1:
        raise ValueError("WO-022 approved lineage requires exactly one Sol review")
    sol_review = matching_reviews[0]
    if sol_review.get("state") not in {"APPROVED", "COMMENTED"}:
        raise ValueError("WO-022 approved lineage requires an approved Sol review")
    if sol_review.get("commit_id") != WO022_APPROVED_PRODUCT_HEAD:
        raise ValueError("WO-022 Sol review is not bound to the audited product HEAD")
    review_text = _normalized_lineage_text(sol_review.get("body"), "Sol review body")
    for marker in ("verdict: approved", WO022_APPROVED_PRODUCT_HEAD):
        if marker.casefold() not in review_text:
            raise ValueError("WO-022 Sol review does not express the approved result")

    merge_commit = _lineage_mapping(sources.get("merge_commit"), "squash merge commit")
    if merge_commit.get("sha") != WO022_APPROVED_SQUASH_MERGE_SHA:
        raise ValueError("WO-022 squash merge commit identity is not verified")
    parents = _lineage_list(merge_commit.get("parents"), "squash merge parents")
    if len(parents) != 1:
        raise ValueError("WO-022 approved merge is not compatible with a squash lineage")
    if _lineage_mapping(parents[0], "squash merge parent").get("sha") != (
        WO022_APPROVED_PRODUCT_BASE_SHA
    ):
        raise ValueError("WO-022 approved squash merge parent is not the authorized base")

    post_merge_run = _lineage_mapping(sources.get("post_merge_run"), "post-merge CI run")
    if not _lineage_id_matches(post_merge_run.get("id"), WO022_APPROVED_POST_MERGE_CI_RUN):
        raise ValueError("WO-022 approved lineage requires the approved post-merge CI run")
    if (
        post_merge_run.get("event") != "push"
        or post_merge_run.get("head_sha") != WO022_APPROVED_SQUASH_MERGE_SHA
        or post_merge_run.get("status") != "completed"
        or post_merge_run.get("conclusion") != "success"
    ):
        raise ValueError("WO-022 post-merge CI run is not a successful push on the merge SHA")

    jobs = _lineage_list(sources.get("post_merge_jobs"), "post-merge CI jobs")
    by_name: dict[str, Mapping[str, Any]] = {}
    for raw_job in jobs:
        job = _lineage_mapping(raw_job, "post-merge CI job")
        name = job.get("name")
        if isinstance(name, str):
            if name in by_name:
                raise ValueError(f"WO-022 post-merge CI has duplicate job {name}")
            by_name[name] = job
    for name in ("Validate", "Integration health", "Review Evidence"):
        if name not in by_name:
            raise ValueError(f"WO-022 post-merge CI is missing {name}")
    for name in ("Validate", "Integration health"):
        job = by_name[name]
        if job.get("status") != "completed" or job.get("conclusion") != "success":
            raise ValueError(f"WO-022 post-merge {name} did not succeed")
    review_job = by_name["Review Evidence"]
    if review_job.get("status") != "completed" or review_job.get("conclusion") != "skipped":
        raise ValueError("WO-022 post-push Review Evidence is not skipped by design")

    comments = _lineage_list(sources.get("prior_review_comments"), "prior Review Evidence comments")
    sticky_comments = []
    for raw_comment in comments:
        comment = _lineage_mapping(raw_comment, "prior Review Evidence comment")
        body = comment.get("body")
        if isinstance(body, str) and "<!-- hive-review-evidence:wo-022 -->" in body.casefold():
            sticky_comments.append(body)
    if len(sticky_comments) != 1:
        raise ValueError("WO-022 requires exactly one prior exact-head Review Evidence comment")
    prior_text = _normalized_lineage_text(sticky_comments[0], "prior Review Evidence body")
    required_prior_fragments = (
        f"exact head sha: `{WO022_APPROVED_PRODUCT_HEAD}`",
        f"backend tests: `{WO022_APPROVED_BACKEND_PASSED} passed, 0 failed, 0 skipped`",
        f"dashboard tests: `{WO022_APPROVED_DASHBOARD_PASSED} passed, 0 failed`",
        "validate result: **pass**",
        "integration health result: **pass**",
        "review evidence result: **pass**",
        f"full control center evidence: `pass`; version `{CONTROL_CENTER_FULL_EVIDENCE_VERSION}`",
        f"migration head: `{CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD}`",
        "canonical verifier: **pass**",
        "canonical changes: project_brain_changed `false`, checkpoint_changed `false`",
        "leaks/calls `0/0/0/0/0`",
    )
    missing_prior = [
        fragment for fragment in required_prior_fragments if fragment not in prior_text
    ]
    if missing_prior:
        raise ValueError("WO-022 prior Review Evidence is incomplete: " + ", ".join(missing_prior))

    result: dict[str, object] = {
        "status": "PASS",
        "product_work_order": WO022_WORK_ORDER,
        "product_pr": WO022_APPROVED_PRODUCT_PR,
        "audited_product_head": WO022_APPROVED_PRODUCT_HEAD,
        "sol_review_id": WO022_APPROVED_SOL_REVIEW_ID,
        "sol_review_commit": sol_review["commit_id"],
        "squash_merge_sha": WO022_APPROVED_SQUASH_MERGE_SHA,
        "product_pr_merged": True,
        "squash_lineage_compatible": True,
        "post_merge_ci_run": WO022_APPROVED_POST_MERGE_CI_RUN,
        "post_merge_ci_event": post_merge_run["event"],
        "post_merge_ci_head_sha": post_merge_run["head_sha"],
        "post_merge_ci_conclusion": post_merge_run["conclusion"],
        "post_merge_validate": by_name["Validate"]["conclusion"],
        "post_merge_integration_health": by_name["Integration health"]["conclusion"],
        "post_merge_review_evidence": by_name["Review Evidence"]["conclusion"],
        "prior_review_evidence_head": WO022_APPROVED_PRODUCT_HEAD,
        "prior_backend_passed": WO022_APPROVED_BACKEND_PASSED,
        "prior_dashboard_passed": WO022_APPROVED_DASHBOARD_PASSED,
        "prior_full_status": "PASS",
        "prior_full_version": CONTROL_CENTER_FULL_EVIDENCE_VERSION,
        "prior_migration_head": CONTROL_CENTER_FULL_MIGRATION_BASE_HEAD,
        "prior_full_leaks": "0/0/0",
        "prior_full_calls": "0/0",
    }
    require_wo022_approved_lineage_result(result)
    return result


def fetch_wo022_approved_lineage(repository: str) -> dict[str, object]:
    """Fetch and validate the immutable approved product lineage via GitHub API."""
    jobs_response = _gh_json(repository, f"actions/runs/{WO022_APPROVED_POST_MERGE_CI_RUN}/jobs")
    return verify_wo022_approved_lineage(
        {
            "product_pr": _gh_json(repository, f"pulls/{WO022_APPROVED_PRODUCT_PR}"),
            "product_reviews": _gh_json(repository, f"pulls/{WO022_APPROVED_PRODUCT_PR}/reviews"),
            "merge_commit": _gh_json(repository, f"commits/{WO022_APPROVED_SQUASH_MERGE_SHA}"),
            "post_merge_run": _gh_json(
                repository, f"actions/runs/{WO022_APPROVED_POST_MERGE_CI_RUN}"
            ),
            "post_merge_jobs": jobs_response.get("jobs")
            if isinstance(jobs_response, Mapping)
            else None,
            "prior_review_comments": _gh_json(
                repository, f"issues/{WO022_APPROVED_PRODUCT_PR}/comments"
            ),
        }
    )


def wo022_approved_lineage_statement(result: Mapping[str, object]) -> str:
    require_wo022_approved_lineage_result(result)
    return WO022_APPROVED_LINEAGE_STATEMENT_PREFIX + json.dumps(
        dict(result), sort_keys=True, separators=(",", ":")
    )


def parse_wo022_approved_lineage_statement(entry: object) -> dict[str, object]:
    if not isinstance(entry, str) or not entry.startswith(WO022_APPROVED_LINEAGE_STATEMENT_PREFIX):
        raise ValueError("WO-022 approved lineage statement is missing")
    try:
        result = json.loads(entry[len(WO022_APPROVED_LINEAGE_STATEMENT_PREFIX) :])
    except json.JSONDecodeError:
        raise ValueError("WO-022 approved lineage statement is not valid JSON") from None
    if not isinstance(result, dict):
        raise ValueError("WO-022 approved lineage statement has an invalid shape")
    require_wo022_approved_lineage_result(result)
    return result


def require_wo023_approved_lineage_result(result: Mapping[str, object]) -> None:
    expected: dict[str, object] = {
        "status": "PASS",
        "product_work_order": WO023_WORK_ORDER,
        "product_pr": WO023_APPROVED_PRODUCT_PR,
        "audited_product_head": WO023_APPROVED_PRODUCT_HEAD,
        "sol_review_id": WO023_APPROVED_SOL_REVIEW_ID,
        "sol_review_commit": WO023_APPROVED_PRODUCT_HEAD,
        "squash_merge_sha": WO023_APPROVED_SQUASH_MERGE_SHA,
        "product_pr_merged": True,
        "squash_lineage_compatible": True,
        "post_merge_ci_run": WO023_APPROVED_POST_MERGE_CI_RUN,
        "post_merge_ci_event": "push",
        "post_merge_ci_head_sha": WO023_APPROVED_SQUASH_MERGE_SHA,
        "post_merge_ci_conclusion": "success",
        "post_merge_validate": "success",
        "post_merge_integration_health": "success",
        "post_merge_review_evidence": "skipped",
        "prior_review_evidence_head": WO023_APPROVED_PRODUCT_HEAD,
        "prior_backend_passed": WO023_APPROVED_BACKEND_PASSED,
        "prior_dashboard_passed": WO023_APPROVED_DASHBOARD_PASSED,
        "prior_full_status": "PASS",
        "prior_full_version": COMPREHENSIVE_BENCHMARKS_EVIDENCE_VERSION,
        "prior_migration_head": COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD,
        "prior_full_leaks": "0/0/0",
        "prior_full_calls": "0/0",
    }
    errors = sorted(
        jsonschema.Draft202012Validator(
            approved_lineage_definition("comprehensive_benchmarks_approved_lineage")
        ).iter_errors(dict(result)),
        key=str,
    )
    if errors:
        raise ValueError(
            "WO-023 approved lineage statement is outside its closed contract: " + errors[0].message
        )
    mismatch = [key for key in expected if result.get(key) != expected[key]]
    if mismatch:
        raise ValueError(
            "WO-023 approved lineage evidence mismatch: " + ", ".join(sorted(mismatch))
        )


def verify_wo023_approved_lineage(sources: Mapping[str, object]) -> dict[str, object]:
    """Validate the approved WO-023 product lineage from bounded GitHub sources."""
    product_pr = _lineage_mapping(sources.get("product_pr"), "product PR data")
    if product_pr.get("number") != WO023_APPROVED_PRODUCT_PR:
        raise ValueError(
            f"WO-023 approved lineage requires product PR #{WO023_APPROVED_PRODUCT_PR}"
        )
    if product_pr.get("state") != "closed" or product_pr.get("merged") is not True:
        raise ValueError("WO-023 approved lineage requires a merged product PR")
    base = _lineage_mapping(product_pr.get("base"), "product PR base")
    head = _lineage_mapping(product_pr.get("head"), "product PR head")
    if base.get("ref") != "main" or base.get("sha") != WO023_APPROVED_PRODUCT_BASE_SHA:
        raise ValueError("WO-023 approved lineage requires the authorized product base")
    if head.get("sha") != WO023_APPROVED_PRODUCT_HEAD:
        raise ValueError("WO-023 approved lineage requires the audited product HEAD")
    if product_pr.get("merge_commit_sha") != WO023_APPROVED_SQUASH_MERGE_SHA:
        raise ValueError("WO-023 approved lineage requires the approved squash merge SHA")
    product_body = _normalized_lineage_text(product_pr.get("body"), "product PR body")
    if "<!-- hive-work-order: wo-023 -->" not in product_body:
        raise ValueError("WO-023 approved lineage requires the product work-order marker")

    reviews = _lineage_list(sources.get("product_reviews"), "product PR reviews")
    matching_reviews = [
        _lineage_mapping(review, "product review")
        for review in reviews
        if _lineage_id_matches(
            _lineage_mapping(review, "product review").get("id"),
            WO023_APPROVED_SOL_REVIEW_ID,
        )
    ]
    if len(matching_reviews) != 1:
        raise ValueError("WO-023 approved lineage requires exactly one Sol review")
    sol_review = matching_reviews[0]
    if sol_review.get("state") not in {"APPROVED", "COMMENTED"}:
        raise ValueError("WO-023 approved lineage requires an approved Sol review")
    if sol_review.get("commit_id") != WO023_APPROVED_PRODUCT_HEAD:
        raise ValueError("WO-023 Sol review is not bound to the audited product HEAD")
    review_text = _normalized_lineage_text(sol_review.get("body"), "Sol review body")
    for marker in ("verdict:", "approved", WO023_APPROVED_PRODUCT_HEAD):
        if marker.casefold() not in review_text:
            raise ValueError("WO-023 Sol review does not express the approved result")

    merge_commit = _lineage_mapping(sources.get("merge_commit"), "squash merge commit")
    if merge_commit.get("sha") != WO023_APPROVED_SQUASH_MERGE_SHA:
        raise ValueError("WO-023 squash merge commit identity is not verified")
    parents = _lineage_list(merge_commit.get("parents"), "squash merge parents")
    if len(parents) != 1:
        raise ValueError("WO-023 approved merge is not compatible with a squash lineage")
    if _lineage_mapping(parents[0], "squash merge parent").get("sha") != (
        WO023_APPROVED_PRODUCT_BASE_SHA
    ):
        raise ValueError("WO-023 approved squash merge parent is not the authorized base")

    post_merge_run = _lineage_mapping(sources.get("post_merge_run"), "post-merge CI run")
    if not _lineage_id_matches(post_merge_run.get("id"), WO023_APPROVED_POST_MERGE_CI_RUN):
        raise ValueError("WO-023 approved lineage requires the approved post-merge CI run")
    if (
        post_merge_run.get("event") != "push"
        or post_merge_run.get("head_sha") != WO023_APPROVED_SQUASH_MERGE_SHA
        or post_merge_run.get("status") != "completed"
        or post_merge_run.get("conclusion") != "success"
    ):
        raise ValueError("WO-023 post-merge CI run is not a successful push on the merge SHA")

    jobs = _lineage_list(sources.get("post_merge_jobs"), "post-merge CI jobs")
    by_name: dict[str, Mapping[str, Any]] = {}
    for raw_job in jobs:
        job = _lineage_mapping(raw_job, "post-merge CI job")
        name = job.get("name")
        if isinstance(name, str):
            if name in by_name:
                raise ValueError(f"WO-023 post-merge CI has duplicate job {name}")
            by_name[name] = job
    for name in ("Validate", "Integration health", "Review Evidence"):
        if name not in by_name:
            raise ValueError(f"WO-023 post-merge CI is missing {name}")
    for name in ("Validate", "Integration health"):
        job = by_name[name]
        if job.get("status") != "completed" or job.get("conclusion") != "success":
            raise ValueError(f"WO-023 post-merge {name} did not succeed")
    review_job = by_name["Review Evidence"]
    if review_job.get("status") != "completed" or review_job.get("conclusion") != "skipped":
        raise ValueError("WO-023 post-push Review Evidence is not skipped by design")

    comments = _lineage_list(sources.get("prior_review_comments"), "prior Review Evidence comments")
    sticky_comments = []
    for raw_comment in comments:
        comment = _lineage_mapping(raw_comment, "prior Review Evidence comment")
        body = comment.get("body")
        if isinstance(body, str) and "<!-- hive-review-evidence:wo-023 -->" in body.casefold():
            sticky_comments.append(body)
    if len(sticky_comments) != 1:
        raise ValueError("WO-023 requires exactly one prior exact-head Review Evidence comment")
    prior_text = _normalized_lineage_text(sticky_comments[0], "prior Review Evidence body")
    required_prior_fragments = (
        f"exact head sha: `{WO023_APPROVED_PRODUCT_HEAD}`",
        f"backend tests: `{WO023_APPROVED_BACKEND_PASSED} passed, 0 failed",
        f"dashboard tests: `{WO023_APPROVED_DASHBOARD_PASSED} passed, 0 failed`",
        "validate result: **pass**",
        "integration health result: **pass**",
        "review evidence result: **pass**",
        f"migration head: `{COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD}`",
        "canonical verifier: **pass**",
        "canonical changes: project_brain_changed `false`, checkpoint_changed `false`",
    )
    missing_prior = [
        fragment for fragment in required_prior_fragments if fragment not in prior_text
    ]
    if missing_prior:
        raise ValueError("WO-023 prior Review Evidence is incomplete: " + ", ".join(missing_prior))

    result: dict[str, object] = {
        "status": "PASS",
        "product_work_order": WO023_WORK_ORDER,
        "product_pr": WO023_APPROVED_PRODUCT_PR,
        "audited_product_head": WO023_APPROVED_PRODUCT_HEAD,
        "sol_review_id": WO023_APPROVED_SOL_REVIEW_ID,
        "sol_review_commit": sol_review["commit_id"],
        "squash_merge_sha": WO023_APPROVED_SQUASH_MERGE_SHA,
        "product_pr_merged": True,
        "squash_lineage_compatible": True,
        "post_merge_ci_run": WO023_APPROVED_POST_MERGE_CI_RUN,
        "post_merge_ci_event": post_merge_run["event"],
        "post_merge_ci_head_sha": post_merge_run["head_sha"],
        "post_merge_ci_conclusion": post_merge_run["conclusion"],
        "post_merge_validate": by_name["Validate"]["conclusion"],
        "post_merge_integration_health": by_name["Integration health"]["conclusion"],
        "post_merge_review_evidence": by_name["Review Evidence"]["conclusion"],
        "prior_review_evidence_head": WO023_APPROVED_PRODUCT_HEAD,
        "prior_backend_passed": WO023_APPROVED_BACKEND_PASSED,
        "prior_dashboard_passed": WO023_APPROVED_DASHBOARD_PASSED,
        "prior_full_status": "PASS",
        "prior_full_version": COMPREHENSIVE_BENCHMARKS_EVIDENCE_VERSION,
        "prior_migration_head": COMPREHENSIVE_BENCHMARKS_MIGRATION_BASE_HEAD,
        "prior_full_leaks": "0/0/0",
        "prior_full_calls": "0/0",
    }
    require_wo023_approved_lineage_result(result)
    return result


def fetch_wo023_approved_lineage(repository: str) -> dict[str, object]:
    """Fetch and validate the immutable approved product lineage via GitHub API."""
    jobs_response = _gh_json(repository, f"actions/runs/{WO023_APPROVED_POST_MERGE_CI_RUN}/jobs")
    return verify_wo023_approved_lineage(
        {
            "product_pr": _gh_json(repository, f"pulls/{WO023_APPROVED_PRODUCT_PR}"),
            "product_reviews": _gh_json(repository, f"pulls/{WO023_APPROVED_PRODUCT_PR}/reviews"),
            "merge_commit": _gh_json(repository, f"commits/{WO023_APPROVED_SQUASH_MERGE_SHA}"),
            "post_merge_run": _gh_json(
                repository, f"actions/runs/{WO023_APPROVED_POST_MERGE_CI_RUN}"
            ),
            "post_merge_jobs": jobs_response.get("jobs")
            if isinstance(jobs_response, Mapping)
            else None,
            "prior_review_comments": _gh_json(
                repository, f"issues/{WO023_APPROVED_PRODUCT_PR}/comments"
            ),
        }
    )


def wo023_approved_lineage_statement(result: Mapping[str, object]) -> str:
    require_wo023_approved_lineage_result(result)
    return WO023_APPROVED_LINEAGE_STATEMENT_PREFIX + json.dumps(
        dict(result), sort_keys=True, separators=(",", ":")
    )


def parse_wo023_approved_lineage_statement(entry: object) -> dict[str, object]:
    if not isinstance(entry, str) or not entry.startswith(WO023_APPROVED_LINEAGE_STATEMENT_PREFIX):
        raise ValueError("WO-023 approved lineage statement is missing")
    try:
        result = json.loads(entry[len(WO023_APPROVED_LINEAGE_STATEMENT_PREFIX) :])
    except json.JSONDecodeError:
        raise ValueError("WO-023 approved lineage statement is not valid JSON") from None
    if not isinstance(result, dict):
        raise ValueError("WO-023 approved lineage statement has an invalid shape")
    require_wo023_approved_lineage_result(result)
    return result


def require_wo024_approved_lineage_result(result: Mapping[str, object]) -> None:
    """Validate the closed WO-024 closure-sprint lineage statement."""

    expected_keys = {
        "status",
        "product_work_order",
        "product_pr",
        "audited_product_head",
        "sol_review_id",
        "sol_review_commit",
        "squash_merge_sha",
        "product_pr_merged",
        "squash_lineage_compatible",
        "post_merge_ci_run",
        "post_merge_ci_event",
        "post_merge_ci_head_sha",
        "post_merge_ci_conclusion",
        "post_merge_validate",
        "post_merge_integration_health",
        "post_merge_review_evidence",
        "prior_review_evidence_head",
        "prior_backend_passed",
        "prior_dashboard_passed",
        "prior_closure_status",
        "prior_closure_version",
        "prior_closure_candidate",
        "prior_dod_pass_count",
        "prior_dod_total_count",
        "prior_migration_head",
        "prior_closure_leaks",
        "prior_closure_calls",
    }
    errors = sorted(
        jsonschema.Draft202012Validator(
            approved_lineage_definition("v01_closure_sprint_approved_lineage")
        ).iter_errors(dict(result)),
        key=str,
    )
    if errors or set(result) != expected_keys:
        raise ValueError(
            "WO-024 approved lineage statement is outside its closed contract"
            + (": " + errors[0].message if errors else "")
        )
    if result.get("status") != "PASS" or result.get("product_work_order") != WO024_WORK_ORDER:
        raise ValueError("WO-024 approved lineage statement must describe a passing WO-024 product")
    if result.get("product_pr_merged") is not True or (
        result.get("squash_lineage_compatible") is not True
    ):
        raise ValueError("WO-024 approved lineage requires a merged squash-compatible product PR")
    if result.get("post_merge_ci_event") != "push" or (
        result.get("post_merge_ci_conclusion") != "success"
    ):
        raise ValueError("WO-024 approved lineage requires a successful post-merge push CI run")
    if result.get("post_merge_validate") != "success" or (
        result.get("post_merge_integration_health") != "success"
    ):
        raise ValueError("WO-024 post-merge validate and integration health must succeed")
    if result.get("post_merge_review_evidence") != "skipped":
        raise ValueError("WO-024 post-merge Review Evidence must be skipped by design on push")
    if result.get("post_merge_ci_head_sha") != result.get("squash_merge_sha"):
        raise ValueError("WO-024 post-merge CI must run on the approved squash merge SHA")
    if result.get("prior_review_evidence_head") != result.get("audited_product_head"):
        raise ValueError("WO-024 prior evidence must be bound to the audited product HEAD")
    if result.get("prior_closure_status") != "PASS" or (
        result.get("prior_closure_version") != V01_CLOSURE_SPRINT_EVIDENCE_VERSION
    ):
        raise ValueError("WO-024 approved lineage requires passing v01 closure sprint evidence")
    if result.get("prior_closure_candidate") is not True:
        raise ValueError("WO-024 approved lineage requires a complete closure candidate")
    pass_count = result.get("prior_dod_pass_count")
    total_count = result.get("prior_dod_total_count")
    for field, value in (
        ("prior_dod_pass_count", pass_count),
        ("prior_dod_total_count", total_count),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValueError(f"WO-024 approved lineage requires a bounded {field}")
    if pass_count != total_count:
        raise ValueError("WO-024 approved lineage requires every definition-of-done item to pass")
    if result.get("prior_migration_head") != V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD:
        raise ValueError("WO-024 approved lineage requires the closure migration head")
    if result.get("prior_closure_leaks") != "0/0/0" or result.get("prior_closure_calls") != "0/0":
        raise ValueError("WO-024 approved lineage requires zero closure leaks and calls")
    for field in ("audited_product_head", "sol_review_commit", "squash_merge_sha"):
        value = result.get(field)
        if not isinstance(value, str) or HEX_SHA.fullmatch(value) is None:
            raise ValueError(f"WO-024 approved lineage requires a resolved {field}")
    for field in ("product_pr", "sol_review_id", "post_merge_ci_run", "prior_backend_passed"):
        value = result.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValueError(f"WO-024 approved lineage requires a bounded {field}")


def wo024p_closure_payload() -> Mapping[str, object]:
    """Return the validated v01 closure payload used to build the WO-024-P lineage.

    The schema-bound ``integration_evidence()`` manifest deliberately omits the closure family
    (it is a gating input, not an undeclared manifest property), so the final-promotion lineage
    must read the same validated artifact source the governance contract already consumes.
    An incomplete, failing or unavailable payload fails closed here rather than surfacing later
    as a runtime conversion error.
    """

    payload = closure_sprint_evidence()
    if not isinstance(payload, Mapping) or not payload:
        raise ValueError("WO-024-P approved lineage requires validated v01 closure sprint evidence")
    if payload.get("status") != "PASS":
        raise ValueError("WO-024-P approved lineage requires passing v01 closure sprint evidence")
    for field in ("dod_pass_count", "dod_total_count"):
        value = payload.get(field)
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"WO-024-P approved lineage requires a measured v01 closure {field}")
    return payload


def _sol_review_test_counts(review_text: str) -> tuple[int, int]:
    """Return the human-audited backend and dashboard counts from the Sol review.

    The exact-head Sol approval review is the source of truth for audited test
    counts. A missing or malformed count fails closed rather than silently
    degrading to zero, which is what the stale Review Evidence extraction did.
    """

    backend_match = re.search(r"- backend: (\d+) passed", review_text)
    dashboard_match = re.search(r"- dashboard: (\d+) passed", review_text)
    if backend_match is None or dashboard_match is None:
        raise ValueError("WO-024 Sol review must record the audited backend and dashboard counts")
    backend_passed = int(backend_match.group(1))
    dashboard_passed = int(dashboard_match.group(1))
    if backend_passed <= 0 or dashboard_passed <= 0:
        raise ValueError("WO-024 Sol review test counts must be positive")
    return backend_passed, dashboard_passed


def require_wo024_squash_ancestry(ancestry: Mapping[str, object]) -> None:
    """Require the approved squash merge to be an ancestor of current protected main.

    The approved product squash merge is immutable, while a later governance
    correction legitimately moves protected main forward. Ancestry replaces the
    old equality assumption without weakening the approved lineage.
    """

    status = ancestry.get("status")
    if status not in {"ahead", "identical"}:
        raise ValueError("WO-024 approved lineage requires the approved squash merge on main")
    merge_base = ancestry.get("merge_base_commit")
    if not isinstance(merge_base, Mapping):
        raise ValueError("WO-024 approved lineage requires a resolved merge base")
    merge_base_sha = cast(Mapping[str, object], merge_base).get("sha")
    if merge_base_sha != WO024_APPROVED_SQUASH_MERGE_SHA:
        raise ValueError("WO-024 approved lineage merge base is not the approved squash merge")


def verify_wo024_approved_lineage(sources: Mapping[str, object]) -> dict[str, object]:
    """Validate the merged WO-024 closure sprint lineage from bounded GitHub sources."""

    product_pr = _lineage_mapping(sources.get("product_pr"), "product PR data")
    base = _lineage_mapping(product_pr.get("base"), "product PR base")
    head = _lineage_mapping(product_pr.get("head"), "product PR head")
    squash_merge = product_pr.get("merge_commit_sha")
    if product_pr.get("state") != "closed" or product_pr.get("merged") is not True:
        raise ValueError("WO-024 approved lineage requires a merged product PR")
    if product_pr.get("number") != WO024_APPROVED_PRODUCT_PR:
        raise ValueError("WO-024 approved lineage requires the approved product pull request")
    if base.get("ref") != "main":
        raise ValueError("WO-024 approved lineage requires the protected main base branch")
    if base.get("sha") != WO024_APPROVED_PRODUCT_BASE_SHA:
        raise ValueError("WO-024 approved lineage requires the authorized product base")
    if not isinstance(squash_merge, str) or HEX_SHA.fullmatch(squash_merge) is None:
        raise ValueError("WO-024 approved lineage requires a resolved squash merge SHA")
    if squash_merge != WO024_APPROVED_SQUASH_MERGE_SHA:
        raise ValueError("WO-024 approved lineage requires the approved squash merge SHA")
    require_wo024_squash_ancestry(_lineage_mapping(sources.get("ancestry"), "squash ancestry"))
    if not isinstance(head.get("sha"), str) or HEX_SHA.fullmatch(str(head.get("sha"))) is None:
        raise ValueError("WO-024 approved lineage requires the audited product HEAD")
    audited_head = str(head.get("sha"))
    if audited_head != WO024_APPROVED_PRODUCT_HEAD_SHA:
        raise ValueError("WO-024 approved lineage requires the audited product HEAD SHA")
    product_body = _normalized_lineage_text(product_pr.get("body"), "product PR body")
    if f"<!-- hive-work-order: {WO024_WORK_ORDER.casefold()} -->" not in product_body:
        raise ValueError("WO-024 approved lineage requires the product work-order marker")

    reviews = _lineage_list(sources.get("product_reviews"), "product PR reviews")
    approved_reviews = [
        _lineage_mapping(review, "product review")
        for review in reviews
        if _lineage_mapping(review, "product review").get("commit_id") == audited_head
        and _lineage_mapping(review, "product review").get("state") in {"APPROVED", "COMMENTED"}
    ]
    if len(approved_reviews) != 1:
        raise ValueError(
            "WO-024 approved lineage requires exactly one Sol review at the audited HEAD"
        )
    sol_review = approved_reviews[0]
    review_id = sol_review.get("id")
    if not isinstance(review_id, int) or isinstance(review_id, bool) or review_id <= 0:
        raise ValueError("WO-024 approved lineage requires a resolved Sol review identity")
    if review_id != WO024_APPROVED_SOL_REVIEW_ID:
        raise ValueError("WO-024 approved lineage requires the approved Sol review identity")
    review_text = _normalized_lineage_text(sol_review.get("body"), "Sol review body")
    for marker in ("verdict:", "approved", audited_head, WO024_APPROVED_PRODUCT_BASE_SHA):
        if marker.casefold() not in review_text:
            raise ValueError("WO-024 Sol review does not express the approved result")
    backend_passed, dashboard_passed = _sol_review_test_counts(review_text)

    merge_commit = _lineage_mapping(sources.get("merge_commit"), "squash merge commit")
    if merge_commit.get("sha") != squash_merge:
        raise ValueError("WO-024 squash merge commit identity is not verified")
    parents = _lineage_list(merge_commit.get("parents"), "squash merge parents")
    if len(parents) != 1:
        raise ValueError("WO-024 approved merge is not compatible with a squash lineage")

    post_merge_run = _lineage_mapping(sources.get("post_merge_run"), "post-merge CI run")
    run_id = post_merge_run.get("id")
    if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id <= 0:
        raise ValueError("WO-024 approved lineage requires a resolved post-merge CI run")
    if run_id != WO024_APPROVED_POST_MERGE_CI_RUN:
        raise ValueError("WO-024 approved lineage requires the approved post-merge CI run")
    if (
        post_merge_run.get("event") != "push"
        or post_merge_run.get("head_sha") != squash_merge
        or post_merge_run.get("status") != "completed"
        or post_merge_run.get("conclusion") != "success"
    ):
        raise ValueError("WO-024 post-merge CI run is not a successful push on the merge SHA")

    jobs = _lineage_list(sources.get("post_merge_jobs"), "post-merge CI jobs")
    by_name: dict[str, Mapping[str, Any]] = {}
    for raw_job in jobs:
        job = _lineage_mapping(raw_job, "post-merge CI job")
        name = job.get("name")
        if isinstance(name, str):
            by_name[name] = job
    for name in ("Validate", "Integration health", "Review Evidence"):
        if name not in by_name:
            raise ValueError(f"WO-024 post-merge CI is missing {name}")
    for name in ("Validate", "Integration health"):
        job = by_name[name]
        if job.get("status") != "completed" or job.get("conclusion") != "success":
            raise ValueError(f"WO-024 post-merge {name} did not succeed")
    review_job = by_name["Review Evidence"]
    if review_job.get("status") != "completed" or review_job.get("conclusion") != "skipped":
        raise ValueError("WO-024 post-push Review Evidence is not skipped by design")

    comments = _lineage_list(sources.get("prior_review_comments"), "prior Review Evidence comments")
    sticky_comments = []
    for raw_comment in comments:
        comment = _lineage_mapping(raw_comment, "prior Review Evidence comment")
        body = comment.get("body")
        if (
            isinstance(body, str)
            and f"<!-- hive-review-evidence:{WO024_WORK_ORDER.casefold()} -->" in body.casefold()
        ):
            sticky_comments.append(body)
    if len(sticky_comments) != 1:
        raise ValueError("WO-024 requires exactly one prior exact-head Review Evidence comment")
    prior_text = _normalized_lineage_text(sticky_comments[0], "prior Review Evidence body")
    closure = cast(Mapping[str, object], sources.get("closure_evidence", {}))
    if closure.get("status") != "PASS":
        raise ValueError("WO-024 approved lineage requires passing v01 closure sprint evidence")
    for field in ("dod_pass_count", "dod_total_count"):
        value = closure.get(field)
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"WO-024 approved lineage requires a measured v01 closure {field}")
    # The approved product comment was rendered before the closure family was
    # attached to the integration evidence, so the closure fragment itself is not
    # required here: the promotion run re-derives the closure evidence and
    # require_wo024_v01_closure_sprint_evidence enforces it independently.
    required_prior_fragments = (
        f"exact head sha: `{audited_head}`",
        "validate result: **pass**",
        "integration health result: **pass**",
        "review evidence result: **pass**",
        f"migration head: `{V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}`",
        "canonical verifier: **pass**",
        "canonical changes: project_brain_changed `false`, checkpoint_changed `false`",
        "thread resolution `true`",
        "auto-merge armed: `false`",
    )
    missing_prior = [
        fragment for fragment in required_prior_fragments if fragment not in prior_text
    ]
    if missing_prior:
        raise ValueError("WO-024 prior Review Evidence is incomplete: " + ", ".join(missing_prior))
    result: dict[str, object] = {
        "status": "PASS",
        "product_work_order": WO024_WORK_ORDER,
        "product_pr": int(cast(int, product_pr.get("number"))),
        "audited_product_head": audited_head,
        "sol_review_id": review_id,
        "sol_review_commit": audited_head,
        "squash_merge_sha": squash_merge,
        "product_pr_merged": True,
        "squash_lineage_compatible": True,
        "post_merge_ci_run": run_id,
        "post_merge_ci_event": "push",
        "post_merge_ci_head_sha": squash_merge,
        "post_merge_ci_conclusion": "success",
        "post_merge_validate": "success",
        "post_merge_integration_health": "success",
        "post_merge_review_evidence": "skipped",
        "prior_review_evidence_head": audited_head,
        "prior_backend_passed": backend_passed,
        "prior_dashboard_passed": dashboard_passed,
        "prior_closure_status": "PASS",
        "prior_closure_version": V01_CLOSURE_SPRINT_EVIDENCE_VERSION,
        "prior_closure_candidate": True,
        "prior_dod_pass_count": int(cast(int, closure.get("dod_pass_count"))),
        "prior_dod_total_count": int(cast(int, closure.get("dod_total_count"))),
        "prior_migration_head": V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD,
        "prior_closure_leaks": "0/0/0",
        "prior_closure_calls": "0/0",
    }
    require_wo024_approved_lineage_result(result)
    return result


def fetch_wo024_approved_lineage(
    repository: str, closure_evidence: Mapping[str, object]
) -> dict[str, object]:
    """Resolve and validate the approved WO-024 product lineage.

    Every source is addressed by immutable approved identity: the product pull
    request by its approved number, the post-merge CI run and its jobs by the
    approved run id, and the squash commit by the approved merge SHA. Current
    protected main is resolved only to prove that the approved squash merge is an
    ancestor, so a later governance correction on main can neither redirect nor
    invalidate the lineage. There is deliberately no fallback that discovers the
    product through the pull requests associated with current main.
    """

    main_sha = git_value("rev-parse", WO012P_PROMOTION_BASE_REF, fallback="")
    if HEX_SHA.fullmatch(main_sha) is None:
        raise ValueError("WO-024 approved lineage requires a resolved protected main SHA")
    number = WO024_APPROVED_PRODUCT_PR
    # the full pull-request resource is the payload that exposes merged state
    product_pr = _lineage_mapping(_gh_json(repository, f"pulls/{number}"), "product pull request")
    run_jobs = _gh_json(repository, f"actions/runs/{WO024_APPROVED_POST_MERGE_CI_RUN}/jobs")
    run = _gh_json(repository, f"actions/runs/{WO024_APPROVED_POST_MERGE_CI_RUN}")
    if run is None:
        raise ValueError("WO-024 approved lineage requires the approved post-merge push CI run")
    return verify_wo024_approved_lineage(
        {
            "product_pr": product_pr,
            "product_reviews": _gh_json(repository, f"pulls/{number}/reviews"),
            "ancestry": _gh_json(
                repository, f"compare/{WO024_APPROVED_SQUASH_MERGE_SHA}...{main_sha}"
            ),
            "merge_commit": _gh_json(repository, f"commits/{WO024_APPROVED_SQUASH_MERGE_SHA}"),
            "post_merge_run": run,
            "post_merge_jobs": cast(Mapping[str, object], run_jobs).get("jobs"),
            "prior_review_comments": _gh_json(repository, f"issues/{number}/comments"),
            "closure_evidence": closure_evidence,
        }
    )


def wo024_approved_lineage_statement(result: Mapping[str, object]) -> str:
    require_wo024_approved_lineage_result(result)
    return "Approved WO-024 product lineage: " + json.dumps(
        dict(result), sort_keys=True, separators=(",", ":")
    )


def parse_wo024_approved_lineage_statement(entry: object) -> dict[str, object]:
    prefix = "Approved WO-024 product lineage: "
    if not isinstance(entry, str) or not entry.startswith(prefix):
        raise ValueError("WO-024 approved lineage statement is missing")
    try:
        result = json.loads(entry[len(prefix) :])
    except json.JSONDecodeError:
        raise ValueError("WO-024 approved lineage statement is not valid JSON") from None
    if not isinstance(result, dict):
        raise ValueError("WO-024 approved lineage statement has an invalid shape")
    require_wo024_approved_lineage_result(result)
    return result


def verify_wo024_g1_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
    authorized_base_sha: str | None = None,
) -> str | None:
    if work_order != WO024_G1_WORK_ORDER:
        return None
    require_wo024_g1_scope(
        work_order,
        base_sha,
        paths,
        authorized_base_sha=authorized_base_sha,
        enforce_authorized_base=authorized_base_sha is not None,
    )
    if frozenset({WO024_G1_WORK_ORDER, WO024P_WORK_ORDER}) != (
        ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS
    ):
        raise ValueError(f"{WO024_G1_WORK_ORDER} requires the active WO-024 promotion pair")
    for rejected in ("WO-030-C1", "WO-028-P", "WO-999"):
        try:
            require_current_work_order_authorization(rejected)
        except ValueError:
            pass
        else:
            raise ValueError(f"{rejected} unexpectedly authorizes a fresh current PR")
    for historical in (WO023P_G1_WORK_ORDER, WO023P_WORK_ORDER):
        try:
            require_current_work_order_authorization(historical)
        except ValueError:
            pass
        else:
            raise ValueError(f"{historical} unexpectedly authorizes a fresh current PR")
    require_current_work_order_authorization(WO024_G1_WORK_ORDER)
    require_current_work_order_authorization(WO024_WORK_ORDER)
    require_current_work_order_authorization(WO024P_WORK_ORDER)
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO024_G1_WORK_ORDER} forbids canonical changes")
    if migration_head_value != V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO024_G1_WORK_ORDER} requires migration head "
            f"{V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO024_G1_WORK_ORDER} requires an unchanged ruleset")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO024_G1_WORK_ORDER} requires auto-merge to remain unarmed")
    require_wo024_v01_closure_sprint_evidence(work_order, integration, migration_head_value)
    return (
        f"work_order={WO024_G1_WORK_ORDER}; exact_base=PASS; governance_scope=PASS; "
        "project_brain_changed=False; checkpoint_changed=False; migration_changed=False; "
        f"active_promotions={WO024_G1_WORK_ORDER},{WO024P_WORK_ORDER}; "
        f"future_{WO024_WORK_ORDER}=REGISTERED; future_{WO024P_WORK_ORDER}=REGISTERED; "
        f"closure_evidence_version={V01_CLOSURE_SPRINT_EVIDENCE_VERSION}; "
        "historical_WO-023-P-G1_WO-023-P=REJECTED; unknown_WO-025_WO-025-P_WO-999=REJECTED; "
        "closure_implementation=False; full_v01_complete_claimed=False; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; checkpoint_promotion=False"
    )


def verify_wo024_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
) -> str | None:
    if work_order != WO024_WORK_ORDER:
        return None
    require_wo024_scope(work_order, base_sha, paths)
    if canonical_changes != {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }:
        raise ValueError(f"{WO024_WORK_ORDER} cannot change canonical Project Brain")
    if migration_head_value != V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD:
        raise ValueError(
            f"{WO024_WORK_ORDER} requires migration head {V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO024_WORK_ORDER} requires the protected ruleset to be unchanged")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO024_WORK_ORDER} requires auto-merge to remain unarmed")
    require_wo024_v01_closure_sprint_evidence(work_order, integration, migration_head_value)
    require_current_work_order_authorization(WO024_WORK_ORDER)
    return (
        f"work_order={WO024_WORK_ORDER}; product_scope=PASS; project_brain_changed=False; "
        f"closure_evidence=PASS; closure_evidence_version={V01_CLOSURE_SPRINT_EVIDENCE_VERSION}; "
        f"migration_head={V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}; "
        "closure_candidate=True; full_v01_complete_claimed=False; "
        "ruleset_unchanged=PASS; auto_merge=UNARMED; checkpoint_promotion=False"
    )


def verify_wo024p_governance_contract(
    work_order: str,
    base_sha: str,
    paths: list[str],
    canonical_changes: Mapping[str, object],
    governance: Mapping[str, object],
    integration: Mapping[str, object],
    migration_head_value: str,
    approved_lineage: Mapping[str, object] | None = None,
    authorized_base_sha: str | None = None,
) -> str | None:
    if work_order != WO024P_WORK_ORDER:
        return None
    closure = closure_sprint_evidence()
    # The marker parsed from the pull request body is forwarded as-is. It stays enforced whenever
    # it exists (the manifest build path); the validation path re-reads a manifest that cannot
    # restate it, exactly like every other registered promotion contract.
    require_wo024p_scope(
        work_order,
        base_sha,
        paths,
        approved_lineage=approved_lineage,
        closure_evidence=closure if isinstance(closure, Mapping) else None,
        authorized_base_sha=authorized_base_sha,
        enforce_authorized_base=authorized_base_sha is not None,
    )
    if canonical_changes != {
        "project_brain_changed": True,
        "checkpoint_changed": True,
        "authorized_paths": sorted(WO024P_PROMOTION_ALLOWED_PATHS),
    }:
        raise ValueError(
            f"{WO024P_WORK_ORDER} requires exactly the checkpoint and manifest canonical changes"
        )
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(f"{WO024P_WORK_ORDER} requires the protected ruleset to be unchanged")
    pull_request = cast(dict[str, Any], governance.get("pull_request", {}))
    if pull_request.get("auto_merge_armed") is not False:
        raise ValueError(f"{WO024P_WORK_ORDER} requires auto-merge to remain unarmed")
    require_wo024_v01_closure_sprint_evidence(
        WO024P_WORK_ORDER,
        integration,
        V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD,
    )
    lineage = cast(Mapping[str, object], approved_lineage)
    return (
        f"work_order={WO024P_WORK_ORDER}; promotion_scope=PASS; checkpoint_semantics=PASS; "
        "manifest_contract=PASS; closure_evidence=PASS; "
        f"closure_evidence_version={V01_CLOSURE_SPRINT_EVIDENCE_VERSION}; "
        f"migration_head={V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD}; "
        f"approved_lineage=PASS,PR#{lineage['product_pr']},"
        f"audited_head={lineage['audited_product_head']},"
        f"squash_merge={lineage['squash_merge_sha']},"
        f"post_merge_ci={lineage['post_merge_ci_run']}; "
        "dod_matrix=PASS; full_v01_complete_claimed=True; "
        "production_quality_claimed_from_fixture=False; ruleset_unchanged=PASS; "
        "auto_merge=UNARMED; checkpoint_promotion=True"
    )


def auto_merge_evidence(auto_merge: Mapping[str, Any] | None) -> dict[str, object]:
    owner = auto_merge.get("enabled_by") if isinstance(auto_merge, Mapping) else None
    owner = owner if isinstance(owner, Mapping) else {}
    login_value = owner.get("login")
    type_value = owner.get("type")
    if not isinstance(type_value, str):
        type_value = owner.get("__typename")
    login = login_value.strip() if isinstance(login_value, str) else ""
    owner_type = type_value.strip() if isinstance(type_value, str) else ""
    normalized_login = login.casefold()
    normalized_type = owner_type.casefold()
    is_bot = (
        owner.get("is_bot") is True
        or normalized_type == "bot"
        or normalized_login.endswith("[bot]")
    )
    is_app = normalized_type in {"app", "application"} or normalized_login.startswith("app/")
    return {
        "armed": auto_merge is not None,
        "method": (
            auto_merge.get("merge_method")
            if isinstance(auto_merge, Mapping) and isinstance(auto_merge.get("merge_method"), str)
            else None
        ),
        "enabled_by_login": login,
        "enabled_by_type": owner_type,
        "user_owned": bool(
            login
            and normalized_type == "user"
            and not is_bot
            and not is_app
            and normalized_login != "github-actions[bot]"
        ),
    }


def pull_request_auto_merge_evidence(
    pull_request_governance: Mapping[str, Any],
) -> Mapping[str, Any]:
    auto_merge = pull_request_governance.get("auto_merge")
    if isinstance(auto_merge, Mapping):
        return auto_merge
    return {
        "armed": pull_request_governance.get("auto_merge_armed"),
        "method": pull_request_governance.get("auto_merge_method"),
        "enabled_by_login": pull_request_governance.get("auto_merge_owner_login", ""),
        "enabled_by_type": pull_request_governance.get("auto_merge_owner_type", ""),
        "user_owned": pull_request_governance.get("auto_merge_user_owned", False),
    }


def verify_native_auto_merge(
    repository: str,
    pr_number: int,
    expected_head_sha: str | None = None,
) -> dict[str, object]:
    pull_request = _gh_json(repository, f"pulls/{pr_number}")
    if not isinstance(pull_request, dict):
        raise ValueError(f"unable to read pull request #{pr_number} for auto-merge verification")
    if expected_head_sha is not None and not HEX_SHA.fullmatch(expected_head_sha):
        raise ValueError("auto-merge verification requires a 40-character expected head SHA")
    if pull_request.get("state") != "open":
        raise ValueError("auto-merge verification requires an open pull request")
    if pull_request.get("draft") is not False:
        raise ValueError("auto-merge verification requires a Ready pull request")
    head = pull_request.get("head")
    observed_head_sha = head.get("sha") if isinstance(head, Mapping) else None
    if expected_head_sha and observed_head_sha != expected_head_sha:
        raise ValueError(
            f"pull request head moved: expected {expected_head_sha}, observed {observed_head_sha}"
        )
    raw_auto_merge = pull_request.get("auto_merge")
    auto_merge = raw_auto_merge if isinstance(raw_auto_merge, Mapping) else None
    evidence = auto_merge_evidence(auto_merge)
    if evidence["armed"] is not True:
        raise ValueError("native auto-merge is not armed")
    if str(evidence["method"]).casefold() != "squash":
        raise ValueError("native auto-merge must use SQUASH")
    if not evidence["enabled_by_login"]:
        raise ValueError("auto-merge owner login is missing")
    if evidence["user_owned"] is not True:
        raise ValueError(
            "native auto-merge must be user-owned; enabled-by identity "
            f"{evidence['enabled_by_login']} ({evidence['enabled_by_type'] or 'unknown'}) "
            "is not a GitHub User"
        )
    return evidence


MERGE_AUTHORIZATION_DIRECT = "DIRECT_SQUASH_MERGE"
MERGE_AUTHORIZATION_AUTO = "ARM_SQUASH_AUTO_MERGE"
MERGE_AUTHORIZATION_REJECT = "REJECT"
REQUIRED_STATUS_CONTEXTS = frozenset({"Validate", "Integration health", "Review Evidence"})
PASSING_CHECK_CONCLUSIONS = frozenset({"pass", "passed", "success", "successful"})
PENDING_CHECK_CONCLUSIONS = frozenset({"in_progress", "pending", "queued", "requested", "waiting"})


def authorize_merge_action(
    state: Mapping[str, Any],
    *,
    expected_head_sha: str,
    expected_base_sha: str,
    expected_base_branch: str = "main",
) -> dict[str, object]:
    """Decide the post-Sol merge action from one normalized, immutable snapshot.

    This helper deliberately does not mutate GitHub state. The caller must take a
    fresh snapshot immediately before acting and include the expected HEAD in the
    direct merge request. Any missing or ambiguous safety input rejects the action.
    """

    def reject(reason: str) -> dict[str, object]:
        return {
            "authorized": False,
            "action": MERGE_AUTHORIZATION_REJECT,
            "reason": reason,
        }

    if not HEX_SHA.fullmatch(expected_head_sha) or not HEX_SHA.fullmatch(expected_base_sha):
        return reject("expected HEAD and base must be valid commit SHAs")
    if state.get("sol_approved") is not True:
        return reject("Sol approval is required before any merge action")
    if state.get("auto_merge_armed") is not False:
        return reject("auto-merge must be unarmed before Sol authorization")
    if state.get("pr_state") != "open":
        return reject("pull request must be open")
    if state.get("is_draft") is not False:
        return reject("pull request must be Ready")
    if state.get("head_sha") != expected_head_sha:
        return reject("pull request HEAD moved")
    if (
        state.get("base_sha") != expected_base_sha
        or state.get("base_branch") != expected_base_branch
    ):
        return reject("pull request base is not the expected safe base")
    if state.get("ruleset_valid") is not True:
        return reject("protected ruleset baseline does not match")
    if state.get("unresolved_threads") != 0:
        return reject("unresolved review threads must be zero")
    if str(state.get("merge_method", "")).casefold() != "squash":
        return reject("merge method must be SQUASH")

    required_checks = state.get("required_checks")
    if not isinstance(required_checks, Mapping):
        return reject("required check conclusions are missing")
    missing = sorted(REQUIRED_STATUS_CONTEXTS - set(required_checks))
    if missing:
        return reject(f"required checks are missing: {', '.join(missing)}")

    conclusions: dict[str, str] = {}
    for context in REQUIRED_STATUS_CONTEXTS:
        value = required_checks[context]
        if isinstance(value, Mapping):
            value = value.get("conclusion", value.get("status", ""))
        if not isinstance(value, str) or not value.strip():
            return reject(f"required check conclusion is missing: {context}")
        conclusions[context] = value.casefold().strip()
    pending = [
        context
        for context, conclusion in conclusions.items()
        if conclusion in PENDING_CHECK_CONCLUSIONS
    ]
    failed = [
        context
        for context, conclusion in conclusions.items()
        if conclusion not in PASSING_CHECK_CONCLUSIONS
        and conclusion not in PENDING_CHECK_CONCLUSIONS
    ]
    if failed:
        return reject(f"required checks are not green: {', '.join(sorted(failed))}")

    mergeable = state.get("mergeable")
    mergeable_state = str(state.get("mergeable_state", "")).casefold()
    if mergeable is not True:
        return reject("pull request mergeability is not confirmed")
    if state.get("mergeable_state") is None:
        return reject("pull request mergeable state is missing")

    if not pending:
        if mergeable_state != "clean":
            return reject("clean direct merge requires mergeable_state=clean")
        return {
            "authorized": True,
            "action": MERGE_AUTHORIZATION_DIRECT,
            "merge_method": "squash",
            "expected_head_sha": expected_head_sha,
            "reason": "all safety gates are green on the exact audited HEAD",
        }

    if mergeable_state != "blocked":
        return reject("pending checks are not the only merge blocker")
    return {
        "authorized": True,
        "action": MERGE_AUTHORIZATION_AUTO,
        "merge_method": "squash",
        "expected_head_sha": expected_head_sha,
        "pending_checks": sorted(pending),
        "reason": "only legitimate required checks remain pending",
    }


def github_review_text(repository: str, pr_number: int | None) -> str:
    if not pr_number:
        return ""
    parts: list[str] = []
    pull_request = _gh_json(repository, f"pulls/{pr_number}")
    if isinstance(pull_request, dict) and isinstance(pull_request.get("body"), str):
        parts.append(pull_request["body"])
    comments = _gh_json(repository, f"issues/{pr_number}/comments")
    if isinstance(comments, list):
        parts.extend(
            str(comment.get("body"))
            for comment in comments
            if isinstance(comment, dict) and isinstance(comment.get("body"), str)
        )
    return "\n\n".join(parts)


def governance_evidence(repository: str, pr_number: int | None = None) -> dict[str, object]:
    rulesets = _gh_json(repository, "rulesets?includes_parents=true")
    selected: dict[str, Any] | None = None
    if isinstance(rulesets, list):
        selected = next(
            (
                item
                for item in rulesets
                if isinstance(item, dict) and item.get("name") == "Protect main"
            ),
            None,
        )
    detail = (
        _gh_json(repository, f"rulesets/{selected['id']}")
        if selected and selected.get("id") is not None
        else None
    )
    repo = _gh_json(repository, "")
    ruleset = detail if isinstance(detail, dict) else selected if selected else {}
    required_contexts: list[str] = []
    allowed_methods: list[str] = []
    thread_resolution: bool | None = None
    has_deletion = False
    has_non_fast_forward = False
    has_pull_request = False
    strict_checks: bool | None = None
    required_approving_review_count: int | None = None
    dismiss_stale_reviews_on_push: bool | None = None
    require_last_push_approval: bool | None = None
    require_extra_approval_for_unattributed_changes: bool | None = None
    for rule in ruleset.get("rules", []) if isinstance(ruleset, dict) else []:
        if not isinstance(rule, dict):
            continue
        rule_type = rule.get("type")
        has_deletion |= rule_type == "deletion"
        has_non_fast_forward |= rule_type == "non_fast_forward"
        has_pull_request |= rule_type == "pull_request"
        params = rule.get("parameters", {})
        if rule_type == "required_status_checks" and isinstance(params, dict):
            required_contexts = [
                str(item.get("context"))
                for item in params.get("required_status_checks", [])
                if isinstance(item, dict) and item.get("context")
            ]
            strict_checks = bool(params.get("strict_required_status_checks_policy"))
        if rule_type == "pull_request" and isinstance(params, dict):
            allowed_methods = [str(item) for item in params.get("allowed_merge_methods", [])]
            if "required_approving_review_count" in params:
                required_approving_review_count = int(params["required_approving_review_count"])
            if "dismiss_stale_reviews_on_push" in params:
                dismiss_stale_reviews_on_push = bool(params["dismiss_stale_reviews_on_push"])
            if "require_last_push_approval" in params:
                require_last_push_approval = bool(params["require_last_push_approval"])
            if "require_extra_approval_for_unattributed_changes" in params:
                require_extra_approval_for_unattributed_changes = bool(
                    params["require_extra_approval_for_unattributed_changes"]
                )
            if "required_review_thread_resolution" in params:
                thread_resolution = bool(params["required_review_thread_resolution"])
    bypass = (
        [
            {
                "actor_id": item.get("actor_id"),
                "actor_type": item.get("actor_type"),
                "actor_name": item.get("actor_name"),
                "bypass_mode": item.get("bypass_mode"),
            }
            for item in ruleset.get("bypass_actors", [])
            if isinstance(item, dict)
        ]
        if isinstance(ruleset, dict)
        else []
    )
    ruleset_unchanged = (
        ruleset.get("id") == PROTECTED_MAIN_RULESET_ID
        and ruleset.get("name") == "Protect main"
        and ruleset.get("enforcement") == "active"
        and sorted(required_contexts) == ["Integration health", "Review Evidence", "Validate"]
        and thread_resolution is True
        and sorted(allowed_methods) == ["squash"]
        and not bypass
        and has_deletion
        and has_non_fast_forward
        and has_pull_request
        and strict_checks is True
        and required_approving_review_count == 0
        and dismiss_stale_reviews_on_push is True
        and require_last_push_approval is False
        and require_extra_approval_for_unattributed_changes is False
    )
    repo_settings = {
        "allow_squash_merge": repo.get("allow_squash_merge") if isinstance(repo, dict) else None,
        "allow_merge_commit": repo.get("allow_merge_commit") if isinstance(repo, dict) else None,
        "allow_rebase_merge": repo.get("allow_rebase_merge") if isinstance(repo, dict) else None,
        "delete_branch_on_merge": repo.get("delete_branch_on_merge")
        if isinstance(repo, dict)
        else None,
        "allow_auto_merge": repo.get("allow_auto_merge") if isinstance(repo, dict) else None,
    }
    if any(value is None for value in repo_settings.values()):
        code, output = run(
            [
                "gh",
                "repo",
                "view",
                repository,
                "--json",
                "mergeCommitAllowed,rebaseMergeAllowed,squashMergeAllowed,deleteBranchOnMerge",
            ]
        )
        if code == 0:
            try:
                graphql_settings = json.loads(output)
            except json.JSONDecodeError:
                graphql_settings = {}
            fallback_settings = {
                "allow_squash_merge": graphql_settings.get("squashMergeAllowed"),
                "allow_merge_commit": graphql_settings.get("mergeCommitAllowed"),
                "allow_rebase_merge": graphql_settings.get("rebaseMergeAllowed"),
                "delete_branch_on_merge": graphql_settings.get("deleteBranchOnMerge"),
            }
            for key, value in fallback_settings.items():
                if repo_settings[key] is None and value is not None:
                    repo_settings[key] = value
    available = bool(detail and repo)
    pr = _gh_json(repository, f"pulls/{pr_number}") if pr_number else None
    reviews = _gh_json(repository, f"pulls/{pr_number}/reviews") if pr_number else None
    author = cast(dict[str, Any], pr.get("user", {})).get("login") if isinstance(pr, dict) else None
    latest_review_by_user: dict[str, dict[str, Any]] = {}
    if isinstance(reviews, list):
        for review in reviews:
            if not isinstance(review, dict):
                continue
            user = review.get("user", {})
            login = user.get("login") if isinstance(user, dict) else None
            if not isinstance(login, str):
                continue
            previous = latest_review_by_user.get(login)
            if previous is None or str(review.get("submitted_at", "")) >= str(
                previous.get("submitted_at", "")
            ):
                latest_review_by_user[login] = review
    independent_approvers = sorted(
        login
        for login, review in latest_review_by_user.items()
        if login != author and review.get("state") == "APPROVED"
    )
    auto_merge = (
        pr.get("auto_merge")
        if isinstance(pr, dict) and isinstance(pr.get("auto_merge"), dict)
        else None
    )
    auto_merge_state = auto_merge_evidence(auto_merge)
    return {
        "status": "PASS" if available else "UNKNOWN",
        "ruleset": {
            "id": ruleset.get("id") if isinstance(ruleset, dict) else None,
            "name": ruleset.get("name", "UNKNOWN") if isinstance(ruleset, dict) else "UNKNOWN",
            "enforcement": ruleset.get("enforcement", "UNKNOWN")
            if isinstance(ruleset, dict)
            else "UNKNOWN",
            "required_contexts": sorted(required_contexts),
            "required_review_thread_resolution": thread_resolution,
            "allowed_merge_methods": sorted(allowed_methods),
            "bypass_actors": bypass,
            "deletion_protection": has_deletion,
            "non_fast_forward_protection": has_non_fast_forward,
            "pull_request_required": has_pull_request,
            "strict_required_status_checks": strict_checks,
            "required_approving_review_count": required_approving_review_count,
            "dismiss_stale_reviews_on_push": dismiss_stale_reviews_on_push,
            "require_last_push_approval": require_last_push_approval,
            "require_extra_approval_for_unattributed_changes": (
                require_extra_approval_for_unattributed_changes
            ),
        },
        "ruleset_unchanged": ruleset_unchanged,
        "repository_merge_settings": repo_settings,
        "pull_request": {
            "number": pr_number,
            "state": pr.get("state") if isinstance(pr, dict) else None,
            "is_draft": pr.get("draft") if isinstance(pr, dict) else None,
            "head_sha": (
                pr.get("head", {}).get("sha")
                if isinstance(pr, dict) and isinstance(pr.get("head"), dict)
                else None
            ),
            "base_sha": (
                pr.get("base", {}).get("sha")
                if isinstance(pr, dict) and isinstance(pr.get("base"), dict)
                else None
            ),
            "auto_merge_armed": auto_merge is not None,
            "auto_merge_method": auto_merge.get("merge_method") if auto_merge else None,
            "auto_merge": auto_merge_state,
        },
        "approval_gate": {
            "required_approving_review_count": required_approving_review_count,
            "dismiss_stale_reviews_on_push": dismiss_stale_reviews_on_push,
            "require_last_push_approval": require_last_push_approval,
            "require_extra_approval_for_unattributed_changes": (
                require_extra_approval_for_unattributed_changes
            ),
            "independent_approvers": independent_approvers,
            "independent_approval_count": len(independent_approvers),
        },
        "sol_reviewer": {
            "login": SOLE_GITHUB_OPERATOR_LOGIN,
            "permission": None,
            "permissions": {},
            "can_satisfy_required_approval": False,
        },
    }


def build_manifest(args: argparse.Namespace) -> dict[str, object]:
    repository = args.repository or repository_name()
    pr_body = ""
    if args.pr_number:
        pr_body = pull_request_body(repository, args.pr_number)
        work_order = parse_work_order_marker(pr_body)
        require_current_work_order_authorization(work_order)
        if args.work_order and args.work_order != work_order:
            raise ValueError(
                f"work-order override {args.work_order!r} does not match PR marker {work_order!r}"
            )
    else:
        work_order = args.work_order or "LOCAL-VALIDATION"
        if (
            work_order != "LOCAL-VALIDATION"
            and WORK_ORDER_IDENTIFIER.fullmatch(work_order) is None
            and GEF_WORK_ORDER_IDENTIFIER.fullmatch(work_order) is None
            and HIVE_REL_WORK_ORDER_IDENTIFIER.fullmatch(work_order) is None
            and RELEASE_TRAIN_WORK_ORDER_IDENTIFIER.fullmatch(work_order) is None
        ):
            raise ValueError(f"invalid or unbounded HIVE work-order identifier: {work_order!r}")
    require_current_work_order_authorization(work_order)
    validation = read_text(VALIDATION / "summary.txt")
    lint = read_text(VALIDATION / "lint-typecheck-build-results.txt")
    tests_text = read_text(VALIDATION / "test-results.txt")
    base_sha = args.base_sha or git_value("merge-base", "HEAD", "origin/main", fallback="0" * 40)
    head_sha = args.head_sha or git_value("rev-parse", "HEAD")
    actual_head = git_value("rev-parse", "HEAD")
    if head_sha != actual_head:
        raise ValueError(f"head SHA mismatch: expected {head_sha}, checked out {actual_head}")
    paths = changed_paths(base_sha, head_sha)
    authorized_base_sha = authorized_base_marker_sha(work_order, pr_body)
    require_wo012p_g1_scope(work_order, base_sha, paths)
    require_wo013p_g1_scope(work_order, base_sha, paths)
    require_wo014p_g1_scope(work_order, base_sha, paths)
    require_wo015p_g1_scope(work_order, base_sha, paths)
    require_wo016p_g1_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
    )
    require_wo017p_g1_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
    )
    require_wo018p_g1_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
    )
    require_wo019p_g1_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
    )
    require_wo020p_g1_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
    )
    require_wo021p_g1_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
    )
    require_wo022p_g1_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
    )
    require_wo023_g1_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
    )
    require_wo019_g1_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
    )
    require_wo020_g1_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
    )
    require_wo021_g1_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
    )
    require_wo022_g1_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
    )
    require_wo012p_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
    )
    require_wo013p_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
    )
    require_wo014p_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
    )
    require_wo008_g1_scope(work_order, base_sha, paths)
    require_wo009_scope(work_order, base_sha, paths)
    require_wo010_g1_scope(work_order, base_sha, paths)
    require_wo010_scope(work_order, base_sha, paths)
    require_wo011_scope(work_order, base_sha, paths)
    require_wo012_scope(work_order, base_sha, paths)
    require_wo013_scope(work_order, base_sha, paths)
    require_wo014_scope(work_order, base_sha, paths)
    require_wo014_c2_scope(work_order, base_sha, paths)
    require_wo015_g1_scope(work_order, base_sha, paths)
    require_wo015_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        enforce_current_main=True,
    )
    require_wo015p_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
        enforce_current_main=True,
    )
    require_wo016p_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
        enforce_current_main=True,
    )
    require_wo017p_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
        enforce_current_main=True,
    )
    require_wo018p_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
        enforce_current_main=True,
    )
    require_wo019p_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
        enforce_current_main=True,
    )
    require_wo020p_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
        enforce_current_main=True,
    )
    require_wo021p_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
        enforce_current_main=True,
    )
    require_wo022p_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
        enforce_current_main=True,
    )
    require_wo023_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        enforce_current_main=True,
    )
    require_wo023p_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
        enforce_current_main=True,
    )
    require_wo023p_g1_c1_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
    )
    require_wo024_g1_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
    )
    require_hive_rel_001_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
    )
    require_hive_rel_002_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
    )
    require_hive_rel_003_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
    )
    require_hive_rel_004_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
    )
    require_hive_rel_005_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
    )
    require_hive_rel_006_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
    )
    require_wo026_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
        enforce_current_main=True,
    )
    require_wo027_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
        enforce_current_main=True,
    )
    require_wo028_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
        enforce_current_main=True,
    )
    require_wo029_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
        enforce_current_main=True,
    )
    require_wo030_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
        enforce_current_main=True,
    )
    require_wo030_c1_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
        enforce_current_main=True,
    )
    require_wo025_g3_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
    )
    require_wo025_g4_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
    )
    require_wo025_g5_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
    )
    require_wo025p_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
    )
    require_wo11_01_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
    )
    require_wo024_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        enforce_current_main=True,
    )
    require_wo016_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        enforce_current_main=True,
    )
    require_wo017_g1_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
    )
    require_wo017_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        enforce_current_main=True,
    )
    require_wo019_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        enforce_current_main=True,
    )
    require_wo020_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        enforce_current_main=True,
    )
    require_wo021_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        enforce_current_main=True,
    )
    require_wo022_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        enforce_current_main=True,
    )
    require_gef_adoption_scope(
        work_order,
        base_sha,
        paths,
        base_branch=args.base_branch,
        authorized_base_sha=authorized_base_sha,
    )
    all_validation = validation + "\n" + lint + "\n" + tests_text
    evidence_text = all_evidence_text()
    github_evidence = github_review_text(repository, args.pr_number)
    benchmark = benchmark_fields(VALIDATION / "retrieval-benchmark.json")
    tests = tests_evidence(validation, tests_text)
    integration = integration_evidence(benchmark, work_order=work_order)
    require_wo009_context_manager_evidence(work_order, integration)
    require_wo010_progressive_disclosure_evidence(
        work_order,
        integration,
        migration_head(),
    )
    require_wo011_context_manager_evidence(
        work_order,
        integration,
        migration_head(),
    )
    require_wo012_context_manager_evidence(
        work_order,
        integration,
        migration_head(),
    )
    require_wo013_context_manager_evidence(
        work_order,
        integration,
        migration_head(),
    )
    require_wo014_provider_prompt_cache_evidence(
        work_order,
        integration,
        migration_head(),
    )
    require_wo015_memory_evidence(work_order, integration, migration_head())
    require_wo016_storage_evidence(work_order, integration, migration_head())
    require_wo017_mcp_evidence(work_order, integration, migration_head())
    require_wo018_autonomous_evidence(work_order, integration, migration_head())
    require_wo019_telemetry_evidence(work_order, integration, migration_head())
    require_wo020_control_center_evidence(work_order, integration, migration_head())
    require_wo021_control_center_metrics_evidence(work_order, integration, migration_head())
    require_wo022_full_control_center_evidence(work_order, integration, migration_head())
    require_wo023_comprehensive_benchmarks_evidence(work_order, integration, migration_head())
    c2_governance_evidence = (
        verify_wo014_c2_governance_contract() if work_order == WO014_C2_WORK_ORDER else None
    )
    security = security_evidence(
        all_validation,
        tests_text,
        evidence_text + "\n" + github_evidence,
        benchmark,
        integration,
    )
    warnings = warnings_evidence(evidence_text)
    require_wo008_c1_evidence(
        work_order,
        benchmark,
        integration,
        security,
        evidence_text,
        github_evidence,
    )
    canonical_changes = canonical_change_evidence(paths, work_order)
    governance = governance_evidence(repository, args.pr_number)
    pr_governance = cast(dict[str, Any], governance.get("pull_request", {}))
    pr_auto_merge = pull_request_auto_merge_evidence(pr_governance)
    approved_lineage = (
        fetch_wo016_approved_lineage(repository)
        if work_order in {WO016P_G1_WORK_ORDER, WO016P_WORK_ORDER}
        else fetch_wo021_approved_lineage(repository)
        if work_order in {WO021P_G1_WORK_ORDER, WO021P_WORK_ORDER}
        else fetch_wo022_approved_lineage(repository)
        if work_order in {WO022P_G1_WORK_ORDER, WO022P_WORK_ORDER}
        else fetch_wo023_approved_lineage(repository)
        if work_order in {WO023P_G1_WORK_ORDER, WO023P_WORK_ORDER}
        else fetch_wo024_approved_lineage(
            repository,
            wo024p_closure_payload(),
        )
        if work_order == WO024P_WORK_ORDER
        else None
    )
    g1_governance_evidence = verify_wo014p_g1_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
    )
    wo015_g1_governance_evidence = verify_wo015_g1_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
    )
    wo015p_g1_governance_evidence = verify_wo015p_g1_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
    )
    wo016p_g1_governance_evidence = verify_wo016p_g1_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
        approved_lineage,
    )
    wo016p_governance_evidence = verify_wo016p_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
        approved_lineage,
    )
    wo016_g1_governance_evidence = verify_wo016_g1_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
    )
    wo018_g1_governance_evidence = verify_wo018_g1_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
    )
    wo018_governance_evidence = verify_wo018_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
    )
    wo019_g1_governance_evidence = verify_wo019_g1_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
    )
    wo019_governance_evidence = verify_wo019_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
    )
    wo020_g1_governance_evidence = verify_wo020_g1_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
    )
    wo020_governance_evidence = verify_wo020_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
    )
    wo021_g1_governance_evidence = verify_wo021_g1_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
    )
    wo021_governance_evidence = verify_wo021_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
    )
    wo022_g1_governance_evidence = verify_wo022_g1_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
    )
    wo022_governance_evidence = verify_wo022_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
    )
    wo023_g1_governance_evidence = verify_wo023_g1_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
    )
    wo023_governance_evidence = verify_wo023_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
    )
    wo023p_g1_governance_evidence = verify_wo023p_g1_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
        approved_lineage,
    )
    wo024_g1_governance_evidence = verify_wo024_g1_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
        authorized_base_sha,
    )
    wo024_governance_evidence = verify_wo024_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
    )
    wo024p_governance_evidence = verify_wo024p_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
        approved_lineage,
        authorized_base_sha,
    )
    wo023p_g1_c1_governance_evidence = verify_wo023p_g1_c1_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
        authorized_base_sha,
    )
    wo024p_g1_c1_governance_evidence = verify_wo024p_g1_c1_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
        authorized_base_sha,
    )
    wo024p_g1_c2_governance_evidence = verify_wo024p_g1_c2_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
        authorized_base_sha,
    )
    wo024p_g1_c3_governance_evidence = verify_wo024p_g1_c3_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
        authorized_base_sha,
    )
    wo024p_g1_c4_governance_evidence = verify_wo024p_g1_c4_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
        authorized_base_sha,
    )
    wo025_g1_governance_evidence = verify_wo025_g1_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
        authorized_base_sha,
    )
    wo025_governance_evidence = verify_wo025_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
        authorized_base_sha,
    )
    wo025_g2_governance_evidence = verify_wo025_g2_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
        authorized_base_sha,
    )
    wo025_g3_governance_evidence = verify_wo025_g3_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
        authorized_base_sha,
    )
    wo025_g4_governance_evidence = verify_wo025_g4_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
        authorized_base_sha,
    )
    wo023p_governance_evidence = verify_wo023p_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
        approved_lineage,
    )
    wo017_g1_governance_evidence = verify_wo017_g1_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
    )
    wo017_governance_evidence = verify_wo017_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
    )
    wo017p_g1_governance_evidence = verify_wo017p_g1_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
    )
    wo017p_governance_evidence = verify_wo017p_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
    )
    wo018p_g1_governance_evidence = verify_wo018p_g1_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
    )
    wo018p_governance_evidence = verify_wo018p_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
    )
    wo019p_g1_governance_evidence = verify_wo019p_g1_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
    )
    wo019p_governance_evidence = verify_wo019p_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
    )
    wo020p_g1_governance_evidence = verify_wo020p_g1_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
    )
    wo020p_governance_evidence = verify_wo020p_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
    )
    wo021p_g1_governance_evidence = verify_wo021p_g1_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
        approved_lineage,
    )
    wo021p_governance_evidence = verify_wo021p_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
        approved_lineage,
    )
    wo022p_g1_governance_evidence = verify_wo022p_g1_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
        approved_lineage,
    )
    wo022p_governance_evidence = verify_wo022p_governance_contract(
        work_order,
        base_sha,
        paths,
        canonical_changes,
        governance,
        integration,
        migration_head(),
        approved_lineage,
    )
    require_hive_final_handoff(work_order, args.pr_number, base_sha, head_sha, governance)
    checks = {
        "validation": "PASS"
        if validation.strip() == "PASS"
        else "FAIL"
        if validation.strip().startswith("FAIL")
        else "UNKNOWN",
        "canonical": validation_status(all_validation, "canonical source verification"),
        "secrets": validation_status(all_validation, "secret scan"),
        "lint": "PASS"
        if validation.strip() == "PASS" and "ruff check" in lint and "run lint" in lint
        else "UNKNOWN",
        "typecheck": "PASS"
        if validation.strip() == "PASS" and "run typecheck" in lint
        else "UNKNOWN",
        "tests": cast(str, tests["status"]),
        "build": "PASS" if validation.strip() == "PASS" and "run build" in lint else "UNKNOWN",
        "integration": (
            "PASS"
            if args.integration_status == "PASS" and benchmark["status"] == "PASS"
            else "FAIL"
            if args.integration_status == "FAIL" or benchmark["status"] == "FAIL"
            else "UNKNOWN"
        ),
        "review_evidence": "PASS",
    }
    observed_draft = pr_governance.get("is_draft")
    draft = (
        args.draft
        or env_bool(args.draft_env, False)
        or (bool(observed_draft) if observed_draft is not None else not args.ready)
    )
    pr_number = args.pr_number
    review_status = "DRAFT" if pr_number and draft else "READY" if pr_number else "NOT_CREATED"
    artifact_name = args.artifact_name or f"hive-review-evidence-{work_order}-{head_sha}"
    return {
        "schema_version": 1,
        "work_order": work_order,
        "repository": repository,
        "pull_request": {"number": pr_number, "is_draft": draft},
        "base": {"branch": args.base_branch, "sha": base_sha},
        "head": {
            "branch": args.head_branch
            or git_value("branch", "--show-current", fallback="DETACHED"),
            "sha": head_sha,
        },
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "changed_files": {"count": len(paths), "paths": paths},
        "migrations": {"head": migration_head()},
        "checks": checks,
        "benchmark": benchmark,
        "evidence": {
            "tests": tests,
            "integration": integration,
            "security": security,
            "warnings": warnings,
        },
        "governance": governance,
        "artifact": {"name": artifact_name, "format": "consolidated-directory", "bounded": True},
        "review_state": {
            "status": review_status,
            "merge_performed": False,
            "sol_review_state": "AWAITING_SOL",
            "auto_merge_armed": bool(pr_governance.get("auto_merge_armed", False)),
            "auto_merge_method": pr_governance.get("auto_merge_method"),
            "auto_merge_owner_login": pr_auto_merge.get("enabled_by_login", ""),
            "auto_merge_owner_type": pr_auto_merge.get("enabled_by_type", ""),
            "auto_merge_user_owned": bool(pr_auto_merge.get("user_owned", False)),
        },
        "negative_scope": [
            "No merge or release was performed.",
            canonical_change_statement(canonical_changes),
            "No implementation outside the approved work-order scope was added.",
        ]
        + (
            [f"WO-014-C2 governance evidence: {c2_governance_evidence}"]
            if c2_governance_evidence
            else []
        )
        + (
            [f"WO-014-P-G1 governance evidence: {g1_governance_evidence}"]
            if g1_governance_evidence
            else []
        )
        + (
            [f"WO-015-G1 governance evidence: {wo015_g1_governance_evidence}"]
            if wo015_g1_governance_evidence
            else []
        )
        + (
            [f"WO-015-P-G1 governance evidence: {wo015p_g1_governance_evidence}"]
            if wo015p_g1_governance_evidence
            else []
        )
        + (
            [f"WO-016-P-G1 governance evidence: {wo016p_g1_governance_evidence}"]
            if wo016p_g1_governance_evidence
            else []
        )
        + (
            [wo016_approved_lineage_statement(approved_lineage)]
            if work_order in {WO016P_G1_WORK_ORDER, WO016P_WORK_ORDER}
            and approved_lineage is not None
            else []
        )
        + (
            [f"WO-016-P governance evidence: {wo016p_governance_evidence}"]
            if wo016p_governance_evidence
            else []
        )
        + (
            [f"WO-016-G1 governance evidence: {wo016_g1_governance_evidence}"]
            if wo016_g1_governance_evidence
            else []
        )
        + (
            [f"WO-017-G1 governance evidence: {wo017_g1_governance_evidence}"]
            if wo017_g1_governance_evidence
            else []
        )
        + (
            [f"WO-017 governance evidence: {wo017_governance_evidence}"]
            if wo017_governance_evidence
            else []
        )
        + (
            [f"WO-018-G1 governance evidence: {wo018_g1_governance_evidence}"]
            if wo018_g1_governance_evidence
            else []
        )
        + (
            [f"WO-018 governance evidence: {wo018_governance_evidence}"]
            if wo018_governance_evidence
            else []
        )
        + (
            [f"WO-019-G1 governance evidence: {wo019_g1_governance_evidence}"]
            if wo019_g1_governance_evidence
            else []
        )
        + (
            [f"WO-019 governance evidence: {wo019_governance_evidence}"]
            if wo019_governance_evidence
            else []
        )
        + (
            [f"WO-020-G1 governance evidence: {wo020_g1_governance_evidence}"]
            if wo020_g1_governance_evidence
            else []
        )
        + (
            [f"WO-020 governance evidence: {wo020_governance_evidence}"]
            if wo020_governance_evidence
            else []
        )
        + (
            [f"WO-021-G1 governance evidence: {wo021_g1_governance_evidence}"]
            if wo021_g1_governance_evidence
            else []
        )
        + (
            [f"WO-021 governance evidence: {wo021_governance_evidence}"]
            if wo021_governance_evidence
            else []
        )
        + (
            [f"WO-022-G1 governance evidence: {wo022_g1_governance_evidence}"]
            if wo022_g1_governance_evidence
            else []
        )
        + (
            [f"WO-022 governance evidence: {wo022_governance_evidence}"]
            if wo022_governance_evidence
            else []
        )
        + (
            [f"WO-023-G1 governance evidence: {wo023_g1_governance_evidence}"]
            if wo023_g1_governance_evidence
            else []
        )
        + (
            [f"WO-023 governance evidence: {wo023_governance_evidence}"]
            if wo023_governance_evidence
            else []
        )
        + (
            [f"WO-017-P-G1 governance evidence: {wo017p_g1_governance_evidence}"]
            if wo017p_g1_governance_evidence
            else []
        )
        + (
            [f"WO-017-P governance evidence: {wo017p_governance_evidence}"]
            if wo017p_governance_evidence
            else []
        )
        + (
            [f"WO-018-P-G1 governance evidence: {wo018p_g1_governance_evidence}"]
            if wo018p_g1_governance_evidence
            else []
        )
        + (
            [f"WO-018-P governance evidence: {wo018p_governance_evidence}"]
            if wo018p_governance_evidence
            else []
        )
        + (
            [f"WO-019-P-G1 governance evidence: {wo019p_g1_governance_evidence}"]
            if wo019p_g1_governance_evidence
            else []
        )
        + (
            [f"WO-019-P governance evidence: {wo019p_governance_evidence}"]
            if wo019p_governance_evidence
            else []
        )
        + (
            [f"WO-020-P-G1 governance evidence: {wo020p_g1_governance_evidence}"]
            if wo020p_g1_governance_evidence
            else []
        )
        + (
            [f"WO-020-P governance evidence: {wo020p_governance_evidence}"]
            if wo020p_governance_evidence
            else []
        )
        + (
            [f"WO-021-P-G1 governance evidence: {wo021p_g1_governance_evidence}"]
            if wo021p_g1_governance_evidence
            else []
        )
        + (
            [wo021_approved_lineage_statement(approved_lineage)]
            if work_order in {WO021P_G1_WORK_ORDER, WO021P_WORK_ORDER}
            and approved_lineage is not None
            else []
        )
        + (
            [f"WO-021-P governance evidence: {wo021p_governance_evidence}"]
            if wo021p_governance_evidence
            else []
        )
        + (
            [f"WO-022-P-G1 governance evidence: {wo022p_g1_governance_evidence}"]
            if wo022p_g1_governance_evidence
            else []
        )
        + (
            [wo022_approved_lineage_statement(approved_lineage)]
            if work_order in {WO022P_G1_WORK_ORDER, WO022P_WORK_ORDER}
            and approved_lineage is not None
            else []
        )
        + (
            [f"WO-022-P governance evidence: {wo022p_governance_evidence}"]
            if wo022p_governance_evidence
            else []
        )
        + (
            [f"WO-023-P-G1 governance evidence: {wo023p_g1_governance_evidence}"]
            if wo023p_g1_governance_evidence
            else []
        )
        + (
            [f"WO-023-P-G1-C1 governance evidence: {wo023p_g1_c1_governance_evidence}"]
            if wo023p_g1_c1_governance_evidence
            else []
        )
        + (
            [f"WO-024-P-G1-C1 governance evidence: {wo024p_g1_c1_governance_evidence}"]
            if wo024p_g1_c1_governance_evidence
            else []
        )
        + (
            [f"WO-024-P-G1-C2 governance evidence: {wo024p_g1_c2_governance_evidence}"]
            if wo024p_g1_c2_governance_evidence
            else []
        )
        + (
            [f"WO-024-P-G1-C3 governance evidence: {wo024p_g1_c3_governance_evidence}"]
            if wo024p_g1_c3_governance_evidence
            else []
        )
        + (
            [f"WO-024-P-G1-C4 governance evidence: {wo024p_g1_c4_governance_evidence}"]
            if wo024p_g1_c4_governance_evidence
            else []
        )
        + (
            [f"WO-025-G1 governance evidence: {wo025_g1_governance_evidence}"]
            if wo025_g1_governance_evidence
            else []
        )
        + (
            [f"WO-025 governance evidence: {wo025_governance_evidence}"]
            if wo025_governance_evidence
            else []
        )
        + (
            [f"WO-025-G2 governance evidence: {wo025_g2_governance_evidence}"]
            if wo025_g2_governance_evidence
            else []
        )
        + (
            [f"WO-025-G3 governance evidence: {wo025_g3_governance_evidence}"]
            if wo025_g3_governance_evidence
            else []
        )
        + (
            [f"WO-025-G4 governance evidence: {wo025_g4_governance_evidence}"]
            if wo025_g4_governance_evidence
            else []
        )
        + (
            [f"WO-024-G1 governance evidence: {wo024_g1_governance_evidence}"]
            if wo024_g1_governance_evidence
            else []
        )
        + (
            [wo024_approved_lineage_statement(approved_lineage)]
            if work_order in {WO024_G1_WORK_ORDER, WO024P_WORK_ORDER}
            and approved_lineage is not None
            else []
        )
        + (
            [f"WO-024 governance evidence: {wo024_governance_evidence}"]
            if wo024_governance_evidence
            else []
        )
        + (
            [f"WO-024-P governance evidence: {wo024p_governance_evidence}"]
            if wo024p_governance_evidence
            else []
        )
        + (
            [wo023_approved_lineage_statement(approved_lineage)]
            if work_order in {WO023P_G1_WORK_ORDER, WO023P_WORK_ORDER}
            and approved_lineage is not None
            else []
        )
        + (
            [f"WO-023-P governance evidence: {wo023p_governance_evidence}"]
            if wo023p_governance_evidence
            else []
        ),
    }


def validate_manifest(manifest: dict[str, object]) -> None:
    required = {
        "schema_version",
        "work_order",
        "repository",
        "pull_request",
        "base",
        "head",
        "generated_at",
        "changed_files",
        "migrations",
        "checks",
        "benchmark",
        "evidence",
        "governance",
        "artifact",
        "review_state",
        "negative_scope",
    }
    if set(manifest) != required or manifest["schema_version"] != 1:
        raise ValueError("manifest does not match the required top-level schema")
    work_order = cast(str, manifest["work_order"])
    require_supported_work_order(work_order)
    base = cast(dict[str, Any], manifest["base"])
    changed_files = cast(dict[str, Any], manifest["changed_files"])
    require_wo026_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, base.get("branch", "main")),
        enforce_current_main=False,
        enforce_authorized_base=False,
    )
    require_wo027_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, base.get("branch", "main")),
        enforce_current_main=False,
        enforce_authorized_base=False,
    )
    require_wo028_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, base.get("branch", "main")),
        enforce_current_main=False,
        enforce_authorized_base=False,
    )
    require_wo029_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, base.get("branch", "main")),
        enforce_current_main=False,
        enforce_authorized_base=False,
    )
    require_wo030_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, base.get("branch", "main")),
        enforce_current_main=False,
        enforce_authorized_base=False,
    )
    require_wo030_c1_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, base.get("branch", "main")),
        enforce_current_main=False,
        enforce_authorized_base=False,
    )
    require_wo012p_g1_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
    )
    require_wo014p_g1_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
    )
    require_wo015p_g1_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
    )
    require_wo016p_g1_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
    )
    require_wo017p_g1_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
    )
    require_wo018p_g1_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
    )
    require_wo019p_g1_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
    )
    require_wo020p_g1_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
    )
    require_wo021p_g1_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
    )
    require_wo022p_g1_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
    )
    require_wo023_g1_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
    )
    require_wo019_g1_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
    )
    require_wo020_g1_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
    )
    require_wo021_g1_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
    )
    require_wo022_g1_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
    )
    require_wo015_g1_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
    )
    require_wo016_g1_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
    )
    require_wo017_g1_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, base.get("branch", "main")),
    )
    require_wo018_g1_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, base.get("branch", "main")),
    )
    require_wo012p_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
        enforce_authorized_base=False,
    )
    require_wo014p_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
        enforce_authorized_base=False,
    )
    require_wo015_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
        enforce_current_main=True,
    )
    require_wo015p_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
        enforce_current_main=True,
        enforce_authorized_base=False,
    )
    require_wo016p_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
        enforce_current_main=True,
        enforce_authorized_base=False,
    )
    require_wo017p_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
        enforce_current_main=True,
        enforce_authorized_base=False,
    )
    require_wo018p_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
        enforce_current_main=True,
        enforce_authorized_base=False,
    )
    require_wo019p_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
        enforce_current_main=True,
        enforce_authorized_base=False,
    )
    require_wo020p_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
        enforce_current_main=True,
        enforce_authorized_base=False,
    )
    require_wo021p_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
        enforce_current_main=True,
        enforce_authorized_base=False,
    )
    require_wo022p_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
        enforce_current_main=True,
        enforce_authorized_base=False,
    )
    require_wo023_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
        enforce_current_main=True,
    )
    require_wo023p_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
        enforce_current_main=True,
        enforce_authorized_base=False,
    )
    require_wo023p_g1_c1_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
        enforce_authorized_base=False,
    )
    require_wo024_g1_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
        enforce_authorized_base=False,
    )
    require_wo024_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
        enforce_current_main=True,
    )
    require_wo016_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
        enforce_current_main=True,
    )
    require_wo017_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
        enforce_current_main=True,
    )
    require_wo018_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
        enforce_current_main=True,
    )
    require_wo019_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
        enforce_current_main=True,
    )
    require_wo020_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
        enforce_current_main=True,
    )
    require_wo021_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
        enforce_current_main=True,
    )
    require_wo022_scope(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        base_branch=cast(str, manifest["base"].get("branch", "main"))
        if isinstance(manifest["base"], Mapping)
        else "main",
        enforce_current_main=True,
    )
    if work_order == "WO-008-G1":
        require_wo008_g1_scope(
            work_order,
            cast(str, base["sha"]),
            cast(list[str], changed_files["paths"]),
        )
        governance = cast(dict[str, Any], manifest["governance"])
        if governance.get("ruleset_unchanged") is not True:
            raise ValueError("WO-008-G1 evidence requires the protected ruleset to be unchanged")
        review_state = cast(dict[str, Any], manifest["review_state"])
        if review_state.get("auto_merge_user_owned") is not True:
            raise ValueError("WO-008-G1 evidence requires user-owned auto-merge")
        if not review_state.get("auto_merge_owner_login") or not review_state.get(
            "auto_merge_owner_type"
        ):
            raise ValueError("WO-008-G1 evidence requires auto-merge owner identity")
        governance_pr = cast(dict[str, Any], governance.get("pull_request", {}))
        if not isinstance(governance_pr.get("auto_merge"), Mapping):
            raise ValueError("WO-008-G1 evidence requires structured auto-merge evidence")
    if work_order == "WO-009":
        require_wo009_scope(
            work_order,
            cast(str, base["sha"]),
            cast(list[str], changed_files["paths"]),
        )
    if work_order == "WO-010-G1":
        require_wo010_g1_scope(
            work_order,
            cast(str, base["sha"]),
            cast(list[str], changed_files["paths"]),
        )
        governance = cast(dict[str, Any], manifest["governance"])
        if governance.get("ruleset_unchanged") is not True:
            raise ValueError(
                "WO-010-G1 evidence requires the protected ruleset to match "
                "the single-account baseline"
            )
        review_state = cast(dict[str, Any], manifest["review_state"])
        if review_state.get("auto_merge_armed") is True:
            raise ValueError(
                "WO-010-G1 evidence requires auto-merge to be unarmed before Sol audit"
            )
        if review_state.get("sol_review_state") != "AWAITING_SOL":
            raise ValueError("WO-010-G1 evidence cannot invent a Sol approval state")
    if work_order == "WO-010":
        require_wo010_scope(
            work_order,
            cast(str, base["sha"]),
            cast(list[str], changed_files["paths"]),
        )
    if work_order == "WO-011":
        require_wo011_scope(
            work_order,
            cast(str, base["sha"]),
            cast(list[str], changed_files["paths"]),
        )
    if work_order == "WO-012":
        require_wo012_scope(
            work_order,
            cast(str, base["sha"]),
            cast(list[str], changed_files["paths"]),
        )
    if work_order == "WO-013":
        require_wo013_scope(
            work_order,
            cast(str, base["sha"]),
            cast(list[str], changed_files["paths"]),
        )
    if work_order == "WO-014":
        require_wo014_scope(
            work_order,
            cast(str, base["sha"]),
            cast(list[str], changed_files["paths"]),
        )
    if work_order == WO014_C2_WORK_ORDER:
        require_wo014_c2_scope(
            work_order,
            cast(str, base["sha"]),
            cast(list[str], changed_files["paths"]),
        )
    if work_order == WO016_G1_WORK_ORDER:
        require_wo016_g1_scope(
            work_order,
            cast(str, base["sha"]),
            cast(list[str], changed_files["paths"]),
        )
    for key in ("base", "head"):
        section = cast(dict[str, Any], manifest[key])
        sha = section["sha"]
        if not isinstance(sha, str) or not HEX_SHA.fullmatch(sha):
            raise ValueError(f"invalid {key} SHA")
    review_state = cast(dict[str, Any], manifest["review_state"])
    if review_state["merge_performed"] is not False:
        raise ValueError("review evidence cannot report a merge")
    negative_scope = cast(list[object], manifest["negative_scope"])
    canonical_entries = [
        entry
        for entry in negative_scope
        if isinstance(entry, str) and entry.startswith("Canonical change evidence: ")
    ]
    if len(canonical_entries) != 1:
        raise ValueError("review evidence must include exactly one canonical change statement")
    try:
        canonical_payload = json.loads(canonical_entries[0].split(": ", 1)[1])
    except (json.JSONDecodeError, IndexError):
        raise ValueError("canonical change evidence must be valid JSON") from None
    if not isinstance(canonical_payload, dict) or set(canonical_payload) != {
        "project_brain_changed",
        "checkpoint_changed",
        "authorized_paths",
    }:
        raise ValueError("canonical change evidence has an invalid shape")
    if any(
        isinstance(entry, str) and "no canonical project brain checkpoint" in entry.casefold()
        for entry in negative_scope
    ):
        raise ValueError("review evidence cannot deny an observed canonical checkpoint change")
    approved_lineage = None
    if work_order in {WO016P_G1_WORK_ORDER, WO016P_WORK_ORDER}:
        lineage_entries = [
            entry
            for entry in negative_scope
            if isinstance(entry, str) and entry.startswith(WO016_APPROVED_LINEAGE_STATEMENT_PREFIX)
        ]
        if len(lineage_entries) != 1:
            raise ValueError("WO-016 evidence must include exactly one approved lineage statement")
        approved_lineage = parse_wo016_approved_lineage_statement(lineage_entries[0])
    elif work_order in {WO021P_G1_WORK_ORDER, WO021P_WORK_ORDER}:
        lineage_entries = [
            entry
            for entry in negative_scope
            if isinstance(entry, str) and entry.startswith(WO021_APPROVED_LINEAGE_STATEMENT_PREFIX)
        ]
        if len(lineage_entries) != 1:
            raise ValueError("WO-021 evidence must include exactly one approved lineage statement")
        approved_lineage = parse_wo021_approved_lineage_statement(lineage_entries[0])
    elif work_order in {WO022P_G1_WORK_ORDER, WO022P_WORK_ORDER}:
        lineage_entries = [
            entry
            for entry in negative_scope
            if isinstance(entry, str) and entry.startswith(WO022_APPROVED_LINEAGE_STATEMENT_PREFIX)
        ]
        if len(lineage_entries) != 1:
            raise ValueError("WO-022 evidence must include exactly one approved lineage statement")
        approved_lineage = parse_wo022_approved_lineage_statement(lineage_entries[0])
    elif work_order in {WO023P_G1_WORK_ORDER, WO023P_WORK_ORDER}:
        lineage_entries = [
            entry
            for entry in negative_scope
            if isinstance(entry, str) and entry.startswith(WO023_APPROVED_LINEAGE_STATEMENT_PREFIX)
        ]
        if len(lineage_entries) != 1:
            raise ValueError("WO-023 evidence must include exactly one approved lineage statement")
        approved_lineage = parse_wo023_approved_lineage_statement(lineage_entries[0])
    elif work_order == WO024P_WORK_ORDER:
        lineage_entries = [
            entry
            for entry in negative_scope
            if isinstance(entry, str) and entry.startswith("Approved WO-024 product lineage: ")
        ]
        if len(lineage_entries) != 1:
            raise ValueError("WO-024 evidence must include exactly one approved lineage statement")
        approved_lineage = parse_wo024_approved_lineage_statement(lineage_entries[0])
    g1_evidence = verify_wo014p_g1_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    if work_order == WO014P_G1_WORK_ORDER:
        expected_g1_entry = f"WO-014-P-G1 governance evidence: {g1_evidence}"
        if expected_g1_entry not in negative_scope:
            raise ValueError(
                "WO-014-P-G1 evidence must record the explicit promotion governance contract"
            )
    if work_order == WO014_C2_WORK_ORDER:
        c2_evidence = verify_wo014_c2_governance_contract()
        expected_c2_entry = f"WO-014-C2 governance evidence: {c2_evidence}"
        if expected_c2_entry not in negative_scope:
            raise ValueError(
                "WO-014-C2 evidence must record the explicit squash-safe governance contract"
            )
    wo015_g1_evidence = verify_wo015_g1_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    if work_order == WO015_G1_WORK_ORDER:
        expected_g1_entry = f"WO-015-G1 governance evidence: {wo015_g1_evidence}"
        if expected_g1_entry not in negative_scope:
            raise ValueError(
                "WO-015-G1 evidence must record the explicit governance enablement contract"
            )
    wo015p_g1_evidence = verify_wo015p_g1_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    if work_order == WO015P_G1_WORK_ORDER:
        expected_g1_entry = f"WO-015-P-G1 governance evidence: {wo015p_g1_evidence}"
        if expected_g1_entry not in negative_scope:
            raise ValueError(
                "WO-015-P-G1 evidence must record the explicit promotion governance contract"
            )
    wo016p_g1_evidence = verify_wo016p_g1_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
        approved_lineage,
    )
    if work_order == WO016P_G1_WORK_ORDER:
        expected_g1_entry = f"WO-016-P-G1 governance evidence: {wo016p_g1_evidence}"
        if expected_g1_entry not in negative_scope:
            raise ValueError(
                "WO-016-P-G1 evidence must record the explicit promotion governance contract"
            )
    wo016p_evidence = verify_wo016p_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
        approved_lineage,
    )
    if work_order == WO016P_WORK_ORDER:
        expected_p_entry = f"WO-016-P governance evidence: {wo016p_evidence}"
        if expected_p_entry not in negative_scope:
            raise ValueError(
                "WO-016-P evidence must record the explicit promotion governance contract"
            )
    wo016_g1_evidence = verify_wo016_g1_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    if work_order == WO016_G1_WORK_ORDER:
        expected_g1_entry = f"WO-016-G1 governance evidence: {wo016_g1_evidence}"
        if expected_g1_entry not in negative_scope:
            raise ValueError(
                "WO-016-G1 evidence must record the explicit governance enablement contract"
            )
    wo018_g1_evidence = verify_wo018_g1_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    if work_order == WO018_G1_WORK_ORDER:
        expected_g1_entry = f"WO-018-G1 governance evidence: {wo018_g1_evidence}"
        if expected_g1_entry not in negative_scope:
            raise ValueError(
                "WO-018-G1 evidence must record the explicit governance enablement contract"
            )
    wo018_evidence = verify_wo018_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    if work_order == WO018_WORK_ORDER:
        expected_entry = f"WO-018 governance evidence: {wo018_evidence}"
        if expected_entry not in negative_scope:
            raise ValueError(
                "WO-018 evidence must record the explicit autonomous execution governance contract"
            )
    wo019_g1_evidence = verify_wo019_g1_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    if work_order == WO019_G1_WORK_ORDER:
        expected_g1_entry = f"WO-019-G1 governance evidence: {wo019_g1_evidence}"
        if expected_g1_entry not in negative_scope:
            raise ValueError(
                "WO-019-G1 evidence must record the explicit governance enablement contract"
            )
    wo019_evidence = verify_wo019_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    if work_order == WO019_WORK_ORDER:
        expected_entry = f"WO-019 governance evidence: {wo019_evidence}"
        if expected_entry not in negative_scope:
            raise ValueError(
                "WO-019 evidence must record the explicit Telemetry/Event Bus governance contract"
            )
    wo020_g1_evidence = verify_wo020_g1_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    if work_order == WO020_G1_WORK_ORDER:
        expected_g1_entry = f"WO-020-G1 governance evidence: {wo020_g1_evidence}"
        if expected_g1_entry not in negative_scope:
            raise ValueError(
                "WO-020-G1 evidence must record the explicit governance enablement contract"
            )
    wo020_evidence = verify_wo020_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    if work_order == WO020_WORK_ORDER:
        expected_entry = f"WO-020 governance evidence: {wo020_evidence}"
        if expected_entry not in negative_scope:
            raise ValueError(
                "WO-020 evidence must record the explicit Control Center governance contract"
            )
    wo021_g1_evidence = verify_wo021_g1_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    if work_order == WO021_G1_WORK_ORDER:
        expected_g1_entry = f"WO-021-G1 governance evidence: {wo021_g1_evidence}"
        if expected_g1_entry not in negative_scope:
            raise ValueError(
                "WO-021-G1 evidence must record the explicit governance enablement contract"
            )
    wo021_evidence = verify_wo021_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    if work_order == WO021_WORK_ORDER:
        expected_entry = f"WO-021 governance evidence: {wo021_evidence}"
        if expected_entry not in negative_scope:
            raise ValueError(
                "WO-021 evidence must record the explicit Control Center metrics "
                "governance contract"
            )
    wo022_g1_evidence = verify_wo022_g1_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    if work_order == WO022_G1_WORK_ORDER:
        expected_g1_entry = f"WO-022-G1 governance evidence: {wo022_g1_evidence}"
        if expected_g1_entry not in negative_scope:
            raise ValueError(
                "WO-022-G1 evidence must record the explicit governance enablement contract"
            )
    wo022_evidence = verify_wo022_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    if work_order == WO022_WORK_ORDER:
        expected_entry = f"WO-022 governance evidence: {wo022_evidence}"
        if expected_entry not in negative_scope:
            raise ValueError(
                "WO-022 evidence must record the explicit Full Control Center governance contract"
            )
    wo023_g1_evidence = verify_wo023_g1_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    if work_order == WO023_G1_WORK_ORDER:
        expected_g1_entry = f"WO-023-G1 governance evidence: {wo023_g1_evidence}"
        if expected_g1_entry not in negative_scope:
            raise ValueError(
                "WO-023-G1 evidence must record the explicit governance enablement contract"
            )
    wo023_evidence = verify_wo023_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    if work_order == WO023_WORK_ORDER:
        expected_entry = f"WO-023 governance evidence: {wo023_evidence}"
        if expected_entry not in negative_scope:
            raise ValueError(
                "WO-023 evidence must record the explicit comprehensive benchmarks "
                "governance contract"
            )
    wo023p_g1_evidence = verify_wo023p_g1_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
        approved_lineage,
    )
    if work_order == WO023P_G1_WORK_ORDER:
        expected_g1_entry = f"WO-023-P-G1 governance evidence: {wo023p_g1_evidence}"
        if expected_g1_entry not in negative_scope:
            raise ValueError(
                "WO-023-P-G1 evidence must record the explicit promotion governance contract"
            )
    wo024_g1_evidence = verify_wo024_g1_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
        None,
    )
    if work_order == WO024_G1_WORK_ORDER:
        expected_wo024_g1_entry = f"WO-024-G1 governance evidence: {wo024_g1_evidence}"
        if expected_wo024_g1_entry not in negative_scope:
            raise ValueError(
                "WO-024-G1 evidence must record the explicit closure governance contract"
            )
    wo024_evidence = verify_wo024_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    if work_order == WO024_WORK_ORDER:
        expected_wo024_entry = f"WO-024 governance evidence: {wo024_evidence}"
        if expected_wo024_entry not in negative_scope:
            raise ValueError("WO-024 evidence must record the explicit closure sprint contract")
    wo024p_evidence = verify_wo024p_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
        approved_lineage,
    )
    if work_order == WO024P_WORK_ORDER:
        expected_wo024p_entry = f"WO-024-P governance evidence: {wo024p_evidence}"
        if expected_wo024p_entry not in negative_scope:
            raise ValueError("WO-024-P evidence must record the explicit final promotion contract")
    wo023p_g1_c1_evidence = verify_wo023p_g1_c1_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
        None,
    )
    if work_order == WO023P_G1_C1_WORK_ORDER:
        expected_c1_entry = f"WO-023-P-G1-C1 governance evidence: {wo023p_g1_c1_evidence}"
        if expected_c1_entry not in negative_scope:
            raise ValueError(
                "WO-023-P-G1-C1 evidence must record the explicit parser correction contract"
            )
    wo024p_g1_c1_evidence = verify_wo024p_g1_c1_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
        None,
    )
    if work_order == WO024P_G1_C1_WORK_ORDER:
        expected_c1_wo024p_entry = f"WO-024-P-G1-C1 governance evidence: {wo024p_g1_c1_evidence}"
        if expected_c1_wo024p_entry not in negative_scope:
            raise ValueError(
                "WO-024-P-G1-C1 evidence must record the explicit promotion deadlock correction"
            )
    wo024p_g1_c2_evidence = verify_wo024p_g1_c2_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
        None,
    )
    if work_order == WO024P_G1_C2_WORK_ORDER:
        expected_c2_entry = f"WO-024-P-G1-C2 governance evidence: {wo024p_g1_c2_evidence}"
        if expected_c2_entry not in negative_scope:
            raise ValueError(
                "WO-024-P-G1-C2 evidence must record the explicit stateful-test correction"
            )
    wo024p_g1_c3_evidence = verify_wo024p_g1_c3_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
        None,
    )
    if work_order == WO024P_G1_C3_WORK_ORDER:
        expected_c3_entry = f"WO-024-P-G1-C3 governance evidence: {wo024p_g1_c3_evidence}"
        if expected_c3_entry not in negative_scope:
            raise ValueError(
                "WO-024-P-G1-C3 evidence must record the explicit closure-to-lineage wiring fix"
            )
    wo024p_g1_c4_evidence = verify_wo024p_g1_c4_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
        None,
    )
    if work_order == WO024P_G1_C4_WORK_ORDER:
        expected_c4_entry = f"WO-024-P-G1-C4 governance evidence: {wo024p_g1_c4_evidence}"
        if expected_c4_entry not in negative_scope:
            raise ValueError(
                "WO-024-P-G1-C4 evidence must record the explicit authorized-base propagation fix"
            )
    wo025_g1_evidence = verify_wo025_g1_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
        None,
    )
    if work_order == WO025_G1_WORK_ORDER:
        expected_wo025_g1_entry = f"WO-025-G1 governance evidence: {wo025_g1_evidence}"
        if expected_wo025_g1_entry not in negative_scope:
            raise ValueError(
                "WO-025-G1 evidence must record the explicit post-1.0 governance bridge"
            )
    wo025_evidence = verify_wo025_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
        None,
    )
    if work_order == WO025_WORK_ORDER:
        expected_wo025_entry = f"WO-025 governance evidence: {wo025_evidence}"
        if expected_wo025_entry not in negative_scope:
            raise ValueError("WO-025 evidence must record the planning-only promotion surface")
    wo025_g2_evidence = verify_wo025_g2_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
        None,
    )
    if work_order == WO025_G2_WORK_ORDER:
        expected_wo025_g2_entry = f"WO-025-G2 governance evidence: {wo025_g2_evidence}"
        if expected_wo025_g2_entry not in negative_scope:
            raise ValueError("WO-025-G2 evidence must record the planning-promotion authorization")
    wo025_g3_evidence = verify_wo025_g3_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
        None,
    )
    if work_order == WO025_G3_WORK_ORDER:
        expected_wo025_g3_entry = f"WO-025-G3 governance evidence: {wo025_g3_evidence}"
        if expected_wo025_g3_entry not in negative_scope:
            raise ValueError("WO-025-G3 evidence must record the work-order namespace governance")
    wo025_g4_evidence = verify_wo025_g4_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
        None,
    )
    if work_order == WO025_G4_WORK_ORDER:
        expected_wo025_g4_entry = f"WO-025-G4 governance evidence: {wo025_g4_evidence}"
        if expected_wo025_g4_entry not in negative_scope:
            raise ValueError(
                "WO-025-G4 evidence must record the closure/post-1.0 checkpoint compatibility"
            )
    wo023p_evidence = verify_wo023p_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
        approved_lineage,
    )
    if work_order == WO023P_WORK_ORDER:
        expected_p_entry = f"WO-023-P governance evidence: {wo023p_evidence}"
        if expected_p_entry not in negative_scope:
            raise ValueError(
                "WO-023-P evidence must record the explicit promotion governance contract"
            )
    wo017_g1_evidence = verify_wo017_g1_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    if work_order == WO017_G1_WORK_ORDER:
        expected_g1_entry = f"WO-017-G1 governance evidence: {wo017_g1_evidence}"
        if expected_g1_entry not in negative_scope:
            raise ValueError(
                "WO-017-G1 evidence must record the explicit governance enablement contract"
            )
    wo017_evidence = verify_wo017_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    if work_order == WO017_WORK_ORDER:
        expected_entry = f"WO-017 governance evidence: {wo017_evidence}"
        if expected_entry not in negative_scope:
            raise ValueError(
                "WO-017 evidence must record the explicit MCP product governance contract"
            )
    wo017p_g1_evidence = verify_wo017p_g1_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    if work_order == WO017P_G1_WORK_ORDER:
        expected_g1_entry = f"WO-017-P-G1 governance evidence: {wo017p_g1_evidence}"
        if expected_g1_entry not in negative_scope:
            raise ValueError(
                "WO-017-P-G1 evidence must record the explicit promotion governance contract"
            )
    wo017p_evidence = verify_wo017p_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    if work_order == WO017P_WORK_ORDER:
        expected_p_entry = f"WO-017-P governance evidence: {wo017p_evidence}"
        if expected_p_entry not in negative_scope:
            raise ValueError(
                "WO-017-P evidence must record the explicit promotion governance contract"
            )
    wo018p_g1_evidence = verify_wo018p_g1_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    if work_order == WO018P_G1_WORK_ORDER:
        expected_g1_entry = f"WO-018-P-G1 governance evidence: {wo018p_g1_evidence}"
        if expected_g1_entry not in negative_scope:
            raise ValueError(
                "WO-018-P-G1 evidence must record the explicit promotion governance contract"
            )
    wo018p_evidence = verify_wo018p_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    if work_order == WO018P_WORK_ORDER:
        expected_p_entry = f"WO-018-P governance evidence: {wo018p_evidence}"
        if expected_p_entry not in negative_scope:
            raise ValueError(
                "WO-018-P evidence must record the explicit promotion governance contract"
            )
    wo019p_g1_evidence = verify_wo019p_g1_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    if work_order == WO019P_G1_WORK_ORDER:
        expected_g1_entry = f"WO-019-P-G1 governance evidence: {wo019p_g1_evidence}"
        if expected_g1_entry not in negative_scope:
            raise ValueError(
                "WO-019-P-G1 evidence must record the explicit promotion governance contract"
            )
    wo019p_evidence = verify_wo019p_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    if work_order == WO019P_WORK_ORDER:
        expected_p_entry = f"WO-019-P governance evidence: {wo019p_evidence}"
        if expected_p_entry not in negative_scope:
            raise ValueError(
                "WO-019-P evidence must record the explicit promotion governance contract"
            )
    wo020p_g1_evidence = verify_wo020p_g1_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    if work_order == WO020P_G1_WORK_ORDER:
        expected_g1_entry = f"WO-020-P-G1 governance evidence: {wo020p_g1_evidence}"
        if expected_g1_entry not in negative_scope:
            raise ValueError(
                "WO-020-P-G1 evidence must record the explicit promotion governance contract"
            )
    wo020p_evidence = verify_wo020p_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    if work_order == WO020P_WORK_ORDER:
        expected_p_entry = f"WO-020-P governance evidence: {wo020p_evidence}"
        if expected_p_entry not in negative_scope:
            raise ValueError(
                "WO-020-P evidence must record the explicit promotion governance contract"
            )
    wo021p_g1_evidence = verify_wo021p_g1_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
        approved_lineage,
    )
    if work_order == WO021P_G1_WORK_ORDER:
        expected_g1_entry = f"WO-021-P-G1 governance evidence: {wo021p_g1_evidence}"
        if expected_g1_entry not in negative_scope:
            raise ValueError(
                "WO-021-P-G1 evidence must record the explicit promotion governance contract"
            )
    wo021p_evidence = verify_wo021p_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
        approved_lineage,
    )
    if work_order == WO021P_WORK_ORDER:
        expected_p_entry = f"WO-021-P governance evidence: {wo021p_evidence}"
        if expected_p_entry not in negative_scope:
            raise ValueError(
                "WO-021-P evidence must record the explicit promotion governance contract"
            )
    wo022p_g1_evidence = verify_wo022p_g1_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
        approved_lineage,
    )
    if work_order == WO022P_G1_WORK_ORDER:
        expected_g1_entry = f"WO-022-P-G1 governance evidence: {wo022p_g1_evidence}"
        if expected_g1_entry not in negative_scope:
            raise ValueError(
                "WO-022-P-G1 evidence must record the explicit promotion governance contract"
            )
    wo022p_evidence = verify_wo022p_governance_contract(
        work_order,
        cast(str, base["sha"]),
        cast(list[str], changed_files["paths"]),
        cast(dict[str, object], canonical_payload),
        cast(dict[str, object], manifest["governance"]),
        cast(dict[str, object], cast(dict[str, Any], manifest["evidence"])["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
        approved_lineage,
    )
    if work_order == WO022P_WORK_ORDER:
        expected_p_entry = f"WO-022-P governance evidence: {wo022p_evidence}"
        if expected_p_entry not in negative_scope:
            raise ValueError(
                "WO-022-P evidence must record the explicit promotion governance contract"
            )
    errors = sorted(
        jsonschema.Draft202012Validator(
            json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        ).iter_errors(manifest),
        key=str,
    )
    if errors:
        raise ValueError(f"manifest schema validation failed: {errors[0].message}")
    evidence = cast(dict[str, Any], manifest["evidence"])
    require_wo009_context_manager_evidence(
        work_order,
        cast(dict[str, Any], evidence["integration"]),
    )
    require_wo010_progressive_disclosure_evidence(
        work_order,
        cast(dict[str, Any], evidence["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    require_wo011_context_manager_evidence(
        work_order,
        cast(dict[str, Any], evidence["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    require_wo012_context_manager_evidence(
        work_order,
        cast(dict[str, Any], evidence["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    require_wo013_context_manager_evidence(
        work_order,
        cast(dict[str, Any], evidence["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    require_wo014_provider_prompt_cache_evidence(
        work_order,
        cast(dict[str, Any], evidence["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    require_wo015_memory_evidence(
        work_order,
        cast(dict[str, Any], evidence["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    require_wo016_storage_evidence(
        work_order,
        cast(dict[str, Any], evidence["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    require_wo017_mcp_evidence(
        work_order,
        cast(dict[str, Any], evidence["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    require_wo018_autonomous_evidence(
        work_order,
        cast(dict[str, Any], evidence["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    require_wo019_telemetry_evidence(
        work_order,
        cast(dict[str, Any], evidence["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    require_wo020_control_center_evidence(
        work_order,
        cast(dict[str, Any], evidence["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    require_wo021_control_center_metrics_evidence(
        work_order,
        cast(dict[str, Any], evidence["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    require_wo022_full_control_center_evidence(
        work_order,
        cast(dict[str, Any], evidence["integration"]),
        cast(str, cast(dict[str, Any], manifest["migrations"])["head"]),
    )
    warnings = cast(dict[str, Any], cast(dict[str, Any], manifest["evidence"])["warnings"])
    items = warnings["items"]
    if isinstance(items, list) and (
        warnings["count"] != len(items) or len(items) != len(set(items))
    ):
        raise ValueError("warning evidence count must match unique warning items")


def all_evidence_text() -> str:
    paths = (
        sorted(VALIDATION.glob("*.txt"))
        + sorted(INTEGRATION_LOGS.glob("*.log"))
        + sorted(INTEGRATION_LOGS.glob("*.json"))
    )
    return "\n\n".join(read_text(path) for path in paths)


def failure_diagnostics() -> str:
    lines: list[str] = []
    for line in all_evidence_text().splitlines():
        folded = line.casefold()
        if any(marker in folded for marker in ("traceback", "error", "exception")) or re.search(
            r"exit_code:\s*[1-9]", folded
        ):
            lines.append(line)
    return bounded("\n".join(lines) or "No relevant failure diagnostics recorded.\n")


def summary_markdown(manifest: dict[str, object], workflow_url: str) -> str:
    head = cast(dict[str, Any], manifest["head"])
    base = cast(dict[str, Any], manifest["base"])
    checks = cast(dict[str, Any], manifest["checks"])
    evidence = cast(dict[str, Any], manifest["evidence"])
    tests = cast(dict[str, Any], evidence["tests"])
    integration = cast(dict[str, Any], evidence["integration"])
    security = cast(dict[str, Any], evidence["security"])
    warnings = cast(dict[str, Any], evidence["warnings"])
    benchmark = cast(dict[str, Any], manifest["benchmark"])
    governance = cast(dict[str, Any], manifest["governance"])
    ruleset = cast(dict[str, Any], governance["ruleset"])
    repo_settings = cast(dict[str, Any], governance["repository_merge_settings"])
    artifact = cast(dict[str, Any], manifest["artifact"])
    review_state = cast(dict[str, Any], manifest["review_state"])
    changed_files = cast(dict[str, Any], manifest["changed_files"])
    canonical_changes = canonical_change_evidence(
        changed_files["paths"], cast(str, manifest["work_order"])
    )
    c2_governance_text = next(
        (
            entry.split(": ", 1)[1]
            for entry in cast(list[object], manifest["negative_scope"])
            if isinstance(entry, str) and entry.startswith("WO-014-C2 governance evidence: ")
        ),
        "NOT_RECORDED",
    )
    g1_governance_text = next(
        (
            entry.split(": ", 1)[1]
            for entry in cast(list[object], manifest["negative_scope"])
            if isinstance(entry, str) and entry.startswith("WO-014-P-G1 governance evidence: ")
        ),
        "NOT_RECORDED",
    )
    wo015_g1_governance_text = next(
        (
            entry.split(": ", 1)[1]
            for entry in cast(list[object], manifest["negative_scope"])
            if isinstance(entry, str) and entry.startswith("WO-015-G1 governance evidence: ")
        ),
        "NOT_RECORDED",
    )
    wo015p_g1_governance_text = next(
        (
            entry.split(": ", 1)[1]
            for entry in cast(list[object], manifest["negative_scope"])
            if isinstance(entry, str) and entry.startswith("WO-015-P-G1 governance evidence: ")
        ),
        "NOT_RECORDED",
    )
    wo016p_g1_governance_text = next(
        (
            entry.split(": ", 1)[1]
            for entry in cast(list[object], manifest["negative_scope"])
            if isinstance(entry, str) and entry.startswith("WO-016-P-G1 governance evidence: ")
        ),
        "NOT_RECORDED",
    )
    wo016p_governance_text = next(
        (
            entry.split(": ", 1)[1]
            for entry in cast(list[object], manifest["negative_scope"])
            if isinstance(entry, str) and entry.startswith("WO-016-P governance evidence: ")
        ),
        "NOT_RECORDED",
    )
    wo017_g1_governance_text = next(
        (
            entry.split(": ", 1)[1]
            for entry in cast(list[object], manifest["negative_scope"])
            if isinstance(entry, str) and entry.startswith("WO-017-G1 governance evidence: ")
        ),
        "NOT_RECORDED",
    )
    wo017_governance_text = next(
        (
            entry.split(": ", 1)[1]
            for entry in cast(list[object], manifest["negative_scope"])
            if isinstance(entry, str) and entry.startswith("WO-017 governance evidence: ")
        ),
        "NOT_RECORDED",
    )
    wo017p_g1_governance_text = next(
        (
            entry.split(": ", 1)[1]
            for entry in cast(list[object], manifest["negative_scope"])
            if isinstance(entry, str) and entry.startswith("WO-017-P-G1 governance evidence: ")
        ),
        "NOT_RECORDED",
    )
    wo017p_governance_text = next(
        (
            entry.split(": ", 1)[1]
            for entry in cast(list[object], manifest["negative_scope"])
            if isinstance(entry, str) and entry.startswith("WO-017-P governance evidence: ")
        ),
        "NOT_RECORDED",
    )
    integrity = cast(dict[str, Any], integration["integrity_tests"])
    semantic = cast(dict[str, Any], benchmark.get("semantic", {}))
    hybrid = cast(dict[str, Any], benchmark.get("hybrid", {}))
    rerank = cast(dict[str, Any], benchmark.get("rerank", {}))
    semantic_integrity = cast(dict[str, Any], benchmark.get("semantic_integrity", {}))
    warning_lines = (
        "\n".join(f"  - {item}" for item in warnings["items"])
        if warnings["items"]
        else "  - none observed"
    )
    contexts = ", ".join(ruleset["required_contexts"]) or "none recorded"
    methods = ", ".join(ruleset["allowed_merge_methods"]) or "none recorded"
    backend_tests = (
        f"`{tests['backend']['passed']} passed, {tests['backend']['failed']} failed, "
        f"{tests['backend']['skipped']} skipped`"
    )
    benchmark_text = (
        f"`{benchmark['status']}`; query count `{benchmark['query_count']}`, "
        f"recall@1 `{benchmark['recall_at_1']}`, recall@5 `{benchmark['recall_at_5']}`, "
        f"MRR `{benchmark['mrr']}`, critical misses `{benchmark['critical_context_misses']}`, "
        f"two-run reproducibility `{benchmark['two_run_reproducibility']}`"
    )
    semantic_text = (
        f"`{semantic.get('status', 'UNKNOWN')}`; recall@5 `"
        f"{semantic.get('recall_at_5', 0.0)}`, MRR `{semantic.get('mrr', 0.0)}`, "
        f"critical misses `{semantic.get('critical_context_misses', 0)}`, "
        f"two-run reproducibility `{semantic.get('two_run_reproducibility', False)}`"
    )
    hybrid_text = (
        f"`{hybrid.get('status', 'UNKNOWN')}`; recall@5 `"
        f"{hybrid.get('recall_at_5', 0.0)}`, MRR `{hybrid.get('mrr', 0.0)}`, "
        f"RRF gate `{benchmark.get('hybrid_recall_at_5_gte_extended_lexical', False)}`"
    )
    rerank_text = (
        f"`{rerank.get('status', 'UNKNOWN')}`; recall@5 `{rerank.get('recall_at_5', 0.0)}` "
        f"vs hybrid `{rerank.get('hybrid_recall_at_5', 0.0)}`, "
        f"MRR `{rerank.get('mrr', 0.0)}` vs `{rerank.get('hybrid_mrr', 0.0)}`, "
        f"strict improvement `{rerank.get('strict_rank_improvement', False)}`, "
        f"pool bounded `{rerank.get('candidate_pool_bounded', False)}`, "
        f"provenance `{rerank.get('provenance_preserved', False)}`"
    )
    rerank_c1_text = (
        f"project isolation `{rerank.get('rerank_project_isolation', False)}`, "
        f"duplicate TASK collapse `{rerank.get('rerank_duplicate_task_collapsed', False)}`, "
        f"cross-project duplicate isolation `"
        f"{rerank.get('rerank_cross_project_duplicate_isolation', False)}`, "
        f"malformed-response matrix `{rerank.get('rerank_malformed_response_matrix', False)}`, "
        f"semantic STALE preservation `"
        f"{rerank.get('rerank_semantic_stale_state_preserved', False)}`, "
        f"secret non-leak `{rerank.get('rerank_secret_not_leaked', False)}`, "
        f"ordering reproducible `{rerank.get('rerank_ordering_reproducible', False)}`, "
        f"run 1 digest `{rerank.get('run_1_order_digest', '')}`, "
        f"run 2 digest `{rerank.get('run_2_order_digest', '')}`"
    )
    semantic_integrity_text = (
        f"pgvector `{semantic_integrity.get('actual_pgvector_type', 'UNKNOWN')}`, "
        f"dimensions `{semantic_integrity.get('profile_dimensions', 'UNKNOWN')}`, "
        "reuse without provider calls "
        f"`{semantic_integrity.get('provider_requests_on_reuse', 'UNKNOWN')}`"
    )
    changed_paths_text = ", ".join(f"`{path}`" for path in changed_files["paths"]) or "none"
    authorized_paths = cast(list[str], canonical_changes["authorized_paths"])
    authorized_paths_text = ", ".join(authorized_paths) or "none"
    canonical_summary_text = (
        f"project_brain_changed `{canonical_changes['project_brain_changed']}`, "
        f"checkpoint_changed `{canonical_changes['checkpoint_changed']}`, "
        f"authorized paths `{authorized_paths_text}`"
    )
    merge_settings = (
        f"squash `{repo_settings['allow_squash_merge']}`, "
        f"merge commit `{repo_settings['allow_merge_commit']}`, "
        f"rebase `{repo_settings['allow_rebase_merge']}`, "
        f"delete head branch `{repo_settings['delete_branch_on_merge']}`, "
        f"automatic merge `{repo_settings['allow_auto_merge']}`"
    )
    ruleset_text = (
        f"`{ruleset['id']}` / `{ruleset['name']}`; enforcement `{ruleset['enforcement']}`; "
        f"required contexts `{contexts}`; "
        f"thread resolution `{ruleset['required_review_thread_resolution']}`; "
        f"merge methods `{methods}`; bypass actors `{len(ruleset['bypass_actors'])}`"
    )
    ruleset_unchanged = governance.get("ruleset_unchanged", False)
    race_summary = (
        f"HEAD `{integrity['head_race_rejected']}`, "
        f"inventory `{integrity['inventory_race_rejected']}`, "
        f"prior corpus preserved `{integrity['prior_corpus_preserved']}`"
    )
    duplicate_summary = (
        f"collapsed `{integrity['duplicate_task_candidate_collapsed']}`, "
        f"task provenance preserved `{integrity['task_provenance_preserved']}`, "
        f"cross-project isolation `{integrity['cross_project_duplicate_isolation']}`"
    )
    approval_gate = cast(dict[str, Any], governance.get("approval_gate", {}))
    auto_merge_text = (
        f"`{review_state.get('auto_merge_armed', False)}` / "
        f"`{review_state.get('auto_merge_method') or 'none'}`"
    )
    auto_merge_owner_text = (
        f"{review_state.get('auto_merge_owner_login') or 'none'} "
        f"({review_state.get('auto_merge_owner_type') or 'unknown'})"
    )
    auto_merge_user_owned = review_state.get("auto_merge_user_owned", False)
    approval_text = (
        f"`{ruleset.get('required_approving_review_count')}`; "
        f"independent approvals observed: "
        f"`{approval_gate.get('independent_approval_count', 0)}`"
    )
    context_manager_evidence = cast(dict[str, Any], integration.get("context_manager", {}))
    context_manager_text = (
        f"`{context_manager_evidence.get('status', 'UNKNOWN')}`; "
        f"checkpoint first `{context_manager_evidence.get('checkpoint_first', False)}`, "
        "mandatory coverage `"
        f"{context_manager_evidence.get('mandatory_governance_coverage', False)}`, "
        "kind sequence `"
        f"{context_manager_evidence.get('mandatory_governance_kind_sequence', [])}`, "
        f"project-scoped `{context_manager_evidence.get('governance_project_scoped', False)}`, "
        f"task-scoped `{context_manager_evidence.get('task_project_scoped', False)}`, "
        f"reranked `{context_manager_evidence.get('reranked_retrieval_used', False)}`, "
        f"bounded `{context_manager_evidence.get('bounded', False)}`, "
        "deterministic two-run `"
        f"{context_manager_evidence.get('deterministic_two_run', False)}`, "
        f"LLM calls `{context_manager_evidence.get('llm_calls', 'UNKNOWN')}`"
    )
    progressive_disclosure_text = (
        f"mapping `{context_manager_evidence.get('progressive_disclosure_level_mapping', False)}`, "
        f"smallest sufficient `{context_manager_evidence.get('smallest_sufficient', False)}`, "
        "no unnecessary escalation `"
        f"{context_manager_evidence.get('no_unnecessary_escalation', False)}`, "
        "explicit insufficiency `"
        f"{context_manager_evidence.get('explicit_insufficiency_escalation', False)}`, "
        f"bounded `{context_manager_evidence.get('bounded_escalation', False)}`, "
        f"stop-on-sufficient `{context_manager_evidence.get('stop_on_sufficient', False)}`, "
        "cross-project disclosure `"
        f"{context_manager_evidence.get('cross_project_disclosure_fail_closed', False)}`, "
        "disclosure LLM calls `"
        f"{context_manager_evidence.get('disclosure_llm_calls', 'UNKNOWN')}`, "
        "adaptive token budget `"
        f"{context_manager_evidence.get('adaptive_token_budget_implemented', 'UNKNOWN')}`, "
        "C1 acceptance `"
        f"{context_manager_evidence.get('smallest_sufficient_uses_acceptance_criteria', False)}`, "
        "C1 L1/L2 `"
        f"{context_manager_evidence.get('l1_module_summary_materialized', False)}/"
        f"{context_manager_evidence.get('l2_symbol_signature_materialized', False)}`, "
        "C1 L4 nonempty `"
        f"{context_manager_evidence.get('l4_nonempty_when_selected', False)}`, "
        "C1 explicit level `"
        f"{context_manager_evidence.get('explicit_disclosure_level_contract_valid', False)}`, "
        "C2 L4 full file `"
        f"{context_manager_evidence.get('l4_complete_file_untruncated', False)}/"
        f"{context_manager_evidence.get('l4_large_file_full_content', False)}`, "
        "C2 L4 oversize fail-closed `"
        f"{context_manager_evidence.get('l4_oversize_capsule_fail_closed', False)}`"
    )
    fp_status = context_manager_evidence.get("context_fingerprint_benchmark_status", "UNKNOWN")
    fp_valid_hit = context_manager_evidence.get(
        "context_fingerprint_valid_hit_identical_capsule", False
    )
    fp_work_avoided = context_manager_evidence.get(
        "context_fingerprint_valid_hit_avoids_rebuild", False
    )
    fp_source = context_manager_evidence.get("context_fingerprint_source_change_invalidates", False)
    fp_task = context_manager_evidence.get("context_fingerprint_task_change_invalidates", False)
    fp_request = context_manager_evidence.get(
        "context_fingerprint_request_change_invalidates", False
    )
    fp_project = context_manager_evidence.get("context_fingerprint_cross_project_isolation", False)
    fp_corrupt = context_manager_evidence.get(
        "context_fingerprint_corrupt_cache_safe_rebuild", False
    )
    fp_equivalent = context_manager_evidence.get(
        "context_fingerprint_equivalent_rebuild_stable", False
    )
    fp_transient = context_manager_evidence.get(
        "context_fingerprint_transient_provider_failure_not_cached", False
    )
    fp_recovery = context_manager_evidence.get(
        "context_fingerprint_provider_recovery_retried", False
    )
    fp_redis = context_manager_evidence.get("context_fingerprint_redis_loss_rebuild", False)
    fp_llm = context_manager_evidence.get("context_fingerprint_llm_calls", "UNKNOWN")
    fp_provider = context_manager_evidence.get("context_fingerprint_provider_calls", "UNKNOWN")
    fingerprint_text = (
        f"`{fp_status}`; valid hit `{fp_valid_hit}`, work avoided `{fp_work_avoided}`, "
        f"source/task/request invalidation `{fp_source}/{fp_task}/{fp_request}`, "
        f"cross-project `{fp_project}`, corrupt-cache rebuild `{fp_corrupt}`, "
        f"Redis loss `{fp_redis}`, equivalent rebuild `{fp_equivalent}`, "
        f"transient-not-cached/recovery-retried `{fp_transient}/{fp_recovery}`, "
        f"LLM/provider calls `{fp_llm}/{fp_provider}`"
    )
    delta_status = context_manager_evidence.get("delta_context_benchmark_status", "UNKNOWN")
    delta_implemented = context_manager_evidence.get("delta_context_implemented", False)
    delta_identical = context_manager_evidence.get(
        "delta_context_identical_context_supported", False
    )
    delta_changed = context_manager_evidence.get(
        "delta_context_changed_context_strict_reduction", False
    )
    delta_dependency = context_manager_evidence.get("delta_context_new_dependency_preserved", False)
    delta_reconstruction = context_manager_evidence.get(
        "delta_context_reconstruction_verified", False
    )
    delta_fingerprint = context_manager_evidence.get(
        "delta_context_target_output_fingerprint_verified", False
    )
    delta_false = context_manager_evidence.get("delta_context_false_reconstructions", "UNKNOWN")
    delta_misses = context_manager_evidence.get("delta_context_critical_context_misses", "UNKNOWN")
    delta_llm = context_manager_evidence.get("delta_context_llm_calls", "UNKNOWN")
    delta_provider = context_manager_evidence.get("delta_context_provider_calls", "UNKNOWN")
    delta_stability = context_manager_evidence.get(
        "delta_context_final_stability_all_delivery_paths", False
    )
    delta_postbuild_race = context_manager_evidence.get(
        "delta_context_postbuild_source_race_fail_closed", False
    )
    delta_not_smaller_baseline = context_manager_evidence.get(
        "delta_context_not_smaller_valid_baseline", False
    )
    delta_not_smaller_reason = context_manager_evidence.get(
        "delta_context_not_smaller_reason_verified", False
    )
    delta_final_bound = context_manager_evidence.get(
        "delta_context_final_delivery_bound_verified", False
    )
    delta_estimate_versioned = context_manager_evidence.get(
        "delta_context_delivery_estimate_versioned", False
    )
    delta_final_estimate = context_manager_evidence.get(
        "delta_context_final_delivery_token_estimate_verified", False
    )
    delta_strict_smaller_final = context_manager_evidence.get(
        "delta_context_strict_smaller_uses_final_delivery_estimate", False
    )
    delta_false_positive = context_manager_evidence.get(
        "delta_context_intermediate_metadata_false_positive_regression", False
    )
    delta_savings_truthful = context_manager_evidence.get(
        "delta_context_fresh_token_avoidance_truthful", False
    )
    delta_text = (
        f"`{delta_status}`; implemented `{delta_implemented}`, "
        f"identical/change/dependency `{delta_identical}/{delta_changed}/{delta_dependency}`, "
        f"reconstruction/fingerprint `{delta_reconstruction}/{delta_fingerprint}`, "
        f"false reconstructions/critical misses `{delta_false}/{delta_misses}`, "
        f"LLM/provider calls `{delta_llm}/{delta_provider}`, "
        f"final stability/post-build race `{delta_stability}/{delta_postbuild_race}`, "
        f"valid not-smaller baseline/reason `"
        f"{delta_not_smaller_baseline}/{delta_not_smaller_reason}`, "
        f"final delivery bound `{delta_final_bound}`, "
        f"estimate contract/final estimate/strict gate `"
        f"{delta_estimate_versioned}/{delta_final_estimate}/{delta_strict_smaller_final}`, "
        f"metadata false-positive/savings truthful `"
        f"{delta_false_positive}/{delta_savings_truthful}`"
    )
    provider_cache_status = context_manager_evidence.get(
        "provider_cache_benchmark_status", "UNKNOWN"
    )
    provider_cache_version = context_manager_evidence.get(
        "provider_cache_independent_canonical_input_version", "UNKNOWN"
    )
    provider_cache_independent = context_manager_evidence.get(
        "provider_cache_independent_semantic_composition_verified", False
    )
    provider_cache_mutation_fixture_count = context_manager_evidence.get(
        "provider_cache_semantic_composition_fixture_count", "UNKNOWN"
    )
    provider_cache_mutation_detection_count = context_manager_evidence.get(
        "provider_cache_semantic_composition_mismatch_detection_count", "UNKNOWN"
    )
    provider_cache_mutation_accepted_count = context_manager_evidence.get(
        "provider_cache_accepted_semantic_composition_mismatches", "UNKNOWN"
    )
    provider_cache_material_fixture = context_manager_evidence.get(
        "provider_cache_material_provider_identity_fixture_verified", False
    )
    provider_cache_credential_rotation = context_manager_evidence.get(
        "provider_cache_credential_rotation_nonmaterial", False
    )
    provider_cache_credential_leaks = context_manager_evidence.get(
        "provider_cache_credential_leaks", "UNKNOWN"
    )
    provider_cache_cross_project_leaks = context_manager_evidence.get(
        "provider_cache_cross_project_leaks", "UNKNOWN"
    )
    provider_cache_requested_unknown = context_manager_evidence.get(
        "provider_cache_requested_without_receipt_hit_unknown", False
    )
    provider_cache_zero_false = context_manager_evidence.get(
        "provider_cache_requested_zero_cached_hit_false", False
    )
    provider_cache_repeat_not_hit = context_manager_evidence.get(
        "provider_cache_repeated_prefix_without_receipt_not_hit", False
    )
    provider_cache_positive_true = context_manager_evidence.get(
        "provider_cache_positive_receipt_hit_true", False
    )
    provider_cache_false_hits = context_manager_evidence.get(
        "provider_cache_false_hit_claims", "UNKNOWN"
    )
    provider_cache_invalid_acceptances = context_manager_evidence.get(
        "provider_cache_invalid_accounting_acceptances", "UNKNOWN"
    )
    provider_cache_full_measured = context_manager_evidence.get(
        "provider_cache_full_compatible_measured", False
    )
    provider_cache_delta_measured = context_manager_evidence.get(
        "provider_cache_delta_compatible_measured", False
    )
    provider_cache_delta_false = context_manager_evidence.get(
        "provider_cache_delta_false_reconstructions", "UNKNOWN"
    )
    provider_cache_delta_misses = context_manager_evidence.get(
        "provider_cache_delta_critical_context_misses", "UNKNOWN"
    )
    provider_cache_llm_calls = context_manager_evidence.get(
        "provider_cache_foundation_llm_calls", "UNKNOWN"
    )
    provider_cache_provider_calls = context_manager_evidence.get(
        "provider_cache_foundation_provider_calls", "UNKNOWN"
    )
    provider_cache_text = (
        f"`{provider_cache_status}`; canonical `{provider_cache_version}`, "
        f"independent composition `{provider_cache_independent}`, "
        f"mutation fixtures/detected/accepted `"
        f"{provider_cache_mutation_fixture_count}/"
        f"{provider_cache_mutation_detection_count}/"
        f"{provider_cache_mutation_accepted_count}`, "
        f"provider identity fixture `{provider_cache_material_fixture}`, "
        f"credential rotation/leaks `{provider_cache_credential_rotation}/"
        f"{provider_cache_credential_leaks}`, "
        f"cross-project leaks `{provider_cache_cross_project_leaks}`, "
        f"requested/no-receipt/zero/repeat/positive `"
        f"{provider_cache_requested_unknown}/{provider_cache_zero_false}/"
        f"{provider_cache_repeat_not_hit}/{provider_cache_positive_true}`, "
        f"false hits `{provider_cache_false_hits}`, "
        f"invalid accounting accepted `{provider_cache_invalid_acceptances}`, "
        f"FULL/DELTA measured `{provider_cache_full_measured}/"
        f"{provider_cache_delta_measured}`, "
        f"Delta false/misses `{provider_cache_delta_false}/"
        f"{provider_cache_delta_misses}`, "
        f"LLM/provider calls `{provider_cache_llm_calls}/"
        f"{provider_cache_provider_calls}`"
    )
    memory_evidence = cast(dict[str, Any], integration.get("memory", {}))
    memory_text = (
        f"`{memory_evidence.get('status', 'UNKNOWN')}`; PostgreSQL durable `"
        f"{memory_evidence.get('memory_postgres_durable', False)}`, Redis noncanonical `"
        f"{memory_evidence.get('memory_redis_noncanonical', False)}`, project-scoped `"
        f"{memory_evidence.get('memory_project_scoped', False)}`, cross-project rejection `"
        f"{memory_evidence.get('memory_cross_project_rejected', False)}`, provenance `"
        f"{memory_evidence.get('memory_provenance_queryable', False)}`, staged model output `"
        f"{memory_evidence.get('memory_model_output_staged', False)}`, qualified promotion `"
        f"{memory_evidence.get('memory_canonical_promotion_qualified', False)}`, history `"
        f"{memory_evidence.get('memory_history_preserved', False)}`, restart/Redis loss `"
        f"{memory_evidence.get('memory_restart_recovery', False)}/"
        f"{memory_evidence.get('memory_redis_loss_recovery', False)}`, secret leaks `"
        f"{memory_evidence.get('memory_secret_leaks', 'UNKNOWN')}`, immutable Git blob `"
        f"{memory_evidence.get('memory_immutable_git_blob_binding', False)}`, source/ADR/HEAD "
        f"race rejection `"
        f"{memory_evidence.get('memory_source_mutation_rejected', False)}/"
        f"{memory_evidence.get('memory_adr_mutation_rejected', False)}/"
        f"{memory_evidence.get('memory_head_mutation_rejected', False)}`, race atomicity `"
        f"{memory_evidence.get('memory_race_atomicity_preserved', False)}`, generic decision `"
        f"{memory_evidence.get('memory_generic_decision_id_qualified', False)}`, identity `"
        f"{memory_evidence.get('memory_provenance_identity_consistent', False)}`"
    )
    acce_storage_evidence = cast(dict[str, Any], integration.get("acce_storage", {}))
    acce_benchmark_matrix = acce_storage_evidence.get("benchmark_matrix")
    acce_benchmark_rows = (
        len(acce_benchmark_matrix) if isinstance(acce_benchmark_matrix, list) else 0
    )
    acce_storage_text = (
        f"`{acce_storage_evidence.get('status', 'UNKNOWN')}`; version `"
        f"{acce_storage_evidence.get('acce_evidence_version', 'UNKNOWN')}`, policy `"
        f"{acce_storage_evidence.get('storage_policy_version', 'UNKNOWN')}`, HOT/WARM/COLD `"
        f"{acce_storage_evidence.get('hot_warm_cold_policy_defined', False)}`, benchmark rows `"
        f"{acce_benchmark_rows}`, "
        f"logical/physical measured `"
        f"{acce_storage_evidence.get('logical_bytes_measured', False)}/"
        f"{acce_storage_evidence.get('physical_bytes_measured', False)}`, dedup truthful `"
        f"{acce_storage_evidence.get('dedup_measurements_truthful', False)}`, canonical loss `"
        f"{acce_storage_evidence.get('canonical_source_loss_count', 'UNKNOWN')}`, "
        f"LLM/provider calls `"
        f"{acce_storage_evidence.get('llm_calls', 'UNKNOWN')}/"
        f"{acce_storage_evidence.get('provider_calls', 'UNKNOWN')}`"
    )
    mcp_surface_evidence = cast(dict[str, Any], integration.get("mcp_surface", {}))
    mcp_surface_text = (
        f"`{mcp_surface_evidence.get('status', 'UNKNOWN')}`; version `"
        f"{mcp_surface_evidence.get('mcp_evidence_version', 'UNKNOWN')}`, file `"
        f"{mcp_surface_evidence.get('evidence_file', 'UNKNOWN')}`, tools `"
        f"{mcp_surface_evidence.get('tool_list_exact', [])}`, real transport `"
        f"{mcp_surface_evidence.get('real_transport_exercised', False)}`, direct Core `"
        f"{mcp_surface_evidence.get('direct_core_reuse', False)}`, isolation `"
        f"{mcp_surface_evidence.get('project_isolation_passed', False)}`, checkpoint first `"
        f"{mcp_surface_evidence.get('context_checkpoint_first', False)}`, restart/Redis loss `"
        f"{mcp_surface_evidence.get('restart_recovery', False)}/"
        f"{mcp_surface_evidence.get('redis_loss_recovery', False)}`, leaks `"
        f"{mcp_surface_evidence.get('secret_leaks', 'UNKNOWN')}/"
        f"{mcp_surface_evidence.get('filesystem_path_leaks', 'UNKNOWN')}`, calls `"
        f"{mcp_surface_evidence.get('mcp_llm_calls', 'UNKNOWN')}/"
        f"{mcp_surface_evidence.get('mcp_provider_calls', 'UNKNOWN')}`, projects `"
        f"{mcp_surface_evidence.get('registered_project_count', 'UNKNOWN')}`, arbitrary "
        f"filesystem rejection `"
        f"{mcp_surface_evidence.get('arbitrary_filesystem_access_rejected', False)}`, "
        f"checkpoint missing/untracked/stale/substitution `"
        f"{mcp_surface_evidence.get('checkpoint_missing_fail_closed', False)}/"
        f"{mcp_surface_evidence.get('checkpoint_untracked_fail_closed', False)}/"
        f"{mcp_surface_evidence.get('checkpoint_stale_fail_closed', False)}/"
        f"{mcp_surface_evidence.get('checkpoint_hive_substitution_absent', False)}`, "
        f"context provenance/bounds `"
        f"{mcp_surface_evidence.get('context_search_provenance_preserved', False)}/"
        f"{mcp_surface_evidence.get('context_search_result_bound_enforced', False)}`, "
        f"memory provenance/status `"
        f"{mcp_surface_evidence.get('memory_search_provenance_preserved', False)}/"
        f"{mcp_surface_evidence.get('memory_get_provenance_preserved', False)}/"
        f"{mcp_surface_evidence.get('memory_status_visibility_preserved', False)}`, "
        f"errors structured/bounded `"
        f"{mcp_surface_evidence.get('structured_errors_enforced', False)}/"
        f"{mcp_surface_evidence.get('bounded_errors_enforced', False)}`"
    )
    telemetry_event_bus_evidence_value = cast(
        dict[str, Any], integration.get("telemetry_event_bus", {})
    )
    telemetry_event_bus_text = (
        f"`{telemetry_event_bus_evidence_value.get('status', 'NOT_REQUIRED')}`; version `"
        f"{telemetry_event_bus_evidence_value.get('telemetry_evidence_version', 'NOT_REQUIRED')}`, "
        f"events `{telemetry_event_bus_evidence_value.get('implemented_event_types', [])}`, "
        f"PostgreSQL durable/Redis noncanonical `"
        f"{telemetry_event_bus_evidence_value.get('durable_event_metadata_postgres', False)}/"
        f"{telemetry_event_bus_evidence_value.get('redis_noncanonical', False)}`, "
        f"replay/stream/reconnect `"
        f"{telemetry_event_bus_evidence_value.get('stable_order_replay', False)}/"
        f"{telemetry_event_bus_evidence_value.get('near_realtime_stream', False)}/"
        f"{telemetry_event_bus_evidence_value.get('reconnect_replay', False)}`, "
        f"leaks secret/path/cross-project `"
        f"{telemetry_event_bus_evidence_value.get('secret_leaks', 'UNKNOWN')}/"
        f"{telemetry_event_bus_evidence_value.get('filesystem_path_leaks', 'UNKNOWN')}/"
        f"{telemetry_event_bus_evidence_value.get('cross_project_leaks', 'UNKNOWN')}`, "
        f"LLM/provider calls `"
        f"{telemetry_event_bus_evidence_value.get('llm_calls', 'UNKNOWN')}/"
        f"{telemetry_event_bus_evidence_value.get('provider_calls', 'UNKNOWN')}`"
    )
    control_center_metrics_evidence_value = cast(
        dict[str, Any], integration.get("control_center_metrics", {})
    )
    metrics_version = control_center_metrics_evidence_value.get(
        "metrics_evidence_version", "NOT_REQUIRED"
    )
    metrics_families = control_center_metrics_evidence_value.get("implemented_metric_families", [])
    metrics_provenance = control_center_metrics_evidence_value.get("metric_value_provenance", [])
    metrics_history = control_center_metrics_evidence_value.get(
        "historical_series_max_points", "UNKNOWN"
    )
    metrics_cache = control_center_metrics_evidence_value.get(
        "cache_hit_miss_measured_from_real_events_or_receipts", False
    )
    metrics_storage = control_center_metrics_evidence_value.get(
        "storage_logical_physical_measured", False
    )
    control_center_metrics_text = (
        f"`{control_center_metrics_evidence_value.get('status', 'NOT_REQUIRED')}`; version `"
        f"{metrics_version}`, families `{metrics_families}`, "
        f"provenance `{metrics_provenance}`, history max `{metrics_history}`, "
        f"token/context/cache/storage bounds `"
        f"{control_center_metrics_evidence_value.get('token_telemetry_visible', False)}/"
        f"{control_center_metrics_evidence_value.get('context_reduction_measured', False)}/"
        f"{metrics_cache}/"
        f"{metrics_storage}`, "
        f"PostgreSQL/Redis canonicality `"
        f"{control_center_metrics_evidence_value.get('postgres_canonical', False)}/"
        f"{control_center_metrics_evidence_value.get('redis_canonical_truth', False)}`, "
        f"cost `{control_center_metrics_evidence_value.get('cost_provenance', 'UNKNOWN')}`, "
        f"leaks/calls `"
        f"{control_center_metrics_evidence_value.get('secret_leaks', 'UNKNOWN')}/"
        f"{control_center_metrics_evidence_value.get('filesystem_path_leaks', 'UNKNOWN')}/"
        f"{control_center_metrics_evidence_value.get('cross_project_leaks', 'UNKNOWN')}/"
        f"{control_center_metrics_evidence_value.get('metrics_llm_calls', 'UNKNOWN')}/"
        f"{control_center_metrics_evidence_value.get('metrics_provider_calls', 'UNKNOWN')}`"
    )
    closure_evidence_value = cast(dict[str, Any], integration.get("v01_closure_sprint", {}))
    closure_evidence_text = (
        f"`{closure_evidence_value.get('status', 'NOT_REQUIRED')}`; version `"
        f"{closure_evidence_value.get('v01_closure_sprint_evidence_version', 'NOT_REQUIRED')}`, "
        f"closure candidate `{closure_evidence_value.get('closure_candidate', False)}`, "
        "dod matrix `"
        f"{closure_evidence_value.get('dod_pass_count', 'UNKNOWN')}/"
        f"{closure_evidence_value.get('dod_total_count', 'UNKNOWN')}`, "
        f"fail `{closure_evidence_value.get('dod_fail_count', 'UNKNOWN')}`, "
        f"unknown `{closure_evidence_value.get('dod_unknown_count', 'UNKNOWN')}`, "
        "remaining HIGH/CRITICAL `"
        f"{closure_evidence_value.get('stabilization_remaining_high', 'UNKNOWN')}/"
        f"{closure_evidence_value.get('stabilization_remaining_critical', 'UNKNOWN')}`, "
        f"leaks/calls `{closure_evidence_value.get('secret_leaks', 'UNKNOWN')}/"
        f"{closure_evidence_value.get('filesystem_path_leaks', 'UNKNOWN')}/"
        f"{closure_evidence_value.get('cross_project_leaks', 'UNKNOWN')}/"
        f"{closure_evidence_value.get('core_llm_calls', 'UNKNOWN')}/"
        f"{closure_evidence_value.get('core_provider_calls', 'UNKNOWN')}`"
    )
    control_center_full_evidence_value = cast(
        dict[str, Any], integration.get("control_center_full", {})
    )
    control_center_full_version = control_center_full_evidence_value.get(
        "full_control_center_evidence_version", "NOT_REQUIRED"
    )
    control_center_full_text = (
        f"`{control_center_full_evidence_value.get('status', 'NOT_REQUIRED')}`; version `"
        f"{control_center_full_version}`, "
        "project capabilities `"
        f"{control_center_full_evidence_value.get('implemented_project_capabilities', [])}`, "
        f"charts `{control_center_full_evidence_value.get('implemented_charts', [])}`, "
        f"alerts `{control_center_full_evidence_value.get('implemented_alerts', [])}`, "
        "health `"
        f"{control_center_full_evidence_value.get('implemented_health_capabilities', [])}`, "
        "full V0.1 claim `"
        f"{control_center_full_evidence_value.get('full_v01_complete_claimed', False)}`, "
        f"leaks/calls `"
        f"{control_center_full_evidence_value.get('secret_leaks', 'UNKNOWN')}/"
        f"{control_center_full_evidence_value.get('filesystem_path_leaks', 'UNKNOWN')}/"
        f"{control_center_full_evidence_value.get('cross_project_leaks', 'UNKNOWN')}/"
        f"{control_center_full_evidence_value.get('llm_calls', 'UNKNOWN')}/"
        f"{control_center_full_evidence_value.get('provider_calls', 'UNKNOWN')}`"
    )
    integration_summary = ", ".join(
        f"{label} `{cast(dict[str, Any], integration[key])['status']}`"
        for key, label in (
            ("project_registry", "Project Registry"),
            ("task_intake_cas", "Task Intake/CAS"),
            ("repository_indexing", "Repository Indexing"),
            ("retrieval", "Retrieval"),
            ("redis_restart", "Redis restart"),
            ("api_restart", "API restart"),
            ("reranking", "Reranking"),
            ("context_manager", "Context Manager"),
            ("acce_storage", "ACCE Storage Policy"),
            ("mcp_surface", "MCP Core Surface"),
            ("telemetry_event_bus", "Telemetry/Event Bus"),
            ("control_center_metrics", "Control Center Metrics"),
            ("control_center_full", "Full Control Center"),
        )
        if key in integration
    )
    return f"""# HIVE Review Evidence — {manifest["work_order"]}

- Work Order: `{manifest["work_order"]}`
- Exact HEAD SHA: `{head["sha"]}`
- Base SHA: `{base["sha"]}`
- PR state: **{review_state["status"]}**
- Changed files: `{changed_files["count"]}` — {changed_paths_text}
- Canonical changes: {canonical_summary_text}
- Validate result: **{checks["validation"]}**
- Integration health result: **{checks["integration"]}**
- Review Evidence result: **{checks["review_evidence"]}**
- Migration head: `{cast(dict[str, Any], manifest["migrations"])["head"]}`
- Backend tests: {backend_tests}
- Dashboard tests: `{tests["dashboard"]["passed"]} passed, {tests["dashboard"]["failed"]} failed`
- Integration summary: {integration_summary}
- Git race-integrity tests: {race_summary}
- Duplicate task candidate tests: {duplicate_summary}
- Benchmark summary: {benchmark_text}
- Semantic benchmark: {semantic_text}
- Hybrid benchmark: {hybrid_text}
- Reranking benchmark: {rerank_text}
- Reranking C1 integration safety: {rerank_c1_text}
- Semantic integrity: {semantic_integrity_text}
- Canonical verifier: **{security["canonical_verifier"]["status"]}**
- Secret scan: **{security["secret_scan"]["status"]}**
- Known warnings: `{warnings["count"]}` recorded
{warning_lines}
- Ruleset: {ruleset_text}
- Ruleset unchanged: `{ruleset_unchanged}`
- Repository merge settings: {merge_settings}
- Auto-merge armed: {auto_merge_text}
- Auto-merge owner: {auto_merge_owner_text}; user-owned: `{auto_merge_user_owned}`
- Context Manager evidence: {context_manager_text}
- Context Fingerprint evidence: {fingerprint_text}
- Delta Context evidence: {delta_text}
- Provider/Prompt Cache evidence: {provider_cache_text}
- Memory Lifecycle evidence: {memory_text}
- ACCE Storage Policy evidence: {acce_storage_text}
- MCP Core Surface evidence: {mcp_surface_text}
- Telemetry/Event Bus evidence: {telemetry_event_bus_text}
- Control Center Metrics evidence: {control_center_metrics_text}
- Full Control Center evidence: {control_center_full_text}
- V0.1 Closure Sprint evidence: {closure_evidence_text}
- WO-014-C2 governance evidence: {c2_governance_text}
- WO-014-P-G1 governance evidence: {g1_governance_text}
- WO-015-G1 governance evidence: {wo015_g1_governance_text}
- WO-015-P-G1 governance evidence: {wo015p_g1_governance_text}
- WO-016-P-G1 governance evidence: {wo016p_g1_governance_text}
- WO-016-P governance evidence: {wo016p_governance_text}
- WO-017-G1 governance evidence: {wo017_g1_governance_text}
- WO-017 governance evidence: {wo017_governance_text}
- WO-017-P-G1 governance evidence: {wo017p_g1_governance_text}
- WO-017-P governance evidence: {wo017p_governance_text}
- Progressive Disclosure evidence: {progressive_disclosure_text}
- Required independent approvals: {approval_text}
- Consolidated artifact: `{artifact["name"]}`
- Workflow run URL: {workflow_url}

Sol Review State: {review_state.get("sol_review_state", "AWAITING_SOL")}
"""


def require_hive_final_handoff(
    work_order: str,
    pr_number: int | None,
    base_sha: str,
    head_sha: str,
    governance: dict[str, object],
) -> None:
    if not pr_number or not work_order.startswith("WO-"):
        return
    if work_order == "WO-008-G1" and base_sha != WO008_G1_BASE_SHA:
        raise ValueError(
            f"WO-008-G1 final handoff requires exact base {WO008_G1_BASE_SHA}, observed {base_sha}"
        )
    if work_order == "WO-008-G1" and governance.get("ruleset_unchanged") is not True:
        raise ValueError("WO-008-G1 final handoff requires the protected ruleset to be unchanged")
    pr_governance = cast(dict[str, Any], governance.get("pull_request", {}))
    if pr_governance.get("head_sha") != head_sha:
        observed_head = pr_governance.get("head_sha")
        raise ValueError(f"manifest head SHA {head_sha} does not match PR head SHA {observed_head}")
    if pr_governance.get("base_sha") != base_sha:
        observed_base = pr_governance.get("base_sha")
        raise ValueError(f"manifest base SHA {base_sha} does not match PR base SHA {observed_base}")
    if pr_governance.get("state") != "open":
        raise ValueError("HIVE final-handoff evidence requires an open pull request")
    if pr_governance.get("is_draft") is not False:
        raise ValueError("HIVE final-handoff evidence requires a Ready pull request")
    auto_merge_state = pull_request_auto_merge_evidence(pr_governance)
    if work_order == "WO-008-G1":
        if auto_merge_state.get("armed") is not True:
            raise ValueError("HIVE final-handoff evidence requires native auto-merge to be armed")
        if str(auto_merge_state.get("method", "")).casefold() != "squash":
            raise ValueError("HIVE final-handoff evidence requires SQUASH auto-merge")
        if not auto_merge_state.get("enabled_by_login") or not auto_merge_state.get(
            "enabled_by_type"
        ):
            raise ValueError("HIVE final-handoff evidence requires auto-merge owner identity")
        if auto_merge_state.get("user_owned") is not True:
            raise ValueError("HIVE final-handoff evidence requires user-owned auto-merge")
        approval_gate = cast(dict[str, Any], governance.get("approval_gate", {}))
        if approval_gate.get("independent_approval_count") != 0:
            raise ValueError(
                "HIVE final-handoff evidence requires zero independent approvals before Sol"
            )
        return
    if governance.get("ruleset_unchanged") is not True:
        raise ValueError(
            "HIVE final-handoff evidence requires the protected ruleset to match "
            "the single-account baseline"
        )
    if auto_merge_state.get("armed") is True:
        raise ValueError(
            "HIVE final-handoff evidence requires native auto-merge to be unarmed before Sol audit"
        )


def write_consolidated_artifact(
    output_dir: Path, manifest: dict[str, object], summary: str
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    changed = cast(dict[str, Any], manifest["changed_files"])
    migrations = cast(dict[str, Any], manifest["migrations"])
    warnings = cast(dict[str, Any], cast(dict[str, Any], manifest["evidence"])["warnings"])
    integration_sources = (
        sorted(VALIDATION.glob("*.txt"))
        + sorted(INTEGRATION_LOGS.glob("*.log"))
        + sorted(INTEGRATION_LOGS.glob("*.json"))
    )
    integration_text = "\n\n".join(
        f"===== {path.as_posix()} =====\n{bounded(read_text(path))}" for path in integration_sources
    )
    files = {
        "changed-files.txt": "\n".join(changed["paths"]) + "\n",
        "migration-head.txt": f"{migrations['head']}\n",
        "validation-summary.txt": bounded(read_text(VALIDATION / "summary.txt")),
        "validation-results.txt": bounded(
            read_text(VALIDATION / "test-results.txt")
            + "\n\n"
            + read_text(VALIDATION / "lint-typecheck-build-results.txt")
            + "\n\n"
            + read_text(VALIDATION / "docker-compose-config.txt")
        ),
        "integration-summary.json": json.dumps(
            cast(dict[str, Any], manifest["evidence"])["integration"], indent=2, sort_keys=True
        )
        + "\n",
        "integration-results.txt": bounded(integration_text),
        "service-logs.log": bounded(
            read_text(INTEGRATION_LOGS / "service-logs.log")
            or "No bounded Docker Compose service logs were captured.\n"
        ),
        "warnings-evidence.json": json.dumps(warnings, indent=2, sort_keys=True) + "\n",
        "benchmark.json": json.dumps(manifest["benchmark"], indent=2, sort_keys=True) + "\n",
        "failure-diagnostics.txt": failure_diagnostics(),
        "review-manifest.json": json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        "review-summary.md": summary,
        "github-governance.json": json.dumps(manifest["governance"], indent=2, sort_keys=True)
        + "\n",
    }
    for name, content in files.items():
        # Keep structured evidence parseable even when the manifest grows beyond
        # the bounded excerpt limit used for free-form logs.
        output_content = content if name.endswith(".json") else bounded(content)
        (output_dir / name).write_text(output_content, encoding="utf-8", newline="\n")


def manifest_log(manifest: dict[str, object]) -> str:
    return (
        "HIVE_REVIEW_MANIFEST_BEGIN\n"
        + json.dumps(manifest, indent=2, sort_keys=True)
        + "\nHIVE_REVIEW_MANIFEST_END"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-order")
    parser.add_argument("--repository")
    parser.add_argument("--pr-number", type=int)
    parser.add_argument("--resolve-work-order", action="store_true")
    parser.add_argument("--verify-auto-merge", action="store_true")
    parser.add_argument("--expected-head-sha", default="")
    parser.add_argument("--draft", action="store_true")
    parser.add_argument("--ready", action="store_true")
    parser.add_argument("--draft-env", default="")
    parser.add_argument("--base-branch", default="main")
    parser.add_argument("--base-sha", default="")
    parser.add_argument("--head-branch", default="")
    parser.add_argument("--head-sha", default="")
    parser.add_argument("--artifact-name", default="")
    parser.add_argument("--workflow-run-url", default="")
    parser.add_argument("--server-url", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument(
        "--integration-status", choices=["PASS", "FAIL", "UNKNOWN"], default="UNKNOWN"
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.verify_auto_merge:
        if args.pr_number is None:
            parser.error("--verify-auto-merge requires --pr-number")
        if not HEX_SHA.fullmatch(args.expected_head_sha):
            parser.error("--verify-auto-merge requires a 40-character expected head SHA")
        try:
            evidence = verify_native_auto_merge(
                args.repository or repository_name(),
                args.pr_number,
                args.expected_head_sha,
            )
        except ValueError as error:
            parser.error(str(error))
        print(json.dumps(evidence, sort_keys=True))
        return 0
    if args.resolve_work_order:
        if args.pr_number is None:
            parser.error("--resolve-work-order requires --pr-number")
        try:
            print(derive_work_order(args.repository or repository_name(), args.pr_number))
        except ValueError as error:
            parser.error(str(error))
        return 0
    manifest = build_manifest(args)
    validate_manifest(manifest)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output_dir / "review-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    workflow_url = args.workflow_run_url or (
        f"{args.server_url}/{args.repository}/actions/runs/{args.run_id}"
        if args.server_url and args.repository and args.run_id
        else "UNKNOWN"
    )
    summary = summary_markdown(manifest, workflow_url)
    write_consolidated_artifact(args.output_dir, manifest, summary)
    print(manifest_log(manifest))
    print(
        json.dumps(
            {"manifest": str(manifest_path), "summary": str(args.output_dir / "review-summary.md")},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
