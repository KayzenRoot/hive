# HIVE 1.1 — Existing Seam & Migration Map

## Status
PLANNING VERIFIED AGAINST v1.0.0 SOURCE at commit a53b5b9fcf55c32a5696180fb1b1ef80ccd1edcf.

## Objective
Tell the executor where Decision Fabric must attach to HIVE 1.0 without inventing parallel infrastructure.

## Verified backend seams
### Context fingerprints
Existing `backend/app/context_fingerprints.py`, consumed by `context_manager.py` and `delta_context.py`.
Decision fingerprints must reuse its project/basis/version discipline where semantically compatible, not replace it.

### Delta context
`backend/app/delta_context.py` already declares versioned `delta-context-v1` and `delta-json-patch-v1`.
Decision Delta is a new decision-layer primitive and must not mutate the existing context-delta contract.

### Provider prompt cache
`backend/app/provider_prompt_cache.py` already exposes preparation logic and a deterministic benchmark helper.
DecisionProvider/cache work must coexist with this provider-prefix optimization rather than create a second prompt-prefix subsystem.

### Context manager
`backend/app/context_manager.py` composes fingerprints, delta delivery and provider prompt-cache behavior.
Decision Context Projector should initially consume stable context outputs/interfaces and avoid a competing retrieval/context manager.

### Telemetry
`backend/app/telemetry.py` is explicitly the project-scoped durable Telemetry/Event Bus; PostgreSQL is canonical event storage.
Decision events extend this envelope/vocabulary. No second event bus.

### Database revision
`backend/app/db.py` identifies current schema revision `0007_telemetry_events`.
Any 1.1 durable schema begins after the current Alembic head and must be additive/reversible according to release contract. Exact migration number/name is implementation-time, after repository inspection.

### Execution / policy
`backend/app/runner.py` contains fail-closed `ToolPolicy`.
`backend/app/execution_orchestrator.py` emits deterministic provenance-backed execution events.
Decision Fabric cannot weaken ToolPolicy and cannot become a shortcut around execution admission.

### Control Center
Existing `control_center.py`, `control_center_metrics.py`, `control_center_full.py` compose registry, telemetry, health/retrieval/memory/storage views.
1.1 decision observability extends these surfaces instead of introducing a second dashboard backend.

## Verified frontend seams
`dashboard/src/eventVocabulary` is imported by Control Center and its tests through `CANONICAL_EVENT_TYPES`.
Decision event types must extend the canonical vocabulary and tests together.

## Main/API seam
`backend/app/main.py` already composes routers including retrieval, semantic retrieval, tasks and telemetry.
Any Decision Fabric API surface must follow the existing router composition style and remain project-scoped.

## Storage ownership proposal
Prefer no new canonical table for ephemeral provider responses.
Durable decision receipts are justified only when needed for audit/promotion evidence and must reference canonical telemetry/evidence rather than duplicate it.
Redis may hold derived decision cache only.
Large benchmark artifacts use existing CAS conventions where applicable.

## Expected new code boundary
Implementation may introduce a cohesive `backend/app/decision_*.py` family or package if repository conventions support it after executor inspection, but it must call existing context/fingerprint/telemetry/policy primitives through explicit interfaces.

## Migration decision gate
WO-1.1-01 should avoid a database migration unless typed contracts truly require durable state.
Later WOs may add additive tables/indexes only with:
- ownership;
- project isolation;
- constraints/indexes;
- upgrade;
- restart;
- rollback classification;
- backup/restore impact;
- data-retention impact;
- migration tests.

## Test seam
Tests must extend the existing backend/dashboard suites in their current locations and naming conventions. Do not create an isolated “Decision Fabric test universe” disconnected from repository CI.

## Anti-duplication gates
second telemetry/event bus=0;
second canonical project registry=0;
second context manager/retrieval engine=0;
second generic provider-prefix cache=0;
ToolPolicy bypass=0;
new durable truth store outside PostgreSQL/Git/CAS governance=0.

## Stop condition
This seam map is complete for planning when every 1.1 module has an existing extension point or an explicitly justified new boundary, and migrations are introduced only when evidence shows persistence is required.
