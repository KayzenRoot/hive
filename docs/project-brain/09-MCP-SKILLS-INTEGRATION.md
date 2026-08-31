# 09 - MCP & SKILLS INTEGRATION

HIVE Core provides infrastructure and intelligence; MCP is the universal
interface for agents and IDEs; Skills are compact behavioral instructions; the
Dashboard is the human operational/control plane.

## Initial MCP capability surface

- Project: project.list, project.open, project.status
- Context: context.build, context.search, context.explain
- Memory: memory.search, memory.stage, memory.get
- Code: code.search, code.symbol, code.references, code.dependencies,
  code.changed
- Decisions: decision.search, decision.get
- Checkpoint: checkpoint.read, checkpoint.propose_update
- Run: run.start, run.status, run.events, run.finish
- Validation: validation.record, validation.status
- Telemetry: telemetry.current, telemetry.run

The executor should not receive the whole MCP catalog by default. HIVE selects
tool subsets based on task type, risk, affected subsystem, and execution stage.

## Global skill intent

An HIVE-aware executor inspects the project, resolves checkpoint/context through
HIVE, uses only the next necessary increment, avoids loading repositories
unnecessarily, prefers deterministic evidence, tests and corrects errors,
reports objective validation, stages learned facts, never promotes unverified
claims, and stops at validated acceptance or a blocker.
