# WO-018 Autonomous Execution Foundation

WO-018 adds one bounded coordination seam beyond the Local Verified Runner.
`ExecutionOrchestrator` resolves a durable project and task identity, verifies
the registered repository branch and HEAD, builds the existing checkpoint-first
Context Manager capsule, invokes a replaceable `ExecutorAdapter`, and routes
its structured `ChangeSet` through the existing Runner.

The adapter boundary is provider-independent. A result must contain bounded
structured changes, at least one validation command, and bounded review
metadata. The orchestrator gates every test and validation argv with the
existing `ToolPolicy`, rejects shell executables and canonical Project Brain
paths, rechecks the execution basis immediately before applying an admitted
change, and never performs Git commit, push, merge, checkpoint promotion, or
durable run persistence.

Each staged result captures relative changed files, hashes and a bounded
deterministic diff, sanitized test and validation results, and an executor
review object. Absolute filesystem paths and secret-shaped values are removed
from serialized evidence. Validation failures are retained as evidence with a
`VALIDATION_FAILED` status after the staged change; malformed output, unsafe
identity/state, tool rejection, canonical mutation, or HEAD races fail closed
before mutation.

The deterministic integration fixture in
`scripts/autonomous_execution_integration.py` registers a temporary project
and task through the running HIVE services, obtains a real Context Manager
capsule, uses a local no-network adapter, stages one coding change through the
Runner, and emits `tmp/integration-logs/autonomous-execution.json`. The file
uses the closed `autonomous-execution-v1` contract consumed by Review Evidence.

This increment is deliberately not full autonomy, telemetry, Control Center,
cloud execution, or canonical promotion. External governance remains required
for any later Git or checkpoint action.

## Production executor status

HIVE's orchestration boundary is provider-independent. The deterministic local adapter used by integration evidence proves staging, identity, governance, tool gating and review evidence, but it MUST NOT be interpreted as proof that a production LLM/provider transport is configured.

HIVE now includes a concrete, replaceable OpenAI-compatible HTTP `ExecutorAdapter` for production execution. It is disabled by default and configured only through `HIVE_EXECUTOR_ENABLED`, `HIVE_EXECUTOR_BASE_URL`, `HIVE_EXECUTOR_MODEL`, optional `HIVE_EXECUTOR_API_KEY`, timeout and response-size bounds. `ExecutionOrchestrator.execute_configured()` is the production wiring point. The adapter performs one bounded provider/LLM request, requires structured JSON changes plus test and validation commands, and routes the result through the same Runner admission, tool gating, diff capture and noncanonical staging path. Provider errors, malformed responses, model mismatches and oversized responses fail closed without exposing credentials.

CI proves the concrete network transport against a local HTTP provider fixture, including request shape and call accounting. It does not claim that a third-party provider credential was exercised in CI. A deployment with the executor disabled or incompletely configured remains explicitly unavailable rather than silently falling back to a deterministic fixture.

Provider prompt-cache accounting is disabled by default. When the configured OpenAI-compatible executor and `HIVE_EXECUTOR_PROMPT_CACHE_ENABLED` are both enabled, HIVE sends the versioned stable-prefix/dynamic-suffix envelope and accepts cached-input tokens only from a provider usage receipt. Missing or malformed usage remains `UNKNOWN`; repeated fingerprints, eligibility and estimated HIVE tokens never become a cache hit by themselves.

Execution success is fail-closed across both command classes: every declared test command and every declared validation command must succeed. A failed or timed-out test prevents a `STAGED` success even when later validation commands pass; the run remains staged evidence with `VALIDATION_FAILED` status for external review.

This distinction is a correctness requirement for v1.0.x maintenance: fixture evidence proves the orchestration seam, while provider E2E evidence is a separate operational capability.
