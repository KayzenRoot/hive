# HIVE 1.x — Release Engineering Contract

## Status
PLANNING CANDIDATE.

## Purpose
Keep the installed stable HIVE usable while each next release is developed, audited and promoted. Define repeatable SemVer, upgrade, rollback and evidence behavior for the 1.x train leading to 2.0.0.

## Stable-channel invariant
- released tags are immutable;
- `main` is not treated as the installed production version;
- development occurs on governed branches/PRs;
- the user can remain on the latest approved stable tag while development continues;
- a release candidate does not replace the stable installation merely because CI is green.

## Version semantics
- PATCH: compatible defect/security/release correction with no intended new capability;
- MINOR: backwards-compatible capability increment;
- MAJOR: approved breaking compatibility boundary or the governed V2 completion boundary.

Pre-release identifiers may be used for release candidates when existing repository release tooling supports them without weakening provenance.

## Release lifecycle
```text
PLAN
 -> IMPLEMENT
 -> FOCUSED TESTS
 -> INTEGRATION
 -> BENCHMARK / SECURITY / MIGRATION PROOF
 -> PR EVIDENCE
 -> SOL EXACT-HEAD AUDIT
 -> MERGE
 -> POST-MERGE CI
 -> RELEASE CANDIDATE / SHADOW VALIDATION if required
 -> RELEASE AUTHORIZATION
 -> IMMUTABLE TAG + ASSETS
 -> INSTALL/UPGRADE SMOKE
 -> STABLE
```

## Upgrade contract
Every release documents:
- supported source version(s);
- target version;
- migration head before/after;
- configuration changes;
- persistent-volume impact;
- derived-state rebuild requirements;
- expected downtime/restart;
- post-upgrade health checks;
- rollback support/limitations.

At minimum, each MINOR must prove upgrade from the immediately previous stable MINOR/PATCH line used as its base.

## Data compatibility classes
Each changed durable object/table/artifact is classified:
- PRESERVED;
- MIGRATED;
- REBUILT_DERIVED;
- DEPRECATED_COMPATIBLE;
- BREAKING_REQUIRES_MAJOR.

No user-owned canonical data may be silently classified as rebuildable derived state.

## Rollback classes
- SAFE_DIRECT: old binary can read state unchanged;
- SAFE_AFTER_REBUILD: only derived state must be rebuilt;
- RESTORE_REQUIRED: canonical schema/data changed incompatibly and rollback requires verified backup/restore;
- UNSUPPORTED: only allowed with explicit release blocker/major-version governance.

A MINOR release should not silently introduce UNSUPPORTED rollback.

## Release evidence manifest
Machine-readable evidence should bind:
- version;
- release commit;
- source/base version;
- migration head;
- tests;
- integration;
- benchmark reports;
- security evidence;
- upgrade evidence;
- rollback class;
- known limitations;
- artifact hashes;
- release authorization provenance.

## Production feedback loop
Installed stable releases may produce:
- bug evidence;
- performance regressions;
- provider compatibility failures;
- migration issues;
- resource pressure evidence.

Classification:
- release blocker before promotion;
- PATCH candidate;
- next-MINOR improvement;
- FUTURE/backlog.

Feedback never silently edits historical release truth.

## Experimental capability policy
Features such as new decision providers, Confidence Debt, novel retrieval methods or local models:
- disabled or shadow by default until evidence;
- versioned config;
- explicit telemetry;
- safe fallback;
- no requirement for stable baseline operation unless formally promoted.

## Release train dependency rule
A later release may rely only on capabilities already:
- stable in an earlier release, or
- implemented within the same governed release with explicit dependency ordering.

Do not build 1.4 assumptions on unapproved 1.3 candidate behavior.

## 2.0 completion rule
2.0.0 is not merely "the next number after 1.9".

It is authorized only after:
- frozen V2 NECESSARY capability mapping is complete;
- all applicable release gates remain green;
- migration chain is proven;
- recovery is proven;
- final documentation is current;
- unresolved HIGH/CRITICAL blockers = 0;
- final exact-head audit and release provenance pass.

## Stop condition
The release train is healthy only while the previous stable version remains recoverable/installable and every promoted release has reproducible provenance plus tested upgrade semantics.
