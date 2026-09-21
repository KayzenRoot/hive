"""Fail-closed identity checks for the governed release publisher."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Mapping

STRICT_SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
LOWER_HEX_SHA40 = re.compile(r"^[0-9a-f]{40}$")

# HIVE-REL-002 is the immutable historical v1.0.0 publication request. The
# v1.0.1 request identity is deliberately separate and must be authorized in
# a later publication increment; this preparation does not create that file.
PUBLISH_REQUEST_WORK_ORDERS = {
    "1.0.0": "HIVE-REL-002",
    "1.0.1": "HIVE-REL-006",
}


def expected_publish_request_work_order(version: str) -> str:
    """Return the only publication work order accepted for a stable version."""

    try:
        return PUBLISH_REQUEST_WORK_ORDERS[version]
    except KeyError as error:
        raise ValueError(
            f"no recognized publish-request work order for version {version!r}"
        ) from error


def validate_publisher_inputs(
    *,
    request: Mapping[str, object],
    candidate: Mapping[str, object],
    version: str,
    tag: str,
    source_sha: str,
    observed_parent: str | None = None,
) -> None:
    """Validate the version-bound request/candidate contract before publication."""

    if STRICT_SEMVER.fullmatch(version) is None:
        raise ValueError(f"stable publisher requires strict SemVer, observed {version!r}")
    if tag != f"v{version}":
        raise ValueError("publisher tag must match the current VERSION exactly")
    if LOWER_HEX_SHA40.fullmatch(source_sha) is None:
        raise ValueError("publisher source SHA is invalid")

    expected = {
        "status": "armed",
        "product": "HIVE",
        "version": version,
        "tag": tag,
        "work_order": expected_publish_request_work_order(version),
    }
    for key, value in expected.items():
        if request.get(key) != value:
            raise ValueError(f"release request {key} mismatch: {request.get(key)!r} != {value!r}")

    if candidate.get("product") != "HIVE":
        raise ValueError("candidate receipt product mismatch")
    if candidate.get("status") != "release-candidate":
        raise ValueError("candidate receipt is not in release-candidate state")
    if candidate.get("release_published") is not False:
        raise ValueError("candidate receipt unexpectedly claims publication")
    if candidate.get("version") != version or candidate.get("tag") != tag:
        raise ValueError("candidate receipt version/tag mismatch")

    security = candidate.get("dependency_security")
    if not isinstance(security, Mapping) or security.get("release_gate") != "PASS":
        raise ValueError("dependency-security release gate is not PASS")
    if security.get("runtime_high_critical_remaining") is not False:
        raise ValueError("runtime HIGH/CRITICAL dependency blocker remains")
    remaining = security.get("remaining_open")
    if (
        not isinstance(remaining, Mapping)
        or remaining.get("critical") != 0
        or remaining.get("high") != 0
    ):
        raise ValueError("applicable unresolved CRITICAL/HIGH dependency alert remains")

    authorized_parent = request.get("authorized_parent")
    if (
        not isinstance(authorized_parent, str)
        or LOWER_HEX_SHA40.fullmatch(authorized_parent) is None
    ):
        raise ValueError("release request authorized_parent is invalid")
    if observed_parent is None:
        observed_parent = subprocess.check_output(
            ["git", "rev-parse", f"{source_sha}^"],
            text=True,
        ).strip()
    if observed_parent != authorized_parent:
        raise ValueError(
            f"publisher commit parent mismatch: {observed_parent} != {authorized_parent}"
        )
