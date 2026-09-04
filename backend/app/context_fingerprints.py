"""Deterministic Context Fingerprints and bounded Redis HOT reuse contracts."""

from __future__ import annotations

import hashlib
import json
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

CONTEXT_FINGERPRINT_POLICY_VERSION: Literal["context-fingerprint-v1"] = "context-fingerprint-v1"
CONTEXT_INPUT_SERIALIZATION_VERSION: Literal["context-input-v1"] = "context-input-v1"
CONTEXT_OUTPUT_SERIALIZATION_VERSION: Literal["context-output-v1"] = "context-output-v1"
CONTEXT_CACHE_SCHEMA_VERSION: Literal["context-fingerprint-cache-v1"] = (
    "context-fingerprint-cache-v1"
)
CONTEXT_FINGERPRINT_ALGORITHM: Literal["SHA-256"] = "SHA-256"
CONTEXT_FINGERPRINT_CACHE_TTL_SECONDS = 300
MAX_CONTEXT_FINGERPRINT_CACHE_VALUE_BYTES = 256_000
MAX_SERIALIZED_CONTEXT_CAPSULE_CHARS = 120_000


class ContextFingerprintEvidence(BaseModel):
    """Stable, additive evidence attached to a successful Context Capsule."""

    model_config = ConfigDict(extra="forbid")

    policy_version: Literal["context-fingerprint-v1"] = CONTEXT_FINGERPRINT_POLICY_VERSION
    algorithm: Literal["SHA-256"] = CONTEXT_FINGERPRINT_ALGORITHM
    input_serialization_version: Literal["context-input-v1"] = CONTEXT_INPUT_SERIALIZATION_VERSION
    output_serialization_version: Literal["context-output-v1"] = (
        CONTEXT_OUTPUT_SERIALIZATION_VERSION
    )
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_independent: Literal[True] = True
    llm_calls: Literal[0] = 0
    provider_calls: Literal[0] = 0
    material_identity_classes: list[str] = Field(min_length=1)


class ContextFingerprintCacheEnvelope(BaseModel):
    """Bounded non-canonical Redis value; the capsule is revalidated separately."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["context-fingerprint-cache-v1"] = CONTEXT_CACHE_SCHEMA_VERSION
    project_id: UUID
    task_id: UUID
    context_input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    context_output_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    serialized_capsule: str = Field(
        min_length=2,
        max_length=MAX_SERIALIZED_CONTEXT_CAPSULE_CHARS,
    )


def canonical_json(value: object) -> str:
    """Serialize JSON deterministically without provider or runtime metadata."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _fingerprint(serialization_version: str, value: object) -> str:
    serialized = canonical_json(
        {
            "serialization_version": serialization_version,
            "value": value,
        }
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def context_input_fingerprint(value: object) -> str:
    """Hash the versioned canonical material-input contract."""

    return _fingerprint(CONTEXT_INPUT_SERIALIZATION_VERSION, value)


def context_output_serialization(value: object) -> str:
    """Serialize semantic context while excluding only explicit self-reference."""

    if not isinstance(value, dict):
        raise TypeError("context output must be a mapping")
    semantic = dict(value)
    semantic.pop("context_fingerprint", None)
    return canonical_json(
        {
            "serialization_version": CONTEXT_OUTPUT_SERIALIZATION_VERSION,
            "value": semantic,
        }
    )


def context_output_fingerprint(value: object) -> str:
    """Hash the versioned deterministic semantic-context representation."""

    serialized = context_output_serialization(value)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
