# Module Registry

Generated deterministically by scripts/generate_maps.py.

| Module | Responsibility |
| --- | --- |
| backend/app/config.py | Environment and persistence configuration. |
| backend/app/db.py | PostgreSQL connection and schema revision gate. |
| backend/app/health.py | Real PostgreSQL, Redis, and storage health checks. |
| backend/app/main.py | Versioned FastAPI health, Project Registry and Task Intake API. |
| backend/app/registry.py | Project Registry schemas, canonical physical identity, safe re-inspection and Git inspection. |
| backend/app/cas.py | Hash-derived Zstandard CAS with atomic publication and integrity verification. |
| backend/app/task_intake.py | Deterministic format extraction, durable tasks, reuse and storage metrics. |
| backend/app/tasks_api.py | Project-scoped task upload, text, artifact, preview and storage routes. |
| backend/app/runner.py | Local Verified Runner change-set admission, safe staged application, changed-file verification and gated subprocess evidence. |
| dashboard/src/App.tsx | Real API health, Project Fleet and Task Intake/CAS dashboard. |
| migrations/versions/0001_create_projects.py | Durable Project Registry schema revision. |
| migrations/versions/0002_task_intake_cas.py | Durable CAS, task and extraction schema revision. |
| scripts/review_bundle.py | Brazilian Portuguese audit bundle generation. |
| scripts/check_secrets.py | Deterministic tracked-file secret scan. |
| scripts/generate_maps.py | Regenerates maintenance maps. |
