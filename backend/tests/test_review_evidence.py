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
    WO009_BASE_SHA,
    WO010_G1_ALLOWED_PATHS,
    WO010_G1_BASE_SHA,
    authorize_merge_action,
    WO010_BASE_SHA,
    auto_merge_evidence,
    canonical_change_evidence,
    canonical_change_statement,
    context_manager_evidence,
    dashboard_counts,
    governance_evidence,
    junit_counts,
    manifest_log,
    parse_work_order_marker,
    require_hive_final_handoff,
    require_wo008_c1_evidence,
    require_wo008_g1_scope,
    require_wo009_context_manager_evidence,
    require_wo009_scope,
    require_wo010_g1_scope,
    require_wo010_progressive_disclosure_evidence,
    require_wo010_scope,
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
                    "mandatory_governance_coverage": True,
                    "mandatory_governance_kind_sequence": [
                        "CHECKPOINT",
                        "SCOPE",
                        "DEFINITION_OF_DONE",
                        "ARCHITECTURE",
                        "DECISIONS",
                    ],
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


def test_hive_final_handoff_requires_unarmed_auto_merge_before_sol() -> None:
    with pytest.raises(ValueError, match="unarmed"):
        require_hive_final_handoff(
            "WO-007-P", 28, "a" * 40, "b" * 40, handoff_governance(auto_merge_armed=True)
        )
    require_hive_final_handoff(
        "WO-007-P",
        28,
        "a" * 40,
        "b" * 40,
        handoff_governance(auto_merge_armed=False, independent_approval_count=1),
    )
    require_hive_final_handoff(
        "WO-007-P", 28, "a" * 40, "b" * 40, handoff_governance(auto_merge_armed=False)
    )


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


def protect_main_ruleset(
    *,
    required_approving_review_count: int = 0,
    require_last_push_approval: bool = False,
    require_extra_approval_for_unattributed_changes: bool = False,
) -> dict[str, object]:
    return {
        "id": 21934284,
        "name": "Protect main",
        "enforcement": "active",
        "bypass_actors": [],
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {
                "type": "pull_request",
                "parameters": {
                    "required_approving_review_count": required_approving_review_count,
                    "dismiss_stale_reviews_on_push": True,
                    "require_last_push_approval": require_last_push_approval,
                    "required_review_thread_resolution": True,
                    "require_extra_approval_for_unattributed_changes": (
                        require_extra_approval_for_unattributed_changes
                    ),
                    "allowed_merge_methods": ["squash"],
                },
            },
            {
                "type": "required_status_checks",
                "parameters": {
                    "strict_required_status_checks_policy": True,
                    "required_status_checks": [
                        {"context": "Validate"},
                        {"context": "Integration health"},
                        {"context": "Review Evidence"},
                    ],
                },
            },
        ],
    }


def fake_github_governance(
    *,
    ruleset: dict[str, object] | None = None,
    reviews: list[dict[str, object]] | None = None,
    auto_merge: dict[str, object] | None = None,
) -> object:
    selected_ruleset = ruleset if ruleset is not None else protect_main_ruleset()

    def _gh_json(_repository: str, endpoint: str) -> object:
        if "kayzenweb3" in endpoint:
            raise AssertionError("kayzenweb3 collaborator permission must not be queried")
        if endpoint.startswith("rulesets"):
            if endpoint.startswith("rulesets/"):
                return selected_ruleset
            return [{"id": 21934284, "name": "Protect main"}]
        if endpoint == "":
            return {
                "allow_squash_merge": True,
                "allow_merge_commit": False,
                "allow_rebase_merge": False,
                "delete_branch_on_merge": True,
                "allow_auto_merge": True,
            }
        if endpoint.endswith("/reviews"):
            return reviews if reviews is not None else []
        if endpoint.startswith("pulls/"):
            return {
                "state": "open",
                "draft": False,
                "user": {"login": "KayzenRoot"},
                "head": {"sha": "b" * 40},
                "base": {"sha": "a" * 40},
                "auto_merge": auto_merge,
            }
        return None

    return _gh_json


def test_single_account_ruleset_baseline_and_no_kayzenweb3_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(review_evidence, "_gh_json", fake_github_governance())
    evidence = governance_evidence("KayzenRoot/hive", 35)
    ruleset = cast(dict[str, object], evidence["ruleset"])
    approval_gate = cast(dict[str, object], evidence["approval_gate"])
    sol_reviewer = cast(dict[str, object], evidence["sol_reviewer"])
    pull_request = cast(dict[str, object], evidence["pull_request"])

    assert evidence["ruleset_unchanged"] is True
    assert ruleset["required_approving_review_count"] == 0
    assert ruleset["require_last_push_approval"] is False
    assert ruleset["require_extra_approval_for_unattributed_changes"] is False
    assert ruleset["required_contexts"] == [
        "Integration health",
        "Review Evidence",
        "Validate",
    ]
    assert ruleset["allowed_merge_methods"] == ["squash"]
    assert ruleset["bypass_actors"] == []
    assert approval_gate["independent_approval_count"] == 0
    assert sol_reviewer["login"] == "KayzenRoot"
    assert sol_reviewer["can_satisfy_required_approval"] is False
    assert pull_request["auto_merge_armed"] is False


def test_legacy_two_account_ruleset_is_not_the_current_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        review_evidence,
        "_gh_json",
        fake_github_governance(
            ruleset=protect_main_ruleset(
                required_approving_review_count=1,
                require_last_push_approval=True,
                require_extra_approval_for_unattributed_changes=True,
            )
        ),
    )
    evidence = governance_evidence("KayzenRoot/hive", 35)
    assert evidence["ruleset_unchanged"] is False


def test_historical_independent_reviews_do_not_block_pre_sol_handoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        review_evidence,
        "_gh_json",
        fake_github_governance(
            reviews=[
                {
                    "user": {"login": "kayzenweb3"},
                    "state": "APPROVED",
                    "submitted_at": "2026-09-01T00:00:00Z",
                }
            ]
        ),
    )
    evidence = governance_evidence("KayzenRoot/hive", 35)
    approval_gate = cast(dict[str, object], evidence["approval_gate"])
    assert approval_gate["independent_approvers"] == ["kayzenweb3"]
    assert approval_gate["independent_approval_count"] == 1
    require_hive_final_handoff(
        "WO-010-G1",
        35,
        "a" * 40,
        "b" * 40,
        {
            "ruleset_unchanged": True,
            "pull_request": evidence["pull_request"],
            "approval_gate": approval_gate,
        },
    )


def test_wo010_g1_scope_and_manifest_require_unarmed_auto_merge() -> None:
    require_wo010_g1_scope("WO-010-G1", WO010_G1_BASE_SHA, sorted(WO010_G1_ALLOWED_PATHS))
    with pytest.raises(ValueError, match="outside"):
        require_wo010_g1_scope(
            "WO-010-G1",
            WO010_G1_BASE_SHA,
            ["docs/project-brain/13-CHECKPOINT.md", "backend/app/progressive_disclosure.py"],
        )
    manifest = evidence_fixture()
    manifest["work_order"] = "WO-010-G1"
    manifest["base"] = {"branch": "main", "sha": WO010_G1_BASE_SHA}
    manifest["changed_files"] = {
        "count": 1,
        "paths": ["docs/project-brain/16-DECISIONS-LEDGER.md"],
    }
    review_state = cast(dict[str, object], manifest["review_state"])
    review_state["auto_merge_armed"] = False
    review_state["sol_review_state"] = "AWAITING_SOL"
    governance = cast(dict[str, object], manifest["governance"])
    pull_request = cast(dict[str, object], governance["pull_request"])
    pull_request["auto_merge_armed"] = False
    pull_request["auto_merge_method"] = None
    pull_request["auto_merge"] = {
        "armed": False,
        "method": None,
        "enabled_by_login": "",
        "enabled_by_type": "",
        "user_owned": False,
    }
    validate_manifest(manifest)
    review_state["auto_merge_armed"] = True
    with pytest.raises(ValueError, match="unarmed"):
        validate_manifest(manifest)
    review_state["auto_merge_armed"] = False
    review_state["sol_review_state"] = "APPROVED"
    with pytest.raises(ValueError, match="Sol approval"):
        validate_manifest(manifest)


def test_wo010_g1_canonical_change_evidence_is_work_order_aware() -> None:
    intended = [
        "docs/project-brain/13-CHECKPOINT.md",
        "docs/project-brain/16-DECISIONS-LEDGER.md",
        "docs/project-brain/CANONICAL-SHA256SUMS.txt",
    ]
    evidence = canonical_change_evidence(intended, "WO-010-G1")
    assert evidence["authorized_paths"] == intended

    unrelated = canonical_change_evidence(
        intended + ["docs/project-brain/04-ARCHITECTURE.md"], "WO-010-G1"
    )
    assert unrelated["authorized_paths"] == intended

    non_g1 = canonical_change_evidence(intended, "WO-011")
    assert non_g1["authorized_paths"] == [
        "docs/project-brain/13-CHECKPOINT.md",
        "docs/project-brain/CANONICAL-SHA256SUMS.txt",
    ]


def test_wo010_g1_summary_prints_all_authorized_canonical_paths() -> None:
    manifest = evidence_fixture()
    manifest["work_order"] = "WO-010-G1"
    manifest["changed_files"] = {
        "count": 3,
        "paths": [
            "docs/project-brain/13-CHECKPOINT.md",
            "docs/project-brain/16-DECISIONS-LEDGER.md",
            "docs/project-brain/CANONICAL-SHA256SUMS.txt",
        ],
    }
    summary = summary_markdown(manifest, "https://example.invalid/run/1")
    assert "docs/project-brain/13-CHECKPOINT.md" in summary
    assert "docs/project-brain/16-DECISIONS-LEDGER.md" in summary
    assert "docs/project-brain/CANONICAL-SHA256SUMS.txt" in summary


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


def test_wo009_scope_rejects_wrong_base_and_canonical_changes() -> None:
    require_wo009_scope("WO-009", WO009_BASE_SHA, ["backend/app/context_manager.py"])
    with pytest.raises(ValueError, match="exact base"):
        require_wo009_scope("WO-009", "a" * 40, ["backend/app/context_manager.py"])
    with pytest.raises(ValueError, match="canonical Project Brain"):
        require_wo009_scope("WO-009", WO009_BASE_SHA, ["docs/project-brain/13-CHECKPOINT.md"])


def test_wo010_scope_rejects_wrong_base_canonical_and_migrations() -> None:
    require_wo010_scope("WO-010", WO010_BASE_SHA, ["backend/app/progressive_disclosure.py"])
    with pytest.raises(ValueError, match="exact base"):
        require_wo010_scope("WO-010", "a" * 40, ["backend/app/progressive_disclosure.py"])
    with pytest.raises(ValueError, match="canonical Project Brain"):
        require_wo010_scope("WO-010", WO010_BASE_SHA, ["docs/project-brain/13-CHECKPOINT.md"])
    with pytest.raises(ValueError, match="migrations"):
        require_wo010_scope(
            "WO-010",
            WO010_BASE_SHA,
            ["migrations/versions/0006_progressive_disclosure.py"],
        )


def native_auto_merge_pull_request(auto_merge: object) -> dict[str, object]:
    return {
        "state": "open",
        "draft": False,
        "head": {"sha": "b" * 40},
        "auto_merge": auto_merge,
    }


def merge_authorization_state(**overrides: object) -> dict[str, object]:
    state: dict[str, object] = {
        "sol_approved": True,
        "auto_merge_armed": False,
        "pr_state": "open",
        "is_draft": False,
        "head_sha": "b" * 40,
        "base_sha": "a" * 40,
        "base_branch": "main",
        "ruleset_valid": True,
        "unresolved_threads": 0,
        "merge_method": "squash",
        "mergeable": True,
        "mergeable_state": "clean",
        "required_checks": {
            "Validate": "success",
            "Integration health": "success",
            "Review Evidence": "success",
        },
    }
    state.update(overrides)
    return state


def test_clean_post_sol_state_authorizes_direct_squash_without_auto_merge() -> None:
    decision = authorize_merge_action(
        merge_authorization_state(),
        expected_head_sha="b" * 40,
        expected_base_sha="a" * 40,
    )

    assert decision == {
        "authorized": True,
        "action": "DIRECT_SQUASH_MERGE",
        "merge_method": "squash",
        "expected_head_sha": "b" * 40,
        "reason": "all safety gates are green on the exact audited HEAD",
    }


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"head_sha": "c" * 40}, "HEAD moved"),
        ({"base_sha": "c" * 40}, "base"),
        (
            {
                "required_checks": {
                    "Validate": "success",
                    "Integration health": "success",
                    "Review Evidence": "failure",
                }
            },
            "not green",
        ),
        (
            {
                "required_checks": {
                    "Validate": "success",
                    "Integration health": "success",
                }
            },
            "missing",
        ),
        ({"mergeable": False, "mergeable_state": "dirty"}, "mergeability"),
        ({"is_draft": True}, "Ready"),
        ({"unresolved_threads": 1}, "threads"),
        ({"ruleset_valid": False}, "ruleset"),
        ({"merge_method": "merge"}, "SQUASH"),
        ({"auto_merge_armed": True}, "unarmed"),
    ],
)
def test_post_sol_direct_merge_fails_closed(overrides: dict[str, object], message: str) -> None:
    decision = authorize_merge_action(
        merge_authorization_state(**overrides),
        expected_head_sha="b" * 40,
        expected_base_sha="a" * 40,
    )

    assert decision["authorized"] is False
    assert decision["action"] == "REJECT"
    assert message.casefold() in str(decision["reason"]).casefold()


def test_pending_required_checks_allow_only_conditional_auto_merge() -> None:
    decision = authorize_merge_action(
        merge_authorization_state(
            mergeable_state="blocked",
            required_checks={
                "Validate": "success",
                "Integration health": "pending",
                "Review Evidence": "success",
            },
        ),
        expected_head_sha="b" * 40,
        expected_base_sha="a" * 40,
    )

    assert decision["authorized"] is True
    assert decision["action"] == "ARM_SQUASH_AUTO_MERGE"
    assert decision["pending_checks"] == ["Integration health"]


def test_sol_approval_is_required_for_any_post_sol_merge_action() -> None:
    decision = authorize_merge_action(
        merge_authorization_state(sol_approved=False),
        expected_head_sha="b" * 40,
        expected_base_sha="a" * 40,
    )

    assert decision["authorized"] is False
    assert decision["action"] == "REJECT"


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


def test_future_work_order_template_uses_single_account_stage_gate() -> None:
    body = render_body(
        work_order="WO-011",
        pr_number=36,
        branch="feature/wo011-future",
        base_sha="a" * 40,
        head_sha="b" * 40,
        artifact_name="hive-review-evidence-WO-011-b",
        ruleset_before="baseline",
        ruleset_after="unchanged",
        merge_before="unarmed",
        merge_after="unarmed",
    )
    folded = body.casefold()
    assert "kayzenroot" in folded
    assert "awaiting_sol" in folded
    assert "auto-merge nativo desarmado" in folded
    assert "sol merge authorization" in folded
    assert "squash direto" in folded
    assert "auto-merge nativo squash" in folded
    assert "push ci" in folded
    assert "sol arms auto-merge" not in folded
    assert "kayzenweb3" not in folded
    assert "aprovação independente elegível" not in folded
    assert "independent native approval" not in folded


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
    assert "CHECKPOINT -> SCOPE -> DEFINITION_OF_DONE -> ARCHITECTURE -> DECISIONS" in body
    assert "mandatory_governance_coverage" in body
    assert "WO-009 READY FOR SOL GITHUB AUDIT" in body


def test_wo010_g1_pr_body_describes_single_account_governance() -> None:
    body = render_body(
        work_order="WO-010-G1",
        pr_number=35,
        branch="governance/wo010-g1-single-account",
        base_sha="a" * 40,
        head_sha="b" * 40,
        artifact_name="hive-review-evidence-WO-010-G1-b",
        ruleset_before="approvals=1",
        ruleset_after="approvals=0",
        merge_before="old",
        merge_after="unchanged",
    )

    assert body.startswith("<!-- HIVE-WORK-ORDER: WO-010-G1 -->")
    assert "KayzenRoot" in body
    assert "kayzenweb3" in body
    assert "auto-merge desarmado" in body
    assert "SOL MERGE AUTHORIZATION" in body
    assert "SQUASH no HEAD" in body
    assert "checks obrigatórios legítimos estiverem pendentes" in body
    assert "WO-010-G1 READY FOR SOL AUDIT" in body
    assert "21934284" in body


def test_wo010_pr_body_describes_progressive_disclosure_handoff() -> None:
    body = render_body(
        work_order="WO-010",
        pr_number=34,
        branch="feature/wo010-progressive-disclosure-foundation",
        base_sha="a" * 40,
        head_sha="b" * 40,
        artifact_name="hive-review-evidence-WO-010-b",
        ruleset_before="old",
        ruleset_after="unchanged",
        merge_before="old",
        merge_after="unchanged",
        auto_merge_owner_login="KayzenRoot",
        auto_merge_owner_type="User",
    )

    assert body.startswith("<!-- HIVE-WORK-ORDER: WO-010 -->")
    assert "L0 Project capsule" in body
    assert "disclosure_level" in body
    assert "adaptive_token_budget_implemented: false" in body
    assert "Auto-merge permanece desarmado" in body
    assert "WO-010 READY FOR SOL GITHUB AUDIT" in body
    assert "## 27. Proposta de checkpoint para WO-010-P" in body


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
    assert "--verify-auto-merge" not in workflow
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
        "mandatory_governance_kind_sequence": [
            "CHECKPOINT",
            "SCOPE",
            "DEFINITION_OF_DONE",
            "ARCHITECTURE",
            "DECISIONS",
        ],
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

    missing_coverage = dict(payload)
    del missing_coverage["mandatory_governance_coverage"]
    (integration_logs / "context-manager.json").write_text(
        json.dumps(missing_coverage),
        encoding="utf-8",
    )
    assert context_manager_evidence()["status"] == "UNKNOWN"
    with pytest.raises(ValueError, match="Context Manager evidence"):
        require_wo009_context_manager_evidence(
            "WO-009",
            {"context_manager": context_manager_evidence()},
        )

    false_coverage = dict(payload)
    false_coverage["mandatory_governance_coverage"] = False
    (integration_logs / "context-manager.json").write_text(
        json.dumps(false_coverage),
        encoding="utf-8",
    )
    false_evidence = context_manager_evidence()
    assert false_evidence["status"] == "FAIL"
    with pytest.raises(ValueError, match="mandatory_governance_coverage"):
        require_wo009_context_manager_evidence("WO-009", {"context_manager": false_evidence})

    wrong_sequence = dict(payload)
    wrong_sequence["mandatory_governance_kind_sequence"] = ["CHECKPOINT", "SCOPE"]
    (integration_logs / "context-manager.json").write_text(
        json.dumps(wrong_sequence),
        encoding="utf-8",
    )
    sequence_evidence = context_manager_evidence()
    assert sequence_evidence["status"] == "FAIL"
    with pytest.raises(ValueError, match="mandatory governance kinds"):
        require_wo009_context_manager_evidence("WO-009", {"context_manager": sequence_evidence})


def test_wo010_progressive_disclosure_review_evidence_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    integration_logs = tmp_path / "integration-logs"
    integration_logs.mkdir()
    payload = {
        "status": "PASS",
        **{field: True for field in CONTEXT_MANAGER_REQUIRED_FIELDS},
        "mandatory_governance_kind_sequence": [
            "CHECKPOINT",
            "SCOPE",
            "DEFINITION_OF_DONE",
            "ARCHITECTURE",
            "DECISIONS",
        ],
        "llm_calls": 0,
        **{field: True for field in review_evidence.PROGRESSIVE_DISCLOSURE_REQUIRED_FIELDS},
        **{field: True for field in review_evidence.PROGRESSIVE_DISCLOSURE_C1_FIELDS},
        **{field: True for field in review_evidence.PROGRESSIVE_DISCLOSURE_C2_FIELDS},
        "disclosure_llm_calls": 0,
        "adaptive_token_budget_implemented": False,
    }
    (integration_logs / "context-manager.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    monkeypatch.setattr(review_evidence, "INTEGRATION_LOGS", integration_logs)

    evidence = context_manager_evidence()
    assert evidence["status"] == "PASS"
    require_wo010_progressive_disclosure_evidence(
        "WO-010",
        {"context_manager": evidence},
        "0005_semantic_retrieval",
    )

    missing = dict(payload)
    del missing["smallest_sufficient"]
    (integration_logs / "context-manager.json").write_text(
        json.dumps(missing),
        encoding="utf-8",
    )
    missing_evidence = context_manager_evidence()
    with pytest.raises(ValueError, match="Progressive Disclosure evidence"):
        require_wo010_progressive_disclosure_evidence(
            "WO-010",
            {"context_manager": missing_evidence},
            "0005_semantic_retrieval",
        )

    false_payload = dict(payload)
    false_payload["no_unnecessary_escalation"] = False
    (integration_logs / "context-manager.json").write_text(
        json.dumps(false_payload),
        encoding="utf-8",
    )
    false_evidence = context_manager_evidence()
    assert false_evidence["no_unnecessary_escalation"] is False
    with pytest.raises(ValueError, match="Progressive Disclosure evidence"):
        require_wo010_progressive_disclosure_evidence(
            "WO-010",
            {"context_manager": false_evidence},
            "0005_semantic_retrieval",
        )

    llm_payload = dict(payload)
    llm_payload["disclosure_llm_calls"] = 1
    (integration_logs / "context-manager.json").write_text(
        json.dumps(llm_payload),
        encoding="utf-8",
    )
    llm_evidence = context_manager_evidence()
    assert llm_evidence["disclosure_llm_calls"] == 1
    with pytest.raises(ValueError, match="zero disclosure LLM calls"):
        require_wo010_progressive_disclosure_evidence(
            "WO-010",
            {"context_manager": llm_evidence},
            "0005_semantic_retrieval",
        )

    adaptive_payload = dict(payload)
    adaptive_payload["adaptive_token_budget_implemented"] = True
    (integration_logs / "context-manager.json").write_text(
        json.dumps(adaptive_payload),
        encoding="utf-8",
    )
    adaptive_evidence = context_manager_evidence()
    assert adaptive_evidence["adaptive_token_budget_implemented"] is True
    with pytest.raises(ValueError, match="adaptive_token_budget_implemented"):
        require_wo010_progressive_disclosure_evidence(
            "WO-010",
            {"context_manager": adaptive_evidence},
            "0005_semantic_retrieval",
        )

    with pytest.raises(ValueError, match="migration head"):
        require_wo010_progressive_disclosure_evidence(
            "WO-010",
            {"context_manager": evidence},
            "0006_adaptive_token_budget",
        )


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
        "Progressive Disclosure evidence",
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
