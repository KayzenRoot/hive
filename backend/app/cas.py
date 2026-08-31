from __future__ import annotations

import hashlib
import os
import re
import tempfile
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, cast

import zstandard

from .config import Settings

CHUNK_SIZE = 1024 * 1024
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class CASStorageError(RuntimeError):
    """A CAS operation could not safely complete."""


class CASIntegrityError(CASStorageError):
    """A stored blob did not reproduce its declared original bytes."""


class InvalidDigestError(ValueError):
    """A caller supplied a digest that cannot identify a CAS path."""


@dataclass(frozen=True)
class StoredBlob:
    sha256: str
    logical_size: int
    physical_size: int
    codec: str
    codec_config: dict[str, int | bool | str]
    path: Path


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

    def put(self, source: Path) -> StoredBlob:
        """Compress a bounded temporary source and publish it atomically by digest."""
        compressed_temp: Path | None = None
        digest_builder = hashlib.sha256()
        logical_size = 0
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=".cas-", suffix=".zst.tmp", dir=self.temp_root, delete=False
            ) as output_handle:
                compressed_temp = Path(output_handle.name)
                compressor = zstandard.ZstdCompressor(
                    level=self.settings.cas_zstd_level,
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
            with lock:
                if final_path.exists():
                    self._verify_path(final_path, digest, logical_size)
                    compressed_temp.unlink(missing_ok=True)
                else:
                    try:
                        os.link(compressed_temp, final_path)
                        compressed_temp.unlink(missing_ok=True)
                    except FileExistsError:
                        self._verify_path(final_path, digest, logical_size)
                        compressed_temp.unlink(missing_ok=True)
                    except OSError:
                        # Hard links are the non-overwriting atomic publication path on
                        # normal filesystems. The lock plus replace is a safe fallback
                        # for filesystems that do not expose hard links.
                        if final_path.exists():
                            self._verify_path(final_path, digest, logical_size)
                            compressed_temp.unlink(missing_ok=True)
                        else:
                            os.replace(compressed_temp, final_path)
                            compressed_temp = None
            return StoredBlob(
                sha256=digest,
                logical_size=logical_size,
                physical_size=final_path.stat().st_size,
                codec="zstd",
                codec_config=self.codec_config.copy(),
                path=final_path,
            )
        except (OSError, zstandard.ZstdError) as exc:
            raise CASStorageError("CAS write failed") from exc
        finally:
            if compressed_temp is not None:
                compressed_temp.unlink(missing_ok=True)

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
