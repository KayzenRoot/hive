from __future__ import annotations

import pytest

from app.adaptive_token_budget import (
    ADAPTIVE_TOKEN_BUDGET_POLICY_VERSION,
    BASE_BUDGET_TOKENS,
    HARD_MAX_BUDGET_TOKENS,
    AdaptiveTokenBudgetError,
    BudgetItem,
    BudgetSignals,
    apply_adaptive_token_budget,
    estimate_tokens,
    run_focused_benchmark,
)


def item(identity: str, text: str) -> BudgetItem:
    return BudgetItem(identity=identity, serialized=text)


def test_utf8_estimator_is_deterministic_and_unicode_safe() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("áéíóú") == 3
    assert estimate_tokens("🙂") == 1
    assert estimate_tokens("🙂" * 100) > estimate_tokens("x" * 100)
    with pytest.raises(AdaptiveTokenBudgetError, match="invalid_token_estimator_input"):
        estimate_tokens(42)  # type: ignore[arg-type]


def test_budget_preserves_required_and_trims_optional_tail_in_order() -> None:
    result = apply_adaptive_token_budget(
        required_items=(item("required", "CHECKPOINT constraints acceptance criteria"),),
        optional_items=(item("optional:0", "a" * 20_000), item("optional:1", "b" * 20_000)),
        signals=BudgetSignals(final_level="L3", retrieval_result_count=5),
    )
    assert result.evidence.policy_version == ADAPTIVE_TOKEN_BUDGET_POLICY_VERSION
    assert result.evidence.required_context_preserved is True
    assert result.evidence.budget_satisfied is True
    assert result.evidence.effective_budget_tokens <= HARD_MAX_BUDGET_TOKENS
    assert result.evidence.estimated_tokens_after <= result.evidence.effective_budget_tokens
    assert result.evidence.estimated_tokens_avoided > 0
    assert [item.identity for item in result.removed_optional_items] == [
        "optional:1",
        "optional:0",
    ]


def test_budget_is_reproducible_and_signals_raise_budget_deterministically() -> None:
    required = (item("required", "governance and task contract"),)
    optional = (item("optional", "tail" * 200),)
    small = apply_adaptive_token_budget(
        required_items=required,
        optional_items=optional,
        signals=BudgetSignals(final_level="L0"),
    )
    medium = apply_adaptive_token_budget(
        required_items=required,
        optional_items=optional,
        signals=BudgetSignals(final_level="L4", l4_complete_file_required=True),
    )
    repeat = apply_adaptive_token_budget(
        required_items=required,
        optional_items=optional,
        signals=BudgetSignals(final_level="L4", l4_complete_file_required=True),
    )
    assert medium.evidence.effective_budget_tokens > small.evidence.effective_budget_tokens
    assert medium.evidence.model_dump() == repeat.evidence.model_dump()
    assert medium.evidence.base_budget_tokens == BASE_BUDGET_TOKENS


def test_budget_fails_closed_when_required_context_exceeds_hard_max() -> None:
    with pytest.raises(
        AdaptiveTokenBudgetError,
        match="required_context_exceeds_token_budget",
    ):
        apply_adaptive_token_budget(
            required_items=(item("required", "x" * 40_000),),
            optional_items=(),
            signals=BudgetSignals(final_level="L4", l4_complete_file_required=True),
        )


def test_focused_benchmark_passes_without_llm_or_provider_calls() -> None:
    benchmark = run_focused_benchmark()
    assert benchmark["status"] == "PASS"
    assert benchmark["provider_independent"] is True
    assert benchmark["llm_calls"] == 0
    assert benchmark["provider_calls"] == 0
    assert benchmark["critical_context_misses"] == 0
    assert benchmark["strict_reduction_fixture"] is True
    assert benchmark["two_run_reproducibility"] is True
