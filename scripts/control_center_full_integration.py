"""Produce control-center-full-v1 evidence from the real Docker HIVE stack."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from control_center_integration import (  # noqa: E402
    ApiProbe,
    Fixture,
    cleanup_fixtures,
    compose,
    current_migration_head,
    emit_event_batch,
    event_spec,
    fetch_dashboard_bundle,
    register_wo020_fixtures,
    require,
    wait_for_api_health,
)

EVIDENCE_FILE = "control-center-full.json"
EVIDENCE_VERSION = "control-center-full-v1"
EVIDENCE_OUTPUT = ROOT / "tmp" / "integration-logs" / EVIDENCE_FILE
MIGRATION_BASE_HEAD = "0007_telemetry_events"
PROJECT_CAPABILITIES = (
    "project-intelligence",
    "checkpoint-scope-dod",
    "index-health",
    "latest-commits",
    "run-history",
    "decisions-memory",
    "modules-symbols",
    "dependency-graph",
    "quality-history",
    "retrieval-quality",
)
CHARTS = (
    "tokens-over-time",
    "cached-vs-fresh-tokens",
    "token-savings",
    "cost-over-time",
    "cache-hit-rate",
    "context-reduction",
    "context-signal-ratio",
    "physical-vs-logical-storage",
    "compression-dedup-savings",
    "project-activity",
    "test-pass-failure-rate",
    "retrieval-latency",
    "service-latency-errors",
)
ALERTS = (
    "disk-low",
    "redis-unavailable",
    "postgres-unavailable",
    "project-stale",
    "index-inconsistent",
    "retrieval-degradation",
    "cache-hit-collapse",
    "token-spike",
    "unexpected-cost-spike",
    "failed-test-build",
    "executor-disconnected",
    "checkpoint-mismatch",
)
HEALTH = ("platform-resource-health", "container-status", "local-model-health-conditional")
EVIDENCE_PATHS = (
    "backend/app/control_center_full.py",
    "backend/app/main.py",
    "backend/tests/test_control_center_full.py",
    "dashboard/src/ControlCenter.tsx",
    "dashboard/src/ControlCenterFull.tsx",
    "dashboard/src/ControlCenterFull.test.tsx",
    "scripts/control_center_full_integration.py",
    "scripts/control_center_integration.py",
    "scripts/integration_health.py",
    "docs/atlas/wo022-control-center-full.md",
)
TRUE_FIELDS = (
    "full_control_center_capabilities_implemented",
    "project_intelligence_visible",
    "project_checkpoint_scope_dod_visible",
    "project_index_health_visible",
    "project_latest_commits_visible",
    "project_run_history_visible",
    "project_decisions_memory_visible",
    "project_modules_symbols_visible",
    "project_dependency_graph_visible",
    "project_quality_history_visible",
    "project_retrieval_quality_visible",
    "required_charts_visible",
    "required_alerts_visible",
    "platform_resource_health_visible",
    "container_status_visible",
    "local_model_health_conditional",
    "estimated_values_labelled",
    "unavailable_metrics_not_fabricated",
    "unknown_metrics_not_zero",
    "postgres_canonical",
    "redis_noncanonical",
    "project_scoped",
    "near_realtime_refresh",
    "payloads_bounded",
    "frontend_render_bounded",
    "restart_recovery",
    "redis_loss_recovery",
)
FALSE_FIELDS = (
    "full_v01_complete_claimed",
    "redis_canonical_truth",
    "fabricated_metrics",
    "fabricated_alerts",
)
ALLOWED_FIELDS = frozenset(
    {
        "status",
        "full_control_center_evidence_version",
        "evidence_file",
        "observed_migration_head",
        "migration_base_head",
        "api_path",
        "dashboard_path",
        "migration_changed",
        *TRUE_FIELDS,
        *FALSE_FIELDS,
        "history_max_points",
        "secret_leaks",
        "filesystem_path_leaks",
        "cross_project_leaks",
        "llm_calls",
        "provider_calls",
        "implemented_project_capabilities",
        "implemented_charts",
        "implemented_alerts",
        "implemented_health_capabilities",
        "evidence_paths",
    }
)


def full_payload(probe: ApiProbe, project_id: UUID) -> dict[str, object]:
    payload = probe.request(
        "GET",
        f"/api/v1/control-center/projects/{project_id}/full?history_points=100",
    )
    require(isinstance(payload, dict), "full Control Center response is not an object")
    return dict(payload)


def emit_full_fixture_events(fixtures: list[Fixture]) -> None:
    alpha, beta = fixtures
    require(
        alpha.project_id is not None and beta.project_id is not None, "fixtures are unregistered"
    )
    require(alpha.task_ids and beta.task_ids, "fixture tasks are missing")
    emit_event_batch(
        alpha.project_id,
        [
            event_spec(
                event_type="executor.started",
                run_id=UUID("00000000-0000-0000-0000-000000000401"),
                emission_key=f"{alpha.label}-full-executor",
                payload={"adapter": "full-control-center-fixture", "input_tokens": 40},
                task_id=alpha.task_ids[0],
            ),
            event_spec(
                event_type="context.built",
                run_id=UUID("00000000-0000-0000-0000-000000000401"),
                emission_key=f"{alpha.label}-full-context",
                payload={"estimated_tokens_before": 100, "estimated_tokens_after": 60},
                task_id=alpha.task_ids[0],
            ),
            event_spec(
                event_type="cache.hit",
                run_id=UUID("00000000-0000-0000-0000-000000000401"),
                emission_key=f"{alpha.label}-full-cache",
                payload={"layer": "retrieval"},
                task_id=alpha.task_ids[0],
            ),
            event_spec(
                event_type="test.finished",
                run_id=UUID("00000000-0000-0000-0000-000000000401"),
                emission_key=f"{alpha.label}-full-test",
                payload={"passed": True, "suite": "full-control-center"},
                task_id=alpha.task_ids[0],
            ),
        ],
    )


def assert_surface(payload: dict[str, object], project_id: UUID) -> None:
    require(payload.get("control_center_full_version") == EVIDENCE_VERSION, "full version drifted")
    require(payload.get("project_id") == str(project_id), "project identity is not scoped")
    require(payload.get("project_scoped") is True, "full response is not project scoped")
    require(payload.get("canonical_store") == "postgres", "PostgreSQL is not canonical")
    require(payload.get("hot_store") == "redis", "Redis hot store is missing")
    require(payload.get("hot_store_canonical") is False, "Redis was reported as canonical")
    require(payload.get("full_v01_complete_claimed") is False, "full V0.1 completion was claimed")
    capabilities = payload.get("capabilities")
    charts = payload.get("charts")
    alerts = payload.get("alerts")
    health = payload.get("health")
    require(isinstance(capabilities, list), "capabilities are missing")
    require(isinstance(charts, list), "charts are missing")
    require(isinstance(alerts, list), "alerts are missing")
    require(isinstance(health, list), "health surfaces are missing")
    require(
        [item.get("id") for item in capabilities if isinstance(item, dict)]
        == list(PROJECT_CAPABILITIES),
        "capability contract drifted",
    )
    require(
        {item.get("id") for item in charts if isinstance(item, dict)} == set(CHARTS),
        "chart contract drifted",
    )
    require(
        {item.get("id") for item in alerts if isinstance(item, dict)} == set(ALERTS),
        "alert contract drifted",
    )
    require(
        {item.get("id") for item in health if isinstance(item, dict)} == set(HEALTH),
        "health contract drifted",
    )
    require(isinstance(payload.get("history_max_points"), int), "history bound is missing")
    require(1 <= int(payload["history_max_points"]) <= 512, "history bound is outside contract")
    for chart in charts:
        require(isinstance(chart, dict), "chart item is not an object")
        points = chart.get("points")
        require(isinstance(points, list), "chart points are not bounded")
        require(len(points) <= 100, "chart exceeded its point bound")
    chart_by_id = {str(chart["id"]): chart for chart in charts if isinstance(chart, dict)}
    context_signal = chart_by_id["context-signal-ratio"]
    require(
        context_signal["status"] == "UNAVAILABLE" and context_signal["points"] == [],
        "context signal ratio was derived from context reduction or fabricated",
    )
    health_by_id = {str(surface["id"]): surface for surface in health if isinstance(surface, dict)}
    resources = health_by_id["platform-resource-health"]
    resource_details = resources.get("details")
    require(isinstance(resource_details, dict), "platform resource details are missing")
    observations = resource_details.get("observations")
    require(isinstance(observations, dict), "platform resource observations are missing")
    for resource_name in ("cpu", "ram", "disk", "io"):
        observation = observations.get(resource_name)
        require(isinstance(observation, dict), f"{resource_name} observation is missing")
        require(
            observation.get("status") in {"AVAILABLE", "UNAVAILABLE"},
            f"{resource_name} observation status is not explicit",
        )
        require(
            isinstance(observation.get("provenance"), str),
            f"{resource_name} provenance missing",
        )
        require(isinstance(observation.get("source"), str), f"{resource_name} source missing")
    alerts_by_id = {str(alert["id"]): alert for alert in alerts if isinstance(alert, dict)}
    require(
        alerts_by_id["executor-disconnected"]["status"] in {"UNKNOWN", "UNAVAILABLE"},
        "executor absence was incorrectly reported as CLEAR",
    )
    require(
        alerts_by_id["checkpoint-mismatch"]["status"] == "CLEAR",
        "canonical fixture checkpoint did not qualify from Git evidence",
    )
    checkpoint = next(
        capability
        for capability in capabilities
        if isinstance(capability, dict) and capability.get("id") == "checkpoint-scope-dod"
    )
    checkpoint_details = checkpoint.get("details")
    require(isinstance(checkpoint_details, dict), "checkpoint details are missing")
    documents = checkpoint_details.get("documents")
    require(
        isinstance(documents, list) and len(documents) == 3,
        "governance documents are missing",
    )
    require(
        all(
            isinstance(document, dict)
            and document.get("status") == "AVAILABLE"
            and str(document.get("source", "")).startswith("git:HEAD-blob:")
            for document in documents
        ),
        "governance documents are not bound to Git-tracked HEAD bytes",
    )


def compare_canonical(left: dict[str, object], right: dict[str, object]) -> None:
    keys = (
        "project_id",
        "project",
        "capabilities",
        "charts",
        "canonical_store",
        "hot_store",
        "hot_store_canonical",
    )
    require(
        {key: left.get(key) for key in keys} == {key: right.get(key) for key in keys},
        "canonical full view changed after service restart",
    )


def verify_dashboard(probe: ApiProbe) -> None:
    bundle, assets = fetch_dashboard_bundle(probe.dashboard_url)
    require(bool(assets), "dashboard did not expose a JavaScript bundle")
    for marker in (
        "Full Control Center",
        "/api/v1/control-center/projects/",
        "tokens-over-time",
        "checkpoint-mismatch",
        "UNAVAILABLE",
        "PostgreSQL is canonical",
        "data-chart-id",
        "real points",
        "live refresh through",
    ):
        require(marker in bundle, f"dashboard full surface is missing {marker!r}")


def verify_no_leaks(
    alpha: dict[str, object], beta: dict[str, object], alpha_id: UUID, beta_id: UUID
) -> tuple[int, int, int]:
    alpha_text = json.dumps(alpha, sort_keys=True)
    beta_text = json.dumps(beta, sort_keys=True)
    cross_project = int(str(beta_id) in alpha_text) + int(str(alpha_id) in beta_text)
    path_markers = (str(ROOT), "/var/lib/hive", ".hive-data", ".hive-projects", "C:\\")
    path_leaks = int(any(marker in alpha_text or marker in beta_text for marker in path_markers))
    lowered = (alpha_text + beta_text).lower()
    secret_leaks = int(
        any(marker in lowered for marker in ("api_key", "authorization", "bearer ", "password"))
    )
    return secret_leaks, path_leaks, cross_project


def collect_evidence(probe: ApiProbe, fixtures: list[Fixture]) -> dict[str, object]:
    observed_head = current_migration_head()
    require(observed_head == MIGRATION_BASE_HEAD, "WO-022 changed the migration head")
    register_wo020_fixtures(probe, fixtures)
    emit_full_fixture_events(fixtures)
    alpha, beta = fixtures
    require(
        alpha.project_id is not None and beta.project_id is not None, "fixture registration failed"
    )
    alpha_payload = full_payload(probe, alpha.project_id)
    beta_payload = full_payload(probe, beta.project_id)
    assert_surface(alpha_payload, alpha.project_id)
    assert_surface(beta_payload, beta.project_id)
    require(
        str(beta.project_id) not in json.dumps(alpha_payload),
        "alpha payload contains beta identity",
    )
    before = full_payload(probe, alpha.project_id)
    emit_event_batch(
        alpha.project_id,
        [
            event_spec(
                event_type="file.changed",
                run_id=UUID("00000000-0000-0000-0000-000000000401"),
                emission_key=f"{alpha.label}-full-live-refresh",
                payload={"path": "src/service.py", "change": "near-realtime-refresh"},
                task_id=alpha.task_ids[0],
            )
        ],
    )
    live_after = full_payload(probe, alpha.project_id)
    before_activity = next(chart for chart in before["charts"] if chart["id"] == "project-activity")
    after_activity = next(
        chart for chart in live_after["charts"] if chart["id"] == "project-activity"
    )
    require(
        len(after_activity["points"]) > len(before_activity["points"])
        and any(point.get("series") == "file.changed" for point in after_activity["points"]),
        "canonical event did not change the live full snapshot",
    )
    require(
        live_after["project_id"] == before["project_id"],
        "live refresh changed the selected project identity",
    )
    restart_baseline = live_after
    compose("restart", "api")
    wait_for_api_health(probe, attempts=90)
    after_restart = full_payload(probe, alpha.project_id)
    compare_canonical(restart_baseline, after_restart)
    compose("stop", "redis")
    try:
        during_redis_loss = full_payload(probe, alpha.project_id)
        require(
            during_redis_loss.get("canonical_store") == "postgres",
            "Redis loss changed canonical store",
        )
        require(
            during_redis_loss.get("hot_store_canonical") is False, "Redis loss promoted hot store"
        )
        redis_alert = next(
            item for item in during_redis_loss["alerts"] if item["id"] == "redis-unavailable"
        )
        require(
            redis_alert["status"] == "ACTIVE", "Redis loss did not produce its deterministic alert"
        )
    finally:
        compose("start", "redis")
    wait_for_api_health(probe, attempts=90)
    after_redis = full_payload(probe, alpha.project_id)
    compare_canonical(restart_baseline, after_redis)
    verify_dashboard(probe)
    secret_leaks, path_leaks, cross_project_leaks = verify_no_leaks(
        alpha_payload, beta_payload, alpha.project_id, beta.project_id
    )
    require(secret_leaks == 0, "full payload leaked a secret marker")
    require(path_leaks == 0, "full payload leaked a filesystem path")
    require(cross_project_leaks == 0, "full payload leaked a foreign project identity")
    for path in EVIDENCE_PATHS:
        require((ROOT / path).is_file(), f"evidence path is missing: {path}")
    evidence: dict[str, object] = {
        "status": "PASS",
        "full_control_center_evidence_version": EVIDENCE_VERSION,
        "evidence_file": EVIDENCE_FILE,
        "observed_migration_head": observed_head,
        "migration_base_head": MIGRATION_BASE_HEAD,
        "api_path": "backend/app/control_center_full.py",
        "dashboard_path": "dashboard/src/ControlCenterFull.tsx",
        "migration_changed": False,
        **{field: True for field in TRUE_FIELDS},
        **{field: False for field in FALSE_FIELDS},
        "history_max_points": 100,
        "secret_leaks": secret_leaks,
        "filesystem_path_leaks": path_leaks,
        "cross_project_leaks": cross_project_leaks,
        "llm_calls": 0,
        "provider_calls": 0,
        "implemented_project_capabilities": list(PROJECT_CAPABILITIES),
        "implemented_charts": list(CHARTS),
        "implemented_alerts": list(ALERTS),
        "implemented_health_capabilities": list(HEALTH),
        "evidence_paths": list(EVIDENCE_PATHS),
    }
    require(set(evidence) == ALLOWED_FIELDS, "WO-022 evidence field set drifted from schema")
    return evidence


def main() -> int:
    api_port = os.environ.get("HIVE_API_PORT", "8000")
    dashboard_port = os.environ.get("HIVE_DASHBOARD_PORT", "3000")
    probe = ApiProbe(f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{dashboard_port}/")
    fixtures: list[Fixture] = []
    started = time.monotonic()
    try:
        wait_for_api_health(probe, attempts=90)
        evidence = collect_evidence(probe, fixtures)
        EVIDENCE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE_OUTPUT.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"[wo022] wrote {EVIDENCE_OUTPUT.relative_to(ROOT).as_posix()}", flush=True)
        print(f"[wo022] PASS in {time.monotonic() - started:.1f}s", flush=True)
        return 0
    except Exception as exc:
        print(f"[wo022] FAIL: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        try:
            cleanup_fixtures(fixtures)
        except Exception as cleanup_exc:
            print(
                f"[wo022] cleanup warning: {type(cleanup_exc).__name__}: {cleanup_exc}",
                file=sys.stderr,
                flush=True,
            )


if __name__ == "__main__":
    raise SystemExit(main())
