# Work Order GEF-UNIVERSAL-ADOPTION-002

## OBJECTIVE

Reconcile HIVE's existing GEF V1 layer with GEF Bootstrap V1.0.0 Universal Adoption while preserving canonical HIVE truth, active exact-base work, product behavior, CI, tests, architecture and history.

## CONTEXT

HIVE is an established BROWNFIELD repository with an already-merged historical GEF adoption (PR #81). Existing GEF metadata became stale and predates the Universal Adoption model. A current release-critical product closure PR (#95 / WO-024) is exact-base-bound to the discovery main SHA.

## SOURCE INPUTS

- HIVE canonical Project Brain sources;
- existing `.engineering/gef/**`;
- `AGENTS.md`;
- `.github/workflows/ci.yml`;
- ruleset `21934284`;
- current open PR state, especially WO-024 PR #95;
- GEF Bootstrap V1.0.0 Universal Adoption reference supplied by the user.

## CONTEXT LOCK

- Repository: `KayzenRoot/hive`
- Authorized discovery base: `4fb0aa111bd5b0f526df85b1897618d8eca1c0e0`
- Adoption branch: `governance/gef-v1-universal-adoption-002`
- Classification: `BROWNFIELD`
- Stale-head policy: `FAIL_CLOSED_FOR_FINAL_ADOPTION`

## IN SCOPE

- repository discovery receipt;
- collision/preservation mapping;
- reconcile stale GEF current/adoption metadata;
- install Universal GEF prompt/review/execution policy;
- install thin Project Master;
- install machine adoption checkpoint;
- install Work Order and Context Lock templates;
- minimally update agent guidance to discover the new protocols;
- prepare adoption for later exact-head PR/audit/merge without invalidating active WO-024.

## OUT OF SCOPE

- HIVE product behavior;
- Product Brain content;
- migrations;
- dependencies;
- Docker/runtime topology;
- CI workflow/ruleset weakening or replacement;
- history rewriting;
- retargeting/rebasing/merging WO-024;
- claiming HIVE V0.1 complete;
- claiming Universal GEF adoption canonically complete before merge/post-merge evidence.

## ALLOWED AREAS

- `.engineering/gef/**`
- `AGENTS.md` only for a concise additive pointer if needed.

## PRESERVATION CONSTRAINTS

- Preserve every active user/product branch and PR.
- Never move main before WO-024 terminates if doing so invalidates its exact authorized base.
- Reuse existing Project Brain rather than creating parallel scope/requirements/architecture/DoD truth.
- Preserve existing required checks and squash-only main ruleset.
- Historical GEF adoption remains historical evidence, not rewritten history.

## REQUIREMENTS

- GEF Universal repository classification and discovery recorded.
- Brownfield collision/preservation analysis recorded.
- Universal execution loop adopted.
- Prompt/Work Order/Context Lock standards installed.
- Exact-head delta review semantics installed.
- Machine-readable resume state installed.
- Adoption progress kept separate from product progress.
- UNKNOWN never treated as PASS.

## ARCHITECTURE RULES

GEF is an engineering/governance overlay. It may map to HIVE architecture but may not become a second persistence, orchestration, context or canonical governance engine.

## SECURITY CONSTRAINTS

No secrets, credentials, local absolute user paths or sensitive runtime material may be copied into adoption artifacts. Do not weaken security/CI/governance to make adoption pass.

## ACCEPTANCE CRITERIA

- [x] discovery completed;
- [x] BROWNFIELD classification recorded;
- [x] collision/preservation plan produced;
- [x] canonical source mapping established;
- [x] Work Order/Context Lock/prompt/review standards prepared;
- [x] existing user work preserved by scope;
- [ ] refreshed against post-WO-024 accepted main;
- [ ] repository-native validations green on final adoption exact head;
- [ ] adoption-compatible Review Evidence green;
- [ ] exact-head technical audit APPROVED;
- [ ] squash merge completed;
- [ ] post-merge main verified;
- [ ] post-adoption GEF checkpoint promoted.

## TESTS / EVIDENCE

Before final adoption merge, run repository-native validation appropriate to the final diff. At minimum require generated/document integrity applicable to changed files plus hosted `Validate`, `Integration health`, and an adoption-compatible exact-head `Review Evidence` path. Do not fabricate green evidence while the adoption branch is only staged.

## ROLLBACK / RECOVERY

Until merge, abandon/delete the adoption branch without affecting canonical HIVE. After merge, normal Git revert/governed correction is required; never rewrite protected history.

## DELIVERABLES

- reconciled `.engineering/gef/**` Universal model;
- machine discovery/preservation/current/checkpoint state;
- exact-head adoption PR when active base dependency permits;
- rewritten Universal Adoption Prompt for reuse after repository reconciliation.

## REVIEW FORMAT

Use `APPROVED | CORRECTION_REQUIRED | BLOCKED`, exact candidate SHA, required-check state, CRITICAL/HIGH counts, preservation status and capability gaps.

## STOP CONDITION

Current safe stop: `GEF_ADOPTION_EXACT_HEAD_EVIDENCE_REQUIRED` while WO-024 remains active and exact-base-bound to discovery main.

Final stop after accepted merge/post-merge only: `GEF_V1_ADOPTED_READY_FOR_GOVERNED_DEVELOPMENT`.
