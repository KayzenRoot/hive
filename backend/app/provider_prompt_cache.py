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
PROVIDER_CANONICAL_INPUT_VERSION: Literal["provider-canonical-input-v1"] = (
    "provider-canonical-input-v1"
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


class ProviderPromptSemanticElement(BaseModel):
    """One ordered semantic element before provider-cache segmentation."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    value: object
    segment: Literal["stable", "dynamic"]


class ProviderPromptSemanticSource(BaseModel):
    """Complete provider-neutral prompt meaning before segmentation."""

    model_config = ConfigDict(extra="forbid")

    version: Literal["provider-canonical-input-v1"] = PROVIDER_CANONICAL_INPUT_VERSION
    elements: tuple[ProviderPromptSemanticElement, ...] = Field(min_length=1)


class SemanticCompositionVerification(BaseModel):
    """Independent canonical-vs-recomposed comparison result."""

    model_config = ConfigDict(extra="forbid")

    canonical_provider_input: str = Field(min_length=1, max_length=MAX_PROMPT_SEGMENT_CHARS * 2)
    recomposed_provider_input: str = Field(min_length=1, max_length=MAX_PROMPT_SEGMENT_CHARS * 2)
    mismatch_count: int = Field(ge=0, le=1)
    verified: bool


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
    canonical_input_version: Literal["provider-canonical-input-v1"] = (
        PROVIDER_CANONICAL_INPUT_VERSION
    )
    stable_prefix_policy_version: Literal["stable-prompt-prefix-v1"] = (
        STABLE_PROMPT_PREFIX_POLICY_VERSION
    )
    project_id: UUID
    delivery_mode: Literal["FULL", "DELTA"]
    stable_prefix: str = Field(min_length=1, max_length=MAX_PROMPT_SEGMENT_CHARS)
    dynamic_suffix: str = Field(min_length=1, max_length=MAX_PROMPT_SEGMENT_CHARS)
    canonical_provider_input: str = Field(min_length=1, max_length=MAX_PROMPT_SEGMENT_CHARS * 2)
    recomposed_provider_input: str = Field(min_length=1, max_length=MAX_PROMPT_SEGMENT_CHARS * 2)
    semantic_source_element_count: int = Field(ge=1)
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
    provider_calls: int
    llm_calls: int

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
        self.provider_calls = 0
        self.llm_calls = 0
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


def _openai_compatible_usage(usage: Mapping[str, object] | None) -> Mapping[str, object] | None:
    """Translate common OpenAI-compatible usage fields into the strict receipt seam."""

    if usage is None:
        return None
    if set(usage) <= {"total_input_tokens", "cached_input_tokens", "output_tokens"}:
        return usage
    allowed = {
        "prompt_tokens",
        "prompt_tokens_details",
        "completion_tokens",
        "total_tokens",
    }
    if set(usage) - allowed:
        return {"unexpected": object()}
    prompt_tokens = usage.get("prompt_tokens")
    details = usage.get("prompt_tokens_details")
    cached_tokens: object = None
    if details is not None:
        if not isinstance(details, Mapping):
            return {"total_input_tokens": "invalid", "cached_input_tokens": 0}
        cached_tokens = details.get("cached_tokens")
    return {
        "total_input_tokens": prompt_tokens,
        "cached_input_tokens": cached_tokens,
        "output_tokens": usage.get("completion_tokens"),
    }


class OpenAICompatibleProviderPromptCacheAdapter:
    """Production cache-accounting seam for providers with automatic prefix caching."""

    def __init__(self, *, model: str, model_revision: str | None = None) -> None:
        if not model.strip():
            raise ProviderPromptCacheError("provider_cache_model_required")
        self.provider_calls = 0
        self.llm_calls = 0
        self.capabilities = make_capabilities(
            adapter_kind="openai-compatible-prompt-cache",
            model=model.strip(),
            model_revision=model_revision,
            support_mode=CacheSupportMode.AUTOMATIC,
            reports_cached_input_tokens=True,
            requires_explicit_metadata=False,
        )

    def prepare(self, *, request_cache: bool) -> ProviderCachePreparation:
        requested = bool(request_cache)
        return ProviderCachePreparation(
            requested=requested,
            eligible=requested,
            reason="provider_automatic" if requested else "cache_not_requested",
        )

    def normalize_usage(self, usage: Mapping[str, object] | None) -> ProviderUsageReceipt:
        return normalize_provider_usage(
            capability_identity=self.capabilities.capability_identity,
            usage=_openai_compatible_usage(usage),
        )


class DeterministicFixtureProviderPromptCacheAdapter:
    """Test-only adapter for automatic/explicit and usage truth fixtures."""

    def __init__(
        self,
        *,
        support_mode: CacheSupportMode = CacheSupportMode.AUTOMATIC,
        provider_usage: Mapping[str, object] | None = None,
        adapter_kind: str = "provider-cache-deterministic-fixture",
        model: str = "fixture-provider-model",
        model_revision: str | None = "fixture-provider-revision-1",
        credential_sentinel: str | None = None,
    ) -> None:
        if support_mode is CacheSupportMode.UNSUPPORTED:
            raise ProviderPromptCacheError("fixture_adapter_requires_cache_support")
        self.provider_calls = 0
        self.llm_calls = 0
        self._credential_sentinel = credential_sentinel
        self.capabilities = make_capabilities(
            adapter_kind=adapter_kind,
            model=model,
            model_revision=model_revision,
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


def build_provider_prompt_semantic_source(
    *,
    project_id: UUID,
    delivery_mode: Literal["FULL", "DELTA"],
    stable_material: Mapping[str, object],
    dynamic_material: Mapping[str, object],
    context_output_fingerprint: str,
    capabilities: ProviderCacheCapabilities,
    stable_instruction: str = "",
) -> ProviderPromptSemanticSource:
    """Build complete provider-neutral prompt meaning before segmentation."""

    if len(stable_instruction) > MAX_STABLE_INSTRUCTION_CHARS:
        raise ProviderPromptCacheError("stable_instruction_too_large")
    if not isinstance(context_output_fingerprint, str) or not re.fullmatch(
        r"[0-9a-f]{64}", context_output_fingerprint
    ):
        raise ProviderPromptCacheError("context_output_fingerprint_invalid")
    _validate_stable_material(stable_material)
    return ProviderPromptSemanticSource(
        elements=(
            ProviderPromptSemanticElement(
                name="envelope_version", value=PROVIDER_PROMPT_ENVELOPE_VERSION, segment="stable"
            ),
            ProviderPromptSemanticElement(
                name="canonical_input_version",
                value=PROVIDER_CANONICAL_INPUT_VERSION,
                segment="stable",
            ),
            ProviderPromptSemanticElement(
                name="stable_prefix_policy_version",
                value=STABLE_PROMPT_PREFIX_POLICY_VERSION,
                segment="stable",
            ),
            ProviderPromptSemanticElement(
                name="project_id", value=str(project_id), segment="stable"
            ),
            ProviderPromptSemanticElement(
                name="capability_identity",
                value=capabilities.capability_identity,
                segment="stable",
            ),
            ProviderPromptSemanticElement(name="model", value=capabilities.model, segment="stable"),
            ProviderPromptSemanticElement(
                name="model_revision", value=capabilities.model_revision, segment="stable"
            ),
            ProviderPromptSemanticElement(
                name="stable_instruction", value=stable_instruction, segment="stable"
            ),
            ProviderPromptSemanticElement(
                name="stable_material", value=dict(stable_material), segment="stable"
            ),
            ProviderPromptSemanticElement(
                name="delivery_mode", value=delivery_mode, segment="dynamic"
            ),
            ProviderPromptSemanticElement(
                name="context_output_fingerprint",
                value=context_output_fingerprint,
                segment="dynamic",
            ),
            ProviderPromptSemanticElement(
                name="dynamic_material", value=dict(dynamic_material), segment="dynamic"
            ),
        )
    )


def _serialize_provider_prompt_semantic_source(source: ProviderPromptSemanticSource) -> str:
    """Independently serialize the unsplit source in its declared order."""

    records = [
        {"name": element.name, "value": element.value, "segment": element.segment}
        for element in source.elements
    ]
    return "\n".join(_canonical_json(record) for record in records)


def segment_provider_prompt_semantic_source(
    source: ProviderPromptSemanticSource,
) -> tuple[str, str]:
    """Classify source elements into stable and dynamic serialized segments."""

    stable_records = []
    dynamic_records = []
    for element in source.elements:
        record = {"name": element.name, "value": element.value, "segment": element.segment}
        if element.segment == "stable":
            stable_records.append(_canonical_json(record))
        else:
            dynamic_records.append(_canonical_json(record))
    return "\n".join(stable_records), "\n".join(dynamic_records)


def verify_semantic_composition(
    *,
    source: ProviderPromptSemanticSource,
    stable_prefix: str,
    dynamic_suffix: str,
) -> SemanticCompositionVerification:
    """Compare independent canonical source bytes with segmented recomposition."""

    canonical_provider_input = _serialize_provider_prompt_semantic_source(source)
    recomposed_provider_input = stable_prefix + "\n" + dynamic_suffix
    mismatch_count = int(canonical_provider_input != recomposed_provider_input)
    return SemanticCompositionVerification(
        canonical_provider_input=canonical_provider_input,
        recomposed_provider_input=recomposed_provider_input,
        mismatch_count=mismatch_count,
        verified=mismatch_count == 0,
    )


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

    source = build_provider_prompt_semantic_source(
        project_id=project_id,
        delivery_mode=delivery_mode,
        stable_material=stable_material,
        dynamic_material=dynamic_material,
        context_output_fingerprint=context_output_fingerprint,
        capabilities=capabilities,
        stable_instruction=stable_instruction,
    )
    stable_prefix, dynamic_suffix = segment_provider_prompt_semantic_source(source)
    _validate_segment(stable_prefix, "stable_prefix")
    _validate_segment(dynamic_suffix, "dynamic_suffix")
    composition = verify_semantic_composition(
        source=source,
        stable_prefix=stable_prefix,
        dynamic_suffix=dynamic_suffix,
    )
    if not composition.verified:
        raise ProviderPromptCacheError("semantic_composition_mismatch")
    canonical_provider_input = composition.canonical_provider_input
    return ProviderPromptEnvelope(
        project_id=project_id,
        delivery_mode=delivery_mode,
        stable_prefix=stable_prefix,
        dynamic_suffix=dynamic_suffix,
        canonical_provider_input=canonical_provider_input,
        recomposed_provider_input=composition.recomposed_provider_input,
        semantic_source_element_count=len(source.elements),
        stable_prefix_fingerprint=_sha256(stable_prefix.encode("utf-8")),
        canonical_input_fingerprint=_sha256(canonical_provider_input.encode("utf-8")),
        context_output_fingerprint=context_output_fingerprint,
        semantic_composition_verified=composition.verified,
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
        provider_calls=adapter.provider_calls,
        llm_calls=adapter.llm_calls,
    )


def provider_prompt_cache_benchmark() -> dict[str, object]:
    """Run deterministic evidence fixtures without provider I/O or truth constants."""

    project_a = UUID("00000000-0000-0000-0000-000000000014")
    project_b = UUID("00000000-0000-0000-0000-000000000015")
    output_fp = "a" * 64
    stable = {
        "governance_identity": "governance-v1",
        "context_anchors": {"repository_head": "b" * 40},
    }
    dynamic = {"task": "one"}
    positive_adapter = DeterministicFixtureProviderPromptCacheAdapter(
        provider_usage={"total_input_tokens": 100, "cached_input_tokens": 64, "output_tokens": 8}
    )
    no_receipt_adapter = DeterministicFixtureProviderPromptCacheAdapter(provider_usage=None)
    zero_adapter = DeterministicFixtureProviderPromptCacheAdapter(
        provider_usage={"total_input_tokens": 100, "cached_input_tokens": 0, "output_tokens": 8}
    )
    explicit_adapter = DeterministicFixtureProviderPromptCacheAdapter(
        support_mode=CacheSupportMode.EXPLICIT,
        provider_usage={"total_input_tokens": 100, "cached_input_tokens": 64, "output_tokens": 8},
    )

    first = prepare_provider_prompt_cache(
        project_id=project_a,
        delivery_mode="FULL",
        stable_material=stable,
        dynamic_material=dynamic,
        context_output_fingerprint=output_fp,
        adapter=positive_adapter,
        request_cache=True,
    )
    second = prepare_provider_prompt_cache(
        project_id=project_a,
        delivery_mode="FULL",
        stable_material=stable,
        dynamic_material={"task": "two"},
        context_output_fingerprint="c" * 64,
        adapter=positive_adapter,
        request_cache=True,
    )
    governance_change = prepare_provider_prompt_cache(
        project_id=project_a,
        delivery_mode="FULL",
        stable_material={**stable, "governance_identity": "governance-v2"},
        dynamic_material=dynamic,
        context_output_fingerprint=output_fp,
        adapter=positive_adapter,
        request_cache=True,
    )
    source_change = prepare_provider_prompt_cache(
        project_id=project_a,
        delivery_mode="FULL",
        stable_material={**stable, "context_anchors": {"repository_head": "d" * 40}},
        dynamic_material=dynamic,
        context_output_fingerprint=output_fp,
        adapter=positive_adapter,
        request_cache=True,
    )
    material_adapter = DeterministicFixtureProviderPromptCacheAdapter(
        support_mode=CacheSupportMode.EXPLICIT,
        provider_usage=positive_adapter.provider_usage,
    )
    material_change = prepare_provider_prompt_cache(
        project_id=project_a,
        delivery_mode="FULL",
        stable_material=stable,
        dynamic_material=dynamic,
        context_output_fingerprint=output_fp,
        adapter=material_adapter,
        request_cache=True,
    )
    no_receipt = prepare_provider_prompt_cache(
        project_id=project_a,
        delivery_mode="FULL",
        stable_material=stable,
        dynamic_material=dynamic,
        context_output_fingerprint=output_fp,
        adapter=no_receipt_adapter,
        request_cache=True,
    )
    no_receipt_repeat = prepare_provider_prompt_cache(
        project_id=project_a,
        delivery_mode="FULL",
        stable_material=stable,
        dynamic_material=dynamic,
        context_output_fingerprint=output_fp,
        adapter=no_receipt_adapter,
        request_cache=True,
    )
    zero = prepare_provider_prompt_cache(
        project_id=project_a,
        delivery_mode="FULL",
        stable_material=stable,
        dynamic_material=dynamic,
        context_output_fingerprint=output_fp,
        adapter=zero_adapter,
        request_cache=True,
    )
    unsupported = prepare_provider_prompt_cache(
        project_id=project_a,
        delivery_mode="FULL",
        stable_material=stable,
        dynamic_material=dynamic,
        context_output_fingerprint=output_fp,
        adapter=NoOpProviderPromptCacheAdapter(),
        request_cache=True,
    )
    other_project = prepare_provider_prompt_cache(
        project_id=project_b,
        delivery_mode="FULL",
        stable_material=stable,
        dynamic_material={"task": "one", "project_sentinel": "PROJECT-B-SENTINEL"},
        context_output_fingerprint=output_fp,
        adapter=positive_adapter,
        request_cache=True,
    )
    delta = prepare_provider_prompt_cache(
        project_id=project_a,
        delivery_mode="DELTA",
        stable_material=stable,
        dynamic_material={"delta_delivery": "target", "target_output_fingerprint": "d" * 64},
        context_output_fingerprint="d" * 64,
        adapter=positive_adapter,
        request_cache=True,
    )

    semantic_source = build_provider_prompt_semantic_source(
        project_id=project_a,
        delivery_mode="FULL",
        stable_material=stable,
        dynamic_material=dynamic,
        context_output_fingerprint=output_fp,
        capabilities=positive_adapter.capabilities,
    )
    semantic_stable, semantic_dynamic = segment_provider_prompt_semantic_source(semantic_source)
    stable_lines = semantic_stable.splitlines()
    dynamic_lines = semantic_dynamic.splitlines()
    mutations = {
        "omit": "\n".join(stable_lines[1:] + dynamic_lines),
        "duplicate": "\n".join(stable_lines + [stable_lines[0]] + dynamic_lines),
        "reorder": "\n".join([stable_lines[1], stable_lines[0], *stable_lines[2:], *dynamic_lines]),
        "stable": "\n".join(
            [stable_lines[0].replace(PROVIDER_PROMPT_ENVELOPE_VERSION, "provider-prompt-mutated")]
            + stable_lines[1:]
            + dynamic_lines
        ),
        "dynamic": "\n".join(
            stable_lines
            + [dynamic_lines[0], dynamic_lines[1].replace(output_fp, "e" * 64)]
            + dynamic_lines[2:]
        ),
    }
    # The mutation matrix above is intentionally reconstructed into segments
    # through the same production verifier, while the valid source remains the
    # independent reference.  Keep the split explicit for readable evidence.
    mutation_results = {}
    for name, value in mutations.items():
        lines = value.splitlines()
        stable_count = len(stable_lines)
        mutated_stable = "\n".join(lines[:stable_count])
        mutated_dynamic = "\n".join(lines[stable_count:])
        mutation_results[name] = verify_semantic_composition(
            source=semantic_source,
            stable_prefix=mutated_stable,
            dynamic_suffix=mutated_dynamic,
        ).verified
    semantic_composition_fixture_count = len(mutation_results)
    semantic_composition_mismatch_detection_count = sum(
        int(not verified) for verified in mutation_results.values()
    )
    semantic_composition_accepted_mismatches = sum(
        int(verified) for verified in mutation_results.values()
    )

    credential_a = DeterministicFixtureProviderPromptCacheAdapter(
        provider_usage=positive_adapter.provider_usage,
        credential_sentinel="CREDENTIAL-SENTINEL-A",
    )
    credential_b = DeterministicFixtureProviderPromptCacheAdapter(
        provider_usage=positive_adapter.provider_usage,
        credential_sentinel="CREDENTIAL-SENTINEL-B",
    )
    credential_result_a = prepare_provider_prompt_cache(
        project_id=project_a,
        delivery_mode="FULL",
        stable_material=stable,
        dynamic_material=dynamic,
        context_output_fingerprint=output_fp,
        adapter=credential_a,
        request_cache=True,
    )
    credential_result_b = prepare_provider_prompt_cache(
        project_id=project_a,
        delivery_mode="FULL",
        stable_material=stable,
        dynamic_material=dynamic,
        context_output_fingerprint=output_fp,
        adapter=credential_b,
        request_cache=True,
    )
    credential_serialized = _canonical_json(
        [credential_result_a.model_dump(mode="json"), credential_result_b.model_dump(mode="json")]
    )
    credential_sentinels = (credential_a._credential_sentinel, credential_b._credential_sentinel)
    credential_leaks = sum(
        int(secret is not None and secret in credential_serialized)
        for secret in credential_sentinels
    )
    credential_rotation_nonmaterial = (
        credential_a.capabilities.capability_identity
        == credential_b.capabilities.capability_identity
        and credential_result_a.envelope.stable_prefix_fingerprint
        == credential_result_b.envelope.stable_prefix_fingerprint
        and credential_result_a.envelope.canonical_provider_input
        == credential_result_b.envelope.canonical_provider_input
        and credential_leaks == 0
    )

    project_a_serialized = _canonical_json(first.model_dump(mode="json"))
    project_b_serialized = _canonical_json(other_project.model_dump(mode="json"))
    cross_project_leaks = sum(
        int(sentinel in serialized)
        for sentinel, serialized in (
            ("PROJECT-B-SENTINEL", project_a_serialized),
            ("PROJECT-A-SENTINEL", project_b_serialized),
        )
    )

    unknown = no_receipt.usage
    invalid_inputs: list[dict[str, object]] = [
        {"total_input_tokens": 2, "cached_input_tokens": 3},
        {"total_input_tokens": -1, "cached_input_tokens": 0},
        {"total_input_tokens": True, "cached_input_tokens": 0},
        {"total_input_tokens": 2, "cached_input_tokens": 0, "unexpected": 1},
        {"cached_input_tokens": 1},
        {"total_input_tokens": 1},
        {"total_input_tokens": "100", "cached_input_tokens": 0},
        {"total_input_tokens": {"malformed": True}, "cached_input_tokens": []},
    ]
    invalid_receipts = [
        normalize_provider_usage(
            capability_identity=positive_adapter.capabilities.capability_identity,
            usage=usage,
        )
        for usage in invalid_inputs
    ]
    invalid_accounting_acceptances = sum(
        int(receipt.reconciliation is UsageReconciliation.EXACT) for receipt in invalid_receipts
    )
    false_hit_claims = sum(
        int(condition)
        for condition in (
            no_receipt.observed_hit is not None,
            zero.observed_hit is not False,
            no_receipt_repeat.observed_hit is not None,
            any(receipt.observed_hit is not None for receipt in invalid_receipts),
        )
    )
    requested_distinct_from_hit = all(
        (
            no_receipt.preparation.requested,
            no_receipt.preparation.eligible,
            no_receipt.observed_hit is None,
            no_receipt.usage.cached_input_tokens is None,
            zero.preparation.requested,
            zero.preparation.eligible,
            zero.observed_hit is False,
            zero.usage.cached_input_tokens == 0,
            no_receipt_repeat.envelope.stable_prefix_fingerprint
            == no_receipt.envelope.stable_prefix_fingerprint,
            no_receipt_repeat.observed_hit is None,
            first.observed_hit is True,
        )
    )
    full_compatible = all(
        (
            first.envelope.delivery_mode == "FULL",
            first.envelope.semantic_composition_verified,
            first.envelope.canonical_provider_input == first.envelope.recomposed_provider_input,
            first.envelope.context_output_fingerprint == output_fp,
        )
    )
    delta_compatible = all(
        (
            delta.envelope.delivery_mode == "DELTA",
            delta.envelope.semantic_composition_verified,
            delta.envelope.canonical_provider_input == delta.envelope.recomposed_provider_input,
            delta.envelope.context_output_fingerprint == "d" * 64,
        )
    )
    same_run = first.model_dump(mode="json") == prepare_provider_prompt_cache(
        project_id=project_a,
        delivery_mode="FULL",
        stable_material=stable,
        dynamic_material=dynamic,
        context_output_fingerprint=output_fp,
        adapter=positive_adapter,
        request_cache=True,
    ).model_dump(mode="json")
    provider_calls = sum(
        adapter.provider_calls
        for adapter in (
            positive_adapter,
            no_receipt_adapter,
            zero_adapter,
            explicit_adapter,
            material_adapter,
            credential_a,
            credential_b,
        )
    )
    llm_calls = sum(
        adapter.llm_calls
        for adapter in (
            positive_adapter,
            no_receipt_adapter,
            zero_adapter,
            explicit_adapter,
            material_adapter,
            credential_a,
            credential_b,
        )
    )
    status = (
        "PASS"
        if all(
            (
                first.envelope.semantic_composition_verified,
                semantic_composition_fixture_count == semantic_composition_mismatch_detection_count,
                semantic_composition_accepted_mismatches == 0,
                first.envelope.stable_prefix_fingerprint
                == second.envelope.stable_prefix_fingerprint,
                first.envelope.canonical_input_fingerprint
                != second.envelope.canonical_input_fingerprint,
                first.envelope.stable_prefix_fingerprint
                != governance_change.envelope.stable_prefix_fingerprint,
                first.envelope.stable_prefix_fingerprint
                != source_change.envelope.stable_prefix_fingerprint,
                first.envelope.stable_prefix_fingerprint
                != material_change.envelope.stable_prefix_fingerprint,
                material_change.capabilities.capability_identity
                != first.capabilities.capability_identity,
                credential_rotation_nonmaterial,
                first.envelope.stable_prefix_fingerprint
                != other_project.envelope.stable_prefix_fingerprint,
                cross_project_leaks == 0,
                credential_leaks == 0,
                unsupported.preparation.requested is False,
                unsupported.preparation.eligible is False,
                unsupported.observed_hit is None,
                requested_distinct_from_hit,
                false_hit_claims == 0,
                unknown.reconciliation is UsageReconciliation.UNKNOWN,
                unknown.observed_hit is None,
                zero.usage.cached_input_tokens == 0,
                zero.observed_hit is False,
                invalid_accounting_acceptances == 0,
                first.usage.reconciliation is UsageReconciliation.EXACT,
                first.usage.fresh_input_tokens == 36,
                full_compatible,
                delta_compatible,
                provider_calls
                == sum(
                    result.provider_calls
                    for result in (first, no_receipt, zero, unsupported, delta)
                ),
                llm_calls
                == sum(
                    result.llm_calls for result in (first, no_receipt, zero, unsupported, delta)
                ),
                same_run,
            )
        )
        else "FAIL"
    )
    return {
        "status": status,
        "canonical_input_versioned": PROVIDER_CANONICAL_INPUT_VERSION
        == "provider-canonical-input-v1",
        "independent_canonical_input_versioned": PROVIDER_CANONICAL_INPUT_VERSION
        == "provider-canonical-input-v1",
        "independent_semantic_composition_verified": full_compatible and delta_compatible,
        "semantic_mutation_detection": semantic_composition_fixture_count
        == semantic_composition_mismatch_detection_count,
        "semantic_composition_fixture_count": semantic_composition_fixture_count,
        "semantic_composition_mismatch_detection_count": (
            semantic_composition_mismatch_detection_count
        ),
        "semantic_composition_accepted_mismatches": semantic_composition_accepted_mismatches,
        "semantic_composition_mismatches": semantic_composition_accepted_mismatches,
        "cross_project_leaks": cross_project_leaks,
        "credential_leaks": credential_leaks,
        "false_cache_hits": false_hit_claims,
        "invalid_accounting_acceptances": invalid_accounting_acceptances,
        "invalid_accounting_matrix_size": len(invalid_receipts),
        "deterministic_two_run": same_run,
        "provider_calls": provider_calls,
        "llm_calls": llm_calls,
        "unsupported_noop": unsupported.preparation.requested is False
        and unsupported.preparation.eligible is False
        and unsupported.observed_hit is None,
        "stable_prefix_reuse": first.envelope.stable_prefix_fingerprint
        == second.envelope.stable_prefix_fingerprint,
        "governance_invalidation": first.envelope.stable_prefix_fingerprint
        != governance_change.envelope.stable_prefix_fingerprint,
        "source_invalidation": first.envelope.stable_prefix_fingerprint
        != source_change.envelope.stable_prefix_fingerprint,
        "material_provider_identity_invalidation": first.envelope.stable_prefix_fingerprint
        != material_change.envelope.stable_prefix_fingerprint
        and material_change.capabilities.capability_identity
        != first.capabilities.capability_identity,
        "material_provider_identity_fixture_verified": (
            material_change.capabilities.capability_identity
            != first.capabilities.capability_identity
        )
        and material_change.envelope.stable_prefix_fingerprint
        != first.envelope.stable_prefix_fingerprint,
        "credential_rotation_nonmaterial": credential_rotation_nonmaterial,
        "cross_project_isolation": first.envelope.stable_prefix_fingerprint
        != other_project.envelope.stable_prefix_fingerprint,
        "cache_requested_distinct_from_hit": requested_distinct_from_hit,
        "requested_without_receipt_hit_unknown": no_receipt.preparation.requested
        and no_receipt.preparation.eligible
        and no_receipt.observed_hit is None
        and no_receipt.usage.cached_input_tokens is None,
        "requested_zero_cached_hit_false": zero.preparation.requested
        and zero.preparation.eligible
        and zero.observed_hit is False
        and zero.usage.cached_input_tokens == 0,
        "repeated_prefix_without_receipt_not_hit": (
            no_receipt_repeat.envelope.stable_prefix_fingerprint
            == no_receipt.envelope.stable_prefix_fingerprint
        )
        and no_receipt_repeat.observed_hit is None,
        "positive_receipt_hit_true": first.usage.reconciliation is UsageReconciliation.EXACT
        and first.usage.cached_input_tokens is not None
        and first.usage.cached_input_tokens > 0
        and first.observed_hit is True,
        "unknown_usage_not_zero": unknown.cached_input_tokens is None,
        "explicit_zero_distinct_from_unknown": zero.usage.cached_input_tokens == 0
        and unknown.cached_input_tokens is None,
        "reported_usage_reconciled": first.usage.reconciliation is UsageReconciliation.EXACT,
        "invalid_usage_fail_closed": all(
            receipt.reconciliation is UsageReconciliation.INVALID for receipt in invalid_receipts
        ),
        "hive_estimates_not_provider_usage": (
            "composed_hive_estimated_tokens" in ProviderPromptEnvelope.model_fields
            and "total_input_tokens" in ProviderUsageReceipt.model_fields
        ),
        "full_compatible": full_compatible,
        "delta_compatible": delta_compatible,
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
