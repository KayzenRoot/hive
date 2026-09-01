"""Add durable task intake, CAS metadata and deterministic extractions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_task_intake_cas"
down_revision: str | None = "0001_create_projects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cas_blobs",
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("logical_size", sa.BigInteger(), nullable=False),
        sa.Column("physical_size", sa.BigInteger(), nullable=False),
        sa.Column("codec", sa.String(length=32), nullable=False, server_default="zstd"),
        sa.Column(
            "codec_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("sha256", name="cas_blobs_pkey"),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_cas_blobs_sha256"),
        sa.CheckConstraint("logical_size >= 0", name="ck_cas_blobs_logical_size"),
        sa.CheckConstraint("physical_size > 0", name="ck_cas_blobs_physical_size"),
        sa.CheckConstraint("codec = 'zstd'", name="ck_cas_blobs_codec"),
    )

    op.create_table(
        "task_extractions",
        sa.Column("extraction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("extraction_kind", sa.String(length=64), nullable=False),
        sa.Column("extractor", sa.String(length=128), nullable=False),
        sa.Column("extractor_version", sa.String(length=128), nullable=False),
        sa.Column("config_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("extraction_error", sa.String(length=256), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("extraction_id", name="task_extractions_pkey"),
        sa.ForeignKeyConstraint(
            ["source_sha256"], ["cas_blobs.sha256"], name="fk_task_extractions_source_sha256"
        ),
        sa.UniqueConstraint(
            "source_sha256",
            "extraction_kind",
            "extractor",
            "extractor_version",
            "config_sha256",
            name="uq_task_extractions_cache_key",
        ),
        sa.CheckConstraint(
            "status IN ('READY', 'EXTRACTION_FAILED')", name="ck_task_extractions_status"
        ),
        sa.CheckConstraint(
            "(status = 'READY' AND text_content IS NOT NULL AND extraction_error IS NULL) "
            "OR (status = 'EXTRACTION_FAILED' AND extraction_error IS NOT NULL)",
            name="ck_task_extractions_result",
        ),
        sa.CheckConstraint(
            "page_count IS NULL OR page_count >= 0", name="ck_task_extractions_page_count"
        ),
    )
    op.create_index("ix_task_extractions_source_sha256", "task_extractions", ["source_sha256"])

    op.create_table(
        "tasks",
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("intake_status", sa.String(length=32), nullable=False),
        sa.Column("original_blob_sha256", sa.String(length=64), nullable=False),
        sa.Column("original_filename", sa.String(length=1024), nullable=True),
        sa.Column("media_type", sa.String(length=128), nullable=False),
        sa.Column("logical_size", sa.BigInteger(), nullable=False),
        sa.Column("extraction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("extraction_method", sa.String(length=128), nullable=False),
        sa.Column("extraction_version", sa.String(length=128), nullable=False),
        sa.Column("extraction_error", sa.String(length=256), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("task_id", name="tasks_pkey"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.project_id"], name="fk_tasks_project_id", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["original_blob_sha256"],
            ["cas_blobs.sha256"],
            name="fk_tasks_original_blob_sha256",
        ),
        sa.ForeignKeyConstraint(
            ["extraction_id"], ["task_extractions.extraction_id"], name="fk_tasks_extraction_id"
        ),
        sa.CheckConstraint(
            "source_type IN ('PDF', 'MARKDOWN', 'TXT', 'STRUCTURED_TEXT')",
            name="ck_tasks_source_type",
        ),
        sa.CheckConstraint(
            "intake_status IN ('READY', 'EXTRACTION_FAILED')", name="ck_tasks_intake_status"
        ),
        sa.CheckConstraint("logical_size >= 0", name="ck_tasks_logical_size"),
        sa.CheckConstraint(
            "(intake_status = 'READY' AND extraction_error IS NULL) "
            "OR (intake_status = 'EXTRACTION_FAILED' AND extraction_error IS NOT NULL)",
            name="ck_tasks_extraction_result",
        ),
        sa.CheckConstraint("page_count IS NULL OR page_count >= 0", name="ck_tasks_page_count"),
    )
    op.create_index("ix_tasks_project_created_at", "tasks", ["project_id", "created_at"])
    op.create_index("ix_tasks_project_status", "tasks", ["project_id", "intake_status"])
    op.create_index("ix_tasks_original_blob_sha256", "tasks", ["original_blob_sha256"])


def downgrade() -> None:
    op.drop_index("ix_tasks_original_blob_sha256", table_name="tasks")
    op.drop_index("ix_tasks_project_status", table_name="tasks")
    op.drop_index("ix_tasks_project_created_at", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("ix_task_extractions_source_sha256", table_name="task_extractions")
    op.drop_table("task_extractions")
    op.drop_table("cas_blobs")
