import subprocess
from pathlib import Path

import pytest

from app.config import Settings
from app.repository_indexer import (
    RepositoryIndexingError,
    _collect_inventory,
    parse_python_symbols,
)


def git(repository: Path, arguments: list[str]) -> None:
    subprocess.run(["git", "-C", str(repository), *arguments], check=True, capture_output=True)


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
