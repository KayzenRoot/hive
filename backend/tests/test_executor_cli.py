from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest

from app import executor_cli
from app.execution_orchestrator import ExecutorAdapterError, ExecutorRequest

PROJECT_ID = UUID("00000000-0000-0000-0000-000000000101")
TASK_ID = UUID("00000000-0000-0000-0000-000000000201")


class _Result:
    status = "STAGED"

    def to_json(self) -> str:
        return '{"status":"STAGED"}\n'


def test_cli_dispatches_configured_execution(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    observed: dict[str, object] = {}

    class Orchestrator:
        def __init__(self, settings: object) -> None:
            observed["settings"] = settings

        def execute_configured(self, request: object) -> _Result:
            observed["request"] = request
            return _Result()

    settings = SimpleNamespace(name="fixture")
    monkeypatch.setattr(executor_cli, "get_settings", lambda: settings)
    monkeypatch.setattr(executor_cli, "ExecutionOrchestrator", Orchestrator)

    exit_code = executor_cli.run(
        [
            "--project-id",
            str(PROJECT_ID),
            "--task-id",
            str(TASK_ID),
            "--expected-branch",
            "main",
            "--expected-head-sha",
            "a" * 40,
            "--top-k",
            "4",
            "--disclosure-level",
            "L2",
        ]
    )

    assert exit_code == 0
    assert observed["settings"] is settings
    request = cast(ExecutorRequest, observed["request"])
    assert request.project_id == PROJECT_ID
    assert request.task_id == TASK_ID
    assert request.expected_branch == "main"
    assert request.expected_head_sha == "a" * 40
    assert request.top_k == 4
    assert request.disclosure_level == "L2"
    assert capsys.readouterr().out == '{"status":"STAGED"}\n'


def test_cli_returns_bounded_error_without_provider_detail(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    secret = "WO029_C3_SECRET_NEVER_LEAK"

    class Orchestrator:
        def __init__(self, _settings: object) -> None:
            pass

        def execute_configured(self, _request: object) -> _Result:
            raise ExecutorAdapterError(f"provider failed: {secret}")

    monkeypatch.setattr(executor_cli, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(executor_cli, "ExecutionOrchestrator", Orchestrator)

    exit_code = executor_cli.run(["--project-id", str(PROJECT_ID), "--task-id", str(TASK_ID)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert '"code":"adapter_error"' in captured.err
    assert secret not in captured.err
    assert captured.out == ""
