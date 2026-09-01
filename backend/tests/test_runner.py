from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

from app import runner as runner_module
from app.runner import (
    AdmissionLimits,
    ChangeOperation,
    ChangeSet,
    ChangeSetValidationError,
    PathPolicy,
    PathPolicyError,
    PreconditionError,
    ToolPolicy,
    ToolPolicyError,
    admit_change_set,
    apply_admitted,
    run_subprocess,
    verify_changed_files,
)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def test_safe_create_and_deterministic_verification(tmp_path: Path) -> None:
    change_set = ChangeSet.from_operations(
        [ChangeOperation.create("backend/new.py", "print('ok')\n")],
        model="test-model",
        effort="low",
    )

    admission = admit_change_set(
        change_set,
        tmp_path,
        policy=PathPolicy(allowed_prefixes=("backend",)),
    )
    result = apply_admitted(admission)

    assert result.status == "staged"
    assert result.verification.passed is True
    assert (tmp_path / "backend" / "new.py").read_text(encoding="utf-8") == "print('ok')\n"
    assert admission.change_set.model == "test-model"


def test_create_refuses_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "new.txt"
    target.write_bytes(b"existing")

    with pytest.raises(PreconditionError, match="refuses overwrite"):
        admit_change_set(
            ChangeSet.from_operations([ChangeOperation.create("new.txt", b"replacement")]),
            tmp_path,
        )


def test_valid_replace_and_stale_hash_refusal(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    original = b"before"
    target.write_bytes(original)
    operation = ChangeOperation.replace("file.txt", b"after", digest(original))

    admission = admit_change_set(ChangeSet.from_operations([operation]), tmp_path)
    assert apply_admitted(admission).verification.passed is True
    assert target.read_bytes() == b"after"

    target.write_bytes(b"changed externally")
    stale = ChangeOperation.replace("file.txt", b"new", digest(b"before"))
    with pytest.raises(PreconditionError, match="stale SHA-256"):
        admit_change_set(ChangeSet.from_operations([stale]), tmp_path)


@pytest.mark.parametrize("later_kind", ("replace", "delete"))
def test_apply_rechecks_later_target_before_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    later_kind: str,
) -> None:
    first_target = tmp_path / "first.txt"
    later_target = tmp_path / "later.txt"
    first_target.write_bytes(b"first before")
    later_target.write_bytes(b"later before")

    first_operation = ChangeOperation.replace(
        "first.txt",
        b"first after",
        digest(b"first before"),
    )
    if later_kind == "replace":
        later_operation = ChangeOperation.replace(
            "later.txt",
            b"runner later",
            digest(b"later before"),
        )
    else:
        later_operation = ChangeOperation.delete("later.txt", digest(b"later before"))

    admission = admit_change_set(
        ChangeSet.from_operations([first_operation, later_operation]),
        tmp_path,
    )

    original_replace = runner_module._replace_file
    mutation_count = 0

    def replace_and_mutate_later(path: Path, content: bytes) -> None:
        nonlocal mutation_count
        original_replace(path, content)
        mutation_count += 1
        if mutation_count == 1:
            later_target.write_bytes(b"changed externally")

    monkeypatch.setattr(runner_module, "_replace_file", replace_and_mutate_later)

    with pytest.raises(PreconditionError, match="during apply"):
        apply_admitted(admission)

    assert first_target.read_bytes() == b"first after"
    assert later_target.read_bytes() == b"changed externally"


def test_valid_delete_and_stale_hash_refusal(tmp_path: Path) -> None:
    target = tmp_path / "remove.txt"
    original = b"remove me"
    target.write_bytes(original)
    operation = ChangeOperation.delete("remove.txt", digest(original))

    admission = admit_change_set(ChangeSet.from_operations([operation]), tmp_path)
    assert apply_admitted(admission).verification.passed is True
    assert not target.exists()

    target.write_bytes(b"different")
    stale = ChangeOperation.delete("remove.txt", digest(original))
    with pytest.raises(PreconditionError, match="stale SHA-256"):
        admit_change_set(ChangeSet.from_operations([stale]), tmp_path)


def test_absolute_and_traversal_paths_are_rejected(tmp_path: Path) -> None:
    unsafe_paths = ("/tmp/outside", "../outside", "nested/../outside", "C:/outside", "nested\\file")
    for unsafe in unsafe_paths:
        with pytest.raises(PathPolicyError):
            admit_change_set(
                ChangeSet.from_operations([ChangeOperation.create(unsafe, b"x")]),
                tmp_path,
            )


def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"runner-outside-{tmp_path.name}"
    outside.mkdir()
    try:
        (tmp_path / "escape").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink unsupported: {exc}")

    with pytest.raises(PathPolicyError):
        admit_change_set(
            ChangeSet.from_operations([ChangeOperation.create("escape/file.txt", b"x")]),
            tmp_path,
        )


def test_allowlist_and_denylist_are_enforced(tmp_path: Path) -> None:
    with pytest.raises(PathPolicyError, match="allowlist"):
        admit_change_set(
            ChangeSet.from_operations([ChangeOperation.create("scripts/run.py", b"x")]),
            tmp_path,
            policy=PathPolicy(allowed_prefixes=("backend",)),
        )
    with pytest.raises(PathPolicyError, match="denied"):
        admit_change_set(
            ChangeSet.from_operations([ChangeOperation.create("docs/private.md", b"x")]),
            tmp_path,
            policy=PathPolicy(denied_prefixes=("docs",)),
        )


def test_operation_and_content_bounds_are_enforced(tmp_path: Path) -> None:
    too_many = ChangeSet.from_operations(
        [ChangeOperation.create(f"file-{index}.txt", b"x") for index in range(3)]
    )
    with pytest.raises(ChangeSetValidationError, match="operation count"):
        admit_change_set(too_many, tmp_path, limits=AdmissionLimits(max_operations=2))

    too_large = ChangeSet.from_operations([ChangeOperation.create("large.txt", b"12345")])
    with pytest.raises(ChangeSetValidationError, match="content size"):
        admit_change_set(too_large, tmp_path, limits=AdmissionLimits(max_content_bytes=4))


def test_verification_detects_external_changed_file(tmp_path: Path) -> None:
    admission = admit_change_set(
        ChangeSet.from_operations([ChangeOperation.create("one.txt", b"one")]),
        tmp_path,
    )
    (tmp_path / "one.txt").write_bytes(b"one")
    (tmp_path / "unexpected.txt").write_bytes(b"unexpected")

    result = verify_changed_files(admission)

    assert result.passed is False
    assert result.unexpected_changed_files == ("unexpected.txt",)


def test_subprocess_success_and_failure_capture_metadata() -> None:
    policy = ToolPolicy((sys.executable,))
    success = run_subprocess(
        [sys.executable, "-c", "print('ok')"],
        cwd=Path.cwd(),
        tool_policy=policy,
        model="runner-test-model",
        effort="medium",
    )
    assert success.succeeded is True
    assert success.returncode == 0
    assert success.stdout.strip() == "ok"
    assert success.model == "runner-test-model"
    assert success.effort == "medium"

    failure = run_subprocess(
        [sys.executable, "-c", "import sys; print('bad', file=sys.stderr); sys.exit(3)"],
        cwd=Path.cwd(),
        tool_policy=policy,
    )
    assert failure.succeeded is False
    assert failure.returncode == 3
    assert "bad" in failure.stderr


def test_subprocess_timeout_and_tool_gate_are_captured() -> None:
    policy = ToolPolicy((sys.executable,))
    evidence = run_subprocess(
        [sys.executable, "-c", "import time; time.sleep(2)"],
        cwd=Path.cwd(),
        tool_policy=policy,
        timeout_seconds=0.05,
    )

    assert evidence.timed_out is True
    assert evidence.returncode is None
    assert evidence.succeeded is False
    assert evidence.duration_seconds >= 0

    with pytest.raises(ToolPolicyError):
        run_subprocess(
            ["not-allowed", "--version"],
            cwd=Path.cwd(),
            tool_policy=policy,
        )


@pytest.mark.parametrize(
    "executable",
    ("bash.exe", "sh.exe", "BASH.EXE", "SH.EXE"),
)
def test_windows_shell_executable_variants_are_rejected(executable: str) -> None:
    policy = ToolPolicy((executable,))

    with pytest.raises(ToolPolicyError, match="shell executables"):
        policy.check([executable, "--version"])


def test_subprocess_environment_is_allowlisted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "must-not-reach-child")
    monkeypatch.setenv("PYTHONPATH", "must-not-reach-child")
    policy = ToolPolicy((sys.executable,))
    evidence = run_subprocess(
        [
            sys.executable,
            "-c",
            (
                "import os; "
                "print(os.getenv('AWS_SECRET_ACCESS_KEY', 'missing')); "
                "print(os.getenv('PYTHONPATH', 'missing')); "
                "print(bool(os.getenv('PATH', '')))"
            ),
        ],
        cwd=Path.cwd(),
        tool_policy=policy,
    )

    lines = evidence.stdout.splitlines()
    assert evidence.succeeded is True
    assert lines == ["missing", "missing", "True"]


def test_path_policy_rejects_case_alias_and_windows_reserved_paths(tmp_path: Path) -> None:
    with pytest.raises(PathPolicyError, match="denied"):
        admit_change_set(
            ChangeSet.from_operations(
                [ChangeOperation.create("DOCS/project-brain/escape.md", b"x")]
            ),
            tmp_path,
            policy=PathPolicy(denied_prefixes=("docs/project-brain",)),
        )

    for unsafe in ("CON", "dir/NUL.txt", "file.txt:stream", "trailing.", "trailing "):
        with pytest.raises(PathPolicyError):
            admit_change_set(
                ChangeSet.from_operations([ChangeOperation.create(unsafe, b"x")]),
                tmp_path,
            )


def test_change_set_rejects_case_alias_duplicates(tmp_path: Path) -> None:
    with pytest.raises(ChangeSetValidationError, match="more than once"):
        admit_change_set(
            ChangeSet.from_operations(
                [
                    ChangeOperation.create("Dir/File.txt", b"one"),
                    ChangeOperation.create("dir/file.txt", b"two"),
                ]
            ),
            tmp_path,
        )


def test_windows_superscript_device_aliases_are_rejected(tmp_path: Path) -> None:
    unsafe_paths = (
        "COM\u00b9",
        "COM\u00b2.txt",
        "COM\u00b3.log",
        "dir/LPT\u00b9",
        "dir/LPT\u00b2.txt",
        "dir/LPT\u00b3.log",
    )

    for unsafe in unsafe_paths:
        with pytest.raises(PathPolicyError):
            admit_change_set(
                ChangeSet.from_operations([ChangeOperation.create(unsafe, b"x")]),
                tmp_path,
            )
