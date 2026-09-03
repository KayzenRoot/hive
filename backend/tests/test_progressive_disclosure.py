from __future__ import annotations

from uuid import UUID

import pytest

from app import context_manager
from app.config import Settings
from app.progressive_disclosure import (
    DISCLOSURE_LEVEL_SEMANTICS,
    DisclosureConsistencyError,
    DisclosureInputError,
    DisclosureLevel,
    apply_disclosure,
    decide_disclosure,
    disclosure_level_bound,
    parse_disclosure_level,
    required_level_from_text,
    starting_level,
)
from tests.test_context_manager import (
    candidate,
    governance_documents,
    patch_build_dependencies,
    repository_snapshot,
    source_state,
    task_text_response,
)

PROJECT_ID = UUID("00000000-0000-0000-0000-000000000001")
TASK_ID = UUID("00000000-0000-0000-0000-000000000003")


def test_levels_match_canonical_semantics_exactly() -> None:
    assert tuple(level.value for level in DisclosureLevel) == (
        "L0",
        "L1",
        "L2",
        "L3",
        "L4",
        "L5",
    )
    assert DISCLOSURE_LEVEL_SEMANTICS == {
        DisclosureLevel.L0: "Project capsule",
        DisclosureLevel.L1: "Module summaries",
        DisclosureLevel.L2: "Symbol signatures and dependency metadata",
        DisclosureLevel.L3: "Relevant implementation excerpts",
        DisclosureLevel.L4: "Complete file",
        DisclosureLevel.L5: "Repository-wide investigation",
    }


def test_invalid_disclosure_level_is_rejected() -> None:
    with pytest.raises(DisclosureInputError, match="invalid_disclosure_level"):
        parse_disclosure_level("L6")
    with pytest.raises(DisclosureInputError, match="invalid_disclosure_level"):
        parse_disclosure_level("deep")
    with pytest.raises(DisclosureInputError, match="invalid_disclosure_level"):
        parse_disclosure_level(3)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Inspect the current project checkpoint only.", DisclosureLevel.L0),
        ("Need module summaries for the service.", DisclosureLevel.L1),
        ("Include src/context.py provenance.", DisclosureLevel.L1),
        ("Need symbol signatures for TargetContextService.build_context.", DisclosureLevel.L2),
        ("Include the implementation excerpt for build_context.", DisclosureLevel.L3),
        ("Return the complete file src/context.py.", DisclosureLevel.L4),
        ("Perform a repository-wide investigation of all tracked files.", DisclosureLevel.L5),
    ],
)
def test_required_level_mapping(text: str, expected: DisclosureLevel) -> None:
    assert required_level_from_text(text) == expected


def test_starting_level_ignores_acceptance_until_escalation() -> None:
    task_text = (
        "# Task\nInspect the project checkpoint.\n\n"
        "## Acceptance Criteria\n- Include the implementation excerpt for build_context.\n"
    )
    assert starting_level("Inspect project state", [], task_text) == DisclosureLevel.L0
    start, final, path = decide_disclosure(
        title="Inspect project state",
        constraints=[],
        acceptance_criteria=["- Include the implementation excerpt for build_context."],
        task_text=task_text,
        files=[],
        symbols=[],
        tests=[],
    )
    assert start == DisclosureLevel.L0
    assert final == DisclosureLevel.L3
    assert [item.reason for item in path] == [
        "required_module_unresolved",
        "required_symbol_unresolved",
        "acceptance_requires_implementation_excerpt",
    ]
    assert path[0].from_level == DisclosureLevel.L0
    assert path[-1].to_level == DisclosureLevel.L3


def test_lower_level_sufficient_has_no_escalation() -> None:
    start, final, path = decide_disclosure(
        title="Inspect project checkpoint",
        constraints=["- Use only the target project's canonical governance."],
        acceptance_criteria=["- Report current project state."],
        task_text="# Task\nInspect project checkpoint.\n",
        files=[],
        symbols=[],
        tests=[],
    )
    assert start == DisclosureLevel.L0
    assert final == DisclosureLevel.L0
    assert path == []


def test_cannot_escalate_past_l5() -> None:
    start, final, path = decide_disclosure(
        title="Repository-wide investigation of all tracked files",
        constraints=[],
        acceptance_criteria=["- Perform a repository-wide investigation."],
        task_text="Repository-wide investigation of all tracked files.\n",
        files=[],
        symbols=[],
        tests=[],
    )
    assert start == DisclosureLevel.L5
    assert final == DisclosureLevel.L5
    assert path == []


def test_fixed_per_level_bounds_are_explicit() -> None:
    l0 = disclosure_level_bound(DisclosureLevel.L0)
    l3 = disclosure_level_bound(DisclosureLevel.L3)
    l5 = disclosure_level_bound(DisclosureLevel.L5)
    assert l0.max_modules == 0
    assert l0.max_excerpts == 0
    assert l3.max_excerpts == 5
    assert l3.max_excerpt_characters == 800
    assert l5.max_inventory_entries == 20


def test_l4_complete_file_and_l5_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documents = governance_documents()
    documents["src/context.py"] = "def build_context():\n    return True\n"
    patch_build_dependencies(
        monkeypatch,
        state=source_state(documents),
        extracted=task_text_response(
            "# Task\n\n## Constraints\n- Keep source order.\n\n"
            "## Acceptance Criteria\n- Return the complete file src/context.py.\n"
        ),
    )

    capsule = context_manager.build_context(Settings(), PROJECT_ID, TASK_ID)

    assert capsule.progressive_disclosure.final_level == DisclosureLevel.L4
    assert capsule.complete_files[0].path == "src/context.py"
    assert "def build_context" in capsule.complete_files[0].text


def test_l5_repository_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_build_dependencies(
        monkeypatch,
        extracted=task_text_response(
            "Perform a repository-wide investigation of all tracked files.\n\n"
            "## Acceptance Criteria\n- Perform a repository-wide investigation.\n"
        ),
    )

    capsule = context_manager.build_context(Settings(), PROJECT_ID, TASK_ID)

    assert capsule.progressive_disclosure.starting_level == DisclosureLevel.L5
    assert capsule.progressive_disclosure.final_level == DisclosureLevel.L5
    assert capsule.inventory
    assert capsule.progressive_disclosure.escalated is False


def test_l1_and_l2_cases(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_build_dependencies(
        monkeypatch,
        extracted=task_text_response("Need module summaries for the service.\n"),
    )
    l1 = context_manager.build_context(Settings(), PROJECT_ID, TASK_ID)
    assert l1.progressive_disclosure.final_level == DisclosureLevel.L1
    assert l1.symbols == []
    assert all(result.snippet == "" for result in l1.retrieval.results)

    patch_build_dependencies(
        monkeypatch,
        extracted=task_text_response(
            "Need symbol signatures for TargetContextService.build_context.\n"
        ),
    )
    l2 = context_manager.build_context(Settings(), PROJECT_ID, TASK_ID)
    assert l2.progressive_disclosure.final_level == DisclosureLevel.L2
    assert l2.symbols
    assert all(result.snippet == "" for result in l2.retrieval.results)


def test_two_run_disclosure_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_build_dependencies(
        monkeypatch,
        extracted=task_text_response(
            "# Task\nInspect project state.\n\n"
            "## Acceptance Criteria\n- Include the implementation excerpt for build_context.\n"
        ),
    )
    first = context_manager.build_context(Settings(), PROJECT_ID, TASK_ID)
    second = context_manager.build_context(Settings(), PROJECT_ID, TASK_ID)
    assert first.progressive_disclosure.model_dump() == second.progressive_disclosure.model_dump()
    assert first.model_dump() == second.model_dump()
    assert first.progressive_disclosure.llm_calls == 0
    assert first.progressive_disclosure.adaptive_token_budget_implemented is False


def test_cross_project_disclosure_path_fails_closed() -> None:
    snapshot = repository_snapshot()
    with pytest.raises(DisclosureConsistencyError, match="cross_project_disclosure_evidence"):
        apply_disclosure(
            title="Complete file",
            constraints=[],
            acceptance_criteria=["- Return the complete file other/secret.py."],
            task_text="Return the complete file other/secret.py.",
            files=[],
            symbols=[],
            tests=[],
            results=[candidate(0, path="other/secret.py")],
            snapshot=snapshot,
        )


def test_invalid_request_level_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_build_dependencies(monkeypatch)
    with pytest.raises(DisclosureInputError):
        context_manager.build_context(
            Settings(),
            PROJECT_ID,
            TASK_ID,
            disclosure_level="L9",
        )
