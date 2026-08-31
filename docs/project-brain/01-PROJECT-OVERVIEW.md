# 01 — PROJECT OVERVIEW

## Project

**HIVE — Local AI Context & Project Intelligence Platform**

## Objective

Build a local-first platform that allows large software projects to be developed with LLMs over long periods without repeatedly loading entire repositories or long chat histories.

HIVE must preserve project continuity, minimize token consumption, maintain objective execution state, provide high-quality context to LLMs, and expose live operational telemetry through a complete dashboard.

## Core outcome

A user should be able to submit a task or prompt — commonly a PDF — and HIVE should autonomously:

1. identify the target project;
2. resolve repository, branch and current commit;
3. load checkpoint, scope, Definition of Done, architecture and relevant decisions;
4. determine task risk and context budget;
5. retrieve only the relevant code, memory, documentation and tests;
6. exploit cache, deduplication, compression and incremental indexing;
7. expose only relevant tools;
8. send a compact, high-signal context capsule to the executor LLM;
9. observe execution, tool calls, token usage, tests and diffs;
10. capture results as staged evidence;
11. require validation before promoting claims into canonical project state;
12. display all relevant state in the HIVE Control Center in near real time.

## Principles

- Local-first.
- Docker-first.
- Persistent data on user-controlled storage.
- Model-provider independent.
- MCP as universal agent interface.
- Canonical truth must be evidence-based.
- Redis is hot cache, not canonical truth.
- PostgreSQL is the structured durable store.
- Source repositories and Git remain canonical for source code.
- Deterministic tools before LLM reasoning.
- Progressive disclosure before large-context loading.
- Optimize tokens without measurable quality loss.
- No infinite scope expansion.
- Every version must be finishable.

## Intended users

Initially: one technical operator managing multiple large software projects with coding LLMs.

Future multi-user and distributed operation are backlog items unless explicitly promoted.

## V0.1 product statement

HIVE V0.1 is complete only when one local installation can manage multiple projects, ingest tasks, construct context autonomously, cache and retrieve project knowledge, track live execution telemetry, persist durable project state, and expose the result in a functional dashboard.
