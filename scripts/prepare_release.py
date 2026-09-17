from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_PRODUCT_BASELINE_SHA = "90cc1b91b48d628dfb3e4773e1672535b4cb8991"
MIGRATIONS_DIR = Path("migrations") / "versions"
REVISION_PATTERN = re.compile(r'^revision: str = "([^"]+)"$', re.MULTILINE)
DOWN_REVISION_PATTERN = re.compile(r'^down_revision: str \| None = "([^"]+)"$', re.MULTILINE)
REQUIRED_FILES = {
    "README.md",
    "VERSION",
    "CHANGELOG.md",
    "LICENSE",
    "docker-compose.yml",
    "requirements.txt",
    "backend/Dockerfile",
    "dashboard/Dockerfile",
    "dashboard/package-lock.json",
    "docs/INSTALLATION.md",
    "docs/RELEASING.md",
    "docs/UPGRADING.md",
    "docs/VERSIONING.md",
}
FORBIDDEN_PARTS = {
    ".git",
    "node_modules",
    "review-bundles",
    "tmp",
    ".hive-data",
    ".hive-projects",
    "HIVE_DATA_ROOT",
    "data",
    "local-data",
    "release-assets",
}


def git_show(root: Path, ref: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"Required path is missing at {ref}: {path}")
    return result.stdout


def git_value(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed in {root}")
    return result.stdout.strip()


def migration_head(root: Path) -> str:
    versions_root = root / MIGRATIONS_DIR
    revisions: dict[str, str | None] = {}
    for path in sorted(versions_root.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        revision_match = REVISION_PATTERN.search(text)
        if revision_match is None:
            continue
        down_match = DOWN_REVISION_PATTERN.search(text)
        revisions[revision_match.group(1)] = down_match.group(1) if down_match else None
    if not revisions:
        raise RuntimeError("Release manifest requires at least one Alembic revision.")
    referenced = {down for down in revisions.values() if down}
    heads = sorted(set(revisions) - referenced)
    if len(heads) != 1:
        raise RuntimeError(
            "Release manifest requires exactly one migration head, found: "
            + (", ".join(heads) or "none")
        )
    return heads[0]


def validation_summary(root: Path) -> str | None:
    summary_path = root / "tmp" / "validation" / "summary.txt"
    if not summary_path.is_file():
        return None
    return summary_path.read_text(encoding="utf-8").strip() or None


def create_archive(root: Path, tag: str, ref: str, output_dir: Path) -> tuple[Path, Path]:
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
        cwd=root,
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


def build_manifest(
    root: Path, tag: str, ref: str, output_dir: Path, dry_run: bool
) -> dict[str, object]:
    version = git_show(root, ref, "VERSION").decode("utf-8").strip()
    if tag.removeprefix("v") != version:
        raise SystemExit(f"Release contract error: tag {tag} does not match VERSION {version}.")
    notes_path = f"docs/releases/{tag}.md"
    git_show(root, ref, notes_path)

    archive_path, checksum_path = create_archive(root, tag, ref, output_dir)
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    manifest: dict[str, object] = {
        "manifest_version": 1,
        "dry_run": dry_run,
        "tag": tag,
        "version": version,
        "source_ref": ref,
        "source_commit": git_value(root, "rev-parse", ref),
        "notes": notes_path,
        "artifact": archive_path.name,
        "size_bytes": archive_path.stat().st_size,
        "sha256": digest,
        "checksum_algorithm": "sha256",
        "checksum_file": checksum_path.name,
        "migration_head": migration_head(root),
        "canonical_product_baseline": CANONICAL_PRODUCT_BASELINE_SHA,
        "validation_summary": validation_summary(root),
        "publication": "not performed",
    }
    manifest_path = output_dir / f"hive-{tag}.manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a deterministic HIVE release package.")
    parser.add_argument("--tag", required=True, help="Release tag, for example v1.0.0")
    parser.add_argument("--ref", default="HEAD", help="Git ref/commit to package")
    parser.add_argument("--output-dir", default="tmp/release-dry-run")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    tag = args.tag.strip()
    if not tag.startswith("v") or tag == "v":
        raise SystemExit("Release contract error: tag must start with v.")
    manifest = build_manifest(ROOT, tag, args.ref, ROOT / args.output_dir, args.dry_run)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
