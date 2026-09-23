# HIVE installation and local operations

This document describes the V0.1 Foundation bootstrap only. HIVE is pre-alpha
and is not production-ready.

## Requirements

Windows requires Docker Desktop with Linux containers, PowerShell, and Git.
Linux requires Docker Engine, the Docker Compose plugin, Git, and curl for the
optional command-line health check. Allocate enough Docker disk for PostgreSQL
data.

## Windows with Docker Desktop

~~~powershell
# The doctor is read-only. It validates Docker, expanded Compose mounts and
# separation of durable state from project sources without printing secrets.
python scripts/hive_install.py doctor
# Recommended Windows layout: keep HIVE durable data and user repositories
# in separate roots. Prefer forward slashes in Compose paths.
New-Item -ItemType Directory -Force 'D:\HIVE' | Out-Null
New-Item -ItemType Directory -Force 'D:\Projects' | Out-Null
$env:HIVE_DATA_ROOT = 'D:/HIVE'
$env:HIVE_PROJECTS_ROOT = 'D:/Projects'
# Install creates .env from the example only if it is absent; existing .env is preserved.
python scripts/hive_install.py install --yes
docker compose ps
Invoke-WebRequest http://localhost:8000/api/v1/health
Start-Process http://localhost:3000
~~~

If these roots are set only in the current PowerShell session, repeat them in a
new session. To persist them for the user, use:

~~~powershell
[Environment]::SetEnvironmentVariable('HIVE_DATA_ROOT', 'D:/HIVE', 'User')
[Environment]::SetEnvironmentVariable('HIVE_PROJECTS_ROOT', 'D:/Projects', 'User')
~~~

You can instead persist the same values in the local `.env` file:

~~~dotenv
HIVE_DATA_ROOT=D:/HIVE
HIVE_PROJECTS_ROOT=D:/Projects
~~~

Do **not** use `D:/HIVE/Projects` as the project root while
`HIVE_DATA_ROOT=D:/HIVE`. The HIVE data root is a writable bind mount, while
project source is intentionally exposed through the separate read-only
`HIVE_PROJECTS_ROOT` mount. Keeping the roots separate preserves that boundary.

A project under `D:\Projects\core` is registered as `core`, not as the
absolute Windows path. A nested project under `D:\Projects\KayzenRoot\core`
is registered as `KayzenRoot/core`. Use forward slashes in the registry value.
The target directory must be a readable Git repository with at least one commit
so that `HEAD` exists; a plain folder or an empty `git init` repository is
reported as `DEGRADED`.

## Linux with Docker Engine and Compose

~~~bash
cp .env.example .env
export HIVE_DATA_ROOT=/mnt/hive
docker compose config --quiet
docker compose up -d --build
docker compose ps
curl --fail http://localhost:8000/api/v1/health
xdg-open http://localhost:3000
~~~

Ensure the Docker daemon can create and write the selected root. For a
secondary disk, create the directory first and grant access to the Docker
daemon according to the host distribution policy. The API and dashboard bind to
localhost by default; PostgreSQL and Redis remain internal to the Compose
network and are not published to the host.

The same persistent `HIVE_DATA_ROOT` also contains CAS originals under
`cas/sha256`. Configure intake limits in `.env` before starting services if the
local workload needs values different from the documented defaults. See
`docs/TASK-INTAKE-CAS.md` for format validation, PDF text-layer behavior and
recovery guarantees.

## Install, upgrade and project discovery

`python scripts/hive_install.py doctor` is read-only. It reports whether Docker
and Compose are reachable, whether the expanded Compose configuration is valid,
and whether the actual bind-mounted `HIVE_DATA_ROOT` and `HIVE_PROJECTS_ROOT`
are separate. Diagnostics never print `.env` values. `install --yes` is
idempotent for an empty data root and never overwrites an existing `.env`; it
refuses to treat a non-empty data root as a new installation.

Before upgrading an existing installation, ensure its PostgreSQL Compose service
is running and choose a new, empty backup destination on a volume with enough
space. Then run, for example:

~~~powershell
python scripts/hive_install.py upgrade --yes --backup-dir 'D:/HIVE_UPGRADE_BACKUPS/hive-before-upgrade-20260922'
~~~

The upgrade records a PostgreSQL custom-format dump and copies CAS content into
that destination before rebuilding services. Redis is a hot cache and is not
backed up. `.env` and provider credentials are never copied into the backup.
If backup preconditions fail, the upgrade stops before Compose changes; after a
successful backup, any failed health check leaves both the backup and canonical
data intact for staged recovery. The command never runs `compose down -v`.

The API discovers valid Git repositories among immediate children of
`HIVE_PROJECTS_ROOT` at startup and then at a bounded interval. Discovery is
enabled by default (`HIVE_AUTO_DISCOVERY_ENABLED=true`), runs every 60 seconds
by default (`HIVE_AUTO_DISCOVERY_INTERVAL_SECONDS`, range 10–3600), and examines
at most 200 projects per scan (`HIVE_AUTO_DISCOVERY_MAX_PROJECTS`, range
1–1000). Symbolic links, junctions, duplicate physical paths, nested projects
and paths escaping the configured root are not auto-admitted. Newly discovered
repos are registered, indexed, and synchronized into retrieval without a manual
registration request. A missing project transitions to `OFFLINE`; HIVE does not
delete its registry record or source data. Set auto-discovery to `false` to opt
out explicitly.

If Redis logs a vm.overcommit_memory warning on Linux, see the manual,
non-autonomous procedure in TROUBLESHOOTING.md. HIVE never changes host sysctl
settings automatically. Docker Desktop on Windows must use the Linux VM or
environment that actually runs Docker; do not run Linux host commands blindly.

## Lifecycle commands

Start or rebuild:

~~~bash
docker compose up -d --build
~~~

Stop containers while preserving data:

~~~bash
docker compose stop
~~~

View status and logs:

~~~bash
docker compose ps
docker compose logs -f api
docker compose logs -f postgres redis dashboard
~~~

Check health:

~~~bash
curl --fail http://localhost:8000/api/v1/health
~~~

Update containers without deleting canonical data:

~~~bash
git pull
docker compose pull
docker compose up -d --build
~~~

The Compose volumes are bind mounts below HIVE_DATA_ROOT. Do not remove that
directory when updating containers. Back up PostgreSQL and the canonical data
root before maintenance.

Clean uninstall while preserving a backup:

~~~bash
docker compose down
cp -a "$HIVE_DATA_ROOT" "${HIVE_DATA_ROOT}.backup"
docker compose down --remove-orphans
~~~

The bootstrap prompt does not authorize deleting user-owned data. Remove the
backup or data directory manually only after confirming the exact path and
retention requirements.
