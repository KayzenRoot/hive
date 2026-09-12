# Context Lock — `<WORK-ORDER-ID>`

## Lock metadata

- ID: `<WORK-ORDER-ID>`
- Status: `LOCKED | STALE | BLOCKED`
- Captured at UTC: `<timestamp>`
- Repository: `<owner/name>`
- Baseline Git SHA: `<40-char SHA>`
- Base branch: `<branch>`
- Executor branch: `<branch>`

## Critical source fingerprints

SHA-256 is computed over the exact repository file bytes.

| Source | SHA-256 |
| --- | --- |
| Source hierarchy | `<hash>` |
| Checkpoint | `<hash>` |
| Decisions ledger | `<hash>` |
| Scope | `<hash>` |
| Definition of Done | `<hash>` |
| Architecture | `<hash>` |
| Requirements | `<hash>` |
| Security/governance | `<hash>` |
| Test plan/deployment | `<hashes>` |
| Agent instructions | `<hash>` |
| Canonical SHA manifest | `<hash>` |

Record absent critical files explicitly as `ABSENT`, never as a guessed
replacement.

## Operational snapshots

- Migration head: `<revision or UNKNOWN>`
- Default branch: `<branch>`
- GitHub Ruleset ID/fingerprint: `<id/hash or UNKNOWN>`
- CI required checks: `<exact names or UNKNOWN>`
- Other critical configuration: `<path/hash or NONE>`

## Staleness protocol

Recompute every fingerprint before final validation and handoff. Any mismatch
sets this lock to `STALE`, invalidates the evidence, and requires a new lock or
explicit owner decision. The executor must not continue silently.
