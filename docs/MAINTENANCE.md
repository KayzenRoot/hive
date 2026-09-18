# Maintenance policy

This document describes how the HIVE stable line is maintained. It does not
replace the canonical project sources in `docs/project-brain/`; where this
document and a newer accepted checkpoint disagree, the checkpoint wins.

## Supported line

- `1.0.x` is the supported stable line. Patch releases are backward compatible
  and never change the public operational contract.
- Older bootstrap artifacts (`v0.0.1-bootstrap`) are historical pre-releases and
  are not maintained.
- Feature work and new capabilities target the next minor release through the
  normal governed branch/PR flow.

## Patch cadence

- Patch releases are demand-driven: security fixes, dependency maintenance,
  documentation corrections and bounded operational defects.
- Every published patch or minor release receives a versioned release-note
  document under `docs/releases/` and a matching CHANGELOG entry. Release notes
  never claim untested behavior.
- There is no fixed time-based release train; a release exists only after
  exact-head review, a protected squash merge, mandatory post-merge CI and a
  published GitHub Release with verified assets.

## Dependency handling

- Dependabot proposes weekly grouped patch/minor updates for pip, npm and
  GitHub Actions; breaking majors remain separate, reviewable PRs.
- Dependency PRs are never auto-merged. They require the same validation and
  review as any other change.
- Security-relevant upgrades may be expedited as a `1.0.x` patch.

## Security fixes

- Security fixes follow `SECURITY.md`. Private reports are handled before public
  disclosure.
- A release candidate must have zero unresolved CRITICAL/HIGH findings, no
  committed secrets and no weakened scanning.
- `scripts/check_secrets.py` remains mandatory and is not replaced by weaker
  scanning.

## Backports and deprecation

- Backports are limited to the supported `1.0.x` line and must be
  backward-compatible.
- Deprecations are announced in release notes before removal and require a major
  version when they break the public contract.
- Breaking schema or API changes are only allowed in `2.0.0` releases.

## Governance

Maintenance follows HIVE-ADR-019: one operational GitHub identity, exact-head
audit, protected `main`, the three required checks (Validate, Integration
health, Review Evidence), squash-only merge and mandatory post-merge CI on the
exact new `main` SHA.
