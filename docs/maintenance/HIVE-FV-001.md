# HIVE-FV-001 | Windows-mounted Git indexer maintenance
Issue: https://github.com/KayzenRoot/hive/issues/168; consumer: https://github.com/KayzenRoot/fairview/issues/1
Base: `b7f5bd8a9c9c1737c64412ebe481c9a70d9ecfc5`, descendant of immutable published HIVE v1.0.3 tag. Scope: no public API change, no database migration, no altered deployment of existing HIVE on the user's machine.

## Repro evidence (external, local R5 report)
Fairview registered READY with HIVE v1.0.3 on an isolated Docker Compose project, read-only `D:/Projects` mount. A Git status command took 6.87 s in Docker Desktop Windows bind mount; `backend/app/repository_indexer.py` hardcodes 5 s, leading to `git_status_unavailable`. The Fairview repository tracks GEF as a Git submodule (mode 160000); this indexer currently rejects any gitlink, so a timeout-only fix would reveal another failure. Host symptoms originate from an operator-provided screenshot and have not been replayed on that host by this PR.

## Authorized candidate patch
- Add typed, bounded `HIVE_REPOSITORY_GIT_TIMEOUT_SECONDS` setting (5-120 s, default 30 s), forward through all repository-indexer Git invocations including stability revalidation. Include Compose API/optional executor environment passthrough.
- Pass `--ignore-submodules=all` for status used by indexed project and for Registry inspection. This avoids recursing into submodule worktrees mounted from Windows. Submodule pointer (gitlink SHA) must remain part of the `ls-files --stage -z` inventory fingerprint; status of the nested worktree is intentionally excluded.
- Safely skip mode 160000 in file-content indexing. Never read or recurse into the submodule; optionally register its own checkout as a separate read-only project. Keep fail-closed symlink/traversal checks, races, and bounds.
- Add deterministic focused tests proving timeout parameter propagation, validation range, gitlink-content skip and pointer-change fingerprint invalidation; preserve existing regression tests.

## Test/evidence
Run focused `pytest backend/tests/test_repository_indexer.py backend/tests/test_registry.py`, ruff/mypy for changed backend files, config/unit tests and `python scripts/validate.py` / HIVE required hosted Validate, Integration health and Review Evidence according to HIVE ADR-019/020. Exact-head owner self-audit is not independent. If existing hosted gates are unrelated-red or this maintenance scope lacks governance registration, mark BLOCKED and do not bypass protected main. Never claim local Windows completion from hosted Linux checks.

## Deployment and STOP CONDITION
Never mutate the existing `D:/HIVE` installation, change its Compose project, mount paths or migrate its volumes. A candidate HIVE fix on this branch is **not a published v1.0.4**; only an accepted immutable commit may be pinned by a separate Fairview Work Order with truthful maintenance labeling and isolated-only upgrade/rebuild safeguards. Before any host upgrade, prove isolation, snapshot the isolated data, check mounted project access, compare upstream commit SHA and rerun REAL Fairview READY/index/corpus/lexical+hybrid and optional semantic CURRENT only if a real embedding provider is configured. HIVE MCP handshake must be verified separately. Stop if actual branch, project root, dataset ownership, mount access or provenance differs.
