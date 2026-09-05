from __future__ import annotations

import json
from uuid import UUID

import pytest
from pydantic import ValidationError

from app import delta_context
from app.adaptive_token_budget import estimate_tokens
from app.config import Settings
from app.context_fingerprints import (
    ContextFingerprintCacheEnvelope,
    canonical_json,
    context_output_fingerprint,
)
from app.delta_context import (
    CONTEXT_DELIVERY_SCHEMA_VERSION,
    DELTA_CONTEXT_POLICY_VERSION,
    DELTA_SERIALIZATION_VERSION,
    ContextDeliveryProvenance,
    DeltaContextError,
    DeltaOperation,
    apply_patch,
    baseline_pointer_key,
    build_context_delivery,
    build_patch,
    register_delta_baseline,
    resolve_delta_baseline,
    semantic_context_value,
    serialized_delivery_bytes,
    serialized_patch,
)

PROJECT_ID = UUID("00000000-0000-0000-0000-000000000001")
TASK_ID = UUID("00000000-0000-0000-0000-000000000002")
INDEX_ID = UUID("00000000-0000-0000-0000-000000000003")
CORPUS_ID = UUID("00000000-0000-0000-0000-000000000004")
HEAD = "a" * 40


def provenance(output_fingerprint: str) -> ContextDeliveryProvenance:
    return ContextDeliveryProvenance(
        repository_head_sha=HEAD,
        registered_head_sha=HEAD,
        index_run_id=INDEX_ID,
        corpus_run_id=CORPUS_ID,
        target_output_fingerprint=output_fingerprint,
    )


def payload(extra: object = None) -> dict[str, object]:
    return {
        "project": {
            "project_id": str(PROJECT_ID),
            "repository_head_sha": HEAD,
            "registered_head_sha": HEAD,
            "index_run_id": str(INDEX_ID),
            "corpus_run_id": str(CORPUS_ID),
        },
        "task": {"task_id": str(TASK_ID), "project_id": str(PROJECT_ID), "excerpt": "task"},
        "governance": [{"kind": "CHECKPOINT", "text": "governance"}],
        "retrieval": {"results": [{"reference_id": "ref", "corpus_run_id": str(CORPUS_ID)}]},
        "extra": extra if extra is not None else {"stable": True},
    }


def test_patch_supports_add_remove_replace_null_and_deterministic_order() -> None:
    baseline = {"b": 2, "remove": True, "nested": {"old": "x"}}
    target = {"a": None, "b": 3, "nested": {"new": "y"}}

    operations = build_patch(baseline, target)

    assert [item.path for item in operations] == [
        "/remove",
        "/a",
        "/b",
        "/nested/old",
        "/nested/new",
    ]
    assert apply_patch(baseline, operations) == target
    assert operations[1].op == "add"
    assert operations[1].value is None
    assert operations[4].op == "add"
    assert operations[4].value == "y"
    assert json.loads(serialized_patch(operations))["serialization_version"] == (
        DELTA_SERIALIZATION_VERSION
    )


def test_patch_escapes_pointer_tokens_and_reconstructs_arrays_as_whole_values() -> None:
    baseline = {"a/b~c": {"array": [1, 2]}}
    target = {"a/b~c": {"array": [1, 2, 3]}}

    operations = build_patch(baseline, target)

    assert [item.path for item in operations] == ["/a~1b~0c/array"]
    assert apply_patch(baseline, operations) == target


def test_identical_context_has_empty_patch() -> None:
    value = payload({"large": "x" * 2_000})
    assert build_patch(value, value) == []
    assert apply_patch(value, []) == value


@pytest.mark.parametrize(
    "operation",
    [
        {"op": "move", "path": "/x", "value": 1},
        {"op": "replace", "path": "x", "value": 1},
        {"op": "replace", "path": "/x~2y", "value": 1},
        {"op": "remove", "path": "/x", "value": None},
        {"op": "replace", "path": "/x"},
    ],
)
def test_invalid_operations_are_rejected(operation: dict[str, object]) -> None:
    with pytest.raises((ValidationError, DeltaContextError)):
        DeltaOperation.model_validate(operation)


def test_apply_rejects_missing_and_array_item_paths() -> None:
    with pytest.raises(DeltaContextError, match="missing"):
        apply_patch({}, [DeltaOperation(op="replace", path="/missing", value=None)])
    with pytest.raises(DeltaContextError, match="array"):
        apply_patch({"items": [1]}, [DeltaOperation(op="replace", path="/items/0", value=2)])


def test_delivery_uses_context_output_v2_and_strictly_reduces_large_target() -> None:
    baseline = payload({"large": "x" * 5_000, "version": 1})
    target = payload({"large": "x" * 5_000, "version": 2})
    target_fp = context_output_fingerprint(target)

    delivery = build_context_delivery(
        project_id=PROJECT_ID,
        task_id=TASK_ID,
        baseline_output_fingerprint=context_output_fingerprint(baseline),
        baseline_payload=baseline,
        target_payload=target,
        target_full_context=target,
        target_output_fingerprint=target_fp,
        current_provenance=provenance(target_fp),
    )

    assert delivery.schema_version == CONTEXT_DELIVERY_SCHEMA_VERSION
    assert delivery.policy_version == DELTA_CONTEXT_POLICY_VERSION
    assert delivery.mode == "DELTA"
    assert delivery.full_context is None
    assert delivery.reconstruction_verified is True
    assert delivery.target_output_fingerprint_verified is True
    reconstructed = apply_patch(
        semantic_context_value(baseline),
        delivery.patch or [],
    )
    assert reconstructed == semantic_context_value(target)
    assert context_output_fingerprint(reconstructed) == target_fp
    assert delivery.estimated_fresh_context_tokens_avoided > 0


def test_delivery_falls_back_to_full_when_delta_is_not_smaller() -> None:
    baseline = {"value": 1}
    target = {"value": 2}
    target_fp = context_output_fingerprint(target)

    delivery = build_context_delivery(
        project_id=PROJECT_ID,
        task_id=TASK_ID,
        baseline_output_fingerprint=context_output_fingerprint(baseline),
        baseline_payload=baseline,
        target_payload=target,
        target_full_context=target,
        target_output_fingerprint=target_fp,
        current_provenance=provenance(target_fp),
    )

    assert delivery.mode == "FULL"
    assert delivery.full_fallback_reason == "delta_not_smaller"
    assert delivery.full_context == target
    assert delivery.patch is None


def test_final_delivery_bound_uses_exact_serialized_context_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = payload({"large": "x" * 5_000, "version": 1})
    target = payload({"large": "x" * 5_000, "version": 2})
    baseline_fp = context_output_fingerprint(baseline)
    target_fp = context_output_fingerprint(target)
    operations = build_patch(semantic_context_value(baseline), semantic_context_value(target))
    patch_text = serialized_patch(operations)
    metadata = delta_context._delta_delivery_metadata(
        project_id=PROJECT_ID,
        task_id=TASK_ID,
        baseline_output_fingerprint=baseline_fp,
        target_output_fingerprint=target_fp,
        current_provenance=provenance(target_fp),
        patch_text=patch_text,
    )
    metadata_bytes = len(canonical_json(metadata).encode("utf-8"))
    candidate = build_context_delivery(
        project_id=PROJECT_ID,
        task_id=TASK_ID,
        baseline_output_fingerprint=baseline_fp,
        baseline_payload=baseline,
        target_payload=target,
        target_full_context=target,
        target_output_fingerprint=target_fp,
        current_provenance=provenance(target_fp),
    )
    assert candidate.mode == "DELTA"
    final_bytes = len(serialized_delivery_bytes(candidate))
    assert metadata_bytes < final_bytes
    assert len(patch_text) < delta_context.MAX_DELTA_PATCH_CHARS

    monkeypatch.setattr(delta_context, "MAX_DELTA_DELIVERY_BYTES", final_bytes - 1)
    overflow = build_context_delivery(
        project_id=PROJECT_ID,
        task_id=TASK_ID,
        baseline_output_fingerprint=baseline_fp,
        baseline_payload=baseline,
        target_payload=target,
        target_full_context=target,
        target_output_fingerprint=target_fp,
        current_provenance=provenance(target_fp),
    )
    assert overflow.mode == "FULL"
    assert overflow.full_fallback_reason == "delta_delivery_bound_exceeded"
    assert overflow.patch is None
    assert overflow.patch_serialized_characters == len(patch_text)

    monkeypatch.setattr(delta_context, "MAX_DELTA_DELIVERY_BYTES", final_bytes)
    at_boundary_first = build_context_delivery(
        project_id=PROJECT_ID,
        task_id=TASK_ID,
        baseline_output_fingerprint=baseline_fp,
        baseline_payload=baseline,
        target_payload=target,
        target_full_context=target,
        target_output_fingerprint=target_fp,
        current_provenance=provenance(target_fp),
    )
    at_boundary_second = build_context_delivery(
        project_id=PROJECT_ID,
        task_id=TASK_ID,
        baseline_output_fingerprint=baseline_fp,
        baseline_payload=baseline,
        target_payload=target,
        target_full_context=target,
        target_output_fingerprint=target_fp,
        current_provenance=provenance(target_fp),
    )
    assert at_boundary_first.mode == "DELTA"
    assert at_boundary_first.model_dump() == at_boundary_second.model_dump()
    assert serialized_delivery_bytes(at_boundary_first) == serialized_delivery_bytes(
        at_boundary_second
    )


def test_delivery_full_fallback_contract_supports_no_baseline() -> None:
    target = payload({"large": "x" * 2_000})
    target_fp = context_output_fingerprint(target)
    delivery = build_context_delivery(
        project_id=PROJECT_ID,
        task_id=TASK_ID,
        baseline_output_fingerprint=None,
        baseline_payload=target,
        target_payload=target,
        target_full_context=target,
        target_output_fingerprint=target_fp,
        current_provenance=provenance(target_fp),
        force_full_reason="baseline_not_requested",
    )
    assert delivery.mode == "FULL"
    assert delivery.baseline_output_fingerprint is None
    assert delivery.full_fallback_reason == "baseline_not_requested"


class FakeRedis:
    values: dict[str, bytes] = {}

    def set(self, key: str, value: bytes, *, ex: int) -> bool:
        assert ex > 0
        self.values[key] = value
        return True

    def getrange(self, key: str, start: int, end: int) -> bytes | None:
        return self.values.get(key, b"")[: end - start + 1]

    def close(self) -> None:
        return None


def test_baseline_pointer_is_project_task_scoped_and_reuses_existing_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(delta_context, "_cache_client", lambda _settings: fake)
    settings = Settings()
    input_fp = "b" * 64
    output_fp = "c" * 64
    envelope = ContextFingerprintCacheEnvelope(
        project_id=PROJECT_ID,
        task_id=TASK_ID,
        context_input_fingerprint=input_fp,
        context_output_fingerprint=output_fp,
        serialized_capsule="{}",
    )
    fake.values[f"hive:context:cf-v2:{PROJECT_ID}:{input_fp}"] = envelope.model_dump_json().encode()

    assert register_delta_baseline(
        settings,
        project_id=PROJECT_ID,
        task_id=TASK_ID,
        input_fingerprint=input_fp,
        output_fingerprint=output_fp,
        repository_head_sha=HEAD,
    )
    assert baseline_pointer_key(PROJECT_ID, TASK_ID, output_fp) in fake.values
    resolved = resolve_delta_baseline(
        settings,
        project_id=PROJECT_ID,
        task_id=TASK_ID,
        output_fingerprint=output_fp,
    )
    assert resolved is not None
    assert resolved[1].context_output_fingerprint == output_fp
    pointer_text = fake.values[baseline_pointer_key(PROJECT_ID, TASK_ID, output_fp)].decode()
    assert "excerpt" not in pointer_text
    assert "source_text" not in pointer_text


def test_corrupt_or_foreign_baseline_is_not_resolved(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(delta_context, "_cache_client", lambda _settings: fake)
    settings = Settings()
    output_fp = "d" * 64
    key = baseline_pointer_key(PROJECT_ID, TASK_ID, output_fp)
    fake.values[key] = b'{"schema_version":"delta-baseline-v1","project_id":"bad"}'
    assert (
        resolve_delta_baseline(
            settings,
            project_id=PROJECT_ID,
            task_id=TASK_ID,
            output_fingerprint=output_fp,
        )
        is None
    )


def test_delivery_estimator_is_the_existing_provider_independent_estimator() -> None:
    assert estimate_tokens("é") == 1
    assert estimate_tokens("x" * 4) == 1
