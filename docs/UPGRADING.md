# Upgrading

HIVE is pre-alpha; upgrade procedures may change between increments.

1. Back up the PostgreSQL database and HIVE_DATA_ROOT.
2. Read the target increment release notes and CHANGELOG.md.
3. Stop services with docker compose stop.
4. Update source and configuration without deleting the data root.
5. Validate with docker compose config --quiet.
6. Run docker compose up -d --build.
7. Check the API health endpoint and dashboard.
8. Keep the backup until the new stack has been verified.

Do not use docker compose down -v for an upgrade. Named volumes and bind-mounted
data are operational state; removal is a destructive action.
