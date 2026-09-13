"""Project-scoped storage observations for WO-021 metrics."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from .config import Settings
from .db import database_connection


@dataclass(frozen=True)
class StorageObservation:
    logical_task_bytes: int
    physical_referenced_bytes: int
    task_count: int
    referenced_blob_count: int


def observe_project_storage(settings: Settings, project_id: UUID) -> StorageObservation:
    """Read exact project storage metadata without exposing host paths.

    Logical bytes count every project task reference. Physical bytes count each
    CAS digest referenced by the project once, so same-project dedup is visible.
    """

    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
              COALESCE((SELECT SUM(logical_size) FROM tasks WHERE project_id = %s), 0),
              COALESCE((SELECT SUM(c.physical_size) FROM cas_blobs AS c JOIN
                (SELECT DISTINCT original_blob_sha256 AS sha256 FROM tasks WHERE project_id = %s)
                AS refs ON refs.sha256 = c.sha256), 0),
              (SELECT COUNT(*) FROM tasks WHERE project_id = %s),
              (SELECT COUNT(DISTINCT original_blob_sha256) FROM tasks WHERE project_id = %s)
            """,
            (project_id, project_id, project_id, project_id),
        )
        row = cursor.fetchone()
    if row is None:
        raise RuntimeError("storage metrics query returned no row")
    return StorageObservation(
        logical_task_bytes=int(row[0]),
        physical_referenced_bytes=int(row[1]),
        task_count=int(row[2]),
        referenced_blob_count=int(row[3]),
    )
