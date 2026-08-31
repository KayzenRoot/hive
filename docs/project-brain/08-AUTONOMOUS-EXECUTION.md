# 08 - AUTONOMOUS EXECUTION

Users should not have to manually request RAG, memory, cache, checkpoint, or
token optimization; those are HIVE responsibilities.

Accepted entry points are dashboard upload, task textbox, MCP, CLI, and API.
Initial artifacts are PDF, Markdown, TXT, and structured JSON tasks.

## Pipeline

1. Ingest and preserve the original artifact.
2. Extract and normalize text.
3. Identify project and resolve repository/branch/HEAD.
4. Read checkpoint, scope, DoD, architecture, and relevant decisions.
5. Classify task/risk and calculate context budget.
6. Discover impacted symbols/modules and retrieve code/tests/memory.
7. Apply ACCE, gate tools, and build a context capsule.
8. Dispatch execution, stream runtime events, and capture diffs/tests/validation.
9. Produce executor review and store claims as staged evidence.
10. Promote only verified information according to governance rules.
11. Update telemetry and update checkpoints only through approved workflow.

Stop when acceptance criteria are met and validated, a critical blocker prevents
safe progress, work would expand scope, evidence cannot be produced, or policy
requires a human/architect decision.

Every implementation run reports summary, changed files, decisions, tests,
lint/typecheck/build, fixed errors, pending issues, risks, evidence/diff, and a
proposed checkpoint update. Completed is not evidence. Autonomous does not mean
uncontrolled: retrieval, caching, compression, indexing, tool selection,
approved tests, and telemetry may be autonomous; canonical truth, destructive
actions, and high-risk permissions follow governance policy.
