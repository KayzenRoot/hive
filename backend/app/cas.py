from __future__ import annotations

import hashlib
import math
import os
import re
import shutil
import tempfile
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, cast

import zstandard

from .config import Settings

CHUNK_SIZE = 1024 * 1024
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ACCE_STORAGE_POLICY_VERSION = "acce-policy-v1"
ACCE_STORAGE_POLICY_EVIDENCE_VERSION = "acce-storage-policy-v1"
ACCE_STORAGE_POLICY_ZSTD_MIN_LEVEL = 1
ACCE_STORAGE_POLICY_ZSTD_MAX_LEVEL = 22
ACCE_STORAGE_POLICY_MAX_BENCHMARK_ROWS = 16
ACCE_STORAGE_POLICY_MIN_BENCHMARK_INPUT_BYTES = 48 * 1024
ACCE_STORAGE_POLICY_MAX_BENCHMARK_INPUT_BYTES = 8 * 1024 * 1024
ACCE_STORAGE_POLICY_MAX_BENCHMARK_SAMPLES = 8
ACCE_STORAGE_POLICY_MEASUREMENT_REPEATS = 3
ACCE_STORAGE_POLICY_MAX_THROUGHPUT_MIB_PER_S = 1_000_000.0
ACCE_STORAGE_POLICY_TIERS = ("HOT", "WARM", "COLD")
ACCE_STORAGE_POLICY_PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
ACCE_STORAGE_POLICY_CANDIDATES: dict[str, tuple[tuple[str, int], ...]] = {
    "HOT": (("hot-fast-a", 1), ("hot-fast-b", 3)),
    "WARM": (("warm-balanced-a", 3), ("warm-balanced-b", 6)),
    "COLD": (("cold-dense-a", 9), ("cold-dense-b", 15)),
}


class CASStorageError(RuntimeError):
    """A CAS operation could not safely complete."""


class CASIntegrityError(CASStorageError):
    """A stored blob did not reproduce its declared original bytes."""


class InvalidDigestError(ValueError):
    """A caller supplied a digest that cannot identify a CAS path."""


class StoragePolicyError(ValueError):
    """A storage policy or measured selection is invalid."""


@dataclass(frozen=True)
class StorageProfile:
    tier: str
    profile_id: str
    zstd_level: int
    policy_version: str = ACCE_STORAGE_POLICY_VERSION


@dataclass(frozen=True)
class StoragePolicy:
    version: str
    selected_profiles: dict[str, StorageProfile]
    benchmark_matrix: tuple[dict[str, object], ...]
    selection_rationale: str

    def profile_for(self, tier: str) -> StorageProfile:
        try:
            return self.selected_profiles[tier]
        except KeyError as exc:
            raise StoragePolicyError(f"unknown storage tier: {tier}") from exc


@dataclass(frozen=True)
class StoredBlob:
    sha256: str
    logical_size: int
    physical_size: int
    codec: str
    codec_config: dict[str, int | bool | str]
    path: Path
    published_new: bool = True


def _validate_storage_profile(profile: StorageProfile) -> None:
    if profile.policy_version != ACCE_STORAGE_POLICY_VERSION:
        raise StoragePolicyError("unsupported ACCE storage policy version")
    if profile.tier not in ACCE_STORAGE_POLICY_TIERS:
        raise StoragePolicyError("storage tier must be HOT, WARM, or COLD")
    if not ACCE_STORAGE_POLICY_PROFILE_ID.fullmatch(profile.profile_id):
        raise StoragePolicyError("storage profile ID is invalid")
    if not (
        ACCE_STORAGE_POLICY_ZSTD_MIN_LEVEL
        <= profile.zstd_level
        <= ACCE_STORAGE_POLICY_ZSTD_MAX_LEVEL
    ):
        raise StoragePolicyError("Zstandard level is outside the supported range")


def _validate_throughput(value: object) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and 0.0 < float(value) <= ACCE_STORAGE_POLICY_MAX_THROUGHPUT_MIB_PER_S
    )


def _validate_benchmark_row(row: object) -> dict[str, object]:
    if not isinstance(row, dict):
        raise StoragePolicyError("benchmark rows must be objects")
    tier = row.get("tier")
    profile_id = row.get("profile_id")
    level = row.get("zstd_level")
    logical = row.get("logical_input_bytes")
    physical = row.get("physical_bytes")
    ratio = row.get("compression_ratio")
    savings = row.get("compression_savings_bytes")
    expands = row.get("compression_expands")
    samples = row.get("measurement_samples")
    if tier not in ACCE_STORAGE_POLICY_TIERS:
        raise StoragePolicyError("benchmark row has an invalid tier")
    if not isinstance(profile_id, str) or not ACCE_STORAGE_POLICY_PROFILE_ID.fullmatch(profile_id):
        raise StoragePolicyError("benchmark row has an invalid profile ID")
    if not isinstance(level, int) or isinstance(level, bool):
        raise StoragePolicyError("benchmark row has an invalid Zstandard level")
    if not ACCE_STORAGE_POLICY_ZSTD_MIN_LEVEL <= level <= ACCE_STORAGE_POLICY_ZSTD_MAX_LEVEL:
        raise StoragePolicyError("benchmark row has an unsupported Zstandard level")
    if not isinstance(logical, int) or isinstance(logical, bool) or logical <= 0:
        raise StoragePolicyError("benchmark row has an invalid logical size")
    if not isinstance(physical, int) or isinstance(physical, bool) or physical <= 0:
        raise StoragePolicyError("benchmark row has an invalid physical size")
    if (
        not isinstance(ratio, int | float)
        or isinstance(ratio, bool)
        or not math.isfinite(float(ratio))
        or abs(float(ratio) - (physical / logical)) > 1e-9
    ):
        raise StoragePolicyError("benchmark row compression ratio is not truthful")
    if not isinstance(savings, int) or isinstance(savings, bool) or savings != logical - physical:
        raise StoragePolicyError("benchmark row compression savings are not truthful")
    if not isinstance(expands, bool) or expands is not (physical > logical):
        raise StoragePolicyError("benchmark row expansion flag is not truthful")
    if row.get("round_trip_identity") is not True:
        raise StoragePolicyError("benchmark row did not prove lossless round-trip")
    if not isinstance(samples, int) or isinstance(samples, bool) or not 1 <= samples <= 100:
        raise StoragePolicyError("benchmark row has invalid measurement samples")
    if row.get("benchmark_measured") is not True:
        raise StoragePolicyError("benchmark row is not measured")
    if not _validate_throughput(row.get("compression_mib_per_s")):
        raise StoragePolicyError("benchmark row has invalid compression throughput")
    if not _validate_throughput(row.get("decompression_mib_per_s")):
        raise StoragePolicyError("benchmark row has invalid decompression throughput")
    return dict(row)


def select_storage_policy(matrix: list[dict[str, object]]) -> StoragePolicy:
    """Select one measured profile per tier using deterministic tier-specific rules."""
    if not 3 <= len(matrix) <= ACCE_STORAGE_POLICY_MAX_BENCHMARK_ROWS:
        raise StoragePolicyError("benchmark matrix size is outside the bounded range")
    rows = [_validate_benchmark_row(row) for row in matrix]
    pairs: set[tuple[str, str]] = set()
    profiles: set[str] = set()
    by_tier: dict[str, list[dict[str, object]]] = {tier: [] for tier in ACCE_STORAGE_POLICY_TIERS}
    for row in rows:
        pair = (cast(str, row["tier"]), cast(str, row["profile_id"]))
        if pair in pairs or pair[1] in profiles:
            raise StoragePolicyError("benchmark matrix contains duplicate profile identity")
        pairs.add(pair)
        profiles.add(pair[1])
        by_tier[pair[0]].append(row)
    if any(len(by_tier[tier]) < 2 for tier in ACCE_STORAGE_POLICY_TIERS):
        raise StoragePolicyError("each tier requires at least two measured candidates")

    def speed(row: dict[str, object]) -> float:
        compression = float(cast(int | float, row["compression_mib_per_s"]))
        decompression = float(cast(int | float, row["decompression_mib_per_s"]))
        return min(compression, decompression)

    def balanced(row: dict[str, object]) -> float:
        average = (
            float(cast(int | float, row["compression_mib_per_s"]))
            + float(cast(int | float, row["decompression_mib_per_s"]))
        ) / 2.0
        return average / max(float(cast(int | float, row["compression_ratio"])), 1e-12)

    selected: dict[str, StorageProfile] = {}
    for tier in ACCE_STORAGE_POLICY_TIERS:
        candidates = by_tier[tier]
        if tier == "HOT":
            winner = min(
                candidates,
                key=lambda row: (
                    -speed(row),
                    -(
                        float(cast(int | float, row["compression_mib_per_s"]))
                        + float(cast(int | float, row["decompression_mib_per_s"]))
                    ),
                    cast(int, row["physical_bytes"]),
                    cast(int, row["zstd_level"]),
                    str(row["profile_id"]),
                ),
            )
        elif tier == "WARM":
            winner = min(
                candidates,
                key=lambda row: (
                    -balanced(row),
                    cast(int, row["physical_bytes"]),
                    cast(int, row["zstd_level"]),
                    str(row["profile_id"]),
                ),
            )
        else:
            winner = min(
                candidates,
                key=lambda row: (
                    cast(int, row["physical_bytes"]),
                    -speed(row),
                    cast(int, row["zstd_level"]),
                    str(row["profile_id"]),
                ),
            )
        selected[tier] = StorageProfile(
            tier=tier,
            profile_id=cast(str, winner["profile_id"]),
            zstd_level=cast(int, winner["zstd_level"]),
        )
    selected_pairs = {(profile.tier, profile.profile_id) for profile in selected.values()}
    if not selected_pairs <= pairs:
        raise StoragePolicyError("selected profile is not measured for its same tier")
    rationale = (
        "Measured deterministic selection: HOT maximizes the compression/decompression "
        "throughput bottleneck; WARM maximizes mean throughput divided by compression ratio; "
        "COLD minimizes physical bytes and then maximizes the throughput bottleneck. "
        "Ties use physical bytes, level, and profile ID in that order."
    )
    return StoragePolicy(
        version=ACCE_STORAGE_POLICY_VERSION,
        selected_profiles=selected,
        benchmark_matrix=tuple(rows),
        selection_rationale=rationale,
    )


def bind_storage_profile(
    policy: StoragePolicy, tier: str, profile: StorageProfile
) -> StorageProfile:
    """Authorize a physical profile against the exact measured policy selection."""
    if policy.version != ACCE_STORAGE_POLICY_VERSION:
        raise StoragePolicyError("unsupported ACCE storage policy version")
    if not all(isinstance(row, dict) for row in policy.benchmark_matrix):
        raise StoragePolicyError("storage policy benchmark matrix is malformed")
    recomputed = select_storage_policy([dict(row) for row in policy.benchmark_matrix])
    if recomputed.selected_profiles != policy.selected_profiles:
        raise StoragePolicyError("storage policy selection is not measured and deterministic")
    _validate_storage_profile(profile)
    selected = policy.profile_for(tier)
    if profile != selected:
        raise StoragePolicyError("storage profile is not the measured selected profile for tier")
    return selected


def measure_storage_policy(samples: Sequence[bytes]) -> StoragePolicy:
    """Measure bounded representative logical bytes and select a policy."""
    if not 1 <= len(samples) <= ACCE_STORAGE_POLICY_MAX_BENCHMARK_SAMPLES:
        raise StoragePolicyError("benchmark sample count is outside the bounded range")
    if any(not isinstance(sample, bytes) or not sample for sample in samples):
        raise StoragePolicyError("benchmark samples must be non-empty bytes")
    total_logical = sum(len(sample) for sample in samples)
    if total_logical < ACCE_STORAGE_POLICY_MIN_BENCHMARK_INPUT_BYTES:
        raise StoragePolicyError("benchmark input is below the representative minimum")
    if total_logical > ACCE_STORAGE_POLICY_MAX_BENCHMARK_INPUT_BYTES:
        raise StoragePolicyError("benchmark input exceeds the bounded size")

    rows: list[dict[str, object]] = []
    for tier, candidates in ACCE_STORAGE_POLICY_CANDIDATES.items():
        for profile_id, level in candidates:
            compressor = zstandard.ZstdCompressor(
                level=level, write_checksum=True, write_content_size=False
            )
            compressed: list[bytes] = []
            compression_start = time.perf_counter()
            for sample in samples:
                current = b""
                for _ in range(ACCE_STORAGE_POLICY_MEASUREMENT_REPEATS):
                    current = compressor.compress(sample)
                compressed.append(current)
            compression_elapsed = time.perf_counter() - compression_start
            decompression_start = time.perf_counter()
            for sample, encoded in zip(samples, compressed, strict=True):
                for _ in range(ACCE_STORAGE_POLICY_MEASUREMENT_REPEATS):
                    decoded = zstandard.ZstdDecompressor().decompress(
                        encoded, max_output_size=len(sample)
                    )
                    if decoded != sample:
                        raise StoragePolicyError("Zstandard round-trip changed logical bytes")
            decompression_elapsed = time.perf_counter() - decompression_start
            physical = sum(len(value) for value in compressed)
            compression_throughput = (
                total_logical
                * ACCE_STORAGE_POLICY_MEASUREMENT_REPEATS
                / max(compression_elapsed, 1e-12)
                / (1024 * 1024)
            )
            decompression_throughput = (
                total_logical
                * ACCE_STORAGE_POLICY_MEASUREMENT_REPEATS
                / max(decompression_elapsed, 1e-12)
                / (1024 * 1024)
            )
            rows.append(
                {
                    "tier": tier,
                    "profile_id": profile_id,
                    "zstd_level": level,
                    "logical_input_bytes": total_logical,
                    "physical_bytes": physical,
                    "compression_ratio": physical / total_logical,
                    "compression_savings_bytes": total_logical - physical,
                    "compression_expands": physical > total_logical,
                    "round_trip_identity": True,
                    "measurement_samples": len(samples),
                    "benchmark_measured": True,
                    "compression_mib_per_s": compression_throughput,
                    "decompression_mib_per_s": decompression_throughput,
                }
            )
    return select_storage_policy(rows)


class CASStore:
    """Content-addressed storage for exact originals compressed with Zstandard."""

    _publish_locks: dict[str, threading.Lock] = {}
    _publish_locks_guard = threading.Lock()

    def __init__(self, settings: Settings) -> None:
        settings.validate_intake_limits()
        self.settings = settings
        self.root = settings.resolved_data_root / "cas" / "sha256"
        self.root.mkdir(parents=True, exist_ok=True)
        self.temp_root = self.root / ".tmp"
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.codec_config: dict[str, int | bool | str] = {
            "level": settings.cas_zstd_level,
            "checksum": True,
            "content_size": False,
            "library": f"zstandard/{zstandard.__version__}",
        }

    def _codec_config_for(
        self, profile: StorageProfile | None = None
    ) -> dict[str, int | bool | str]:
        if profile is None:
            return self.codec_config.copy()
        _validate_storage_profile(profile)
        return {
            **self.codec_config,
            "level": profile.zstd_level,
            "storage_policy_version": profile.policy_version,
            "tier": profile.tier,
            "profile_id": profile.profile_id,
            "zstd_level": profile.zstd_level,
        }

    def blob_path(self, sha256: str) -> Path:
        digest = self.validate_digest(sha256)
        return self.root / digest[:2] / f"{digest[2:]}.zst"

    @staticmethod
    def validate_digest(sha256: str) -> str:
        digest = sha256.lower()
        if not SHA256_PATTERN.fullmatch(digest):
            raise InvalidDigestError("CAS digest must be a lowercase 64-character SHA-256")
        return digest

    @classmethod
    def _publish_lock(cls, digest: str) -> threading.Lock:
        with cls._publish_locks_guard:
            return cls._publish_locks.setdefault(digest, threading.Lock())

    def put(
        self,
        source: Path,
        profile: StorageProfile | None = None,
        *,
        publish_guard: Callable[[StoredBlob], None] | None = None,
    ) -> StoredBlob:
        """Compress a bounded source and publish it atomically by digest.

        ``publish_guard`` runs while the per-digest publication lock is held,
        after a new physical representation is published.  A guard failure
        removes that just-published representation before the lock is released,
        so a rejected repair cannot masquerade as the durable CAS truth.
        """
        compressed_temp: Path | None = None
        digest_builder = hashlib.sha256()
        logical_size = 0
        codec_config = self._codec_config_for(profile)
        level = cast(int, codec_config["level"])
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=".cas-", suffix=".zst.tmp", dir=self.temp_root, delete=False
            ) as output_handle:
                compressed_temp = Path(output_handle.name)
                compressor = zstandard.ZstdCompressor(
                    level=level,
                    write_checksum=True,
                    write_content_size=False,
                )
                with (
                    compressor.stream_writer(output_handle, closefd=False) as writer,
                    source.open("rb") as source_handle,
                ):
                    while chunk := source_handle.read(CHUNK_SIZE):
                        digest_builder.update(chunk)
                        logical_size += len(chunk)
                        writer.write(chunk)
                output_handle.flush()
                os.fsync(output_handle.fileno())

            digest = digest_builder.hexdigest()
            final_path = self.blob_path(digest)
            final_path.parent.mkdir(parents=True, exist_ok=True)
            self._verify_path(compressed_temp, digest, logical_size)
            lock = self._publish_lock(digest)
            published_new = True
            with lock:
                if final_path.exists():
                    self._verify_path(final_path, digest, logical_size)
                    compressed_temp.unlink(missing_ok=True)
                    published_new = False
                else:
                    try:
                        os.link(compressed_temp, final_path)
                        compressed_temp.unlink(missing_ok=True)
                    except FileExistsError:
                        self._verify_path(final_path, digest, logical_size)
                        compressed_temp.unlink(missing_ok=True)
                        published_new = False
                    except OSError:
                        # Hard links are the non-overwriting atomic publication path on
                        # normal filesystems. The lock plus replace is a safe fallback
                        # for filesystems that do not expose hard links.
                        if final_path.exists():
                            self._verify_path(final_path, digest, logical_size)
                            compressed_temp.unlink(missing_ok=True)
                            published_new = False
                        else:
                            os.replace(compressed_temp, final_path)
                            compressed_temp = None
                stored = StoredBlob(
                    sha256=digest,
                    logical_size=logical_size,
                    physical_size=final_path.stat().st_size,
                    codec="zstd",
                    codec_config=(
                        codec_config if published_new else {"representation": "existing"}
                    ),
                    path=final_path,
                    published_new=published_new,
                )
                if publish_guard is not None and published_new:
                    try:
                        publish_guard(stored)
                    except Exception:
                        try:
                            self._verify_path(final_path, digest, logical_size)
                            final_path.unlink()
                            self._fsync_directory(final_path.parent)
                        except (OSError, CASIntegrityError) as cleanup_exc:
                            raise CASStorageError(
                                "CAS publish guard failed and cleanup was unsafe"
                            ) from cleanup_exc
                        raise
            return stored
        except (OSError, zstandard.ZstdError) as exc:
            raise CASStorageError("CAS write failed") from exc
        finally:
            if compressed_temp is not None:
                compressed_temp.unlink(missing_ok=True)

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        directory_flag = getattr(os, "O_DIRECTORY", 0)
        if not directory_flag:
            return
        descriptor: int | None = None
        try:
            descriptor = os.open(str(path), os.O_RDONLY | directory_flag)
            os.fsync(descriptor)
        except OSError:
            return
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def _compress_file(self, source: Path, destination: Path, profile: StorageProfile) -> None:
        _validate_storage_profile(profile)
        compressor = zstandard.ZstdCompressor(
            level=profile.zstd_level,
            write_checksum=True,
            write_content_size=False,
        )
        with destination.open("wb") as output_handle, source.open("rb") as source_handle:
            with compressor.stream_writer(output_handle, closefd=False) as writer:
                while chunk := source_handle.read(CHUNK_SIZE):
                    writer.write(chunk)
            output_handle.flush()
            os.fsync(output_handle.fileno())

    def _cleanup_backup(self, backup: Path) -> None:
        backup.unlink(missing_ok=True)

    def transition(
        self,
        sha256: str,
        profile: StorageProfile,
        *,
        expected_size: int | None = None,
        persist_metadata: Callable[[StoredBlob], None] | None = None,
    ) -> StoredBlob:
        """Atomically recompress a verified digest and optionally commit its metadata."""
        digest = self.validate_digest(sha256)
        _validate_storage_profile(profile)
        final_path = self.blob_path(digest)
        if not final_path.is_file():
            raise CASIntegrityError("CAS blob is missing")
        lock = self._publish_lock(digest)
        logical_temp: Path | None = None
        compressed_temp: Path | None = None
        backup_temp: Path | None = None
        published = False
        metadata_committed = False

        def restore_previous() -> None:
            nonlocal backup_temp
            if backup_temp is None or not backup_temp.exists():
                raise CASStorageError("verified prior CAS representation is unavailable")
            os.replace(backup_temp, final_path)
            backup_temp = None
            self._fsync_directory(final_path.parent)

        with lock:
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    prefix=".cas-backup-",
                    suffix=".zst.tmp",
                    dir=self.temp_root,
                    delete=False,
                ) as backup_handle:
                    backup_temp = Path(backup_handle.name)
                    with final_path.open("rb") as source_handle:
                        shutil.copyfileobj(source_handle, backup_handle, length=CHUNK_SIZE)
                    backup_handle.flush()
                    os.fsync(backup_handle.fileno())

                with tempfile.NamedTemporaryFile(
                    mode="w+b",
                    prefix=".cas-logical-",
                    suffix=".tmp",
                    dir=self.temp_root,
                    delete=False,
                ) as logical_handle:
                    logical_temp = Path(logical_handle.name)
                    self._decompress_verified(
                        final_path, digest, expected_size, cast(BinaryIO, logical_handle)
                    )
                    logical_size = logical_handle.tell()
                    logical_handle.flush()
                    os.fsync(logical_handle.fileno())

                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    prefix=".cas-transition-",
                    suffix=".zst.tmp",
                    dir=self.temp_root,
                    delete=False,
                ) as compressed_handle:
                    compressed_temp = Path(compressed_handle.name)
                self._compress_file(logical_temp, compressed_temp, profile)
                self._verify_path(compressed_temp, digest, logical_size)
                physical_size = compressed_temp.stat().st_size
                os.replace(compressed_temp, final_path)
                compressed_temp = None
                published = True
                self._fsync_directory(final_path.parent)
                stored = StoredBlob(
                    sha256=digest,
                    logical_size=logical_size,
                    physical_size=physical_size,
                    codec="zstd",
                    codec_config=self._codec_config_for(profile),
                    path=final_path,
                )
                if persist_metadata is not None:
                    try:
                        persist_metadata(stored)
                    except Exception:
                        restore_previous()
                        published = False
                        raise
                metadata_committed = persist_metadata is not None
                if backup_temp is not None:
                    if metadata_committed:
                        try:
                            self._cleanup_backup(backup_temp)
                        except OSError:
                            # PostgreSQL metadata is already durable. Keep the verified
                            # backup as best-effort cleanup rather than rolling back truth.
                            backup_temp = None
                        else:
                            backup_temp = None
                    else:
                        self._cleanup_backup(backup_temp)
                        backup_temp = None
                return stored
            except (OSError, zstandard.ZstdError, CASIntegrityError) as exc:
                if published and not metadata_committed:
                    try:
                        restore_previous()
                    except (OSError, CASStorageError) as restore_exc:
                        raise CASStorageError(
                            "CAS transition failed and restore was unsafe"
                        ) from restore_exc
                if isinstance(exc, CASIntegrityError):
                    raise
                raise CASStorageError("CAS transition failed") from exc
            finally:
                for temporary in (logical_temp, compressed_temp):
                    if temporary is not None:
                        temporary.unlink(missing_ok=True)
                if backup_temp is not None and not metadata_committed:
                    backup_temp.unlink(missing_ok=True)

    def open_verified(self, sha256: str, expected_size: int | None = None) -> BinaryIO:
        """Materialize a fully verified decompression before any response is returned."""
        digest = self.validate_digest(sha256)
        path = self.blob_path(digest)
        if not path.is_file():
            raise CASIntegrityError("CAS blob is missing")

        temporary = cast(BinaryIO, tempfile.TemporaryFile(mode="w+b", dir=self.temp_root))  # noqa: SIM115 - ownership is transferred to the response iterator
        try:
            self._decompress_verified(path, digest, expected_size, temporary)
            temporary.seek(0)
            return temporary
        except (OSError, zstandard.ZstdError, CASIntegrityError) as exc:
            temporary.close()
            if isinstance(exc, CASIntegrityError):
                raise
            raise CASIntegrityError("CAS blob could not be verified") from exc

    def read_verified(self, sha256: str, expected_size: int | None = None) -> bytes:
        with self.open_verified(sha256, expected_size) as handle:
            return handle.read()

    def _verify_path(self, path: Path, digest: str, expected_size: int) -> None:
        with cast(BinaryIO, tempfile.TemporaryFile(mode="w+b", dir=self.temp_root)) as verified:
            self._decompress_verified(path, digest, expected_size, verified)

    def _decompress_verified(
        self,
        path: Path,
        digest: str,
        expected_size: int | None,
        output: BinaryIO,
    ) -> None:
        digest_builder = hashlib.sha256()
        logical_size = 0
        decompressor = zstandard.ZstdDecompressor().decompressobj()
        with path.open("rb") as compressed:
            while compressed_chunk := compressed.read(CHUNK_SIZE):
                chunk = decompressor.decompress(compressed_chunk)
                logical_size += len(chunk)
                if expected_size is not None and logical_size > expected_size:
                    raise CASIntegrityError("CAS decompression exceeded declared logical size")
                digest_builder.update(chunk)
                output.write(chunk)
            chunk = decompressor.flush()
            logical_size += len(chunk)
            if expected_size is not None and logical_size > expected_size:
                raise CASIntegrityError("CAS decompression exceeded declared logical size")
            digest_builder.update(chunk)
            output.write(chunk)
        if not decompressor.eof or decompressor.unused_data or decompressor.unconsumed_tail:
            raise CASIntegrityError("CAS Zstandard frame is truncated or has trailing data")
        if expected_size is not None and logical_size != expected_size:
            raise CASIntegrityError("CAS logical size does not match stored metadata")
        if digest_builder.hexdigest() != digest:
            raise CASIntegrityError("CAS SHA-256 does not match its content-addressed path")

    def iter_file(self, handle: BinaryIO) -> Iterator[bytes]:
        try:
            while chunk := handle.read(CHUNK_SIZE):
                yield chunk
        finally:
            handle.close()
