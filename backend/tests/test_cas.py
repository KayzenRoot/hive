import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import cast

import pytest

from app.cas import (
    ACCE_STORAGE_POLICY_MAX_BENCHMARK_INPUT_BYTES,
    ACCE_STORAGE_POLICY_MIN_BENCHMARK_INPUT_BYTES,
    CASIntegrityError,
    CASStorageError,
    CASStore,
    InvalidDigestError,
    StoragePolicy,
    StoragePolicyError,
    StorageProfile,
    StoredBlob,
    bind_storage_profile,
    measure_storage_policy,
    select_storage_policy,
)
from app.config import Settings


def make_store(tmp_path: Path) -> CASStore:
    return CASStore(Settings(data_root=tmp_path))


def measured_row(
    tier: str,
    profile_id: str,
    level: int,
    physical: int,
    compression: float,
    decompression: float,
) -> dict[str, object]:
    logical = 1000
    return {
        "tier": tier,
        "profile_id": profile_id,
        "zstd_level": level,
        "logical_input_bytes": logical,
        "physical_bytes": physical,
        "compression_ratio": physical / logical,
        "compression_savings_bytes": logical - physical,
        "compression_expands": physical > logical,
        "round_trip_identity": True,
        "measurement_samples": 3,
        "benchmark_measured": True,
        "compression_mib_per_s": compression,
        "decompression_mib_per_s": decompression,
    }


def measured_policy() -> StoragePolicy:
    return select_storage_policy(
        [
            measured_row("HOT", "hot-a", 1, 600, 100.0, 110.0),
            measured_row("HOT", "hot-b", 3, 700, 200.0, 210.0),
            measured_row("WARM", "warm-a", 3, 500, 100.0, 100.0),
            measured_row("WARM", "warm-b", 6, 1000, 200.0, 200.0),
            measured_row("COLD", "cold-a", 9, 900, 100.0, 100.0),
            measured_row("COLD", "cold-b", 15, 800, 50.0, 50.0),
        ]
    )


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


def test_storage_policy_selects_measured_same_tier_profiles_deterministically() -> None:
    matrix = [
        measured_row("HOT", "hot-a", 1, 600, 100.0, 110.0),
        measured_row("HOT", "hot-b", 3, 700, 200.0, 210.0),
        measured_row("WARM", "warm-a", 3, 500, 100.0, 100.0),
        measured_row("WARM", "warm-b", 6, 1000, 200.0, 200.0),
        measured_row("COLD", "cold-a", 9, 900, 100.0, 100.0),
        measured_row("COLD", "cold-b", 15, 800, 50.0, 50.0),
    ]

    first = select_storage_policy(matrix)
    second = select_storage_policy(matrix)

    assert first == second
    assert first.profile_for("HOT").profile_id == "hot-b"
    assert first.profile_for("WARM").profile_id == "warm-a"
    assert first.profile_for("COLD").profile_id == "cold-b"
    measured_pairs = {(str(row["tier"]), str(row["profile_id"])) for row in matrix}
    assert {
        (tier, profile.profile_id) for tier, profile in first.selected_profiles.items()
    } <= measured_pairs


def test_storage_policy_rejects_ambiguous_or_unsupported_measurements() -> None:
    matrix = [
        measured_row("HOT", "hot-a", 1, 600, 100.0, 110.0),
        measured_row("HOT", "hot-b", 3, 700, 200.0, 210.0),
        measured_row("WARM", "warm-a", 3, 500, 100.0, 100.0),
        measured_row("WARM", "warm-b", 6, 1000, 200.0, 200.0),
        measured_row("COLD", "cold-a", 9, 900, 100.0, 100.0),
        measured_row("COLD", "cold-b", 15, 800, 50.0, 50.0),
    ]
    duplicate = [*matrix, dict(matrix[0])]
    with pytest.raises(StoragePolicyError, match="duplicate"):
        select_storage_policy(duplicate)
    invalid_level = [dict(row) for row in matrix]
    invalid_level[0]["zstd_level"] = 23
    with pytest.raises(StoragePolicyError, match="unsupported"):
        select_storage_policy(invalid_level)
    invalid_throughput = [dict(row) for row in matrix]
    invalid_throughput[0]["compression_mib_per_s"] = float("nan")
    with pytest.raises(StoragePolicyError, match="throughput"):
        select_storage_policy(invalid_throughput)


def test_storage_policy_benchmark_measures_multiple_candidates() -> None:
    representative = b"HIVE representative artifact " * 16_384
    policy = measure_storage_policy([representative])

    assert policy.version == "acce-policy-v1"
    assert len(policy.benchmark_matrix) == 6
    assert set(policy.selected_profiles) == {"HOT", "WARM", "COLD"}
    assert all(
        row["benchmark_measured"] is True
        and float(cast(int | float, row["compression_mib_per_s"])) > 0
        and float(cast(int | float, row["decompression_mib_per_s"])) > 0
        for row in policy.benchmark_matrix
    )


def test_storage_policy_benchmark_rejects_tiny_aggregate_input() -> None:
    with pytest.raises(StoragePolicyError, match="representative minimum"):
        measure_storage_policy([b"HIVE artifact" * 8])


def test_storage_policy_benchmark_rejects_oversized_aggregate_input() -> None:
    oversized = b"x" * (ACCE_STORAGE_POLICY_MAX_BENCHMARK_INPUT_BYTES + 1)

    with pytest.raises(StoragePolicyError, match="exceeds the bounded size"):
        measure_storage_policy([oversized])


def test_storage_policy_benchmark_minimum_is_materially_bounded() -> None:
    assert ACCE_STORAGE_POLICY_MIN_BENCHMARK_INPUT_BYTES >= 32 * 1024


def test_storage_policy_reports_compression_expansion_truthfully() -> None:
    matrix = [
        measured_row("HOT", "hot-a", 1, 1200, 100.0, 110.0),
        measured_row("HOT", "hot-b", 3, 1300, 90.0, 100.0),
        measured_row("WARM", "warm-a", 3, 1100, 100.0, 100.0),
        measured_row("WARM", "warm-b", 6, 1200, 90.0, 100.0),
        measured_row("COLD", "cold-a", 9, 1050, 80.0, 90.0),
        measured_row("COLD", "cold-b", 15, 1100, 70.0, 80.0),
    ]

    policy = select_storage_policy(matrix)

    for row in policy.benchmark_matrix:
        assert row["compression_savings_bytes"] == cast(int, row["logical_input_bytes"]) - cast(
            int, row["physical_bytes"]
        )
        assert row["compression_expands"] is (
            cast(int, row["physical_bytes"]) > cast(int, row["logical_input_bytes"])
        )


def test_measured_policy_binding_accepts_selected_hot_warm_cold() -> None:
    policy = measured_policy()

    for tier in ("HOT", "WARM", "COLD"):
        selected = policy.profile_for(tier)
        assert bind_storage_profile(policy, tier, selected) == selected


@pytest.mark.parametrize("tier", ["HOT", "WARM", "COLD"])
def test_measured_policy_binding_rejects_unselected_profile(tier: str) -> None:
    policy = measured_policy()
    unselected_row = next(
        row
        for row in policy.benchmark_matrix
        if row["tier"] == tier and row["profile_id"] != policy.profile_for(tier).profile_id
    )
    unselected = StorageProfile(
        tier=tier,
        profile_id=cast(str, unselected_row["profile_id"]),
        zstd_level=cast(int, unselected_row["zstd_level"]),
    )

    with pytest.raises(StoragePolicyError, match="selected profile"):
        bind_storage_profile(policy, tier, unselected)


def test_measured_policy_binding_rejects_selected_profile_from_another_tier() -> None:
    policy = measured_policy()

    with pytest.raises(StoragePolicyError, match="selected profile"):
        bind_storage_profile(policy, "HOT", policy.profile_for("WARM"))


def test_measured_policy_binding_rejects_policy_profile_mismatch() -> None:
    policy = measured_policy()
    mismatched_policy = StoragePolicy(
        version=policy.version,
        selected_profiles={
            **policy.selected_profiles,
            "HOT": StorageProfile("HOT", "hot-unmeasured", 3),
        },
        benchmark_matrix=policy.benchmark_matrix,
        selection_rationale=policy.selection_rationale,
    )

    with pytest.raises(StoragePolicyError, match="measured and deterministic"):
        bind_storage_profile(mismatched_policy, "HOT", policy.profile_for("HOT"))


def test_verified_transition_preserves_sha_and_publishes_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = make_store(tmp_path)
    source = tmp_path / "transition.txt"
    payload = b"transition identity must remain canonical\n" * 4096
    source.write_bytes(payload)
    initial = store.put(source)
    profile = StorageProfile("WARM", "warm-balanced-test", 6)
    replacements: list[tuple[Path, Path]] = []
    original_replace = os.replace

    def observe_replace(
        source_path: str | os.PathLike[str], target_path: str | os.PathLike[str]
    ) -> None:
        replacements.append((Path(source_path), Path(target_path)))
        original_replace(source_path, target_path)

    monkeypatch.setattr(os, "replace", observe_replace)
    transitioned = store.transition(initial.sha256, profile, expected_size=len(payload))

    assert transitioned.sha256 == initial.sha256 == hashlib.sha256(payload).hexdigest()
    assert store.read_verified(initial.sha256, len(payload)) == payload
    assert transitioned.codec_config["tier"] == "WARM"
    assert transitioned.codec_config["profile_id"] == "warm-balanced-test"
    assert any(target == initial.path for _, target in replacements)
    assert transitioned.physical_size == initial.path.stat().st_size

    repeated = store.transition(initial.sha256, profile, expected_size=len(payload))

    assert repeated.sha256 == transitioned.sha256
    assert repeated.codec_config == transitioned.codec_config
    assert store.read_verified(initial.sha256, len(payload)) == payload


def test_transition_failure_and_corruption_leave_prior_representation_readable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = make_store(tmp_path)
    source = tmp_path / "failure.txt"
    payload = b"prior representation remains readable\n" * 4096
    source.write_bytes(payload)
    initial = store.put(source)
    before = initial.path.read_bytes()
    profile = StorageProfile("COLD", "cold-dense-test", 15)

    def fail_compression(*_args: object, **_kwargs: object) -> None:
        raise OSError("forced target compression failure")

    monkeypatch.setattr(store, "_compress_file", fail_compression)
    with pytest.raises(CASStorageError, match="transition failed"):
        store.transition(initial.sha256, profile, expected_size=len(payload))
    assert initial.path.read_bytes() == before
    assert store.read_verified(initial.sha256, len(payload)) == payload

    monkeypatch.undo()
    initial.path.write_bytes(before[:-1])
    with pytest.raises(CASIntegrityError):
        store.transition(initial.sha256, profile, expected_size=len(payload))
    initial.path.write_bytes(before)
    assert store.read_verified(initial.sha256, len(payload)) == payload


def test_metadata_persist_failure_restores_prior_representation(
    tmp_path: Path,
) -> None:
    store = make_store(tmp_path)
    source = tmp_path / "metadata-failure.txt"
    payload = b"metadata commit failure restores the prior bytes\n" * 4096
    source.write_bytes(payload)
    initial = store.put(source)
    before = initial.path.read_bytes()

    def fail_metadata(_stored: object) -> None:
        raise CASStorageError("forced metadata persistence failure")

    with pytest.raises(CASStorageError, match="forced metadata persistence failure"):
        store.transition(
            initial.sha256,
            StorageProfile("WARM", "warm-balanced-test", 6),
            expected_size=len(payload),
            persist_metadata=fail_metadata,
        )

    assert initial.path.read_bytes() == before
    assert store.read_verified(initial.sha256, len(payload)) == payload


def test_backup_cleanup_failure_after_metadata_commit_keeps_new_truth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = make_store(tmp_path)
    source = tmp_path / "cleanup-failure.txt"
    payload = b"metadata commit outranks backup cleanup failure\n" * 4096
    source.write_bytes(payload)
    initial = store.put(source)
    before = initial.path.read_bytes()
    persisted: list[dict[str, int | bool | str]] = []

    def persist_metadata(stored: StoredBlob) -> None:
        persisted.append(stored.codec_config)

    def fail_backup_cleanup(_backup: Path) -> None:
        raise OSError("forced backup cleanup failure")

    monkeypatch.setattr(store, "_cleanup_backup", fail_backup_cleanup)
    transitioned = store.transition(
        initial.sha256,
        StorageProfile("COLD", "cold-dense-test", 15),
        expected_size=len(payload),
        persist_metadata=persist_metadata,
    )

    assert persisted == [transitioned.codec_config]
    assert initial.path.read_bytes() != before
    assert transitioned.physical_size == initial.path.stat().st_size
    assert transitioned.codec_config["tier"] == "COLD"
    assert transitioned.codec_config["profile_id"] == "cold-dense-test"
    assert store.read_verified(initial.sha256, len(payload)) == payload
    leftovers = list(store.temp_root.glob(".cas-backup-*.zst.tmp"))
    assert leftovers
    for leftover in leftovers:
        leftover.unlink()


def test_duplicate_put_does_not_overwrite_active_representation(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    source = tmp_path / "duplicate.txt"
    payload = b"active representation" * 4096
    source.write_bytes(payload)
    initial = store.put(source)
    store.transition(
        initial.sha256,
        StorageProfile("COLD", "cold-dense-test", 15),
        expected_size=len(payload),
    )
    active = initial.path.read_bytes()

    duplicate = store.put(source)

    assert duplicate.sha256 == initial.sha256
    assert duplicate.published_new is False
    assert duplicate.codec_config == {"representation": "existing"}
    assert "level" not in duplicate.codec_config
    assert "tier" not in duplicate.codec_config
    assert "profile_id" not in duplicate.codec_config
    assert duplicate.path.read_bytes() == active

    conflicting = store.put(source, StorageProfile("HOT", "hot-fast-test", 1))

    assert conflicting.sha256 == initial.sha256
    assert conflicting.published_new is False
    assert conflicting.codec_config == {"representation": "existing"}
    assert conflicting.path == duplicate.path == initial.path
    assert conflicting.path.read_bytes() == active
    assert len(list((tmp_path / "cas" / "sha256").rglob("*.zst"))) == 1
