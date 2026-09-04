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

The estimator is `utf8-byte-ratio-approx-v1`: UTF-8 byte length divided by
four, rounded up. This is a deterministic approximation, not a provider-exact
count and not a guaranteed provider-token upper bound. It does not claim a
safety ceiling. The existing 24k character bound remains a separate safety
layer.

The measured serialization contract is `context-payload-v1`: canonical JSON
with UTF-8 output, sorted keys, compact separators and no ASCII escaping. It
includes the project envelope, task contract, governance, retrieval query and
metadata, results, projections, and all materialized Progressive Disclosure
payload. It excludes only `adaptive_token_budget` evidence (to avoid
self-reference) and `bounds` accounting (transport/audit metadata). Therefore
`estimated_tokens_after` is the estimate of this exact context payload, not of
the complete HTTP response.

The policy is `adaptive-token-budget-v1` with base budget 4096 tokens, hard
minimum 2048, and hard maximum 6144. The effective budget is derived from the
resolved disclosure level and bounded repository/task signals: resolved files,
symbols, tests, retrieval results, constraints, acceptance criteria, and L4/L5
requirements. No user budget mode or provider-specific `max_tokens` is needed.

Required context is reserved first. Optional governance excerpts and lower
priority retrieval results are considered in stable order and removed from the
tail only when necessary. Required governance, task identity, constraints,
acceptance criteria, disclosure payload, L4 complete files, provenance, and
rerank order are preserved. The context-manager path adds a fixed 256-token
serialization allowance to the effective budget and reserves 1024 tokens while
the fragment planner selects optional items; these are deterministic structural
allowances, not provider-token claims. If required context exceeds the hard
maximum, the request fails closed.

Each successful capsule carries versioned machine-readable budget evidence:
base/effective/hard boundaries, same-serialization baseline/final/avoided
estimates, final-estimate verification flags, deterministic reasons, removed
optional identities, preservation/satisfaction flags, and zero LLM/provider
call counters. The final payload is measured after materialization; if it does
not fit the effective budget, the request fails closed without reducing
Progressive Disclosure or truncating an L4 file.
