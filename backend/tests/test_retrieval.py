import hashlib
import subprocess
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app import main, retrieval
from app.config import Settings


def git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def source_bundle(
    repository: Path, head: str, inventory: tuple[str, ...]
) -> retrieval._SourceBundle:
    content = (repository / "tracked.txt").read_bytes()
    source_hash = hashlib.sha256(content).hexdigest()
    source = retrieval._Source(
        source_kind="REPOSITORY_FILE",
        source_id=UUID("00000000-0000-0000-0000-000000000002"),
        repository_file_id=UUID("00000000-0000-0000-0000-000000000002"),
        repository_symbol_id=None,
        task_id=None,
        path="tracked.txt",
        source_title=None,
        qualified_symbol=None,
        source_content_sha256=source_hash,
        text=content.decode("utf-8"),
        file_path=repository / "tracked.txt",
    )
    return retrieval._SourceBundle(
        project_id=UUID("00000000-0000-0000-0000-000000000001"),
        repository_path=repository,
        repository_index_run_id=UUID("00000000-0000-0000-0000-000000000003"),
        repository_head=head,
        repository_inventory=inventory,
        repository_file_hashes=(("tracked.txt", source_hash),),
        repository_sources=(source,),
        task_sources=(),
        repository_source_fingerprint="a" * 64,
        task_source_fingerprint="b" * 64,
        source_fingerprint="c" * 64,
        skipped_binary_count=0,
        skipped_decode_count=0,
    )


def test_lexical_normalization_covers_identifier_shapes() -> None:
    normalized = retrieval.normalize_lexical_query("backend/app/OrderService.get_project-value")

    assert normalized.normalized == "backend app order service get project value"
    assert normalized.basename == "orderservice.get_project-value"


def test_lexical_search_text_adds_identifier_aliases() -> None:
    expanded = retrieval.lexical_search_text("get_project HTTPServer")

    assert "get_project HTTPServer" in expanded
    assert "get project http server" in expanded


def test_sql_queries_are_parameterized() -> None:
    source = Path(retrieval.__file__).read_text(encoding="utf-8")
    assert "plainto_tsquery('simple', %s)" in source
    assert "WHERE r.project_id = %s" in source
    assert "LIMIT %s" in source


def test_chunker_is_stable_bounded_and_line_overlapping() -> None:
    source = "".join(f"line {index}: retrieval\n" for index in range(1, 121))

    first = retrieval.chunk_text(source)
    second = retrieval.chunk_text(source)

    assert first == second
    assert len(first) == 2
    assert first[0].start_line == 1
    assert first[0].end_line == 80
    assert first[1].start_line == 71
    assert first[1].end_line == 120
    assert all(len(chunk.content) <= retrieval.MAX_CHUNK_CHARS for chunk in first)
    assert all(chunk.content_sha256 for chunk in first)
    assert all(source[chunk.start_char : chunk.end_char] == chunk.content for chunk in first)


def test_chunker_splits_long_lines_without_unbounded_results() -> None:
    source = "x" * (retrieval.MAX_CHUNK_CHARS * 2 + 100)

    chunks = retrieval.chunk_text(source)

    assert len(chunks) >= 3
    assert all(0 < len(chunk.content) <= retrieval.MAX_CHUNK_CHARS for chunk in chunks)
    assert all(chunk.start_line == chunk.end_line == 1 for chunk in chunks)
    assert all(source[chunk.start_char : chunk.end_char] == chunk.content for chunk in chunks)


def test_empty_and_short_input_have_exact_ranges() -> None:
    assert retrieval.chunk_text("") == []
    chunks = retrieval.chunk_text("one\ntwo")

    assert len(chunks) == 1
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 2
    assert chunks[0].start_char == 0
    assert chunks[0].end_char == 7


def test_promotion_rejects_a_git_head_race(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    git(repository, "init", "-b", "main")
    git(repository, "config", "user.email", "hive-test@example.invalid")
    git(repository, "config", "user.name", "HIVE Test")
    (repository / "tracked.txt").write_text("stable\n", encoding="utf-8")
    git(repository, "add", "tracked.txt")
    git(repository, "commit", "-m", "initial")
    captured_head = git(repository, "rev-parse", "HEAD")
    bundle = source_bundle(repository, captured_head, ("tracked.txt",))

    (repository / "tracked.txt").write_text("changed\n", encoding="utf-8")
    git(repository, "add", "tracked.txt")
    git(repository, "commit", "-m", "head race")

    with pytest.raises(retrieval.RetrievalSyncError, match="repository_source_stale"):
        retrieval._revalidate_bundle(Settings(), bundle)


def test_promotion_rejects_an_inventory_race_with_unchanged_captured_bytes(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    git(repository, "init", "-b", "main")
    git(repository, "config", "user.email", "hive-test@example.invalid")
    git(repository, "config", "user.name", "HIVE Test")
    (repository / "tracked.txt").write_text("stable\n", encoding="utf-8")
    git(repository, "add", "tracked.txt")
    git(repository, "commit", "-m", "initial")
    captured_head = git(repository, "rev-parse", "HEAD")
    bundle = source_bundle(repository, captured_head, ("tracked.txt",))

    (repository / "added.txt").write_text("added after bundle\n", encoding="utf-8")
    git(repository, "add", "added.txt")

    with pytest.raises(retrieval.RetrievalSyncError, match="repository_source_stale"):
        retrieval._revalidate_bundle(Settings(), bundle)


def test_lexical_api_rejects_invalid_bounds_before_database_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        retrieval,
        "_settings",
        lambda: Settings(),
    )
    client = TestClient(main.app)
    project_id = UUID("00000000-0000-0000-0000-000000000001")

    oversized = client.post(
        f"/api/v1/projects/{project_id}/retrieval/lexical",
        json={"query": "x" * (retrieval.MAX_QUERY_CHARS + 1)},
    )
    invalid_source = client.post(
        f"/api/v1/projects/{project_id}/retrieval/lexical",
        json={"query": "project", "source_kind": "MEMORY"},
    )

    assert oversized.status_code == 422
    assert invalid_source.status_code == 422


def test_sync_missing_project_is_stable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        retrieval,
        "sync_corpus",
        lambda *_args: (_ for _ in ()).throw(retrieval.RetrievalProjectNotFoundError("missing")),
    )
    client = TestClient(main.app)
    project_id = UUID("00000000-0000-0000-0000-000000000001")

    response = client.post(f"/api/v1/projects/{project_id}/retrieval/corpus/sync")

    assert response.status_code == 404
    assert response.json() == {"detail": "project not found"}
