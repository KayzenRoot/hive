# Project Registry

The Project Registry is the first durable HIVE business schema. PostgreSQL is
the canonical store; Redis is never needed to list, fetch or inspect a project.
The API performs only deterministic filesystem and Git inspection.

## Configure the project boundary

Set `HIVE_PROJECTS_ROOT` to the one host directory HIVE may inspect:

```dotenv
# Windows
HIVE_PROJECTS_ROOT=D:\Projects

# Linux
HIVE_PROJECTS_ROOT=/home/user/projects
```

Compose mounts exactly that directory read-only into the API container:

```text
${HIVE_PROJECTS_ROOT:-.hive-projects}:/workspace/projects:ro
```

Requests use a POSIX-relative path below `/workspace/projects`, such as
`acme/widget`. Absolute paths, backslashes, empty components, `.`/`..`, and
symlinks resolving outside the configured root are rejected. For an existing
target, the registry resolves symlinks, verifies containment, and stores the
canonical POSIX-relative path rather than the client alias. The PostgreSQL
unique constraint on `relative_path` is the deterministic concurrency guard;
registration also serializes identity checks and uses `os.path.samefile` when
the filesystem can prove two paths are the same directory without assuming
case-insensitivity. The default `.hive-projects` directory is intentionally
narrow and safe for development and CI; it does not expose the host filesystem
broadly.

## Migrations

Business schema migrations are explicit Alembic revisions. The Compose
`migration` one-shot service runs before `api`; if it fails, the API does not
start. To inspect or apply the current revision locally:

```powershell
docker compose run --rm migration alembic current
docker compose run --rm migration alembic upgrade head
```

`docker/postgres/init.sql` only enables the `vector` extension. It does not
create HIVE business tables. The Project Registry revision is
`0001_create_projects`; after Prompt #003, Alembic records the current head as
`0002_task_intake_cas`.

## API contract

Register a project and perform its initial inspection:

```http
POST /api/v1/projects
Content-Type: application/json

{"name":"Widget","relative_path":"acme/widget"}
```

The response is a typed project record containing its UUID, relative path,
Git branch/HEAD, detached-HEAD flag, working-tree cleanliness, detected
language stack, state, and UTC timestamps. `GET /api/v1/projects` lists the
PostgreSQL records, and `GET /api/v1/projects/{project_id}` fetches one record.
`POST /api/v1/projects/{project_id}/inspect` re-runs read-only inspection and
updates the canonical path, Git/language/state/inspection timestamp. If a
registered route later resolves outside the configured root, or cannot be
resolved safely, the endpoint does not inspect that target: it persists
`BLOCKED`, clears stale Git fields, records a stable `inspection_error`,
advances `last_inspected_at`, and returns the updated record. If the route
resolves to another already registered physical project, it persists
`BLOCKED` with `physical_identity_conflict` and leaves operator resolution
explicit; records are never merged automatically.

Duplicate relative paths return `409`. Invalid paths return `400`, malformed
typed request fields return `422`, and an unknown UUID returns `404`.

## Deterministic states

- `READY`: the path is accessible and valid Git state, HEAD and status were
  inspected successfully.
- `OFFLINE`: the configured path is missing or unavailable.
- `DEGRADED`: the path is accessible but Git inspection cannot complete, for
  example because it is not a repository or Git timed out.
- `BLOCKED`: a deterministic HIVE policy condition prevents inspection, such
  as `path_boundary_violation`, `path_resolution_failed`, or
  `physical_identity_conflict`. Git fields are cleared while blocked.

`STALE`, `INDEXING` and `ACTIVE` remain reserved for later HIVE subsystems in
this increment. Language detection uses top-level manifest and file signals
only; no LLM classifier or repository index is involved.

Git commands use argv with `shell=False`, `GIT_OPTIONAL_LOCKS=0`, a finite
timeout, and an exact `safe.directory=<resolved repository path>` value. The
wildcard `safe.directory=*` is not used.

## Control Center

The Project Fleet section lists real registry records, total count, state,
relative path, branch, short HEAD, languages and last inspection. It supports
registration and manual re-inspection through the same API and reports loading,
empty and API-error states.

The Control Center also provides the separate project-scoped Task Intake
surface. Its storage and task records are documented in
`docs/TASK-INTAKE-CAS.md`; Project Registry remains the ownership boundary.

## Troubleshooting

Check migration status first with `docker compose ps --all` and
`docker compose logs migration`. A failed migration is intentionally a startup
failure. If a project is `OFFLINE`, verify that its relative path exists below
`HIVE_PROJECTS_ROOT` and that the host directory is available to Docker
Desktop. If it is `DEGRADED`, inspect the stored `inspection_error` and confirm
the directory is a readable Git repository.
