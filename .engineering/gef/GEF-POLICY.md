# GEF V1 Local Policy — HIVE

## Authority

This policy applies only where it is compatible with current HIVE canonical sources. A conflict produces `SOURCE_CONFLICT`; canonical HIVE truth wins.

## Global rules

- Think once, compile once, execute narrowly, prove incrementally, review only what changed.
- Deterministic tools before LLM calls.
- Begin with the smallest safe context radius and expand only for a real dependency, source drift, or source conflict.
- Executor claims are staged until tests/evidence validate them.
- Exact-head proof is mandatory for governed candidate approval.
- UNKNOWN remains UNKNOWN. It never becomes ALLOW, PASS, HIT, zero, exact usage, or exact cost.
- PostgreSQL remains canonical durable structured state; Redis remains noncanonical HOT state.
- Git remains canonical source-code history.
- No GEF cache, summary, receipt or derived artifact replaces canonical source.

## HIVE overrides / preserved governance

- Source hierarchy remains checkpoint > decisions > scope > DoD > architecture > requirements > remaining sources.
- ADR-019 remains authoritative for GitHub stage-gated governance.
- Required hosted checks remain `Validate`, `Integration health`, `Review Evidence` unless a future approved decision changes them.
- Ruleset `21934284` must not be weakened by GEF adoption.
- Native approving review count may remain 0; HEDS semantic assurance is a logical quality gate, not a GitHub-native approval requirement.
- Existing UADS fail-closed assurance/finalize rules are preserved.

## Task classes

- `T0`: mechanical change with no architectural exploration.
- `T1`: bounded patch with prescribed recipe and minimal search.
- `T2`: semantic correction within frozen architecture.
- `T3`: architecture work with explicitly governed broad analysis.

## Context radius

- `C0`: target symbol/function + direct test.
- `C1`: target symbols + direct dependencies + tests.
- `C2`: module + interfaces.
- `C3`: related architecture + cross-module contracts.
- `C4`: broad project architecture.

## Default budgets

Budgets are guardrails, not permission to truncate correctness.

- T0/T1 expected patch: 1-3 source files and 1-3 test files when compatible with the task.
- Search budget must be explicit in each pack; repeated identical search/command without causal change is forbidden.
- Retry budget defaults to 2 causal retries unless the pack states otherwise.
- Token/output discipline: compact machine output; no repeated project history.
- Any material budget expansion must be reported with the dependency/source reason.

## Forbidden shortcuts

- `UNKNOWN -> ALLOW`
- fabricating test/gate/proof/reviewer/receipt data
- using old-head evidence as exact-head proof
- silently increasing scope
- full-repository search by default
- asking the executor to rediscover frozen architecture
- duplicate full local + hosted validation without diagnosis or explicit requirement
- evidence-only commit after exact-head receipts
- merge before required review/gates
- deleting existing governance to simplify GEF
- treating optimization targets as measured gains
- proof carry-forward without input validity
- weakening reviewer independence because host session capacity is unavailable
