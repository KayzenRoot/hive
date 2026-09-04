"""Deterministic Progressive Disclosure Foundation over Context Manager results."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .repository_indexer import _RepositorySnapshot, _TrackedFile
from .reranking import RerankCandidate


class DisclosureLevel(StrEnum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"
    L5 = "L5"


DISCLOSURE_LEVEL_ORDER: tuple[DisclosureLevel, ...] = (
    DisclosureLevel.L0,
    DisclosureLevel.L1,
    DisclosureLevel.L2,
    DisclosureLevel.L3,
    DisclosureLevel.L4,
    DisclosureLevel.L5,
)
DISCLOSURE_LEVEL_SEMANTICS: dict[DisclosureLevel, str] = {
    DisclosureLevel.L0: "Project capsule",
    DisclosureLevel.L1: "Module summaries",
    DisclosureLevel.L2: "Symbol signatures and dependency metadata",
    DisclosureLevel.L3: "Relevant implementation excerpts",
    DisclosureLevel.L4: "Complete file",
    DisclosureLevel.L5: "Repository-wide investigation",
}

L1_MAX_MODULES = 5
L1_MAX_SUMMARY_CHARS = 160
L2_MAX_SYMBOLS = 8
L2_MAX_SIGNATURE_CHARS = 160
L2_MAX_DEPENDENCIES = 8
L3_MAX_EXCERPTS = 5
L3_MAX_EXCERPT_CHARS = 800
L4_MAX_COMPLETE_FILES = 2
L5_MAX_INVENTORY_ENTRIES = 20
DISCLOSURE_EVIDENCE_CHARS = 160

_PATH_RE = re.compile(r"(?<![A-Za-z0-9_])(?:[\w.-]+/)+[\w.-]+\.[A-Za-z0-9]+")
_SYMBOL_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+")
_FILE_SUFFIX_RE = re.compile(
    r"\.(?:py|pyi|md|rst|txt|toml|ya?ml|json|ts|tsx|js|jsx|css|html|ini|cfg)$",
    re.IGNORECASE,
)
_LEVEL_RE = re.compile(r"^L[0-5]$")
_IMPLEMENTATION_HINTS = (
    "implement",
    "implementation",
    "refactor",
    "function",
    "module summary",
    "module summaries",
    "symbol",
    "excerpt",
    "signature",
    "complete file",
    "source excerpt",
    "fix the",
    "build the",
    "build a",
)
_L5_PHRASES = (
    "repository-wide",
    "entire repository",
    "all tracked files",
    "repository investigation",
    "repository-wide investigation",
)
_L4_PHRASES = (
    "complete file",
    "entire file",
    "full file",
    "whole file",
)
_L3_PHRASES = (
    "implementation excerpt",
    "implementation excerpts",
    "implementation evidence",
    "source excerpt",
    "function body",
)
_L2_PHRASES = (
    "symbol signature",
    "symbol signatures",
    "qualified symbol",
    "dependency metadata",
)
_L1_PHRASES = (
    "module summary",
    "module summaries",
)


class DisclosureInputError(ValueError):
    """The requested disclosure level is outside the L0-L5 contract."""

    def __init__(self, code: str = "invalid_disclosure_level") -> None:
        self.code = code
        super().__init__(code)


class DisclosureConsistencyError(RuntimeError):
    """Disclosure evidence referenced content outside the target project."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        message = f"{code}:{detail}" if detail else code
        super().__init__(message[:256])


class DisclosureEscalation(BaseModel):
    from_level: DisclosureLevel
    to_level: DisclosureLevel
    reason: str
    evidence: str


class DisclosureLevelBound(BaseModel):
    level: DisclosureLevel
    semantics: str
    max_modules: int
    max_symbols: int
    max_excerpts: int
    max_excerpt_characters: int
    max_complete_files: int
    max_complete_file_characters: int
    max_inventory_entries: int


class ProgressiveDisclosure(BaseModel):
    starting_level: DisclosureLevel
    final_level: DisclosureLevel
    escalated: bool
    path: list[DisclosureEscalation] = Field(default_factory=list)
    level_semantics: dict[str, str]
    bounds: DisclosureLevelBound
    truncated: bool
    requested_level: DisclosureLevel | None = None
    requested_level_applied: bool = False
    llm_calls: Literal[0] = 0
    adaptive_token_budget_implemented: Literal[True] = True


class CompleteFileExcerpt(BaseModel):
    path: str
    source_content_sha256: str
    git_blob_sha: str | None
    text: str
    truncated: bool


class RepositoryInventoryEntry(BaseModel):
    path: str
    file_size: int
    source_content_sha256: str


class ModuleSummary(BaseModel):
    path: str
    language: str | None
    source_kind: str
    structure: str
    symbols: list[str]
    tests: list[str]
    source_content_sha256: str
    git_blob_sha: str | None


class SymbolSignature(BaseModel):
    qualified_name: str
    kind: str
    signature: str
    class_name: str | None
    bases: list[str] = Field(default_factory=list)
    path: str
    start_line: int
    end_line: int
    source_content_sha256: str
    git_blob_sha: str | None


class DependencyEdge(BaseModel):
    source_path: str
    imported_module: str
    names: list[str] = Field(default_factory=list)
    kind: str


class DisclosurePresentation(BaseModel):
    disclosure: ProgressiveDisclosure
    files: list[Any]
    symbols: list[Any]
    tests: list[Any]
    results: list[RerankCandidate]
    module_summaries: list[ModuleSummary]
    symbol_signatures: list[SymbolSignature]
    dependencies: list[DependencyEdge]
    complete_files: list[CompleteFileExcerpt]
    inventory: list[RepositoryInventoryEntry]


def parse_disclosure_level(value: object) -> DisclosureLevel:
    if isinstance(value, DisclosureLevel):
        return value
    if not isinstance(value, str) or not _LEVEL_RE.fullmatch(value):
        raise DisclosureInputError("invalid_disclosure_level")
    return DisclosureLevel(value)


def disclosure_level_bound(level: DisclosureLevel) -> DisclosureLevelBound:
    index = DISCLOSURE_LEVEL_ORDER.index(level)
    return DisclosureLevelBound(
        level=level,
        semantics=DISCLOSURE_LEVEL_SEMANTICS[level],
        max_modules=L1_MAX_MODULES if index >= 1 else 0,
        max_symbols=L2_MAX_SYMBOLS if index >= 2 else 0,
        max_excerpts=L3_MAX_EXCERPTS if index >= 3 else 0,
        max_excerpt_characters=L3_MAX_EXCERPT_CHARS if index >= 3 else 0,
        max_complete_files=L4_MAX_COMPLETE_FILES if index >= 4 else 0,
        max_complete_file_characters=0,
        max_inventory_entries=L5_MAX_INVENTORY_ENTRIES if index >= 5 else 0,
    )


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def _contains_phrase(text: str, phrases: Sequence[str]) -> bool:
    normalized = _normalize(text)
    return any(phrase in normalized for phrase in phrases)


def _mentioned_paths(text: str) -> tuple[str, ...]:
    return tuple(sorted({match.group(0).replace("\\", "/") for match in _PATH_RE.finditer(text)}))


def _mentioned_symbols(text: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                match.group(0)
                for match in _SYMBOL_RE.finditer(text)
                if not _FILE_SUFFIX_RE.search(match.group(0))
            }
        )
    )


def _max_level(*levels: DisclosureLevel) -> DisclosureLevel:
    return max(levels, key=lambda level: DISCLOSURE_LEVEL_ORDER.index(level))


def _task_corpus(
    title: str | None,
    constraints: Sequence[str],
    acceptance_criteria: Sequence[str],
    task_text: str,
) -> str:
    return " ".join((title or "", " ".join(constraints), " ".join(acceptance_criteria), task_text))


def required_level_from_text(text: str) -> DisclosureLevel:
    if _contains_phrase(text, _L5_PHRASES):
        return DisclosureLevel.L5
    if _contains_phrase(text, _L4_PHRASES):
        return DisclosureLevel.L4
    if _contains_phrase(text, _L3_PHRASES):
        return DisclosureLevel.L3
    if _contains_phrase(text, _L2_PHRASES) or _mentioned_symbols(text):
        return DisclosureLevel.L2
    if _contains_phrase(text, _L1_PHRASES) or _mentioned_paths(text):
        return DisclosureLevel.L1
    return DisclosureLevel.L0


def _is_implementation_task(text: str) -> bool:
    return _contains_phrase(text, _IMPLEMENTATION_HINTS)


def _has_symbol_evidence(symbols: Sequence[Any], results: Sequence[Any]) -> bool:
    if any(getattr(item, "qualified_symbol", None) for item in symbols):
        return True
    return any(getattr(item, "qualified_symbol", None) for item in results)


def _has_file_evidence(files: Sequence[Any], results: Sequence[Any]) -> bool:
    if any(getattr(item, "path", None) for item in files):
        return True
    return any(getattr(item, "path", None) for item in results)


def starting_level(
    title: str | None,
    constraints: Sequence[str],
    task_text: str,
    acceptance_criteria: Sequence[str] = (),
    files: Sequence[Any] = (),
    symbols: Sequence[Any] = (),
    tests: Sequence[Any] = (),
    results: Sequence[Any] = (),
    requested_level: object | None = None,
) -> DisclosureLevel:
    corpus = _task_corpus(title, constraints, acceptance_criteria, task_text)
    text_level = required_level_from_text(corpus)
    evidence_level = DisclosureLevel.L0
    if text_level == DisclosureLevel.L0 and _is_implementation_task(corpus):
        if _has_symbol_evidence(symbols, results) or tests:
            evidence_level = DisclosureLevel.L2
        elif _has_file_evidence(files, results):
            evidence_level = DisclosureLevel.L1
    start = _max_level(text_level, evidence_level)
    if requested_level is not None:
        start = _max_level(start, parse_disclosure_level(requested_level))
    return start


def _next_level(level: DisclosureLevel) -> DisclosureLevel | None:
    index = DISCLOSURE_LEVEL_ORDER.index(level)
    if index >= len(DISCLOSURE_LEVEL_ORDER) - 1:
        return None
    return DISCLOSURE_LEVEL_ORDER[index + 1]


def _bounded_evidence(value: str) -> str:
    compact = " ".join(value.split())
    if len(compact) <= DISCLOSURE_EVIDENCE_CHARS:
        return compact
    return compact[:DISCLOSURE_EVIDENCE_CHARS]


def _parse_python(entry: _TrackedFile) -> ast.AST | None:
    suffix = Path(entry.path).suffix.casefold()
    if entry.language != "python" and suffix != ".py":
        return None
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(entry.source).readline)
        return ast.parse(entry.source.decode(encoding), filename=entry.path, mode="exec")
    except (LookupError, SyntaxError, UnicodeError, ValueError):
        return None


def _unparse(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return getattr(node, "id", "") or type(node).__name__


def _module_symbols(tree: ast.AST) -> list[tuple[str, str, ast.AST]]:
    records: list[tuple[str, str, ast.AST]] = []

    def walk(nodes: Sequence[ast.stmt], parent: str | None) -> None:
        for node in nodes:
            if isinstance(node, ast.ClassDef):
                qualified = f"{parent}.{node.name}" if parent else node.name
                records.append((qualified, "class", node))
                walk(node.body, qualified)
            elif isinstance(node, ast.FunctionDef):
                qualified = f"{parent}.{node.name}" if parent else node.name
                records.append((qualified, "function", node))
            elif isinstance(node, ast.AsyncFunctionDef):
                qualified = f"{parent}.{node.name}" if parent else node.name
                records.append((qualified, "async_function", node))

    walk(getattr(tree, "body", []), None)
    return records


def _format_signature(name: str, node: ast.AST) -> str:
    if isinstance(node, ast.ClassDef):
        bases = [_unparse(base) for base in node.bases]
        rendered = f"class {name}({', '.join(bases)})" if bases else f"class {name}"
        return rendered[:L2_MAX_SIGNATURE_CHARS]
    if isinstance(node, ast.AsyncFunctionDef):
        return f"async def {name}({_unparse(node.args)})"[:L2_MAX_SIGNATURE_CHARS]
    if isinstance(node, ast.FunctionDef):
        return f"def {name}({_unparse(node.args)})"[:L2_MAX_SIGNATURE_CHARS]
    return name[:L2_MAX_SIGNATURE_CHARS]


def _import_edges(path: str, tree: ast.AST) -> list[DependencyEdge]:
    edges: list[DependencyEdge] = []
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Import):
            for alias in node.names:
                edges.append(
                    DependencyEdge(
                        source_path=path,
                        imported_module=alias.name,
                        names=[alias.asname or alias.name],
                        kind="import",
                    )
                )
        elif isinstance(node, ast.ImportFrom) and node.module:
            edges.append(
                DependencyEdge(
                    source_path=path,
                    imported_module=node.module,
                    names=[alias.name for alias in node.names],
                    kind="import_from",
                )
            )
    return edges[:L2_MAX_DEPENDENCIES]


def _snapshot_contains_symbol(snapshot: _RepositorySnapshot, qualified: str) -> bool:
    short = qualified.rsplit(".", 1)[-1]
    for entry in snapshot.files:
        tree = _parse_python(entry)
        if tree is None:
            continue
        names = {name for name, _kind, _node in _module_symbols(tree)}
        if qualified in names or any(name.endswith(f".{short}") or name == short for name in names):
            return True
    return False


def _snapshot_entry(snapshot: _RepositorySnapshot, path: str | None) -> _TrackedFile | None:
    if not path:
        return None
    for entry in snapshot.files:
        if entry.path == path:
            return entry
    return None


def _linked_tests(path: str, tests: Sequence[Any]) -> list[str]:
    stem = Path(path).stem
    linked: list[str] = []
    for item in tests:
        test_path = getattr(item, "path", None)
        if not test_path:
            continue
        if stem in test_path or path.rsplit("/", 1)[-1] in test_path:
            linked.append(test_path)
    return linked[:L2_MAX_SYMBOLS]


def _module_summaries(
    snapshot: _RepositorySnapshot,
    files: Sequence[Any],
    tests: Sequence[Any],
    bound: DisclosureLevelBound,
) -> tuple[list[ModuleSummary], bool]:
    summaries: list[ModuleSummary] = []
    truncated = len(files) > bound.max_modules
    for item in files[: bound.max_modules]:
        path = getattr(item, "path", None)
        entry = _snapshot_entry(snapshot, path)
        if path is None:
            continue
        if entry is None:
            structure = "unresolved module; snapshot identity missing"
            summaries.append(
                ModuleSummary(
                    path=path,
                    language=None,
                    source_kind=getattr(item, "source_kind", "REPOSITORY_FILE"),
                    structure=structure[:L1_MAX_SUMMARY_CHARS],
                    symbols=[],
                    tests=_linked_tests(path, tests),
                    source_content_sha256=getattr(item, "source_content_sha256", ""),
                    git_blob_sha=None,
                )
            )
            continue
        tree = _parse_python(entry)
        records = _module_symbols(tree) if tree is not None else []
        classes = sum(1 for _name, kind, _node in records if kind == "class")
        functions = len(records) - classes
        structure = (
            f"{entry.language or 'unknown'} {entry.file_type}; "
            f"symbols={len(records)}; classes={classes}; functions={functions}"
        )
        summaries.append(
            ModuleSummary(
                path=entry.path,
                language=entry.language,
                source_kind=entry.file_type,
                structure=structure[:L1_MAX_SUMMARY_CHARS],
                symbols=[name for name, _kind, _node in records[:L2_MAX_SYMBOLS]],
                tests=_linked_tests(entry.path, tests),
                source_content_sha256=entry.content_sha256,
                git_blob_sha=entry.git_blob_sha,
            )
        )
    return summaries, truncated


def _symbol_payload(
    snapshot: _RepositorySnapshot,
    symbols: Sequence[Any],
    files: Sequence[Any],
    bound: DisclosureLevelBound,
) -> tuple[list[SymbolSignature], list[DependencyEdge], bool]:
    signatures: list[SymbolSignature] = []
    dependencies: list[DependencyEdge] = []
    seen_paths: set[str] = set()
    truncated = len(symbols) > bound.max_symbols
    for item in symbols[: bound.max_symbols]:
        path = getattr(item, "path", None)
        qualified = getattr(item, "qualified_symbol", None)
        entry = _snapshot_entry(snapshot, path)
        if path is None or qualified is None or entry is None:
            continue
        tree = _parse_python(entry)
        records = _module_symbols(tree) if tree is not None else []
        match = next((record for record in records if record[0] == qualified), None)
        if match is None:
            short = qualified.rsplit(".", 1)[-1]
            match = next((record for record in records if record[0].endswith(f".{short}")), None)
        if match is None:
            continue
        name, kind, node = match
        parent = name.rsplit(".", 1)[0] if "." in name else None
        bases = [_unparse(base) for base in node.bases] if isinstance(node, ast.ClassDef) else []
        signatures.append(
            SymbolSignature(
                qualified_name=name,
                kind=kind,
                signature=_format_signature(name.rsplit(".", 1)[-1], node),
                class_name=parent if kind != "class" else name,
                bases=bases,
                path=entry.path,
                start_line=int(getattr(node, "lineno", 1)),
                end_line=int(getattr(node, "end_lineno", getattr(node, "lineno", 1))),
                source_content_sha256=entry.content_sha256,
                git_blob_sha=entry.git_blob_sha,
            )
        )
        if tree is not None and entry.path not in seen_paths:
            seen_paths.add(entry.path)
            dependencies.extend(_import_edges(entry.path, tree))
    if not dependencies:
        for item in files[: bound.max_modules]:
            path = getattr(item, "path", None)
            entry = _snapshot_entry(snapshot, path)
            if entry is None or entry.path in seen_paths:
                continue
            tree = _parse_python(entry)
            if tree is None:
                continue
            seen_paths.add(entry.path)
            dependencies.extend(_import_edges(entry.path, tree))
            if len(dependencies) >= L2_MAX_DEPENDENCIES:
                break
    return signatures, dependencies[:L2_MAX_DEPENDENCIES], truncated


def _assert_project_paths(
    snapshot: _RepositorySnapshot,
    paths: Sequence[str | None],
) -> None:
    tracked = {entry.path for entry in snapshot.files}
    escaped = sorted({path for path in paths if path and path not in tracked})
    if escaped:
        raise DisclosureConsistencyError(
            "cross_project_disclosure_evidence",
            ",".join(escaped)[:128],
        )


def _evidence_paths(
    files: Sequence[Any],
    symbols: Sequence[Any],
    results: Sequence[Any],
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for item in (*files, *symbols, *results):
        path = getattr(item, "path", None)
        if path and path not in seen:
            seen.add(path)
            ordered.append(path)
    return ordered


def _copy_with_symbol(item: Any, *, path: str, qualified: str) -> Any:
    if hasattr(item, "model_copy"):
        return item.model_copy(update={"path": path, "qualified_symbol": qualified})
    return item


def _augment_symbols_from_snapshot(
    *,
    snapshot: _RepositorySnapshot,
    corpus: str,
    files: Sequence[Any],
    symbols: Sequence[Any],
    limit: int,
) -> list[Any]:
    mentioned = _mentioned_symbols(corpus)
    if not mentioned or limit <= 0:
        return list(symbols[:limit])
    merged: list[Any] = list(symbols)
    existing = {
        (getattr(item, "path", None), getattr(item, "qualified_symbol", None)) for item in merged
    }
    donors: dict[str, Any] = {}
    for item in (*symbols, *files):
        path = getattr(item, "path", None)
        if path and path not in donors:
            donors[path] = item
    for entry in snapshot.files:
        donor = donors.get(entry.path)
        if donor is None:
            continue
        tree = _parse_python(entry)
        if tree is None:
            continue
        names = [name for name, _kind, _node in _module_symbols(tree)]
        name_set = set(names)
        shorts = {name.rsplit(".", 1)[-1]: name for name in names}
        for required in mentioned:
            match = required if required in name_set else shorts.get(required.rsplit(".", 1)[-1])
            if match is None:
                continue
            key = (entry.path, match)
            if key in existing:
                continue
            existing.add(key)
            merged.append(_copy_with_symbol(donor, path=entry.path, qualified=match))
            if len(merged) >= limit:
                return merged[:limit]
    return merged[:limit]


def _paths_matching_symbols(
    snapshot: _RepositorySnapshot,
    paths: Sequence[str],
    required_symbols: Sequence[str],
) -> list[str]:
    matched: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if path in seen:
            continue
        entry = _snapshot_entry(snapshot, path)
        if entry is None:
            continue
        tree = _parse_python(entry)
        names = {name for name, _kind, _node in _module_symbols(tree)} if tree else set()
        short_names = {name.rsplit(".", 1)[-1] for name in names}
        if any(
            symbol in names or symbol.rsplit(".", 1)[-1] in short_names
            for symbol in required_symbols
        ):
            seen.add(path)
            matched.append(path)
    return matched


def _l4_target_paths(
    *,
    acceptance_criteria: Sequence[str],
    task_text: str,
    files: Sequence[Any],
    symbols: Sequence[Any],
    results: Sequence[Any],
    snapshot: _RepositorySnapshot,
) -> list[str]:
    mentioned = list(_mentioned_paths(" ".join(acceptance_criteria) + " " + task_text))
    if mentioned:
        _assert_project_paths(snapshot, mentioned)
        return mentioned
    tracked = {entry.path for entry in snapshot.files}
    required_symbols = _mentioned_symbols(" ".join(acceptance_criteria) + " " + task_text)
    evidence_paths = [path for path in _evidence_paths(files, symbols, results) if path in tracked]
    if required_symbols:
        matched = _paths_matching_symbols(snapshot, evidence_paths, required_symbols)
        if not matched:
            matched = _paths_matching_symbols(snapshot, sorted(tracked), required_symbols)
        if not matched:
            raise DisclosureConsistencyError("l4_target_unresolved")
        return matched
    if not evidence_paths:
        raise DisclosureConsistencyError("l4_target_unresolved")
    return evidence_paths


def _decode_complete_file_text(entry: _TrackedFile) -> str:
    if b"\x00" in entry.source:
        raise DisclosureConsistencyError("l4_complete_file_not_textual", entry.path)
    suffix = Path(entry.path).suffix.casefold()
    try:
        if entry.language == "python" or suffix in {".py", ".pyi"}:
            encoding, _ = tokenize.detect_encoding(io.BytesIO(entry.source).readline)
            return entry.source.decode(encoding)
        return entry.source.decode("utf-8")
    except (LookupError, UnicodeError, ValueError) as exc:
        raise DisclosureConsistencyError("l4_complete_file_not_textual", entry.path) from exc


def _complete_files(
    snapshot: _RepositorySnapshot,
    requested_paths: Sequence[str],
    bound: DisclosureLevelBound,
) -> tuple[list[CompleteFileExcerpt], bool]:
    excerpts: list[CompleteFileExcerpt] = []
    truncated = len(requested_paths) > bound.max_complete_files
    entries = {entry.path: entry for entry in snapshot.files}
    for path in requested_paths[: bound.max_complete_files]:
        entry = entries.get(path)
        if entry is None:
            raise DisclosureConsistencyError("cross_project_disclosure_evidence", path)
        if entry.git_blob_sha is None:
            raise DisclosureConsistencyError("disclosure_git_identity_missing", path)
        excerpts.append(
            CompleteFileExcerpt(
                path=path,
                source_content_sha256=entry.content_sha256,
                git_blob_sha=entry.git_blob_sha,
                text=_decode_complete_file_text(entry),
                truncated=False,
            )
        )
    return excerpts, truncated


def _inventory(
    snapshot: _RepositorySnapshot,
    bound: DisclosureLevelBound,
) -> tuple[list[RepositoryInventoryEntry], bool]:
    files: tuple[_TrackedFile, ...] = tuple(sorted(snapshot.files, key=lambda item: item.path))
    truncated = len(files) > bound.max_inventory_entries
    entries = [
        RepositoryInventoryEntry(
            path=item.path,
            file_size=item.file_size,
            source_content_sha256=item.content_sha256,
        )
        for item in files[: bound.max_inventory_entries]
    ]
    return entries, truncated


def disclosure_payload_characters(
    module_summaries: Sequence[ModuleSummary],
    symbol_signatures: Sequence[SymbolSignature],
    dependencies: Sequence[DependencyEdge],
    complete_files: Sequence[CompleteFileExcerpt],
    inventory: Sequence[RepositoryInventoryEntry],
) -> int:
    return (
        sum(len(item.structure) + len(item.path) for item in module_summaries)
        + sum(len(item.signature) + len(item.qualified_name) for item in symbol_signatures)
        + sum(len(item.source_path) + len(item.imported_module) for item in dependencies)
        + sum(len(item.text) for item in complete_files)
        + sum(len(item.path) for item in inventory)
    )


def _post_materialize_insufficiency(
    level: DisclosureLevel,
    *,
    corpus: str,
    signatures: Sequence[SymbolSignature],
    results: Sequence[RerankCandidate],
    complete_files: Sequence[CompleteFileExcerpt],
    snapshot: _RepositorySnapshot,
) -> tuple[str, str] | None:
    required_symbols = _mentioned_symbols(corpus)
    if level == DisclosureLevel.L2 and required_symbols:
        materialized = {item.qualified_name for item in signatures}
        short = {name.rsplit(".", 1)[-1] for name in materialized}
        missing = [
            name
            for name in required_symbols
            if name not in materialized and name.rsplit(".", 1)[-1] not in short
        ]
        if missing:
            return (
                "required_signature_unresolved",
                _bounded_evidence(" ".join(missing)),
            )
    if level == DisclosureLevel.L3 and required_symbols:
        blob = " ".join(item.snippet for item in results)
        missing = [
            name
            for name in required_symbols
            if name not in blob and name.rsplit(".", 1)[-1] not in blob
        ]
        present_in_source = [name for name in missing if _snapshot_contains_symbol(snapshot, name)]
        if present_in_source:
            return (
                "implementation_excerpt_unavailable",
                _bounded_evidence(" ".join(present_in_source)),
            )
    if level == DisclosureLevel.L4 and not complete_files:
        return (
            "complete_file_unresolved",
            _bounded_evidence("complete file selected without payload"),
        )
    return None


def decide_disclosure(
    *,
    title: str | None,
    constraints: Sequence[str],
    acceptance_criteria: Sequence[str],
    task_text: str,
    files: Sequence[Any],
    symbols: Sequence[Any],
    tests: Sequence[Any] = (),
    results: Sequence[Any] = (),
    requested_level: object | None = None,
) -> tuple[DisclosureLevel, DisclosureLevel, list[DisclosureEscalation]]:
    start = starting_level(
        title,
        constraints,
        task_text,
        acceptance_criteria=acceptance_criteria,
        files=files,
        symbols=symbols,
        tests=tests,
        results=results,
        requested_level=requested_level,
    )
    return start, start, []


def apply_disclosure(
    *,
    title: str | None,
    constraints: Sequence[str],
    acceptance_criteria: Sequence[str],
    task_text: str,
    files: Sequence[Any],
    symbols: Sequence[Any],
    tests: Sequence[Any],
    results: Sequence[RerankCandidate],
    snapshot: _RepositorySnapshot,
    requested_level: object | None = None,
) -> DisclosurePresentation:
    parsed_request = (
        parse_disclosure_level(requested_level) if requested_level is not None else None
    )
    start = starting_level(
        title,
        constraints,
        task_text,
        acceptance_criteria=acceptance_criteria,
        files=files,
        symbols=symbols,
        tests=tests,
        results=results,
        requested_level=requested_level,
    )
    corpus = _task_corpus(title, constraints, acceptance_criteria, task_text)
    current = start
    path: list[DisclosureEscalation] = []
    presented_files: list[Any] = []
    presented_symbols: list[Any] = []
    presented_tests: list[Any] = []
    presented_results: list[RerankCandidate] = []
    module_summaries: list[ModuleSummary] = []
    symbol_signatures: list[SymbolSignature] = []
    dependencies: list[DependencyEdge] = []
    complete_files: list[CompleteFileExcerpt] = []
    inventory: list[RepositoryInventoryEntry] = []
    truncated = False
    bound = disclosure_level_bound(current)
    while True:
        bound = disclosure_level_bound(current)
        presented_files = list(files[: bound.max_modules]) if bound.max_modules else []
        presented_symbols = (
            _augment_symbols_from_snapshot(
                snapshot=snapshot,
                corpus=corpus,
                files=presented_files,
                symbols=list(symbols[: bound.max_symbols]),
                limit=bound.max_symbols,
            )
            if bound.max_symbols
            else []
        )
        presented_tests = list(tests[: bound.max_symbols]) if bound.max_symbols else []
        presented_results = []
        truncated = (
            len(files) > bound.max_modules
            or len(symbols) > bound.max_symbols
            or len(tests) > bound.max_symbols
        )
        module_summaries = []
        symbol_signatures = []
        dependencies = []
        complete_files = []
        inventory = []
        if bound.max_modules:
            module_summaries, summary_truncated = _module_summaries(
                snapshot, presented_files, tests, bound
            )
            truncated |= summary_truncated
        if bound.max_symbols:
            symbol_signatures, dependencies, symbol_truncated = _symbol_payload(
                snapshot, presented_symbols, presented_files, bound
            )
            truncated |= symbol_truncated
        if bound.max_excerpts:
            for candidate in results[: bound.max_excerpts]:
                snippet = candidate.snippet
                snippet_truncated = len(snippet) > bound.max_excerpt_characters
                if snippet_truncated:
                    snippet = snippet[: bound.max_excerpt_characters]
                    truncated = True
                presented_results.append(candidate.model_copy(update={"snippet": snippet}))
            truncated |= len(results) > bound.max_excerpts
        elif bound.max_modules:
            presented_results = [
                candidate.model_copy(update={"snippet": ""})
                for candidate in results[: bound.max_modules]
            ]
            truncated |= len(results) > bound.max_modules
        if bound.max_complete_files:
            requested_paths = _l4_target_paths(
                acceptance_criteria=acceptance_criteria,
                task_text=task_text,
                files=files,
                symbols=symbols,
                results=results,
                snapshot=snapshot,
            )
            complete_files, file_truncated = _complete_files(snapshot, requested_paths, bound)
            truncated |= file_truncated
            if not complete_files:
                raise DisclosureConsistencyError("l4_target_unresolved")
        if bound.max_inventory_entries:
            inventory, inventory_truncated = _inventory(snapshot, bound)
            truncated |= inventory_truncated
        reason = _post_materialize_insufficiency(
            current,
            corpus=corpus,
            signatures=symbol_signatures,
            results=presented_results,
            complete_files=complete_files,
            snapshot=snapshot,
        )
        if reason is None:
            break
        nxt = _next_level(current)
        if nxt is None:
            if current == DisclosureLevel.L4 and not complete_files:
                raise DisclosureConsistencyError("l4_target_unresolved")
            break
        code, evidence = reason
        path.append(
            DisclosureEscalation(
                from_level=current,
                to_level=nxt,
                reason=code,
                evidence=evidence,
            )
        )
        current = nxt
    disclosure = ProgressiveDisclosure(
        starting_level=start,
        final_level=current,
        escalated=bool(path),
        path=path,
        level_semantics={level.value: label for level, label in DISCLOSURE_LEVEL_SEMANTICS.items()},
        bounds=bound,
        truncated=truncated,
        requested_level=parsed_request,
        requested_level_applied=parsed_request is not None,
        llm_calls=0,
        adaptive_token_budget_implemented=True,
    )
    return DisclosurePresentation(
        disclosure=disclosure,
        files=presented_files,
        symbols=presented_symbols,
        tests=presented_tests,
        results=presented_results,
        module_summaries=module_summaries,
        symbol_signatures=symbol_signatures,
        dependencies=dependencies,
        complete_files=complete_files,
        inventory=inventory,
    )
