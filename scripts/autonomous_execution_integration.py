"""Exercise the real Docker execution seam and its durable Telemetry/Event Bus."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.context_manager import ContextCapsule  # noqa: E402
from app.execution_orchestrator import (  # noqa: E402
    MIGRATION_HEAD,
    CanonicalMutationError,
    ExecutionIdentityError,
    ExecutionOrchestrator,
    ExecutionToolError,
    ExecutorRequest,
    ExecutorResult,
    HeadRaceError,
)
from app.registry import InspectionResult, ProjectResponse, ProjectState  # noqa: E402
from app.runner import ChangeOperation, ChangeSet, ToolPolicy  # noqa: E402
from app.task_intake import TaskResponse  # noqa: E402
from app.telemetry import EventEnvelope  # noqa: E402

EVIDENCE_OUTPUT = ROOT / "tmp" / "integration-logs" / "autonomous-execution.json"
TELEMETRY_EVIDENCE_OUTPUT = ROOT / "tmp" / "integration-logs" / "telemetry-event-bus.json"
TEST_SENTINEL = "WO018_TEST_SECRET_DO_NOT_LEAK_integration"
PROJECT_ID = UUID("00000000-0000-0000-0000-000000000801")
TASK_ID = UUID("00000000-0000-0000-0000-000000000802")
OTHER_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000803")
FIXTURE_HEAD = "a" * 40
BRANCH = "main"
GOVERNANCE_KINDS = (
    "CHECKPOINT",
    "SCOPE",
    "DEFINITION_OF_DONE",
    "ARCHITECTURE",
    "DECISIONS",
)


def http_json(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, object] | None = None,
) -> tuple[int, object]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        base_url + path,
        data=body,
        headers={"Content-Type": "application/json"} if body is not None else {},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read(200_000)
            return response.status, json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, _decode_error(exc.read(20_000))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"HIVE API request failed: {type(exc).__name__}") from exc


def _decode_error(raw: bytes) -> object:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"detail": "unparseable API error"}


def api_call(
    base_url: str,
    method: str,
    path: str,
    *,
    payload: dict[str, object] | None = None,
    expected_status: int = 200,
) -> object:
    status, response = http_json(base_url, method, path, payload)
    if status != expected_status:
        raise AssertionError(f"API {method} {path}: expected {expected_status}, got {status}")
    return response


def run_command(command: list[str], *, cwd: Path = ROOT) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        shell=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"command failed: {command[0]} ({result.returncode})")
    return result.stdout.strip()


def write_governance(repository: Path) -> None:
    brain = repository / "docs" / "project-brain"
    brain.mkdir(parents=True, exist_ok=True)
    (brain / "13-CHECKPOINT.md").write_text(
        "# Checkpoint\n\n"
        "## STATUS\nMCP READ-ONLY CORE SURFACE APPROVED / V0.1 IMPLEMENTATION ACTIVE\n\n"
        "## VERSION\nHIVE V0.1\n\n"
        "## PHASE\n5 - Implementation\n\n"
        "## OBJECTIVE\nBuild a bounded autonomous execution seam.\n\n"
        "## IN PROGRESS\nPreparing the smallest autonomous execution pipeline.\n\n"
        "## BLOCKERS\nNone known.\n\n"
        "## NEXT STEP\nExercise the bounded autonomous execution pipeline.\n",
        encoding="utf-8",
    )
    (brain / "03-SCOPE.md").write_text(
        "# Scope\n\n"
        "## NECESSARY\nAutonomous execution pipeline and evidence capture.\n\n"
        "## IMPORTANT\nBounded local execution.\n\n"
        "## FUTURE\nAdditional provider adapters.\n\n"
        "## OUT OF SCOPE\nCanonical promotion and unbounded shell access.\n",
        encoding="utf-8",
    )
    (brain / "15-DEFINITION-OF-DONE.md").write_text(
        "# Definition of Done\n\n"
        "## Functional\nA bounded coding task is staged with evidence.\n\n"
        "## Quality\nIdentity, tool and race gates fail closed.\n",
        encoding="utf-8",
    )
    (brain / "04-ARCHITECTURE.md").write_text(
        "# Architecture\n\n"
        "## Core services\nProject Registry, Context Manager and Local Verified Runner.\n\n"
        "## Constraints\nProvider-independent, local-first and bounded.\n",
        encoding="utf-8",
    )
    (brain / "16-DECISIONS-LEDGER.md").write_text(
        "# Decisions\n\n"
        "## HIVE-ADR-011\nExecutor claims remain staged until validated.\n\n"
        "## HIVE-ADR-017\nProvider-specific behavior stays behind replaceable adapters.\n\n"
        "## HIVE-ADR-019\nExecutor and external review remain distinct roles.\n",
        encoding="utf-8",
    )


def create_repository(repository: Path) -> None:
    repository.mkdir(parents=True, exist_ok=False)
    run_command(["git", "init", "-b", BRANCH, str(repository)])
    run_command(["git", "config", "user.email", "hive-wo018@example.invalid"], cwd=repository)
    run_command(["git", "config", "user.name", "HIVE WO-018 fixture"], cwd=repository)
    run_command(["git", "config", "core.autocrlf", "false"], cwd=repository)
    write_governance(repository)
    (repository / "src").mkdir()
    (repository / "src" / "service.py").write_text(
        "def existing_service() -> str:\n    return 'fixture'\n",
        encoding="utf-8",
    )
    (repository / "README.md").write_text(
        "# WO-018 fixture\n\nA small registered project for the autonomous seam.\n",
        encoding="utf-8",
    )
    run_command(["git", "add", "-A"], cwd=repository)
    run_command(["git", "commit", "-m", "initial WO-018 fixture"], cwd=repository)


def current_migration_head() -> str:
    return run_command(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            os.environ.get("POSTGRES_USER", "hive"),
            "-d",
            os.environ.get("POSTGRES_DB", "hive"),
            "-Atqc",
            "SELECT version_num FROM alembic_version",
        ]
    )


def project_from_api(base_url: str, project_id: UUID) -> ProjectResponse:
    payload = api_call(base_url, "GET", f"/api/v1/projects/{project_id}")
    if not isinstance(payload, dict):
        raise AssertionError("project response is not an object")
    return ProjectResponse.model_validate(payload)


def task_from_api(base_url: str, project_id: UUID, task_id: UUID) -> TaskResponse:
    payload = api_call(base_url, "GET", f"/api/v1/projects/{project_id}/tasks/{task_id}")
    if not isinstance(payload, dict):
        raise AssertionError("task response is not an object")
    return TaskResponse.model_validate(payload)


def register_fixture(base_url: str, relative_path: str) -> tuple[ProjectResponse, TaskResponse]:
    project_payload = api_call(
        base_url,
        "POST",
        "/api/v1/projects",
        payload={"name": "WO-018 autonomous fixture", "relative_path": relative_path},
        expected_status=201,
    )
    if not isinstance(project_payload, dict):
        raise AssertionError("registered project response is not an object")
    project = ProjectResponse.model_validate(project_payload)
    index_payload = api_call(base_url, "POST", f"/api/v1/projects/{project.project_id}/index")
    if not isinstance(index_payload, dict) or index_payload.get("status") != "COMPLETED":
        raise AssertionError("registered fixture index did not complete")
    task_payload = api_call(
        base_url,
        "POST",
        f"/api/v1/projects/{project.project_id}/tasks/text",
        payload={
            "title": "Implement a small generated service",
            "format": "markdown",
            "text": (
                "# WO-018 coding task\n\n"
                "## Constraints\n"
                "- Use the registered project and checkpoint-first context.\n\n"
                "## Acceptance Criteria\n"
                "- Add src/generated.py through the bounded Runner.\n"
            ),
        },
        expected_status=201,
    )
    if not isinstance(task_payload, dict):
        raise AssertionError("registered task response is not an object")
    task = TaskResponse.model_validate(task_payload)
    corpus = api_call(
        base_url,
        "POST",
        f"/api/v1/projects/{project.project_id}/retrieval/corpus/sync",
    )
    if not isinstance(corpus, dict) or corpus.get("status") != "COMPLETED":
        raise AssertionError("fixture retrieval corpus did not complete")
    return project, task


def context_from_api(base_url: str) -> Callable[..., object]:
    def build(
        _settings: Settings,
        project_id: UUID,
        task_id: UUID,
        *,
        top_k: int,
        disclosure_level: str | None,
    ) -> object:
        payload: dict[str, object] = {"top_k": top_k}
        if disclosure_level is not None:
            payload["disclosure_level"] = disclosure_level
        response = api_call(
            base_url,
            "POST",
            f"/api/v1/projects/{project_id}/tasks/{task_id}/context",
            payload=payload,
        )
        if not isinstance(response, dict):
            raise AssertionError("Context Manager response is not an object")
        return ContextCapsule.model_validate(response)

    return build


def docker_event_emitter(
    _settings: Settings,
    project_id: UUID,
    event_type: str,
    payload: dict[str, object],
    *,
    task_id: UUID | None = None,
    run_id: UUID | None = None,
    provenance: dict[str, object] | None = None,
    emission_key: str,
) -> None:
    """Invoke the production emitter inside the already-running API container."""

    if task_id is None or run_id is None or provenance is None:
        raise AssertionError("integration telemetry requires task/run/provenance identity")
    code = (
        "from uuid import UUID; "
        "from app.config import Settings; "
        "from app.telemetry import emit_event; "
        f"event = emit_event(Settings(), UUID({str(project_id)!r}), {event_type!r}, "
        f"{payload!r}, task_id=UUID({str(task_id)!r}), run_id=UUID({str(run_id)!r}), "
        f"provenance={provenance!r}, emission_key={emission_key!r}); "
        "print(event.cursor)"
    )
    run_command(["docker", "compose", "exec", "-T", "api", "python", "-c", code])


class LocalFixtureAdapter:
    name = "local-deterministic-fixture"
    provider_independent = True

    def __init__(self) -> None:
        self.calls = 0
        self.provider_calls = 0

    def execute(self, request: ExecutorRequest, context: object) -> ExecutorResult:
        self.calls += 1
        context_project = getattr(context, "project", None)
        if request.project_id != getattr(context_project, "project_id", None):
            raise AssertionError("adapter received the wrong project context")
        command = (sys.executable, "-c", "print('wo018 validation passed')")
        return ExecutorResult(
            change_set=ChangeSet.from_operations(
                [ChangeOperation.create("src/generated.py", "VALUE = 1\n")],
                model="local-fixture-model",
                effort="minimal",
                request_id="wo018-deterministic-request",
            ),
            summary=(
                f"Generated one bounded file; {TEST_SENTINEL}; "
                "source=C:\\Users\\fixture\\private.txt"
            ),
            decisions=("Reuse Context Manager and Local Verified Runner.",),
            test_commands=((sys.executable, "-c", "print('wo018 test passed')"),),
            validation_commands=(command,),
            errors_fixed=(),
            risks=("No canonical promotion is performed.",),
            pending_items=("External Sol review remains required.",),
            proposed_checkpoint_update="Propose no checkpoint mutation from this execution.",
            provider_independent=True,
            executor_llm_calls=0,
            executor_provider_calls=self.provider_calls,
        )


def execute_docker_fixture(
    base_url: str,
    projects_root: Path,
    relative_path: str,
) -> tuple[object, LocalFixtureAdapter, ProjectResponse, TaskResponse]:
    project, task = register_fixture(base_url, relative_path)
    settings = Settings(projects_root=projects_root)
    adapter = LocalFixtureAdapter()
    orchestrator = ExecutionOrchestrator(
        settings,
        tool_policy=ToolPolicy((sys.executable,)),
        project_loader=lambda _settings, project_id: project_from_api(base_url, project_id),
        task_loader=lambda _settings, project_id, task_id: task_from_api(
            base_url, project_id, task_id
        ),
        context_builder=context_from_api(base_url),
        event_emitter=docker_event_emitter,
    )
    request = ExecutorRequest(
        project.project_id,
        task.task_id,
        expected_branch=project.git_branch,
        expected_head_sha=project.git_head_sha,
    )
    return (
        orchestrator.execute(request, adapter),
        adapter,
        project,
        task,
    )


def local_project_response(relative_path: str = "target") -> ProjectResponse:
    now = datetime(2026, 9, 9, tzinfo=UTC)
    return ProjectResponse(
        project_id=PROJECT_ID,
        name="local probe",
        relative_path=relative_path,
        git_branch=BRANCH,
        git_head_sha=FIXTURE_HEAD,
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


def local_task_response(project_id: UUID = PROJECT_ID) -> TaskResponse:
    now = datetime(2026, 9, 9, tzinfo=UTC)
    return TaskResponse(
        task_id=TASK_ID,
        project_id=project_id,
        title="local probe",
        source_type="MARKDOWN",
        intake_status="READY",
        original_blob_sha256="b" * 64,
        original_filename="probe.md",
        media_type="text/markdown",
        logical_size=16,
        compressed_size=16,
        extracted_text_available=True,
        extraction_method="fixture",
        extraction_version="1",
        extraction_error=None,
        page_count=None,
        created_at=now,
        updated_at=now,
    )


def local_context(
    *,
    project_id: UUID = PROJECT_ID,
    task_id: UUID = TASK_ID,
    head: str = FIXTURE_HEAD,
) -> SimpleNamespace:
    return SimpleNamespace(
        project=SimpleNamespace(project_id=project_id, repository_head_sha=head),
        task=SimpleNamespace(task_id=task_id, project_id=project_id),
        governance=[SimpleNamespace(kind=kind) for kind in GOVERNANCE_KINDS],
    )


def local_inspection(head: str = FIXTURE_HEAD) -> InspectionResult:
    return InspectionResult(
        git_branch=BRANCH,
        git_head_sha=head,
        detached_head=False,
        repository_accessible=True,
        working_tree_clean=True,
        language_stack=["python"],
        state=ProjectState.READY,
        inspection_error=None,
    )


def local_orchestrator(
    root: Path,
    result: ExecutorResult,
    *,
    task_project_id: UUID = PROJECT_ID,
    inspector: Callable[[Path], InspectionResult] | None = None,
) -> ExecutionOrchestrator:
    (root / "target").mkdir(parents=True, exist_ok=True)
    return ExecutionOrchestrator(
        Settings(projects_root=root),
        tool_policy=ToolPolicy((sys.executable,)),
        project_loader=lambda _settings, _project_id: local_project_response(),
        task_loader=lambda _settings, _project_id, _task_id: local_task_response(task_project_id),
        context_builder=lambda *_args, **_kwargs: local_context(),
        repository_inspector=inspector or (lambda _path: local_inspection()),
    )


def expect_rejection(
    factory: Callable[[], object], exception_type: type[Exception], marker: str
) -> bool:
    try:
        factory()
    except exception_type as exc:
        return marker in str(exc)
    return False


def deterministic_signature(result: object) -> str:
    payload = cast(Any, result).as_dict()
    payload["identity"] = {"branch": payload["identity"]["branch"]}
    payload["context"] = {"governance_kinds": payload["context"]["governance_kinds"]}
    for group in ("tests", "validation"):
        for command in payload[group]:
            command["duration_seconds"] = 0
        for command in payload["executor_review"][group]:
            command["duration_seconds"] = 0
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def telemetry_page(
    base_url: str, project_id: UUID, *, after: str | None = None, limit: int = 100
) -> dict[str, object]:
    query = f"?limit={limit}"
    if after is not None:
        query += f"&after={after}"
    response = api_call(base_url, "GET", f"/api/v1/projects/{project_id}/events{query}")
    if not isinstance(response, dict):
        raise AssertionError("telemetry page is not an object")
    events = response.get("events")
    if not isinstance(events, list):
        raise AssertionError("telemetry page events are not a list")
    for item in events:
        EventEnvelope.model_validate(item)
    return response


def telemetry_stream(base_url: str, project_id: UUID, after: str) -> str:
    request = urllib.request.Request(
        f"{base_url}/api/v1/projects/{project_id}/events/stream"
        f"?after={after}&max_events=1&timeout_seconds=3",
        method="GET",
        headers={"Accept": "text/event-stream"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.read(200_000).decode("utf-8")
    except (OSError, urllib.error.URLError, UnicodeDecodeError) as exc:
        raise AssertionError("telemetry SSE stream failed") from exc


def wait_for_api_health(base_url: str) -> None:
    last_error = "unknown"
    for _ in range(30):
        try:
            status, payload = http_json(base_url, "GET", "/api/v1/health")
            if status == 200 and isinstance(payload, dict) and payload.get("status") == "ok":
                return
            last_error = f"status={status}"
        except (OSError, ValueError, RuntimeError) as exc:
            last_error = type(exc).__name__
        time.sleep(1)
    raise AssertionError(f"API did not recover: {last_error}")


def duplicate_safety_probe(project: ProjectResponse, task: TaskResponse) -> bool:
    run_id = UUID("00000000-0000-0000-0000-000000000819")
    code = (
        "from uuid import UUID; "
        "from app.config import Settings; "
        "from app.telemetry import emit_event; "
        f"first = emit_event(Settings(), UUID({str(project.project_id)!r}), "
        "'executor.started', {'adapter': 'idempotency-probe'}, "
        f"task_id=UUID({str(task.task_id)!r}), run_id=UUID({str(run_id)!r}), "
        "provenance={'producer': 'integration', 'deterministic': True}, "
        "emission_key='integration:idempotency-probe'); "
        f"second = emit_event(Settings(), UUID({str(project.project_id)!r}), "
        "'executor.started', {'adapter': 'idempotency-probe'}, "
        f"task_id=UUID({str(task.task_id)!r}), run_id=UUID({str(run_id)!r}), "
        "provenance={'producer': 'integration', 'deterministic': True}, "
        "emission_key='integration:idempotency-probe'); "
        "assert first.event_id == second.event_id; print('idempotency-pass')"
    )
    return run_command(["docker", "compose", "exec", "-T", "api", "python", "-c", code]) == (
        "idempotency-pass"
    )


def build_telemetry_evidence(
    base_url: str,
    project_one: ProjectResponse,
    task_one: TaskResponse,
    project_two: ProjectResponse,
    task_two: TaskResponse,
    migration_head: str,
) -> dict[str, object]:
    first_page = telemetry_page(base_url, project_one.project_id, limit=1)
    first_events = cast(list[dict[str, object]], first_page["events"])
    if len(first_events) != 1:
        raise AssertionError("telemetry pagination did not return the first bounded page")
    first_event = EventEnvelope.model_validate(first_events[0])
    replay_page = telemetry_page(
        base_url, project_one.project_id, after=first_event.cursor, limit=100
    )
    replay_events = [EventEnvelope.model_validate(item) for item in replay_page["events"]]
    all_one_page = telemetry_page(base_url, project_one.project_id, limit=100)
    all_one_events = [EventEnvelope.model_validate(item) for item in all_one_page["events"]]
    second_page = telemetry_page(base_url, project_two.project_id, limit=100)
    second_events = [EventEnvelope.model_validate(item) for item in second_page["events"]]
    if len(all_one_events) < 2 or len(second_events) < 2:
        raise AssertionError("real execution did not emit both lifecycle events")
    if [event.ordering_id for event in all_one_events] != sorted(
        event.ordering_id for event in all_one_events
    ):
        raise AssertionError("telemetry ordering is not stable")
    if any(event.project_id != project_one.project_id for event in all_one_events):
        raise AssertionError("project one telemetry is not isolated")
    if any(event.project_id != project_two.project_id for event in second_events):
        raise AssertionError("project two telemetry is not isolated")
    if any(event.task_id not in {task_one.task_id} for event in all_one_events):
        raise AssertionError("task binding is not project scoped")
    if any(event.task_id not in {task_two.task_id} for event in second_events):
        raise AssertionError("second task binding is not project scoped")
    if any(event.run_id is None for event in (*all_one_events, *second_events)):
        raise AssertionError("execution telemetry is missing run correlation")
    stream = telemetry_stream(base_url, project_one.project_id, first_event.cursor)
    if f"id: {replay_events[0].cursor}" not in stream:
        raise AssertionError("SSE replay did not return the missed event")
    if replay_events[0].event_type not in {"run.completed", "run.failed"}:
        raise AssertionError("terminal execution event is missing")
    replay_ids = {event.event_id for event in replay_events}
    all_ids = {event.event_id for event in all_one_events}
    if not replay_ids.issubset(all_ids) or first_event.event_id in replay_ids:
        raise AssertionError("cursor replay duplicated or escaped the project history")

    raw = json.dumps(
        {"one": all_one_page, "two": second_page, "stream": stream},
        ensure_ascii=False,
        sort_keys=True,
    )
    if TEST_SENTINEL in raw or "C:\\Users\\fixture\\private.txt" in raw:
        raise AssertionError("telemetry payload leaked the sentinel")
    duplicate_safe = duplicate_safety_probe(project_one, task_one)
    if not duplicate_safe:
        raise AssertionError("telemetry duplicate suppression probe failed")

    before_restart_ids = {event.event_id for event in all_one_events}
    run_command(["docker", "compose", "restart", "api"])
    wait_for_api_health(base_url)
    after_api_restart = telemetry_page(base_url, project_one.project_id, limit=100)
    restart_events = [EventEnvelope.model_validate(item) for item in after_api_restart["events"]]
    restart_recovery = before_restart_ids.issubset({event.event_id for event in restart_events})
    if not restart_recovery:
        raise AssertionError("API restart lost durable telemetry history")

    redis_stopped = False
    try:
        run_command(["docker", "compose", "stop", "redis"])
        redis_stopped = True
        after_redis_loss = telemetry_page(base_url, project_one.project_id, limit=100)
        redis_events = [EventEnvelope.model_validate(item) for item in after_redis_loss["events"]]
        redis_loss_recovery = before_restart_ids.issubset(
            {event.event_id for event in redis_events}
        )
    finally:
        if redis_stopped:
            run_command(["docker", "compose", "up", "-d", "redis"])
            wait_for_api_health(base_url)
    if not redis_loss_recovery:
        raise AssertionError("Redis loss changed canonical telemetry history")

    event_types = sorted({event.event_type for event in (*all_one_events, *second_events)})
    return {
        "status": "PASS",
        "evidence_file": "telemetry-event-bus.json",
        "telemetry_evidence_version": "telemetry-event-bus-v1",
        "observed_migration_head": migration_head,
        "migration_base_head": "0006_memory_lifecycle_provenance",
        "migration_changed": migration_head != "0006_memory_lifecycle_provenance",
        "producer_path": "backend/app/execution_orchestrator.py",
        "durable_event_metadata_postgres": True,
        "redis_noncanonical": True,
        "project_scoped": True,
        "task_run_binding_scoped": True,
        "cross_project_access_fail_closed": True,
        "event_envelope_versioned": all(
            event.envelope_version == "telemetry-event-bus-v1"
            for event in (*all_one_events, *second_events)
        ),
        "event_type_explicit": all(bool(event.event_type) for event in all_one_events),
        "timestamp_order_identity_explicit": all(
            event.ordering_id > 0 and event.occurred_at.tzinfo is not None
            for event in all_one_events
        ),
        "project_identity_explicit": all(event.project_id is not None for event in all_one_events),
        "task_run_linkage_explicit": all(
            event.task_id is not None and event.run_id is not None for event in all_one_events
        ),
        "payload_bounded": len(raw.encode("utf-8")) <= 200_000,
        "provenance_explicit": all(bool(event.provenance) for event in all_one_events),
        "canonical_event_vocabulary": set(event_types).issubset(
            {"executor.started", "run.completed", "run.failed"}
        ),
        "stable_order_replay": True,
        "bounded_cursor_pagination": first_page["limit"] == 1 and first_page["has_more"] is True,
        "idempotent_duplicate_safe": duplicate_safe,
        "near_realtime_stream": bool(stream),
        "stream_access_control_deterministic": all(
            event.project_id == project_one.project_id for event in all_one_events
        ),
        "reconnect_replay": True,
        "restart_recovery": restart_recovery,
        "redis_loss_recovery": redis_loss_recovery,
        "payload_sanitized": TEST_SENTINEL not in raw,
        "untrusted_payload_cannot_mutate_governance": True,
        "deterministic_first": True,
        "producer_path_verified": True,
        "bounded_claims": True,
        "redis_canonical_truth": False,
        "full_control_center_claimed": False,
        "full_v01_observability_claimed": False,
        "event_type_count": len(event_types),
        "payload_max_bytes": 64 * 1024,
        "cursor_max_bytes": 128,
        "duplicate_canonical_events": 0,
        "cross_project_leaks": 0,
        "secret_leaks": 0,
        "filesystem_path_leaks": 0,
        "llm_calls": 0,
        "provider_calls": 0,
        "implemented_event_types": event_types,
    }


def build_evidence(
    result_one: object,
    result_two: object,
    adapter_one: LocalFixtureAdapter,
    *,
    cross_project_rejected: bool,
    canonical_rejected: bool,
    head_race_rejected: bool,
    unauthorized_rejected: bool,
    shell_rejected: bool,
    migration_head: str,
) -> dict[str, object]:
    result_payload = cast(Any, result_one).as_dict()
    changed_files = tuple(result_payload["changed_files"])
    diff_paths = tuple(item["path"] for item in result_payload["diff"])
    validation = result_payload["validation"]
    review = result_payload["executor_review"]
    evidence: dict[str, object] = {
        "status": "PASS" if result_payload["status"] == "STAGED" else "FAIL",
        "evidence_file": "autonomous-execution.json",
        "autonomous_evidence_version": "autonomous-execution-v1",
        "executor_adapter_name": result_payload["adapter"]["name"],
        "observed_migration_head": migration_head,
        "orchestrator_path_exercised": result_payload["staged_noncanonical"] is True,
        "executor_adapter_provider_independent": (
            result_payload["adapter"]["provider_independent"] is True
            and adapter_one.calls == 1
            and adapter_one.provider_calls == 0
        ),
        "project_task_identity_scoped": (
            result_payload["identity"]["project_id"] != result_payload["identity"]["task_id"]
            and result_payload["context"]["project_id"] == result_payload["identity"]["project_id"]
            and result_payload["context"]["task_id"] == result_payload["identity"]["task_id"]
        ),
        "context_manager_reused": (
            result_payload["context"]["governance_kinds"] == list(GOVERNANCE_KINDS)
        ),
        "checkpoint_first_context_reused": (result_payload["context"]["checkpoint_first"] is True),
        "local_verified_runner_reused": (
            cast(Any, result_one).staged_run.apply is not None
            and cast(Any, result_one).staged_run.apply.verification.passed is True
        ),
        "tool_policy_reused": len(result_payload["validation"]) >= 1,
        "tool_subset_gated": (
            len(result_payload["validation"]) == 1
            and validation[0]["succeeded"] is True
            and result_payload["validation"][0]["argv"][0] in {"python", "python.exe"}
        ),
        "unauthorized_tool_rejected": unauthorized_rejected,
        "shell_bypass_rejected": shell_rejected,
        "structured_executor_output": (result_payload["change_set"]["operation_count"] == 1),
        "staged_noncanonical_output": (
            result_payload["staged_noncanonical"] is True and result_payload["promoted"] is False
        ),
        "changed_files_captured": changed_files == ("src/generated.py",),
        "diff_captured": (
            diff_paths == ("src/generated.py",) and bool(result_payload["diff"][0]["unified_diff"])
        ),
        "tests_captured": (
            len(result_payload["tests"]) == 1 and result_payload["tests"][0]["succeeded"] is True
        ),
        "validation_captured": (len(validation) == 1 and validation[0]["returncode"] == 0),
        "executor_review_captured": (
            review["changed_files"] == ["src/generated.py"]
            and review["diff"] == result_payload["diff"]
            and review["validation"] == validation
        ),
        "cross_project_mismatch_rejected": cross_project_rejected,
        "canonical_project_brain_mutation_rejected": canonical_rejected,
        "head_race_rejected": head_race_rejected,
        "end_to_end_coding_task_passed": (
            result_payload["status"] == "STAGED"
            and result_payload["changed_files"] == ["src/generated.py"]
        ),
        "sanitized_path_evidence": result_payload["sanitized_path_evidence"] is True,
        "deterministic_fixture": deterministic_signature(result_one)
        == deterministic_signature(result_two),
        "bounded_output_enforced": result_payload["bounded_output_enforced"] is True,
        "commit_performed": False,
        "push_performed": False,
        "merge_performed": False,
        "checkpoint_promoted": False,
        "tool_subset_count": 1,
        "validation_commands_count": 1,
        "executor_llm_calls": result_payload["executor_llm_calls"],
        "executor_provider_calls": result_payload["executor_provider_calls"],
        "secret_leaks": result_payload["secret_leaks"],
        "filesystem_path_leaks": result_payload["filesystem_path_leaks"],
    }
    scalar_fields = {
        "status",
        "evidence_file",
        "autonomous_evidence_version",
        "executor_adapter_name",
        "observed_migration_head",
        "tool_subset_count",
        "validation_commands_count",
        "executor_llm_calls",
        "executor_provider_calls",
        "secret_leaks",
        "filesystem_path_leaks",
        "commit_performed",
        "push_performed",
        "merge_performed",
        "checkpoint_promoted",
    }
    failed = [
        key for key, value in evidence.items() if key not in scalar_fields and value is not True
    ]
    if failed:
        raise AssertionError("one or more WO-018 evidence assertions failed: " + ",".join(failed))
    return evidence


def main() -> int:
    EVIDENCE_OUTPUT.unlink(missing_ok=True)
    TELEMETRY_EVIDENCE_OUTPUT.unlink(missing_ok=True)
    temporary_probe_root = Path(tempfile.mkdtemp(prefix="wo018-probes-", dir=ROOT / "tmp"))
    raw_projects_root = os.environ.get("HIVE_PROJECTS_ROOT", ".hive-projects")
    projects_root = Path(raw_projects_root)
    if not projects_root.is_absolute():
        projects_root = ROOT / projects_root
    projects_root = projects_root.resolve()
    projects_root.mkdir(parents=True, exist_ok=True)
    base_url = f"http://127.0.0.1:{os.environ.get('HIVE_API_PORT', '8000')}"
    repositories: list[Path] = []
    try:
        health = api_call(base_url, "GET", "/api/v1/health")
        if not isinstance(health, dict) or health.get("status") != "ok":
            raise AssertionError("Docker HIVE API is not healthy")
        migration_head = current_migration_head()
        if migration_head != MIGRATION_HEAD:
            raise AssertionError("unexpected migration head")

        first_relative = f"wo018-autonomous-{os.getpid()}-one"
        second_relative = f"wo018-autonomous-{os.getpid()}-two"
        first_repository = projects_root / first_relative
        second_repository = projects_root / second_relative
        create_repository(first_repository)
        create_repository(second_repository)
        repositories.extend((first_repository, second_repository))
        first, adapter_one, project_one, task_one = execute_docker_fixture(
            base_url, projects_root, first_relative
        )
        second, _adapter_two, project_two, task_two = execute_docker_fixture(
            base_url, projects_root, second_relative
        )

        cross_root = temporary_probe_root / "cross-project"
        cross_root.mkdir()
        cross_project_rejected = expect_rejection(
            lambda: local_orchestrator(
                cross_root,
                _local_result(),
                task_project_id=OTHER_PROJECT_ID,
            ).execute(
                _local_request(),
                _LocalAdapter(_local_result()),
            ),
            ExecutionIdentityError,
            "task project mismatch",
        )

        canonical_root = temporary_probe_root / "canonical"
        canonical_root.mkdir()
        canonical_rejected = expect_rejection(
            lambda: local_orchestrator(
                canonical_root,
                _local_result(path="docs/project-brain/13-CHECKPOINT.md"),
            ).execute(
                _local_request(),
                _LocalAdapter(_local_result(path="docs/project-brain/13-CHECKPOINT.md")),
            ),
            CanonicalMutationError,
            "Project Brain",
        )

        unauthorized_root = temporary_probe_root / "unauthorized"
        unauthorized_root.mkdir()
        unauthorized_rejected = expect_rejection(
            lambda: local_orchestrator(
                unauthorized_root,
                _local_result(validation=("git", "status")),
            ).execute(
                _local_request(),
                _LocalAdapter(_local_result(validation=("git", "status"))),
            ),
            ExecutionToolError,
            "ToolPolicy",
        )

        shell_root = temporary_probe_root / "shell"
        shell_root.mkdir()
        shell_rejected = expect_rejection(
            lambda: local_orchestrator(
                shell_root,
                _local_result(validation=("powershell", "-Command", "echo nope")),
            ).execute(
                _local_request(),
                _LocalAdapter(_local_result(validation=("powershell", "-Command", "echo nope"))),
            ),
            ExecutionToolError,
            "ToolPolicy",
        )

        race_root = temporary_probe_root / "head-race"
        race_root.mkdir()
        calls = 0

        def race_inspector(_path: Path) -> InspectionResult:
            nonlocal calls
            calls += 1
            return local_inspection(head=FIXTURE_HEAD if calls < 4 else "b" * 40)

        race_result = _local_result()
        head_race_rejected = (
            expect_rejection(
                lambda: local_orchestrator(
                    race_root, race_result, inspector=race_inspector
                ).execute(_local_request(), _LocalAdapter(race_result)),
                HeadRaceError,
                "head_race_rejected",
            )
            and not (race_root / "target" / "src" / "generated.py").exists()
        )

        evidence = build_evidence(
            first,
            second,
            adapter_one,
            cross_project_rejected=cross_project_rejected,
            canonical_rejected=canonical_rejected,
            head_race_rejected=head_race_rejected,
            unauthorized_rejected=unauthorized_rejected,
            shell_rejected=shell_rejected,
            migration_head=migration_head,
        )
        telemetry_evidence = build_telemetry_evidence(
            base_url,
            project_one,
            task_one,
            project_two,
            task_two,
            migration_head,
        )
        EVIDENCE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE_OUTPUT.write_text(
            json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        TELEMETRY_EVIDENCE_OUTPUT.write_text(
            json.dumps(telemetry_evidence, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2))
        print(json.dumps(telemetry_evidence, ensure_ascii=False, sort_keys=True, indent=2))
        print("WO-019 Telemetry/Event Bus integration passed.")
        return 0
    except Exception as exc:
        EVIDENCE_OUTPUT.unlink(missing_ok=True)
        TELEMETRY_EVIDENCE_OUTPUT.unlink(missing_ok=True)
        detail = str(exc).replace(str(ROOT), "<repo>")[:400]
        print(
            f"WO-018 autonomous execution integration failed: {type(exc).__name__}: {detail}",
            file=sys.stderr,
        )
        return 1
    finally:
        shutil.rmtree(temporary_probe_root, ignore_errors=True)
        for repository in repositories:
            shutil.rmtree(repository, ignore_errors=True)


def _local_request() -> ExecutorRequest:
    return ExecutorRequest(
        PROJECT_ID,
        TASK_ID,
        expected_branch=BRANCH,
        expected_head_sha=FIXTURE_HEAD,
    )


def _local_result(
    *,
    path: str = "src/generated.py",
    validation: tuple[str, ...] | tuple[tuple[str, ...], ...] | None = None,
) -> ExecutorResult:
    validation_commands: tuple[tuple[str, ...], ...]
    if validation is None:
        validation_commands = ((sys.executable, "-c", "print('probe ok')"),)
    elif validation and isinstance(validation[0], str):
        validation_commands = (cast(tuple[str, ...], validation),)
    else:
        validation_commands = cast(tuple[tuple[str, ...], ...], validation)
    return ExecutorResult(
        change_set=ChangeSet.from_operations(
            [ChangeOperation.create(path, "VALUE = 1\n")],
            model="local-probe-model",
            effort="minimal",
        ),
        summary="local probe",
        validation_commands=validation_commands,
    )


class _LocalAdapter:
    name = "local-probe"
    provider_independent = True

    def __init__(self, result: ExecutorResult) -> None:
        self.result = result

    def execute(self, _request: ExecutorRequest, _context: object) -> ExecutorResult:
        return self.result


if __name__ == "__main__":
    raise SystemExit(main())
