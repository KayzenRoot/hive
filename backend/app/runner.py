from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import MappingProxyType

DEFAULT_MAX_OPERATIONS = 32
DEFAULT_MAX_CONTENT_BYTES = 1_048_576
DEFAULT_MAX_CAPTURE_BYTES = 64_000
DEFAULT_TIMEOUT_SECONDS = 30.0

_SAFE_ENV_NAMES = frozenset(
    {
        "LANG",
        "LC_ALL",
        "PATH",
        "PATHEXT",
        "PYTHONIOENCODING",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "WINDIR",
    }
)


class RunnerError(Exception):
    """Base class for local verified runner errors."""


class ChangeSetValidationError(RunnerError):
    """Raised when executor output is unsafe or malformed."""


class PathPolicyError(ChangeSetValidationError):
    """Raised when a path is invalid or outside the configured policy."""


class PreconditionError(ChangeSetValidationError):
    """Raised when a file precondition does not match the workspace."""


class ApplicationError(RunnerError):
    """Raised when an admitted change cannot be applied safely."""


class ToolPolicyError(RunnerError):
    """Raised when a subprocess is not admitted by the tool gate."""


class OperationKind(StrEnum):
    CREATE = "create"
    REPLACE = "replace"
    DELETE = "delete"


@dataclass(frozen=True, slots=True)
class ChangeOperation:
    """One bounded, structured file mutation proposed by an executor."""

    kind: OperationKind
    path: str
    content: bytes | None = None
    sha256_before: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, OperationKind):
            raise ChangeSetValidationError("operation kind is invalid")
        if not isinstance(self.path, str):
            raise ChangeSetValidationError("operation path must be text")
        if self.content is not None and not isinstance(self.content, bytes):
            raise ChangeSetValidationError("operation content must be bytes")
        if self.kind is OperationKind.CREATE:
            if self.content is None:
                raise ChangeSetValidationError("create requires content")
            if self.sha256_before is not None:
                raise ChangeSetValidationError("create cannot have a precondition")
        elif self.kind is OperationKind.REPLACE:
            if self.content is None:
                raise ChangeSetValidationError("replace requires content")
            _validate_digest(self.sha256_before, "replace")
        else:
            if self.content is not None:
                raise ChangeSetValidationError("delete cannot have content")
            _validate_digest(self.sha256_before, "delete")

    @classmethod
    def create(cls, path: str, content: bytes | str) -> ChangeOperation:
        return cls(OperationKind.CREATE, path, _as_bytes(content))

    @classmethod
    def replace(
        cls,
        path: str,
        content: bytes | str,
        sha256_before: str,
    ) -> ChangeOperation:
        return cls(OperationKind.REPLACE, path, _as_bytes(content), sha256_before)

    @classmethod
    def delete(cls, path: str, sha256_before: str) -> ChangeOperation:
        return cls(OperationKind.DELETE, path, None, sha256_before)

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {"kind": self.kind.value, "path": self.path}
        if self.content is not None:
            result["content_base64"] = base64.b64encode(self.content).decode("ascii")
        if self.sha256_before is not None:
            result["sha256_before"] = self.sha256_before
        return result


@dataclass(frozen=True, slots=True)
class PathPolicy:
    """Portable allow/deny policy for paths relative to a workspace."""

    allowed_prefixes: tuple[str, ...] = ()
    denied_prefixes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value in (*self.allowed_prefixes, *self.denied_prefixes):
            _validate_policy_prefix(value)

    def check(self, relative_path: str) -> None:
        path = validate_relative_path(relative_path)
        if self.denied_prefixes and any(
            _is_same_or_child(path, prefix) for prefix in self.denied_prefixes
        ):
            raise PathPolicyError(f"path is denied by policy: {relative_path}")
        if self.allowed_prefixes and not any(
            _is_same_or_child(path, prefix) for prefix in self.allowed_prefixes
        ):
            raise PathPolicyError(f"path is outside the allowlist: {relative_path}")


@dataclass(frozen=True, slots=True)
class ToolPolicy:
    """Fail-closed allowlist for structured subprocess execution."""

    allowed_executables: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.allowed_executables:
            raise ValueError("at least one executable must be allowed")
        if any(not executable for executable in self.allowed_executables):
            raise ValueError("allowed executable names cannot be empty")

    def check(self, argv: Sequence[str]) -> None:
        if not argv or argv[0] not in self.allowed_executables:
            raise ToolPolicyError("executable is not allowed by the tool policy")
        shell_names = {"sh", "bash", "zsh", "fish", "cmd", "cmd.exe", "powershell", "pwsh"}
        executable_name = PureWindowsPath(argv[0]).name.casefold()
        if executable_name in shell_names:
            raise ToolPolicyError("shell executables are not allowed")


@dataclass(frozen=True, slots=True)
class ChangeSet:
    """Immutable executor output admitted as a bounded change set."""

    operations: tuple[ChangeOperation, ...]
    model: str = "unknown"
    effort: str = "unknown"
    request_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.operations, tuple):
            raise ChangeSetValidationError("operations must be a tuple")
        if any(not isinstance(operation, ChangeOperation) for operation in self.operations):
            raise ChangeSetValidationError("operations contain an invalid value")
        if not self.model.strip():
            raise ChangeSetValidationError("model metadata is required")
        if not self.effort.strip():
            raise ChangeSetValidationError("effort metadata is required")
        if self.request_id is not None and not self.request_id.strip():
            raise ChangeSetValidationError("request_id cannot be empty")

    @classmethod
    def from_operations(
        cls,
        operations: Sequence[ChangeOperation],
        *,
        model: str = "unknown",
        effort: str = "unknown",
        request_id: str | None = None,
    ) -> ChangeSet:
        return cls(tuple(operations), model, effort, request_id)

    def total_content_bytes(self) -> int:
        return sum(len(operation.content or b"") for operation in self.operations)

    def as_dict(self) -> dict[str, object]:
        return {
            "operations": [operation.as_dict() for operation in self.operations],
            "model": self.model,
            "effort": self.effort,
            "request_id": self.request_id,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.as_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


@dataclass(frozen=True, slots=True)
class AdmissionLimits:
    max_operations: int = DEFAULT_MAX_OPERATIONS
    max_content_bytes: int = DEFAULT_MAX_CONTENT_BYTES

    def __post_init__(self) -> None:
        if self.max_operations < 1:
            raise ValueError("max_operations must be positive")
        if self.max_content_bytes < 0:
            raise ValueError("max_content_bytes cannot be negative")


@dataclass(frozen=True, slots=True)
class Admission:
    """Validated staged result; admission does not mutate the workspace."""

    change_set: ChangeSet
    workspace: Path
    normalized_paths: tuple[str, ...]
    before_sha256: Mapping[str, str]
    expected_sha256: Mapping[str, str | None]

    def as_dict(self) -> dict[str, object]:
        return {
            "change_set": self.change_set.as_dict(),
            "workspace": str(self.workspace),
            "normalized_paths": list(self.normalized_paths),
            "before_file_count": len(self.before_sha256),
            "expected_sha256": dict(self.expected_sha256),
            "status": "admitted",
        }


@dataclass(frozen=True, slots=True)
class FileVerification:
    path: str
    expected_sha256: str | None
    actual_sha256: str | None
    status: str

    def as_dict(self) -> dict[str, str | None]:
        return {
            "path": self.path,
            "expected_sha256": self.expected_sha256,
            "actual_sha256": self.actual_sha256,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Deterministic comparison of the admitted target files and workspace."""

    passed: bool
    files: tuple[FileVerification, ...]
    unexpected_changed_files: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "files": [item.as_dict() for item in self.files],
            "unexpected_changed_files": list(self.unexpected_changed_files),
        }


@dataclass(frozen=True, slots=True)
class ApplyResult:
    """Result of applying an admitted change set without implicit promotion."""

    applied_paths: tuple[str, ...]
    verification: VerificationResult
    status: str = "staged"

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "applied_paths": list(self.applied_paths),
            "verification": self.verification.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class ProcessEvidence:
    """Bounded, secret-free evidence for one approved local subprocess."""

    argv: tuple[str, ...]
    returncode: int | None
    timed_out: bool
    stdout: str
    stderr: str
    duration_seconds: float
    model: str = "unknown"
    effort: str = "unknown"

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    def as_dict(self) -> dict[str, object]:
        return {
            "argv": list(self.argv),
            "returncode": self.returncode,
            "timed_out": self.timed_out,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_seconds": self.duration_seconds,
            "model": self.model,
            "effort": self.effort,
        }


@dataclass(frozen=True, slots=True)
class StagedRun:
    """Complete staged evidence for future PR and telemetry adapters."""

    admission: Admission
    apply: ApplyResult | None = None
    process: tuple[ProcessEvidence, ...] = ()
    promoted: bool = False

    def __post_init__(self) -> None:
        if self.promoted:
            raise ChangeSetValidationError("automatic canonical promotion is not supported")

    def as_dict(self) -> dict[str, object]:
        return {
            "status": "staged",
            "promoted": False,
            "admission": self.admission.as_dict(),
            "apply": self.apply.as_dict() if self.apply is not None else None,
            "process": [item.as_dict() for item in self.process],
        }


def _as_bytes(content: bytes | str) -> bytes:
    if isinstance(content, bytes):
        return content
    if isinstance(content, str):
        return content.encode("utf-8")
    raise ChangeSetValidationError("content must be bytes or text")


def _validate_digest(value: str | None, operation: str) -> None:
    if value is None or len(value) != 64:
        raise ChangeSetValidationError(f"{operation} requires a 64-character SHA-256 precondition")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ChangeSetValidationError(f"{operation} has an invalid SHA-256 precondition") from exc


def _validate_policy_prefix(value: str) -> None:
    if not value:
        raise ValueError("policy prefixes cannot be empty")
    validate_relative_path(value)


_WINDOWS_RESERVED_BASE_NAMES = frozenset(
    {
        "aux",
        "com1",
        "com2",
        "com3",
        "com4",
        "com5",
        "com6",
        "com7",
        "com8",
        "com9",
        "com\u00b9",
        "com\u00b2",
        "com\u00b3",
        "con",
        "lpt1",
        "lpt2",
        "lpt3",
        "lpt4",
        "lpt5",
        "lpt6",
        "lpt7",
        "lpt8",
        "lpt9",
        "lpt\u00b9",
        "lpt\u00b2",
        "lpt\u00b3",
        "nul",
        "prn",
    }
)


def _is_windows_unsafe_component(part: str) -> bool:
    if part.endswith((" ", ".")):
        return True
    if any(ord(character) < 32 or character in '< >:"|?*'.replace(" ", "") for character in part):
        return True
    base_name = part.split(".", 1)[0].casefold()
    return base_name in _WINDOWS_RESERVED_BASE_NAMES


def validate_relative_path(value: str) -> str:
    """Return a normalized portable relative path or raise a policy error."""
    if not isinstance(value, str) or not value or "\x00" in value:
        raise PathPolicyError("path must be non-empty and cannot contain NUL")
    if "\\" in value:
        raise PathPolicyError("path must use '/' separators")
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        raise PathPolicyError(f"path must be relative: {value}")
    parts = posix.parts
    if any(_is_windows_unsafe_component(part) for part in parts):
        raise PathPolicyError(f"path is reserved or ambiguous on Windows: {value}")
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise PathPolicyError(f"path must be normalized and traversal-free: {value}")
    normalized = "/".join(parts)
    if normalized != value:
        raise PathPolicyError(f"path must be normalized: {value}")
    return normalized


def _is_same_or_child(path: str, prefix: str) -> bool:
    normalized_path = path.casefold()
    normalized_prefix = prefix.casefold()
    return normalized_path == normalized_prefix or normalized_path.startswith(
        normalized_prefix + "/"
    )


def _workspace_root(workspace: Path) -> Path:
    try:
        root = workspace.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise PathPolicyError("workspace cannot be resolved") from exc
    if not root.is_dir():
        raise PathPolicyError("workspace must be a directory")
    return root


def _safe_target(workspace: Path, relative_path: str) -> Path:
    root = _workspace_root(workspace)
    target = (root / relative_path).resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise PathPolicyError(f"path escapes workspace: {relative_path}") from exc
    return target


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(65_536), b""):
                digest.update(block)
    except OSError as exc:
        raise ApplicationError(f"cannot read file: {path}") from exc
    return digest.hexdigest()


def _current_digest(path: Path) -> str | None:
    if not path.exists():
        return None
    if not path.is_file():
        raise PreconditionError(f"target is not a regular file: {path}")
    return _digest_file(path)


def _snapshot_files(root: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for candidate in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if candidate.is_symlink():
            try:
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(root)
            except (OSError, RuntimeError, ValueError) as exc:
                raise PathPolicyError("workspace contains a symlink outside its boundary") from exc
            if not resolved.is_file():
                continue
            digest_path = resolved
        elif candidate.is_file():
            digest_path = candidate
        else:
            continue
        relative = candidate.relative_to(root).as_posix()
        snapshot[validate_relative_path(relative)] = _digest_file(digest_path)
    return snapshot


def admit_change_set(
    change_set: ChangeSet,
    workspace: Path,
    *,
    policy: PathPolicy | None = None,
    limits: AdmissionLimits | None = None,
) -> Admission:
    """Validate executor output and capture pre-state without mutation."""
    active_policy = policy or PathPolicy()
    active_limits = limits or AdmissionLimits()
    if not change_set.operations:
        raise ChangeSetValidationError("change set must contain at least one operation")
    if len(change_set.operations) > active_limits.max_operations:
        raise ChangeSetValidationError("operation count exceeds configured bound")
    if change_set.total_content_bytes() > active_limits.max_content_bytes:
        raise ChangeSetValidationError("content size exceeds configured bound")

    root = _workspace_root(workspace)
    before = _snapshot_files(root)
    normalized: list[str] = []
    expected: dict[str, str | None] = {}
    seen: set[str] = set()
    for operation in change_set.operations:
        relative_path = validate_relative_path(operation.path)
        active_policy.check(relative_path)
        identity = relative_path.casefold()
        if identity in seen:
            raise ChangeSetValidationError(f"path appears more than once: {relative_path}")
        if any(
            _is_same_or_child(identity, previous) or _is_same_or_child(previous, identity)
            for previous in seen
        ):
            raise ChangeSetValidationError("change set contains conflicting paths")
        seen.add(identity)
        target = _safe_target(root, relative_path)
        current = _current_digest(target)
        if operation.kind is OperationKind.CREATE and target.exists():
            raise PreconditionError(f"create refuses overwrite: {relative_path}")
        if (
            operation.kind in (OperationKind.REPLACE, OperationKind.DELETE)
            and current != operation.sha256_before
        ):
            raise PreconditionError(f"stale SHA-256 precondition: {relative_path}")
        normalized.append(relative_path)
        expected[relative_path] = _expected_digest(operation)
    return Admission(
        change_set,
        root,
        tuple(normalized),
        MappingProxyType(before),
        MappingProxyType(expected),
    )


def _expected_digest(operation: ChangeOperation) -> str | None:
    if operation.kind is OperationKind.DELETE:
        return None
    if operation.content is None:
        raise ChangeSetValidationError("file operation content is missing")
    return hashlib.sha256(operation.content).hexdigest()


def _check_operation_state(operation: ChangeOperation, target: Path) -> None:
    if operation.kind is OperationKind.CREATE:
        if target.exists():
            raise PreconditionError(f"create refuses overwrite: {target}")
        return
    if operation.sha256_before is None:
        raise ApplicationError(f"precondition missing: {target}")
    if _current_digest(target) != operation.sha256_before:
        raise PreconditionError(f"stale SHA-256 precondition during apply: {target}")


def _write_new_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(content)
    except FileExistsError as exc:
        raise ApplicationError(f"create refuses overwrite: {path}") from exc
    except OSError as exc:
        raise ApplicationError(f"cannot create file: {path}") from exc


def _replace_file(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.hive-tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
        os.replace(temporary, path)
    except FileExistsError as exc:
        raise ApplicationError(f"temporary target already exists: {temporary}") from exc
    except OSError as exc:
        raise ApplicationError(f"cannot replace file: {path}") from exc
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def _delete_file(path: Path) -> None:
    try:
        path.unlink()
    except OSError as exc:
        raise ApplicationError(f"cannot delete file: {path}") from exc


def apply_admitted(admission: Admission) -> ApplyResult:
    """Apply an admitted set, then verify its deterministic result."""
    operations = admission.change_set.operations
    targets = [
        (operation, _safe_target(admission.workspace, relative_path))
        for operation, relative_path in zip(
            operations,
            admission.normalized_paths,
            strict=True,
        )
    ]
    for operation, target in targets:
        _check_operation_state(operation, target)

    applied: list[str] = []
    for operation, relative_path in zip(operations, admission.normalized_paths, strict=True):
        target = _safe_target(admission.workspace, relative_path)
        if operation.kind is OperationKind.CREATE:
            if operation.content is None:
                raise ApplicationError(f"content missing for create: {relative_path}")
            _write_new_file(target, operation.content)
        elif operation.kind is OperationKind.REPLACE:
            if operation.content is None:
                raise ApplicationError(f"content missing for replace: {relative_path}")
            _replace_file(target, operation.content)
        else:
            _delete_file(target)
        applied.append(relative_path)

    verification = verify_changed_files(admission)
    if not verification.passed:
        raise ApplicationError("deterministic changed-file verification failed")
    return ApplyResult(tuple(applied), verification)


def verify_changed_files(admission: Admission) -> VerificationResult:
    """Verify targets and identify files changed outside the admitted set."""
    after = _snapshot_files(admission.workspace)
    files: list[FileVerification] = []
    for relative_path in admission.normalized_paths:
        expected = admission.expected_sha256[relative_path]
        actual = after.get(relative_path)
        status = "ok" if actual == expected else "mismatch"
        files.append(FileVerification(relative_path, expected, actual, status))

    unexpected: list[str] = []
    all_paths = set(admission.before_sha256) | set(after)
    expected_paths = set(admission.expected_sha256)
    for relative_path in sorted(all_paths - expected_paths):
        if admission.before_sha256.get(relative_path) != after.get(relative_path):
            unexpected.append(relative_path)
    passed = not unexpected and all(item.status == "ok" for item in files)
    return VerificationResult(passed, tuple(files), tuple(unexpected))


def run_subprocess(
    argv: Sequence[str],
    *,
    cwd: Path,
    tool_policy: ToolPolicy,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    capture_limit_bytes: int = DEFAULT_MAX_CAPTURE_BYTES,
    model: str = "unknown",
    effort: str = "unknown",
) -> ProcessEvidence:
    """Run one gated argv and return bounded, secret-free evidence."""
    if not argv or any(not isinstance(argument, str) or not argument for argument in argv):
        raise ValueError("argv must contain non-empty strings")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if capture_limit_bytes < 0:
        raise ValueError("capture_limit_bytes cannot be negative")
    tool_policy.check(argv)
    start = time.monotonic()
    safe_environment = {key: value for key, value in os.environ.items() if key in _SAFE_ENV_NAMES}
    try:
        completed = subprocess.run(
            list(argv),
            cwd=cwd,
            shell=False,
            check=False,
            capture_output=True,
            text=False,
            timeout=timeout_seconds,
            env=safe_environment,
        )
        returncode: int | None = completed.returncode
        timed_out = False
        stdout = _bounded_text(completed.stdout, capture_limit_bytes)
        stderr = _bounded_text(completed.stderr, capture_limit_bytes)
    except subprocess.TimeoutExpired as exc:
        returncode = None
        timed_out = True
        stdout = _bounded_text(exc.stdout, capture_limit_bytes)
        stderr = _bounded_text(exc.stderr, capture_limit_bytes)
    except OSError as exc:
        returncode = None
        timed_out = False
        stdout = ""
        stderr = str(exc)
    duration = time.monotonic() - start
    return ProcessEvidence(
        tuple(argv),
        returncode,
        timed_out,
        stdout,
        stderr,
        duration,
        model=model,
        effort=effort,
    )


def _bounded_text(value: bytes | str | None, limit: int) -> str:
    if value is None:
        return ""
    raw = value if isinstance(value, bytes) else value.encode("utf-8", errors="replace")
    clipped = raw[:limit]
    suffix = "\n[output truncated]" if len(raw) > limit else ""
    return clipped.decode("utf-8", errors="replace") + suffix
