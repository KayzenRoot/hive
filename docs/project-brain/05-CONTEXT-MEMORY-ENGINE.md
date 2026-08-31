# 05 — CONTEXT & MEMORY ENGINE

## Goal

Build the smallest context that preserves the information required for correct work.

## Memory classes

### Working
Current task state.

### Session
Current interaction/run context.

### Project
Durable project facts and operating state.

### Semantic
Stable knowledge, architecture and domain facts.

### Episodic
What happened during prior runs.

### Decision
Approved architectural/product decisions.

### Failure
Prior errors, causes and verified fixes.

### Procedural
How approved workflows are executed.

## Memory lifecycle

A memory record has:
- id;
- project;
- type;
- status;
- content;
- source;
- source version/commit;
- created time;
- updated time;
- confidence;
- importance;
- authority;
- tags;
- supersedes/superseded-by references.

Recommended statuses:
- OBSERVATION
- INFERRED
- PROPOSED
- CONFIRMED
- CANONICAL
- DEPRECATED

Model output must not automatically become CANONICAL.

## Context construction pipeline

1. Resolve project.
2. Read latest checkpoint.
3. Parse task intent.
4. Determine risk.
5. Resolve likely modules/symbols.
6. Query lexical index.
7. Query semantic index.
8. Query decision/failure memory.
9. Merge and deduplicate candidates.
10. Rerank.
11. Apply progressive disclosure.
12. Apply token budget.
13. Build context capsule.
14. Attach provenance manifest.
15. Send to executor.

## Progressive disclosure levels

- L0: Project capsule.
- L1: Module summaries.
- L2: Symbol signatures and dependency metadata.
- L3: Relevant implementation excerpts.
- L4: Complete file.
- L5: Repository-wide investigation.

Escalate only when lower levels are insufficient.

## Context capsule

Must contain only relevant elements:
- task;
- current project state;
- constraints;
- acceptance criteria;
- relevant architecture;
- relevant decisions;
- relevant symbols/files;
- relevant tests;
- known failures;
- allowed tools;
- token/risk mode;
- provenance map.

## Context signal ratio

Track:

`useful_context_tokens / total_context_tokens_sent`

It is an optimization metric, not a substitute for quality validation.

## Memory consolidation

Periodically:
- detect duplicate or semantically equivalent records;
- merge references;
- preserve provenance;
- deprecate superseded facts;
- never silently destroy canonical source evidence.
