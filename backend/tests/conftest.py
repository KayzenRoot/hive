from __future__ import annotations

import os
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
import scripts.review_evidence as review_evidence

if TYPE_CHECKING:
    from app.config import Settings

_HOST_SETTINGS_ENV = {
    name: value
    for name, value in os.environ.items()
    if name.startswith("HIVE_") or name in {"POSTGRES_DSN", "REDIS_URL", "CORS_ORIGINS"}
}
for _name in _HOST_SETTINGS_ENV:
    os.environ.pop(_name, None)
os.environ["HIVE_AUTO_DISCOVERY_ENABLED"] = "false"


def pytest_unconfigure(config: pytest.Config) -> None:
    """Restore caller settings after collection and tests are completely finished."""

    del config
    os.environ.update(_HOST_SETTINGS_ENV)


@pytest.fixture(autouse=True)
def historical_governance_schema_fixture(
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep the WO-016-P-G1 fixture independent of the current schema head."""
    if request.node.name == "test_wo016p_governance_requires_six_row_acce_lineage":
        monkeypatch.setattr(
            review_evidence,
            "migration_head",
            lambda: "0006_memory_lifecycle_provenance",
        )


@pytest.fixture
def isolated_settings_factory() -> Callable[..., Settings]:
    """Provide settings which cannot read the host environment or repository .env."""

    from app.config import Settings

    return Settings.for_testing
