## Summary

<!-- What changed and why? -->

## Governed delivery

- Work Order ID: `<!-- ENG-PROTOCOL-ADOPTION-001 or current ID -->`
- Work Order: `.engineering/work-orders/<ID>.md`
- Context Lock: `.engineering/context-locks/<ID>.md`
- Evidence Bundle: `.engineering/reports/EVIDENCE-BUNDLE-<ID>.md`
- Checkpoint Delta: `.engineering/reports/CHECKPOINT-DELTA-<ID>.md`
- [ ] Branch and PR use the same Work Order ID.
- [ ] PR is Ready for review and auto-merge is not armed by the executor.

## Scope

- [ ] Within the approved increment
- [ ] No out-of-scope subsystem added
- [ ] No canonical source, migration, product contract or runtime data changed without explicit scope
- [ ] No broad cleanup was performed

## Validation

<!-- Include BEFORE x AFTER commands/results. Do not invent required check names. -->

- BEFORE: `<link or report>`
- AFTER: `<link or report>`
- CI required checks: `Validate`, `Integration health`, `Review Evidence` (verify against the active Ruleset)

## Evidence and risks

<!-- Link evidence, list known limitations, pre-existing failures, risks and migration/data impact. -->

- Pre-existing failures/warnings: `<NONE or exact items>`
- Introduced failures/corrections: `<NONE or exact items>`
- Migration/data impact: `<NONE or exact impact>`
- [ ] Cleanup candidates are classified; no suspect item was deleted.
- [ ] Checkpoint promotion/merge/release is left for independent review.
