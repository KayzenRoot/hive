# Module Registry

Generated deterministically by scripts/generate_maps.py.

| Module | Responsibility |
| --- | --- |
| backend/app/config.py | Environment and persistence configuration. |
| backend/app/context_manager.py | Deterministic bounded project/task context capsule assembly. |
| backend/app/progressive_disclosure.py | Deterministic L0-L5 starting level, bounded escalation and per-level presentation bounds. |
| backend/app/db.py | PostgreSQL connection and schema revision gate. |
| backend/app/health.py | Real PostgreSQL, Redis, and storage health checks. |
| backend/app/main.py | Versioned FastAPI health, Project Registry, repository indexing, Task Intake, and Context Manager API. |
| backend/app/registry.py | Project Registry schemas, canonical physical identity, safe re-inspection and Git inspection. |
| backend/app/repository_indexer.py | Git-aware bounded inventory, deterministic hashing, incremental reconciliation and Python AST symbols. |
| backend/app/cas.py | Hash-derived Zstandard CAS with atomic publication and integrity verification. |
| backend/app/task_intake.py | Deterministic format extraction, durable tasks, reuse and storage metrics. |
| backend/app/retrieval.py | Project-scoped deterministic corpus sync, chunk provenance and bounded lexical retrieval. |
| backend/app/semantic_retrieval.py | Project-scoped pgvector embeddings, semantic retrieval, deterministic RRF fusion and lexical fallback. |
| backend/app/tasks_api.py | Project-scoped task upload, text, artifact, preview and storage routes. |
| backend/app/runner.py | Local Verified Runner change-set admission/application, path policy, deterministic verification, subprocess gating and bounded evidence. |
| dashboard/src/App.tsx | Real API health, Project Fleet and Task Intake/CAS dashboard. |
| migrations/versions/0001_create_projects.py | Durable Project Registry schema revision. |
| migrations/versions/0002_task_intake_cas.py | Durable CAS, task and extraction schema revision. |
| migrations/versions/0003_repository_indexing.py | Durable repository index runs, current files and Python symbol metadata. |
| migrations/versions/0004_retrieval_lexical.py | Durable retrieval corpus, chunk and reference metadata. |
| migrations/versions/0005_semantic_retrieval.py | Durable project-scoped embedding profiles, runs and pgvector chunk embeddings. |
| scripts/context_manager_integration.py | Real Docker/Git two-project Context Manager, progressive disclosure, mandatory governance coverage, isolation, bounds and restart evidence. |
| scripts/review_bundle.py | Generic audit bundle generation from repository evidence. |
| scripts/review_evidence.py | Versioned, secret-free Review Evidence manifest generation. |
| scripts/review_pr_body.py | Generic twenty-section PT-BR PR review template. |
| schemas/review-evidence-v1.schema.json | Machine-readable Review Evidence contract. |
| scripts/check_secrets.py | Deterministic tracked-file secret scan. |
| scripts/generate_maps.py | Regenerates maintenance maps. |
