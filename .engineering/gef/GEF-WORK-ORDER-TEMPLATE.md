# GEF Work Order Template

> Use for substantial implementation, correction, migration, adoption or release-critical validation. Reuse an existing HIVE Work Order when it already provides an equivalent or stronger contract.

## WORK ORDER

- ID: `<STABLE-ID>`
- Title: `<title>`
- Project: `HIVE`
- Repository: `KayzenRoot/hive`
- State: `PLANNED | ACTIVE | READY_FOR_AUDIT | CORRECTION_REQUIRED | APPROVED | BLOCKED | COMPLETE`
- Risk: `LOW | MEDIUM | HIGH | CRITICAL`

## OBJECTIVE

State the smallest necessary outcome that advances the canonical checkpoint/DoD.

## CONTEXT

Explain why the increment exists, the current accepted state, and the specific gap being closed. Do not restate the whole repository.

## SOURCE CHECK

Read/resolve before mutation:

1. latest canonical checkpoint;
2. decisions/ADRs;
3. scope;
4. Definition of Done / acceptance criteria;
5. architecture;
6. security/policy;
7. this Work Order and Context Lock;
8. only then supporting documentation/code needed for the increment.

Record material contradictions instead of silently choosing one.

## CONTEXT LOCK

- Authorized base SHA: `<sha>`
- Expected branch: `<branch>`
- Project identity: `<id/name>`
- Task/increment identity: `<id>`
- Canonical source fingerprint: `<digest or references>`
- Stale-head action: `FAIL_CLOSED`

Attach/refer to a machine-readable Context Lock when useful.

## IN SCOPE

- `<necessary behavior/file family>`

## OUT OF SCOPE

- `<explicit exclusions>`
- unrelated refactors/cleanup;
- speculative FUTURE features;
- canonical source mutation unless explicitly authorized.

## ALLOWED / PRESERVED AREAS

### Allowed

- `<path/prefix>`

### Preserve

- `<path/prefix and reason>`

## REQUIREMENTS

- `<requirement and source>`

## ARCHITECTURE RULES

- Preserve approved architecture and existing project-native seams.
- Prefer additive/reuse-compatible changes over parallel subsystems.
- Deterministic tools before LLM/provider calls where possible.

## SECURITY CONSTRAINTS

- No secret exposure.
- Fail closed on identity/authority/path violations.
- Preserve least privilege and project isolation.
- HIGH/CRITICAL unresolved release blockers prohibit approval.

## EXECUTOR ACCELERATION PACK

### Implementation Seed Tree

`<smallest relevant file/module tree>`

### File Intent Capsule

| Path | Why it matters | Intended change |
|---|---|---|
| `<path>` | `<reason>` | `<intent>` |

### Brownfield Patch Intent Capsule

State preservation-sensitive boundaries and legacy behavior that must not change.

### Executor Navigation Map

1. `<first file/source>`
2. `<second file/source>`
3. `<test/evidence seam>`

### Decision Closure Capsule

List already-resolved choices that must not be re-debated.

### Execution Waves

- Wave 1: `<dependency-safe work>`
- Wave 2: `<dependent work>`

### Validation Reuse Plan

State which accepted evidence remains valid and which checks must rerun because this increment invalidates them.

### Critical Path

`<minimum blocking sequence>`

## ACCEPTANCE CRITERIA

- [ ] exact scope satisfied;
- [ ] no preservation violation;
- [ ] required deterministic checks pass;
- [ ] evidence binds exact candidate HEAD;
- [ ] CRITICAL=0 and HIGH=0;
- [ ] no unresolved evidence mismatch;
- [ ] no stale-head mismatch.

## TESTS

Discover and use real repository commands. Apply the assurance ladder proportionate to risk:

1. structural/static;
2. focused/direct;
3. impacted dependency;
4. boundary/integration;
5. risk-expansion;
6. full candidate assurance for release-critical work.

Do not invent commands or hide failed checks.

## EVIDENCE

Bind evidence to:

- Work Order ID;
- exact base and candidate HEAD;
- commands/workflows and run IDs;
- results and artifacts;
- failures/corrections;
- security findings;
- unresolved risks;
- changed-file inventory.

`UNKNOWN` is not `PASS`.

## REVIEW REQUIREMENTS

Final executor review in Brazilian Portuguese must include:

- summary;
- exact base/head/branch/PR;
- files created/changed;
- decisions;
- tests/results;
- lint/typecheck/build where applicable;
- errors fixed;
- pending risks;
- evidence/diff;
- proposed checkpoint delta;
- CRITICAL/HIGH counts;
- final stop marker.

## ROLLBACK / RECOVERY

Describe how to restore the pre-increment state or safely abandon staged output without mutating canonical truth.

## DELIVERABLES

- `<code/docs/evidence/PR>`

## STOP CONDITION

Stop normally only when the Work Order's acceptance criteria and required exact-head evidence are satisfied and the candidate is ready for independent audit. Fixable in-scope failures are `CORRECTION_REQUIRED`, not `BLOCKED`.

Use `BLOCKED` only for a concrete external/canonical/capability blocker that prevents safe continuation.
