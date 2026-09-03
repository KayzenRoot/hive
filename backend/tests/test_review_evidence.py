from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import cast

import pytest
import scripts.review_evidence as review_evidence
from scripts.capture_service_logs import DEFAULT_COMMAND, capture_service_logs, redact_service_logs
from scripts.review_bundle import deterministic_zip
from scripts.review_evidence import (
    CONTEXT_MANAGER_REQUIRED_FIELDS,
    SCHEMA_PATH,
    WO008_G1_ALLOWED_PATHS,
    WO008_G1_BASE_SHA,
    auto_merge_evidence,
    canonical_change_evidence,
    canonical_change_statement,
    context_manager_evidence,
    dashboard_counts,
    junit_counts,
    manifest_log,
    parse_work_order_marker,
    require_hive_final_handoff,
    require_wo008_c1_evidence,
    require_wo008_g1_scope,
    require_wo009_context_manager_evidence,
    summary_markdown,
    validate_manifest,
    verify_native_auto_merge,
    warnings_evidence,
    write_consolidated_artifact,
)
from scripts.review_pr_body import render_body


def evidence_fixture() -> dict[str, object]:
    return {
        "schema_version": 1,
        "work_order": "WO-006",
        "repository": "KayzenRoot/hive",
        "pull_request": {"number": 42, "is_draft": True},
        "base": {"branch": "main", "sha": "a" * 40},
        "head": {"branch": "feature/wo006", "sha": "b" * 40},
        "generated_at": "2026-09-02T00:00:00Z",
        "changed_files": {"count": 1, "paths": ["backend/app/retrieval.py"]},
        "migrations": {"head": "0004_retrieval_lexical"},
        "checks": {
            "validation": "PASS",
            "canonical": "PASS",
            "secrets": "PASS",
            "lint": "PASS",
            "typecheck": "PASS",
            "tests": "PASS",
            "build": "PASS",
            "integration": "PASS",
            "review_evidence": "PASS",
        },
        "benchmark": {
            "status": "PASS",
            "query_count": 4,
            "recall_at_1": 1.0,
            "recall_at_5": 1.0,
            "mrr": 1.0,
            "critical_context_misses": 0,
            "two_run_reproducibility": True,
            "cross_project_isolation": True,
            "redis_restart": True,
            "api_restart": True,
        },
        "evidence": {
            "tests": {
                "status": "PASS",
                "backend": {"status": "PASS", "passed": 72, "failed": 0, "skipped": 0, "errors": 0},
                "dashboard": {"status": "PASS", "passed": 7, "failed": 0, "skipped": 0},
            },
            "integration": {
                "status": "PASS",
                "project_registry": {"status": "PASS", "evidence_file": "project-registry.log"},
                "task_intake_cas": {"status": "PASS", "evidence_file": "task-intake.log"},
                "repository_indexing": {
                    "status": "PASS",
                    "evidence_file": "repository-indexing.log",
                },
                "retrieval": {"status": "PASS", "evidence_file": "retrieval.log"},
                "redis_restart": {"status": "PASS"},
                "api_restart": {"status": "PASS"},
                "context_manager": {
                    "status": "PASS",
                    "evidence_file": "context-manager.json",
                    "checkpoint_first": True,
                    "governance_project_scoped": True,
                    "task_project_scoped": True,
                    "reranked_retrieval_used": True,
                    "provenance_preserved": True,
                    "deterministic_two_run": True,
                    "bounded": True,
                    "cross_project_isolation": True,
                    "missing_governance_fail_closed": True,
                    "head_race_fail_closed": True,
                    "redis_restart_rebuild": True,
                    "api_restart_rebuild": True,
                    "llm_calls": 0,
                },
                "benchmark_gate": {
                    "status": "PASS",
                    "query_count": 4,
                    "recall_at_1": 1.0,
                    "recall_at_5": 1.0,
                    "mrr": 1.0,
                    "critical_context_misses": 0,
                    "two_run_reproducibility": True,
                },
                "cross_project_retrieval": {"status": "PASS"},
                "integrity_tests": {
                    "head_race_rejected": True,
                    "inventory_race_rejected": True,
                    "prior_corpus_preserved": True,
                    "duplicate_task_candidate_collapsed": True,
                    "task_provenance_preserved": True,
                    "cross_project_duplicate_isolation": True,
                },
            },
            "security": {
                "status": "PASS",
                "canonical_verifier": {"status": "PASS"},
                "secret_scan": {"status": "PASS"},
                "project_isolation": {"status": "PASS"},
                "cross_project_retrieval": {"status": "PASS"},
                "sql_query_parameterization": {"status": "PASS", "basis": "test"},
                "source_staleness_fail_closed": {"status": "PASS"},
            },
            "warnings": {"status": "NONE", "count": 0, "items": []},
        },
        "governance": {
            "status": "PASS",
            "ruleset": {
                "id": 21934284,
                "name": "Protect main",
                "enforcement": "active",
                "required_contexts": ["Validate", "Integration health", "Review Evidence"],
                "required_review_thread_resolution": True,
                "allowed_merge_methods": ["squash"],
                "bypass_actors": [],
                "deletion_protection": True,
                "non_fast_forward_protection": True,
                "pull_request_required": True,
                "strict_required_status_checks": True,
            },
            "repository_merge_settings": {
                "allow_squash_merge": True,
                "allow_merge_commit": False,
                "allow_rebase_merge": False,
                "delete_branch_on_merge": True,
                "allow_auto_merge": False,
            },
            "ruleset_unchanged": True,
            "pull_request": {
                "number": 42,
                "state": "open",
                "is_draft": True,
                "head_sha": "b" * 40,
                "base_sha": "a" * 40,
                "auto_merge_armed": True,
                "auto_merge_method": "squash",
                "auto_merge": {
                    "armed": True,
                    "method": "squash",
                    "enabled_by_login": "KayzenRoot",
                    "enabled_by_type": "User",
                    "user_owned": True,
                },
            },
        },
        "artifact": {
            "name": "hive-review-evidence-WO-006-head",
            "format": "consolidated-directory",
            "bounded": True,
        },
        "review_state": {
            "status": "DRAFT",
            "merge_performed": False,
            "auto_merge_owner_login": "KayzenRoot",
            "auto_merge_owner_type": "User",
            "auto_merge_user_owned": True,
        },
        "negative_scope": [
            "No merge or release was performed.",
            canonical_change_statement(canonical_change_evidence(["backend/app/main.py"])),
        ],
    }


def test_review_evidence_schema_is_validated() -> None:
    manifest = evidence_fixture()
    validate_manifest(manifest)
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["properties"]["schema_version"]["const"] == 1


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("<!-- HIVE-WORK-ORDER: WO-007-P -->", "WO-007-P"),
        ("<!-- HIVE-WORK-ORDER: WO-008 -->", "WO-008"),
        ("<!-- HIVE-WORK-ORDER: WO-007-P-C1 -->", "WO-007-P-C1"),
    ],
)
def test_work_order_marker_parser_accepts_bounded_future_and_corrective_ids(
    body: str, expected: str
) -> None:
    assert parse_work_order_marker(body) == expected


def test_work_order_marker_parser_rejects_missing_conflicting_and_untrusted_ids() -> None:
    with pytest.raises(ValueError, match="missing exactly one"):
        parse_work_order_marker("ordinary product pull request")
    with pytest.raises(ValueError, match="multiple conflicting"):
        parse_work_order_marker(
            "<!-- HIVE-WORK-ORDER: WO-007-P -->\n<!-- HIVE-WORK-ORDER: WO-008 -->"
        )
    with pytest.raises(ValueError, match="invalid or unbounded"):
        parse_work_order_marker("<!-- HIVE-WORK-ORDER: WO-007-P; rm -rf / -->")
    with pytest.raises(ValueError, match="invalid or unbounded"):
        parse_work_order_marker(f"<!-- HIVE-WORK-ORDER: {'WO-' + '9' * 70} -->")


def test_canonical_change_evidence_distinguishes_promotion_from_product_changes() -> None:
    promotion = canonical_change_evidence(
        [
            "docs/project-brain/13-CHECKPOINT.md",
            "docs/project-brain/CANONICAL-SHA256SUMS.txt",
        ]
    )
    assert promotion == {
        "project_brain_changed": True,
        "checkpoint_changed": True,
        "authorized_paths": [
            "docs/project-brain/13-CHECKPOINT.md",
            "docs/project-brain/CANONICAL-SHA256SUMS.txt",
        ],
    }
    assert canonical_change_evidence(["backend/app/main.py"]) == {
        "project_brain_changed": False,
        "checkpoint_changed": False,
        "authorized_paths": [],
    }


def test_promotion_evidence_does_not_emit_false_canonical_negative_scope() -> None:
    manifest = evidence_fixture()
    manifest["changed_files"] = {
        "count": 2,
        "paths": [
            "docs/project-brain/13-CHECKPOINT.md",
            "docs/project-brain/CANONICAL-SHA256SUMS.txt",
        ],
    }
    manifest["negative_scope"] = [
        canonical_change_statement(
            canonical_change_evidence(
                [
                    "docs/project-brain/13-CHECKPOINT.md",
                    "docs/project-brain/CANONICAL-SHA256SUMS.txt",
                ]
            )
        )
    ]
    validate_manifest(manifest)
    summary = summary_markdown(manifest, "https://example.invalid/run/1")
    assert "project_brain_changed `True`" in summary
    assert "checkpoint_changed `True`" in summary
    assert "No canonical Project Brain checkpoint was modified" not in summary


def handoff_governance(
    *,
    auto_merge_armed: bool = True,
    auto_merge_method: str | None = "squash",
    head_sha: str = "b" * 40,
    base_sha: str = "a" * 40,
    independent_approval_count: int = 0,
) -> dict[str, object]:
    return {
        "ruleset_unchanged": True,
        "pull_request": {
            "state": "open",
            "is_draft": False,
            "head_sha": head_sha,
            "base_sha": base_sha,
            "auto_merge_armed": auto_merge_armed,
            "auto_merge_method": auto_merge_method,
            "auto_merge": {
                "armed": auto_merge_armed,
                "method": auto_merge_method,
                "enabled_by_login": "KayzenRoot" if auto_merge_armed else "",
                "enabled_by_type": "User" if auto_merge_armed else "",
                "user_owned": auto_merge_armed,
            },
        },
        "approval_gate": {"independent_approval_count": independent_approval_count},
    }


def test_hive_final_handoff_requires_armed_squash_and_zero_approvals() -> None:
    with pytest.raises(ValueError, match="auto-merge"):
        require_hive_final_handoff(
            "WO-007-P", 28, "a" * 40, "b" * 40, handoff_governance(auto_merge_armed=False)
        )
    with pytest.raises(ValueError, match="zero independent approvals"):
        require_hive_final_handoff(
            "WO-007-P",
            28,
            "a" * 40,
            "b" * 40,
            handoff_governance(independent_approval_count=1),
        )
    require_hive_final_handoff("WO-007-P", 28, "a" * 40, "b" * 40, handoff_governance())


def test_hive_final_handoff_rejects_manifest_pr_head_mismatch() -> None:
    with pytest.raises(ValueError, match="does not match PR head"):
        require_hive_final_handoff("WO-007-P", 28, "a" * 40, "c" * 40, handoff_governance())


def test_g1_handoff_requires_exact_base_ruleset_and_user_owned_auto_merge() -> None:
    governance = handoff_governance(base_sha=WO008_G1_BASE_SHA)
    require_hive_final_handoff("WO-008-G1", 30, WO008_G1_BASE_SHA, "b" * 40, governance)

    wrong_base = handoff_governance(base_sha="a" * 40)
    with pytest.raises(ValueError, match="exact base"):
        require_hive_final_handoff("WO-008-G1", 30, "a" * 40, "b" * 40, wrong_base)

    bot_owned = handoff_governance(base_sha=WO008_G1_BASE_SHA)
    bot_pull_request = cast(dict[str, object], bot_owned["pull_request"])
    bot_auto_merge = cast(dict[str, object], bot_pull_request["auto_merge"])
    bot_auto_merge["user_owned"] = False
    with pytest.raises(ValueError, match="user-owned"):
        require_hive_final_handoff("WO-008-G1", 30, WO008_G1_BASE_SHA, "b" * 40, bot_owned)

    changed_ruleset = handoff_governance(base_sha=WO008_G1_BASE_SHA)
    changed_ruleset["ruleset_unchanged"] = False
    with pytest.raises(ValueError, match="ruleset"):
        require_hive_final_handoff("WO-008-G1", 30, WO008_G1_BASE_SHA, "b" * 40, changed_ruleset)


def test_g1_scope_rejects_non_governance_files() -> None:
    require_wo008_g1_scope("WO-008-G1", WO008_G1_BASE_SHA, sorted(WO008_G1_ALLOWED_PATHS))
    with pytest.raises(ValueError, match="outside"):
        require_wo008_g1_scope(
            "WO-008-G1",
            WO008_G1_BASE_SHA,
            [".github/workflows/ci.yml", "backend/app/reranking.py"],
        )


def test_g1_manifest_records_user_owned_identity_and_scope() -> None:
    manifest = evidence_fixture()
    manifest["work_order"] = "WO-008-G1"
    manifest["base"] = {"branch": "main", "sha": WO008_G1_BASE_SHA}
    manifest["changed_files"] = {
        "count": 1,
        "paths": ["scripts/review_evidence.py"],
    }

    validate_manifest(manifest)
    review_state = cast(dict[str, object], manifest["review_state"])
    assert review_state["auto_merge_owner_login"] == "KayzenRoot"
    assert review_state["auto_merge_owner_type"] == "User"
    assert review_state["auto_merge_user_owned"] is True


def native_auto_merge_pull_request(auto_merge: object) -> dict[str, object]:
    return {
        "state": "open",
        "draft": False,
        "head": {"sha": "b" * 40},
        "auto_merge": auto_merge,
    }


def test_user_owned_squash_auto_merge_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pull_request = native_auto_merge_pull_request(
        {
            "merge_method": "squash",
            "enabled_by": {"login": "KayzenRoot", "type": "User"},
        }
    )
    monkeypatch.setattr(review_evidence, "_gh_json", lambda _repository, _endpoint: pull_request)

    assert verify_native_auto_merge("KayzenRoot/hive", 42, "b" * 40) == {
        "armed": True,
        "method": "squash",
        "enabled_by_login": "KayzenRoot",
        "enabled_by_type": "User",
        "user_owned": True,
    }


@pytest.mark.parametrize(
    ("auto_merge", "message"),
    [
        (
            {
                "merge_method": "squash",
                "enabled_by": {"login": "github-actions[bot]", "type": "Bot"},
            },
            "github-actions",
        ),
        (
            {
                "merge_method": "squash",
                "enabled_by": {"login": "automation-app", "type": "App"},
            },
            "user-owned",
        ),
        (
            {
                "merge_method": "squash",
                "enabled_by": {"login": "automation", "type": "Bot"},
            },
            "user-owned",
        ),
        (None, "not armed"),
        (
            {
                "merge_method": "merge",
                "enabled_by": {"login": "KayzenRoot", "type": "User"},
            },
            "SQUASH",
        ),
    ],
)
def test_native_auto_merge_verification_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    auto_merge: object,
    message: str,
) -> None:
    pull_request = native_auto_merge_pull_request(auto_merge)
    monkeypatch.setattr(review_evidence, "_gh_json", lambda _repository, _endpoint: pull_request)

    with pytest.raises(ValueError, match=message):
        verify_native_auto_merge("KayzenRoot/hive", 42, "b" * 40)


def test_native_auto_merge_verification_rejects_draft_and_moved_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pull_request = native_auto_merge_pull_request(
        {
            "merge_method": "squash",
            "enabled_by": {"login": "KayzenRoot", "type": "User"},
        }
    )
    monkeypatch.setattr(review_evidence, "_gh_json", lambda _repository, _endpoint: pull_request)
    pull_request["draft"] = True
    with pytest.raises(ValueError, match="Ready"):
        verify_native_auto_merge("KayzenRoot/hive", 42, "b" * 40)

    pull_request["draft"] = False
    cast(dict[str, object], pull_request["head"])["sha"] = "c" * 40
    with pytest.raises(ValueError, match="head moved"):
        verify_native_auto_merge("KayzenRoot/hive", 42, "b" * 40)


def test_auto_merge_identity_is_recorded_without_secret_fields() -> None:
    evidence = auto_merge_evidence(
        {
            "merge_method": "squash",
            "enabled_by": {
                "login": "KayzenRoot",
                "type": "User",
                "token": "must-not-be-copied",
            },
        }
    )

    assert evidence == {
        "armed": True,
        "method": "squash",
        "enabled_by_login": "KayzenRoot",
        "enabled_by_type": "User",
        "user_owned": True,
    }
    assert "must-not-be-copied" not in json.dumps(evidence)


def test_review_evidence_rejects_merge_claim() -> None:
    manifest = evidence_fixture()
    manifest["review_state"] = {"status": "MERGED", "merge_performed": True}
    try:
        validate_manifest(manifest)
    except ValueError as error:
        assert "merge" in str(error)
    else:
        raise AssertionError("merged evidence must be rejected")


def test_review_evidence_aggregates_wrapped_junit_and_strips_dashboard_ansi(
    tmp_path: Path,
) -> None:
    junit = tmp_path / "backend-junit.xml"
    junit.write_text(
        '<testsuites><testsuite tests="81" failures="0" errors="0" skipped="0" /></testsuites>',
        encoding="utf-8",
    )
    assert junit_counts(junit) == {"passed": 81, "failed": 0, "skipped": 0, "errors": 0}
    assert dashboard_counts("\x1b[2m Tests 7 passed (7)\x1b[0m") == {
        "passed": 7,
        "failed": 0,
        "skipped": 0,
    }


def test_warning_evidence_is_deterministic_deduplicated_and_rendered() -> None:
    evidence = "\n".join(
        [
            "WARNING Memory overcommit must be enabled for Redis / vm.overcommit_memory.",
            "WARNING Memory overcommit must be enabled for Redis / vm.overcommit_memory.",
            "npm warn deprecated whatwg-encoding@3.1.1",
            "npm warn deprecated whatwg-encoding@3.1.1",
            "Node 20 is being deprecated for an action runtime.",
            "Node 20 is being deprecated for an action runtime.",
        ]
    )
    warnings = warnings_evidence(evidence)
    assert warnings == {
        "status": "RECORDED",
        "count": 3,
        "items": [
            "Redis host warning observed: vm.overcommit_memory is disabled.",
            "npm dependency deprecation warning observed.",
            "GitHub Actions Node runtime deprecation warning observed.",
        ],
    }
    manifest = evidence_fixture()
    cast(dict[str, object], manifest["evidence"])["warnings"] = warnings
    summary = summary_markdown(manifest, "https://example.invalid/run/1")
    assert "Known warnings: `3` recorded" in summary
    for item in cast(list[str], warnings["items"]):
        assert item in summary


def test_service_log_redaction_preserves_warning_without_credentials() -> None:
    captured = (
        "redis | WARNING Memory overcommit must be enabled for vm.overcommit_memory.\n"
        "api | DATABASE_URL=postgres://hive:secret@postgres:5432/hive\n"
        "api | token=ghp_1234567890abcdef\n"
    )
    safe = redact_service_logs(captured)
    assert "vm.overcommit_memory" in safe
    assert "secret" not in safe
    assert "ghp_1234567890abcdef" not in safe
    assert "[REDACTED]" in safe


def test_service_log_capture_preserves_command_failure_status(tmp_path: Path) -> None:
    output = tmp_path / "integration-logs" / "service-logs.log"
    status = capture_service_logs(
        output,
        (sys.executable, "-c", "print('bounded service output'); raise SystemExit(7)"),
    )
    assert status == 7
    assert output.read_text(encoding="utf-8") == "bounded service output\n"


def test_review_manifest_is_emitted_between_stable_log_delimiters() -> None:
    rendered = manifest_log(evidence_fixture())
    begin, payload, end = rendered.split("\n", 2)[0], rendered.split("\n", 1)[1], ""
    assert begin == "HIVE_REVIEW_MANIFEST_BEGIN"
    json_payload, end = payload.rsplit("\nHIVE_REVIEW_MANIFEST_END", 1)
    assert end == ""
    assert json.loads(json_payload)["evidence"]["tests"]["backend"]["passed"] == 72


def test_review_bundle_has_only_generic_fallback_implementation() -> None:
    source = (Path(__file__).parents[2] / "scripts" / "review_bundle.py").read_text(
        encoding="utf-8"
    )
    assert "legacy_main" not in source
    assert "Prompt #001" not in source
    assert "Prompt #002" not in source
    assert "Prompt #003" not in source


def test_pr_body_template_contains_work_order_marker_and_sol_state() -> None:
    body = render_body(
        work_order="WO-006",
        pr_number=25,
        branch="feature/wo006-retrieval-lexical",
        base_sha="a" * 40,
        head_sha="b" * 40,
        artifact_name="hive-review-evidence-WO-006-b",
        ruleset_before="old",
        ruleset_after="new",
        merge_before="old",
        merge_after="new",
    )
    assert body.startswith("<!-- HIVE-WORK-ORDER: WO-006 -->")
    assert body.count("Sol Review State: AWAITING_SOL") == 1
    assert body.count("## ") == 20


def test_g1_pr_body_describes_identity_correction() -> None:
    body = render_body(
        work_order="WO-008-G1",
        pr_number=30,
        branch="fix/wo008-postmerge-ci-automerge-identity",
        base_sha="a" * 40,
        head_sha="b" * 40,
        artifact_name="hive-review-evidence-WO-008-G1-b",
        ruleset_before="old",
        ruleset_after="unchanged",
        merge_before="old",
        merge_after="unchanged",
    )

    assert body.startswith("<!-- HIVE-WORK-ORDER: WO-008-G1 -->")
    assert "GITHUB_TOKEN" in body
    assert "gh pr merge --auto" in body
    assert "python -m pytest" in body
    assert "Riscos conhecidos" in body
    assert "docs/project-brain/13-CHECKPOINT.md" in body
    assert "WO-008-G1 READY FOR SOL GITHUB AUDIT" in body
    assert "fundação de reranking" not in body


def test_wo009_pr_body_describes_context_manager_handoff() -> None:
    body = render_body(
        work_order="WO-009",
        pr_number=32,
        branch="feature/wo009-context-manager-foundation",
        base_sha="a" * 40,
        head_sha="b" * 40,
        artifact_name="hive-review-evidence-WO-009-b",
        ruleset_before="old",
        ruleset_after="unchanged",
        merge_before="old",
        merge_after="unchanged",
        auto_merge_owner_login="KayzenRoot",
        auto_merge_owner_type="User",
    )

    assert body.startswith("<!-- HIVE-WORK-ORDER: WO-009 -->")
    assert "/projects/{project_id}/tasks/{task_id}/context" in body
    assert "Auto-merge owner: `KayzenRoot` (User)" in body
    assert "context-capsule-v1" in body
    assert "WO-009 READY FOR SOL GITHUB AUDIT" in body


def test_consolidated_artifact_contains_the_required_audit_inputs(tmp_path: Path) -> None:
    manifest = evidence_fixture()
    manifest["large_audit_field"] = "x" * review_evidence.MAX_EVIDENCE_CHARS
    write_consolidated_artifact(tmp_path, manifest, "summary\n")
    expected = {
        "changed-files.txt",
        "migration-head.txt",
        "validation-summary.txt",
        "validation-results.txt",
        "integration-summary.json",
        "integration-results.txt",
        "service-logs.log",
        "warnings-evidence.json",
        "benchmark.json",
        "failure-diagnostics.txt",
        "review-manifest.json",
        "review-summary.md",
        "github-governance.json",
    }
    assert expected <= {path.name for path in tmp_path.iterdir()}
    assert json.loads((tmp_path / "review-manifest.json").read_text(encoding="utf-8")) == manifest


def test_consolidated_artifact_contains_captured_service_warning_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    integration_logs = tmp_path / "integration-logs"
    integration_logs.mkdir()
    service_log = (
        "redis-1 | WARNING Memory overcommit must be enabled for Redis / vm.overcommit_memory.\n"
    )
    (integration_logs / "service-logs.log").write_text(service_log, encoding="utf-8")
    monkeypatch.setattr(review_evidence, "INTEGRATION_LOGS", integration_logs)
    output = tmp_path / "review-evidence"

    write_consolidated_artifact(output, evidence_fixture(), "summary\n")

    assert (output / "service-logs.log").read_text(encoding="utf-8") == service_log
    warnings = json.loads((output / "warnings-evidence.json").read_text(encoding="utf-8"))
    assert warnings == {"status": "NONE", "count": 0, "items": []}


def test_ci_persists_bounded_service_logs_and_uses_supported_action_majors() -> None:
    workflow = (Path(__file__).parents[2] / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert DEFAULT_COMMAND == ("docker", "compose", "logs", "--no-color", "--tail=200")
    assert "on:\n  push:\n    branches:\n      - main" in workflow
    assert "--verify-auto-merge" in workflow
    assert "gh pr merge" not in workflow
    assert "tmp/integration-logs/service-logs.log" in workflow
    assert "path: |\n            tmp/validation\n            tmp/integration-logs" in workflow
    assert "actions/upload-artifact@v7" in workflow
    assert "actions/download-artifact@v8" in workflow


def test_context_manager_review_evidence_fails_closed_when_missing_or_incomplete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    integration_logs = tmp_path / "integration-logs"
    integration_logs.mkdir()
    payload = {
        "status": "PASS",
        **{field: True for field in CONTEXT_MANAGER_REQUIRED_FIELDS},
        "llm_calls": 0,
    }
    (integration_logs / "context-manager.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    monkeypatch.setattr(review_evidence, "INTEGRATION_LOGS", integration_logs)

    evidence = context_manager_evidence()
    assert evidence["status"] == "PASS"
    require_wo009_context_manager_evidence("WO-009", {"context_manager": evidence})

    incomplete = dict(payload)
    incomplete["checkpoint_first"] = False
    (integration_logs / "context-manager.json").write_text(
        json.dumps(incomplete),
        encoding="utf-8",
    )
    failed = context_manager_evidence()
    assert failed["status"] == "FAIL"
    with pytest.raises(ValueError, match="Context Manager evidence"):
        require_wo009_context_manager_evidence("WO-009", {"context_manager": failed})

    (integration_logs / "context-manager.json").write_text("{malformed", encoding="utf-8")
    assert context_manager_evidence()["status"] == "UNKNOWN"


def test_sticky_summary_has_required_review_fields() -> None:
    summary = summary_markdown(evidence_fixture(), "https://example.invalid/run/1")
    for field in (
        "Work Order",
        "Exact HEAD SHA",
        "Validate result",
        "Integration health result",
        "Review Evidence result",
        "Migration head",
        "Backend tests",
        "Dashboard tests",
        "Canonical verifier",
        "Secret scan",
        "Consolidated artifact",
        "Workflow run URL",
        "Context Manager evidence",
        "Ruleset unchanged",
        "Auto-merge owner: KayzenRoot (User)",
        "Sol Review State: AWAITING_SOL",
    ):
        assert field in summary


@pytest.mark.parametrize("work_order", ["WO-008", "WO-008-G1"])
def test_wo008_c1_evidence_fails_closed_on_missing_safety_proof(work_order: str) -> None:
    required = {field: True for field in review_evidence.RERANK_C1_REQUIRED_FIELDS}
    benchmark = {"status": "PASS", "rerank": {"status": "PASS", **required}}
    integration = {"integrity_tests": required}
    security = {"reranking": {"status": "PASS"}}

    require_wo008_c1_evidence(
        work_order, benchmark, integration, security, "bounded evidence", "review text"
    )

    failed_benchmark = {
        "status": "PASS",
        "rerank": {"status": "PASS", **required, "rerank_ordering_reproducible": False},
    }
    with pytest.raises(ValueError, match="mandatory rerank C1 evidence"):
        require_wo008_c1_evidence(
            work_order,
            failed_benchmark,
            integration,
            security,
            "bounded evidence",
            "review text",
        )


def test_generic_bundle_zip_is_byte_deterministic(tmp_path: Path) -> None:
    files = {"z.txt": "last\n", "a.txt": "first\n"}
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    assert deterministic_zip(first, files) == deterministic_zip(second, files)
    assert first.read_bytes() == second.read_bytes()
