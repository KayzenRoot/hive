"""Deterministic PostgreSQL plus CAS backup and clean-target restore proof.

The procedure backs up canonical structured state, canonical content-addressed
storage bytes and the non-secret registry/configuration identity, restores them
into an isolated clean target and proves equivalence:

* every canonical table row hash matches between source and restored database;
* every backed-up CAS blob digest matches its manifest and the restored store;
* the registry/configuration identity is identical after restore;
* Redis is explicitly excluded because it is noncanonical hot state.

Missing, corrupt or mismatched material fails closed. No secret material is ever
written into the backup directory.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import review_evidence as governance  # noqa: E402
from control_center_integration import (  # noqa: E402
    compose,
    current_migration_head,
    require,
)

WORK_DIR = ROOT / "tmp" / "v01-closure" / "backup-restore"
BACKUP_DIR = WORK_DIR / "backup"
RESTORE_DIR = WORK_DIR / "restore"
SUMMARY_FILE = ROOT / "tmp" / "integration-logs" / "v01-backup-restore.json"
RESTORE_DATABASE = "hive_restore_check"
CANONICAL_TABLES = (
    "alembic_version",
    "projects",
    "tasks",
    "task_extractions",
    "repository_index_runs",
    "repository_files",
    "repository_symbols",
    "retrieval_corpus_runs",
    "retrieval_chunks",
    "retrieval_references",
    "embedding_profiles",
    "retrieval_embedding_runs",
    "retrieval_chunk_embeddings",
    "memory_records",
    "memory_record_history",
    "telemetry_events",
    "cas_blobs",
)
CANONICAL_CAS_ROOT = os.environ.get("HIVE_CAS_ROOT", "/var/lib/hive/cas/sha256")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "hive")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "hive")


def psql(database: str, statement: str) -> str:
    result = compose(
        "exec",
        "-T",
        "postgres",
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        POSTGRES_USER,
        "-d",
        database,
        "-Atqc",
        statement,
    )
    return result


def table_row_digest(database: str, table: str) -> tuple[int, str]:
    """Return (row count, digest over every row serialization) for one table."""

    count_text = psql(database, f"SELECT count(*) FROM {table}").strip()
    require(count_text.isdigit(), f"pg count failed for {table}")
    digest_statement = (
        f"SELECT coalesce(md5(string_agg(row_text, '' ORDER BY row_text)), 'empty') FROM "
        f"(SELECT t::text AS row_text FROM {table} t) rows"
    )
    digest = psql(database, digest_statement).strip()
    require(digest == "empty" or len(digest) == 32, f"pg digest failed for {table}")
    return int(count_text), digest


def canonical_database_digest(database: str) -> dict[str, object]:
    tables: dict[str, object] = {}
    combined = hashlib.sha256()
    for table in CANONICAL_TABLES:
        rows, digest = table_row_digest(database, table)
        tables[table] = {"rows": rows, "digest": digest}
        combined.update(f"{table}:{rows}:{digest}\n".encode())
    return {"tables": tables, "digest": combined.hexdigest()}


def registry_identity(database: str) -> dict[str, object]:
    """Return the non-secret registry identity of the durable project rows."""

    statement = (
        "SELECT coalesce(json_agg(json_build_object("
        "'project', project_id, 'name', name, 'path', relative_path, 'state', state, "
        "'head', git_head_sha) ORDER BY project_id), '[]'::json) FROM projects"
    )

    payload = json.loads(psql(database, statement))
    if not isinstance(payload, list):
        raise AssertionError("registry identity is not a list")
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return {"projects": len(payload), "digest": digest}


def backup_cas(destination: Path) -> dict[str, object]:
    """Archive canonical CAS bytes and record their digests."""

    manifest_text = compose(
        "exec",
        "-T",
        "api",
        "sh",
        "-c",
        f"find {CANONICAL_CAS_ROOT} -type f -exec sha256sum {{}} \\;",
    )
    lines = [line.strip() for line in manifest_text.splitlines() if line.strip()]
    require(bool(lines), "canonical CAS root has no files to back up")
    archive = destination / "cas.tar"
    with archive.open("wb") as archive_stream:
        extract = subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "api",
                "tar",
                "-C",
                CANONICAL_CAS_ROOT,
                "-cf",
                "-",
                ".",
            ],
            cwd=ROOT,
            stdout=archive_stream,
            stderr=subprocess.PIPE,
            check=False,
            timeout=600,
        )
    require(extract.returncode == 0, f"canonical CAS archive failed: {extract.stderr[-300:]!r}")
    entries: list[dict[str, object]] = []
    for line in sorted(lines):
        digest, _, path = line.partition("  ")
        relative = path[len(CANONICAL_CAS_ROOT) :].lstrip("/")
        entries.append({"digest": digest, "path": relative})
    manifest = {"entries": entries, "count": len(entries)}
    (destination / "cas-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    require(len({entry["digest"] for entry in entries}) == len(entries), "duplicate CAS digest")
    return manifest


def backup_configuration(destination: Path, identity: dict[str, object]) -> dict[str, object]:
    """Record non-secret configuration and registry identity without secrets."""

    payload = {
        "canonical_cas_root_identity": hashlib.sha256(CANONICAL_CAS_ROOT.encode()).hexdigest(),
        "postgres_database": POSTGRES_DB,
        "migration_head": current_migration_head(),
        "registry_identity": identity,
        "redis_excluded": True,
    }
    serialized = json.dumps(payload, sort_keys=True)
    for forbidden in ("password", "secret", "token", "api_key"):
        require(forbidden not in serialized.casefold(), "backup configuration leaked a secret key")
    (destination / "config-identity.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def main() -> int:
    started = time.monotonic()
    try:
        require(
            current_migration_head() == governance.V01_CLOSURE_SPRINT_MIGRATION_BASE_HEAD,
            "migration drift",
        )
        shutil.rmtree(WORK_DIR, ignore_errors=True)
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        RESTORE_DIR.mkdir(parents=True, exist_ok=True)

        source = canonical_database_digest(POSTGRES_DB)
        identity = registry_identity(POSTGRES_DB)
        dump = compose(
            "exec",
            "-T",
            "postgres",
            "pg_dump",
            "-U",
            POSTGRES_USER,
            "-d",
            POSTGRES_DB,
            "--no-owner",
            "--no-acl",
        )
        require(len(dump) > 1024, "postgres dump is implausibly small")
        (BACKUP_DIR / "postgres.sql").write_text(dump, encoding="utf-8")
        backup_cas(BACKUP_DIR)
        configuration = backup_configuration(BACKUP_DIR, identity)

        # restore into a clean isolated target
        psql("postgres", f"DROP DATABASE IF EXISTS {RESTORE_DATABASE}")
        psql("postgres", f"CREATE DATABASE {RESTORE_DATABASE}")
        with (BACKUP_DIR / "postgres.sql").open("rb") as dump_stream:
            restore = subprocess.run(
                [
                    "docker",
                    "compose",
                    "exec",
                    "-T",
                    "postgres",
                    "psql",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-U",
                    POSTGRES_USER,
                    "-d",
                    RESTORE_DATABASE,
                    "-q",
                ],
                cwd=ROOT,
                stdin=dump_stream,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=600,
            )
        require(restore.returncode == 0, f"postgres restore failed: {restore.stderr[-400:]}")

        restored = canonical_database_digest(RESTORE_DATABASE)
        require(
            restored["digest"] == source["digest"],
            "restored canonical database does not match the source",
        )
        restored_identity = registry_identity(RESTORE_DATABASE)
        require(
            restored_identity == identity,
            "restored registry identity does not match the source",
        )

        with tarfile.open(BACKUP_DIR / "cas.tar", "r:") as archive:
            archive.extractall(RESTORE_DIR / "cas", filter="data")
        manifest = json.loads((BACKUP_DIR / "cas-manifest.json").read_text(encoding="utf-8"))
        restored_cas = hashlib.sha256()
        verified = 0
        for entry in manifest["entries"]:
            path = RESTORE_DIR / "cas" / str(entry["path"])
            require(path.is_file(), f"restored CAS blob missing: {entry['path']}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            require(
                digest == entry["digest"], f"restored CAS blob digest mismatch: {entry['path']}"
            )
            restored_cas.update(f"{entry['digest']}\n".encode())
            verified += 1
        require(verified == int(manifest["count"]), "restored CAS blob count mismatch")

        blob_rows = psql(
            POSTGRES_DB,
            "SELECT coalesce(md5(string_agg(sha256, '' ORDER BY sha256)), 'empty') FROM cas_blobs",
        ).strip()
        restored_blob_rows = psql(
            RESTORE_DATABASE,
            "SELECT coalesce(md5(string_agg(sha256, '' ORDER BY sha256)), 'empty') FROM cas_blobs",
        ).strip()
        require(blob_rows == restored_blob_rows, "restored CAS rows do not match the source")

        summary: dict[str, object] = {
            "status": "PASS",
            "database": {
                "canonical_digest": source["digest"],
                "restored_digest": restored["digest"],
                "tables": source["tables"],
                "rows": sum(int(cast["rows"]) for cast in source["tables"].values()),
            },
            "cas": {
                "blobs": int(manifest["count"]),
                "digest": restored_cas.hexdigest(),
                "row_digest": blob_rows,
                "restored_row_digest": restored_blob_rows,
            },
            "configuration": configuration,
            "restored_registry_digest": restored_identity["digest"],
            "redis_excluded": True,
            "restore_target": RESTORE_DATABASE,
        }
        SUMMARY_FILE.parent.mkdir(parents=True, exist_ok=True)
        SUMMARY_FILE.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        psql("postgres", f"DROP DATABASE IF EXISTS {RESTORE_DATABASE}")
        print(
            "[wo024] backup/restore PASS "
            f"tables={len(CANONICAL_TABLES)} rows={summary['database']['rows']} "
            f"cas_blobs={manifest['count']} in {time.monotonic() - started:.1f}s",
            flush=True,
        )
        return 0
    except Exception as exc:
        print(
            f"[wo024] backup/restore FAIL: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
