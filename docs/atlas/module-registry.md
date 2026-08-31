# Module Registry

Generated deterministically by scripts/generate_maps.py.

| Module | Responsibility |
| --- | --- |
| backend/app/config.py | Environment and persistence configuration. |
| backend/app/health.py | Real PostgreSQL, Redis, and storage health checks. |
| backend/app/main.py | Versioned FastAPI health surface. |
| dashboard/src/App.tsx | Real API health dashboard shell. |
| scripts/review_bundle.py | Brazilian Portuguese audit bundle generation. |
| scripts/check_secrets.py | Deterministic tracked-file secret scan. |
| scripts/generate_maps.py | Regenerates maintenance maps. |
