"""Deterministic, provider-independent adaptive token-budget foundation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, cast

from pydantic import BaseModel, Field

ADAPTIVE_TOKEN_BUDGET_POLICY_VERSION: Literal["adaptive-token-budget-v1"] = (
    "adaptive-token-budget-v1"
)
TOKEN_BUDGET_SERIALIZATION_VERSION: Literal["context-payload-v1"] = "context-payload-v1"
TOKEN_ESTIMATOR_VERSION: Literal["utf8-byte-ratio-approx-v1"] = "utf8-byte-ratio-approx-v1"
BASE_BUDGET_TOKENS = 4_096
HARD_MIN_BUDGET_TOKENS = 2_048
HARD_MAX_BUDGET_TOKENS = 6_144
ESTIMATED_BYTES_PER_TOKEN = 4
PLANNER_OVERHEAD_TOKENS = 64
TOKEN_BUDGET_SELECTION_HEADROOM_TOKENS = 1_024
FINAL_PAYLOAD_SERIALIZATION_ALLOWANCE_TOKENS = 256


class AdaptiveTokenBudgetError(ValueError):
    """A bounded budget cannot preserve the required context."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class AdaptiveTokenBudget(BaseModel):
    """Machine-readable evidence for one context-build budget decision."""

    policy_version: Literal["adaptive-token-budget-v1"] = ADAPTIVE_TOKEN_BUDGET_POLICY_VERSION
    estimator_version: Literal["utf8-byte-ratio-approx-v1"] = TOKEN_ESTIMATOR_VERSION
    estimate_serialization_version: Literal["context-payload-v1"] = (
        TOKEN_BUDGET_SERIALIZATION_VERSION
    )
    base_budget_tokens: int
    effective_budget_tokens: int
    hard_min_budget_tokens: int
    hard_max_budget_tokens: int
    estimated_tokens_before: int
    estimated_tokens_after: int
    estimated_tokens_avoided: int
    adaptation_reasons: list[str] = Field(default_factory=list)
    optional_items_removed: list[str] = Field(default_factory=list)
    required_context_preserved: Literal[True] = True
    budget_satisfied: Literal[True] = True
    required_context_exceeds_hard_budget: Literal[False] = False
    llm_calls: Literal[0] = 0
    provider_calls: Literal[0] = 0
    final_context_token_estimate: int | None = None
    final_context_token_estimate_verified: bool = False
    final_context_estimate_within_effective_budget: bool = False


@dataclass(frozen=True)
class BudgetItem:
    """A stable context item considered by the budget planner."""

    identity: str
    serialized: str


@dataclass(frozen=True)
class BudgetSignals:
    """Deterministic signals already available after Progressive Disclosure."""

    final_level: str
    resolved_file_count: int = 0
    resolved_symbol_count: int = 0
    resolved_test_count: int = 0
    retrieval_result_count: int = 0
    constraint_count: int = 0
    acceptance_criteria_count: int = 0
    l4_complete_file_required: bool = False
    l5_repository_investigation: bool = False
    task_excerpt_truncated: bool = False
    governance_truncated: bool = False
    retrieval_truncated: bool = False
    disclosure_truncated: bool = False
    final_payload_serialization_required: bool = False


@dataclass(frozen=True)
class AdaptiveTokenBudgetResult:
    """Retained/removed optional items and their evidence."""

    retained_required_items: tuple[BudgetItem, ...]
    retained_optional_items: tuple[BudgetItem, ...]
    removed_optional_items: tuple[BudgetItem, ...]
    evidence: AdaptiveTokenBudget


def estimate_tokens(value: str) -> int:
    """Estimate tokens by a deterministic UTF-8 byte-ratio approximation."""

    if not isinstance(value, str):
        raise AdaptiveTokenBudgetError("invalid_token_estimator_input")
    byte_count = len(value.encode("utf-8"))
    return (byte_count + ESTIMATED_BYTES_PER_TOKEN - 1) // ESTIMATED_BYTES_PER_TOKEN


def _json_default(value: object) -> object:
    if hasattr(value, "model_dump"):
        return cast(object, value.model_dump(mode="json"))
    raise TypeError(f"value of type {type(value).__name__} is not JSON serializable")


def serialize_context_payload(value: object) -> str:
    """Serialize the exact versioned payload measured by the token contract."""

    return json.dumps(
        value,
        default=_json_default,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def estimate_context_payload_tokens(value: object) -> int:
    """Estimate one canonical context-payload serialization."""

    return estimate_tokens(serialize_context_payload(value))


def verify_context_payload_estimate(value: object, *, effective_budget_tokens: int) -> int:
    """Return the final estimate or fail closed when the payload is too large."""

    estimate = estimate_context_payload_tokens(value)
    if estimate > effective_budget_tokens:
        raise AdaptiveTokenBudgetError("final_context_exceeds_effective_token_budget")
    return estimate


def _estimate_items(items: tuple[BudgetItem, ...]) -> int:
    if not items:
        return 0
    serialized = "\n".join(item.serialized for item in items)
    return estimate_tokens(serialized) + PLANNER_OVERHEAD_TOKENS


def _level_increment(signals: BudgetSignals) -> tuple[int, list[str]]:
    increments = {
        "L0": 0,
        "L1": 128,
        "L2": 256,
        "L3": 512,
        "L4": 1_024,
        "L5": 1_024,
    }
    if signals.final_level not in increments:
        raise AdaptiveTokenBudgetError("invalid_progressive_disclosure_level")
    reasons: list[str] = []
    increment = increments[signals.final_level]
    if increment:
        reasons.append(f"progressive_disclosure_{signals.final_level.casefold()}")
    if signals.resolved_file_count > 1:
        increment += 128
        reasons.append("resolved_file_breadth")
    if signals.resolved_symbol_count > 2:
        increment += 128
        reasons.append("resolved_symbol_breadth")
    if signals.resolved_test_count > 1:
        increment += 128
        reasons.append("resolved_test_breadth")
    if signals.retrieval_result_count > 3:
        increment += 128
        reasons.append("retrieval_evidence_breadth")
    if signals.constraint_count > 2:
        increment += 128
        reasons.append("explicit_constraint_breadth")
    if signals.acceptance_criteria_count > 2:
        increment += 128
        reasons.append("acceptance_criteria_breadth")
    if signals.l4_complete_file_required:
        reasons.append("l4_complete_file_required")
    if signals.l5_repository_investigation:
        reasons.append("l5_repository_investigation")
    if signals.final_payload_serialization_required:
        increment += FINAL_PAYLOAD_SERIALIZATION_ALLOWANCE_TOKENS
        reasons.append("final_payload_serialization_allowance")
    for enabled, reason in (
        (signals.task_excerpt_truncated, "task_excerpt_truncated"),
        (signals.governance_truncated, "governance_truncated"),
        (signals.retrieval_truncated, "retrieval_truncated"),
        (signals.disclosure_truncated, "disclosure_truncated"),
    ):
        if enabled:
            increment += 256
            reasons.append(reason)
    return increment, reasons


def _validate_items(items: tuple[BudgetItem, ...]) -> None:
    identities = [item.identity for item in items]
    if any(not identity for identity in identities) or len(identities) != len(set(identities)):
        raise AdaptiveTokenBudgetError("invalid_token_budget_item_identity")
    if any(not isinstance(item.serialized, str) for item in items):
        raise AdaptiveTokenBudgetError("invalid_token_budget_item_payload")


def apply_adaptive_token_budget(
    *,
    required_items: tuple[BudgetItem, ...],
    optional_items: tuple[BudgetItem, ...],
    signals: BudgetSignals,
) -> AdaptiveTokenBudgetResult:
    """Reserve required context, then remove optional tails deterministically."""

    _validate_items(required_items)
    _validate_items(optional_items)
    if set(item.identity for item in required_items) & {item.identity for item in optional_items}:
        raise AdaptiveTokenBudgetError("duplicate_token_budget_item_identity")

    increment, reasons = _level_increment(signals)
    required_tokens = _estimate_items(required_items)
    effective = max(HARD_MIN_BUDGET_TOKENS, BASE_BUDGET_TOKENS + increment)
    if required_tokens > HARD_MAX_BUDGET_TOKENS:
        raise AdaptiveTokenBudgetError("required_context_exceeds_token_budget")
    if required_tokens > effective:
        effective = required_tokens
        reasons.append("required_context_floor")
    effective = min(effective, HARD_MAX_BUDGET_TOKENS)
    if not HARD_MIN_BUDGET_TOKENS <= effective <= HARD_MAX_BUDGET_TOKENS:
        raise AdaptiveTokenBudgetError("adaptive_token_budget_unsatisfied")

    all_items = required_items + optional_items
    estimated_before = _estimate_items(all_items)
    retained = list(optional_items)
    removed: list[BudgetItem] = []
    # The planner serializes fragments, while the final contract serializes
    # the materialized capsule. Reserve deterministic structural headroom for
    # the latter; final verification remains authoritative and fail-closed.
    selection_budget = max(
        HARD_MIN_BUDGET_TOKENS,
        effective - TOKEN_BUDGET_SELECTION_HEADROOM_TOKENS,
    )
    if optional_items and selection_budget < effective:
        reasons.append("final_payload_serialization_headroom")
    for item in reversed(optional_items):
        if _estimate_items(required_items + tuple(retained)) <= selection_budget:
            break
        retained.remove(item)
        removed.append(item)
    estimated_after = _estimate_items(required_items + tuple(retained))
    if estimated_after > effective:
        raise AdaptiveTokenBudgetError("adaptive_token_budget_unsatisfied")
    if removed:
        reasons.append("optional_context_reduced_to_fit")
    evidence = AdaptiveTokenBudget(
        base_budget_tokens=BASE_BUDGET_TOKENS,
        effective_budget_tokens=effective,
        hard_min_budget_tokens=HARD_MIN_BUDGET_TOKENS,
        hard_max_budget_tokens=HARD_MAX_BUDGET_TOKENS,
        estimated_tokens_before=estimated_before,
        estimated_tokens_after=estimated_after,
        estimated_tokens_avoided=max(0, estimated_before - estimated_after),
        adaptation_reasons=reasons,
        optional_items_removed=[item.identity for item in removed],
    )
    return AdaptiveTokenBudgetResult(required_items, tuple(retained), tuple(removed), evidence)


@dataclass(frozen=True)
class _BenchmarkRequirement:
    identity: str
    category: str
    text: str


def _benchmark_item(identity: str, text: str) -> BudgetItem:
    return BudgetItem(
        identity=identity,
        serialized=serialize_context_payload({"identity": identity, "text": text}),
    )


def _benchmark_payload(
    required: tuple[BudgetItem, ...], optional: tuple[BudgetItem, ...]
) -> dict[str, list[dict[str, str]]]:
    return {
        "required": [
            {"identity": item.identity, "serialized": item.serialized} for item in required
        ],
        "optional": [
            {"identity": item.identity, "serialized": item.serialized} for item in optional
        ],
    }


def _benchmark_evaluation(
    *,
    requirements: tuple[_BenchmarkRequirement, ...],
    required_items: tuple[BudgetItem, ...],
    optional_items: tuple[BudgetItem, ...],
    result: AdaptiveTokenBudgetResult,
    reproducible: bool,
) -> dict[str, object]:
    expected_ids = [requirement.identity for requirement in requirements]
    retained_required_ids = [item.identity for item in result.retained_required_items]
    retained_required_set = set(retained_required_ids)
    missing_ids = [identity for identity in expected_ids if identity not in retained_required_set]
    baseline_estimate = estimate_context_payload_tokens(
        _benchmark_payload(required_items, optional_items)
    )
    adaptive_estimate = estimate_context_payload_tokens(
        _benchmark_payload(
            result.retained_required_items,
            result.retained_optional_items,
        )
    )
    removed_ids = [item.identity for item in result.removed_optional_items]
    category_coverage = {
        category: all(
            requirement.identity in retained_required_set
            for requirement in requirements
            if requirement.category == category
        )
        for category in {requirement.category for requirement in requirements}
    }
    strict_reduction = adaptive_estimate < baseline_estimate and bool(removed_ids)
    quality_pass = (
        not missing_ids
        and all(category_coverage.values())
        and adaptive_estimate <= result.evidence.effective_budget_tokens
    )
    return {
        "baseline_estimated_tokens": baseline_estimate,
        "adaptive_estimated_tokens": adaptive_estimate,
        "estimated_tokens_avoided": max(0, baseline_estimate - adaptive_estimate),
        "effective_budget_tokens": result.evidence.effective_budget_tokens,
        "required_identities": expected_ids,
        "retained_required_identities": retained_required_ids,
        "missing_required_identities": missing_ids,
        "critical_context_misses": len(missing_ids),
        "mandatory_governance_coverage": category_coverage.get("governance", False),
        "task_constraints_preserved": category_coverage.get("task_constraints", False),
        "acceptance_criteria_preserved": category_coverage.get("acceptance_criteria", False),
        "progressive_disclosure_semantics_preserved": category_coverage.get(
            "progressive_disclosure", False
        ),
        "retained_optional_identities": [item.identity for item in result.retained_optional_items],
        "removed_optional_identities": removed_ids,
        "required_context_retained": not missing_ids,
        "budget_within_hard_max": (
            HARD_MIN_BUDGET_TOKENS
            <= result.evidence.effective_budget_tokens
            <= HARD_MAX_BUDGET_TOKENS
        ),
        "strict_reduction": strict_reduction,
        "strict_reduction_has_actual_optional_removal": bool(removed_ids),
        "two_run_reproducibility": reproducible,
        "status": "PASS" if quality_pass else "FAIL",
    }


def _benchmark_fixture(
    name: str,
    *,
    level: str,
    requirements: tuple[_BenchmarkRequirement, ...],
    optional_texts: tuple[str, ...],
    signals: BudgetSignals,
) -> dict[str, object]:
    required = tuple(_benchmark_item(item.identity, item.text) for item in requirements)
    optional = tuple(
        _benchmark_item(f"optional:{name}:{i}", text) for i, text in enumerate(optional_texts)
    )
    first = apply_adaptive_token_budget(
        required_items=required,
        optional_items=optional,
        signals=signals,
    )
    second = apply_adaptive_token_budget(
        required_items=required,
        optional_items=optional,
        signals=signals,
    )
    reproducible = (
        first.evidence.model_dump() == second.evidence.model_dump()
        and first.retained_required_items == second.retained_required_items
        and first.retained_optional_items == second.retained_optional_items
    )
    return {
        "name": name,
        "level": level,
        **_benchmark_evaluation(
            requirements=requirements,
            required_items=required,
            optional_items=optional,
            result=first,
            reproducible=reproducible,
        ),
    }


def _benchmark_negative_fixture(
    *,
    name: str,
    requirement: _BenchmarkRequirement,
    requirements: tuple[_BenchmarkRequirement, ...],
    signals: BudgetSignals,
) -> dict[str, object]:
    expected = tuple(_benchmark_item(item.identity, item.text) for item in requirements)
    required = tuple(item for item in expected if item.identity != requirement.identity)
    result = apply_adaptive_token_budget(
        required_items=required,
        optional_items=(),
        signals=signals,
    )
    evaluation = _benchmark_evaluation(
        requirements=requirements,
        required_items=required,
        optional_items=(),
        result=result,
        reproducible=True,
    )
    critical_context_misses = cast(int, evaluation["critical_context_misses"])
    return {
        "name": name,
        "removed_required_identity": requirement.identity,
        "removed_required_category": requirement.category,
        "detected_expected_failure": (
            evaluation["status"] == "FAIL" and critical_context_misses > 0
        ),
        **evaluation,
    }


def run_focused_benchmark() -> dict[str, object]:
    """Return the bounded WO-011 benchmark without network/provider dependencies."""

    fixtures = [
        _benchmark_fixture(
            "small-no-op-baseline",
            level="L0",
            requirements=(
                _BenchmarkRequirement("governance:CHECKPOINT", "governance", "CHECKPOINT"),
                _BenchmarkRequirement("task:constraints", "task_constraints", "constraints"),
                _BenchmarkRequirement(
                    "task:acceptance_criteria", "acceptance_criteria", "acceptance criteria"
                ),
                _BenchmarkRequirement(
                    "disclosure:required", "progressive_disclosure", "L0 project payload"
                ),
            ),
            optional_texts=(),
            signals=BudgetSignals(final_level="L0"),
        ),
        _benchmark_fixture(
            "small-project-state",
            level="L0",
            requirements=(
                _BenchmarkRequirement("governance:CHECKPOINT", "governance", "CHECKPOINT"),
                _BenchmarkRequirement("governance:SCOPE", "governance", "SCOPE"),
                _BenchmarkRequirement(
                    "governance:DEFINITION_OF_DONE", "governance", "DEFINITION_OF_DONE"
                ),
                _BenchmarkRequirement("governance:ARCHITECTURE", "governance", "ARCHITECTURE"),
                _BenchmarkRequirement("governance:DECISIONS", "governance", "DECISIONS"),
                _BenchmarkRequirement("task:constraints", "task_constraints", "constraints"),
                _BenchmarkRequirement(
                    "task:acceptance_criteria", "acceptance_criteria", "acceptance criteria"
                ),
                _BenchmarkRequirement(
                    "disclosure:required", "progressive_disclosure", "L0 project payload"
                ),
            ),
            optional_texts=("optional low-priority project tail " * 1_000,),
            signals=BudgetSignals(final_level="L0"),
        ),
        _benchmark_fixture(
            "medium-implementation",
            level="L3",
            requirements=(
                _BenchmarkRequirement("governance:CHECKPOINT", "governance", "CHECKPOINT"),
                _BenchmarkRequirement("governance:SCOPE", "governance", "SCOPE"),
                _BenchmarkRequirement(
                    "governance:DEFINITION_OF_DONE", "governance", "DEFINITION_OF_DONE"
                ),
                _BenchmarkRequirement("governance:ARCHITECTURE", "governance", "ARCHITECTURE"),
                _BenchmarkRequirement("governance:DECISIONS", "governance", "DECISIONS"),
                _BenchmarkRequirement(
                    "task:constraints", "task_constraints", "Constraints implementation evidence"
                ),
                _BenchmarkRequirement(
                    "task:acceptance_criteria",
                    "acceptance_criteria",
                    "Acceptance Criteria implementation evidence",
                ),
                _BenchmarkRequirement(
                    "disclosure:required", "progressive_disclosure", "L3 implementation payload"
                ),
            ),
            optional_texts=(
                "retrieval candidate tail " * 800,
                "redundant derived projection " * 800,
            ),
            signals=BudgetSignals(
                final_level="L3",
                resolved_file_count=2,
                resolved_symbol_count=3,
                retrieval_result_count=5,
            ),
        ),
        _benchmark_fixture(
            "large-deeper-context",
            level="L4",
            requirements=(
                _BenchmarkRequirement("governance:CHECKPOINT", "governance", "CHECKPOINT"),
                _BenchmarkRequirement("governance:SCOPE", "governance", "SCOPE"),
                _BenchmarkRequirement(
                    "governance:DEFINITION_OF_DONE", "governance", "DEFINITION_OF_DONE"
                ),
                _BenchmarkRequirement("governance:ARCHITECTURE", "governance", "ARCHITECTURE"),
                _BenchmarkRequirement("governance:DECISIONS", "governance", "DECISIONS"),
                _BenchmarkRequirement("task:constraints", "task_constraints", "constraints"),
                _BenchmarkRequirement(
                    "task:acceptance_criteria", "acceptance_criteria", "acceptance criteria"
                ),
                _BenchmarkRequirement(
                    "disclosure:required",
                    "progressive_disclosure",
                    "complete-file source content " * 700,
                ),
            ),
            optional_texts=("lower-ranked optional evidence " * 400,),
            signals=BudgetSignals(
                final_level="L4",
                resolved_file_count=2,
                resolved_symbol_count=3,
                resolved_test_count=2,
                retrieval_result_count=5,
                constraint_count=3,
                acceptance_criteria_count=3,
                l4_complete_file_required=True,
            ),
        ),
    ]
    negative_requirements = (
        _BenchmarkRequirement("governance:CHECKPOINT", "governance", "CHECKPOINT"),
        _BenchmarkRequirement("task:constraints", "task_constraints", "constraints"),
        _BenchmarkRequirement(
            "task:acceptance_criteria", "acceptance_criteria", "acceptance criteria"
        ),
        _BenchmarkRequirement(
            "disclosure:required", "progressive_disclosure", "required disclosure payload"
        ),
    )
    negative_fixtures = [
        _benchmark_negative_fixture(
            name=f"negative-{requirement.category}",
            requirement=requirement,
            requirements=negative_requirements,
            signals=BudgetSignals(final_level="L3"),
        )
        for requirement in negative_requirements
    ]
    critical_misses = sum(cast(int, fixture["critical_context_misses"]) for fixture in fixtures)
    strict_reduction = any(bool(fixture["strict_reduction"]) for fixture in fixtures)
    negative_detected = all(
        bool(fixture["detected_expected_failure"]) for fixture in negative_fixtures
    )
    status = (
        "PASS"
        if all(fixture["status"] == "PASS" for fixture in fixtures)
        and critical_misses == 0
        and strict_reduction
        and negative_detected
        else "FAIL"
    )
    return {
        "schema_version": 1,
        "status": status,
        "policy_version": ADAPTIVE_TOKEN_BUDGET_POLICY_VERSION,
        "estimator_version": TOKEN_ESTIMATOR_VERSION,
        "estimate_serialization_version": TOKEN_BUDGET_SERIALIZATION_VERSION,
        "provider_independent": True,
        "llm_calls": 0,
        "provider_calls": 0,
        "baseline_definition": "same-fixture full eligible context payload",
        "hard_max_budget_tokens": HARD_MAX_BUDGET_TOKENS,
        "fixtures": fixtures,
        "negative_fixtures": negative_fixtures,
        "critical_context_misses": critical_misses,
        "mandatory_governance_coverage": all(
            fixture["mandatory_governance_coverage"] for fixture in fixtures
        ),
        "task_constraints_preserved": all(
            fixture["task_constraints_preserved"] for fixture in fixtures
        ),
        "acceptance_criteria_preserved": all(
            fixture["acceptance_criteria_preserved"] for fixture in fixtures
        ),
        "progressive_disclosure_semantics_preserved": all(
            fixture["progressive_disclosure_semantics_preserved"] for fixture in fixtures
        ),
        "strict_reduction_fixture": strict_reduction,
        "strict_reduction_is_real": all(
            not bool(fixture["strict_reduction"])
            or bool(fixture["strict_reduction_has_actual_optional_removal"])
            for fixture in fixtures
        ),
        "benchmark_critical_misses_computed": True,
        "benchmark_required_identity_negative_fixture": negative_detected,
        "benchmark_mandatory_governance_computed": True,
        "benchmark_task_contract_computed": True,
        "benchmark_disclosure_retention_computed": True,
        "two_run_reproducibility": all(
            bool(fixture["two_run_reproducibility"]) for fixture in fixtures
        ),
    }
