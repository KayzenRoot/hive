"""Deterministic, bounded Context Manager assembly over existing HIVE seams."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, cast
from uuid import UUID

import psycopg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .config import Settings
from .progressive_disclosure import (
    CompleteFileExcerpt,
    DependencyEdge,
    DisclosureConsistencyError,
    DisclosureInputError,
    ModuleSummary,
    ProgressiveDisclosure,
    RepositoryInventoryEntry,
    SymbolSignature,
    apply_disclosure,
    disclosure_payload_characters,
    parse_disclosure_level,
)
from .registry import (
    ProjectPathError,
    ProjectResponse,
    ProjectState,
    get_project,
    normalize_project_path,
)
from .repository_indexer import (
    IndexRunStatus,
    RepositoryIndexingError,
    _assert_snapshot_stable,
    _collect_inventory,
    _RepositorySnapshot,
    _TrackedFile,
    latest_index_run,
)
from .reranking import (
    RerankCandidate,
    RerankerProfile,
    RerankError,
    RerankRequest,
    RerankResponse,
    rerank_search,
)
from .retrieval import (
    MAX_QUERY_CHARS,
    RetrievalProjectNotFoundError,
    RetrievalQueryError,
    RetrievalSyncError,
    corpus_status,
)
from .semantic_retrieval import SemanticError, SemanticState
from .task_intake import (
    ExtractionNotReadyError,
    TaskNotFoundError,
    TaskResponse,
    get_task,
    get_task_text,
)

CONTEXT_CAPSULE_VERSION: Literal["context-capsule-v1"] = "context-capsule-v1"
DEFAULT_CONTEXT_TOP_K = 5
MAX_CONTEXT_TOP_K = 10
MAX_TASK_EXCERPT_CHARS = 4_000
MAX_TASK_SECTION_ITEMS = 20
MAX_TASK_SECTION_ITEM_CHARS = 512
MAX_GOVERNANCE_EXCERPT_CHARS = 1_600
MAX_GOVERNANCE_EXCERPTS = 12
MAX_TOTAL_GOVERNANCE_CHARS = 12_000
MAX_RETRIEVAL_CANDIDATE_POOL = 10
MAX_RETRIEVAL_RESULTS = 5
MAX_TOTAL_RETRIEVAL_CHARS = 6_000
MAX_CAPSULE_CHARS = 24_000
GOVERNANCE_PATHS: tuple[tuple[str, str], ...] = (
    ("CHECKPOINT", "docs/project-brain/13-CHECKPOINT.md"),
    ("SCOPE", "docs/project-brain/03-SCOPE.md"),
    ("DEFINITION_OF_DONE", "docs/project-brain/15-DEFINITION-OF-DONE.md"),
    ("ARCHITECTURE", "docs/project-brain/04-ARCHITECTURE.md"),
    ("DECISIONS", "docs/project-brain/16-DECISIONS-LEDGER.md"),
)
MANDATORY_GOVERNANCE_KINDS: tuple[str, ...] = tuple(kind for kind, _path in GOVERNANCE_PATHS)
CHECKPOINT_SECTION_GROUPS: tuple[tuple[str, frozenset[str]], ...] = (
    ("STATUS", frozenset({"status"})),
    ("VERSION", frozenset({"version", "version phase"})),
    ("PHASE", frozenset({"phase", "version phase"})),
    ("OBJECTIVE", frozenset({"objective"})),
    ("IN PROGRESS", frozenset({"in progress", "inprogress"})),
    ("BLOCKERS", frozenset({"blockers", "blocker"})),
    ("NEXT STEP", frozenset({"next step", "next"})),
)
_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", re.MULTILINE)
_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_TEST_PATH_RE = re.compile(
    r"(^|/)(tests?|__tests__)(/|$)|(^|/)(test_[^/]+|[^/]+_test|[^/]+\.(test|spec))\."
)


class ContextManagerError(RuntimeError):
    """Bounded, safe Context Manager failure."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        message = f"{code}:{detail}" if detail else code
        super().__init__(message[:256])


class ContextProjectNotFoundError(LookupError):
    """The requested project does not exist."""


class ContextInputError(ValueError):
    """The Context Manager request is outside its bounded contract."""


class ContextStaleError(ContextManagerError):
    """The project, source, index, or corpus state is not coherent."""


class ContextGovernanceError(ContextManagerError):
    """The target project does not have safe HIVE governance sources."""


class ContextRetrievalError(ContextManagerError):
    """The existing retrieval service could not produce a safe response."""


class ContextBoundsError(ContextManagerError):
    """The assembled capsule cannot satisfy its fixed size limits."""


class GovernanceAuthority(StrEnum):
    CANONICAL_GOVERNANCE = "CANONICAL_GOVERNANCE"


class TaskTrust(StrEnum):
    TASK_INPUT_NONCANONICAL = "TASK_INPUT_NONCANONICAL"


class RepositoryEvidenceTrust(StrEnum):
    REPOSITORY_RETRIEVAL_EVIDENCE = "REPOSITORY_RETRIEVAL_EVIDENCE"


class ContextRequest(BaseModel):
    top_k: int = Field(default=DEFAULT_CONTEXT_TOP_K, ge=1, le=MAX_CONTEXT_TOP_K)
    disclosure_level: str | None = None


class ContextProject(BaseModel):
    project_id: UUID
    name: str
    relative_path: str
    current_state: ProjectState
    repository_head_sha: str
    registered_head_sha: str
    working_tree_clean: bool | None
    index_run_id: UUID
    corpus_run_id: UUID


class ContextTask(BaseModel):
    task_id: UUID
    project_id: UUID
    title: str | None
    source_type: str
    original_filename: str | None
    extraction_method: str
    extraction_version: str
    original_blob_sha256: str
    extracted_text_sha256: str
    excerpt: str
    excerpt_truncated: bool
    trust_classification: TaskTrust


class GovernanceExcerpt(BaseModel):
    kind: str
    path: str
    source_content_sha256: str
    git_blob_sha: str
    git_head_sha: str
    section_heading: str
    start_line: int
    end_line: int
    start_char: int
    end_char: int
    text: str
    authority: GovernanceAuthority
    trust_classification: GovernanceAuthority
    truncated: bool


class TaskDerivedStructure(BaseModel):
    constraints: list[str]
    acceptance_criteria: list[str]
    trust_classification: TaskTrust


class ContextReferenceProjection(BaseModel):
    reference_id: UUID
    source_kind: str
    path: str | None
    qualified_symbol: str | None
    source_content_sha256: str
    pre_rerank_rank: int
    rerank_rank: int
    trust_classification: RepositoryEvidenceTrust


class ContextRetrieval(BaseModel):
    query: str
    normalized_query: str
    rerank_state: str
    hybrid_state: str
    semantic_state: SemanticState
    fallback_reason: str | None
    candidate_pool: int
    serialization_version: str
    reranker_profile: RerankerProfile | None
    results: list[RerankCandidate]


class ContextBounds(BaseModel):
    task_characters_included: int
    governance_characters_included: int
    retrieval_characters_included: int
    total_emitted_context_characters: int
    serialized_capsule_characters: int
    governance_excerpt_count: int
    retrieval_result_count: int
    task_constraint_count: int
    task_acceptance_criteria_count: int
    file_projection_count: int
    symbol_projection_count: int
    test_projection_count: int
    disclosure_characters_included: int = 0
    task_excerpt_truncated: bool
    governance_excerpt_truncated: bool
    retrieval_truncated: bool
    capsule_truncated: bool


class ContextCapsule(BaseModel):
    version: Literal["context-capsule-v1"] = CONTEXT_CAPSULE_VERSION
    project: ContextProject
    task: ContextTask
    governance: list[GovernanceExcerpt]
    task_derived: TaskDerivedStructure
    retrieval: ContextRetrieval
    files: list[ContextReferenceProjection]
    symbols: list[ContextReferenceProjection]
    tests: list[ContextReferenceProjection]
    complete_files: list[CompleteFileExcerpt] = Field(default_factory=list)
    inventory: list[RepositoryInventoryEntry] = Field(default_factory=list)
    module_summaries: list[ModuleSummary] = Field(default_factory=list)
    symbol_signatures: list[SymbolSignature] = Field(default_factory=list)
    dependencies: list[DependencyEdge] = Field(default_factory=list)
    progressive_disclosure: ProgressiveDisclosure
    bounds: ContextBounds


@dataclass(frozen=True)
class _MarkdownSection:
    heading: str
    level: int
    text: str
    start_line: int
    end_line: int
    start_char: int
    end_char: int


@dataclass(frozen=True)
class _GovernanceSelection:
    excerpts: tuple[GovernanceExcerpt, ...]
    truncated: bool


@dataclass(frozen=True)
class _GovernanceCandidate:
    kind: str
    entry: _TrackedFile
    section: _MarkdownSection
    score: int
    source_index: int
    kind_index: int


@dataclass(frozen=True)
class _SourceState:
    project: ProjectResponse
    snapshot: _RepositorySnapshot
    index_run_id: UUID
    corpus_run_id: UUID


def _tokens(value: str) -> set[str]:
    return {token.casefold() for token in _TOKEN_RE.findall(value)}


def _normalize_heading(value: str) -> str:
    return " ".join(_TOKEN_RE.findall(value.casefold()))


def _parse_markdown_sections(text: str) -> list[_MarkdownSection]:
    matches = list(_HEADING_RE.finditer(text))
    sections: list[_MarkdownSection] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        end_cursor = max(start, end - 1)
        sections.append(
            _MarkdownSection(
                heading=match.group(2).strip(),
                level=len(match.group(1)),
                text=text[start:end],
                start_line=text.count("\n", 0, start) + 1,
                end_line=text.count("\n", 0, end_cursor) + 1,
                start_char=start,
                end_char=end,
            )
        )
    return sections


def _section_score(section: _MarkdownSection, query_tokens: set[str]) -> int:
    heading_tokens = _tokens(section.heading)
    body_tokens = _tokens(section.text)
    return 4 * len(heading_tokens & query_tokens) + len(body_tokens & query_tokens)


def _task_section_items(text: str, headings: frozenset[str]) -> tuple[list[str], bool]:
    sections = _parse_markdown_sections(text)
    section = next(
        (item for item in sections if _normalize_heading(item.heading) in headings),
        None,
    )
    if section is None:
        return [], False
    heading_end = text.find("\n", section.start_char, section.end_char)
    body_start = section.end_char if heading_end == -1 else heading_end + 1
    raw_items = [line.strip() for line in text[body_start : section.end_char].splitlines()]
    items = [item for item in raw_items if item]
    truncated = len(items) > MAX_TASK_SECTION_ITEMS
    bounded = [item[:MAX_TASK_SECTION_ITEM_CHARS] for item in items[:MAX_TASK_SECTION_ITEMS]]
    truncated |= any(
        len(item) > MAX_TASK_SECTION_ITEM_CHARS for item in items[:MAX_TASK_SECTION_ITEMS]
    )
    return bounded, truncated


def _derive_query(
    task: TaskResponse,
    task_text: str,
    constraints: list[str],
    acceptance_criteria: list[str],
) -> tuple[str, str]:
    source_parts = [
        (task.title or "")[:128],
        task_text[:192],
        " ".join(constraints[:2])[:96],
        " ".join(acceptance_criteria[:2])[:96],
    ]
    source = " ".join(part.strip() for part in source_parts if part.strip())
    source = source[:MAX_QUERY_CHARS]
    try:
        from .retrieval import normalize_lexical_query

        normalized = normalize_lexical_query(source)
    except RetrievalQueryError as exc:
        raise ContextInputError("context retrieval query is empty or invalid") from exc
    return normalized.original, normalized.normalized


def _checkpoint_sections(
    sections: list[_MarkdownSection],
) -> list[_MarkdownSection]:
    selected: list[_MarkdownSection] = []
    seen: set[tuple[int, int]] = set()
    for _label, accepted in CHECKPOINT_SECTION_GROUPS:
        match = next(
            (section for section in sections if _normalize_heading(section.heading) in accepted),
            None,
        )
        if match is None:
            raise ContextGovernanceError(
                "missing_governance_section",
                f"CHECKPOINT:{_label}",
            )
        identity = (match.start_char, match.end_char)
        if identity not in seen:
            selected.append(match)
            seen.add(identity)
    return selected


def mandatory_governance_kind_sequence(
    excerpts: Sequence[GovernanceExcerpt],
) -> tuple[str, ...]:
    sequence: list[str] = []
    seen: set[str] = set()
    for excerpt in excerpts:
        if excerpt.kind in seen or excerpt.kind not in MANDATORY_GOVERNANCE_KINDS:
            continue
        sequence.append(excerpt.kind)
        seen.add(excerpt.kind)
    return tuple(sequence)


def _assert_mandatory_governance_coverage(excerpts: Sequence[GovernanceExcerpt]) -> None:
    observed = mandatory_governance_kind_sequence(excerpts)
    if observed != MANDATORY_GOVERNANCE_KINDS:
        missing = [kind for kind in MANDATORY_GOVERNANCE_KINDS if kind not in observed]
        raise ContextGovernanceError(
            "mandatory_governance_coverage_missing",
            ",".join(missing) if missing else "order",
        )


def _governance_excerpt(
    kind: str,
    entry: _TrackedFile,
    section: _MarkdownSection,
    git_head_sha: str,
    remaining_chars: int,
) -> tuple[GovernanceExcerpt, bool]:
    source_content_sha256 = entry.content_sha256
    git_blob_sha = entry.git_blob_sha
    if git_blob_sha is None:
        raise ContextGovernanceError("governance_git_identity_missing", kind)
    limit = min(MAX_GOVERNANCE_EXCERPT_CHARS, remaining_chars)
    if limit <= 0:
        raise ContextBoundsError("governance_character_bound_exceeded")
    text = section.text
    truncated = len(text) > limit
    bounded_text = text[:limit]
    bounded_end_char = section.start_char + len(bounded_text)
    bounded_line_offset = bounded_text.count("\n")
    if bounded_text.endswith("\n"):
        bounded_line_offset = max(0, bounded_line_offset - 1)
    excerpt = GovernanceExcerpt(
        kind=kind,
        path=entry.path,
        source_content_sha256=source_content_sha256,
        git_blob_sha=git_blob_sha,
        git_head_sha=git_head_sha,
        section_heading=section.heading,
        start_line=section.start_line,
        end_line=(section.start_line + bounded_line_offset if truncated else section.end_line),
        start_char=section.start_char,
        end_char=bounded_end_char,
        text=bounded_text,
        authority=GovernanceAuthority.CANONICAL_GOVERNANCE,
        trust_classification=GovernanceAuthority.CANONICAL_GOVERNANCE,
        truncated=truncated,
    )
    return excerpt, truncated


def _tracked_governance_file(
    snapshot: _RepositorySnapshot,
    kind: str,
    path: str,
) -> _TrackedFile:
    entries = {item.path: item for item in snapshot.files}
    entry = entries.get(path)
    if entry is None:
        raise ContextGovernanceError("governance_not_git_tracked", f"{kind}:{path}")
    try:
        entry.source.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContextGovernanceError("governance_not_utf8", f"{kind}:{path}") from exc
    if entry.git_blob_sha is None:
        raise ContextGovernanceError("governance_git_identity_missing", kind)
    return entry


def _fair_excerpt_limit(remaining_budget: int, remaining_count: int) -> int:
    if remaining_count <= 0 or remaining_budget < remaining_count:
        raise ContextBoundsError("mandatory_governance_coverage_unsatisfiable")
    share = remaining_budget // remaining_count
    if share <= 0:
        raise ContextBoundsError("mandatory_governance_coverage_unsatisfiable")
    return min(MAX_GOVERNANCE_EXCERPT_CHARS, share)


def _reserved_chars_for_later_kinds(checkpoint_excerpt_count: int) -> int:
    later = max(0, len(GOVERNANCE_PATHS) - 1)
    mandatory_count = checkpoint_excerpt_count + later
    if mandatory_count > MAX_GOVERNANCE_EXCERPTS:
        raise ContextBoundsError("mandatory_governance_coverage_unsatisfiable")
    if mandatory_count > MAX_TOTAL_GOVERNANCE_CHARS:
        raise ContextBoundsError("mandatory_governance_coverage_unsatisfiable")
    available_after_checkpoint_min = MAX_TOTAL_GOVERNANCE_CHARS - checkpoint_excerpt_count
    if available_after_checkpoint_min < later:
        raise ContextBoundsError("mandatory_governance_coverage_unsatisfiable")
    return min(later * MAX_GOVERNANCE_EXCERPT_CHARS, available_after_checkpoint_min)


def _emit_mandatory_excerpt(
    candidate: _GovernanceCandidate,
    git_head_sha: str,
    remaining_budget: int,
    remaining_mandatory: int,
) -> tuple[GovernanceExcerpt, bool]:
    limit = _fair_excerpt_limit(remaining_budget, remaining_mandatory)
    return _governance_excerpt(
        candidate.kind,
        candidate.entry,
        candidate.section,
        git_head_sha,
        limit,
    )


def _checkpoint_selection(snapshot: _RepositorySnapshot) -> _GovernanceSelection:
    checkpoint_kind, checkpoint_path = GOVERNANCE_PATHS[0]
    checkpoint_entry = _tracked_governance_file(snapshot, checkpoint_kind, checkpoint_path)
    checkpoint_text = checkpoint_entry.source.decode("utf-8")
    checkpoint_sections = _checkpoint_sections(_parse_markdown_sections(checkpoint_text))
    reserved_chars = _reserved_chars_for_later_kinds(len(checkpoint_sections))
    checkpoint_budget = MAX_TOTAL_GOVERNANCE_CHARS - reserved_chars
    excerpts: list[GovernanceExcerpt] = []
    remaining_budget = checkpoint_budget
    remaining_count = len(checkpoint_sections)
    truncated = False
    for section in checkpoint_sections:
        candidate = _GovernanceCandidate(
            kind=checkpoint_kind,
            entry=checkpoint_entry,
            section=section,
            score=0,
            source_index=section.start_char,
            kind_index=0,
        )
        excerpt, excerpt_truncated = _emit_mandatory_excerpt(
            candidate,
            snapshot.repository_head_sha,
            remaining_budget,
            remaining_count,
        )
        excerpts.append(excerpt)
        remaining_budget -= len(excerpt.text)
        remaining_count -= 1
        truncated |= excerpt_truncated
    return _GovernanceSelection(tuple(excerpts), truncated)


def _later_governance_candidates(
    snapshot: _RepositorySnapshot,
    query_tokens: set[str],
) -> tuple[list[_GovernanceCandidate], list[_GovernanceCandidate]]:
    mandatory: list[_GovernanceCandidate] = []
    optional: list[_GovernanceCandidate] = []
    for kind_index, (kind, path) in enumerate(GOVERNANCE_PATHS[1:], start=1):
        entry = _tracked_governance_file(snapshot, kind, path)
        sections = _parse_markdown_sections(entry.source.decode("utf-8"))
        if not sections:
            raise ContextGovernanceError("governance_sections_missing", f"{kind}:{path}")
        ranked = sorted(
            enumerate(sections),
            key=lambda item: (-_section_score(item[1], query_tokens), item[0]),
        )
        top_index, top_section = ranked[0]
        mandatory.append(
            _GovernanceCandidate(
                kind=kind,
                entry=entry,
                section=top_section,
                score=_section_score(top_section, query_tokens),
                source_index=top_index,
                kind_index=kind_index,
            )
        )
        for source_index, section in ranked[1:]:
            score = _section_score(section, query_tokens)
            if score <= 0:
                continue
            optional.append(
                _GovernanceCandidate(
                    kind=kind,
                    entry=entry,
                    section=section,
                    score=score,
                    source_index=source_index,
                    kind_index=kind_index,
                )
            )
    optional.sort(key=lambda item: (item.kind_index, -item.score, item.source_index))
    return mandatory, optional


def _resolve_governance(
    snapshot: _RepositorySnapshot,
    query_tokens: set[str],
    checkpoint: _GovernanceSelection | None = None,
) -> _GovernanceSelection:
    checkpoint = checkpoint or _checkpoint_selection(snapshot)
    mandatory_later, optional_later = _later_governance_candidates(snapshot, query_tokens)
    excerpts = list(checkpoint.excerpts)
    remaining_slots = MAX_GOVERNANCE_EXCERPTS - len(excerpts)
    remaining_chars = MAX_TOTAL_GOVERNANCE_CHARS - sum(len(item.text) for item in excerpts)
    remaining_mandatory = len(mandatory_later)
    if remaining_slots < remaining_mandatory or remaining_chars < remaining_mandatory:
        raise ContextBoundsError("mandatory_governance_coverage_unsatisfiable")
    truncated = checkpoint.truncated
    for candidate in mandatory_later:
        excerpt, excerpt_truncated = _emit_mandatory_excerpt(
            candidate,
            snapshot.repository_head_sha,
            remaining_chars,
            remaining_mandatory,
        )
        excerpts.append(excerpt)
        remaining_chars -= len(excerpt.text)
        remaining_slots -= 1
        remaining_mandatory -= 1
        truncated |= excerpt_truncated
    for candidate in optional_later:
        if remaining_slots <= 0 or remaining_chars <= 0:
            break
        excerpt, excerpt_truncated = _governance_excerpt(
            candidate.kind,
            candidate.entry,
            candidate.section,
            snapshot.repository_head_sha,
            min(MAX_GOVERNANCE_EXCERPT_CHARS, remaining_chars),
        )
        excerpts.append(excerpt)
        remaining_chars -= len(excerpt.text)
        remaining_slots -= 1
        truncated |= excerpt_truncated
    selection = _GovernanceSelection(tuple(excerpts), truncated)
    _assert_mandatory_governance_coverage(selection.excerpts)
    return selection


def _resolve_source_state(
    settings: Settings,
    project_id: UUID,
) -> _SourceState:
    project = get_project(settings, project_id)
    if project is None:
        raise ContextProjectNotFoundError("project not found")
    if project.state not in {ProjectState.READY, ProjectState.ACTIVE}:
        raise ContextStaleError("project_state_unusable", project.state.value)
    if not project.repository_accessible or not project.git_head_sha:
        raise ContextStaleError("project_repository_unavailable")
    try:
        _, repository_path = normalize_project_path(project.relative_path, settings)
        snapshot = _collect_inventory(settings, repository_path)
    except (ProjectPathError, RepositoryIndexingError, OSError, RuntimeError) as exc:
        raise ContextStaleError("repository_snapshot_unavailable") from exc
    if snapshot.repository_head_sha.lower() != project.git_head_sha.lower():
        raise ContextStaleError("project_head_stale")
    dirty_paths = [entry.path for entry in snapshot.files if entry.git_status != "CLEAN"]
    if dirty_paths:
        raise ContextStaleError("project_worktree_dirty", ",".join(dirty_paths))
    index_run = latest_index_run(settings, project_id)
    if (
        index_run is None
        or index_run.status != IndexRunStatus.COMPLETED
        or index_run.repository_head_sha is None
        or index_run.repository_head_sha.lower() != snapshot.repository_head_sha.lower()
    ):
        raise ContextStaleError("repository_index_not_current")
    corpus = corpus_status(settings, project_id)
    if (
        corpus.state.value != "CURRENT"
        or corpus.latest_run is None
        or corpus.latest_run.repository_index_run_id != index_run.run_id
    ):
        raise ContextStaleError("retrieval_corpus_not_current")
    return _SourceState(project, snapshot, index_run.run_id, corpus.latest_run.run_id)


def _bounded_retrieval_results(
    response: RerankResponse,
) -> tuple[list[RerankCandidate], bool, int]:
    bounded: list[RerankCandidate] = []
    total_chars = 0
    truncated = len(response.results) > MAX_RETRIEVAL_RESULTS
    for candidate in response.results[:MAX_RETRIEVAL_RESULTS]:
        remaining = MAX_TOTAL_RETRIEVAL_CHARS - total_chars
        if remaining <= 0:
            truncated = True
            break
        snippet = candidate.snippet
        if len(snippet) > remaining:
            snippet = snippet[:remaining]
            truncated = True
        bounded.append(candidate.model_copy(update={"snippet": snippet}))
        total_chars += len(snippet)
    return bounded, truncated, total_chars


def _projection(candidate: RerankCandidate) -> ContextReferenceProjection:
    return ContextReferenceProjection(
        reference_id=candidate.reference_id,
        source_kind=candidate.source_kind,
        path=candidate.path,
        qualified_symbol=candidate.qualified_symbol,
        source_content_sha256=candidate.source_content_sha256,
        pre_rerank_rank=candidate.pre_rerank_rank,
        rerank_rank=candidate.rerank_rank,
        trust_classification=RepositoryEvidenceTrust.REPOSITORY_RETRIEVAL_EVIDENCE,
    )


def _projections(
    results: list[RerankCandidate],
    predicate: Callable[[RerankCandidate], bool],
    key_function: Callable[[RerankCandidate], object],
) -> list[ContextReferenceProjection]:
    seen: set[object] = set()
    projections: list[ContextReferenceProjection] = []
    for candidate in results:
        if not predicate(candidate):
            continue
        key = key_function(candidate)
        if key in seen:
            continue
        seen.add(key)
        projections.append(_projection(candidate))
    return projections


def _is_test_candidate(candidate: RerankCandidate) -> bool:
    path = candidate.path.casefold() if candidate.path else ""
    return bool(path and _TEST_PATH_RE.search(path))


def _assert_state_stable(
    settings: Settings,
    project_id: UUID,
    task_id: UUID,
    state: _SourceState,
    task_text_sha256: str,
) -> None:
    try:
        _assert_snapshot_stable(settings, state.snapshot)
    except (RepositoryIndexingError, OSError, RuntimeError) as exc:
        raise ContextStaleError("repository_source_changed") from exc
    current_project = get_project(settings, project_id)
    if (
        current_project is None
        or current_project.git_head_sha is None
        or current_project.git_head_sha.lower() != state.snapshot.repository_head_sha.lower()
        or current_project.state != state.project.state
    ):
        raise ContextStaleError("project_state_changed")
    current_index = latest_index_run(settings, project_id)
    if (
        current_index is None
        or current_index.run_id != state.index_run_id
        or current_index.status != IndexRunStatus.COMPLETED
        or current_index.repository_head_sha is None
        or current_index.repository_head_sha.lower() != state.snapshot.repository_head_sha.lower()
    ):
        raise ContextStaleError("repository_index_changed")
    current_corpus = corpus_status(settings, project_id)
    if (
        current_corpus.latest_run is None
        or current_corpus.latest_run.run_id != state.corpus_run_id
        or current_corpus.state.value != "CURRENT"
        or current_corpus.latest_run.repository_index_run_id != state.index_run_id
    ):
        raise ContextStaleError("retrieval_corpus_changed")
    try:
        current_task_text = get_task_text(settings, project_id, task_id)
    except (TaskNotFoundError, ExtractionNotReadyError) as exc:
        raise ContextStaleError("task_source_changed") from exc
    current_hash = hashlib.sha256(current_task_text.text.encode("utf-8")).hexdigest()
    if current_hash != task_text_sha256:
        raise ContextStaleError("task_source_changed")


def _settings() -> Settings:
    from .config import get_settings

    return get_settings()


def build_context(
    settings: Settings,
    project_id: UUID,
    task_id: UUID,
    *,
    top_k: int = DEFAULT_CONTEXT_TOP_K,
    disclosure_level: str | None = None,
) -> ContextCapsule:
    if not 1 <= top_k <= MAX_CONTEXT_TOP_K:
        raise ContextInputError("context top_k is outside the bounded contract")
    if disclosure_level is not None:
        parse_disclosure_level(disclosure_level)
    state = _resolve_source_state(settings, project_id)
    project = state.project
    checkpoint = _checkpoint_selection(state.snapshot)
    try:
        task = get_task(settings, project_id, task_id)
        extracted = get_task_text(settings, project_id, task_id)
    except TaskNotFoundError:
        raise
    except ExtractionNotReadyError:
        raise
    if task.project_id != project_id or extracted.project_id != project_id:
        raise ContextStaleError("task_project_mismatch")
    extracted_text_sha256 = hashlib.sha256(extracted.text.encode("utf-8")).hexdigest()
    constraints, constraints_truncated = _task_section_items(
        extracted.text,
        frozenset({"constraints"}),
    )
    acceptance_criteria, acceptance_truncated = _task_section_items(
        extracted.text,
        frozenset({"acceptance criteria"}),
    )
    query, normalized_query = _derive_query(
        task,
        extracted.text,
        constraints,
        acceptance_criteria,
    )
    governance = _resolve_governance(
        state.snapshot,
        _tokens(normalized_query),
        checkpoint,
    )
    _assert_mandatory_governance_coverage(governance.excerpts)
    try:
        rerank_response = rerank_search(
            settings,
            project_id,
            RerankRequest(
                query=query,
                top_k=top_k,
                candidate_pool=MAX_RETRIEVAL_CANDIDATE_POOL,
                strict_rerank=False,
            ),
        )
    except (
        RerankError,
        SemanticError,
        RetrievalProjectNotFoundError,
        RetrievalQueryError,
        RetrievalSyncError,
    ) as exc:
        raise ContextRetrievalError("retrieval_pipeline_unavailable") from exc
    if rerank_response.project_id != project_id:
        raise ContextRetrievalError("retrieval_project_mismatch")
    results, retrieval_truncated, retrieval_chars = _bounded_retrieval_results(rerank_response)
    task_excerpt = extracted.text[:MAX_TASK_EXCERPT_CHARS]
    task_excerpt_truncated = len(extracted.text) > MAX_TASK_EXCERPT_CHARS
    files = _projections(
        results,
        lambda candidate: candidate.source_kind in {"REPOSITORY_FILE", "REPOSITORY_SYMBOL"}
        and candidate.path is not None,
        lambda candidate: candidate.path,
    )
    symbols = _projections(
        results,
        lambda candidate: candidate.qualified_symbol is not None,
        lambda candidate: (candidate.path, candidate.qualified_symbol),
    )
    tests = _projections(
        results,
        _is_test_candidate,
        lambda candidate: (candidate.path, candidate.qualified_symbol),
    )
    presentation = apply_disclosure(
        title=task.title,
        constraints=constraints,
        acceptance_criteria=acceptance_criteria,
        task_text=extracted.text,
        files=files,
        symbols=symbols,
        tests=tests,
        results=results,
        snapshot=state.snapshot,
        requested_level=disclosure_level,
    )
    files = presentation.files
    symbols = presentation.symbols
    tests = presentation.tests
    results = presentation.results
    retrieval_chars = sum(len(item.snippet) for item in results)
    retrieval_truncated = retrieval_truncated or presentation.disclosure.truncated
    governance_chars = sum(len(item.text) for item in governance.excerpts)
    task_structure_chars = sum(len(item) for item in (*constraints, *acceptance_criteria))
    disclosure_chars = disclosure_payload_characters(
        presentation.module_summaries,
        presentation.symbol_signatures,
        presentation.dependencies,
        presentation.complete_files,
        presentation.inventory,
    )
    total_emitted = (
        len(task_excerpt)
        + task_structure_chars
        + governance_chars
        + retrieval_chars
        + disclosure_chars
    )
    bounds = ContextBounds(
        task_characters_included=len(task_excerpt),
        governance_characters_included=governance_chars,
        retrieval_characters_included=retrieval_chars,
        total_emitted_context_characters=total_emitted,
        serialized_capsule_characters=0,
        governance_excerpt_count=len(governance.excerpts),
        retrieval_result_count=len(results),
        task_constraint_count=len(constraints),
        task_acceptance_criteria_count=len(acceptance_criteria),
        file_projection_count=len(files),
        symbol_projection_count=len(symbols),
        test_projection_count=len(tests),
        disclosure_characters_included=disclosure_chars,
        task_excerpt_truncated=task_excerpt_truncated
        or constraints_truncated
        or acceptance_truncated,
        governance_excerpt_truncated=governance.truncated,
        retrieval_truncated=retrieval_truncated,
        capsule_truncated=False,
    )
    capsule = ContextCapsule(
        project=ContextProject(
            project_id=project.project_id,
            name=project.name,
            relative_path=project.relative_path,
            current_state=project.state,
            repository_head_sha=state.snapshot.repository_head_sha,
            registered_head_sha=cast(str, project.git_head_sha),
            working_tree_clean=project.working_tree_clean,
            index_run_id=state.index_run_id,
            corpus_run_id=state.corpus_run_id,
        ),
        task=ContextTask(
            task_id=task.task_id,
            project_id=task.project_id,
            title=task.title,
            source_type=task.source_type,
            original_filename=task.original_filename,
            extraction_method=extracted.extraction_method,
            extraction_version=extracted.extraction_version,
            original_blob_sha256=task.original_blob_sha256,
            extracted_text_sha256=extracted_text_sha256,
            excerpt=task_excerpt,
            excerpt_truncated=task_excerpt_truncated,
            trust_classification=TaskTrust.TASK_INPUT_NONCANONICAL,
        ),
        governance=list(governance.excerpts),
        task_derived=TaskDerivedStructure(
            constraints=constraints,
            acceptance_criteria=acceptance_criteria,
            trust_classification=TaskTrust.TASK_INPUT_NONCANONICAL,
        ),
        retrieval=ContextRetrieval(
            query=query,
            normalized_query=normalized_query,
            rerank_state=rerank_response.rerank_state.value,
            hybrid_state=rerank_response.hybrid_state,
            semantic_state=rerank_response.semantic_state,
            fallback_reason=rerank_response.fallback_reason,
            candidate_pool=rerank_response.candidate_pool,
            serialization_version=rerank_response.serialization_version,
            reranker_profile=rerank_response.reranker_profile,
            results=results,
        ),
        files=files,
        symbols=symbols,
        tests=tests,
        complete_files=presentation.complete_files,
        inventory=presentation.inventory,
        module_summaries=presentation.module_summaries,
        symbol_signatures=presentation.symbol_signatures,
        dependencies=presentation.dependencies,
        progressive_disclosure=presentation.disclosure,
        bounds=bounds,
    )
    _assert_state_stable(
        settings,
        project_id,
        task_id,
        state,
        extracted_text_sha256,
    )
    final_length = 0
    for _ in range(4):
        serialized_length = len(capsule.model_dump_json())
        if serialized_length > MAX_CAPSULE_CHARS:
            if capsule.complete_files:
                raise ContextBoundsError("l4_complete_file_exceeds_capsule_bound")
            raise ContextBoundsError("capsule_character_bound_exceeded")
        capsule = capsule.model_copy(
            update={
                "bounds": bounds.model_copy(
                    update={"serialized_capsule_characters": serialized_length}
                )
            }
        )
        final_length = len(capsule.model_dump_json())
        if capsule.bounds.serialized_capsule_characters == final_length:
            break
    if final_length > MAX_CAPSULE_CHARS:
        if capsule.complete_files:
            raise ContextBoundsError("l4_complete_file_exceeds_capsule_bound")
        raise ContextBoundsError("capsule_character_bound_exceeded")
    if capsule.bounds.serialized_capsule_characters != final_length:
        raise ContextBoundsError("capsule_serialization_length_unstable")
    _assert_mandatory_governance_coverage(capsule.governance)
    return capsule


router = APIRouter(tags=["context-manager"])


@router.post(
    "/api/v1/projects/{project_id}/tasks/{task_id}/context",
    response_model=ContextCapsule,
)
def build_context_endpoint(
    project_id: UUID,
    task_id: UUID,
    request: ContextRequest | None = None,
) -> ContextCapsule:
    try:
        return build_context(
            _settings(),
            project_id,
            task_id,
            top_k=request.top_k if request is not None else DEFAULT_CONTEXT_TOP_K,
            disclosure_level=request.disclosure_level if request is not None else None,
        )
    except DisclosureInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DisclosureConsistencyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ContextProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=404, detail="task not found") from exc
    except ExtractionNotReadyError as exc:
        raise HTTPException(status_code=409, detail="task extraction is not ready") from exc
    except ContextInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ContextManagerError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="context manager database unavailable") from exc
