# Context Manager Foundation

The Context Manager builds one deterministic `context-capsule-v1` for an
already-resolved `project_id` and durable `task_id`:

```text
POST /api/v1/projects/{project_id}/tasks/{task_id}/context
```

The optional request body accepts only a bounded `top_k` presentation limit.
The service does not accept a free-form retrieval query, persist a capsule,
write memory, invoke an executor or require an LLM.

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
sections. Other sections are selected by deterministic heading/token overlap.
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
`governance_not_git_tracked`/`missing_governance_section` error. Project,
task, source, index, corpus and HEAD mismatches fail closed with a stable
HTTP 404/409 response. Database failures return 503 without host paths or
credentials.

## Non-goals

This foundation does not implement memory lifecycle, adaptive token budgets,
token accounting, full progressive disclosure, fingerprints, delta context,
provider prompt caches, semantic response caches, MCP, planner/router,
executor dispatch, tool execution, telemetry expansion, dashboard UI, local
rerankers, new embedding models, migrations or canonical Project Brain edits.
