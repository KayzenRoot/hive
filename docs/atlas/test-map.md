# Test Map

Generated deterministically by scripts/generate_maps.py.

| Test or check | Coverage |
| --- | --- |
| backend/tests/test_config.py | Defaults and HIVE_DATA_ROOT/intake limit parsing. |
| backend/tests/test_health.py | API response shape and degraded status. |
| backend/tests/test_registry.py | Path boundary, canonical aliases, safe Git command construction, language detection and states. |
| backend/tests/test_repository_indexer.py | Python qualified symbols, syntax failure and cached tracked-file inventory. |
| backend/tests/test_projects_api.py | Typed Project Registry API contract, errors and persisted blocked state. |
| backend/tests/test_cas.py | SHA-256 identity, Zstandard round-trip, atomic dedup, concurrency and fail-closed corruption checks. |
| backend/tests/test_task_intake.py | UTF-8/BOM, Markdown, structured text, PDF extraction, bounds and no-text behavior. |
| backend/tests/test_retrieval.py | Identifier normalization, deterministic chunking, request bounds and project-scoped retrieval contracts. |
| backend/tests/test_review_evidence.py | Versioned Review Evidence schema and merge-state guard. |
| backend/tests/test_tasks_api.py | Project isolation, verified artifact headers and upload/text API contracts. |
| backend/tests/test_runner.py | Local Verified Runner admission/application, path policy, deterministic verification, subprocess gating and bounded evidence. |
| dashboard/src/App.test.tsx | Health, Project Fleet and real Task Intake rendering/operations. |
| ruff | Backend and script lint/format. |
| mypy | Backend static typing. |
| npm run lint | Dashboard lint. |
| npm run typecheck | Dashboard TypeScript. |
| npm run test:run | Dashboard test suite. |
| npm run build | Dashboard production build. |
| docker compose config --quiet | Compose syntax and interpolation. |
| scripts/integration_health.py | Container startup and API/dashboard smoke. |
| scripts/project_registry_integration.py | Clean-database real-Git registry E2E, canonical alias guard, unsafe transition/recovery and persistence smoke. |
| scripts/repository_indexing_integration.py | Real-Git/PostgreSQL full, incremental, symbol, syntax-failure, isolation and restart evidence. |
| scripts/task_intake_integration.py | Isolated Docker PostgreSQL/CAS E2E for all formats, reuse, dedup, isolation, restarts, metrics and corruption. |
| scripts/retrieval_integration.py | Real-Git corpus sync, lexical benchmark, revalidation, isolation and restart persistence. |
| scripts/check_secrets.py | Tracked-file secret scan. |
| scripts/review_evidence.py | Review Evidence schema and exact-head validation. |

Indexed source files: 50
