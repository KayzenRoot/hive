"""Bounded, provider-independent autonomous execution over existing HIVE seams.

The orchestrator deliberately owns coordination only.  Project and task
identity come from the durable registry/intake modules, context comes from the
existing Context Manager, and file/process safety remains in ``runner``.
There is no Git promotion or durable execution-run store in this module.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Protocol, cast, runtime_checkable
from uuid import UUID, uuid4

from . import context_manager
from .config import Settings, get_settings
from .registry import (
    InspectionResult,
    ProjectResponse,
    ProjectState,
    get_project,
    inspect_project,
    normalize_project_path,
)
from .runner import (
    AdmissionLimits,
    ChangeSet,
    PathPolicy,
    ProcessEvidence,
    StagedRun,
    ToolPolicy,
    admit_change_set,
    apply_admitted,
    run_subprocess,
    validate_relative_path,
    verify_changed_files,
)
from .task_intake import TaskResponse, get_task
from .telemetry import emit_event

EXECUTION_EVIDENCE_VERSION = "execution-evidence-v1"
DEFAULT_TOOL_SUBSET = ("python",)
DEFAULT_DENIED_PATHS = ("docs/project-brain", ".git")
MAX_ADAPTER_NAME_CHARS = 128
MAX_SUMMARY_CHARS = 4_096
MAX_REVIEW_FIELD_CHARS = 2_048
MAX_COMMANDS = 64
MAX_COMMAND_ARGUMENTS = 32
MAX_COMMAND_ARGUMENT_CHARS = 2_048
MAX_CHANGED_FILE_BYTES = 1_048_576
MAX_DIFF_CHARS = 16_000
MAX_PROCESS_EVIDENCE_CHARS = 8_000
MAX_RESULT_CHARS = 100_000
MIGRATION_HEAD = "0007_telemetry_events"
MANDATORY_GOVERNANCE_KINDS = (
    "CHECKPOINT",
    "SCOPE",
    "DEFINITION_OF_DONE",
    "ARCHITECTURE",
    "DECISIONS",
)

_SECRET_PATTERN = re.compile(
    r"(?ix)(?:"
    r"WO\d+_[A-Z0-9_-]*SECRET[A-Z0-9_-]*"
    r"|(?:api[_-]?key|access[_-]?token|refresh[_-]?token|authorization|password|secret)"
    r"\s*[:=]\s*['\"]?[^\s,'\"]+"
    r"|(?:gh[pousr]_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]+)"
    r")"
)
_WINDOWS_ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9_])(?:[A-Za-z]:[\\/]|\\\\)[^\s<>\"',;)]*")
_POSIX_ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9_:])/(?!/)[^\s<>\"',;)]*")
_HEX_SHA = re.compile(r"^[0-9a-f]{40,64}$", re.IGNORECASE)


class ExecutionError(RuntimeError):
    """Base class for fail-closed orchestrator errors."""

    code = "execution_error"

    def __init__(self, detail: str = "") -> None:
        self.detail = detail
        message = self.code if not detail else f"{self.code}:{detail}"
        super().__init__(message[:512])


class ExecutionIdentityError(ExecutionError):
    code = "identity_error"


class ExecutionPreconditionError(ExecutionError):
    code = "precondition_error"


class ExecutionContextError(ExecutionError):
    code = "context_error"


class ExecutorAdapterError(ExecutionError):
    code = "adapter_error"


class ExecutionToolError(ExecutionError):
    code = "tool_error"


class ExecutionEvidenceError(ExecutionError):
    code = "evidence_error"


class CanonicalMutationError(ExecutionPreconditionError):
    code = "canonical_mutation_rejected"


class HeadRaceError(ExecutionPreconditionError):
    code = "head_race_rejected"


@dataclass(frozen=True, slots=True)
class ExecutorRequest:
    """Bounded identity and context request supplied to an adapter."""

    project_id: UUID
    task_id: UUID
    expected_branch: str | None = None
    expected_head_sha: str | None = None
    top_k: int = 5
    disclosure_level: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.project_id, UUID) or not isinstance(self.task_id, UUID):
            raise ValueError("project_id and task_id must be UUID values")
        if not 1 <= self.top_k <= 10:
            raise ValueError("top_k must be between 1 and 10")
        if self.expected_branch is not None and (
            not self.expected_branch.strip() or any(char.isspace() for char in self.expected_branch)
        ):
            raise ValueError("expected_branch must be a non-whitespace branch name")
        if self.expected_head_sha is not None and not _HEX_SHA.fullmatch(self.expected_head_sha):
            raise ValueError("expected_head_sha must be a Git SHA")


@dataclass(frozen=True, slots=True)
class ExecutorResult:
    """Structured, bounded adapter output before Runner admission."""

    change_set: ChangeSet
    summary: str
    decisions: tuple[str, ...] = ()
    test_commands: tuple[tuple[str, ...], ...] = ()
    validation_commands: tuple[tuple[str, ...], ...] = ()
    errors_fixed: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    pending_items: tuple[str, ...] = ()
    proposed_checkpoint_update: str = ""
    provider_independent: bool = True
    executor_llm_calls: int = 0
    executor_provider_calls: int = 0

    @property
    def changes(self) -> ChangeSet:
        """Compatibility spelling for callers that call the payload changes."""

        return self.change_set


# The longer name is useful at call sites and keeps the core contract easy to
# discover without introducing a second result type.
ExecutorAdapterResult = ExecutorResult


@runtime_checkable
class ExecutorAdapter(Protocol):
    """Replaceable provider-independent executor boundary."""

    def execute(self, request: ExecutorRequest, context: object) -> ExecutorResult:
        """Return structured changes and bounded audit metadata."""


@dataclass(frozen=True, slots=True)
class ExecutionIdentity:
    project_id: UUID
    task_id: UUID
    branch: str
    head_sha: str
    workspace: Path = field(repr=False)

    def as_dict(self) -> dict[str, str]:
        # The workspace is intentionally omitted.  Evidence must remain
        # portable and must not disclose absolute host paths.
        return {
            "project_id": str(self.project_id),
            "task_id": str(self.task_id),
            "branch": _sanitize_text(self.branch),
            "head_sha": self.head_sha,
        }


@dataclass(frozen=True, slots=True)
class CommandEvidence:
    argv: tuple[str, ...]
    returncode: int | None
    timed_out: bool
    stdout: str
    stderr: str
    duration_seconds: float

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    @classmethod
    def from_process(cls, evidence: ProcessEvidence) -> CommandEvidence:
        return cls(
            tuple(
                _sanitize_argument(argument, index == 0)
                for index, argument in enumerate(evidence.argv)
            ),
            evidence.returncode,
            evidence.timed_out,
            _bounded_sanitized_text(evidence.stdout, MAX_PROCESS_EVIDENCE_CHARS),
            _bounded_sanitized_text(evidence.stderr, MAX_PROCESS_EVIDENCE_CHARS),
            round(max(0.0, evidence.duration_seconds), 6),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "argv": list(self.argv),
            "returncode": self.returncode,
            "timed_out": self.timed_out,
            "succeeded": self.succeeded,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_seconds": self.duration_seconds,
        }


@dataclass(frozen=True, slots=True)
class DiffEvidence:
    path: str
    before_sha256: str | None
    after_sha256: str | None
    before_bytes: int
    after_bytes: int
    unified_diff: str
    binary: bool
    truncated: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "before_sha256": self.before_sha256,
            "after_sha256": self.after_sha256,
            "before_bytes": self.before_bytes,
            "after_bytes": self.after_bytes,
            "binary": self.binary,
            "truncated": self.truncated,
            "unified_diff": self.unified_diff,
        }


@dataclass(frozen=True, slots=True)
class ExecutorReview:
    summary: str
    changed_files: tuple[str, ...]
    decisions: tuple[str, ...]
    tests: tuple[CommandEvidence, ...]
    validation: tuple[CommandEvidence, ...]
    errors_fixed: tuple[str, ...]
    risks: tuple[str, ...]
    pending_items: tuple[str, ...]
    diff: tuple[DiffEvidence, ...]
    proposed_checkpoint_update: str

    def as_dict(self) -> dict[str, object]:
        return {
            "summary": self.summary,
            "changed_files": list(self.changed_files),
            "decisions": list(self.decisions),
            "tests": [item.as_dict() for item in self.tests],
            "validation": [item.as_dict() for item in self.validation],
            "errors_fixed": list(self.errors_fixed),
            "risks": list(self.risks),
            "pending_items": list(self.pending_items),
            "diff": [item.as_dict() for item in self.diff],
            "proposed_checkpoint_update": self.proposed_checkpoint_update,
        }


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Staged execution evidence; never a canonical promotion result."""

    status: str
    identity: ExecutionIdentity
    adapter_name: str
    provider_independent: bool
    context_project_id: UUID
    context_task_id: UUID
    governance_kinds: tuple[str, ...]
    change_set: ChangeSet
    changed_files: tuple[str, ...]
    diff: tuple[DiffEvidence, ...]
    tests: tuple[CommandEvidence, ...]
    validation: tuple[CommandEvidence, ...]
    review: ExecutorReview
    staged_run: StagedRun = field(repr=False)
    executor_llm_calls: int = 0
    executor_provider_calls: int = 0

    @property
    def promoted(self) -> bool:
        return False

    @property
    def validation_passed(self) -> bool:
        return all(item.succeeded for item in self.validation)

    def _payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "evidence_version": EXECUTION_EVIDENCE_VERSION,
            "status": self.status,
            "identity": self.identity.as_dict(),
            "adapter": {
                "name": _sanitize_text(self.adapter_name),
                "provider_independent": self.provider_independent,
            },
            "context": {
                "project_id": str(self.context_project_id),
                "task_id": str(self.context_task_id),
                "governance_kinds": list(self.governance_kinds),
                "checkpoint_first": self.governance_kinds[:1] == ("CHECKPOINT",),
            },
            "change_set": {
                "operation_count": len(self.change_set.operations),
                "model": _sanitize_text(self.change_set.model),
                "effort": _sanitize_text(self.change_set.effort),
                "request_id": _sanitize_text(self.change_set.request_id or "") or None,
            },
            "changed_files": list(self.changed_files),
            "diff": [item.as_dict() for item in self.diff],
            "tests": [item.as_dict() for item in self.tests],
            "validation": [item.as_dict() for item in self.validation],
            "executor_review": self.review.as_dict(),
            "staged_noncanonical": True,
            "promoted": False,
            "commit_performed": False,
            "push_performed": False,
            "merge_performed": False,
            "checkpoint_promoted": False,
            "executor_llm_calls": self.executor_llm_calls,
            "executor_provider_calls": self.executor_provider_calls,
            "bounded_output_enforced": True,
        }
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        secret_leaks = len(_SECRET_PATTERN.findall(serialized))
        filesystem_path_leaks = len(_filesystem_path_matches(serialized))
        payload["secret_leaks"] = secret_leaks
        payload["filesystem_path_leaks"] = filesystem_path_leaks
        payload["sanitized_path_evidence"] = secret_leaks == 0 and filesystem_path_leaks == 0
        return payload

    def as_dict(self) -> dict[str, object]:
        payload = self._payload()
        serialized_length = len(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
        if serialized_length > MAX_RESULT_CHARS:
            raise ExecutionEvidenceError("staged evidence exceeds its character bound")
        return payload

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, sort_keys=True, indent=2) + "\n"


@dataclass(frozen=True, slots=True)
class _RepositoryObservation:
    branch: str
    head_sha: str
    detached_head: bool
    repository_accessible: bool
    working_tree_clean: bool | None
    state: str


ProjectLoader = Callable[[Settings, UUID], ProjectResponse | None]
TaskLoader = Callable[[Settings, UUID, UUID], TaskResponse]
ContextBuilder = Callable[..., object]
RepositoryInspector = Callable[[Path], InspectionResult]
EventEmitter = Callable[..., object]


class ExecutionOrchestrator:
    """Coordinate one bounded execution against a registered project/task."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        tool_policy: ToolPolicy | None = None,
        path_policy: PathPolicy | None = None,
        limits: AdmissionLimits | None = None,
        project_loader: ProjectLoader | None = None,
        task_loader: TaskLoader | None = None,
        context_builder: ContextBuilder | None = None,
        repository_inspector: RepositoryInspector | None = None,
        event_emitter: EventEmitter | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.tool_policy = tool_policy or ToolPolicy(DEFAULT_TOOL_SUBSET)
        self.path_policy = path_policy or PathPolicy(denied_prefixes=DEFAULT_DENIED_PATHS)
        self.limits = limits or AdmissionLimits()
        self.project_loader = project_loader or get_project
        self.task_loader = task_loader or get_task
        self.context_builder = context_builder or context_manager.build_context
        self.repository_inspector = repository_inspector or inspect_project
        default_seams = all(
            seam is None
            for seam in (
                project_loader,
                task_loader,
                context_builder,
                repository_inspector,
            )
        )
        self.event_emitter = event_emitter or (emit_event if default_seams else None)

    def execute(self, request: ExecutorRequest, adapter: ExecutorAdapter) -> ExecutionResult:
        """Run one execution and emit bounded durable lifecycle events."""

        run_id = uuid4()
        identity, _project = self._resolve_identity(request)
        self._emit_event(
            request,
            run_id,
            "executor.started",
            {"adapter": type(adapter).__name__},
            "executor.started",
        )
        try:
            result = self._execute(request, adapter, identity=identity, project=_project)
        except Exception as exc:
            self._emit_event(
                request,
                run_id,
                "run.failed",
                {"status": "failed", "error_type": type(exc).__name__},
                "run.failed",
            )
            raise
        terminal_type = "run.completed" if result.status == "STAGED" else "run.failed"
        self._emit_event(
            request,
            run_id,
            terminal_type,
            {
                "status": result.status,
                "validation_passed": result.validation_passed,
                "changed_file_count": len(result.changed_files),
            },
            terminal_type,
        )
        return result

    def _emit_event(
        self,
        request: ExecutorRequest,
        run_id: UUID,
        event_type: str,
        payload: dict[str, object],
        emission_suffix: str,
    ) -> None:
        if self.event_emitter is None:
            return
        self.event_emitter(
            self.settings,
            request.project_id,
            event_type,
            payload,
            task_id=request.task_id,
            run_id=run_id,
            provenance={"producer": "execution_orchestrator", "deterministic": True},
            emission_key=f"execution:{run_id}:{emission_suffix}",
        )

    def _execute(
        self,
        request: ExecutorRequest,
        adapter: ExecutorAdapter,
        *,
        identity: ExecutionIdentity | None = None,
        project: ProjectResponse | None = None,
    ) -> ExecutionResult:
        """Run one adapter result through one verified execution basis."""

        if identity is None or project is None:
            identity, project = self._resolve_identity(request)
        initial = self._observe(identity.workspace)
        self._assert_observation(identity, initial, require_clean=True)
        context = self._build_context(request, identity, project)
        governance_kinds = self._assert_context(context, request, identity)
        self._assert_unchanged(identity, initial, require_clean=True)

        adapter_name = self._adapter_name(adapter)
        try:
            if getattr(adapter, "provider_independent", True) is False:
                raise ExecutorAdapterError("provider-independent adapter required")
            execute_method = getattr(adapter, "execute", None)
            if not callable(execute_method):
                raise ExecutorAdapterError("adapter must expose execute")
            raw_result = execute_method(request, context)
        except ExecutionError:
            raise
        except Exception as exc:
            raise ExecutorAdapterError("adapter execution failed") from exc

        result = self._validate_result(raw_result, adapter_name)
        self._assert_unchanged(identity, initial, require_clean=True)
        self._validate_change_paths(result.change_set)
        self._gate_commands(result)
        before_bytes = self._capture_changed_files(identity.workspace, result.change_set)

        try:
            admission = admit_change_set(
                result.change_set,
                identity.workspace,
                policy=self.path_policy,
                limits=self.limits,
            )
        except Exception as exc:
            if isinstance(exc, ExecutionError):
                raise
            raise ExecutionPreconditionError("change admission failed") from exc

        def verify_basis_before_apply() -> None:
            self._assert_unchanged(identity, initial, require_clean=True)

        try:
            applied = apply_admitted(admission, before_apply=verify_basis_before_apply)
        except HeadRaceError:
            raise
        except Exception as exc:
            if isinstance(exc, ExecutionError):
                raise
            raise ExecutionPreconditionError("admitted change could not be applied") from exc

        self._assert_unchanged(identity, initial, require_clean=False)
        test_evidence = self._run_commands(
            result.test_commands,
            identity.workspace,
            result.change_set,
        )
        validation_evidence = self._run_commands(
            result.validation_commands,
            identity.workspace,
            result.change_set,
        )
        post_command_verification = verify_changed_files(admission)
        if not post_command_verification.passed:
            raise ExecutionEvidenceError("commands changed files outside the admitted set")
        after_bytes = self._capture_changed_files(identity.workspace, result.change_set)
        diff = self._build_diff(result.change_set, before_bytes, after_bytes)
        changed_files = tuple(sorted(admission.normalized_paths))
        review = ExecutorReview(
            summary=_bounded_sanitized_text(result.summary, MAX_SUMMARY_CHARS),
            changed_files=changed_files,
            decisions=_sanitize_sequence(result.decisions),
            tests=test_evidence,
            validation=validation_evidence,
            errors_fixed=_sanitize_sequence(result.errors_fixed),
            risks=_sanitize_sequence(result.risks),
            pending_items=_sanitize_sequence(result.pending_items),
            diff=diff,
            proposed_checkpoint_update=_bounded_sanitized_text(
                result.proposed_checkpoint_update,
                MAX_REVIEW_FIELD_CHARS,
            ),
        )
        status = (
            "STAGED" if all(item.succeeded for item in validation_evidence) else "VALIDATION_FAILED"
        )
        staged_process = tuple(
            ProcessEvidence(
                item.argv,
                item.returncode,
                item.timed_out,
                item.stdout,
                item.stderr,
                item.duration_seconds,
            )
            for item in (*test_evidence, *validation_evidence)
        )
        staged = StagedRun(
            admission=admission,
            apply=applied,
            process=staged_process,
            promoted=False,
        )
        execution = ExecutionResult(
            status=status,
            identity=identity,
            adapter_name=adapter_name,
            provider_independent=result.provider_independent,
            context_project_id=request.project_id,
            context_task_id=request.task_id,
            governance_kinds=governance_kinds,
            change_set=result.change_set,
            changed_files=changed_files,
            diff=diff,
            tests=test_evidence,
            validation=validation_evidence,
            review=review,
            staged_run=staged,
            executor_llm_calls=result.executor_llm_calls,
            executor_provider_calls=result.executor_provider_calls,
        )
        execution.as_dict()
        return execution

    def run(self, request: ExecutorRequest, adapter: ExecutorAdapter) -> ExecutionResult:
        """Readable alias for callers that model the orchestrator as a runner."""

        return self.execute(request, adapter)

    def _resolve_identity(
        self,
        request: ExecutorRequest,
    ) -> tuple[ExecutionIdentity, ProjectResponse]:
        try:
            project = self.project_loader(self.settings, request.project_id)
        except Exception as exc:
            raise ExecutionIdentityError("project lookup failed") from exc
        if project is None:
            raise ExecutionIdentityError("project not found")
        if not _same_uuid(getattr(project, "project_id", None), request.project_id):
            raise ExecutionIdentityError("project identity mismatch")
        if _state_value(getattr(project, "state", None)) not in {
            ProjectState.READY.value,
            ProjectState.ACTIVE.value,
        }:
            raise ExecutionIdentityError("project state is not executable")
        if getattr(project, "repository_accessible", False) is not True:
            raise ExecutionIdentityError("repository is not accessible")
        if getattr(project, "detached_head", True) is not False:
            raise ExecutionIdentityError("detached HEAD is not executable")
        if getattr(project, "working_tree_clean", None) is not True:
            raise ExecutionIdentityError("registered working tree is not clean")
        branch = getattr(project, "git_branch", None)
        head_sha = getattr(project, "git_head_sha", None)
        if not isinstance(branch, str) or not branch.strip():
            raise ExecutionIdentityError("registered branch is unavailable")
        if not isinstance(head_sha, str) or not _HEX_SHA.fullmatch(head_sha):
            raise ExecutionIdentityError("registered HEAD is unavailable")
        expected_branch = request.expected_branch or branch
        expected_head = (request.expected_head_sha or head_sha).lower()
        if expected_branch != branch or expected_head != head_sha.lower():
            raise ExecutionIdentityError("execution basis differs from registered identity")
        try:
            _relative_path, workspace = normalize_project_path(project.relative_path, self.settings)
        except Exception as exc:
            raise ExecutionIdentityError("registered project path is invalid") from exc
        try:
            task = self.task_loader(self.settings, request.project_id, request.task_id)
        except Exception as exc:
            raise ExecutionIdentityError("task lookup failed") from exc
        if not _same_uuid(getattr(task, "task_id", None), request.task_id):
            raise ExecutionIdentityError("task identity mismatch")
        if not _same_uuid(getattr(task, "project_id", None), request.project_id):
            raise ExecutionIdentityError("task project mismatch")
        return (
            ExecutionIdentity(
                project_id=request.project_id,
                task_id=request.task_id,
                branch=branch,
                head_sha=head_sha.lower(),
                workspace=workspace,
            ),
            project,
        )

    def _observe(self, workspace: Path) -> _RepositoryObservation:
        try:
            observed = self.repository_inspector(workspace)
        except Exception as exc:
            raise ExecutionPreconditionError("repository inspection failed") from exc
        return _RepositoryObservation(
            branch=str(getattr(observed, "git_branch", "") or ""),
            head_sha=str(getattr(observed, "git_head_sha", "") or "").lower(),
            detached_head=bool(getattr(observed, "detached_head", True)),
            repository_accessible=getattr(observed, "repository_accessible", False) is True,
            working_tree_clean=cast(bool | None, getattr(observed, "working_tree_clean", None)),
            state=_state_value(getattr(observed, "state", None)),
        )

    def _assert_observation(
        self,
        identity: ExecutionIdentity,
        observation: _RepositoryObservation,
        *,
        require_clean: bool,
    ) -> None:
        if not observation.repository_accessible or observation.detached_head:
            raise ExecutionPreconditionError("repository state is unsafe")
        if observation.branch != identity.branch:
            raise ExecutionPreconditionError("repository branch changed")
        if observation.head_sha != identity.head_sha:
            raise HeadRaceError("repository HEAD changed")
        if require_clean and observation.working_tree_clean is not True:
            raise ExecutionPreconditionError("working tree is not clean")
        if observation.state not in {ProjectState.READY.value, ProjectState.ACTIVE.value}:
            raise ExecutionPreconditionError("repository state is not executable")

    def _assert_unchanged(
        self,
        identity: ExecutionIdentity,
        initial: _RepositoryObservation,
        *,
        require_clean: bool,
    ) -> None:
        observed = self._observe(identity.workspace)
        self._assert_observation(identity, observed, require_clean=require_clean)
        if observed.head_sha != initial.head_sha or observed.branch != initial.branch:
            raise HeadRaceError("execution basis changed")

    def _build_context(
        self,
        request: ExecutorRequest,
        identity: ExecutionIdentity,
        project: ProjectResponse,
    ) -> object:
        try:
            context = self.context_builder(
                self.settings,
                request.project_id,
                request.task_id,
                top_k=request.top_k,
                disclosure_level=request.disclosure_level,
            )
        except Exception as exc:
            raise ExecutionContextError("Context Manager build failed") from exc
        if context is None:
            raise ExecutionContextError("Context Manager returned no capsule")
        # Keep the project object in this method's signature as an explicit
        # proof that identity was resolved before context construction.
        _ = project
        context_project = getattr(context, "project", None)
        context_task = getattr(context, "task", None)
        if context_project is None or context_task is None:
            raise ExecutionContextError("context capsule lacks project/task identity")
        if not _same_uuid(getattr(context_project, "project_id", None), identity.project_id):
            raise ExecutionContextError("context project mismatch")
        if not _same_uuid(getattr(context_task, "task_id", None), identity.task_id):
            raise ExecutionContextError("context task mismatch")
        if not _same_uuid(getattr(context_task, "project_id", None), identity.project_id):
            raise ExecutionContextError("context task project mismatch")
        context_head = getattr(context_project, "repository_head_sha", None)
        if context_head is not None and str(context_head).lower() != identity.head_sha:
            raise HeadRaceError("context repository HEAD differs from execution basis")
        return context

    def _assert_context(
        self,
        context: object,
        request: ExecutorRequest,
        identity: ExecutionIdentity,
    ) -> tuple[str, ...]:
        try:
            raw_governance = _attribute(context, "governance")
            if not isinstance(raw_governance, Sequence) or isinstance(raw_governance, str | bytes):
                raise TypeError("governance is not a sequence")
            governance = cast(Sequence[context_manager.GovernanceExcerpt], raw_governance)
            kinds = context_manager.mandatory_governance_kind_sequence(governance)
        except Exception as exc:
            raise ExecutionContextError("context governance is unavailable") from exc
        if kinds != MANDATORY_GOVERNANCE_KINDS:
            raise ExecutionContextError("checkpoint-first governance coverage is incomplete")
        if not governance or getattr(governance[0], "kind", None) != "CHECKPOINT":
            raise ExecutionContextError("checkpoint-first context is required")
        context_project = getattr(context, "project", None)
        context_task = getattr(context, "task", None)
        if not _same_uuid(getattr(context_project, "project_id", None), request.project_id):
            raise ExecutionContextError("context project identity changed")
        if not _same_uuid(getattr(context_task, "task_id", None), request.task_id):
            raise ExecutionContextError("context task identity changed")
        _ = identity
        return tuple(kinds)

    def _adapter_name(self, adapter: ExecutorAdapter) -> str:
        raw_name = getattr(adapter, "name", type(adapter).__name__)
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise ExecutorAdapterError("adapter name is required")
        name = _sanitize_text(raw_name).strip()
        if not name or len(name) > MAX_ADAPTER_NAME_CHARS or any(char in name for char in "\r\n"):
            raise ExecutorAdapterError("adapter name is outside its bound")
        return name

    def _validate_result(self, raw_result: object, adapter_name: str) -> ExecutorResult:
        if not isinstance(raw_result, ExecutorResult):
            raise ExecutorAdapterError("adapter output must be a structured ExecutorResult")
        result = raw_result
        if not result.provider_independent:
            raise ExecutorAdapterError("provider-specific adapter output is not allowed")
        if not isinstance(result.summary, str) or not result.summary.strip():
            raise ExecutorAdapterError("adapter summary is required")
        if len(result.summary) > MAX_SUMMARY_CHARS:
            raise ExecutorAdapterError("adapter summary exceeds its bound")
        if not isinstance(result.change_set, ChangeSet):
            raise ExecutorAdapterError("adapter change_set is invalid")
        if len(result.change_set.operations) > self.limits.max_operations:
            raise ExecutorAdapterError("adapter operation count exceeds its bound")
        if result.change_set.total_content_bytes() > self.limits.max_content_bytes:
            raise ExecutorAdapterError("adapter content exceeds its bound")
        if (
            not isinstance(result.executor_llm_calls, int)
            or isinstance(result.executor_llm_calls, bool)
            or result.executor_llm_calls < 0
        ):
            raise ExecutorAdapterError("executor_llm_calls is invalid")
        if (
            not isinstance(result.executor_provider_calls, int)
            or isinstance(result.executor_provider_calls, bool)
            or result.executor_provider_calls < 0
        ):
            raise ExecutorAdapterError("executor_provider_calls is invalid")
        for field_name in (
            "decisions",
            "errors_fixed",
            "risks",
            "pending_items",
        ):
            _validate_text_sequence(getattr(result, field_name), field_name)
        if (
            not isinstance(result.proposed_checkpoint_update, str)
            or len(result.proposed_checkpoint_update) > MAX_REVIEW_FIELD_CHARS
        ):
            raise ExecutorAdapterError("proposed checkpoint update exceeds its bound")
        _validate_commands(result.test_commands, "test_commands", allow_empty=True)
        _validate_commands(result.validation_commands, "validation_commands", allow_empty=False)
        if not adapter_name:
            raise ExecutorAdapterError("adapter identity is empty")
        return result

    def _validate_change_paths(self, change_set: ChangeSet) -> None:
        for operation in change_set.operations:
            try:
                path = validate_relative_path(operation.path)
            except Exception as exc:
                raise ExecutionPreconditionError("unsafe change path") from exc
            folded = path.casefold()
            if folded == "docs/project-brain" or folded.startswith("docs/project-brain/"):
                raise CanonicalMutationError("Project Brain mutation is forbidden")
            if folded == ".git" or folded.startswith(".git/"):
                raise CanonicalMutationError("Git metadata mutation is forbidden")
            self.path_policy.check(path)

    def _gate_commands(self, result: ExecutorResult) -> None:
        for command in (*result.test_commands, *result.validation_commands):
            try:
                self.tool_policy.check(command)
            except Exception as exc:
                raise ExecutionToolError("command rejected by ToolPolicy") from exc

    def _capture_changed_files(
        self,
        workspace: Path,
        change_set: ChangeSet,
    ) -> dict[str, bytes | None]:
        captured: dict[str, bytes | None] = {}
        for operation in change_set.operations:
            path = validate_relative_path(operation.path)
            target = _safe_target(workspace, path)
            try:
                if not target.exists():
                    captured[path] = None
                    continue
                if not target.is_file():
                    raise ExecutionEvidenceError("changed target is not a regular file")
                content = target.read_bytes()
            except ExecutionError:
                raise
            except OSError as exc:
                raise ExecutionEvidenceError("changed target could not be read") from exc
            if len(content) > MAX_CHANGED_FILE_BYTES:
                raise ExecutionEvidenceError("changed target exceeds evidence bound")
            captured[path] = content
        return captured

    def _run_commands(
        self,
        commands: tuple[tuple[str, ...], ...],
        workspace: Path,
        change_set: ChangeSet,
    ) -> tuple[CommandEvidence, ...]:
        evidence: list[CommandEvidence] = []
        for command in commands:
            process = run_subprocess(
                command,
                cwd=workspace,
                tool_policy=self.tool_policy,
                model=change_set.model,
                effort=change_set.effort,
            )
            evidence.append(CommandEvidence.from_process(process))
        return tuple(evidence)

    def _build_diff(
        self,
        change_set: ChangeSet,
        before: dict[str, bytes | None],
        after: dict[str, bytes | None],
    ) -> tuple[DiffEvidence, ...]:
        result: list[DiffEvidence] = []
        for operation in sorted(change_set.operations, key=lambda item: item.path):
            path = validate_relative_path(operation.path)
            before_bytes = before.get(path)
            after_bytes = after.get(path)
            unified, binary, truncated = _bounded_diff(path, before_bytes, after_bytes)
            result.append(
                DiffEvidence(
                    path=path,
                    before_sha256=_sha256_or_none(before_bytes),
                    after_sha256=_sha256_or_none(after_bytes),
                    before_bytes=len(before_bytes or b""),
                    after_bytes=len(after_bytes or b""),
                    unified_diff=unified,
                    binary=binary,
                    truncated=truncated,
                )
            )
        return tuple(result)


def _same_uuid(value: object, expected: UUID) -> bool:
    try:
        return UUID(str(value)) == expected
    except (TypeError, ValueError, AttributeError):
        return False


def _attribute(value: object, name: str) -> object:
    return getattr(value, name, None)


def _state_value(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "")


def _validate_text_sequence(value: object, field_name: str) -> None:
    if not isinstance(value, tuple) or len(value) > MAX_COMMANDS:
        raise ExecutorAdapterError(f"{field_name} must be a bounded tuple")
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item) > MAX_REVIEW_FIELD_CHARS:
            raise ExecutorAdapterError(f"{field_name} contains invalid text")


def _validate_commands(
    commands: object,
    field_name: str,
    *,
    allow_empty: bool,
) -> None:
    if not isinstance(commands, tuple):
        raise ExecutorAdapterError(f"{field_name} must be a tuple")
    if not allow_empty and not commands:
        raise ExecutorAdapterError(f"{field_name} must contain at least one command")
    if len(commands) > MAX_COMMANDS:
        raise ExecutorAdapterError(f"{field_name} exceeds its command bound")
    for command in commands:
        if not isinstance(command, tuple) or not command or len(command) > MAX_COMMAND_ARGUMENTS:
            raise ExecutorAdapterError(f"{field_name} contains an invalid argv")
        for argument in command:
            if (
                not isinstance(argument, str)
                or not argument
                or len(argument) > MAX_COMMAND_ARGUMENT_CHARS
            ):
                raise ExecutorAdapterError(f"{field_name} contains an invalid argument")


def _safe_target(workspace: Path, relative_path: str) -> Path:
    root = workspace.resolve(strict=True)
    target = (root / relative_path).resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ExecutionPreconditionError("changed path escapes registered workspace") from exc
    return target


def _sha256_or_none(value: bytes | None) -> str | None:
    return hashlib.sha256(value).hexdigest() if value is not None else None


def _bounded_diff(
    path: str,
    before: bytes | None,
    after: bytes | None,
) -> tuple[str, bool, bool]:
    before_value = before or b""
    after_value = after or b""
    binary = b"\x00" in before_value or b"\x00" in after_value
    if binary:
        return "[binary diff omitted]", True, False
    try:
        before_text = before_value.decode("utf-8")
        after_text = after_value.decode("utf-8")
    except UnicodeDecodeError:
        return "[binary diff omitted]", True, False
    diff = "".join(
        difflib.unified_diff(
            before_text.splitlines(keepends=True),
            after_text.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        )
    )
    sanitized = _sanitize_text(diff)
    if len(sanitized) <= MAX_DIFF_CHARS:
        return sanitized, False, False
    return sanitized[:MAX_DIFF_CHARS] + "\n[diff truncated]", False, True


def _sanitize_argument(value: str, first: bool) -> str:
    if first and (_WINDOWS_ABSOLUTE_PATH.search(value) or value.startswith("/")):
        name = PureWindowsPath(value).name
        return _sanitize_text(name or "<executable>")
    return _bounded_sanitized_text(value, MAX_COMMAND_ARGUMENT_CHARS)


def _bounded_sanitized_text(value: str, limit: int) -> str:
    sanitized = _sanitize_text(value)
    if len(sanitized) <= limit:
        return sanitized
    return sanitized[:limit] + "\n[output truncated]"


def _sanitize_text(value: str) -> str:
    if not isinstance(value, str):
        return ""
    sanitized = _SECRET_PATTERN.sub("[REDACTED]", value)
    sanitized = _WINDOWS_ABSOLUTE_PATH.sub("[PATH]", sanitized)
    sanitized = _POSIX_ABSOLUTE_PATH.sub("[PATH]", sanitized)
    return sanitized


def _sanitize_sequence(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(_bounded_sanitized_text(value, MAX_REVIEW_FIELD_CHARS) for value in values)


def _filesystem_path_matches(value: str) -> list[str]:
    return [*_WINDOWS_ABSOLUTE_PATH.findall(value), *_POSIX_ABSOLUTE_PATH.findall(value)]


__all__ = [
    "CanonicalMutationError",
    "CommandEvidence",
    "DiffEvidence",
    "ExecutionContextError",
    "ExecutionError",
    "ExecutionEvidenceError",
    "ExecutionIdentity",
    "ExecutionIdentityError",
    "ExecutionOrchestrator",
    "ExecutionPreconditionError",
    "ExecutionResult",
    "ExecutorAdapter",
    "ExecutorAdapterError",
    "ExecutorAdapterResult",
    "ExecutorRequest",
    "ExecutorResult",
    "ExecutorReview",
    "ExecutionToolError",
    "HeadRaceError",
    "MIGRATION_HEAD",
]
