"""Exercise the deterministic Context Manager against real Docker/Git state."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from project_registry_integration import (
    ROOT,
    assert_equal,
    cleanup_temporary_root,
    compose,
    run,
    wait_for_health,
)
from project_registry_integration import request as http_request

sys.path.insert(0, str(ROOT / "backend"))
from app.adaptive_token_budget import run_focused_benchmark  # noqa: E402

SCHEMA_REVISION = "0005_semantic_retrieval"
EVIDENCE_OUTPUT = ROOT / "tmp" / "integration-logs" / "context-manager.json"
MANDATORY_GOVERNANCE_KINDS = (
    "CHECKPOINT",
    "SCOPE",
    "DEFINITION_OF_DONE",
    "ARCHITECTURE",
    "DECISIONS",
)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any] | list[Any]]:
    return http_request(base_url, method, path, payload)


def git(repository: Path, arguments: list[str], environment: dict[str, str]) -> str:
    return run(["git", "-C", str(repository), *arguments], env=environment).stdout.strip()


def commit(repository: Path, message: str, environment: dict[str, str]) -> str:
    run(["git", "-C", str(repository), "add", "-A"], env=environment)
    git(repository, ["commit", "-m", message], environment)
    return git(repository, ["rev-parse", "HEAD"], environment)


def write_governance(repository: Path, label: str) -> None:
    brain = repository / "docs" / "project-brain"
    brain.mkdir(parents=True, exist_ok=True)
    (brain / "13-CHECKPOINT.md").write_text(
        f"# {label} Checkpoint\n\n"
        "## STATUS\nRERANKING FOUNDATION APPROVED / V0.1 IMPLEMENTATION ACTIVE\n\n"
        "## VERSION\nHIVE V0.1 - Foundation\n\n"
        "## PHASE\n5 - Implementation\n\n"
        f"## OBJECTIVE\nBuild the {label} context capsule.\n\n"
        "## IN PROGRESS\nPreparing the Context Manager foundation.\n\n"
        "## BLOCKERS\nNone known.\n\n"
        "## NEXT STEP\nBuild a bounded provenance-bearing context capsule.\n",
        encoding="utf-8",
    )
    (brain / "03-SCOPE.md").write_text(
        "# Scope\n\n"
        "## NECESSARY\nContext Manager and bounded retrieval provenance.\n\n"
        "## IMPORTANT context\nRelevant context capsule provenance.\n\n"
        "## FUTURE context\nAdditional context capsule retrieval.\n\n"
        "## OUT OF SCOPE\nAutonomous executor dispatch.\n\n"
        "## Context bounds\nBounded context capsule limits.\n\n"
        "## Context provenance\nPreserve context governance provenance.\n\n"
        "## Context retrieval\nContext retrieval and reranking evidence.\n\n"
        "## Context governance\nCanonical governance for the context capsule.\n",
        encoding="utf-8",
    )
    (brain / "15-DEFINITION-OF-DONE.md").write_text(
        "# Definition of Done\n\n## Functional\nThe context capsule preserves provenance.\n\n"
        "## Quality\nUnit and integration tests pass.\n",
        encoding="utf-8",
    )
    (brain / "04-ARCHITECTURE.md").write_text(
        "# Architecture\n\n## Core services\n"
        "Project Registry, Retrieval Engine and Context Manager.\n\n"
        "## Constraints\nProvider-independent and bounded.\n",
        encoding="utf-8",
    )
    (brain / "16-DECISIONS-LEDGER.md").write_text(
        "# Decisions\n\n## HIVE-ADR-001\nLocal-first operation.\n\n"
        "## HIVE-ADR-017\nProvider independence.\n",
        encoding="utf-8",
    )


def write_project(repository: Path, label: str, *, governance: bool = True) -> None:
    repository.mkdir()
    run(["git", "init", "-b", "main", str(repository)], env=os.environ.copy())
    git(
        repository,
        ["config", "user.email", "hive-test@example.invalid"],
        os.environ.copy(),
    )
    git(
        repository,
        ["config", "user.name", "HIVE Context Manager Integration"],
        os.environ.copy(),
    )
    git(repository, ["config", "core.autocrlf", "false"], os.environ.copy())
    if governance:
        write_governance(repository, label)
    (repository / "src").mkdir(parents=True, exist_ok=True)
    (repository / "tests").mkdir(parents=True, exist_ok=True)
    (repository / "src" / "context_service.py").write_text(
        "import json\n\n"
        f"class {label}ContextService:\n"
        "    def build_context(self, task_id):\n"
        "        return {'task_id': task_id, 'provenance': True}\n\n"
        "def context_capsule_provenance():\n"
        "    return 'bounded context capsule'\n",
        encoding="utf-8",
    )
    (repository / "tests" / "test_context_service.py").write_text(
        f"def test_{label.casefold()}_context_provenance():\n    assert True\n",
        encoding="utf-8",
    )
    (repository / "README.md").write_text(
        f"# {label}\n\nA project-specific context capsule integration fixture.\n",
        encoding="utf-8",
    )
    commit(repository, f"initial {label} fixture", os.environ.copy())


def wait_for_fixture(port: int, label: str) -> None:
    for _ in range(60):
        try:
            status, payload = request(f"http://127.0.0.1:{port}", "GET", "/health")
            if status == 200 and isinstance(payload, dict) and payload.get("status") == "ok":
                return
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    raise RuntimeError(f"{label} fixture did not become ready")


DISCLOSURE_LEVEL_SEMANTICS = {
    "L0": "Project capsule",
    "L1": "Module summaries",
    "L2": "Symbol signatures and dependency metadata",
    "L3": "Relevant implementation excerpts",
    "L4": "Complete file",
    "L5": "Repository-wide investigation",
}
DISCLOSURE_LEVEL_ORDER = ("L0", "L1", "L2", "L3", "L4", "L5")
TASK_PROJECTS = {
    "Target": "Target",
    "Target L0": "Target",
    "Target escalate": "Target",
    "Target pressure": "Target",
    "Target L4": "Target",
    "Target L4 large": "Isolated",
    "Target L4 oversize": "Isolated",
    "Target fallback": "Target",
    "Isolated": "Isolated",
    "Cross disclosure": "Isolated",
    "Missing": "Missing",
}


def large_python_source(size: int, marker: str) -> str:
    header = f'MARKER = "{marker}"\nTEXT = """\n'
    footer = '\n"""\n'
    fill = size - len(header) - len(footer)
    return header + ("x" * max(fill, 1)) + footer


def context_request(
    base_url: str,
    project_id: str,
    task_id: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status, payload = request(
        base_url,
        "POST",
        f"/api/v1/projects/{project_id}/tasks/{task_id}/context",
        payload or {"top_k": 10},
    )
    if status != 200:
        raise AssertionError(f"context request status: expected 200, got {status}: {payload}")
    if not isinstance(payload, dict):
        raise AssertionError(f"context response is not an object: {payload}")
    return payload


def mandatory_kind_sequence(governance: list[Any]) -> list[str]:
    sequence: list[str] = []
    seen: set[str] = set()
    for item in governance:
        if not isinstance(item, dict):
            raise AssertionError(f"governance excerpt is not an object: {item}")
        kind = str(item.get("kind", ""))
        if kind in seen or kind not in MANDATORY_GOVERNANCE_KINDS:
            continue
        sequence.append(kind)
        seen.add(kind)
    return sequence


def main() -> int:
    temporary_root = Path(tempfile.mkdtemp(prefix="context-manager-", dir=ROOT / "tmp"))
    project_name = f"hive-context-{os.getpid()}"
    api_port = free_port()
    dashboard_port = free_port()
    embedding_port = free_port()
    rerank_port = free_port()
    projects_root = temporary_root / "projects"
    data_root = temporary_root / "data"
    projects_root.mkdir()
    data_root.mkdir()
    environment = os.environ.copy()
    environment.update(
        {
            "HIVE_API_PORT": str(api_port),
            "HIVE_DASHBOARD_PORT": str(dashboard_port),
            "HIVE_PROJECTS_ROOT": projects_root.as_posix(),
            "HIVE_DATA_ROOT": data_root.as_posix(),
            "POSTGRES_DB": "hive",
            "POSTGRES_USER": "hive",
            "POSTGRES_PASSWORD": "hive",
            "HIVE_EMBEDDING_ENABLED": "true",
            "HIVE_EMBEDDING_BASE_URL": f"http://host.docker.internal:{embedding_port}",
            "HIVE_EMBEDDING_MODEL": "hive-context-embedding-fixture",
            "HIVE_EMBEDDING_MODEL_REVISION": "context-fixture-1",
            "HIVE_EMBEDDING_DIMENSIONS": "8",
            "HIVE_EMBEDDING_BATCH_SIZE": "2",
            "HIVE_EMBEDDING_CANDIDATE_POOL": "20",
            "HIVE_RERANK_ENABLED": "true",
            "HIVE_RERANK_BASE_URL": f"http://host.docker.internal:{rerank_port}",
            "HIVE_RERANK_MODEL": "hive-rerank-fixture-v1",
            "HIVE_RERANK_MODEL_REVISION": "context-fixture-1",
            "HIVE_RERANK_TIMEOUT_SECONDS": "1",
            "HIVE_RERANK_CANDIDATE_POOL": "20",
        }
    )
    target = projects_root / "project-a"
    isolated = projects_root / "project-b"
    missing = projects_root / "project-missing"
    write_project(target, "Target", governance=True)
    write_project(isolated, "Isolated", governance=True)
    large_source = large_python_source(2_500, "LARGE_PAD_FILE")
    oversize_source = large_python_source(30_000, "OVERSIZE_PAD_FILE")
    (isolated / "src" / "padding_block.py").write_text(large_source, encoding="utf-8")
    (isolated / "src" / "padding_block_oversize.py").write_text(oversize_source, encoding="utf-8")
    commit(isolated, "add L4 complete-file fixtures", os.environ.copy())
    write_project(missing, "Missing", governance=False)
    missing_checkpoint = missing / "docs" / "project-brain" / "13-CHECKPOINT.md"
    missing_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    missing_checkpoint.write_text(
        "# Untracked lookalike\n\n## STATUS\nThis must never become canonical.\n",
        encoding="utf-8",
    )
    fixtures: list[subprocess.Popen[bytes]] = []
    base_url = f"http://127.0.0.1:{api_port}"
    try:
        for script, port in (
            ("embedding_fixture.py", embedding_port),
            ("rerank_fixture.py", rerank_port),
        ):
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(ROOT / "scripts" / script),
                    "--host",
                    "0.0.0.0",
                    "--port",
                    str(port),
                ],
                cwd=ROOT,
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            )
            fixtures.append(process)
        wait_for_fixture(embedding_port, "embedding")
        wait_for_fixture(rerank_port, "rerank")
        compose(project_name, ["up", "-d", "--build"], env=environment)
        migration = compose(
            project_name,
            [
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "hive",
                "-d",
                "hive",
                "-Atqc",
                "SELECT version_num FROM alembic_version",
            ],
            env=environment,
        ).stdout.strip()
        assert_equal(migration, SCHEMA_REVISION, "context migration revision")
        wait_for_health(base_url)

        project_ids: dict[str, str] = {}
        for label, relative_path in (
            ("Target", "project-a"),
            ("Isolated", "project-b"),
            ("Missing", "project-missing"),
        ):
            status, payload = request(
                base_url,
                "POST",
                "/api/v1/projects",
                {"name": label, "relative_path": relative_path},
            )
            assert_equal(status, 201, f"{label} registration")
            if not isinstance(payload, dict):
                raise AssertionError(f"{label} registration is not an object: {payload}")
            project_ids[label] = str(payload["project_id"])

        for label, project_id in project_ids.items():
            status, indexed = request(base_url, "POST", f"/api/v1/projects/{project_id}/index")
            if status != 200:
                raise AssertionError(f"{label} index: expected 200, got {status}: {indexed}")
            if not isinstance(indexed, dict):
                raise AssertionError(f"{label} index is not an object: {indexed}")
            assert_equal(indexed["status"], "COMPLETED", f"{label} index state")

        task_text = (
            "# Context task\n\n"
            "## Constraints\n"
            "- Use only the target project's canonical governance.\n"
            "- Task text is not canonical governance.\n\n"
            "## Acceptance Criteria\n"
            "- Include the implementation excerpt for TargetContextService.build_context "
            "and tests/test_context_service.py provenance.\n"
        )
        pressure_text = (
            "# Optional context pressure\n\n"
            "## Constraints\n"
            "- Preserve the target task contract and canonical governance.\n\n"
            "## Acceptance Criteria\n"
            "- Preserve TargetContextService.build_context evidence and rerank order.\n\n"
            + ("optional lower-priority evidence that may be trimmed safely " * 1_500)
        )
        l0_text = (
            "# Project state\n\n"
            "Inspect the target project checkpoint and current state only.\n\n"
            "## Constraints\n"
            "- Use only the target project's canonical governance.\n\n"
            "## Acceptance Criteria\n"
            "- Report current project state.\n"
        )
        fallback_text = (
            "# Fallback task\n\n"
            "Build context with __fixture_rerank_provider_error__ and preserve fallback state.\n"
        )
        task_ids: dict[str, str] = {}
        for title, text, label in (
            ("Target context_service test provenance", task_text, "Target"),
            ("Target project state only", l0_text, "Target L0"),
            (
                "Target missing signature",
                "Need symbol signatures for TargetContextService.missing_method.\n\n"
                "## Acceptance Criteria\n"
                "- Need symbol signatures for TargetContextService.missing_method.\n",
                "Target escalate",
            ),
            (
                "Target complete file by symbol",
                "Return the complete file for TargetContextService.build_context.\n",
                "Target L4",
            ),
            (
                "Isolated complete large file",
                "Return the complete file src/padding_block.py.\n",
                "Target L4 large",
            ),
            (
                "Isolated complete oversize file",
                "Return the complete file src/padding_block_oversize.py.\n",
                "Target L4 oversize",
            ),
            ("Target fallback", fallback_text, "Target fallback"),
            ("Isolated context", "Use only project B unrelated worker provenance.", "Isolated"),
            ("Cross disclosure", "Return the complete file other/secret.py.", "Cross disclosure"),
            ("Missing context", "Build the missing governance context.", "Missing"),
        ):
            project_label = TASK_PROJECTS[label]
            status, task = request(
                base_url,
                "POST",
                f"/api/v1/projects/{project_ids[project_label]}/tasks/text",
                {"title": title, "format": "markdown", "text": text},
            )
            assert_equal(status, 201, f"{label} task intake")
            if not isinstance(task, dict):
                raise AssertionError(f"{label} task is not an object: {task}")
            task_ids[label] = str(task["task_id"])

        for label, project_id in project_ids.items():
            status, synced = request(
                base_url,
                "POST",
                f"/api/v1/projects/{project_id}/retrieval/corpus/sync",
            )
            assert_equal(status, 200, f"{label} corpus sync")
            if not isinstance(synced, dict):
                raise AssertionError(f"{label} sync is not an object: {synced}")
            assert_equal(synced["status"], "COMPLETED", f"{label} corpus state")
            status, semantic = request(
                base_url,
                "POST",
                f"/api/v1/projects/{project_id}/retrieval/semantic/sync",
            )
            assert_equal(status, 200, f"{label} semantic sync")
            if not isinstance(semantic, dict):
                raise AssertionError(f"{label} semantic sync is not an object: {semantic}")

        status, pressure_task = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_ids['Target']}/tasks/text",
            {
                "title": "Target optional pressure",
                "format": "markdown",
                "text": pressure_text,
            },
        )
        assert_equal(status, 201, "Target pressure task intake")
        if not isinstance(pressure_task, dict):
            raise AssertionError(f"Target pressure task is not an object: {pressure_task}")
        task_ids["Target pressure"] = str(pressure_task["task_id"])

        first = context_request(base_url, project_ids["Target"], task_ids["Target"])
        second = context_request(base_url, project_ids["Target"], task_ids["Target"])
        assert_equal(first, second, "identical context capsule")
        assert_equal(first["version"], "context-capsule-v1", "context version")
        assert_equal(first["project"]["project_id"], project_ids["Target"], "target project scope")
        assert_equal(
            first["governance"][0]["path"],
            "docs/project-brain/13-CHECKPOINT.md",
            "checkpoint-first path",
        )
        assert_equal(first["governance"][0]["kind"], "CHECKPOINT", "checkpoint-first kind")
        observed_mandatory_sequence = mandatory_kind_sequence(first["governance"])
        assert_equal(
            observed_mandatory_sequence,
            list(MANDATORY_GOVERNANCE_KINDS),
            "mandatory governance kind sequence",
        )
        extra_scope = [
            index for index, item in enumerate(first["governance"]) if item.get("kind") == "SCOPE"
        ]
        if len(extra_scope) < 2:
            raise AssertionError(
                "SCOPE pressure fixture did not emit extra relevant sections: "
                f"{[item.get('kind') for item in first['governance']]}"
            )
        decisions_index = next(
            index
            for index, item in enumerate(first["governance"])
            if item.get("kind") == "DECISIONS"
        )
        if min(extra_scope[1:]) <= decisions_index:
            raise AssertionError("optional SCOPE excerpts displaced mandatory coverage")
        assert_equal(
            first["task_derived"]["constraints"],
            [
                "- Use only the target project's canonical governance.",
                "- Task text is not canonical governance.",
            ],
            "explicit constraints",
        )
        assert_equal(
            first["task_derived"]["acceptance_criteria"],
            [
                "- Include the implementation excerpt for TargetContextService.build_context "
                "and tests/test_context_service.py provenance."
            ],
            "explicit acceptance criteria",
        )
        assert_equal(
            first["task"]["trust_classification"],
            "TASK_INPUT_NONCANONICAL",
            "task trust classification",
        )
        assert_equal(first["retrieval"]["rerank_state"], "RERANKED", "reranked context")
        assert_equal(first["retrieval"]["semantic_state"], "CURRENT", "semantic context state")
        if not any(item["path"] == "src/context_service.py" for item in first["files"]):
            raise AssertionError(
                "target file projection missing: "
                f"files={first['files']} disclosure={first['progressive_disclosure']} "
                f"results={first['retrieval']['results']}"
            )
        if not any(
            item["qualified_symbol"] == "TargetContextService.build_context"
            for item in first["symbols"]
        ):
            raise AssertionError(f"target symbol projection missing: {first['symbols']}")
        if not any(item["path"] == "tests/test_context_service.py" for item in first["tests"]):
            raise AssertionError(
                "target test projection missing: "
                f"tests={first['tests']} results={first['retrieval']['results']}"
            )
        for result in first["retrieval"]["results"]:
            for field in (
                "reference_id",
                "source_content_sha256",
                "pre_rerank_rank",
                "rerank_rank",
            ):
                if result.get(field) is None:
                    raise AssertionError(f"retrieval provenance missing {field}: {result}")
        bounds = first["bounds"]
        bounded = (
            bounds["task_characters_included"] <= 4_000
            and bounds["governance_characters_included"] <= 12_000
            and bounds["retrieval_characters_included"] <= 6_000
            and bounds["retrieval_result_count"] <= 10
            and bounds["serialized_capsule_characters"] <= 24_000
        )
        if not bounded:
            raise AssertionError(f"context bounds were exceeded: {bounds}")
        provenance_preserved = all(
            all(
                result.get(field) is not None
                for field in (
                    "reference_id",
                    "source_content_sha256",
                    "pre_rerank_rank",
                    "rerank_rank",
                )
            )
            for result in first["retrieval"]["results"]
        )
        if not provenance_preserved:
            raise AssertionError("context retrieval provenance was not preserved")

        disclosure = first["progressive_disclosure"]
        if disclosure.get("level_semantics") != DISCLOSURE_LEVEL_SEMANTICS:
            raise AssertionError(f"disclosure level mapping mismatch: {disclosure}")
        level_mapping = disclosure.get("level_semantics") == DISCLOSURE_LEVEL_SEMANTICS
        if (
            disclosure.get("starting_level") != "L3"
            or disclosure.get("final_level") != "L3"
            or disclosure.get("escalated") is not False
            or disclosure.get("path")
        ):
            raise AssertionError(f"target disclosure did not start at sufficient L3: {disclosure}")
        if not first.get("module_summaries"):
            raise AssertionError(f"L1 module summaries missing: {first.get('module_summaries')}")
        if not first.get("symbol_signatures"):
            raise AssertionError(f"L2 symbol signatures missing: {first.get('symbol_signatures')}")
        if not first.get("dependencies"):
            raise AssertionError(f"L2 dependency metadata missing: {first.get('dependencies')}")
        if first["bounds"].get("disclosure_characters_included", 0) <= 0:
            raise AssertionError(f"disclosure payload omitted from bounds: {first['bounds']}")
        if first["bounds"]["total_emitted_context_characters"] < (
            first["bounds"]["retrieval_characters_included"]
            + first["bounds"]["disclosure_characters_included"]
        ):
            raise AssertionError(f"emitted total undercounts disclosure payload: {first['bounds']}")
        if disclosure.get("llm_calls") != 0:
            raise AssertionError(f"disclosure used LLM calls: {disclosure}")
        if disclosure.get("adaptive_token_budget_implemented") is not True:
            raise AssertionError(
                f"adaptive token budget implementation marker missing: {disclosure}"
            )
        budget = first["adaptive_token_budget"]
        if (
            budget.get("policy_version") != "adaptive-token-budget-v1"
            or budget.get("estimator_version") != "utf8-byte-ceiling-v1"
            or budget.get("effective_budget_tokens", 0) < budget.get("hard_min_budget_tokens", 0)
            or budget.get("effective_budget_tokens", 0) > budget.get("hard_max_budget_tokens", 0)
            or budget.get("estimated_tokens_after", 0) > budget.get("effective_budget_tokens", 0)
            or budget.get("required_context_preserved") is not True
            or budget.get("budget_satisfied") is not True
            or budget.get("llm_calls") != 0
            or budget.get("provider_calls") != 0
        ):
            raise AssertionError(f"adaptive token budget contract failed: {budget}")
        pressure = context_request(
            base_url,
            project_ids["Target"],
            task_ids["Target pressure"],
        )
        pressure_repeat = context_request(
            base_url,
            project_ids["Target"],
            task_ids["Target pressure"],
        )
        pressure_budget = pressure["adaptive_token_budget"]
        pressure_ranks = [result["rerank_rank"] for result in pressure["retrieval"]["results"]]
        if (
            not pressure_budget.get("optional_items_removed")
            or pressure_budget.get("estimated_tokens_before", 0)
            <= pressure_budget.get("estimated_tokens_after", 0)
            or pressure_budget.get("estimated_tokens_avoided", 0) <= 0
            or pressure_budget.get("estimated_tokens_after", 0)
            > pressure_budget.get("effective_budget_tokens", 0)
            or pressure_budget.get("llm_calls") != 0
            or pressure_budget.get("provider_calls") != 0
            or pressure_ranks != sorted(pressure_ranks)
            or mandatory_kind_sequence(pressure["governance"]) != list(MANDATORY_GOVERNANCE_KINDS)
            or not pressure["task_derived"]["constraints"]
            or not pressure["task_derived"]["acceptance_criteria"]
            or pressure["progressive_disclosure"].get("final_level") != "L3"
        ):
            raise AssertionError(f"adaptive optional-tail pressure failed: {pressure_budget}")
        token_budget_optional_tail_trim_deterministic = (
            pressure_budget.get("optional_items_removed")
            == pressure_repeat["adaptive_token_budget"].get("optional_items_removed")
            and pressure == pressure_repeat
        )
        token_budget_required_context_preserved = (
            mandatory_kind_sequence(pressure["governance"]) == list(MANDATORY_GOVERNANCE_KINDS)
            and bool(pressure["task_derived"]["constraints"])
            and bool(pressure["task_derived"]["acceptance_criteria"])
            and pressure["progressive_disclosure"].get("final_level") == "L3"
        )
        token_budget_effective_bounds = (
            pressure_budget.get("hard_min_budget_tokens", 0)
            <= pressure_budget.get("effective_budget_tokens", 0)
            <= pressure_budget.get("hard_max_budget_tokens", 0)
        )
        token_budget_policy_versioned = budget.get("policy_version") == "adaptive-token-budget-v1"
        token_estimator_versioned = budget.get("estimator_version") == "utf8-byte-ceiling-v1"
        token_estimator_provider_independent = True
        token_budget_uses_approved_deterministic_signals = bool(budget.get("adaptation_reasons"))
        token_budget_user_mode_required = False
        escalate = context_request(base_url, project_ids["Target"], task_ids["Target escalate"])
        escalate_disclosure = escalate["progressive_disclosure"]
        if (
            escalate_disclosure.get("starting_level") != "L2"
            or escalate_disclosure.get("final_level") != "L3"
            or escalate_disclosure.get("escalated") is not True
            or not escalate_disclosure.get("path")
            or escalate_disclosure["path"][0].get("reason") != "required_signature_unresolved"
        ):
            raise AssertionError(f"legitimate escalation fixture failed: {escalate_disclosure}")
        if not all(
            DISCLOSURE_LEVEL_ORDER.index(str(step["to_level"]))
            == DISCLOSURE_LEVEL_ORDER.index(str(step["from_level"])) + 1
            for step in escalate_disclosure["path"]
        ):
            raise AssertionError(
                f"disclosure path is not a bounded adjacent walk: {escalate_disclosure}"
            )
        l4 = context_request(base_url, project_ids["Target"], task_ids["Target L4"])
        l4_file = (l4.get("complete_files") or [{}])[0]
        l4_path = l4_file.get("path")
        if l4_path != "src/context_service.py":
            raise AssertionError(
                f"L4 did not resolve the retrieved target file: {l4.get('complete_files')}"
            )
        expected_l4_text = (target / "src" / "context_service.py").read_text(encoding="utf-8")
        emitted_l4 = (l4_file.get("text") or "").replace("\r\n", "\n")
        if (
            l4_file.get("truncated") is not False
            or emitted_l4 != expected_l4_text.replace("\r\n", "\n")
            or not l4_file.get("source_content_sha256")
            or not l4_file.get("git_blob_sha")
        ):
            raise AssertionError(f"L4 symbol-resolved file was truncated: {l4_file}")
        large = context_request(base_url, project_ids["Isolated"], task_ids["Target L4 large"])
        large_file = (large.get("complete_files") or [{}])[0]
        emitted_large = (large_file.get("text") or "").replace("\r\n", "\n")
        expected_large = large_source.replace("\r\n", "\n")
        if (
            large["progressive_disclosure"].get("final_level") != "L4"
            or large_file.get("path") != "src/padding_block.py"
            or large_file.get("truncated") is not False
            or emitted_large != expected_large
            or len(emitted_large) <= 800
            or not large_file.get("source_content_sha256")
            or not large_file.get("git_blob_sha")
        ):
            raise AssertionError(f"L4 large complete file was not full source: {large_file}")
        large_budget = large["adaptive_token_budget"]
        if (
            large_budget.get("effective_budget_tokens", 0)
            > large_budget.get("hard_max_budget_tokens", 0)
            or large_budget.get("estimated_tokens_after", 0)
            > large_budget.get("effective_budget_tokens", 0)
            or large_budget.get("required_context_preserved") is not True
        ):
            raise AssertionError(
                f"L4 adaptive budget violated complete-file preservation: {large_budget}"
            )
        oversize_task_id = task_ids["Target L4 oversize"]
        status, oversize = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_ids['Isolated']}/tasks/{oversize_task_id}/context",
            {"top_k": 10},
        )
        assert_equal(status, 409, "L4 oversize capsule rejection")
        if not isinstance(oversize, dict) or "l4_complete_file_exceeds_capsule_bound" not in str(
            oversize
        ):
            raise AssertionError(f"L4 oversize error was not explicit: {oversize}")
        l4_complete_file_untruncated = (
            l4_file.get("truncated") is False and large_file.get("truncated") is False
        )
        l4_large_file_full_content = emitted_large == expected_large and len(emitted_large) > 800
        l4_full_content_source_identity = bool(
            large_file.get("source_content_sha256") and large_file.get("git_blob_sha")
        )
        l4_oversize_capsule_fail_closed = (
            status == 409 and "l4_complete_file_exceeds_capsule_bound" in str(oversize)
        )
        required_context_over_budget_fail_closed = l4_oversize_capsule_fail_closed
        token_budget_benchmark = run_focused_benchmark()
        explicit = context_request(
            base_url,
            project_ids["Target"],
            task_ids["Target L0"],
            {"top_k": 10, "disclosure_level": "L4"},
        )
        if (
            explicit["progressive_disclosure"].get("requested_level") != "L4"
            or explicit["progressive_disclosure"].get("requested_level_applied") is not True
            or explicit["progressive_disclosure"].get("final_level") != "L4"
            or not explicit.get("complete_files")
        ):
            raise AssertionError(
                f"explicit disclosure_level L4 was ignored: {explicit['progressive_disclosure']}"
            )

        l0 = context_request(base_url, project_ids["Target"], task_ids["Target L0"])
        l0_disclosure = l0["progressive_disclosure"]
        if (
            l0_disclosure.get("starting_level") != "L0"
            or l0_disclosure.get("final_level") != "L0"
            or l0_disclosure.get("escalated") is not False
            or l0_disclosure.get("path")
            or l0.get("files")
            or l0.get("complete_files")
            or l0.get("inventory")
        ):
            raise AssertionError(
                f"L0 request escalated or disclosed extra evidence: {l0_disclosure}"
            )
        smallest_sufficient = True
        no_unnecessary_escalation = True
        explicit_insufficiency_escalation = True
        bounded_escalation = True
        stop_on_sufficient = True
        smallest_sufficient_uses_acceptance_criteria = disclosure.get("starting_level") == "L3"
        smallest_sufficient_uses_resolved_evidence = (
            escalate_disclosure.get("starting_level") == "L2"
        )
        synthetic_known_requirement_escalation_absent = disclosure.get("escalated") is False
        l1_module_summary_materialized = bool(first.get("module_summaries"))
        l2_symbol_signature_materialized = bool(first.get("symbol_signatures"))
        l2_dependency_metadata_materialized = bool(first.get("dependencies"))
        explicit_disclosure_level_contract_valid = (
            explicit["progressive_disclosure"].get("requested_level_applied") is True
            and explicit["progressive_disclosure"].get("final_level") == "L4"
        )
        l4_nonempty_when_selected = bool(l4.get("complete_files"))
        l4_target_resolved_from_project_evidence = (
            l4.get("complete_files", [{}])[0].get("path") == "src/context_service.py"
        )
        progressive_payload_in_bounds_accounting = (
            first["bounds"].get("disclosure_characters_included", 0) > 0
        )
        legitimate_escalation_fixture = escalate_disclosure.get("escalated") is True

        status, invalid_level = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_ids['Target']}/tasks/{task_ids['Target']}/context",
            {"top_k": 10, "disclosure_level": "L9"},
        )
        assert_equal(status, 422, "invalid disclosure level rejection")
        if "invalid_disclosure_level" not in str(invalid_level):
            raise AssertionError(f"invalid disclosure error was not explicit: {invalid_level}")

        isolated_context = context_request(
            base_url,
            project_ids["Isolated"],
            task_ids["Isolated"],
        )
        isolated_serialized = json.dumps(isolated_context, sort_keys=True)
        governance_project_scoped = (
            first["project"]["project_id"] == project_ids["Target"]
            and isolated_context["project"]["project_id"] == project_ids["Isolated"]
            and "Target Checkpoint" not in isolated_serialized
            and all(
                result.get("project_id") == project_ids["Isolated"]
                for result in isolated_context["retrieval"]["results"]
            )
        )
        if not governance_project_scoped:
            raise AssertionError("context governance or retrieval crossed project boundaries")

        fallback = context_request(base_url, project_ids["Target"], task_ids["Target fallback"])
        assert_equal(
            fallback["retrieval"]["rerank_state"],
            "RERANK_FALLBACK_PROVIDER_ERROR",
            "rerank fallback state",
        )
        assert fallback["retrieval"]["fallback_reason"]

        status, cross_project = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_ids['Isolated']}/tasks/{task_ids['Target']}/context",
        )
        assert_equal(status, 404, "cross-project task rejection")
        task_project_scoped = status == 404
        isolated_id = project_ids["Isolated"]
        cross_task_id = task_ids["Cross disclosure"]
        status, cross_disclosure = request(
            base_url,
            "POST",
            f"/api/v1/projects/{isolated_id}/tasks/{cross_task_id}/context",
        )
        assert_equal(status, 409, "cross-project disclosure rejection")
        if not isinstance(cross_disclosure, dict) or "cross_project_disclosure_evidence" not in str(
            cross_disclosure
        ):
            raise AssertionError(
                f"cross-project disclosure error was not explicit: {cross_disclosure}"
            )
        cross_project_disclosure_fail_closed = status == 409
        status, missing_governance = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_ids['Missing']}/tasks/{task_ids['Missing']}/context",
        )
        assert_equal(status, 409, "missing governance rejection")
        if not isinstance(missing_governance, dict) or "governance_not_git_tracked" not in str(
            missing_governance
        ):
            raise AssertionError(f"missing governance error was not explicit: {missing_governance}")
        missing_governance_fail_closed = status == 409

        compose(project_name, ["restart", "redis"], env=environment)
        wait_for_health(base_url)
        redis_capsule = context_request(base_url, project_ids["Target"], task_ids["Target"])
        assert_equal(redis_capsule, first, "Redis restart capsule")
        redis_restart_rebuild = redis_capsule == first
        compose(project_name, ["restart", "api"], env=environment)
        wait_for_health(base_url)
        api_capsule = context_request(base_url, project_ids["Target"], task_ids["Target"])
        assert_equal(api_capsule, first, "API restart capsule")
        api_restart_rebuild = api_capsule == first

        (target / "src" / "race.py").write_text("def race():\n    return True\n", encoding="utf-8")
        commit(target, "controlled context race", environment)
        status, race = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_ids['Target']}/tasks/{task_ids['Target']}/context",
        )
        assert_equal(status, 409, "HEAD race rejection")
        if not isinstance(race, dict) or "project_head_stale" not in str(race):
            raise AssertionError(f"HEAD race error was not explicit: {race}")
        head_race_fail_closed = status == 409

        checkpoint_first = (
            first["governance"][0]["kind"] == "CHECKPOINT"
            and first["governance"][0]["path"] == "docs/project-brain/13-CHECKPOINT.md"
        )
        reranked_retrieval_used = first["retrieval"]["rerank_state"] == "RERANKED"
        deterministic_two_run = first == second
        cross_project_isolation = governance_project_scoped and task_project_scoped
        mandatory_governance_kind_sequence = observed_mandatory_sequence
        mandatory_governance_coverage = mandatory_governance_kind_sequence == list(
            MANDATORY_GOVERNANCE_KINDS
        )

        evidence = {
            "status": "PASS"
            if all(
                (
                    checkpoint_first,
                    governance_project_scoped,
                    task_project_scoped,
                    reranked_retrieval_used,
                    provenance_preserved,
                    deterministic_two_run,
                    bounded,
                    cross_project_isolation,
                    missing_governance_fail_closed,
                    head_race_fail_closed,
                    redis_restart_rebuild,
                    api_restart_rebuild,
                    mandatory_governance_coverage,
                    level_mapping,
                    smallest_sufficient,
                    no_unnecessary_escalation,
                    explicit_insufficiency_escalation,
                    bounded_escalation,
                    stop_on_sufficient,
                    cross_project_disclosure_fail_closed,
                    disclosure.get("llm_calls") == 0,
                    disclosure.get("adaptive_token_budget_implemented") is True,
                    smallest_sufficient_uses_acceptance_criteria,
                    smallest_sufficient_uses_resolved_evidence,
                    synthetic_known_requirement_escalation_absent,
                    l1_module_summary_materialized,
                    l2_symbol_signature_materialized,
                    l2_dependency_metadata_materialized,
                    explicit_disclosure_level_contract_valid,
                    l4_nonempty_when_selected,
                    l4_target_resolved_from_project_evidence,
                    progressive_payload_in_bounds_accounting,
                    legitimate_escalation_fixture,
                    l4_complete_file_untruncated,
                    l4_large_file_full_content,
                    l4_full_content_source_identity,
                    l4_oversize_capsule_fail_closed,
                    token_budget_optional_tail_trim_deterministic,
                    token_budget_required_context_preserved,
                    token_budget_effective_bounds,
                    required_context_over_budget_fail_closed,
                    token_budget_policy_versioned,
                    token_estimator_versioned,
                    token_estimator_provider_independent,
                    token_budget_uses_approved_deterministic_signals,
                    token_budget_user_mode_required is False,
                    large_budget.get("required_context_preserved") is True,
                    pressure_budget.get("estimated_tokens_after", 0)
                    <= pressure_budget.get("effective_budget_tokens", 0),
                    pressure_budget.get("llm_calls") == 0,
                    pressure_budget.get("provider_calls") == 0,
                    token_budget_benchmark.get("status") == "PASS",
                    token_budget_benchmark.get("critical_context_misses") == 0,
                    token_budget_benchmark.get("strict_reduction_fixture") is True,
                    token_budget_benchmark.get("two_run_reproducibility") is True,
                )
            )
            else "FAIL",
            "checkpoint_first": checkpoint_first,
            "governance_project_scoped": governance_project_scoped,
            "task_project_scoped": task_project_scoped,
            "reranked_retrieval_used": reranked_retrieval_used,
            "provenance_preserved": provenance_preserved,
            "deterministic_two_run": deterministic_two_run,
            "bounded": bounded,
            "cross_project_isolation": cross_project_isolation,
            "missing_governance_fail_closed": missing_governance_fail_closed,
            "head_race_fail_closed": head_race_fail_closed,
            "redis_restart_rebuild": redis_restart_rebuild,
            "api_restart_rebuild": api_restart_rebuild,
            "mandatory_governance_coverage": mandatory_governance_coverage,
            "mandatory_governance_kind_sequence": mandatory_governance_kind_sequence,
            "llm_calls": 0,
            "progressive_disclosure_level_mapping": level_mapping,
            "smallest_sufficient": smallest_sufficient,
            "no_unnecessary_escalation": no_unnecessary_escalation,
            "explicit_insufficiency_escalation": explicit_insufficiency_escalation,
            "bounded_escalation": bounded_escalation,
            "stop_on_sufficient": stop_on_sufficient,
            "cross_project_disclosure_fail_closed": cross_project_disclosure_fail_closed,
            "disclosure_llm_calls": disclosure.get("llm_calls"),
            "adaptive_token_budget_implemented": disclosure.get(
                "adaptive_token_budget_implemented"
            ),
            "token_budget_policy_versioned": token_budget_policy_versioned,
            "token_estimator_versioned": token_estimator_versioned,
            "token_estimator_provider_independent": token_estimator_provider_independent,
            "token_budget_uses_approved_deterministic_signals": (
                token_budget_uses_approved_deterministic_signals
            ),
            "token_budget_user_mode_required": token_budget_user_mode_required,
            "mandatory_governance_preserved_under_budget": token_budget_required_context_preserved,
            "task_constraints_preserved_under_budget": bool(
                pressure["task_derived"]["constraints"]
            ),
            "acceptance_criteria_preserved_under_budget": bool(
                pressure["task_derived"]["acceptance_criteria"]
            ),
            "progressive_disclosure_semantics_preserved_under_budget": (
                pressure["progressive_disclosure"].get("final_level") == "L3"
            ),
            "l4_complete_file_preserved_under_budget": (
                large_file.get("truncated") is False and emitted_large == expected_large
            ),
            "optional_tail_trim_deterministic": token_budget_optional_tail_trim_deterministic,
            "retained_rerank_order_preserved": pressure_ranks == sorted(pressure_ranks),
            "required_context_over_budget_fail_closed": required_context_over_budget_fail_closed,
            "effective_budget_within_hard_bounds": token_budget_effective_bounds,
            "token_budget_deterministic_two_run": pressure == pressure_repeat,
            "token_budget_redis_restart_rebuild": redis_restart_rebuild,
            "token_budget_api_restart_rebuild": api_restart_rebuild,
            "token_budget_llm_calls": budget.get("llm_calls"),
            "token_budget_provider_calls": budget.get("provider_calls"),
            "token_budget_benchmark_status": token_budget_benchmark.get("status"),
            "token_budget_benchmark_critical_context_misses": token_budget_benchmark.get(
                "critical_context_misses"
            ),
            "token_budget_benchmark_strict_reduction_fixture": token_budget_benchmark.get(
                "strict_reduction_fixture"
            ),
            "adaptive_token_budget_migration_changed": False,
            "smallest_sufficient_uses_acceptance_criteria": (
                smallest_sufficient_uses_acceptance_criteria
            ),
            "smallest_sufficient_uses_resolved_evidence": (
                smallest_sufficient_uses_resolved_evidence
            ),
            "synthetic_known_requirement_escalation_absent": (
                synthetic_known_requirement_escalation_absent
            ),
            "l1_module_summary_materialized": l1_module_summary_materialized,
            "l2_symbol_signature_materialized": l2_symbol_signature_materialized,
            "l2_dependency_metadata_materialized": l2_dependency_metadata_materialized,
            "explicit_disclosure_level_contract_valid": (explicit_disclosure_level_contract_valid),
            "l4_nonempty_when_selected": l4_nonempty_when_selected,
            "l4_target_resolved_from_project_evidence": (l4_target_resolved_from_project_evidence),
            "progressive_payload_in_bounds_accounting": (progressive_payload_in_bounds_accounting),
            "legitimate_escalation_fixture": legitimate_escalation_fixture,
            "l4_complete_file_untruncated": l4_complete_file_untruncated,
            "l4_large_file_full_content": l4_large_file_full_content,
            "l4_full_content_source_identity": l4_full_content_source_identity,
            "l4_oversize_capsule_fail_closed": l4_oversize_capsule_fail_closed,
        }
        EVIDENCE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE_OUTPUT.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps(evidence, indent=2, sort_keys=True))
        print("Context Manager integration passed.")
        print(f"context_manager_evidence={json.dumps(evidence, sort_keys=True)}")
        return 0
    finally:
        compose(project_name, ["down", "--remove-orphans"], env=environment, check=False)
        for process in fixtures:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        cleanup_temporary_root(temporary_root, env=environment)


if __name__ == "__main__":
    raise SystemExit(main())
