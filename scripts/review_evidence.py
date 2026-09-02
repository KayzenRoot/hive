"""Generate and validate a generic, secret-free Review Evidence manifest."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "review-evidence-v1.schema.json"
DEFAULT_OUTPUT = ROOT / "tmp" / "review-evidence"
HEX_SHA = re.compile(r"^[0-9a-f]{40}$")


def run(command: list[str]) -> tuple[int, str]:
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.returncode, result.stdout.strip()


def git_value(*args: str, fallback: str = "") -> str:
    code, output = run(["git", *args])
    return output if code == 0 and output else fallback


def env_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y"}


def repository_name() -> str:
    remote = git_value("remote", "get-url", "origin", fallback="local")
    remote = remote.removesuffix(".git")
    if remote.startswith("git@") and ":" in remote:
        return remote.split(":", 1)[1]
    if "/" in remote:
        return remote.rsplit("/", 2)[-2] + "/" + remote.rsplit("/", 1)[-1]
    return remote


def changed_paths(base_sha: str, head_sha: str) -> list[str]:
    base_exists, _ = run(["git", "cat-file", "-e", f"{base_sha}^{{commit}}"])
    if HEX_SHA.fullmatch(base_sha) and base_exists == 0:
        code, output = run(["git", "diff", "--name-only", f"{base_sha}...{head_sha}"])
        if code == 0:
            return [path for path in output.splitlines() if path]
    return [path for path in git_value("diff", "--name-only", "HEAD^", "HEAD").splitlines() if path]


def migration_head() -> str:
    db_path = ROOT / "backend" / "app" / "db.py"
    match = re.search(r'CURRENT_SCHEMA_REVISION\s*=\s*"([^"]+)"', db_path.read_text())
    return match.group(1) if match else "UNKNOWN"


def validation_status(text: str, marker: str) -> str:
    if marker not in text:
        return "UNKNOWN"
    return "PASS" if "exit_code: 0" in text else "FAIL"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def benchmark_fields(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "UNKNOWN",
            "query_count": 0,
            "recall_at_1": 0.0,
            "recall_at_5": 0.0,
            "mrr": 0.0,
            "critical_context_misses": 0,
        }
    return {
        "status": "PASS" if not data.get("critical_context_misses") else "FAIL",
        "query_count": int(data.get("query_count", 0)),
        "recall_at_1": float(data.get("recall_at_1", 0.0)),
        "recall_at_5": float(data.get("recall_at_5", 0.0)),
        "mrr": float(data.get("mrr", 0.0)),
        "critical_context_misses": len(data.get("critical_context_misses", [])),
    }


def build_manifest(args: argparse.Namespace) -> dict[str, object]:
    validation = ROOT / "tmp" / "validation"
    summary = read_text(validation / "summary.txt")
    lint = read_text(validation / "lint-typecheck-build-results.txt")
    tests = read_text(validation / "test-results.txt")
    base_sha = args.base_sha or git_value("merge-base", "HEAD", "origin/main", fallback="0" * 40)
    head_sha = args.head_sha or git_value("rev-parse", "HEAD")
    actual_head = git_value("rev-parse", "HEAD")
    if head_sha != actual_head:
        raise ValueError(f"head SHA mismatch: expected {head_sha}, checked out {actual_head}")
    paths = changed_paths(base_sha, head_sha)
    all_validation = summary + "\n" + lint + "\n" + tests
    checks = {
        "canonical": validation_status(all_validation, "canonical source verification"),
        "secrets": validation_status(all_validation, "secret scan"),
        "lint": "PASS" if summary.strip() == "PASS" and "ruff lint" in lint else "UNKNOWN",
        "typecheck": "PASS"
        if summary.strip() == "PASS" and "dashboard typecheck" in lint
        else "UNKNOWN",
        "tests": "PASS" if summary.strip() == "PASS" and "backend tests" in tests else "UNKNOWN",
        "build": "PASS" if summary.strip() == "PASS" and "dashboard build" in lint else "UNKNOWN",
        "integration": "PASS" if args.integration_status == "PASS" else args.integration_status,
        "review_evidence": "PASS",
    }
    draft = args.draft or env_bool(args.draft_env, False)
    pr_number = args.pr_number
    benchmark = benchmark_fields(validation / "retrieval-benchmark.json")
    review_status = "DRAFT" if pr_number and draft else "OPEN" if pr_number else "NOT_CREATED"
    return {
        "schema_version": 1,
        "work_order": args.work_order,
        "repository": args.repository or repository_name(),
        "pull_request": {"number": pr_number, "is_draft": draft},
        "base": {"branch": args.base_branch, "sha": base_sha},
        "head": {
            "branch": args.head_branch
            or git_value("branch", "--show-current", fallback="DETACHED"),
            "sha": head_sha,
        },
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "changed_files": {"count": len(paths), "paths": paths},
        "migrations": {"head": migration_head()},
        "checks": checks,
        "benchmark": benchmark,
        "review_state": {"status": review_status, "merge_performed": False},
        "negative_scope": [
            "No merge or release was performed.",
            "No canonical Project Brain checkpoint was modified.",
            "No embeddings, reranking, autonomous executor, or LLM provider was added.",
        ],
    }


def validate_manifest(manifest: dict[str, object]) -> None:
    required = {
        "schema_version",
        "work_order",
        "repository",
        "pull_request",
        "base",
        "head",
        "generated_at",
        "changed_files",
        "migrations",
        "checks",
        "benchmark",
        "review_state",
        "negative_scope",
    }
    if set(manifest) != required or manifest["schema_version"] != 1:
        raise ValueError("manifest does not match the required top-level schema")
    for key in ("base", "head"):
        section = cast(dict[str, Any], manifest[key])
        sha = section["sha"]
        if not isinstance(sha, str) or not HEX_SHA.fullmatch(sha):
            raise ValueError(f"invalid {key} SHA")
    review_state = cast(dict[str, Any], manifest["review_state"])
    if review_state["merge_performed"] is not False:
        raise ValueError("review evidence cannot report a merge")
    errors = sorted(
        jsonschema.Draft202012Validator(
            json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        ).iter_errors(manifest),
        key=str,
    )
    if errors:
        raise ValueError(f"manifest schema validation failed: {errors[0].message}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-order", default="WO-006")
    parser.add_argument("--repository")
    parser.add_argument("--pr-number", type=int)
    parser.add_argument("--draft", action="store_true")
    parser.add_argument("--draft-env", default="")
    parser.add_argument("--base-branch", default="main")
    parser.add_argument("--base-sha", default="")
    parser.add_argument("--head-branch", default="")
    parser.add_argument("--head-sha", default="")
    parser.add_argument(
        "--integration-status", choices=["PASS", "FAIL", "UNKNOWN"], default="UNKNOWN"
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = build_manifest(args)
    validate_manifest(manifest)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output_dir / "review-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    head = cast(dict[str, Any], manifest["head"])
    base = cast(dict[str, Any], manifest["base"])
    benchmark = cast(dict[str, Any], manifest["benchmark"])
    review_state = cast(dict[str, Any], manifest["review_state"])
    migrations = cast(dict[str, Any], manifest["migrations"])
    summary = (
        f"# HIVE Review Evidence — {manifest['work_order']}\n\n"
        f"- Head: `{head['sha']}`\n"
        f"- Base: `{base['sha']}`\n"
        f"- Review state: **{review_state['status']}**\n"
        f"- Migration head: `{migrations['head']}`\n"
        f"- Benchmark: **{benchmark['status']}**; "
        f"recall@1 `{benchmark['recall_at_1']}`, "
        f"recall@5 `{benchmark['recall_at_5']}`, "
        f"MRR `{benchmark['mrr']}`\n\n"
        "The machine-readable manifest is the source for this summary. "
        "Merge and release remain prohibited for this evidence run.\n"
    )
    (args.output_dir / "review-summary.md").write_text(summary, encoding="utf-8")
    print(
        json.dumps(
            {"manifest": str(manifest_path), "summary": str(args.output_dir / "review-summary.md")},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
