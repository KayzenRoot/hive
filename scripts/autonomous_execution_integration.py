"""Exercise the real Docker execution seam and its durable Telemetry/Event Bus."""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from queue import Empty, Queue
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
from app.telemetry import (  # noqa: E402
    CANONICAL_EVENT_TYPES,
    EVENT_CURSOR_MAX_BYTES,
    EVENT_PAYLOAD_MAX_BYTES,
    EventEnvelope,
    EventPage,
)

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
RUN_CORRELATED_EVENT_TYPES = frozenset(
    {
        "executor.started",
        "tool.called",
        "file.changed",
        "test.started",
        "test.finished",
        "validation.failed",
        "validation.passed",
        "run.completed",
        "run.failed",
    }
)
TASK_CORRELATED_EVENT_TYPES = frozenset(
    {
        "task.ingested",
        "context.started",
        "context.retrieved",
        "context.built",
        "cache.hit",
        "cache.miss",
    }
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
        detail = response.get("detail") if isinstance(response, dict) else None
        detail_suffix = ""
        if isinstance(detail, str):
            bounded_detail = detail.replace(str(ROOT), "<repo>")[:240]
            detail_suffix = f"; detail={bounded_detail}"
        raise AssertionError(
            f"API {method} {path}: expected {expected_status}, got {status}{detail_suffix}"
        )
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


def _bounded_cli_stream(raw: bytes) -> str:
    """Return a small, redacted head/tail sample suitable for CI diagnostics."""

    limit = 160
    omitted = max(0, len(raw) - (limit * 2))
    sample = raw[:limit]
    if omitted:
        sample += f"\n... {omitted} bytes omitted ...\n".encode("ascii")
        sample += raw[-limit:]
    text = sample.decode("utf-8", errors="replace")
    text = text.replace(str(ROOT), "<repo>").replace(str(ROOT).replace("\\", "/"), "<repo>")
    text = re.sub(r"(?i)\bBearer\s+[^\s,;]+", "Bearer <redacted>", text)
    text = re.sub(
        r"(?i)([\"']?[\w.-]*(?:api[_-]?key|token|secret|password|authorization)"
        r"[\w.-]*[\"']?\s*[:=]\s*[\"']?)([^\"'\s,;}]+)",
        r"\1<redacted>",
        text,
    )
    text = re.sub(r"\b[A-Za-z]:\\(?:[^\\\s\"']+\\)*[^\\\s\"']*", "<path>", text)
    text = re.sub(r"(?<![:\w])/(?:[\w.-]+/)+[\w.-]*", "<path>", text)
    return json.dumps(text, ensure_ascii=True)


def run_executor_cli(command: list[str], *, cwd: Path = ROOT) -> dict[str, Any]:
    """Run the machine-readable executor CLI and retain bounded failure evidence."""

    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        check=False,
        shell=False,
    )
    stdout_bytes = len(result.stdout)
    stderr_bytes = len(result.stderr)
    diagnostic = (
        f"exit_code={result.returncode}, stdout_bytes={stdout_bytes}, stderr_bytes={stderr_bytes}, "
        f"stdout_head_tail={_bounded_cli_stream(result.stdout)}, "
        f"stderr_head_tail={_bounded_cli_stream(result.stderr)}"
    )
    if result.returncode != 0:
        stderr_text = result.stderr.decode("utf-8", errors="replace").strip()
        try:
            stderr_payload = json.loads(stderr_text)
        except json.JSONDecodeError:
            stderr_payload = None
        if isinstance(stderr_payload, dict) and stderr_payload.get("status") == "ERROR":
            error_code = stderr_payload.get("code")
            if (
                not isinstance(error_code, str)
                or re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", error_code) is None
            ):
                error_code = "unknown"
            failure_kind = f"executor_error_code={error_code}"
        else:
            failure_kind = "nonzero_compose_or_container_process"
        raise AssertionError(f"executor service CLI {failure_kind} ({diagnostic})")

    raw = result.stdout.decode("utf-8", errors="replace").strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            "executor service CLI returned invalid JSON "
            f"(json_error={exc.msg}, line={exc.lineno}, column={exc.colno}; {diagnostic})"
        ) from exc
    if not isinstance(payload, dict):
        raise AssertionError(f"executor service CLI returned non-object JSON ({diagnostic})")
    return cast(dict[str, Any], payload)


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


def cleanup_registered_fixtures(relative_paths: tuple[str, ...]) -> set[str]:
    """Remove only this run's durable fixture graph and prove it is gone."""

    if not relative_paths:
        return set()
    expected_paths = (
        f"wo019-c4-{os.getpid()}-one",
        f"wo019-c4-{os.getpid()}-two",
        f"wo029-c3-{os.getpid()}-executor",
    )
    if relative_paths != expected_paths:
        raise AssertionError("fixture cleanup received an unexpected relative path")
    path_sql = ", ".join(f"'{path}'" for path in relative_paths)
    cleanup_sql = f"""
BEGIN;
CREATE TEMP TABLE c4_fixture_blobs ON COMMIT DROP AS
SELECT DISTINCT t.extraction_id, t.original_blob_sha256
FROM tasks AS t
JOIN projects AS p ON p.project_id = t.project_id
WHERE p.relative_path IN ({path_sql});
DELETE FROM retrieval_references
WHERE project_id IN (SELECT project_id FROM projects WHERE relative_path IN ({path_sql}));
DELETE FROM retrieval_chunk_embeddings
WHERE project_id IN (SELECT project_id FROM projects WHERE relative_path IN ({path_sql}));
DELETE FROM retrieval_embedding_runs
WHERE project_id IN (SELECT project_id FROM projects WHERE relative_path IN ({path_sql}));
DELETE FROM retrieval_chunks
WHERE project_id IN (SELECT project_id FROM projects WHERE relative_path IN ({path_sql}));
DELETE FROM retrieval_corpus_runs
WHERE project_id IN (SELECT project_id FROM projects WHERE relative_path IN ({path_sql}));
DELETE FROM repository_symbols
WHERE project_id IN (SELECT project_id FROM projects WHERE relative_path IN ({path_sql}));
DELETE FROM repository_files
WHERE project_id IN (SELECT project_id FROM projects WHERE relative_path IN ({path_sql}));
DELETE FROM repository_index_runs
WHERE project_id IN (SELECT project_id FROM projects WHERE relative_path IN ({path_sql}));
DELETE FROM telemetry_events
WHERE project_id IN (SELECT project_id FROM projects WHERE relative_path IN ({path_sql}));
DELETE FROM tasks
WHERE project_id IN (SELECT project_id FROM projects WHERE relative_path IN ({path_sql}));
DELETE FROM task_extractions AS e
USING c4_fixture_blobs AS b
WHERE e.extraction_id = b.extraction_id
  AND NOT EXISTS (SELECT 1 FROM tasks AS t WHERE t.extraction_id = e.extraction_id);
WITH deleted_cas AS (
    DELETE FROM cas_blobs AS c
    USING c4_fixture_blobs AS b
    WHERE c.sha256 = b.original_blob_sha256
      AND NOT EXISTS (SELECT 1 FROM tasks AS t WHERE t.original_blob_sha256 = c.sha256)
      AND NOT EXISTS (SELECT 1 FROM task_extractions AS e WHERE e.source_sha256 = c.sha256)
    RETURNING c.sha256
)
SELECT 'CAS_ORPHAN:' || sha256 FROM deleted_cas;
DELETE FROM projects WHERE relative_path IN ({path_sql});
SELECT 'PROJECTS:' || count(*) FROM projects WHERE relative_path IN ({path_sql});
COMMIT;
"""
    output = run_command(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            os.environ.get("POSTGRES_USER", "hive"),
            "-d",
            os.environ.get("POSTGRES_DB", "hive"),
            "-Atqc",
            cleanup_sql,
        ]
    )
    lines = output.splitlines()
    project_lines = [line for line in lines if line.startswith("PROJECTS:")]
    if project_lines != ["PROJECTS:0"]:
        remaining = project_lines[-1] if project_lines else "missing project cleanup assertion"
        raise AssertionError(f"fixture cleanup left {remaining} registered projects")
    return {line.removeprefix("CAS_ORPHAN:") for line in lines if line.startswith("CAS_ORPHAN:")}


def remove_unreferenced_cas_files(digests: set[str]) -> None:
    """Remove and verify only CAS files whose database rows were deleted."""

    raw_data_root = Path(os.environ.get("HIVE_DATA_ROOT", ".hive-data"))
    data_root = raw_data_root if raw_data_root.is_absolute() else ROOT / raw_data_root
    cas_root = data_root.resolve() / "cas" / "sha256"
    for digest in digests:
        path = cas_root / digest[:2] / f"{digest[2:]}.zst"
        if not path.exists():
            continue
        container_path = f"/var/lib/hive/cas/sha256/{digest[:2]}/{digest[2:]}.zst"
        try:
            path.unlink()
        except (PermissionError, OSError):
            try:
                os.chmod(path, stat.S_IWRITE)
                path.unlink()
            except (PermissionError, OSError):
                run_command(["docker", "compose", "exec", "-T", "api", "rm", "-f", container_path])
        if path.exists():
            raise AssertionError(f"CAS fixture artifact remains: {path}")


def remove_filesystem_fixture(path: Path) -> None:
    """Remove a fixture tree, clearing container-created read-only files, then verify it."""

    if not path.exists():
        return

    def retry_readonly(
        function: Callable[..., object], failed_path: str, _exc_info: object
    ) -> None:
        os.chmod(failed_path, stat.S_IWRITE)
        function(failed_path)

    shutil.rmtree(path, onerror=retry_readonly)
    if path.exists():
        raise AssertionError(f"fixture filesystem path remains: {path}")


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


def task_ids_are_scoped(task_ids: list[UUID | None], expected_task_id: UUID) -> bool:
    """Allow project-level events without tasks; reject foreign task bindings."""

    return all(task_id is None or task_id == expected_task_id for task_id in task_ids)


def execution_run_ids_are_present(events: list[tuple[str, UUID | None]]) -> bool:
    """Require run correlation on execution lifecycle events, not project telemetry."""

    run_ids = [run_id for event_type, run_id in events if event_type in RUN_CORRELATED_EVENT_TYPES]
    return bool(run_ids) and all(run_id is not None for run_id in run_ids)


def event_linkage_is_explicit(events: list[tuple[str, UUID | None, UUID | None]]) -> bool:
    """Validate task/run identity according to each canonical event's lifecycle scope."""

    if not events:
        return False
    for event_type, task_id, run_id in events:
        if event_type in RUN_CORRELATED_EVENT_TYPES:
            if task_id is None or run_id is None:
                return False
        elif event_type == "project.indexing":
            if task_id is not None or run_id is None:
                return False
        elif event_type in TASK_CORRELATED_EVENT_TYPES:
            if task_id is None or run_id is not None:
                return False
        elif event_type == "project.discovered" and (task_id is not None or run_id is not None):
            return False
    return True


def terminal_replay_after_cursor(events: list[tuple[str, str]]) -> str:
    """Choose the cursor immediately before a terminal event for replay assertions."""

    for index, (event_type, _) in enumerate(events):
        if event_type in {"run.completed", "run.failed"}:
            if index == 0:
                raise AssertionError("terminal execution event has no preceding replay cursor")
            return events[index - 1][1]
    raise AssertionError("terminal execution event is missing")


def register_fixture(base_url: str, relative_path: str) -> tuple[ProjectResponse, TaskResponse]:
    try:
        project_payload = api_call(
            base_url,
            "POST",
            "/api/v1/projects",
            payload={"name": "WO-018 autonomous fixture", "relative_path": relative_path},
            expected_status=201,
        )
    except AssertionError as exc:
        raise AssertionError(f"{exc}; fixture_relative_path={relative_path}") from exc
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
) -> dict[str, object]:
    """Invoke the production emitter inside the already-running API container."""

    if task_id is None or run_id is None or provenance is None:
        raise AssertionError("integration telemetry requires task/run/provenance identity")
    code = (
        "import json; from uuid import UUID; "
        "from app.config import Settings; "
        "from app.telemetry import TelemetryValidationError, emit_event; "
        f"event = emit_event(Settings(), UUID({str(project_id)!r}), {event_type!r}, "
        f"{payload!r}, task_id=UUID({str(task_id)!r}), run_id=UUID({str(run_id)!r}), "
        f"provenance={provenance!r}, emission_key={emission_key!r}); "
        "print(json.dumps(event.model_dump(mode='json'), sort_keys=True))"
    )
    output = run_command(["docker", "compose", "exec", "-T", "api", "python", "-c", code])
    try:
        event = json.loads(output)
    except json.JSONDecodeError as exc:
        raise AssertionError("production telemetry emitter returned invalid JSON") from exc
    if not isinstance(event, dict):
        raise AssertionError("production telemetry emitter returned a non-object")
    return cast(dict[str, object], event)


class LocalProviderServer:
    """Credential-free HTTP fixture that exercises the production executor transport."""

    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                try:
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                    self.send_response(400)
                    self.end_headers()
                    return
                if not isinstance(payload, dict) or self.path != "/v1/chat/completions":
                    self.send_response(404)
                    self.end_headers()
                    return
                owner.requests.append(cast(dict[str, object], payload))
                provider_result = {
                    "operations": [
                        {
                            "kind": "create",
                            "path": "src/generated.py",
                            "content_base64": base64.b64encode(b"VALUE = 1\n").decode("ascii"),
                        }
                    ],
                    "summary": (
                        f"Generated one bounded file; {TEST_SENTINEL}; "
                        "source=C:\\Users\\fixture\\private.txt"
                    ),
                    "decisions": ["Reuse Context Manager and Local Verified Runner."],
                    "test_commands": [["python", "-c", "print('wo018 test passed')"]],
                    "validation_commands": [["python", "-c", "print('wo018 validation passed')"]],
                    "errors_fixed": [],
                    "risks": ["No canonical promotion is performed."],
                    "pending_items": ["External Sol review remains required."],
                    "proposed_checkpoint_update": (
                        "Propose no checkpoint mutation from this execution."
                    ),
                }
                body = json.dumps(
                    {
                        "id": "wo029-c3-integration-request",
                        "model": "hive-integration-model",
                        "choices": [{"message": {"content": json.dumps(provider_result)}}],
                        "usage": {
                            "prompt_tokens": 100,
                            "prompt_tokens_details": {"cached_tokens": 64},
                            "completion_tokens": 8,
                        },
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        self.server = ThreadingHTTPServer(("0.0.0.0", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> LocalProviderServer:
        self.thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    @property
    def port(self) -> int:
        return int(self.server.server_address[1])

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    @property
    def container_base_url(self) -> str:
        return f"http://host.docker.internal:{self.port}/v1"


def execute_docker_fixture(
    base_url: str,
    projects_root: Path,
    relative_path: str,
) -> tuple[object, ProjectResponse, TaskResponse]:
    project, task = register_fixture(base_url, relative_path)
    with LocalProviderServer() as provider:
        settings = Settings(
            projects_root=projects_root,
            executor_enabled=True,
            executor_base_url=provider.base_url,
            executor_model="hive-integration-model",
            executor_timeout_seconds=5,
            executor_max_response_bytes=200_000,
            executor_prompt_cache_enabled=True,
        )
        orchestrator = ExecutionOrchestrator(
            settings,
            tool_policy=ToolPolicy((sys.executable, "python")),
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
        result = orchestrator.execute_configured(request)
        if len(provider.requests) != 1:
            raise AssertionError("configured executor must perform exactly one provider request")
        provider_request = provider.requests[0]
        if provider_request.get("model") != "hive-integration-model":
            raise AssertionError("configured executor sent the wrong provider model")
        if provider_request.get("response_format") != {"type": "json_object"}:
            raise AssertionError("configured executor did not request structured JSON")
        if result.executor_provider_calls != 1 or result.executor_llm_calls != 1:
            raise AssertionError("configured executor call accounting is not authoritative")
        usage = result.provider_cache_usage
        if (
            usage is None
            or usage.reconciliation.value != "EXACT"
            or usage.cached_input_tokens != 64
            or usage.observed_hit is not True
        ):
            raise AssertionError("configured executor did not reconcile provider cache usage")
        page = telemetry_page(base_url, project.project_id, limit=20)
        terminal = next(
            (event for event in reversed(page.events) if event.event_type == "run.completed"),
            None,
        )
        if terminal is None:
            raise AssertionError("configured executor terminal telemetry was not persisted")
        payload = terminal.payload
        if (
            payload.get("executor_provider_calls") != 1
            or payload.get("executor_llm_calls") != 1
            or payload.get("input_tokens") != 100
            or payload.get("cached_tokens") != 64
            or payload.get("fresh_tokens") != 36
            or payload.get("output_tokens") != 8
            or payload.get("usage_reconciled") is not True
            or payload.get("provider_final_usage") is not True
        ):
            raise AssertionError("configured executor usage telemetry is not truthful")
        return result, project, task


def verify_executor_service_cli(base_url: str, relative_path: str) -> None:
    """Exercise the shipping writable executor service through its CLI entry point."""

    project, task = register_fixture(base_url, relative_path)
    with LocalProviderServer() as provider:
        # Preserve stdout as a single JSON document; an allocated TTY can merge
        # executor stderr diagnostics into the machine-readable CLI response.
        command = ["docker", "compose", "run", "--rm", "-T"]
        user_id = getattr(os, "getuid", None)
        group_id = getattr(os, "getgid", None)
        if callable(user_id) and callable(group_id):
            command.extend(["--user", f"{user_id()}:{group_id()}"])
        command.extend(
            [
                "-e",
                "HIVE_EXECUTOR_ENABLED=true",
                "-e",
                f"HIVE_EXECUTOR_BASE_URL={provider.container_base_url}",
                "-e",
                "HIVE_EXECUTOR_MODEL=hive-integration-model",
                "-e",
                "HIVE_EXECUTOR_PROMPT_CACHE_ENABLED=true",
                "executor",
                "--project-id",
                str(project.project_id),
                "--task-id",
                str(task.task_id),
                "--expected-branch",
                str(project.git_branch),
                "--expected-head-sha",
                str(project.git_head_sha),
            ]
        )
        payload = run_executor_cli(command)
        if payload.get("status") != "STAGED":
            raise AssertionError("executor service CLI did not complete a staged run")
        if payload.get("executor_provider_calls") != 1 or payload.get("executor_llm_calls") != 1:
            raise AssertionError("executor service CLI did not preserve provider call accounting")
        cache_usage = payload.get("provider_cache_usage")
        if (
            not isinstance(cache_usage, dict)
            or cache_usage.get("reconciliation") != "EXACT"
            or cache_usage.get("cached_input_tokens") != 64
        ):
            raise AssertionError("executor service CLI did not preserve provider cache receipt")
        if len(provider.requests) != 1:
            raise AssertionError("executor service CLI did not cross the concrete HTTP transport")

    page = telemetry_page(base_url, project.project_id, limit=20)
    terminal = next(
        (event for event in reversed(page.events) if event.event_type == "run.completed"),
        None,
    )
    if terminal is None:
        raise AssertionError("executor service CLI terminal telemetry was not persisted")
    telemetry_payload = terminal.payload
    if (
        telemetry_payload.get("executor_provider_calls") != 1
        or telemetry_payload.get("input_tokens") != 100
        or telemetry_payload.get("cached_tokens") != 64
        or telemetry_payload.get("fresh_tokens") != 36
        or telemetry_payload.get("output_tokens") != 8
        or telemetry_payload.get("usage_reconciled") is not True
    ):
        raise AssertionError("executor service CLI usage telemetry is incomplete")


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
) -> EventPage:
    query = f"?limit={limit}"
    if after is not None:
        query += f"&after={after}"
    response = api_call(base_url, "GET", f"/api/v1/projects/{project_id}/events{query}")
    if not isinstance(response, dict):
        raise AssertionError("telemetry page is not an object")
    return EventPage.model_validate(response)


def telemetry_stream(base_url: str, project_id: UUID, after: str) -> str:
    request = urllib.request.Request(
        f"{base_url}/api/v1/projects/{project_id}/events/stream"
        f"?after={after}&max_events=1&timeout_seconds=3",
        method="GET",
        headers={"Accept": "text/event-stream"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return cast(bytes, response.read(200_000)).decode("utf-8")
    except (OSError, urllib.error.URLError, UnicodeDecodeError) as exc:
        raise AssertionError("telemetry SSE stream failed") from exc


def open_live_telemetry_stream(
    base_url: str,
    project_id: UUID,
    after: str,
) -> tuple[threading.Thread, Queue[object]]:
    """Open the SSE connection before the producer emits the target event."""

    ready = threading.Event()
    result: Queue[object] = Queue(maxsize=1)
    request = urllib.request.Request(
        f"{base_url}/api/v1/projects/{project_id}/events/stream"
        f"?after={after}&max_events=1&timeout_seconds=10",
        method="GET",
        headers={"Accept": "text/event-stream"},
    )

    def receive() -> None:
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                ready.set()
                result.put(response.read(200_000).decode("utf-8"))
        except Exception as exc:
            ready.set()
            result.put(exc)

    thread = threading.Thread(target=receive, name="wo019-live-sse", daemon=True)
    thread.start()
    if not ready.wait(timeout=5):
        raise AssertionError("SSE connection did not open within the bounded timeout")
    return thread, result


def read_live_telemetry_stream(thread: threading.Thread, result: Queue[object]) -> str:
    try:
        value = result.get(timeout=15)
    except Empty as exc:
        raise AssertionError("open SSE stream did not receive an event in time") from exc
    thread.join(timeout=1)
    if isinstance(value, Exception):
        raise AssertionError("open SSE stream failed") from value
    if not isinstance(value, str):
        raise AssertionError("open SSE stream returned an invalid result")
    return value


def telemetry_sanitization_probe() -> bool:
    """Exercise the production sanitizer with embedded sensitive values."""

    code = (
        "from app.telemetry import TelemetryValidationError, sanitize_payload\n"
        "bad = [\n"
        "    '/',\n"
        "    '/secret.txt',\n"
        "    '/secret.txt/',\n"
        "    'embedded /secret.txt',\n"
        "    'embedded /safe+name.txt',\n"
        "    'embedded /safe%20name.txt',\n"
        "    r'embedded C:\\Users\\fixture\\secret.txt',\n"
        "    r'embedded \\\\server\\share\\secret.txt',\n"
        "    'embedded /home/fixture/secret.txt',\n"
        "    'prefix Authorization: Bearer abc.def.ghi',\n"
        "    'prefix api_key=embedded-secret',\n"
        "    'prefix client_secret=embedded-secret',\n"
        "    'prefix password: embedded-secret',\n"
        "    'prefix token=embedded-secret',\n"
        "    'prefix https://example.com/path?api_key=embedded-secret',\n"
        "    'prefix https://example.com/path#client_secret=embedded-secret',\n"
        "    'Authorization/Bearer',\n"
        "    'AK' + 'IA1234567890ABCDEF',\n"
        "    'prefix WO018_TEST_SECRET_DO_NOT_LEAK_integration',\n"
        "    'prefix Bearer x',\n"
        "    'prefix https://user:pass@example.com/path',\n"
        "    'prefix https://user%3Apass%40example.com/path',\n"
        "    'prefix postgres://user:pass@host/db',\n"
        "    'prefix redis://:secret@redis:6379/0',\n"
        "    '%252Fsecret.txt',\n"
        "    'prefix %252Fhome%252Fuser%252Fsecret.txt',\n"
        "    'prefix https://example.com/path?api%5Fkey=embedded-secret',\n"
        "    'prefix https://example.com/path?api%5Fkey%3Dembedded-secret',\n"
        "    'OPENAI_API_KEY=embedded-secret',\n"
        "    'GITHUB_TOKEN: embedded-secret',\n"
        "    'AUTH_TOKEN%3Dembedded-secret',\n"
        "    'MY_API_KEY=foo',\n"
        "    'https://example.com?MY_API_KEY=foo',\n"
        "    'https://example.com/path#DATABASE_PASSWORD=foo',\n"
        "    'https://example.com?a=1&AWS_ACCESS_TOKEN=foo',\n"
        "    'https://example.com?HIVE_CLIENT_SECRET%3Dfoo',\n"
        "    'DATABASE_PASSWORD=foo',\n"
        "    'AWS_ACCESS_TOKEN=foo',\n"
        "    'HIVE_CLIENT_SECRET=foo',\n"
        "    'MY_REFRESH_TOKEN=foo',\n"
        "    'APP_AUTH_TOKEN=foo',\n"
        "    'file:///home/user/secret.txt',\n"
        "    'file:///secret.txt',\n"
        "    'file:/etc/passwd',\n"
        "    {'DATABASE_PASSWORD': 'safe'},\n"
        "    '/n',\n"
        "    'prefix /n suffix',\n"
        "    '/segredo-ç.txt',\n"
        "    '/home/usuário/segredo.txt',\n"
        "    '/🔒/secret.txt',\n"
        "]\n"
        "for value in bad:\n"
        "    try:\n"
        "        sanitize_payload({'message': value})\n"
        "    except TelemetryValidationError:\n"
        "        continue\n"
        "    raise AssertionError('unsafe value accepted')\n"
        "for value in ({'/secret.txt': 'safe'}, {'api_key': 'safe'}, "
        "{'GITHUB_TOKEN': 'safe'}, {'nested': {'/secret.txt': 'safe'}}):\n"
        "    try:\n"
        "        sanitize_payload(value)\n"
        "    except TelemetryValidationError:\n"
        "        continue\n"
        "    raise AssertionError('unsafe object key accepted')\n"
        "safe = sanitize_payload({"
        "'path': 'src/module.py', 'url': 'https://example.com/path', "
        "'query_url': 'https://example.com?a=1&b=2', "
        "'doc_url': 'https://example.com/documentação', "
        "'input_tokens': 12, 'output_tokens': 34, "
        "'message': 'ordinary prose with / between words'})\n"
        "assert safe['path'] == 'src/module.py'\n"
        "assert safe['url'] == 'https://example.com/path'\n"
        "assert safe['input_tokens'] == 12\n"
        "print('sanitization-pass')\n"
    )
    return run_command(["docker", "compose", "exec", "-T", "api", "python", "-c", code]) == (
        "sanitization-pass"
    )


def cross_project_binding_probe(project: ProjectResponse, task: TaskResponse) -> bool:
    """Prove the production emitter rejects a foreign task binding."""

    code = (
        "from uuid import UUID; "
        "from app.config import Settings; "
        "from app.telemetry import TelemetryValidationError, emit_event\n"
        "try:\n    "
        f"emit_event(Settings(), UUID({str(project.project_id)!r}), 'tool.called', "
        "{'operation': 'cross-project-probe'}, "
        f"task_id=UUID({str(task.task_id)!r}), "
        "run_id=UUID('00000000-0000-0000-0000-000000000820'), "
        "provenance={'producer': 'integration', 'deterministic': True}, "
        "emission_key='integration:cross-project-probe')"
        "\nexcept TelemetryValidationError:\n"
        "    print('cross-project-pass')\n"
        "else:\n"
        "    raise AssertionError('foreign task binding accepted')\n"
    )
    return run_command(["docker", "compose", "exec", "-T", "api", "python", "-c", code]) == (
        "cross-project-pass"
    )


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
        "from app.telemetry import TelemetryValidationError, emit_event; "
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
        "assert first.event_id == second.event_id\n"
        "try:\n    "
        f"emit_event(Settings(), UUID({str(project.project_id)!r}), "
        "'run.completed', {'adapter': 'different-content'}, "
        f"task_id=UUID({str(task.task_id)!r}), run_id=UUID({str(run_id)!r}), "
        "provenance={'producer': 'integration', 'deterministic': True}, "
        "emission_key='integration:idempotency-probe')"
        "\nexcept TelemetryValidationError:\n"
        "    pass\n"
        "else:\n"
        "    raise AssertionError('semantic collision accepted')\n"
        f"typed_first = emit_event(Settings(), UUID({str(project.project_id)!r}), "
        "'tool.called', {'nested': {'flag': True}, 'items': [False]}, "
        f"task_id=UUID({str(task.task_id)!r}), run_id=UUID({str(run_id)!r}), "
        "provenance={'producer': 'integration', 'deterministic': True}, "
        "emission_key='integration:type-safe-probe')\n"
        "try:\n    "
        f"emit_event(Settings(), UUID({str(project.project_id)!r}), "
        "'tool.called', {'nested': {'flag': 1}, 'items': [0]}, "
        f"task_id=UUID({str(task.task_id)!r}), run_id=UUID({str(run_id)!r}), "
        "provenance={'producer': 'integration', 'deterministic': True}, "
        "emission_key='integration:type-safe-probe')\n"
        "except TelemetryValidationError:\n"
        "    print('idempotency-pass')\n"
        "else:\n"
        "    raise AssertionError('boolean-number collision accepted')"
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
    execution_result: object,
) -> dict[str, object]:
    first_page = telemetry_page(base_url, project_one.project_id, limit=1)
    if len(first_page.events) != 1:
        raise AssertionError("telemetry pagination did not return the first bounded page")
    all_one_page = telemetry_page(base_url, project_one.project_id, limit=100)
    all_one_events = all_one_page.events
    replay_after_cursor = terminal_replay_after_cursor(
        [(event.event_type, event.cursor) for event in all_one_events]
    )
    replay_page = telemetry_page(
        base_url, project_one.project_id, after=replay_after_cursor, limit=100
    )
    replay_events = replay_page.events
    second_page = telemetry_page(base_url, project_two.project_id, limit=100)
    second_events = second_page.events
    if len(all_one_events) < 2 or len(second_events) < 2:
        raise AssertionError("real execution did not emit both lifecycle events")
    stable_order_replay = [event.ordering_id for event in all_one_events] == sorted(
        event.ordering_id for event in all_one_events
    )
    if not stable_order_replay:
        raise AssertionError("telemetry ordering is not stable")
    if any(event.project_id != project_one.project_id for event in all_one_events):
        raise AssertionError("project one telemetry is not isolated")
    if any(event.project_id != project_two.project_id for event in second_events):
        raise AssertionError("project two telemetry is not isolated")
    if not task_ids_are_scoped([event.task_id for event in all_one_events], task_one.task_id):
        raise AssertionError("task binding is not project scoped")
    if not task_ids_are_scoped([event.task_id for event in second_events], task_two.task_id):
        raise AssertionError("second task binding is not project scoped")
    if not execution_run_ids_are_present(
        [(event.event_type, event.run_id) for event in (*all_one_events, *second_events)]
    ):
        raise AssertionError("execution telemetry is missing run correlation")
    stream = telemetry_stream(base_url, project_one.project_id, replay_after_cursor)
    if f"id: {replay_events[0].cursor}" not in stream:
        raise AssertionError("SSE replay did not return the missed event")
    if replay_events[0].event_type not in {"run.completed", "run.failed"}:
        raise AssertionError("terminal execution event is missing")
    replay_ids = {event.event_id for event in replay_events}
    reconnect_stream = telemetry_stream(base_url, project_one.project_id, replay_after_cursor)
    reconnect_ids = {
        line[4:].strip() for line in reconnect_stream.splitlines() if line.startswith("id: ")
    }
    if not reconnect_ids or reconnect_ids != {event.cursor for event in replay_events}:
        raise AssertionError("SSE reconnect did not replay the same missed events")

    live_after = all_one_events[-1].cursor
    live_run_id = all_one_events[-1].run_id
    if live_run_id is None:
        raise AssertionError("live telemetry probe lacks a run binding")
    live_thread, live_result = open_live_telemetry_stream(
        base_url,
        project_one.project_id,
        live_after,
    )
    docker_event_emitter(
        Settings(),
        project_one.project_id,
        "tool.called",
        {"operation": "live-open-probe"},
        task_id=task_one.task_id,
        run_id=live_run_id,
        provenance={"producer": "integration_live_open", "deterministic": True},
        emission_key="integration:live-open-probe",
    )
    live_stream = read_live_telemetry_stream(live_thread, live_result)
    live_data = [
        json.loads(line[6:]) for line in live_stream.splitlines() if line.startswith("data: ")
    ]
    if len(live_data) != 1:
        raise AssertionError("open SSE stream did not deliver exactly one live event")
    live_event = EventEnvelope.model_validate(live_data[0])
    live_delivery = (
        live_event.event_type == "tool.called"
        and live_event.project_id == project_one.project_id
        and live_event.task_id == task_one.task_id
        and live_event.cursor != live_after
        and int(live_event.cursor) > int(live_after)
    )
    if not live_delivery:
        raise AssertionError("open SSE stream delivered an invalid live event")

    all_one_page = telemetry_page(base_url, project_one.project_id, limit=100)
    all_one_events = all_one_page.events
    all_ids = {event.event_id for event in all_one_events}
    if not replay_ids.issubset(all_ids) or any(
        event.cursor == replay_after_cursor for event in replay_events
    ):
        raise AssertionError("cursor replay duplicated or escaped the project history")

    raw = json.dumps(
        {
            "one": all_one_page.model_dump(mode="json"),
            "two": second_page.model_dump(mode="json"),
            "stream": stream,
            "reconnect": reconnect_stream,
            "live_stream": live_stream,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    secret_leaks = int(TEST_SENTINEL in raw)
    filesystem_path_leaks = int("C:\\Users\\fixture\\private.txt" in raw)
    if secret_leaks or filesystem_path_leaks:
        raise AssertionError("telemetry payload leaked the sentinel")
    duplicate_safe = duplicate_safety_probe(project_one, task_one)
    if not duplicate_safe:
        raise AssertionError("telemetry duplicate suppression probe failed")
    sanitization_safe = telemetry_sanitization_probe()
    if not sanitization_safe:
        raise AssertionError("telemetry sanitizer probe failed")
    cross_project_safe = cross_project_binding_probe(project_one, task_two)
    if not cross_project_safe:
        raise AssertionError("telemetry cross-project binding probe failed")

    before_restart_ids = {event.event_id for event in all_one_events}
    run_command(["docker", "compose", "restart", "api"])
    wait_for_api_health(base_url)
    after_api_restart = telemetry_page(base_url, project_one.project_id, limit=100)
    restart_events = after_api_restart.events
    restart_recovery = before_restart_ids.issubset({event.event_id for event in restart_events})
    if not restart_recovery:
        raise AssertionError("API restart lost durable telemetry history")

    redis_stopped = False
    redis_before_events = restart_events
    if not redis_before_events or redis_before_events[-1].run_id is None:
        raise AssertionError("Redis outage probe lacks a bounded run binding")
    redis_before_cursor = redis_before_events[-1].cursor
    redis_outage_event: EventEnvelope | None = None
    redis_outage_durable_read = False
    redis_outage_stream_delivery = False
    redis_outage_replay_cursors: set[str] = set()
    redis_outage_reconnect_cursors: set[str] = set()
    redis_restore_same_event = False
    redis_restore_no_duplicate = False
    try:
        run_command(["docker", "compose", "stop", "redis"])
        redis_stopped = True
        outage_thread, outage_result = open_live_telemetry_stream(
            base_url,
            project_one.project_id,
            redis_before_cursor,
        )
        outage_payload = docker_event_emitter(
            Settings(),
            project_one.project_id,
            "tool.called",
            {"operation": "redis-loss-new-event"},
            task_id=task_one.task_id,
            run_id=redis_before_events[-1].run_id,
            provenance={"producer": "integration_redis_loss", "deterministic": True},
            emission_key="integration:redis-loss-new-event",
        )
        redis_outage_event = EventEnvelope.model_validate(outage_payload)
        outage_stream = read_live_telemetry_stream(outage_thread, outage_result)
        outage_data = [
            json.loads(line[6:]) for line in outage_stream.splitlines() if line.startswith("data: ")
        ]
        redis_outage_stream_delivery = len(outage_data) == 1 and (
            EventEnvelope.model_validate(outage_data[0]).event_id == redis_outage_event.event_id
        )
        after_redis_loss = telemetry_page(base_url, project_one.project_id, limit=100)
        redis_events = after_redis_loss.events
        redis_outage_durable_read = any(
            event.event_id == redis_outage_event.event_id for event in redis_events
        )
        redis_replay_stream = telemetry_stream(
            base_url, project_one.project_id, redis_before_cursor
        )
        redis_outage_replay_cursors = {
            line[4:].strip() for line in redis_replay_stream.splitlines() if line.startswith("id: ")
        }
        redis_reconnect_stream = telemetry_stream(
            base_url, project_one.project_id, redis_before_cursor
        )
        redis_outage_reconnect_cursors = {
            line[4:].strip()
            for line in redis_reconnect_stream.splitlines()
            if line.startswith("id: ")
        }
    finally:
        if redis_stopped:
            run_command(["docker", "compose", "up", "-d", "redis"])
            wait_for_api_health(base_url)
    if redis_outage_event is None:
        raise AssertionError("Redis outage emitter did not return an event")
    restored_payload = docker_event_emitter(
        Settings(),
        project_one.project_id,
        "tool.called",
        {"operation": "redis-loss-new-event"},
        task_id=task_one.task_id,
        run_id=redis_before_events[-1].run_id,
        provenance={"producer": "integration_redis_loss", "deterministic": True},
        emission_key="integration:redis-loss-new-event",
    )
    restored_event = EventEnvelope.model_validate(restored_payload)
    after_redis_restore = telemetry_page(base_url, project_one.project_id, limit=100)
    restored_events = after_redis_restore.events
    redis_restore_same_event = restored_event.event_id == redis_outage_event.event_id
    redis_restore_no_duplicate = (
        sum(event.event_id == redis_outage_event.event_id for event in restored_events) == 1
    )
    redis_outage_cursors = {redis_outage_event.cursor}
    redis_loss_recovery = all(
        (
            redis_outage_durable_read,
            redis_outage_stream_delivery,
            redis_outage_cursors.issubset(redis_outage_replay_cursors),
            redis_outage_replay_cursors == redis_outage_reconnect_cursors,
            redis_restore_same_event,
            redis_restore_no_duplicate,
        )
    )
    if not redis_loss_recovery:
        raise AssertionError("Redis outage emission/replay/reconnect recovery was not proven")

    all_one_page = telemetry_page(base_url, project_one.project_id, limit=100)
    all_one_events = all_one_page.events
    observed_events = (*all_one_events, *second_events)
    project_scoped = all(
        event.project_id == expected_project
        for event, expected_project in (
            *((event, project_one.project_id) for event in all_one_events),
            *((event, project_two.project_id) for event in second_events),
        )
    )
    first_run_task_ids = [
        event.task_id for event in all_one_events if event.event_type in RUN_CORRELATED_EVENT_TYPES
    ]
    second_run_task_ids = [
        event.task_id for event in second_events if event.event_type in RUN_CORRELATED_EVENT_TYPES
    ]
    task_run_binding_scoped = (
        bool(first_run_task_ids)
        and bool(second_run_task_ids)
        and all(task_id == task_one.task_id for task_id in first_run_task_ids)
        and all(task_id == task_two.task_id for task_id in second_run_task_ids)
    )
    event_types = sorted({event.event_type for event in observed_events})
    event_ids = [event.event_id for event in observed_events]
    duplicate_canonical_events = len(event_ids) - len(set(event_ids))
    cross_project_leaks = sum(
        event.project_id != expected_project
        for event, expected_project in (
            *((event, project_one.project_id) for event in all_one_events),
            *((event, project_two.project_id) for event in second_events),
        )
    )
    payloads_bounded = all(
        len(json.dumps(event.payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        <= EVENT_PAYLOAD_MAX_BYTES
        for event in observed_events
    )
    producer_source = (ROOT / "backend" / "app" / "execution_orchestrator.py").read_text(
        encoding="utf-8"
    )
    producer_path_verified = all(
        marker in producer_source
        for marker in ("event_emitter", '"executor.started"', '"run.completed"', "_emit_event")
    )
    telemetry_source = (ROOT / "backend" / "app" / "telemetry.py").read_text(encoding="utf-8")
    postgres_canonical_architecture = all(
        marker in telemetry_source
        for marker in (
            "database_connection",
            "INSERT INTO telemetry_events",
            "FROM telemetry_events",
        )
    )
    redis_dependency_absent = not any(
        line.lstrip().startswith(("import redis", "from redis"))
        for line in telemetry_source.splitlines()
    )
    redis_noncanonical = (
        postgres_canonical_architecture
        and redis_dependency_absent
        and redis_loss_recovery
        and redis_outage_durable_read
    )
    executor_llm_calls = getattr(execution_result, "executor_llm_calls", None)
    executor_provider_calls = getattr(execution_result, "executor_provider_calls", None)
    deterministic_first = (
        getattr(execution_result, "provider_independent", False) is True
        and executor_llm_calls == 0
        and executor_provider_calls == 0
    )
    reconnect_replay = (
        bool(reconnect_ids)
        and reconnect_ids == {event.cursor for event in replay_events}
        and redis_outage_cursors.issubset(redis_outage_reconnect_cursors)
    )
    idempotent_duplicate_safe = duplicate_safe and redis_restore_no_duplicate
    near_realtime_stream = live_delivery and redis_outage_stream_delivery
    task_run_linkage_explicit = event_linkage_is_explicit(
        [(event.event_type, event.task_id, event.run_id) for event in observed_events]
    )
    telemetry_checks = {
        "postgres_canonical_architecture": postgres_canonical_architecture,
        "redis_noncanonical": redis_noncanonical,
        "project_scoped": project_scoped,
        "task_run_binding_scoped": task_run_binding_scoped,
        "stable_order_replay": stable_order_replay,
        "task_run_linkage_explicit": task_run_linkage_explicit,
        "idempotent_duplicate_safe": idempotent_duplicate_safe,
        "near_realtime_stream": near_realtime_stream,
        "reconnect_replay": reconnect_replay,
        "restart_recovery": restart_recovery,
        "redis_loss_recovery": redis_loss_recovery,
        "sanitization_safe": sanitization_safe,
        "producer_path_verified": producer_path_verified,
        "deterministic_first": deterministic_first,
    }
    failed_checks = [name for name, passed in telemetry_checks.items() if not passed]
    telemetry_pass = not failed_checks
    if failed_checks:
        raise AssertionError("telemetry evidence observations failed: " + ",".join(failed_checks))
    return {
        "status": "PASS" if telemetry_pass else "FAIL",
        "evidence_file": "telemetry-event-bus.json",
        "telemetry_evidence_version": "telemetry-event-bus-v1",
        "observed_migration_head": migration_head,
        "migration_base_head": "0006_memory_lifecycle_provenance",
        "migration_changed": migration_head != "0006_memory_lifecycle_provenance",
        "producer_path": "backend/app/execution_orchestrator.py",
        "durable_event_metadata_postgres": (
            postgres_canonical_architecture and restart_recovery and redis_loss_recovery
        ),
        "redis_noncanonical": redis_noncanonical,
        "project_scoped": project_scoped,
        "task_run_binding_scoped": task_run_binding_scoped,
        "cross_project_access_fail_closed": cross_project_safe and cross_project_leaks == 0,
        "event_envelope_versioned": all(
            event.envelope_version == "telemetry-event-bus-v1"
            for event in (*all_one_events, *second_events)
        ),
        "event_type_explicit": all(bool(event.event_type) for event in observed_events),
        "timestamp_order_identity_explicit": all(
            event.ordering_id > 0 and event.occurred_at.tzinfo is not None
            for event in observed_events
        ),
        "project_identity_explicit": all(event.project_id is not None for event in observed_events),
        "task_run_linkage_explicit": task_run_linkage_explicit,
        "payload_bounded": payloads_bounded and len(raw.encode("utf-8")) <= 200_000,
        "provenance_explicit": all(bool(event.provenance) for event in observed_events),
        "canonical_event_vocabulary": set(event_types).issubset(CANONICAL_EVENT_TYPES),
        "stable_order_replay": stable_order_replay,
        "bounded_cursor_pagination": first_page.limit == 1 and first_page.has_more is True,
        "idempotent_duplicate_safe": idempotent_duplicate_safe,
        "near_realtime_stream": near_realtime_stream,
        "stream_access_control_deterministic": cross_project_safe
        and all(event.project_id == project_one.project_id for event in all_one_events),
        "reconnect_replay": reconnect_replay,
        "restart_recovery": restart_recovery,
        "redis_loss_recovery": redis_loss_recovery,
        "payload_sanitized": sanitization_safe and secret_leaks == 0 and filesystem_path_leaks == 0,
        "untrusted_payload_cannot_mutate_governance": sanitization_safe and producer_path_verified,
        "deterministic_first": deterministic_first,
        "producer_path_verified": producer_path_verified,
        "bounded_claims": payloads_bounded
        and len(raw.encode("utf-8")) <= 200_000
        and 1 <= EVENT_CURSOR_MAX_BYTES <= 65_536,
        "redis_canonical_truth": False,
        "full_control_center_claimed": False,
        "full_v01_observability_claimed": False,
        "event_type_count": len(event_types),
        "payload_max_bytes": EVENT_PAYLOAD_MAX_BYTES,
        "cursor_max_bytes": EVENT_CURSOR_MAX_BYTES,
        "duplicate_canonical_events": duplicate_canonical_events,
        "cross_project_leaks": cross_project_leaks,
        "secret_leaks": secret_leaks,
        "filesystem_path_leaks": filesystem_path_leaks,
        "llm_calls": executor_llm_calls,
        "provider_calls": executor_provider_calls,
        "implemented_event_types": event_types,
    }


def build_evidence(
    result_one: object,
    result_two: object,
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
            and result_payload["adapter"]["name"] == "openai-compatible-http"
            and result_payload["executor_llm_calls"] == 1
            and result_payload["executor_provider_calls"] == 1
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
    temporary_probe_root: Path | None = None
    raw_projects_root = os.environ.get("HIVE_PROJECTS_ROOT", ".hive-projects")
    projects_root = Path(raw_projects_root)
    if not projects_root.is_absolute():
        projects_root = ROOT / projects_root
    projects_root = projects_root.resolve()
    projects_root.mkdir(parents=True, exist_ok=True)
    base_url = f"http://127.0.0.1:{os.environ.get('HIVE_API_PORT', '8000')}"
    repositories: list[Path] = []
    fixture_relative_paths: tuple[str, ...] = ()
    failure_detail: str | None = None
    exit_code = 1
    evidence: dict[str, object] | None = None
    telemetry_evidence: dict[str, object] | None = None
    cas_cleanup_verified = False
    try:
        temporary_probe_root = Path(tempfile.mkdtemp(prefix="wo019-c4-probes-", dir=ROOT / "tmp"))
        health = api_call(base_url, "GET", "/api/v1/health")
        if not isinstance(health, dict) or health.get("status") != "ok":
            raise AssertionError("Docker HIVE API is not healthy")
        migration_head = current_migration_head()
        if migration_head != MIGRATION_HEAD:
            raise AssertionError("unexpected migration head")

        first_relative = f"wo019-c4-{os.getpid()}-one"
        second_relative = f"wo019-c4-{os.getpid()}-two"
        executor_relative = f"wo029-c3-{os.getpid()}-executor"
        first_repository = projects_root / first_relative
        second_repository = projects_root / second_relative
        executor_repository = projects_root / executor_relative
        fixture_relative_paths = (first_relative, second_relative, executor_relative)
        repositories.extend((first_repository, second_repository, executor_repository))
        create_repository(first_repository)
        create_repository(second_repository)
        create_repository(executor_repository)
        first, project_one, task_one = execute_docker_fixture(
            base_url, projects_root, first_relative
        )
        second, project_two, task_two = execute_docker_fixture(
            base_url, projects_root, second_relative
        )
        verify_executor_service_cli(base_url, executor_relative)

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

        telemetry_probe_root = temporary_probe_root / "telemetry-deterministic"
        telemetry_probe_root.mkdir()
        telemetry_probe_seed = _local_result()
        telemetry_probe_result = local_orchestrator(
            telemetry_probe_root, telemetry_probe_seed
        ).execute(_local_request(), _LocalAdapter(telemetry_probe_seed))

        evidence = build_evidence(
            first,
            second,
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
            telemetry_probe_result,
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
        exit_code = 0
    except Exception as exc:
        EVIDENCE_OUTPUT.unlink(missing_ok=True)
        TELEMETRY_EVIDENCE_OUTPUT.unlink(missing_ok=True)
        failure_detail = f"{type(exc).__name__}: {str(exc).replace(str(ROOT), '<repo>')[:400]}"
    finally:
        cleanup_errors: list[str] = []
        orphan_cas_digests: set[str] = set()
        try:
            orphan_cas_digests = cleanup_registered_fixtures(fixture_relative_paths)
            remove_unreferenced_cas_files(orphan_cas_digests)
            cas_cleanup_verified = True
        except Exception as exc:
            cleanup_errors.append(
                f"{type(exc).__name__}: {str(exc).replace(str(ROOT), '<repo>')[:300]}"
            )
        paths_to_remove = (
            [temporary_probe_root] if temporary_probe_root is not None else []
        ) + repositories
        for path in paths_to_remove:
            try:
                remove_filesystem_fixture(path)
            except Exception as exc:
                cleanup_errors.append(
                    f"{type(exc).__name__}: {str(exc).replace(str(ROOT), '<repo>')[:300]}"
                )
        if cleanup_errors:
            EVIDENCE_OUTPUT.unlink(missing_ok=True)
            TELEMETRY_EVIDENCE_OUTPUT.unlink(missing_ok=True)
            cleanup_detail = " | ".join(cleanup_errors)
            failure_detail = (
                f"{failure_detail}; fixture cleanup failed: {cleanup_detail}"
                if failure_detail is not None
                else f"fixture cleanup failed: {cleanup_detail}"
            )
            exit_code = 1
    if failure_detail is not None:
        print(f"WO-019 telemetry integration failed: {failure_detail}", file=sys.stderr)
    elif evidence is not None and telemetry_evidence is not None:
        print(json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2))
        print(json.dumps(telemetry_evidence, ensure_ascii=False, sort_keys=True, indent=2))
        if cas_cleanup_verified:
            print("WO-019 CAS cleanup verified.")
        print("WO-019 fixture cleanup passed.")
        print("WO-019 Telemetry/Event Bus integration passed.")
    return exit_code


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
