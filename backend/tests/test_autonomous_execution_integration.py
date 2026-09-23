from __future__ import annotations

import subprocess
from types import SimpleNamespace
from uuid import UUID

import pytest
from scripts import autonomous_execution_integration
from scripts.autonomous_execution_integration import (
    event_linkage_is_explicit,
    execution_run_ids_are_present,
    task_ids_are_scoped,
    terminal_replay_after_cursor,
)


def test_project_level_events_may_be_taskless_but_foreign_task_ids_fail() -> None:
    expected_task = UUID("00000000-0000-0000-0000-000000000801")
    foreign_task = UUID("00000000-0000-0000-0000-000000000802")

    assert task_ids_are_scoped([None, expected_task], expected_task)
    assert not task_ids_are_scoped([None, foreign_task], expected_task)


def test_run_ids_are_required_for_execution_events_not_project_events() -> None:
    run_id = UUID("00000000-0000-0000-0000-000000000003")

    assert execution_run_ids_are_present(
        [("project.indexing", None), ("task.ingested", None), ("run.completed", run_id)]
    )
    assert not execution_run_ids_are_present([("project.indexing", None), ("run.completed", None)])


def test_event_linkage_matches_project_task_and_execution_lifecycles() -> None:
    task_id = UUID("00000000-0000-0000-0000-000000000811")
    index_run_id = UUID("00000000-0000-0000-0000-000000000812")
    execution_run_id = UUID("00000000-0000-0000-0000-000000000813")

    assert event_linkage_is_explicit(
        [
            ("project.indexing", None, index_run_id),
            ("task.ingested", task_id, None),
            ("context.built", task_id, None),
            ("executor.started", task_id, execution_run_id),
            ("run.completed", task_id, execution_run_id),
            ("project.discovered", None, None),
        ]
    )
    assert not event_linkage_is_explicit([("project.indexing", None, None)])
    assert not event_linkage_is_explicit([("task.ingested", None, None)])
    assert not event_linkage_is_explicit([("run.completed", None, execution_run_id)])


def test_terminal_event_replay_starts_after_its_immediate_predecessor() -> None:
    events = [
        ("project.indexing", "cursor-1"),
        ("task.ingested", "cursor-2"),
        ("executor.started", "cursor-3"),
        ("run.completed", "cursor-4"),
    ]

    assert terminal_replay_after_cursor(events) == "cursor-3"


def test_api_call_reports_bounded_error_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    detail = "project physical identity is already registered"
    monkeypatch.setattr(
        autonomous_execution_integration,
        "http_json",
        lambda *_args, **_kwargs: (409, {"detail": detail}),
    )

    with pytest.raises(
        AssertionError,
        match="detail=project physical identity is already registered",
    ):
        autonomous_execution_integration.api_call(
            "http://127.0.0.1:8000",
            "POST",
            "/api/v1/projects",
            expected_status=201,
        )


def test_register_fixture_reports_conflicting_relative_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def conflict(*_args: object, **_kwargs: object) -> object:
        raise AssertionError(
            "expected 201, got 409; detail=project physical identity is already registered"
        )

    monkeypatch.setattr(autonomous_execution_integration, "api_call", conflict)

    with pytest.raises(AssertionError, match="fixture_relative_path=wo019-c4-123-one"):
        autonomous_execution_integration.register_fixture(
            "http://127.0.0.1:8000", "wo019-c4-123-one"
        )


def test_executor_cli_invalid_json_reports_bounded_redacted_streams(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout = (
        b"prefix"
        + (b"x" * 470)
        + b'{"token":"supersecret","path":"/tmp/hive-private/file"} trailing'
    )
    stderr = b"separate stderr diagnostic"

    def fake_run(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=0, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(AssertionError) as error:
        autonomous_execution_integration.run_executor_cli(["docker", "compose", "run"])

    message = str(error.value)
    assert "returned invalid JSON" in message
    assert "exit_code=0" in message
    assert f"stdout_bytes={len(stdout)}" in message
    assert f"stderr_bytes={len(stderr)}" in message
    assert "prefix" in message and "separate stderr diagnostic" in message
    assert f"{len(stdout) - 320} bytes omitted" in message
    assert "supersecret" not in message
    assert "/tmp/hive-private" not in message
    assert "<redacted>" in message and "<path>" in message


def test_executor_cli_nonzero_reports_cli_error_and_keeps_streams_separate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stdout = b"unexpected stdout"
    stderr = b'{"status":"ERROR","code":"executor_unavailable"}'

    def fake_run(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=1, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(AssertionError) as error:
        autonomous_execution_integration.run_executor_cli(["docker", "compose", "run"])

    message = str(error.value)
    assert "executor_error_code=executor_unavailable" in message
    assert "exit_code=1" in message
    assert 'stdout_head_tail="unexpected stdout"' in message
    assert "stderr_head_tail=" in message and "executor_unavailable" in message


def test_executor_cli_returns_parsed_object_and_ignores_separate_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=0, stdout=b'{"status":"STAGED"}', stderr=b"diagnostic")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert autonomous_execution_integration.run_executor_cli(["docker", "compose", "run"]) == {
        "status": "STAGED"
    }
