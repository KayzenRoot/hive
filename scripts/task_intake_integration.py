from __future__ import annotations

import hashlib
import json
import os
import socket
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from project_registry_integration import (
    ROOT,
    assert_equal,
    cleanup_temporary_root,
    compose,
    request,
    run,
    wait_for_health,
)

SCHEMA_REVISION = "0003_repository_indexing"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def make_git_project(path: Path, name: str) -> None:
    path.mkdir()
    environment = os.environ.copy()
    run(["git", "init", "-b", "main", str(path)], env=environment)
    run(
        ["git", "-C", str(path), "config", "user.email", "hive-test@example.invalid"],
        env=environment,
    )
    run(["git", "-C", str(path), "config", "user.name", "HIVE Integration Test"], env=environment)
    (path / "pyproject.toml").write_text(
        f"[project]\nname = '{name}'\nversion = '0.1.0'\n", encoding="utf-8"
    )
    run(["git", "-C", str(path), "add", "pyproject.toml"], env=environment)
    run(["git", "-C", str(path), "commit", "-m", "initial sample"], env=environment)


def make_text_pdf(path: Path) -> bytes:
    writer = PdfWriter()
    for value in ("HIVE intake first page", "HIVE intake second page"):
        page = writer.add_blank_page(width=300, height=300)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
        content = DecodedStreamObject()
        content.set_data(f"BT /F1 12 Tf 72 200 Td ({value}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(content)
    with path.open("wb") as handle:
        writer.write(handle)
    return path.read_bytes()


def multipart_upload(
    base_url: str, project_id: str, filename: str, content: bytes, title: str
) -> tuple[int, dict[str, Any]]:
    boundary = "----HIVEIntegrationBoundary"
    body = b"".join(
        [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="title"\r\n\r\n',
            title.encode("utf-8"),
            b"\r\n",
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
            b"Content-Type: application/octet-stream\r\n\r\n",
            content,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    request_object = urllib.request.Request(
        f"{base_url}/api/v1/projects/{project_id}/tasks/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request_object, timeout=15) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def download(base_url: str, project_id: str, task_id: str) -> tuple[int, bytes, dict[str, str]]:
    request_object = urllib.request.Request(
        f"{base_url}/api/v1/projects/{project_id}/tasks/{task_id}/artifact", method="GET"
    )
    try:
        with urllib.request.urlopen(request_object, timeout=15) as response:
            return (
                response.status,
                response.read(),
                {key.lower(): value for key, value in response.headers.items()},
            )
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), {key.lower(): value for key, value in exc.headers.items()}


def scalar(project_name: str, environment: dict[str, str], query: str) -> str:
    return compose(
        project_name,
        ["exec", "-T", "postgres", "psql", "-U", "hive", "-d", "hive", "-Atqc", query],
        env=environment,
    ).stdout.strip()


def main() -> int:
    api_port = free_port()
    dashboard_port = free_port()
    project_name = f"hive-intake-{os.getpid()}"
    temporary_parent = ROOT / "tmp"
    temporary_parent.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(tempfile.mkdtemp(prefix="task-intake-", dir=temporary_parent))
    environment = os.environ.copy()
    environment.update(
        {
            "HIVE_API_PORT": str(api_port),
            "HIVE_DASHBOARD_PORT": str(dashboard_port),
            "HIVE_DATA_ROOT": (temporary_root / "data").as_posix(),
            "HIVE_PROJECTS_ROOT": (temporary_root / "projects").as_posix(),
            "POSTGRES_DB": "hive",
            "POSTGRES_USER": "hive",
            "POSTGRES_PASSWORD": "hive",
        }
    )
    projects_root = temporary_root / "projects"
    data_root = temporary_root / "data"
    projects_root.mkdir()
    data_root.mkdir()
    project_a_path = projects_root / "project-a"
    project_b_path = projects_root / "project-b"
    make_git_project(project_a_path, "project-a")
    make_git_project(project_b_path, "project-b")

    passed = False
    try:
        compose(project_name, ["up", "-d", "--build"], env=environment)
        migration_version = scalar(
            project_name, environment, "SELECT version_num FROM alembic_version"
        )
        assert_equal(migration_version, SCHEMA_REVISION, "task intake migration revision")
        base_url = f"http://127.0.0.1:{api_port}"
        wait_for_health(base_url)

        status, project_a = request(
            base_url,
            "POST",
            "/api/v1/projects",
            {"name": "Project A", "relative_path": "project-a"},
        )
        assert_equal(status, 201, "project A registration")
        status, project_b = request(
            base_url,
            "POST",
            "/api/v1/projects",
            {"name": "Project B", "relative_path": "project-b"},
        )
        assert_equal(status, 201, "project B registration")
        assert isinstance(project_a, dict) and isinstance(project_b, dict)
        project_a_id = str(project_a["project_id"])
        project_b_id = str(project_b["project_id"])

        text_original = "Prompt A\r\nsecond line"
        status, text_task = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_a_id}/tasks/text",
            {"title": "Text task", "text": text_original, "format": "text"},
        )
        assert_equal(status, 201, f"TXT task status ({text_task})")
        assert isinstance(text_task, dict)
        assert_equal(text_task["source_type"], "STRUCTURED_TEXT", "structured source type")
        assert_equal(text_task["intake_status"], "READY", "TXT task status state")
        text_task_id = str(text_task["task_id"])
        status, text_payload = request(
            base_url, "GET", f"/api/v1/projects/{project_a_id}/tasks/{text_task_id}/text"
        )
        assert_equal(status, 200, "TXT text retrieval")
        assert isinstance(text_payload, dict)
        assert_equal(text_payload["text"], "Prompt A\nsecond line", "normalized TXT text")
        artifact_status, artifact_body, artifact_headers = download(
            base_url, project_a_id, text_task_id
        )
        assert_equal(artifact_status, 200, "TXT artifact status")
        assert_equal(artifact_body, text_original.encode("utf-8"), "TXT artifact exact bytes")
        assert_equal(
            artifact_headers["x-hive-original-sha256"],
            hashlib.sha256(artifact_body).hexdigest(),
            "TXT artifact digest",
        )

        status, txt_upload_task = multipart_upload(
            base_url, project_a_id, "prompt.txt", text_original.encode("utf-8"), "TXT upload"
        )
        assert_equal(status, 201, "multipart TXT task status")
        assert isinstance(txt_upload_task, dict)
        assert_equal(txt_upload_task["source_type"], "TXT", "multipart TXT source type")

        markdown_original = "# Markdown\r\n\r\nBody"
        status, markdown_task = request(
            base_url,
            "POST",
            f"/api/v1/projects/{project_a_id}/tasks/text",
            {"title": "Markdown task", "text": markdown_original, "format": "markdown"},
        )
        assert_equal(status, 201, "Markdown task status")
        assert isinstance(markdown_task, dict)
        assert_equal(markdown_task["source_type"], "MARKDOWN", "Markdown source type")
        status, markdown_upload_task = multipart_upload(
            base_url, project_a_id, "notes.md", markdown_original.encode("utf-8"), "Markdown upload"
        )
        assert_equal(status, 201, "multipart Markdown task status")
        assert isinstance(markdown_upload_task, dict)
        assert_equal(
            markdown_upload_task["source_type"], "MARKDOWN", "multipart Markdown source type"
        )

        pdf_path = temporary_root / "fixture.pdf"
        pdf_bytes = make_text_pdf(pdf_path)
        pdf_digest = hashlib.sha256(pdf_bytes).hexdigest()
        status, pdf_task = multipart_upload(
            base_url, project_a_id, "nested/evil.pdf", pdf_bytes, "PDF task"
        )
        assert_equal(status, 201, f"PDF task status ({pdf_task})")
        assert isinstance(pdf_task, dict)
        assert_equal(pdf_task["source_type"], "PDF", "PDF source type")
        assert_equal(pdf_task["page_count"], 2, "PDF page count")
        assert_equal(pdf_task["intake_status"], "READY", "PDF task status state")
        pdf_task_id = str(pdf_task["task_id"])
        assert_equal(pdf_task["original_blob_sha256"], pdf_digest, "PDF original digest")
        status, pdf_text = request(
            base_url, "GET", f"/api/v1/projects/{project_a_id}/tasks/{pdf_task_id}/text"
        )
        assert_equal(status, 200, "PDF text retrieval")
        assert isinstance(pdf_text, dict)
        assert_equal(
            pdf_text["text"],
            "HIVE intake first page\nHIVE intake second page",
            "PDF text extraction",
        )
        artifact_status, artifact_body, artifact_headers = download(
            base_url, project_a_id, pdf_task_id
        )
        assert_equal(artifact_status, 200, "PDF artifact status")
        assert_equal(artifact_body, pdf_bytes, "PDF artifact exact bytes")
        assert_equal(artifact_headers["x-hive-original-sha256"], pdf_digest, "PDF artifact digest")
        assert "\r" not in artifact_headers["content-disposition"]
        assert "\n" not in artifact_headers["content-disposition"]

        no_text_path = temporary_root / "no-text.pdf"
        no_text_writer = PdfWriter()
        no_text_writer.add_blank_page(width=300, height=300)
        with no_text_path.open("wb") as handle:
            no_text_writer.write(handle)
        no_text_bytes = no_text_path.read_bytes()
        status, no_text_task = multipart_upload(
            base_url, project_a_id, "no-text.pdf", no_text_bytes, "No text PDF"
        )
        assert_equal(status, 201, "no-text PDF task status")
        assert isinstance(no_text_task, dict)
        assert_equal(no_text_task["intake_status"], "EXTRACTION_FAILED", "no-text PDF state")
        assert_equal(no_text_task["extraction_error"], "no_extractable_text", "no-text PDF error")
        no_text_artifact_status, no_text_artifact, _ = download(
            base_url, project_a_id, str(no_text_task["task_id"])
        )
        assert_equal(no_text_artifact_status, 200, "no-text PDF artifact status")
        assert_equal(no_text_artifact, no_text_bytes, "no-text PDF exact artifact")

        status, duplicate_pdf = multipart_upload(
            base_url, project_a_id, "same-content.pdf", pdf_bytes, "Duplicate PDF"
        )
        assert_equal(status, 201, "duplicate PDF task status")
        assert isinstance(duplicate_pdf, dict)
        duplicate_pdf_id = str(duplicate_pdf["task_id"])
        assert duplicate_pdf_id != pdf_task_id
        status, cross_project_pdf = multipart_upload(
            base_url, project_b_id, "project-b.pdf", pdf_bytes, "Project B PDF"
        )
        assert_equal(status, 201, "cross-project PDF task status")
        assert isinstance(cross_project_pdf, dict)
        cross_project_task_id = str(cross_project_pdf["task_id"])

        status, wrong_project = request(
            base_url, "GET", f"/api/v1/projects/{project_b_id}/tasks/{pdf_task_id}"
        )
        assert_equal(status, 404, "wrong-project detail status")
        status, wrong_project_text = request(
            base_url, "GET", f"/api/v1/projects/{project_b_id}/tasks/{pdf_task_id}/text"
        )
        assert_equal(status, 404, "wrong-project text status")
        wrong_artifact_status, _, _ = download(base_url, project_b_id, pdf_task_id)
        assert_equal(wrong_artifact_status, 404, "wrong-project artifact status")

        extraction_count = scalar(
            project_name,
            environment,
            f"SELECT count(*) FROM task_extractions WHERE source_sha256 = '{pdf_digest}'",
        )
        assert_equal(extraction_count, "1", "deterministic PDF extraction reuse")
        status, storage = request(base_url, "GET", "/api/v1/storage")
        assert_equal(status, 200, "storage stats status")
        assert isinstance(storage, dict)
        assert_equal(storage["task_count"], 8, "storage task count")
        assert_equal(storage["unique_blob_count"], 4, "storage unique blob count")
        assert_equal(
            storage["unique_logical_bytes"],
            len(text_original.encode())
            + len(markdown_original.encode())
            + len(pdf_bytes)
            + len(no_text_bytes),
            "storage unique logical bytes",
        )
        assert_equal(
            storage["deduplication_delta_bytes"],
            len(text_original.encode()) + len(markdown_original.encode()) + len(pdf_bytes) * 2,
            "storage deduplication delta",
        )
        if storage["compression_delta_bytes"] < 0:
            assert storage["compression_savings_bytes"] is None

        compose(project_name, ["stop", "redis"], env=environment)
        status, persisted_without_redis = request(
            base_url, "GET", f"/api/v1/projects/{project_a_id}/tasks/{text_task_id}"
        )
        assert_equal(status, 200, "task availability without Redis")
        compose(project_name, ["start", "redis"], env=environment)
        wait_for_health(base_url)
        compose(project_name, ["restart", "api"], env=environment)
        wait_for_health(base_url)
        status, persisted_after_restart = request(
            base_url, "GET", f"/api/v1/projects/{project_a_id}/tasks/{pdf_task_id}"
        )
        assert_equal(status, 200, "task availability after API restart")

        cas_container_path = f"/var/lib/hive/cas/sha256/{pdf_digest[:2]}/{pdf_digest[2:]}.zst"
        compose(
            project_name,
            [
                "exec",
                "-T",
                "--user",
                "root",
                "api",
                "python",
                "-c",
                (
                    "from pathlib import Path; "
                    f"path = Path({cas_container_path!r}); "
                    "path.write_bytes(path.read_bytes()[:-1])"
                ),
            ],
            env=environment,
        )
        corrupted_status, corrupted_body, _ = download(base_url, project_a_id, pdf_task_id)
        assert_equal(corrupted_status, 500, "corrupt CAS fails closed")
        assert b"stored artifact integrity" in corrupted_body
        assert not list(projects_root.rglob("*.zst")), "CAS must stay under HIVE_DATA_ROOT"
        assert not list((temporary_root / "data").rglob("*.part")), "temporary intake files cleaned"
        print(
            json.dumps(
                {
                    "migration": migration_version,
                    "project_a": project_a_id,
                    "project_b": project_b_id,
                    "tasks": [
                        text_task_id,
                        str(txt_upload_task["task_id"]),
                        str(markdown_task["task_id"]),
                        str(markdown_upload_task["task_id"]),
                        pdf_task_id,
                        duplicate_pdf_id,
                        cross_project_task_id,
                        str(no_text_task["task_id"]),
                    ],
                    "pdf_sha256": pdf_digest,
                    "storage": storage,
                    "redis_restart": "passed",
                    "api_restart": "passed",
                    "corruption_fail_closed": "passed",
                },
                indent=2,
            )
        )
        passed = True
        return 0
    finally:
        if not passed:
            logs = compose(project_name, ["logs", "--no-color"], env=environment, check=False)
            print(logs.stdout, flush=True)
            print(logs.stderr, flush=True)
        compose(project_name, ["down", "--remove-orphans"], env=environment, check=False)
        if temporary_root.exists():
            cleanup_temporary_root(temporary_root, env=environment)


if __name__ == "__main__":
    raise SystemExit(main())
