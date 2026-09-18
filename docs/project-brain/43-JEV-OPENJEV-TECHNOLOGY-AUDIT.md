# HIVE — Jev / OpenJev Technology Audit

## Status
RESEARCH AUDIT. External technology remains non-authoritative until benchmarked inside HIVE.

## Sources reviewed
Public repositories/docs current on 2026-09-18:
- Brainwires/jevwire, a harness around TypeSafe AI Jev.
- daseinlabs/open-jev, local MLX option scoring.
- TheoLeeCJ/openjev, local CUDA/open-model reproduction research.

## What Jev actually contributes
The useful primitive is not generic generation. It is bounded semantic decision scoring:
state + declared questions/options -> probability distribution/confidence, with no free-form answer generation.

Useful architecture patterns:
1. typed bounded decisions;
2. code before model;
3. deterministic prefilters;
4. probability/confidence returned as data;
5. policy overrides after model output;
6. harness-boundary checks rather than optional agent calls;
7. shared-state/prefix computation;
8. no decoding for local/open reproductions;
9. explicit escalation for uncertainty;
10. provider-agnostic DecisionModel seam in jevwire.

## Important limitations
- TypeSafe Jev is an external API dependency for jevwire.
- Jev is not a substitute for arithmetic, ordering, deterministic checks or multi-hop reasoning.
- jevwire explicitly describes its judgment layer as advisory, not a security boundary.
- jevwire hook behavior is intentionally fail-open on API/runtime failure; that is incompatible with HIVE hard safety/canonical gates if copied literally.
- open reproductions show that raw local option scoring is not automatically calibrated like a specialized decision model.
- daseinlabs reports a zero-shot Gemma example that routes correctly but disagrees strongly on judgment/calibration.
- TheoLeeCJ reports local Qwen direct-logit speed benefits but also quality gaps and argmax changes on experimental prefix-reuse paths.

## Measured external evidence worth reproducing
### daseinlabs/open-jev
Reported M5 Pro example, 202-token context, 8 options:
- prefix cached + batched options: ~0.17 s median;
- context re-encoded per option: ~0.68 s.
Its synthetic benchmark is intentionally easy and is not enough for HIVE promotion.

### TheoLeeCJ/openjev
Reported RTX 3090 same-model experiment, 21 binary criteria:
- direct typed logits: 1.023 s median, 0 generated output tokens;
- compact autoregressive JSON: 5.332 s median, 111 output tokens;
- choices agreed on 18/21, so speed does not prove semantic equivalence.
Reported 37x21 workload:
- fresh direct scoring 2.33 decisions/s;
- serial prefix reuse 10.75 decisions/s;
- parallel suffixes 20.03 decisions/s;
but fast BF16 reuse changed 5-6/777 argmaxes versus fresh scoring.

## License / integration
The reviewed open repositories expose MIT-licensed code according to their public repository documentation. Model weights and external services retain their own terms. HIVE must pin exact upstream/revision and recheck licenses before code adoption.

## HIVE comparison
HIVE's planned Decision Fabric already contains the broader control architecture:
- deterministic prefilter;
- typed Decision Contract;
- DecisionProvider adapter;
- escalation policy;
- evidence-weighted escalation;
- decision fingerprint/cache/delta;
- Confidence Debt;
- shadow mode;
- sensitive-action boundary;
- telemetry/benchmark;
- canonical-governance precedence.

Therefore HIVE should not depend on Jev as its architecture. Jev-compatible scoring is one provider candidate behind DecisionProvider.

## Adopt
- typed bounded option scoring;
- provider-agnostic decision interface;
- deterministic prefilter before semantic scoring;
- batch decisions;
- prefix/shared-state optimization experiments;
- explicit distributions and uncertainty;
- code-owned policy overrides;
- zero-generation local decision path as a benchmark target.

## Do not copy
- external API as mandatory core dependency;
- fail-open semantics for HIVE hard gates;
- confidence as proof;
- semantic scoring for deterministic questions;
- automatic trust in raw local logits/calibration;
- agent-optional MCP checks for mandatory policy.

## New HIVE research track: HIVE Decision Microkernel (HDM)
Provider-independent bounded-decision runtime:
1. deterministic resolver;
2. local scorer adapter;
3. remote specialized scorer adapter;
4. ordinary structured-output LLM fallback;
5. policy kernel;
6. calibration layer;
7. evidence/provenance;
8. shadow comparator.

The runtime selects the cheapest valid path, but policy/canonical authority remains outside the scorer.

## New HIVE technology: Calibration Firewall
A provider's raw confidence cannot directly become AUTO. HIVE maps raw distributions through provider+decision-kind calibration evidence. Unknown/stale calibration lowers authority to REVIEW/ESCALATE.

## New HIVE technology: Decision Value Router
Choose deterministic/local/remote/generative path from:
risk + uncertainty + evidence quality + expected context cost + latency/resource budget + calibration validity.
Mandatory safety checks cannot be skipped for economy.

## New HIVE technology: Shared-State Decision Pack
Compile one bounded state capsule and evaluate multiple independent typed decisions against it. Initially SHADOW because external research shows reuse can change decisions.

## Benchmark required inside HIVE
Frozen fixture families:
- deterministic-answer controls;
- bounded semantic routing;
- evidence support/contradiction/not-addressed;
- missing-evidence;
- adversarial/injection;
- stale evidence;
- cross-project isolation;
- safety-sensitive gates;
- retry/next-step;
- domain profiles.

Compare:
A deterministic only;
B HIVE existing generative/structured baseline where applicable;
C Jev remote if credentials explicitly available;
D local direct-logit scorer compatible with user's hardware;
E shared-state/batched variant.

Measure:
balanced accuracy/F1 or task-appropriate quality;
ECE/Brier/calibration where probabilities matter;
critical false AUTO;
review/escalation rate;
fresh/cached/output tokens;
context bytes;
latency p50/p95;
CPU/RAM/GPU/VRAM;
cost;
provider failures;
decision stability.

## Hardware note
The public local examples reviewed use Apple M5 Pro or RTX 3090-class hardware and 4B models. They do not prove suitability for the user's RTX 5050 8 GB. HIVE must benchmark a smaller/quantized local scorer on target hardware rather than assume 4B BF16 viability.

## Maturity disposition
- Jev-compatible remote provider: SCREENED, optional.
- local direct-logit scorer: LAB_CANDIDATE.
- shared-state/prefix scoring: LAB_CANDIDATE / SHADOW mandatory.
- Calibration Firewall: LAB_CANDIDATE.
- Decision Value Router: LAB_CANDIDATE.
- Shared-State Decision Pack: LAB_CANDIDATE.

## Decision
No external Jev implementation becomes a mandatory HIVE dependency. HIVE adopts the bounded-decision architecture patterns and benchmarks providers behind its own DecisionProvider contract.

## Stop condition
Jev research can influence 1.1 freeze only after HIVE-owned fixtures compare quality, calibration, economy and safety. External speed/token claims alone cannot promote the provider.
