# Evidence Bundle — `<WORK-ORDER-ID>`

## Identity

- ID: `<WORK-ORDER-ID>`
- Repository: `<owner/name>`
- Base branch/SHA: `<branch>/<SHA>`
- Head branch/SHA: `<branch>/<SHA>`
- PR: `<number/URL>`
- Context Lock: `<path>`
- Work Order: `<path>`

## Change boundary

- Product code changed: `YES | NO`
- Canonical Project Brain changed: `YES | NO`
- Migration/data change: `YES | NO`
- Cleanup performed: `YES | NO`
- Changed paths: `<exact list or NONE>`
- Diff review: `PASS | FAIL`

## BEFORE × AFTER

| Area | BEFORE | AFTER | Evidence |
| --- | --- | --- | --- |
| Tests | `<result>` | `<result>` | `<log/artifact>` |
| Lint | `<result>` | `<result>` | `<log/artifact>` |
| Typecheck | `<result>` | `<result>` | `<log/artifact>` |
| Build | `<result>` | `<result>` | `<log/artifact>` |
| Integration/E2E | `<result>` | `<result>` | `<log/artifact>` |
| Security/dependencies | `<result>` | `<result>` | `<log/artifact>` |
| CI required checks | `<result>` | `<result>` | `<URL>` |

## Warnings and pre-existing failures

- Pre-existing failures: `<NONE or exact command/output>`
- Non-blocking warnings: `<exact warning and provenance>`
- Environment-blocked checks: `<NONE or exact reason>`

## Security and provenance

- Secret scan: `<PASS/FAIL/UNKNOWN>`
- Context lock revalidated: `<YES/NO>`
- Exact-head checks: `<PASS/FAIL/PENDING>`
- Ruleset baseline unchanged: `<YES/NO/PENDING>`
- Auto-merge armed: `NO | YES — explain authorization`
- Merge/release performed: `NO | YES — explain authorization`

## Review handoff

- Sol/independent review: `AWAITING | APPROVED | REJECTED`
- Checkpoint Delta: `<path/status>`
- Cleanup Inventory: `<path/status>`
- Known risks: `<list>`
