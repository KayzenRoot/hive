# Versioning policy

HIVE uses Semantic Versioning for published releases. This document is the
canonical maintenance reference for public release numbers. The machine-readable
source of truth is the repository `VERSION` file, validated deterministically by
`scripts/verify_release_metadata.py`.

## Release number semantics

- `1.0.x` — backward-compatible bug, security, dependency, documentation and
  bounded operational fixes.
- `1.x.0` — backward-compatible capabilities accepted through normal HIVE
  governance, including exact-head review under `docs/project-brain/16-DECISIONS-LEDGER.md`
  (HIVE-ADR-019).
- `2.0.0` — breaking public API, schema or operational contract changes that
  cannot remain backward compatible.

Prerelease suffixes such as `-rc.1` require explicit owner authorization and are
never used silently. The deterministic verifier rejects a non-stable active
`VERSION` for a stable release.

## Tags, branches and immutability

- `main` is the latest accepted stable development baseline.
- Release tags (`vX.Y.Z`) are immutable by policy and must target the exact
  accepted release commit.
- The tag/version/notes contract is enforced by `.github/workflows/release.yml`;
  a tag whose version, release notes or validation evidence do not match is not
  published.
- Historical release notes and receipts are immutable evidence. A correction is
  a new patch release or an explicitly marked erratum; accepted lineage is never
  rewritten.

## Version surfaces

Active runtime and distribution identity must agree everywhere:

- `VERSION`
- `backend/app/__init__.py`
- `backend/app/config.py`
- `dashboard/package.json` and `dashboard/package-lock.json`
- the README latest-stable identity

`python scripts/verify_release_metadata.py` fails closed on any drift and runs
inside `python scripts/validate.py`, so the hosted Validate gate enforces it.

## Historical identity

The internal HIVE V0.1 Foundation program closed the product baseline that is
distributed publicly as HIVE v1.0.0. Historical bootstrap and V0.1 documents
(for example `docs/releases/v0.0.1-bootstrap.md`, the historical CHANGELOG entry
and `docs/project-brain/`) keep their original meaning and are never rewritten
to match a newer release number.
