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
WORK_ORDER_IDENTIFIER = re.compile(r"WO-[0-9]+(?:-[A-Z0-9]+)*")
WORK_ORDER_MARKER = re.compile(r"<!--\s*HIVE-WORK-ORDER:\s*([^<>\r\n]+?)\s*-->", re.IGNORECASE)
CHECKPOINT_PATH = "docs/project-brain/13-CHECKPOINT.md"
CANONICAL_PATHS = (
    CHECKPOINT_PATH,
    "docs/project-brain/CANONICAL-SHA256SUMS.txt",
)

WARNING_RULES = (
    (
        re.compile(r"(?:vm\.overcommit_memory|memory overcommit|overcommit_memory)", re.I),
        "Redis host warning observed: vm.overcommit_memory is disabled.",
    ),
    (
        re.compile(r"\bnpm\s+(?:warn|warning)\s+deprecated\b", re.I),
        "npm dependency deprecation warning observed.",
    ),
    (
        re.compile(
            r"(?:node(?:\.js)?\s+20\s+is\s+(?:being\s+)?deprecated|"
            r"target\s+node(?:\.js)?\s+20\b)",
            re.I,
        ),
        "GitHub Actions Node runtime deprecation warning observed.",
    ),
    (
        re.compile(r"\bnpm\s+(?:warn|warning)\s+allow-scripts\b", re.I),
        "npm install-script approval warning observed for a dependency.",
    ),
)


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


def parse_work_order_marker(body: str) -> str:
    markers = WORK_ORDER_MARKER.findall(body)
    if len(markers) != 1:
        if not markers:
            raise ValueError("HIVE work-order PR is missing exactly one work-order marker")
        raise ValueError("HIVE work-order PR has multiple conflicting work-order markers")
    work_order = str(markers[0]).strip()
    if len(work_order) > 64 or WORK_ORDER_IDENTIFIER.fullmatch(work_order) is None:
        raise ValueError(f"invalid or unbounded HIVE work-order identifier: {work_order!r}")
    return work_order


def derive_work_order(repository: str, pr_number: int) -> str:
    pr = _gh_json(repository, f"pulls/{pr_number}")
    if not isinstance(pr, dict):
        raise ValueError(f"unable to read pull request #{pr_number} for work-order derivation")
    body = pr.get("body")
    if not isinstance(body, str):
        body = ""
    return parse_work_order_marker(body)


def canonical_change_evidence(paths: list[str]) -> dict[str, object]:
    changed = set(paths)
    project_brain_changed = any(
        path == "docs/project-brain" or path.startswith("docs/project-brain/") for path in changed
    )
    return {
        "project_brain_changed": project_brain_changed,
        "checkpoint_changed": CHECKPOINT_PATH in changed,
        "authorized_paths": [path for path in CANONICAL_PATHS if path in changed],
    }


def canonical_change_statement(evidence: dict[str, object]) -> str:
    payload = json.dumps(evidence, sort_keys=True, separators=(",", ":"))
    return f"Canonical change evidence: {payload}"


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
    unknown_slice = {
        "status": "UNKNOWN",
        "query_count": 0,
        "recall_at_1": 0.0,
        "recall_at_5": 0.0,
        "mrr": 0.0,
        "critical_context_misses": 0,
        "two_run_reproducibility": False,
    }
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
            "semantic": unknown_slice,
            "hybrid": unknown_slice,
            "semantic_integrity": {},
            "fallback": {},
            "hybrid_recall_at_5_gte_extended_lexical": False,
            "semantic_challenge_recovered": False,
        }
    reproducibility = cast(dict[str, Any], data.get("reproducibility", {}))
    persistence = cast(dict[str, Any], data.get("persistence", {}))
    semantic = cast(dict[str, Any], data.get("semantic", {}))
    hybrid = cast(dict[str, Any], data.get("hybrid", {}))
    semantic_run = cast(dict[str, Any], semantic.get("run_1", {}))
    hybrid_run = cast(dict[str, Any], hybrid.get("run_1", {}))
    semantic_status = (
        "PASS"
        if semantic_run and not semantic_run.get("critical_context_misses")
        else "FAIL"
        if semantic_run
        else "UNKNOWN"
    )
    hybrid_status = (
        "PASS"
        if hybrid_run and not hybrid_run.get("critical_context_misses")
        else "FAIL"
        if hybrid_run
        else "UNKNOWN"
    )
    overall_status = "PASS" if not data.get("critical_context_misses") else "FAIL"
    if semantic_status == "FAIL" or hybrid_status == "FAIL":
        overall_status = "FAIL"
    return {
        "status": overall_status,
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
        "semantic": {
            "status": semantic_status if semantic else "UNKNOWN",
            "query_count": int(semantic_run.get("query_count", 0)),
            "recall_at_1": float(semantic_run.get("recall_at_1", 0.0)),
            "recall_at_5": float(semantic_run.get("recall_at_5", 0.0)),
            "mrr": float(semantic_run.get("mrr", 0.0)),
            "critical_context_misses": len(semantic_run.get("critical_context_misses", [])),
            "two_run_reproducibility": bool(
                semantic.get("run_1", {}).get("recall_at_5")
                == semantic.get("run_2", {}).get("recall_at_5")
            ),
        },
        "hybrid": {
            "status": hybrid_status if hybrid else "UNKNOWN",
            "query_count": int(hybrid_run.get("query_count", 0)),
            "recall_at_1": float(hybrid_run.get("recall_at_1", 0.0)),
            "recall_at_5": float(hybrid_run.get("recall_at_5", 0.0)),
            "mrr": float(hybrid_run.get("mrr", 0.0)),
            "critical_context_misses": len(hybrid_run.get("critical_context_misses", [])),
            "two_run_reproducibility": bool(
                hybrid.get("run_1", {}).get("recall_at_5")
                == hybrid.get("run_2", {}).get("recall_at_5")
            ),
        },
        "semantic_integrity": data.get("semantic_integrity", {}),
        "fallback": data.get("fallback", {}),
        "hybrid_recall_at_5_gte_extended_lexical": bool(
            data.get("thresholds", {}).get("hybrid_recall_at_5_gte_extended_lexical", False)
        ),
        "semantic_challenge_recovered": bool(
            data.get("thresholds", {}).get("semantic_challenge_recovered", False)
        ),
    }


def junit_counts(path: Path) -> dict[str, int]:
    if not path.exists():
        return {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    try:
        root = ET.parse(path).getroot()
        suites = [root] if "tests" in root.attrib else list(root.iter("testsuite"))
        if not suites:
            return {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
        tests = sum(int(suite.attrib.get("tests", 0)) for suite in suites)
        failures = sum(int(suite.attrib.get("failures", 0)) for suite in suites)
        errors = sum(int(suite.attrib.get("errors", 0)) for suite in suites)
        skipped = sum(int(suite.attrib.get("skipped", 0)) for suite in suites)
        return {
            "passed": max(0, tests - failures - errors - skipped),
            "failed": failures,
            "skipped": skipped,
            "errors": errors,
        }
    except (OSError, ET.ParseError, TypeError, ValueError):
        return {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}


def dashboard_counts(text: str) -> dict[str, int]:
    plain_text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    match = re.search(r"Tests\s+(\d+) passed", plain_text)
    skipped_match = re.search(r"Tests\s+.*?(\d+) skipped", plain_text)
    failed = re.search(r"(\d+) failed", plain_text)
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
            "semantic_challenge_recovered": False,
            "hybrid_fallback_provider_error": False,
            "hybrid_fallback_stale": False,
            "semantic_project_isolation": False,
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
            "semantic_challenge_recovered",
            "hybrid_fallback_provider_error",
            "hybrid_fallback_stale",
            "semantic_project_isolation",
        )
    }


def integration_evidence(benchmark: dict[str, object]) -> dict[str, object]:
    retrieval = integration_file("retrieval.log") + integration_file("retrieval-integration.txt")
    status = (
        "PASS"
        if "retrieval corpus/lexical" in retrieval.casefold()
        and "integration passed" in retrieval.casefold()
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
        "semantic_hybrid": {
            "status": "PASS"
            if cast(dict[str, Any], benchmark["semantic"])["status"] == "PASS"
            and cast(dict[str, Any], benchmark["hybrid"])["status"] == "PASS"
            and benchmark["hybrid_recall_at_5_gte_extended_lexical"]
            and benchmark["semantic_challenge_recovered"]
            else "UNKNOWN",
            "semantic": benchmark["semantic"],
            "hybrid": benchmark["hybrid"],
            "semantic_integrity": benchmark["semantic_integrity"],
            "fallback": benchmark["fallback"],
        },
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
    items = [message for pattern, message in WARNING_RULES if pattern.search(all_text)]
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


def governance_evidence(repository: str, pr_number: int | None = None) -> dict[str, object]:
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
    required_approving_review_count: int | None = None
    dismiss_stale_reviews_on_push: bool | None = None
    require_last_push_approval: bool | None = None
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
            if "required_approving_review_count" in params:
                required_approving_review_count = int(params["required_approving_review_count"])
            if "dismiss_stale_reviews_on_push" in params:
                dismiss_stale_reviews_on_push = bool(params["dismiss_stale_reviews_on_push"])
            if "require_last_push_approval" in params:
                require_last_push_approval = bool(params["require_last_push_approval"])
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
    if any(value is None for value in repo_settings.values()):
        code, output = run(
            [
                "gh",
                "repo",
                "view",
                repository,
                "--json",
                "mergeCommitAllowed,rebaseMergeAllowed,squashMergeAllowed,deleteBranchOnMerge",
            ]
        )
        if code == 0:
            try:
                graphql_settings = json.loads(output)
            except json.JSONDecodeError:
                graphql_settings = {}
            fallback_settings = {
                "allow_squash_merge": graphql_settings.get("squashMergeAllowed"),
                "allow_merge_commit": graphql_settings.get("mergeCommitAllowed"),
                "allow_rebase_merge": graphql_settings.get("rebaseMergeAllowed"),
                "delete_branch_on_merge": graphql_settings.get("deleteBranchOnMerge"),
            }
            for key, value in fallback_settings.items():
                if repo_settings[key] is None and value is not None:
                    repo_settings[key] = value
    available = bool(detail and repo)
    pr = _gh_json(repository, f"pulls/{pr_number}") if pr_number else None
    reviews = _gh_json(repository, f"pulls/{pr_number}/reviews") if pr_number else None
    author = cast(dict[str, Any], pr.get("user", {})).get("login") if isinstance(pr, dict) else None
    latest_review_by_user: dict[str, dict[str, Any]] = {}
    if isinstance(reviews, list):
        for review in reviews:
            if not isinstance(review, dict):
                continue
            user = review.get("user", {})
            login = user.get("login") if isinstance(user, dict) else None
            if not isinstance(login, str):
                continue
            previous = latest_review_by_user.get(login)
            if previous is None or str(review.get("submitted_at", "")) >= str(
                previous.get("submitted_at", "")
            ):
                latest_review_by_user[login] = review
    independent_approvers = sorted(
        login
        for login, review in latest_review_by_user.items()
        if login != author and review.get("state") == "APPROVED"
    )
    sol_permission = _gh_json(repository, "collaborators/kayzenweb3/permission")
    sol_permissions = (
        sol_permission.get("permissions", {}) if isinstance(sol_permission, dict) else {}
    )
    sol_eligible = bool(
        isinstance(sol_permission, dict)
        and sol_permission.get("permission") in {"write", "triage", "maintain", "admin"}
    )
    auto_merge = (
        pr.get("auto_merge")
        if isinstance(pr, dict) and isinstance(pr.get("auto_merge"), dict)
        else None
    )
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
            "required_approving_review_count": required_approving_review_count,
            "dismiss_stale_reviews_on_push": dismiss_stale_reviews_on_push,
            "require_last_push_approval": require_last_push_approval,
        },
        "repository_merge_settings": repo_settings,
        "pull_request": {
            "number": pr_number,
            "state": pr.get("state") if isinstance(pr, dict) else None,
            "is_draft": pr.get("draft") if isinstance(pr, dict) else None,
            "head_sha": (
                pr.get("head", {}).get("sha")
                if isinstance(pr, dict) and isinstance(pr.get("head"), dict)
                else None
            ),
            "base_sha": (
                pr.get("base", {}).get("sha")
                if isinstance(pr, dict) and isinstance(pr.get("base"), dict)
                else None
            ),
            "auto_merge_armed": auto_merge is not None,
            "auto_merge_method": auto_merge.get("merge_method") if auto_merge else None,
        },
        "approval_gate": {
            "required_approving_review_count": required_approving_review_count,
            "dismiss_stale_reviews_on_push": dismiss_stale_reviews_on_push,
            "require_last_push_approval": require_last_push_approval,
            "independent_approvers": independent_approvers,
            "independent_approval_count": len(independent_approvers),
        },
        "sol_reviewer": {
            "login": "kayzenweb3",
            "permission": (
                sol_permission.get("permission") if isinstance(sol_permission, dict) else None
            ),
            "permissions": sol_permissions,
            "can_satisfy_required_approval": sol_eligible,
        },
    }


def build_manifest(args: argparse.Namespace) -> dict[str, object]:
    repository = args.repository or repository_name()
    if args.pr_number:
        work_order = derive_work_order(repository, args.pr_number)
        if args.work_order and args.work_order != work_order:
            raise ValueError(
                f"work-order override {args.work_order!r} does not match PR marker {work_order!r}"
            )
    else:
        work_order = args.work_order or "LOCAL-VALIDATION"
        if work_order != "LOCAL-VALIDATION" and WORK_ORDER_IDENTIFIER.fullmatch(work_order) is None:
            raise ValueError(f"invalid or unbounded HIVE work-order identifier: {work_order!r}")
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
    canonical_changes = canonical_change_evidence(paths)
    governance = governance_evidence(repository, args.pr_number)
    pr_governance = cast(dict[str, Any], governance.get("pull_request", {}))
    require_hive_final_handoff(work_order, args.pr_number, base_sha, head_sha, governance)
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
    observed_draft = pr_governance.get("is_draft")
    draft = (
        args.draft
        or env_bool(args.draft_env, False)
        or (bool(observed_draft) if observed_draft is not None else not args.ready)
    )
    pr_number = args.pr_number
    review_status = "DRAFT" if pr_number and draft else "READY" if pr_number else "NOT_CREATED"
    artifact_name = args.artifact_name or f"hive-review-evidence-{work_order}-{head_sha}"
    return {
        "schema_version": 1,
        "work_order": work_order,
        "repository": repository,
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
        "governance": governance,
        "artifact": {"name": artifact_name, "format": "consolidated-directory", "bounded": True},
        "review_state": {
            "status": review_status,
            "merge_performed": False,
            "sol_review_state": "AWAITING_SOL",
            "auto_merge_armed": bool(pr_governance.get("auto_merge_armed", False)),
            "auto_merge_method": pr_governance.get("auto_merge_method"),
        },
        "negative_scope": [
            "No merge or release was performed.",
            canonical_change_statement(canonical_changes),
            "No reranking, autonomous executor, or LLM provider was added.",
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
    negative_scope = cast(list[object], manifest["negative_scope"])
    canonical_entries = [
        entry
        for entry in negative_scope
        if isinstance(entry, str) and entry.startswith("Canonical change evidence: ")
    ]
    if len(canonical_entries) != 1:
        raise ValueError("review evidence must include exactly one canonical change statement")
    try:
        canonical_payload = json.loads(canonical_entries[0].split(": ", 1)[1])
    except (json.JSONDecodeError, IndexError):
        raise ValueError("canonical change evidence must be valid JSON") from None
    if not isinstance(canonical_payload, dict) or set(canonical_payload) != {
        "project_brain_changed",
        "checkpoint_changed",
        "authorized_paths",
    }:
        raise ValueError("canonical change evidence has an invalid shape")
    if any(
        isinstance(entry, str) and "no canonical project brain checkpoint" in entry.casefold()
        for entry in negative_scope
    ):
        raise ValueError("review evidence cannot deny an observed canonical checkpoint change")
    errors = sorted(
        jsonschema.Draft202012Validator(
            json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        ).iter_errors(manifest),
        key=str,
    )
    if errors:
        raise ValueError(f"manifest schema validation failed: {errors[0].message}")
    warnings = cast(dict[str, Any], cast(dict[str, Any], manifest["evidence"])["warnings"])
    items = warnings["items"]
    if isinstance(items, list) and (
        warnings["count"] != len(items) or len(items) != len(set(items))
    ):
        raise ValueError("warning evidence count must match unique warning items")


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
    review_state = cast(dict[str, Any], manifest["review_state"])
    changed_files = cast(dict[str, Any], manifest["changed_files"])
    canonical_changes = canonical_change_evidence(changed_files["paths"])
    integrity = cast(dict[str, Any], integration["integrity_tests"])
    semantic = cast(dict[str, Any], benchmark.get("semantic", {}))
    hybrid = cast(dict[str, Any], benchmark.get("hybrid", {}))
    semantic_integrity = cast(dict[str, Any], benchmark.get("semantic_integrity", {}))
    warning_lines = (
        "\n".join(f"  - {item}" for item in warnings["items"])
        if warnings["items"]
        else "  - none observed"
    )
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
    semantic_text = (
        f"`{semantic.get('status', 'UNKNOWN')}`; recall@5 `"
        f"{semantic.get('recall_at_5', 0.0)}`, MRR `{semantic.get('mrr', 0.0)}`, "
        f"critical misses `{semantic.get('critical_context_misses', 0)}`, "
        f"two-run reproducibility `{semantic.get('two_run_reproducibility', False)}`"
    )
    hybrid_text = (
        f"`{hybrid.get('status', 'UNKNOWN')}`; recall@5 `"
        f"{hybrid.get('recall_at_5', 0.0)}`, MRR `{hybrid.get('mrr', 0.0)}`, "
        f"RRF gate `{benchmark.get('hybrid_recall_at_5_gte_extended_lexical', False)}`"
    )
    semantic_integrity_text = (
        f"pgvector `{semantic_integrity.get('actual_pgvector_type', 'UNKNOWN')}`, "
        f"dimensions `{semantic_integrity.get('profile_dimensions', 'UNKNOWN')}`, "
        "reuse without provider calls "
        f"`{semantic_integrity.get('provider_requests_on_reuse', 'UNKNOWN')}`"
    )
    changed_paths_text = ", ".join(f"`{path}`" for path in changed_files["paths"]) or "none"
    authorized_paths = cast(list[str], canonical_changes["authorized_paths"])
    authorized_paths_text = ", ".join(authorized_paths) or "none"
    canonical_summary_text = (
        f"project_brain_changed `{canonical_changes['project_brain_changed']}`, "
        f"checkpoint_changed `{canonical_changes['checkpoint_changed']}`, "
        f"authorized paths `{authorized_paths_text}`"
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
    approval_gate = cast(dict[str, Any], governance.get("approval_gate", {}))
    auto_merge_text = (
        f"`{review_state.get('auto_merge_armed', False)}` / "
        f"`{review_state.get('auto_merge_method') or 'none'}`"
    )
    approval_text = (
        f"`{ruleset.get('required_approving_review_count')}`; "
        f"independent approvals observed: "
        f"`{approval_gate.get('independent_approval_count', 0)}`"
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
- PR state: **{review_state["status"]}**
- Changed files: `{changed_files["count"]}` — {changed_paths_text}
- Canonical changes: {canonical_summary_text}
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
- Semantic benchmark: {semantic_text}
- Hybrid benchmark: {hybrid_text}
- Semantic integrity: {semantic_integrity_text}
- Canonical verifier: **{security["canonical_verifier"]["status"]}**
- Secret scan: **{security["secret_scan"]["status"]}**
- Known warnings: `{warnings["count"]}` recorded
{warning_lines}
- Ruleset: {ruleset_text}
- Repository merge settings: {merge_settings}
- Auto-merge armed: {auto_merge_text}
- Required independent approvals: {approval_text}
- Consolidated artifact: `{artifact["name"]}`
- Workflow run URL: {workflow_url}

Sol Review State: {review_state.get("sol_review_state", "AWAITING_SOL")}
"""


def require_hive_final_handoff(
    work_order: str,
    pr_number: int | None,
    base_sha: str,
    head_sha: str,
    governance: dict[str, object],
) -> None:
    if not pr_number or not work_order.startswith("WO-"):
        return
    pr_governance = cast(dict[str, Any], governance.get("pull_request", {}))
    if pr_governance.get("head_sha") != head_sha:
        observed_head = pr_governance.get("head_sha")
        raise ValueError(f"manifest head SHA {head_sha} does not match PR head SHA {observed_head}")
    if pr_governance.get("base_sha") != base_sha:
        observed_base = pr_governance.get("base_sha")
        raise ValueError(f"manifest base SHA {base_sha} does not match PR base SHA {observed_base}")
    if pr_governance.get("state") != "open":
        raise ValueError("HIVE final-handoff evidence requires an open pull request")
    if pr_governance.get("is_draft") is not False:
        raise ValueError("HIVE final-handoff evidence requires a Ready pull request")
    if pr_governance.get("auto_merge_armed") is not True:
        raise ValueError("HIVE final-handoff evidence requires native auto-merge to be armed")
    if str(pr_governance.get("auto_merge_method", "")).casefold() != "squash":
        raise ValueError("HIVE final-handoff evidence requires SQUASH auto-merge")
    approval_gate = cast(dict[str, Any], governance.get("approval_gate", {}))
    if approval_gate.get("independent_approval_count") != 0:
        raise ValueError(
            "HIVE final-handoff evidence requires zero independent approvals before Sol"
        )


def write_consolidated_artifact(
    output_dir: Path, manifest: dict[str, object], summary: str
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    changed = cast(dict[str, Any], manifest["changed_files"])
    migrations = cast(dict[str, Any], manifest["migrations"])
    warnings = cast(dict[str, Any], cast(dict[str, Any], manifest["evidence"])["warnings"])
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
        "service-logs.log": bounded(
            read_text(INTEGRATION_LOGS / "service-logs.log")
            or "No bounded Docker Compose service logs were captured.\n"
        ),
        "warnings-evidence.json": json.dumps(warnings, indent=2, sort_keys=True) + "\n",
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
    parser.add_argument("--work-order")
    parser.add_argument("--repository")
    parser.add_argument("--pr-number", type=int)
    parser.add_argument("--resolve-work-order", action="store_true")
    parser.add_argument("--draft", action="store_true")
    parser.add_argument("--ready", action="store_true")
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
    if args.resolve_work_order:
        if args.pr_number is None:
            parser.error("--resolve-work-order requires --pr-number")
        try:
            print(derive_work_order(args.repository or repository_name(), args.pr_number))
        except ValueError as error:
            parser.error(str(error))
        return 0
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
