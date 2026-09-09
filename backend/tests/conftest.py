from __future__ import annotations

import pytest
import scripts.review_evidence as review_evidence


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
