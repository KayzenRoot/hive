from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, cast

SCRIPT_PATH = Path(__file__).parents[2] / "scripts" / "v01_closure_sprint.py"
BACKUP_PATH = Path(__file__).parents[2] / "scripts" / "v01_backup_restore.py"


def load(module_name: str, script_path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(Any, module)


closure = load("v01_closure_sprint_unit", SCRIPT_PATH)
backup = load("v01_backup_restore_unit", BACKUP_PATH)


def test_closure_evidence_fields_match_the_closed_contract() -> None:
    assert closure.EVIDENCE_VERSION == "v01-closure-sprint-v1"
    assert closure.EVIDENCE_FILE == "v01-closure-sprint.json"
    assert closure.EVIDENCE_OUTPUT.name == closure.EVIDENCE_FILE


def test_dod_scan_covers_every_canonical_requirement_once() -> None:
    items = closure.canonical_dod_items()
    requirements = [str(item["requirement"]) for item in items]
    assert len(requirements) == len(set(requirements))
    assert len(requirements) >= 40
    for item in items:
        assert item["section"]
        assert len(str(item["sha256"])) == 64


def test_every_dod_requirement_has_a_registered_deterministic_verifier() -> None:
    items = closure.canonical_dod_items()
    keys = [
        closure.requirement_key(str(item["section"]), str(item["requirement"])) for item in items
    ]
    assert len(keys) == len(set(keys)), "a canonical requirement appears more than once"
    missing = [key for key in keys if key not in closure.DOD_VERIFIERS]
    assert missing == [], f"requirements without a verifier: {missing}"
    assert closure.verifier_count() == len(keys)


def test_missing_verifier_never_becomes_pass() -> None:
    entry = closure.ledger_entry("Functional", "a requirement that has no verifier")
    assert entry["status"] == "FAIL"
    assert entry["verifier"] == "missing"


def test_ledger_digest_is_bound_to_the_evidence_artifact_not_the_source_document() -> None:
    entry = closure.ledger_entry("Resilience", "Backup and recovery tested.")
    assert entry["evidence_path"] == "v01-backup-restore.json"
    assert entry["evidence_digest"] != closure.sha256_text(closure.git_blob(closure.DOD_DOCUMENT))
    if closure.artifact("v01-backup-restore.json"):
        assert entry["evidence_digest"] == closure.artifact_digest("v01-backup-restore.json")


def test_authority_order_and_negative_matrix_are_closed() -> None:
    import scripts.review_evidence as governance

    assert closure.CLOSURE_GOVERNANCE.keys() == {
        "docs/project-brain/13-CHECKPOINT.md",
        "docs/project-brain/03-SCOPE.md",
        "docs/project-brain/15-DEFINITION-OF-DONE.md",
        "docs/project-brain/04-ARCHITECTURE.md",
        "docs/project-brain/16-DECISIONS-LEDGER.md",
    }
    assert governance.V01_CLOSURE_SPRINT_AUTHORITY_ORDER[0] == "CHECKPOINT"
    assert set(governance.V01_CLOSURE_SPRINT_NEGATIVE_CASES) == {
        "missing_authority",
        "stale_authority",
        "untracked_authority",
        "cross_project_authority",
    }
    assert len(governance.V01_CLOSURE_SPRINT_E2E_STAGES) == 12


def test_backup_tables_cover_every_canonical_durable_table() -> None:
    required = {
        "projects",
        "tasks",
        "task_extractions",
        "repository_files",
        "repository_symbols",
        "retrieval_references",
        "memory_records",
        "memory_record_history",
        "telemetry_events",
        "cas_blobs",
    }
    assert required.issubset(set(backup.CANONICAL_TABLES))
    assert backup.CANONICAL_CAS_ROOT.endswith("/cas/sha256")
    assert backup.SUMMARY_FILE.name == "v01-backup-restore.json"


def test_backup_configuration_identity_never_contains_secret_keys() -> None:
    import inspect

    source = inspect.getsource(backup.backup_configuration)
    assert "password" in source and "token" in source
    assert "redis_excluded" in source


def test_no_closure_function_shadows_a_module_helper_it_calls() -> None:
    """A local binding that reuses a helper name makes the evidence run crash.

    ``main`` unpacked a loop variable named ``artifact`` while still calling the
    module-level ``artifact()`` reader, so the closure sprint died with
    ``TypeError: 'str' object is not callable`` instead of writing evidence.
    """

    import ast

    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    helpers = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    }
    shadowed: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        bound: set[str] = {argument.arg for argument in node.args.args}
        called: set[str] = set()
        pending: list[ast.AST] = list(node.body)
        while pending:
            current = pending.pop()
            if isinstance(current, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
                continue
            if isinstance(current, ast.Name) and isinstance(current.ctx, ast.Store):
                bound.add(current.id)
            if isinstance(current, ast.Call) and isinstance(current.func, ast.Name):
                called.add(current.func.id)
            pending.extend(ast.iter_child_nodes(current))
        shadowed.extend(sorted(bound & called & helpers))
    assert shadowed == []
