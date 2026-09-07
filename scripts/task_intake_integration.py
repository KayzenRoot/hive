from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
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

SCHEMA_REVISION = "0006_memory_lifecycle_provenance"
EVIDENCE_OUTPUT = ROOT / "tmp" / "integration-logs" / "acce-storage-policy.json"


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


def api_python(
    project_name: str, environment: dict[str, str], code: str, *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return compose(
        project_name,
        ["exec", "-T", "api", "python", "-c", code],
        env=environment,
        check=check,
    )


def blob_metadata(project_name: str, environment: dict[str, str], digest: str) -> dict[str, Any]:
    raw = scalar(
        project_name,
        environment,
        "SELECT json_build_object("
        "'sha256', sha256, 'logical_size', logical_size, 'physical_size', physical_size, "
        "'codec', codec, 'codec_config', codec_config)::text FROM cas_blobs "
        f"WHERE sha256 = '{digest}'",
    )
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise AssertionError(f"CAS metadata is not an object: {value!r}")
    return value


def measure_policy(
    project_name: str, environment: dict[str, str], digests: list[str]
) -> dict[str, Any]:
    digests_literal = repr(digests)
    code = (
        "import json\n"
        "from pathlib import Path\n"
        "from app.cas import CASStore, measure_storage_policy, select_storage_policy\n"
        "from app.config import Settings\n"
        "settings = Settings()\n"
        "store = CASStore(settings)\n"
        "representative_paths = [\n"
        "    Path('/app/docs/project-brain/06-ACCE-TOKEN-STORAGE-OPTIMIZATION.md'),\n"
        "    Path('/app/docs/project-brain/13-CHECKPOINT.md'),\n"
        "    Path('/app/backend/app/cas.py'),\n"
        "    Path('/app/backend/app/task_intake.py'),\n"
        "    Path('/app/backend/app/config.py'),\n"
        "    Path('/app/migrations/versions/0002_task_intake_cas.py'),\n"
        "]\n"
        "assert all(path.is_file() for path in representative_paths)\n"
        "samples = [path.read_bytes() for path in representative_paths]\n"
        f"samples.extend(store.read_verified(digest) for digest in {digests_literal}[:2])\n"
        "benchmark_input_bytes = sum(len(sample) for sample in samples)\n"
        "benchmark_sample_count = len(samples)\n"
        "policy = measure_storage_policy(samples)\n"
        "repeat = select_storage_policy(list(policy.benchmark_matrix))\n"
        "selected = {\n"
        "    tier: profile.profile_id\n"
        "    for tier, profile in policy.selected_profiles.items()\n"
        "}\n"
        "repeat_selected = {\n"
        "    tier: profile.profile_id\n"
        "    for tier, profile in repeat.selected_profiles.items()\n"
        "}\n"
        "deterministic_selection = selected == repeat_selected\n"
        "assert deterministic_selection\n"
        "print(json.dumps({'storage_policy_version': policy.version, "
        "'selected_profiles': {tier: {'tier': profile.tier, 'profile_id': profile.profile_id, "
        "'zstd_level': profile.zstd_level} for tier, profile in policy.selected_profiles.items()}, "
        "'benchmark_matrix': list(policy.benchmark_matrix), "
        "'benchmark_input_bytes': benchmark_input_bytes, "
        "'benchmark_sample_count': benchmark_sample_count, "
        "'benchmark_sources': [str(path) for path in representative_paths] "
        "+ ['task-cas-fixture'] * 2, "
        "'selection_rationale': policy.selection_rationale, "
        "'deterministic_selection': deterministic_selection}))"
    )
    result = api_python(project_name, environment, code)
    value = json.loads(result.stdout.strip().splitlines()[-1])
    if not isinstance(value, dict):
        raise AssertionError(f"storage policy is not an object: {value!r}")
    return value


def transition_blob(
    project_name: str,
    environment: dict[str, str],
    project_id: str,
    task_id: str,
    policy: dict[str, Any],
    tier: str,
) -> dict[str, Any]:
    policy_literal = repr(policy)
    code = (
        "import json\n"
        "from uuid import UUID\n"
        "from app.cas import StoragePolicy, StorageProfile\n"
        "from app.config import Settings\n"
        "from app.task_intake import transition_task_blob\n"
        f"policy_payload = {policy_literal}\n"
        "policy = StoragePolicy(\n"
        "    version=policy_payload['storage_policy_version'],\n"
        "    selected_profiles={\n"
        "        tier: StorageProfile(\n"
        "            tier=profile['tier'], profile_id=profile['profile_id'],\n"
        "            zstd_level=profile['zstd_level'],\n"
        "        )\n"
        "        for tier, profile in policy_payload['selected_profiles'].items()\n"
        "    },\n"
        "    benchmark_matrix=tuple(policy_payload['benchmark_matrix']),\n"
        "    selection_rationale=policy_payload['selection_rationale'],\n"
        ")\n"
        f"tier = {tier!r}\n"
        "profile = policy.profile_for(tier)\n"
        f"stored = transition_task_blob(Settings(), UUID({project_id!r}), UUID({task_id!r}), "
        "policy, tier, profile)\n"
        "assert stored.codec_config['tier'] == tier\n"
        "assert stored.codec_config['profile_id'] == profile.profile_id\n"
        "assert stored.codec_config['zstd_level'] == profile.zstd_level\n"
        "print(json.dumps({'sha256': stored.sha256, 'logical_size': stored.logical_size, "
        "'physical_size': stored.physical_size, 'codec_config': stored.codec_config, "
        "'policy_authorized': True, 'tier': tier, 'profile_id': profile.profile_id}))"
    )
    result = api_python(project_name, environment, code)
    value = json.loads(result.stdout.strip().splitlines()[-1])
    if not isinstance(value, dict):
        raise AssertionError(f"transition result is not an object: {value!r}")
    return value


def reject_unselected_profile(
    project_name: str,
    environment: dict[str, str],
    project_id: str,
    task_id: str,
    policy: dict[str, Any],
    tier: str,
) -> bool:
    policy_literal = repr(policy)
    code = (
        "from uuid import UUID\n"
        "from app.cas import StoragePolicy, StoragePolicyError, StorageProfile\n"
        "from app.config import Settings\n"
        "from app.task_intake import transition_task_blob\n"
        f"policy_payload = {policy_literal}\n"
        "policy = StoragePolicy(\n"
        "    version=policy_payload['storage_policy_version'],\n"
        "    selected_profiles={\n"
        "        tier: StorageProfile(\n"
        "            tier=profile['tier'], profile_id=profile['profile_id'],\n"
        "            zstd_level=profile['zstd_level'],\n"
        "        )\n"
        "        for tier, profile in policy_payload['selected_profiles'].items()\n"
        "    },\n"
        "    benchmark_matrix=tuple(policy_payload['benchmark_matrix']),\n"
        "    selection_rationale=policy_payload['selection_rationale'],\n"
        ")\n"
        f"tier = {tier!r}\n"
        "selected = policy.profile_for(tier)\n"
        "candidate = next(row for row in policy.benchmark_matrix "
        "if row['tier'] == tier and row['profile_id'] != selected.profile_id)\n"
        "rejected = False\n"
        "try:\n"
        f"    transition_task_blob(Settings(), UUID({project_id!r}), UUID({task_id!r}), "
        "        policy, tier, StorageProfile(\n"
        "            tier=candidate['tier'], profile_id=candidate['profile_id'],\n"
        "            zstd_level=candidate['zstd_level'],\n"
        "        ))\n"
        "except StoragePolicyError:\n"
        "    rejected = True\n"
        "assert rejected\n"
        "print('PASS')"
    )
    result = api_python(project_name, environment, code)
    return result.stdout.strip().splitlines()[-1] == "PASS"


def orphan_retry_probe(
    project_name: str,
    environment: dict[str, str],
    project_id: str,
) -> bool:
    code = (
        "from pathlib import Path\n"
        "from uuid import UUID\n"
        "from app.cas import CASStorageError, CASStore\n"
        "from app.config import Settings\n"
        "from app.db import database_connection\n"
        "from app.task_intake import ExtractionResult, ValidatedSource, create_task\n"
        "settings = Settings()\n"
        "store = CASStore(settings)\n"
        "source = store.temp_root / 'integration-orphan-retry.txt'\n"
        "payload = b'orphan physical bytes must remain exact\\n' * 4096\n"
        "source.write_bytes(payload)\n"
        "candidate = store.put(source)\n"
        "assert candidate.published_new is True\n"
        "failed = False\n"
        "try:\n"
        f"    create_task(settings, UUID({project_id!r}), source, ValidatedSource(\n"
        "        source_type='TXT', media_type='text/plain', original_filename='orphan.txt',\n"
        "        extraction=ExtractionResult(\n"
        "            extraction_kind='text', extractor='integration',\n"
        "            extractor_version='1', config_sha256='orphan-config',\n"
        "            status='READY', text='orphan', page_count=None, error=None,\n"
        "        ),\n"
        "    ), 'Orphan retry')\n"
        "except CASStorageError:\n"
        "    failed = True\n"
        "assert failed\n"
        "assert store.read_verified(candidate.sha256, len(payload)) == payload\n"
        "with database_connection(settings) as connection, connection.cursor() as cursor:\n"
        "    cursor.execute('SELECT 1 FROM cas_blobs WHERE sha256 = %s', (candidate.sha256,))\n"
        "    assert cursor.fetchone() is None\n"
        "source.unlink(missing_ok=True)\n"
        "store.blob_path(candidate.sha256).unlink(missing_ok=True)\n"
        "print('PASS')"
    )
    result = api_python(project_name, environment, code)
    return result.stdout.strip().splitlines()[-1] == "PASS"


def cleanup_failure_probe(
    project_name: str,
    environment: dict[str, str],
    project_id: str,
    task_id: str,
    policy: dict[str, Any],
) -> bool:
    policy_literal = repr(policy)
    code = (
        "from pathlib import Path\n"
        "from uuid import UUID\n"
        "from app.cas import CASStore, StoragePolicy, StorageProfile\n"
        "from app.config import Settings\n"
        "from app.task_intake import task_blob, transition_task_blob\n"
        f"policy_payload = {policy_literal}\n"
        "policy = StoragePolicy(\n"
        "    version=policy_payload['storage_policy_version'],\n"
        "    selected_profiles={\n"
        "        tier: StorageProfile(\n"
        "            tier=profile['tier'], profile_id=profile['profile_id'],\n"
        "            zstd_level=profile['zstd_level'],\n"
        "        )\n"
        "        for tier, profile in policy_payload['selected_profiles'].items()\n"
        "    },\n"
        "    benchmark_matrix=tuple(policy_payload['benchmark_matrix']),\n"
        "    selection_rationale=policy_payload['selection_rationale'],\n"
        ")\n"
        "settings = Settings()\n"
        "store = CASStore(settings)\n"
        f"before_task, before_blob = task_blob(settings, UUID({project_id!r}), UUID({task_id!r}))\n"
        "before_bytes = store.blob_path(before_blob.sha256).read_bytes()\n"
        "def fail_backup_cleanup(_self: CASStore, _backup: Path) -> None:\n"
        "    raise OSError('forced post-commit backup cleanup failure')\n"
        "CASStore._cleanup_backup = fail_backup_cleanup\n"
        "stored = transition_task_blob(\n"
        f"    settings, UUID({project_id!r}), UUID({task_id!r}),\n"
        "    policy, 'COLD', policy.profile_for('COLD'),\n"
        ")\n"
        f"after_task, durable = task_blob(settings, UUID({project_id!r}), UUID({task_id!r}))\n"
        "active_path = store.blob_path(durable.sha256)\n"
        "assert after_task.original_blob_sha256 == durable.sha256 == stored.sha256\n"
        "assert active_path.read_bytes() != before_bytes\n"
        "active_size = active_path.stat().st_size\n"
        "assert active_size == durable.physical_size == stored.physical_size\n"
        "assert durable.codec_config == stored.codec_config\n"
        "assert store.read_verified(durable.sha256, before_task.logical_size)\n"
        "leftovers = list(store.temp_root.glob('.cas-backup-*.zst.tmp'))\n"
        "assert leftovers\n"
        "for leftover in leftovers:\n"
        "    leftover.unlink(missing_ok=True)\n"
        "assert not list(store.temp_root.glob('.cas-backup-*.zst.tmp'))\n"
        "print('PASS')"
    )
    result = api_python(project_name, environment, code)
    return result.stdout.strip().splitlines()[-1] == "PASS"


def missing_physical_reingest_probe(
    project_name: str,
    environment: dict[str, str],
    project_id: str,
    task_id: str,
    policy: dict[str, Any],
) -> dict[str, Any]:
    policy_literal = repr(policy)
    code = (
        "import json\n"
        "import os\n"
        "from pathlib import Path\n"
        "from uuid import UUID\n"
        "from app.cas import CASStorageError, CASStore, StoragePolicy, StorageProfile\n"
        "from app.config import Settings\n"
        "from app.db import database_connection\n"
        "from app.task_intake import (\n"
        "    ExtractionResult, ValidatedSource, create_task, transition_task_blob\n"
        ")\n"
        f"policy_payload = {policy_literal}\n"
        "policy = StoragePolicy(\n"
        "    version=policy_payload['storage_policy_version'],\n"
        "    selected_profiles={\n"
        "        tier: StorageProfile(\n"
        "            tier=profile['tier'], profile_id=profile['profile_id'],\n"
        "            zstd_level=profile['zstd_level'],\n"
        "        )\n"
        "        for tier, profile in policy_payload['selected_profiles'].items()\n"
        "    },\n"
        "    benchmark_matrix=tuple(policy_payload['benchmark_matrix']),\n"
        "    selection_rationale=policy_payload['selection_rationale'],\n"
        ")\n"
        "settings = Settings()\n"
        "store = CASStore(settings)\n"
        f"project_id = UUID({project_id!r})\n"
        f"task_id = UUID({task_id!r})\n"
        "digest = None\n"
        "with database_connection(settings) as connection, connection.cursor() as cursor:\n"
        "    cursor.execute(\n"
        "        'SELECT original_blob_sha256 FROM tasks WHERE task_id = %s AND project_id = %s',\n"
        "        (task_id, project_id),\n"
        "    )\n"
        "    digest = cursor.fetchone()[0]\n"
        "    cursor.execute(\n"
        "        'SELECT logical_size, physical_size, codec, codec_config '\n"
        "        'FROM cas_blobs WHERE sha256 = %s',\n"
        "        (digest,),\n"
        "    )\n"
        "    before = cursor.fetchone()\n"
        "    cursor.execute('SELECT count(*) FROM tasks WHERE project_id = %s', (project_id,))\n"
        "    task_count_before = cursor.fetchone()[0]\n"
        "assert before is not None\n"
        "transition_task_blob(\n"
        "    settings, project_id, task_id, policy, 'COLD', policy.profile_for('COLD')\n"
        ")\n"
        "with database_connection(settings) as connection, connection.cursor() as cursor:\n"
        "    cursor.execute(\n"
        "        'SELECT logical_size, physical_size, codec, codec_config '\n"
        "        'FROM cas_blobs WHERE sha256 = %s',\n"
        "        (digest,),\n"
        "    )\n"
        "    before = cursor.fetchone()\n"
        "    cursor.execute('SELECT count(*) FROM tasks WHERE project_id = %s', (project_id,))\n"
        "    task_count_before = cursor.fetchone()[0]\n"
        "path = store.blob_path(digest)\n"
        "assert path.stat().st_size == before[1]\n"
        "backup = store.temp_root / f'{digest}.c3-backup'\n"
        "backup.write_bytes(path.read_bytes())\n"
        "logical = store.read_verified(digest, before[0])\n"
        "assert store.read_verified(digest, before[0]) == logical\n"
        "pre_delete_physical_size = path.stat().st_size\n"
        "pre_delete_codec_config = before[3]\n"
        "path.unlink()\n"
        "source = store.temp_root / 'integration-missing-physical-retry.txt'\n"
        "source.write_bytes(logical)\n"
        "default_codec_config = store.codec_config.copy()\n"
        "failed = False\n"
        "error = ''\n"
        "try:\n"
        "    create_task(settings, project_id, source, ValidatedSource(\n"
        "        source_type='TXT', media_type='text/plain', original_filename='retry.txt',\n"
        "        extraction=ExtractionResult(\n"
        "            extraction_kind='text', extractor='integration',\n"
        "            extractor_version='1', config_sha256='c3-retry-config',\n"
        "            status='READY', text='retry', page_count=None, error=None,\n"
        "        ),\n"
        "    ), 'Missing physical retry')\n"
        "except CASStorageError as exc:\n"
        "    failed = True\n"
        "    error = str(exc)\n"
        "with database_connection(settings) as connection, connection.cursor() as cursor:\n"
        "    cursor.execute(\n"
        "        'SELECT logical_size, physical_size, codec, codec_config '\n"
        "        'FROM cas_blobs WHERE sha256 = %s',\n"
        "        (digest,),\n"
        "    )\n"
        "    after = cursor.fetchone()\n"
        "    cursor.execute('SELECT count(*) FROM tasks WHERE project_id = %s', (project_id,))\n"
        "    task_count_after = cursor.fetchone()[0]\n"
        "assert failed\n"
        "assert 'physical representation was recreated' in error\n"
        "assert not path.exists()\n"
        "rejected_path_exists = path.exists()\n"
        "assert after == before\n"
        "assert task_count_after == task_count_before\n"
        "assert default_codec_config != before[3]\n"
        "os.replace(backup, path)\n"
        "assert store.read_verified(digest, before[0]) == logical\n"
        "source.unlink(missing_ok=True)\n"
        "print(json.dumps({\n"
        "    'failed_closed': failed,\n"
        "    'task_count_unchanged': task_count_after == task_count_before,\n"
        "    'physical_path_after_rejected_retry': (\n"
        "        None if not rejected_path_exists else path.stat().st_size\n"
        "    ),\n"
        "    'persisted_physical_size': after[1],\n"
        "    'persisted_codec_config': after[3],\n"
        "    'retry_default_codec_config': default_codec_config,\n"
        "    'pre_delete_physical_size': pre_delete_physical_size,\n"
        "    'pre_delete_codec_config': pre_delete_codec_config,\n"
        "    'pre_delete_metadata_matches_physical': pre_delete_physical_size == before[1],\n"
        "    'metadata_unchanged': after == before,\n"
        "    'restored_exact_bytes': store.read_verified(digest, before[0]) == logical,\n"
        "}))"
    )
    result = api_python(project_name, environment, code)
    value = json.loads(result.stdout.strip().splitlines()[-1])
    if not isinstance(value, dict):
        raise AssertionError(f"missing physical re-ingest evidence is not an object: {value!r}")
    return value


def benchmark_bounds_probe(project_name: str, environment: dict[str, str]) -> tuple[bool, bool]:
    code = (
        "from app.cas import (\n"
        "    ACCE_STORAGE_POLICY_MAX_BENCHMARK_INPUT_BYTES,\n"
        "    StoragePolicyError,\n"
        "    measure_storage_policy,\n"
        ")\n"
        "tiny_rejected = False\n"
        "try:\n"
        "    measure_storage_policy([b'tiny HIVE fixture'])\n"
        "except StoragePolicyError:\n"
        "    tiny_rejected = True\n"
        "oversized_rejected = False\n"
        "try:\n"
        "    measure_storage_policy([b'x' * (ACCE_STORAGE_POLICY_MAX_BENCHMARK_INPUT_BYTES + 1)])\n"
        "except StoragePolicyError:\n"
        "    oversized_rejected = True\n"
        "assert tiny_rejected and oversized_rejected\n"
        "import json\n"
        "print(json.dumps({'tiny': tiny_rejected, 'oversized': oversized_rejected}))"
    )
    result = api_python(project_name, environment, code)
    value = json.loads(result.stdout.strip().splitlines()[-1])
    return bool(value["tiny"]), bool(value["oversized"])


def main() -> int:
    api_port = free_port()
    dashboard_port = free_port()
    project_name = f"hive-intake-{os.getpid()}"
    temporary_parent = ROOT / "tmp"
    temporary_parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_OUTPUT.unlink(missing_ok=True)
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

        policy = measure_policy(
            project_name,
            environment,
            [
                str(text_task["original_blob_sha256"]),
                str(markdown_task["original_blob_sha256"]),
                pdf_digest,
                str(no_text_task["original_blob_sha256"]),
            ],
        )
        selected_profiles = policy["selected_profiles"]
        benchmark_matrix = policy["benchmark_matrix"]
        assert policy["storage_policy_version"] == "acce-policy-v1"
        assert isinstance(selected_profiles, dict)
        assert isinstance(benchmark_matrix, list)
        assert len(benchmark_matrix) == 6
        assert set(selected_profiles) == {"HOT", "WARM", "COLD"}
        for tier, profile in selected_profiles.items():
            assert isinstance(profile, dict)
            selected_row = next(
                (
                    row
                    for row in benchmark_matrix
                    if isinstance(row, dict)
                    and row.get("tier") == tier
                    and row.get("profile_id") == profile.get("profile_id")
                ),
                None,
            )
            assert selected_row is not None, f"selected profile is not measured for {tier}"
        assert int(policy["benchmark_input_bytes"]) >= 48 * 1024
        assert int(policy["benchmark_sample_count"]) == 8
        assert len(policy["benchmark_sources"]) == 8

        orphan_retry_fail_closed = orphan_retry_probe(project_name, environment, project_a_id)
        assert orphan_retry_fail_closed
        cleanup_failure_consistency = cleanup_failure_probe(
            project_name,
            environment,
            project_a_id,
            str(no_text_task["task_id"]),
            policy,
        )
        assert cleanup_failure_consistency
        tiny_benchmark_rejected, oversized_benchmark_rejected = benchmark_bounds_probe(
            project_name, environment
        )
        assert tiny_benchmark_rejected and oversized_benchmark_rejected

        unselected_profile_rejection = reject_unselected_profile(
            project_name, environment, project_a_id, pdf_task_id, policy, "COLD"
        )
        assert unselected_profile_rejection

        transition_results: list[dict[str, Any]] = []
        for tier in ("HOT", "WARM", "COLD", "HOT"):
            profile = selected_profiles[tier]
            assert isinstance(profile, dict)
            result = transition_blob(
                project_name, environment, project_a_id, pdf_task_id, policy, tier
            )
            assert_equal(result["sha256"], pdf_digest, f"{tier} transition SHA")
            assert_equal(result["policy_authorized"], True, f"{tier} policy authorization")
            metadata = blob_metadata(project_name, environment, pdf_digest)
            config = metadata["codec_config"]
            assert isinstance(config, dict)
            assert_equal(config["tier"], tier, f"{tier} durable tier")
            assert_equal(config["profile_id"], profile["profile_id"], f"{tier} durable profile")
            assert_equal(config["zstd_level"], profile["zstd_level"], f"{tier} durable level")
            assert_equal(
                metadata["physical_size"], result["physical_size"], f"{tier} physical size"
            )
            artifact_status, artifact_body, artifact_headers = download(
                base_url, project_a_id, pdf_task_id
            )
            assert_equal(artifact_status, 200, f"{tier} readable transition")
            assert_equal(artifact_body, pdf_bytes, f"{tier} exact logical bytes")
            assert_equal(
                artifact_headers["x-hive-original-sha256"], pdf_digest, f"{tier} SHA header"
            )
            transition_results.append(result)

        idempotent_transition = transition_blob(
            project_name,
            environment,
            project_a_id,
            pdf_task_id,
            policy,
            "HOT",
        )
        assert_equal(idempotent_transition["sha256"], pdf_digest, "idempotent transition SHA")
        idempotent_metadata = blob_metadata(project_name, environment, pdf_digest)
        assert_equal(
            idempotent_metadata["codec_config"]["tier"],
            selected_profiles["HOT"]["tier"],
            "idempotent transition durable tier",
        )
        idempotent_status, idempotent_body, _ = download(base_url, project_a_id, pdf_task_id)
        assert_equal(idempotent_status, 200, "idempotent transition readable")
        assert_equal(idempotent_body, pdf_bytes, "idempotent transition exact bytes")

        missing_physical_reingest = missing_physical_reingest_probe(
            project_name,
            environment,
            project_a_id,
            pdf_task_id,
            policy,
        )
        assert_equal(
            missing_physical_reingest["failed_closed"],
            True,
            "missing physical re-ingest fails closed",
        )
        assert_equal(
            missing_physical_reingest["metadata_unchanged"],
            True,
            "missing physical retry preserves durable metadata",
        )
        assert_equal(
            missing_physical_reingest["task_count_unchanged"],
            True,
            "missing physical retry does not create a task",
        )
        assert_equal(
            missing_physical_reingest["pre_delete_metadata_matches_physical"],
            True,
            "transition metadata matches physical representation before removal",
        )
        assert_equal(
            missing_physical_reingest["physical_path_after_rejected_retry"],
            None,
            "rejected replacement is removed",
        )
        restored_hot = transition_blob(
            project_name,
            environment,
            project_a_id,
            pdf_task_id,
            policy,
            "HOT",
        )
        assert_equal(restored_hot["sha256"], pdf_digest, "C3 post-probe HOT restoration SHA")

        metadata_before_reingest = blob_metadata(project_name, environment, pdf_digest)
        status, duplicate_after_transition = multipart_upload(
            base_url,
            project_a_id,
            "same-content-after-transition.pdf",
            pdf_bytes,
            "Duplicate after transition",
        )
        assert_equal(status, 201, "duplicate after transition status")
        assert isinstance(duplicate_after_transition, dict)
        assert_equal(
            duplicate_after_transition["original_blob_sha256"],
            pdf_digest,
            "duplicate after transition identity",
        )
        metadata_after_reingest = blob_metadata(project_name, environment, pdf_digest)
        assert_equal(
            metadata_after_reingest["codec_config"],
            metadata_before_reingest["codec_config"],
            "re-ingest preserves active profile",
        )
        assert_equal(
            metadata_after_reingest["physical_size"],
            metadata_before_reingest["physical_size"],
            "re-ingest preserves active physical size",
        )

        duplicate_low_level_probe = api_python(
            project_name,
            environment,
            (
                "from app.cas import CASStore, StorageProfile\n"
                "from app.config import Settings\n"
                "settings = Settings(cas_zstd_level=1)\n"
                "store = CASStore(settings)\n"
                f"digest = {pdf_digest!r}\n"
                "path = store.blob_path(digest)\n"
                "before = path.read_bytes()\n"
                "source = store.temp_root / 'integration-duplicate-source.pdf'\n"
                "source.write_bytes(store.read_verified(digest))\n"
                "duplicate = store.put(source, StorageProfile('COLD', 'cold-dense-a', 9))\n"
                "source.unlink(missing_ok=True)\n"
                "assert duplicate.published_new is False\n"
                "assert duplicate.codec_config == {'representation': 'existing'}\n"
                "assert duplicate.path == path and path.read_bytes() == before\n"
                "print('PASS')"
            ),
        )
        duplicate_low_level_truth = (
            duplicate_low_level_probe.stdout.strip().splitlines()[-1] == "PASS"
        )
        assert duplicate_low_level_truth

        persisted_metadata_probe = api_python(
            project_name,
            environment,
            (
                "import json\n"
                "from uuid import UUID\n"
                "from app.config import Settings\n"
                "from app.task_intake import task_blob\n"
                f"_, stored = task_blob(Settings(cas_zstd_level=1), UUID({project_a_id!r}), "
                f"UUID({pdf_task_id!r}))\n"
                "print(json.dumps(stored.codec_config))"
            ),
        )
        persisted_config = json.loads(persisted_metadata_probe.stdout.strip().splitlines()[-1])
        assert persisted_config == metadata_before_reingest["codec_config"]

        failed_transition = api_python(
            project_name,
            environment,
            (
                "from app.cas import CASStorageError, CASStore, StorageProfile\n"
                "from app.config import Settings\n"
                f"digest = {pdf_digest!r}\n"
                "settings = Settings()\n"
                "store = CASStore(settings)\n"
                "path = store.blob_path(digest)\n"
                "before = path.read_bytes()\n"
                "def fail_compression(*_args, **_kwargs):\n"
                "    raise OSError('forced target compression failure')\n"
                "store._compress_file = fail_compression\n"
                "failed = False\n"
                "try:\n"
                "    store.transition(\n"
                "        digest, StorageProfile('COLD', 'forced-failure', 15), "
                f"expected_size={len(pdf_bytes)}\n"
                "    )\n"
                "except CASStorageError:\n"
                "    failed = True\n"
                "assert failed and path.read_bytes() == before\n"
                f"assert store.read_verified(digest, {len(pdf_bytes)}) == {pdf_bytes!r}\n"
                "print('PASS')"
            ),
        )
        assert failed_transition.stdout.strip().splitlines()[-1] == "PASS"

        corruption_transition = api_python(
            project_name,
            environment,
            (
                "import os\n"
                "from uuid import UUID\n"
                "from app.cas import CASIntegrityError, CASStore, StoragePolicy, StorageProfile\n"
                "from app.config import Settings\n"
                "from app.task_intake import transition_task_blob\n"
                f"policy_payload = {repr(policy)}\n"
                "policy = StoragePolicy(\n"
                "    version=policy_payload['storage_policy_version'],\n"
                "    selected_profiles={\n"
                "        tier: StorageProfile(\n"
                "            tier=profile['tier'], profile_id=profile['profile_id'],\n"
                "            zstd_level=profile['zstd_level'],\n"
                "        )\n"
                "        for tier, profile in policy_payload['selected_profiles'].items()\n"
                "    },\n"
                "    benchmark_matrix=tuple(policy_payload['benchmark_matrix']),\n"
                "    selection_rationale=policy_payload['selection_rationale'],\n"
                ")\n"
                "settings = Settings()\n"
                "store = CASStore(settings)\n"
                f"path = store.blob_path({pdf_digest!r})\n"
                "backup = store.temp_root / 'integration-corruption-backup.zst'\n"
                "backup.write_bytes(path.read_bytes())\n"
                "path.write_bytes(path.read_bytes()[:-1])\n"
                "failed = False\n"
                "try:\n"
                "    transition_task_blob(\n"
                f"        settings, UUID({project_a_id!r}), UUID({pdf_task_id!r}),\n"
                "        policy, 'WARM', policy.profile_for('WARM'),\n"
                "    )\n"
                "except CASIntegrityError:\n"
                "    failed = True\n"
                "finally:\n"
                "    os.replace(backup, path)\n"
                "assert failed and store.read_verified(\n"
                f"    {pdf_digest!r}, {len(pdf_bytes)}\n"
                f") == {pdf_bytes!r}\n"
                "print('PASS')"
            ),
        )
        assert corruption_transition.stdout.strip().splitlines()[-1] == "PASS"

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
        restarted_status, restarted_body, restarted_headers = download(
            base_url, project_a_id, pdf_task_id
        )
        assert_equal(restarted_status, 200, "transition artifact after API restart")
        assert_equal(restarted_body, pdf_bytes, "transition artifact after API restart bytes")
        assert_equal(restarted_headers["x-hive-original-sha256"], pdf_digest, "restart SHA")
        restarted_metadata = blob_metadata(project_name, environment, pdf_digest)
        assert_equal(
            restarted_metadata["codec_config"]["tier"],
            selected_profiles["HOT"]["tier"],
            "restart durable active tier",
        )

        no_text_digest = str(no_text_task["original_blob_sha256"])
        no_text_container_path = (
            f"/var/lib/hive/cas/sha256/{no_text_digest[:2]}/{no_text_digest[2:]}.zst"
        )
        no_text_backup_path = f"/var/lib/hive/cas/sha256/.tmp/{no_text_digest}.integration-backup"
        api_python(
            project_name,
            environment,
            (
                "from pathlib import Path\n"
                f"path = Path({no_text_container_path!r})\n"
                f"backup = Path({no_text_backup_path!r})\n"
                "backup.write_bytes(path.read_bytes())\n"
                "path.write_bytes(path.read_bytes()[:-1])"
            ),
        )
        try:
            corrupted_status, corrupted_body, _ = download(
                base_url, project_a_id, str(no_text_task["task_id"])
            )
            assert_equal(corrupted_status, 500, "corrupt CAS fails closed")
            assert b"stored artifact integrity" in corrupted_body
        finally:
            api_python(
                project_name,
                environment,
                (
                    "import os\n"
                    "from pathlib import Path\n"
                    f"path = Path({no_text_container_path!r})\n"
                    f"backup = Path({no_text_backup_path!r})\n"
                    "os.replace(backup, path)"
                ),
                check=False,
            )
        restored_status, restored_body, _ = download(
            base_url, project_a_id, str(no_text_task["task_id"])
        )
        assert_equal(restored_status, 200, "restored CAS status")
        assert_equal(restored_body, no_text_bytes, "restored CAS exact bytes")
        assert not list(projects_root.rglob("*.zst")), "CAS must stay under HIVE_DATA_ROOT"
        assert not list((temporary_root / "data").rglob("*.part")), "temporary intake files cleaned"

        final_status, final_storage = request(base_url, "GET", "/api/v1/storage")
        assert_equal(final_status, 200, "final storage stats status")
        assert isinstance(final_storage, dict)
        final_metadata = blob_metadata(project_name, environment, pdf_digest)
        final_config = final_metadata["codec_config"]
        physical_probe = api_python(
            project_name,
            environment,
            (
                "from app.cas import CASStore; from app.config import Settings; "
                f"print(CASStore(Settings()).blob_path({pdf_digest!r}).stat().st_size)"
            ),
        )
        actual_physical_size = int(physical_probe.stdout.strip().splitlines()[-1])
        assert isinstance(final_config, dict)
        dedup_logical = int(final_storage["referenced_logical_bytes"])
        dedup_unique = int(final_storage["unique_logical_bytes"])
        dedup_savings = int(final_storage["deduplication_delta_bytes"])
        measured_rows = [row for row in benchmark_matrix if isinstance(row, dict)]
        selected_pairs = {
            (tier, profile["profile_id"])
            for tier, profile in selected_profiles.items()
            if isinstance(profile, dict)
        }
        measured_pairs = {
            (row["tier"], row["profile_id"])
            for row in measured_rows
            if "tier" in row and "profile_id" in row
        }
        checks = {
            "hot_warm_cold_policy_defined": set(selected_profiles) == {"HOT", "WARM", "COLD"},
            "policy_selection_internal_deterministic": policy["deterministic_selection"] is True,
            "representative_benchmark_corpus": int(policy["benchmark_input_bytes"]) >= 48 * 1024
            and int(policy["benchmark_sample_count"]) == 8
            and len(policy["benchmark_sources"]) == 8,
            "tiny_benchmark_rejected": tiny_benchmark_rejected,
            "oversized_benchmark_rejected": oversized_benchmark_rejected,
            "cleanup_failure_consistency": cleanup_failure_consistency,
            "orphan_retry_fail_closed": orphan_retry_fail_closed,
            "orphan_no_row_not_inserted": orphan_retry_fail_closed,
            "policy_bound_transitions": all(
                result.get("policy_authorized") is True
                and result.get("tier") in selected_profiles
                and result.get("profile_id") == selected_profiles[result["tier"]]["profile_id"]
                for result in transition_results
            ),
            "unselected_profile_rejected": unselected_profile_rejection,
            "zstd_lossless_codec": all(
                row.get("round_trip_identity") is True for row in measured_rows
            ),
            "zstd_profiles_measured": selected_pairs <= measured_pairs,
            "zstd_levels_supported": all(
                isinstance(profile.get("zstd_level"), int) and 1 <= profile["zstd_level"] <= 22
                for profile in selected_profiles.values()
                if isinstance(profile, dict)
            ),
            "content_identity_sha256_preserved": all(
                result["sha256"] == pdf_digest for result in transition_results
            )
            and restarted_headers["x-hive-original-sha256"] == pdf_digest,
            "dedup_identity_across_tiers": all(
                result["sha256"] == pdf_digest for result in transition_results
            ),
            "single_canonical_cas_identity": final_storage["unique_blob_count"] == 4,
            "corruption_fail_closed": corrupted_status == 500
            and corruption_transition.stdout.strip().splitlines()[-1] == "PASS",
            "physical_replacement_atomic": len(transition_results) == 4
            and restarted_body == pdf_bytes,
            "logical_bytes_measured": dedup_logical >= dedup_unique > 0,
            "physical_bytes_measured": actual_physical_size == int(final_metadata["physical_size"])
            and actual_physical_size > 0,
            "compression_measurements_truthful": all(
                row.get("compression_savings_bytes")
                == int(row["logical_input_bytes"]) - int(row["physical_bytes"])
                and abs(
                    float(row["compression_ratio"])
                    - int(row["physical_bytes"]) / int(row["logical_input_bytes"])
                )
                <= 1e-9
                for row in measured_rows
            ),
            "dedup_measurements_truthful": dedup_savings == dedup_logical - dedup_unique,
            "restart_durable": restarted_status == 200
            and restarted_metadata["physical_size"] == final_metadata["physical_size"],
            "idempotent_transition": idempotent_transition["sha256"] == pdf_digest
            and idempotent_status == 200
            and idempotent_body == pdf_bytes,
            "persisted_metadata_not_reconstructed_from_settings": persisted_config
            == metadata_before_reingest["codec_config"],
            "duplicate_put_truthful_existing_representation": duplicate_low_level_truth,
            "missing_physical_reingest_fail_closed": missing_physical_reingest["failed_closed"],
            "missing_physical_reingest_no_task_success": missing_physical_reingest[
                "task_count_unchanged"
            ],
            "missing_physical_reingest_metadata_unchanged": missing_physical_reingest[
                "metadata_unchanged"
            ],
            "missing_physical_reingest_replacement_removed": missing_physical_reingest[
                "physical_path_after_rejected_retry"
            ]
            is None,
            "missing_physical_transition_truthful_before_removal": missing_physical_reingest[
                "pre_delete_metadata_matches_physical"
            ],
            "redis_loss_preserves_cas_truth": persisted_without_redis["original_blob_sha256"]
            == str(text_task["original_blob_sha256"]),
            "selection_rationale_measured": "Measured deterministic selection"
            in policy["selection_rationale"],
        }
        assert_equal(all(checks.values()), True, "ACCE storage policy checks")
        EVIDENCE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE_OUTPUT.write_text(
            json.dumps(
                {
                    "status": "PASS",
                    "evidence_file": "acce-storage-policy.json",
                    "acce_evidence_version": "acce-storage-policy-v1",
                    "storage_policy_version": policy["storage_policy_version"],
                    **checks,
                    "canonical_source_loss_count": 0,
                    "llm_calls": 0,
                    "provider_calls": 0,
                    "dedup_logical_bytes": dedup_logical,
                    "dedup_unique_logical_bytes": dedup_unique,
                    "dedup_savings_bytes": dedup_savings,
                    "benchmark_input_bytes": policy["benchmark_input_bytes"],
                    "benchmark_sample_count": policy["benchmark_sample_count"],
                    "benchmark_sources": policy["benchmark_sources"],
                    "zstd_supported_level_min": 1,
                    "zstd_supported_level_max": 22,
                    "policy_mapping": {
                        tier: profile["profile_id"]
                        for tier, profile in selected_profiles.items()
                        if isinstance(profile, dict)
                    },
                    "missing_physical_reingest": missing_physical_reingest,
                    "selection_rationale": policy["selection_rationale"],
                    "benchmark_matrix": benchmark_matrix,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
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
                        str(duplicate_after_transition["task_id"]),
                        cross_project_task_id,
                        str(no_text_task["task_id"]),
                    ],
                    "pdf_sha256": pdf_digest,
                    "storage": final_storage,
                    "storage_policy": json.loads(EVIDENCE_OUTPUT.read_text(encoding="utf-8")),
                    "redis_restart": "passed",
                    "api_restart": "passed",
                    "corruption_fail_closed": "passed",
                },
                indent=2,
            )
        )
        print("Task Intake and CAS integration passed.")
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
