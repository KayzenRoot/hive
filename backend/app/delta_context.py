"""Bounded, deterministic Delta Context delivery over context-output-v2."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from contextlib import suppress
from typing import Literal, cast
from uuid import UUID

import redis
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from redis.backoff import NoBackoff
from redis.retry import Retry

from .adaptive_token_budget import estimate_tokens
from .config import Settings
from .context_fingerprints import (
    CONTEXT_CACHE_SCHEMA_VERSION,
    CONTEXT_FINGERPRINT_CACHE_TTL_SECONDS,
    CONTEXT_FINGERPRINT_POLICY_VERSION,
    CONTEXT_OUTPUT_SERIALIZATION_VERSION,
    MAX_CONTEXT_FINGERPRINT_CACHE_VALUE_BYTES,
    ContextFingerprintCacheEnvelope,
    canonical_json,
    context_output_fingerprint,
    context_output_serialization,
)

DELTA_CONTEXT_POLICY_VERSION: Literal["delta-context-v1"] = "delta-context-v1"
DELTA_SERIALIZATION_VERSION: Literal["delta-json-patch-v1"] = "delta-json-patch-v1"
CONTEXT_DELIVERY_SCHEMA_VERSION: Literal["context-delivery-v1"] = "context-delivery-v1"
DELTA_BASELINE_SCHEMA_VERSION: Literal["delta-baseline-v1"] = "delta-baseline-v1"
DELTA_BASELINE_KEY_VERSION = "delta-v1"
MAX_DELTA_OPERATIONS = 512
MAX_DELTA_PATCH_CHARS = 24_000
MAX_DELTA_PATH_CHARS = 512
MAX_DELTA_PATH_DEPTH = 16
MAX_DELTA_BASELINE_VALUE_BYTES = 8_192
MAX_DELTA_DELIVERY_CHARS = 24_000
HEX64 = r"^[0-9a-f]{64}$"
HEX40 = r"^[0-9a-f]{40}$"

DeltaMode = Literal["DELTA", "FULL"]


class DeltaContextError(ValueError):
    """A malformed or unsafe delta is rejected before delivery."""


class DeltaOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: Literal["add", "remove", "replace"]
    path: str = Field(max_length=MAX_DELTA_PATH_CHARS)
    value: object | None = None

    @model_validator(mode="after")
    def validate_operation(self) -> DeltaOperation:
        _pointer_tokens(self.path)
        has_value = "value" in self.model_fields_set
        if self.op == "remove" and has_value:
            raise ValueError("remove operation cannot contain value")
        if self.op != "remove" and not has_value:
            raise ValueError("add and replace operations require value, including null")
        return self


class DeltaBaselinePointer(BaseModel):
    """Small Redis pointer to an existing Context Fingerprint cache entry."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["delta-baseline-v1"] = DELTA_BASELINE_SCHEMA_VERSION
    project_id: UUID
    task_id: UUID
    context_input_fingerprint: str = Field(pattern=HEX64)
    context_output_fingerprint: str = Field(pattern=HEX64)
    context_capsule_version: Literal["context-capsule-v1"] = "context-capsule-v1"
    context_fingerprint_policy_version: Literal["context-fingerprint-v2"] = (
        CONTEXT_FINGERPRINT_POLICY_VERSION
    )
    context_output_serialization_version: Literal["context-output-v2"] = (
        CONTEXT_OUTPUT_SERIALIZATION_VERSION
    )
    delta_policy_version: Literal["delta-context-v1"] = DELTA_CONTEXT_POLICY_VERSION
    delta_serialization_version: Literal["delta-json-patch-v1"] = DELTA_SERIALIZATION_VERSION
    repository_head_sha: str = Field(pattern=HEX40)


class ContextDeliveryProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository_head_sha: str = Field(pattern=HEX40)
    registered_head_sha: str = Field(pattern=HEX40)
    index_run_id: UUID
    corpus_run_id: UUID
    target_output_fingerprint: str = Field(pattern=HEX64)


class ContextDelivery(BaseModel):
    """Additive response envelope; DELTA never carries the full target."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["context-delivery-v1"] = CONTEXT_DELIVERY_SCHEMA_VERSION
    policy_version: Literal["delta-context-v1"] = DELTA_CONTEXT_POLICY_VERSION
    serialization_version: Literal["delta-json-patch-v1"] = DELTA_SERIALIZATION_VERSION
    mode: DeltaMode
    project_id: UUID
    task_id: UUID
    baseline_output_fingerprint: str | None = Field(default=None, pattern=HEX64)
    target_output_fingerprint: str = Field(pattern=HEX64)
    target_semantic_serialization_version: Literal["context-output-v2"] = (
        CONTEXT_OUTPUT_SERIALIZATION_VERSION
    )
    reconstruction_verified: bool
    target_output_fingerprint_verified: bool
    full_fallback_reason: str | None = Field(default=None, max_length=64)
    current_provenance: ContextDeliveryProvenance
    patch: list[DeltaOperation] | None = None
    full_context: dict[str, object] | None = None
    delta_estimated_tokens: int = Field(ge=0)
    full_estimated_tokens: int = Field(ge=0)
    estimated_fresh_context_tokens_avoided: int = Field(ge=0)
    patch_operation_count: int = Field(ge=0, le=MAX_DELTA_OPERATIONS)
    patch_serialized_characters: int = Field(ge=0, le=MAX_DELTA_PATCH_CHARS)

    @model_validator(mode="after")
    def validate_mode_contract(self) -> ContextDelivery:
        if self.mode == "DELTA":
            if self.baseline_output_fingerprint is None:
                raise ValueError("DELTA requires a baseline output fingerprint")
            if self.patch is None or self.full_context is not None:
                raise ValueError("DELTA requires patch and forbids full context")
            if self.full_fallback_reason is not None:
                raise ValueError("DELTA cannot contain a fallback reason")
            if not self.reconstruction_verified or not self.target_output_fingerprint_verified:
                raise ValueError("DELTA requires verified reconstruction and target fingerprint")
        else:
            if self.full_context is None or self.patch is not None:
                raise ValueError("FULL requires full context and forbids patch")
            if not self.full_fallback_reason:
                raise ValueError("FULL requires a bounded fallback reason")
            if self.reconstruction_verified:
                raise ValueError("FULL cannot claim delta reconstruction")
        if self.patch_operation_count != len(self.patch or []):
            raise ValueError("patch operation count mismatch")
        return self


def _pointer_tokens(path: str) -> tuple[str, ...]:
    if not isinstance(path, str) or len(path) > MAX_DELTA_PATH_CHARS:
        raise DeltaContextError("delta_path_bound_exceeded")
    if path == "":
        return ()
    if not path.startswith("/"):
        raise DeltaContextError("delta_path_malformed")
    parts: list[str] = []
    for raw in path[1:].split("/"):
        index = 0
        decoded: list[str] = []
        while index < len(raw):
            char = raw[index]
            if char != "~":
                decoded.append(char)
                index += 1
                continue
            if index + 1 >= len(raw) or raw[index + 1] not in {"0", "1"}:
                raise DeltaContextError("delta_pointer_escape_invalid")
            decoded.append("~" if raw[index + 1] == "0" else "/")
            index += 2
        parts.append("".join(decoded))
    if len(parts) > MAX_DELTA_PATH_DEPTH:
        raise DeltaContextError("delta_path_depth_exceeded")
    return tuple(parts)


def _escape_pointer_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def semantic_context_value(value: object) -> dict[str, object]:
    """Return the exact value hashed by the existing context-output-v2 seam."""

    try:
        serialized = context_output_serialization(value)
        envelope = json.loads(serialized)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise DeltaContextError("delta_semantic_payload_invalid") from exc
    semantic = envelope.get("value") if isinstance(envelope, dict) else None
    if not isinstance(semantic, dict):
        raise DeltaContextError("delta_semantic_payload_invalid")
    return semantic


def _diff_values(baseline: object, target: object, path: str, output: list[DeltaOperation]) -> None:
    if len(output) > MAX_DELTA_OPERATIONS:
        raise DeltaContextError("delta_operation_bound_exceeded")
    if isinstance(baseline, dict) and isinstance(target, dict):
        baseline_keys = set(baseline)
        target_keys = set(target)
        for key in sorted(baseline_keys - target_keys):
            child = f"{path}/{_escape_pointer_token(str(key))}"
            output.append(DeltaOperation(op="remove", path=child))
        for key in sorted(target_keys - baseline_keys):
            child = f"{path}/{_escape_pointer_token(str(key))}"
            output.append(DeltaOperation(op="add", path=child, value=copy.deepcopy(target[key])))
        for key in sorted(baseline_keys & target_keys):
            child = f"{path}/{_escape_pointer_token(str(key))}"
            _diff_values(baseline[key], target[key], child, output)
        return
    if isinstance(baseline, list) and isinstance(target, list) and baseline == target:
        return
    if baseline == target:
        return
    output.append(DeltaOperation(op="replace", path=path, value=copy.deepcopy(target)))


def build_patch(
    baseline: Mapping[str, object], target: Mapping[str, object]
) -> list[DeltaOperation]:
    operations: list[DeltaOperation] = []
    _diff_values(dict(baseline), dict(target), "", operations)
    if len(operations) > MAX_DELTA_OPERATIONS:
        raise DeltaContextError("delta_operation_bound_exceeded")
    serialized_patch(operations)
    return operations


def _parent_and_key(document: object, tokens: tuple[str, ...]) -> tuple[dict[str, object], str]:
    if not tokens:
        raise DeltaContextError("delta_root_operation_unsupported")
    current = document
    for token in tokens[:-1]:
        if not isinstance(current, dict) or token not in current:
            raise DeltaContextError("delta_path_missing")
        current = current[token]
        if isinstance(current, list):
            raise DeltaContextError("delta_array_item_operation_unsupported")
    if not isinstance(current, dict):
        raise DeltaContextError("delta_parent_not_object")
    return current, tokens[-1]


def apply_patch(
    baseline: Mapping[str, object], operations: Sequence[DeltaOperation]
) -> dict[str, object]:
    if len(operations) > MAX_DELTA_OPERATIONS:
        raise DeltaContextError("delta_operation_bound_exceeded")
    document: object = copy.deepcopy(dict(baseline))
    for operation in operations:
        parsed = (
            operation
            if isinstance(operation, DeltaOperation)
            else DeltaOperation.model_validate(operation)
        )
        tokens = _pointer_tokens(parsed.path)
        if not tokens:
            if parsed.op != "replace" or not isinstance(parsed.value, dict):
                raise DeltaContextError("delta_root_replace_requires_object")
            document = copy.deepcopy(parsed.value)
            continue
        parent, key = _parent_and_key(document, tokens)
        if parsed.op == "add":
            if key in parent:
                raise DeltaContextError("delta_add_path_exists")
            parent[key] = copy.deepcopy(parsed.value)
        elif parsed.op == "remove":
            if key not in parent:
                raise DeltaContextError("delta_remove_path_missing")
            del parent[key]
        else:
            if key not in parent:
                raise DeltaContextError("delta_replace_path_missing")
            parent[key] = copy.deepcopy(parsed.value)
    if not isinstance(document, dict):
        raise DeltaContextError("delta_result_not_object")
    return document


def serialized_patch(operations: Sequence[DeltaOperation]) -> str:
    if len(operations) > MAX_DELTA_OPERATIONS:
        raise DeltaContextError("delta_operation_bound_exceeded")
    payload = {
        "serialization_version": DELTA_SERIALIZATION_VERSION,
        "operations": [item.model_dump(mode="json", exclude_unset=True) for item in operations],
    }
    serialized = canonical_json(payload)
    if len(serialized) > MAX_DELTA_PATCH_CHARS:
        raise DeltaContextError("delta_patch_bound_exceeded")
    return serialized


def _cache_client(settings: Settings) -> redis.Redis:
    return redis.Redis.from_url(
        settings.redis_url,
        decode_responses=False,
        socket_connect_timeout=0.2,
        socket_timeout=0.2,
        retry_on_timeout=False,
        retry=Retry(NoBackoff(), retries=0),
    )


def baseline_pointer_key(project_id: UUID, task_id: UUID, output_fingerprint: str) -> str:
    if not isinstance(output_fingerprint, str) or len(output_fingerprint) != 64:
        raise DeltaContextError("delta_baseline_fingerprint_invalid")
    return (
        f"hive:context-baseline:{DELTA_BASELINE_KEY_VERSION}:"
        f"{project_id}:{task_id}:{output_fingerprint}"
    )


def _context_cache_key(project_id: UUID, input_fingerprint: str) -> str:
    return f"hive:context:cf-v2:{project_id}:{input_fingerprint}"


def register_delta_baseline(
    settings: Settings,
    *,
    project_id: UUID,
    task_id: UUID,
    input_fingerprint: str,
    output_fingerprint: str,
    repository_head_sha: str,
) -> bool:
    try:
        pointer = DeltaBaselinePointer(
            project_id=project_id,
            task_id=task_id,
            context_input_fingerprint=input_fingerprint,
            context_output_fingerprint=output_fingerprint,
            repository_head_sha=repository_head_sha.lower(),
        )
        encoded = pointer.model_dump_json().encode("utf-8")
        if len(encoded) > MAX_DELTA_BASELINE_VALUE_BYTES:
            return False
        client = _cache_client(settings)
        try:
            return bool(
                client.set(
                    baseline_pointer_key(project_id, task_id, output_fingerprint),
                    encoded,
                    ex=CONTEXT_FINGERPRINT_CACHE_TTL_SECONDS,
                )
            )
        finally:
            with suppress(redis.RedisError, OSError):
                client.close()  # type: ignore[no-untyped-call]
    except (redis.RedisError, OSError, TypeError, ValueError, ValidationError):
        return False


def resolve_delta_baseline(
    settings: Settings,
    *,
    project_id: UUID,
    task_id: UUID,
    output_fingerprint: str,
) -> tuple[DeltaBaselinePointer, ContextFingerprintCacheEnvelope] | None:
    try:
        key = baseline_pointer_key(project_id, task_id, output_fingerprint)
    except DeltaContextError:
        return None
    client = _cache_client(settings)
    try:
        raw_pointer = cast(bytes | None, client.getrange(key, 0, MAX_DELTA_BASELINE_VALUE_BYTES))
        if not raw_pointer or len(raw_pointer) > MAX_DELTA_BASELINE_VALUE_BYTES:
            return None
        pointer = DeltaBaselinePointer.model_validate_json(raw_pointer)
        if (
            pointer.project_id != project_id
            or pointer.task_id != task_id
            or pointer.context_output_fingerprint != output_fingerprint
        ):
            return None
        raw_cache = cast(
            bytes | None,
            client.getrange(
                _context_cache_key(project_id, pointer.context_input_fingerprint),
                0,
                MAX_CONTEXT_FINGERPRINT_CACHE_VALUE_BYTES,
            ),
        )
    except (redis.RedisError, OSError, ValidationError, ValueError, TypeError):
        return None
    finally:
        with suppress(redis.RedisError, OSError):
            client.close()  # type: ignore[no-untyped-call]
    if not raw_cache or len(raw_cache) > MAX_CONTEXT_FINGERPRINT_CACHE_VALUE_BYTES:
        return None
    try:
        envelope = ContextFingerprintCacheEnvelope.model_validate_json(raw_cache)
    except (ValidationError, ValueError, TypeError):
        return None
    if (
        envelope.schema_version != CONTEXT_CACHE_SCHEMA_VERSION
        or envelope.project_id != project_id
        or envelope.task_id != task_id
        or envelope.context_input_fingerprint != pointer.context_input_fingerprint
        or envelope.context_output_fingerprint != pointer.context_output_fingerprint
    ):
        return None
    return pointer, envelope


def delivery_size_tokens(delivery_metadata: Mapping[str, object]) -> int:
    return estimate_tokens(canonical_json(dict(delivery_metadata)))


def build_context_delivery(
    *,
    project_id: UUID,
    task_id: UUID,
    baseline_output_fingerprint: str | None,
    baseline_payload: Mapping[str, object],
    target_payload: Mapping[str, object],
    target_full_context: Mapping[str, object],
    target_output_fingerprint: str,
    current_provenance: ContextDeliveryProvenance,
    force_full_reason: str | None = None,
) -> ContextDelivery:
    baseline_semantic = semantic_context_value(baseline_payload)
    target_semantic = semantic_context_value(target_payload)
    full_serialization = context_output_serialization(target_payload)
    full_estimate = estimate_tokens(full_serialization)
    if force_full_reason is not None:
        return _full_delivery(
            project_id=project_id,
            task_id=task_id,
            baseline_output_fingerprint=baseline_output_fingerprint,
            target_full_context=target_full_context,
            target_output_fingerprint=target_output_fingerprint,
            current_provenance=current_provenance,
            full_estimate=full_estimate,
            reason=force_full_reason,
        )
    try:
        operations = build_patch(baseline_semantic, target_semantic)
        patch_text = serialized_patch(operations)
        reconstructed = apply_patch(baseline_semantic, operations)
        reconstruction_verified = reconstructed == target_semantic
        target_fp_verified = context_output_fingerprint(reconstructed) == target_output_fingerprint
        metadata = {
            "schema_version": CONTEXT_DELIVERY_SCHEMA_VERSION,
            "policy_version": DELTA_CONTEXT_POLICY_VERSION,
            "serialization_version": DELTA_SERIALIZATION_VERSION,
            "mode": "DELTA",
            "project_id": str(project_id),
            "task_id": str(task_id),
            "baseline_output_fingerprint": baseline_output_fingerprint,
            "target_output_fingerprint": target_output_fingerprint,
            "target_semantic_serialization_version": CONTEXT_OUTPUT_SERIALIZATION_VERSION,
            "patch": json.loads(patch_text),
            "current_provenance": current_provenance.model_dump(mode="json"),
        }
        delta_estimate = delivery_size_tokens(metadata)
        if not reconstruction_verified or not target_fp_verified:
            reason = "reconstruction_failed"
        elif delta_estimate >= full_estimate:
            reason = "delta_not_smaller"
        elif len(patch_text) > MAX_DELTA_PATCH_CHARS:
            reason = "delta_patch_bound_exceeded"
        elif len(canonical_json(metadata)) > MAX_DELTA_DELIVERY_CHARS:
            reason = "delta_delivery_bound_exceeded"
        else:
            return ContextDelivery(
                mode="DELTA",
                project_id=project_id,
                task_id=task_id,
                baseline_output_fingerprint=baseline_output_fingerprint,
                target_output_fingerprint=target_output_fingerprint,
                reconstruction_verified=True,
                target_output_fingerprint_verified=True,
                current_provenance=current_provenance,
                patch=operations,
                delta_estimated_tokens=delta_estimate,
                full_estimated_tokens=full_estimate,
                estimated_fresh_context_tokens_avoided=full_estimate - delta_estimate,
                patch_operation_count=len(operations),
                patch_serialized_characters=len(patch_text),
            )
    except DeltaContextError as exc:
        reason = exc.args[0] if exc.args else "delta_invalid"
        delta_estimate = 0
        operations = []
        patch_text = ""
    return _full_delivery(
        project_id=project_id,
        task_id=task_id,
        baseline_output_fingerprint=baseline_output_fingerprint,
        target_full_context=target_full_context,
        target_output_fingerprint=target_output_fingerprint,
        current_provenance=current_provenance,
        full_estimate=full_estimate,
        reason=str(reason)[:64],
        delta_estimate=delta_estimate,
        patch_serialized_characters=len(patch_text),
    )


def _full_delivery(
    *,
    project_id: UUID,
    task_id: UUID,
    baseline_output_fingerprint: str | None,
    target_full_context: Mapping[str, object],
    target_output_fingerprint: str,
    current_provenance: ContextDeliveryProvenance,
    full_estimate: int,
    reason: str,
    delta_estimate: int = 0,
    patch_serialized_characters: int = 0,
) -> ContextDelivery:
    return ContextDelivery(
        mode="FULL",
        project_id=project_id,
        task_id=task_id,
        baseline_output_fingerprint=baseline_output_fingerprint,
        target_output_fingerprint=target_output_fingerprint,
        reconstruction_verified=False,
        target_output_fingerprint_verified=True,
        full_fallback_reason=str(reason)[:64],
        current_provenance=current_provenance,
        full_context=dict(target_full_context),
        delta_estimated_tokens=delta_estimate,
        full_estimated_tokens=full_estimate,
        estimated_fresh_context_tokens_avoided=0,
        patch_operation_count=0,
        patch_serialized_characters=patch_serialized_characters,
    )
