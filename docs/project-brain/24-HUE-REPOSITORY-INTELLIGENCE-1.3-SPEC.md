# HIVE 1.3.0 — HUE Repository Intelligence Specification

## Status
PLANNING CANDIDATE. Translates the frozen V2 HUE-IR/EET capability into an incremental release using the existing v1.0 repository-indexing foundation.

## Objective
Turn HIVE's Git-aware file/AST/symbol foundation into bounded engineering intelligence that can answer repository-structure, symbol, dependency, change-impact and evidence-topology questions with deterministic/static evidence before LLM reasoning.

## Existing foundation to reuse
Verified in v1.0:
- Git-aware incremental repository indexing;
- stable SHA-256 content identity;
- Python AST symbol metadata;
- progressive disclosure L2 already models symbol signatures/dependency metadata;
- hybrid retrieval/reranking;
- deterministic Atlas / Module Registry / Test Map;
- GEF adoption already identifies source/module→tests/evals mapping and evidence-validity carry-forward as active/ready directions.

No second repository indexer should be created.

## HUE-01 — HUE-IR Core Contract
Bounded intermediate representation for repository intelligence.

Node families, introduced only when supported by deterministic evidence:
- repository;
- commit/snapshot;
- file;
- module/package;
- symbol;
- test/eval;
- documentation artifact;
- configuration/schema/migration;
- generated artifact.

Edge families:
- contains/declares;
- imports/depends_on;
- calls/references when statically supported;
- tests/verifies;
- documents;
- generated_from;
- changed_with;
- invalidates;
- evidence_for.

Unsupported relation types remain absent/UNKNOWN, not hallucinated.

## HUE-02 — Symbol Identity
Stable symbol identity must bind:
- project;
- repository snapshot;
- language;
- file content/path identity as appropriate;
- qualified symbol name;
- symbol kind;
- source span/signature fingerprint.

Rename/move detection may be heuristic evidence but cannot silently rewrite canonical Git history.

## HUE-03 — Dependency Extraction
Use deterministic parsers/AST/static tools first.

Required:
- language-specific adapter boundary;
- import/module dependency;
- symbol-level relation only where reliable;
- parse failure visible;
- generated/vendor exclusions follow explicit policy;
- incremental recomputation.

## HUE-04 — Engineering Evidence Topology (EET)
Connect implementation objects to engineering evidence:
- source → tests;
- source → evals;
- source → docs;
- source → schemas/migrations;
- source → review/release evidence where deterministic linkage exists.

Evidence strength/derivation is explicit.

## HUE-05 — Change Impact Engine
Given an exact Git delta, produce bounded impact candidates:
- directly changed files/symbols;
- deterministic dependents;
- mapped tests/evals;
- affected docs/contracts;
- invalidated derived evidence;
- confidence/coverage gaps.

Impact output is evidence for planning/testing, not permission to skip all non-selected tests automatically.

## HUE-06 — Test Impact Selection
Conservative test/eval selection.

Modes:
- FOCUSED: selected impacted tests during iteration;
- REQUIRED_FULL: canonical release/security/migration gates remain full when policy requires;
- UNKNOWN_COVERAGE: expand rather than shrink when mapping confidence is insufficient.

Observed test outcomes may improve derived mappings but cannot self-promote to canonical policy without validation.

## HUE-07 — Incremental Graph Maintenance
Update only impacted HUE objects after Git changes.

Requirements:
- exact snapshot basis;
- add/change/delete/rename handling;
- deterministic invalidation;
- rebuild equivalence;
- no stale edge survives incompatible source change;
- project isolation.

## HUE-08 — Structured Retrieval
Expose HUE evidence to retrieval/context as structured candidates rather than flattening everything into prose.

Examples:
- symbol signatures;
- dependency neighborhood;
- impact set;
- test evidence;
- compact module summary.

Progressive disclosure decides how much implementation text follows.

## HUE-09 — HUE Query Contract
Bounded query families:
- symbol lookup;
- references/dependents;
- module neighborhood;
- impacted-by-delta;
- tests-for-change;
- evidence-for-object;
- docs/contracts-for-change.

Avoid a general arbitrary graph-query language in 1.3.

## HUE-10 — Uncertainty / Coverage
Every result can report:
- COMPLETE_WITHIN_ADAPTER;
- PARTIAL;
- UNKNOWN;
- UNSUPPORTED_LANGUAGE/RELATION;
- PARSE_FAILED.

Absence of an edge does not imply proof of no dependency when adapter coverage is partial.

## HUE-11 — Context Integration
Context Manager/C³ future integration receives:
- compact HUE summaries first;
- selected symbols/dependencies second;
- excerpts only when required;
- exact provenance and snapshot basis.

1.3 must not require 1.4 C³ to be complete.

## HUE-12 — Decision Fabric Integration
Decision Fabric may use HUE evidence for bounded questions such as:
- which focused tests are candidates;
- whether impact coverage is uncertain;
- whether escalation is needed.

Probabilistic decisions cannot invent HUE edges.

## HUE-13 — Telemetry
Use existing Event Bus for:
- graph/index update;
- parse/coverage status;
- impact query;
- focused test selection;
- rebuild;
- invalidation.

Metrics:
- nodes/edges by supported family;
- incremental reuse;
- parse failures;
- query latency;
- impact set size;
- test selection reduction;
- UNKNOWN/PARTIAL rate;
- rebuild equivalence failures.

## HUE-14 — Control Center
Expose:
- repository intelligence health;
- language/adapter coverage;
- latest indexed Git basis;
- incremental reuse;
- parse failures;
- recent change-impact traces;
- source→test/eval mapping;
- stale/invalidated intelligence.

## HUE-15 — Benchmark Harness
Measure:
- symbol lookup correctness;
- dependency relation precision on labelled fixtures;
- impact recall for labelled changes;
- critical missed impacted tests;
- focused-test reduction;
- index/update latency;
- rebuild equivalence;
- storage overhead;
- context/token reduction when structured HUE replaces broad source context;
- project isolation.

No token-saving claim is valid if critical impact recall degrades beyond approved threshold.

## HIVE-original research candidates

### Evidence-Carrying Edges
Each derived relation carries compact proof metadata: extractor, source span/config, snapshot and validity fingerprint. This makes graph edges auditable instead of opaque.

### Impact Cone Compression
Represent repeated dependency neighborhoods as content-addressed immutable cones/deltas so unchanged impact structure can be reused across nearby Git snapshots.

Candidate only if benchmark proves useful storage/query savings.

### Negative Knowledge Guard
HIVE distinguishes "no edge found with complete adapter coverage" from "no evidence because coverage is partial". Prevents false certainty from sparse graphs.

### Proof-Carry-Forward Graph
Reuse still-valid test/review evidence across exact compatible deltas, invalidating it through HUE impact edges. Must begin in shadow mode against full CI, consistent with existing GEF adoption direction.

### Semantic Edge Quarantine
LLM/embedding-suggested relationships may be useful discovery hints, but remain quarantined/derived until deterministic or validated evidence supports promotion. They never mix silently with static truth.

## Proposed work orders
- WO-1.3-01 HUE-IR + identity contracts
- WO-1.3-02 language adapter + dependency extraction
- WO-1.3-03 EET source/test/doc/eval mapping
- WO-1.3-04 incremental graph maintenance
- WO-1.3-05 change-impact + test selection
- WO-1.3-06 structured HUE queries/retrieval
- WO-1.3-07 context/Decision Fabric integration
- WO-1.3-08 telemetry + Control Center
- WO-1.3-09 proof-carry-forward shadow experiment
- WO-1.3-10 benchmark/rebuild/migration/release hardening

## Acceptance criteria
1. Git snapshot basis is explicit.
2. Existing indexer is extended rather than duplicated.
3. Unsupported/partial static knowledge is never presented as complete.
4. Incremental state rebuilds equivalently from canonical Git/source.
5. Stale relations invalidate after material source changes.
6. Cross-project edges/results are impossible.
7. Critical release tests cannot be skipped solely by probabilistic suggestion.
8. HUE structured retrieval preserves provenance.
9. Evidence-carrying relations are auditable.
10. benchmark reports quality, economy and coverage together.
11. full existing regression remains green.
12. upgrade from previous stable release preserves canonical user state.

## Release gates
- zero cross-project graph leakage;
- zero stale-edge survival in accepted invalidation fixtures;
- zero critical missed-impact cases in frozen critical fixtures;
- rebuild equivalence green;
- migration/upgrade green;
- benchmark quality threshold frozen and passed;
- storage/latency overhead measured;
- Control Center reports real adapter/coverage state.

## Stop condition
1.3.0 is releasable only when HIVE can explain what repository intelligence it knows, how it knows it, what changed, what may be impacted, and where its static knowledge is incomplete.
