# HIVE — Executor Prompt Optimization Contract

## Status
PLANNING CANDIDATE. Applies to Codex/executor work orders after the current planning gate is frozen.

## Objective
Every implementation prompt must use the installed HIVE as an active context/retrieval/checkpoint layer, not merely mention HIVE in prose. The executor should spend model tokens on implementation reasoning that deterministic repository intelligence and HIVE cannot answer reliably.

## HIVE-first preflight
Before changing code, the executor must:
1. resolve repository root, Git branch/HEAD and cleanliness deterministically;
2. verify HIVE availability/health through the installed integration;
3. use HIVE read-only MCP capabilities to identify the project and current governed state;
4. read the exact canonical files required by the work order, with checkpoint/decisions/scope/DoD/architecture precedence;
5. build/search HIVE context for the approved increment instead of indiscriminately loading the repository;
6. inspect Git/AST/static sources directly for deterministic questions;
7. record the context basis/fingerprint or equivalent evidence exposed by HIVE.

## Stable MCP surface for current baseline
The installed v1.0.0 baseline exposes the governed read-only surface:
project.list
project.status
context.build
context.search
memory.search
memory.get
checkpoint.read

Prompts must not invent unavailable HIVE tools. Canonical writes remain governed through normal repository changes, tests, review and approval.

## Retrieval strategy
Start with progressive disclosure:
L0 project/checkpoint status;
L1 relevant canonical decisions/scope;
L2 module/contracts/seams named by the WO;
L3 exact code/tests/dependencies;
L4 broader context only when evidence shows insufficiency.

Do not load large files/repository trees by default.

## Deterministic-first rule
Use Git, hashes, file metadata, AST/symbol/dependency analysis, test discovery, static analysis and normal code before asking an LLM to infer facts those tools can prove.

## Delta-context rule
For iterative/corrective WOs, retrieve what changed since the prior accepted basis and reuse stable context fingerprints/provider-prefix cache where supported. Do not resend unchanged canonical context merely for completeness.

## Tool gating
Expose/use only tools needed by the increment. HIVE context tools are read-only; implementation tools remain executor-controlled under the WO and repository policy.

## Prompt structure
Every Codex WO must contain:
OBJECTIVE
HIVE PREFLIGHT
CANONICAL BASIS
CONTEXT BUDGET
SCOPE
OUT OF SCOPE
FILES/SEAMS TO INSPECT
REQUIREMENTS
ARCHITECTURE RULES
CONSTRAINTS
ACCEPTANCE CRITERIA
TESTS
EVIDENCE
DELIVERABLES
REVIEW FORMAT PT-BR
STOP CONDITION

## Context budget
Prompts specify a relevance-first budget rather than a request to “read everything”.
The executor may expand context only when:
- a contract/reference cannot be resolved;
- a failing test points outside the initial cone;
- dependency/impact analysis proves an adjacent module is material;
- security/data-integrity review requires it.

Expansion reason must appear in final evidence.

## HIVE autonomy
The executor should not require the user to say “use RAG”, “check memory”, “read checkpoint” or “save tokens”. Those actions are part of the HIVE preflight when applicable.

## Evidence required from executor
Final review in Brazilian Portuguese must report:
- HIVE availability and project resolution;
- Git basis;
- canonical sources actually used;
- HIVE context/search calls or equivalent retrieved-context evidence;
- any context expansion and reason;
- files changed;
- decisions;
- tests/lint/typecheck/build;
- failures fixed;
- pending risks;
- diff/evidence;
- proposed checkpoint update;
- token/context telemetry when HIVE exposes it.

## Failures
If HIVE is unavailable, the executor must not fake HIVE evidence. It may continue only if the WO explicitly permits degraded-safe execution, using canonical files directly and recording the degraded state. A safety/canonical gate that requires HIVE-derived evidence fails closed when that evidence cannot be established.

## Token-economy acceptance
No WO is “optimized” merely because its prompt is short. Optimization means:
high relevant context / low redundant context / deterministic answers before LLM / stable prefix reuse / delta retrieval / no measurable quality loss.

## Anti-patterns
- “Read the entire repo.”
- pasting all canonical docs into every prompt.
- asking Codex to rediscover architecture already frozen.
- using HIVE memory as canonical truth.
- letting retrieved summaries override Git/canonical docs.
- duplicate repository-wide searches when HIVE/Git already proved the answer.
- treating cached context as valid after basis fingerprint changes.

## HIVE self-hosting loop
As HIVE evolves, new releases may improve the executor workflow used to build subsequent releases. New capabilities may enter prompt generation only after they are released/validated. A prompt for release N must not assume unreleased release N capabilities already exist.

## Stop condition
No post-1.0 Codex implementation prompt is issued without this HIVE-first structure unless an explicit audited exception explains why HIVE cannot materially assist the work.
