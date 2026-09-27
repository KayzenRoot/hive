# HCODER-WO-0027-HIVE-UNBLOCK-001 — Context Lock

**State:** PROPOSED / GOVERNANCE ONLY. NO LOCAL MUTATION AUTHORIZED UNTIL ACCEPTED.  
**Date:** 2026-09-27  
**Risk:** ELEVATED  
**Work Order:** `.engineering/work-orders/HCODER-WO-0027-HIVE-UNBLOCK-001.md`  
**Issue:** https://github.com/KayzenRoot/hive/issues/166  
**Governance branch:** `ops/HCODER-WO-0027-HIVE-UNBLOCK-001`  
**Captured HIVE remote `main` before governance branch:** `b7f5bd8a9c9c1737c64412ebe481c9a70d9ecfc5`  
**Captured Hive Coder remote `main`:** `a9b48bce43fcc2c1a14b70036ed4555f52ba3537`  
**Captured Hive Coder PR #93 head:** `d6b512292b2d8bb9085059b4e3ff114a9ddea805` (DRAFT / NOT PROMOTED)  
**HIVE parallel work:** WO-032 / Issue #163, with reported unpushed local candidate `78c466b9e984931c52f0bad62fe4a04931828f5d` (issue narrative only; this Work Order has no local proof).

## Exact Git blob fingerprints at this governance proposal

| Repository | Source path | Git blob SHA |
| --- | --- | --- |
| HIVE | `AGENTS.md` | `4ddd5b0974d83319bec1efc8cecc817a275b4569` |
| HIVE | `docker-compose.yml` | `0ca2508257d89b5890aeb1e6bf9bae04280a51ca` |
| HIVE | `.env.example` | `28548d665ab3c7649cefb318da99f4e187366511` |
| HIVE | `docs/project-brain/13-CHECKPOINT.md` | `ae0c8d68da08dea892b27ba0fd05fc83755410c6` |
| HIVE | `docs/project-brain/16-DECISIONS-LEDGER.md` | `96805ca5318c0e3c28c0e8f9c9462e23f831c6ed` |
| HIVE | `docs/project-brain/03-SCOPE.md` | `5d57c08a3241aa960622d4d002ff64033316db4b` |
| Hive Coder | `AGENTS.md` | `c59e02d5b891a4dcc15b71753eef4884726774c5` |
| Hive Coder | `docs/project-brain/11-CHECKPOINT.md` | `df0ead8e90a46320b8e02bc8dce4f3e27dd67266` |
| Hive Coder | `.engineering/work-orders/HCODER-WO-0027.md` | `c941918746673996b180f2b31fe4c7b3a0837991` |
| Hive Coder | `.engineering/context-locks/HCODER-WO-0027.md` | `868147fee2fe72fcef4a82ba99ee5d17193a0c8b` |
| Hive Coder | `README.md` | `48a6f83528525a65ae9bad62855ff33340850cec` (stale prose, frozen for this WO) |

These are source observation fingerprints, NOT an instruction to reset a local checkout or force it onto an old remote commit.

## Host / container observations requiring local proof

The supplied screenshot reports a Hive Coder checkout `D:\Projects\coder` on `main` at `a9b48bc...`, an existing differently rooted `hive-coder` HIVE project and a running HIVE API rooted at `/workspace/projects` with no child `coder` mount. Proposed narrow mapping is **only** verified host checkout `D:\Projects\coder` -> `/workspace/projects/coder:ro`; do not replace the original `HIVE_PROJECTS_ROOT` host mapping or assume the screenshot is still current.

## Locks

1. **Governance-phase files:** exactly the Work Order and this Context Lock on the HIVE ops branch. No HIVE tracked `docker-compose.yml`, source code, Project Brain checksum manifest or release metadata edits.
2. **Local after approval:** one site-local untracked Compose override/configuration change plus reversible backup; documented project-scoped registration/reinspection/indexing only after identity proofs.
3. **Frozen:** HIVE WO-032 branch and its local state; existing `hive-coder` registered entry referring to a different physical path; the four existing external repos/mounts; all data/DB/cache/CAS volumes, services/ports/secrets; Hive Coder product/updater code, README, PR #93, DEC-031 and canonical checkpoint.
4. **Drift:** changes to either repository's accepted checkpoint, scope, this WO, relevant ADR or any above source fingerprints mark this lock STALE. Recompile from current Git, preserve existing local work and review before changes. If the HIVE ops governance merge legitimately advances remote `main`, capture the actual post-merge SHA in the Evidence Bundle before local operations; do not preserve the pre-merge SHA as a fake runtime start SHA.
5. **No concurrent writes:** if HIVE WO-032 is modifying local Compose, registry, index or corpus at the same time, serialize; STOP until non-overlap is proven.
6. **No source-of-truth promotion:** HIVE is read-only context to the Hive Coder executor; no HIVE summary proves approval, source freshness, a healthy install, production updater or current corpus on its own.

## Acceptance gate

The governance PR must be reviewed at its exact head, mandatory applicable checks must pass and the document must be accepted/merged through the existing HIVE policy **before** local Compose/registry operations. HIVE owner self-audit is explicitly NOT INDEPENDENT. Record a local exact-environment Evidence Bundle and final STOP/CONTINUE recommendation, never an invented pass or checkpoint promotion.
