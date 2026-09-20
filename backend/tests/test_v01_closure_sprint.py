from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, cast

import pytest

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


CHECKPOINT_RELATIVE = "docs/project-brain/13-CHECKPOINT.md"


def wo024p_lineage_fixture() -> dict[str, object]:
    """The approved WO-024 lineage values the promotion contract consumes."""

    import scripts.review_evidence as governance

    return {
        "product_pr": governance.WO024_APPROVED_PRODUCT_PR,
        "audited_product_head": governance.WO024_APPROVED_PRODUCT_HEAD_SHA,
        "sol_review_id": governance.WO024_APPROVED_SOL_REVIEW_ID,
        "squash_merge_sha": governance.WO024_APPROVED_SQUASH_MERGE_SHA,
        "post_merge_ci_run": governance.WO024_APPROVED_POST_MERGE_CI_RUN,
        "prior_backend_passed": 676,
        "prior_dashboard_passed": 34,
    }


def wo024p_closure_fixture() -> dict[str, object]:
    """The measured closure values the promotion contract consumes."""

    import scripts.review_evidence as governance

    return {
        "v01_closure_sprint_evidence_version": governance.V01_CLOSURE_SPRINT_EVIDENCE_VERSION,
        "dod_pass_count": 46,
        "dod_total_count": 46,
        "stabilization_remaining_critical": 0,
        "stabilization_remaining_high": 0,
    }


def synthesized_checkpoint_pair() -> tuple[str, str]:
    """Build a pre-promotion checkpoint and its promoted successor deterministically.

    Both texts are synthesized from the contract's own expectations, so this regression holds
    whether the working tree currently holds the pre-promotion checkpoint or the final promoted
    checkpoint. The live checkpoint is never used as a promotion base, and the promoted
    checkpoint is never presented to the contract as that base.
    """

    import scripts.review_evidence as governance

    newline = "\n"
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
    base_text = "".join(
        [
            "# 13 — CHECKPOINT",
            newline,
            newline,
            "## STATUS",
            newline,
            governance.EXPECTED_WO024P_PREVIOUS_STATUS,
            newline,
            newline,
            "## VERSION",
            newline,
            "HIVE V0.1 — Foundation",
            newline,
            newline,
            "## COMPLETED",
            newline,
            "- historical entry preserved byte-for-byte.",
            newline,
            newline,
            "## GOVERNANCE",
            newline,
            "See `16-DECISIONS-LEDGER.md`.",
            newline,
            newline,
            "## IN PROGRESS",
            newline,
            "- Preparing the stabilization increment.",
            newline,
            newline,
            "## PENDING",
            newline,
        ]
    )
    base_text += "".join(f"- {item}{newline}" for item in governance.WO024P_COMPLETED_PENDING_ITEMS)
    base_text += "".join(
        [
            newline,
            "## BLOCKERS",
            newline,
            "None known before promotion.",
            newline,
            newline,
            "## NEXT STEP",
            newline,
            "Preparing the stabilization increment.",
            newline,
        ]
    )
    _preamble, _ordered, base_sections = governance._raw_checkpoint_structure(base_text, "base")
    controlled = {
        "STATUS": f"{governance.EXPECTED_WO024P_STATUS}{newline}{newline}",
        "COMPLETED": base_sections["COMPLETED"][:-1]
        + "".join(f"- {bullet}{newline}" for bullet in bullets)
        + newline,
        "IN PROGRESS": f"- {governance.EXPECTED_WO024P_IN_PROGRESS}{newline}{newline}",
        "BLOCKERS": f"{governance.EXPECTED_WO024P_BLOCKERS}{newline}{newline}",
        "NEXT STEP": f"{governance.EXPECTED_WO024P_NEXT_STEP}{newline}{newline}",
        "PENDING": newline,
    }
    candidate = base_text
    for name, body in controlled.items():
        _p, _o, sections = governance._raw_checkpoint_structure(candidate, "candidate")
        marker = f"## {name}{newline}"
        start = candidate.index(marker) + len(marker)
        candidate = candidate[:start] + body + candidate[start + len(sections[name]) :]
    return base_text, candidate


def with_checkpoint(text: str) -> Any:
    """Patch the closure sprint so only the checkpoint document is synthesized."""

    original = closure.document_text
    closure.document_text = lambda relative: (
        text if relative == CHECKPOINT_RELATIVE else original(relative)
    )
    return original


def assert_promotion_contract_holds_for_the_synthesized_pair() -> None:
    """The synthesized base and its promoted successor must satisfy the strict contract."""

    import scripts.review_evidence as governance

    base_text, promoted = synthesized_checkpoint_pair()
    governance.require_wo024p_checkpoint_semantics(
        base_text,
        promoted,
        wo024p_lineage_fixture(),
        wo024p_closure_fixture(),
    )


def assert_checkpoint_verifier_accepts_both_states() -> None:
    """`checkpoint_current` must accept the pre-promotion and the promoted checkpoint."""

    base_text, promoted = synthesized_checkpoint_pair()
    original = closure.document_text
    try:
        closure.document_text = lambda relative: (
            base_text if relative == CHECKPOINT_RELATIVE else original(relative)
        )
        assert closure.checkpoint_current()[0] == "PASS"
        assert closure.documentation_currentness_entry("checkpoint")["status"] == "PASS"
        closure.document_text = lambda relative: (
            promoted if relative == CHECKPOINT_RELATIVE else original(relative)
        )
        assert closure.checkpoint_current()[0] == "PASS"
        assert closure.documentation_currentness_entry("checkpoint")["status"] == "PASS"
    finally:
        closure.document_text = original


def malformed_checkpoint_matrix() -> dict[str, str]:
    """Malformed and stale variants, all derived from the synthesized pair."""

    import scripts.review_evidence as governance

    base_text, promoted = synthesized_checkpoint_pair()
    first_pending = governance.WO024P_COMPLETED_PENDING_ITEMS[0]
    without_one_pending = base_text.replace(f"- {first_pending}\n", "", 1)
    # A negative fixture must actually change the document: a no-op replacement would leave the
    # legitimate state in place and make the case vacuous.
    assert without_one_pending != base_text
    assert f"- {first_pending}\n" not in without_one_pending
    return {
        "promoted status with pending work": promoted.replace(
            "## PENDING\n\n", "## PENDING\n- leftover.\n\n"
        ),
        "unknown status": promoted.replace(governance.EXPECTED_WO024P_STATUS, "SOMETHING ELSE"),
        "missing canonical section": promoted.replace("## BLOCKERS\n", ""),
        "promoted status with stale next step": promoted.replace(
            governance.EXPECTED_WO024P_NEXT_STEP, "Preparing the stabilization increment."
        ),
        "active status without one pending item": without_one_pending,
        "active status without any pending items": base_text.replace(
            "".join(f"- {item}\n" for item in governance.WO024P_COMPLETED_PENDING_ITEMS),
            "",
            1,
        ),
        "empty checkpoint": "",
    }


def assert_malformed_matrix_fails_closed() -> None:
    """Every malformed or stale variant must stay FAIL/UNKNOWN and never become PASS."""

    for label, text in malformed_checkpoint_matrix().items():
        original = with_checkpoint(text)
        try:
            status = closure.checkpoint_current()[0]
            expected = {"UNKNOWN"} if text == "" else {"FAIL", "UNKNOWN"}
            assert status in expected, (label, status)
        finally:
            closure.document_text = original


def test_checkpoint_current_accepts_both_legitimate_states() -> None:
    assert_promotion_contract_holds_for_the_synthesized_pair()
    assert_checkpoint_verifier_accepts_both_states()
    # Whatever legitimate state the working tree is in must remain accepted.
    assert closure.checkpoint_current()[0] == "PASS"


def test_checkpoint_regressions_hold_with_a_promoted_working_tree() -> None:
    """The same regressions must hold when the tree already holds the promoted checkpoint."""

    _base_text, promoted = synthesized_checkpoint_pair()
    original = with_checkpoint(promoted)
    try:
        assert_promotion_contract_holds_for_the_synthesized_pair()
        assert_checkpoint_verifier_accepts_both_states()
        assert_malformed_matrix_fails_closed()
    finally:
        closure.document_text = original


def test_checkpoint_current_fails_closed_on_malformed_or_stale_states() -> None:
    assert_malformed_matrix_fails_closed()
    # An unknown status value must stay FAIL even when a pending item is present.
    original = with_checkpoint("## STATUS\nSOMETHING ELSE\n\n## PENDING\n- stabilization.\n\n")
    try:
        assert closure.checkpoint_current()[0] == "FAIL"
        assert closure.documentation_currentness_entry("checkpoint")["status"] == "FAIL"
    finally:
        closure.document_text = original


def checkpoint_with_controlled_sections(text: str, bodies: dict[str, str]) -> str:
    """Rewrite named section bodies in the raw grammar, leaving every other byte alone."""

    import scripts.review_evidence as governance

    preamble, ordered, _current = governance._raw_checkpoint_structure(text, "base")
    return preamble + "".join(
        section.heading + bodies.get(section.name, section.body) for section in ordered
    )


def post_1_0_checkpoint(base: str) -> str:
    """The exact post-WO-025-P release-train-authorized state derived from a closure checkpoint."""

    import scripts.review_evidence as governance

    newline = "\n"
    return checkpoint_with_controlled_sections(
        base,
        {
            "STATUS": f"{governance.EXPECTED_WO025P_STATUS}{newline}{newline}",
            "IN PROGRESS": f"- {governance.EXPECTED_WO025P_IN_PROGRESS}{newline}{newline}",
            "BLOCKERS": f"{governance.EXPECTED_WO025P_BLOCKERS}{newline}{newline}",
            "NEXT STEP": f"{governance.EXPECTED_WO025P_NEXT_STEP}{newline}{newline}",
            "PENDING": newline,
        },
    )


def legitimate_checkpoint_families() -> dict[str, str]:
    """The three checkpoint states Integration health has to recognize, and nothing else."""

    active_checkpoint, closure_checkpoint = synthesized_checkpoint_pair()
    return {
        "pre WO-024-P active closure": active_checkpoint,
        "final V0.1 closure": closure_checkpoint,
        "post WO-025-P release train authorized": post_1_0_checkpoint(closure_checkpoint),
    }


def post_1_0_checkpoint_mutations() -> dict[str, str]:
    """Narrower post-1.0 variants, including the status swap WO-025-G4 must keep rejecting."""

    import scripts.review_evidence as governance

    newline = "\n"
    closure_checkpoint = legitimate_checkpoint_families()["final V0.1 closure"]
    promoted = post_1_0_checkpoint(closure_checkpoint)
    stale_next_step = promoted.replace(
        governance.EXPECTED_WO025P_NEXT_STEP, governance.EXPECTED_WO024P_NEXT_STEP
    )
    stale_in_progress = promoted.replace(
        governance.EXPECTED_WO025P_IN_PROGRESS, governance.EXPECTED_WO024P_IN_PROGRESS
    )
    stale_blockers = promoted.replace(
        governance.EXPECTED_WO025P_BLOCKERS, governance.EXPECTED_WO024P_BLOCKERS
    )
    mutations = {
        "status swap only": checkpoint_with_controlled_sections(
            closure_checkpoint, {"STATUS": f"{governance.EXPECTED_WO025P_STATUS}{newline}{newline}"}
        ),
        "unknown status": promoted.replace(governance.EXPECTED_WO025P_STATUS, "SOMETHING ELSE"),
        "near-miss status": promoted.replace(
            governance.EXPECTED_WO025P_STATUS, f"{governance.EXPECTED_WO025P_STATUS} / partial"
        ),
        "stale NEXT STEP": stale_next_step,
        "stale IN PROGRESS": stale_in_progress,
        "stale BLOCKERS": stale_blockers,
        "undue pending": promoted.replace("## PENDING\n\n", "## PENDING\n- leftover.\n\n"),
        "missing canonical section": promoted.replace("## BLOCKERS\n", ""),
    }
    assert stale_next_step != promoted
    assert stale_in_progress != promoted
    assert stale_blockers != promoted
    return mutations


def working_tree_checkpoint_status() -> str:
    import scripts.review_evidence as governance

    sections = governance.checkpoint_sections(closure.document_text(CHECKPOINT_RELATIVE))
    return governance.normalized_checkpoint_value(sections, "STATUS")


def test_checkpoint_current_accepts_exactly_the_three_legitimate_families() -> None:
    """WO-025-G4: a valid WO-025-P promotion must never be rejected for being post-1.0."""

    original = closure.document_text
    try:
        for label, text in legitimate_checkpoint_families().items():
            closure.document_text = (
                lambda relative, value=text: value
                if relative == CHECKPOINT_RELATIVE
                else original(relative)
            )
            assert closure.checkpoint_current()[0] == "PASS", label
            assert closure.documentation_currentness_entry("checkpoint")["status"] == "PASS", label
    finally:
        closure.document_text = original
    # The working tree itself stays in a historical family: this increment does not promote.
    import scripts.review_evidence as governance

    status = working_tree_checkpoint_status()
    assert status in {
        governance.EXPECTED_WO024P_PREVIOUS_STATUS,
        governance.EXPECTED_WO024P_STATUS,
    }
    assert status != governance.EXPECTED_WO025P_STATUS


def test_checkpoint_current_fails_closed_on_narrower_post_1_0_states() -> None:
    """No mutation of the promoted state may read as a legitimate checkpoint."""

    original = closure.document_text
    try:
        for label, text in post_1_0_checkpoint_mutations().items():
            closure.document_text = (
                lambda relative, value=text: value
                if relative == CHECKPOINT_RELATIVE
                else original(relative)
            )
            assert closure.checkpoint_current()[0] == "FAIL", label
            assert closure.documentation_currentness_entry("checkpoint")["status"] == "FAIL", label
    finally:
        closure.document_text = original


def test_wo025p_promotion_contract_accepts_only_the_declared_successor() -> None:
    """The strict promotion grammar holds for the closure state and rejects every mutation."""

    import scripts.review_evidence as governance

    families = legitimate_checkpoint_families()
    closure_checkpoint = families["final V0.1 closure"]
    promoted = families["post WO-025-P release train authorized"]
    governance.require_wo025p_checkpoint_semantics(closure_checkpoint, promoted)
    mutations = post_1_0_checkpoint_mutations()
    rejected: list[str] = []
    for label, text in mutations.items():
        with pytest.raises(ValueError, match="WO-025-P"):
            governance.require_wo025p_checkpoint_semantics(closure_checkpoint, text)
        rejected.append(label)
    assert len(rejected) == len(mutations)
    # The active-closure checkpoint is not a valid promotion base.
    with pytest.raises(ValueError, match="promotion base is not the V0.1 closure"):
        governance.require_wo025p_checkpoint_semantics(
            families["pre WO-024-P active closure"], promoted
        )
    # Drift in an uncontrolled section is rejected even when every controlled section is correct.
    drifted = checkpoint_with_controlled_sections(
        promoted, {"COMPLETED": "- historical entry rewritten after closure.\n\n"}
    )
    assert drifted != promoted
    with pytest.raises(ValueError, match="changed unrelated checkpoint section: COMPLETED"):
        governance.require_wo025p_checkpoint_semantics(closure_checkpoint, drifted)


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


def test_closure_scope_applies_wo024_scope_only_to_the_work_orders_that_produced_it() -> None:
    """The closure suite runs as regression evidence for later work orders."""

    planning = [
        "docs/project-brain/17-POST-1.0-EVOLUTION-ROADMAP.md",
        "docs/project-brain/49-DECISION-FABRIC-1.1-PLANNING-FREEZE.md",
        "docs/project-brain/work-orders/WO-1.1-01-DECISION-CONTRACT-DETERMINISTIC-RESOLVER.md",
    ]
    assert closure.closure_scope_check(planning, "WO-025") == []
    assert closure.closure_scope_check(planning, "WO-025-G1") == []
    assert closure.closure_scope_check(planning, "WO-1.1-01") == []

    product = ["backend/app/retrieval.py"]
    assert closure.closure_scope_check(product, "WO-025") == []
    assert closure.closure_scope_check(product, "WO-024") == []
    assert closure.closure_scope_check(product, "WO-024-P") == []
    assert closure.closure_scope_check(product, None) == []


def test_closure_scope_keeps_the_historical_fail_closed_paths() -> None:
    """WO-024-family runs, unresolved runs and canonical paths keep failing closed."""

    import scripts.review_evidence as governance

    canonical = ["docs/project-brain/13-CHECKPOINT.md"]
    planning = ["docs/project-brain/17-POST-1.0-EVOLUTION-ROADMAP.md"]
    for work_order in (None, "WO-024", "WO-024-P"):
        assert closure.closure_scope_check(canonical, work_order) == canonical, work_order
        assert closure.closure_scope_check(planning, work_order) == planning, work_order
    assert frozenset({"WO-024", "WO-024-P"}) == governance.CLOSURE_STRICT_SCOPE_WORK_ORDERS
    assert governance.closure_sprint_scope(["backend/app/retrieval.py"]) == [], (
        "the WO-024 product scope itself is unchanged"
    )


def test_closure_scope_still_allows_the_promotion_pair() -> None:
    import scripts.review_evidence as governance

    pair = sorted(governance.WO024P_PROMOTION_ALLOWED_PATHS)
    assert closure.closure_scope_check(pair, "WO-024-P") == []
    assert closure.closure_scope_check(pair, "WO-024") == []
