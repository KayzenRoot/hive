# HIVE V2 — Verified Learning Kernel Contract

## Status
PLANNING CANDIDATE. Compact current specification for the frozen R20 learning requirement. Preserves the frozen object chain instead of replacing it with generic "memory learning".

## Frozen requirement
The R20-ratified learning kernel is:

`VEXL → Archetype → EEC → OCAR → XTV / HCELB`

Fine-tuning/model evolution is FUTURE and is not required to prove V2 learning.

## Objective
Allow HIVE to reuse verified engineering experience across future tasks only when validity, applicability, provenance and negative-transfer controls justify it.

## LK-01 — VEXL
Verified Experience Ledger.

Role:
- record candidate/verified engineering experiences;
- bind task/change basis, context, execution, verification, outcome and provenance;
- distinguish successful, failed and inconclusive experience;
- never treat executor narrative as verified outcome by itself.

VEXL is a logical governed view over shared evidence/storage primitives, not a competing database.

## LK-02 — Archetype
A bounded task/problem family derived from verified experience.

An archetype declares:
- applicability features;
- exclusions;
- required evidence;
- stack/domain/version constraints;
- confidence/coverage;
- counterexamples.

Novel/low-confidence tasks must be allowed to remain UNKNOWN rather than forced into an archetype.

## LK-03 — EEC
Engineering Experience Capsule.

Compact reusable experience:
- archetype identity;
- problem/task signature;
- verified strategy/pattern;
- critical context/evidence references;
- verification obligations;
- known failure modes;
- applicability fingerprint;
- validity/freshness;
- counterevidence;
- provenance.

EEC never replaces canonical project source.

## LK-04 — OCAR
Outcome-Corrected Applicability/Relevance.

Before an EEC is reused, HIVE adjusts its applicability using current evidence and prior observed outcomes.

Inputs include:
- current project/domain/stack;
- dependency/version drift;
- architecture/policy;
- task similarity;
- prior positive outcomes;
- negative transfer/counterexamples;
- evidence freshness.

The exact scoring formula is not frozen before calibration.

## LK-05 — XTV
Cross-Task Validation.

A candidate learning pattern must demonstrate usefulness beyond the exact task that created it before broad reuse claims.

Validation distinguishes:
- same-project/same-archetype;
- same-project/new instance;
- cross-project transfer;
- incompatible/novel task.

## LK-06 — HCELB
HIVE Continuous Engineering Learning Benchmark.

Required comparisons:
- COLD: learning disabled/no reusable EEC;
- WARM: eligible verified learning enabled;
- novel-task safety;
- stale-knowledge rejection;
- negative-transfer cases.

Measure quality together with token/context/tool/provider/time/resource effects.

## LK-07 — Validity
Shared 1.2 validity/freshness governs learning.

EEC can become:
CURRENT, STALE, REVALIDATE, QUARANTINED, SUPERSEDED, INVALID/UNKNOWN according to the shared contract.

## LK-08 — Negative Transfer Guard
If archetype/applicability confidence is weak:
- do not force EEC;
- broaden safe current context;
- escalate verification;
- capture the result as candidate experience.

## LK-09 — Cross-Project Transfer
Frozen governance requires transfer evaluation + operator approval by default for organizational EEC promotion.

Project secrets/canonical content do not become global learning. Prefer abstracted patterns with proof references and provenance.

## LK-10 — Learning Promotion
Suggested ladder:
OBSERVED → CANDIDATE → VERIFIED_LOCAL → XTV_VALIDATED → REUSABLE_APPROVED → STALE/REJECTED/QUARANTINED.

No model self-promotion.

## LK-11 — C³ Integration
Learning is one context source, below current canonical project truth and current verified project evidence.

C³ can omit an EEC if invalid/inapplicable or if current authoritative evidence conflicts.

## LK-12 — Debug/Test Integration
- Test Intelligence contributes verified outcome evidence.
- Debug Intelligence contributes verified Failure DNA/repair evidence.
- failed experiences are valuable counterevidence.
- regression locks can invalidate outdated repair patterns.

## LK-13 — Learning Economics
Track:
- EEC retrievals;
- accepted/rejected applicability;
- context/token delta;
- verification delta;
- task outcome;
- negative transfer;
- stale rejection;
- cross-project approval.

Savings without equal-or-better verified quality are not learning benefit.

## HIVE-original extensions
### Counterexample Reservoir
Keep compact verified examples where an archetype/EEC failed or was inapplicable, preventing success-only reinforcement.

### Applicability Drift Alarm
Dependency/architecture/policy drift proactively marks affected EECs for revalidation.

### Experience Minimality Test
Research whether removing portions of an EEC preserves verified benefit, reducing context/storage without losing utility.

### Learning Benefit Receipt
Every promoted reusable learning claim references the exact HCELB/XTV evidence that justified promotion.

## Absolute gates
- raw executor claim promoted as verified learning = 0;
- stale EEC silently overrides current canonical source = 0;
- forced archetype on UNKNOWN novel task = 0;
- cross-project secret leakage = 0;
- reusable promotion without XTV/equivalent proof = 0;
- negative HCELB result hidden = 0.

## Stop condition
The frozen learning requirement is planning-complete only when VEXL, Archetype, EEC, OCAR, XTV and HCELB have implementation contracts, migration/storage ownership, benchmark fixtures and Control Center evidence mapped into the release train.
