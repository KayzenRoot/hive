"""Concrete, bounded executor transport behind HIVE's provider-independent contract."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .config import Settings
from .execution_orchestrator import ExecutorAdapterError, ExecutorRequest, ExecutorResult
from .provider_prompt_cache import (
    NoOpProviderPromptCacheAdapter,
    OpenAICompatibleProviderPromptCacheAdapter,
    ProviderUsageReceipt,
    prepare_provider_prompt_cache,
)
from .runner import ChangeOperation, ChangeSet, OperationKind

ADAPTER_KIND = "openai-compatible-http"
MAX_ERROR_CHARS = 256


class _NoRedirectHandler(HTTPRedirectHandler):
    """Do not forward a bearer credential to a redirected provider host."""

    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        return None


_HTTP_OPENER = build_opener(_NoRedirectHandler)


def _base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"}:
        raise ExecutorAdapterError("executor_base_url_invalid_scheme")
    if (
        not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ExecutorAdapterError("executor_base_url_contains_credentials")
    return normalized


def _provider_error(error: Exception) -> str:
    if isinstance(error, HTTPError):
        return f"provider_http_{error.code}"
    if isinstance(error, TimeoutError):
        return "provider_timeout"
    if isinstance(error, URLError):
        return "provider_unavailable"
    return "provider_request_failed"


def _context_payload(context: object) -> object:
    model_dump = getattr(context, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    if isinstance(context, dict):
        return context
    raise ExecutorAdapterError("context_not_serializable")


def _text_tuple(value: object, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ExecutorAdapterError(f"provider_{field}_invalid")
    return tuple(cast(list[str], value))


def _commands(value: object, field: str) -> tuple[tuple[str, ...], ...]:
    if not isinstance(value, list):
        raise ExecutorAdapterError(f"provider_{field}_invalid")
    commands: list[tuple[str, ...]] = []
    for raw in value:
        if (
            not isinstance(raw, list)
            or not raw
            or any(not isinstance(argument, str) or not argument for argument in raw)
        ):
            raise ExecutorAdapterError(f"provider_{field}_invalid")
        commands.append(tuple(cast(list[str], raw)))
    return tuple(commands)


def _operation(raw: object) -> ChangeOperation:
    if not isinstance(raw, dict):
        raise ExecutorAdapterError("provider_operation_invalid")
    kind = raw.get("kind")
    path = raw.get("path")
    if not isinstance(kind, str) or not isinstance(path, str):
        raise ExecutorAdapterError("provider_operation_invalid")
    try:
        operation_kind = OperationKind(kind)
    except ValueError as exc:
        raise ExecutorAdapterError("provider_operation_invalid") from exc
    before = raw.get("sha256_before")
    if before is not None and not isinstance(before, str):
        raise ExecutorAdapterError("provider_operation_invalid")
    if operation_kind is OperationKind.DELETE:
        if before is None:
            raise ExecutorAdapterError("provider_operation_invalid")
        return ChangeOperation.delete(path, before)
    encoded = raw.get("content_base64")
    if not isinstance(encoded, str):
        raise ExecutorAdapterError("provider_operation_invalid")
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise ExecutorAdapterError("provider_operation_content_invalid") from exc
    if operation_kind is OperationKind.CREATE:
        return ChangeOperation.create(path, content)
    if before is None:
        raise ExecutorAdapterError("provider_operation_invalid")
    return ChangeOperation.replace(path, content, before)


def _result(
    payload: object,
    model: str,
    request_id: str | None,
    provider_cache_usage: ProviderUsageReceipt | None = None,
) -> ExecutorResult:
    if not isinstance(payload, dict):
        raise ExecutorAdapterError("provider_result_invalid")
    raw_operations = payload.get("operations")
    summary = payload.get("summary")
    if not isinstance(raw_operations, list) or not isinstance(summary, str):
        raise ExecutorAdapterError("provider_result_invalid")
    operations = tuple(_operation(item) for item in raw_operations)
    tests = _commands(payload.get("test_commands"), "test_commands")
    validation = _commands(payload.get("validation_commands"), "validation_commands")
    if not tests or not validation:
        raise ExecutorAdapterError("provider_commands_required")
    return ExecutorResult(
        change_set=ChangeSet(
            operations=operations,
            model=model,
            effort="provider",
            request_id=request_id,
        ),
        summary=summary,
        decisions=_text_tuple(payload.get("decisions"), "decisions"),
        test_commands=tests,
        validation_commands=validation,
        errors_fixed=_text_tuple(payload.get("errors_fixed"), "errors_fixed"),
        risks=_text_tuple(payload.get("risks"), "risks"),
        pending_items=_text_tuple(payload.get("pending_items"), "pending_items"),
        proposed_checkpoint_update=str(payload.get("proposed_checkpoint_update") or ""),
        provider_independent=True,
        executor_llm_calls=1,
        executor_provider_calls=1,
        provider_cache_usage=provider_cache_usage,
    )


class OpenAICompatibleExecutorAdapter:
    """One-call structured executor transport; Runner remains the mutation authority."""

    provider_independent = True
    name = ADAPTER_KIND

    def __init__(self, settings: Settings) -> None:
        settings.validate_executor_limits()
        if not settings.executor_enabled:
            raise ExecutorAdapterError("executor_disabled")
        if not settings.executor_base_url or not settings.executor_model:
            raise ExecutorAdapterError("executor_configuration_incomplete")
        self.settings = settings
        self.model = settings.executor_model.strip()
        self.url = _base_url(settings.executor_base_url) + "/chat/completions"
        self.prompt_cache_adapter = (
            OpenAICompatibleProviderPromptCacheAdapter(model=self.model)
            if settings.executor_prompt_cache_enabled
            else NoOpProviderPromptCacheAdapter()
        )

    def execute(self, request: ExecutorRequest, context: object) -> ExecutorResult:
        instruction = (
            "Return only a JSON object with operations, summary, decisions, test_commands, "
            "validation_commands, errors_fixed, risks, pending_items and "
            "proposed_checkpoint_update. Each operation uses kind/path/content_base64/"
            "sha256_before as applicable. Do not commit, push, merge, or edit canonical "
            "Project Brain. Tests and validation commands are required."
        )
        context_payload = _context_payload(context)
        if self.settings.executor_prompt_cache_enabled:
            context_fingerprint = hashlib.sha256(
                json.dumps(
                    context_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest()
            cache_result = prepare_provider_prompt_cache(
                project_id=request.project_id,
                delivery_mode="FULL",
                stable_material={"executor_adapter": ADAPTER_KIND},
                dynamic_material={
                    "task_id": str(request.task_id),
                    "context": context_payload,
                },
                context_output_fingerprint=context_fingerprint,
                adapter=self.prompt_cache_adapter,
                request_cache=True,
                stable_instruction=instruction,
            )
            messages = [
                {"role": "system", "content": cache_result.envelope.stable_prefix},
                {"role": "user", "content": cache_result.envelope.dynamic_suffix},
            ]
        else:
            messages = [
                {"role": "system", "content": instruction},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "project_id": str(request.project_id),
                            "task_id": str(request.task_id),
                            "context": context_payload,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                },
            ]
        payload = {
            "model": self.model,
            "response_format": {"type": "json_object"},
            "messages": messages,
        }
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.settings.executor_api_key is not None:
            headers["Authorization"] = f"Bearer {self.settings.executor_api_key.get_secret_value()}"
        http_request = Request(self.url, data=data, headers=headers, method="POST")
        try:
            with _HTTP_OPENER.open(
                http_request, timeout=self.settings.executor_timeout_seconds
            ) as response:
                body = response.read(self.settings.executor_max_response_bytes + 1)
        except (HTTPError, OSError, TimeoutError, URLError) as exc:
            raise ExecutorAdapterError(_provider_error(exc)[:MAX_ERROR_CHARS]) from exc
        if len(body) > self.settings.executor_max_response_bytes:
            raise ExecutorAdapterError("provider_response_too_large")
        try:
            decoded = json.loads(body.decode("utf-8"))
            choices = decoded["choices"]
            message = choices[0]["message"]["content"]
            structured = json.loads(message)
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise ExecutorAdapterError("provider_malformed_response") from exc
        if (
            not isinstance(decoded, dict)
            or not isinstance(choices, list)
            or not isinstance(message, str)
        ):
            raise ExecutorAdapterError("provider_malformed_response")
        response_model = decoded.get("model")
        if response_model is not None and response_model != self.model:
            raise ExecutorAdapterError("provider_model_mismatch")
        request_id = decoded.get("id")
        if request_id is not None and not isinstance(request_id, str):
            raise ExecutorAdapterError("provider_request_id_invalid")
        provider_cache_usage = (
            self.prompt_cache_adapter.normalize_usage(decoded.get("usage"))
            if self.settings.executor_prompt_cache_enabled
            else None
        )
        return _result(structured, self.model, request_id, provider_cache_usage)


def build_executor_adapter(settings: Settings) -> OpenAICompatibleExecutorAdapter:
    """Build the configured production adapter or fail closed."""

    try:
        settings.validate_executor_limits()
    except ValueError as exc:
        raise ExecutorAdapterError("executor_configuration_invalid") from exc
    return OpenAICompatibleExecutorAdapter(settings)
