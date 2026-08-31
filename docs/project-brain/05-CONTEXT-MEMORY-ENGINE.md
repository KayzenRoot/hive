# 05 - CONTEXT & MEMORY ENGINE

## Goal

Build the smallest context that preserves the information required for correct
work.

## Memory classes

Working, session, project, semantic, episodic, decision, failure, and
procedural memory.

## Memory lifecycle

A memory record has id, project, type, status, content, source, source
version/commit, created/updated time, confidence, importance, authority, tags,
and supersedes/superseded-by references. Recommended statuses are OBSERVATION,
INFERRED, PROPOSED, CONFIRMED, CANONICAL, and DEPRECATED. Model output must not
automatically become CANONICAL.

## Context construction pipeline

Resolve project; read latest checkpoint; parse task intent; determine risk;
resolve likely modules/symbols; query lexical and semantic indexes plus
decision/failure memory; merge and deduplicate; rerank; apply progressive
disclosure and token budget; build the context capsule; attach a provenance
manifest; send it to the executor.

## Progressive disclosure

L0 project capsule, L1 module summaries, L2 symbol signatures/dependency
metadata, L3 relevant implementation excerpts, L4 complete file, L5
repository-wide investigation. Escalate only when lower levels are insufficient.

## Context capsule

The capsule contains task, project state, constraints, acceptance criteria,
relevant architecture and decisions, symbols/files, tests, known failures,
allowed tools, token/risk mode, and provenance map.

Track context signal ratio as useful context tokens divided by total context
tokens sent. Consolidation may merge duplicates and deprecate superseded facts,
but must preserve provenance and canonical source evidence.
