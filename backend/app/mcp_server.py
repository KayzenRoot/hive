"""The bounded, read-only MCP surface for HIVE.

This module is deliberately a thin protocol adapter.  It owns MCP argument
validation and response/error envelopes; all project, context, retrieval,
memory, and checkpoint decisions remain in the existing HIVE Core services.
The executable entry point uses the official SDK stdio transport only.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any, cast
from uuid import UUID

import anyio
import mcp.types as types
import psycopg
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from .config import Settings, get_settings
from .context_manager import (
    ContextBoundsError,
    ContextCapsule,
    ContextGovernanceError,
    ContextManagerError,
    ContextProjectNotFoundError,
    ContextRetrievalError,
    ContextStaleError,
    _checkpoint_sections,
    _parse_markdown_sections,
    _tracked_governance_file,
    build_context,
)
from .memory import (
    MemoryNotFoundError,
    MemoryProjectNotFoundError,
    MemoryResponse,
    MemoryStatus,
    get_memory,
    list_memories,
)
from .registry import (
    ProjectPathError,
    ProjectResponse,
    ProjectState,
    get_project,
    list_projects,
    normalize_project_path,
)
from .repository_indexer import (
    RepositoryIndexingError,
    _assert_snapshot_stable,
    _collect_inventory,
)
from .reranking import RerankError, RerankRequest, RerankResponse, rerank_search
from .retrieval import RetrievalProjectNotFoundError, RetrievalQueryError
from .semantic_retrieval import SemanticError
from .task_intake import ExtractionNotReadyError, TaskNotFoundError

MCP_SERVER_NAME = "hive-mcp"
MCP_SERVER_VERSION = "mcp-core-surface-v1"
MCP_ERROR_VERSION = "mcp-error-v1"
MCP_PROTOCOL_TRANSPORT = "stdio"

TOOL_NAMES: tuple[str, ...] = (
    "project.list",
    "project.status",
    "context.build",
    "context.search",
    "memory.search",
    "memory.get",
    "checkpoint.read",
)

MAX_PROJECTS = 32
MAX_LANGUAGE_STACK_ENTRIES = 16
MAX_LANGUAGE_STACK_ITEM_CHARS = 64
MAX_BRANCH_CHARS = 128
MAX_QUERY_CHARS = 512
MAX_SEARCH_TOP_K = 10
MAX_MEMORY_LIMIT = 32
MAX_MEMORY_CONTENT_CHARS = 2_048
# Historical checkpoint-content cap. It rejected the WO-019-P candidate of
# 30,812 bytes even though the tool contract is to return the complete
# tracked checkpoint. Do not restore this as the live admission limit.
LEGACY_MAX_CHECKPOINT_BYTES = 30_000
WO019P_CANDIDATE_CHECKPOINT_BYTES = 30_812
# Checkpoint-specific content bound. 48 KiB admits the WO-019-P candidate and
# remaining V0.1 COMPLETED growth while leaving at least 16 KiB of envelope
# headroom under the unchanged 64 KiB transport guard. Oversized success
# still fails closed in `_encode_payload` before it can escape.
MAX_CHECKPOINT_BYTES = 48 * 1024
MAX_CHECKPOINT_SECTIONS = 16
MAX_TOOL_OUTPUT_BYTES = 64 * 1024
MAX_ERROR_BYTES = 2_048
MAX_UUID_TEXT_CHARS = 64
MAX_PATH_CHARS = 1_024

_UUID_PATTERN = r"^[0-9a-fA-F-]{1,64}$"
_SAFE_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40,64}$")
_ABSOLUTE_PATH_PATTERN = re.compile(r"^(?:[A-Za-z]:[\\/]|/|\\\\)")
_PATH_KEYS = frozenset(
    {
        "path",
        "relative_path",
        "file_path",
        "resolved_path",
        "project_root",
        "root",
        "file",
        "original_filename",
        "source",
    }
)


class MCPDispatchError(Exception):
    """A stable, bounded error safe to return through the MCP protocol."""

    def __init__(self, code: str, category: str, message: str) -> None:
        self.code = code
        self.category = category
        self.message = message
        super().__init__(code)


def _object_schema(
    properties: dict[str, dict[str, Any]], required: tuple[str, ...] = ()
) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": list(required),
    }


_UUID_SCHEMA: dict[str, Any] = {
    "type": "string",
    "minLength": 1,
    "maxLength": MAX_UUID_TEXT_CHARS,
    "pattern": _UUID_PATTERN,
}
_LIMIT_SCHEMA: dict[str, Any] = {"type": "integer", "minimum": 1, "maximum": MAX_MEMORY_LIMIT}
_TOP_K_SCHEMA: dict[str, Any] = {"type": "integer", "minimum": 1, "maximum": MAX_SEARCH_TOP_K}
_SUCCESS_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["version"],
    "properties": {"version": {"type": "string", "minLength": 1}},
    "additionalProperties": True,
}
_READ_ONLY_ANNOTATIONS = types.ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

TOOL_DEFINITIONS: tuple[types.Tool, ...] = (
    types.Tool(
        name="project.list",
        description="List registered HIVE projects in deterministic bounded order.",
        inputSchema=_object_schema(
            {
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_PROJECTS,
                    "default": MAX_PROJECTS,
                }
            }
        ),
        outputSchema=_SUCCESS_OUTPUT_SCHEMA,
        annotations=_READ_ONLY_ANNOTATIONS,
    ),
    types.Tool(
        name="project.status",
        description="Read one registered HIVE project status and Git identity.",
        inputSchema=_object_schema({"project_id": _UUID_SCHEMA}, ("project_id",)),
        outputSchema=_SUCCESS_OUTPUT_SCHEMA,
        annotations=_READ_ONLY_ANNOTATIONS,
    ),
    types.Tool(
        name="context.build",
        description="Build a bounded project/task context capsule through HIVE Core.",
        inputSchema=_object_schema(
            {
                "project_id": _UUID_SCHEMA,
                "task_id": _UUID_SCHEMA,
                "top_k": _TOP_K_SCHEMA,
                "disclosure_level": {
                    "type": "string",
                    "enum": ["L0", "L1", "L2", "L3", "L4", "L5"],
                },
            },
            ("project_id", "task_id"),
        ),
        outputSchema=_SUCCESS_OUTPUT_SCHEMA,
        annotations=_READ_ONLY_ANNOTATIONS,
    ),
    types.Tool(
        name="context.search",
        description="Search the current project retrieval seam with provenance.",
        inputSchema=_object_schema(
            {
                "project_id": _UUID_SCHEMA,
                "query": {"type": "string", "minLength": 1, "maxLength": MAX_QUERY_CHARS},
                "top_k": _TOP_K_SCHEMA,
            },
            ("project_id", "query"),
        ),
        outputSchema=_SUCCESS_OUTPUT_SCHEMA,
        annotations=_READ_ONLY_ANNOTATIONS,
    ),
    types.Tool(
        name="memory.search",
        description="Read bounded project-scoped memories and lifecycle provenance.",
        inputSchema=_object_schema(
            {
                "project_id": _UUID_SCHEMA,
                "status": {
                    "type": "string",
                    "enum": [
                        "OBSERVATION",
                        "INFERRED",
                        "PROPOSED",
                        "CONFIRMED",
                        "CANONICAL",
                        "DEPRECATED",
                    ],
                },
                "limit": _LIMIT_SCHEMA,
            },
            ("project_id",),
        ),
        outputSchema=_SUCCESS_OUTPUT_SCHEMA,
        annotations=_READ_ONLY_ANNOTATIONS,
    ),
    types.Tool(
        name="memory.get",
        description="Read one project-scoped memory record with provenance fields.",
        inputSchema=_object_schema(
            {"project_id": _UUID_SCHEMA, "memory_id": _UUID_SCHEMA},
            ("project_id", "memory_id"),
        ),
        outputSchema=_SUCCESS_OUTPUT_SCHEMA,
        annotations=_READ_ONLY_ANNOTATIONS,
    ),
    types.Tool(
        name="checkpoint.read",
        description="Read the complete current tracked checkpoint for one project.",
        inputSchema=_object_schema({"project_id": _UUID_SCHEMA}, ("project_id",)),
        outputSchema=_SUCCESS_OUTPUT_SCHEMA,
        annotations=_READ_ONLY_ANNOTATIONS,
    ),
)


def _invalid_arguments() -> MCPDispatchError:
    return MCPDispatchError("invalid_arguments", "input", "arguments are invalid")


def _require_exact_keys(
    arguments: Mapping[str, object] | None,
    allowed: frozenset[str],
    required: frozenset[str],
) -> dict[str, object]:
    if not isinstance(arguments, dict):
        raise _invalid_arguments()
    if set(arguments) - allowed or required - set(arguments):
        raise _invalid_arguments()
    return dict(arguments)


def _string_argument(
    arguments: Mapping[str, object], name: str, *, maximum: int, optional: bool = False
) -> str | None:
    if name not in arguments:
        if optional:
            return None
        raise _invalid_arguments()
    value = arguments[name]
    if not isinstance(value, str):
        raise _invalid_arguments()
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise _invalid_arguments()
    return normalized


def _uuid_argument(arguments: Mapping[str, object], name: str) -> UUID:
    value = _string_argument(arguments, name, maximum=MAX_UUID_TEXT_CHARS)
    assert value is not None
    try:
        return UUID(value)
    except (AttributeError, ValueError):
        raise _invalid_arguments() from None


def _integer_argument(
    arguments: Mapping[str, object],
    name: str,
    *,
    minimum: int,
    maximum: int,
    default: int | None = None,
) -> int:
    if name not in arguments:
        if default is not None:
            return default
        raise _invalid_arguments()
    value = arguments[name]
    if type(value) is not int:
        raise _invalid_arguments()
    if not minimum <= value <= maximum:
        raise _invalid_arguments()
    return value


def _parse_arguments(tool_name: str, arguments: Mapping[str, object] | None) -> dict[str, object]:
    if tool_name == "project.list":
        values = _require_exact_keys(arguments, frozenset({"limit"}), frozenset())
        return {
            "limit": _integer_argument(
                values, "limit", minimum=1, maximum=MAX_PROJECTS, default=MAX_PROJECTS
            )
        }
    if tool_name == "project.status":
        values = _require_exact_keys(
            arguments, frozenset({"project_id"}), frozenset({"project_id"})
        )
        return {"project_id": _uuid_argument(values, "project_id")}
    if tool_name == "context.build":
        values = _require_exact_keys(
            arguments,
            frozenset({"project_id", "task_id", "top_k", "disclosure_level"}),
            frozenset({"project_id", "task_id"}),
        )
        disclosure_level = _string_argument(values, "disclosure_level", maximum=2, optional=True)
        if disclosure_level is not None and disclosure_level not in {
            f"L{index}" for index in range(6)
        }:
            raise _invalid_arguments()
        return {
            "project_id": _uuid_argument(values, "project_id"),
            "task_id": _uuid_argument(values, "task_id"),
            "top_k": _integer_argument(
                values, "top_k", minimum=1, maximum=MAX_SEARCH_TOP_K, default=5
            ),
            "disclosure_level": disclosure_level,
        }
    if tool_name == "context.search":
        values = _require_exact_keys(
            arguments,
            frozenset({"project_id", "query", "top_k"}),
            frozenset({"project_id", "query"}),
        )
        query = _string_argument(values, "query", maximum=MAX_QUERY_CHARS)
        assert query is not None
        return {
            "project_id": _uuid_argument(values, "project_id"),
            "query": query,
            "top_k": _integer_argument(
                values, "top_k", minimum=1, maximum=MAX_SEARCH_TOP_K, default=5
            ),
        }
    if tool_name == "memory.search":
        values = _require_exact_keys(
            arguments,
            frozenset({"project_id", "status", "limit"}),
            frozenset({"project_id"}),
        )
        status = _string_argument(values, "status", maximum=16, optional=True)
        if status is not None and status not in {item.value for item in MemoryStatus}:
            raise _invalid_arguments()
        return {
            "project_id": _uuid_argument(values, "project_id"),
            "status": MemoryStatus(status) if status is not None else None,
            "limit": _integer_argument(
                values, "limit", minimum=1, maximum=MAX_MEMORY_LIMIT, default=MAX_MEMORY_LIMIT
            ),
        }
    if tool_name == "memory.get":
        values = _require_exact_keys(
            arguments,
            frozenset({"project_id", "memory_id"}),
            frozenset({"project_id", "memory_id"}),
        )
        return {
            "project_id": _uuid_argument(values, "project_id"),
            "memory_id": _uuid_argument(values, "memory_id"),
        }
    if tool_name == "checkpoint.read":
        values = _require_exact_keys(
            arguments, frozenset({"project_id"}), frozenset({"project_id"})
        )
        return {"project_id": _uuid_argument(values, "project_id")}
    raise MCPDispatchError("unknown_tool", "protocol", "the requested tool is not exposed")


def _safe_relative_path(value: object) -> str:
    if not isinstance(value, str) or not 0 < len(value) <= MAX_PATH_CHARS:
        raise MCPDispatchError("unsafe_core_output", "security", "core output is unsafe")
    if (
        "\\" in value
        or value.startswith("/")
        or "\x00" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
        or PurePosixPath(value).is_absolute()
    ):
        raise MCPDispatchError("unsafe_core_output", "security", "core output is unsafe")
    return value


def _safe_optional_text(value: object, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > maximum or "\x00" in value:
        raise MCPDispatchError("unsafe_core_output", "security", "core output is unsafe")
    return value


def _safe_head(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or _SAFE_SHA_PATTERN.fullmatch(value) is None:
        raise MCPDispatchError("unsafe_core_output", "security", "core output is unsafe")
    return value.lower()


def _project_summary(project: ProjectResponse) -> dict[str, object]:
    return {
        "project_id": str(project.project_id),
        "name": _safe_optional_text(project.name, 120) or "",
        "relative_path": _safe_relative_path(project.relative_path),
        "git_branch": _safe_optional_text(project.git_branch, MAX_BRANCH_CHARS),
        "git_head_sha": _safe_head(project.git_head_sha),
        "detached_head": project.detached_head,
        "repository_accessible": project.repository_accessible,
        "working_tree_clean": project.working_tree_clean,
        "language_stack": [
            _safe_optional_text(item, MAX_LANGUAGE_STACK_ITEM_CHARS) or ""
            for item in project.language_stack[:MAX_LANGUAGE_STACK_ENTRIES]
        ],
        "state": project.state.value,
    }


def _memory_view(memory: MemoryResponse) -> dict[str, object]:
    data = cast(dict[str, object], memory.model_dump(mode="json"))
    content = data.get("content")
    if not isinstance(content, str):
        raise MCPDispatchError("unsafe_core_output", "security", "core output is unsafe")
    data["content_characters"] = len(content)
    data["content_truncated"] = len(content) > MAX_MEMORY_CONTENT_CHARS
    data["content"] = content[:MAX_MEMORY_CONTENT_CHARS]
    return data


def _context_search_view(response: RerankResponse) -> dict[str, object]:
    if response.project_id is None or response.candidate_pool > MAX_SEARCH_TOP_K:
        raise MCPDispatchError("output_bound_exceeded", "bounds", "tool output exceeds its bound")
    if len(response.results) > MAX_SEARCH_TOP_K:
        raise MCPDispatchError("output_bound_exceeded", "bounds", "tool output exceeds its bound")
    results: list[dict[str, object]] = []
    for candidate in response.results:
        item = cast(dict[str, object], candidate.model_dump(mode="json"))
        snippet = item.get("snippet")
        if not isinstance(snippet, str):
            raise MCPDispatchError("unsafe_core_output", "security", "core output is unsafe")
        item["snippet_characters"] = len(snippet)
        item["snippet_truncated"] = len(snippet) > 640
        item["snippet"] = snippet[:640]
        results.append(item)
    return {
        "version": "mcp-context-search-v1",
        "project_id": str(response.project_id),
        "query": response.query,
        "normalized_query": response.normalized_query,
        "top_k": response.top_k,
        "candidate_pool": response.candidate_pool,
        "hybrid_state": response.hybrid_state,
        "semantic_state": response.semantic_state.value,
        "rerank_state": response.rerank_state.value,
        "fallback_reason": response.fallback_reason,
        "results": results,
    }


def _context_build_view(capsule: ContextCapsule) -> dict[str, object]:
    payload = cast(dict[str, object], capsule.model_dump(mode="json"))
    governance = payload.get("governance")
    if not isinstance(governance, list) or not governance or not isinstance(governance[0], dict):
        raise MCPDispatchError("checkpoint_not_first", "core", "context checkpoint is unavailable")
    if governance[0].get("kind") != "CHECKPOINT":
        raise MCPDispatchError("checkpoint_not_first", "core", "context checkpoint is unavailable")
    return {
        "version": "mcp-context-build-v1",
        "project_id": str(capsule.project.project_id),
        "task_id": str(capsule.task.task_id),
        "checkpoint_first": True,
        "context": payload,
    }


def _checkpoint_view(settings: Settings, project_id: UUID) -> dict[str, object]:
    project = get_project(settings, project_id)
    if project is None:
        raise ContextProjectNotFoundError("project not found")
    if project.state not in {ProjectState.READY, ProjectState.ACTIVE}:
        raise ContextStaleError("project_state_unusable")
    if not project.repository_accessible or not project.git_head_sha:
        raise ContextStaleError("project_repository_unavailable")
    try:
        _, project_path = normalize_project_path(project.relative_path, settings)
        snapshot = _collect_inventory(settings, project_path)
    except (ProjectPathError, RepositoryIndexingError, OSError, RuntimeError) as exc:
        raise ContextStaleError("repository_snapshot_unavailable") from exc
    if snapshot.repository_head_sha.lower() != project.git_head_sha.lower():
        raise ContextStaleError("project_head_stale")
    if any(entry.git_status != "CLEAN" for entry in snapshot.files):
        raise ContextStaleError("project_worktree_dirty")
    entry = _tracked_governance_file(snapshot, "CHECKPOINT", "docs/project-brain/13-CHECKPOINT.md")
    _assert_snapshot_stable(settings, snapshot)
    try:
        content = entry.source.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContextGovernanceError("checkpoint_not_utf8") from exc
    if len(content.encode("utf-8")) > MAX_CHECKPOINT_BYTES:
        raise ContextBoundsError("checkpoint_response_bound_exceeded")
    sections = _checkpoint_sections(_parse_markdown_sections(content))
    if len(sections) > MAX_CHECKPOINT_SECTIONS:
        raise ContextBoundsError("checkpoint_section_bound_exceeded")
    return {
        "version": "mcp-checkpoint-read-v1",
        "project_id": str(project_id),
        "checkpoint": {
            "path": entry.path,
            "git_head_sha": snapshot.repository_head_sha,
            "registered_head_sha": project.git_head_sha,
            "git_blob_sha": entry.git_blob_sha,
            "source_content_sha256": entry.content_sha256,
            "section_count": len(sections),
            "sections": [
                {
                    "heading": section.heading,
                    "start_line": section.start_line,
                    "end_line": section.end_line,
                    "start_char": section.start_char,
                    "end_char": section.end_char,
                }
                for section in sections
            ],
            "content_characters": len(content),
            "content": content,
        },
    }


def dispatch_tool(
    settings: Settings, tool_name: str, arguments: Mapping[str, object] | None = None
) -> dict[str, object]:
    """Dispatch one validated MCP call through the existing HIVE Core seams."""

    if tool_name not in TOOL_NAMES:
        raise MCPDispatchError("unknown_tool", "protocol", "the requested tool is not exposed")
    parsed = _parse_arguments(tool_name, arguments)
    if tool_name == "project.list":
        projects = list_projects(settings)
        if len(projects) > MAX_PROJECTS:
            raise MCPDispatchError(
                "output_bound_exceeded", "bounds", "tool output exceeds its bound"
            )
        limit = cast(int, parsed["limit"])
        return {
            "version": "mcp-project-list-v1",
            "limit": limit,
            "returned_count": min(limit, len(projects)),
            "truncated": len(projects) > limit,
            "projects": [_project_summary(project) for project in projects[:limit]],
        }
    if tool_name == "project.status":
        project = get_project(settings, cast(UUID, parsed["project_id"]))
        if project is None:
            raise ContextProjectNotFoundError("project not found")
        return {"version": "mcp-project-status-v1", "project": _project_summary(project)}
    if tool_name == "context.build":
        capsule = build_context(
            settings,
            cast(UUID, parsed["project_id"]),
            cast(UUID, parsed["task_id"]),
            top_k=cast(int, parsed["top_k"]),
            disclosure_level=cast(str | None, parsed["disclosure_level"]),
        )
        return _context_build_view(capsule)
    if tool_name == "context.search":
        response = rerank_search(
            settings,
            cast(UUID, parsed["project_id"]),
            RerankRequest(
                query=cast(str, parsed["query"]),
                top_k=cast(int, parsed["top_k"]),
                candidate_pool=cast(int, parsed["top_k"]),
                strict_rerank=False,
            ),
        )
        return _context_search_view(response)
    if tool_name == "memory.search":
        memories = list_memories(
            settings,
            cast(UUID, parsed["project_id"]),
            cast(MemoryStatus | None, parsed["status"]),
            cast(int, parsed["limit"]),
        )
        if len(memories) > cast(int, parsed["limit"]):
            raise MCPDispatchError(
                "output_bound_exceeded", "bounds", "tool output exceeds its bound"
            )
        return {
            "version": "mcp-memory-search-v1",
            "project_id": str(cast(UUID, parsed["project_id"])),
            "status": (
                cast(MemoryStatus, parsed["status"]).value if parsed["status"] is not None else None
            ),
            "limit": cast(int, parsed["limit"]),
            "returned_count": len(memories),
            "memories": [_memory_view(memory) for memory in memories],
        }
    if tool_name == "memory.get":
        memory = get_memory(
            settings,
            cast(UUID, parsed["project_id"]),
            cast(UUID, parsed["memory_id"]),
        )
        return {
            "version": "mcp-memory-get-v1",
            "project_id": str(cast(UUID, parsed["project_id"])),
            "memory": _memory_view(memory),
        }
    return _checkpoint_view(settings, cast(UUID, parsed["project_id"]))


def _error_for_exception(exc: Exception) -> MCPDispatchError:
    if isinstance(exc, MCPDispatchError):
        return exc
    if isinstance(
        exc,
        ContextProjectNotFoundError | RetrievalProjectNotFoundError | MemoryProjectNotFoundError,
    ):
        return MCPDispatchError("project_not_found", "not_found", "project not found")
    if isinstance(exc, TaskNotFoundError | MemoryNotFoundError):
        return MCPDispatchError("resource_not_found", "not_found", "resource not found")
    if isinstance(exc, ContextStaleError | ContextGovernanceError | RepositoryIndexingError):
        return MCPDispatchError("source_not_current", "stale", "project source is not current")
    if isinstance(exc, ContextBoundsError):
        return MCPDispatchError("output_bound_exceeded", "bounds", "tool output exceeds its bound")
    if isinstance(exc, ContextManagerError | ContextRetrievalError | RerankError | SemanticError):
        return MCPDispatchError("core_operation_failed", "core", "core operation failed closed")
    if isinstance(exc, ExtractionNotReadyError):
        return MCPDispatchError("resource_not_ready", "stale", "resource is not ready")
    if isinstance(exc, RetrievalQueryError | ValueError | TypeError):
        return _invalid_arguments()
    if isinstance(exc, psycopg.Error):
        return MCPDispatchError(
            "database_unavailable", "unavailable", "durable store is unavailable"
        )
    return MCPDispatchError("core_operation_failed", "internal", "core operation failed closed")


def _assert_no_absolute_paths(value: object, key: str = "") -> None:
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            _assert_no_absolute_paths(child_value, str(child_key).casefold())
    elif isinstance(value, list):
        for item in value:
            _assert_no_absolute_paths(item, key)
    elif (
        isinstance(value, str)
        and (key in _PATH_KEYS or key.endswith("_path"))
        and _ABSOLUTE_PATH_PATTERN.match(value)
    ):
        raise MCPDispatchError("filesystem_path_leak", "security", "absolute paths are not exposed")


def _encode_payload(payload: dict[str, object], *, error: bool = False) -> str:
    _assert_no_absolute_paths(payload)
    try:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        raise MCPDispatchError(
            "output_not_serializable", "core", "tool output is not serializable"
        ) from None
    limit = MAX_ERROR_BYTES if error else MAX_TOOL_OUTPUT_BYTES
    if len(encoded.encode("utf-8")) > limit:
        raise MCPDispatchError(
            "error_bound_exceeded" if error else "output_bound_exceeded",
            "bounds",
            "response exceeds its bound",
        )
    return encoded


def _success_result(payload: dict[str, object]) -> types.CallToolResult:
    encoded = _encode_payload(payload)
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=encoded)],
        structuredContent=payload,
        isError=False,
    )


def _error_result(error: MCPDispatchError) -> types.CallToolResult:
    payload: dict[str, object] = {
        "version": MCP_ERROR_VERSION,
        "error": {"code": error.code, "category": error.category, "message": error.message},
    }
    try:
        encoded = _encode_payload(payload, error=True)
    except MCPDispatchError:
        payload = {
            "version": MCP_ERROR_VERSION,
            "error": {
                "code": "core_operation_failed",
                "category": "internal",
                "message": "core operation failed closed",
            },
        }
        encoded = json.dumps(payload, separators=(",", ":"))
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=encoded)],
        structuredContent=payload,
        isError=True,
    )


async def _call_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
    try:
        return _success_result(dispatch_tool(get_settings(), name, arguments))
    except Exception as exc:
        return _error_result(_error_for_exception(exc))


server = Server(
    MCP_SERVER_NAME,
    version=MCP_SERVER_VERSION,
    instructions="HIVE local-first read-only Core surface; no canonical write or execution tools.",
)


@server.list_tools()  # type: ignore[no-untyped-call,misc]
async def list_tool_definitions() -> list[types.Tool]:
    return list(TOOL_DEFINITIONS)


@server.call_tool(validate_input=False)  # type: ignore[misc]
async def call_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
    return await _call_tool(name, arguments)


async def run_stdio() -> None:
    """Run one standard MCP session over stdin/stdout."""

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
            raise_exceptions=False,
        )


if __name__ == "__main__":
    anyio.run(run_stdio)
