# 10 — SECURITY & GOVERNANCE

## Principles

- Least privilege.
- Project isolation.
- Provenance for memory and evidence.
- Explicit authority boundaries.
- No trust in executor self-claims.
- Local secrets never stored in prompt artifacts.
- No canonical mutation from unverified content.

## Prompt and document ingestion

Treat all ingested content as potentially untrusted.

Separate:
- user task intent;
- project documentation;
- external retrieved content;
- tool output;
- executor-generated claims.

Do not allow document text to silently override system/project governance.

## Project boundaries

Every retrieval, memory and artifact operation must include project scope.

Cross-project retrieval is denied by default unless explicitly allowed.

## Secrets

- Use environment variables/secrets stores.
- Redact secrets from logs and telemetry.
- Do not embed secrets.
- Do not persist raw API keys in memory records.
- Dashboard must mask sensitive values.

## Canonical promotion

Promotion to canonical memory requires:
- trusted source OR
- validated evidence OR
- approved architectural decision.

Executor output alone is staged/proposed.

## Destructive actions

Deletion, destructive migrations, credential rotation or irreversible external actions require an explicit policy gate.

## Audit

Record:
- task;
- executor;
- model/provider;
- tools;
- files affected;
- tests;
- important decisions;
- memory promotions;
- timestamps;
- relevant hashes/commits.
