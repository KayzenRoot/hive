import hashlib
import subprocess
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from app import memory as memory_module
from app.config import Settings
from app.memory import (
    MemoryCreateRequest,
    MemoryError,
    MemoryOrigin,
    MemoryStatus,
    MemoryType,
    PromotionBasis,
    PromotionBasisKind,
    _approved_adr_id,
    _approved_decision_status,
    _normalized_source_reference,
    _resolve_trusted_source,
    validate_transition,
)

PROJECT_ID = UUID("00000000-0000-0000-0000-000000000001")


def git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def create_git_project(root: Path, *, with_decision: bool = False) -> tuple[Path, str]:
    repository = root / "project"
    repository.mkdir()
    git(repository, "init", "-b", "main")
    git(repository, "config", "user.email", "hive-test@example.invalid")
    git(repository, "config", "user.name", "HIVE Memory Tests")
    (repository / "README.md").write_bytes(b"stable source\n")
    paths = ["README.md"]
    if with_decision:
        ledger = repository / "docs" / "project-brain" / "16-DECISIONS-LEDGER.md"
        ledger.parent.mkdir(parents=True)
        ledger.write_bytes(
            b"# Decisions\n\n"
            b"## PROJECT-DEC-7 - Project-specific decision\n"
            b"**Status:** Approved\n\n"
            b"Project-specific canonical decision.\n"
        )
        paths.append("docs/project-brain/16-DECISIONS-LEDGER.md")
    git(repository, "add", *paths)
    git(repository, "commit", "-m", "memory test fixture")
    return repository, git(repository, "rev-parse", "HEAD")


class ProjectCursor:
    def __init__(self, relative_path: str, head: str) -> None:
        self.relative_path = relative_path
        self.head = head

    def execute(self, query: str, _parameters: tuple[object, ...]) -> None:
        self.next_row = {
            "relative_path": self.relative_path,
            "git_head_sha": self.head,
        }

    def fetchone(self) -> dict[str, str]:
        return self.next_row


class PromotionCursor:
    def __init__(self, relative_path: str, head: str) -> None:
        self.relative_path = relative_path
        self.head = head
        self.queries: list[str] = []
        self.next_row: dict[str, object] | None = None

    def __enter__(self) -> "PromotionCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str, _parameters: tuple[object, ...]) -> None:
        self.queries.append(query)
        if "FROM memory_records" in query:
            self.next_row = {"status": "CONFIRMED"}
        elif "FROM projects" in query:
            self.next_row = {
                "relative_path": self.relative_path,
                "git_head_sha": self.head,
            }

    def fetchone(self) -> dict[str, object] | None:
        return self.next_row


class PromotionConnection:
    def __init__(self, cursor: PromotionCursor) -> None:
        self.cursor_value = cursor
        self.failed = False

    def __enter__(self) -> "PromotionConnection":
        return self

    def __exit__(self, exc_type: object, *_args: object) -> None:
        self.failed = exc_type is not None
        return None

    def cursor(self, **_kwargs: object) -> PromotionCursor:
        return self.cursor_value


def valid_request(**overrides: object) -> MemoryCreateRequest:
    values: dict[str, object] = {
        "type": MemoryType.PROJECT,
        "content": "The project uses a durable PostgreSQL registry.",
        "source": "docs/project-brain/04-ARCHITECTURE.md",
        "authority": "canonical-project-source",
    }
    values.update(overrides)
    return MemoryCreateRequest.model_validate(values)


def test_memory_classes_and_model_output_are_noncanonical() -> None:
    request = valid_request(origin=MemoryOrigin.MODEL)

    assert request.status is MemoryStatus.PROPOSED
    assert request.origin is MemoryOrigin.MODEL
    assert tuple(item.value for item in MemoryType) == (
        "WORKING",
        "SESSION",
        "PROJECT",
        "SEMANTIC",
        "EPISODIC",
        "DECISION",
        "FAILURE",
        "PROCEDURAL",
    )


def test_direct_canonical_and_deprecated_creation_are_rejected() -> None:
    for status in (MemoryStatus.CANONICAL, MemoryStatus.DEPRECATED):
        with pytest.raises(ValidationError):
            valid_request(status=status)


def test_secret_material_is_rejected_and_limits_are_bounded() -> None:
    with pytest.raises(ValidationError):
        valid_request(content="provider response api_key=not-a-real-key")
    with pytest.raises(ValidationError):
        valid_request(tags=["x" * 129])
    with pytest.raises(ValidationError):
        valid_request(source_commit="not-a-sha")


def test_lifecycle_transitions_are_explicit() -> None:
    validate_transition(MemoryStatus.PROPOSED, MemoryStatus.CONFIRMED)
    validate_transition(MemoryStatus.CANONICAL, MemoryStatus.DEPRECATED)
    with pytest.raises(ValueError):
        validate_transition(MemoryStatus.PROPOSED, MemoryStatus.CANONICAL)
    with pytest.raises(ValueError):
        validate_transition(MemoryStatus.DEPRECATED, MemoryStatus.CONFIRMED)


def test_promotion_basis_is_explicit_and_project_bound() -> None:
    basis = PromotionBasis(
        kind=PromotionBasisKind.VALIDATED_EVIDENCE,
        reference="memory-lifecycle integration evidence",
        project_id=PROJECT_ID,
    )

    assert basis.kind is PromotionBasisKind.VALIDATED_EVIDENCE
    assert basis.project_id == PROJECT_ID
    assert basis.reference == "memory-lifecycle integration evidence"


def test_canonical_basis_references_are_strictly_normalized() -> None:
    assert _approved_adr_id("HIVE-ADR-019") == "HIVE-ADR-019"
    assert (
        _approved_adr_id("docs/project-brain/16-DECISIONS-LEDGER.md#HIVE-ADR-019") == "HIVE-ADR-019"
    )
    assert _normalized_source_reference("docs/project-brain/16-DECISIONS-LEDGER.md") == (
        "docs/project-brain/16-DECISIONS-LEDGER.md"
    )
    for reference in (
        "",
        "../outside.md",
        "docs/./source.md",
        "docs//source.md",
        "docs\\source.md",
        "/outside.md",
        "C:/outside.md",
    ):
        with pytest.raises(MemoryError):
            _normalized_source_reference(reference)
    with pytest.raises(MemoryError):
        _approved_adr_id("HIVE ADR 9999")


def test_project_decision_ids_are_generic_exact_and_unambiguous() -> None:
    ledger = (
        b"# Decisions\n\n"
        b"## PROJECT-DEC-7 - Project-specific decision\n"
        b"Status: Approved\n\n"
        b"## PROJECT-DEC-8 - Another decision\n"
        b"Status: Accepted\n"
    )

    assert _approved_adr_id("PROJECT-DEC-7") == "PROJECT-DEC-7"
    assert _approved_decision_status(ledger, "PROJECT-DEC-7") == "Approved"
    with pytest.raises(MemoryError):
        _approved_decision_status(ledger, "PROJECT-DEC-7-extra")
    with pytest.raises(MemoryError):
        _approved_decision_status(
            ledger + b"\n## PROJECT-DEC-7 - Duplicate\nStatus: Accepted\n",
            "PROJECT-DEC-7",
        )


def test_trusted_source_uses_exact_immutable_git_blob_bytes(tmp_path: Path) -> None:
    repository, head = create_git_project(tmp_path)
    settings = Settings(projects_root=tmp_path)
    verified, source = _resolve_trusted_source(
        ProjectCursor("project", head), settings, PROJECT_ID, "README.md"
    )
    expected_source = b"stable source\n"

    assert source == expected_source
    assert verified["source_commit"] == head
    assert verified["git_blob_sha"] == git(repository, "rev-parse", "HEAD:README.md")
    assert verified["source_sha256"] == hashlib.sha256(expected_source).hexdigest()
    assert verified["byte_binding"] == "immutable-git-blob-v1"


def test_source_mutation_between_snapshot_reads_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repository, head = create_git_project(tmp_path)
    settings = Settings(projects_root=tmp_path)
    original_read = memory_module._read_stable_file  # type: ignore[attr-defined]
    calls = 0

    def mutate_after_first_read(path: Path, current_settings: Settings) -> tuple[bytes, object]:
        nonlocal calls
        result = original_read(path, current_settings)
        calls += 1
        if calls == 1:
            path.write_bytes(b"racing source\n")
        return result

    monkeypatch.setattr(memory_module, "_read_stable_file", mutate_after_first_read)
    with pytest.raises(MemoryError, match="mutated|changed"):
        _resolve_trusted_source(ProjectCursor("project", head), settings, PROJECT_ID, "README.md")


def test_decisions_source_mutation_fails_closed_before_adr_parse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, head = create_git_project(tmp_path, with_decision=True)
    settings = Settings(projects_root=tmp_path)
    original_read = memory_module._read_stable_file  # type: ignore[attr-defined]
    calls = 0

    def mutate_after_first_read(path: Path, current_settings: Settings) -> tuple[bytes, object]:
        nonlocal calls
        result = original_read(path, current_settings)
        calls += 1
        if calls == 1:
            (repository / "docs" / "project-brain" / "16-DECISIONS-LEDGER.md").write_bytes(
                b"# Decisions\n\n## PROJECT-DEC-7 - Project-specific decision\nStatus: Rejected\n"
            )
        return result

    monkeypatch.setattr(memory_module, "_read_stable_file", mutate_after_first_read)
    with pytest.raises(MemoryError, match="mutated|changed"):
        memory_module._resolve_promotion_basis(
            ProjectCursor("project", head),
            settings,
            PROJECT_ID,
            PromotionBasis(kind=PromotionBasisKind.APPROVED_ADR, reference="PROJECT-DEC-7"),
        )


def test_head_mutation_during_qualification_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, head = create_git_project(tmp_path)
    settings = Settings(projects_root=tmp_path)
    original_head = memory_module._git_head  # type: ignore[attr-defined]
    calls = 0

    def mutate_after_first_head(path: Path) -> str:
        nonlocal calls
        result = original_head(path)
        calls += 1
        if calls == 1:
            (repository / "README.md").write_bytes(b"new HEAD source\n")
            git(repository, "add", "README.md")
            git(repository, "commit", "-m", "head race")
        return result

    monkeypatch.setattr(memory_module, "_git_head", mutate_after_first_head)
    with pytest.raises(MemoryError, match="uncommitted|mutated|stale"):
        _resolve_trusted_source(ProjectCursor("project", head), settings, PROJECT_ID, "README.md")


def test_source_race_rejection_keeps_promotion_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repository, head = create_git_project(tmp_path)
    settings = Settings(projects_root=tmp_path)
    cursor = PromotionCursor("project", head)
    connection = PromotionConnection(cursor)
    original_read = memory_module._read_stable_file  # type: ignore[attr-defined]
    calls = 0

    def mutate_after_first_read(path: Path, current_settings: Settings) -> tuple[bytes, object]:
        nonlocal calls
        result = original_read(path, current_settings)
        calls += 1
        if calls == 1:
            path.write_bytes(b"racing source\n")
        return result

    monkeypatch.setattr(memory_module, "_read_stable_file", mutate_after_first_read)
    monkeypatch.setattr(memory_module, "database_connection", lambda _settings: connection)
    with pytest.raises(MemoryError):
        memory_module.promote_memory(
            settings,
            PROJECT_ID,
            UUID("00000000-0000-0000-0000-000000000002"),
            PromotionBasis(kind=PromotionBasisKind.TRUSTED_SOURCE, reference="README.md"),
        )

    assert connection.failed
    assert not any(query.startswith("UPDATE memory_records") for query in cursor.queries)
    assert not any("memory_record_history" in query for query in cursor.queries)
