"""Generate and validate bounded, secret-free Review Evidence."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "review-evidence-v1.schema.json"
DEFAULT_OUTPUT = ROOT / "tmp" / "review-evidence"
VALIDATION = ROOT / "tmp" / "validation"
INTEGRATION_LOGS = ROOT / "tmp" / "integration-logs"
HEX_SHA = re.compile(r"^[0-9a-f]{40}$")
MAX_EVIDENCE_CHARS = 12_000
WORK_ORDER_IDENTIFIER = re.compile(r"(?:WO-[0-9]+|ENG-[A-Z0-9]+)(?:-[A-Z0-9]+)*")
WORK_ORDER_MARKER = re.compile(r"<!--\s*HIVE-WORK-ORDER:\s*([^<>\r\n]+?)\s*-->", re.IGNORECASE)
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
MANDATORY_GOVERNANCE_KIND_SEQUENCE = (
    "CHECKPOINT",
    "SCOPE",
    "DEFINITION_OF_DONE",
    "ARCHITECTURE",
    "DECISIONS",
)
CHECKPOINT_PATH = "docs/project-brain/13-CHECKPOINT.md"
CANONICAL_PATHS = (
    CHECKPOINT_PATH,
    "docs/project-brain/CANONICAL-SHA256SUMS.txt",
)
WO008_G1_BASE_SHA = "fcbf0849a54e0283ed523e09ce18ea31a8bd7849"
WO009_BASE_SHA = "7e95a026ff050c4bd953c27fb61ff79acff15d1f"
WO010_G1_BASE_SHA = "552d809f6e0a6e1f940084c35f3109dc4ec931a1"
WO010_BASE_SHA = "68bb6679da32355b9e5c4bbb241bec0d1e685e26"
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
    if len(work_order) > 64 or WORK_ORDER_IDENTIFIER.fullmatch(work_order) is None:
        raise ValueError(f"invalid or unbounded HIVE work-order identifier: {work_order!r}")
    return work_order


def derive_work_order(repository: str, pr_number: int) -> str:
    pr = _gh_json(repository, f"pulls/{pr_number}")
    if not isinstance(pr, dict):
        raise ValueError(f"unable to read pull request #{pr_number} for work-order derivation")
    body = pr.get("body")
    if not isinstance(body, str):
        body = ""
    return parse_work_order_marker(body)


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
    evidence = {
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


def integration_evidence(benchmark: dict[str, object]) -> dict[str, object]:
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
    integrity = retrieval_integrity(retrieval)
    return {
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
    if args.pr_number:
        work_order = derive_work_order(repository, args.pr_number)
        if args.work_order and args.work_order != work_order:
            raise ValueError(
                f"work-order override {args.work_order!r} does not match PR marker {work_order!r}"
            )
    else:
        work_order = args.work_order or "LOCAL-VALIDATION"
        if work_order != "LOCAL-VALIDATION" and WORK_ORDER_IDENTIFIER.fullmatch(work_order) is None:
            raise ValueError(f"invalid or unbounded HIVE work-order identifier: {work_order!r}")
    validation = read_text(VALIDATION / "summary.txt")
    lint = read_text(VALIDATION / "lint-typecheck-build-results.txt")
    tests_text = read_text(VALIDATION / "test-results.txt")
    base_sha = args.base_sha or git_value("merge-base", "HEAD", "origin/main", fallback="0" * 40)
    head_sha = args.head_sha or git_value("rev-parse", "HEAD")
    actual_head = git_value("rev-parse", "HEAD")
    if head_sha != actual_head:
        raise ValueError(f"head SHA mismatch: expected {head_sha}, checked out {actual_head}")
    paths = changed_paths(base_sha, head_sha)
    require_wo008_g1_scope(work_order, base_sha, paths)
    require_wo009_scope(work_order, base_sha, paths)
    require_wo010_g1_scope(work_order, base_sha, paths)
    require_wo010_scope(work_order, base_sha, paths)
    all_validation = validation + "\n" + lint + "\n" + tests_text
    evidence_text = all_evidence_text()
    github_evidence = github_review_text(repository, args.pr_number)
    benchmark = benchmark_fields(VALIDATION / "retrieval-benchmark.json")
    tests = tests_evidence(validation, tests_text)
    integration = integration_evidence(benchmark)
    require_wo009_context_manager_evidence(work_order, integration)
    require_wo010_progressive_disclosure_evidence(
        work_order,
        integration,
        migration_head(),
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
        ],
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
    if work_order == "WO-008-G1":
        base = cast(dict[str, Any], manifest["base"])
        changed_files = cast(dict[str, Any], manifest["changed_files"])
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
        base = cast(dict[str, Any], manifest["base"])
        changed_files = cast(dict[str, Any], manifest["changed_files"])
        require_wo009_scope(
            work_order,
            cast(str, base["sha"]),
            cast(list[str], changed_files["paths"]),
        )
    if work_order == "WO-010-G1":
        base = cast(dict[str, Any], manifest["base"])
        changed_files = cast(dict[str, Any], manifest["changed_files"])
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
        base = cast(dict[str, Any], manifest["base"])
        changed_files = cast(dict[str, Any], manifest["changed_files"])
        require_wo010_scope(
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
