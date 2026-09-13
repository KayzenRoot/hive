# GEF V1 HEDS Delta Review Protocol — HIVE

## Review pipeline

`ANALYZE DELTA -> SOURCE CHECK -> INVALIDATED PROOFS -> SEMANTIC REVIEW -> GATE RECEIPTS -> EXACT-HEAD VERDICT`

## First candidate

The first candidate of an increment may receive broad review necessary to establish the semantic baseline. Accepted findings, frozen decisions and proof dependencies are recorded.

## Subsequent candidates

Review delta-first:

- compare last reviewed head to current exact head,
- identify changed files/symbols and material toolchain/policy changes,
- carry forward only proofs whose relevant inputs and Evidence Validity Fingerprint remain compatible,
- invalidate proofs whose relevant inputs changed,
- do not reopen accepted findings without a new invalidating delta.

## Evidence Validity Fingerprint

A proof fingerprint may include, when material:

- source/blob hashes or target symbol hashes,
- test/eval implementation hash,
- config/toolchain versions,
- policy/schema version,
- OS/platform when the proof is platform-sensitive,
- canonical source/checkpoint/ADR identity,
- provider/runtime identity for provider-specific evidence.

A matching test name is never sufficient by itself.

## Exact-head rule

- HEDS may begin while CI is running.
- Final verdict waits for all mandatory exact-head gates.
- Old-head CI/evidence is historical only.
- Gate receipts belong outside source head when possible: GitHub check/artifact/comment or equivalent.
- Do not create an evidence-only source commit after gates merely to record run IDs.

## HIVE hosted gate mapping

- A3 `Validate` -> deterministic validation, unit/static/build/package/compose checks.
- A3 `Integration health` -> Docker-backed integration/recovery/system proofs.
- A3 `Review Evidence` -> machine manifest/sticky exact-head governance evidence.
- A4 `HEDS Delta` -> independent semantic/scope/architecture/security review.

Ruleset `21934284` and ADR-019 remain authoritative. Native GitHub Approve is not the semantic quality gate.

## Current assurance gap

The active GLOBAL UADS host currently lacks a supported way to allocate the distinct reviewer sessions required by the most recent recovery. Until resolved, GEF must report `BLOCKED_EVIDENCE`; it must not reinterpret the missing independent/security reviewer as PASS. This gap does not authorize weakening UADS or HIVE governance.
