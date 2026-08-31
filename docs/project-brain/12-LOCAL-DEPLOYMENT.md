# 12 - LOCAL DEPLOYMENT

Deployment targets one local workstation using Docker Compose; no VPS is
required for V0.1. The suggested topology is hive-api, hive-mcp, hive-indexer,
hive-worker, hive-dashboard, postgres, redis, and optional local embedding and
reranker services. The implementation may simplify the split while preserving
contracts and observability.

## Persistent storage

Preferred host roots are D:\HIVE\ on Windows and /mnt/hive/ on Linux. Recommended
subdirectories are postgres, redis, cas, projects, artifacts, backups, logs,
models, and telemetry. Secondary-HDD persistence must work; performance indexes
may use SSD later, and V0.1 must not require new hardware.

Back up PostgreSQL, canonical CAS, configuration, project registry, and
decision/checkpoint sources not safely versioned elsewhere. Redis backups are
optional because Redis is reconstructible cache. Test a documented recovery
procedure before V0.1 completion.
