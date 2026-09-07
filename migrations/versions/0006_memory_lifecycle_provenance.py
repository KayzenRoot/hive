"""Add project-scoped durable memory lifecycle and provenance."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_memory_lifecycle_provenance"
down_revision: str | None = "0005_semantic_retrieval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


MEMORY_TYPES = (
    "WORKING",
    "SESSION",
    "PROJECT",
    "SEMANTIC",
    "EPISODIC",
    "DECISION",
    "FAILURE",
    "PROCEDURAL",
)
MEMORY_STATUSES = ("OBSERVATION", "INFERRED", "PROPOSED", "CONFIRMED", "CANONICAL", "DEPRECATED")
MEMORY_ORIGINS = ("USER", "SYSTEM", "MODEL", "EXECUTOR", "RETRIEVAL", "IMPORT")


def upgrade() -> None:
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        "memory_records",
        sa.Column("memory_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("memory_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=256), nullable=False),
        sa.Column("source_version", sa.String(length=128), nullable=True),
        sa.Column("source_commit", sa.String(length=64), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("importance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("authority", sa.String(length=128), nullable=False),
        sa.Column("tags", jsonb, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("promotion_basis", jsonb, nullable=True),
        sa.Column("supersedes_memory_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("memory_id", name="memory_records_pkey"),
        sa.UniqueConstraint("project_id", "memory_id", name="uq_memory_records_project_memory"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_memory_records_project",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "supersedes_memory_id"],
            ["memory_records.project_id", "memory_records.memory_id"],
            name="fk_memory_records_project_supersedes",
        ),
        sa.CheckConstraint(
            "memory_type IN ("
            "'WORKING', 'SESSION', 'PROJECT', 'SEMANTIC', 'EPISODIC', "
            "'DECISION', 'FAILURE', 'PROCEDURAL')",
            name="ck_memory_records_type",
        ),
        sa.CheckConstraint(
            "status IN ('OBSERVATION', 'INFERRED', 'PROPOSED', "
            "'CONFIRMED', 'CANONICAL', 'DEPRECATED')",
            name="ck_memory_records_status",
        ),
        sa.CheckConstraint(
            "origin IN ('USER', 'SYSTEM', 'MODEL', 'EXECUTOR', 'RETRIEVAL', 'IMPORT')",
            name="ck_memory_records_origin",
        ),
        sa.CheckConstraint(
            "length(btrim(content)) > 0", name="ck_memory_records_content_not_blank"
        ),
        sa.CheckConstraint("length(btrim(source)) > 0", name="ck_memory_records_source_not_blank"),
        sa.CheckConstraint(
            "length(btrim(authority)) > 0", name="ck_memory_records_authority_not_blank"
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0 AND 1", name="ck_memory_records_confidence"
        ),
        sa.CheckConstraint("importance BETWEEN 0 AND 100", name="ck_memory_records_importance"),
        sa.CheckConstraint("version > 0", name="ck_memory_records_version"),
        sa.CheckConstraint("jsonb_typeof(tags) = 'array'", name="ck_memory_records_tags_array"),
    )
    op.create_index("ix_memory_records_project_status", "memory_records", ["project_id", "status"])
    op.create_index(
        "ix_memory_records_project_type", "memory_records", ["project_id", "memory_type"]
    )
    op.create_index(
        "ix_memory_records_project_updated", "memory_records", ["project_id", "updated_at"]
    )

    op.create_table(
        "memory_record_history",
        sa.Column("history_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("memory_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("memory_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=256), nullable=False),
        sa.Column("source_version", sa.String(length=128), nullable=True),
        sa.Column("source_commit", sa.String(length=64), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("importance", sa.Integer(), nullable=False),
        sa.Column("authority", sa.String(length=128), nullable=False),
        sa.Column("tags", jsonb, nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("promotion_basis", jsonb, nullable=True),
        sa.Column("supersedes_memory_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("changed_reason", sa.String(length=256), nullable=False),
        sa.Column(
            "recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("history_id", name="memory_record_history_pkey"),
        sa.UniqueConstraint(
            "project_id", "memory_id", "version", name="uq_memory_record_history_version"
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "memory_id"],
            ["memory_records.project_id", "memory_records.memory_id"],
            name="fk_memory_record_history_memory",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "supersedes_memory_id"],
            ["memory_records.project_id", "memory_records.memory_id"],
            name="fk_memory_record_history_supersedes",
        ),
        sa.CheckConstraint("version > 0", name="ck_memory_record_history_version"),
    )
    op.create_index(
        "ix_memory_record_history_project_memory",
        "memory_record_history",
        ["project_id", "memory_id", "recorded_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_memory_record_history_project_memory", table_name="memory_record_history")
    op.drop_table("memory_record_history")
    op.drop_index("ix_memory_records_project_updated", table_name="memory_records")
    op.drop_index("ix_memory_records_project_type", table_name="memory_records")
    op.drop_index("ix_memory_records_project_status", table_name="memory_records")
    op.drop_table("memory_records")
