"""Host/project executor CLI for the writable HIVE executor service."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from uuid import UUID

from .config import get_settings
from .execution_orchestrator import ExecutionError, ExecutionOrchestrator, ExecutorRequest


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a UUID") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hive-execute",
        description=(
            "Execute one registered HIVE task through the configured provider and "
            "Local Verified Runner. Output remains staged and noncanonical."
        ),
    )
    parser.add_argument("--project-id", required=True, type=_uuid)
    parser.add_argument("--task-id", required=True, type=_uuid)
    parser.add_argument("--expected-branch")
    parser.add_argument("--expected-head-sha")
    parser.add_argument("--top-k", type=int, default=5, choices=range(1, 11))
    parser.add_argument(
        "--disclosure-level",
        choices=("L0", "L1", "L2", "L3", "L4", "L5"),
    )
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        request = ExecutorRequest(
            project_id=args.project_id,
            task_id=args.task_id,
            expected_branch=args.expected_branch,
            expected_head_sha=args.expected_head_sha,
            top_k=args.top_k,
            disclosure_level=args.disclosure_level,
        )
        result = ExecutionOrchestrator(get_settings()).execute_configured(request)
    except ExecutionError as exc:
        print(
            json.dumps(
                {"status": "ERROR", "code": exc.code},
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1
    except Exception:
        print(
            json.dumps(
                {"status": "ERROR", "code": "executor_unavailable"},
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1

    print(result.to_json(), end="")
    return 0 if result.status == "STAGED" else 2


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
