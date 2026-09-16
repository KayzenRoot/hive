# GEF Project Master — HIVE

This document is a thin operational map. It does not duplicate or supersede HIVE Project Brain.

## Project identity

- Name: HIVE
- Repository: `KayzenRoot/hive`
- Classification: `BROWNFIELD`
- GEF baseline: `1.0.0 Universal Adoption`
- Canonical product version at adoption: `HIVE V0.1 — Foundation`
- Canonical phase at adoption: `5 — Implementation`
- Default branch: `main`
- Discovery baseline: `4fb0aa111bd5b0f526df85b1897618d8eca1c0e0`

## Purpose

HIVE is a local-first governed context, memory and execution platform for software projects. The canonical objective, scope and product claims live in Project Brain, not in this GEF map.

## Canonical source map

| Concern | Authoritative source |
|---|---|
| Current accepted state | `docs/project-brain/13-CHECKPOINT.md` |
| Approved decisions | `docs/project-brain/16-DECISIONS-LEDGER.md` |
| Scope | `docs/project-brain/03-SCOPE.md` |
| Definition of Done | `docs/project-brain/15-DEFINITION-OF-DONE.md` |
| Architecture | `docs/project-brain/04-ARCHITECTURE.md` |
| Security/governance | `docs/project-brain/10-SECURITY-GOVERNANCE.md` |
| Requirements | `docs/project-brain/02-REQUIREMENTS.md` |
| Test plan | `docs/project-brain/11-TEST-PLAN.md` |
| Local deployment/recovery | `docs/project-brain/12-LOCAL-DEPLOYMENT.md` |
| Autonomous execution | `docs/project-brain/08-AUTONOMOUS-EXECUTION.md` |
| GEF execution model | `.engineering/gef/GEF-EXECUTION-PROTOCOL.md` |
| GEF review model | `.engineering/gef/GEF-REVIEW-PROTOCOL.md` |
| GEF current state | `.engineering/gef/GEF-CURRENT.json` |

## Technology summary

- Backend: Python 3.12, typed application services, pytest, Ruff, strict mypy.
- Dashboard: React, TypeScript, Vite, Vitest, ESLint.
- Runtime: Docker Compose.
- Durable structured state: PostgreSQL with pgvector.
- HOT noncanonical cache: Redis-compatible service.
- Canonical blob/content layer: local CAS.
- Source history: Git.
- CI: GitHub Actions with `Validate`, `Integration health`, `Review Evidence`.

## Architecture summary

Preserve local-first architecture, PostgreSQL as canonical structured storage, Redis only as HOT cache, Git as source history, content-addressable storage, incremental/Git-aware indexing, context/retrieval/memory provenance, deterministic tooling before LLM use, staged executor output and exact-head governed promotion. Consult `04-ARCHITECTURE.md` for the actual contract.

## Current accepted state

The accepted product state is whatever the latest canonical checkpoint says. At Universal Adoption discovery, main is `4fb0aa111bd5b0f526df85b1897618d8eca1c0e0`; WO-024 product closure remains active in PR #95 and has not been canonically promoted.

## Historical vs GEF-governed periods

### Pre-GEF historical project state

HIVE existed with substantial product code, architecture, CI, tests and governance before GEF. That history must never be relabelled as having been executed under GEF merely because equivalent evidence exists today.

### Prior GEF baseline

Historical GEF adoption PR #81 was merged as `2ccbf09c193ba30e78d768bb32a4e78a4f209812`. Its artifacts remain valid history but some current-state metadata became stale as HIVE advanced.

### Universal GEF reconciliation

`GEF-UNIVERSAL-ADOPTION-002` reconciles HIVE with the Universal Adoption model, adds discovery/preservation/project-master/checkpoint/Work Order/Context Lock artifacts, and updates prompt/review protocols. It must remain behavior-neutral.

## Active increment

- Product Work Order: `WO-024`
- PR: `#95`
- Authorized base: `4fb0aa111bd5b0f526df85b1897618d8eca1c0e0`
- Preservation rule: this GEF adoption must not move canonical main before WO-024 reaches a governed terminal state.

## Next legal increment

The next legal product action is to finish the active WO-024 correction/validation lifecycle. The next legal GEF action is to refresh and exact-head validate `GEF-UNIVERSAL-ADOPTION-002` after that active exact-base dependency is resolved.

## Constraints

- HIVE canonical Project Brain always wins over derived GEF state.
- No GEF adoption step may rewrite project history.
- No GEF optimization may silently weaken tests or required checks.
- No merge may invalidate an active exact-base Work Order without explicit canonical authorization.
- UNKNOWN is not PASS.
- Hash integrity is not signing.
- CRITICAL/HIGH unresolved release blockers prevent approval.

## GEF adoption status

`STAGED_UNIVERSAL_RECONCILIATION` on `governance/gef-v1-universal-adoption-002`.

Canonical project adoption is not complete until exact-head evidence, merge and post-adoption checkpoint are accepted.
