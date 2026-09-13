from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app import control_center_full, main
from app.config import Settings
from app.control_center_full import (
    ALERT_IDS,
    CHART_IDS,
    HEALTH_IDS,
    PROJECT_CAPABILITIES,
    FullStatus,
)
from app.control_center_metrics import MetricProvenance
from app.control_center_storage_metrics import StorageObservation
from app.registry import ProjectResponse, ProjectState
from app.telemetry import EVENT_ENVELOPE_VERSION, EventEnvelope

PROJECT_ID = UUID("00000000-0000-0000-0000-000000000022")
NOW = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)


def project() -> SimpleNamespace:
    return SimpleNamespace(
        project_id=PROJECT_ID,
        name="fixture",
        relative_path="fixture",
        git_branch="main",
        git_head_sha="a" * 40,
        detached_head=False,
        repository_accessible=True,
        working_tree_clean=True,
        language_stack=["python"],
        state=ProjectState.READY,
        inspection_error=None,
        created_at=NOW,
        updated_at=NOW,
        last_inspected_at=NOW,
    )


def event(event_type: str, ordering_id: int, payload: dict[str, object]) -> EventEnvelope:
    return EventEnvelope(
        event_id=uuid4(),
        envelope_version=EVENT_ENVELOPE_VERSION,
        event_type=event_type,
        project_id=PROJECT_ID,
        task_id=None,
        run_id=uuid4(),
        ordering_id=ordering_id,
        occurred_at=NOW,
        payload=payload,
        provenance={"producer": "test", "deterministic": True},
        cursor=str(ordering_id),
    )


def wire(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(control_center_full, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(control_center_full, "get_project", lambda _settings, _id: project())
    monkeypatch.setattr(
        control_center_full,
        "_events_for_project",
        lambda _settings, _id: (
            [
                event("executor.started", 1, {"input_tokens": 10}),
                event("cache.hit", 2, {"layer": "retrieval"}),
                event("validation.passed", 3, {"passed": True}),
            ],
            False,
        ),
    )
    monkeypatch.setattr(
        control_center_full,
        "_index_details",
        lambda _settings, _project: (FullStatus.AVAILABLE, {"head_matches": True}),
    )
    monkeypatch.setattr(
        control_center_full,
        "_repository_inventory",
        lambda _settings, _id: ({}, [{"path": "app.py", "language": "python"}], []),
    )
    monkeypatch.setattr(
        control_center_full,
        "_retrieval_details",
        lambda _settings, _id: (FullStatus.AVAILABLE, {"corpus_state": "CURRENT"}),
    )
    monkeypatch.setattr(
        control_center_full,
        "_document_observations",
        lambda _settings, _project: [
            SimpleNamespace(
                path="docs/project-brain/13-CHECKPOINT.md",
                status=FullStatus.AVAILABLE,
                model_dump=lambda **_kwargs: {
                    "path": "docs/project-brain/13-CHECKPOINT.md",
                    "status": "AVAILABLE",
                    "byte_count": 10,
                    "source": "test",
                },
            ),
            SimpleNamespace(
                path="docs/project-brain/03-SCOPE.md",
                status=FullStatus.AVAILABLE,
                model_dump=lambda **_kwargs: {
                    "path": "docs/project-brain/03-SCOPE.md",
                    "status": "AVAILABLE",
                    "byte_count": 10,
                    "source": "test",
                },
            ),
            SimpleNamespace(
                path="docs/project-brain/15-DEFINITION-OF-DONE.md",
                status=FullStatus.AVAILABLE,
                model_dump=lambda **_kwargs: {
                    "path": "docs/project-brain/15-DEFINITION-OF-DONE.md",
                    "status": "AVAILABLE",
                    "byte_count": 10,
                    "source": "test",
                },
            ),
        ],
    )
    monkeypatch.setattr(control_center_full, "_git_commits", lambda _settings, _project: [])
    monkeypatch.setattr(control_center_full, "summarize_runs", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        control_center_full,
        "_memory_details",
        lambda _settings, _id: (FullStatus.AVAILABLE, {"record_count": 0}),
    )
    monkeypatch.setattr(
        control_center_full,
        "_health_surfaces",
        lambda _settings: [
            control_center_full.HealthSurface(
                id=health_id,
                status=FullStatus.AVAILABLE,
                summary="test",
                provenance=MetricProvenance.EXACT,
                details={"free_ratio": 0.5} if health_id == "platform-resource-health" else {},
            )
            for health_id in HEALTH_IDS
        ],
    )
    monkeypatch.setattr(
        control_center_full,
        "observe_project_storage",
        lambda _settings, _id: StorageObservation(100, 50, 1, 1),
    )


def test_full_contract_exposes_all_closed_surface_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    wire(monkeypatch)

    response = TestClient(main.app).get(
        "/api/v1/control-center/projects/00000000-0000-0000-0000-000000000022/full?history_points=7"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["control_center_full_version"] == "control-center-full-v1"
    assert {item["id"] for item in body["capabilities"]} == set(PROJECT_CAPABILITIES)
    assert {item["id"] for item in body["charts"]} == set(CHART_IDS)
    assert {item["id"] for item in body["alerts"]} == set(ALERT_IDS)
    assert {item["id"] for item in body["health"]} == set(HEALTH_IDS)
    assert body["canonical_store"] == "postgres"
    assert body["hot_store_canonical"] is False
    assert body["full_v01_complete_claimed"] is False
    assert body["history_max_points"] == 7
    assert {chart["max_points"] for chart in body["charts"]} == {7, 100}


def test_full_endpoint_keeps_missing_observations_truthful(monkeypatch: pytest.MonkeyPatch) -> None:
    wire(monkeypatch)

    def missing_document(path: str) -> SimpleNamespace:
        return SimpleNamespace(
            path=path,
            status=FullStatus.UNAVAILABLE,
            model_dump=lambda **_kwargs: {
                "path": path,
                "status": "UNAVAILABLE",
                "byte_count": None,
                "source": "test",
            },
        )

    monkeypatch.setattr(
        control_center_full,
        "_document_observations",
        lambda _settings, _project: [
            missing_document(path) for path in control_center_full.FULL_DOCUMENTS
        ],
    )

    response = TestClient(main.app).get(
        "/api/v1/control-center/projects/00000000-0000-0000-0000-000000000022/full"
    )

    assert response.status_code == 200
    checkpoint = next(
        item for item in response.json()["capabilities"] if item["id"] == "checkpoint-scope-dod"
    )
    assert checkpoint["status"] == "UNAVAILABLE"
    assert "0" not in checkpoint["summary"]


def test_context_signal_ratio_never_reuses_context_reduction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire(monkeypatch)
    fixture_settings = cast(Settings, SimpleNamespace())
    fixture_project = cast(ProjectResponse, project())
    reduction_only = control_center_full._charts(
        fixture_settings,
        fixture_project,
        [event("context.built", 1, {"estimated_tokens_before": 100, "estimated_tokens_after": 60})],
        False,
        7,
    )
    charts = {item.id: item for item in reduction_only}
    assert charts["context-reduction"].points[0].value == 40
    assert charts["context-signal-ratio"].status is FullStatus.UNAVAILABLE
    assert charts["context-signal-ratio"].points == []

    signal = control_center_full._charts(
        fixture_settings,
        fixture_project,
        [
            event(
                "context.built",
                1,
                {
                    "useful_context_tokens": 30,
                    "total_context_tokens_sent": 60,
                },
            )
        ],
        False,
        7,
    )
    signal_chart = {item.id: item for item in signal}["context-signal-ratio"]
    assert signal_chart.points[0].value == 0.5
    assert signal_chart.points[0].source.startswith("derived:useful-context-tokens")


def test_executor_absence_is_unknown_and_explicit_disconnect_is_active() -> None:
    unknown = control_center_full._executor_connection_observation(
        [event("executor.started", 1, {"adapter": "fixture"})]
    )
    assert unknown[0] is FullStatus.UNKNOWN
    assert unknown[2] is MetricProvenance.UNAVAILABLE

    connected = control_center_full._executor_connection_observation(
        [event("tool.called", 1, {"executor_heartbeat": True})]
    )
    assert connected[0] is FullStatus.CLEAR

    disconnected = control_center_full._executor_connection_observation(
        [event("tool.called", 1, {"connection_status": "disconnected"})]
    )
    assert disconnected[0] is FullStatus.ACTIVE


def test_checkpoint_mismatch_uses_git_heads_and_dirty_governance_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate = project()

    def fake_git(_root: Path, *arguments: str) -> str | None:
        if arguments[:2] == ("rev-parse", "--verify"):
            return "b" * 40
        if arguments[0] == "ls-files":
            return "100644"
        if arguments[0] == "status":
            return ""
        if arguments[0] == "cat-file":
            return "10"
        return None

    monkeypatch.setattr(control_center_full, "_project_path", lambda _s, _p: tmp_path)
    monkeypatch.setattr(control_center_full, "_git_command", fake_git)
    checkpoint = control_center_full.DocumentObservation(
        path=control_center_full.FULL_DOCUMENTS[0],
        status=FullStatus.AVAILABLE,
        byte_count=10,
        git_head_sha="b" * 40,
        tracked=True,
        working_tree_clean=True,
        source="git:HEAD-blob:fixture",
    )
    mismatch = control_center_full._checkpoint_observation(
        cast(Settings, SimpleNamespace()), cast(ProjectResponse, candidate), checkpoint
    )
    assert mismatch[0] is FullStatus.ACTIVE
    assert mismatch[2] is MetricProvenance.EXACT

    candidate.git_head_sha = "b" * 40
    dirty = control_center_full.DocumentObservation(
        path=control_center_full.FULL_DOCUMENTS[0],
        status=FullStatus.UNAVAILABLE,
        byte_count=None,
        git_head_sha="b" * 40,
        tracked=True,
        working_tree_clean=False,
        source="git:governance-document-working-tree-dirty",
    )
    unavailable = control_center_full._checkpoint_observation(
        cast(Settings, SimpleNamespace()), cast(ProjectResponse, candidate), dirty
    )
    assert unavailable[0] is FullStatus.UNAVAILABLE
    assert unavailable[2] is MetricProvenance.UNAVAILABLE


def test_document_observation_rejects_dirty_working_tree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_git(_root: Path, *arguments: str) -> str | None:
        if arguments[:2] == ("rev-parse", "--verify"):
            return "a" * 40
        if arguments[0] == "ls-files":
            return "100644"
        if arguments[0] == "status":
            return (
                " M docs/project-brain/13-CHECKPOINT.md"
                if arguments[-1].endswith("13-CHECKPOINT.md")
                else ""
            )
        if arguments[0] == "cat-file":
            return "10"
        return None

    monkeypatch.setattr(control_center_full, "_project_path", lambda _s, _p: tmp_path)
    monkeypatch.setattr(control_center_full, "_git_command", fake_git)
    observations = control_center_full._document_observations(
        cast(Settings, SimpleNamespace()), cast(ProjectResponse, project())
    )
    assert observations[0].status is FullStatus.UNAVAILABLE
    assert observations[0].working_tree_clean is False
    assert observations[0].source == "git:governance-document-working-tree-dirty"
    assert observations[1].status is FullStatus.AVAILABLE


def test_platform_resource_health_exposes_required_observation_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        control_center_full,
        "collect_health",
        lambda _settings: SimpleNamespace(checks={}),
    )
    monkeypatch.setattr(control_center_full, "observed_schema_revision", lambda _settings: "0007")
    monkeypatch.setattr(
        control_center_full,
        "_read_platform_text",
        lambda _path: (_ for _ in ()).throw(OSError("unsupported")),
    )
    monkeypatch.setattr(
        shutil,
        "disk_usage",
        lambda _path: (_ for _ in ()).throw(OSError("unsupported")),
    )
    settings = cast(Settings, SimpleNamespace(resolved_data_root=Path("fixture-data")))
    resource = control_center_full._health_surfaces(settings)[0]
    assert resource.status is FullStatus.UNAVAILABLE
    observations = cast(dict[str, dict[str, object]], resource.details["observations"])
    assert set(observations) == {"cpu", "ram", "disk", "io"}
    assert all(item["status"] == "UNAVAILABLE" for item in observations.values())


def test_dependency_graph_exposes_python_only_limitation() -> None:
    status, details = control_center_full._dependency_summary(
        cast(Settings, SimpleNamespace()),
        cast(ProjectResponse, project()),
        [
            {"path": "app.py", "language": "python"},
            {"path": "ui.ts", "language": "typescript"},
        ],
    )
    assert status is FullStatus.DEGRADED
    assert details["supported_languages"] == ["python"]
    assert details["unsupported_languages"] == ["typescript"]
    assert details["complete_graph"] is False


def _canonical_observations() -> list[control_center_full.DocumentObservation]:
    return [
        control_center_full.DocumentObservation(
            path=path,
            status=FullStatus.AVAILABLE,
            byte_count=100,
            git_head_sha="a" * 40,
            tracked=True,
            working_tree_clean=True,
            source=f"git:HEAD-blob:{path}",
        )
        for path in control_center_full.FULL_DOCUMENTS
    ]


def test_project_intelligence_parses_bounded_canonical_head_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blobs = {
        "docs/project-brain/13-CHECKPOINT.md": (
            "# Checkpoint\n## STATUS\nFIXTURE ACTIVE\n## IN PROGRESS\n"
            "- Verify project intelligence\n## PENDING\n- Fixture follow-up\n"
            "- Fixture audit\n## NEXT STEP\nPublish fixture result.\n"
        ),
        "docs/project-brain/03-SCOPE.md": (
            "# Scope\n## NECESSARY — V0.1\n- Full HIVE Control Center.\n- Bounded fixture scope.\n"
        ),
        "docs/project-brain/15-DEFINITION-OF-DONE.md": (
            "# DoD\n## Functional\n- [x] Fixture validation\n- [ ] Fixture follow-up\n"
        ),
    }
    monkeypatch.setattr(
        control_center_full,
        "_git_head_blob",
        lambda _settings, _project, relative, _observation: blobs[relative],
    )

    status, details = control_center_full._canonical_project_intelligence(
        cast(Settings, SimpleNamespace()),
        cast(ProjectResponse, project()),
        _canonical_observations(),
    )

    assert status is FullStatus.AVAILABLE
    checkpoint = cast(dict[str, object], details["checkpoint"])
    assert checkpoint["current_status"] == "FIXTURE ACTIVE"
    pending = cast(dict[str, object], checkpoint["pending"])
    assert pending["count"] == 2
    assert checkpoint["next_step"] == "Publish fixture result."
    scope = cast(dict[str, object], details["scope"])
    assert "Full HIVE Control Center." in cast(list[str], scope["required_items"])
    dod = cast(dict[str, object], details["definition_of_done"])
    assert dod["total_count"] == 2
    assert dod["completed_count"] == 1
    assert dod["percentage"] == 50.0
    assert dod["source"] == "git:HEAD-blob:docs/project-brain/15-DEFINITION-OF-DONE.md"


def test_definition_of_done_without_status_grammar_never_fabricates_percentage() -> None:
    details = control_center_full._parse_definition_of_done(
        "# DoD\n## Functional\n- One requirement\n- Another requirement\n"
    )

    assert details is not None
    assert details["status"] == "UNAVAILABLE"
    assert details["total_count"] == 2
    assert details["completed_count"] is None
    assert details["percentage"] is None
    assert details["percentage_status"] == "UNAVAILABLE"


def _project_intelligence_with_blobs(
    monkeypatch: pytest.MonkeyPatch,
    checkpoint: str,
    scope: str | None = None,
) -> tuple[FullStatus, dict[str, object]]:
    blobs = {
        control_center_full.FULL_DOCUMENTS[0]: checkpoint,
        control_center_full.FULL_DOCUMENTS[1]: scope
        or "# Scope\n## NECESSARY \u2014 V0.1\n- Required\n",
        control_center_full.FULL_DOCUMENTS[2]: (
            "# DoD\n## Functional\n- [x] Fixture validation\n- [ ] Fixture follow-up\n"
        ),
    }
    monkeypatch.setattr(
        control_center_full,
        "_git_head_blob",
        lambda _settings, _project, relative, _observation: blobs[relative],
    )
    return control_center_full._canonical_project_intelligence(
        cast(Settings, SimpleNamespace()),
        cast(ProjectResponse, project()),
        _canonical_observations(),
    )


def test_project_intelligence_fails_closed_when_checkpoint_in_progress_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status, details = _project_intelligence_with_blobs(
        monkeypatch,
        "# Checkpoint\n## STATUS\nACTIVE\n## PENDING\n- Follow-up\n## NEXT STEP\nContinue.\n",
    )

    assert status is FullStatus.UNAVAILABLE
    assert details["status"] == "UNAVAILABLE"
    assert "13-CHECKPOINT.md" in cast(str, details["reason"])


def test_project_intelligence_fails_closed_when_checkpoint_pending_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status, details = _project_intelligence_with_blobs(
        monkeypatch,
        "# Checkpoint\n## STATUS\nACTIVE\n## IN PROGRESS\n- Work\n## NEXT STEP\nContinue.\n",
    )

    assert status is FullStatus.UNAVAILABLE
    assert details["status"] == "UNAVAILABLE"
    assert "13-CHECKPOINT.md" in cast(str, details["reason"])


def test_project_intelligence_fails_closed_when_scope_required_section_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status, details = _project_intelligence_with_blobs(
        monkeypatch,
        "# Checkpoint\n## STATUS\nACTIVE\n## IN PROGRESS\n- Work\n"
        "## PENDING\n- Follow-up\n## NEXT STEP\nContinue.\n",
        scope="# Scope\n## FUTURE\n- Not required now\n",
    )

    assert status is FullStatus.UNAVAILABLE
    assert details["status"] == "UNAVAILABLE"
    assert "03-SCOPE.md" in cast(str, details["reason"])


def test_project_intelligence_fails_closed_when_mandatory_section_is_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status, details = _project_intelligence_with_blobs(
        monkeypatch,
        "# Checkpoint\n## STATUS\nACTIVE\n## IN PROGRESS\n- Work\n"
        "## PENDING\n\n## NEXT STEP\nContinue.\n",
    )

    assert status is FullStatus.UNAVAILABLE
    assert details["status"] == "UNAVAILABLE"
    assert "13-CHECKPOINT.md" in cast(str, details["reason"])


def test_canonical_project_intelligence_fails_closed_on_missing_or_malformed_blob(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blobs: dict[str, str | None] = {
        control_center_full.FULL_DOCUMENTS[0]: (
            "# Checkpoint\n## STATUS\nACTIVE\n## IN PROGRESS\n- Work\n"
            "## PENDING\n- Follow-up\n## NEXT STEP\nContinue.\n"
        ),
        control_center_full.FULL_DOCUMENTS[1]: ("# Scope\n## NECESSARY \u2014 V0.1\n- Required\n"),
        control_center_full.FULL_DOCUMENTS[2]: None,
    }
    monkeypatch.setattr(
        control_center_full,
        "_git_head_blob",
        lambda _settings, _project, relative, _observation: blobs[relative],
    )

    status, details = control_center_full._canonical_project_intelligence(
        cast(Settings, SimpleNamespace()),
        cast(ProjectResponse, project()),
        _canonical_observations(),
    )

    assert status is FullStatus.UNAVAILABLE
    assert details["status"] == "UNAVAILABLE"
    assert "15-DEFINITION-OF-DONE.md" in cast(str, details["reason"])


def test_git_head_blob_requires_clean_exact_registered_head(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    candidate = cast(ProjectResponse, project())
    observation = _canonical_observations()[0]

    def fake_git(_root: Path, *arguments: str) -> str | None:
        if arguments[:2] == ("rev-parse", "--verify"):
            return "a" * 40
        if arguments[:2] == ("cat-file", "blob"):
            return "## STATUS\nACTIVE\n"
        return None

    monkeypatch.setattr(control_center_full, "_project_path", lambda _s, _p: tmp_path)
    monkeypatch.setattr(control_center_full, "_git_command", fake_git)
    assert (
        control_center_full._git_head_blob(
            cast(Settings, SimpleNamespace()), candidate, observation.path, observation
        )
        == "## STATUS\nACTIVE\n"
    )

    dirty = observation.model_copy(update={"working_tree_clean": False})
    assert (
        control_center_full._git_head_blob(
            cast(Settings, SimpleNamespace()), candidate, observation.path, dirty
        )
        is None
    )
    candidate.git_head_sha = "b" * 40
    assert (
        control_center_full._git_head_blob(
            cast(Settings, SimpleNamespace()), candidate, observation.path, observation
        )
        is None
    )


def test_decisions_details_exposes_canonical_ledger_separately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observation = control_center_full.DocumentObservation(
        path=control_center_full.DECISIONS_DOCUMENT,
        status=FullStatus.AVAILABLE,
        byte_count=120,
        git_head_sha="a" * 40,
        tracked=True,
        working_tree_clean=True,
        source=f"git:HEAD-blob:{control_center_full.DECISIONS_DOCUMENT}",
    )
    monkeypatch.setattr(control_center_full, "_document_observation", lambda *_args: observation)
    monkeypatch.setattr(
        control_center_full,
        "_git_head_blob",
        lambda *_args: ("# Decisions\n## HIVE-ADR-001 — Fixture decision\n**Status:** Accepted\n"),
    )

    status, details = control_center_full._decisions_details(
        cast(Settings, SimpleNamespace()), cast(ProjectResponse, project())
    )

    assert status is FullStatus.AVAILABLE
    assert details["count"] == 1
    decisions = cast(list[dict[str, object]], details["decisions"])
    assert decisions[0]["id"] == "HIVE-ADR-001"
    assert decisions[0]["title"] == "Fixture decision"
    assert decisions[0]["status"] == "Accepted"
    assert decisions[0]["source"] == ("git:HEAD-blob:docs/project-brain/16-DECISIONS-LEDGER.md")
