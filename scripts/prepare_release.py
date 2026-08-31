from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = {
    "README.md",
    "VERSION",
    "docker-compose.yml",
    "backend/Dockerfile",
    "dashboard/package-lock.json",
    "docs/INSTALLATION.md",
    "docs/RELEASING.md",
}
FORBIDDEN_PARTS = {
    ".git",
    "node_modules",
    "review-bundles",
    "tmp",
    ".hive-data",
    "HIVE_DATA_ROOT",
    "data",
    "local-data",
    "release-assets",
}


def git_show(ref: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"Required path is missing at {ref}: {path}")
    return result.stdout


def create_archive(tag: str, ref: str, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"hive-{tag}.zip"
    checksum_path = output_dir / f"hive-{tag}.zip.sha256"
    subprocess.run(
        [
            "git",
            "archive",
            "--format=zip",
            f"--prefix=hive-{tag}/",
            f"--output={archive_path}",
            ref,
        ],
        cwd=ROOT,
        check=True,
    )

    with zipfile.ZipFile(archive_path) as archive:
        names = [name.replace("\\", "/") for name in archive.namelist()]
    prefix = f"hive-{tag}/"
    relative_names = {name.removeprefix(prefix) for name in names if name.startswith(prefix)}
    missing = sorted(REQUIRED_FILES - relative_names)
    if missing:
        raise RuntimeError(f"Release package is missing required files: {', '.join(missing)}")
    forbidden = sorted(
        name
        for name in relative_names
        if any(part in FORBIDDEN_PARTS for part in Path(name).parts)
        or Path(name).name in {".env", ".secrets"}
        or Path(name).suffix in {".pem", ".key"}
    )
    if forbidden:
        raise RuntimeError(f"Release package contains forbidden paths: {', '.join(forbidden)}")

    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    checksum_path.write_text(f"{digest}  {archive_path.name}\n", encoding="utf-8")
    return archive_path, checksum_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a deterministic HIVE release package.")
    parser.add_argument("--tag", required=True, help="Release tag, for example v0.0.1-bootstrap")
    parser.add_argument("--ref", default="HEAD", help="Git ref/commit to package")
    parser.add_argument("--output-dir", default="tmp/release-dry-run")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    tag = args.tag.strip()
    if not tag.startswith("v") or tag == "v":
        raise SystemExit("Release contract error: tag must start with v.")
    version = git_show(args.ref, "VERSION").decode("utf-8").strip()
    if tag.removeprefix("v") != version:
        raise SystemExit(f"Release contract error: tag {tag} does not match VERSION {version}.")
    notes_path = f"docs/releases/{tag}.md"
    git_show(args.ref, notes_path)

    archive_path, checksum_path = create_archive(tag, args.ref, ROOT / args.output_dir)
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    result = {
        "dry_run": args.dry_run,
        "tag": tag,
        "source_ref": args.ref,
        "version": version,
        "notes": notes_path,
        "archive": str(archive_path),
        "checksum": str(checksum_path),
        "size_bytes": archive_path.stat().st_size,
        "sha256": digest,
        "publication": "not performed",
    }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
