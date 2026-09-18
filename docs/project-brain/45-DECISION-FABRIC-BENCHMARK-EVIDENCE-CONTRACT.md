# HIVE 1.1 — Benchmark & Evidence Ownership Contract

## Status
PLANNING CANDIDATE. Closes the benchmark/evidence freeze blocker for Decision Fabric.

## Ownership
HIVE core owns benchmark contract and evidence schema.
Release-specific modules own fixtures for their decision kinds.
Domain Profiles own domain-specific strata.
Security/Verification owns critical/adversarial gates.
Control Center consumes evidence but does not redefine it.

## Fixture identity
Each fixture has:
fixture_id, corpus_version, decision_kind, domain_profile, risk, input_basis_hash, declared_options, expected invariant/outcome, evidence provenance, deterministic_or_semantic classification, and change history.

## Corpus governance
A corpus version is frozen before candidate-vs-baseline comparison. Any fixture change creates a new corpus version. Results from different corpus versions are not silently aggregated.

## Run identity
Each benchmark run binds:
release candidate commit, config fingerprint, provider/model/revision, calibration revision, hardware/resource profile, warm/cold state, corpus version, timestamps and content hashes.

## Evidence schema
For every decision attempt record:
- selected path/provider;
- options/distribution when applicable;
- calibrated confidence/validity;
- AUTO/REVIEW/ESCALATE outcome;
- policy reasons;
- evidence/context fingerprints;
- cache/delta state;
- disagreement with baseline/shadow;
- latency;
- fresh/cached/output tokens;
- sent context bytes/tokens;
- cost when known;
- CPU/RAM/GPU/VRAM observations when available;
- final verified outcome or UNKNOWN;
- failure/degraded state.

## Quality metrics
Use task-appropriate accuracy/F1 plus confusion data. Where probabilities matter include Brier/ECE or an explicitly justified calibration metric. Critical false AUTO is reported separately and cannot be hidden in aggregate accuracy.

## Economy metrics
Tokens, context, latency, cost and resources are reported beside quality. Savings with unacceptable quality/safety regression are not promotion evidence.

## Baselines
Minimum:
A deterministic resolver;
B current HIVE/generative structured path where applicable;
C candidate provider/path;
D shadow optimized variant where applicable.

## Reproducibility
Store exact command/config/environment metadata sufficient to repeat locally. Large raw artifacts may live in CAS with immutable references.

## Evidence validity
A result becomes STALE when material provider/model, corpus, contract, calibration, architecture, hardware assumption or policy changes.

## Promotion receipt
Promotion per decision kind references exact corpus/run/evidence hashes and records allowed maturity/control state.

## Gates
critical false AUTO=0 in governed critical fixtures;
fixture mutation during comparison=0;
cross-project evidence leakage=0;
missing baseline disguised as improvement=0;
single-run noisy percentage marketed as universal=0.

## Stop condition
WO-1.1 benchmark implementation must not invent a competing evidence format.
