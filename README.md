# HIVE

HIVE is a local-first AI context and project-intelligence platform for large
LLM-assisted software projects.

## Status

HIVE is pre-alpha and in the V0.1 Foundation bootstrap increment. This release
preparation is not production-ready and does not implement the full HIVE
product, RAG, memory semantics, MCP surface, or autonomous executor.

The implemented vertical slice reports real API, PostgreSQL/pgvector, Redis, and
canonical data-root health, and persists a deterministic Project Registry in
PostgreSQL. Redis is a non-canonical hot cache; PostgreSQL and the user-owned
data root are the durable foundation.

## Quick start

Requirements: Docker Desktop on Windows or Docker Engine plus Docker Compose on
Linux.

PowerShell:

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
curl http://localhost:8000/api/v1/health
xdg-open http://localhost:3000
~~~

The dashboard is available at http://localhost:3000 and the API health endpoint
is available at http://localhost:8000/api/v1/health. The API and dashboard bind
to localhost by default. PostgreSQL and Redis remain internal to the Compose
network and are not published to the host. Compose runs the Alembic migration
service before the API starts.

## Data and configuration

HIVE_DATA_ROOT defaults to .hive-data in the repository for development and is
ignored by Git. For secondary storage, set it to D:/HIVE on Windows or
/mnt/hive on Linux before starting Compose. HIVE_PROJECTS_ROOT defaults to the
safe, repository-local .hive-projects directory. It is the only host project
directory mounted into the API, at /workspace/projects:ro. Registered existing
targets are stored by their resolved canonical POSIX-relative identity, with
PostgreSQL uniqueness and same-file checks preventing physical aliases from
creating duplicate projects. PostgreSQL is canonical durable state; Redis
persistence is convenience-only and reconstructible.

See [docs/PROJECT-REGISTRY.md](docs/PROJECT-REGISTRY.md) for registration,
inspection, migration and path-boundary details.

See [docs/TASK-INTAKE-CAS.md](docs/TASK-INTAKE-CAS.md) for durable task intake,
exact-byte CAS recovery, Zstandard, project isolation, limits and storage
metrics.

See [docs/RETRIEVAL-LEXICAL.md](docs/RETRIEVAL-LEXICAL.md) and
[docs/RETRIEVAL-SEMANTIC-HYBRID.md](docs/RETRIEVAL-SEMANTIC-HYBRID.md) for the
project-scoped corpus, pgvector embeddings, hybrid RRF queries and fallback
operation.

See docs/INSTALLATION.md for the full lifecycle and docs/TROUBLESHOOTING.md for
common failures.

## Development validation

~~~powershell
python -m pip install -r requirements-dev.txt
python scripts/check_secrets.py
python scripts/generate_maps.py --check
ruff format --check backend scripts
ruff check backend scripts
mypy
pytest
Set-Location dashboard
npm ci
npm run lint
npm run typecheck
npm run test:run
npm run build
Set-Location ..
docker compose config --quiet
~~~

The same checks run in GitHub Actions. Run scripts/review_bundle.py after
validation to produce the deterministic audit ZIP.

## Canonical project sources and governance

The approved source pack is in docs/project-brain/. Start with
docs/project-brain/13-CHECKPOINT.md, then consult scope, Definition of Done,
architecture, requirements, and the decisions ledger. See AGENTS.md,
CONTRIBUTING.md, SECURITY.md, and SUPPORT.md for repository governance.

## Versioning and license

HIVE uses Semantic Versioning for published releases. The prepared bootstrap
target is v0.0.1-bootstrap and must remain a pre-release until Sol approval.
No open-source license has been selected yet.
