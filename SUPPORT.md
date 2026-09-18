# Support

HIVE v1.0.x is the supported stable line. Historical pre-releases are not
supported. This is a local-first, self-hosted project: support covers the
documented Docker Compose deployment, not custom environments or modified
stacks.

## Before opening a request

1. Read [docs/INSTALLATION.md](docs/INSTALLATION.md),
   [docs/UPGRADING.md](docs/UPGRADING.md) and
   [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).
2. Run `docker compose ps` and `curl --fail http://localhost:8000/api/v1/health`.
3. Capture bounded service logs (`docker compose logs api postgres redis dashboard`)
   with secrets removed.

## Where to go

- **Usage questions** — open a discussion or issue using the question route,
  including the exact release version and your platform.
- **Bugs** — use the bug report form: version, OS, Docker/Compose version,
  minimal reproduction, expected vs actual behavior, redacted logs and whether
  the issue is a regression.
- **Feature or improvement requests** — use the feature request form: problem,
  proposed outcome, scope classification and acceptance evidence.
- **Security concerns** — do not open a public issue; follow
  [SECURITY.md](SECURITY.md) and report privately.

## Required reproduction evidence

Requests without a reproducible description of the deployment (release tag or
commit, configuration deltas, exact commands, observed output) cannot be
triaged. Never include secrets, `.env` contents or user runtime data.
