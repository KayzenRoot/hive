# WO-021 — Control Center Metrics Implementation Blueprint

Status: IN EXECUTION
Issue: #79
Authorized base: `2ccbf09c193ba30e78d768bb32a4e78a4f209812`
Branch: `feat/wo021-control-center-metrics-r2`
Evidence contract: `control-center-metrics-v1`
Migration head: `0007_telemetry_events` (MUST remain unchanged)

## Objective
Implement the smallest production-capable metrics/observability increment for the existing HIVE Control Center. The increment exposes truthful, project-scoped token, context, cache and storage metrics with bounded history and deterministic global aggregation, reusing existing PostgreSQL telemetry, CAS and dashboard seams.

The previous branch `feat/wo021-control-center-metrics` is historical and remains untouched. This branch starts from the post-GEF protected `main`; no force-push or history rewrite is used.

## Frozen truth boundaries
- PostgreSQL remains canonical durable truth.
- Redis remains noncanonical and cannot be required for metrics correctness.
- Canonical telemetry events are the runtime observation seam.
- Provider-final token usage is EXACT only with explicit reconciled/final provenance.
- Local estimates are ESTIMATED.
- Missing evidence is UNAVAILABLE or UNKNOWN, never zero by invention.
- Cache hits/misses come only from actual `cache.hit` / `cache.miss` events or an already-approved explicit receipt seam.
- Storage uses durable task/CAS metadata without exposing host paths.
- No LLM or provider call is made to manufacture metrics.

## Provenance vocabulary
Exactly: `EXACT`, `ESTIMATED`, `UNAVAILABLE`, `UNKNOWN`.

## Metric families
1. **Token** — input, output, cached, fresh, count, budget and savings when observed. Exact reconciliation supersedes estimates for the same run/metric. Fresh may be derived only from compatible input/cache observations.
2. **Context** — before/after measurements and reduction only when compatible telemetry exists; estimator-produced counts remain ESTIMATED.
3. **Cache** — exact observed decisions from canonical cache events. No decisions means UNAVAILABLE, not 0%.
4. **Storage** — exact project logical task bytes and physical bytes of distinct referenced CAS blobs, plus bounded derived savings.

## API
- `GET /api/v1/control-center/metrics?project_id=<uuid>&history_points=<1..100>`
- `GET /api/v1/control-center/metrics/global?history_points=<1..100>`

Global metrics are deterministic composition of project-scoped summaries, not a competing persistence source.

## Near-real-time
The existing project SSE + durable bounded replay remains the event transport. The metrics snapshot is refreshed on the existing bounded Control Center cadence and may be refreshed after relevant live events by the frontend. No second event bus or WebSocket is introduced.

## Scope guard
Allowed: `backend/app/**`, `backend/tests/**`, `dashboard/src/**`, `dashboard/tests/**`, `scripts/**`, `docs/atlas/**`.

Forbidden in WO-021 product PR: migrations, dependencies, CI/workflows, release/version files, canonical Project Brain/checkpoint, WO-021-G1 verifier/schema governance files.

## Acceptance evidence
`tmp/integration-logs/control-center-metrics.json` must satisfy `control-center-metrics-v1`, proving all four families, truthful provenance, unknown-not-zero behavior, context reduction, real cache decisions, logical/physical storage, bounded history, deterministic global aggregation, project isolation, API/Redis restart truth preservation, no secret/path/cross-project leaks, zero metrics LLM/provider calls, unchanged migration head, and no full-Control-Center/V0.1-complete claim.

## STOP CONDITION
WO-021 is complete only when the implementation, focused/unit/dashboard/integration tests, `control-center-metrics-v1` evidence, and exact-head `Validate`, `Integration health`, and `Review Evidence` are all PASS and Sol independently audits the final PR HEAD. Otherwise it remains IN EXECUTION or CORRECTION REQUIRED.
