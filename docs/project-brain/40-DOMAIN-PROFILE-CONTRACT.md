# HIVE V2 — Domain Profile Contract

## Status
PLANNING CANDIDATE.

## Objective
Allow one HIVE core to adapt context, verification, security, resource and evidence policy to materially different software domains without forking the architecture.

## Principle
A Domain Profile is a compact behavioral adapter. It may strengthen or specialize shared policy, but may not weaken canonical governance, project isolation, security boundaries or mandatory release gates.

## DP-01 Profile identity
Each profile declares id, version, supported project signals, applicability confidence, parent/shared profile, compatibility range and provenance.

## DP-02 Detection
Prefer deterministic evidence: manifests, languages, frameworks, package files, schemas, infra and repository structure. Ambiguous detection returns UNKNOWN and requests/uses explicit project configuration rather than guessing.

## DP-03 Context policy
Profile may prioritize relevant source classes, HUE relations, documentation and tests while C3 remains the compiler and authority-aware budget owner.

## DP-04 Verification policy
Profile adds domain-specific proof obligations to Test Intelligence and Orchestration.

## DP-05 Security/risk
Profile maps domain hazards into STANDARD/ELEVATED/CRITICAL assurance without reducing global hard constraints.

## DP-06 Resource policy
Profile may tune local CPU/RAM/GPU/VRAM/disk work classes through Resource Intelligence.

## DP-07 Evidence
Every profile-derived decision records profile id/version and why it applied.

## Initial profiles
### WEB2_SAAS_API
API/schema compatibility, migrations, auth boundaries, frontend/backend contracts, accessibility/performance where applicable.

### FINTECH_TRADING
Numeric precision, deterministic calculations, time/order semantics, replay, idempotency, exchange/broker adapters, loss/risk boundaries, auditability. Elevated by default for money-moving or order-executing paths.

### WEB3_DAPP
Smart-contract invariants, chain/network identity, signing/key boundaries, RPC assumptions, reorg/finality semantics, transaction simulation and contract security. Critical controls for key/custody/value-moving paths.

### GAME_SYSTEMS
Determinism where required, simulation/state transitions, save compatibility, performance/frame/resource budgets, asset/code boundaries, networking/anti-cheat where applicable.

### AI_LLM_APP
Provider/model identity, prompt/tool boundaries, eval datasets, nondeterminism, structured-output contracts, token/cost/latency, injection/untrusted context and degraded-provider mode.

### UADS
Core software-quality integration profile. UADS evidence plugs into verification/evidence contracts without becoming a second source of canonical truth.

### UGAS
IMPORTANT integration profile. Media/runtime-specific resources, asset provenance and generation workflows are extension contracts; full UGAS runtime is not a generic 2.0 blocker.

## DP-08 Composition
Projects may compose profiles, e.g. WEB3_DAPP + AI_LLM_APP. Conflicting constraints resolve toward stronger safety/verification; unresolved conflicts block rather than silently choose.

## DP-09 Project DNA relation
Project DNA/Adaptive Golden Paths remain IMPORTANT. A Domain Profile is generic and versioned; Project DNA is project-specific learned/configured specialization.

## HIVE-original extensions
- Profile Confidence Envelope: explicit evidence and uncertainty for auto-detection.
- Cross-Domain Hazard Join: composition creates the union of hazards plus interaction hazards.
- Profile Delta Context: send only profile rules material to the current task.
- Profile Proof Receipt: records which domain obligations actually affected verification.

## Gates
cross-project profile leakage=0; silent profile guess on ambiguous project=0; profile weakening hard policy=0; domain-specific required proof omitted after applicable profile=0.

## Stop condition
Profiles are planning-ready when detection, composition, policy hooks, evidence and initial domain verification obligations are implementation-grade and benchmarkable.
