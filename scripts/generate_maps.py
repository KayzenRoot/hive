from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / "docs" / "atlas"


def tracked(pattern: str) -> list[Path]:
    return sorted(
        path.relative_to(ROOT)
        for path in ROOT.glob(pattern)
        if path.is_file() and ".git" not in path.parts and "node_modules" not in path.parts
    )


def build_files() -> dict[Path, str]:
    backend = tracked("backend/**/*.py")
    dashboard = tracked("dashboard/src/**/*")
    migrations = tracked("migrations/**/*.py")
    scripts = tracked("scripts/*.py")
    all_source = backend + dashboard + migrations + scripts
    atlas_lines = [
        "# Code Atlas",
        "",
        "Generated deterministically by scripts/generate_maps.py.",
        "",
        "## Backend",
        "",
    ]
    atlas_lines += [f"- {path.as_posix()}: Python source or test module." for path in backend]
    atlas_lines += ["", "## Dashboard", ""]
    atlas_lines += [
        f"- {path.as_posix()}: TypeScript/React source or test module." for path in dashboard
    ]
    atlas_lines += ["", "## Migrations", ""]
    atlas_lines += [
        f"- {path.as_posix()}: Ordered PostgreSQL business-schema revision." for path in migrations
    ]
    atlas_lines += ["", "## Operational scripts", ""]
    atlas_lines += [
        f"- {path.as_posix()}: deterministic maintenance or validation script." for path in scripts
    ]

    registry = [
        "# Module Registry",
        "",
        "Generated deterministically by scripts/generate_maps.py.",
        "",
        "| Module | Responsibility |",
        "| --- | --- |",
        "| backend/app/config.py | Environment and persistence configuration. |",
        "| backend/app/db.py | PostgreSQL connection and schema revision gate. |",
        "| backend/app/health.py | Real PostgreSQL, Redis, and storage health checks. |",
        (
            "| backend/app/main.py | Versioned FastAPI health, Project Registry, "
            "repository indexing and Task Intake API. |"
        ),
        (
            "| backend/app/registry.py | Project Registry schemas, canonical physical "
            "identity, safe re-inspection and Git inspection. |"
        ),
        (
            "| backend/app/repository_indexer.py | Git-aware bounded inventory, "
            "deterministic hashing, incremental reconciliation and Python AST "
            "symbols. |"
        ),
        (
            "| backend/app/cas.py | Hash-derived Zstandard CAS with atomic "
            "publication and integrity verification. |"
        ),
        (
            "| backend/app/task_intake.py | Deterministic format extraction, durable "
            "tasks, reuse and storage metrics. |"
        ),
        (
            "| backend/app/retrieval.py | Project-scoped deterministic corpus sync, "
            "chunk provenance and bounded lexical retrieval. |"
        ),
        (
            "| backend/app/semantic_retrieval.py | Project-scoped pgvector embeddings, "
            "semantic retrieval, deterministic RRF fusion and lexical fallback. |"
        ),
        (
            "| backend/app/tasks_api.py | Project-scoped task upload, text, artifact, "
            "preview and storage routes. |"
        ),
        (
            "| backend/app/runner.py | Local Verified Runner change-set "
            "admission/application, path policy, deterministic verification, "
            "subprocess gating and bounded evidence. |"
        ),
        "| dashboard/src/App.tsx | Real API health, Project Fleet and Task Intake/CAS dashboard. |",
        (
            "| migrations/versions/0001_create_projects.py | Durable Project Registry "
            "schema revision. |"
        ),
        (
            "| migrations/versions/0002_task_intake_cas.py | Durable CAS, task and "
            "extraction schema revision. |"
        ),
        (
            "| migrations/versions/0003_repository_indexing.py | Durable repository "
            "index runs, current files and Python symbol metadata. |"
        ),
        (
            "| migrations/versions/0004_retrieval_lexical.py | Durable retrieval corpus, "
            "chunk and reference metadata. |"
        ),
        (
            "| migrations/versions/0005_semantic_retrieval.py | Durable project-scoped "
            "embedding profiles, runs and pgvector chunk embeddings. |"
        ),
        "| scripts/review_bundle.py | Generic audit bundle generation from repository evidence. |",
        (
            "| scripts/review_evidence.py | Versioned, secret-free Review Evidence "
            "manifest generation. |"
        ),
        "| scripts/review_pr_body.py | Generic twenty-section PT-BR PR review template. |",
        "| schemas/review-evidence-v1.schema.json | Machine-readable Review Evidence contract. |",
        "| scripts/check_secrets.py | Deterministic tracked-file secret scan. |",
        "| scripts/generate_maps.py | Regenerates maintenance maps. |",
    ]

    test_map = [
        "# Test Map",
        "",
        "Generated deterministically by scripts/generate_maps.py.",
        "",
        "| Test or check | Coverage |",
        "| --- | --- |",
        "| backend/tests/test_config.py | Defaults and HIVE_DATA_ROOT/intake limit parsing. |",
        "| backend/tests/test_health.py | API response shape and degraded status. |",
        (
            "| backend/tests/test_registry.py | Path boundary, canonical aliases, "
            "safe Git command construction, language detection and states. |"
        ),
        (
            "| backend/tests/test_repository_indexer.py | Python qualified symbols, "
            "syntax failure and cached tracked-file inventory. |"
        ),
        (
            "| backend/tests/test_projects_api.py | Typed Project Registry API "
            "contract, errors and persisted blocked state. |"
        ),
        (
            "| backend/tests/test_cas.py | SHA-256 identity, Zstandard round-trip, "
            "atomic dedup, concurrency and fail-closed corruption checks. |"
        ),
        (
            "| backend/tests/test_task_intake.py | UTF-8/BOM, Markdown, structured "
            "text, PDF extraction, bounds and no-text behavior. |"
        ),
        (
            "| backend/tests/test_retrieval.py | Identifier normalization, deterministic "
            "chunking, request bounds and project-scoped retrieval contracts. |"
        ),
        (
            "| backend/tests/test_semantic_retrieval.py | Embedding configuration, "
            "provider contract validation, currentness, RRF and lexical fallback. |"
        ),
        (
            "| backend/tests/test_review_evidence.py | Versioned Review Evidence schema "
            "and merge-state guard. |"
        ),
        (
            "| backend/tests/test_tasks_api.py | Project isolation, verified artifact "
            "headers and upload/text API contracts. |"
        ),
        (
            "| backend/tests/test_runner.py | Local Verified Runner "
            "admission/application, path policy, deterministic verification, "
            "subprocess gating and bounded evidence. |"
        ),
        (
            "| dashboard/src/App.test.tsx | Health, Project Fleet and real Task "
            "Intake rendering/operations. |"
        ),
        "| ruff | Backend and script lint/format. |",
        "| mypy | Backend static typing. |",
        "| npm run lint | Dashboard lint. |",
        "| npm run typecheck | Dashboard TypeScript. |",
        "| npm run test:run | Dashboard test suite. |",
        "| npm run build | Dashboard production build. |",
        "| docker compose config --quiet | Compose syntax and interpolation. |",
        "| scripts/integration_health.py | Container startup and API/dashboard smoke. |",
        (
            "| scripts/project_registry_integration.py | Clean-database real-Git "
            "registry E2E, canonical alias guard, unsafe transition/recovery and "
            "persistence smoke. |"
        ),
        (
            "| scripts/repository_indexing_integration.py | Real-Git/PostgreSQL full, "
            "incremental, symbol, syntax-failure, isolation and restart evidence. |"
        ),
        (
            "| scripts/task_intake_integration.py | Isolated Docker PostgreSQL/CAS "
            "E2E for all formats, reuse, dedup, isolation, restarts, metrics and "
            "corruption. |"
        ),
        (
            "| scripts/retrieval_integration.py | Real-Git corpus sync, lexical, "
            "semantic and hybrid benchmark, revalidation, isolation and restart persistence. |"
        ),
        "| scripts/check_secrets.py | Tracked-file secret scan. |",
        "| scripts/review_evidence.py | Review Evidence schema and exact-head validation. |",
        (
            "| scripts/review_pr_body.py | Work-order marker, twenty-section review "
            "and Sol-state template. |"
        ),
        "",
        f"Indexed source files: {len(all_source)}",
    ]
    return {
        ATLAS / "code-atlas.md": "\n".join(atlas_lines) + "\n",
        ATLAS / "module-registry.md": "\n".join(registry) + "\n",
        ATLAS / "test-map.md": "\n".join(test_map) + "\n",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = build_files()
    mismatches: list[Path] = []
    for path, content in expected.items():
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                mismatches.append(path)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
    if mismatches:
        print("Generated maps are stale:", *mismatches, sep="\n- ", file=sys.stderr)
        return 1
    if not args.check:
        print("Generated maps:", *expected, sep="\n- ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
