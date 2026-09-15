export const FULL_PROJECT_CAPABILITIES = [
  "project-intelligence",
  "checkpoint-scope-dod",
  "index-health",
  "latest-commits",
  "run-history",
  "decisions-memory",
  "modules-symbols",
  "dependency-graph",
  "quality-history",
  "retrieval-quality",
] as const;

export const FULL_CHARTS = [
  "tokens-over-time",
  "cached-vs-fresh-tokens",
  "token-savings",
  "cost-over-time",
  "cache-hit-rate",
  "context-reduction",
  "context-signal-ratio",
  "physical-vs-logical-storage",
  "compression-dedup-savings",
  "project-activity",
  "test-pass-failure-rate",
  "retrieval-latency",
  "service-latency-errors",
] as const;

export const FULL_ALERTS = [
  "disk-low",
  "redis-unavailable",
  "postgres-unavailable",
  "project-stale",
  "index-inconsistent",
  "retrieval-degradation",
  "cache-hit-collapse",
  "token-spike",
  "unexpected-cost-spike",
  "failed-test-build",
  "executor-disconnected",
  "checkpoint-mismatch",
] as const;

export const FULL_HEALTH = [
  "platform-resource-health",
  "container-status",
  "local-model-health-conditional",
] as const;
