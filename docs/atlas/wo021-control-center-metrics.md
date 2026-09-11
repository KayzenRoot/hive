# WO-021 — Control Center Metrics Implementation Blueprint

Status: AUTHORIZED FOR EXECUTION
Issue: #79
Authorized base: `c9430af13860ab30e31bd162991eb88c05215f4f`
Branch: `feat/wo021-control-center-metrics`
Evidence contract: `control-center-metrics-v1`
Migration head: `0007_telemetry_events` (MUST remain unchanged)

## Objective
Implement the smallest production-capable metrics/observability increment for the existing HIVE Control Center. The increment must expose truthful, project-scoped token, context, cache and storage metrics with bounded history and deterministic global aggregation, reusing existing telemetry/event, PostgreSQL, CAS and dashboard seams.

This Work Order does not implement the full Control Center and must not claim V0.1 completion.

## Authority and truth boundaries
- PostgreSQL remains canonical for durable project/event truth.
- Redis remains noncanonical and cannot become required for correctness.
- Existing canonical telemetry events are the primary runtime observation seam.
- Provider-final token usage may be EXACT only when explicit reconciled/provider receipt evidence exists.
- Local token estimates remain ESTIMATED.
- Missing values remain UNAVAILABLE or UNKNOWN and never become zero/success/hit.
- Cache hit/miss is counted only from actual canonical `cache.hit` / `cache.miss` events or already-approved provider receipts.
- No LLM/provider call may be made merely to compute dashboard metrics.
- No absolute filesystem path, secret, provider credential, raw environment or cross-project data may appear in API/dashboard/evidence payloads.

## Frozen value provenance
Every externally visible metric value that can be uncertain uses one of:
- `EXACT`
- `ESTIMATED`
- `UNAVAILABLE`
- `UNKNOWN`

No alternate vocabulary is permitted in this increment.

## Metric families
### 1. Token
Read only approved token keys already accepted by telemetry sanitization (`input_tokens`, `output_tokens`, `cached_tokens`, `fresh_tokens`, `token_count`, `token_budget`, `token_savings`) and provider usage receipts already present in the codebase.

Rules:
- Do not infer cached tokens from repeated prompts.
- When total input and cached input are both exact, `fresh = max(total - cached, 0)` may be exact.
- When a local estimator produced a value, label it ESTIMATED.
- Provider-final values override earlier estimates only through explicit reconciliation identity/provenance.
- Unknown/missing token usage is not zero.

### 2. Context
Expose bounded context-flow measurements when the underlying canonical events/evidence provide them, including available/budget, retrieved, post-selection/rerank/dedup when represented, sent/final context, and reduction.

Rules:
- Preserve source/provenance for each available stage.
- Reduction is computed only when both numerator/denominator are valid and compatible.
- If the event stream cannot prove a stage, return UNAVAILABLE/UNKNOWN rather than inventing it.

### 3. Cache
Aggregate actual cache decisions from canonical `cache.hit` and `cache.miss` events and approved provider prompt-cache receipts.

Rules:
- Expose hits, misses, total observed decisions and hit rate only when denominator > 0.
- No observed decisions => hit rate UNAVAILABLE/UNKNOWN, not 0%.
- Redis availability is health/context only; it is not itself a cache-hit metric.
- Provider prompt-cache truth requires provider support/receipt already modeled by existing code.

### 4. Storage
Expose logical vs physical storage only from existing durable metadata/CAS/storage evidence or filesystem-safe aggregate observations that do not leak paths.

Rules:
- Keep logical and physical values distinct.
- Derived saved bytes/ratio require compatible exact measurements.
- PostgreSQL/CAS/Redis/artifact categories may be displayed only when measurable without new canonical schema.
- Redis is never canonical storage truth.

## Backend plan
Preferred new module: `backend/app/control_center_metrics.py`.

Responsibilities:
1. Define frozen provenance enum and bounded response DTOs.
2. Query project-scoped canonical telemetry using existing telemetry APIs/helpers rather than duplicating event-store SQL unless a bounded read query is materially simpler and preserves the same filters/order.
3. Aggregate token/context/cache metrics deterministically.
4. Read existing storage/CAS metadata using current repository/storage helpers. Do not add migrations.
5. Produce bounded historical series, default/maximum chosen once and <= 512 points; preferred evidence target 128 points.
6. Produce project-scoped summary and global aggregate where global = deterministic composition of project summaries, never a separate conflicting truth source.
7. Preserve generated_at/observed_at and provenance needed to distinguish live estimate from reconciled final value.
8. Fail closed or return explicit unavailable values when dependencies are unavailable; never fabricate operational health.

Preferred API surface under existing Control Center namespace:
- `GET /api/v1/control-center/metrics?project_id=<uuid>` for project-scoped metrics.
- `GET /api/v1/control-center/metrics/global` for deterministic aggregation across registered projects.

If existing routing conventions require a slightly different path, that is an OPEN_LOCAL choice only if semantics remain identical and tests/documentation use one canonical path.

Do not create write endpoints.

## Dashboard plan
Integrate metrics into the existing `dashboard/src/ControlCenter.tsx`; do not create a second dashboard application.

Add a `Metrics` view or bounded metrics surface that shows:
- tokens: input/fresh/cached/output/savings where available, with EXACT/ESTIMATED/UNAVAILABLE/UNKNOWN badges;
- context: stage values + reduction percentage only when valid;
- cache: observed hits/misses/hit rate with explicit no-observation state;
- storage: logical/physical/saved values with provenance;
- bounded historical mini-series or tables from backend data;
- project/global selector consistent with existing Control Center project selection.

UI rules:
- Unknown/unavailable never renders as `0`.
- Estimated values visibly say ESTIMATED.
- Exact and estimated values are not merged into one unlabeled number.
- No fake cost field. `cost_provenance` remains UNAVAILABLE unless explicit pricing provenance exists, which is out of scope for WO-021.
- Existing Fleet/Project/Runs/Health/Tests/Errors behavior must not regress.

## Near-real-time behavior
Reuse existing SSE + bounded replay/reconciliation behavior. Do not add WebSocket or a second event bus.

A metrics snapshot may refresh on relevant canonical events and/or the existing bounded snapshot cadence. Keep implementation deterministic and avoid per-event unbounded recomputation.

Relevant event classes include context, cache, executor/run and other existing canonical events carrying accepted numeric metrics. Metrics aggregation must ignore unrelated payloads safely.

## Integration/evidence plan
Add a dedicated script such as `scripts/control_center_metrics_integration.py` and wire it into existing integration-health execution through an allowed script change.

The integration must generate `tmp/integration-logs/control-center-metrics.json` matching the already-merged `control-center-metrics-v1` closed contract.

The evidence must prove at minimum:
- all four metric families implemented;
- exact/estimated/unavailable/unknown provenance preserved;
- final provider reconciliation supported without provider calls during the test;
- no fabricated provider usage/cache hit/cost;
- unknown metrics not zero;
- context reduction measured with provenance;
- cache hit/miss from real event/receipt fixtures;
- logical/physical storage measured with provenance;
- bounded history <= 512;
- near-real-time refresh behavior;
- project isolation and deterministic global aggregation;
- PostgreSQL canonical / Redis noncanonical;
- restart and Redis-loss recovery;
- bounded backend payload and frontend render;
- zero secret/path/cross-project leaks;
- zero metrics LLM/provider calls;
- migration unchanged at `0007_telemetry_events`;
- `full_control_center_claimed=false`;
- `full_v01_complete_claimed=false`.

## Required tests
Backend:
- aggregation for each metric family;
- exact vs estimated reconciliation;
- missing/unknown values;
- cache denominator zero;
- project isolation;
- deterministic global aggregation;
- bounded history and payload size;
- database/Redis loss semantics;
- secrets/path sanitization;
- no migration/dependency assumptions.

Dashboard:
- all four families render;
- provenance labels render;
- UNKNOWN/UNAVAILABLE do not render as zero;
- project/global selection;
- near-real-time refresh/reconciliation;
- existing Control Center views continue to work;
- bounded historical UI does not grow unbounded.

Integration:
- two-project fixture proving isolation and deterministic aggregate;
- restart API/PostgreSQL-compatible path and Redis-loss path;
- evidence JSON validates through Review Evidence.

## Change surface
MUST/LIKELY:
- `backend/app/control_center_metrics.py` (preferred new module)
- `backend/tests/test_control_center_metrics.py` (preferred)
- `dashboard/src/ControlCenter.tsx`
- `dashboard/src/ControlCenter.test.tsx`
- `scripts/control_center_metrics_integration.py` (preferred)
- `scripts/integration_health.py`
- `docs/atlas/wo021-control-center-metrics.md`

WATCH ONLY / DO NOT MODIFY:
- `backend/tests/test_review_evidence.py`
- `schemas/review-evidence-v1.schema.json`
- `scripts/review_evidence.py`
- `scripts/review_pr_body.py`
- `migrations/**`
- `.github/**`
- dependency manifests/lockfiles
- `VERSION`, `CHANGELOG.md`, release assets
- `docs/project-brain/**`

## Decision budget
FROZEN:
- source-of-truth boundaries;
- four metric families;
- provenance vocabulary;
- migration head;
- no provider/LLM metric calls;
- no fake cost/cache/token values;
- project isolation;
- Review Evidence closed contract.

BOUNDED:
- exact module/function names;
- history default, but must be deterministic, bounded and <= 512;
- whether global aggregation reuses project summaries in memory or a bounded server helper, provided the result is deterministic and project isolation tests prove correctness;
- UI layout inside the existing Control Center.

ESCALATE:
- any need for a migration;
- dependency change;
- CI/workflow change;
- new canonical event type;
- Project Brain/checkpoint mutation;
- modification of the four WO-021-G1 governance files;
- external provider call required to obtain a metric;
- inability to satisfy the closed Review Evidence contract without expanding scope.

## FailureShield
Prevent these known failure modes:
- unknown metric silently shown as zero;
- estimated token count shown as exact;
- repeated request treated as provider cache hit;
- Redis treated as canonical state;
- path/secret leakage through metric provenance;
- cross-project metrics mixed by global aggregation;
- history array growing without bound;
- evidence generated from a stale head;
- product PR modifying its own evidence schema/verifier;
- full Control Center/V0.1 completion overclaim.

## Git/PR contract
- Base: exact current protected `main` initially `c9430af13860ab30e31bd162991eb88c05215f4f`.
- Branch: `feat/wo021-control-center-metrics`.
- Issue: #79.
- PR must be Ready, not draft, and remain unmerged for SOL audit.
- PR body must be rendered by the existing `scripts/review_pr_body.py` WO-021 renderer.
- Auto-merge remains unarmed until governance allows it.
- Final evidence must bind the exact PR HEAD.

## STOP CONDITION
Return COMPLETE only when all implementation tests pass, integration evidence generates a valid `control-center-metrics-v1` PASS artifact, GitHub required checks are green at the exact final head, migration/dependency/CI/release/canonical Project Brain boundaries remain unchanged, no HIGH/CRITICAL unresolved defect exists, and the PR is ready for independent SOL audit. Otherwise return BLOCKED with the precise failed gate.