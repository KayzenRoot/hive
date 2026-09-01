"""Add durable Git-aware repository indexing metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_repository_indexing"
down_revision: str | None = "0002_task_intake_cas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "repository_index_runs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repository_head_sha", sa.String(length=64), nullable=True),
        sa.Column("git_branch", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discovered_file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("indexed_file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reused_file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("changed_file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("added_file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("removed_file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unchanged_file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("parsed_file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("symbol_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.String(length=256), nullable=True),
        sa.PrimaryKeyConstraint("run_id", name="repository_index_runs_pkey"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_repository_index_runs_project_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'COMPLETED', 'FAILED')",
            name="ck_repository_index_runs_status",
        ),
        sa.CheckConstraint(
            "discovered_file_count >= 0", name="ck_repository_index_runs_discovered"
        ),
        sa.CheckConstraint("indexed_file_count >= 0", name="ck_repository_index_runs_indexed"),
        sa.CheckConstraint("reused_file_count >= 0", name="ck_repository_index_runs_reused"),
        sa.CheckConstraint("changed_file_count >= 0", name="ck_repository_index_runs_changed"),
        sa.CheckConstraint("added_file_count >= 0", name="ck_repository_index_runs_added"),
        sa.CheckConstraint("removed_file_count >= 0", name="ck_repository_index_runs_removed"),
        sa.CheckConstraint("unchanged_file_count >= 0", name="ck_repository_index_runs_unchanged"),
        sa.CheckConstraint("parsed_file_count >= 0", name="ck_repository_index_runs_parsed"),
        sa.CheckConstraint("symbol_count >= 0", name="ck_repository_index_runs_symbols"),
    )
    op.create_index(
        "ix_repository_index_runs_project_started",
        "repository_index_runs",
        ["project_id", "started_at"],
    )
    op.create_index(
        "ix_repository_index_runs_project_status",
        "repository_index_runs",
        ["project_id", "status"],
    )

    op.create_table(
        "repository_files",
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("language", sa.String(length=64), nullable=True),
        sa.Column("file_type", sa.String(length=64), nullable=False),
        sa.Column("git_mode", sa.String(length=16), nullable=False),
        sa.Column("git_blob_sha", sa.String(length=64), nullable=True),
        sa.Column("git_status", sa.String(length=16), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("parse_status", sa.String(length=32), nullable=False),
        sa.Column("parse_error", sa.String(length=256), nullable=True),
        sa.Column("first_seen_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_seen_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_indexed_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("removed_in_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("file_id", name="repository_files_pkey"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_repository_files_project_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["first_seen_run_id"],
            ["repository_index_runs.run_id"],
            name="fk_repository_files_first_seen_run_id",
        ),
        sa.ForeignKeyConstraint(
            ["last_seen_run_id"],
            ["repository_index_runs.run_id"],
            name="fk_repository_files_last_seen_run_id",
        ),
        sa.ForeignKeyConstraint(
            ["last_indexed_run_id"],
            ["repository_index_runs.run_id"],
            name="fk_repository_files_last_indexed_run_id",
        ),
        sa.ForeignKeyConstraint(
            ["removed_in_run_id"],
            ["repository_index_runs.run_id"],
            name="fk_repository_files_removed_in_run_id",
        ),
        sa.UniqueConstraint("project_id", "path", name="uq_repository_files_project_path"),
        sa.CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name="ck_repository_files_sha256"),
        sa.CheckConstraint("file_size >= 0", name="ck_repository_files_size"),
        sa.CheckConstraint(
            "parse_status IN ('PARSED', 'NOT_APPLICABLE')",
            name="ck_repository_files_parse_status",
        ),
        sa.CheckConstraint(
            "(parse_status = 'PARSED' AND language = 'python') OR "
            "(parse_status = 'NOT_APPLICABLE' AND language IS DISTINCT FROM 'python')",
            name="ck_repository_files_parse_language",
        ),
    )
    op.create_index(
        "ix_repository_files_project_current", "repository_files", ["project_id", "is_current"]
    )
    op.create_index(
        "ix_repository_files_project_current_path",
        "repository_files",
        ["project_id", "path"],
        postgresql_where=sa.text("is_current"),
    )

    op.create_table(
        "repository_symbols",
        sa.Column("symbol_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("qualified_name", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("line_start", sa.Integer(), nullable=False),
        sa.Column("line_end", sa.Integer(), nullable=False),
        sa.Column("parent_qualified_name", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("symbol_id", name="repository_symbols_pkey"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_repository_symbols_project_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["repository_files.file_id"],
            name="fk_repository_symbols_file_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "file_id", "qualified_name", "kind", name="uq_repository_symbols_identity"
        ),
        sa.CheckConstraint(
            "kind IN ('class', 'function', 'async_function')",
            name="ck_repository_symbols_kind",
        ),
        sa.CheckConstraint(
            "line_start > 0 AND line_end >= line_start", name="ck_repository_symbols_lines"
        ),
    )
    op.create_index(
        "ix_repository_symbols_project_file", "repository_symbols", ["project_id", "file_id"]
    )
    op.create_index(
        "ix_repository_symbols_project_name", "repository_symbols", ["project_id", "qualified_name"]
    )


def downgrade() -> None:
    op.drop_index("ix_repository_symbols_project_name", table_name="repository_symbols")
    op.drop_index("ix_repository_symbols_project_file", table_name="repository_symbols")
    op.drop_table("repository_symbols")
    op.drop_index("ix_repository_files_project_current_path", table_name="repository_files")
    op.drop_index("ix_repository_files_project_current", table_name="repository_files")
    op.drop_table("repository_files")
    op.drop_index("ix_repository_index_runs_project_status", table_name="repository_index_runs")
    op.drop_index("ix_repository_index_runs_project_started", table_name="repository_index_runs")
    op.drop_table("repository_index_runs")
