from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "tmp" / "integration-logs" / "auto-discovery.json"
MARKER = "WO031_AUTODISCOVERY_RETRIEVAL_MARKER"


def request_json(url: str, *, method: str = "GET", payload: object | None = None) -> object:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def run_git(repository: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )


def create_fixture(root: Path) -> tuple[Path, str]:
    if not root.exists():
        root.mkdir(parents=True)
    fixture = root / f".wo031-autodiscovery-{uuid4().hex[:12]}"
    fixture.mkdir()
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(fixture)],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    run_git(fixture, "config", "user.name", "HIVE WO-031 integration")
    run_git(fixture, "config", "user.email", "hive-wo031@example.invalid")
    (fixture / "README.md").write_text(
        f"# HIVE automatic discovery fixture\n\n{MARKER} proves retrieval.\n",
        encoding="utf-8",
        newline="\n",
    )
    run_git(fixture, "add", "README.md")
    run_git(fixture, "commit", "-m", "WO-031 automatic discovery fixture")
    head = subprocess.run(
        ["git", "-C", str(fixture), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    ).stdout.strip()
    return fixture, head


def main() -> int:
    api_port = os.environ.get("HIVE_API_PORT", "8000")
    api_base = f"http://127.0.0.1:{api_port}"
    if os.environ.get("HIVE_WO031_ISOLATED_E2E", "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        raise RuntimeError("set HIVE_WO031_ISOLATED_E2E only for the isolated Compose test stack")
    if not os.environ.get("HIVE_PROJECTS_ROOT") or not os.environ.get("HIVE_DATA_ROOT"):
        raise RuntimeError("isolated HIVE_DATA_ROOT and HIVE_PROJECTS_ROOT must be explicit")
    projects_root = Path(os.environ["HIVE_PROJECTS_ROOT"]).expanduser()
    if not projects_root.is_absolute():
        projects_root = ROOT / projects_root
    projects_root = projects_root.resolve()
    data_root = Path(os.environ["HIVE_DATA_ROOT"]).expanduser()
    if not data_root.is_absolute():
        data_root = ROOT / data_root
    data_root = data_root.resolve()
    if "wo031" not in str(projects_root).casefold() or "wo031" not in str(data_root).casefold():
        raise RuntimeError("isolated project and data roots must be named for the WO-031 test")
    if (
        projects_root == data_root
        or projects_root in data_root.parents
        or data_root in projects_root.parents
    ):
        raise RuntimeError("HIVE_DATA_ROOT and HIVE_PROJECTS_ROOT must be separate roots")
    if os.environ.get("HIVE_AUTO_DISCOVERY_ENABLED", "true").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        raise RuntimeError("automatic discovery is disabled for this integration run")

    fixture, head = create_fixture(projects_root)
    relative_path = fixture.relative_to(projects_root).as_posix()
    interval = int(os.environ.get("HIVE_AUTO_DISCOVERY_INTERVAL_SECONDS", "60"))
    deadline = time.monotonic() + min(300, max(120, interval * 3 + 30))
    project: dict[str, object] | None = None
    index: dict[str, object] | None = None
    corpus: dict[str, object] | None = None
    events: list[dict[str, object]] = []
    while time.monotonic() < deadline:
        listing = request_json(f"{api_base}/api/v1/projects")
        if not isinstance(listing, list):
            raise RuntimeError("project registry response is not a list")
        project = next(
            (
                item
                for item in listing
                if isinstance(item, dict) and item.get("relative_path") == relative_path
            ),
            None,
        )
        if project is None:
            time.sleep(2)
            continue
        project_id = str(project["project_id"])
        try:
            index_result = request_json(f"{api_base}/api/v1/projects/{project_id}/index/status")
            corpus_result = request_json(
                f"{api_base}/api/v1/projects/{project_id}/retrieval/corpus"
            )
            event_result = request_json(f"{api_base}/api/v1/projects/{project_id}/events?limit=100")
            if (
                not isinstance(index_result, dict)
                or not isinstance(corpus_result, dict)
                or not isinstance(event_result, dict)
            ):
                raise RuntimeError("discovery integration received malformed project evidence")
            index = index_result
            corpus = corpus_result
            event_list = event_result.get("events")
            events = (
                [item for item in event_list if isinstance(item, dict)]
                if isinstance(event_list, list)
                else []
            )
            if (
                index.get("status") == "COMPLETED"
                and corpus.get("state") == "CURRENT"
                and any(item.get("event_type") == "project.discovered" for item in events)
                and any(item.get("event_type") == "project.indexing" for item in events)
            ):
                break
        except urllib.error.HTTPError as exc:
            if exc.code not in {404, 503}:
                raise
        time.sleep(2)
    if project is None or index is None or corpus is None:
        raise RuntimeError("automatic discovery/index/retrieval did not complete within the bound")
    if index.get("status") != "COMPLETED" or corpus.get("state") != "CURRENT":
        raise RuntimeError(
            "automatic discovery did not produce a completed index and current corpus"
        )

    project_id = str(project["project_id"])
    retrieval = request_json(
        f"{api_base}/api/v1/projects/{project_id}/retrieval/lexical",
        method="POST",
        payload={"query": MARKER, "top_k": 5, "source_kind": "REPOSITORY_FILE"},
    )
    if not isinstance(retrieval, dict) or not isinstance(retrieval.get("results"), list):
        raise RuntimeError("retrieval response is malformed")
    matched = any(
        isinstance(item, dict) and MARKER in str(item.get("snippet", ""))
        for item in retrieval["results"]
    )
    if not matched:
        raise RuntimeError("auto-discovered repository marker was not retrievable")

    evidence = {
        "schema_version": 1,
        "status": "PASS",
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "auto_registration_without_post": True,
        "fixture_relative_path": relative_path,
        "fixture_head_sha": head,
        "project_id": project_id,
        "index_status": index.get("status"),
        "indexed_file_count": index.get("indexed_file_count"),
        "corpus_state": corpus.get("state"),
        "corpus_chunk_count": corpus.get("chunk_count"),
        "discovery_event_observed": any(
            item.get("event_type") == "project.discovered" for item in events
        ),
        "indexing_event_observed": any(
            item.get("event_type") == "project.indexing" for item in events
        ),
        "retrieval_marker_matched": matched,
        "fixture_retained_in_isolated_projects_root": True,
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, urllib.error.URLError) as exc:
        print(
            f"Automatic discovery integration failed: {type(exc).__name__}: {exc}", file=sys.stderr
        )
        raise SystemExit(1) from exc
