# WO-1.1-01 — Decision Contract Kernel + Deterministic Resolver

## STATUS
AUTHORIZED EXECUTOR INCREMENT after HIVE 1.1 planning freeze. This WO alone is authorized.

## OBJECTIVE
Implement the smallest production-quality foundation of HIVE Decision Fabric: typed bounded decision contracts plus a deterministic resolver that answers provable decision kinds without an LLM/provider.

## HIVE PREFLIGHT
Before edits:
1. resolve repo root, branch, HEAD and cleanliness with Git;
2. verify installed HIVE 1.0.0 availability/health;
3. use only the available read-only MCP surface: project.list, project.status, context.build, context.search, memory.search, memory.get, checkpoint.read;
4. resolve this /hive project and checkpoint;
5. retrieve canonical context progressively, not the entire repository;
6. record HIVE/Git basis in final evidence.
If HIVE is unavailable, this WO permits DEGRADED_SAFE execution only after recording the failure and directly reading canonical Git sources. Never fake HIVE evidence.

## CANONICAL BASIS
Authority order:
docs/project-brain/13-CHECKPOINT.md
docs/project-brain/16-DECISIONS-LEDGER.md
docs/project-brain/03-SCOPE.md
docs/project-brain/15-DEFINITION-OF-DONE.md
docs/project-brain/04-ARCHITECTURE.md
docs/project-brain/02-REQUIREMENTS.md

Planning contracts to retrieve:
49-DECISION-FABRIC-1.1-PLANNING-FREEZE.md
48-DECISION-FABRIC-1.1-CANONICAL-CROSS-AUDIT.md
47-HIVE-FIRST-EXECUTOR-PROMPT-CONTRACT.md
46-DECISION-FABRIC-EXISTING-SEAM-MAP.md
45-DECISION-FABRIC-BENCHMARK-EVIDENCE-CONTRACT.md
41-SHARED-RUNTIME-EVIDENCE-CONVENTIONS.md
21-DECISION-FABRIC-CONTRACTS-BENCHMARKS.md
20-DECISION-FABRIC-PRE-CODEX-MAP.md
19-DECISION-FABRIC-1.1-SPEC.md

## CONTEXT BUDGET
Use progressive disclosure. Start with canonical governance + files/seams below. Expand only for unresolved contracts, failing tests, proven dependencies or security/data-integrity needs. Record expansion reason.

## SCOPE
A. Typed contract kernel for bounded decisions.
B. Deterministic resolver for explicitly supported deterministic decision kinds.
C. Strict validation/fail-closed behavior.
D. Unit/integration tests appropriate to current repository conventions.
E. Module/test registry updates if the repository deterministically requires them.
F. Documentation/evidence required by existing CI/review workflow.

## OUT OF SCOPE
No Context Projector implementation.
No external/LLM DecisionProvider.
No Jev/OpenJev adapter.
No local scorer.
No Calibration Firewall/Decision Value Router beyond contract seams strictly necessary.
No decision cache/Decision Delta.
No Shadow Comparator.
No Control Center feature.
No new MCP tools.
No new canonical store.
No database migration unless repository inspection proves typed contracts cannot be correctly implemented without durable state. If so, STOP and report the blocker rather than inventing persistence.
No unrelated refactor.

## FILES / SEAMS TO INSPECT
backend/app/context_fingerprints.py
backend/app/delta_context.py
backend/app/provider_prompt_cache.py
backend/app/context_manager.py
backend/app/runner.py
backend/app/execution_orchestrator.py
backend/app/telemetry.py
backend/app/db.py
backend/app/main.py
existing backend tests, deterministic module registry/test map, validation scripts and CI configuration relevant to changed files.

Inspect existing naming/Pydantic/dataclass/error patterns before choosing new filenames. A decision_* module/package is permitted only when consistent with repository conventions.

## REQUIRED CONTRACTS
Create versioned, project-scoped bounded decision types equivalent in semantics to:
decision-contract-v1
decision-input-v1
decision-receipt-v1
Names may follow existing code conventions, but schema/version identity must be explicit and stable.

A decision request must carry at minimum:
decision kind;
declared bounded options;
project identity/scope;
basis/provenance reference or fingerprint fields appropriate to this WO;
contract/schema version;
input needed by the supported deterministic resolver.

A result/receipt must make explicit:
selected declared option or non-success state;
resolver/provider path = deterministic for this WO;
reason/evidence suitable for audit;
contract/schema version;
project/basis binding;
no implied canonical/destructive authority.

Do not add confidence as authority in this WO.

## DETERMINISTIC RESOLVER
Implement a registry/dispatch pattern that is explicit and closed-world for supported deterministic kinds. Do not build a general expression language or arbitrary code execution.

Initial supported kinds should be derived from existing repository needs and fixtures, prioritizing facts provable with exact values, hashes, set membership, policy/static metadata or other pure deterministic inputs.

Requirements:
- same valid input produces same normalized result;
- selected value must be one of declared options when selection succeeds;
- malformed request fails closed;
- undeclared option can never be emitted;
- unknown decision kind returns explicit unsupported/non-success behavior, not guessed semantic inference;
- no network/provider/LLM call;
- no filesystem mutation;
- no canonical write;
- no subprocess execution unless an existing deterministic primitive is strictly required and already policy-governed. Prefer pure functions for WO-01.

## ARCHITECTURE RULES
Preserve all accepted ADRs.
Deterministic before LLM.
Provider independent.
No duplicate context/retrieval/cache/event/policy infrastructure.
ToolPolicy remains authoritative.
Git/PostgreSQL/CAS canonical responsibilities unchanged.
Redis remains noncanonical.
Derived summaries/memory never override canonical source.
Project isolation is mandatory.

## CONSTRAINTS
Keep implementation small and composable for WO-02/03.
Do not over-design future providers.
Do not add dependencies without demonstrated necessity.
Do not change public API/MCP surface unless strictly required by acceptance criteria. Default is no public API change in WO-01.
Do not change VERSION or release tag.
Do not merge to main.
Do not implement later WOs opportunistically.

## ACCEPTANCE CRITERIA
AC01 versioned typed request/result/receipt contracts exist and validate.
AC02 bounded declared options are mandatory and normalized deterministically.
AC03 malformed/empty/duplicate-invalid option structures fail closed according to chosen documented semantics.
AC04 deterministic resolver supports an explicit finite registry of decision kinds.
AC05 unknown kind never falls back to semantic/model inference.
AC06 successful selection is always a declared option.
AC07 resolver performs zero LLM/provider calls.
AC08 no new canonical database/cache/event bus/context manager is created.
AC09 project/basis/provenance binding is represented sufficiently for later fingerprint/evidence integration.
AC10 no decision result grants canonical/destructive/security authority.
AC11 tests cover happy path, malformed input, unsupported kind, undeclared-output defense, determinism/repeatability and project isolation/binding semantics where applicable.
AC12 existing relevant regression suite remains green.
AC13 lint/typecheck/build/validation required by repository for touched surfaces pass.
AC14 no migration unless this WO stops with a justified blocker.
AC15 final evidence is complete in Brazilian Portuguese.

## TESTS
Run the narrow new tests first.
Then run all directly impacted backend tests.
Run repository-prescribed validation/lint/typecheck/build for touched components.
Run deterministic module/test-map checks if present.
Run broader regression required by existing CI before declaring completion.
If Docker/integration is required by current repository validation for these files, run it and report exact results. Do not claim tests not executed.

## EVIDENCE
Capture exact start/end HEAD, branch, git status, HIVE preflight, canonical sources retrieved, context expansion, changed files, test commands/results, lint/typecheck/build, failures fixed, dependency changes, migration status, diff summary and pending risks.
Report any available HIVE token/context telemetry, but do not invent unavailable metrics.

## DELIVERABLES
Implementation and tests only for WO-1.1-01.
Required repository documentation/registry evidence for changed modules.
Final executor review in Brazilian Portuguese.
Proposed checkpoint update text, but do not falsely claim canonical approval/merge.

## REVIEW FORMAT PT-BR
1. Resumo.
2. HIVE preflight e contexto utilizado.
3. Git basis.
4. Arquivos criados/alterados.
5. Decisões locais de implementação.
6. Critérios de aceitação AC01-AC15 com PASS/FAIL + evidência.
7. Testes e resultados exatos.
8. Lint/typecheck/build/validate/integration.
9. Erros encontrados e corrigidos.
10. Segurança, isolamento e integridade.
11. Migração/dependências.
12. Riscos/pendências.
13. Diff/evidências.
14. Atualização proposta do checkpoint.
15. STOP CONDITION.

## STOP CONDITION
Stop when WO-1.1-01 alone is implemented and all applicable AC01-AC15 are evidenced.
Do not start WO-1.1-02.
Do not merge.
If any critical/high-severity defect, architecture conflict, required migration surprise, canonical-source conflict or inability to prove acceptance remains, stop and report BLOCKED/FAIL with evidence.
