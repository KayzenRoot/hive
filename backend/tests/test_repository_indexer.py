import hashlib
import subprocess
from pathlib import Path

import pytest

from app.config import Settings
from app.repository_indexer import (
    RepositoryIndexingError,
    _assert_snapshot_stable,
    _collect_inventory,
    parse_python_symbols,
)


def git(repository: Path, arguments: list[str]) -> None:
    subprocess.run(["git", "-C", str(repository), *arguments], check=True, capture_output=True)


def git_output(repository: Path, arguments: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_python_parser_emits_qualified_nested_symbols() -> None:
    source = (
        b"class Outer:\n"
        b"    def method(self):\n"
        b"        def nested():\n"
        b"            pass\n"
        b"        return nested\n"
        b"\n"
        b"async def top():\n"
        b"    pass\n"
    )

    symbols = parse_python_symbols("sample.py", source)

    assert [(symbol.qualified_name, symbol.kind) for symbol in symbols] == [
        ("Outer", "class"),
        ("Outer.method", "function"),
        ("Outer.method.nested", "function"),
        ("top", "async_function"),
    ]
    assert symbols[1].line_start == 2
    assert symbols[1].line_end == 5
    assert symbols[2].parent_qualified_name == "Outer.method"


def test_malformed_python_fails_before_durable_reconcile() -> None:
    with pytest.raises(RepositoryIndexingError) as error:
        parse_python_symbols("broken.py", b"def broken(:\n    pass\n")

    assert error.value.code == "python_syntax_error"


def test_inventory_contains_only_cached_git_files(tmp_path: Path) -> None:
    repository = tmp_path / "sample"
    repository.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repository)], check=True, capture_output=True)
    git(repository, ["config", "user.email", "test@example.invalid"])
    git(repository, ["config", "user.name", "HIVE Tests"])
    (repository / "tracked.py").write_text("def tracked():\n    pass\n", encoding="utf-8")
    git(repository, ["add", "tracked.py"])
    git(repository, ["commit", "-m", "initial"])
    (repository / "untracked.py").write_text("def ignored():\n    pass\n", encoding="utf-8")

    snapshot = _collect_inventory(Settings(projects_root=tmp_path), repository)

    assert [entry.path for entry in snapshot.files] == ["tracked.py"]
    assert snapshot.files[0].language == "python"
    assert snapshot.files[0].file_type == "source"


def test_inventory_records_hash_size_git_provenance_and_dirty_status(tmp_path: Path) -> None:
    repository = tmp_path / "provenance"
    repository.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repository)], check=True, capture_output=True)
    git(repository, ["config", "user.email", "test@example.invalid"])
    git(repository, ["config", "user.name", "HIVE Tests"])
    source = b"def tracked():\n    return 1\n"
    (repository / "tracked.py").write_bytes(source)
    git(repository, ["add", "tracked.py"])
    git(repository, ["commit", "-m", "initial"])

    settings = Settings(projects_root=tmp_path)
    snapshot = _collect_inventory(settings, repository)
    entry = snapshot.files[0]

    assert entry.content_sha256 == hashlib.sha256(source).hexdigest()
    assert entry.file_size == len(source)
    assert entry.git_mode == "100644"
    assert entry.git_blob_sha == git_output(repository, ["rev-parse", "HEAD:tracked.py"])
    assert entry.git_status == "CLEAN"

    dirty_source = b"def tracked():\n    return 2\n"
    (repository / "tracked.py").write_bytes(dirty_source)
    dirty_snapshot = _collect_inventory(settings, repository)
    assert dirty_snapshot.files[0].content_sha256 == hashlib.sha256(dirty_source).hexdigest()
    assert dirty_snapshot.files[0].git_status == "MODIFIED"


def test_git_inventory_race_fails_closed_after_discovery(tmp_path: Path) -> None:
    repository = tmp_path / "race"
    repository.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repository)], check=True, capture_output=True)
    git(repository, ["config", "user.email", "test@example.invalid"])
    git(repository, ["config", "user.name", "HIVE Tests"])
    (repository / "tracked.py").write_text("def tracked():\n    pass\n", encoding="utf-8")
    git(repository, ["add", "tracked.py"])
    git(repository, ["commit", "-m", "initial"])

    settings = Settings(projects_root=tmp_path)
    snapshot = _collect_inventory(settings, repository)
    (repository / "staged.py").write_text("def staged():\n    pass\n", encoding="utf-8")
    git(repository, ["add", "staged.py"])

    with pytest.raises(RepositoryIndexingError) as error:
        _assert_snapshot_stable(settings, snapshot)

    assert error.value.code == "git_inventory_changed_during_index"
    assert [entry.path for entry in snapshot.files] == ["tracked.py"]


def test_tracked_symlink_escape_fails_before_reading_outside_bytes(tmp_path: Path) -> None:
    repository = tmp_path / "symlink"
    repository.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repository)], check=True, capture_output=True)
    git(repository, ["config", "user.email", "test@example.invalid"])
    git(repository, ["config", "user.name", "HIVE Tests"])
    (repository / "tracked.py").write_text("def tracked():\n    pass\n", encoding="utf-8")
    git(repository, ["add", "tracked.py"])
    git(repository, ["commit", "-m", "initial"])
    outside = tmp_path / "outside.py"
    outside.write_bytes(b"secret outside source\n")
    link = repository / "escape.py"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink support unavailable: {exc}")
    git(repository, ["add", "escape.py"])

    with pytest.raises(RepositoryIndexingError) as error:
        _collect_inventory(Settings(projects_root=tmp_path), repository)

    assert error.value.code == "tracked_path_unsafe"
