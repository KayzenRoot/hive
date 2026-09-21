from __future__ import annotations

from pathlib import Path

import pytest
from scripts.release_publisher_contract import validate_publisher_inputs


def candidate(version: str) -> dict[str, object]:
    return {
        "product": "HIVE",
        "status": "release-candidate",
        "release_published": False,
        "version": version,
        "tag": f"v{version}",
        "dependency_security": {
            "release_gate": "PASS",
            "runtime_high_critical_remaining": False,
            "remaining_open": {"critical": 0, "high": 0},
        },
    }


def request(version: str, work_order: str) -> dict[str, object]:
    return {
        "status": "armed",
        "product": "HIVE",
        "version": version,
        "tag": f"v{version}",
        "work_order": work_order,
        "authorized_parent": "b" * 40,
    }


def validate(version: str, work_order: str) -> None:
    validate_publisher_inputs(
        request=request(version, work_order),
        candidate=candidate(version),
        version=version,
        tag=f"v{version}",
        source_sha="a" * 40,
        observed_parent="b" * 40,
    )


def test_historical_v100_publish_request_remains_compatible() -> None:
    validate("1.0.0", "HIVE-REL-002")


def test_v101_future_publish_request_is_version_bound() -> None:
    validate("1.0.1", "HIVE-REL-006")


def test_unknown_publish_request_work_order_fails_closed() -> None:
    with pytest.raises(ValueError, match="work_order mismatch"):
        validate("1.0.1", "HIVE-REL-999")


def test_completed_release_noop_check_precedes_request_validation() -> None:
    workflow = (
        Path(__file__).parents[2] / ".github" / "workflows" / "release-publisher.yml"
    ).read_text(encoding="utf-8")
    terminal_check = workflow.index(
        "is already fully published with final receipt; publisher will no-op"
    )
    request_validation = workflow.index('python - "$request" "$candidate" "$version"')
    assert terminal_check < request_validation
