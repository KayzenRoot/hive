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
