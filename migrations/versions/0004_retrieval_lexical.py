"""Add the project-scoped lexical retrieval corpus."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_retrieval_lexical"
down_revision: str | None = "0003_repository_indexing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The older tables have globally unique identifiers, but these composite
    # keys let the retrieval layer enforce project ownership in PostgreSQL.
    op.create_unique_constraint("uq_tasks_project_task", "tasks", ["project_id", "task_id"])
    op.create_unique_constraint(
        "uq_repository_symbols_project_symbol",
        "repository_symbols",
        ["project_id", "symbol_id"],
    )

    op.create_table(
        "retrieval_corpus_runs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repository_index_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("repository_source_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("task_source_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("repository_source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("task_source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reference_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("repository_reference_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("task_reference_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reused_chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_reference_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reused_reference_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("removed_reference_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_reference_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_binary_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_decode_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.String(length=256), nullable=True),
        sa.PrimaryKeyConstraint("run_id", name="retrieval_corpus_runs_pkey"),
        sa.UniqueConstraint("project_id", "run_id", name="uq_retrieval_corpus_runs_project_run"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_retrieval_corpus_runs_project_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "repository_index_run_id"],
            ["repository_index_runs.project_id", "repository_index_runs.run_id"],
            name="fk_retrieval_corpus_runs_project_index_run",
        ),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'COMPLETED', 'FAILED', 'STALE', 'BLOCKED')",
            name="ck_retrieval_corpus_runs_status",
        ),
        sa.CheckConstraint(
            "repository_source_fingerprint IS NULL OR "
            "repository_source_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_retrieval_corpus_runs_repo_fingerprint",
        ),
        sa.CheckConstraint(
            "task_source_fingerprint IS NULL OR task_source_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_retrieval_corpus_runs_task_fingerprint",
        ),
        sa.CheckConstraint(
            "source_fingerprint IS NULL OR source_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_retrieval_corpus_runs_source_fingerprint",
        ),
        sa.CheckConstraint(
            "repository_source_count >= 0 AND task_source_count >= 0 AND chunk_count >= 0 "
            "AND reference_count >= 0 AND repository_reference_count >= 0 "
            "AND task_reference_count >= 0 AND new_chunk_count >= 0 "
            "AND reused_chunk_count >= 0 AND new_reference_count >= 0 "
            "AND reused_reference_count >= 0 AND removed_reference_count >= 0 "
            "AND current_reference_count >= 0 AND skipped_binary_count >= 0 "
            "AND skipped_decode_count >= 0",
            name="ck_retrieval_corpus_runs_counts",
        ),
    )
    op.create_index(
        "ix_retrieval_corpus_runs_project_started",
        "retrieval_corpus_runs",
        ["project_id", "started_at"],
    )
    op.create_index(
        "ix_retrieval_corpus_runs_project_status",
        "retrieval_corpus_runs",
        ["project_id", "status"],
    )

    op.create_table(
        "retrieval_chunks",
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("chunker_version", sa.String(length=64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("line_count", sa.Integer(), nullable=False),
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("chunk_id", name="retrieval_chunks_pkey"),
        sa.UniqueConstraint(
            "project_id",
            "chunk_id",
            name="uq_retrieval_chunks_project_chunk",
        ),
        sa.UniqueConstraint(
            "project_id",
            "chunker_version",
            "content_sha256",
            name="uq_retrieval_chunks_project_content",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_retrieval_chunks_project_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name="ck_retrieval_chunks_sha256"),
        sa.CheckConstraint("char_count > 0", name="ck_retrieval_chunks_chars"),
        sa.CheckConstraint("line_count > 0", name="ck_retrieval_chunks_lines"),
    )
    op.create_index(
        "ix_retrieval_chunks_search_vector",
        "retrieval_chunks",
        ["search_vector"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_retrieval_chunks_project_version",
        "retrieval_chunks",
        ["project_id", "chunker_version"],
    )

    op.create_table(
        "retrieval_references",
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("corpus_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("repository_file_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("repository_symbol_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("path", sa.Text(), nullable=True),
        sa.Column("source_title", sa.Text(), nullable=True),
        sa.Column("qualified_symbol", sa.Text(), nullable=True),
        sa.Column("source_content_sha256", sa.String(length=64), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("start_char", sa.Integer(), nullable=False),
        sa.Column("end_char", sa.Integer(), nullable=False),
        sa.Column("chunk_ordinal", sa.Integer(), nullable=False),
        sa.Column("reference_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("metadata_vector", postgresql.TSVECTOR(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("reference_id", name="retrieval_references_pkey"),
        sa.UniqueConstraint(
            "project_id",
            "reference_id",
            name="uq_retrieval_references_project_reference",
        ),
        sa.UniqueConstraint(
            "project_id",
            "reference_fingerprint",
            name="uq_retrieval_references_project_fingerprint",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_retrieval_references_project_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "chunk_id"],
            ["retrieval_chunks.project_id", "retrieval_chunks.chunk_id"],
            name="fk_retrieval_references_project_chunk",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "corpus_run_id"],
            ["retrieval_corpus_runs.project_id", "retrieval_corpus_runs.run_id"],
            name="fk_retrieval_references_project_run",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "repository_file_id"],
            ["repository_files.project_id", "repository_files.file_id"],
            name="fk_retrieval_references_project_file",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "repository_symbol_id"],
            ["repository_symbols.project_id", "repository_symbols.symbol_id"],
            name="fk_retrieval_references_project_symbol",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "task_id"],
            ["tasks.project_id", "tasks.task_id"],
            name="fk_retrieval_references_project_task",
        ),
        sa.CheckConstraint(
            "source_kind IN ('REPOSITORY_FILE', 'REPOSITORY_SYMBOL', 'TASK')",
            name="ck_retrieval_references_source_kind",
        ),
        sa.CheckConstraint(
            "(source_kind = 'REPOSITORY_FILE' AND repository_file_id IS NOT NULL "
            "AND repository_symbol_id IS NULL AND task_id IS NULL) OR "
            "(source_kind = 'REPOSITORY_SYMBOL' AND repository_file_id IS NOT NULL "
            "AND repository_symbol_id IS NOT NULL AND task_id IS NULL) OR "
            "(source_kind = 'TASK' AND repository_file_id IS NULL "
            "AND repository_symbol_id IS NULL AND task_id IS NOT NULL)",
            name="ck_retrieval_references_source_identity",
        ),
        sa.CheckConstraint(
            "source_content_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_retrieval_references_source_sha256",
        ),
        sa.CheckConstraint(
            "start_line > 0 AND end_line >= start_line AND start_char >= 0 "
            "AND end_char > start_char",
            name="ck_retrieval_references_ranges",
        ),
        sa.CheckConstraint("chunk_ordinal >= 0", name="ck_retrieval_references_ordinal"),
        sa.CheckConstraint(
            "reference_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_retrieval_references_fingerprint",
        ),
    )
    op.create_index(
        "ix_retrieval_references_project_current",
        "retrieval_references",
        ["project_id", "is_current"],
    )
    op.create_index(
        "ix_retrieval_references_project_source",
        "retrieval_references",
        ["project_id", "source_kind", "is_current"],
    )
    op.create_index(
        "ix_retrieval_references_metadata_vector",
        "retrieval_references",
        ["metadata_vector"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_retrieval_references_project_file",
        "retrieval_references",
        ["project_id", "repository_file_id"],
    )
    op.create_index(
        "ix_retrieval_references_project_task",
        "retrieval_references",
        ["project_id", "task_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_retrieval_references_project_task", table_name="retrieval_references")
    op.drop_index("ix_retrieval_references_project_file", table_name="retrieval_references")
    op.drop_index("ix_retrieval_references_metadata_vector", table_name="retrieval_references")
    op.drop_index("ix_retrieval_references_project_source", table_name="retrieval_references")
    op.drop_index("ix_retrieval_references_project_current", table_name="retrieval_references")
    op.drop_table("retrieval_references")
    op.drop_index("ix_retrieval_chunks_project_version", table_name="retrieval_chunks")
    op.drop_index("ix_retrieval_chunks_search_vector", table_name="retrieval_chunks")
    op.drop_table("retrieval_chunks")
    op.drop_index("ix_retrieval_corpus_runs_project_status", table_name="retrieval_corpus_runs")
    op.drop_index("ix_retrieval_corpus_runs_project_started", table_name="retrieval_corpus_runs")
    op.drop_table("retrieval_corpus_runs")
    op.drop_constraint("uq_repository_symbols_project_symbol", "repository_symbols", type_="unique")
    op.drop_constraint("uq_tasks_project_task", "tasks", type_="unique")
