# UADS GEF V1 Adoption — HIVE

## Adoption status

- Project: `KayzenRoot/hive`
- Mode: `EXISTING_PROJECT`
- GEF version: `1.0`
- Baseline head: `c9430af13860ab30e31bd162991eb88c05215f4f`
- Default branch: `main`
- Project fingerprint: `ee11fdd1ec7677d4aa69261a0f0abbe43efb8cadba33f4929db1aa4427558a36`
- Adoption branch: `governance/gef-v1-adoption-001`
- Adoption PR: `#81` (draft, unmerged)
- Adoption issue: `#80`
- Current prompt mode after adoption: `GEF_V1`
- Current review mode after adoption: `HEDS_DELTA`
- Shadow assurance: `ON`
- Adoption stop state: `READY_WITH_GAPS`

> Historical adoption snapshot at baseline `c9430af`: the reviewer-session gap
> and adoption bridge listed below were later resolved by HIVE-ADR-020 / WO-033.
> Current HEDS A4 is a KayzenRoot owner self-audit, explicitly `NOT INDEPENDENT`.
> No second account or reviewer session is required. This snapshot does not block
> current Work Orders; protected-main, exact-head CI/evidence and severity gates
> remain mandatory.

GEF is adopted as an engineering/governance layer. It does not replace HIVE canonical product truth, ADRs, checkpoint, Definition of Done, architecture, Review Evidence, GitHub ruleset, UADS fail-closed behavior, or exact-head CI.

## Source hierarchy

HIVE keeps its canonical hierarchy unchanged:

1. `docs/project-brain/13-CHECKPOINT.md`
2. `docs/project-brain/16-DECISIONS-LEDGER.md`
3. `docs/project-brain/03-SCOPE.md`
4. `docs/project-brain/15-DEFINITION-OF-DONE.md`
5. `docs/project-brain/04-ARCHITECTURE.md`
6. `docs/project-brain/02-REQUIREMENTS.md`
7. remaining Project Brain sources

GEF artifacts are derived engineering policy/state. They never override a newer canonical HIVE decision.

## Baseline inventory

- Repository id: `1352430022`
- Default branch: `main`
- Protected-main baseline: `c9430af13860ab30e31bd162991eb88c05215f4f`
- Required checks: `Validate`, `Integration health`, `Review Evidence`
- Merge policy: squash-only through ruleset `21934284`, zero bypass actors, thread resolution required
- Backend: Python 3.12, Ruff, strict mypy, pytest
- Dashboard: React 19, TypeScript 5.7, Vite 6, Vitest, ESLint
- Packaging/runtime: Docker Compose, PostgreSQL + pgvector, Redis-compatible HOT cache
- Deterministic validation entry point: `python scripts/validate.py`
- Hosted CI: `.github/workflows/ci.yml`
- Active legacy governance PR observed and intentionally untouched: `#37 chore: adopt governed engineering delivery protocol`
- Active Control Center metrics planning/work observed and intentionally untouched: issue `#79`, branch `feat/wo021-control-center-metrics`
- Most recent merged governance work: PR `#78`, merge commit `c9430af13860ab30e31bd162991eb88c05215f4f`
- Adoption PR `#81` exists as draft so it cannot be mistaken for merge-ready work.

## Adoption Gap Matrix

| Current | Target | Migration action | Risk | Owner/status |
|---|---|---|---|---|
| Large executor prompts can repeat repository history | Compiled Execution/Correction Packs | Use GEF prompt compiler structure immediately | LOW | ACTIVE |
| Review rereads broad history | HEDS delta-first review | Use exact-head delta + invalidated proofs | LOW | ACTIVE |
| Proof reuse is informal | Evidence Validity Fingerprint + carry-forward graph | Start in shadow mode, compare against full CI | MEDIUM | SHADOW |
| Machine evidence exists in multiple current artifacts | GEF Machine Evidence Manifest | Map current validation/review evidence into one derived manifest | LOW | READY |
| Test impact knowledge is implicit | Source/module -> tests/evals map | Seed conservative mapping; refine from observed runs | LOW | READY |
| Token/search/time telemetry incomplete | Baseline + per-WO GEF telemetry | Record UNKNOWN when unavailable; never coerce to zero | LOW | READY |
| UADS host could not allocate distinct reviewer sessions at adoption baseline | Legitimate A4 assurance | Superseded by HIVE-ADR-020 / WO-033: exact-head KayzenRoot owner self-audit, disclosed `NOT INDEPENDENT` | HIGH | CLOSED BY WO-033 |
| Review Evidence did not recognize the adoption bridge at baseline | Governed registration of the corrective work order | WO-033 is registered and covered by exact-marker / deny-by-default regression tests; no technical gate is weakened | MEDIUM | CLOSED BY WO-033 |
| Open PR #37 is based on old main and overlaps `.engineering` concepts | Preserve concurrent work | Do not modify/rebase/close it during GEF adoption; reconcile later explicitly | MEDIUM | OPEN GAP |
| PR #81 CI run `34699511231` failed before any Validate steps were exposed | Legitimate hosted A3 evidence | Treat as infrastructure/runner cause UNKNOWN until diagnosed; do not bypass or call it a product failure | MEDIUM | OPEN GAP |

## Compatibility decisions

- GEF task classes and context radii are engineering metadata, not product architecture.
- GEF A0-A2 does not remove current validation. Test/proof skipping has no authority until shadow assurance demonstrates no loss.
- GEF A3 maps to existing hosted required checks and their artifacts.
- GEF A4 maps to a KayzenRoot exact-head owner self-audit after executor handoff. The record must state `NOT INDEPENDENT`; a second GitHub identity or reviewer session is not required.
- Technical UADS, exact-head CI, Review Evidence, protected-main and unresolved HIGH/CRITICAL gates remain fail-closed. Missing another identity alone is not a technical failure and never becomes approval evidence.
- No CI workflow, branch ruleset, product runtime, migration, dependency, checkpoint or canonical Project Brain file is changed by this adoption.

## Adoption report

```text
GEF ADOPTION RESULT
project: KayzenRoot/hive
mode: EXISTING_PROJECT
projectFingerprint: ee11fdd1ec7677d4aa69261a0f0abbe43efb8cadba33f4929db1aa4427558a36
baselineHead: c9430af13860ab30e31bd162991eb88c05215f4f
adoptionBranch: governance/gef-v1-adoption-001
pr: #81 (draft, unmerged)
filesCreated: GEF adoption/policy/execution/review/evidence/profile/current/baseline/proof-map/test-impact artifacts
filesAdapted: none in canonical product/governance sources
currentPromptMode: GEF_V1
currentReviewMode: HEDS_DELTA
shadowAssurance: ON
existingGates: Validate, Integration health, Review Evidence
historicalGapsAtBaseline: UADS reviewer-session capacity (superseded by HIVE-ADR-020 / WO-033 owner self-audit); Review Evidence adoption bridge (closed by registered WO-033); legacy PR #37 overlap; PR #81 hosted Validate runner/start failure with no exposed steps
currentReviewPolicy: HEDS A4 exact-head KayzenRoot owner self-audit; NOT INDEPENDENT; no second identity/session required
risks: exact required checks, thread resolution, protected-main and unresolved HIGH/CRITICAL gates remain fail-closed; no test-skipping authority
nextAction: use the current canonical checkpoint and active Work Order. If PR #81 is reactivated, diagnose its exact-head hosted Validate failure under current gates; do not reinstate a second-account/session-capacity requirement.
statusAtBaseline: READY_WITH_GAPS (historical); reviewer-session gap superseded by HIVE-ADR-020 / WO-033
```

## Next action

Use the current canonical checkpoint, active Work Order, and HIVE-ADR-019/020 for new prompts and reviews. The former UADS reviewer-session gap is closed for governance purposes by the transparent single-account owner self-audit; do not wait for or request another account. Keep all required technical checks, exact-head evidence, protected-main rules, thread resolution, scope validation, and severity gates. Review legacy adoption PR #81 only if it is explicitly reactivated, and diagnose its recorded hosted-runner failure on its exact current head before any merge.
