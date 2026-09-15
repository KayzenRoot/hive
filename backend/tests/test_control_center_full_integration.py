from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

SCRIPT_PATH = Path(__file__).parents[2] / "scripts" / "control_center_full_integration.py"


def load_integration_script() -> Any:
    """Load the stand-alone evidence script without pulling it into the static import graph."""

    spec = importlib.util.spec_from_file_location(
        "wo022_control_center_full_integration", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(Any, module)


full_integration = load_integration_script()

PROJECT_ID = UUID("00000000-0000-0000-0000-0000000000aa")


def governance_documents() -> list[dict[str, object]]:
    return [
        {
            "path": path,
            "status": "AVAILABLE",
            "byte_count": 100,
            "source": f"git:HEAD-blob:{path}",
        }
        for path in (
            "docs/project-brain/13-CHECKPOINT.md",
            "docs/project-brain/03-SCOPE.md",
            "docs/project-brain/15-DEFINITION-OF-DONE.md",
        )
    ]


def canonical_checkpoint() -> dict[str, object]:
    return {
        "current_status": "FIXTURE CONTROL CENTER ACTIVE",
        "in_progress": ["Verify bounded project intelligence"],
        "pending": {
            "count": 2,
            "summary": "2 pending item(s)",
            "items": ["Fixture follow-up", "Fixture audit"],
        },
        "next_step": "Publish the next bounded fixture result.",
        "source": "git:HEAD-blob:docs/project-brain/13-CHECKPOINT.md",
        "provenance": "EXACT",
    }


def available_payload() -> dict[str, object]:
    return {
        "project_id": str(PROJECT_ID),
        "capabilities": [
            {
                "id": "checkpoint-scope-dod",
                "status": "AVAILABLE",
                "summary": (
                    "canonical checkpoint, scope and Definition of Done content is visible from "
                    "the project-relative Git HEAD blobs"
                ),
                "provenance": "EXACT",
                "details": {
                    "status": "AVAILABLE",
                    "provenance": "EXACT",
                    "documents": governance_documents(),
                    "checkpoint": canonical_checkpoint(),
                    "scope": {
                        "summary": "NECESSARY — V0.1: 2 required item(s)",
                        "required_items_count": 2,
                        "required_items": ["Full HIVE Control Center.", "Bounded fixture scope."],
                        "source": "git:HEAD-blob:docs/project-brain/03-SCOPE.md",
                        "provenance": "EXACT",
                    },
                    "definition_of_done": {
                        "status": "AVAILABLE",
                        "total_count": 2,
                        "completed_count": 1,
                        "percentage": 50.0,
                        "percentage_status": "AVAILABLE",
                    },
                    "source": "git:HEAD-blob:canonical-project-brain",
                },
            }
        ],
    }


def unavailable_payload(document: str) -> dict[str, object]:
    return {
        "project_id": str(PROJECT_ID),
        "capabilities": [
            {
                "id": "checkpoint-scope-dod",
                "status": "UNAVAILABLE",
                "summary": (
                    "canonical checkpoint, scope and Definition of Done content is UNAVAILABLE "
                    "because a mandatory governance section is missing or malformed in the "
                    "project-relative Git HEAD blobs"
                ),
                "provenance": "UNAVAILABLE",
                "details": {
                    "status": "UNAVAILABLE",
                    "provenance": "UNAVAILABLE",
                    "reason": (
                        "canonical Git HEAD blob parsing is unavailable for "
                        f"docs/project-brain/{document}"
                    ),
                    "documents": governance_documents(),
                    "source": "git:HEAD-blob:canonical-project-brain",
                },
            }
        ],
    }


class StubProbe:
    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self.payloads = payloads

    def request(self, _method: str, _path: str, **_kwargs: object) -> dict[str, object]:
        return self.payloads.pop(0)


def stub_fixture(
    _probe: object,
    _fixtures: list[object],
    _label: str,
    _document: str,
    _content: str,
) -> Any:
    return full_integration.Fixture(
        label="stub-fixture",
        relative_path="stub-fixture",
        repository=Path("stub-fixture"),
        project_id=PROJECT_ID,
    )


def test_canonical_governance_payload_is_accepted() -> None:
    assert full_integration.verify_canonical_governance(available_payload()) is True


def test_canonical_governance_rejects_a_vanished_mandatory_section() -> None:
    payload = available_payload()
    details = cast(dict[str, object], _capability(payload)["details"])
    checkpoint = cast(dict[str, object], details["checkpoint"])
    del checkpoint["pending"]

    with pytest.raises(AssertionError, match="mandatory section"):
        full_integration.verify_canonical_governance(payload)


def test_canonical_governance_rejects_fabricated_zero_counts() -> None:
    for field, replacement in (
        ("pending", {"count": 0, "summary": "0 pending item(s)", "items": []}),
        ("scope", {"required_items_count": 0, "required_items": []}),
    ):
        payload = available_payload()
        details = cast(dict[str, object], _capability(payload)["details"])
        if field == "scope":
            details["scope"] = replacement
        else:
            checkpoint = cast(dict[str, object], details["checkpoint"])
            checkpoint["pending"] = replacement

        with pytest.raises(AssertionError, match="not truthful|not visible"):
            full_integration.verify_canonical_governance(payload)


def test_missing_sections_fail_closed_verification_accepts_fail_closed_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(full_integration, "create_fail_closed_fixture", stub_fixture)
    probe = StubProbe(
        [unavailable_payload(entry[3]) for entry in full_integration.FAIL_CLOSED_FIXTURES]
    )

    assert full_integration.verify_missing_sections_fail_closed(probe, []) is True


def test_missing_sections_fail_closed_verification_rejects_available_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(full_integration, "create_fail_closed_fixture", stub_fixture)
    probe = StubProbe([available_payload() for _entry in full_integration.FAIL_CLOSED_FIXTURES])

    with pytest.raises(AssertionError, match="observable data"):
        full_integration.verify_missing_sections_fail_closed(probe, [])


def test_fail_closed_fixtures_cover_checkpoint_and_scope_documents() -> None:
    assert {entry[1] for entry in full_integration.FAIL_CLOSED_FIXTURES} == {
        full_integration.CHECKPOINT_DOCUMENT,
        full_integration.SCOPE_DOCUMENT,
    }


def test_missing_pending_fixture_removes_only_that_mandatory_section() -> None:
    label, document, content, marker = full_integration.FAIL_CLOSED_FIXTURES[0]

    assert label == "missing-pending"
    assert document == full_integration.CHECKPOINT_DOCUMENT
    assert marker in document
    assert "## PENDING" not in content
    for heading in full_integration.MANDATORY_CHECKPOINT_SECTIONS:
        if heading != "PENDING":
            assert f"## {heading}\n" in content


def test_missing_scope_fixture_drops_the_canonical_scope_heading() -> None:
    label, document, content, marker = full_integration.FAIL_CLOSED_FIXTURES[1]

    assert label == "missing-scope"
    assert document == full_integration.SCOPE_DOCUMENT
    assert marker in document
    assert full_integration.MANDATORY_SCOPE_SECTION not in content


def _capability(payload: dict[str, object]) -> dict[str, object]:
    capabilities = cast(list[dict[str, object]], payload["capabilities"])
    return capabilities[0]
