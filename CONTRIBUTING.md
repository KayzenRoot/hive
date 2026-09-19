# Contributing to HIVE

HIVE is maintained as a professional, auditable project. Read
[AGENTS.md](AGENTS.md) and the canonical sources in `docs/project-brain/` before
changing code.

## License and contribution terms

HIVE is open source under the [Apache License 2.0](LICENSE). Unless explicitly
stated otherwise, a contribution intentionally submitted for inclusion in HIVE
is provided under the Apache-2.0 terms described in Section 5 of the license.

Only submit code, documentation or other material that you have the right to
license for inclusion in the project. Third-party components retain their own
licenses and must remain compatible with HIVE's distribution obligations.

## Workflow

- Work on a focused branch and open one Ready pull request against protected
  `main`. Never push directly to `main`.
- The PR body must contain exactly one work-order marker and, when the governed
  work order requires it, one authorized-base marker.
- Include motivation, scope, out-of-scope boundaries, test evidence, security
  impact, migration/data impact and a rollback plan.
- Release-affecting changes must keep version and release metadata coherent:
  run `python scripts/verify_release_metadata.py`.
- Run `python scripts/validate.py` locally. Hosted Validate, Integration health
  and Review Evidence must pass on the exact PR HEAD.
- Zero unresolved review threads are required before merge. Merge is SQUASH-only
  through the protected ruleset; native auto-merge must remain unarmed.

## Release classification

- `1.0.x` — backward-compatible fixes (bug, security, dependency, documentation,
  bounded operational).
- `1.x.0` — backward-compatible capabilities accepted through normal governance.
- `2.0.0` — breaking public contract changes.

See [docs/VERSIONING.md](docs/VERSIONING.md) and
[docs/MAINTENANCE.md](docs/MAINTENANCE.md).

## Never commit

- Secrets, API keys, credentials, `.env` files or private keys.
- User runtime data, local HIVE state or review bundles.
- Generated local artifacts that are not part of the reviewed increment.
