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
    rerank_response,
    task_response,
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


@pytest.mark.parametrize(
    ("acceptance", "expected"),
    [
        (["- Include the implementation excerpt for build_context."], DisclosureLevel.L3),
        (["- Return the complete file src/context.py."], DisclosureLevel.L4),
        (["- Perform a repository-wide investigation."], DisclosureLevel.L5),
    ],
)
def test_starting_level_uses_acceptance_criteria(
    acceptance: list[str],
    expected: DisclosureLevel,
) -> None:
    task_text = (
        "# Task\nInspect the project checkpoint.\n\n## Acceptance Criteria\n" + acceptance[0]
    )
    start = starting_level("Inspect project state", [], task_text, acceptance_criteria=acceptance)
    assert start == expected
    decided_start, final, path = decide_disclosure(
        title="Inspect project state",
        constraints=[],
        acceptance_criteria=acceptance,
        task_text=task_text,
        files=[],
        symbols=[],
        tests=[],
        results=[],
    )
    assert decided_start == expected
    assert final == expected
    assert path == []


def test_plain_project_state_stays_at_l0() -> None:
    start, final, path = decide_disclosure(
        title="Inspect project checkpoint",
        constraints=["- Use only the target project's canonical governance."],
        acceptance_criteria=["- Report current project state."],
        task_text="# Task\nInspect project checkpoint.\n",
        files=[candidate(0)],
        symbols=[candidate(1, qualified_symbol="build_context")],
        tests=[],
        results=[candidate(0)],
    )
    assert start == DisclosureLevel.L0
    assert final == DisclosureLevel.L0
    assert path == []


def test_coding_task_with_resolved_symbols_does_not_stay_at_l0() -> None:
    start = starting_level(
        "Fix the context builder",
        [],
        "Fix the context builder without extra headings.",
        files=[candidate(0)],
        symbols=[candidate(0, qualified_symbol="TargetContextService.build_context")],
        results=[candidate(0, qualified_symbol="TargetContextService.build_context")],
    )
    assert start == DisclosureLevel.L2


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


def test_l1_emits_deterministic_module_summaries(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_build_dependencies(
        monkeypatch,
        extracted=task_text_response("Need module summaries for the service.\n"),
    )
    first = context_manager.build_context(Settings(), PROJECT_ID, TASK_ID)
    second = context_manager.build_context(Settings(), PROJECT_ID, TASK_ID)
    assert first.progressive_disclosure.final_level == DisclosureLevel.L1
    assert first.module_summaries
    summary = first.module_summaries[0]
    assert summary.path == "src/context.py"
    assert summary.language == "python"
    assert "symbols=" in summary.structure
    assert "TargetContextService" in summary.symbols
    assert summary.source_content_sha256
    assert first.bounds.disclosure_characters_included > 0
    assert first.module_summaries == second.module_summaries


def test_l2_emits_signatures_and_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_build_dependencies(
        monkeypatch,
        extracted=task_text_response(
            "Need symbol signatures for TargetContextService.build_context.\n"
        ),
    )
    first = context_manager.build_context(Settings(), PROJECT_ID, TASK_ID)
    second = context_manager.build_context(Settings(), PROJECT_ID, TASK_ID)
    assert first.progressive_disclosure.final_level == DisclosureLevel.L2
    assert first.symbol_signatures
    signature = first.symbol_signatures[0]
    assert signature.qualified_name == "TargetContextService.build_context"
    assert "def build_context" in signature.signature
    assert "task_id" in signature.signature
    assert signature.path == "src/context.py"
    assert signature.git_blob_sha
    assert first.dependencies
    assert first.dependencies[0].imported_module == "json"
    assert first.dependencies[0].kind == "import"
    assert first.symbol_signatures == second.symbol_signatures
    assert first.dependencies == second.dependencies
    assert first.bounds.disclosure_characters_included > 0


def test_mentioned_method_is_resolved_from_snapshot_when_retrieval_has_class_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_build_dependencies(
        monkeypatch,
        extracted=task_text_response(
            "Need symbol signatures for TargetContextService.build_context.\n"
        ),
        response=rerank_response(
            [
                candidate(0, qualified_symbol="TargetContextService"),
                candidate(
                    1,
                    qualified_symbol=None,
                    source_kind="REPOSITORY_FILE",
                ),
            ]
        ),
    )
    capsule = context_manager.build_context(Settings(), PROJECT_ID, TASK_ID)
    assert any(
        item.qualified_symbol == "TargetContextService.build_context" for item in capsule.symbols
    )
    assert any(
        item.qualified_name == "TargetContextService.build_context"
        for item in capsule.symbol_signatures
    )


def test_l3_emits_implementation_excerpts(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_build_dependencies(monkeypatch)
    capsule = context_manager.build_context(Settings(), PROJECT_ID, TASK_ID)
    assert capsule.progressive_disclosure.starting_level == DisclosureLevel.L3
    assert capsule.progressive_disclosure.final_level == DisclosureLevel.L3
    assert capsule.progressive_disclosure.escalated is False
    assert capsule.retrieval.results
    assert all(result.snippet for result in capsule.retrieval.results)


def test_l4_complete_file_and_l5_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_build_dependencies(
        monkeypatch,
        extracted=task_text_response(
            "# Task\n\n## Constraints\n- Keep source order.\n\n"
            "## Acceptance Criteria\n- Return the complete file src/context.py.\n"
        ),
    )
    capsule = context_manager.build_context(Settings(), PROJECT_ID, TASK_ID)
    assert capsule.progressive_disclosure.starting_level == DisclosureLevel.L4
    assert capsule.progressive_disclosure.final_level == DisclosureLevel.L4
    assert capsule.complete_files
    assert capsule.complete_files[0].path == "src/context.py"
    assert "def build_context" in capsule.complete_files[0].text
    assert capsule.bounds.disclosure_characters_included >= len(capsule.complete_files[0].text)


def test_l4_resolves_file_from_retrieval_without_literal_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_build_dependencies(
        monkeypatch,
        extracted=task_text_response(
            "Return the complete file for TargetContextService.build_context.\n"
        ),
    )
    capsule = context_manager.build_context(Settings(), PROJECT_ID, TASK_ID)
    assert capsule.progressive_disclosure.final_level == DisclosureLevel.L4
    assert capsule.complete_files
    assert capsule.complete_files[0].path == "src/context.py"


def test_l4_never_claims_success_without_complete_file() -> None:
    snapshot = repository_snapshot(governance_documents())
    with pytest.raises(DisclosureConsistencyError, match="l4_target_unresolved"):
        apply_disclosure(
            title="Return the complete file",
            constraints=[],
            acceptance_criteria=["- Return the complete file."],
            task_text="Return the complete file.",
            files=[],
            symbols=[],
            tests=[],
            results=[],
            snapshot=snapshot,
        )


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
    assert capsule.bounds.disclosure_characters_included >= sum(
        len(item.path) for item in capsule.inventory
    )


def test_legitimate_escalation_when_signature_cannot_be_materialized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_build_dependencies(
        monkeypatch,
        extracted=task_text_response(
            "Need symbol signatures for TargetContextService.missing_method.\n"
        ),
    )
    capsule = context_manager.build_context(Settings(), PROJECT_ID, TASK_ID)
    assert capsule.progressive_disclosure.starting_level == DisclosureLevel.L2
    assert capsule.progressive_disclosure.final_level == DisclosureLevel.L3
    assert capsule.progressive_disclosure.escalated is True
    assert capsule.progressive_disclosure.path[0].reason == "required_signature_unresolved"
    assert capsule.progressive_disclosure.path[0].from_level == DisclosureLevel.L2
    assert capsule.progressive_disclosure.path[0].to_level == DisclosureLevel.L3


def test_explicit_requested_levels_are_a_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_build_dependencies(
        monkeypatch,
        task=task_response(),
        extracted=task_text_response(
            "Inspect the target project checkpoint and current state only.\n"
        ),
    )
    l0 = context_manager.build_context(Settings(), PROJECT_ID, TASK_ID, disclosure_level="L0")
    assert l0.progressive_disclosure.starting_level == DisclosureLevel.L0
    assert l0.progressive_disclosure.requested_level_applied is True

    l3 = context_manager.build_context(Settings(), PROJECT_ID, TASK_ID, disclosure_level="L3")
    assert l3.progressive_disclosure.starting_level == DisclosureLevel.L3
    assert l3.progressive_disclosure.final_level == DisclosureLevel.L3
    assert l3.retrieval.results

    l4 = context_manager.build_context(Settings(), PROJECT_ID, TASK_ID, disclosure_level="L4")
    assert l4.progressive_disclosure.final_level == DisclosureLevel.L4
    assert l4.complete_files

    l5 = context_manager.build_context(Settings(), PROJECT_ID, TASK_ID, disclosure_level="L5")
    assert l5.progressive_disclosure.final_level == DisclosureLevel.L5
    assert l5.inventory


def test_explicit_level_never_returns_shallower_than_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_build_dependencies(monkeypatch)
    capsule = context_manager.build_context(Settings(), PROJECT_ID, TASK_ID, disclosure_level="L4")
    assert capsule.progressive_disclosure.starting_level == DisclosureLevel.L4
    assert capsule.progressive_disclosure.final_level == DisclosureLevel.L4
    assert capsule.complete_files


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


def test_disclosure_payload_changes_emitted_size(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_build_dependencies(
        monkeypatch,
        extracted=task_text_response(
            "Inspect the target project checkpoint and current state only.\n"
        ),
    )
    l0 = context_manager.build_context(Settings(), PROJECT_ID, TASK_ID)
    l2 = context_manager.build_context(Settings(), PROJECT_ID, TASK_ID, disclosure_level="L2")
    l4 = context_manager.build_context(Settings(), PROJECT_ID, TASK_ID, disclosure_level="L4")
    l5 = context_manager.build_context(Settings(), PROJECT_ID, TASK_ID, disclosure_level="L5")
    assert l0.bounds.disclosure_characters_included == 0
    assert l2.bounds.disclosure_characters_included > l0.bounds.disclosure_characters_included
    assert l4.bounds.disclosure_characters_included > l2.bounds.disclosure_characters_included
    assert l5.bounds.disclosure_characters_included > 0
    assert l4.bounds.total_emitted_context_characters > l0.bounds.total_emitted_context_characters
    assert (
        l4.bounds.serialized_capsule_characters
        == len(l4.model_dump_json())
        == l4.bounds.serialized_capsule_characters
    )
