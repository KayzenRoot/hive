# HCODER-WO-0027-HIVE-UNBLOCK-001 — Narrow local HIVE mount for the active Hive Coder checkout

**Status:** PROPOSED / NOT AUTHORIZED FOR LOCAL MUTATION UNTIL GOVERNED ACCEPTANCE  
**Classification:** NECESSARY operational prerequisite, not a HIVE product increment  
**Risk:** ELEVATED (local container mount, durable project registration/index identity)  
**Task class / context radius:** T2 / C1  
**Issue:** [HIVE #166](https://github.com/KayzenRoot/hive/issues/166)  
**Related active Hive Coder work:** [HCODER #89](https://github.com/KayzenRoot/hive-coder/issues/89), [Draft PR #93](https://github.com/KayzenRoot/hive-coder/pull/93)  
**Independent existing HIVE work:** [WO-032 / HIVE #163](https://github.com/KayzenRoot/hive/issues/163) — DO NOT CHANGE OR CLAIM IT IS CLOSED  
**Governance branch:** `ops/HCODER-WO-0027-HIVE-UNBLOCK-001`  
**Governance base:** HIVE `main` at `b7f5bd8a9c9c1737c64412ebe481c9a70d9ecfc5`  
**Observed Hive Coder base:** `a9b48bce43fcc2c1a14b70036ed4555f52ba3537`  
**Proposed local source:** `D:\Projects\coder` (must re-derive and verify; screenshot observation is not local proof)  
**Proposed container destination:** `/workspace/projects/coder` (read-only; conditional on actual Docker/registry validation)

## OBJECTIVE

Make only the *actual active* Hive Coder Git checkout visible to HIVE as a read-only child repository, and establish trustworthy HIVE discovery/project/index/retrieval evidence for HCODER-WO-0027 without replacing existing mounts or rewriting an existing HIVE project that refers to another physical checkout.

This is a site-local operational prerequisite to the existing Hive Coder Work Order; no HIVE application feature or Hive Coder updater capability is admitted here.

## CONTEXT / SOURCE CHECK

1. Read the *actual* current HIVE Git checkout, its `AGENTS.md`, canonical `docs/project-brain/13-CHECKPOINT.md`, decisions ledger, Scope, DoD, architecture, installation instructions, `docker-compose.yml`, and active WO-032 Issue #163/branch truth. Compare to this proposed Context Lock. If HIVE source/gates changed, mark STALE before any config write.
2. Read the *actual* `D:\Projects\coder` checkout's Git remote, branch, full HEAD, real physical root, working tree, `AGENTS.md`, canonical `docs/project-brain/11-CHECKPOINT.md`, HCODER-WO-0027 + Context Lock, Issue #30/#89 and Draft PR #93. Do not infer identity from directory name.
3. Determine from actual `docker inspect` / `docker compose config` which running HIVE Compose project/API service and host paths are active. Screenshot indicated a parent mount for another host folder, but a fresh inspection wins.
4. Confirm this Work Order was accepted via the documented governance path and that it does not contradict the active HIVE WO-032. A Draft PR or Issue by itself is not local execution authority.

## SCOPE

**Governance stage, available before local permission:** add only this proposed Work Order and its Context Lock in a docs-only Draft PR in HIVE; run the applicable governance/source validation and obtain an exact-head review. Keep the PR unmerged until that review. No machine-local mutation in this stage.

**Site-local operations, only after acceptance:**
1. Back up the actual local Compose/.env/mount configuration and record a restore command. Snapshot relevant registry metadata read-only before registration/reinspection.
2. Add one **additive**, read-only bind for the verified `D:\Projects\coder` physical checkout at `/workspace/projects/coder` through a site-local, untracked Compose override or an already-approved local configuration seam; leave the existing `HIVE_PROJECTS_ROOT -> /workspace/projects:ro` mapping intact. Never add a broad mount of `D:\Projects` or replace the previous parent.
3. Validate `docker compose config --quiet` against the **actual** active Compose file set; inspect the final volume mapping before recreating only the minimum necessary API container. Preserve data, Redis, PostgreSQL, CAS, service ports, external project mounts, and optional profiles. Do not tear down the stack.
4. Verify HIVE API health, service health, Git root/remote/HEAD, and deterministic tracked-file hashes across host and container. Demonstrate effective read-only access with inspection, never by attempting an unauthorized write into the project.
5. Use the actual version-exposed MCP `project.list`/`project.status` and documented localhost REST to check for *physical identity*. Prefer existing documented auto-discovery. If no matching identity is present, register only the newly verified child checkout through a documented public API **if it permits a distinct identity without rewriting/colliding with an existing project**. Any duplicate-name or physical-identity ambiguity is STOP.
6. If registration is authorized and identity resolved, use only documented, bounded project-scoped inspection/index/retrieval operations. Never guess tool names or fabricate a task ID. A task-scoped `context.build` is allowed only with an existing verified HCODER-WO-0027 task ID.
7. Preserve the existing `hive-coder` project if it identifies a different checkout, and verify the other existing project paths remain accessible.

## OUT OF SCOPE

No changes to HIVE application code, Docker image/dependencies/runtime version, public Compose template, WO-032, canonical checkpoint, decisions, provider/embedding/rerank settings, database schema/direct writes, project deletion/repoint, other repositories, release state, or Hive Coder PR #93 implementation. No `README.md` change in either repository here; the Hive Coder README discrepancy is a separate governed, docs-only change with its own Context Lock Delta or authorized Work Order.

## FILES / SOURCES TO READ

HIVE: `AGENTS.md`; `docs/project-brain/13-CHECKPOINT.md`; `docs/project-brain/16-DECISIONS-LEDGER.md`; `docs/project-brain/03-SCOPE.md`; current DoD and architecture; `docker-compose.yml`; `.env.example`; `docs/INSTALLATION.md`; HIVE #163/#166; this WO and matching Context Lock.  
Hive Coder: `AGENTS.md`; `docs/project-brain/11-CHECKPOINT.md`; `docs/project-brain/10-DECISIONS-LEDGER.md`; `.engineering/work-orders/HCODER-WO-0027.md`; `.engineering/context-locks/HCODER-WO-0027.md`; Issues #30/#89 and PR #93.

**Allowed tracked paths for this governance PR only:** `.engineering/work-orders/HCODER-WO-0027-HIVE-UNBLOCK-001.md`, `.engineering/context-locks/HCODER-WO-0027-HIVE-UNBLOCK-001.md`. Runtime changes belong exclusively to the site-local, separately approved phase and must remain untracked.

## REQUIREMENTS / ARCHITECTURE / CONSTRAINTS

- Exact host physical checkout and Git remote/HEAD match the intended Hive Coder project; stale or modified alternate checkouts never substitute.
- The new mount is a child of the existing container project root, `:ro`, limited to one verified repo; existing parent mount is neither replaced nor widened.
- Host-specific paths and runtime configuration are never committed to public Git; back up/restore and redact sensitive configuration evidence.
- HIVE-derived state remains derived; Git/approved checkpoint/code/tests prevail.
- Only already documented and exposed localhost REST/MCP operations may mutate project registration or indexing, and only after this governance record is accepted.
- Preserve HIVE WO-032 and its local unpushed branch, checkouts and registry identity; no concurrency with overlapping local Compose/registry mutations. If another executor is modifying those resources, STOP and serialize.
- No `git reset --hard`, force push, `docker compose down -v`, volume deletion, registry overwrite, direct SQL mutation, mass sync, provider calls or fake PASS.

## ACCEPTANCE CRITERIA

1. This WO and Context Lock are reviewed at the exact governance head, with no unresolved HIGH/CRITICAL, and any required HIVE gates pass; the governance PR is merged/postvalidated before local mutation, or another independently documented canonical approval predicate is proven.
2. Actual host checkout, running Compose files, host root and container root are observed, not assumed.
3. Backups and reversible targeted restore are documented and tested non-destructively where safe.
4. Only one new site-local child mount exists; `:ro` and all pre-existing effective mounts/ports/data/service settings are preserved.
5. Relevant HIVE services healthy after the minimal Compose change; no loss of other project accessibility.
6. Host/container Git root, remote, full HEAD and at least two tracked-file content digests match the intended checkout.
7. Exactly one unambiguous project identity points to the intended checkout. Older differently rooted entries remain unchanged; registration ambiguity produces a truthful BLOCKED verdict.
8. Bounded HIVE retrieval proves provenance for HCODER-CP-0026 and HCODER-WO-0027 without asserting source/corpus freshness not demonstrated by the actual API.
9. No tracked product/runtime file changed in either repository and no HIVE WO-032 branch, registry or corpus change is attributed to this WO.
10. Final exact-environment Evidence Bundle, rollback instructions, findings, remaining unknowns and proposed Checkpoint Delta = NONE.

## TESTS / EVIDENCE

- Governance: inspect exact base/head and 2-file diff; applicable HIVE source-integrity/format/security validations, required PR CI and exact-head owner self-audit **NOT INDEPENDENT** under HIVE policy.
- Local: `git rev-parse`, `git status --porcelain`, `docker compose config --quiet`, effective `docker inspect` bind/ports, existing mount inventory comparison, API health, documented MCP handshake, host/container `git hash-object` of selected tracked files, registry before/after read-only comparison, bounded project inspection/retrieval.
- For registration/indexing, record actual documented endpoint/tool, request class, project ID, physical root, prior vs resulting HEAD/corpus/index status. Do not record secrets or assume `CURRENT` from mere handshake.
- Document any checks not run as NOT RUN, any external state UNKNOWN and skipped release/PR lanes as SKIPPED, not PASS.

## DELIVERABLES / REVIEW FORMAT

Governance: one proposed Work Order and one append-safe Context Lock; Draft PR and linked Issue #166; exact-head gates and audit.  
Local after approval: host-only reversible configuration delta, HIVE identity/retrieval proof, redacted Evidence Bundle with Git full SHAs, file changes, actual commands/result classes, backup/restore and honest verdict in Brazilian Portuguese. No canonical checkpoint promotion.

## STOP CONDITION

STOP before local modification unless the scoped authorization is **accepted**, HIVE WO-032 is compatible, exact Git/Compose/source fingerprints match and the mount can be proven narrow/read-only. STOP after backup and **before** registry mutation on ambiguity, reused project identity pointing elsewhere, unavailable documented API, existing concurrent HIVE local state mutation, unhealthy HIVE or loss of any existing mount. Leave PR #93 Draft and DEC-031 proposed; no next product increment.


## Correction Delta 001 — CI work-order registration (PROPOSED)

**Trigger:** Exact-head CI on original Draft PR #167 at `886e45c18a3db45b3cd4aeeb16d7c351f62c3426`: Validate, CodeQL and Dependency Review passed; Integration health failed only at the historical closure sprint because the pull_request event resolved work_order=UNRESOLVED and applied WO-024's historical fail-closed path scope to this separate proposal. Review Evidence was skipped by its dependency gate. A synthetic marker or spoofing WO-032/WO-033 is forbidden; the new HIVE-native ID for this proposed operational governance proposal is **`WO-035`**, mapped one-to-one to external cross-repository identifier `HCODER-WO-0027-HIVE-UNBLOCK-001`. The latter remains the stable cross-repo Issue/branch/path link.

**Exact added governance scope for this PR only:** In addition to the two existing documents, authorize only `scripts/review_evidence.py` and `backend/tests/test_review_evidence.py` to register `WO-035` explicitly with a fixed exact-main authorized base, a closed four-path allowlist, explicit disallow of WO-034/historical aliases, and focused positive/negative tests. This replaces the earlier two-file-only restriction **for proposed CI registration**, not for runtime mutation; no other tracked source, product code, global parser weakening, V0.1 closure exception, feature flags, environment secret, workflow edit, project registration or local Docker mutation is approved. If deterministic generated atlas files become necessary, STOP and request a new explicit delta; do not silently change them.

**PR event contract:** The PR description must contain exactly one `<!-- HIVE-WORK-ORDER: WO-035 -->` and the exact `<!-- HIVE-AUTHORIZED-BASE: b7f5bd8a9c9c1737c64412ebe481c9a70d9ecfc5 -->`. CI must still fail closed when the event is missing, the marker is unknown or the file scope/base differs. All required checks, including Review Evidence on a Ready PR, must pass on the final exact head. This delta does not authorize local operations before the governed PR is accepted/merged and exact-main postvalidation passes. HIVE WO-032 may have unpublished local changes to the same review script; preserve that branch and require compatibility review before any merge rather than resetting or overwriting it.
