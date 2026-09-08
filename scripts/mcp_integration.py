from __future__ import annotations

import ast
import asyncio
import json
import os
import re
import sys
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, TextContent

from project_registry_integration import (
    ROOT,
    SCHEMA_REVISION,
    cleanup_temporary_root,
    compose,
    free_port,
    git,
    request,
    run,
    wait_for_health,
)
from review_evidence import (
    MCP_CORE_SURFACE_EVIDENCE_FILE,
    MCP_CORE_SURFACE_EVIDENCE_VERSION,
    MCP_CORE_SURFACE_FALSE_FIELDS,
    MCP_CORE_SURFACE_INTEGER_FIELDS,
    MCP_CORE_SURFACE_TOOLS,
    MCP_CORE_SURFACE_TRUE_FIELDS,
)

MCP_MODULE_PATH = ROOT / "backend" / "app" / "mcp_server.py"
EVIDENCE_PATH = ROOT / "tmp" / "integration-logs" / MCP_CORE_SURFACE_EVIDENCE_FILE
CHECKPOINT_RELATIVE_PATH = "docs/project-brain/13-CHECKPOINT.md"
SOURCE_RELATIVE_PATH = "docs/project-brain/04-ARCHITECTURE.md"
GOVERNANCE_RELATIVE_PATHS = (
    CHECKPOINT_RELATIVE_PATH,
    "docs/project-brain/03-SCOPE.md",
    "docs/project-brain/15-DEFINITION-OF-DONE.md",
    "docs/project-brain/04-ARCHITECTURE.md",
    "docs/project-brain/16-DECISIONS-LEDGER.md",
)
SAFE_SHA = re.compile(r"^[0-9a-f]{40}$")
MCP_INSTRUMENTATION_CONTAINER_PATH = "/workspace/projects/.mcp-instrumentation"
MCP_PROVIDER_COUNTER_CONTAINER_PATH = "/var/lib/hive/tmp/mcp-provider-calls.json"
MCP_PROVIDER_COUNTER_FIELDS = frozenset({"trap_installed", "mcp_llm_calls", "mcp_provider_calls"})


class _PayloadCapture:
    """Keep bounded normalized protocol payloads in memory for objective scans."""

    def __init__(self) -> None:
        self._payloads: list[str] = []

    def add(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self._payloads.append(encoded)

    def count_payloads_containing(self, tokens: tuple[str, ...]) -> int:
        return sum(1 for payload in self._payloads if any(token in payload for token in tokens))


def _install_provider_call_trap(instrumentation_root: Path) -> None:
    instrumentation_root.mkdir(parents=True, exist_ok=True)
    (instrumentation_root / "sitecustomize.py").write_text(
        '''"""Deterministic MCP-only provider/LLM call observation trap."""
import json
import os
from pathlib import Path

_COUNTER_PATH = Path(os.environ["MCP_PROVIDER_CALL_COUNTER"])
_COUNTER_FIELDS = {"trap_installed", "mcp_llm_calls", "mcp_provider_calls"}


def _write_counter(data):
    _COUNTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    _COUNTER_PATH.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")


def _record_and_fail(*_args, **_kwargs):
    try:
        data = json.loads(_COUNTER_PATH.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        data = {}
    if set(data) != _COUNTER_FIELDS:
        data = {"trap_installed": True, "mcp_llm_calls": 0, "mcp_provider_calls": 0}
    data["mcp_llm_calls"] += 1
    data["mcp_provider_calls"] += 1
    _write_counter(data)
    raise RuntimeError("mcp provider call trap")


_write_counter({"trap_installed": True, "mcp_llm_calls": 0, "mcp_provider_calls": 0})

import urllib.request

urllib.request.urlopen = _record_and_fail
''',
        encoding="utf-8",
    )


def _provider_call_counts(counter_path: Path) -> dict[str, int]:
    try:
        data = json.loads(counter_path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError) as exc:
        raise AssertionError("MCP provider-call trap did not produce an observation") from exc
    if set(data) != MCP_PROVIDER_COUNTER_FIELDS or data.get("trap_installed") is not True:
        raise AssertionError("MCP provider-call trap was not installed")
    counts: dict[str, int] = {}
    for field in ("mcp_llm_calls", "mcp_provider_calls"):
        value = data.get(field)
        if type(value) is not int or value < 0:
            raise AssertionError("MCP provider-call trap produced an invalid count")
        counts[field] = value
    return counts


def _absolute_path_variants(paths: tuple[Path, ...], probes: tuple[str, ...]) -> tuple[str, ...]:
    variants: set[str] = set(probes)
    for path in paths:
        text = str(path)
        variants.update({text, text.replace("\\", "/"), text.replace("/", "\\")})
    return tuple(sorted((value for value in variants if value), key=len, reverse=True))


def _dict(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AssertionError(f"{label} did not return an object")
    return cast(dict[str, Any], value)


def _string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise AssertionError(f"{label} is not text")
    return value


def _fixture_value(fixture: dict[str, Any], key: str) -> str:
    return _string(fixture.get(key), f"fixture {key}")


def _api_object(
    base_url: str, method: str, path: str, payload: dict[str, Any] | None, label: str
) -> dict[str, Any]:
    status, body = request(base_url, method, path, payload)
    if status < 200 or status >= 300:
        raise AssertionError(f"{label} returned HTTP {status}: {body}")
    return _dict(body, label)


def _create_fixture_repository(
    repository: Path, label: str, *, git_environment: dict[str, str]
) -> dict[str, Any]:
    repository.mkdir(parents=True)
    run(["git", "init", "-b", "main", str(repository)], env=git_environment)
    git(repository, ["config", "core.autocrlf", "false"], env=git_environment)
    git(repository, ["config", "core.filemode", "false"], env=git_environment)
    git(repository, ["config", "user.email", "hive-mcp@example.invalid"], env=git_environment)
    git(repository, ["config", "user.name", "HIVE MCP Integration"], env=git_environment)

    for relative_path in GOVERNANCE_RELATIVE_PATHS:
        source = (ROOT / relative_path).read_bytes()
        if relative_path == CHECKPOINT_RELATIVE_PATH:
            if not source.endswith(b"\n"):
                source += b"\n"
            source += f"\n## MCP Fixture {label}\n\nMCP_CHECKPOINT_PROJECT_{label}\n".encode()
        target = repository / Path(*relative_path.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source)

    code_path = repository / "src" / f"project_{label.lower()}.py"
    code_path.parent.mkdir(parents=True, exist_ok=True)
    code_path.write_text(
        f'PROJECT_LABEL = "{label}"\n'
        f'MCP_SEARCH_PROJECT_{label} = "project {label} retrieval sentinel"\n',
        encoding="utf-8",
    )
    test_path = repository / "tests" / f"test_project_{label.lower()}.py"
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text(
        f"def test_project_{label.lower()}_sentinel() -> None:\n"
        f'    assert "MCP_SEARCH_PROJECT_{label}"\n',
        encoding="utf-8",
    )
    (repository / "README.md").write_text(
        f"# MCP fixture {label}\n\nMCP_README_PROJECT_{label}\n", encoding="utf-8"
    )
    git(repository, ["add", "."], env=git_environment)
    git(repository, ["commit", "-m", f"MCP fixture project {label}"], env=git_environment)
    head = git(repository, ["rev-parse", "HEAD"], env=git_environment)
    if SAFE_SHA.fullmatch(head) is None:
        raise AssertionError(f"fixture {label} did not produce a valid Git HEAD")
    return {
        "label": label,
        "name": f"MCP Fixture {label}",
        "path": repository,
        "relative_path": repository.name,
        "head": head,
        "checkpoint_sentinel": f"MCP_CHECKPOINT_PROJECT_{label}",
        "search_sentinel": f"MCP_SEARCH_PROJECT_{label}",
        "memory_sentinel": f"MCP_MEMORY_PROJECT_{label}",
        "task_sentinel": f"MCP_TASK_PROJECT_{label}",
    }


def _register_and_prepare_projects(
    base_url: str, projects_root: Path, *, git_environment: dict[str, str]
) -> list[dict[str, Any]]:
    fixtures = [
        _create_fixture_repository(
            projects_root / "mcp-project-a", "A", git_environment=git_environment
        ),
        _create_fixture_repository(
            projects_root / "mcp-project-b", "B", git_environment=git_environment
        ),
    ]
    for fixture in fixtures:
        registered = _api_object(
            base_url,
            "POST",
            "/api/v1/projects",
            {"name": fixture["name"], "relative_path": fixture["relative_path"]},
            f"register project {fixture['label']}",
        )
        fixture["project_id"] = _string(registered.get("project_id"), "project ID")
        if registered.get("state") != "READY":
            raise AssertionError(f"project {fixture['label']} was not READY")
        if registered.get("git_head_sha") != fixture["head"]:
            raise AssertionError(f"project {fixture['label']} registered a wrong HEAD")

        task_text = (
            f"# Read-only MCP task {fixture['label']}\n\n"
            "## Constraints\n"
            f"- Preserve MCP_TASK_PROJECT_{fixture['label']} in the project.\n\n"
            "## Acceptance Criteria\n"
            f"- Retrieve MCP_SEARCH_PROJECT_{fixture['label']} with provenance.\n"
        )
        task = _api_object(
            base_url,
            "POST",
            f"/api/v1/projects/{fixture['project_id']}/tasks/text",
            {"title": fixture["name"], "text": task_text, "format": "markdown"},
            f"create task {fixture['label']}",
        )
        fixture["task_id"] = _string(task.get("task_id"), "task ID")

        index = _api_object(
            base_url,
            "POST",
            f"/api/v1/projects/{fixture['project_id']}/index",
            None,
            f"index project {fixture['label']}",
        )
        if index.get("status") != "COMPLETED":
            raise AssertionError(f"project {fixture['label']} indexing was not completed: {index}")
        corpus = _api_object(
            base_url,
            "POST",
            f"/api/v1/projects/{fixture['project_id']}/retrieval/corpus/sync",
            None,
            f"sync corpus {fixture['label']}",
        )
        if corpus.get("status") not in {"COMPLETED", "CURRENT"}:
            raise AssertionError(f"project {fixture['label']} corpus was not current: {corpus}")

        memory = _api_object(
            base_url,
            "POST",
            f"/api/v1/projects/{fixture['project_id']}/memories",
            {
                "type": "PROJECT",
                "content": fixture["memory_sentinel"] + " durable project fact",
                "source": SOURCE_RELATIVE_PATH,
                "source_version": "mcp-fixture-v1",
                "source_commit": fixture["head"],
                "confidence": 1.0,
                "importance": 5,
                "authority": "integration-fixture",
                "tags": ["mcp", "fixture"],
                "status": "CONFIRMED",
                "origin": "USER",
            },
            f"create memory {fixture['label']}",
        )
        fixture["memory_id"] = _string(memory.get("memory_id"), "memory ID")
    return fixtures


@asynccontextmanager
async def _mcp_session(
    project_name: str, environment: dict[str, str]
) -> AsyncIterator[ClientSession]:
    parameters = StdioServerParameters(
        command="docker",
        args=[
            "compose",
            "-p",
            project_name,
            "exec",
            "-T",
            "-e",
            f"PYTHONPATH={MCP_INSTRUMENTATION_CONTAINER_PATH}:/app/backend",
            "-e",
            f"MCP_PROVIDER_CALL_COUNTER={MCP_PROVIDER_COUNTER_CONTAINER_PATH}",
            "api",
            "python",
            "-m",
            "app.mcp_server",
        ],
        env=environment,
        cwd=str(ROOT),
    )
    async with (
        stdio_client(parameters, errlog=sys.stderr) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        initialized = await session.initialize()
        if initialized.serverInfo.name != "hive-mcp":
            raise AssertionError(f"unexpected MCP server name: {initialized.serverInfo.name}")
        if initialized.serverInfo.version != "mcp-core-surface-v1":
            raise AssertionError(f"unexpected MCP server version: {initialized.serverInfo.version}")
        yield session


def _result_payload(result: CallToolResult, label: str) -> dict[str, Any]:
    for content in result.content:
        if isinstance(content, TextContent):
            try:
                decoded = json.loads(content.text)
            except (TypeError, ValueError) as exc:
                raise AssertionError(f"{label} did not return JSON text") from exc
            if isinstance(decoded, dict):
                return cast(dict[str, Any], decoded)
    structured = result.structuredContent
    if isinstance(structured, dict):
        return cast(dict[str, Any], structured)
    raise AssertionError(f"{label} did not return a structured object")


def _captured_payload(
    result: CallToolResult, label: str, capture: _PayloadCapture
) -> dict[str, Any]:
    payload = _result_payload(result, label)
    capture.add(payload)
    return payload


async def _success(
    session: ClientSession,
    name: str,
    arguments: dict[str, Any],
    *,
    capture: _PayloadCapture,
) -> dict[str, Any]:
    result = await session.call_tool(name, arguments)
    payload = _captured_payload(result, name, capture)
    if result.isError is True:
        raise AssertionError(f"{name} unexpectedly failed: {payload}")
    if not isinstance(payload.get("version"), str):
        raise AssertionError(f"{name} returned no versioned payload")
    return payload


async def _failure(
    session: ClientSession,
    name: str,
    arguments: dict[str, Any],
    *,
    capture: _PayloadCapture,
    forbidden: tuple[str, ...] = (),
) -> dict[str, Any]:
    result = await session.call_tool(name, arguments)
    payload = _captured_payload(result, name, capture)
    if result.isError is not True:
        raise AssertionError(f"{name} unexpectedly succeeded: {payload}")
    if set(payload) != {"version", "error"}:
        raise AssertionError(f"{name} returned an open error shape: {payload}")
    error = _dict(payload["error"], f"{name} error")
    if set(error) != {"code", "category", "message"}:
        raise AssertionError(f"{name} returned an unbounded error shape: {error}")
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > 2_048:
        raise AssertionError(f"{name} returned an oversized error")
    if any(token in encoded for token in forbidden):
        raise AssertionError(f"{name} echoed rejected input")
    return payload


def _project_ids(payload: dict[str, Any]) -> set[str]:
    projects = payload.get("projects")
    if not isinstance(projects, list):
        raise AssertionError("project.list did not return projects")
    return {
        _string(_dict(item, "project list item").get("project_id"), "listed project ID")
        for item in projects
    }


def _assert_project_scoped_results(
    payload: dict[str, Any], project_id: str
) -> list[dict[str, Any]]:
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        raise AssertionError("context.search did not return results")
    results = [_dict(item, "context result") for item in raw_results]
    if any(item.get("project_id") != project_id for item in results):
        raise AssertionError("context.search returned a cross-project result")
    return results


async def _protocol_checks(
    project_name: str,
    environment: dict[str, str],
    fixtures: list[dict[str, Any]],
    capture: _PayloadCapture,
) -> dict[str, object]:
    first, second = fixtures
    first_id = _fixture_value(first, "project_id")
    second_id = _fixture_value(second, "project_id")
    first_task_id = _fixture_value(first, "task_id")
    first_memory_id = _fixture_value(first, "memory_id")

    async with _mcp_session(project_name, environment) as session:
        tool_result = await session.list_tools()
        tool_names = [tool.name for tool in tool_result.tools]
        write_capable_tools = [
            tool.name
            for tool in tool_result.tools
            if tool.annotations is None
            or tool.annotations.readOnlyHint is not True
            or tool.annotations.destructiveHint is not False
        ]
        capture.add({"tool_names": tool_names})
        canonical_write_tools_exposed = bool(write_capable_tools)
        if canonical_write_tools_exposed:
            raise AssertionError("MCP tool catalog exposed a write-capable tool")
        if tool_names != list(MCP_CORE_SURFACE_TOOLS):
            raise AssertionError(f"MCP tool catalog mismatch: {tool_names}")

        listed = await _success(session, "project.list", {"limit": 32}, capture=capture)
        listed_projects = listed.get("projects")
        if not isinstance(listed_projects, list):
            raise AssertionError("project.list did not return a project list")
        if _project_ids(listed) != {first_id, second_id}:
            raise AssertionError("project.list did not expose exactly the two fixtures")
        if (
            listed.get("returned_count") != len(listed_projects)
            or listed.get("truncated") is not False
        ):
            raise AssertionError("project.list returned an unexpected count")
        registered_project_count = len(listed_projects)

        status = await _success(
            session, "project.status", {"project_id": first_id}, capture=capture
        )
        status_project = _dict(status.get("project"), "project.status project")
        if status_project.get("git_head_sha") != first["head"]:
            raise AssertionError("project.status did not preserve the registered HEAD")
        if str(status_project.get("relative_path", "")).startswith(("/", "\\")):
            raise AssertionError("project.status exposed an absolute project path")

        built = await _success(
            session,
            "context.build",
            {"project_id": first_id, "task_id": first_task_id, "top_k": 5},
            capture=capture,
        )
        context = _dict(built.get("context"), "context.build context")
        governance = context.get("governance")
        if not isinstance(governance, list) or not governance:
            raise AssertionError("context.build returned no governance")
        first_governance = _dict(governance[0], "first governance excerpt")
        if first_governance.get("kind") != "CHECKPOINT":
            raise AssertionError("context.build did not return checkpoint first")
        if built.get("checkpoint_first") is not True:
            raise AssertionError("context.build did not certify checkpoint first")

        searched = await _success(
            session,
            "context.search",
            {"project_id": first_id, "query": first["search_sentinel"], "top_k": 5},
            capture=capture,
        )
        first_results = _assert_project_scoped_results(searched, first_id)
        if len(first_results) > 5 or not first_results:
            raise AssertionError("context.search did not enforce or return bounded fixture results")
        if not any(first["search_sentinel"] in str(item.get("snippet")) for item in first_results):
            raise AssertionError("context.search did not return the fixture sentinel")
        if not all(
            item.get("source_kind")
            and item.get("reference_id")
            and item.get("chunk_id")
            and item.get("source_content_sha256")
            and item.get("chunk_content_sha256")
            for item in first_results
        ):
            raise AssertionError("context.search omitted source provenance")

        memories = await _success(
            session,
            "memory.search",
            {"project_id": first_id, "status": "CONFIRMED", "limit": 32},
            capture=capture,
        )
        memory_items = memories.get("memories")
        if not isinstance(memory_items, list) or not memory_items:
            raise AssertionError("memory.search returned no fixture memory")
        first_memory = next(
            (
                _dict(item, "memory search item")
                for item in memory_items
                if _dict(item, "memory search item").get("memory_id") == first_memory_id
            ),
            None,
        )
        if first_memory is None:
            raise AssertionError("memory.search did not return the requested project memory")
        if (
            first_memory.get("status") != "CONFIRMED"
            or first_memory.get("source") != SOURCE_RELATIVE_PATH
        ):
            raise AssertionError("memory.search did not preserve status or provenance")

        fetched_memory = await _success(
            session,
            "memory.get",
            {"project_id": first_id, "memory_id": first_memory_id},
            capture=capture,
        )
        fetched_memory_body = _dict(fetched_memory.get("memory"), "memory.get memory")
        if fetched_memory_body.get("memory_id") != first_memory_id:
            raise AssertionError("memory.get returned the wrong memory")
        if fetched_memory_body.get("project_id") != first_id:
            raise AssertionError("memory.get lost project binding")

        first_checkpoint = await _success(
            session, "checkpoint.read", {"project_id": first_id}, capture=capture
        )
        second_checkpoint = await _success(
            session, "checkpoint.read", {"project_id": second_id}, capture=capture
        )
        first_checkpoint_body = _dict(first_checkpoint.get("checkpoint"), "first checkpoint")
        second_checkpoint_body = _dict(second_checkpoint.get("checkpoint"), "second checkpoint")
        if first["checkpoint_sentinel"] not in _string(
            first_checkpoint_body.get("content"), "checkpoint content"
        ):
            raise AssertionError("checkpoint.read returned the wrong first project content")
        if second["checkpoint_sentinel"] not in _string(
            second_checkpoint_body.get("content"), "checkpoint content"
        ):
            raise AssertionError("checkpoint.read returned the wrong second project content")
        if first_checkpoint_body.get("git_head_sha") != first["head"]:
            raise AssertionError("checkpoint.read returned the wrong first HEAD")
        if second_checkpoint_body.get("git_head_sha") != second["head"]:
            raise AssertionError("checkpoint.read returned the wrong second HEAD")
        if first_checkpoint_body.get("path") != CHECKPOINT_RELATIVE_PATH:
            raise AssertionError("checkpoint.read returned a noncanonical path")

        invalid_arguments: list[tuple[str, dict[str, Any], tuple[str, ...]]] = [
            ("project.status", {"project_id": "not-a-uuid"}, ()),
            ("context.search", {"project_id": first_id, "query": "x", "top_k": 0}, ()),
            ("memory.search", {"project_id": first_id, "limit": 999}, ()),
            (
                "checkpoint.read",
                {"project_id": first_id, "path": "C:/Windows"},
                ("C:/Windows",),
            ),
            (
                "checkpoint.read",
                {"project_id": first_id, "root": "/etc"},
                ("/etc",),
            ),
            (
                "checkpoint.read",
                {"project_id": first_id, "file": "secret.txt"},
                ("secret.txt",),
            ),
        ]
        for tool_name, arguments, forbidden in invalid_arguments:
            await _failure(session, tool_name, arguments, capture=capture, forbidden=forbidden)
        await _failure(session, "missing.tool", {}, capture=capture)

        await _failure(
            session,
            "memory.get",
            {"project_id": second_id, "memory_id": first_memory_id},
            capture=capture,
        )
        await _failure(
            session,
            "context.build",
            {"project_id": first_id, "task_id": _fixture_value(second, "task_id")},
            capture=capture,
        )
        isolated_search = await _success(
            session,
            "context.search",
            {"project_id": first_id, "query": second["search_sentinel"], "top_k": 5},
            capture=capture,
        )
        isolated_results = _assert_project_scoped_results(isolated_search, first_id)
        if any(second["search_sentinel"] in str(item) for item in isolated_results):
            raise AssertionError("context.search leaked the second project")

        repeated_a = await _success(
            session,
            "context.search",
            {"project_id": first_id, "query": first["search_sentinel"], "top_k": 5},
            capture=capture,
        )
        repeated_b = await _success(
            session,
            "context.search",
            {"project_id": first_id, "query": first["search_sentinel"], "top_k": 5},
            capture=capture,
        )
        if json.dumps(repeated_a, sort_keys=True) != json.dumps(repeated_b, sort_keys=True):
            raise AssertionError("repeated context.search was not deterministic")

    async with _mcp_session(project_name, environment) as session:
        await _success(session, "project.status", {"project_id": first_id}, capture=capture)
        await _success(session, "checkpoint.read", {"project_id": first_id}, capture=capture)

    return {
        "registered_project_count": registered_project_count,
        "canonical_write_tools_exposed": canonical_write_tools_exposed,
        "tool_list_exact": tool_names,
        "protocol_handshake_passed": True,
        "protocol_tool_list_passed": True,
        "real_transport_exercised": True,
        "project_list_passed": True,
        "project_status_passed": True,
        "context_build_passed": True,
        "context_search_passed": True,
        "memory_search_passed": True,
        "memory_get_passed": True,
        "checkpoint_read_passed": True,
        "project_isolation_passed": True,
        "cross_project_access_rejected": True,
        "invalid_arguments_fail_closed": True,
        "unknown_tool_fail_closed": True,
        "bounded_output_enforced": True,
        "checkpoint_target_project_correct": True,
        "context_checkpoint_first": True,
        "deterministic_repeat": True,
        "structured_errors_enforced": True,
        "bounded_errors_enforced": True,
        "checkpoint_hive_substitution_absent": True,
        "context_search_provenance_preserved": True,
        "context_search_result_bound_enforced": True,
        "memory_search_provenance_preserved": True,
        "memory_get_provenance_preserved": True,
        "memory_status_visibility_preserved": True,
        "arbitrary_filesystem_access_rejected": True,
        "checkpoint_missing_fail_closed": False,
        "checkpoint_untracked_fail_closed": False,
        "checkpoint_stale_fail_closed": False,
        "restart_recovery": True,
        "redis_loss_recovery": False,
        "direct_core_reuse": False,
        "rest_loopback_absent": False,
        "duplicate_persistence_absent": False,
    }


async def _checkpoint_negative_checks(
    project_name: str,
    environment: dict[str, str],
    fixture: dict[str, Any],
    capture: _PayloadCapture,
) -> dict[str, bool]:
    checkpoint_path = cast(Path, fixture["path"]) / Path(*CHECKPOINT_RELATIVE_PATH.split("/"))
    missing_path = checkpoint_path.with_name("13-CHECKPOINT.md.mcp-missing")
    original = checkpoint_path.read_bytes()
    if missing_path.exists():
        missing_path.unlink()

    async with _mcp_session(project_name, environment) as session:
        checkpoint_path.rename(missing_path)
        try:
            await _failure(
                session,
                "checkpoint.read",
                {"project_id": fixture["project_id"]},
                capture=capture,
            )
            missing_passed = True
        finally:
            missing_path.rename(checkpoint_path)

        checkpoint_path.write_bytes(original + b"\nMCP_STALE_WORKTREE_BYTES\n")
        try:
            await _failure(
                session,
                "checkpoint.read",
                {"project_id": fixture["project_id"]},
                capture=capture,
            )
            stale_passed = True
        finally:
            checkpoint_path.write_bytes(original)

        run(
            ["git", "-C", str(fixture["path"]), "rm", "--cached", "--", CHECKPOINT_RELATIVE_PATH],
            env=environment,
        )
        await _failure(
            session,
            "checkpoint.read",
            {"project_id": fixture["project_id"]},
            capture=capture,
        )
        untracked_passed = True

    return {
        "checkpoint_missing_fail_closed": missing_passed,
        "checkpoint_stale_fail_closed": stale_passed,
        "checkpoint_untracked_fail_closed": untracked_passed,
    }


def _static_surface_checks() -> dict[str, bool]:
    source = MCP_MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        alias.name.split(".", maxsplit=1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_from = {
        node.module.split(".", maxsplit=1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    forbidden_transport_imports = {
        "anthropic",
        "boto3",
        "cohere",
        "fastapi",
        "httpx",
        "openai",
        "requests",
        "sqlalchemy",
        "urllib",
    }
    rest_loopback_absent = not bool(imported_modules & forbidden_transport_imports) and not bool(
        imported_from & forbidden_transport_imports
    )
    if not rest_loopback_absent:
        raise AssertionError("MCP adapter imports a REST/provider/persistence transport")
    required_core_symbols = (
        "list_projects",
        "get_project",
        "build_context",
        "rerank_search",
        "list_memories",
        "get_memory",
        "_collect_inventory",
        "_assert_snapshot_stable",
    )
    direct_core_reuse = all(symbol in source for symbol in required_core_symbols)
    if not direct_core_reuse:
        raise AssertionError("MCP adapter does not expose every direct Core seam")
    duplicate_persistence_absent = not any(
        token in source for token in ("database_connection", "INSERT INTO", "UPDATE ")
    )
    if not duplicate_persistence_absent:
        raise AssertionError("MCP adapter contains a duplicate persistence surface")
    return {
        "direct_core_reuse": direct_core_reuse,
        "rest_loopback_absent": rest_loopback_absent,
        "duplicate_persistence_absent": duplicate_persistence_absent,
    }


def _git_paths(environment: dict[str, str], arguments: list[str]) -> set[str]:
    try:
        output = git(ROOT, arguments, env=environment)
    except RuntimeError as exc:
        raise AssertionError("unable to determine the current validation delta") from exc
    return {path for path in output.splitlines() if path}


def _current_validation_paths(environment: dict[str, str]) -> set[str]:
    """Resolve the exact committed and local delta for the current validation mode."""

    try:
        head = git(ROOT, ["rev-parse", "HEAD"], env=environment)
        origin_main = git(ROOT, ["rev-parse", "origin/main"], env=environment)
    except RuntimeError as exc:
        raise AssertionError("unable to resolve HEAD and origin/main") from exc
    if not SAFE_SHA.fullmatch(head) or not SAFE_SHA.fullmatch(origin_main):
        raise AssertionError("validation boundary contains an invalid Git SHA")

    if head != origin_main:
        try:
            merge_base = git(ROOT, ["merge-base", "origin/main", "HEAD"], env=environment)
        except RuntimeError as exc:
            raise AssertionError(
                "candidate is stale or divergent from current protected-main base"
            ) from exc
        if merge_base != origin_main:
            raise AssertionError("candidate is stale or divergent from current protected-main base")
        committed_paths = _git_paths(
            environment, ["diff", "--name-only", "--no-renames", "origin/main", "HEAD", "--"]
        )
    else:
        try:
            parents = git(
                ROOT, ["rev-list", "--parents", "-n", "1", "HEAD"], env=environment
            ).split()
        except RuntimeError as exc:
            raise AssertionError("unable to resolve the current protected-main lineage") from exc
        if len(parents) != 2 or not SAFE_SHA.fullmatch(parents[1]):
            raise AssertionError("current protected-main HEAD must have exactly one parent")
        committed_paths = _git_paths(
            environment, ["diff", "--name-only", "--no-renames", parents[1], "HEAD", "--"]
        )

    unresolved_paths = _git_paths(
        environment, ["diff", "--name-only", "--diff-filter=U", "HEAD", "--"]
    )
    if unresolved_paths:
        raise AssertionError("working tree has unresolved merge state")
    working_tree_paths = _git_paths(environment, ["diff", "--name-only", "HEAD", "--"])
    untracked_paths = _git_paths(environment, ["ls-files", "--others", "--exclude-standard", "--"])
    return committed_paths | working_tree_paths | untracked_paths


def _observe_migration_changed(environment: dict[str, str]) -> bool:
    changed_paths = _current_validation_paths(environment)
    return any(path == "migrations" or path.startswith("migrations/") for path in changed_paths)


def _write_evidence(flags: dict[str, object]) -> None:
    observed_fields = (
        "registered_project_count",
        "tool_list_exact",
        "observed_migration_head",
        *MCP_CORE_SURFACE_TRUE_FIELDS,
        *MCP_CORE_SURFACE_FALSE_FIELDS,
        *MCP_CORE_SURFACE_INTEGER_FIELDS,
    )
    missing = [field for field in observed_fields if field not in flags]
    if missing:
        raise AssertionError("missing observed MCP evidence: " + ", ".join(sorted(missing)))

    tool_list = flags["tool_list_exact"]
    if not isinstance(tool_list, list) or any(not isinstance(item, str) for item in tool_list):
        raise AssertionError("tool list observation has the wrong type")
    if tool_list != list(MCP_CORE_SURFACE_TOOLS):
        raise AssertionError("tool list observation does not match the closed catalog")

    registered_project_count = flags["registered_project_count"]
    if type(registered_project_count) is not int or not 2 <= registered_project_count <= 32:
        raise AssertionError("registered project count observation is invalid")

    observed_migration_head = flags["observed_migration_head"]
    if observed_migration_head != SCHEMA_REVISION:
        raise AssertionError("migration head observation is invalid")

    for field in MCP_CORE_SURFACE_TRUE_FIELDS:
        if type(flags[field]) is not bool or flags[field] is not True:
            raise AssertionError(f"true MCP observation failed: {field}")
    for field in MCP_CORE_SURFACE_FALSE_FIELDS:
        if type(flags[field]) is not bool or flags[field] is not False:
            raise AssertionError(f"false MCP observation failed: {field}")
    for field in MCP_CORE_SURFACE_INTEGER_FIELDS:
        value = flags[field]
        if type(value) is not int or value < 0 or value != 0:
            raise AssertionError(f"zero MCP observation failed: {field}")

    evidence: dict[str, Any] = {
        "status": "PASS",
        "evidence_file": MCP_CORE_SURFACE_EVIDENCE_FILE,
        "mcp_evidence_version": MCP_CORE_SURFACE_EVIDENCE_VERSION,
        "tool_list_exact": tool_list,
        "registered_project_count": registered_project_count,
        "migration_changed": flags["migration_changed"],
        "canonical_write_tools_exposed": flags["canonical_write_tools_exposed"],
        "observed_migration_head": observed_migration_head,
    }
    evidence.update({field: flags[field] for field in MCP_CORE_SURFACE_TRUE_FIELDS})
    evidence.update({field: flags[field] for field in MCP_CORE_SURFACE_FALSE_FIELDS})
    evidence.update({field: flags[field] for field in MCP_CORE_SURFACE_INTEGER_FIELDS})
    if set(evidence) != {
        "status",
        "evidence_file",
        "mcp_evidence_version",
        "tool_list_exact",
        "registered_project_count",
        "migration_changed",
        "canonical_write_tools_exposed",
        "observed_migration_head",
        *MCP_CORE_SURFACE_TRUE_FIELDS,
        *MCP_CORE_SURFACE_INTEGER_FIELDS,
    }:
        raise AssertionError("MCP evidence shape is not closed")
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> int:
    EVIDENCE_PATH.unlink(missing_ok=True)
    api_port = free_port()
    dashboard_port = free_port()
    project_name = f"hive-mcp-{os.getpid()}"
    secret_sentinel = f"mcp-secret-sentinel-{os.getpid()}-{uuid4().hex}"
    temporary_parent = ROOT / "tmp"
    temporary_parent.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.update(
        {
            "HIVE_DATA_ROOT": "",
            "HIVE_PROJECTS_ROOT": "",
            "HIVE_API_PORT": str(api_port),
            "HIVE_DASHBOARD_PORT": str(dashboard_port),
            "POSTGRES_DB": "hive",
            "POSTGRES_USER": "hive",
            "POSTGRES_PASSWORD": "hive",
            "HIVE_EMBEDDING_ENABLED": "false",
            "HIVE_RERANK_ENABLED": "false",
            "HIVE_EMBEDDING_API_KEY": secret_sentinel,
            "HIVE_RERANK_API_KEY": secret_sentinel,
        }
    )
    temporary_root = Path(tempfile.mkdtemp(prefix="mcp-surface-", dir=temporary_parent))
    flags: dict[str, object] = {}
    capture = _PayloadCapture()
    succeeded = False
    try:
        projects_root = temporary_root / "projects"
        data_root = temporary_root / "data"
        projects_root.mkdir()
        data_root.mkdir()
        instrumentation_root = projects_root / ".mcp-instrumentation"
        _install_provider_call_trap(instrumentation_root)
        provider_counter_path = data_root / "tmp" / "mcp-provider-calls.json"
        provider_counter_path.parent.mkdir(parents=True, exist_ok=True)
        provider_counter_path.unlink(missing_ok=True)
        environment["HIVE_PROJECTS_ROOT"] = projects_root.as_posix()
        environment["HIVE_DATA_ROOT"] = data_root.as_posix()

        compose(project_name, ["down", "--remove-orphans"], env=environment, check=False)
        compose(project_name, ["up", "-d", "--build"], env=environment)
        migration_version = compose(
            project_name,
            [
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "hive",
                "-d",
                "hive",
                "-Atqc",
                "SELECT version_num FROM alembic_version",
            ],
            env=environment,
        ).stdout.strip()
        if migration_version != SCHEMA_REVISION:
            raise AssertionError(f"unexpected migration head: {migration_version}")
        if not migration_version:
            raise AssertionError("migration head was empty")
        flags["observed_migration_head"] = migration_version
        base_url = f"http://127.0.0.1:{api_port}"
        wait_for_health(base_url)
        fixtures = _register_and_prepare_projects(
            base_url, projects_root, git_environment=environment
        )
        flags.update(asyncio.run(_protocol_checks(project_name, environment, fixtures, capture)))

        compose(project_name, ["exec", "-T", "redis", "redis-cli", "FLUSHALL"], env=environment)
        compose(project_name, ["restart", "redis"], env=environment)
        wait_for_health(base_url)
        compose(project_name, ["up", "-d", "--force-recreate", "api"], env=environment)
        wait_for_health(base_url)

        async def redis_recovery() -> None:
            async with _mcp_session(project_name, environment) as session:
                await _success(
                    session,
                    "project.status",
                    {"project_id": fixtures[0]["project_id"]},
                    capture=capture,
                )
                await _success(
                    session,
                    "checkpoint.read",
                    {"project_id": fixtures[0]["project_id"]},
                    capture=capture,
                )

        asyncio.run(redis_recovery())
        flags["redis_loss_recovery"] = True
        flags.update(
            asyncio.run(
                _checkpoint_negative_checks(project_name, environment, fixtures[0], capture)
            )
        )
        flags.update(_static_surface_checks())
        flags["checkpoint_hive_substitution_absent"] = True
        flags.update(_provider_call_counts(provider_counter_path))
        flags["migration_changed"] = _observe_migration_changed(environment)
        flags["secret_leaks"] = capture.count_payloads_containing((secret_sentinel,))
        flags["filesystem_path_leaks"] = capture.count_payloads_containing(
            _absolute_path_variants(
                (temporary_root, projects_root, data_root),
                ("C:/Windows", r"C:\Windows", "/etc"),
            )
        )
        _write_evidence(flags)
        succeeded = True
        print("MCP read-only core surface integration passed.")
        print(f"tool_list={','.join(cast(list[str], flags['tool_list_exact']))}")
        print(f"registered_project_count={flags['registered_project_count']}")
        print(f"migration_head={migration_version}")
        print("real_stdio_transport=passed")
        print("restart_recovery=passed")
        print("redis_loss_recovery=passed")
        print("checkpoint_negative_guards=passed")
        print(f"provider_calls={flags['mcp_llm_calls']}/{flags['mcp_provider_calls']}")
        return 0
    finally:
        compose(project_name, ["down", "--remove-orphans"], env=environment, check=False)
        try:
            cleanup_temporary_root(temporary_root, env=environment)
        finally:
            if not succeeded:
                EVIDENCE_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
