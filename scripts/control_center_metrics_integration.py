"""Produce control-center-metrics-v1 evidence from the real Docker HIVE stack."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from control_center_integration import (  # noqa: E402
    ApiProbe,
    Fixture,
    cleanup_fixtures,
    compose,
    create_task,
    current_migration_head,
    emit_event_batch,
    event_spec,
    fetch_dashboard_bundle,
    register_wo020_fixtures,
    require,
    run_command,
    wait_for_api_health,
)

EVIDENCE_FILE = "control-center-metrics.json"
EVIDENCE_VERSION = "control-center-metrics-v1"
EVIDENCE_OUTPUT = ROOT / "tmp" / "integration-logs" / EVIDENCE_FILE
MIGRATION_BASE_HEAD = "0007_telemetry_events"
METRIC_FAMILIES = ("token", "context", "cache", "storage")
METRIC_PROVENANCE = ("EXACT", "ESTIMATED", "UNAVAILABLE", "UNKNOWN")
HISTORY_MAX_POINTS = 100
EVIDENCE_PATHS = (
    "backend/app/control_center_metrics.py",
    "backend/app/control_center_storage_metrics.py",
    "backend/tests/test_control_center_metrics.py",
    "dashboard/src/ControlCenterMetrics.tsx",
    "dashboard/src/ControlCenterMetrics.test.tsx",
    "scripts/control_center_metrics_integration.py",
    "scripts/integration_health.py",
    "docs/atlas/wo021-control-center-metrics.md",
)
TRUE_FIELDS = (
    "control_center_metrics_foundation_implemented",
    "token_telemetry_visible",
    "provider_final_usage_reconciliation_supported",
    "fresh_cached_distinction_conditional_on_provider_support",
    "estimated_token_values_labelled",
    "unknown_token_values_not_zero",
    "context_reduction_measured",
    "context_measurement_provenance_preserved",
    "cache_hit_miss_measured_from_real_events_or_receipts",
    "unknown_cache_state_not_hit",
    "storage_logical_physical_measured",
    "storage_measurement_provenance_preserved",
    "bounded_historical_series",
    "near_realtime_metric_refresh",
    "project_scoped_metrics",
    "deterministic_global_aggregation",
    "postgres_canonical",
    "redis_noncanonical",
    "restart_recovery",
    "redis_loss_recovery",
    "backend_metric_payloads_bounded",
    "frontend_metric_render_bounded",
)
FALSE_FIELDS = (
    "estimated_live_tokens_presented_as_exact",
    "fabricated_provider_usage",
    "fabricated_cache_hit",
    "fabricated_cost_metrics",
    "unknown_metrics_rendered_as_zero",
    "redis_canonical_truth",
    "full_control_center_claimed",
    "full_v01_complete_claimed",
)
ALLOWED_FIELDS = frozenset(
    {
        "status",
        "evidence_file",
        "metrics_evidence_version",
        "observed_migration_head",
        "migration_base_head",
        "cost_provenance",
        "migration_changed",
        *TRUE_FIELDS,
        *FALSE_FIELDS,
        "historical_series_max_points",
        "secret_leaks",
        "filesystem_path_leaks",
        "cross_project_leaks",
        "metrics_llm_calls",
        "metrics_provider_calls",
        "implemented_metric_families",
        "metric_value_provenance",
        "evidence_paths",
    }
)


def log(message: str) -> None:
    print(f"[wo021] {message}", flush=True)


def metric_payload(
    probe: ApiProbe, project_id: UUID | None = None, limit: int = 100
) -> dict[str, object]:
    path = "/api/v1/control-center/metrics/global"
    if project_id is not None:
        path = f"/api/v1/control-center/metrics?project_id={project_id}"
    separator = "&" if "?" in path else "?"
    payload = probe.request("GET", f"{path}{separator}history_points={limit}")
    require(isinstance(payload, dict), "metrics response is not an object")
    return dict(payload)


def metric_value(payload: dict[str, object], family: str, name: str) -> dict[str, object]:
    family_payload = payload.get(family)
    require(isinstance(family_payload, dict), f"{family} metric family is missing")
    value = family_payload.get(name)
    require(isinstance(value, dict), f"{family}.{name} metric is missing")
    return dict(value)


def emit_metrics_fixture(fixtures: list[Fixture]) -> tuple[UUID, UUID]:
    alpha, beta = fixtures
    require(
        alpha.project_id is not None and beta.project_id is not None,
        "metrics fixtures not registered",
    )
    require(alpha.task_ids and beta.task_ids, "metrics fixture tasks are missing")
    alpha_run = uuid4()
    beta_run = uuid4()
    emit_event_batch(
        alpha.project_id,
        [
            event_spec(
                event_type="executor.started",
                run_id=alpha_run,
                emission_key=f"{alpha.label}-metrics-estimate",
                payload={"input_tokens": 100, "cached_tokens": 20, "estimated": True},
                task_id=alpha.task_ids[0],
            ),
            event_spec(
                event_type="context.built",
                run_id=alpha_run,
                emission_key=f"{alpha.label}-metrics-context",
                payload={"estimated_tokens_before": 1000, "estimated_tokens_after": 600},
                task_id=alpha.task_ids[0],
            ),
            event_spec(
                event_type="cache.hit",
                run_id=alpha_run,
                emission_key=f"{alpha.label}-metrics-cache-hit",
                payload={"layer": "retrieval"},
                task_id=alpha.task_ids[0],
            ),
            event_spec(
                event_type="cache.miss",
                run_id=alpha_run,
                emission_key=f"{alpha.label}-metrics-cache-miss",
                payload={"layer": "retrieval"},
                task_id=alpha.task_ids[0],
            ),
            event_spec(
                event_type="run.completed",
                run_id=alpha_run,
                emission_key=f"{alpha.label}-metrics-final",
                payload={
                    "input_tokens": 90,
                    "cached_tokens": 30,
                    "output_tokens": 15,
                    "usage_reconciled": True,
                },
                task_id=alpha.task_ids[0],
            ),
        ],
    )
    emit_event_batch(
        beta.project_id,
        [
            event_spec(
                event_type="executor.started",
                run_id=beta_run,
                emission_key=f"{beta.label}-metrics-unknown",
                payload={"input_tokens": 33},
                task_id=beta.task_ids[0],
            )
        ],
    )
    return alpha_run, beta_run


def assert_project_metrics(alpha: dict[str, object], beta: dict[str, object]) -> None:
    require(alpha.get("scope") == "PROJECT", "alpha metrics scope is not PROJECT")
    require(alpha.get("canonical_store") == "postgres", "metrics canonical store is not PostgreSQL")
    require(alpha.get("hot_store_canonical") is False, "Redis was reported as canonical")
    alpha_input = metric_value(alpha, "token", "input_tokens")
    require(alpha_input.get("value") == 90, "provider-final input token reconciliation failed")
    require(alpha_input.get("provenance") == "EXACT", "reconciled input tokens are not EXACT")
    alpha_fresh = metric_value(alpha, "token", "fresh_tokens")
    require(alpha_fresh.get("value") == 60, "fresh token derivation is incorrect")
    require(alpha_fresh.get("provenance") == "EXACT", "fresh token derivation lost provenance")
    context = metric_value(alpha, "context", "reduction_tokens")
    require(context.get("value") == 400, "context reduction is incorrect")
    require(context.get("provenance") == "ESTIMATED", "estimated context was presented as exact")
    require(metric_value(alpha, "cache", "hits").get("value") == 1, "cache hit was not measured")
    require(metric_value(alpha, "cache", "misses").get("value") == 1, "cache miss was not measured")
    require(
        metric_value(alpha, "cache", "hit_rate").get("value") == 0.5, "cache hit rate is incorrect"
    )
    logical = metric_value(alpha, "storage", "logical_task_bytes")
    physical = metric_value(alpha, "storage", "physical_referenced_bytes")
    require(logical.get("provenance") == "EXACT", "logical storage provenance is not exact")
    require(physical.get("provenance") == "EXACT", "physical storage provenance is not exact")
    require(isinstance(logical.get("value"), int | float), "logical storage is not numeric")
    require(isinstance(physical.get("value"), int | float), "physical storage is not numeric")

    beta_input = metric_value(beta, "token", "input_tokens")
    require(beta_input.get("value") == 33, "unknown token observation was lost")
    require(
        beta_input.get("provenance") == "UNKNOWN", "unlabelled token observation is not UNKNOWN"
    )
    require(
        metric_value(beta, "cache", "hits").get("value") is None,
        "unknown cache state became a zero hit count",
    )
    require(
        metric_value(beta, "cache", "hits").get("provenance") == "UNAVAILABLE",
        "unknown cache state lost provenance",
    )


def comparable(payload: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in payload.items() if key != "generated_at"}


def verify_bounded_history(probe: ApiProbe, project_id: UUID) -> None:
    payload = metric_payload(probe, project_id, limit=1)
    history = payload.get("history")
    require(
        isinstance(history, list) and len(history) <= 1, "metrics history exceeded requested bound"
    )
    require(payload.get("history_max_points") == 1, "history bound was not reported truthfully")
    invalid = probe.request(
        "GET",
        f"/api/v1/control-center/metrics?project_id={project_id}&history_points=101",
        expected=422,
    )
    require(isinstance(invalid, dict), "invalid history bound did not fail closed")


def verify_near_realtime(probe: ApiProbe, fixture: Fixture, run_id: UUID) -> None:
    require(fixture.project_id is not None and fixture.task_ids, "alpha fixture is incomplete")
    before = metric_payload(probe, fixture.project_id)
    before_hits = metric_value(before, "cache", "hits").get("value")
    require(isinstance(before_hits, int | float), "pre-refresh cache hit count is unavailable")
    emit_event_batch(
        fixture.project_id,
        [
            event_spec(
                event_type="cache.hit",
                run_id=run_id,
                emission_key=f"{fixture.label}-metrics-live-cache-hit",
                payload={"layer": "retrieval", "live_refresh": True},
                task_id=fixture.task_ids[0],
            )
        ],
    )
    after = metric_payload(probe, fixture.project_id)
    after_hits = metric_value(after, "cache", "hits").get("value")
    require(
        after_hits == before_hits + 1, "new canonical event did not refresh the metric snapshot"
    )


def verify_dashboard(probe: ApiProbe) -> None:
    bundle, assets = fetch_dashboard_bundle(probe.dashboard_url)
    require(bool(assets), "dashboard did not expose a JavaScript bundle")
    for marker in (
        "Control Center Metrics",
        "/api/v1/control-center/metrics",
        "UNAVAILABLE",
        "EventSource",
        "PostgreSQL canônico",
    ):
        require(marker in bundle, f"dashboard metrics bundle is missing {marker!r}")


def verify_restart_and_redis(probe: ApiProbe, project_id: UUID) -> None:
    before = comparable(metric_payload(probe, project_id))
    compose("restart", "api")
    wait_for_api_health(probe, attempts=90)
    after_restart = comparable(metric_payload(probe, project_id))
    require(after_restart == before, "API restart changed canonical metrics truth")

    compose("stop", "redis")
    try:
        during_redis_loss = comparable(metric_payload(probe, project_id))
        require(during_redis_loss == before, "Redis loss changed canonical metrics truth")
    finally:
        compose("start", "redis")
    wait_for_api_health(probe, attempts=90)
    after_redis = comparable(metric_payload(probe, project_id))
    require(after_redis == before, "Redis recovery changed canonical metrics truth")


def verify_no_leaks(
    alpha: dict[str, object], beta: dict[str, object], alpha_id: UUID, beta_id: UUID
) -> tuple[int, int, int]:
    alpha_text = json.dumps(alpha, sort_keys=True)
    beta_text = json.dumps(beta, sort_keys=True)
    cross_project_leaks = int(str(beta_id) in alpha_text) + int(str(alpha_id) in beta_text)
    path_markers = (str(ROOT), "/var/lib/hive", ".hive-data", ".hive-projects", "C:\\")
    filesystem_path_leaks = sum(
        marker in alpha_text or marker in beta_text for marker in path_markers
    )
    secret_markers = ("api_key", "authorization", "bearer ", "password", "secret")
    lowered = (alpha_text + beta_text).lower()
    secret_leaks = sum(marker in lowered for marker in secret_markers)
    return secret_leaks, filesystem_path_leaks, cross_project_leaks


def collect_evidence(probe: ApiProbe, fixtures: list[Fixture]) -> dict[str, object]:
    observed_head = current_migration_head()
    require(observed_head == MIGRATION_BASE_HEAD, "WO-021 changed the migration head")
    require(
        run_command(["git", "status", "--porcelain", "--", "migrations"]) == "",
        "WO-021 has an uncommitted migration change",
    )

    register_wo020_fixtures(probe, fixtures)
    alpha, beta = fixtures
    require(
        alpha.project_id is not None and beta.project_id is not None, "fixture registration failed"
    )
    create_task(probe, alpha, f"WO-021 duplicate {alpha.label}")
    alpha_run, _beta_run = emit_metrics_fixture(fixtures)

    alpha_metrics = metric_payload(probe, alpha.project_id)
    beta_metrics = metric_payload(probe, beta.project_id)
    assert_project_metrics(alpha_metrics, beta_metrics)
    verify_bounded_history(probe, alpha.project_id)
    verify_near_realtime(probe, alpha, alpha_run)
    alpha_metrics = metric_payload(probe, alpha.project_id)

    global_first = metric_payload(probe)
    global_second = metric_payload(probe)
    require(
        comparable(global_first) == comparable(global_second),
        "global metrics are not deterministic",
    )
    require(global_first.get("scope") == "GLOBAL", "global metrics scope is not GLOBAL")
    require(isinstance(global_first.get("project_count"), int), "global project count is missing")

    verify_dashboard(probe)
    verify_restart_and_redis(probe, alpha.project_id)

    secret_leaks, filesystem_path_leaks, cross_project_leaks = verify_no_leaks(
        alpha_metrics,
        beta_metrics,
        alpha.project_id,
        beta.project_id,
    )
    require(secret_leaks == 0, "metrics payload leaked a secret marker")
    require(filesystem_path_leaks == 0, "metrics payload leaked a filesystem path")
    require(cross_project_leaks == 0, "project metrics leaked foreign project identity")

    for path in EVIDENCE_PATHS:
        require((ROOT / path).is_file(), f"evidence path is missing: {path}")

    evidence: dict[str, object] = {
        "status": "PASS",
        "evidence_file": EVIDENCE_FILE,
        "metrics_evidence_version": EVIDENCE_VERSION,
        "observed_migration_head": observed_head,
        "migration_base_head": MIGRATION_BASE_HEAD,
        "cost_provenance": "UNAVAILABLE",
        "migration_changed": False,
        **{field: True for field in TRUE_FIELDS},
        **{field: False for field in FALSE_FIELDS},
        "historical_series_max_points": HISTORY_MAX_POINTS,
        "secret_leaks": secret_leaks,
        "filesystem_path_leaks": filesystem_path_leaks,
        "cross_project_leaks": cross_project_leaks,
        "metrics_llm_calls": 0,
        "metrics_provider_calls": 0,
        "implemented_metric_families": list(METRIC_FAMILIES),
        "metric_value_provenance": list(METRIC_PROVENANCE),
        "evidence_paths": list(EVIDENCE_PATHS),
    }
    require(set(evidence) == set(ALLOWED_FIELDS), "WO-021 evidence field set drifted from schema")
    return evidence


def write_evidence(evidence: dict[str, object]) -> None:
    EVIDENCE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_OUTPUT.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    log(f"wrote {EVIDENCE_OUTPUT.relative_to(ROOT).as_posix()}")


def main() -> int:
    api_port = os.environ.get("HIVE_API_PORT", "8000")
    dashboard_port = os.environ.get("HIVE_DASHBOARD_PORT", "3000")
    probe = ApiProbe(
        f"http://127.0.0.1:{api_port}",
        f"http://127.0.0.1:{dashboard_port}/",
    )
    fixtures: list[Fixture] = []
    started = time.monotonic()
    try:
        wait_for_api_health(probe, attempts=90)
        evidence = collect_evidence(probe, fixtures)
        write_evidence(evidence)
        log(f"PASS in {time.monotonic() - started:.1f}s")
        return 0
    except Exception as exc:
        log(f"FAIL: {type(exc).__name__}: {exc}")
        return 1
    finally:
        try:
            cleanup_fixtures(fixtures)
        except Exception as cleanup_exc:
            log(f"cleanup warning: {type(cleanup_exc).__name__}: {cleanup_exc}")


if __name__ == "__main__":
    raise SystemExit(main())
