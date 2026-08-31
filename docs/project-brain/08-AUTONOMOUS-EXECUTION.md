# 08 — AUTONOMOUS EXECUTION

## Objective

The user should not need to manually instruct the executor to use RAG, memory, cache, checkpoint or token optimization.

Those are HIVE responsibilities.

## Intake flow

Accepted entry points:
- dashboard upload;
- task textbox;
- MCP;
- CLI;
- API.

Accepted initial artifact types:
- PDF;
- Markdown;
- TXT;
- structured JSON task.

## Autonomous pipeline

1. Ingest prompt artifact.
2. Preserve original artifact.
3. Extract/normalize text.
4. Identify project.
5. Resolve repository/branch/HEAD.
6. Read checkpoint.
7. Read scope and Definition of Done.
8. Retrieve relevant architecture/decisions.
9. Classify task and risk.
10. Calculate context budget.
11. Discover impacted symbols/modules.
12. Retrieve memory/code/tests.
13. Apply ACCE.
14. Gate tools.
15. Build executor context capsule.
16. Dispatch execution.
17. Stream runtime events.
18. Capture diffs, files, tests and validation.
19. Produce executor review.
20. Store claims as staged evidence.
21. Promote only verified information according to governance rules.
22. Update telemetry.
23. Update checkpoint only through approved workflow.

## Stop conditions

The executor must stop when:
- acceptance criteria are met and validated;
- a critical blocker prevents safe progress;
- work would require scope expansion;
- required evidence cannot be produced;
- policy requires human/architect decision.

## Executor review contract

Every implementation run must report:
- summary;
- files created/changed;
- relevant decisions;
- tests and results;
- lint/typecheck/build as applicable;
- errors fixed;
- pending issues;
- risks;
- evidence/diff;
- proposed checkpoint update.

"Completed" is not evidence.

## Autonomous does not mean uncontrolled

HIVE may autonomously:
- retrieve;
- cache;
- compress;
- index;
- select tools;
- classify context;
- run approved tests;
- collect telemetry.

Canonical truth, destructive actions and high-risk permissions must follow governance policy.
