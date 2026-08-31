"""Create the durable Project Registry table."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_create_projects"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE hive_project_state AS ENUM (
                'OFFLINE', 'STALE', 'INDEXING', 'READY', 'ACTIVE', 'DEGRADED', 'BLOCKED'
            );
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.create_table(
        "projects",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("git_branch", sa.Text(), nullable=True),
        sa.Column("git_head_sha", sa.Text(), nullable=True),
        sa.Column("detached_head", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("repository_accessible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("working_tree_clean", sa.Boolean(), nullable=True),
        sa.Column(
            "language_stack",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "state",
            postgresql.ENUM(
                "OFFLINE",
                "STALE",
                "INDEXING",
                "READY",
                "ACTIVE",
                "DEGRADED",
                "BLOCKED",
                name="hive_project_state",
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'OFFLINE'"),
        ),
        sa.Column("inspection_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("last_inspected_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("project_id", name="projects_pkey"),
        sa.UniqueConstraint("relative_path", name="uq_projects_relative_path"),
        sa.CheckConstraint("length(btrim(name)) > 0", name="ck_projects_name_not_blank"),
        sa.CheckConstraint(
            "length(btrim(relative_path)) > 0", name="ck_projects_relative_path_not_blank"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(language_stack) = 'array'", name="ck_projects_language_stack_array"
        ),
    )
    op.create_index("ix_projects_last_inspected_at", "projects", ["last_inspected_at"])


def downgrade() -> None:
    op.drop_index("ix_projects_last_inspected_at", table_name="projects")
    op.drop_table("projects")
    op.execute("DROP TYPE hive_project_state")
