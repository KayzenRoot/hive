from __future__ import annotations

from typing import cast
from uuid import UUID

import pytest

from app.provider_prompt_cache import (
    PROVIDER_CANONICAL_INPUT_VERSION,
    CacheSupportMode,
    DeterministicFixtureProviderPromptCacheAdapter,
    NoOpProviderPromptCacheAdapter,
    ProviderPromptCacheError,
    UsageReconciliation,
    build_capability_identity,
    build_prompt_envelope,
    build_provider_prompt_semantic_source,
    normalize_provider_usage,
    prepare_provider_prompt_cache,
    provider_prompt_cache_benchmark,
    segment_provider_prompt_semantic_source,
    verify_semantic_composition,
)

PROJECT_ID = UUID("00000000-0000-0000-0000-000000000014")
OUTPUT_FINGERPRINT = "a" * 64
STABLE = {
    "governance_identity": "governance-v1",
    "context_anchors": {"repository_head": "b" * 40},
}


def test_stable_prefix_reuses_across_dynamic_suffixes() -> None:
    adapter = NoOpProviderPromptCacheAdapter()
    first = build_prompt_envelope(
        project_id=PROJECT_ID,
        delivery_mode="FULL",
        stable_material=STABLE,
        dynamic_material={"task": "one"},
        context_output_fingerprint=OUTPUT_FINGERPRINT,
        capabilities=adapter.capabilities,
    )
    second = build_prompt_envelope(
        project_id=PROJECT_ID,
        delivery_mode="FULL",
        stable_material=STABLE,
        dynamic_material={"task": "two"},
        context_output_fingerprint="c" * 64,
        capabilities=adapter.capabilities,
    )
    assert first.stable_prefix_fingerprint == second.stable_prefix_fingerprint
    assert first.canonical_input_fingerprint != second.canonical_input_fingerprint
    assert first.semantic_composition_verified is True


def test_material_identity_and_project_scope_invalidate_prefix() -> None:
    adapter = NoOpProviderPromptCacheAdapter()
    base = build_prompt_envelope(
        project_id=PROJECT_ID,
        delivery_mode="FULL",
        stable_material=STABLE,
        dynamic_material={"task": "same"},
        context_output_fingerprint=OUTPUT_FINGERPRINT,
        capabilities=adapter.capabilities,
    )
    governance = build_prompt_envelope(
        project_id=PROJECT_ID,
        delivery_mode="FULL",
        stable_material={**STABLE, "governance_identity": "governance-v2"},
        dynamic_material={"task": "same"},
        context_output_fingerprint=OUTPUT_FINGERPRINT,
        capabilities=adapter.capabilities,
    )
    other_project = build_prompt_envelope(
        project_id=UUID("00000000-0000-0000-0000-000000000015"),
        delivery_mode="FULL",
        stable_material=STABLE,
        dynamic_material={"task": "same"},
        context_output_fingerprint=OUTPUT_FINGERPRINT,
        capabilities=adapter.capabilities,
    )
    assert base.stable_prefix_fingerprint != governance.stable_prefix_fingerprint
    assert base.stable_prefix_fingerprint != other_project.stable_prefix_fingerprint


def test_credential_rotation_is_not_in_stable_identity() -> None:
    adapter = NoOpProviderPromptCacheAdapter()
    first = build_prompt_envelope(
        project_id=PROJECT_ID,
        delivery_mode="FULL",
        stable_material=STABLE,
        dynamic_material={"task": "same"},
        context_output_fingerprint=OUTPUT_FINGERPRINT,
        capabilities=adapter.capabilities,
    )
    second = build_prompt_envelope(
        project_id=PROJECT_ID,
        delivery_mode="FULL",
        stable_material=STABLE,
        dynamic_material={"task": "same"},
        context_output_fingerprint=OUTPUT_FINGERPRINT,
        capabilities=adapter.capabilities,
    )
    assert first.stable_prefix_fingerprint == second.stable_prefix_fingerprint
    with pytest.raises(ProviderPromptCacheError, match="nonmaterial"):
        build_prompt_envelope(
            project_id=PROJECT_ID,
            delivery_mode="FULL",
            stable_material={**STABLE, "api_key": "must-not-be-bound"},
            dynamic_material={"task": "same"},
            context_output_fingerprint=OUTPUT_FINGERPRINT,
            capabilities=adapter.capabilities,
        )


def test_noop_never_claims_requested_or_hit() -> None:
    result = prepare_provider_prompt_cache(
        project_id=PROJECT_ID,
        delivery_mode="FULL",
        stable_material=STABLE,
        dynamic_material={"task": "same"},
        context_output_fingerprint=OUTPUT_FINGERPRINT,
        adapter=NoOpProviderPromptCacheAdapter(),
        request_cache=True,
    )
    assert result.preparation.requested is False
    assert result.preparation.eligible is False
    assert result.observed_hit is None
    assert result.usage.reconciliation is UsageReconciliation.UNKNOWN


@pytest.mark.parametrize(
    ("usage", "cached", "hit"),
    [
        ({"total_input_tokens": 100, "cached_input_tokens": 64, "output_tokens": 8}, 64, True),
        ({"total_input_tokens": 100, "cached_input_tokens": 0, "output_tokens": 8}, 0, False),
    ],
)
def test_reported_usage_distinguishes_positive_hit_and_known_zero(
    usage: dict[str, int], cached: int, hit: bool
) -> None:
    receipt = normalize_provider_usage(
        capability_identity="a" * 64,
        usage=usage,
    )
    assert receipt.reconciliation is UsageReconciliation.EXACT
    assert receipt.cached_input_tokens == cached
    assert receipt.observed_hit is hit
    assert receipt.fresh_input_tokens == 100 - cached


def test_missing_usage_is_unknown_not_zero() -> None:
    receipt = normalize_provider_usage(capability_identity="a" * 64, usage=None)
    assert receipt.reconciliation is UsageReconciliation.UNKNOWN
    assert receipt.cached_input_tokens is None
    assert receipt.observed_hit is None


@pytest.mark.parametrize(
    "usage",
    [
        {"total_input_tokens": 2, "cached_input_tokens": 3},
        {"total_input_tokens": -1, "cached_input_tokens": 0},
        {"total_input_tokens": True, "cached_input_tokens": 0},
        {"total_input_tokens": 2, "cached_input_tokens": 0, "unexpected": 1},
    ],
)
def test_invalid_usage_fails_closed(usage: dict[str, object]) -> None:
    receipt = normalize_provider_usage(capability_identity="a" * 64, usage=usage)
    assert receipt.reconciliation is UsageReconciliation.INVALID
    assert receipt.observed_hit is None
    assert receipt.cached_input_tokens is None


def test_explicit_adapter_prepares_metadata_without_transport() -> None:
    adapter = DeterministicFixtureProviderPromptCacheAdapter(
        support_mode=CacheSupportMode.EXPLICIT,
    )
    preparation = adapter.prepare(request_cache=True)
    assert preparation.requested is True
    assert preparation.eligible is True
    assert preparation.metadata == {"cache_control": "ephemeral"}


def test_capability_identity_is_credential_free_and_material() -> None:
    first = build_capability_identity(
        adapter_kind="fixture",
        model="model-a",
        model_revision="r1",
        support_mode=CacheSupportMode.AUTOMATIC,
        reports_cached_input_tokens=True,
        requires_explicit_metadata=False,
    )
    second = build_capability_identity(
        adapter_kind="fixture",
        model="model-b",
        model_revision="r1",
        support_mode=CacheSupportMode.AUTOMATIC,
        reports_cached_input_tokens=True,
        requires_explicit_metadata=False,
    )
    assert first != second
    assert len(first) == 64


def test_required_deterministic_benchmark_passes() -> None:
    benchmark = provider_prompt_cache_benchmark()
    assert benchmark["status"] == "PASS"
    assert benchmark["semantic_composition_mismatches"] == 0
    assert benchmark["false_cache_hits"] == 0
    assert benchmark["invalid_accounting_acceptances"] == 0
    assert cast(int, benchmark["semantic_composition_fixture_count"]) >= 5
    assert (
        benchmark["semantic_composition_mismatch_detection_count"]
        == benchmark["semantic_composition_fixture_count"]
    )
    assert benchmark["semantic_composition_accepted_mismatches"] == 0
    assert benchmark["provider_calls"] == 0
    assert benchmark["llm_calls"] == 0


def test_independent_canonical_source_detects_all_segment_mutations() -> None:
    adapter = NoOpProviderPromptCacheAdapter()
    source = build_provider_prompt_semantic_source(
        project_id=PROJECT_ID,
        delivery_mode="FULL",
        stable_material=STABLE,
        dynamic_material={"task": "same"},
        context_output_fingerprint=OUTPUT_FINGERPRINT,
        capabilities=adapter.capabilities,
    )
    stable_prefix, dynamic_suffix = segment_provider_prompt_semantic_source(source)
    assert source.version == PROVIDER_CANONICAL_INPUT_VERSION
    valid = verify_semantic_composition(
        source=source,
        stable_prefix=stable_prefix,
        dynamic_suffix=dynamic_suffix,
    )
    assert valid.verified is True
    assert valid.mismatch_count == 0

    stable_lines = stable_prefix.splitlines()
    mutations = (
        ("\n".join(stable_lines[1:]), dynamic_suffix),
        ("\n".join(stable_lines + [stable_lines[0]]), dynamic_suffix),
        (
            "\n".join([stable_lines[1], stable_lines[0], *stable_lines[2:]]),
            dynamic_suffix,
        ),
        (
            stable_prefix.replace("provider-prompt-envelope-v1", "provider-prompt-mutated"),
            dynamic_suffix,
        ),
        (stable_prefix, dynamic_suffix.replace(OUTPUT_FINGERPRINT, "c" * 64)),
    )
    results = [
        verify_semantic_composition(
            source=source,
            stable_prefix=mutated_stable,
            dynamic_suffix=mutated_dynamic,
        )
        for mutated_stable, mutated_dynamic in mutations
    ]
    assert all(result.verified is False and result.mismatch_count == 1 for result in results)


def test_provider_material_fixture_and_credential_rotation_are_measured() -> None:
    automatic = DeterministicFixtureProviderPromptCacheAdapter(credential_sentinel="CREDENTIAL-A")
    explicit = DeterministicFixtureProviderPromptCacheAdapter(
        support_mode=CacheSupportMode.EXPLICIT,
        credential_sentinel="CREDENTIAL-B",
    )
    first = prepare_provider_prompt_cache(
        project_id=PROJECT_ID,
        delivery_mode="FULL",
        stable_material=STABLE,
        dynamic_material={"task": "same"},
        context_output_fingerprint=OUTPUT_FINGERPRINT,
        adapter=automatic,
        request_cache=True,
    )
    second = prepare_provider_prompt_cache(
        project_id=PROJECT_ID,
        delivery_mode="FULL",
        stable_material=STABLE,
        dynamic_material={"task": "same"},
        context_output_fingerprint=OUTPUT_FINGERPRINT,
        adapter=explicit,
        request_cache=True,
    )
    assert automatic.capabilities.capability_identity != explicit.capabilities.capability_identity
    assert first.envelope.stable_prefix_fingerprint != second.envelope.stable_prefix_fingerprint

    credential_a = DeterministicFixtureProviderPromptCacheAdapter(
        credential_sentinel="CREDENTIAL-A"
    )
    credential_b = DeterministicFixtureProviderPromptCacheAdapter(
        credential_sentinel="CREDENTIAL-B"
    )
    result_a = prepare_provider_prompt_cache(
        project_id=PROJECT_ID,
        delivery_mode="FULL",
        stable_material=STABLE,
        dynamic_material={"task": "same"},
        context_output_fingerprint=OUTPUT_FINGERPRINT,
        adapter=credential_a,
        request_cache=True,
    )
    result_b = prepare_provider_prompt_cache(
        project_id=PROJECT_ID,
        delivery_mode="FULL",
        stable_material=STABLE,
        dynamic_material={"task": "same"},
        context_output_fingerprint=OUTPUT_FINGERPRINT,
        adapter=credential_b,
        request_cache=True,
    )
    serialized = result_a.model_dump_json() + result_b.model_dump_json()
    assert (
        credential_a.capabilities.capability_identity
        == credential_b.capabilities.capability_identity
    )
    assert (
        result_a.envelope.stable_prefix_fingerprint == result_b.envelope.stable_prefix_fingerprint
    )
    assert result_a.envelope.canonical_provider_input == result_b.envelope.canonical_provider_input
    assert "CREDENTIAL-A" not in serialized
    assert "CREDENTIAL-B" not in serialized


def test_requested_eligible_and_hit_states_are_independent() -> None:
    no_receipt = DeterministicFixtureProviderPromptCacheAdapter(provider_usage=None)
    absent = prepare_provider_prompt_cache(
        project_id=PROJECT_ID,
        delivery_mode="FULL",
        stable_material=STABLE,
        dynamic_material={"task": "same"},
        context_output_fingerprint=OUTPUT_FINGERPRINT,
        adapter=no_receipt,
        request_cache=True,
    )
    zero = prepare_provider_prompt_cache(
        project_id=PROJECT_ID,
        delivery_mode="FULL",
        stable_material=STABLE,
        dynamic_material={"task": "same"},
        context_output_fingerprint=OUTPUT_FINGERPRINT,
        adapter=DeterministicFixtureProviderPromptCacheAdapter(
            provider_usage={"total_input_tokens": 100, "cached_input_tokens": 0}
        ),
        request_cache=True,
    )
    repeat = prepare_provider_prompt_cache(
        project_id=PROJECT_ID,
        delivery_mode="FULL",
        stable_material=STABLE,
        dynamic_material={"task": "same"},
        context_output_fingerprint=OUTPUT_FINGERPRINT,
        adapter=no_receipt,
        request_cache=True,
    )
    positive = prepare_provider_prompt_cache(
        project_id=PROJECT_ID,
        delivery_mode="FULL",
        stable_material=STABLE,
        dynamic_material={"task": "same"},
        context_output_fingerprint=OUTPUT_FINGERPRINT,
        adapter=DeterministicFixtureProviderPromptCacheAdapter(
            provider_usage={"total_input_tokens": 100, "cached_input_tokens": 1}
        ),
        request_cache=True,
    )
    assert absent.preparation.requested is True and absent.preparation.eligible is True
    assert absent.observed_hit is None and absent.usage.cached_input_tokens is None
    assert zero.observed_hit is False and zero.usage.cached_input_tokens == 0
    assert repeat.envelope.stable_prefix_fingerprint == absent.envelope.stable_prefix_fingerprint
    assert repeat.observed_hit is None
    assert positive.observed_hit is True and positive.usage.cached_input_tokens == 1


@pytest.mark.parametrize(
    "usage",
    [
        {"cached_input_tokens": 1},
        {"total_input_tokens": 1},
        {"total_input_tokens": "100", "cached_input_tokens": 0},
        {"total_input_tokens": {"malformed": True}, "cached_input_tokens": []},
    ],
)
def test_incomplete_and_malformed_accounting_is_invalid(usage: dict[str, object]) -> None:
    receipt = normalize_provider_usage(capability_identity="a" * 64, usage=usage)
    assert receipt.reconciliation is UsageReconciliation.INVALID
    assert receipt.observed_hit is None
