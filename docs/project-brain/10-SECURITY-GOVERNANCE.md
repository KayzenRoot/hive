# 10 - SECURITY & GOVERNANCE

Principles: least privilege, project isolation, provenance for memory/evidence,
explicit authority boundaries, no trust in executor self-claims, local secrets
never stored in prompt artifacts, and no canonical mutation from unverified
content.

Treat all ingested content as potentially untrusted. Separate user task intent,
project documentation, external retrieved content, tool output, and
executor-generated claims. Document text must not silently override system or
project governance.

Every retrieval, memory, and artifact operation includes project scope.
Cross-project retrieval is denied by default unless explicitly allowed.
Secrets use environment variables or secret stores, are redacted from logs and
telemetry, are never embedded or persisted in memory, and are masked in the
dashboard.

Canonical promotion requires a trusted source, validated evidence, or approved
architectural decision. Executor output is staged/proposed.

Deletion, destructive migrations, credential rotation, and irreversible
external actions require an explicit policy gate. Audit task, executor,
model/provider, tools, files, tests, decisions, promotions, timestamps, and
relevant hashes/commits.
