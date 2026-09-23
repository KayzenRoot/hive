from __future__ import annotations

import hashlib
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.config import Settings
from app.execution_orchestrator import (
    CanonicalMutationError,
    ExecutionContextError,
    ExecutionIdentity,
    ExecutionIdentityError,
    ExecutionOrchestrator,
    ExecutionToolError,
    ExecutorAdapterError,
    ExecutorRequest,
    ExecutorResult,
    HeadRaceError,
)
from app.provider_prompt_cache import ProviderUsageReceipt, UsageReconciliation, UsageSource
from app.registry import InspectionResult, ProjectResponse, ProjectState
from app.runner import ChangeOperation, ChangeSet, ToolPolicy
from app.task_intake import TaskResponse

PROJECT_ID = UUID("00000000-0000-0000-0000-000000000101")
OTHER_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000102")
TASK_ID = UUID("00000000-0000-0000-0000-000000000201")
HEAD = "a" * 40


def project_response(relative_path: str = "target") -> ProjectResponse:
    now = datetime(2026, 9, 9, tzinfo=UTC)
    return ProjectResponse(
        project_id=PROJECT_ID,
        name="Target project",
        relative_path=relative_path,
        git_branch="main",
        git_head_sha=HEAD,
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
    now = datetime(2026, 9, 9, tzinfo=UTC)
    return TaskResponse(
        task_id=TASK_ID,
        project_id=project_id,
        title="Implement a small coding task",
        source_type="MARKDOWN",
        intake_status="READY",
        original_blob_sha256="b" * 64,
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


def context_capsule(
    project_id: UUID = PROJECT_ID,
    task_id: UUID = TASK_ID,
    *,
    head: str = HEAD,
    governance: tuple[str, ...] = (
        "CHECKPOINT",
        "SCOPE",
        "DEFINITION_OF_DONE",
        "ARCHITECTURE",
        "DECISIONS",
    ),
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


class FixtureAdapter:
    name = "local-fixture"

    def __init__(self, result: ExecutorResult) -> None:
        self.result = result
        self.requests: list[ExecutorRequest] = []

    def execute(self, request: ExecutorRequest, context: object) -> ExecutorResult:
        context_project = getattr(context, "project", None)
        assert context_project is not None
        assert context_project.project_id == PROJECT_ID
        self.requests.append(request)
        return self.result


def make_orchestrator(
    root: Path,
    *,
    task_project_id: UUID = PROJECT_ID,
    context: object | None = None,
    inspector: Callable[[Path], InspectionResult] | None = None,
    event_emitter: Callable[..., object] | None = None,
) -> ExecutionOrchestrator:
    workspace = root / "target"
    workspace.mkdir(parents=True, exist_ok=True)
    settings = Settings(projects_root=root)
    return ExecutionOrchestrator(
        settings,
        tool_policy=ToolPolicy((sys.executable,)),
        project_loader=lambda _settings, _project_id: project_response(),
        task_loader=lambda _settings, _project_id, _task_id: task_response(task_project_id),
        context_builder=lambda *_args, **_kwargs: context or context_capsule(),
        repository_inspector=inspector or (lambda _path: inspection()),
        event_emitter=event_emitter,
    )


def coding_result(
    *,
    path: str = "src/generated.py",
    tests: tuple[tuple[str, ...], ...] | None = None,
    validation: tuple[tuple[str, ...], ...] | None = None,
    summary: str = "Created a bounded fixture module.",
) -> ExecutorResult:
    command = (sys.executable, "-c", "print('validation ok')")
    return ExecutorResult(
        change_set=ChangeSet.from_operations(
            [ChangeOperation.create(path, "VALUE = 1\n")],
            model="fixture-model",
            effort="minimal",
            request_id="fixture-request",
        ),
        summary=summary,
        decisions=("Use the existing Runner seam.",),
        test_commands=tests or ((sys.executable, "-c", "print('test ok')"),),
        validation_commands=validation or (command,),
        errors_fixed=(),
        risks=("No canonical promotion is performed.",),
        pending_items=("External review remains required.",),
        proposed_checkpoint_update="Do not update the checkpoint from this run.",
    )


def request() -> ExecutorRequest:
    return ExecutorRequest(
        PROJECT_ID,
        TASK_ID,
        expected_branch="main",
        expected_head_sha=HEAD,
    )


def test_happy_path_reuses_context_and_runner_and_captures_evidence(tmp_path: Path) -> None:
    orchestrator = make_orchestrator(tmp_path)
    adapter = FixtureAdapter(coding_result())

    result = orchestrator.execute(request(), adapter)

    assert result.status == "STAGED"
    assert result.promoted is False
    assert result.validation_passed is True
    assert result.changed_files == ("src/generated.py",)
    assert result.diff[0].after_sha256 == hashlib.sha256(b"VALUE = 1\n").hexdigest()
    assert result.tests[0].succeeded is True
    assert result.validation[0].succeeded is True
    assert result.review.changed_files == result.changed_files
    assert result.review.diff == result.diff
    assert result.staged_run.apply is not None
    assert len(result.staged_run.process) == 2
    assert adapter.requests == [request()]
    payload = result.as_dict()
    assert payload["staged_noncanonical"] is True
    assert payload["commit_performed"] is False
    assert payload["sanitized_path_evidence"] is True
    assert payload["secret_leaks"] == 0
    assert payload["filesystem_path_leaks"] == 0


def test_execution_emits_started_and_terminal_telemetry(tmp_path: Path) -> None:
    events: list[tuple[str, dict[str, object], dict[str, object]]] = []

    def capture(
        _settings: Settings,
        project_id: UUID,
        event_type: str,
        payload: dict[str, object],
        **kwargs: object,
    ) -> None:
        assert project_id == PROJECT_ID
        events.append((event_type, payload, kwargs))

    result = make_orchestrator(tmp_path, event_emitter=capture).execute(
        request(), FixtureAdapter(coding_result())
    )

    assert result.status == "STAGED"
    assert [event[0] for event in events] == [
        "executor.started",
        "tool.called",
        "test.started",
        "test.finished",
        "validation.passed",
        "file.changed",
        "run.completed",
    ]
    assert all(event[2]["task_id"] == TASK_ID for event in events)
    assert len({event[2]["run_id"] for event in events}) == 1
    assert events[1][1]["succeeded"] is True
    assert events[3][1]["passed"] is True
    assert events[4][1]["passed"] is True
    assert events[5][1] == {"file_count": 1}


def test_terminal_telemetry_publishes_exact_provider_usage(tmp_path: Path) -> None:
    events: list[tuple[str, dict[str, object]]] = []

    def capture(
        _settings: Settings,
        _project_id: UUID,
        event_type: str,
        payload: dict[str, object],
        **_kwargs: object,
    ) -> None:
        events.append((event_type, payload))

    base = coding_result()
    receipt = ProviderUsageReceipt(
        capability_identity="a" * 64,
        total_input_tokens=100,
        cached_input_tokens=64,
        fresh_input_tokens=36,
        output_tokens=8,
        observed_hit=True,
        sources=[UsageSource.PROVIDER_REPORTED],
        reconciliation=UsageReconciliation.EXACT,
    )
    result = ExecutorResult(
        change_set=base.change_set,
        summary=base.summary,
        decisions=base.decisions,
        test_commands=base.test_commands,
        validation_commands=base.validation_commands,
        errors_fixed=base.errors_fixed,
        risks=base.risks,
        pending_items=base.pending_items,
        proposed_checkpoint_update=base.proposed_checkpoint_update,
        executor_llm_calls=1,
        executor_provider_calls=1,
        provider_cache_usage=receipt,
    )

    executed = make_orchestrator(tmp_path, event_emitter=capture).execute(
        request(), FixtureAdapter(result)
    )

    assert executed.status == "STAGED"
    terminal = events[-1]
    assert terminal[0] == "run.completed"
    assert terminal[1]["executor_llm_calls"] == 1
    assert terminal[1]["executor_provider_calls"] == 1
    assert terminal[1]["input_tokens"] == 100
    assert terminal[1]["cached_tokens"] == 64
    assert terminal[1]["fresh_tokens"] == 36
    assert terminal[1]["output_tokens"] == 8
    assert terminal[1]["usage_reconciled"] is True
    assert terminal[1]["provider_final_usage"] is True
    assert terminal[1]["cached_tokens_provenance"] == "EXACT"


def test_context_must_be_checkpoint_first_and_complete(tmp_path: Path) -> None:
    orchestrator = make_orchestrator(
        tmp_path,
        context=context_capsule(governance=("SCOPE", "CHECKPOINT")),
    )

    with pytest.raises(ExecutionContextError, match="governance"):
        orchestrator.execute(request(), FixtureAdapter(coding_result()))


def test_cross_project_task_mismatch_is_rejected_before_adapter(tmp_path: Path) -> None:
    orchestrator = make_orchestrator(tmp_path, task_project_id=OTHER_PROJECT_ID)
    adapter = FixtureAdapter(coding_result())

    with pytest.raises(ExecutionIdentityError, match="identity_error:task project mismatch"):
        orchestrator.execute(request(), adapter)

    assert adapter.requests == []
    assert not (tmp_path / "target" / "src" / "generated.py").exists()


def test_structured_output_and_bounds_are_required(tmp_path: Path) -> None:
    orchestrator = make_orchestrator(tmp_path)

    class NarrativeOnlyAdapter:
        name = "narrative-only"

        def execute(self, _request: ExecutorRequest, _context: object) -> object:
            return {"summary": "done"}

    with pytest.raises(ExecutorAdapterError, match="structured"):
        orchestrator.execute(request(), NarrativeOnlyAdapter())  # type: ignore[arg-type]

    with pytest.raises(ExecutorAdapterError, match="validation_commands"):
        orchestrator.execute(
            request(),
            FixtureAdapter(
                ExecutorResult(
                    change_set=coding_result().change_set,
                    summary="missing validation",
                )
            ),
        )


def test_project_brain_mutation_is_rejected_without_writing(tmp_path: Path) -> None:
    orchestrator = make_orchestrator(tmp_path)
    result = coding_result(path="docs/project-brain/13-CHECKPOINT.md")

    with pytest.raises(CanonicalMutationError, match="Project Brain"):
        orchestrator.execute(request(), FixtureAdapter(result))

    assert not (tmp_path / "target" / "docs" / "project-brain" / "13-CHECKPOINT.md").exists()


@pytest.mark.parametrize("argv", [("git", "status"), ("powershell", "-Command", "echo nope")])
def test_unauthorized_and_shell_commands_fail_closed(
    tmp_path: Path,
    argv: tuple[str, ...],
) -> None:
    orchestrator = make_orchestrator(tmp_path)
    result = coding_result(validation=(argv,))

    with pytest.raises(ExecutionToolError, match="ToolPolicy"):
        orchestrator.execute(request(), FixtureAdapter(result))

    assert not (tmp_path / "target" / "src" / "generated.py").exists()


def test_head_race_is_rejected_before_first_mutation(tmp_path: Path) -> None:
    calls = 0

    def changing_inspector(_path: Path) -> InspectionResult:
        nonlocal calls
        calls += 1
        return inspection(head=HEAD if calls < 4 else "b" * 40)

    orchestrator = make_orchestrator(tmp_path, inspector=changing_inspector)

    with pytest.raises(HeadRaceError, match="head_race_rejected"):
        orchestrator.execute(request(), FixtureAdapter(coding_result()))

    assert calls == 4
    assert not (tmp_path / "target" / "src" / "generated.py").exists()


def test_validation_failure_is_captured_after_staging(tmp_path: Path) -> None:
    failing = (sys.executable, "-c", "raise SystemExit(7)")
    orchestrator = make_orchestrator(tmp_path)

    result = orchestrator.execute(
        request(),
        FixtureAdapter(coding_result(validation=(failing,))),
    )

    assert result.status == "VALIDATION_FAILED"
    assert result.validation_passed is False
    assert result.validation[0].returncode == 7
    assert (tmp_path / "target" / "src" / "generated.py").read_text() == "VALUE = 1\n"


def test_test_failure_prevents_staged_success(tmp_path: Path) -> None:
    failing = (sys.executable, "-c", "raise SystemExit(9)")
    orchestrator = make_orchestrator(tmp_path)

    result = orchestrator.execute(
        request(),
        FixtureAdapter(coding_result(tests=(failing,))),
    )

    assert result.status == "VALIDATION_FAILED"
    assert result.validation_passed is False
    assert result.tests[0].returncode == 9
    assert result.validation[0].succeeded is True
    assert (tmp_path / "target" / "src" / "generated.py").read_text() == "VALUE = 1\n"


def test_evidence_sanitizes_secret_and_absolute_path(tmp_path: Path) -> None:
    orchestrator = make_orchestrator(tmp_path)
    result = orchestrator.execute(
        request(),
        FixtureAdapter(
            coding_result(
                summary=(
                    "WO018_TEST_SECRET_DO_NOT_LEAK_alpha at C:\\Users\\csn19\\private\\fixture.txt"
                )
            )
        ),
    )

    serialized = result.to_json()
    assert "WO018_TEST_SECRET_DO_NOT_LEAK" not in serialized
    assert "C:\\Users\\csn19" not in serialized
    assert result.as_dict()["sanitized_path_evidence"] is True


def test_execute_resolves_identity_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Lifecycle preflight and execution must share one exact identity basis."""

    orchestrator = make_orchestrator(tmp_path)
    adapter = FixtureAdapter(coding_result())
    original = orchestrator._resolve_identity
    calls = 0

    def counted(request_value: ExecutorRequest) -> tuple[ExecutionIdentity, ProjectResponse]:
        nonlocal calls
        calls += 1
        return original(request_value)

    monkeypatch.setattr(orchestrator, "_resolve_identity", counted)
    result = orchestrator.execute(request(), adapter)

    assert result.status == "STAGED"
    assert calls == 1
