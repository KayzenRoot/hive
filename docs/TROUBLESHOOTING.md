# Troubleshooting

## Port already occupied

Change HIVE_API_PORT or HIVE_DASHBOARD_PORT in .env and restart Compose. On
Windows use Get-NetTCPConnection -LocalPort 8000; on Linux use ss -ltnp | grep
8000. The dashboard build receives the configured API port through Compose, so
rebuild after changing HIVE_API_PORT. PostgreSQL and Redis are internal to the
Compose network and do not require host ports.

## Docker is unavailable

Confirm Docker Desktop is running on Windows or that the Docker daemon is
active on Linux:

~~~bash
docker version
docker compose version
~~~

The API and dashboard can be run locally for development, but PostgreSQL with
pgvector and Redis still need reachable services. The documented bootstrap path
is Docker Compose.

## PostgreSQL is unhealthy

Inspect logs with docker compose logs postgres. Confirm that the data root is
writable and that no stale container owns the port. The API requires the
pgvector extension; a fresh database runs docker/postgres/init.sql. Existing
databases need the extension enabled by an operator before the health check
reports ok.

## Redis is unhealthy

Inspect docker compose logs redis and confirm the data root is writable. Redis
is a non-canonical hot cache. Its loss must not destroy canonical project truth;
recreate it with docker compose up -d redis when needed.

## Redis vm.overcommit_memory warning on Linux

The Redis log may report that vm.overcommit_memory is disabled. Redis
recommends vm.overcommit_memory=1 because background persistence and fork
operations are more reliable when the kernel permits the memory reservation.
Inspect the current value with:

~~~bash
sysctl vm.overcommit_memory
cat /proc/sys/vm/overcommit_memory
~~~

An operator may apply this optional manual host-level fix in the relevant Linux
environment:

~~~bash
sudo sysctl -w vm.overcommit_memory=1
~~~

Persisting it in /etc/sysctl.d/99-hive-redis.conf is also an operator choice;
review local distribution policy before doing so. HIVE does not modify host
sysctl settings autonomously, and this warning does not make Redis canonical
state. Windows Docker Desktop users must not run Linux host commands blindly;
inspect the Linux VM or environment that actually runs Docker instead.

## API health is degraded

Fetch http://localhost:8000/api/v1/health and inspect the checks object. The
endpoint intentionally returns HTTP 503 while any required check is degraded.
It does not return credentials or connection strings. Fix the reported service,
then retry.

## Dashboard cannot reach the API

Open the browser developer console and verify the API URL. The default is
http://localhost:8000. If HIVE_API_PORT changed, rebuild with:

~~~bash
docker compose up -d --build dashboard
~~~

Confirm CORS_ORIGINS is aligned with the dashboard port if running outside the
standard Compose setup.

## HIVE_DATA_ROOT path or permission problems

Use an absolute host path for a secondary disk, such as D:/HIVE or /mnt/hive.
Create it before starting Compose and ensure Docker can write it. Avoid paths
containing unescaped shell metacharacters. Do not use a path containing secrets
or commit the data directory.
