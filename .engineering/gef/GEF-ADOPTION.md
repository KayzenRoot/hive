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
| UADS host cannot currently allocate distinct reviewer sessions for the latest recovery | Legitimate A4 independent assurance | Preserve fail-closed blocker; resolve host/session lifecycle separately | HIGH | OPEN GAP |
| Current Review Evidence only recognizes registered HIVE work orders | Governed GEF adoption PR that can satisfy required Review Evidence | Do not weaken the check; register an adoption-compatible work-order/bridge in a separate governed correction before merge if required | MEDIUM | OPEN GAP |
| Open PR #37 is based on old main and overlaps `.engineering` concepts | Preserve concurrent work | Do not modify/rebase/close it during GEF adoption; reconcile later explicitly | MEDIUM | OPEN GAP |
| PR #81 CI run `34699511231` failed before any Validate steps were exposed | Legitimate hosted A3 evidence | Treat as infrastructure/runner cause UNKNOWN until diagnosed; do not bypass or call it a product failure | MEDIUM | OPEN GAP |

## Compatibility decisions

- GEF task classes and context radii are engineering metadata, not product architecture.
- GEF A0-A2 does not remove current validation. Test/proof skipping has no authority until shadow assurance demonstrates no loss.
- GEF A3 maps to existing hosted required checks and their artifacts.
- GEF A4 maps to independent semantic assurance/HEDS and must remain distinct from executor work.
- Existing UADS reviewer/finalize requirements remain fail-closed. GEF does not convert an unavailable reviewer into approval.
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
gaps: UADS reviewer-session capacity; Review Evidence adoption bridge; legacy PR #37 overlap; PR #81 hosted Validate runner/start failure with no exposed steps
risks: no bypass of fail-closed assurance; no test-skipping authority yet
nextAction: resolve the smallest adoption compatibility/hosted-validation gap without changing product scope; separately resolve UADS reviewer-session capacity; then validate and review PR #81
status: READY_WITH_GAPS
```

## Next action

Use GEF V1 immediately for new prompts and reviews. Do not start/advance product work that is still blocked by existing HIVE/UADS governance. Resolve the UADS reviewer-session gap and the adoption-PR Review Evidence/hosted-validation gaps as separate, smallest governed corrections before any adoption merge that requires those gates.
