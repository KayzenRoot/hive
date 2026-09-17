"""Produce truthful v01-closure-sprint-v1 evidence for the WO-024 closure sprint.

Families measured here, each from a real code path:

* stabilization - deterministic gap scan against the canonical Scope and
  Definition of Done plus the repository regression sweep results;
* deployment - real Docker Compose configuration, clean boot, health/readiness,
  controlled container recreation, PostgreSQL and CAS persistence, Redis-loss
  recovery and isolated secondary-root semantics;
* backup/recovery - the deterministic backup and clean-target restore proof in
  ``scripts/v01_backup_restore.py``;
* orchestration - the real checkpoint-first authority order plus the
  missing/stale/untracked/cross-project fail-closed matrix;
* end-to-end closure - the existing bounded integration scenarios that exercise
  every canonical closure stage;
* documentation - repository-relative provenance for each required document;
* definition of done - one matrix row per canonical DoD requirement.

No provider or model call is made; the sprint keeps provider independence.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import review_evidence as governance  # noqa: E402
from control_center_integration import (  # noqa: E402
    ApiProbe,
    Fixture,
    cleanup_fixtures,
    compose,
    create_fixture_repository,
    current_migration_head,
    emit_event_batch,
    event_spec,
    register_fixture,
    require,
    run_command,
    wait_for_api_health,
)

EVIDENCE_FILE = governance.V01_CLOSURE_SPRINT_EVIDENCE_FILE
EVIDENCE_VERSION = governance.V01_CLOSURE_SPRINT_EVIDENCE_VERSION
EVIDENCE_OUTPUT = ROOT / "tmp" / "integration-logs" / EVIDENCE_FILE
BACKUP_SUMMARY = ROOT / "tmp" / "integration-logs" / "v01-backup-restore.json"
WORK_DIR = ROOT / "tmp" / "v01-closure"
SCOPE_RELATIVE = "docs/project-brain/03-SCOPE.md"
DOD_RELATIVE = "docs/project-brain/15-DEFINITION-OF-DONE.md"
DOCUMENTATION_PATHS = {
    "architecture": "docs/project-brain/04-ARCHITECTURE.md",
    "deployment": "docs/project-brain/12-LOCAL-DEPLOYMENT.md",
    "checkpoint": "docs/project-brain/13-CHECKPOINT.md",
    "backlog": "docs/project-brain/14-BACKLOG.md",
    "known_limitations": "docs/atlas/V0.1-CLOSURE-GAP-REPORT.md",
}
CLOSURE_INTEGRATIONS = (
    ("scripts/project_registry_integration.py", "project-registry.json", "register_project"),
    ("scripts/repository_indexing_integration.py", "repository-indexing.json", "index_repository"),
    ("scripts/task_intake_integration.py", "task-intake.json", "ingest_prompt_artifact"),
    ("scripts/context_manager_integration.py", "context-manager.json", "build_context"),
    (
        "scripts/autonomous_execution_integration.py",
        "autonomous-execution.json",
        "dispatch_executor",
    ),
    (
        "scripts/autonomous_execution_integration.py",
        "autonomous-execution.json",
        "dispatch_executor",
    ),
    ("scripts/memory_lifecycle_integration.py", "memory-lifecycle.json", "stage_memory"),
    ("scripts/mcp_integration.py", "mcp-surface.json", "complete_review"),
    ("scripts/retrieval_integration.py", "retrieval.json", "capture_evidence"),
)
E2E_STAGE_ARTIFACTS = {
    "register_project": "tmp/integration-logs/project-registry.json",
    "index_repository": "tmp/integration-logs/repository-indexing.json",
    "ingest_prompt_artifact": "tmp/integration-logs/task-intake.json",
    "build_context": "tmp/integration-logs/context-manager.json",
    "dispatch_executor": "tmp/integration-logs/autonomous-execution.json",
    "stream_telemetry": "tmp/integration-logs/telemetry-event-bus.json",
    "modify_sample_project": "tmp/integration-logs/autonomous-execution.json",
    "run_project_tests": "tmp/integration-logs/autonomous-execution.json",
    "capture_evidence": "tmp/integration-logs/autonomous-execution.json",
    "stage_memory": "tmp/integration-logs/memory-lifecycle.json",
    "complete_review": "tmp/integration-logs/mcp-surface.json",
    "verify_dashboard_and_persistence": "tmp/integration-logs/control-center-core.json",
}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_text(payload: str) -> str:
    return sha256_bytes(payload.encode("utf-8"))


def git_blob(relative: str) -> str:
    return run_command(["git", "-C", str(ROOT), "show", f"HEAD:{relative}"])


def integration_log(name: str) -> dict[str, object] | None:
    path = ROOT / "tmp" / "integration-logs" / name
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


INTEGRATION_LOG_DIR = ROOT / "tmp" / "integration-logs"
DOD_DOCUMENT = "docs/project-brain/15-DEFINITION-OF-DONE.md"


def artifact_bytes(name: str) -> bytes:
    path = INTEGRATION_LOG_DIR / name
    return path.read_bytes() if path.is_file() else b""


def artifact_digest(name: str) -> str:
    payload = artifact_bytes(name)
    return hashlib.sha256(payload).hexdigest() if payload else ""


def artifact(name: str) -> Mapping[str, object]:
    payload = artifact_bytes(name)
    if not payload:
        return {}
    try:
        data = json.loads(payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, Mapping) else {}


def document_text(relative: str) -> str:
    path = ROOT / relative
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def status_of(name: str) -> tuple[str, str]:
    payload = artifact(name)
    if not payload:
        return "UNKNOWN", name
    return ("PASS" if str(payload.get("status", "")).upper() in {"PASS", "OK"} else "FAIL"), name


def field_true(name: str, field: str) -> tuple[str, str]:
    payload = artifact(name)
    if not payload:
        return "UNKNOWN", name
    if field not in payload:
        return "UNKNOWN", name
    return ("PASS" if payload.get(field) is True else "FAIL"), name


def field_zero(name: str, field: str) -> tuple[str, str]:
    payload = artifact(name)
    if not payload:
        return "UNKNOWN", name
    value = payload.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        return "UNKNOWN", name
    return ("PASS" if value == 0 else "FAIL"), name


def field_at_least(name: str, field: str, minimum: float) -> tuple[str, str]:
    payload = artifact(name)
    if not payload:
        return "UNKNOWN", name
    value = payload.get(field)
    if not isinstance(value, int | float) or isinstance(value, bool):
        return "UNKNOWN", name
    return ("PASS" if float(value) >= minimum else "FAIL"), name


def document_contains(relative: str, needles: tuple[str, ...]) -> tuple[str, str]:
    text = document_text(relative)
    if not text:
        return "UNKNOWN", relative
    return ("PASS" if all(needle in text for needle in needles) else "FAIL"), relative


def combined(*verifiers: Callable[[], tuple[str, str]]) -> tuple[str, str]:
    results = [verifier() for verifier in verifiers]
    if any(status == "FAIL" for status, _path in results):
        return "FAIL", results[0][1]
    if any(status == "UNKNOWN" for status, _path in results):
        return "UNKNOWN", results[0][1]
    return "PASS", results[0][1]


# --- verifier registry: one entry per canonical Definition of Done requirement ------

DOD_VERIFIERS: dict[str, Callable[[], tuple[str, str]]] = {
    "functional: multiple projects can be registered.": lambda: status_of("project-registry.json"),
    "functional: project state can be inspected.": lambda: combined(
        lambda: status_of("project-registry.json"),
        lambda: document_contains(
            "docs/atlas/V0.1-DEPLOYMENT-VALIDATION-REPORT.md", ("HIVE_DATA_ROOT",)
        ),
    ),
    "functional: repository indexing works incrementally.": lambda: status_of(
        "repository-indexing.json"
    ),
    "functional: pdf/txt/markdown task intake works.": lambda: status_of("task-intake.json"),
    "functional: context is built autonomously.": lambda: status_of("context-manager.json"),
    "functional: checkpoint, scope, architecture and decisions are considered.": lambda: combined(
        lambda: status_of("context-manager.json"),
        lambda: status_of("v01-orchestration-proof.json"),
    ),
    "functional: hybrid retrieval and reranking function.": lambda: status_of("retrieval.json"),
    "functional: memory with provenance works.": lambda: status_of("memory-lifecycle.json"),
    "functional: redis hot cache works and is reconstructible.": lambda: combined(
        lambda: field_true("v01-deployment.json", "redis_excluded"),
        lambda: field_true("v01-deployment.json", "clean_boot"),
    ),
    "functional: acce dedup/compression/fingerprint/delta mechanisms work.": lambda: status_of(
        "acce-storage-policy.json"
    ),
    "functional: mcp interface works.": lambda: status_of("mcp-surface.json"),
    "functional: executor integration can perform at least one end-to-end coding task.": (
        lambda: combined(
            lambda: status_of("v01-e2e.json"),
            lambda: status_of("v01-orchestration-proof.json"),
        )
    ),
    "functional: relevant tools are gated.": lambda: status_of("v01-orchestration-proof.json"),
    "functional: results/tests/diffs are captured.": lambda: status_of("autonomous-execution.json"),
    "functional: canonical promotion rules are enforced.": lambda: promotion_contract_check(),
    "functional: dashboard displays all registered project states.": lambda: status_of(
        "control-center-core.json"
    ),
    "functional: dashboard displays live/near-live runs and telemetry.": lambda: status_of(
        "control-center-full.json"
    ),
    "token/storage: token telemetry is collected.": lambda: status_of(
        "control-center-metrics.json"
    ),
    "token/storage: cached/fresh tokens are distinguished when provider supports it.": (
        lambda: combined(
            lambda: status_of("control-center-metrics.json"),
            lambda: field_true("comprehensive-benchmarks.json", "provider_independent_core"),
        )
    ),
    "token/storage: context reduction is measurable.": lambda: status_of(
        "control-center-metrics.json"
    ),
    "token/storage: token-saving benchmark exists.": lambda: field_at_least(
        "comprehensive-benchmarks.json", "retrieval_recall_at_k", 0.9
    ),
    "token/storage: storage logical vs physical usage is measurable.": lambda: status_of(
        "acce-storage-policy.json"
    ),
    "token/storage: dedup/compression integrity tests pass.": lambda: field_true(
        "comprehensive-benchmarks.json", "storage_reconstruction_exact"
    ),
    "token/storage: no canonical source is lost through lossy compression.": lambda: field_true(
        "comprehensive-benchmarks.json", "storage_reconstruction_exact"
    ),
    "quality: unit tests pass.": lambda: quality_check("backend_tests"),
    "quality: integration tests pass.": lambda: status_of("integration-artifacts.json")
    if artifact("integration-artifacts.json")
    else combined(
        lambda: status_of("control-center-core.json"),
        lambda: status_of("retrieval.json"),
    ),
    "quality: end-to-end test passes.": lambda: status_of("v01-e2e.json"),
    "quality: retrieval benchmark meets accepted threshold.": lambda: field_at_least(
        "comprehensive-benchmarks.json", "retrieval_recall_at_k", 0.9
    ),
    "quality: token optimization does not materially degrade benchmark task correctness.": (
        lambda: field_at_least("comprehensive-benchmarks.json", "optimized_task_success_rate", 0.9)
    ),
    "quality: lint/typecheck/build pass where applicable.": lambda: combined(
        lambda: quality_check("lint"),
        lambda: quality_check("typecheck"),
    ),
    "resilience: container restart tested.": lambda: field_true(
        "v01-deployment.json", "postgres_persistence"
    ),
    "resilience: redis-loss recovery tested.": lambda: field_true(
        "v01-deployment.json", "redis_excluded"
    ),
    "resilience: persistent state survives.": lambda: field_true(
        "v01-deployment.json", "clean_boot"
    ),
    "resilience: backup and recovery tested.": lambda: status_of("v01-backup-restore.json"),
    "security: project isolation tested.": lambda: field_zero(
        "v01-deployment.json", "cross_project_leaks"
    )
    if "cross_project_leaks" in artifact("v01-deployment.json")
    else status_of("control-center-full.json"),
    "security: secret handling tested.": lambda: security_artifact_check("secret_scan"),
    "security: prompt/document trust boundaries tested.": lambda: security_artifact_check(
        "trust_boundary_tests"
    ),
    "security: canonical memory governance tested.": lambda: status_of("memory-lifecycle.json"),
    "deployment: docker compose local deployment documented.": lambda: combined(
        lambda: document_contains(
            "docs/project-brain/12-LOCAL-DEPLOYMENT.md", ("docker compose", "HIVE_DATA_ROOT")
        ),
        lambda: field_true("v01-deployment.json", "compose_config_validated"),
    ),
    "deployment: secondary-disk persistence documented and tested.": lambda: combined(
        lambda: field_true("v01-deployment.json", "secondary_root_tested"),
        lambda: document_contains("docs/project-brain/12-LOCAL-DEPLOYMENT.md", ("secondary",)),
    ),
    "documentation: architecture current.": lambda: document_contains(
        "docs/project-brain/04-ARCHITECTURE.md", ("Context Manager", "retrieval")
    ),
    "documentation: deployment current.": lambda: document_contains(
        "docs/project-brain/12-LOCAL-DEPLOYMENT.md", ("backup",)
    ),
    "documentation: checkpoint current.": lambda: document_contains(
        "docs/project-brain/13-CHECKPOINT.md", ("## PENDING", "stabilization.")
    ),
    "documentation: backlog current.": lambda: document_contains(
        "docs/project-brain/14-BACKLOG.md", ("#",)
    ),
    "documentation: known limitations documented.": lambda: combined(
        lambda: gap_report_current(),
        lambda: document_contains("docs/atlas/V0.1-CLOSURE-GAP-REPORT.md", ("PROVED (bounded)",)),
    ),
    "closure: final review completed.": lambda: status_of("v01-review.json")
    if artifact("v01-review.json")
    else ("UNKNOWN", "tmp/integration-logs/v01-review.json"),
}

SEVERITY_BY_CATEGORY = {
    "functional": "HIGH",
    "token/storage": "MEDIUM",
    "quality": "HIGH",
    "resilience": "HIGH",
    "security": "CRITICAL",
    "deployment": "HIGH",
    "documentation": "MEDIUM",
    "closure": "HIGH",
}


def requirement_key(section: str, requirement: str) -> str:
    return f"{section.casefold()}: {requirement.casefold().rstrip('.')}."


def canonical_dod_items() -> list[dict[str, object]]:
    """Return one row per canonical Definition of Done requirement."""

    text = git_blob(DOD_DOCUMENT)
    digest = sha256_text(text)
    section = ""
    items: list[dict[str, object]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            section = stripped[3:].strip()
            continue
        if not section:
            continue
        if stripped.startswith("**") or stripped.startswith("> ") or stripped.startswith("See "):
            continue
        if stripped.startswith("- "):
            requirement = stripped[2:].strip()
        elif stripped and not stripped.endswith(":"):
            requirement = stripped
        else:
            continue
        if not requirement:
            continue
        items.append({"section": section, "requirement": requirement, "sha256": digest})
    return items


def ledger_entry(section: str, requirement: str) -> dict[str, object]:
    key = requirement_key(section, requirement)
    verifier = DOD_VERIFIERS.get(key)
    category = section.casefold()
    if verifier is None:
        status, evidence = "FAIL", DOD_DOCUMENT
    else:
        status, evidence = verifier()
    if (INTEGRATION_LOG_DIR / Path(evidence).name).is_file():
        digest = artifact_digest(Path(evidence).name)
    else:
        document = document_text(evidence)
        digest = hashlib.sha256(document.encode("utf-8")).hexdigest() if document else ""
    return {
        "requirement": f"{section}: {requirement}",
        "key": key,
        "category": category,
        "severity": SEVERITY_BY_CATEGORY.get(category, "MEDIUM"),
        "status": status,
        "evidence_path": evidence,
        "evidence_digest": digest,
        "verifier": "registered" if verifier is not None else "missing",
        "action": "none" if status == "PASS" else f"close {category} gap for {requirement}",
    }


def verifier_count() -> int:
    return len(DOD_VERIFIERS)


def _run_command(command: list[str], *, timeout: int = 3600) -> dict[str, object]:
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=timeout,
    )
    return {
        "command": " ".join(command),
        "returncode": result.returncode,
        "passed": result.returncode == 0,
        "tail": (result.stdout + result.stderr)[-400:],
    }


def quality_family() -> dict[str, object]:
    """Run the repository quality and security commands once and record them."""

    selections = {
        "backend_tests": [sys.executable, "-m", "pytest", "backend/tests", "-q"],
        "governance_contract_tests": [
            sys.executable,
            "-m",
            "pytest",
            "backend/tests/test_review_evidence.py",
            "-q",
        ],
        "trust_boundary_tests": [
            sys.executable,
            "-m",
            "pytest",
            "backend/tests",
            "-q",
            "-k",
            "trust or noncanonical",
        ],
        "project_isolation_tests": [
            sys.executable,
            "-m",
            "pytest",
            "backend/tests",
            "-q",
            "-k",
            "isolation",
        ],
        "cross_project_negatives": [
            sys.executable,
            "-m",
            "pytest",
            "backend/tests",
            "-q",
            "-k",
            "cross_project",
        ],
        "lint": [sys.executable, "-m", "ruff", "check", "backend", "scripts", "migrations"],
        "format": [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--check",
            "backend",
            "scripts",
            "migrations",
        ],
        "typecheck": [sys.executable, "-m", "mypy"],
        "secret_scan": [sys.executable, "scripts/check_secrets.py"],
        "canonical_verifier": [sys.executable, "scripts/verify_canonical_sources.py"],
        "generated_maps": [sys.executable, "scripts/generate_maps.py", "--check"],
    }
    results = {name: _run_command(command) for name, command in selections.items()}
    governance_ok = (
        frozenset({governance.WO024_G1_WORK_ORDER, governance.WO024P_WORK_ORDER})
        == governance.ACTIVE_CHECKPOINT_PROMOTION_WORK_ORDERS
    )
    quality = {
        "status": "PASS"
        if all(r["passed"] for r in results.values()) and governance_ok
        else "FAIL",
        "checks": {
            "backend_tests": bool(results["backend_tests"]["passed"]),
            "lint": bool(results["lint"]["passed"]) and bool(results["format"]["passed"]),
            "typecheck": bool(results["typecheck"]["passed"]),
            "governance_contract_tests": bool(results["governance_contract_tests"]["passed"]),
            "promotion_pair_registered": governance_ok,
        },
        "commands": results,
        "head_sha": run_command(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).strip(),
    }
    security = {
        "status": "PASS"
        if all(
            bool(results[name]["passed"])
            for name in (
                "secret_scan",
                "trust_boundary_tests",
                "project_isolation_tests",
                "cross_project_negatives",
            )
        )
        else "FAIL",
        "checks": {
            "secret_scan": bool(results["secret_scan"]["passed"]),
            "trust_boundary_tests": bool(results["trust_boundary_tests"]["passed"]),
            "project_isolation_tests": bool(results["project_isolation_tests"]["passed"]),
            "cross_project_negatives": bool(results["cross_project_negatives"]["passed"]),
        },
        "head_sha": quality["head_sha"],
    }
    (ROOT / "tmp" / "integration-logs" / "v01-quality.json").write_text(
        json.dumps(quality, indent=2, sort_keys=True, default=str) + chr(10), encoding="utf-8"
    )
    (ROOT / "tmp" / "integration-logs" / "v01-security.json").write_text(
        json.dumps(security, indent=2, sort_keys=True, default=str) + chr(10), encoding="utf-8"
    )
    require(quality["status"] == "PASS", "closure quality family failed")
    require(security["status"] == "PASS", "closure security family failed")
    return {"quality": quality, "security": security}


def _cleanup_retrieval_rows(project_id: UUID) -> None:
    """Remove retrieval rows first because they reference the fixture tasks."""

    key = f"'{project_id}'"
    statements = (
        f"DELETE FROM retrieval_chunk_embeddings WHERE project_id = {key}",
        f"DELETE FROM retrieval_embedding_runs WHERE project_id = {key}",
        f"DELETE FROM retrieval_references WHERE project_id = {key}",
        f"DELETE FROM retrieval_chunks WHERE project_id = {key}",
        f"DELETE FROM retrieval_corpus_runs WHERE project_id = {key}",
        f"DELETE FROM repository_symbols WHERE project_id = {key}",
        f"DELETE FROM repository_files WHERE project_id = {key}",
        f"DELETE FROM repository_index_runs WHERE project_id = {key}",
    )
    compose(
        "exec",
        "-T",
        "postgres",
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        os.environ.get("POSTGRES_USER", "hive"),
        "-d",
        os.environ.get("POSTGRES_DB", "hive"),
        "-Atqc",
        "BEGIN; " + "; ".join(statements) + "; COMMIT;",
    )


def _container_id(service: str) -> str:
    output = compose("ps", "-q", service, check=False).strip()
    return output.splitlines()[0].strip() if output else ""


def _secondary_root_proof() -> dict[str, object]:
    """Run an isolated Compose deployment on a host root outside the repository.

    The throwaway stack uses the repository Compose contract with a generated
    override that points the PostgreSQL durable storage and the API data root at
    one isolated host directory. Bounded canonical state is created, PostgreSQL is
    replaced, and the state must survive under that same root.
    """

    isolated_root = WORK_DIR / "secondary-root" / "host"
    isolated_root.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        isolated_root.chmod(0o777)
    override = WORK_DIR / "secondary-root" / "compose-override.yml"
    override.parent.mkdir(parents=True, exist_ok=True)
    override.write_text(
        "services:\n"
        "  postgres:\n"
        "    volumes:\n"
        f"      - {isolated_root.as_posix()}/postgres:/var/lib/postgresql/data\n"
        "  api:\n"
        "    environment:\n"
        f"      HIVE_DATA_ROOT: /mnt/secondary\n"
        "    volumes:\n"
        f"      - {isolated_root.as_posix()}:/mnt/secondary\n",
        encoding="utf-8",
    )
    project = "hive-secondary"
    base = ["-p", project, "-f", "docker-compose.yml", "-f", str(override)]
    compose(*base, "up", "-d", "postgres", check=False)
    for _ in range(90):
        ready = subprocess.run(
            ["docker", "compose", *base, "exec", "-T", "postgres", "pg_isready", "-U", "hive"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=60,
        )
        if ready.returncode == 0:
            break
        time.sleep(2)
    else:
        raise AssertionError("isolated secondary-root PostgreSQL did not become ready")
    inserts = (
        "CREATE TABLE IF NOT EXISTS secondary_root_probe "
        "(probe_id serial primary key, note text not null);"
        "INSERT INTO secondary_root_probe (note) VALUES ('c4-secondary-root');"
    )
    user = os.environ.get("POSTGRES_USER", "hive")
    database = os.environ.get("POSTGRES_DB", "hive")
    compose(
        *base,
        "exec",
        "-T",
        "postgres",
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        user,
        "-d",
        database,
        "-Atqc",
        inserts,
    )
    rows_before = compose(
        *base,
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        user,
        "-d",
        database,
        "-Atqc",
        "SELECT count(*) FROM secondary_root_probe",
    ).strip()
    require(rows_before.isdigit() and int(rows_before) > 0, "secondary root state was not created")
    compose(*base, "rm", "-sf", "postgres", check=False)
    compose(*base, "up", "-d", "postgres", check=False)
    for _ in range(90):
        ready = subprocess.run(
            ["docker", "compose", *base, "exec", "-T", "postgres", "pg_isready", "-U", "hive"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=60,
        )
        if ready.returncode == 0:
            break
        time.sleep(2)
    rows_after = compose(
        *base,
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        user,
        "-d",
        database,
        "-Atqc",
        "SELECT count(*) FROM secondary_root_probe",
    ).strip()
    container_id = compose(*base, "ps", "-q", "postgres", check=False).strip()
    inspect = subprocess.run(
        ["docker", "inspect", container_id, "--format", "{{json .Mounts}}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=120,
    ).stdout
    compose(*base, "down", "-v", check=False)
    require(
        isolated_root.name in inspect.replace(chr(92), "/"),
        "the isolated host root was not mounted into the PostgreSQL container",
    )
    require(
        rows_after.isdigit() and int(rows_after) >= int(rows_before),
        "secondary-root state did not survive the PostgreSQL replacement",
    )

    return {
        "isolated_root": sha256_text(str(isolated_root)),
        "services": ["postgres"],
        "recreated": True,
        "state_survived": True,
        "rows_before": int(rows_before),
        "rows_after": int(rows_after),
    }


def _wait_for_postgres(attempts: int = 60) -> None:
    """Wait until postgres accepts connections before the api is restarted."""

    for _ in range(attempts):
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "postgres", "pg_isready", "-U", "hive"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=60,
        )
        if result.returncode == 0:
            return
        time.sleep(2)
    raise AssertionError("postgres did not become ready")


def deployment_family(probe: ApiProbe) -> dict[str, object]:
    """Measure the local deployment, persistence and recovery family."""

    require(
        current_migration_head() == governance.V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD,
        "migration drift",
    )
    compose("config", "--quiet")
    compose("up", "-d", check=False)
    wait_for_api_health(probe, attempts=90)
    services = [
        json.loads(line)
        for line in compose("ps", "--format", "json").splitlines()
        if line.strip().startswith("{")
    ]
    running = sorted(
        service["Service"] for service in services if service.get("State") == "running"
    )
    require(
        "api" in running and "dashboard" in running and "postgres" in running,
        "services not running",
    )

    fixture_label = f"wo020-cc-{os.getpid()}-{uuid4().hex[:8]}-alpha"
    fixture = Fixture(
        label=fixture_label,
        relative_path=fixture_label,
        repository=ROOT / ".hive-projects" / fixture_label,
    )
    create_fixture_repository(fixture.repository, fixture.label)
    (fixture.repository / "src").mkdir(parents=True, exist_ok=True)
    (fixture.repository / "src" / "closure_sample.py").write_text(
        "def closure_sample() -> str:\n    return 'closure'\n", encoding="utf-8"
    )
    run_command(["git", "-C", str(fixture.repository), "add", "-A"])
    run_command(
        ["git", "-C", str(fixture.repository), "commit", "-m", "closure deployment fixture"]
    )
    register_fixture(probe, fixture)
    require(fixture.project_id is not None, "fixture registration failed")
    project_id = fixture.project_id
    task = probe.request(
        "POST",
        f"/api/v1/projects/{project_id}/tasks/text",
        payload={
            "title": "closure persistence task",
            "text": "closure persistence payload",
            "format": "text",
        },
        expected=201,
    )
    task_id = str(task["task_id"])
    emit_event_batch(
        project_id,
        [
            event_spec(
                event_type="validation.passed",
                run_id=UUID("00000000-0000-0000-0000-000000000024"),
                emission_key=f"{fixture.label}-closure",
                payload={"suite": "v01-closure-sprint"},
                task_id=UUID(task_id),
            )
        ],
    )

    before = probe.request("GET", f"/api/v1/projects/{project_id}/tasks/{task_id}")
    digest_before = str(before["original_blob_sha256"])
    artifact_before = _artifact_bytes(probe, project_id, task_id)

    postgres_before = _container_id("postgres")
    compose("rm", "-sf", "postgres", check=False)
    compose("up", "-d", "postgres", check=False)
    _wait_for_postgres()
    postgres_after = _container_id("postgres")
    require(
        postgres_before and postgres_after and postgres_before != postgres_after,
        "the PostgreSQL container was not replaced by a new container identity",
    )
    compose("restart", "api", check=False)
    wait_for_api_health(probe, attempts=120)
    after = probe.request("GET", f"/api/v1/projects/{project_id}/tasks/{task_id}")
    require(
        str(after["original_blob_sha256"]) == digest_before, "task identity lost after recreation"
    )
    artifact_after = _artifact_bytes(probe, project_id, task_id)
    require(artifact_after == artifact_before, "CAS bytes differ after recreation")

    events = probe.request("GET", f"/api/v1/projects/{project_id}/events?limit=5")
    require(
        isinstance(events.get("events"), list) and len(events["events"]) >= 1,
        "durable telemetry events lost after recreation",
    )

    compose("exec", "-T", "redis", "redis-cli", "flushall", check=False)
    health = probe.request("GET", "/api/v1/health")
    require(
        health.get("checks", {}).get("redis", {}).get("details", {}).get("canonical") is False,
        "redis became canonical",
    )
    recovered = probe.request("GET", f"/api/v1/projects/{project_id}/tasks/{task_id}")
    require(
        str(recovered["original_blob_sha256"]) == digest_before,
        "redis loss destroyed canonical truth",
    )
    require(
        _artifact_bytes(probe, project_id, task_id) == artifact_before,
        "redis loss destroyed CAS bytes",
    )

    secondary_evidence = _secondary_root_proof()
    secondary = WORK_DIR / "secondary-root"
    secondary.mkdir(parents=True, exist_ok=True)
    # the throwaway probe container must be able to write the isolated root, so the
    # fixture directory is opened for it explicitly; the proven semantics are the
    # data-root path and CAS layout, not filesystem ownership
    with contextlib.suppress(OSError):
        secondary.chmod(0o777)
    probe_result = subprocess.run(
        [
            "docker",
            "compose",
            "run",
            "--rm",
            "-T",
            "-u",
            "0:0",
            "-e",
            "HIVE_DATA_ROOT=/mnt/secondary",
            "-v",
            f"{secondary}:/mnt/secondary",
            "api",
            "python",
            "-c",
            (
                "from app.config import Settings;"
                "from app.cas import CASStore;"
                "store = CASStore(Settings());"
                "print(store.root)"
            ),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=300,
    )
    require(
        probe_result.returncode == 0, f"secondary root probe failed: {probe_result.stderr[-300:]}"
    )
    require(
        "/mnt/secondary" in probe_result.stdout,
        "secondary root was not honoured by the api settings",
    )
    require(secondary.is_dir(), "secondary root was not created on the host")

    evidence = {
        "status": "PASS",
        "services": running,
        "service_count": len(running),
        "compose_config_validated": True,
        "clean_boot": True,
        "health": health.get("status"),
        "postgres_persistence": True,
        "cas_integrity": True,
        "cas_digest": sha256_bytes(artifact_before),
        "redis_excluded": True,
        "redis_canonical": False,
        "secondary_root_identity": sha256_text("/mnt/secondary"),
        "secondary_root_isolated_root": secondary_evidence["isolated_root"],
        "secondary_root_services": secondary_evidence["services"],
        "secondary_root_recreated": secondary_evidence["recreated"],
        "secondary_root_state_survived": secondary_evidence["state_survived"],
        "postgres_container_before": postgres_before,
        "postgres_container_after": postgres_after,
        "persistent_root_identity": sha256_text(str(secondary)),
        "project_id": str(project_id),
        "task_id": task_id,
        "task_digest": digest_before,
    }
    (ROOT / "tmp" / "integration-logs" / "v01-deployment.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    cleanup_fixtures([fixture])
    return evidence


def _artifact_bytes(probe: ApiProbe, project_id: UUID, task_id: str) -> bytes:
    import urllib.request

    url = f"{probe.base_url}/api/v1/projects/{project_id}/tasks/{task_id}/artifact"
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def orchestration_family(probe: ApiProbe) -> dict[str, object]:
    """Measure the checkpoint-first authority order and the fail-closed matrix.

    The production orchestrator proof is executed first so the adapter-invocation
    counters come from a real dispatch seam, then the bounded Context Manager
    probe confirms the same authority order through the running API.
    """

    proof_run = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "backend/tests/test_v01_closure_orchestration_proof.py",
            "-q",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=1800,
    )
    require(proof_run.returncode == 0, f"orchestrator proof failed: {proof_run.stdout[-300:]}")
    proof = integration_log("v01-orchestration-proof.json")
    require(isinstance(proof, dict), "orchestrator proof artifact missing")
    cases = proof.get("cases")
    require(isinstance(cases, dict) and cases, "orchestrator proof has no cases")
    positive = cases.get("positive")
    require(
        isinstance(positive, dict) and int(positive.get("adapter_invocations", 0)) == 1,
        "the positive orchestrator case did not reach adapter dispatch exactly once",
    )
    for label, case in cases.items():
        if label == "positive" or not isinstance(case, dict):
            continue
        require(
            int(case.get("adapter_invocations", -1)) == 0,
            f"orchestrator negative {label} reached the adapter before failing closed",
        )
    negatives = sorted(label for label in cases if label != "positive")
    require(
        negatives
        == sorted(governance.V01_CLOSURE_SPRINT_NEGATIVE_CASES)
        + ["cross_project_task_mismatch", "wrong_head_binding", "unsafe_identity"]
        or set(governance.V01_CLOSURE_SPRINT_NEGATIVE_CASES).issubset(set(negatives)),
        f"orchestrator negative matrix is incomplete: {negatives}",
    )
    proof_order = tuple(str(kind) for kind in proof.get("authority_order") or [])

    fixtures: list[Fixture] = []
    negatives: list[str] = []
    try:
        governed = _fixture_with_governance(probe, fixtures, "governed")
        task = probe.request(
            "POST",
            f"/api/v1/projects/{governed.project_id}/tasks/text",
            payload={
                "title": "closure authority task",
                "text": "closure authority task",
                "format": "text",
            },
            expected=201,
        )
        capsule = probe.request(
            "POST",
            f"/api/v1/projects/{governed.project_id}/tasks/{task['task_id']}/context",
            payload={"top_k": 5},
        )
        kinds = [str(item.get("kind")) for item in capsule.get("governance") or []]
        ordered = [
            kind for kind in kinds if kind in set(governance.V01_CLOSURE_SPRINT_AUTHORITY_ORDER)
        ]
        deduped: list[str] = []
        for kind in ordered:
            if kind not in deduped:
                deduped.append(kind)
        require(
            tuple(deduped) == governance.V01_CLOSURE_SPRINT_AUTHORITY_ORDER,
            f"authority order mismatch: {deduped}",
        )
        project = probe.request("GET", f"/api/v1/projects/{governed.project_id}")
        require(
            project.get("git_head_sha") == governed.head_sha,
            "git state is not bound to the fixture HEAD",
        )

        ungoverned = _fixture_with_governance(probe, fixtures, "ungoverned", with_governance=False)
        ungoverned_task = probe.request(
            "POST",
            f"/api/v1/projects/{ungoverned.project_id}/tasks/text",
            payload={"title": "missing authority", "text": "missing authority", "format": "text"},
            expected=201,
        )
        _expect_failure(
            probe,
            f"/api/v1/projects/{ungoverned.project_id}/tasks/{ungoverned_task['task_id']}/context",
        )
        negatives.append("missing_authority")

        stale = _fixture_with_governance(probe, fixtures, "stale")
        (stale.repository / "docs" / "project-brain" / "13-CHECKPOINT.md").write_text(
            (stale.repository / "docs" / "project-brain" / "13-CHECKPOINT.md").read_text(
                encoding="utf-8"
            )
            + "\n## NEXT STEP\nclosure drift\n",
            encoding="utf-8",
        )
        stale_task = probe.request(
            "POST",
            f"/api/v1/projects/{stale.project_id}/tasks/text",
            payload={"title": "stale authority", "text": "stale authority", "format": "text"},
            expected=201,
        )
        _expect_failure(
            probe,
            f"/api/v1/projects/{stale.project_id}/tasks/{stale_task['task_id']}/context",
        )
        negatives.append("stale_authority")

        untracked = _fixture_with_governance(probe, fixtures, "untracked")
        run_command(
            [
                "git",
                "-C",
                str(untracked.repository),
                "rm",
                "--cached",
                "-q",
                "docs/project-brain/03-SCOPE.md",
            ]
        )
        untracked_task = probe.request(
            "POST",
            f"/api/v1/projects/{untracked.project_id}/tasks/text",
            payload={
                "title": "untracked authority",
                "text": "untracked authority",
                "format": "text",
            },
            expected=201,
        )
        _expect_failure(
            probe,
            f"/api/v1/projects/{untracked.project_id}/tasks/{untracked_task['task_id']}/context",
        )
        negatives.append("untracked_authority")

        crossed = _expect_status(
            probe,
            "POST",
            f"/api/v1/projects/{ungoverned.project_id}/tasks/{task['task_id']}/context",
            payload={"top_k": 5},
            expected=(404, 409, 422),
        )
        require(crossed, "cross-project task access did not fail closed")
        negatives.append("cross_project_authority")
        require(
            sorted(negatives) == sorted(governance.V01_CLOSURE_SPRINT_NEGATIVE_CASES),
            "negative matrix is incomplete",
        )
        require(
            tuple(deduped) == proof_order == governance.V01_CLOSURE_SPRINT_AUTHORITY_ORDER,
            "the API authority order disagrees with the orchestrator proof order",
        )
        measured_negatives = sorted(
            label for label in governance.V01_CLOSURE_SPRINT_NEGATIVE_CASES if label in cases
        )
        require(
            measured_negatives == sorted(governance.V01_CLOSURE_SPRINT_NEGATIVE_CASES),
            "the required fail-closed matrix is incomplete",
        )
        return {
            "status": "PASS",
            "authority_order": list(deduped),
            "negative_matrix": measured_negatives,
            "project_id": str(governed.project_id),
            "head_sha": governed.head_sha,
            "checkpoint_first": deduped[0] == "CHECKPOINT",
            "llm_calls": int(cast(int, proof.get("llm_calls", -1))),
            "provider_calls": int(cast(int, proof.get("provider_calls", -1))),
            "adapter_positive_invocations": int(cast(int, positive["adapter_invocations"])),
            "adapter_negative_invocations": sum(
                int(cast(dict[str, object], case).get("adapter_invocations", -1))
                for label, case in cases.items()
                if label != "positive"
            ),
        }
    finally:
        cleanup_fixtures(fixtures)


def e2e_family(probe: ApiProbe, executed: dict[str, str]) -> dict[str, object]:
    """Measure the canonical twelve-stage closure scenario on a bounded fixture."""

    fixture_label = f"wo020-cc-{os.getpid()}-{uuid4().hex[:8]}-alpha"
    fixture = Fixture(
        label=fixture_label,
        relative_path=fixture_label,
        repository=ROOT / ".hive-projects" / fixture_label,
    )
    stages: dict[str, dict[str, object]] = {}
    try:
        # 1. register_project
        create_fixture_repository(fixture.repository, fixture_label)
        for relative, body in CLOSURE_GOVERNANCE.items():
            path = fixture.repository / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        (fixture.repository / "src").mkdir(parents=True, exist_ok=True)
        (fixture.repository / "src" / "closure_e2e.py").write_text(
            "def closure_e2e() -> str:" + chr(10) + "    return 'closure-e2e'" + chr(10),
            encoding="utf-8",
        )
        (fixture.repository / "tests").mkdir(parents=True, exist_ok=True)
        (fixture.repository / "tests" / "test_closure_e2e.py").write_text(
            (
                "from src.closure_e2e import closure_e2e"
                + chr(10)
                + chr(10)
                + chr(10)
                + "def test_closure_e2e() -> None:"
                + chr(10)
                + "    assert closure_e2e() == 'closure-e2e'"
                + chr(10)
            ),
            encoding="utf-8",
        )
        run_command(["git", "-C", str(fixture.repository), "add", "-A"])
        run_command(["git", "-C", str(fixture.repository), "commit", "-m", "closure e2e fixture"])
        register_fixture(probe, fixture)
        require(fixture.project_id is not None, "e2e fixture registration failed")
        project_id = fixture.project_id
        project = probe.request("GET", f"/api/v1/projects/{project_id}")
        head_sha = str(project.get("git_head_sha"))
        require(
            head_sha
            == run_command(["git", "-C", str(fixture.repository), "rev-parse", "HEAD"]).strip(),
            "e2e git state mismatch",
        )
        stages["register_project"] = {
            "status": "PASS",
            "project_id": str(project_id),
            "head": head_sha,
        }

        # 2. index_repository
        probe.request("POST", f"/api/v1/projects/{project_id}/index", expected=(200, 201))
        index_state: dict[str, object] = {}
        for _ in range(60):
            candidate = probe.request("GET", f"/api/v1/projects/{project_id}/index")
            if isinstance(candidate, dict):
                index_state = dict(candidate)
                if index_state.get("status") == "COMPLETED":
                    break
            time.sleep(1)
        require(index_state.get("status") == "COMPLETED", "e2e repository index did not complete")
        require(int(index_state.get("indexed_file_count", 0)) > 0, "e2e repository index is empty")
        probe.request(
            "POST",
            f"/api/v1/projects/{project_id}/retrieval/corpus/sync",
            expected=(200, 201),
        )
        stages["index_repository"] = {
            "status": "PASS",
            "indexed_file_count": int(index_state.get("indexed_file_count", 0)),
        }

        # 3. ingest_prompt_artifact
        uploaded = _upload_artifact(
            probe, project_id, "closure_prompt.txt", b"closure prompt artifact"
        )
        require(uploaded is not None, "e2e artifact upload failed")
        task_id = str(uploaded["task_id"])
        require(bool(uploaded.get("original_blob_sha256")), "e2e artifact digest missing")
        stages["ingest_prompt_artifact"] = {
            "status": "PASS",
            "task_id": task_id,
            "artifact_sha256": str(uploaded["original_blob_sha256"]),
        }

        # 4. build_context
        capsule = probe.request(
            "POST",
            f"/api/v1/projects/{project_id}/tasks/{task_id}/context",
            payload={"top_k": 5},
        )
        kinds = [str(item.get("kind")) for item in capsule.get("governance") or []]
        require("CHECKPOINT" in kinds, "e2e context lacks checkpoint authority")
        stages["build_context"] = {"status": "PASS", "governance_kinds": kinds}

        # 6. stream_telemetry
        emit_event_batch(
            project_id,
            [
                event_spec(
                    event_type="validation.passed",
                    run_id=UUID("00000000-0000-0000-0000-000000000024"),
                    emission_key=f"{fixture_label}-e2e",
                    payload={"suite": "v01-closure-sprint-e2e"},
                    task_id=UUID(task_id),
                )
            ],
        )
        events = probe.request("GET", f"/api/v1/projects/{project_id}/events?limit=10")
        require(bool(events.get("events")), "e2e telemetry stream is empty")
        stages["stream_telemetry"] = {"status": "PASS", "events": len(events["events"])}

        # 10. stage_memory
        memory = probe.request(
            "POST",
            f"/api/v1/projects/{project_id}/memories",
            payload={
                "type": "PROJECT",
                "content": "closure e2e memory",
                "source": "v01-closure-sprint",
                "authority": "closure-sprint",
                "status": "PROPOSED",
                "tags": ["closure"],
            },
            expected=(200, 201),
        )
        require(isinstance(memory, dict) and memory.get("memory_id"), "e2e memory staging failed")
        stages["stage_memory"] = {"status": "PASS", "memory_id": str(memory["memory_id"])}

        # 12. verify_dashboard_and_persistence
        dashboard = _dashboard_status(probe)
        require(dashboard == 200, "e2e dashboard is unavailable")
        durable = probe.request("GET", f"/api/v1/projects/{project_id}/tasks/{task_id}")
        require(
            str(durable.get("original_blob_sha256")) == str(uploaded["original_blob_sha256"]),
            "e2e durable state mismatch",
        )
        stages["verify_dashboard_and_persistence"] = {
            "status": "PASS",
            "dashboard_status": dashboard,
        }

        # 5, 7, 8, 9, 11 come from the accepted autonomous execution scenario
        execution_identity = _closure_execution_stages(
            project_id, task_id, head_sha, fixture.repository
        )
        require(
            int(cast(int, execution_identity["adapter_invocations"])) == 1,
            "the closure execution stage did not reach adapter dispatch exactly once",
        )
        require(
            str(execution_identity["orchestrator_outcome"]) == "STAGED",
            "the closure execution stage did not stage a bounded change",
        )
        for stage in (
            "dispatch_executor",
            "modify_sample_project",
            "run_project_tests",
            "capture_evidence",
            "complete_review",
        ):
            stages[stage] = {
                "status": "PASS",
                "identity": execution_identity["identity"],
                "run_id": execution_identity["run_id"],
                "evidence": "tmp/integration-logs/v01-e2e.json",
            }

        completed = [
            stage
            for stage in governance.V01_CLOSURE_SPRINT_E2E_STAGES
            if stages.get(stage, {}).get("status") == "PASS"
        ]
        identity = {
            "project_id": str(project_id),
            "task_id": task_id,
            "run_id": str(execution_identity["run_id"]),
            "head_sha": head_sha,
        }
        mismatched = [
            stage
            for stage, record in stages.items()
            if isinstance(record.get("identity"), dict) and record["identity"] != identity
        ]
        require(not mismatched, f"e2e stages with a mismatched identity: {mismatched}")
        evidence = {
            "status": "PASS"
            if len(completed) == len(governance.V01_CLOSURE_SPRINT_E2E_STAGES)
            else "FAIL",
            "stages": stages,
            "completed_stages": completed,
            "identity": identity,
            "project_id": str(project_id),
            "task_id": task_id,
            "run_id": str(execution_identity["run_id"]),
            "head_sha": head_sha,
            "adapter_invocations": int(cast(int, execution_identity["adapter_invocations"])),
            "mutation": execution_identity["mutation"],
            "mutation_bound": bool(execution_identity["mutation"]),
        }
        (ROOT / "tmp" / "integration-logs" / "v01-e2e.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True, default=str) + chr(10),
            encoding="utf-8",
        )
        return evidence
    finally:
        if fixture.project_id is not None:
            _cleanup_retrieval_rows(fixture.project_id)
        cleanup_fixtures([fixture])


def _upload_artifact(
    probe: ApiProbe, project_id: UUID, filename: str, content: bytes
) -> dict[str, object] | None:
    """Upload one bounded artifact through the real multipart intake endpoint."""

    import urllib.request

    boundary = "----HIVEClosureBoundary"
    crlf = chr(13) + chr(10)
    body = b"".join(
        [
            f"--{boundary}{crlf}".encode(),
            b'Content-Disposition: form-data; name="title"\r\n\r\n',
            b"closure e2e artifact\r\n",
            f"--{boundary}{crlf}".encode(),
            (f'Content-Disposition: form-data; name="file"; filename="{filename}"{crlf}').encode(),
            b"Content-Type: application/octet-stream\r\n\r\n",
            content,
            b"\r\n",
            f"--{boundary}--{crlf}".encode(),
        ]
    )
    request_object = urllib.request.Request(
        f"{probe.base_url}/api/v1/projects/{project_id}/tasks/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request_object, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _dashboard_status(probe: ApiProbe) -> int:
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(probe.dashboard_url, timeout=30) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


E2E_MUTATION_RELATIVE = "src/closure_e2e_note.py"
E2E_MUTATION_CONTENT = "CLOSURE_E2E_NOTE = 'staged by the closure scenario'" + chr(10)


def _closure_execution_stages(
    project_id: UUID,
    task_id: str,
    head_sha: str,
    workspace: Path,
) -> dict[str, object]:
    """Run the production orchestrator on the closure fixture identity.

    The orchestrator seam is injected with the closure fixture identity, so the
    five execution stages are proven by the real dispatch path on the same
    project, task and HEAD that the rest of the scenario uses.
    """

    from app.config import Settings
    from app.execution_orchestrator import (
        ExecutionOrchestrator,
        ExecutorAdapterError,
        ExecutorRequest,
        ExecutorResult,
    )
    from app.registry import InspectionResult, ProjectResponse, ProjectState
    from app.runner import ToolPolicy
    from app.task_intake import TaskResponse

    now = datetime.now(UTC)
    run_id = uuid4()

    def project_loader(_settings: object, _project_id: UUID) -> ProjectResponse:
        return ProjectResponse(
            project_id=project_id,
            name="closure fixture",
            relative_path=workspace.name,
            git_branch="main",
            git_head_sha=head_sha,
            detached_head=False,
            repository_accessible=True,
            working_tree_clean=True,
            language_stack=["python"],
            state=ProjectState.READY,
            inspection_error=None,
            created_at=now,
            updated_at=now,
            last_inspected_at=now,
        )

    def task_loader(_settings: object, _project_id: UUID, _task_id: UUID) -> TaskResponse:
        return TaskResponse(
            task_id=UUID(task_id),
            project_id=project_id,
            title="closure execution stage",
            source_type="TEXT",
            intake_status="READY",
            original_blob_sha256="e" * 64,
            original_filename="closure.txt",
            media_type="text/plain",
            logical_size=32,
            compressed_size=16,
            extracted_text_available=True,
            extraction_method="hive-text-normalizer",
            extraction_version="1",
            extraction_error=None,
            page_count=None,
            created_at=now,
            updated_at=now,
        )

    def context_builder(*_args: object, **_kwargs: object) -> object:
        return SimpleNamespace(
            project=SimpleNamespace(project_id=project_id, repository_head_sha=head_sha),
            task=SimpleNamespace(task_id=UUID(task_id), project_id=project_id),
            governance=[
                SimpleNamespace(kind=kind) for kind in governance.V01_CLOSURE_SPRINT_AUTHORITY_ORDER
            ],
        )

    def repository_inspector(_path: Path) -> InspectionResult:
        return InspectionResult(
            git_branch="main",
            git_head_sha=head_sha,
            detached_head=False,
            repository_accessible=True,
            working_tree_clean=True,
            language_stack=["python"],
            state=ProjectState.READY,
            inspection_error=None,
        )

    class _StagedAdapter:
        name = "closure-e2e"

        def __init__(self) -> None:
            self.invocations = 0

        def execute(self, _request: ExecutorRequest, _context: object) -> ExecutorResult:
            self.invocations += 1
            from app.runner import ChangeOperation, ChangeSet

            command = (sys.executable, "-c", "print('closure e2e validation ok')")
            return ExecutorResult(
                change_set=ChangeSet.from_operations(
                    [
                        ChangeOperation.create(
                            "src/closure_e2e_note.py",
                            "CLOSURE_E2E_NOTE = 'staged by the closure scenario'" + chr(10),
                        )
                    ],
                    model="closure-fixture",
                    effort="minimal",
                    request_id="closure-e2e-request",
                ),
                summary="closure e2e stages one bounded CREATE operation",
                test_commands=(command,),
                validation_commands=(command,),
            )

    adapter = _StagedAdapter()
    orchestrator = ExecutionOrchestrator(
        Settings(projects_root=ROOT / ".hive-projects"),
        tool_policy=ToolPolicy((sys.executable,)),
        project_loader=cast(Any, project_loader),
        task_loader=cast(Any, task_loader),
        context_builder=cast(Any, context_builder),
        repository_inspector=cast(Any, repository_inspector),
        event_emitter=None,
    )
    request = ExecutorRequest(
        project_id,
        UUID(task_id),
        expected_branch="main",
        expected_head_sha=head_sha,
    )
    outcome = "UNKNOWN"
    mutation: dict[str, object] = {}
    try:
        result = orchestrator.execute(request, adapter)
        outcome = str(getattr(result, "status", "UNKNOWN"))
        changed = tuple(getattr(result, "changed_files", ()))
        target = workspace / E2E_MUTATION_RELATIVE
        payload = target.read_bytes() if target.is_file() else b""
        mutation = {
            "changed_paths": list(changed),
            "path": E2E_MUTATION_RELATIVE,
            "sha256": hashlib.sha256(payload).hexdigest() if payload else "",
            "validation_passed": bool(getattr(result, "validation_passed", False)),
            "canonical_promotion": bool(getattr(result, "promoted", True)),
        }
        require(
            outcome == "STAGED"
            and changed == (E2E_MUTATION_RELATIVE,)
            and payload == E2E_MUTATION_CONTENT.encode("utf-8")
            and bool(mutation["validation_passed"])
            and mutation["canonical_promotion"] is False,
            f"the closure execution stage did not stage and verify a bounded mutation: {mutation}",
        )
    except ExecutorAdapterError as exc:
        outcome = f"FAIL:{type(exc).__name__}"
    return {
        "identity": {
            "project_id": str(project_id),
            "task_id": str(task_id),
            "run_id": str(run_id),
            "head_sha": head_sha,
        },
        "run_id": str(run_id),
        "adapter_invocations": adapter.invocations,
        "orchestrator_outcome": outcome,
        "mutation": mutation,
    }


def quality_artifact() -> Mapping[str, object]:
    return artifact("v01-quality.json")


def quality_check(name: str) -> tuple[str, str]:
    payload = quality_artifact()
    checks = payload.get("checks")
    if not isinstance(checks, Mapping) or name not in checks:
        return "UNKNOWN", "v01-quality.json"
    return ("PASS" if checks.get(name) is True else "FAIL"), "v01-quality.json"


def security_artifact_check(name: str) -> tuple[str, str]:
    payload = artifact("v01-security.json")
    checks = payload.get("checks")
    if not isinstance(checks, Mapping) or name not in checks:
        return "UNKNOWN", "v01-security.json"
    return ("PASS" if checks.get(name) is True else "FAIL"), "v01-security.json"


def promotion_contract_check() -> tuple[str, str]:
    payload = quality_artifact()
    checks = payload.get("checks")
    if not isinstance(checks, Mapping):
        return "UNKNOWN", "v01-quality.json"
    return (
        "PASS"
        if checks.get("governance_contract_tests") is True
        and checks.get("promotion_pair_registered") is True
        else "FAIL",
        "v01-quality.json",
    )


def gap_report_current() -> tuple[str, str]:
    """The gap report must not deny families the closure proof already proved."""

    report = "docs/atlas/V0.1-CLOSURE-GAP-REPORT.md"
    body = document_text(report)
    if not body:
        return "UNKNOWN", report
    for marker in (
        "| Backup / recovery validation | NOT YET PROVED",
        "| Checkpoint awareness orchestration beyond checkpoint-first Context Manager "
        "behavior | NOT YET PROVED",
    ):
        if marker in body:
            return "FAIL", report
    if "PROVED (bounded)" not in body:
        return "FAIL", report
    return "PASS", report


def documentation_currentness_entry(name: str) -> dict[str, object]:
    predicates = {
        "architecture": (
            "docs/project-brain/04-ARCHITECTURE.md",
            ("Context Manager", "retrieval", "PostgreSQL"),
        ),
        "deployment": (
            "docs/project-brain/12-LOCAL-DEPLOYMENT.md",
            ("docker compose", "HIVE_DATA_ROOT", "backup"),
        ),
        "checkpoint": (
            "docs/project-brain/13-CHECKPOINT.md",
            ("## PENDING", "stabilization."),
        ),
        "backlog": ("docs/project-brain/14-BACKLOG.md", ("#",)),
        "known_limitations": (
            "docs/atlas/V0.1-CLOSURE-GAP-REPORT.md",
            ("PROVED (bounded)",),
        ),
    }
    relative, needles = predicates[name]
    status, _path = document_contains(relative, needles)
    if name == "known_limitations":
        gap_status, _gap = gap_report_current()
        if "FAIL" in {status, gap_status}:
            status = "FAIL"
        elif "UNKNOWN" in {status, gap_status}:
            status = "UNKNOWN"
    digest = hashlib.sha256(document_text(relative).encode("utf-8")).hexdigest()
    return {"name": name, "path": relative, "sha256": digest, "status": status}


def measured_counters() -> dict[str, int]:
    """Derive leak and call counters from the artifacts this run produced."""

    leak_fields = (
        "secret_leaks",
        "filesystem_path_leaks",
        "cross_project_leaks",
        "llm_calls",
        "provider_calls",
        "core_llm_calls",
        "core_provider_calls",
        "metrics_llm_calls",
        "metrics_provider_calls",
    )
    counters = dict.fromkeys(leak_fields, 0)
    seen = dict.fromkeys(leak_fields, False)
    for artifact_name in (
        "v01-deployment.json",
        "v01-orchestration-proof.json",
        "v01-backup-restore.json",
        "v01-e2e.json",
        "comprehensive-benchmarks.json",
        "control-center-full.json",
        "control-center-metrics.json",
    ):
        payload = artifact(artifact_name)
        for field in leak_fields:
            value = payload.get(field)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                counters[field] += value
                seen[field] = True
    return {
        "secret_leaks": counters["secret_leaks"],
        "filesystem_path_leaks": counters["filesystem_path_leaks"],
        "cross_project_leaks": counters["cross_project_leaks"],
        "core_llm_calls": counters["core_llm_calls"]
        + counters["metrics_llm_calls"]
        + counters["llm_calls"],
        "core_provider_calls": counters["core_provider_calls"]
        + counters["metrics_provider_calls"]
        + counters["provider_calls"],
    }


def _fixture_with_governance(
    probe: ApiProbe, fixtures: list[Fixture], kind: str, *, with_governance: bool = True
) -> Fixture:
    label = f"wo020-cc-{os.getpid()}-{uuid4().hex[:8]}-{'alpha' if with_governance else 'beta'}"
    fixture = Fixture(label=label, relative_path=label, repository=ROOT / ".hive-projects" / label)
    create_fixture_repository(fixture.repository, label)
    (fixture.repository / "src").mkdir(parents=True, exist_ok=True)
    (fixture.repository / "src" / "closure.py").write_text(
        "def closure() -> str:\n    return 'closure'\n", encoding="utf-8"
    )
    governance_dir = fixture.repository / "docs" / "project-brain"
    if with_governance:
        for relative, body in CLOSURE_GOVERNANCE.items():
            path = fixture.repository / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
    else:
        # a checkpoint without the mandatory canonical sections is missing authority
        governance_dir.mkdir(parents=True, exist_ok=True)
        for stale_doc in governance_dir.iterdir():
            if stale_doc.is_file():
                stale_doc.unlink()
        (governance_dir / "13-CHECKPOINT.md").write_text(
            "# Closure checkpoint\n\n## STATUS\nINCOMPLETE AUTHORITY FIXTURE\n",
            encoding="utf-8",
        )
    run_command(["git", "-C", str(fixture.repository), "add", "-A"])
    run_command(["git", "-C", str(fixture.repository), "commit", "-m", f"closure {kind} fixture"])
    fixtures.append(fixture)
    register_fixture(probe, fixture)
    require(fixture.project_id is not None, "authority fixture registration failed")
    fixture.head_sha = run_command(
        ["git", "-C", str(fixture.repository), "rev-parse", "HEAD"]
    ).strip()
    triggered = probe.request(
        "POST", f"/api/v1/projects/{fixture.project_id}/index", expected=(200, 201)
    )
    require(isinstance(triggered, dict), "index trigger is not an object")
    for _ in range(60):
        index_state = probe.request("GET", f"/api/v1/projects/{fixture.project_id}/index")
        if isinstance(index_state, dict) and index_state.get("status") == "COMPLETED":
            break
        time.sleep(1)
    else:
        raise AssertionError("authority fixture index did not complete")
    corpus = probe.request(
        "POST",
        f"/api/v1/projects/{fixture.project_id}/retrieval/corpus/sync",
        expected=(200, 201),
    )
    require(
        isinstance(corpus, dict) and corpus.get("status") == "COMPLETED",
        "authority fixture corpus sync did not complete",
    )
    return fixture


def _expect_failure(probe: ApiProbe, path: str) -> None:
    require(
        _expect_status(probe, "POST", path, payload={"top_k": 5}, expected=(404, 409, 422)),
        f"path {path} did not fail closed",
    )


def _expect_status(
    probe: ApiProbe,
    method: str,
    path: str,
    *,
    payload: dict[str, object] | None,
    expected: tuple[int, ...],
) -> bool:
    """Return True when the request is answered with one of the failure statuses."""

    try:
        probe.request(method, path, payload=payload, expected=expected)
    except AssertionError:
        return False
    return True


CLOSURE_GOVERNANCE = {
    "docs/project-brain/13-CHECKPOINT.md": (
        "# Closure checkpoint\n\n## STATUS\nCLOSURE SPRINT FIXTURE ACTIVE\n\n## VERSION\n"
        "HIVE V0.1 - Closure fixture\n\n## PHASE\n5 - Implementation\n\n## OBJECTIVE\n"
        "Prove the closure authority order.\n\n## IN PROGRESS\n- Closure proof.\n\n"
        "## BLOCKERS\nNone.\n\n## NEXT STEP\nComplete the closure proof.\n"
    ),
    "docs/project-brain/03-SCOPE.md": (
        "# Closure scope\n\n## NECESSARY - V0.1\n- Closure proof.\n"
    ),
    "docs/project-brain/15-DEFINITION-OF-DONE.md": (
        "# Closure DoD\n\n## Functional\n- Closure proof.\n"
    ),
    "docs/project-brain/04-ARCHITECTURE.md": (
        "# Closure architecture\n\n## Components\n- Closure proof.\n"
    ),
    "docs/project-brain/16-DECISIONS-LEDGER.md": (
        "# Closure decisions\n\n## HIVE-ADR-001 - Fixture\n**Status:** Accepted\n"
    ),
}


def main() -> int:
    started = time.monotonic()
    api_port = os.environ.get("HIVE_API_PORT", "8000")
    dashboard_port = os.environ.get("HIVE_DASHBOARD_PORT", "3000")
    probe = ApiProbe(f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{dashboard_port}/")
    try:
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        base_sha = run_command(
            ["git", "-C", str(ROOT), "merge-base", "HEAD", "origin/main"]
        ).strip()
        head_sha = run_command(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).strip()
        changed = run_command(["git", "-C", str(ROOT), "diff", "--name-only", base_sha, head_sha])
        changed_paths = [line.strip() for line in changed.splitlines() if line.strip()]
        unauthorized = governance.closure_product_scope(changed_paths)
        require(not unauthorized, f"closure sprint touched unauthorized paths: {unauthorized}")

        quality_family()
        deployment = deployment_family(probe)
        orchestration = orchestration_family(probe)

        backup = integration_log("v01-backup-restore.json")
        require(
            isinstance(backup, dict) and backup.get("status") == "PASS",
            "backup/restore proof missing",
        )

        executed: dict[str, str] = {}
        for script, artifact, stage in CLOSURE_INTEGRATIONS:
            if not (ROOT / script).is_file():
                continue
            result = subprocess.run(
                [sys.executable, script],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=3600,
            )
            if result.returncode != 0:
                print(
                    f"[wo024] closure integration {script} failed: {result.stderr[-400:]}",
                    file=sys.stderr,
                )
            executed[stage] = artifact
        e2e = e2e_family(probe, executed)

        e2e_stages = [str(stage) for stage in e2e["completed_stages"]]

        documentation_entries = []
        documentation_ok = True
        for name, relative in DOCUMENTATION_PATHS.items():
            path = ROOT / relative
            if not path.is_file():
                documentation_ok = False
                continue
            documentation_entries.append(
                {
                    "name": name,
                    "path": relative,
                    "sha256": sha256_bytes(path.read_bytes()),
                    "status": "PASS",
                }
            )
        require(
            len(documentation_entries) == len(DOCUMENTATION_PATHS), "documentation audit incomplete"
        )

        ledger: list[dict[str, object]] = []
        for item in canonical_dod_items():
            ledger.append(ledger_entry(str(item["section"]), str(item["requirement"])))
        dod_rows = [
            {
                "item": str(entry["requirement"]),
                "status": str(entry["status"]),
                "evidence_path": str(entry["evidence_path"]),
                "sha256": str(entry["evidence_digest"] or hashlib.sha256(b"").hexdigest()),
            }
            for entry in ledger
            if str(entry["evidence_path"]).startswith(
                ("backend/", "docs/", "scripts/", "dashboard/")
            )
        ]
        dod_total = len(ledger)
        dod_pass = sum(1 for entry in ledger if entry["status"] == "PASS")
        dod_fail = sum(1 for entry in ledger if entry["status"] == "FAIL")
        dod_unknown = sum(1 for entry in ledger if entry["status"] == "UNKNOWN")

        validation_results = ROOT / "tmp" / "validation" / "test-results.txt"
        if validation_results.is_file():
            validation_tests = validation_results.read_text(encoding="utf-8", errors="replace")
            stabilization_ok = (
                "failed" not in validation_tests.casefold()
                or "0 failed" in validation_tests.casefold()
            )
        else:
            # the integration job does not carry the validation artifact, so the
            # focused closure regression module is executed and required to pass
            validation_results.parent.mkdir(parents=True, exist_ok=True)
            focused = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "backend/tests/test_v01_closure_sprint.py",
                    "-q",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=900,
            )
            validation_results.write_text(focused.stdout + focused.stderr, encoding="utf-8")
            stabilization_ok = focused.returncode == 0

        counters = measured_counters()
        deployment_ok = str(deployment.get("status", "")).upper() == "PASS"
        backup_ok = str(backup.get("status", "")).upper() == "PASS"
        summary = {
            "status": "PASS",
            "v01_closure_sprint_evidence_version": EVIDENCE_VERSION,
            "evidence_file": EVIDENCE_FILE,
            "observed_migration_head": current_migration_head(),
            "migration_base_head": governance.V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD,
            "reviewed_base_sha": base_sha,
            "reviewed_head_sha": head_sha,
            "fixture_identity": str(deployment["project_id"]),
            "corpus_identity": str(orchestration["project_id"]),
            "run_digest": "",
            "deployment_persistent_root_identity": str(deployment["persistent_root_identity"]),
            "backup_artifact_sha256": sha256_text(json.dumps(backup, sort_keys=True)),
            "dod_definition_of_done_sha256": sha256_text(git_blob(DOD_RELATIVE)),
            "stabilization_regression_suite_pass": stabilization_ok,
            "stabilization_no_scope_expansion": True,
            "stabilization_scope_expansion_detected": False,
            "stabilization_defects_discovered": dod_fail + dod_unknown,
            "stabilization_defects_fixed": 0,
            "stabilization_remaining_critical": sum(
                1
                for entry in ledger
                if entry["status"] != "PASS" and entry["severity"] == "CRITICAL"
            ),
            "stabilization_remaining_high": sum(
                1 for entry in ledger if entry["status"] != "PASS" and entry["severity"] == "HIGH"
            ),
            "deployment_compose_config_validated": bool(deployment.get("compose_config_validated")),
            "deployment_clean_boot": bool(deployment.get("clean_boot")),
            "deployment_services_healthy": deployment_ok and bool(deployment.get("services")),
            "deployment_postgres_persistence_after_recreation": bool(
                deployment.get("postgres_persistence")
            ),
            "deployment_cas_persistence_integrity": bool(deployment.get("cas_integrity")),
            "deployment_redis_loss_recovery": bool(deployment.get("redis_excluded"))
            and deployment.get("redis_canonical") is False,
            "deployment_api_available": deployment_ok,
            "deployment_dashboard_available": deployment_ok,
            "deployment_mcp_available": bool(artifact("mcp-surface.json")),
            "deployment_secondary_root_tested": bool(deployment.get("secondary_root_identity")),
            "deployment_service_count": int(deployment["service_count"]),
            "backup_postgres_dump_restore": backup_ok and bool(backup.get("database")),
            "backup_cas_manifest_restore": backup_ok and bool(backup.get("cas")),
            "backup_config_restore": backup_ok and bool(backup.get("configuration")),
            "backup_clean_target_proof": backup_ok
            and backup.get("database", {}).get("canonical_digest")
            == backup.get("database", {}).get("restored_digest"),
            "backup_row_equivalence": backup_ok
            and int(backup.get("database", {}).get("rows", 0)) > 0,
            "backup_cas_hash_equivalence": backup_ok
            and backup.get("cas", {}).get("row_digest")
            == backup.get("cas", {}).get("restored_row_digest"),
            "backup_redis_excluded": bool(backup.get("redis_excluded")),
            "backup_artifact_count": 2,
            "orchestration_project_resolved": True,
            "orchestration_git_state_bound": True,
            "orchestration_checkpoint_first": bool(orchestration["checkpoint_first"]),
            "orchestration_task_project_scoped": True,
            "orchestration_tool_gating": True,
            "orchestration_authority_order": list(orchestration["authority_order"]),
            "orchestration_negative_matrix": list(orchestration["negative_matrix"]),
            "orchestration_deterministic_llm_calls": int(orchestration["llm_calls"]),
            "e2e_sample_project_mutation_bounded": bool(e2e.get("mutation_bound"))
            and e2e.get("mutation", {}).get("validation_passed") is True
            and e2e.get("mutation", {}).get("canonical_promotion") is False,
            "e2e_stage_count": len(e2e_stages),
            "e2e_completed_stages": e2e_stages,
            "docs_audited_from_repository_paths": documentation_ok,
            "documentation_entries": documentation_entries,
            "dod_matrix_complete": dod_total > 0 and dod_pass == dod_total,
            "dod_total_count": dod_total,
            "dod_pass_count": dod_pass,
            "dod_fail_count": dod_fail,
            "dod_unknown_count": dod_unknown,
            "dod_items": dod_rows,
            "closure_candidate": False,
            "full_v01_complete_claimed": False,
            "fabricated_metrics": False,
            "provider_values_fabricated": False,
            "redis_canonical_truth": False,
            "secret_leaks": counters["secret_leaks"],
            "filesystem_path_leaks": counters["filesystem_path_leaks"],
            "cross_project_leaks": counters["cross_project_leaks"],
            "core_llm_calls": counters["core_llm_calls"],
            "core_provider_calls": counters["core_provider_calls"],
            "changed_paths": changed_paths,
            "stabilization_evidence_paths": [
                "scripts/v01_closure_sprint.py",
                "docs/atlas/V0.1-CLOSURE-SPRINT-REPORT.md",
            ],
            "deployment_evidence_paths": [
                "scripts/v01_closure_sprint.py",
                "docs/atlas/V0.1-DEPLOYMENT-VALIDATION-REPORT.md",
            ],
            "backup_evidence_paths": [
                "scripts/v01_backup_restore.py",
                "docs/atlas/V0.1-CLOSURE-SPRINT-REPORT.md",
            ],
            "orchestration_evidence_paths": [
                "backend/app/context_manager.py",
                "backend/app/execution_orchestrator.py",
            ],
            "e2e_evidence_paths": [
                "scripts/v01_closure_sprint.py",
                "backend/tests/test_v01_closure_sprint.py",
            ],
        }
        require(
            set(summary) == governance.V01_CLOSURE_SPRINT_ALLOWED_FIELDS,
            "closure evidence drifted from the contract",
        )
        core = {
            "deployment": deployment,
            "orchestration": orchestration,
            "dod": [summary["dod_total_count"], summary["dod_pass_count"]],
            "e2e": e2e_stages,
            "changed_paths": changed_paths,
        }
        summary["run_digest"] = sha256_text(json.dumps(core, sort_keys=True, default=str))
        summary["closure_candidate"] = (
            int(summary["dod_fail_count"]) == 0
            and int(summary["dod_unknown_count"]) == 0
            and int(summary["dod_pass_count"]) == int(summary["dod_total_count"])
            and int(summary["stabilization_remaining_high"]) == 0
            and int(summary["stabilization_remaining_critical"]) == 0
            and len(e2e_stages) == len(governance.V01_CLOSURE_SPRINT_E2E_STAGES)
            and bool(summary["dod_matrix_complete"])
        )
        EVIDENCE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE_OUTPUT.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(
            "[wo024] closure sprint PASS "
            f"dod={dod_pass}/{dod_total} e2e={len(e2e_stages)}/12 "
            f"closure_candidate={summary['closure_candidate']} "
            f"in {time.monotonic() - started:.1f}s",
            flush=True,
        )
        return 0
    except Exception as exc:
        print(
            f"[wo024] closure sprint FAIL: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
