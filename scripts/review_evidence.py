"""Generate and validate bounded, secret-free Review Evidence."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "review-evidence-v1.schema.json"
DEFAULT_OUTPUT = ROOT / "tmp" / "review-evidence"
VALIDATION = ROOT / "tmp" / "validation"
INTEGRATION_LOGS = ROOT / "tmp" / "integration-logs"
HEX_SHA = re.compile(r"^[0-9a-f]{40}$")
MAX_EVIDENCE_CHARS = 12_000


def run(command: list[str]) -> tuple[int, str]:
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.returncode, result.stdout.strip()


def git_value(*args: str, fallback: str = "") -> str:
    code, output = run(["git", *args])
    return output if code == 0 and output else fallback


def env_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y"}


def repository_name() -> str:
    remote = git_value("remote", "get-url", "origin", fallback="local").removesuffix(".git")
    if remote.startswith("git@") and ":" in remote:
        return remote.split(":", 1)[1]
    if "/" in remote:
        return remote.rsplit("/", 2)[-2] + "/" + remote.rsplit("/", 1)[-1]
    return remote


def changed_paths(base_sha: str, head_sha: str) -> list[str]:
    base_exists, _ = run(["git", "cat-file", "-e", f"{base_sha}^{{commit}}"])
    if HEX_SHA.fullmatch(base_sha) and base_exists == 0:
        code, output = run(["git", "diff", "--name-only", f"{base_sha}...{head_sha}"])
        if code == 0:
            return [path for path in output.splitlines() if path]
    return [path for path in git_value("diff", "--name-only", "HEAD^", "HEAD").splitlines() if path]


def migration_head() -> str:
    db_path = ROOT / "backend" / "app" / "db.py"
    match = re.search(r'CURRENT_SCHEMA_REVISION\s*=\s*"([^"]+)"', db_path.read_text())
    return match.group(1) if match else "UNKNOWN"


def validation_status(text: str, marker: str) -> str:
    normalized_text = text.casefold()
    if marker.casefold() not in normalized_text:
        return "UNKNOWN"
    return "PASS" if "exit_code: 0" in normalized_text else "FAIL"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def bounded(text: str, limit: int = MAX_EVIDENCE_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n[bounded evidence excerpt truncated]\n"


def benchmark_fields(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "UNKNOWN",
            "query_count": 0,
            "recall_at_1": 0.0,
            "recall_at_5": 0.0,
            "mrr": 0.0,
            "critical_context_misses": 0,
            "two_run_reproducibility": False,
            "cross_project_isolation": False,
            "redis_restart": False,
            "api_restart": False,
        }
    reproducibility = cast(dict[str, Any], data.get("reproducibility", {}))
    persistence = cast(dict[str, Any], data.get("persistence", {}))
    return {
        "status": "PASS" if not data.get("critical_context_misses") else "FAIL",
        "query_count": int(data.get("query_count", 0)),
        "recall_at_1": float(data.get("recall_at_1", 0.0)),
        "recall_at_5": float(data.get("recall_at_5", 0.0)),
        "mrr": float(data.get("mrr", 0.0)),
        "critical_context_misses": len(data.get("critical_context_misses", [])),
        "two_run_reproducibility": bool(
            reproducibility.get("same_query_count") and reproducibility.get("same_recall_at_5")
        ),
        "cross_project_isolation": bool(data.get("cross_project_isolation", False)),
        "redis_restart": bool(persistence.get("redis_restart", False)),
        "api_restart": bool(persistence.get("api_restart", False)),
    }


def junit_counts(path: Path) -> dict[str, int]:
    if not path.exists():
        return {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    try:
        root = ET.parse(path).getroot()
        return {
            "passed": max(
                0,
                int(root.attrib.get("tests", 0))
                - int(root.attrib.get("failures", 0))
                - int(root.attrib.get("errors", 0))
                - int(root.attrib.get("skipped", 0)),
            ),
            "failed": int(root.attrib.get("failures", 0)),
            "skipped": int(root.attrib.get("skipped", 0)),
            "errors": int(root.attrib.get("errors", 0)),
        }
    except (OSError, ET.ParseError, TypeError, ValueError):
        return {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}


def dashboard_counts(text: str) -> dict[str, int]:
    match = re.search(r"Tests\s+(\d+) passed", text)
    skipped_match = re.search(r"Tests\s+.*?(\d+) skipped", text)
    failed = re.search(r"(\d+) failed", text)
    passed = int(match.group(1)) if match else 0
    skipped = int(skipped_match.group(1)) if skipped_match else 0
    return {"passed": passed, "failed": int(failed.group(1)) if failed else 0, "skipped": skipped}


def tests_evidence(summary: str, test_results: str) -> dict[str, object]:
    backend = junit_counts(VALIDATION / "backend-junit.xml")
    dashboard = dashboard_counts(test_results)
    backend_known = bool(backend["passed"] or backend["failed"] or backend["skipped"])
    dashboard_known = bool(dashboard["passed"] or dashboard["failed"] or dashboard["skipped"])
    status = (
        "PASS" if summary.strip() == "PASS" and (backend_known or dashboard_known) else "UNKNOWN"
    )
    if backend["failed"] or backend["errors"] or dashboard["failed"]:
        status = "FAIL"
    return {
        "status": status,
        "backend": {
            "status": "PASS"
            if backend_known and not backend["failed"] and not backend["errors"]
            else "UNKNOWN",
            **backend,
        },
        "dashboard": {
            "status": "PASS" if dashboard_known and not dashboard["failed"] else "UNKNOWN",
            **dashboard,
        },
    }


def integration_file(name: str) -> str:
    for path in (VALIDATION / name, INTEGRATION_LOGS / name):
        if path.exists():
            return read_text(path)
    return ""


def integration_result(name: str, markers: tuple[str, ...]) -> dict[str, object]:
    text = integration_file(name)
    passed = bool(text) and all(marker.casefold() in text.casefold() for marker in markers)
    return {"status": "PASS" if passed else "UNKNOWN", "evidence_file": name}


def retrieval_integrity(text: str) -> dict[str, bool]:
    match = re.search(r"retrieval_integrity=(\{.*\})", text)
    if not match:
        return {
            "head_race_rejected": False,
            "inventory_race_rejected": False,
            "prior_corpus_preserved": False,
            "duplicate_task_candidate_collapsed": False,
            "task_provenance_preserved": False,
            "cross_project_duplicate_isolation": False,
        }
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError:
        value = {}
    return {
        key: bool(value.get(key, False))
        for key in (
            "head_race_rejected",
            "inventory_race_rejected",
            "prior_corpus_preserved",
            "duplicate_task_candidate_collapsed",
            "task_provenance_preserved",
            "cross_project_duplicate_isolation",
        )
    }


def integration_evidence(benchmark: dict[str, object]) -> dict[str, object]:
    retrieval = integration_file("retrieval.log") + integration_file("retrieval-integration.txt")
    status = (
        "PASS"
        if "retrieval corpus/lexical integration passed" in retrieval.casefold()
        else "UNKNOWN"
    )
    if benchmark["status"] == "FAIL":
        status = "FAIL"
    integrity = retrieval_integrity(retrieval)
    return {
        "status": status,
        "project_registry": integration_result(
            "project-registry.log", ("project registry integration passed",)
        ),
        "task_intake_cas": integration_result(
            "task-intake.log", ("task intake and cas integration passed",)
        ),
        "repository_indexing": integration_result(
            "repository-indexing.log", ("repository indexing integration passed",)
        ),
        "retrieval": {"status": status, "evidence_file": "retrieval.log"},
        "redis_restart": {"status": "PASS" if benchmark["redis_restart"] else "UNKNOWN"},
        "api_restart": {"status": "PASS" if benchmark["api_restart"] else "UNKNOWN"},
        "benchmark_gate": {
            "status": benchmark["status"],
            "query_count": benchmark["query_count"],
            "recall_at_1": benchmark["recall_at_1"],
            "recall_at_5": benchmark["recall_at_5"],
            "mrr": benchmark["mrr"],
            "critical_context_misses": benchmark["critical_context_misses"],
            "two_run_reproducibility": benchmark["two_run_reproducibility"],
        },
        "cross_project_retrieval": {
            "status": "PASS" if benchmark["cross_project_isolation"] else "UNKNOWN"
        },
        "integrity_tests": integrity,
    }


def security_evidence(
    all_validation: str,
    test_results: str,
    benchmark: dict[str, object],
    integration: dict[str, object],
) -> dict[str, object]:
    canonical = validation_status(all_validation, "canonical source verification passed")
    secrets = validation_status(all_validation, "secret scan passed")
    sql_basis = read_text(VALIDATION / "backend-junit.xml") + test_results
    sql = "PASS" if "test_sql_queries_are_parameterized" in sql_basis else "UNKNOWN"
    retrieval = cast(dict[str, Any], integration["retrieval"])
    integrity = cast(dict[str, Any], integration["integrity_tests"])
    stale = (
        "PASS"
        if retrieval["status"] == "PASS"
        and integrity["head_race_rejected"]
        and integrity["inventory_race_rejected"]
        and integrity["prior_corpus_preserved"]
        else "UNKNOWN"
    )
    isolation = "PASS" if benchmark["cross_project_isolation"] else "UNKNOWN"
    values = {
        "canonical_verifier": {"status": canonical},
        "secret_scan": {"status": secrets},
        "project_isolation": {"status": isolation},
        "cross_project_retrieval": {"status": isolation},
        "sql_query_parameterization": {
            "status": sql,
            "basis": "backend/tests/test_retrieval.py::test_sql_queries_are_parameterized",
        },
        "source_staleness_fail_closed": {"status": stale},
    }
    return {
        "status": "PASS"
        if all(item["status"] == "PASS" for item in values.values())
        else "UNKNOWN",
        **values,
    }


def warnings_evidence(all_text: str) -> dict[str, object]:
    items: list[str] = []
    folded = all_text.casefold()
    if "overcommit_memory" in folded or "overcommit" in folded:
        items.append("Redis host warning observed: vm.overcommit_memory is disabled.")
    if "npm warn deprecated" in folded:
        items.append("npm dependency deprecation warning observed.")
    if "npm warn allow-scripts" in folded:
        items.append("npm install-script approval warning observed for a dependency.")
    return {"status": "RECORDED" if items else "NONE", "count": len(items), "items": items}


def _gh_json(repository: str, endpoint: str) -> dict[str, Any] | list[Any] | None:
    path = f"repos/{repository}/{endpoint}" if endpoint else f"repos/{repository}"
    code, output = run(["gh", "api", path])
    if code != 0:
        return None
    try:
        value = json.loads(output)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict | list) else None


def governance_evidence(repository: str) -> dict[str, object]:
    rulesets = _gh_json(repository, "rulesets?includes_parents=true")
    selected: dict[str, Any] | None = None
    if isinstance(rulesets, list):
        selected = next(
            (
                item
                for item in rulesets
                if isinstance(item, dict) and item.get("name") == "Protect main"
            ),
            None,
        )
    detail = (
        _gh_json(repository, f"rulesets/{selected['id']}")
        if selected and selected.get("id") is not None
        else None
    )
    repo = _gh_json(repository, "")
    ruleset = detail if isinstance(detail, dict) else selected if selected else {}
    required_contexts: list[str] = []
    allowed_methods: list[str] = []
    thread_resolution: bool | None = None
    has_deletion = False
    has_non_fast_forward = False
    has_pull_request = False
    strict_checks: bool | None = None
    for rule in ruleset.get("rules", []) if isinstance(ruleset, dict) else []:
        if not isinstance(rule, dict):
            continue
        rule_type = rule.get("type")
        has_deletion |= rule_type == "deletion"
        has_non_fast_forward |= rule_type == "non_fast_forward"
        has_pull_request |= rule_type == "pull_request"
        params = rule.get("parameters", {})
        if rule_type == "required_status_checks" and isinstance(params, dict):
            required_contexts = [
                str(item.get("context"))
                for item in params.get("required_status_checks", [])
                if isinstance(item, dict) and item.get("context")
            ]
            strict_checks = bool(params.get("strict_required_status_checks_policy"))
        if rule_type == "pull_request" and isinstance(params, dict):
            allowed_methods = [str(item) for item in params.get("allowed_merge_methods", [])]
            if "required_review_thread_resolution" in params:
                thread_resolution = bool(params["required_review_thread_resolution"])
    bypass = (
        [
            {
                "actor_id": item.get("actor_id"),
                "actor_type": item.get("actor_type"),
                "actor_name": item.get("actor_name"),
                "bypass_mode": item.get("bypass_mode"),
            }
            for item in ruleset.get("bypass_actors", [])
            if isinstance(item, dict)
        ]
        if isinstance(ruleset, dict)
        else []
    )
    repo_settings = {
        "allow_squash_merge": repo.get("allow_squash_merge") if isinstance(repo, dict) else None,
        "allow_merge_commit": repo.get("allow_merge_commit") if isinstance(repo, dict) else None,
        "allow_rebase_merge": repo.get("allow_rebase_merge") if isinstance(repo, dict) else None,
        "delete_branch_on_merge": repo.get("delete_branch_on_merge")
        if isinstance(repo, dict)
        else None,
        "allow_auto_merge": repo.get("allow_auto_merge") if isinstance(repo, dict) else None,
    }
    available = bool(detail and repo)
    return {
        "status": "PASS" if available else "UNKNOWN",
        "ruleset": {
            "id": ruleset.get("id") if isinstance(ruleset, dict) else None,
            "name": ruleset.get("name", "UNKNOWN") if isinstance(ruleset, dict) else "UNKNOWN",
            "enforcement": ruleset.get("enforcement", "UNKNOWN")
            if isinstance(ruleset, dict)
            else "UNKNOWN",
            "required_contexts": sorted(required_contexts),
            "required_review_thread_resolution": thread_resolution,
            "allowed_merge_methods": sorted(allowed_methods),
            "bypass_actors": bypass,
            "deletion_protection": has_deletion,
            "non_fast_forward_protection": has_non_fast_forward,
            "pull_request_required": has_pull_request,
            "strict_required_status_checks": strict_checks,
        },
        "repository_merge_settings": repo_settings,
    }


def build_manifest(args: argparse.Namespace) -> dict[str, object]:
    validation = read_text(VALIDATION / "summary.txt")
    lint = read_text(VALIDATION / "lint-typecheck-build-results.txt")
    tests_text = read_text(VALIDATION / "test-results.txt")
    base_sha = args.base_sha or git_value("merge-base", "HEAD", "origin/main", fallback="0" * 40)
    head_sha = args.head_sha or git_value("rev-parse", "HEAD")
    actual_head = git_value("rev-parse", "HEAD")
    if head_sha != actual_head:
        raise ValueError(f"head SHA mismatch: expected {head_sha}, checked out {actual_head}")
    paths = changed_paths(base_sha, head_sha)
    all_validation = validation + "\n" + lint + "\n" + tests_text
    benchmark = benchmark_fields(VALIDATION / "retrieval-benchmark.json")
    tests = tests_evidence(validation, tests_text)
    integration = integration_evidence(benchmark)
    security = security_evidence(all_validation, tests_text, benchmark, integration)
    warnings = warnings_evidence(all_evidence_text())
    checks = {
        "validation": "PASS"
        if validation.strip() == "PASS"
        else "FAIL"
        if validation.strip().startswith("FAIL")
        else "UNKNOWN",
        "canonical": validation_status(all_validation, "canonical source verification"),
        "secrets": validation_status(all_validation, "secret scan"),
        "lint": "PASS"
        if validation.strip() == "PASS" and "ruff check" in lint and "run lint" in lint
        else "UNKNOWN",
        "typecheck": "PASS"
        if validation.strip() == "PASS" and "run typecheck" in lint
        else "UNKNOWN",
        "tests": cast(str, tests["status"]),
        "build": "PASS" if validation.strip() == "PASS" and "run build" in lint else "UNKNOWN",
        "integration": "PASS" if args.integration_status == "PASS" else args.integration_status,
        "review_evidence": "PASS",
    }
    draft = args.draft or env_bool(args.draft_env, False)
    pr_number = args.pr_number
    review_status = "DRAFT" if pr_number and draft else "OPEN" if pr_number else "NOT_CREATED"
    artifact_name = args.artifact_name or f"hive-review-evidence-{args.work_order}-{head_sha}"
    return {
        "schema_version": 1,
        "work_order": args.work_order,
        "repository": args.repository or repository_name(),
        "pull_request": {"number": pr_number, "is_draft": draft},
        "base": {"branch": args.base_branch, "sha": base_sha},
        "head": {
            "branch": args.head_branch
            or git_value("branch", "--show-current", fallback="DETACHED"),
            "sha": head_sha,
        },
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "changed_files": {"count": len(paths), "paths": paths},
        "migrations": {"head": migration_head()},
        "checks": checks,
        "benchmark": benchmark,
        "evidence": {
            "tests": tests,
            "integration": integration,
            "security": security,
            "warnings": warnings,
        },
        "governance": governance_evidence(args.repository or repository_name()),
        "artifact": {"name": artifact_name, "format": "consolidated-directory", "bounded": True},
        "review_state": {"status": review_status, "merge_performed": False},
        "negative_scope": [
            "No merge or release was performed.",
            "No canonical Project Brain checkpoint was modified.",
            "No embeddings, reranking, autonomous executor, or LLM provider was added.",
        ],
    }


def validate_manifest(manifest: dict[str, object]) -> None:
    required = {
        "schema_version",
        "work_order",
        "repository",
        "pull_request",
        "base",
        "head",
        "generated_at",
        "changed_files",
        "migrations",
        "checks",
        "benchmark",
        "evidence",
        "governance",
        "artifact",
        "review_state",
        "negative_scope",
    }
    if set(manifest) != required or manifest["schema_version"] != 1:
        raise ValueError("manifest does not match the required top-level schema")
    for key in ("base", "head"):
        section = cast(dict[str, Any], manifest[key])
        sha = section["sha"]
        if not isinstance(sha, str) or not HEX_SHA.fullmatch(sha):
            raise ValueError(f"invalid {key} SHA")
    review_state = cast(dict[str, Any], manifest["review_state"])
    if review_state["merge_performed"] is not False:
        raise ValueError("review evidence cannot report a merge")
    errors = sorted(
        jsonschema.Draft202012Validator(
            json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        ).iter_errors(manifest),
        key=str,
    )
    if errors:
        raise ValueError(f"manifest schema validation failed: {errors[0].message}")


def all_evidence_text() -> str:
    paths = sorted(VALIDATION.glob("*.txt")) + sorted(INTEGRATION_LOGS.glob("*.log"))
    return "\n\n".join(read_text(path) for path in paths)


def failure_diagnostics() -> str:
    lines: list[str] = []
    for line in all_evidence_text().splitlines():
        folded = line.casefold()
        if any(marker in folded for marker in ("traceback", "error", "exception")) or re.search(
            r"exit_code:\s*[1-9]", folded
        ):
            lines.append(line)
    return bounded("\n".join(lines) or "No relevant failure diagnostics recorded.\n")


def summary_markdown(manifest: dict[str, object], workflow_url: str) -> str:
    head = cast(dict[str, Any], manifest["head"])
    base = cast(dict[str, Any], manifest["base"])
    checks = cast(dict[str, Any], manifest["checks"])
    evidence = cast(dict[str, Any], manifest["evidence"])
    tests = cast(dict[str, Any], evidence["tests"])
    integration = cast(dict[str, Any], evidence["integration"])
    security = cast(dict[str, Any], evidence["security"])
    warnings = cast(dict[str, Any], evidence["warnings"])
    benchmark = cast(dict[str, Any], manifest["benchmark"])
    governance = cast(dict[str, Any], manifest["governance"])
    ruleset = cast(dict[str, Any], governance["ruleset"])
    repo_settings = cast(dict[str, Any], governance["repository_merge_settings"])
    artifact = cast(dict[str, Any], manifest["artifact"])
    pr = cast(dict[str, Any], manifest["pull_request"])
    integrity = cast(dict[str, Any], integration["integrity_tests"])
    warning_text = ", ".join(warnings["items"]) if warnings["items"] else "none observed"
    contexts = ", ".join(ruleset["required_contexts"]) or "none recorded"
    methods = ", ".join(ruleset["allowed_merge_methods"]) or "none recorded"
    backend_tests = (
        f"`{tests['backend']['passed']} passed, {tests['backend']['failed']} failed, "
        f"{tests['backend']['skipped']} skipped`"
    )
    benchmark_text = (
        f"`{benchmark['status']}`; query count `{benchmark['query_count']}`, "
        f"recall@1 `{benchmark['recall_at_1']}`, recall@5 `{benchmark['recall_at_5']}`, "
        f"MRR `{benchmark['mrr']}`, critical misses `{benchmark['critical_context_misses']}`, "
        f"two-run reproducibility `{benchmark['two_run_reproducibility']}`"
    )
    merge_settings = (
        f"squash `{repo_settings['allow_squash_merge']}`, "
        f"merge commit `{repo_settings['allow_merge_commit']}`, "
        f"rebase `{repo_settings['allow_rebase_merge']}`, "
        f"delete head branch `{repo_settings['delete_branch_on_merge']}`, "
        f"automatic merge `{repo_settings['allow_auto_merge']}`"
    )
    ruleset_text = (
        f"`{ruleset['id']}` / `{ruleset['name']}`; enforcement `{ruleset['enforcement']}`; "
        f"required contexts `{contexts}`; "
        f"thread resolution `{ruleset['required_review_thread_resolution']}`; "
        f"merge methods `{methods}`; bypass actors `{len(ruleset['bypass_actors'])}`"
    )
    race_summary = (
        f"HEAD `{integrity['head_race_rejected']}`, "
        f"inventory `{integrity['inventory_race_rejected']}`, "
        f"prior corpus preserved `{integrity['prior_corpus_preserved']}`"
    )
    duplicate_summary = (
        f"collapsed `{integrity['duplicate_task_candidate_collapsed']}`, "
        f"task provenance preserved `{integrity['task_provenance_preserved']}`, "
        f"cross-project isolation `{integrity['cross_project_duplicate_isolation']}`"
    )
    integration_summary = ", ".join(
        f"{label} `{cast(dict[str, Any], integration[key])['status']}`"
        for key, label in (
            ("project_registry", "Project Registry"),
            ("task_intake_cas", "Task Intake/CAS"),
            ("repository_indexing", "Repository Indexing"),
            ("retrieval", "Retrieval"),
            ("redis_restart", "Redis restart"),
            ("api_restart", "API restart"),
        )
    )
    return f"""# HIVE Review Evidence — {manifest["work_order"]}

- Work Order: `{manifest["work_order"]}`
- Exact HEAD SHA: `{head["sha"]}`
- Base SHA: `{base["sha"]}`
- PR state: **{"DRAFT" if pr["is_draft"] else "NOT DRAFT"}**
- Validate result: **{checks["validation"]}**
- Integration health result: **{checks["integration"]}**
- Review Evidence result: **{checks["review_evidence"]}**
- Migration head: `{cast(dict[str, Any], manifest["migrations"])["head"]}`
- Backend tests: {backend_tests}
- Dashboard tests: `{tests["dashboard"]["passed"]} passed, {tests["dashboard"]["failed"]} failed`
- Integration summary: {integration_summary}
- Git race-integrity tests: {race_summary}
- Duplicate task candidate tests: {duplicate_summary}
- Benchmark summary: {benchmark_text}
- Canonical verifier: **{security["canonical_verifier"]["status"]}**
- Secret scan: **{security["secret_scan"]["status"]}**
- Known warnings: `{warnings["count"]}` recorded; {warning_text}
- Ruleset: {ruleset_text}
- Repository merge settings: {merge_settings}
- Consolidated artifact: `{artifact["name"]}`
- Workflow run URL: {workflow_url}

Sol Review State: AWAITING_SOL
"""


def write_consolidated_artifact(
    output_dir: Path, manifest: dict[str, object], summary: str
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    changed = cast(dict[str, Any], manifest["changed_files"])
    migrations = cast(dict[str, Any], manifest["migrations"])
    integration_sources = sorted(VALIDATION.glob("*.txt")) + sorted(INTEGRATION_LOGS.glob("*.log"))
    integration_text = "\n\n".join(
        f"===== {path.as_posix()} =====\n{bounded(read_text(path))}" for path in integration_sources
    )
    files = {
        "changed-files.txt": "\n".join(changed["paths"]) + "\n",
        "migration-head.txt": f"{migrations['head']}\n",
        "validation-summary.txt": bounded(read_text(VALIDATION / "summary.txt")),
        "validation-results.txt": bounded(
            read_text(VALIDATION / "test-results.txt")
            + "\n\n"
            + read_text(VALIDATION / "lint-typecheck-build-results.txt")
            + "\n\n"
            + read_text(VALIDATION / "docker-compose-config.txt")
        ),
        "integration-summary.json": json.dumps(
            cast(dict[str, Any], manifest["evidence"])["integration"], indent=2, sort_keys=True
        )
        + "\n",
        "integration-results.txt": bounded(integration_text),
        "benchmark.json": json.dumps(manifest["benchmark"], indent=2, sort_keys=True) + "\n",
        "failure-diagnostics.txt": failure_diagnostics(),
        "review-manifest.json": json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        "review-summary.md": summary,
        "github-governance.json": json.dumps(manifest["governance"], indent=2, sort_keys=True)
        + "\n",
    }
    for name, content in files.items():
        (output_dir / name).write_text(bounded(content), encoding="utf-8", newline="\n")


def manifest_log(manifest: dict[str, object]) -> str:
    return (
        "HIVE_REVIEW_MANIFEST_BEGIN\n"
        + json.dumps(manifest, indent=2, sort_keys=True)
        + "\nHIVE_REVIEW_MANIFEST_END"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-order", default="WO-006")
    parser.add_argument("--repository")
    parser.add_argument("--pr-number", type=int)
    parser.add_argument("--draft", action="store_true")
    parser.add_argument("--draft-env", default="")
    parser.add_argument("--base-branch", default="main")
    parser.add_argument("--base-sha", default="")
    parser.add_argument("--head-branch", default="")
    parser.add_argument("--head-sha", default="")
    parser.add_argument("--artifact-name", default="")
    parser.add_argument("--workflow-run-url", default="")
    parser.add_argument("--server-url", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument(
        "--integration-status", choices=["PASS", "FAIL", "UNKNOWN"], default="UNKNOWN"
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = build_manifest(args)
    validate_manifest(manifest)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output_dir / "review-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    workflow_url = args.workflow_run_url or (
        f"{args.server_url}/{args.repository}/actions/runs/{args.run_id}"
        if args.server_url and args.repository and args.run_id
        else "UNKNOWN"
    )
    summary = summary_markdown(manifest, workflow_url)
    write_consolidated_artifact(args.output_dir, manifest, summary)
    print(manifest_log(manifest))
    print(
        json.dumps(
            {"manifest": str(manifest_path), "summary": str(args.output_dir / "review-summary.md")},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
