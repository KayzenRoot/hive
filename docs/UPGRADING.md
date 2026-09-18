# Upgrading HIVE

This document covers upgrading a local HIVE deployment across stable releases.
For first-time setup see [INSTALLATION.md](INSTALLATION.md); for upgrade
failures see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Before you upgrade

1. Read the target `docs/releases/vX.Y.Z.md` notes and the matching CHANGELOG
   entry.
2. Back up PostgreSQL and the canonical data root. `HIVE_DATA_ROOT` holds
   durable bind-mounted state and CAS originals under `cas/sha256`.
3. Record the currently deployed commit (`git rev-parse HEAD`) so a rollback is
   unambiguous.

Never use `docker compose down -v` for an upgrade. Removing volumes or the data
root is a destructive action that is not part of any upgrade procedure.

## Clean source upgrade

~~~bash
git fetch origin
git checkout v1.0.0          # or the exact target release tag
docker compose config --quiet
docker compose stop
docker compose up -d --build
docker compose ps
curl --fail http://localhost:8000/api/v1/health
~~~

The Compose migration service applies Alembic migrations before the API starts;
`docker compose up` alone is not sufficient after a pull because images must be
rebuilt.

## Local state and migrations

- PostgreSQL remains canonical durable state; Redis is a non-canonical hot cache
  and may be rebuilt from canonical truth.
- Migration head for this release line is recorded by the release manifest and
  by `python scripts/migrate.py`-driven startup gating.
- `1.0.x` patch releases are expected to contain no migrations. If a release
  note lists a migration, run the documented upgrade before restarting the API.

## Compatibility verification

After the upgrade:

~~~bash
curl --fail http://localhost:8000/api/v1/health
python scripts/integration_health.py
~~~

Confirm the dashboard loads at `http://localhost:3000`, the reported version
matches the release tag and the Project Registry still lists the expected
projects. Keep the backup until verification passes.

## Rollback

1. `docker compose stop`
2. Restore the previous source revision (`git checkout <previous release tag>`).
3. Restore the PostgreSQL backup and, if required, the previous data root.
4. `docker compose up -d --build` and re-run the health checks.

Schema migrations are forward-only; rolling back across a migration requires
restoring the database backup taken before the upgrade.

## Disaster recovery

Backup, restore and secondary-disk procedures are documented in
[12-LOCAL-DEPLOYMENT.md](project-brain/12-LOCAL-DEPLOYMENT.md) and
[TROUBLESHOOTING.md](TROUBLESHOOTING.md), and are exercised by the
deterministic backup/restore tooling in `scripts/v01_backup_restore.py`.
