import ast
import asyncio
import importlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from mcp.types import TextContent

from app import mcp_server
from app.config import Settings
from app.context_manager import ContextBoundsError
from app.memory import MemoryOrigin, MemoryResponse, MemoryStatus, MemoryType
from app.registry import ProjectResponse, ProjectState
from app.reranking import RerankCandidate, RerankResponse, RerankState
from app.semantic_retrieval import SemanticState

PROJECT_ID = UUID("00000000-0000-0000-0000-000000000001")
MEMORY_ID = UUID("00000000-0000-0000-0000-000000000002")
TASK_ID = UUID("00000000-0000-0000-0000-000000000003")
HEAD = "a" * 40
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _mcp_integration_module() -> Any:
    scripts_path = str(Path(__file__).parents[2] / "scripts")
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    return importlib.import_module("mcp_integration")


def _complete_evidence_observations(integration: Any) -> dict[str, object]:
    return {
        **{field: True for field in integration.MCP_CORE_SURFACE_TRUE_FIELDS},
        **{field: False for field in integration.MCP_CORE_SURFACE_FALSE_FIELDS},
        **{field: 0 for field in integration.MCP_CORE_SURFACE_INTEGER_FIELDS},
        "registered_project_count": 3,
        "tool_list_exact": list(integration.MCP_CORE_SURFACE_TOOLS),
        "observed_migration_head": "0006_memory_lifecycle_provenance",
    }


def _git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def _lineage_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "lineage-repo"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=main")
    _git(repo, "config", "user.name", "HIVE test")
    _git(repo, "config", "user.email", "hive-test@example.invalid")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    return repo, base


def _commit_files(repo: Path, files: dict[str, str], message: str) -> str:
    for relative_path, content in files.items():
        path = repo / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(repo, "add", "--all")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _set_origin_main(repo: Path, commit: str) -> None:
    _git(repo, "update-ref", "refs/remotes/origin/main", commit)


def _observe_lineage(integration: Any, monkeypatch: pytest.MonkeyPatch, repo: Path) -> bool:
    monkeypatch.setattr(integration, "ROOT", repo)
    return bool(integration._observe_migration_changed(os.environ.copy()))


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


def test_project_status_delegates_to_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_get_project(_settings: Settings, project_id: UUID) -> ProjectResponse:
        captured["project_id"] = project_id
        return project_response(project_id=project_id)

    monkeypatch.setattr(mcp_server, "get_project", fake_get_project)

    result = mcp_server.dispatch_tool(
        Settings(projects_root=Path.cwd()),
        "project.status",
        {"project_id": str(PROJECT_ID)},
    )

    assert captured["project_id"] == PROJECT_ID
    projection = result["project"]
    assert isinstance(projection, dict)
    assert projection["project_id"] == str(PROJECT_ID)
    assert projection["git_head_sha"] == HEAD
    assert projection["state"] == "READY"


def test_context_build_delegates_with_exact_bounded_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_build_context(
        _settings: Settings,
        project_id: UUID,
        task_id: UUID,
        *,
        top_k: int,
        disclosure_level: str | None,
    ) -> Any:
        captured.update(
            {
                "project_id": project_id,
                "task_id": task_id,
                "top_k": top_k,
                "disclosure_level": disclosure_level,
            }
        )
        return SimpleNamespace(
            project=project_response(project_id=project_id),
            task=SimpleNamespace(task_id=task_id),
            model_dump=lambda mode: {"governance": [{"kind": "CHECKPOINT"}]},
        )

    monkeypatch.setattr(mcp_server, "build_context", fake_build_context)

    result = mcp_server.dispatch_tool(
        Settings(projects_root=Path.cwd()),
        "context.build",
        {
            "project_id": str(PROJECT_ID),
            "task_id": str(TASK_ID),
            "top_k": 7,
            "disclosure_level": "L2",
        },
    )

    assert captured == {
        "project_id": PROJECT_ID,
        "task_id": TASK_ID,
        "top_k": 7,
        "disclosure_level": "L2",
    }
    assert result["project_id"] == str(PROJECT_ID)
    assert result["task_id"] == str(TASK_ID)
    assert result["checkpoint_first"] is True


def test_memory_get_delegates_and_preserves_project_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_get_memory(_settings: Settings, project_id: UUID, memory_id: UUID) -> MemoryResponse:
        captured.update({"project_id": project_id, "memory_id": memory_id})
        return memory_response(project_id=project_id)

    monkeypatch.setattr(mcp_server, "get_memory", fake_get_memory)

    result = mcp_server.dispatch_tool(
        Settings(projects_root=Path.cwd()),
        "memory.get",
        {"project_id": str(PROJECT_ID), "memory_id": str(MEMORY_ID)},
    )

    assert captured == {"project_id": PROJECT_ID, "memory_id": MEMORY_ID}
    memory = result["memory"]
    assert isinstance(memory, dict)
    assert memory["project_id"] == str(PROJECT_ID)
    assert memory["status"] == "CONFIRMED"
    assert memory["source"] == "docs/project-brain/04-ARCHITECTURE.md"
    assert memory["source_commit"] == HEAD


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


def test_memory_search_fails_closed_when_core_exceeds_requested_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mcp_server,
        "list_memories",
        lambda *_args: [memory_response(), memory_response(content="second")],
    )

    with pytest.raises(mcp_server.MCPDispatchError) as error:
        mcp_server.dispatch_tool(
            Settings(projects_root=Path.cwd()),
            "memory.search",
            {"project_id": str(PROJECT_ID), "limit": 1},
        )

    assert error.value.code == "output_bound_exceeded"


def test_project_list_fails_closed_when_inventory_exceeds_hard_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projects = [
        project_response(project_id=UUID(int=index + 1), relative_path=f"project-{index}")
        for index in range(mcp_server.MAX_PROJECTS + 1)
    ]
    monkeypatch.setattr(mcp_server, "list_projects", lambda _settings: projects)

    with pytest.raises(mcp_server.MCPDispatchError) as error:
        mcp_server.dispatch_tool(Settings(projects_root=Path.cwd()), "project.list", {"limit": 1})

    assert error.value.code == "output_bound_exceeded"


def test_success_payload_bound_fails_closed() -> None:
    with pytest.raises(mcp_server.MCPDispatchError) as error:
        mcp_server._encode_payload(
            {"version": "test", "content": "x" * mcp_server.MAX_TOOL_OUTPUT_BYTES}
        )

    assert error.value.code == "output_bound_exceeded"


def test_checkpoint_read_rejects_oversized_content_without_partial_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = Settings(projects_root=tmp_path)
    entry = SimpleNamespace(
        path="docs/project-brain/13-CHECKPOINT.md",
        source=b"x" * (mcp_server.MAX_CHECKPOINT_BYTES + 1),
        git_status="CLEAN",
        git_blob_sha="d" * 40,
        content_sha256="e" * 64,
    )
    snapshot = SimpleNamespace(repository_head_sha=HEAD, files=[entry])
    monkeypatch.setattr(mcp_server, "get_project", lambda *_args: project_response())
    monkeypatch.setattr(mcp_server, "_collect_inventory", lambda *_args: snapshot)
    monkeypatch.setattr(mcp_server, "_tracked_governance_file", lambda *_args: entry)
    monkeypatch.setattr(mcp_server, "_assert_snapshot_stable", lambda *_args: None)

    with pytest.raises(ContextBoundsError) as error:
        mcp_server.dispatch_tool(settings, "checkpoint.read", {"project_id": str(PROJECT_ID)})

    assert str(error.value) == "checkpoint_response_bound_exceeded"


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


def test_migration_observation_accepts_post_squash_head_equal_to_current_main(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    integration = _mcp_integration_module()
    repo, _base = _lineage_repo(tmp_path)
    product = _commit_files(
        repo,
        {"backend/app/mcp_server.py": "product\n"},
        "introduce MCP product",
    )
    _set_origin_main(repo, product)

    assert _observe_lineage(integration, monkeypatch, repo) is False


def test_migration_observation_ignores_unrelated_later_commit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    integration = _mcp_integration_module()
    repo, _base = _lineage_repo(tmp_path)
    _commit_files(
        repo,
        {"backend/app/mcp_server.py": "product\n"},
        "introduce MCP product",
    )
    later = _commit_files(repo, {"README.md": "unrelated\n"}, "unrelated later change")
    _set_origin_main(repo, later)

    assert _observe_lineage(integration, monkeypatch, repo) is False


def test_migration_observation_detects_migration_in_product_introduction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    integration = _mcp_integration_module()
    repo, _base = _lineage_repo(tmp_path)
    product = _commit_files(
        repo,
        {
            "backend/app/mcp_server.py": "product\n",
            "migrations/versions/0007_mcp_product.py": "revision = '0007'\n",
        },
        "introduce MCP product with migration",
    )
    _set_origin_main(repo, product)

    assert _observe_lineage(integration, monkeypatch, repo) is True


def test_migration_observation_fails_closed_when_product_lineage_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    integration = _mcp_integration_module()
    repo, base = _lineage_repo(tmp_path)
    _set_origin_main(repo, base)

    monkeypatch.setattr(integration, "ROOT", repo)
    with pytest.raises(AssertionError, match="lineage is missing or ambiguous"):
        integration._observe_migration_changed(os.environ.copy())


def test_migration_observation_fails_closed_when_product_lineage_is_ambiguous(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    integration = _mcp_integration_module()
    repo, _base = _lineage_repo(tmp_path)
    first_product = _commit_files(
        repo,
        {"backend/app/mcp_server.py": "first\n"},
        "introduce MCP product",
    )
    _git(repo, "rm", "backend/app/mcp_server.py")
    _git(repo, "commit", "-m", "remove MCP product")
    second_product = _commit_files(
        repo,
        {"backend/app/mcp_server.py": "second\n"},
        "reintroduce MCP product",
    )
    assert first_product != second_product
    _set_origin_main(repo, second_product)

    monkeypatch.setattr(integration, "ROOT", repo)
    with pytest.raises(AssertionError, match="lineage is missing or ambiguous"):
        integration._observe_migration_changed(os.environ.copy())


def test_migration_observation_preserves_current_base_stale_candidate_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    integration = _mcp_integration_module()
    repo, _base = _lineage_repo(tmp_path)
    product = _commit_files(
        repo,
        {"backend/app/mcp_server.py": "product\n"},
        "introduce MCP product",
    )
    _git(repo, "branch", "future-main")
    _git(repo, "switch", "future-main")
    future_main = _commit_files(repo, {"README.md": "future\n"}, "future protected-main change")
    _set_origin_main(repo, future_main)
    _git(repo, "switch", "--detach", product)

    monkeypatch.setattr(integration, "ROOT", repo)
    with pytest.raises(AssertionError, match="current protected-main base"):
        integration._observe_migration_changed(os.environ.copy())


def test_evidence_writer_fails_closed_on_missing_observation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    integration = _mcp_integration_module()
    output_path = tmp_path / "mcp-surface.json"
    monkeypatch.setattr(integration, "EVIDENCE_PATH", output_path)
    observations = _complete_evidence_observations(integration)
    observations.pop("secret_leaks")

    with pytest.raises(AssertionError, match="missing observed MCP evidence"):
        integration._write_evidence(observations)

    assert not output_path.exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [("migration_changed", True), ("mcp_provider_calls", 1)],
)
def test_evidence_writer_rejects_wrong_false_or_zero_observation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    integration = _mcp_integration_module()
    output_path = tmp_path / f"{field}.json"
    monkeypatch.setattr(integration, "EVIDENCE_PATH", output_path)
    observations = _complete_evidence_observations(integration)
    observations[field] = value

    with pytest.raises(AssertionError):
        integration._write_evidence(observations)

    assert not output_path.exists()


def test_evidence_writer_serializes_only_observed_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    integration = _mcp_integration_module()
    output_path = tmp_path / "mcp-surface.json"
    monkeypatch.setattr(integration, "EVIDENCE_PATH", output_path)
    observations = _complete_evidence_observations(integration)

    integration._write_evidence(observations)
    written = json.loads(output_path.read_text(encoding="utf-8"))

    for field in (
        "registered_project_count",
        "tool_list_exact",
        "migration_changed",
        "canonical_write_tools_exposed",
        "observed_migration_head",
        *integration.MCP_CORE_SURFACE_TRUE_FIELDS,
        *integration.MCP_CORE_SURFACE_FALSE_FIELDS,
        *integration.MCP_CORE_SURFACE_INTEGER_FIELDS,
    ):
        assert written[field] == observations[field]
