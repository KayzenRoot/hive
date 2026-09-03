"""Deterministic Progressive Disclosure Foundation over Context Manager results."""

from __future__ import annotations

import re
from collections.abc import Sequence
from enum import StrEnum
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
L2_MAX_SYMBOLS = 8
L3_MAX_EXCERPTS = 5
L3_MAX_EXCERPT_CHARS = 800
L4_MAX_COMPLETE_FILES = 2
L4_MAX_COMPLETE_FILE_CHARS = 800
L5_MAX_INVENTORY_ENTRIES = 20
DISCLOSURE_EVIDENCE_CHARS = 160

_PATH_RE = re.compile(r"(?<![A-Za-z0-9_])(?:[\w.-]+/)+[\w.-]+\.[A-Za-z0-9]+")
_SYMBOL_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+")
_FILE_SUFFIX_RE = re.compile(
    r"\.(?:py|pyi|md|rst|txt|toml|ya?ml|json|ts|tsx|js|jsx|css|html|ini|cfg)$",
    re.IGNORECASE,
)
_LEVEL_RE = re.compile(r"^L[0-5]$")
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
    llm_calls: Literal[0] = 0
    adaptive_token_budget_implemented: Literal[False] = False


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


class DisclosurePresentation(BaseModel):
    disclosure: ProgressiveDisclosure
    files: list[Any]
    symbols: list[Any]
    tests: list[Any]
    results: list[RerankCandidate]
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
        max_complete_file_characters=L4_MAX_COMPLETE_FILE_CHARS if index >= 4 else 0,
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


def starting_level(
    title: str | None, constraints: Sequence[str], task_text: str
) -> DisclosureLevel:
    acceptance_start = task_text.casefold().find("## acceptance criteria")
    leading = task_text if acceptance_start == -1 else task_text[:acceptance_start]
    source = " ".join((title or "", " ".join(constraints), leading))
    return required_level_from_text(source)


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


def _insufficiency(
    level: DisclosureLevel,
    acceptance_text: str,
    files: Sequence[Any],
    symbols: Sequence[Any],
    tests: Sequence[Any],
) -> tuple[str, str] | None:
    required = required_level_from_text(acceptance_text)
    paths = _mentioned_paths(acceptance_text)
    mentioned_symbols = _mentioned_symbols(acceptance_text)
    if level == DisclosureLevel.L0 and (
        required != DisclosureLevel.L0 or paths or mentioned_symbols
    ):
        return (
            "required_module_unresolved",
            _bounded_evidence(acceptance_text or "module or path required"),
        )
    if level == DisclosureLevel.L1 and (
        required in {DisclosureLevel.L2, DisclosureLevel.L3, DisclosureLevel.L4, DisclosureLevel.L5}
        or mentioned_symbols
        or (tests and paths)
    ):
        return (
            "required_symbol_unresolved",
            _bounded_evidence(" ".join(mentioned_symbols) or "symbol or test mapping required"),
        )
    if level == DisclosureLevel.L2 and required in {
        DisclosureLevel.L3,
        DisclosureLevel.L4,
        DisclosureLevel.L5,
    }:
        return (
            "acceptance_requires_implementation_excerpt",
            _bounded_evidence(acceptance_text),
        )
    if level == DisclosureLevel.L3 and required in {DisclosureLevel.L4, DisclosureLevel.L5}:
        return (
            "acceptance_requires_complete_file",
            _bounded_evidence(acceptance_text),
        )
    if level == DisclosureLevel.L4 and required == DisclosureLevel.L5:
        return (
            "acceptance_requires_repository_investigation",
            _bounded_evidence(acceptance_text),
        )
    _ = (files, symbols)
    return None


def decide_disclosure(
    *,
    title: str | None,
    constraints: Sequence[str],
    acceptance_criteria: Sequence[str],
    task_text: str,
    files: Sequence[Any],
    symbols: Sequence[Any],
    tests: Sequence[Any],
) -> tuple[DisclosureLevel, DisclosureLevel, list[DisclosureEscalation]]:
    start = starting_level(title, constraints, task_text)
    acceptance_text = " ".join(acceptance_criteria)
    current = start
    path: list[DisclosureEscalation] = []
    while True:
        reason = _insufficiency(current, acceptance_text, files, symbols, tests)
        if reason is None:
            break
        nxt = _next_level(current)
        if nxt is None:
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
    return start, current, path


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
        text = entry.source.decode("utf-8", errors="replace")
        excerpt_truncated = len(text) > bound.max_complete_file_characters
        excerpts.append(
            CompleteFileExcerpt(
                path=path,
                source_content_sha256=entry.content_sha256,
                git_blob_sha=entry.git_blob_sha,
                text=text[: bound.max_complete_file_characters],
                truncated=excerpt_truncated,
            )
        )
        truncated |= excerpt_truncated
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
    if requested_level is not None:
        parse_disclosure_level(requested_level)
    start, final, path = decide_disclosure(
        title=title,
        constraints=constraints,
        acceptance_criteria=acceptance_criteria,
        task_text=task_text,
        files=files,
        symbols=symbols,
        tests=tests,
    )
    bound = disclosure_level_bound(final)
    presented_files = list(files[: bound.max_modules]) if bound.max_modules else []
    presented_symbols = list(symbols[: bound.max_symbols]) if bound.max_symbols else []
    presented_tests = list(tests[: bound.max_symbols]) if bound.max_symbols else []
    presented_results: list[RerankCandidate] = []
    truncated = (
        len(files) > bound.max_modules
        or len(symbols) > bound.max_symbols
        or len(tests) > bound.max_symbols
    )
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
    complete_files: list[CompleteFileExcerpt] = []
    inventory: list[RepositoryInventoryEntry] = []
    if bound.max_complete_files:
        requested_paths = _mentioned_paths(" ".join(acceptance_criteria) + " " + task_text)
        _assert_project_paths(snapshot, requested_paths)
        complete_files, file_truncated = _complete_files(snapshot, requested_paths, bound)
        truncated |= file_truncated
    if bound.max_inventory_entries:
        inventory, inventory_truncated = _inventory(snapshot, bound)
        truncated |= inventory_truncated
    disclosure = ProgressiveDisclosure(
        starting_level=start,
        final_level=final,
        escalated=bool(path),
        path=path,
        level_semantics={level.value: label for level, label in DISCLOSURE_LEVEL_SEMANTICS.items()},
        bounds=bound,
        truncated=truncated,
    )
    return DisclosurePresentation(
        disclosure=disclosure,
        files=presented_files,
        symbols=presented_symbols,
        tests=presented_tests,
        results=presented_results,
        complete_files=complete_files,
        inventory=inventory,
    )
