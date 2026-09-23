from __future__ import annotations

from uuid import UUID

from scripts.autonomous_execution_integration import (
    event_linkage_is_explicit,
    execution_run_ids_are_present,
    task_ids_are_scoped,
    terminal_replay_after_cursor,
)


def test_project_level_events_may_be_taskless_but_foreign_task_ids_fail() -> None:
    expected_task = UUID("00000000-0000-0000-0000-000000000801")
    foreign_task = UUID("00000000-0000-0000-0000-000000000802")

    assert task_ids_are_scoped([None, expected_task], expected_task)
    assert not task_ids_are_scoped([None, foreign_task], expected_task)


def test_run_ids_are_required_for_execution_events_not_project_events() -> None:
    run_id = UUID("00000000-0000-0000-0000-000000000003")

    assert execution_run_ids_are_present(
        [("project.indexing", None), ("task.ingested", None), ("run.completed", run_id)]
    )
    assert not execution_run_ids_are_present([("project.indexing", None), ("run.completed", None)])


def test_event_linkage_matches_project_task_and_execution_lifecycles() -> None:
    task_id = UUID("00000000-0000-0000-0000-000000000811")
    index_run_id = UUID("00000000-0000-0000-0000-000000000812")
    execution_run_id = UUID("00000000-0000-0000-0000-000000000813")

    assert event_linkage_is_explicit(
        [
            ("project.indexing", None, index_run_id),
            ("task.ingested", task_id, None),
            ("context.built", task_id, None),
            ("executor.started", task_id, execution_run_id),
            ("run.completed", task_id, execution_run_id),
            ("project.discovered", None, None),
        ]
    )
    assert not event_linkage_is_explicit([("project.indexing", None, None)])
    assert not event_linkage_is_explicit([("task.ingested", None, None)])
    assert not event_linkage_is_explicit([("run.completed", None, execution_run_id)])


def test_terminal_event_replay_starts_after_its_immediate_predecessor() -> None:
    events = [
        ("project.indexing", "cursor-1"),
        ("task.ingested", "cursor-2"),
        ("executor.started", "cursor-3"),
        ("run.completed", "cursor-4"),
    ]

    assert terminal_replay_after_cursor(events) == "cursor-3"
