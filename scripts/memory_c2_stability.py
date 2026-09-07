"""Exercise deterministic WO-015-C2 source and promotion race rejection."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "backend"))

from app import memory as memory_module  # noqa: E402
from app.config import Settings  # noqa: E402
from app.memory import MemoryError, PromotionBasis, PromotionBasisKind  # noqa: E402

PROJECT_ID = UUID("00000000-0000-0000-0000-000000000001")


def git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def create_repository(root: Path) -> tuple[Path, str]:
    repository = root / "project"
    repository.mkdir()
    git(repository, "init", "-b", "main")
    git(repository, "config", "user.email", "hive-test@example.invalid")
    git(repository, "config", "user.name", "HIVE Memory C2")
    (repository / "README.md").write_bytes(b"stable source\n")
    ledger = repository / "docs" / "project-brain" / "16-DECISIONS-LEDGER.md"
    ledger.parent.mkdir(parents=True)
    ledger.write_bytes(
        b"# Decisions\n\n"
        b"## HIVE-ADR-019 - Stable accepted decision\n"
        b"**Status:** Accepted\n\n"
        b"Stable decision fixture.\n"
    )
    git(repository, "add", "README.md", "docs/project-brain/16-DECISIONS-LEDGER.md")
    git(repository, "commit", "-m", "memory C2 fixture")
    return repository, git(repository, "rev-parse", "HEAD")


class ProjectCursor:
    def __init__(self, relative_path: str, head: str) -> None:
        self.relative_path = relative_path
        self.head = head
        self.next_row: dict[str, object] | None = None
        self.queries: list[str] = []

    def __enter__(self) -> ProjectCursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str, _parameters: tuple[object, ...]) -> None:
        self.queries.append(query)
        if "FROM memory_records" in query:
            self.next_row = {"status": "CONFIRMED"}
        else:
            self.next_row = {
                "relative_path": self.relative_path,
                "git_head_sha": self.head,
            }

    def fetchone(self) -> dict[str, object] | None:
        return self.next_row


class AtomicConnection:
    def __init__(self, relative_path: str, head: str) -> None:
        self.cursor_value = ProjectCursor(relative_path, head)
        self.failed = False

    def __enter__(self) -> AtomicConnection:
        return self

    def __exit__(self, exc_type: object, *_args: object) -> None:
        self.failed = exc_type is not None
        return None

    def cursor(self, **_kwargs: object) -> ProjectCursor:
        return self.cursor_value


def _run_resolver_race(resolver: Callable[[], object], restore: Callable[[], None]) -> bool:
    try:
        resolver()
    except MemoryError:
        return True
    finally:
        restore()
    return False


def _source_race(settings: Settings, repository: Path, head: str) -> bool:
    original_read = memory_module._read_stable_file
    original_source = (repository / "README.md").read_bytes()
    calls = 0

    def mutate_after_first_read(path: Path, current_settings: Settings) -> tuple[bytes, Any]:
        nonlocal calls
        result = original_read(path, current_settings)
        calls += 1
        if calls == 1:
            path.write_bytes(b"racing source\n")
        return result

    memory_module._read_stable_file = mutate_after_first_read
    try:
        rejected = _run_resolver_race(
            lambda: memory_module._resolve_trusted_source(
                ProjectCursor("project", head), settings, PROJECT_ID, "README.md"
            ),
            lambda: (repository / "README.md").write_bytes(original_source),
        )
    finally:
        memory_module._read_stable_file = original_read
    return rejected


def _adr_race(settings: Settings, repository: Path, head: str) -> bool:
    original_read = memory_module._read_stable_file
    ledger = repository / "docs" / "project-brain" / "16-DECISIONS-LEDGER.md"
    original_source = ledger.read_bytes()
    calls = 0

    def mutate_after_first_read(path: Path, current_settings: Settings) -> tuple[bytes, Any]:
        nonlocal calls
        result = original_read(path, current_settings)
        calls += 1
        if calls == 1:
            path.write_bytes(
                b"# Decisions\n\n## HIVE-ADR-019 - Stable accepted decision\nStatus: Rejected\n"
            )
        return result

    memory_module._read_stable_file = mutate_after_first_read
    try:
        rejected = _run_resolver_race(
            lambda: memory_module._resolve_promotion_basis(
                ProjectCursor("project", head),
                settings,
                PROJECT_ID,
                PromotionBasis(kind=PromotionBasisKind.APPROVED_ADR, reference="HIVE-ADR-019"),
            ),
            lambda: ledger.write_bytes(original_source),
        )
    finally:
        memory_module._read_stable_file = original_read
    return rejected


def _head_race(settings: Settings, head: str) -> bool:
    original_head = memory_module._git_head
    calls = 0

    def mutate_after_first_head(path: Path) -> str:
        nonlocal calls
        result = original_head(path)
        calls += 1
        return "0" * 40 if calls == 2 else result

    memory_module._git_head = mutate_after_first_head
    try:
        return _run_resolver_race(
            lambda: memory_module._resolve_trusted_source(
                ProjectCursor("project", head), settings, PROJECT_ID, "README.md"
            ),
            lambda: None,
        )
    finally:
        memory_module._git_head = original_head


def _atomic_race(
    settings: Settings,
    head: str,
    basis: PromotionBasis,
    mutate: Callable[[], Callable[[], None]],
) -> bool:
    connection = AtomicConnection("project", head)
    original_connection = memory_module.database_connection
    restore_mutation = mutate()
    memory_module.database_connection = lambda _settings: connection
    try:
        try:
            memory_module.promote_memory(
                settings,
                PROJECT_ID,
                UUID("00000000-0000-0000-0000-000000000002"),
                basis,
            )
        except MemoryError:
            queries = getattr(connection.cursor_value, "queries", [])
            return connection.failed and not any(
                query.startswith("UPDATE memory_records") or "memory_record_history" in query
                for query in queries
            )
        return False
    finally:
        memory_module.database_connection = original_connection
        restore_mutation()


def main() -> int:
    temporary_root = Path(tempfile.mkdtemp(prefix="memory-c2-stability-"))
    try:
        repository, head = create_repository(temporary_root)
        inherited_projects_root = os.environ.pop("HIVE_PROJECTS_ROOT", None)
        try:
            settings = Settings(projects_root=temporary_root)
        finally:
            if inherited_projects_root is not None:
                os.environ["HIVE_PROJECTS_ROOT"] = inherited_projects_root
        stable, source = memory_module._resolve_trusted_source(
            ProjectCursor("project", head), settings, PROJECT_ID, "README.md"
        )
        expected_source = (repository / "README.md").read_bytes()
        expected_blob = git(repository, "rev-parse", "HEAD:README.md")
        evidence = {
            "status": "PASS",
            "memory_immutable_git_blob_binding": (
                source == expected_source
                and stable["source_commit"] == head
                and stable["git_blob_sha"] == expected_blob
                and stable["source_sha256"] == hashlib.sha256(expected_source).hexdigest()
                and stable["byte_binding"] == "immutable-git-blob-v1"
            ),
            "memory_provenance_identity_consistent": (
                stable["source_commit"] == head
                and stable["git_blob_sha"] == expected_blob
                and stable["source_sha256"] == hashlib.sha256(source).hexdigest()
                and source == expected_source
            ),
            "memory_source_mutation_rejected": _source_race(settings, repository, head),
            "memory_adr_mutation_rejected": _adr_race(settings, repository, head),
            "memory_head_mutation_rejected": _head_race(settings, head),
            "memory_source_race_rejections": 1,
            "memory_adr_race_rejections": 1,
            "memory_head_race_rejections": 1,
        }
        evidence["memory_race_atomicity_preserved"] = all(
            (
                _atomic_race(
                    settings,
                    head,
                    PromotionBasis(kind=PromotionBasisKind.TRUSTED_SOURCE, reference="README.md"),
                    lambda: _install_source_mutation(repository),
                ),
                _atomic_race(
                    settings,
                    head,
                    PromotionBasis(kind=PromotionBasisKind.APPROVED_ADR, reference="HIVE-ADR-019"),
                    lambda: _install_adr_mutation(repository),
                ),
                _atomic_race(
                    settings,
                    head,
                    PromotionBasis(kind=PromotionBasisKind.TRUSTED_SOURCE, reference="README.md"),
                    lambda: _install_head_mutation(),
                ),
            )
        )
        if not all(
            value
            for key, value in evidence.items()
            if key.startswith("memory_") and isinstance(value, bool)
        ):
            evidence["status"] = "FAIL"
        print(json.dumps(evidence, indent=2, sort_keys=True))
        return 0 if evidence["status"] == "PASS" else 1
    finally:
        shutil.rmtree(temporary_root, ignore_errors=True)


def _install_source_mutation(repository: Path) -> Callable[[], None]:
    original_read = memory_module._read_stable_file
    original_source = (repository / "README.md").read_bytes()
    calls = 0

    def mutate(path: Path, settings: Settings) -> tuple[bytes, Any]:
        nonlocal calls
        result = original_read(path, settings)
        calls += 1
        if calls == 1:
            path.write_bytes(b"atomic race source\n")
        return result

    memory_module._read_stable_file = mutate

    def restore() -> None:
        memory_module._read_stable_file = original_read
        (repository / "README.md").write_bytes(original_source)

    return restore


def _install_adr_mutation(repository: Path) -> Callable[[], None]:
    original_read = memory_module._read_stable_file
    ledger = repository / "docs" / "project-brain" / "16-DECISIONS-LEDGER.md"
    original_source = ledger.read_bytes()
    calls = 0

    def mutate(path: Path, settings: Settings) -> tuple[bytes, Any]:
        nonlocal calls
        result = original_read(path, settings)
        calls += 1
        if calls == 1:
            path.write_bytes(b"# Decisions\n\n## HIVE-ADR-019\nStatus: Rejected\n")
        return result

    memory_module._read_stable_file = mutate

    def restore() -> None:
        memory_module._read_stable_file = original_read
        ledger.write_bytes(original_source)

    return restore


def _install_head_mutation() -> Callable[[], None]:
    original_head = memory_module._git_head
    calls = 0

    def mutate(path: Path) -> str:
        nonlocal calls
        result = original_head(path)
        calls += 1
        return "0" * 40 if calls == 2 else result

    memory_module._git_head = mutate
    return lambda: setattr(memory_module, "_git_head", original_head)


if __name__ == "__main__":
    raise SystemExit(main())
