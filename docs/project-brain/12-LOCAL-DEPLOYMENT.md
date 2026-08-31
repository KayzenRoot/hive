# 12 — LOCAL DEPLOYMENT

## Deployment target

Single local workstation using Docker Compose.

No VPS is required for V0.1.

## Suggested service topology

- hive-api
- hive-mcp
- hive-indexer
- hive-worker
- hive-dashboard
- postgres
- redis
- optional local-embedding service
- optional local-reranker service

Exact process split may be simplified during implementation if it preserves contracts and observability.

## Persistent storage

Preferred host root:

Windows example:
`D:\HIVE\`

Linux example:
`/mnt/hive/`

Recommended structure:

```text
HIVE/
  postgres/
  redis/
  cas/
  projects/
  artifacts/
  backups/
  logs/
  models/
  telemetry/
```

## HDD/SSD policy

The platform must work with secondary-HDD persistence.

Performance-sensitive indexes may optionally be placed on SSD later.

V0.1 must not require buying additional hardware.

## Backup

Back up:
- PostgreSQL;
- canonical CAS;
- configuration;
- project registry;
- decision/checkpoint sources not already safely versioned elsewhere.

Redis backups are optional because Redis is reconstructible cache.

## Recovery test

A documented recovery procedure must be tested before V0.1 is declared complete.
