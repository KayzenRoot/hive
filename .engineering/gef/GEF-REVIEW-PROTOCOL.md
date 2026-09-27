# GEF V1 HEDS Delta Review Protocol — HIVE

## Review pipeline

`ANALYZE DELTA -> SOURCE CHECK -> INVALIDATED PROOFS -> SEMANTIC REVIEW -> GATE RECEIPTS -> EXACT-HEAD VERDICT`

## First candidate

The first candidate of an increment may receive broad review necessary to establish the semantic baseline. Accepted findings, frozen decisions, and proof dependencies are recorded.

## Subsequent candidates

Review delta-first:

- compare the last audited head to the current exact head,
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
- A4 `HEDS Delta` -> the sole owner's semantic/scope/architecture/security self-audit of the exact PR head.

## Single-account identity and verdict

HIVE-ADR-019/020 define `KayzenRoot` as the sole operational GitHub identity. Executor and Sol remain distinct logical stages; they do not require distinct GitHub accounts or reviewer sessions. A4 is an owner self-audit, not an independent review. Record the exact base and head SHAs, changed surface, findings and severity, evidence/check results, unresolved HIGH/CRITICAL count, and the explicit `NOT INDEPENDENT` disclosure in the PR conversation.

The owner self-audit may return `OWNER_SELF_AUDIT_APPROVED` only after every mandatory exact-head gate passes and unresolved HIGH/CRITICAL findings are zero. Otherwise return `CORRECTION REQUIRED` or `BLOCKED_EVIDENCE` with the factual technical gap. Never create a native GitHub `APPROVE` review from the KayzenRoot author account.

The absence of a second identity or reviewer session alone is not a reason for `BLOCKED_EVIDENCE`. Missing/failed checks, missing required evidence, scope/source mismatch, or unresolved HIGH/CRITICAL findings remain fail-closed blockers. Ruleset `21934284`, protected-main requirements, and the approved single-account tradeoff in ADR-019 remain in force.
