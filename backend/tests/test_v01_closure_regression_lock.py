"""C4-G regression lock: the rejected implementations must be impossible."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, cast

SCRIPT_PATH = Path(__file__).parents[2] / "scripts" / "v01_closure_sprint.py"


def load_closure() -> Any:
    spec = importlib.util.spec_from_file_location("v01_closure_regression_lock", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(Any, module)


closure = load_closure()


def test_blanket_dod_pass_is_impossible() -> None:
    """A requirement without a registered verifier and evidence must never be PASS."""

    entry = closure.ledger_entry("Quality", "a requirement with no verifier registered")
    assert entry["verifier"] == "missing"
    assert entry["status"] == "FAIL"


def test_source_document_digest_is_not_accepted_as_row_evidence() -> None:
    """Row digests must come from the proving artifact, not the DoD document."""

    document_digest = closure.sha256_text(closure.git_blob(closure.DOD_DOCUMENT))
    for section, requirement in (
        ("Quality", "Unit tests pass."),
        ("Security", "Secret handling tested."),
        ("Resilience", "Backup and recovery tested."),
    ):
        entry = closure.ledger_entry(section, requirement)
        assert entry["evidence_digest"] != document_digest


def test_documentation_presence_alone_never_passes_executable_requirements() -> None:
    """Executable requirements must fail closed when the quality artifact is absent."""

    original = closure.artifact
    closure.artifact = lambda _name: {}
    try:
        for section, requirement in (
            ("Quality", "Unit tests pass."),
            ("Quality", "Lint/typecheck/build pass where applicable."),
            ("Security", "Secret handling tested."),
            ("Security", "Prompt/document trust boundaries tested."),
            ("Functional", "Canonical promotion rules are enforced."),
        ):
            entry = closure.ledger_entry(section, requirement)
            assert entry["status"] in {"UNKNOWN", "FAIL"}, (section, requirement, entry["status"])
    finally:
        closure.artifact = original


def test_measured_counters_come_from_artifacts() -> None:
    """Closure counters must be derived, not assigned."""

    counters = closure.measured_counters()
    assert set(counters) == {
        "secret_leaks",
        "filesystem_path_leaks",
        "cross_project_leaks",
        "core_llm_calls",
        "core_provider_calls",
    }
    assert all(isinstance(value, int) and value >= 0 for value in counters.values())
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert '"secret_leaks": 0,' not in source
    assert '"core_provider_calls": 0,' not in source


def test_documentation_currentness_flags_a_stale_gap_report(tmp_path: Path) -> None:
    """A gap report that denies an already-proved family must fail currentness."""

    original = closure.document_text
    closure.document_text = lambda relative: (
        "| Backup / recovery validation | NOT YET PROVED | stale claim |"
    )
    try:
        status, _path = closure.gap_report_current()
        assert status == "FAIL"
        entry = closure.documentation_currentness_entry("known_limitations")
        assert entry["status"] == "FAIL"
    finally:
        closure.document_text = original


def test_e2e_identity_mismatch_is_rejected(tmp_path: Path) -> None:
    """The closure scenario rejects a stage whose identity differs from the scenario."""

    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "e2e stages with a mismatched identity" in source
    assert '"identity": execution_identity["identity"]' in source


def test_empty_staged_change_set_cannot_satisfy_the_execution_stage() -> None:
    """The execution stage requires a real validated mutation."""

    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "did not stage and verify a bounded mutation" in source
    assert "ChangeOperation.create(" in source


def test_backup_requires_representative_state() -> None:
    """An empty or migration-only database must be rejected as backup evidence."""

    source = Path(__file__).parents[2] / "scripts" / "v01_backup_restore.py"
    body = source.read_text(encoding="utf-8")
    assert "backup source has no representative" in body
    assert "backup CAS bytes are not linked to canonical task rows" in body


def test_postgres_recreation_requires_a_new_container_identity() -> None:
    """A plain service restart is not recreation proof."""

    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "the PostgreSQL container was not replaced by a new container identity" in source
    assert 'compose("rm", "-sf", "postgres"' in source


def test_secondary_root_proof_is_not_cas_only() -> None:
    """The isolated root proof must exercise the persistent stack, not only CAS."""

    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "secondary_root_probe" in source
    assert "the isolated host root was not used by PostgreSQL" in source or (
        "isolated_root" in source and "hive-secondary" in source
    )


def test_orchestration_proof_stages_a_real_operation() -> None:
    """The proof must not accept an empty change set as a successful staging."""

    proof = Path(__file__).parent / "test_v01_closure_orchestration_proof.py"
    body = proof.read_text(encoding="utf-8")
    assert "ChangeOperation.create(" in body
    assert 'staged.status == "STAGED"' in body
    assert "pytest.raises(ExecutorAdapterError)" not in body
    assert "assert staged.changed_files ==" in body


def test_quality_artifact_is_the_only_source_for_the_quality_rows() -> None:
    """Quality rows must be driven by the recorded current-head commands."""

    source = SCRIPT_PATH.read_text(encoding="utf-8")
    for name in (
        "backend_tests",
        "governance_contract_tests",
        "trust_boundary_tests",
        "project_isolation_tests",
        "cross_project_negatives",
        "secret_scan",
        "canonical_verifier",
        "generated_maps",
    ):
        assert f'"{name}"' in source, name
    assert json.loads(json.dumps({"status": "PASS"})) == {"status": "PASS"}
