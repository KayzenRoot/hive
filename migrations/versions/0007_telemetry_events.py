"""Add the project-scoped durable Telemetry/Event Bus event history."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_telemetry_events"
down_revision: str | None = "0006_memory_lifecycle_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_tasks_project_task'
            ) THEN
                ALTER TABLE tasks ADD CONSTRAINT uq_tasks_project_task
                    UNIQUE (project_id, task_id);
            END IF;
        END $$;
        """
    )
    op.create_table(
        "telemetry_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("envelope_version", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "ordering_id",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("payload", jsonb, nullable=False),
        sa.Column("provenance", jsonb, nullable=False),
        sa.Column("emission_key", sa.String(length=256), nullable=False),
        sa.PrimaryKeyConstraint("event_id", name="telemetry_events_pkey"),
        sa.UniqueConstraint("ordering_id", name="uq_telemetry_events_ordering_id"),
        sa.UniqueConstraint(
            "project_id", "emission_key", name="uq_telemetry_events_project_emission"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.project_id"],
            name="fk_telemetry_events_project",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "task_id"],
            ["tasks.project_id", "tasks.task_id"],
            name="fk_telemetry_events_project_task",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "envelope_version = 'telemetry-event-bus-v1'",
            name="ck_telemetry_events_envelope_version",
        ),
        sa.CheckConstraint(
            "event_type IN ("
            "'project.discovered', 'project.indexing', 'task.ingested', "
            "'context.started', 'context.retrieved', 'context.built', "
            "'cache.hit', 'cache.miss', 'executor.started', 'tool.called', "
            "'file.changed', 'test.started', 'test.finished', "
            "'validation.failed', 'validation.passed', 'memory.staged', "
            "'memory.promoted', 'run.completed', 'run.failed'"
            ")",
            name="ck_telemetry_events_type",
        ),
        sa.CheckConstraint("length(btrim(emission_key)) > 0", name="ck_telemetry_events_key"),
        sa.CheckConstraint("jsonb_typeof(payload) = 'object'", name="ck_telemetry_events_payload"),
        sa.CheckConstraint(
            "jsonb_typeof(provenance) = 'object'", name="ck_telemetry_events_provenance"
        ),
    )
    op.create_index(
        "ix_telemetry_events_project_ordering",
        "telemetry_events",
        ["project_id", "ordering_id"],
    )
    op.create_index(
        "ix_telemetry_events_project_occurred",
        "telemetry_events",
        ["project_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_telemetry_events_project_occurred", table_name="telemetry_events")
    op.drop_index("ix_telemetry_events_project_ordering", table_name="telemetry_events")
    op.drop_table("telemetry_events")
    op.execute("ALTER TABLE tasks DROP CONSTRAINT IF EXISTS uq_tasks_project_task")
