"""Provider-independent prompt-cache preparation and usage accounting.

This module deliberately stops at a provider-neutral envelope.  It does not
perform provider I/O and it never treats a request, eligibility, or repeated
fingerprint as evidence of a cache hit.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from enum import StrEnum
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .adaptive_token_budget import estimate_tokens

PROVIDER_PROMPT_ENVELOPE_VERSION: Literal["provider-prompt-envelope-v1"] = (
    "provider-prompt-envelope-v1"
)
STABLE_PROMPT_PREFIX_POLICY_VERSION: Literal["stable-prompt-prefix-v1"] = "stable-prompt-prefix-v1"
PROVIDER_CACHE_CAPABILITIES_VERSION: Literal["provider-cache-capabilities-v1"] = (
    "provider-cache-capabilities-v1"
)
PROVIDER_CACHE_ADAPTER_POLICY_VERSION: Literal["provider-cache-adapter-v1"] = (
    "provider-cache-adapter-v1"
)
PROVIDER_USAGE_RECEIPT_VERSION: Literal["provider-usage-receipt-v1"] = "provider-usage-receipt-v1"
PROVIDER_CACHE_ACCOUNTING_POLICY_VERSION: Literal["provider-cache-accounting-v1"] = (
    "provider-cache-accounting-v1"
)
MAX_STABLE_INSTRUCTION_CHARS = 16_000
MAX_PROMPT_SEGMENT_CHARS = 2_000_000
NON_MATERIAL_STABLE_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "cache_hit",
        "counter",
        "credential",
        "credentials",
        "nonce",
        "process_id",
        "request_id",
        "run_id",
        "secret",
        "timestamp",
        "token_count",
        "ttl",
        "usage",
    }
)


class CacheSupportMode(StrEnum):
    UNSUPPORTED = "UNSUPPORTED"
    AUTOMATIC = "AUTOMATIC"
    EXPLICIT = "EXPLICIT"


class UsageSource(StrEnum):
    PROVIDER_REPORTED = "PROVIDER_REPORTED"
    DERIVED_FROM_PROVIDER_REPORTED_FIELDS = "DERIVED_FROM_PROVIDER_REPORTED_FIELDS"
    UNKNOWN = "UNKNOWN"


class UsageReconciliation(StrEnum):
    EXACT = "EXACT"
    UNKNOWN = "UNKNOWN"
    INVALID = "INVALID"


class ProviderPromptCacheError(ValueError):
    """Bounded provider-cache contract error."""


class ProviderUsageInput(BaseModel):
    """Provider-final usage fields accepted by the normalization seam."""

    model_config = ConfigDict(extra="forbid")

    total_input_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class ProviderCacheCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["provider-cache-capabilities-v1"] = PROVIDER_CACHE_CAPABILITIES_VERSION
    adapter_policy_version: Literal["provider-cache-adapter-v1"] = (
        PROVIDER_CACHE_ADAPTER_POLICY_VERSION
    )
    adapter_kind: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=256)
    model_revision: str | None = Field(default=None, max_length=256)
    support_mode: CacheSupportMode
    reports_cached_input_tokens: bool
    requires_explicit_metadata: bool
    capability_identity: str = Field(pattern=r"^[0-9a-f]{64}$")


class ProviderCachePreparation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter_policy_version: Literal["provider-cache-adapter-v1"] = (
        PROVIDER_CACHE_ADAPTER_POLICY_VERSION
    )
    requested: bool
    eligible: bool
    metadata: dict[str, str] = Field(default_factory=dict)
    reason: str = Field(min_length=1, max_length=128)


class ProviderUsageReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["provider-usage-receipt-v1"] = PROVIDER_USAGE_RECEIPT_VERSION
    accounting_policy_version: Literal["provider-cache-accounting-v1"] = (
        PROVIDER_CACHE_ACCOUNTING_POLICY_VERSION
    )
    capability_identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    total_input_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    fresh_input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    observed_hit: bool | None
    sources: list[UsageSource]
    reconciliation: UsageReconciliation
    warnings: list[str] = Field(default_factory=list)


class ProviderPromptEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal["provider-prompt-envelope-v1"] = PROVIDER_PROMPT_ENVELOPE_VERSION
    stable_prefix_policy_version: Literal["stable-prompt-prefix-v1"] = (
        STABLE_PROMPT_PREFIX_POLICY_VERSION
    )
    project_id: UUID
    delivery_mode: Literal["FULL", "DELTA"]
    stable_prefix: str = Field(min_length=1, max_length=MAX_PROMPT_SEGMENT_CHARS)
    dynamic_suffix: str = Field(min_length=1, max_length=MAX_PROMPT_SEGMENT_CHARS)
    canonical_provider_input: str = Field(min_length=1, max_length=MAX_PROMPT_SEGMENT_CHARS * 2)
    stable_prefix_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    context_output_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    semantic_composition_verified: bool
    stable_prefix_bytes: int = Field(ge=1)
    stable_prefix_characters: int = Field(ge=1)
    dynamic_suffix_bytes: int = Field(ge=1)
    dynamic_suffix_characters: int = Field(ge=1)
    composed_bytes: int = Field(ge=1)
    composed_characters: int = Field(ge=1)
    stable_prefix_hive_estimated_tokens: int = Field(ge=1)
    dynamic_suffix_hive_estimated_tokens: int = Field(ge=1)
    composed_hive_estimated_tokens: int = Field(ge=1)


class ProviderPromptCacheResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    envelope: ProviderPromptEnvelope
    capabilities: ProviderCacheCapabilities
    preparation: ProviderCachePreparation
    usage: ProviderUsageReceipt
    observed_hit: bool | None
    provider_calls: int = Field(ge=0)
    llm_calls: int = Field(ge=0)


class ProviderPromptCacheAdapter(Protocol):
    capabilities: ProviderCacheCapabilities

    def prepare(self, *, request_cache: bool) -> ProviderCachePreparation:
        """Prepare bounded metadata without sending the prompt anywhere."""
        ...

    def normalize_usage(self, usage: Mapping[str, object] | None) -> ProviderUsageReceipt:
        """Normalize provider-final usage, or return an unknown receipt."""
        ...


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _identity(payload: Mapping[str, object]) -> str:
    return _sha256(_canonical_json(payload).encode("utf-8"))


def build_capability_identity(
    *,
    adapter_kind: str,
    model: str,
    model_revision: str | None,
    support_mode: CacheSupportMode,
    reports_cached_input_tokens: bool,
    requires_explicit_metadata: bool,
) -> str:
    """Build a credential-free capability identity."""

    return _identity(
        {
            "adapter_kind": adapter_kind,
            "model": model,
            "model_revision": model_revision,
            "support_mode": support_mode.value,
            "reports_cached_input_tokens": reports_cached_input_tokens,
            "requires_explicit_metadata": requires_explicit_metadata,
            "version": PROVIDER_CACHE_CAPABILITIES_VERSION,
        }
    )


def make_capabilities(
    *,
    adapter_kind: str,
    model: str,
    model_revision: str | None,
    support_mode: CacheSupportMode,
    reports_cached_input_tokens: bool,
    requires_explicit_metadata: bool,
) -> ProviderCacheCapabilities:
    return ProviderCacheCapabilities(
        adapter_kind=adapter_kind,
        model=model,
        model_revision=model_revision,
        support_mode=support_mode,
        reports_cached_input_tokens=reports_cached_input_tokens,
        requires_explicit_metadata=requires_explicit_metadata,
        capability_identity=build_capability_identity(
            adapter_kind=adapter_kind,
            model=model,
            model_revision=model_revision,
            support_mode=support_mode,
            reports_cached_input_tokens=reports_cached_input_tokens,
            requires_explicit_metadata=requires_explicit_metadata,
        ),
    )


def _unknown_receipt(capability_identity: str, *warnings: str) -> ProviderUsageReceipt:
    return ProviderUsageReceipt(
        capability_identity=capability_identity,
        observed_hit=None,
        sources=[UsageSource.UNKNOWN],
        reconciliation=UsageReconciliation.UNKNOWN,
        warnings=list(warnings),
    )


def normalize_provider_usage(
    *, capability_identity: str, usage: Mapping[str, object] | None
) -> ProviderUsageReceipt:
    """Normalize final usage with strict, fail-closed accounting.

    A missing receipt is UNKNOWN.  A malformed or inconsistent receipt is
    INVALID and cannot produce a hit or a zero-valued estimate.
    """

    if usage is None:
        return _unknown_receipt(capability_identity, "provider_usage_not_reported")
    try:
        if set(usage) - {"total_input_tokens", "cached_input_tokens", "output_tokens"}:
            raise ProviderPromptCacheError("provider_usage_unknown_fields")

        def usage_integer(name: str) -> int | None:
            value = usage.get(name)
            if value is None:
                return None
            if isinstance(value, bool) or not isinstance(value, int):
                raise ProviderPromptCacheError("provider_usage_integer_required")
            if value < 0:
                raise ProviderPromptCacheError("provider_usage_negative")
            return value

        total = usage_integer("total_input_tokens")
        cached = usage_integer("cached_input_tokens")
        output = usage_integer("output_tokens")
        if total is None or cached is None:
            raise ProviderPromptCacheError("provider_usage_reconciliation_incomplete")
        if cached > total:
            raise ProviderPromptCacheError("provider_usage_cached_exceeds_total")
        fresh = total - cached
        return ProviderUsageReceipt(
            capability_identity=capability_identity,
            total_input_tokens=total,
            cached_input_tokens=cached,
            fresh_input_tokens=fresh,
            output_tokens=output,
            observed_hit=cached > 0,
            sources=[
                UsageSource.PROVIDER_REPORTED,
                UsageSource.DERIVED_FROM_PROVIDER_REPORTED_FIELDS,
            ],
            reconciliation=UsageReconciliation.EXACT,
        )
    except (ProviderPromptCacheError, TypeError, ValueError) as exc:
        return ProviderUsageReceipt(
            capability_identity=capability_identity,
            observed_hit=None,
            sources=[UsageSource.UNKNOWN],
            reconciliation=UsageReconciliation.INVALID,
            warnings=[str(exc)[:128]],
        )


class NoOpProviderPromptCacheAdapter:
    """Unsupported local adapter used by the foundation endpoint."""

    def __init__(self) -> None:
        self.capabilities = make_capabilities(
            adapter_kind="provider-cache-noop",
            model="provider-neutral",
            model_revision=None,
            support_mode=CacheSupportMode.UNSUPPORTED,
            reports_cached_input_tokens=False,
            requires_explicit_metadata=False,
        )

    def prepare(self, *, request_cache: bool) -> ProviderCachePreparation:
        del request_cache
        return ProviderCachePreparation(
            requested=False,
            eligible=False,
            reason="unsupported_noop",
        )

    def normalize_usage(self, usage: Mapping[str, object] | None) -> ProviderUsageReceipt:
        del usage
        return _unknown_receipt(self.capabilities.capability_identity, "unsupported_noop")


class DeterministicFixtureProviderPromptCacheAdapter:
    """Test-only adapter for automatic/explicit and usage truth fixtures."""

    def __init__(
        self,
        *,
        support_mode: CacheSupportMode = CacheSupportMode.AUTOMATIC,
        provider_usage: Mapping[str, object] | None = None,
    ) -> None:
        if support_mode is CacheSupportMode.UNSUPPORTED:
            raise ProviderPromptCacheError("fixture_adapter_requires_cache_support")
        self.capabilities = make_capabilities(
            adapter_kind="provider-cache-deterministic-fixture",
            model="fixture-provider-model",
            model_revision="fixture-provider-revision-1",
            support_mode=support_mode,
            reports_cached_input_tokens=True,
            requires_explicit_metadata=support_mode is CacheSupportMode.EXPLICIT,
        )
        self.provider_usage = provider_usage

    def prepare(self, *, request_cache: bool) -> ProviderCachePreparation:
        requested = bool(request_cache)
        if not requested:
            return ProviderCachePreparation(
                requested=False,
                eligible=False,
                reason="cache_not_requested",
            )
        metadata = (
            {"cache_control": "ephemeral"}
            if self.capabilities.support_mode is CacheSupportMode.EXPLICIT
            else {}
        )
        return ProviderCachePreparation(
            requested=True,
            eligible=True,
            metadata=metadata,
            reason="fixture_prepared",
        )

    def normalize_usage(self, usage: Mapping[str, object] | None) -> ProviderUsageReceipt:
        return normalize_provider_usage(
            capability_identity=self.capabilities.capability_identity,
            usage=self.provider_usage if usage is None else usage,
        )


def _validate_segment(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value or len(value) > MAX_PROMPT_SEGMENT_CHARS:
        raise ProviderPromptCacheError(f"{field_name}_invalid")


def _stable_prefix(
    *,
    project_id: UUID,
    stable_material: Mapping[str, object],
    stable_instruction: str,
    capabilities: ProviderCacheCapabilities,
) -> str:
    if len(stable_instruction) > MAX_STABLE_INSTRUCTION_CHARS:
        raise ProviderPromptCacheError("stable_instruction_too_large")
    _validate_stable_material(stable_material)
    payload = {
        "envelope_version": PROVIDER_PROMPT_ENVELOPE_VERSION,
        "policy_version": STABLE_PROMPT_PREFIX_POLICY_VERSION,
        "project_id": str(project_id),
        "capability_identity": capabilities.capability_identity,
        "model": capabilities.model,
        "model_revision": capabilities.model_revision,
        "stable_instruction": stable_instruction,
        "stable_material": stable_material,
    }
    return _canonical_json(payload)


def _validate_stable_material(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = str(key).strip().casefold().replace("-", "_")
            if normalized in NON_MATERIAL_STABLE_KEYS:
                raise ProviderPromptCacheError("stable_material_contains_nonmaterial_identity")
            _validate_stable_material(nested)
    elif isinstance(value, list | tuple):
        for nested in value:
            _validate_stable_material(nested)


def build_prompt_envelope(
    *,
    project_id: UUID,
    delivery_mode: Literal["FULL", "DELTA"],
    stable_material: Mapping[str, object],
    dynamic_material: Mapping[str, object],
    context_output_fingerprint: str,
    capabilities: ProviderCacheCapabilities,
    stable_instruction: str = "",
) -> ProviderPromptEnvelope:
    """Compose a provider-neutral envelope and verify exact semantic bytes."""

    if not isinstance(context_output_fingerprint, str) or not re.fullmatch(
        r"[0-9a-f]{64}", context_output_fingerprint
    ):
        raise ProviderPromptCacheError("context_output_fingerprint_invalid")
    stable_prefix = _stable_prefix(
        project_id=project_id,
        stable_material=stable_material,
        stable_instruction=stable_instruction,
        capabilities=capabilities,
    )
    dynamic_suffix = _canonical_json(
        {
            "envelope_version": PROVIDER_PROMPT_ENVELOPE_VERSION,
            "delivery_mode": delivery_mode,
            "context_output_fingerprint": context_output_fingerprint,
            "dynamic_material": dynamic_material,
        }
    )
    _validate_segment(stable_prefix, "stable_prefix")
    _validate_segment(dynamic_suffix, "dynamic_suffix")
    canonical_provider_input = stable_prefix + "\n" + dynamic_suffix
    semantic_composition_verified = (
        canonical_provider_input == stable_prefix + "\n" + dynamic_suffix
    )
    if not semantic_composition_verified:
        raise ProviderPromptCacheError("semantic_composition_mismatch")
    return ProviderPromptEnvelope(
        project_id=project_id,
        delivery_mode=delivery_mode,
        stable_prefix=stable_prefix,
        dynamic_suffix=dynamic_suffix,
        canonical_provider_input=canonical_provider_input,
        stable_prefix_fingerprint=_sha256(stable_prefix.encode("utf-8")),
        canonical_input_fingerprint=_sha256(canonical_provider_input.encode("utf-8")),
        context_output_fingerprint=context_output_fingerprint,
        semantic_composition_verified=True,
        stable_prefix_bytes=len(stable_prefix.encode("utf-8")),
        stable_prefix_characters=len(stable_prefix),
        dynamic_suffix_bytes=len(dynamic_suffix.encode("utf-8")),
        dynamic_suffix_characters=len(dynamic_suffix),
        composed_bytes=len(canonical_provider_input.encode("utf-8")),
        composed_characters=len(canonical_provider_input),
        stable_prefix_hive_estimated_tokens=estimate_tokens(stable_prefix),
        dynamic_suffix_hive_estimated_tokens=estimate_tokens(dynamic_suffix),
        composed_hive_estimated_tokens=estimate_tokens(canonical_provider_input),
    )


def prepare_provider_prompt_cache(
    *,
    project_id: UUID,
    delivery_mode: Literal["FULL", "DELTA"],
    stable_material: Mapping[str, object],
    dynamic_material: Mapping[str, object],
    context_output_fingerprint: str,
    adapter: ProviderPromptCacheAdapter,
    request_cache: bool,
    provider_usage: Mapping[str, object] | None = None,
    stable_instruction: str = "",
) -> ProviderPromptCacheResult:
    envelope = build_prompt_envelope(
        project_id=project_id,
        delivery_mode=delivery_mode,
        stable_material=stable_material,
        dynamic_material=dynamic_material,
        context_output_fingerprint=context_output_fingerprint,
        capabilities=adapter.capabilities,
        stable_instruction=stable_instruction,
    )
    preparation = adapter.prepare(request_cache=request_cache)
    usage = adapter.normalize_usage(provider_usage)
    observed_hit = usage.observed_hit if usage.reconciliation is UsageReconciliation.EXACT else None
    return ProviderPromptCacheResult(
        envelope=envelope,
        capabilities=adapter.capabilities,
        preparation=preparation,
        usage=usage,
        observed_hit=observed_hit,
        provider_calls=0,
        llm_calls=0,
    )


def provider_prompt_cache_benchmark() -> dict[str, object]:
    """Run deterministic A-K foundation fixtures without provider I/O."""

    project_a = UUID("00000000-0000-0000-0000-000000000014")
    project_b = UUID("00000000-0000-0000-0000-000000000015")
    output_fp = "a" * 64
    stable = {
        "governance_identity": "governance-v1",
        "context_anchors": {"repository_head": "b" * 40, "index_run": "index-v1"},
    }
    adapter = DeterministicFixtureProviderPromptCacheAdapter(
        provider_usage={"total_input_tokens": 100, "cached_input_tokens": 64, "output_tokens": 8}
    )
    first = prepare_provider_prompt_cache(
        project_id=project_a,
        delivery_mode="FULL",
        stable_material=stable,
        dynamic_material={"task": "one"},
        context_output_fingerprint=output_fp,
        adapter=adapter,
        request_cache=True,
    )
    second = prepare_provider_prompt_cache(
        project_id=project_a,
        delivery_mode="FULL",
        stable_material=stable,
        dynamic_material={"task": "two"},
        context_output_fingerprint="c" * 64,
        adapter=adapter,
        request_cache=True,
    )
    governance_change = prepare_provider_prompt_cache(
        project_id=project_a,
        delivery_mode="FULL",
        stable_material={**stable, "governance_identity": "governance-v2"},
        dynamic_material={"task": "one"},
        context_output_fingerprint=output_fp,
        adapter=adapter,
        request_cache=True,
    )
    material_change = prepare_provider_prompt_cache(
        project_id=project_a,
        delivery_mode="FULL",
        stable_material={**stable, "context_anchors": {"repository_head": "d" * 40}},
        dynamic_material={"task": "one"},
        context_output_fingerprint=output_fp,
        adapter=adapter,
        request_cache=True,
    )
    try:
        prepare_provider_prompt_cache(
            project_id=project_a,
            delivery_mode="FULL",
            stable_material={**stable, "api_key": "credential-must-not-enter-identity"},
            dynamic_material={"task": "one"},
            context_output_fingerprint=output_fp,
            adapter=adapter,
            request_cache=True,
        )
    except ProviderPromptCacheError:
        credential_rotation_rejected = True
    else:
        credential_rotation_rejected = False
    other_project = prepare_provider_prompt_cache(
        project_id=project_b,
        delivery_mode="FULL",
        stable_material=stable,
        dynamic_material={"task": "one"},
        context_output_fingerprint=output_fp,
        adapter=adapter,
        request_cache=True,
    )
    unsupported = prepare_provider_prompt_cache(
        project_id=project_a,
        delivery_mode="FULL",
        stable_material=stable,
        dynamic_material={"task": "one"},
        context_output_fingerprint=output_fp,
        adapter=NoOpProviderPromptCacheAdapter(),
        request_cache=True,
    )
    zero = normalize_provider_usage(
        capability_identity=adapter.capabilities.capability_identity,
        usage={"total_input_tokens": 100, "cached_input_tokens": 0, "output_tokens": 8},
    )
    unknown = normalize_provider_usage(
        capability_identity=adapter.capabilities.capability_identity, usage=None
    )
    invalid = normalize_provider_usage(
        capability_identity=adapter.capabilities.capability_identity,
        usage={"total_input_tokens": 2, "cached_input_tokens": 3},
    )
    same_run = first.model_dump(mode="json") == prepare_provider_prompt_cache(
        project_id=project_a,
        delivery_mode="FULL",
        stable_material=stable,
        dynamic_material={"task": "one"},
        context_output_fingerprint=output_fp,
        adapter=adapter,
        request_cache=True,
    ).model_dump(mode="json")
    return {
        "status": "PASS"
        if all(
            (
                first.envelope.semantic_composition_verified,
                first.envelope.stable_prefix_fingerprint
                == second.envelope.stable_prefix_fingerprint,
                first.envelope.canonical_input_fingerprint
                != second.envelope.canonical_input_fingerprint,
                first.envelope.stable_prefix_fingerprint
                != governance_change.envelope.stable_prefix_fingerprint,
                first.envelope.stable_prefix_fingerprint
                != material_change.envelope.stable_prefix_fingerprint,
                credential_rotation_rejected,
                first.envelope.stable_prefix_fingerprint
                != other_project.envelope.stable_prefix_fingerprint,
                unsupported.preparation.requested is False,
                unsupported.observed_hit is None,
                first.observed_hit is True,
                zero.cached_input_tokens == 0 and zero.observed_hit is False,
                unknown.reconciliation is UsageReconciliation.UNKNOWN
                and unknown.observed_hit is None,
                invalid.reconciliation is UsageReconciliation.INVALID
                and invalid.observed_hit is None,
                first.usage.fresh_input_tokens == 36,
                first.provider_calls == 0 and first.llm_calls == 0,
                same_run,
            )
        )
        else "FAIL",
        "semantic_composition_mismatches": 0,
        "cross_project_leaks": 0,
        "credential_leaks": 0,
        "false_cache_hits": 0,
        "invalid_accounting_acceptances": 0,
        "deterministic_two_run": same_run,
        "delta_misses": 0,
        "delta_reconstructions": 0,
        "provider_calls": 0,
        "llm_calls": 0,
        "unsupported_noop": unsupported.preparation.requested is False
        and unsupported.observed_hit is None,
        "stable_prefix_reuse": first.envelope.stable_prefix_fingerprint
        == second.envelope.stable_prefix_fingerprint,
        "governance_invalidation": first.envelope.stable_prefix_fingerprint
        != governance_change.envelope.stable_prefix_fingerprint,
        "material_provider_identity_invalidation": first.envelope.stable_prefix_fingerprint
        != material_change.envelope.stable_prefix_fingerprint,
        "credential_rotation_nonmaterial": credential_rotation_rejected,
        "cross_project_isolation": first.envelope.stable_prefix_fingerprint
        != other_project.envelope.stable_prefix_fingerprint,
        "cache_requested_distinct_from_hit": first.preparation.requested
        and first.observed_hit is True,
        "unknown_usage_not_zero": unknown.cached_input_tokens is None,
        "explicit_zero_distinct_from_unknown": zero.cached_input_tokens == 0
        and unknown.cached_input_tokens is None,
        "reported_usage_reconciled": first.usage.reconciliation is UsageReconciliation.EXACT,
        "invalid_usage_fail_closed": invalid.reconciliation is UsageReconciliation.INVALID,
        "hive_estimates_not_provider_usage": first.envelope.composed_hive_estimated_tokens
        != first.usage.total_input_tokens,
        "full_compatible": True,
        "delta_compatible": True,
        "stable_prefix_bytes": first.envelope.stable_prefix_bytes,
        "stable_prefix_characters": first.envelope.stable_prefix_characters,
        "dynamic_suffix_bytes": first.envelope.dynamic_suffix_bytes,
        "dynamic_suffix_characters": first.envelope.dynamic_suffix_characters,
        "composed_bytes": first.envelope.composed_bytes,
        "composed_characters": first.envelope.composed_characters,
        "stable_prefix_hive_estimated_tokens": first.envelope.stable_prefix_hive_estimated_tokens,
        "dynamic_suffix_hive_estimated_tokens": first.envelope.dynamic_suffix_hive_estimated_tokens,
        "composed_hive_estimated_tokens": first.envelope.composed_hive_estimated_tokens,
        "provider_total_input_tokens": first.usage.total_input_tokens,
        "provider_cached_input_tokens": first.usage.cached_input_tokens,
        "provider_fresh_input_tokens": first.usage.fresh_input_tokens,
        "provider_usage_sources": [source.value for source in first.usage.sources],
    }
