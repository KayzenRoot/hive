from __future__ import annotations

import base64
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from pydantic import SecretStr

from app.config import Settings
from app.execution_orchestrator import (
    ExecutionOrchestrator,
    ExecutorAdapterError,
    ExecutorRequest,
)
from app.executor_provider import OpenAICompatibleExecutorAdapter, build_executor_adapter
from app.registry import InspectionResult, ProjectResponse
from app.runner import ToolPolicy
from app.task_intake import TaskResponse

PROJECT_ID = UUID("00000000-0000-0000-0000-000000000101")
TASK_ID = UUID("00000000-0000-0000-0000-000000000201")


class ProviderServer:
    def __init__(self, response: bytes, *, redirect_to: str | None = None) -> None:
        self.response = response
        self.redirect_to = redirect_to
        self.requests: list[dict[str, Any]] = []
        self.authorization: str | None = None
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                if owner.redirect_to is not None:
                    self.send_response(302)
                    self.send_header("Location", owner.redirect_to)
                    self.end_headers()
                    return
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                owner.requests.append(json.loads(body))
                owner.authorization = self.headers.get("Authorization")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(owner.response)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> ProviderServer:
        self.thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address
        if isinstance(host, bytes):
            host = host.decode("ascii")
        return f"http://{host}:{port}/v1"


def provider_response(
    *,
    content: dict[str, object],
    model: str = "test-model",
    usage: dict[str, object] | None = None,
) -> bytes:
    response: dict[str, object] = {
        "id": "req-123",
        "model": model,
        "choices": [{"message": {"content": json.dumps(content)}}],
    }
    if usage is not None:
        response["usage"] = usage
    return json.dumps(response).encode()


def structured_result() -> dict[str, object]:
    return {
        "operations": [
            {
                "kind": "create",
                "path": "src/generated.py",
                "content_base64": base64.b64encode(b"VALUE = 1\n").decode(),
            }
        ],
        "summary": "Create generated module.",
        "decisions": ["Use the existing Runner."],
        "test_commands": [[sys.executable, "-c", "print('test ok')"]],
        "validation_commands": [[sys.executable, "-c", "print('validation ok')"]],
        "errors_fixed": ["executor transport missing"],
        "risks": [],
        "pending_items": [],
        "proposed_checkpoint_update": "",
    }


def settings(base_url: str, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "executor_enabled": True,
        "executor_base_url": base_url,
        "executor_model": "test-model",
        "executor_api_key": SecretStr("WO029_C3_SECRET_NEVER_LEAK"),
        "executor_timeout_seconds": 2,
        "executor_max_response_bytes": 100_000,
    }
    values.update(overrides)
    return Settings.model_validate(values)


def request() -> ExecutorRequest:
    return ExecutorRequest(PROJECT_ID, TASK_ID)


def context() -> SimpleNamespace:
    class Serializable(SimpleNamespace):
        def model_dump(self, *, mode: str) -> dict[str, object]:
            assert mode == "json"
            return {"governance": ["CHECKPOINT"], "task": {"title": "small task"}}

    return Serializable()


def test_concrete_transport_returns_structured_result_and_real_call_counts() -> None:
    with ProviderServer(
        provider_response(
            content=structured_result(),
            usage={
                "prompt_tokens": 100,
                "prompt_tokens_details": {"cached_tokens": 64},
                "completion_tokens": 8,
            },
        )
    ) as provider:
        adapter = build_executor_adapter(settings(provider.base_url))
        result = adapter.execute(request(), context())

    assert isinstance(adapter, OpenAICompatibleExecutorAdapter)
    assert result.change_set.operations[0].path == "src/generated.py"
    assert result.change_set.operations[0].content == b"VALUE = 1\n"
    assert result.change_set.request_id == "req-123"
    assert result.executor_provider_calls == 1
    assert result.executor_llm_calls == 1
    assert len(provider.requests) == 1
    assert provider.requests[0]["response_format"] == {"type": "json_object"}
    assert provider.authorization == "Bearer WO029_C3_SECRET_NEVER_LEAK"


def test_disabled_or_incomplete_configuration_fails_closed() -> None:
    with pytest.raises(ExecutorAdapterError, match="executor_disabled"):
        build_executor_adapter(Settings())
    with pytest.raises(ExecutorAdapterError, match="configuration_invalid"):
        build_executor_adapter(Settings(executor_enabled=True))


@pytest.mark.parametrize(
    "response",
    [
        b"not-json",
        json.dumps({"choices": []}).encode(),
        provider_response(content={"summary": "missing operations"}),
    ],
)
def test_malformed_provider_output_fails_closed(response: bytes) -> None:
    with ProviderServer(response) as provider:
        adapter = build_executor_adapter(settings(provider.base_url))
        with pytest.raises(ExecutorAdapterError):
            adapter.execute(request(), context())


def test_oversized_provider_response_fails_closed() -> None:
    response = provider_response(content=structured_result())
    with ProviderServer(response) as provider:
        adapter = build_executor_adapter(
            settings(provider.base_url, executor_max_response_bytes=32)
        )
        with pytest.raises(ExecutorAdapterError, match="provider_response_too_large"):
            adapter.execute(request(), context())


def test_provider_model_mismatch_fails_closed() -> None:
    with ProviderServer(
        provider_response(content=structured_result(), model="unexpected-model")
    ) as provider:
        adapter = build_executor_adapter(settings(provider.base_url))
        with pytest.raises(ExecutorAdapterError, match="provider_model_mismatch"):
            adapter.execute(request(), context())


def test_secret_is_not_present_in_adapter_error() -> None:
    secret = "WO029_C3_SECRET_NEVER_LEAK"
    configured = Settings(
        executor_enabled=True,
        executor_base_url="http://127.0.0.1:1/v1",
        executor_model="test-model",
        executor_api_key=SecretStr(secret),
        executor_timeout_seconds=0.1,
    )
    adapter = build_executor_adapter(configured)
    with pytest.raises(ExecutorAdapterError) as caught:
        adapter.execute(request(), context())
    assert secret not in str(caught.value)


def test_provider_redirect_is_rejected_before_forwarding_credentials() -> None:
    with (
        ProviderServer(provider_response(content=structured_result())) as target,
        ProviderServer(b"", redirect_to=target.base_url) as redirect,
    ):
        adapter = build_executor_adapter(settings(redirect.base_url))
        with pytest.raises(ExecutorAdapterError, match="provider_http_302"):
            adapter.execute(request(), context())
        assert target.requests == []


def test_configured_transport_runs_through_orchestrator_runner_and_staging(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    project = SimpleNamespace(
        project_id=PROJECT_ID,
        relative_path="project",
        state="READY",
        repository_accessible=True,
        detached_head=False,
        working_tree_clean=True,
        git_branch="main",
        git_head_sha="a" * 40,
    )
    task = SimpleNamespace(task_id=TASK_ID, project_id=PROJECT_ID)

    class SerializableContext(SimpleNamespace):
        def model_dump(self, *, mode: str) -> dict[str, object]:
            assert mode == "json"
            return {
                "project": {"project_id": str(PROJECT_ID)},
                "task": {"task_id": str(TASK_ID), "project_id": str(PROJECT_ID)},
                "governance": [
                    "CHECKPOINT",
                    "SCOPE",
                    "DEFINITION_OF_DONE",
                    "ARCHITECTURE",
                    "DECISIONS",
                ],
            }

    context_value = SerializableContext(
        project=SimpleNamespace(project_id=PROJECT_ID),
        task=SimpleNamespace(task_id=TASK_ID, project_id=PROJECT_ID),
        governance=[
            SimpleNamespace(kind=kind)
            for kind in ("CHECKPOINT", "SCOPE", "DEFINITION_OF_DONE", "ARCHITECTURE", "DECISIONS")
        ],
    )
    inspection = SimpleNamespace(
        git_branch="main",
        git_head_sha="a" * 40,
        detached_head=False,
        repository_accessible=True,
        working_tree_clean=True,
        state="READY",
    )

    with ProviderServer(
        provider_response(
            content=structured_result(),
            usage={
                "prompt_tokens": 100,
                "prompt_tokens_details": {"cached_tokens": 64},
                "completion_tokens": 8,
            },
        )
    ) as provider:
        configured = settings(
            provider.base_url,
            projects_root=tmp_path,
            executor_prompt_cache_enabled=True,
        )
        orchestrator = ExecutionOrchestrator(
            configured,
            tool_policy=ToolPolicy((sys.executable,)),
            project_loader=lambda _settings, _project_id: cast(ProjectResponse, project),
            task_loader=lambda _settings, _project_id, _task_id: cast(TaskResponse, task),
            context_builder=lambda *_args, **_kwargs: context_value,
            repository_inspector=lambda _path: cast(InspectionResult, inspection),
            event_emitter=lambda *_args, **_kwargs: None,
        )
        result = orchestrator.execute_configured(request())

        assert result.status == "STAGED"
        assert result.validation_passed is True
        assert result.executor_provider_calls == 1
        assert result.executor_llm_calls == 1
        assert result.provider_cache_usage is not None
        assert result.provider_cache_usage.reconciliation.value == "EXACT"
        assert result.provider_cache_usage.observed_hit is True
        assert result.staged_run.apply is not None
        assert (workspace / "src" / "generated.py").read_text() == "VALUE = 1\n"
        assert len(provider.requests) == 1
        assert len(provider.requests[0]["messages"]) == 2
        assert provider.requests[0]["response_format"] == {"type": "json_object"}
