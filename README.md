# HIVE

Local-first AI context, memory, retrieval, token-optimization and governed
execution platform for large LLM-assisted software projects.

[![CI](https://github.com/KayzenRoot/hive/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/KayzenRoot/hive/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/KayzenRoot/hive?label=release&sort=semver)](https://github.com/KayzenRoot/hive/releases)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue)
![Docker Compose](https://img.shields.io/badge/deployment-docker%20compose-blue)
![All Rights Reserved](https://img.shields.io/badge/license-All%20Rights%20Reserved-red)

## Status

**HIVE v1.0.0 stable release candidate.** This repository is release-ready only
after the professionalization PR is accepted, the exact-head audit passes and
the `v1.0.0` GitHub Release is published from the accepted commit. Until that tag
exists, v1.0.0 is not a published release.

Latest stable release: v1.0.0 (target). See [CHANGELOG.md](CHANGELOG.md) and
[docs/releases/v1.0.0.md](docs/releases/v1.0.0.md).

HIVE v1.0.0 is the stable public distribution of the product baseline accepted
internally as HIVE V0.1 — Foundation. Historical V0.1 and bootstrap evidence
remains canonical and unchanged; see
[docs/project-brain/13-CHECKPOINT.md](docs/project-brain/13-CHECKPOINT.md).

## Capabilities

The accepted baseline provides, with deterministic test coverage:

- Durable project registry for multiple local projects, with Git branch, HEAD,
  working-tree state and language-stack inspection.
- Durable task/prompt intake (PDF, TXT, Markdown, structured text) with
  content-addressed original preservation (SHA-256 + lossless Zstandard) and
  project-scoped recovery.
- Git-aware incremental repository indexing with stable content identity and
  Python AST symbol metadata.
- Project-scoped lexical, semantic (PostgreSQL + pgvector) and hybrid RRF
  retrieval with provider-independent embedding adapters, optional reranking and
  deterministic lexical fallback.
- Checkpoint-first Context Manager, progressive disclosure (L0–L5), adaptive
  token budgeting, context fingerprints, delta context and provider/prompt cache
  adapters over durable memory with provenance and lifecycle.
- Governed autonomous execution foundation (tool gating, staged noncanonical
  output, local verified runner) and a read-only MCP core surface.
- Telemetry/event bus and the full HIVE Control Center with bounded,
  provenance-labelled metrics — unknown values are never rendered as zero.
- Local Docker Compose deployment, backup/recovery and secondary-disk
  persistence with durable PostgreSQL and content-addressed storage.

Exact capability evidence and boundaries live in the canonical Project Brain
sources; this README intentionally links instead of duplicating them.

## Quick start

Requirements: Docker Desktop on Windows or Docker Engine plus the Compose plugin
on Linux, and Git.

Windows (PowerShell):

~~~powershell
Copy-Item .env.example .env
docker compose up -d --build
docker compose ps
Invoke-WebRequest http://localhost:8000/api/v1/health
Start-Process http://localhost:3000
~~~

Linux:

~~~bash
cp .env.example .env
docker compose up -d --build
docker compose ps
curl --fail http://localhost:8000/api/v1/health
xdg-open http://localhost:3000
~~~

The dashboard is served at `http://localhost:3000` and the API health endpoint
at `http://localhost:8000/api/v1/health`. The API and dashboard bind to
localhost by default; PostgreSQL and Redis stay internal to the Compose network.
The Compose migration service applies Alembic migrations before the API starts.

## Runtime and storage model

- PostgreSQL (with pgvector) is the canonical durable structured store.
- Redis-compatible cache is a non-canonical hot layer; losing it never destroys
  canonical project truth.
- `HIVE_DATA_ROOT` holds durable bind-mounted state and CAS originals under
  `cas/sha256`; it defaults to `.hive-data` for development and is ignored by
  Git. For secondary storage set it to e.g. `D:/HIVE` (Windows) or `/mnt/hive`
  (Linux).
- `HIVE_PROJECTS_ROOT` is the single read-only host project directory mounted
  into the API; project access is constrained to it.
- Git remains the canonical source history; derived artifacts never replace it.

See [docs/INSTALLATION.md](docs/INSTALLATION.md) and
[docs/project-brain/12-LOCAL-DEPLOYMENT.md](docs/project-brain/12-LOCAL-DEPLOYMENT.md).

## Repository map

| Path | Purpose |
|---|---|
| `backend/` | FastAPI core, data layer, execution and retrieval logic, tests |
| `dashboard/` | React/TypeScript Control Center |
| `scripts/` | Deterministic validation, release, governance and integration tooling |
| `docs/` | Installation, operations, release and maintenance documentation |
| `docs/project-brain/` | Canonical project decisions and scope |
| `docs/releases/` | Versioned release notes and templates |
| `migrations/` | Versioned Alembic schema migrations |
| `.github/` | CI, release, security automation and templates |
| `.engineering/` | Derived engineering policy and release provenance |

## Validation

~~~powershell
python -m pip install -r requirements-dev.txt
python scripts/validate.py
~~~

`scripts/validate.py` runs canonical source verification, deterministic release
metadata verification, the release package dry-run, secret scanning, generated
map checks, lint, typecheck, backend/dashboard tests, the dashboard build,
`npm audit` and `docker compose config --quiet`. The same entry point runs in
the hosted Validate gate.

## Versioning and releases

HIVE uses Semantic Versioning as defined in [docs/VERSIONING.md](docs/VERSIONING.md)
and maintained under [docs/MAINTENANCE.md](docs/MAINTENANCE.md). Release
metadata coherence is enforced deterministically by
`scripts/verify_release_metadata.py`.

The release process is documented in [docs/RELEASING.md](docs/RELEASING.md),
[docs/RELEASE-CHECKLIST.md](docs/RELEASE-CHECKLIST.md) and
[docs/UPGRADING.md](docs/UPGRADING.md). Source releases are the only supported
distribution channel in this increment.

## Security, support, contributions and rights

- [SECURITY.md](SECURITY.md) — supported line, private reporting, severity
  expectations.
- [SUPPORT.md](SUPPORT.md) — support boundary and required reproduction evidence.
- [CONTRIBUTING.md](CONTRIBUTING.md) — branch/PR and exact-head review workflow.
- [AGENTS.md](AGENTS.md) — agent guidance and release/maintenance rules.
- [LICENSE](LICENSE) — All Rights Reserved. This is not an open-source license;
  no copy, modification or distribution rights are granted.

## Canonical sources

Start with [docs/project-brain/13-CHECKPOINT.md](docs/project-brain/13-CHECKPOINT.md),
then consult scope, Definition of Done, architecture, requirements and the
decisions ledger. Canonical sources take precedence over this README.
