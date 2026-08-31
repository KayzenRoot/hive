# 07 — HIVE CONTROL CENTER

## Status

The Control Center is a NECESSARY V0.1 capability.

It is not a cosmetic dashboard. It is the operational interface and observability plane of HIVE.

## Home view

Show in near real time:

### Fleet
- total registered projects;
- READY;
- ACTIVE;
- INDEXING;
- DEGRADED;
- BLOCKED;
- STALE;
- OFFLINE.

### Active runs
For each run:
- project;
- task;
- executor/model;
- stage;
- elapsed time;
- current token estimate;
- cache hit rate;
- last event;
- test state;
- errors/warnings.

### Global token telemetry
- input tokens;
- fresh input tokens;
- cached input tokens;
- output tokens;
- tokens per minute;
- estimated saved tokens;
- effective cost where pricing/provider data is available;
- cost saved estimate;
- historical charts.

### Context telemetry
- available tokens;
- retrieved;
- after reranking;
- after dedup;
- sent to model;
- context reduction percentage;
- context signal ratio.

### Cache
- L1/process cache;
- Redis;
- retrieval cache;
- provider prompt cache;
- hit/miss rates;
- evictions;
- invalidations;
- memory footprint.

### Storage
- logical bytes;
- deduplicated bytes;
- compressed physical bytes;
- bytes saved;
- PostgreSQL;
- CAS;
- Redis;
- artifacts;
- logs;
- backup usage.

### Platform health
- API;
- MCP;
- PostgreSQL;
- Redis;
- indexer;
- event system;
- dashboard;
- local model services when present;
- CPU;
- RAM;
- disk utilization;
- I/O;
- container status.

## Project detail

Show:
- project overview;
- current version/phase;
- checkpoint;
- scope;
- DoD progress;
- branch/HEAD;
- index health;
- latest commits;
- current and historical runs;
- decisions;
- canonical/staged memory;
- modules/symbols;
- dependency graph summary;
- tests/build/lint/typecheck history;
- token/cost charts;
- cache charts;
- storage charts;
- retrieval quality;
- alerts.

## Run detail

Live event timeline with:
- prompt ingested;
- context phases;
- cache decisions;
- retrieval candidates;
- selected sources;
- token estimates;
- executor requests;
- tool calls;
- file changes;
- tests;
- validation;
- staged memories;
- final outcome.

## Real-time semantics

"Real time" means near-real-time operational refresh.

Use:
- WebSocket or SSE event stream;
- event persistence for replay;
- client reconciliation;
- provider-final token reconciliation when live token count was estimated.

Never present estimated live token counts as exact. Mark them as estimated until reconciled.

## Charts

Required:
- tokens over time;
- cached vs fresh tokens;
- token savings;
- cost over time;
- cache hit rate;
- context reduction;
- context signal ratio;
- physical vs logical storage;
- compression/dedup savings;
- project activity;
- test pass/failure rate;
- retrieval latency;
- service latency/errors.

## Alerts

Examples:
- disk low;
- Redis unavailable;
- PostgreSQL unavailable;
- project stale;
- index inconsistent;
- retrieval degradation;
- cache hit collapse;
- token spike;
- unexpected cost spike;
- failed test/build;
- executor disconnected;
- checkpoint mismatch.
