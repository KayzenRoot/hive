"""Add project-scoped pgvector semantic retrieval state."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_semantic_retrieval"
down_revision: str | None = "0004_retrieval_lexical"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class VectorType(sa.types.UserDefinedType):
    """Variable-dimension pgvector type; application code validates dimensions."""

    cache_ok = True

    def get_col_spec(self, **_kw: object) -> str:
        return "vector"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "embedding_profiles",
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("adapter_kind", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("model_revision", sa.String(length=200), nullable=True),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("distance_metric", sa.String(length=32), nullable=False),
        sa.Column("identity_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("profile_id", name="embedding_profiles_pkey"),
        sa.UniqueConstraint(
            "identity_fingerprint", name="uq_embedding_profiles_identity_fingerprint"
        ),
        sa.CheckConstraint("dimensions BETWEEN 1 AND 2000", name="ck_embedding_profiles_dims"),
        sa.CheckConstraint(
            "distance_metric = 'cosine'", name="ck_embedding_profiles_distance_metric"
        ),
        sa.CheckConstraint(
            "identity_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_embedding_profiles_fingerprint",
        ),
    )

    op.create_table(
        "retrieval_embedding_runs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("corpus_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("newly_embedded_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reused_embedding_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider_request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.String(length=256), nullable=True),
        sa.PrimaryKeyConstraint("run_id", name="retrieval_embedding_runs_pkey"),
        sa.UniqueConstraint("project_id", "run_id", name="uq_retrieval_embedding_runs_project_run"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_retrieval_embedding_runs_project_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "corpus_run_id"],
            ["retrieval_corpus_runs.project_id", "retrieval_corpus_runs.run_id"],
            name="fk_retrieval_embedding_runs_project_corpus",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["embedding_profiles.profile_id"],
            name="fk_retrieval_embedding_runs_profile",
        ),
        sa.CheckConstraint(
            "status IN ('RUNNING', 'COMPLETED', 'FAILED', 'STALE', 'BLOCKED')",
            name="ck_retrieval_embedding_runs_status",
        ),
        sa.CheckConstraint(
            "source_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_retrieval_embedding_runs_fingerprint",
        ),
        sa.CheckConstraint(
            "current_chunk_count >= 0 AND newly_embedded_count >= 0 "
            "AND reused_embedding_count >= 0 AND failed_count >= 0 "
            "AND provider_request_count >= 0",
            name="ck_retrieval_embedding_runs_counts",
        ),
    )
    op.create_index(
        "ix_retrieval_embedding_runs_project_started",
        "retrieval_embedding_runs",
        ["project_id", "started_at"],
    )
    op.create_index(
        "ix_retrieval_embedding_runs_project_status",
        "retrieval_embedding_runs",
        ["project_id", "status"],
    )

    op.create_table(
        "retrieval_chunk_embeddings",
        sa.Column("embedding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("embedding", VectorType(), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("source_chunk_content_sha256", sa.String(length=64), nullable=False),
        sa.Column("embedding_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("embedding_id", name="retrieval_chunk_embeddings_pkey"),
        sa.UniqueConstraint(
            "project_id",
            "chunk_id",
            "profile_id",
            name="uq_retrieval_chunk_embeddings_project_chunk_profile",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "chunk_id"],
            ["retrieval_chunks.project_id", "retrieval_chunks.chunk_id"],
            name="fk_retrieval_chunk_embeddings_project_chunk",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["embedding_profiles.profile_id"],
            name="fk_retrieval_chunk_embeddings_profile",
        ),
        sa.CheckConstraint(
            "dimensions BETWEEN 1 AND 2000",
            name="ck_retrieval_chunk_embeddings_dims",
        ),
        sa.CheckConstraint(
            "source_chunk_content_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_retrieval_chunk_embeddings_source_sha256",
        ),
        sa.CheckConstraint(
            "embedding_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_retrieval_chunk_embeddings_fingerprint",
        ),
    )
    op.create_index(
        "ix_retrieval_chunk_embeddings_project_profile",
        "retrieval_chunk_embeddings",
        ["project_id", "profile_id", "dimensions"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_retrieval_chunk_embeddings_project_profile",
        table_name="retrieval_chunk_embeddings",
    )
    op.drop_table("retrieval_chunk_embeddings")
    op.drop_index(
        "ix_retrieval_embedding_runs_project_status", table_name="retrieval_embedding_runs"
    )
    op.drop_index(
        "ix_retrieval_embedding_runs_project_started", table_name="retrieval_embedding_runs"
    )
    op.drop_table("retrieval_embedding_runs")
    op.drop_table("embedding_profiles")
