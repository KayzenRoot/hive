# 01 - PROJECT OVERVIEW

## Project

HIVE - Local AI Context & Project Intelligence Platform.

## Objective

Build a local-first platform that allows large software projects to be developed
with LLMs over long periods without repeatedly loading entire repositories or
long chat histories. HIVE preserves project continuity, minimizes token
consumption, maintains objective execution state, provides high-quality context
to LLMs, and exposes live operational telemetry through a complete dashboard.

## Core outcome

A user submits a task or prompt, commonly a PDF, and HIVE autonomously identifies
the project, resolves repository/branch/commit, loads checkpoint/scope/DoD/
architecture/decisions, determines risk and context budget, retrieves relevant
code/memory/docs/tests, uses cache/deduplication/compression/incremental indexing,
gates tools, sends a compact context capsule to the executor, observes execution,
captures staged evidence, validates claims before canonical promotion, and
displays relevant state in the Control Center.

## Principles

- Local-first and Docker-first.
- Persistent data on user-controlled storage.
- Model-provider independent.
- MCP as universal agent interface.
- Canonical truth is evidence-based.
- Redis is hot cache, not canonical truth.
- PostgreSQL is the structured durable store.
- Git remains canonical for source code and history.
- Deterministic tools before LLM reasoning.
- Progressive disclosure before large-context loading.
- Optimize tokens without measurable quality loss.
- No infinite scope expansion; every version must be finishable.

## Intended users

Initially, one technical operator managing multiple large software projects with
coding LLMs. Multi-user and distributed operation are backlog items unless
explicitly promoted.

## V0.1 product statement

One local installation must manage multiple projects, ingest tasks, construct
context autonomously, cache and retrieve project knowledge, track live execution
telemetry, persist durable project state, and expose the result in a functional
dashboard.
