import ast
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from mcp.types import TextContent

from app import mcp_server
from app.config import Settings
from app.memory import MemoryOrigin, MemoryResponse, MemoryStatus, MemoryType
from app.registry import ProjectResponse, ProjectState
from app.reranking import RerankCandidate, RerankResponse, RerankState
from app.semantic_retrieval import SemanticState

PROJECT_ID = UUID("00000000-0000-0000-0000-000000000001")
MEMORY_ID = UUID("00000000-0000-0000-0000-000000000002")
TASK_ID = UUID("00000000-0000-0000-0000-000000000003")
HEAD = "a" * 40
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def project_response(
    *, project_id: UUID = PROJECT_ID, relative_path: str = "project"
) -> ProjectResponse:
    return ProjectResponse(
        project_id=project_id,
        name="Fixture project",
        relative_path=relative_path,
        git_branch="main",
        git_head_sha=HEAD,
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


def memory_response(
    *, project_id: UUID = PROJECT_ID, content: str = "confirmed fact"
) -> MemoryResponse:
    return MemoryResponse(
        memory_id=MEMORY_ID,
        project_id=project_id,
        type=MemoryType.PROJECT,
        status=MemoryStatus.CONFIRMED,
        content=content,
        source="docs/project-brain/04-ARCHITECTURE.md",
        source_version="architecture-v1",
        source_commit=HEAD,
        confidence=1.0,
        importance=5,
        authority="integration-fixture",
        tags=["fixture"],
        origin=MemoryOrigin.USER,
        promotion_basis=None,
        supersedes_memory_id=None,
        superseded_by_memory_id=None,
        version=1,
        created_at=NOW,
        updated_at=NOW,
    )


def test_catalog_is_exactly_read_only_and_closed() -> None:
    assert tuple(tool.name for tool in mcp_server.TOOL_DEFINITIONS) == mcp_server.TOOL_NAMES
    assert len(mcp_server.TOOL_DEFINITIONS) == 7
    for tool in mcp_server.TOOL_DEFINITIONS:
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert tool.inputSchema["additionalProperties"] is False
        assert not set(tool.inputSchema["properties"]) & {"path", "root", "file"}
    assert mcp_server.TOOL_NAMES == (
        "project.list",
        "project.status",
        "context.build",
        "context.search",
        "memory.search",
        "memory.get",
        "checkpoint.read",
    )


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("checkpoint.read", {"project_id": str(PROJECT_ID), "path": "C:/Windows"}),
        ("checkpoint.read", {"project_id": str(PROJECT_ID), "root": "/etc"}),
        ("checkpoint.read", {"project_id": str(PROJECT_ID), "file": "secret.txt"}),
        ("project.status", {"project_id": "not-a-uuid"}),
        ("context.search", {"project_id": str(PROJECT_ID), "query": "x", "top_k": 0}),
        ("memory.search", {"project_id": str(PROJECT_ID), "limit": 999}),
        ("memory.search", {"project_id": str(PROJECT_ID), "status": "UNKNOWN"}),
    ],
)
def test_invalid_arguments_reject_injection_and_out_of_bounds_inputs(
    tool_name: str, arguments: dict[str, object]
) -> None:
    with pytest.raises(mcp_server.MCPDispatchError) as error:
        mcp_server.dispatch_tool(Settings(projects_root=Path.cwd()), tool_name, arguments)
    assert error.value.code == "invalid_arguments"


def test_project_list_delegates_to_registry_and_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    projects = [project_response(), project_response(project_id=MEMORY_ID, relative_path="second")]
    monkeypatch.setattr(mcp_server, "list_projects", lambda _settings: projects)

    result = mcp_server.dispatch_tool(
        Settings(projects_root=Path.cwd()), "project.list", {"limit": 1}
    )

    assert result["returned_count"] == 1
    assert result["truncated"] is True
    assert result["projects"] == [
        {
            "project_id": str(PROJECT_ID),
            "name": "Fixture project",
            "relative_path": "project",
            "git_branch": "main",
            "git_head_sha": HEAD,
            "detached_head": False,
            "repository_accessible": True,
            "working_tree_clean": True,
            "language_stack": ["python"],
            "state": "READY",
        }
    ]


def test_context_search_delegates_to_current_reranking_seam(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    candidate = RerankCandidate(
        project_id=PROJECT_ID,
        reference_id=UUID("00000000-0000-0000-0000-000000000010"),
        chunk_id=UUID("00000000-0000-0000-0000-000000000011"),
        corpus_run_id=UUID("00000000-0000-0000-0000-000000000012"),
        source_kind="TASK",
        hybrid_score=1.0,
        lexical_score=1.0,
        semantic_score=None,
        semantic_distance=None,
        lexical_rank=1,
        semantic_rank=None,
        lexical_contribution=1.0,
        semantic_contribution=0.0,
        snippet="project-specific provenance",
        path="docs/project-brain/04-ARCHITECTURE.md",
        title="Fixture task",
        qualified_symbol=None,
        repository_file_id=None,
        repository_symbol_id=None,
        task_id=TASK_ID,
        source_content_sha256="b" * 64,
        chunk_content_sha256="c" * 64,
        chunker_version="line-window-v1",
        start_line=1,
        end_line=1,
        start_char=0,
        end_char=30,
        pre_rerank_rank=1,
        rerank_rank=1,
        rerank_score=None,
    )
    response = RerankResponse(
        project_id=PROJECT_ID,
        query="provenance",
        normalized_query="provenance",
        top_k=3,
        candidate_pool=1,
        hybrid_state="LEXICAL_FALLBACK",
        semantic_state=SemanticState.UNAVAILABLE,
        rerank_state=RerankState.RERANK_FALLBACK_DISABLED,
        fallback_reason="disabled",
        reranker_profile=None,
        serialization_version="rerank-document-v1",
        results=[candidate],
    )

    def fake_rerank(_settings: Settings, project_id: UUID, request: Any) -> Any:
        captured["project_id"] = project_id
        captured["request"] = request
        return response

    monkeypatch.setattr(mcp_server, "rerank_search", fake_rerank)
    result = mcp_server.dispatch_tool(
        Settings(projects_root=Path.cwd()),
        "context.search",
        {"project_id": str(PROJECT_ID), "query": "provenance", "top_k": 3},
    )

    assert captured["project_id"] == PROJECT_ID
    assert captured["request"].candidate_pool == 3
    assert result["project_id"] == str(PROJECT_ID)
    results = result["results"]
    assert isinstance(results, list)
    assert isinstance(results[0], dict)
    assert results[0]["path"] == "docs/project-brain/04-ARCHITECTURE.md"
    json.dumps(result)


def test_memory_search_preserves_status_and_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    memory = memory_response(content="x" * (mcp_server.MAX_MEMORY_CONTENT_CHARS + 10))
    monkeypatch.setattr(mcp_server, "list_memories", lambda *_args: [memory])

    result = mcp_server.dispatch_tool(
        Settings(projects_root=Path.cwd()),
        "memory.search",
        {"project_id": str(PROJECT_ID), "status": "CONFIRMED", "limit": 1},
    )

    assert result["status"] == "CONFIRMED"
    memories = result["memories"]
    assert isinstance(memories, list)
    assert isinstance(memories[0], dict)
    item = memories[0]
    assert item["status"] == "CONFIRMED"
    assert item["source"] == "docs/project-brain/04-ARCHITECTURE.md"
    assert item["content_truncated"] is True
    assert len(item["content"]) == mcp_server.MAX_MEMORY_CONTENT_CHARS
    json.dumps(result)


def test_checkpoint_read_returns_tracked_project_bound_content(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = Settings(projects_root=tmp_path)
    checkpoint = (
        b"# Status\n\nProject-specific checkpoint.\n\n"
        b"## Version\n\n1\n\n"
        b"## Phase\n\nACTIVE\n\n"
        b"## Objective\n\nRead-only MCP surface.\n\n"
        b"## In Progress\n\nCore adapter.\n\n"
        b"## Blockers\n\nNone.\n\n"
        b"## Next Step\n\nReview.\n"
    )
    entry = SimpleNamespace(
        path="docs/project-brain/13-CHECKPOINT.md",
        source=checkpoint,
        git_status="CLEAN",
        git_blob_sha="d" * 40,
        content_sha256="e" * 64,
    )
    snapshot = SimpleNamespace(repository_head_sha=HEAD, files=[entry])
    monkeypatch.setattr(mcp_server, "get_project", lambda *_args: project_response())
    monkeypatch.setattr(mcp_server, "_collect_inventory", lambda *_args: snapshot)
    monkeypatch.setattr(mcp_server, "_tracked_governance_file", lambda *_args: entry)
    monkeypatch.setattr(mcp_server, "_assert_snapshot_stable", lambda *_args: None)

    result = mcp_server.dispatch_tool(settings, "checkpoint.read", {"project_id": str(PROJECT_ID)})

    data = result["checkpoint"]
    assert isinstance(data, dict)
    assert result["project_id"] == str(PROJECT_ID)
    assert data["path"] == "docs/project-brain/13-CHECKPOINT.md"
    assert data["content"] == checkpoint.decode()
    assert data["git_head_sha"] == HEAD


def test_checkpoint_unavailable_is_structured_and_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        mcp_server,
        "dispatch_tool",
        lambda *_args: (_ for _ in ()).throw(
            mcp_server.MCPDispatchError(
                "source_not_current", "stale", "project source is not current"
            )
        ),
    )

    result = asyncio.run(mcp_server._call_tool("checkpoint.read", {"project_id": str(PROJECT_ID)}))

    assert result.isError is True
    content = result.content[0]
    assert isinstance(content, TextContent)
    encoded = content.text
    assert len(encoded.encode("utf-8")) <= mcp_server.MAX_ERROR_BYTES
    payload = json.loads(encoded)
    assert payload == {
        "version": "mcp-error-v1",
        "error": {
            "category": "stale",
            "code": "source_not_current",
            "message": "project source is not current",
        },
    }
    assert "C:/" not in encoded and "D:/" not in encoded


def test_error_transport_rejects_absolute_path_payloads() -> None:
    with pytest.raises(mcp_server.MCPDispatchError) as error:
        mcp_server._encode_payload({"version": "test", "path": "C:/secret"})
    assert error.value.code == "filesystem_path_leak"


def test_adapter_has_no_rest_provider_or_persistence_surface() -> None:
    source_path = Path(__file__).parents[1] / "app" / "mcp_server.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
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
    assert not imported_modules & {"fastapi", "httpx", "requests", "urllib", "sqlalchemy"}
    assert not imported_from & {"fastapi", "httpx", "requests", "urllib", "sqlalchemy"}
    source = source_path.read_text(encoding="utf-8")
    for symbol in (
        "list_projects",
        "get_project",
        "build_context",
        "rerank_search",
        "list_memories",
        "get_memory",
        "_collect_inventory",
        "_assert_snapshot_stable",
    ):
        assert symbol in source
    assert "database_connection" not in source
