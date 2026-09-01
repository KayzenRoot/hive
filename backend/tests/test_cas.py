import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.cas import CASIntegrityError, CASStore, InvalidDigestError
from app.config import Settings


def make_store(tmp_path: Path) -> CASStore:
    return CASStore(Settings(data_root=tmp_path))


def test_known_hash_round_trip_and_hash_derived_path(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    source = tmp_path / "first-name.txt"
    payload = b"HIVE exact original\r\nbytes\n"
    source.write_bytes(payload)

    blob = store.put(source)

    assert blob.sha256 == hashlib.sha256(payload).hexdigest()
    assert blob.path == store.blob_path(blob.sha256)
    assert store.read_verified(blob.sha256, blob.logical_size) == payload


def test_identical_bytes_deduplicate_even_with_different_filenames(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    first = tmp_path / "user-name-one.txt"
    second = tmp_path / "user-name-two.txt"
    first.write_bytes(b"same input")
    second.write_bytes(first.read_bytes())

    first_blob = store.put(first)
    second_blob = store.put(second)

    assert first_blob.sha256 == second_blob.sha256
    assert first_blob.path == second_blob.path
    assert len(list((tmp_path / "cas" / "sha256").rglob("*.zst"))) == 1


def test_different_bytes_get_different_identities(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    assert store.put(first).sha256 != store.put(second).sha256


def test_concurrent_identical_writes_converge_without_corruption(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    sources = []
    for index in range(8):
        source = tmp_path / f"concurrent-{index}.txt"
        source.write_bytes(b"concurrent HIVE payload" * 100)
        sources.append(source)

    with ThreadPoolExecutor(max_workers=8) as executor:
        blobs = list(executor.map(store.put, sources))

    assert {blob.sha256 for blob in blobs}.__len__() == 1
    assert len(list((tmp_path / "cas" / "sha256").rglob("*.zst"))) == 1
    blob = blobs[0]
    assert store.read_verified(blob.sha256, blob.logical_size) == sources[0].read_bytes()


def test_corrupt_or_truncated_zstd_fails_closed(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    source = tmp_path / "payload.txt"
    source.write_bytes(b"integrity matters")
    blob = store.put(source)
    blob.path.write_bytes(blob.path.read_bytes()[:-1])

    with pytest.raises(CASIntegrityError):
        store.read_verified(blob.sha256, blob.logical_size)


def test_invalid_digest_never_becomes_a_path(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    with pytest.raises(InvalidDigestError):
        store.blob_path("../../not-a-digest")
