from __future__ import annotations

import pytest
from scripts import auto_discovery_integration


def test_end_to_end_discovery_refuses_unmarked_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HIVE_WO031_ISOLATED_E2E", raising=False)
    monkeypatch.delenv("HIVE_PROJECTS_ROOT", raising=False)
    monkeypatch.delenv("HIVE_DATA_ROOT", raising=False)

    with pytest.raises(RuntimeError, match="isolated Compose test stack"):
        auto_discovery_integration.main()
