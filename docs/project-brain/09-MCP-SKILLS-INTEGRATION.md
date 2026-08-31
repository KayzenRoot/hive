# 09 — MCP & SKILLS INTEGRATION

## Separation of responsibilities

### HIVE Core
Actual infrastructure and intelligence.

### MCP
Universal interface for agents and IDEs.

### Skills
Compact behavioral instructions teaching an executor when/how to use HIVE.

### Dashboard
Human operational/control plane.

## Initial MCP capability surface

### Project
- project.list
- project.open
- project.status

### Context
- context.build
- context.search
- context.explain

### Memory
- memory.search
- memory.stage
- memory.get

### Code
- code.search
- code.symbol
- code.references
- code.dependencies
- code.changed

### Decisions
- decision.search
- decision.get

### Checkpoint
- checkpoint.read
- checkpoint.propose_update

### Run
- run.start
- run.status
- run.events
- run.finish

### Validation
- validation.record
- validation.status

### Telemetry
- telemetry.current
- telemetry.run

## Tool gating

The executor should not receive the whole MCP catalog by default.

HIVE selects tool subsets based on:
- task type;
- risk;
- affected subsystem;
- execution stage.

## Global skill intent

A HIVE-aware coding executor should:

1. inspect the existing project before implementation;
2. resolve checkpoint and context through HIVE;
3. use only the next necessary increment;
4. avoid loading entire repositories unnecessarily;
5. prefer deterministic evidence;
6. test and correct errors;
7. report objective validation;
8. stage relevant learned facts;
9. never promote unverified claims into canonical memory;
10. stop when acceptance criteria are met or a blocker is reached.
