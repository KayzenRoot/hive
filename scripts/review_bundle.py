"""Build a generic, secret-free and reproducible review evidence bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "review-bundles"
VALIDATION = ROOT / "tmp" / "validation"
EVIDENCE = ROOT / "tmp" / "review-evidence"


def run(command: list[str], check: bool = False) -> str:
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    output = result.stdout + result.stderr
    if check and result.returncode:
        raise RuntimeError(f"{' '.join(command)} failed with {result.returncode}:\n{output}")
    return output


def read_file(path: Path, fallback: str) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else fallback


def repository_slug() -> str:
    remote = run(["git", "remote", "get-url", "origin"]).strip().removesuffix(".git")
    if remote.startswith("git@") and ":" in remote:
        return remote.split(":", 1)[1]
    if "/" in remote:
        return "/".join(remote.rsplit("/", 2)[-2:])
    return remote or "unknown/unknown"


def github_evidence(repository: str, branch: str, base_branch: str) -> str:
    api_root = f"repos/{repository}"
    commands = [
        ["gh", "api", api_root],
        ["gh", "api", f"{api_root}/rulesets?includes_parents=true"],
        ["gh", "api", f"{api_root}/branches/{base_branch}/protection"],
        [
            "gh",
            "pr",
            "list",
            "--head",
            branch,
            "--base",
            base_branch,
            "--state",
            "all",
            "--json",
            "number,state,mergedAt,url,headRefName,baseRefName,headRefOid,title",
        ],
    ]
    sections: list[str] = []
    for command in commands:
        result = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        sections.append(
            "$ "
            + " ".join(command)
            + f"\nexit_code: {result.returncode}\n"
            + result.stdout
            + result.stderr
        )
    return "\n\n".join(sections)


def generic_review_markdown(work_order: str, head: str, status: str) -> str:
    return f"""# HIVE review bundle — {work_order}

Head: `{head}`
Validation: {status}

This generic fallback bundle contains repository metadata, deterministic
validation/integration evidence, the versioned Review Evidence model and safe
GitHub governance evidence. It is staged for audit only: no merge, release,
tag or canonical checkpoint update is performed by this generator.
"""


def ensure_manifest(args: argparse.Namespace, head: str) -> None:
    manifest_path = EVIDENCE / "review-manifest.json"
    if manifest_path.exists():
        return
    base = run(["git", "merge-base", "HEAD", f"origin/{args.base_branch}"]).strip()
    command = [
        sys.executable,
        "scripts/review_evidence.py",
        "--work-order",
        args.work_order,
        "--repository",
        args.repository,
        "--base-branch",
        args.base_branch,
        "--base-sha",
        base,
        "--head-branch",
        run(["git", "branch", "--show-current"]).strip() or "DETACHED",
        "--head-sha",
        head,
        "--output-dir",
        str(EVIDENCE),
    ]
    run(command, check=True)


def bounded(text: str, limit: int = 12_000) -> str:
    return text if len(text) <= limit else text[:limit] + "\n[bounded excerpt truncated]\n"


def deterministic_zip(zip_path: Path, files: dict[str, str]) -> str:
    with zipfile.ZipFile(
        zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, files[name].encode("utf-8"))
    return hashlib.sha256(zip_path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-order", required=True)
    parser.add_argument("--repository", default="")
    parser.add_argument("--base-branch", default="main")
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    repository = args.repository or repository_slug()
    head = run(["git", "rev-parse", "HEAD"]).strip()
    branch = run(["git", "branch", "--show-current"]).strip() or "DETACHED"
    ensure_manifest(args, head)
    status = read_file(VALIDATION / "summary.txt", "No validation results recorded.").strip()
    safe_work_order = "".join(
        character if character.isalnum() or character in "-_" else "-"
        for character in args.work_order
    )
    work = ROOT / "tmp" / f"review-bundle-{safe_work_order}"
    work.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {
        "REVIEW.md": generic_review_markdown(args.work_order, head, status),
        "git-status.txt": run(["git", "status", "--short", "--branch"]),
        "git-log.txt": run(["git", "log", "--oneline", "--decorate", "--graph", "-n", "30"]),
        "git-diff.patch": run(["git", "diff", "--binary", f"origin/{args.base_branch}...HEAD"]),
        "changed-files.txt": run(
            ["git", "diff", "--name-status", f"origin/{args.base_branch}...HEAD"]
        ),
        "validation-summary.txt": read_file(
            VALIDATION / "summary.txt", "No validation results recorded."
        ),
        "validation-results.txt": bounded(
            read_file(VALIDATION / "test-results.txt", "No test results recorded.")
            + "\n\n"
            + read_file(
                VALIDATION / "lint-typecheck-build-results.txt",
                "No lint/typecheck/build results recorded.",
            )
            + "\n\n"
            + read_file(VALIDATION / "docker-compose-config.txt", "No Compose results recorded.")
        ),
        "integration-results.txt": bounded(
            "\n\n".join(
                f"===== {path.name} =====\n{path.read_text(encoding='utf-8', errors='replace')}"
                for path in sorted(
                    list(VALIDATION.glob("*-integration*.txt"))
                    + list((ROOT / "tmp" / "integration-logs").glob("*.log"))
                )
                if path.is_file()
            )
        ),
        "review-manifest.json": read_file(EVIDENCE / "review-manifest.json", "{}\n"),
        "review-summary.md": read_file(
            EVIDENCE / "review-summary.md", "No review summary recorded.\n"
        ),
        "github-governance.json": read_file(EVIDENCE / "github-governance.json", "{}\n"),
        "github-configuration-evidence.txt": github_evidence(repository, branch, args.base_branch),
    }
    benchmark = VALIDATION / "retrieval-benchmark.json"
    if benchmark.exists():
        files["benchmark.json"] = benchmark.read_text(encoding="utf-8")
    for name, content in files.items():
        (work / name).write_text(content, encoding="utf-8", newline="\n")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = args.output_dir / f"hive-{safe_work_order.lower()}-review-{head[:12]}.zip"
    digest = deterministic_zip(zip_path, files)
    checksum_path = zip_path.with_suffix(".zip.sha256")
    checksum_path.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    print(json.dumps({"zip": str(zip_path), "sha256": digest}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
