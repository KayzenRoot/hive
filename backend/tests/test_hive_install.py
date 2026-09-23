from __future__ import annotations

from pathlib import Path

import pytest
from scripts.hive_install import configured_roots, safe_roots


def test_install_root_safety_requires_distinct_non_nested_paths(tmp_path: Path) -> None:
    data = tmp_path / "hive-data"
    projects = tmp_path / "projects"

    assert safe_roots(data, projects) == (data.resolve(), projects.resolve())
    with pytest.raises(ValueError, match="separate"):
        safe_roots(data, data / "projects")
    with pytest.raises(ValueError, match="separate"):
        safe_roots(data, data)


def test_doctor_extracts_roots_from_expanded_compose_bind_mounts(tmp_path: Path) -> None:
    data = tmp_path / "isolated-data"
    projects = tmp_path / "isolated-projects"
    configuration = {
        "services": {
            "api": {
                "volumes": [
                    {"source": str(data), "target": "/var/lib/hive"},
                    {"source": str(projects), "target": "/workspace/projects"},
                ]
            },
            "postgres": {
                "volumes": [
                    {"source": str(data / "postgres"), "target": "/var/lib/postgresql/data"}
                ]
            },
        }
    }

    assert configured_roots(configuration) == (data.resolve(), projects.resolve())


def test_doctor_rejects_unexpected_postgres_root(tmp_path: Path) -> None:
    data = tmp_path / "isolated-data"
    configuration = {
        "services": {
            "api": {
                "volumes": [
                    {"source": str(data), "target": "/var/lib/hive"},
                    {"source": str(tmp_path / "projects"), "target": "/workspace/projects"},
                ]
            },
            "postgres": {
                "volumes": [
                    {"source": str(tmp_path / "other"), "target": "/var/lib/postgresql/data"}
                ]
            },
        }
    }

    with pytest.raises(ValueError, match="expected child"):
        configured_roots(configuration)
