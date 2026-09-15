"""Produce control-center-core-v1 evidence from the real Docker HIVE stack.

The module is invoked by ``scripts/integration_health.py``, which is already
part of the CI integration path; the CI workflow itself stays untouched.  Every
claim written to ``tmp/integration-logs/control-center-core.json`` comes from an
observed assertion against the running compose stack: real Project Registry
registrations, real telemetry emitted through the production emitter inside the
API container, real SSE delivery, real durable replay/reconnect, real Redis loss
and a real API restart.

The script fails closed: PASS evidence is only written after every observation
passed, the closed field set of the merged contract is asserted immediately
before writing, and the stack is restored and the fixtures removed afterwards.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Queue
from typing import Any
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.telemetry import (  # noqa: E402
    EventEnvelope,
    TelemetryValidationError,
    sanitize_payload,
)

EVIDENCE_FILE = "control-center-core.json"
EVIDENCE_VERSION = "control-center-core-v1"
EVIDENCE_OUTPUT = ROOT / "tmp" / "integration-logs" / EVIDENCE_FILE
MIGRATION_BASE_HEAD = "0007_telemetry_events"
API_PATH = "backend/app/control_center.py"
DASHBOARD_PATH = "dashboard/src/ControlCenter.tsx"
STREAM_TRANSPORT = "sse"
FLEET_MAX_PROJECTS = 200
IMPLEMENTED_SURFACES = (
    "fleet",
    "active-runs",
    "project-detail",
    "run-detail",
    "event-stream",
    "platform-health",
    "test-status",
    "errors-warnings",
)
UNAVAILABLE_METRICS = (
    "exact_live_token_usage",
    "exact_provider_cost",
    "cache_hit_rate",
    "context_signal_ratio",
)
TRUE_FIELDS = (
    "control_center_operational_core_implemented",
    "project_fleet_visible",
    "project_state_counts_truthful",
    "selected_project_detail_available",
    "run_surface_available",
    "event_timeline_near_realtime",
    "telemetry_stream_sse_or_ws",
    "stream_replay_supported",
    "client_reconciliation_supported",
    "platform_health_visible",
    "tests_validation_state_visible",
    "errors_warnings_visible",
    "durable_sources_reused",
    "postgres_canonical",
    "redis_noncanonical",
    "project_isolation",
    "deterministic_access_control",
    "backend_api_bounded",
    "frontend_render_bounded",
    "estimated_metrics_labelled",
    "unavailable_metrics_not_fabricated",
    "restart_recovery",
    "redis_loss_recovery",
)
FALSE_FIELDS = (
    "redis_canonical_truth",
    "exact_live_token_claim_without_reconciliation",
    "fabricated_cost_metrics",
    "control_center_can_bypass_governance",
    "full_control_center_claimed",
    "full_v01_complete_claimed",
)
INTEGER_FIELDS = (
    "surface_count",
    "secret_leaks",
    "filesystem_path_leaks",
    "cross_project_leaks",
    "llm_calls",
    "provider_calls",
)
EVIDENCE_ALLOWED_FIELDS = frozenset(
    {
        "status",
        "evidence_file",
        "control_center_evidence_version",
        "observed_migration_head",
        "migration_base_head",
        "stream_transport",
        "api_path",
        "dashboard_path",
        "migration_changed",
        *TRUE_FIELDS,
        *FALSE_FIELDS,
        *INTEGER_FIELDS,
        "implemented_surfaces",
    }
)
DASHBOARD_BUNDLE_MARKERS = (
    "left this bounded live buffer",
    "NOT YET INSTRUMENTED",
    "ESTIMATED",
)
DASHBOARD_BUNDLE_API_MARKER = "/api/v1/control-center/fleet"
PROVIDER_MARKERS = (
    "semantic_retrieval",
    "reranking",
    "provider_prompt_cache",
    "openai",
    "anthropic",
    "httpx",
    "requests",
)
COST_KEY_MARKERS = ("provider_cost", "cost_usd", "exact_provider_cost", "billing")
READ_ONLY_SQL_MARKERS = ("INSERT ", "UPDATE ", "DELETE ")
CONTROL_CENTER_EVENT_LIMIT_DEFAULT = 50
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
WO020_FIXTURE_PATH = re.compile(
    r"^wo020-cc-\d+-[0-9a-f]{8}-(alpha|beta|missing-pending|missing-scope)$"
)
CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f]")


def log(message: str) -> None:
    print(f"[wo020] {message}", flush=True)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_equal(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, observed {actual!r}")


def run_command(command: list[str], *, check: bool = True, timeout: float = 180) -> str:
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        shell=False,
        timeout=timeout,
    )
    if check and result.returncode != 0:
        detail = (result.stdout + result.stderr).strip()[-2000:]
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}: {detail}")
    return result.stdout.strip()


def compose(*arguments: str, check: bool = True) -> str:
    return run_command(["docker", "compose", *arguments], check=check)


class ApiProbe:
    """Bounded HTTP probe that records every raw body for the leak scan."""

    def __init__(self, base_url: str, dashboard_url: str) -> None:
        self.base_url = base_url
        self.dashboard_url = dashboard_url
        self.bodies: list[str] = []
        self.payloads: list[object] = []

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, object] | None = None,
        expected: int | tuple[int, ...] = 200,
        timeout: float = 30,
        record: bool = True,
    ) -> object:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            headers={"Content-Type": "application/json"} if body else {},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
        text = raw.decode("utf-8", "replace")
        parsed: object
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if record:
            self.bodies.append(text)
            self.payloads.append(parsed)
        expected_codes = (expected,) if isinstance(expected, int) else expected
        if status not in expected_codes:
            raise AssertionError(
                f"{method} {path}: expected {expected_codes}, observed {status}: {text[:400]}"
            )
        return parsed


def wait_for_api_health(probe: ApiProbe, *, attempts: int = 60) -> dict[str, object]:
    last_error = "unknown"
    for _ in range(attempts):
        try:
            payload = probe.request("GET", "/api/v1/health", record=False)
            if isinstance(payload, dict) and payload.get("status") == "ok":
                return payload
            last_error = f"status payload={payload!r}"
        except (AssertionError, OSError, urllib.error.URLError, ValueError) as exc:
            last_error = repr(exc)
        time.sleep(1)
    raise AssertionError(f"API health did not become ready: {last_error}")


def current_migration_head() -> str:
    return compose(
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
    )


def projects_root() -> Path:
    raw = os.environ.get("HIVE_PROJECTS_ROOT", ".hive-projects")
    root = Path(raw)
    if not root.is_absolute():
        root = ROOT / root
    root.mkdir(parents=True, exist_ok=True)
    return root


@dataclass
class Fixture:
    label: str
    relative_path: str
    repository: Path
    project_id: UUID | None = None
    task_ids: list[UUID] = field(default_factory=list)
    task_digests: list[str] = field(default_factory=list)


def create_fixture_repository(repository: Path, label: str) -> None:
    repository.mkdir(parents=True, exist_ok=False)
    run_command(["git", "init", "-b", "main", str(repository)])
    run_command(
        ["git", "-C", str(repository), "config", "user.email", "hive-wo020@example.invalid"]
    )
    run_command(["git", "-C", str(repository), "config", "user.name", "HIVE WO-020 fixture"])
    run_command(["git", "-C", str(repository), "config", "core.autocrlf", "false"])
    (repository / "pyproject.toml").write_text(
        f"[project]\nname = '{label}'\nversion = '0.1.0'\n", encoding="utf-8"
    )
    (repository / "README.md").write_text(
        f"# {label}\n\nBounded WO-020 Control Center fixture.\n", encoding="utf-8"
    )
    source = repository / "src"
    source.mkdir()
    (source / "service.py").write_text(
        "def fixture() -> str:\n    return 'wo020'\n", encoding="utf-8"
    )
    governance = repository / "docs" / "project-brain"
    governance.mkdir(parents=True)
    for relative, content in (
        (
            "13-CHECKPOINT.md",
            "# Fixture checkpoint\n\n"
            "## STATUS\nFIXTURE CONTROL CENTER ACTIVE\n\n"
            "## IN PROGRESS\n- Verify bounded project intelligence\n\n"
            "## PENDING\n- Fixture follow-up\n- Fixture audit\n\n"
            "## NEXT STEP\nPublish the next bounded fixture result.\n",
        ),
        (
            "03-SCOPE.md",
            "# Fixture scope\n\n"
            "## NECESSARY — V0.1\n- Full HIVE Control Center.\n- Bounded fixture scope.\n",
        ),
        (
            "15-DEFINITION-OF-DONE.md",
            "# Fixture Definition of Done\n\n"
            "## Functional\n- [x] Fixture validation\n- [ ] Fixture follow-up\n",
        ),
        (
            "16-DECISIONS-LEDGER.md",
            "# Fixture decisions\n\n"
            "## HIVE-ADR-001 — Fixture canonical decision\n"
            "**Status:** Accepted\n",
        ),
    ):
        (governance / relative).write_text(content, encoding="utf-8")
    run_command(["git", "-C", str(repository), "add", "-A"])
    run_command(["git", "-C", str(repository), "commit", "-m", "initial WO-020 fixture"])


def register_fixture(probe: ApiProbe, fixture: Fixture) -> dict[str, object]:
    payload = probe.request(
        "POST",
        "/api/v1/projects",
        payload={"name": fixture.label, "relative_path": fixture.relative_path},
        expected=201,
    )
    require(isinstance(payload, dict), "registration response is not an object")
    registered = dict(payload)
    fixture.project_id = UUID(str(registered["project_id"]))
    expect_equal(registered["relative_path"], fixture.relative_path, "registered relative path")
    expect_equal(registered["state"], "READY", "registered state")
    expect_equal(registered["repository_accessible"], True, "registered accessibility")
    return registered


def create_task(probe: ApiProbe, fixture: Fixture, title: str) -> UUID:
    require(fixture.project_id is not None, "fixture project is not registered")
    payload = probe.request(
        "POST",
        f"/api/v1/projects/{fixture.project_id}/tasks/text",
        payload={"title": title, "text": f"# {title}\n\nbounded WO-020 fixture text\n"},
        expected=201,
    )
    require(isinstance(payload, dict), "task response is not an object")
    task = dict(payload)
    task_id = UUID(str(task["task_id"]))
    fixture.task_ids.append(task_id)
    fixture.task_digests.append(str(task["original_blob_sha256"]))
    return task_id


def event_spec(
    *,
    event_type: str,
    run_id: UUID,
    emission_key: str,
    payload: dict[str, object],
    task_id: UUID | None = None,
) -> dict[str, object]:
    return {
        "event_type": event_type,
        "payload": payload,
        "provenance": {"producer": "control_center_integration", "deterministic": True},
        "emission_key": emission_key,
        "run_id": str(run_id),
        "task_id": str(task_id) if task_id is not None else None,
    }


def emit_event_batch(project_id: UUID, specs: list[dict[str, object]]) -> list[EventEnvelope]:
    code = "\n".join(
        [
            "import json",
            "from uuid import UUID",
            "from app.config import Settings",
            "from app.telemetry import emit_event",
            f"project = UUID('{project_id}')",
            f"specs = {specs!r}",
            "for spec in specs:",
            "    event = emit_event(",
            "        Settings(),",
            "        project,",
            "        spec['event_type'],",
            "        spec['payload'],",
            "        task_id=UUID(spec['task_id']) if spec.get('task_id') else None,",
            "        run_id=UUID(spec['run_id']) if spec.get('run_id') else None,",
            "        provenance=spec['provenance'],",
            "        emission_key=spec['emission_key'],",
            "    )",
            "    print(json.dumps(event.model_dump(mode='json'), sort_keys=True))",
        ]
    )
    output = compose("exec", "-T", "api", "python", "-c", code)
    envelopes = [
        EventEnvelope.model_validate(json.loads(line))
        for line in output.splitlines()
        if line.strip()
    ]
    expect_equal(len(envelopes), len(specs), "emitted event count")
    return envelopes


def sse_events(text: str) -> list[dict[str, object]]:
    frames: list[dict[str, object]] = []
    for block in text.split("\n\n"):
        data = [line[len("data: ") :] for line in block.splitlines() if line.startswith("data: ")]
        if not data:
            continue
        parsed = json.loads("\n".join(data))
        require(isinstance(parsed, dict), "SSE frame is not an object")
        frames.append(parsed)
    return frames


def stream_path(project_id: UUID, *, after: str, max_events: int, timeout_seconds: float) -> str:
    return (
        f"/api/v1/projects/{project_id}/events/stream?after={after}"
        f"&max_events={max_events}&timeout_seconds={timeout_seconds}"
    )


def read_stream(
    probe: ApiProbe,
    project_id: UUID,
    *,
    after: str,
    max_events: int,
    timeout_seconds: float = 5.0,
) -> tuple[str, list[dict[str, object]]]:
    path = stream_path(
        project_id, after=after, max_events=max_events, timeout_seconds=timeout_seconds
    )
    request = urllib.request.Request(
        probe.base_url + path, method="GET", headers={"Accept": "text/event-stream"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds + 15) as response:
            content_type = response.headers.get("Content-Type", "")
            raw = response.read(2_000_000).decode("utf-8", "replace")
    except (OSError, urllib.error.URLError, UnicodeDecodeError) as exc:
        raise AssertionError(f"SSE stream failed: {exc!r}") from exc
    probe.bodies.append(raw)
    return content_type, sse_events(raw)


def open_live_stream(
    probe: ApiProbe,
    project_id: UUID,
    *,
    after: str,
    timeout_seconds: float = 10.0,
) -> tuple[threading.Thread, Queue[object]]:
    ready = threading.Event()
    result: Queue[object] = Queue(maxsize=1)
    path = stream_path(project_id, after=after, max_events=1, timeout_seconds=timeout_seconds)

    def receive() -> None:
        try:
            request = urllib.request.Request(
                probe.base_url + path, method="GET", headers={"Accept": "text/event-stream"}
            )
            with urllib.request.urlopen(request, timeout=timeout_seconds + 15) as response:
                ready.set()
                payload = response.read(2_000_000).decode("utf-8", "replace")
            probe.bodies.append(payload)
            result.put((response.status, payload))
        except Exception as exc:  # noqa: BLE001 - the probe reports the failure to its caller
            ready.set()
            result.put(exc)

    thread = threading.Thread(target=receive, daemon=True, name="wo020-live-sse")
    thread.start()
    require(ready.wait(timeout=10), "live SSE connection did not open within the bound")
    return thread, result


def read_live_stream(result: Queue[object], *, timeout_seconds: float) -> list[dict[str, object]]:
    try:
        value = result.get(timeout=timeout_seconds)
    except Empty as exc:
        raise AssertionError("live SSE stream did not deliver an event in time") from exc
    if isinstance(value, Exception):
        raise AssertionError(f"live SSE stream failed: {value!r}") from value
    require(
        isinstance(value, tuple) and len(value) == 2 and isinstance(value[1], str),
        "live SSE stream returned an invalid payload",
    )
    status, payload = value
    expect_equal(status, 200, "live SSE status")
    return sse_events(payload)


def pages_events(
    probe: ApiProbe, project_id: UUID, *, after: str | None = None, limit: int = 100
) -> dict[str, object]:
    query = f"?limit={limit}" + (f"&after={after}" if after else "")
    payload = probe.request("GET", f"/api/v1/projects/{project_id}/events{query}")
    require(isinstance(payload, dict), "event page is not an object")
    events = payload.get("events")
    require(isinstance(events, list), "event page events are not a list")
    return dict(payload)


def event_ids(events: list[Any]) -> list[str]:
    return [str(dict(event)["event_id"]) for event in events]


def control_center_detail(probe: ApiProbe, project_id: UUID, query: str = "") -> dict[str, object]:
    payload = probe.request("GET", f"/api/v1/control-center/projects/{project_id}{query}")
    require(isinstance(payload, dict), "project detail is not an object")
    return dict(payload)


def scan_control_center_keys(payload: object, *, marker: str) -> int:
    hits = 0
    if isinstance(payload, dict):
        for key, value in payload.items():
            if marker in key and isinstance(value, int | float) and not isinstance(value, bool):
                hits += 1
            hits += scan_control_center_keys(value, marker=marker)
    elif isinstance(payload, list):
        for item in payload:
            hits += scan_control_center_keys(item, marker=marker)
    return hits


def forbidden_fragments(text: str) -> int:
    """Count fragments the production sanitizer refuses on event values.

    SSE transport framing carries literal newlines and the sanitizer refuses every
    string with control characters, so framing is normalised to spaces first.
    Event values are JSON strings and never carry raw newlines, so the
    normalisation cannot hide a leaked secret or filesystem path.
    """

    normalized = CONTROL_CHARACTERS.sub(" ", text)
    if len(normalized) < 2:
        return 0
    window = 1024
    step = 256
    fragments = 0
    for start in range(0, len(normalized), step):
        candidate = normalized[start : start + window]
        if not candidate.strip():
            continue
        try:
            sanitize_payload({"value": candidate})
        except TelemetryValidationError:
            fragments += 1
        if start + window >= len(normalized):
            break
    return fragments


def cross_project_hits(text: str, foreign_tokens: tuple[str, ...]) -> int:
    return sum(1 for token in foreign_tokens if token and token in text)


def fetch_dashboard_bundle(url: str) -> tuple[str, list[str]]:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            html = response.read(2_000_000).decode("utf-8", "replace")
    except (OSError, urllib.error.URLError, UnicodeDecodeError) as exc:
        raise AssertionError(f"dashboard root failed: {exc!r}") from exc
    assets: list[str] = []
    bundle = html
    for token in html.split('src="')[1:]:
        asset = token.split('"', 1)[0]
        if not asset.endswith(".js"):
            continue
        assets.append(asset)
        try:
            with urllib.request.urlopen(url.rstrip("/") + asset, timeout=20) as response:
                bundle += response.read(5_000_000).decode("utf-8", "replace")
        except (OSError, urllib.error.URLError, UnicodeDecodeError) as exc:
            raise AssertionError(f"dashboard asset {asset} failed: {exc!r}") from exc
    return bundle, assets


def source_scan() -> dict[str, object]:
    source = (ROOT / API_PATH).read_text(encoding="utf-8")
    import_lines = [
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    provider_imports = [
        line for line in import_lines if any(marker in line for marker in PROVIDER_MARKERS)
    ]
    upper = source.upper()
    write_statements = [marker for marker in READ_ONLY_SQL_MARKERS if marker in upper]
    return {
        "durable_imports": all(
            marker in source
            for marker in ("from .registry import", "from .telemetry import", "from .health import")
        ),
        "provider_imports": provider_imports,
        "write_statements": write_statements,
    }


def register_wo020_fixtures(probe: ApiProbe, fixtures: list[Fixture]) -> list[dict[str, object]]:
    """Create two isolated real Git fixtures and register them through the API."""

    root = projects_root()
    suffix = f"{os.getpid()}-{uuid4().hex[:8]}"
    for label in ("alpha", "beta"):
        name = f"wo020-cc-{suffix}-{label}"
        fixtures.append(Fixture(label=name, relative_path=name, repository=root / name))
    for fixture in fixtures:
        create_fixture_repository(fixture.repository, fixture.label)
    log(f"created {len(fixtures)} isolated fixture repositories")
    registrations: list[dict[str, object]] = []
    for fixture in fixtures:
        registration = register_fixture(probe, fixture)
        expect_equal(registration["name"], fixture.label, "registered fixture name")
        require(fixture.project_id is not None, "fixture registration returned no project id")
        create_task(probe, fixture, f"WO-020 {fixture.label} fixture task")
        registrations.append(registration)
    log("registered fixture projects and their intake tasks")
    return registrations


@dataclass(frozen=True)
class TelemetryRuns:
    """Typed handles to the telemetry emitted for the two fixture projects."""

    completed_run: UUID
    active_run: UUID
    failed_run: UUID
    alpha_task: UUID
    beta_task: UUID
    completed_events: list[EventEnvelope]
    active_events: list[EventEnvelope]
    failed_events: list[EventEnvelope]


def emit_wo020_telemetry(fixtures: list[Fixture]) -> TelemetryRuns:
    """Emit bounded canonical telemetry through the production emitter in the container."""

    alpha, beta = fixtures
    require(
        alpha.project_id is not None and beta.project_id is not None,
        "fixtures must be registered before telemetry emission",
    )
    alpha_task = alpha.task_ids[0]
    beta_task = beta.task_ids[0]
    completed_run = uuid4()
    active_run = uuid4()
    failed_run = uuid4()
    completed = emit_event_batch(
        alpha.project_id,
        [
            event_spec(
                event_type="context.started",
                run_id=completed_run,
                emission_key=f"{alpha.label}-completed-context",
                payload={"stage": "context", "attempt": 1},
                task_id=alpha_task,
            ),
            event_spec(
                event_type="executor.started",
                run_id=completed_run,
                emission_key=f"{alpha.label}-completed-executor",
                payload={"adapter": "control-center-fixture", "deterministic": True},
                task_id=alpha_task,
            ),
            event_spec(
                event_type="test.started",
                run_id=completed_run,
                emission_key=f"{alpha.label}-completed-test-started",
                payload={"suite": "unit", "deterministic": True},
                task_id=alpha_task,
            ),
            event_spec(
                event_type="test.finished",
                run_id=completed_run,
                emission_key=f"{alpha.label}-completed-test-finished",
                payload={"suite": "unit", "passed": True},
                task_id=alpha_task,
            ),
            event_spec(
                event_type="validation.passed",
                run_id=completed_run,
                emission_key=f"{alpha.label}-completed-validation",
                payload={"gate": "unit", "passed": True},
                task_id=alpha_task,
            ),
            event_spec(
                event_type="run.completed",
                run_id=completed_run,
                emission_key=f"{alpha.label}-completed-run",
                payload={"status": "COMPLETED", "exit_code": 0},
                task_id=alpha_task,
            ),
        ],
    )
    active = emit_event_batch(
        alpha.project_id,
        [
            event_spec(
                event_type="context.started",
                run_id=active_run,
                emission_key=f"{alpha.label}-active-context",
                payload={"stage": "context", "attempt": 1},
                task_id=alpha_task,
            ),
            event_spec(
                event_type="executor.started",
                run_id=active_run,
                emission_key=f"{alpha.label}-active-executor",
                payload={"adapter": "control-center-fixture", "deterministic": True},
                task_id=alpha_task,
            ),
            event_spec(
                event_type="tool.called",
                run_id=active_run,
                emission_key=f"{alpha.label}-active-tool",
                payload={"tool": "fixture-tool", "duration_ms": 12},
                task_id=alpha_task,
            ),
            event_spec(
                event_type="cache.miss",
                run_id=active_run,
                emission_key=f"{alpha.label}-active-cache",
                payload={"token_count": 12, "estimated": True},
                task_id=alpha_task,
            ),
        ],
    )
    failed = emit_event_batch(
        beta.project_id,
        [
            event_spec(
                event_type="validation.failed",
                run_id=failed_run,
                emission_key=f"{beta.label}-failed-validation",
                payload={"gate": "unit", "passed": False},
                task_id=beta_task,
            ),
            event_spec(
                event_type="run.failed",
                run_id=failed_run,
                emission_key=f"{beta.label}-failed-run",
                payload={
                    "status": "FAILED",
                    "error_type": "fixture_error",
                    "message": "bounded WO-020 fixture failure",
                },
                task_id=beta_task,
            ),
        ],
    )
    return TelemetryRuns(
        completed_run=completed_run,
        active_run=active_run,
        failed_run=failed_run,
        alpha_task=alpha_task,
        beta_task=beta_task,
        completed_events=completed,
        active_events=active,
        failed_events=failed,
    )


def verify_fleet_surface(
    probe: ApiProbe, fixtures: list[Fixture], registrations: list[dict[str, object]]
) -> dict[str, object]:
    """Prove the bounded fleet pagination against the durable registry on the same stack."""

    payload = probe.request("GET", "/api/v1/control-center/fleet")
    require(isinstance(payload, dict), "fleet response is not an object")
    fleet = dict(payload)
    expect_equal(fleet["max_projects"], FLEET_MAX_PROJECTS, "fleet max_projects")
    expect_equal(fleet["offset"], 0, "fleet default offset")
    expect_equal(fleet["limit"], FLEET_MAX_PROJECTS, "fleet default limit")
    projects = fleet["projects"]
    require(isinstance(projects, list), "fleet projects are not a list")
    listing = probe.request("GET", "/api/v1/projects")
    require(
        isinstance(listing, list) and len(listing) >= len(fixtures),
        "registry listing cannot bound the fleet comparison",
    )
    bounded = listing[:FLEET_MAX_PROJECTS]
    expect_equal(fleet["project_count"], len(listing), "fleet global project_count")
    expect_equal(fleet["truncated"], len(bounded) < len(listing), "fleet truncated")
    expect_equal(fleet["has_more"], len(listing) > FLEET_MAX_PROJECTS, "fleet has_more")
    expect_equal(
        fleet["next_offset"],
        FLEET_MAX_PROJECTS if len(listing) > FLEET_MAX_PROJECTS else None,
        "fleet next_offset",
    )
    expect_equal(
        [str(project["project_id"]) for project in projects],
        [str(project["project_id"]) for project in bounded],
        "fleet ordering against the durable registry",
    )
    counts = {
        state: 0
        for state in ("offline", "stale", "indexing", "ready", "active", "degraded", "blocked")
    }
    for project in listing:
        counts[str(project["state"]).lower()] += 1
    expect_equal(dict(fleet["state_counts"]), counts, "fleet global state counts")
    headlines = {str(project["project_id"]): project for project in projects}
    for fixture, registration in zip(fixtures, registrations, strict=True):
        headline = headlines.get(str(fixture.project_id))
        require(isinstance(headline, dict), f"fleet is missing {fixture.relative_path}")
        for field_name in (
            "name",
            "relative_path",
            "state",
            "repository_accessible",
            "git_branch",
            "git_head_sha",
            "detached_head",
            "working_tree_clean",
            "language_stack",
        ):
            expect_equal(
                headline[field_name],
                registration[field_name],
                f"fleet {field_name} for {fixture.relative_path}",
            )
    if len(listing) >= 2:
        first_page = probe.request("GET", "/api/v1/control-center/fleet?offset=0&limit=1")
        require(isinstance(first_page, dict), "fleet size-one page is not an object")
        expect_equal(first_page["offset"], 0, "fleet size-one offset")
        expect_equal(first_page["limit"], 1, "fleet size-one limit")
        expect_equal(first_page["project_count"], len(listing), "fleet size-one global count")
        expect_equal(len(first_page["projects"]), 1, "fleet size-one page bound")
        expect_equal(
            str(first_page["projects"][0]["project_id"]),
            str(listing[0]["project_id"]),
            "fleet size-one first identity",
        )
        expect_equal(first_page["has_more"], True, "fleet size-one has_more")
        expect_equal(first_page["next_offset"], 1, "fleet size-one next_offset")
        expect_equal(dict(first_page["state_counts"]), counts, "fleet size-one global state counts")
        second_page = probe.request("GET", "/api/v1/control-center/fleet?offset=1&limit=1")
        require(isinstance(second_page, dict), "fleet second page is not an object")
        expect_equal(second_page["offset"], 1, "fleet second page offset")
        expect_equal(len(second_page["projects"]), 1, "fleet second page bound")
        expect_equal(
            str(second_page["projects"][0]["project_id"]),
            str(listing[1]["project_id"]),
            "fleet second page reaches the next registry project",
        )
        first_ids = {str(project["project_id"]) for project in first_page["projects"]}
        second_ids = {str(project["project_id"]) for project in second_page["projects"]}
        require(not (first_ids & second_ids), "fleet pages must not overlap")
        expect_equal(
            dict(second_page["state_counts"]), counts, "fleet second page global state counts"
        )
    return {"project_count": fleet["project_count"], "truncated": fleet["truncated"]}


def verify_alpha_project_surfaces(
    probe: ApiProbe, project_id: UUID, telemetry: TelemetryRuns
) -> dict[str, object]:
    """Prove the project detail, run, test and error surfaces for the alpha fixture."""

    completed_run = str(telemetry.completed_run)
    active_run = str(telemetry.active_run)
    completed_ids = [str(event.event_id) for event in telemetry.completed_events]
    active_ids = [str(event.event_id) for event in telemetry.active_events]
    detail = control_center_detail(probe, project_id)
    headline = detail["project"]
    require(isinstance(headline, dict), "detail headline is not an object")
    expect_equal(str(headline["project_id"]), str(project_id), "detail project identity")
    expect_equal(headline["state"], "READY", "detail project state")
    expect_equal(detail["active_run_count"], 1, "detail active run count")
    expect_equal(detail["recent_runs_truncated"], False, "detail runs truncated")
    expect_equal(detail["window"]["max_events"], 50, "detail default event window")
    expect_equal(detail["window"]["truncated"], False, "detail event window truncated")
    runs = {str(run["run_id"]): run for run in detail["recent_runs"]}
    expect_equal(set(runs), {completed_run, active_run}, "detail run identities")
    expect_equal(runs[completed_run]["status"], "COMPLETED", "detail completed run status")
    expect_equal(runs[active_run]["status"], "ACTIVE", "detail active run status")
    expect_equal(
        event_ids(detail["recent_events"]),
        completed_ids + active_ids,
        "detail recent events",
    )

    runs_payload = probe.request("GET", f"/api/v1/control-center/projects/{project_id}/runs")
    require(isinstance(runs_payload, dict), "runs response is not an object")
    expect_equal(runs_payload["window"]["max_events"], 20, "runs default limit")
    expect_equal(runs_payload["truncated"], False, "runs truncated")
    expect_equal(
        [str(item["run_id"]) for item in runs_payload["active"]], [active_run], "runs active"
    )
    expect_equal(
        [str(item["run_id"]) for item in runs_payload["recent"]],
        [completed_run],
        "runs recent",
    )

    run_detail = probe.request(
        "GET", f"/api/v1/control-center/projects/{project_id}/runs/{completed_run}"
    )
    require(isinstance(run_detail, dict), "run detail is not an object")
    expect_equal(run_detail["run"]["status"], "COMPLETED", "run detail status")
    expect_equal(str(run_detail["task_id"]), str(telemetry.alpha_task), "run detail task identity")
    expect_equal(
        run_detail["executor_identity"], "control-center-fixture", "run detail executor identity"
    )
    expect_equal(run_detail["max_timeline_events"], 100, "run detail default timeline bound")
    expect_equal(run_detail["timeline_truncated"], False, "run detail timeline truncated")
    expect_equal(event_ids(run_detail["timeline"]), completed_ids, "run detail timeline")

    tests = probe.request("GET", f"/api/v1/control-center/projects/{project_id}/tests")
    require(isinstance(tests, dict), "tests response is not an object")
    test_runs = {str(run["run_id"]): run for run in tests["runs"]}
    expect_equal(set(test_runs), {completed_run}, "test status run identities")
    completed_tests = test_runs[completed_run]
    expect_equal(completed_tests["status"], "PASSED", "test status value")
    expect_equal(completed_tests["test_started"], 1, "test.started count")
    expect_equal(completed_tests["test_finished"], 1, "test.finished count")
    expect_equal(completed_tests["validation_passed"], 1, "validation.passed count")
    expect_equal(completed_tests["validation_failed"], 0, "validation.failed count")
    expect_equal(tests["runs_without_test_telemetry_in_window"], 1, "runs without test telemetry")

    errors = probe.request("GET", f"/api/v1/control-center/projects/{project_id}/errors")
    require(isinstance(errors, dict), "errors response is not an object")
    expect_equal(errors["errors"], [], "alpha has no error events")
    expect_equal(errors["warnings"], [], "alpha has no warnings while the platform is healthy")
    expect_equal(errors["truncated"], False, "alpha errors are not truncated")
    return {
        "detail": detail,
        "runs": runs_payload,
        "run_detail": run_detail,
        "tests": tests,
        "errors": errors,
    }


def verify_beta_surfaces(
    probe: ApiProbe, project_id: UUID, telemetry: TelemetryRuns
) -> dict[str, object]:
    """Prove the failure surfaces are project-scoped and truthful for beta."""

    failed_run = str(telemetry.failed_run)
    tests = probe.request("GET", f"/api/v1/control-center/projects/{project_id}/tests")
    require(isinstance(tests, dict), "beta tests response is not an object")
    test_runs = {str(run["run_id"]): run for run in tests["runs"]}
    expect_equal(set(test_runs), {failed_run}, "beta test run identities")
    expect_equal(test_runs[failed_run]["status"], "FAILED", "beta test status")
    expect_equal(test_runs[failed_run]["validation_failed"], 1, "beta validation.failed count")
    expect_equal(test_runs[failed_run]["validation_passed"], 0, "beta validation.passed count")
    errors = probe.request("GET", f"/api/v1/control-center/projects/{project_id}/errors")
    require(isinstance(errors, dict), "beta errors response is not an object")
    expect_equal(
        [item["kind"] for item in errors["errors"]],
        ["run.failed", "validation.failed"],
        "beta error kinds",
    )
    expect_equal(
        [str(item["run_id"]) for item in errors["errors"]],
        [failed_run, failed_run],
        "beta error run identity",
    )
    expect_equal(
        [item["severity"] for item in errors["errors"]], ["ERROR", "ERROR"], "beta error severity"
    )
    expect_equal(errors["warnings"], [], "beta has no warnings while the platform is healthy")
    return {"tests": tests, "errors": errors}


def verify_event_streams(
    probe: ApiProbe, project_id: UUID, expected_ids: list[str]
) -> dict[str, object]:
    """Prove durable replay, SSE delivery and reconnect continuity without gaps."""

    page = pages_events(probe, project_id, limit=100)
    expect_equal(page["has_more"], False, "durable page has_more")
    expect_equal(event_ids(page["events"]), expected_ids, "durable replay order")
    cursors = [str(event["cursor"]) for event in page["events"]]
    require(len(cursors) >= 9, "durable replay window is too small for the stream checks")
    for event in page["events"]:
        expect_equal(str(event["project_id"]), str(project_id), "replayed event project scope")
    tail = pages_events(probe, project_id, after=cursors[1], limit=100)
    expect_equal(event_ids(tail["events"]), expected_ids[2:], "durable replay after cursor")

    content_type, frames = read_stream(
        probe, project_id, after=cursors[1], max_events=3, timeout_seconds=5.0
    )
    require("text/event-stream" in content_type, f"unexpected stream content type {content_type!r}")
    expect_equal(event_ids(frames), expected_ids[2:5], "SSE replay window")

    first_head, first_frames = read_stream(
        probe, project_id, after=cursors[4], max_events=2, timeout_seconds=5.0
    )
    second_head, second_frames = read_stream(
        probe, project_id, after=cursors[6], max_events=2, timeout_seconds=5.0
    )
    require(
        "text/event-stream" in first_head and "text/event-stream" in second_head,
        "stream content type drifted across the reconnect",
    )
    reconnected = event_ids(first_frames) + event_ids(second_frames)
    expect_equal(reconnected, expected_ids[5:9], "SSE reconnect concatenation")
    require(len(reconnected) == len(set(reconnected)), "SSE reconnect duplicated an event")
    return {"cursors": cursors, "reconnected": reconnected}


def verify_live_stream(
    probe: ApiProbe, project_id: UUID, telemetry: TelemetryRuns, label: str
) -> str:
    """Open the stream before the emission and require near-real-time delivery."""

    page = pages_events(probe, project_id, limit=100)
    events = page["events"]
    require(isinstance(events, list) and bool(events), "durable replay window is empty")
    after = str(dict(events[-1])["cursor"])
    thread, result = open_live_stream(probe, project_id, after=after, timeout_seconds=10.0)
    started = time.monotonic()
    envelopes = emit_event_batch(
        project_id,
        [
            event_spec(
                event_type="file.changed",
                run_id=telemetry.active_run,
                emission_key=f"{label}-live-change-{int(started)}",
                payload={"change": "modified", "file": "src/service.py"},
                task_id=telemetry.alpha_task,
            )
        ],
    )
    frames = read_live_stream(result, timeout_seconds=15.0)
    elapsed = time.monotonic() - started
    thread.join(timeout=5)
    expect_equal(len(frames), 1, "live stream frame count")
    expect_equal(str(frames[0]["event_id"]), str(envelopes[0].event_id), "live stream identity")
    expect_equal(frames[0]["event_type"], "file.changed", "live stream event type")
    require(elapsed <= 15.0, f"live stream delivery took {elapsed:.1f}s")
    log(f"live SSE delivered {frames[0]['event_type']} in {elapsed:.2f}s")
    return str(envelopes[0].event_id)


def verify_health_surface(probe: ApiProbe, observed_head: str) -> dict[str, object]:
    """Prove the bounded platform-health surface against the live collectors."""

    health = probe.request("GET", "/api/v1/control-center/health")
    require(isinstance(health, dict), "health response is not an object")
    expect_equal(health["status"], "ok", "control center health status")
    expect_equal(health["migration_head"], observed_head, "health migration head")
    expect_equal(health["canonical_store"], "postgres", "canonical store")
    expect_equal(health["hot_store"], "redis", "hot store")
    expect_equal(health["hot_store_canonical"], False, "hot store canonical claim")
    checks = health["checks"]
    require(isinstance(checks, dict), "health checks are not an object")
    expect_equal(checks["postgres"]["details"]["pgvector"], True, "pgvector availability")
    expect_equal(checks["redis"]["details"], {"canonical": False}, "redis check details")
    expect_equal(
        checks["storage"]["details"],
        {"configured": True, "writable": True},
        "storage check details",
    )
    expect_equal(health["unavailable_metrics"], list(UNAVAILABLE_METRICS), "unavailable metrics")
    return dict(health)


def verify_bounded_access(probe: ApiProbe, project_id: UUID) -> None:
    """Prove every read surface is bounded and access control is deterministic."""

    for query in ("runs=51", "runs=0", "events=101", "warnings=51", "warnings=0"):
        probe.request("GET", f"/api/v1/control-center/projects/{project_id}?{query}", expected=422)
    probe.request(
        "GET", f"/api/v1/control-center/projects/{project_id}/runs?limit=51", expected=422
    )
    probe.request(
        "GET", f"/api/v1/control-center/projects/{project_id}/tests?events=101", expected=422
    )
    probe.request(
        "GET", f"/api/v1/control-center/projects/{project_id}/errors?limit=51", expected=422
    )
    probe.request("GET", "/api/v1/control-center/projects/not-a-project", expected=422)
    probe.request("GET", f"/api/v1/control-center/projects/{uuid4()}", expected=404)
    probe.request("GET", f"/api/v1/control-center/projects/{uuid4()}/runs", expected=404)
    probe.request(
        "GET", f"/api/v1/control-center/projects/{project_id}/runs/{uuid4()}", expected=404
    )
    probe.request("POST", "/api/v1/control-center/fleet", expected=405)
    observed_events = len(pages_events(probe, project_id, limit=100)["events"])
    bounded = control_center_detail(probe, project_id, "?runs=1")
    expect_equal(len(bounded["recent_runs"]), 1, "bounded runs window")
    expect_equal(bounded["recent_runs_truncated"], True, "bounded runs truncation flag")
    expect_equal(
        bounded["window"]["scanned_events"],
        min(observed_events, CONTROL_CENTER_EVENT_LIMIT_DEFAULT),
        "bounded window scanned events",
    )
    log("bounded access control rejected unbounded and cross-scope reads")


def verify_isolation(bodies: list[object], foreign_tokens: tuple[str, ...]) -> int:
    """Count foreign project identity leaks across project-scoped response bodies."""

    require(bool(foreign_tokens), "isolation scan needs foreign tokens")
    text = "\n".join(json.dumps(body, sort_keys=True) for body in bodies)
    return cross_project_hits(text, foreign_tokens)


def verify_dashboard_bundle(probe: ApiProbe) -> list[str]:
    """Prove the served dashboard bundle carries the bounded rendering markers."""

    bundle, assets = fetch_dashboard_bundle(f"{probe.dashboard_url.rstrip('/')}/")
    require(bool(assets), "dashboard bundle exposes no script asset")
    markers = (*DASHBOARD_BUNDLE_MARKERS, DASHBOARD_BUNDLE_API_MARKER)
    missing = [marker for marker in markers if marker not in bundle]
    require(not missing, f"dashboard bundle is missing markers {missing}")
    log(f"dashboard bundle asserts {len(markers)} bounded rendering markers")
    return assets


def verify_restart_recovery(probe: ApiProbe, project_id: UUID) -> None:
    """Restart the API container and prove the durable timeline is unchanged."""

    before = event_ids(pages_events(probe, project_id, limit=100)["events"])

    def statuses_of(payload: dict[str, object]) -> list[tuple[str, str]]:
        runs = payload["recent_runs"]
        require(isinstance(runs, list), "recent runs are not a list")
        return sorted((str(dict(run)["run_id"]), str(dict(run)["status"])) for run in runs)

    before_statuses = statuses_of(control_center_detail(probe, project_id))
    compose("restart", "api")
    wait_for_api_health(probe, attempts=90)
    after = event_ids(pages_events(probe, project_id, limit=100)["events"])
    expect_equal(after, before, "restart recovery of the durable timeline")
    expect_equal(
        statuses_of(control_center_detail(probe, project_id)),
        before_statuses,
        "restart recovery of the run surface",
    )
    log("API restart preserved the durable timeline and the run surface")


def verify_redis_loss_recovery(probe: ApiProbe, fixture: Fixture, telemetry: TelemetryRuns) -> None:
    """Stop Redis, prove the durable sources stay canonical, then restore it."""

    require(fixture.project_id is not None, "fixture is not registered")
    project_id = fixture.project_id
    before = event_ids(pages_events(probe, project_id, limit=100)["events"])
    fleet_before = probe.request("GET", "/api/v1/control-center/fleet")
    require(isinstance(fleet_before, dict), "fleet response is not an object")
    compose("stop", "redis")
    try:
        health = probe.request("GET", "/api/v1/control-center/health", expected=(200, 503))
        require(isinstance(health, dict), "degraded health response is not an object")
        expect_equal(health["status"], "degraded", "health status without Redis")
        expect_equal(health["checks"]["redis"]["status"], "degraded", "redis check status")
        expect_equal(health["hot_store_canonical"], False, "redis canonical claim without Redis")
        expect_equal(health["canonical_store"], "postgres", "canonical store without Redis")
        fleet_during = probe.request("GET", "/api/v1/control-center/fleet")
        require(isinstance(fleet_during, dict), "fleet response without Redis is not an object")
        expect_equal(
            fleet_during["project_count"], fleet_before["project_count"], "fleet without Redis"
        )
        expect_equal(
            [str(project["project_id"]) for project in fleet_during["projects"]],
            [str(project["project_id"]) for project in fleet_before["projects"]],
            "fleet ordering without Redis",
        )
        durable = pages_events(probe, project_id, limit=100)
        expect_equal(event_ids(durable["events"]), before, "durable replay without Redis")
        live_id = verify_live_stream(probe, project_id, telemetry, f"{fixture.label}-redis-out")
        require(live_id not in before, "live emission during Redis loss was not a new event")
        degraded = probe.request(
            "GET", f"/api/v1/control-center/projects/{project_id}/errors?limit=50"
        )
        require(isinstance(degraded, dict), "errors response without Redis is not an object")
        expect_equal(
            [item["kind"] for item in degraded["warnings"]],
            ["health.redis"],
            "degraded health warning",
        )
        expect_equal(
            [item["severity"] for item in degraded["warnings"]],
            ["WARNING"],
            "degraded health warning severity",
        )
    finally:
        compose("start", "redis")
    restored = probe.request("GET", "/api/v1/control-center/health")
    require(isinstance(restored, dict), "restored health response is not an object")
    expect_equal(restored["status"], "ok", "health status after Redis restart")
    expect_equal(restored["checks"]["redis"]["status"], "ok", "redis check after restart")
    after = event_ids(pages_events(probe, project_id, limit=100)["events"])
    expect_equal(after, before + [live_id], "durable timeline after Redis restart")
    log("Redis loss recovered without losing canonical telemetry")


def verify_evidence_hygiene(probe: ApiProbe, cross_project_leaks: int) -> dict[str, object]:
    """Scan every recorded body, the API source and the running container flags."""

    forbidden = sum(forbidden_fragments(body) for body in probe.bodies)
    path_tokens = ("/var/lib/hive", ".hive-data", ".hive-projects", str(ROOT))
    leaked_paths = sum(1 for body in probe.bodies for token in path_tokens if token in body)
    cost_hits = sum(
        scan_control_center_keys(body, marker=marker)
        for body in probe.payloads
        for marker in COST_KEY_MARKERS
    )
    scan = source_scan()
    expect_equal(forbidden, 0, "sanitizer-refused fragments in recorded bodies")
    expect_equal(leaked_paths, 0, "host or container paths in recorded bodies")
    expect_equal(cost_hits, 0, "fabricated cost metrics in recorded bodies")
    expect_equal(scan["provider_imports"], [], "provider imports in the control center module")
    expect_equal(scan["write_statements"], [], "write statements in the control center module")
    expect_equal(scan["durable_imports"], True, "control center reuses the durable sources")
    flags = compose(
        "exec",
        "-T",
        "api",
        "python",
        "-c",
        "from app.config import Settings; s = Settings(); "
        "print(f'{s.embedding_enabled} {s.rerank_enabled}')",
    )
    expect_equal(flags, "False False", "provider-backed retrieval flags")
    provider_imports = scan["provider_imports"]
    require(isinstance(provider_imports, list), "provider import scan is not a list")
    provider_paths = len(provider_imports) + (0 if flags == "False False" else 1)
    return {
        "secret_leaks": forbidden,
        "filesystem_path_leaks": leaked_paths,
        "cross_project_leaks": cross_project_leaks,
        "llm_calls": provider_paths,
        "provider_calls": provider_paths,
        "durable_imports": bool(scan["durable_imports"]),
        "scanned_bodies": len(probe.bodies),
    }


def collect_evidence(probe: ApiProbe, fixtures: list[Fixture]) -> dict[str, object]:
    """Observe every WO-020 claim against the live compose stack."""

    observed: dict[str, bool] = {}
    surfaces: dict[str, bool] = {name: False for name in IMPLEMENTED_SURFACES}

    observed_head = current_migration_head()
    expect_equal(observed_head, MIGRATION_BASE_HEAD, "observed migration head")
    expect_equal(
        run_command(["git", "status", "--porcelain", "--", "migrations"]),
        "",
        "uncommitted migration changes",
    )
    log(f"observed migration head {observed_head}")

    registrations = register_wo020_fixtures(probe, fixtures)
    telemetry = emit_wo020_telemetry(fixtures)
    alpha, beta = fixtures
    require(
        alpha.project_id is not None and beta.project_id is not None,
        "fixture projects are not registered",
    )
    alpha_ids = [
        str(event.event_id) for event in telemetry.completed_events + telemetry.active_events
    ]
    beta_ids = [str(event.event_id) for event in telemetry.failed_events]

    verify_fleet_surface(probe, fixtures, registrations)
    surfaces["fleet"] = True
    observed["project_fleet_visible"] = True
    observed["project_state_counts_truthful"] = True

    alpha_scope = verify_alpha_project_surfaces(probe, alpha.project_id, telemetry)
    surfaces["project-detail"] = True
    surfaces["active-runs"] = True
    surfaces["run-detail"] = True
    surfaces["test-status"] = True
    surfaces["errors-warnings"] = True
    observed["selected_project_detail_available"] = True
    observed["run_surface_available"] = True
    observed["tests_validation_state_visible"] = True
    observed["errors_warnings_visible"] = True

    metric_event = next(
        event for event in telemetry.active_events if event.event_type == "cache.miss"
    )
    detail = alpha_scope["detail"]
    require(isinstance(detail, dict), "alpha detail is not an object")
    stored = {
        str(dict(event)["event_id"]): dict(event)["payload"] for event in detail["recent_events"]
    }
    expect_equal(
        stored[str(metric_event.event_id)],
        {"token_count": 12, "estimated": True},
        "estimated metric payload preserved exactly",
    )
    observed["estimated_metrics_labelled"] = True

    beta_scope = verify_beta_surfaces(probe, beta.project_id, telemetry)

    verify_event_streams(probe, alpha.project_id, alpha_ids)
    surfaces["event-stream"] = True
    observed["telemetry_stream_sse_or_ws"] = True
    observed["stream_replay_supported"] = True
    observed["client_reconciliation_supported"] = True

    alpha_ids.append(verify_live_stream(probe, alpha.project_id, telemetry, alpha.label))
    observed["event_timeline_near_realtime"] = True

    verify_health_surface(probe, observed_head)
    surfaces["platform-health"] = True
    observed["platform_health_visible"] = True
    observed["postgres_canonical"] = True
    observed["redis_noncanonical"] = True
    observed["unavailable_metrics_not_fabricated"] = True

    verify_bounded_access(probe, alpha.project_id)
    observed["deterministic_access_control"] = True
    observed["backend_api_bounded"] = True

    verify_restart_recovery(probe, alpha.project_id)
    observed["restart_recovery"] = True

    verify_redis_loss_recovery(probe, alpha, telemetry)
    observed["redis_loss_recovery"] = True

    beta_tokens = (
        str(beta.project_id),
        beta.relative_path,
        str(telemetry.failed_run),
        str(telemetry.beta_task),
        *beta_ids,
    )
    alpha_leaks = verify_isolation(
        [
            alpha_scope["detail"],
            alpha_scope["runs"],
            alpha_scope["run_detail"],
            alpha_scope["tests"],
            alpha_scope["errors"],
            pages_events(probe, alpha.project_id, limit=100),
        ],
        beta_tokens,
    )
    alpha_tokens = (
        str(alpha.project_id),
        alpha.relative_path,
        str(telemetry.completed_run),
        str(telemetry.active_run),
        str(telemetry.alpha_task),
        *alpha_ids,
    )
    beta_leaks = verify_isolation(
        [
            beta_scope["tests"],
            beta_scope["errors"],
            control_center_detail(probe, beta.project_id),
            pages_events(probe, beta.project_id, limit=100),
        ],
        alpha_tokens,
    )
    expect_equal(alpha_leaks, 0, "alpha-scoped surfaces leak beta identity")
    expect_equal(beta_leaks, 0, "beta-scoped surfaces leak alpha identity")
    observed["project_isolation"] = True

    verify_dashboard_bundle(probe)
    observed["frontend_render_bounded"] = True

    hygiene = verify_evidence_hygiene(probe, alpha_leaks + beta_leaks)
    require(hygiene["durable_imports"] is True, "durable source reuse was not observed")
    observed["durable_sources_reused"] = True

    require(all(surfaces.values()), "not every canonical surface was observed")
    observed["control_center_operational_core_implemented"] = True
    missing = sorted(field for field in TRUE_FIELDS if observed.get(field) is not True)
    require(not missing, f"unobserved mandatory evidence fields: {missing}")
    expect_equal(len(IMPLEMENTED_SURFACES), len(surfaces), "surface bookkeeping")

    evidence: dict[str, object] = {
        "status": "PASS",
        "evidence_file": EVIDENCE_FILE,
        "control_center_evidence_version": EVIDENCE_VERSION,
        "observed_migration_head": observed_head,
        "migration_base_head": MIGRATION_BASE_HEAD,
        "stream_transport": STREAM_TRANSPORT,
        "api_path": API_PATH,
        "dashboard_path": DASHBOARD_PATH,
        "migration_changed": observed_head != MIGRATION_BASE_HEAD,
        **{field: True for field in TRUE_FIELDS},
        **{field: False for field in FALSE_FIELDS},
        "surface_count": len(IMPLEMENTED_SURFACES),
        "secret_leaks": hygiene["secret_leaks"],
        "filesystem_path_leaks": hygiene["filesystem_path_leaks"],
        "cross_project_leaks": hygiene["cross_project_leaks"],
        "llm_calls": hygiene["llm_calls"],
        "provider_calls": hygiene["provider_calls"],
        "implemented_surfaces": list(IMPLEMENTED_SURFACES),
    }
    require(
        set(evidence) == set(EVIDENCE_ALLOWED_FIELDS),
        "evidence drifted from the closed WO-020 control-center contract",
    )
    log(f"scanned {hygiene['scanned_bodies']} recorded bodies without leaks")
    return evidence


def write_evidence(evidence: dict[str, object]) -> None:
    EVIDENCE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_OUTPUT.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    log(f"wrote {EVIDENCE_OUTPUT.relative_to(ROOT).as_posix()}")


def data_root() -> Path:
    raw = os.environ.get("HIVE_DATA_ROOT", ".hive-data")
    root = Path(raw)
    return root if root.is_absolute() else ROOT / raw


def remove_cas_file(digest: str) -> None:
    local = data_root() / "cas" / "sha256" / digest[:2] / f"{digest[2:]}.zst"
    if local.exists():
        try:
            local.unlink()
        except OSError:
            container_path = f"/var/lib/hive/cas/sha256/{digest[:2]}/{digest[2:]}.zst"
            run_command(
                ["docker", "compose", "exec", "-T", "api", "rm", "-f", container_path],
                check=False,
            )
    require(not local.exists(), f"CAS fixture artifact remains: {digest}")


def remove_fixture_repository(repository: Path) -> None:
    if not repository.exists():
        return

    def retry_readonly(
        function: Callable[..., object], failed_path: str, _exc_info: object
    ) -> None:
        os.chmod(failed_path, stat.S_IWRITE)
        function(failed_path)

    shutil.rmtree(repository, onerror=retry_readonly)
    if repository.exists():
        run_command(["git", "-C", str(repository), "clean", "-fdx"], check=False)
        shutil.rmtree(repository, ignore_errors=True)
    require(not repository.exists(), f"fixture repository remains: {repository}")


def cleanup_fixtures(fixtures: list[Fixture]) -> list[str]:
    """Delete this run's fixture graph, prove it is gone and remove the repositories."""

    if not fixtures:
        return []
    for fixture in fixtures:
        require(
            WO020_FIXTURE_PATH.fullmatch(fixture.relative_path) is not None,
            f"fixture cleanup refused an unexpected path {fixture.relative_path}",
        )
    digests = sorted({digest for fixture in fixtures for digest in fixture.task_digests})
    for digest in digests:
        require(SHA256_PATTERN.fullmatch(digest) is not None, "fixture digest is not a SHA-256")
    path_sql = ", ".join(f"'{fixture.relative_path}'" for fixture in fixtures)
    digest_sql = ", ".join(f"'{digest}'" for digest in digests) or "''"
    cleanup_sql = f"""
BEGIN;
CREATE TEMP TABLE wo020_fixture_blobs ON COMMIT DROP AS
SELECT DISTINCT t.extraction_id, t.original_blob_sha256
FROM tasks AS t
JOIN projects AS p ON p.project_id = t.project_id
WHERE p.relative_path IN ({path_sql});
DELETE FROM telemetry_events
WHERE project_id IN (SELECT project_id FROM projects WHERE relative_path IN ({path_sql}));
SELECT 'TELEMETRY:' || count(*) FROM telemetry_events AS e
JOIN projects AS p ON p.project_id = e.project_id
WHERE p.relative_path IN ({path_sql});
DELETE FROM tasks
WHERE project_id IN (SELECT project_id FROM projects WHERE relative_path IN ({path_sql}));
SELECT 'TASKS:' || count(*) FROM tasks AS t
JOIN projects AS p ON p.project_id = t.project_id
WHERE p.relative_path IN ({path_sql});
DELETE FROM task_extractions AS e
USING wo020_fixture_blobs AS b
WHERE e.extraction_id = b.extraction_id
  AND NOT EXISTS (SELECT 1 FROM tasks AS t WHERE t.extraction_id = e.extraction_id);
WITH deleted_cas AS (
    DELETE FROM cas_blobs AS c
    USING wo020_fixture_blobs AS b
    WHERE c.sha256 = b.original_blob_sha256
      AND NOT EXISTS (SELECT 1 FROM tasks AS t WHERE t.original_blob_sha256 = c.sha256)
      AND NOT EXISTS (SELECT 1 FROM task_extractions AS e WHERE e.source_sha256 = c.sha256)
    RETURNING c.sha256
)
SELECT 'CAS_ORPHAN:' || sha256 FROM deleted_cas;
DELETE FROM projects WHERE relative_path IN ({path_sql});
SELECT 'PROJECTS:' || count(*) FROM projects WHERE relative_path IN ({path_sql});
SELECT 'CAS_ROWS:' || count(*) FROM cas_blobs WHERE sha256 IN ({digest_sql});
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
    for name in ("TELEMETRY", "TASKS", "PROJECTS", "CAS_ROWS"):
        observed_lines = [line for line in lines if line.startswith(f"{name}:")]
        expect_equal(observed_lines, [f"{name}:0"], f"fixture cleanup assertion for {name}")
    orphans = [line.removeprefix("CAS_ORPHAN:") for line in lines if line.startswith("CAS_ORPHAN:")]
    for digest in orphans:
        require(SHA256_PATTERN.fullmatch(digest) is not None, "orphan digest is not a SHA-256")
        remove_cas_file(digest)
    for fixture in fixtures:
        remove_fixture_repository(fixture.repository)
    log(f"removed {len(fixtures)} fixtures and {len(orphans)} CAS artifacts")
    return [fixture.relative_path for fixture in fixtures]


def restore_stack(probe: ApiProbe) -> None:
    compose("start", "redis", check=False)
    compose("start", "api", check=False)
    wait_for_api_health(probe, attempts=90)
    log("compose stack restored")


def main() -> int:
    api_port = os.environ.get("HIVE_API_PORT", "8000")
    dashboard_port = os.environ.get("HIVE_DASHBOARD_PORT", "3000")
    probe = ApiProbe(
        f"http://127.0.0.1:{api_port}",
        f"http://127.0.0.1:{dashboard_port}",
    )
    fixtures: list[Fixture] = []
    failure: BaseException | None = None
    evidence: dict[str, object] | None = None
    try:
        EVIDENCE_OUTPUT.unlink(missing_ok=True)
        wait_for_api_health(probe, attempts=60)
        evidence = collect_evidence(probe, fixtures)
        write_evidence(evidence)
    except BaseException as exc:  # noqa: BLE001 - any failure must fail the integration run
        failure = exc
    finally:
        try:
            removed = cleanup_fixtures(fixtures)
            log(f"fixture cleanup removed {len(removed)} project fixtures")
        except BaseException as cleanup_exc:  # noqa: BLE001
            failure = failure or cleanup_exc
            log(f"fixture cleanup failed: {cleanup_exc!r}")
        try:
            restore_stack(probe)
        except BaseException as restore_exc:  # noqa: BLE001
            failure = failure or restore_exc
            log(f"stack restore failed: {restore_exc!r}")
    if failure is not None:
        EVIDENCE_OUTPUT.unlink(missing_ok=True)
        log(f"FAILED: {failure!r}")
        return 1
    require(evidence is not None, "evidence collection returned no payload")
    log(f"control-center-core-v1 evidence ready with {len(evidence)} bounded fields")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
