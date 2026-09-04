# Context Manager Foundation

The Context Manager builds one deterministic `context-capsule-v1` for an
already-resolved `project_id` and durable `task_id`:

```text
POST /api/v1/projects/{project_id}/tasks/{task_id}/context
```

The optional request body accepts a bounded `top_k` presentation limit and an
optional `disclosure_level` (`L0`-`L5`). Invalid levels are rejected. The
service does not accept a free-form retrieval query, persist a capsule, write
memory, invoke an executor or require an LLM.

## Source ordering and authority

The target registered Git repository is the only governance source. The
following tracked paths are processed in this order:

1. `docs/project-brain/13-CHECKPOINT.md`
2. `docs/project-brain/03-SCOPE.md`
3. `docs/project-brain/15-DEFINITION-OF-DONE.md`
4. `docs/project-brain/04-ARCHITECTURE.md`
5. `docs/project-brain/16-DECISIONS-LEDGER.md`

The HIVE contract is defined by the
[checkpoint](project-brain/13-CHECKPOINT.md),
[scope](project-brain/03-SCOPE.md),
[Definition of Done](project-brain/15-DEFINITION-OF-DONE.md),
[architecture](project-brain/04-ARCHITECTURE.md), and
[decisions ledger](project-brain/16-DECISIONS-LEDGER.md).

The checkpoint is emitted first and always includes bounded `STATUS`,
`VERSION`, `PHASE`, `OBJECTIVE`, `IN PROGRESS`, `BLOCKERS` and `NEXT STEP`
sections. A successful capsule then includes at least one excerpt from
`SCOPE`, `DEFINITION_OF_DONE`, `ARCHITECTURE` and `DECISIONS` in that
authority order. Optional extra sections are added only after this mandatory
coverage, using leftover excerpt slots and leftover character budget, and
cannot displace a mandatory kind. Character budget is reserved for the four
later mandatory kinds before checkpoint extras or optional excerpts spend it.
If mandatory coverage cannot fit the fixed bounds, assembly fails closed.
Excerpts preserve their source text, path, content SHA-256, Git blob SHA,
repository HEAD and line/character ranges.

Canonical governance is authoritative. Task text is explicitly
`TASK_INPUT_NONCANONICAL`; task-derived constraints and acceptance criteria are
parsed only from headings with those exact meanings. Retrieval results are
`REPOSITORY_RETRIEVAL_EVIDENCE`. Task text cannot change governance ordering or
authority.

## Query and retrieval

The retrieval query is formed from bounded task title, leading task text and
explicit task sections, then normalized through the existing lexical query
contract (maximum 512 characters). The Context Manager calls the existing
rerank service seam, which owns hybrid/semantic behavior and fallback policy.
Reranking or semantic retrieval may safely return their existing disabled,
unconfigured, provider-error or stale states.

## Progressive disclosure

After reranked retrieval, the capsule applies a deterministic L0-L5
disclosure decision:

- L0 Project capsule
- L1 Module summaries
- L2 Symbol signatures and dependency metadata
- L3 Relevant implementation excerpts
- L4 Complete file
- L5 Repository-wide investigation

The starting level uses every explicit signal already available: title,
constraints, full task text including acceptance criteria, requested
`disclosure_level` (a floor, never a no-op), and resolved file/symbol/test
evidence when the task is an implementation task that would otherwise stay
at L0. Escalation happens only after that initial selection, when the
current level cannot materialize required signatures or excerpts. Each step
records `from_level`, `to_level`, a machine-readable reason and bounded
evidence, then stops at the first sufficient level and never exceeds L5.
Per-level item/character bounds are fixed and conservative. L1 emits
deterministic module summaries from the Git snapshot; L2 emits Python
signatures and import dependency edges. L4 resolves complete files from
literal paths or project-scoped retrieval/symbol evidence and never claims
success with an empty payload. `total_emitted_context_characters` includes
this disclosure payload without double-counting retrieval snippets.

## Fixed bounds

- Task excerpt: 4,000 characters.
- Task section items: 20 items, 512 characters per item.
- Governance: 1,600 characters per excerpt, 12 excerpts and 12,000 total
  characters.
- Retrieval: candidate pool of 10, at most 5 emitted results and 6,000 total
  snippet characters.
- Serialized capsule: 24,000 characters, checked after serialization.

Every bounded section exposes counts and truthful truncation flags. An
oversized serialized capsule is rejected rather than silently emitted.

## Consistency and failures

Before assembly, the project must be accessible and in a usable `READY` or
`ACTIVE` state; its current Git HEAD must match the registered HEAD, the latest
index must be complete for that HEAD, and the current retrieval corpus must
refer to that index. The stable Git snapshot and task/index/corpus identities
are checked again before returning the capsule.

Missing or untracked governance returns a bounded
`governance_not_git_tracked`/`missing_governance_section` error. Missing
mandatory coverage returns `mandatory_governance_coverage_missing`; coverage
that cannot fit the fixed bounds returns
`mandatory_governance_coverage_unsatisfiable`. Project, task, source, index,
corpus and HEAD mismatches fail closed with a stable HTTP 404/409 response.
Database failures return 503 without host paths or credentials.

## Non-goals

This foundation does not implement memory lifecycle, adaptive token budgets,
token accounting, fingerprints, delta context, provider prompt caches,
semantic response caches, MCP, planner/router, executor dispatch, tool
execution, telemetry expansion, dashboard UI, local rerankers, new embedding
models, migrations or canonical Project Brain edits.
