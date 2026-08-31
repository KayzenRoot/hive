# Test Map

Generated deterministically by scripts/generate_maps.py.

| Test or check | Coverage |
| --- | --- |
| backend/tests/test_config.py | Defaults and HIVE_DATA_ROOT parsing. |
| backend/tests/test_health.py | API response shape and degraded status. |
| backend/tests/test_registry.py | Path boundary, canonical aliases, safe Git command construction, language detection and states. |
| backend/tests/test_projects_api.py | Typed Project Registry API contract, errors and persisted blocked state. |
| dashboard/src/App.test.tsx | Health and Project Fleet rendering/operations. |
| ruff | Backend and script lint/format. |
| mypy | Backend static typing. |
| npm run lint | Dashboard lint. |
| npm run typecheck | Dashboard TypeScript. |
| npm run test:run | Dashboard test suite. |
| npm run build | Dashboard production build. |
| docker compose config --quiet | Compose syntax and interpolation. |
| scripts/integration_health.py | Container startup and API/dashboard smoke. |
| scripts/project_registry_integration.py | Clean-database real-Git registry E2E, canonical alias guard, unsafe transition/recovery and persistence smoke. |
| scripts/check_secrets.py | Tracked-file secret scan. |

Indexed source files: 30
