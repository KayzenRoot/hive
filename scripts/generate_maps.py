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
        "| backend/app/main.py | Versioned FastAPI health and Project Registry API. |",
        "| backend/app/registry.py | Project Registry schemas, canonical physical "
        "identity, safe re-inspection and Git inspection. |",
        "| dashboard/src/App.tsx | Real API health and Project Fleet dashboard. |",
        "| migrations/versions/0001_create_projects.py | Durable Project "
        "Registry schema revision. |",
        "| scripts/review_bundle.py | Brazilian Portuguese audit bundle generation. |",
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
        "| backend/tests/test_config.py | Defaults and HIVE_DATA_ROOT parsing. |",
        "| backend/tests/test_health.py | API response shape and degraded status. |",
        "| backend/tests/test_registry.py | Path boundary, canonical aliases, safe "
        "Git command construction, language detection and states. |",
        "| backend/tests/test_projects_api.py | Typed Project Registry API contract, "
        "errors and persisted blocked state. |",
        "| dashboard/src/App.test.tsx | Health and Project Fleet rendering/operations. |",
        "| ruff | Backend and script lint/format. |",
        "| mypy | Backend static typing. |",
        "| npm run lint | Dashboard lint. |",
        "| npm run typecheck | Dashboard TypeScript. |",
        "| npm run test:run | Dashboard test suite. |",
        "| npm run build | Dashboard production build. |",
        "| docker compose config --quiet | Compose syntax and interpolation. |",
        "| scripts/integration_health.py | Container startup and API/dashboard smoke. |",
        "| scripts/project_registry_integration.py | Clean-database real-Git registry "
        "E2E, canonical alias guard, unsafe transition/recovery and persistence smoke. |",
        "| scripts/check_secrets.py | Tracked-file secret scan. |",
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
