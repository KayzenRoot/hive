# Module Registry

Generated deterministically by scripts/generate_maps.py.

| Module | Responsibility |
| --- | --- |
| backend/app/config.py | Environment and persistence configuration. |
| backend/app/db.py | PostgreSQL connection and schema revision gate. |
| backend/app/health.py | Real PostgreSQL, Redis, and storage health checks. |
| backend/app/main.py | Versioned FastAPI health and Project Registry API. |
| backend/app/registry.py | Project Registry schemas, path boundary and Git inspection. |
| dashboard/src/App.tsx | Real API health and Project Fleet dashboard. |
| migrations/versions/0001_create_projects.py | Durable Project Registry schema revision. |
| scripts/review_bundle.py | Brazilian Portuguese audit bundle generation. |
| scripts/check_secrets.py | Deterministic tracked-file secret scan. |
| scripts/generate_maps.py | Regenerates maintenance maps. |
