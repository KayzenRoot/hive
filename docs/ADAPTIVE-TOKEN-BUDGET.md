# Adaptive Token Budget Foundation

This document records the implementation contract for WO-011. It is
non-canonical implementation documentation; the approved checkpoint and
Project Brain remain authoritative.

## Position in the pipeline

The foundation runs after Progressive Disclosure has selected and materialized
the requested L0-L5 payload and before the context capsule is serialized. The
order is fixed:

`project → checkpoint → task → retrieval → rerank → Progressive Disclosure → Adaptive Token Budget → capsule`

It does not call an LLM, a model provider, or a network service.

## Deterministic policy

The estimator is `utf8-byte-ceiling-v1`: UTF-8 byte length divided by four,
rounded up. This is an internal planning estimate, not provider billing.

The policy is `adaptive-token-budget-v1` with base budget 4096 tokens, hard
minimum 2048, and hard maximum 6144. The effective budget is derived from the
resolved disclosure level and bounded repository/task signals: resolved files,
symbols, tests, retrieval results, constraints, acceptance criteria, and L4/L5
requirements. No user budget mode or provider-specific `max_tokens` is needed.

Required context is reserved first. Optional governance excerpts and lower
priority retrieval results are considered in stable order and removed from the
tail only when necessary. Required governance, task identity, constraints,
acceptance criteria, disclosure payload, L4 complete files, provenance, and
rerank order are preserved. If required context exceeds the hard maximum, the
request fails closed.

Each successful capsule carries versioned machine-readable budget evidence:
base/effective/hard boundaries, before/after/avoided estimates, deterministic
reasons, removed optional identities, preservation/satisfaction flags, and
zero LLM/provider call counters.
