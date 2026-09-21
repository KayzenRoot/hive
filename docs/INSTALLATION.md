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
Copy-Item .env.example .env
# Recommended Windows layout: keep HIVE durable data and user repositories
# in separate roots. Prefer forward slashes in Compose paths.
New-Item -ItemType Directory -Force 'D:\HIVE' | Out-Null
New-Item -ItemType Directory -Force 'D:\Projects' | Out-Null
$env:HIVE_DATA_ROOT = 'D:/HIVE'
$env:HIVE_PROJECTS_ROOT = 'D:/Projects'
docker compose config --quiet
docker compose up -d --build
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
