from __future__ import annotations

import json
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.context_fingerprints import (
    CONTEXT_FINGERPRINT_CACHE_TTL_SECONDS,
    CONTEXT_FINGERPRINT_POLICY_VERSION,
    CONTEXT_INPUT_SERIALIZATION_VERSION,
    CONTEXT_OUTPUT_SERIALIZATION_VERSION,
    MAX_CONTEXT_FINGERPRINT_CACHE_VALUE_BYTES,
    ContextFingerprintCacheEnvelope,
    ContextFingerprintEvidence,
    canonical_json,
    context_input_fingerprint,
    context_output_fingerprint,
    context_output_serialization,
)


def test_canonical_fingerprint_is_sha256_and_order_independent() -> None:
    first = {"unicode": "café 🙂", "nested": {"b": 2, "a": 1}}
    second = {"nested": {"a": 1, "b": 2}, "unicode": "café 🙂"}

    assert context_input_fingerprint(first) == context_input_fingerprint(second)
    assert len(context_input_fingerprint(first)) == 64
    assert json.loads(canonical_json(first)) == first


def test_material_input_change_changes_fingerprint_without_raw_secret() -> None:
    first = {
        "task": {"task_id": "task-a", "extracted_text_sha256": "a" * 64},
        "rerank": {"profile_identity": "profile-a"},
    }
    second = {
        "task": {"task_id": "task-b", "extracted_text_sha256": "a" * 64},
        "rerank": {"profile_identity": "profile-a"},
    }
    serialized = canonical_json(first)

    assert context_input_fingerprint(first) != context_input_fingerprint(second)
    assert "WO012_PROVIDER_SECRET" not in serialized


def test_output_fingerprint_excludes_only_its_explicit_self_reference() -> None:
    semantic = {
        "project": {"project_id": "project-a"},
        "task": {"task_id": "task-a", "excerpt": "Unicode 🙂 and code"},
        "context_fingerprint": {"output_fingerprint": "old"},
    }

    without_evidence = dict(semantic)
    without_evidence.pop("context_fingerprint")
    assert context_output_fingerprint(semantic) == context_output_fingerprint(without_evidence)
    assert '"serialization_version":"context-output-v1"' in context_output_serialization(semantic)


def test_fingerprint_evidence_is_versioned_provider_independent_and_strict() -> None:
    evidence = ContextFingerprintEvidence(
        input_fingerprint="a" * 64,
        output_fingerprint="b" * 64,
        material_identity_classes=["project-source", "task-provenance"],
    )

    assert evidence.policy_version == CONTEXT_FINGERPRINT_POLICY_VERSION
    assert evidence.input_serialization_version == CONTEXT_INPUT_SERIALIZATION_VERSION
    assert evidence.output_serialization_version == CONTEXT_OUTPUT_SERIALIZATION_VERSION
    assert evidence.provider_independent is True
    assert evidence.llm_calls == 0
    assert evidence.provider_calls == 0
    with pytest.raises(ValidationError):
        ContextFingerprintEvidence.model_validate({**evidence.model_dump(), "unexpected": True})


def test_cache_envelope_is_bounded_versioned_and_rejects_extra_fields() -> None:
    envelope = ContextFingerprintCacheEnvelope(
        project_id=UUID("00000000-0000-0000-0000-000000000001"),
        task_id=UUID("00000000-0000-0000-0000-000000000002"),
        context_input_fingerprint="a" * 64,
        context_output_fingerprint="b" * 64,
        serialized_capsule="{}",
    )

    assert envelope.schema_version == "context-fingerprint-cache-v1"
    assert CONTEXT_FINGERPRINT_CACHE_TTL_SECONDS > 0
    assert len(envelope.model_dump_json().encode("utf-8")) < (
        MAX_CONTEXT_FINGERPRINT_CACHE_VALUE_BYTES
    )
    with pytest.raises(ValidationError):
        ContextFingerprintCacheEnvelope.model_validate(
            {**envelope.model_dump(), "unexpected": True}
        )
