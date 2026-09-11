/**
 * Mirror of the canonical telemetry event vocabulary declared by
 * backend/app/telemetry.py (CANONICAL_EVENT_TYPES).
 *
 * The SSE transport emits named events, so the browser EventSource API needs
 * one listener per canonical type. Drift between this mirror and the backend
 * vocabulary is guarded by ControlCenter.test.tsx, which parses the backend
 * source and asserts parity; in addition, every reconnect reconciles through
 * the durable replay endpoint, so an event that is missing a named listener is
 * still recovered from canonical PostgreSQL storage.
 */
export const CANONICAL_EVENT_TYPES = [
  "project.discovered",
  "project.indexing",
  "task.ingested",
  "context.started",
  "context.retrieved",
  "context.built",
  "cache.hit",
  "cache.miss",
  "executor.started",
  "tool.called",
  "file.changed",
  "test.started",
  "test.finished",
  "validation.failed",
  "validation.passed",
  "memory.staged",
  "memory.promoted",
  "run.completed",
  "run.failed",
] as const;