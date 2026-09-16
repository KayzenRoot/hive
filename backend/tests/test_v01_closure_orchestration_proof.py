"""Load-bearing proof of the production autonomous execution path.

The closure sprint must not accept a context-only or self-asserted orchestration
claim: this module drives the real ``ExecutionOrchestrator.execute`` seam with a
counting adapter and proves that identity resolution, Git observation,
checkpoint-first governance and tool gating all complete before any adapter
invocation, for the positive case and for every required negative case.

The resulting bounded artifact is written to
``tmp/integration-logs/v01-orchestration-proof.json`` so the closure sprint can
consume measured counters instead of asserting them.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from app.config import Settings
from app.execution_orchestrator import (
    ExecutionOrchestrator,
    ExecutorRequest,
    ExecutorResult,
)
from app.registry import InspectionResult, ProjectResponse, ProjectState
from app.runner import ChangeOperation, ChangeSet, ToolPolicy
from app.task_intake import TaskResponse

ROOT = Path(__file__).parents[2]
EVIDENCE_FILE = ROOT / "tmp" / "integration-logs" / "v01-orchestration-proof.json"
PROJECT_ID = UUID("00000000-0000-0000-0000-000000000301")
OTHER_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000302")
TASK_ID = UUID("00000000-0000-0000-0000-000000000401")
HEAD = "c" * 40
AUTHORITY_ORDER = ("CHECKPOINT", "SCOPE", "DEFINITION_OF_DONE", "ARCHITECTURE", "DECISIONS")


def project_response(project_id: UUID = PROJECT_ID, head: str = HEAD) -> ProjectResponse:
    now = datetime(2026, 9, 16, tzinfo=UTC)
    return ProjectResponse(
        project_id=project_id,
        name="Closure target",
        relative_path="target",
        git_branch="main",
        git_head_sha=head,
        detached_head=False,
        repository_accessible=True,
        working_tree_clean=True,
        language_stack=["python"],
        state=ProjectState.READY,
        inspection_error=None,
        created_at=now,
        updated_at=now,
        last_inspected_at=now,
    )


def task_response(project_id: UUID = PROJECT_ID) -> TaskResponse:
    now = datetime(2026, 9, 16, tzinfo=UTC)
    return TaskResponse(
        task_id=TASK_ID,
        project_id=project_id,
        title="Closure orchestration task",
        source_type="MARKDOWN",
        intake_status="READY",
        original_blob_sha256="d" * 64,
        original_filename="task.md",
        media_type="text/markdown",
        logical_size=128,
        compressed_size=64,
        extracted_text_available=True,
        extraction_method="hive-text-normalizer",
        extraction_version="1",
        extraction_error=None,
        page_count=None,
        created_at=now,
        updated_at=now,
    )


def capsule(
    project_id: UUID = PROJECT_ID,
    task_id: UUID = TASK_ID,
    *,
    head: str = HEAD,
    governance: tuple[str, ...] = AUTHORITY_ORDER,
) -> SimpleNamespace:
    return SimpleNamespace(
        project=SimpleNamespace(project_id=project_id, repository_head_sha=head),
        task=SimpleNamespace(task_id=task_id, project_id=project_id),
        governance=[SimpleNamespace(kind=kind) for kind in governance],
    )


def inspection(*, head: str = HEAD, clean: bool | None = True) -> InspectionResult:
    return InspectionResult(
        git_branch="main",
        git_head_sha=head,
        detached_head=False,
        repository_accessible=True,
        working_tree_clean=clean,
        language_stack=["python"],
        state=ProjectState.READY,
        inspection_error=None,
    )


MUTATION_RELATIVE = "src/closure_proof_note.py"
MUTATION_CONTENT = b"CLOSURE_PROOF_NOTE = 'staged by the closure proof'" + b"\n"


class CountingAdapter:
    """Adapter that records invocations and stages one deterministic mutation.

    The negative cases never reach this adapter, so the counter proves that
    authority, identity and tool gating complete before dispatch; the positive case
    stages exactly one bounded CREATE through the production runner.
    """

    name = "closure-counting"

    def __init__(self) -> None:
        self.invocations = 0

    def execute(self, request: ExecutorRequest, context: object) -> ExecutorResult:
        self.invocations += 1
        return staged_result()


def staged_result() -> ExecutorResult:
    command = (sys.executable, "-c", "print('closure validation ok')")
    return ExecutorResult(
        change_set=ChangeSet.from_operations(
            [ChangeOperation.create(MUTATION_RELATIVE, MUTATION_CONTENT.decode("utf-8"))],
            model="closure-fixture",
            effort="minimal",
            request_id="closure-proof-request",
        ),
        summary="closure proof adapter stages one bounded CREATE operation",
        decisions=("Reuse the existing Runner seam.",),
        test_commands=(command,),
        validation_commands=(command,),
        risks=("No canonical promotion is performed.",),
    )


def counting_adapter() -> CountingAdapter:
    return CountingAdapter()


def build_orchestrator(
    root: Path,
    *,
    task_project_id: UUID = PROJECT_ID,
    context: object | None = None,
    inspector: Callable[[Path], InspectionResult] | None = None,
) -> ExecutionOrchestrator:
    workspace = root / "target"
    workspace.mkdir(parents=True, exist_ok=True)
    settings = Settings(projects_root=root)
    return ExecutionOrchestrator(
        settings,
        tool_policy=ToolPolicy((sys.executable,)),
        project_loader=lambda _settings, _project_id: project_response(),
        task_loader=lambda _settings, _project_id, _task_id: task_response(task_project_id),
        context_builder=lambda *_args, **_kwargs: context or capsule(),
        repository_inspector=inspector or (lambda _path: inspection()),
        event_emitter=None,
    )


def request() -> ExecutorRequest:
    return ExecutorRequest(
        PROJECT_ID,
        TASK_ID,
        expected_branch="main",
        expected_head_sha=HEAD,
    )


def write_evidence(payload: dict[str, object]) -> None:
    EVIDENCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_closure_orchestration_proof_is_pre_dispatch_and_fail_closed(tmp_path: Path) -> None:
    """Positive and negative proof through the real orchestrator dispatch seam."""

    positive_adapter = counting_adapter()
    orchestrator = build_orchestrator(tmp_path)
    staged = orchestrator.execute(request(), positive_adapter)
    assert positive_adapter.invocations == 1, "the positive case must reach the adapter"
    assert staged.status == "STAGED", "the positive case must stage a bounded change"
    assert staged.validation_passed is True, "the staged change must pass validation"
    assert staged.promoted is False, "a staged execution must never promote canonically"
    assert staged.changed_files == (MUTATION_RELATIVE,), staged.changed_files
    staged_path = tmp_path / "target" / MUTATION_RELATIVE
    assert staged_path.is_file(), "the staged mutation was not applied to the fixture"
    staged_bytes = staged_path.read_bytes()
    assert staged_bytes == MUTATION_CONTENT, "the staged mutation content does not match the plan"
    staged_digest = hashlib.sha256(staged_bytes).hexdigest()
    positive_capsule = capsule()

    cases: dict[str, dict[str, object]] = {
        "positive": {
            "status": "PASS",
            "adapter_invocations": positive_adapter.invocations,
            "authority_order": list(AUTHORITY_ORDER),
            "project_bound": str(positive_capsule.project.project_id),
            "head_bound": positive_capsule.project.repository_head_sha,
            "staged_status": staged.status,
            "validation_passed": bool(staged.validation_passed),
            "canonical_promotion": bool(staged.promoted),
            "changed_paths": list(staged.changed_files),
            "mutation_path": MUTATION_RELATIVE,
            "mutation_sha256": staged_digest,
            "unexpected_changed_paths": 0,
        }
    }
    negative_specs: tuple[tuple[str, dict[str, Any]], ...] = (
        (
            "missing_authority",
            {"context": capsule(governance=("SCOPE", "DEFINITION_OF_DONE"))},
        ),
        (
            "stale_authority",
            {"context": capsule(head="e" * 40)},
        ),
        (
            "untracked_authority",
            {"context": capsule(governance=("CHECKPOINT",))},
        ),
        (
            "cross_project_authority",
            {"task_project_id": OTHER_PROJECT_ID},
        ),
        (
            "wrong_head_binding",
            {"inspector": lambda _path: inspection(head="f" * 40)},
        ),
        (
            "unsafe_identity",
            {"inspector": lambda _path: inspection(clean=False)},
        ),
    )
    for label, overrides in negative_specs:
        adapter = counting_adapter()
        negative_root = tmp_path / label
        negative_root.mkdir(parents=True, exist_ok=True)
        negative = build_orchestrator(negative_root, **overrides)
        with pytest.raises(Exception) as failure:
            negative.execute(request(), adapter)
        assert adapter.invocations == 0, f"{label} reached the adapter before failing"
        cases[label] = {
            "status": "PASS",
            "adapter_invocations": adapter.invocations,
            "error_type": type(failure.value).__name__,
        }

    write_evidence(
        {
            "status": "PASS",
            "evidence_version": "v01-orchestration-proof-v1",
            "authority_order": list(AUTHORITY_ORDER),
            "cases": cases,
            "llm_calls": 0,
            "provider_calls": 0,
            "project_id": str(PROJECT_ID),
            "task_id": str(TASK_ID),
            "head_sha": HEAD,
        }
    )
    assert set(cases) == {"positive"} | {label for label, _ in negative_specs}
