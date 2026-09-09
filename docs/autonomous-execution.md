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
