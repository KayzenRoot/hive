# GEF V1 Machine Evidence Specification — HIVE

## Principle

Machine evidence is primary. Human review summaries should be derived from structured evidence where practical.

## Manifest shape

```json
{
  "schemaVersion": "gef-evidence-v1",
  "workOrder": "...",
  "projectFingerprint": "...",
  "baseSha": "...",
  "headSha": "...",
  "taskClass": "T0|T1|T2|T3",
  "contextRadius": "C0|C1|C2|C3|C4",
  "changedFiles": [],
  "proofs": {},
  "tests": [],
  "evals": {},
  "gates": {},
  "resolvedFindings": [],
  "openFindings": [],
  "telemetry": {},
  "stopState": "..."
}
```

## Evidence rules

- Bind governed evidence to exact `baseSha` and `headSha`.
- Record exit code/status and artifact/receipt identity for executed checks.
- Record `UNKNOWN`/`UNAVAILABLE` when the runtime does not expose a metric.
- Never synthesize provider usage, cached usage, cost, reviewer verdicts or receipts.
- HIVE secrets, absolute host paths and cross-project payloads are forbidden.
- Gate receipts should live in hosted checks/artifacts/comments rather than source commits where possible.
- A derived human report does not become canonical product truth.

## Proof state

Each proof has one state:

- `PROVEN`: executed against compatible inputs/current exact head where required.
- `CARRY_FORWARD`: not re-executed, but all declared relevant inputs remain compatible under shadow policy.
- `INVALIDATED`: a relevant input changed; fresh proof required.
- `UNKNOWN`: insufficient evidence.
- `NOT_REQUIRED`: explicitly outside the current bounded change.

During HIVE GEF shadow assurance, `CARRY_FORWARD` is observational only and does not permit skipping an otherwise mandatory hosted gate.

## Gate receipts

Current hosted gate names are `Validate`, `Integration health`, `Review Evidence`. Receipts must include head SHA and hosted run/artifact/comment identity. HEDS adds the exact-head semantic verdict separately.

## Human report generation

A human report should summarize manifest identity, delta, invalidated proofs, tests/evals, gate receipts, findings and final verdict. It must not add unsupported facts.
