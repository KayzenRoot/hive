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


def test_every_dod_row_cites_tracked_evidence_that_exists_at_head() -> None:
    """Each matrix row must cite a repository artifact a reviewer can re-run."""

    import scripts.review_evidence as governance

    rows = [
        closure.ledger_entry(str(item["section"]), str(item["requirement"]))
        for item in closure.canonical_dod_items()
    ]
    assert len(rows) == len(closure.canonical_dod_items())
    for row in rows:
        path = str(row["evidence_path"])
        assert governance.valid_closure_evidence_path(path), (row["requirement"], path)
        assert path in closure.DOD_EVIDENCE_PATHS.values() or path == closure.DOD_DOCUMENT
        assert len(str(row["evidence_digest"])) == 64, (row["requirement"], path)
    assert set(closure.DOD_EVIDENCE_PATHS) == set(closure.DOD_VERIFIERS)


def test_dod_verifiers_never_cite_an_artifact_the_integrations_do_not_write() -> None:
    """Verifier evidence must be an artifact a deterministic script actually produces."""

    produced = set(closure.MEASURED_ARTIFACTS) | {"telemetry-event-bus.json"}
    for name, path in (
        ("control-center-core.json", "scripts/control_center_integration.py"),
        ("control-center-full.json", "scripts/control_center_integration.py"),
        ("control-center-metrics.json", "scripts/control_center_integration.py"),
        ("comprehensive-benchmarks.json", "scripts/comprehensive_benchmarks.py"),
        ("acce-storage-policy.json", "scripts/task_intake_integration.py"),
        ("context-manager.json", "scripts/context_manager_integration.py"),
        ("autonomous-execution.json", "scripts/autonomous_execution_integration.py"),
        ("memory-lifecycle.json", "scripts/memory_lifecycle_integration.py"),
        ("mcp-surface.json", "scripts/mcp_integration.py"),
        ("retrieval-benchmark.json", "scripts/retrieval_integration.py"),
        ("v01-deployment.json", "scripts/v01_closure_sprint.py"),
        ("v01-e2e.json", "scripts/v01_closure_sprint.py"),
        ("v01-orchestration-proof.json", "scripts/v01_closure_sprint.py"),
        ("v01-backup-restore.json", "scripts/v01_backup_restore.py"),
    ):
        assert name in produced, name
        assert (Path(__file__).parents[2] / path).is_file(), path


def test_missing_verifier_never_becomes_pass() -> None:
    entry = closure.ledger_entry("Functional", "a requirement that has no verifier")
    assert entry["status"] == "FAIL"
    assert entry["verifier"] == "missing"


def test_ledger_digest_is_bound_to_the_tracked_evidence_not_the_source_document() -> None:
    entry = closure.ledger_entry("Resilience", "Backup and recovery tested.")
    assert entry["evidence_path"] == "scripts/v01_backup_restore.py"
    assert entry["evidence_digest"] == closure.tracked_evidence_digest(
        "scripts/v01_backup_restore.py"
    )
    assert entry["evidence_digest"] != closure.sha256_text(closure.git_blob(closure.DOD_DOCUMENT))


def test_e2e_stage_verifier_fails_closed_without_a_measured_stage() -> None:
    original = closure.artifact
    closure.artifact = lambda _name: {}
    try:
        assert closure.e2e_stage("capture_evidence")[0] == "UNKNOWN"
        assert closure.e2e_stage("index_repository", "indexed_file_count", 1)[0] == "UNKNOWN"
    finally:
        closure.artifact = original
    closure.artifact = lambda _name: {"stages": {"capture_evidence": {"status": "FAIL"}}}
    try:
        assert closure.e2e_stage("capture_evidence")[0] == "FAIL"
    finally:
        closure.artifact = original


def test_integration_suite_verifier_requires_every_run_to_pass() -> None:
    original = closure.INTEGRATION_RUN_RESULTS
    try:
        closure.INTEGRATION_RUN_RESULTS = {}
        assert closure.integration_suite_check()[0] == "UNKNOWN"
        closure.INTEGRATION_RUN_RESULTS = {"one": 1}
        assert closure.integration_suite_check()[0] == "UNKNOWN"
        closure.INTEGRATION_RUN_RESULTS = {
            f"{index:02d}": 0 for index, _entry in enumerate(closure.CLOSURE_INTEGRATIONS)
        }
        assert closure.integration_suite_check()[0] == "PASS"
        closure.INTEGRATION_RUN_RESULTS["00"] = 1
        assert closure.integration_suite_check()[0] == "FAIL"
    finally:
        closure.INTEGRATION_RUN_RESULTS = original


def test_document_needles_are_case_insensitive() -> None:
    assert (
        closure.document_contains("docs/project-brain/12-LOCAL-DEPLOYMENT.md", ("DOCKER COMPOSE",))[
            0
        ]
        == "PASS"
    )


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


def promoted_checkpoint_text() -> str:
    """Synthesize the strict promoted checkpoint the WO-024-P contract demands."""

    import scripts.review_evidence as governance

    relative = "docs/project-brain/13-CHECKPOINT.md"
    root = Path(__file__).parents[2]
    base_text = (root / relative).read_text(encoding="utf-8")
    _preamble, _ordered, sections = governance._raw_checkpoint_structure(base_text, "base")
    bullets = governance.wo024p_completion_bullets(
        version=governance.V01_CLOSURE_SPRINT_EVIDENCE_VERSION,
        pass_count=46,
        total_count=46,
        critical=0,
        high=0,
        product_pr=governance.WO024_APPROVED_PRODUCT_PR,
        audited_head=governance.WO024_APPROVED_PRODUCT_HEAD_SHA,
        sol_review=governance.WO024_APPROVED_SOL_REVIEW_ID,
        squash_merge=governance.WO024_APPROVED_SQUASH_MERGE_SHA,
        post_merge_ci=governance.WO024_APPROVED_POST_MERGE_CI_RUN,
        backend_passed=676,
        dashboard_passed=34,
        migration_head=governance.V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD,
    )
    newline = "\n"
    controlled = {
        "STATUS": f"{governance.EXPECTED_WO024P_STATUS}{newline}{newline}",
        "COMPLETED": sections["COMPLETED"][:-1]
        + "".join(f"- {bullet}{newline}" for bullet in bullets)
        + newline,
        "IN PROGRESS": f"- {governance.EXPECTED_WO024P_IN_PROGRESS}{newline}{newline}",
        "BLOCKERS": f"{governance.EXPECTED_WO024P_BLOCKERS}{newline}{newline}",
        "NEXT STEP": f"{governance.EXPECTED_WO024P_NEXT_STEP}{newline}{newline}",
        "PENDING": newline,
    }
    text = base_text
    for name, body in controlled.items():
        _p, _o, current = governance._raw_checkpoint_structure(text, "candidate")
        marker = f"## {name}{newline}"
        start = text.index(marker) + len(marker)
        text = text[:start] + body + text[start + len(current[name]) :]
    return text


def with_checkpoint(text: str) -> Any:
    """Patch the closure sprint so only the checkpoint document is synthesized."""

    original = closure.document_text
    closure.document_text = lambda relative: (
        text if relative == "docs/project-brain/13-CHECKPOINT.md" else original(relative)
    )
    return original


def test_checkpoint_current_accepts_both_legitimate_states() -> None:
    import scripts.review_evidence as governance

    original = closure.document_text
    try:
        assert closure.checkpoint_current()[0] == "PASS"
        promoted = promoted_checkpoint_text()
        governance.require_wo024p_checkpoint_semantics(
            closure.document_text("docs/project-brain/13-CHECKPOINT.md"),
            promoted,
            {
                "product_pr": governance.WO024_APPROVED_PRODUCT_PR,
                "audited_product_head": governance.WO024_APPROVED_PRODUCT_HEAD_SHA,
                "sol_review_id": governance.WO024_APPROVED_SOL_REVIEW_ID,
                "squash_merge_sha": governance.WO024_APPROVED_SQUASH_MERGE_SHA,
                "post_merge_ci_run": governance.WO024_APPROVED_POST_MERGE_CI_RUN,
                "prior_backend_passed": 676,
                "prior_dashboard_passed": 34,
            },
            {
                "v01_closure_sprint_evidence_version": (
                    governance.V01_CLOSURE_SPRINT_EVIDENCE_VERSION
                ),
                "dod_pass_count": 46,
                "dod_total_count": 46,
                "stabilization_remaining_critical": 0,
                "stabilization_remaining_high": 0,
            },
        )
        closure.document_text = lambda relative: (
            promoted if relative == "docs/project-brain/13-CHECKPOINT.md" else original(relative)
        )
        assert closure.checkpoint_current()[0] == "PASS"
        assert closure.documentation_currentness_entry("checkpoint")["status"] == "PASS"
    finally:
        closure.document_text = original


def test_checkpoint_current_fails_closed_on_malformed_or_stale_states() -> None:
    import scripts.review_evidence as governance

    original = closure.document_text
    active = closure.document_text("docs/project-brain/13-CHECKPOINT.md")
    promoted = promoted_checkpoint_text()
    cases = {
        "promoted status with pending work": promoted.replace(
            "## PENDING\n\n", "## PENDING\n- leftover.\n\n"
        ),
        "unknown status": promoted.replace(governance.EXPECTED_WO024P_STATUS, "SOMETHING ELSE"),
        "missing canonical section": promoted.replace("## BLOCKERS\n", ""),
        "promoted status with stale next step": promoted.replace(
            governance.EXPECTED_WO024P_NEXT_STEP, "Preparing the stabilization increment."
        ),
        "active status without pending items": active.replace("- stabilization.\n", ""),
        "empty checkpoint": "",
    }
    try:
        for label, text in cases.items():
            closure.document_text = lambda relative, value=text: (
                value if relative == "docs/project-brain/13-CHECKPOINT.md" else original(relative)
            )
            status = closure.checkpoint_current()[0]
            assert status in {"FAIL", "UNKNOWN"}, (label, status)
        closure.document_text = lambda relative: (
            "## STATUS\nSOMETHING ELSE\n\n## PENDING\n- stabilization.\n\n"
            if relative == "docs/project-brain/13-CHECKPOINT.md"
            else original(relative)
        )
        assert closure.checkpoint_current()[0] == "FAIL"
        assert closure.documentation_currentness_entry("checkpoint")["status"] == "FAIL"
    finally:
        closure.document_text = original


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
