from uuid import UUID

import pytest
from pydantic import ValidationError

from app.memory import (
    MemoryCreateRequest,
    MemoryOrigin,
    MemoryStatus,
    MemoryType,
    PromotionBasis,
    PromotionBasisKind,
    validate_transition,
)

PROJECT_ID = UUID("00000000-0000-0000-0000-000000000001")


def valid_request(**overrides: object) -> MemoryCreateRequest:
    values: dict[str, object] = {
        "type": MemoryType.PROJECT,
        "content": "The project uses a durable PostgreSQL registry.",
        "source": "docs/project-brain/04-ARCHITECTURE.md",
        "authority": "canonical-project-source",
    }
    values.update(overrides)
    return MemoryCreateRequest.model_validate(values)


def test_memory_classes_and_model_output_are_noncanonical() -> None:
    request = valid_request(origin=MemoryOrigin.MODEL)

    assert request.status is MemoryStatus.PROPOSED
    assert request.origin is MemoryOrigin.MODEL
    assert tuple(item.value for item in MemoryType) == (
        "WORKING",
        "SESSION",
        "PROJECT",
        "SEMANTIC",
        "EPISODIC",
        "DECISION",
        "FAILURE",
        "PROCEDURAL",
    )


def test_direct_canonical_and_deprecated_creation_are_rejected() -> None:
    for status in (MemoryStatus.CANONICAL, MemoryStatus.DEPRECATED):
        with pytest.raises(ValidationError):
            valid_request(status=status)


def test_secret_material_is_rejected_and_limits_are_bounded() -> None:
    with pytest.raises(ValidationError):
        valid_request(content="provider response api_key=not-a-real-key")
    with pytest.raises(ValidationError):
        valid_request(tags=["x" * 129])
    with pytest.raises(ValidationError):
        valid_request(source_commit="not-a-sha")


def test_lifecycle_transitions_are_explicit() -> None:
    validate_transition(MemoryStatus.PROPOSED, MemoryStatus.CONFIRMED)
    validate_transition(MemoryStatus.CANONICAL, MemoryStatus.DEPRECATED)
    with pytest.raises(ValueError):
        validate_transition(MemoryStatus.PROPOSED, MemoryStatus.CANONICAL)
    with pytest.raises(ValueError):
        validate_transition(MemoryStatus.DEPRECATED, MemoryStatus.CONFIRMED)


def test_promotion_basis_is_explicit_and_project_bound() -> None:
    basis = PromotionBasis(
        kind=PromotionBasisKind.VALIDATED_EVIDENCE,
        reference="memory-lifecycle integration evidence",
        project_id=PROJECT_ID,
    )

    assert basis.kind is PromotionBasisKind.VALIDATED_EVIDENCE
    assert basis.project_id == PROJECT_ID
    assert basis.reference == "memory-lifecycle integration evidence"
