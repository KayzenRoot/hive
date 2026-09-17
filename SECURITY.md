# Security policy

HIVE is a local-first platform; the supported security line is **1.0.x**.
Historical pre-releases (for example `v0.0.1-bootstrap`) are not supported.

## Reporting a vulnerability

Report vulnerabilities privately through GitHub's private vulnerability
reporting ("Report a vulnerability" in the repository Security tab) or by
contacting the repository owner (`KayzenRoot`) privately before any public
disclosure. Never open a public issue that contains exploit-sensitive details,
live credentials or personal data.

Include:

- affected version or commit and deployment mode (Docker Compose, OS);
- a minimal reproduction or proof of impact;
- expected and observed behavior, with logs stripped of secrets;
- your assessment of severity and any suggested remediation.

## Severity expectations

- **CRITICAL / HIGH** — actively exploitable issues affecting isolation,
  credential handling, canonical data integrity or remote execution controls.
  Acknowledge quickly and fix before the next release; a release candidate must
  have zero unresolved CRITICAL/HIGH findings.
- **MEDIUM** — bounded impact requiring unusual preconditions; fixed in the
  normal patch cadence.
- **LOW** — hardening and defense-in-depth; scheduled with maintenance work.

## Release security posture

- `scripts/check_secrets.py` is mandatory in the Validate gate and is never
  replaced by weaker scanning.
- GitHub secret scanning and push protection are enabled for the repository.
- CodeQL (Python, JavaScript/TypeScript) and Dependency Review run as advisory
  automation and do not bypass the required Validate, Integration health and
  Review Evidence gates or ruleset 21934284.
- Release packages are generated from `git archive` and exclude secrets, keys,
  `.env` files, local data, review bundles and user-owned project data.
- Tag signing, SBOM and provenance attestations are not claimed.

Do not commit secrets or personal data to issues, pull requests or logs.
