import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";

import { API_BASE_URL } from "./config";
import ControlCenterFull from "./ControlCenterFull";
import { CANONICAL_EVENT_TYPES } from "./eventVocabulary";
import { formatDateTime, formatTimestamp, shortId } from "./format";

/**
 * Operational core of the HIVE Control Center.
 *
 * The component composes the eight canonical operational surfaces from the
 * real bounded Control Center API, the durable project event replay and the
 * existing project SSE transport. It never fabricates metrics: values that are
 * not present in sanitized telemetry are rendered as UNAVAILABLE instead of
 * zero, and estimated values carry an explicit ESTIMATED marker.
 */

export type ControlViewId =
  | "fleet"
  | "project"
  | "full"
  | "runs"
  | "health"
  | "tests"
  | "errors";

type ProjectOption = {
  project_id: string;
  label: string;
};

export type ControlCenterProps = {
  selectedProjectId: string;
  onSelectProject: (projectId: string) => void;
};

type FleetStateCounts = {
  offline: number;
  stale: number;
  indexing: number;
  ready: number;
  active: number;
  degraded: number;
  blocked: number;
};

type ProjectHeadline = {
  project_id: string;
  name: string;
  relative_path: string;
  state: string;
  git_branch: string | null;
  git_head_sha: string | null;
  short_head: string | null;
  detached_head: boolean;
  repository_accessible: boolean;
  working_tree_clean: boolean | null;
  language_stack: string[];
  inspection_error: string | null;
  last_inspected_at: string;
  updated_at: string;
};

type FleetResponse = {
  generated_at: string;
  project_count: number;
  state_counts: FleetStateCounts;
  projects: ProjectHeadline[];
  truncated: boolean;
  max_projects: number;
  offset: number;
  limit: number;
  has_more: boolean;
  next_offset: number | null;
};

type RunStatus = "ACTIVE" | "COMPLETED" | "FAILED" | "OBSERVED";

type RunSummary = {
  run_id: string;
  status: RunStatus;
  stage: string;
  last_event_type: string;
  last_event_at: string;
  first_event_at: string;
  event_count: number;
};

type EventEnvelope = {
  event_id: string;
  envelope_version: string;
  event_type: string;
  project_id: string;
  task_id: string | null;
  run_id: string | null;
  ordering_id: number;
  occurred_at: string;
  payload: Record<string, unknown>;
  provenance: Record<string, unknown>;
  cursor: string;
};

type EventPage = {
  events: EventEnvelope[];
  next_cursor: string | null;
  has_more: boolean;
  limit: number;
};

type EventWindow = {
  scanned_events: number;
  max_events: number;
  truncated: boolean;
};

type RunsResponse = {
  generated_at: string;
  project_id: string;
  active: RunSummary[];
  recent: RunSummary[];
  truncated: boolean;
  window: EventWindow;
};

type RunDetailResponse = {
  generated_at: string;
  project_id: string;
  run: RunSummary;
  task_id: string | null;
  executor_identity: string | null;
  timeline: EventEnvelope[];
  timeline_truncated: boolean;
  max_timeline_events: number;
};

type TestStatusValue = "PASSED" | "FAILED" | "RUNNING" | "UNRECORDED";

type TestRunStatus = {
  run_id: string;
  status: TestStatusValue;
  test_started: number;
  test_finished: number;
  validation_passed: number;
  validation_failed: number;
  last_event_type: string;
  last_event_at: string;
};

type TestStatusResponse = {
  generated_at: string;
  project_id: string;
  window: EventWindow;
  runs: TestRunStatus[];
  runs_without_test_telemetry_in_window: number;
  last_validation_event_at: string | null;
};

type WarningItem = {
  severity: "ERROR" | "WARNING";
  kind: string;
  project_id: string;
  run_id: string | null;
  event_id: string | null;
  occurred_at: string | null;
  summary: string;
};

type ErrorsWarningsResponse = {
  generated_at: string;
  project_id: string;
  window: EventWindow;
  errors: WarningItem[];
  warnings: WarningItem[];
  truncated: boolean;
};

type ControlCenterCheck = {
  status: string;
  details: Record<string, boolean>;
  reason: string | null;
};

type ControlCenterHealth = {
  generated_at: string;
  status: string;
  version: string;
  environment: string;
  migration_head: string;
  canonical_store: string;
  hot_store: string;
  hot_store_canonical: boolean;
  checks: Record<string, ControlCenterCheck>;
  unavailable_metrics: string[];
};

type ProjectDetailResponse = {
  generated_at: string;
  project: ProjectHeadline;
  active_run_count: number;
  recent_runs: RunSummary[];
  recent_runs_truncated: boolean;
  recent_events: EventEnvelope[];
  window: EventWindow;
  tests: TestStatusResponse;
  errors: ErrorsWarningsResponse;
};

type RunOverride = {
  status: "COMPLETED" | "FAILED";
  last_event_type: string;
  last_event_at: string;
};

type StreamState = "idle" | "connecting" | "live" | "reconnecting" | "fallback";

type ReplayWindow = { limit: number; hasMore: boolean };

const CONTROL_VIEWS: { id: ControlViewId; label: string }[] = [
  { id: "fleet", label: "Fleet" },
  { id: "project", label: "Project detail" },
  { id: "full", label: "Full Control Center" },
  { id: "runs", label: "Runs" },
  { id: "health", label: "Platform health" },
  { id: "tests", label: "Tests" },
  { id: "errors", label: "Errors / warnings" },
];

const EVENT_TIMELINE_MAX = 200;
const STREAM_BATCH_SIZE = 100;
const RUN_TIMELINE_MAX = STREAM_BATCH_SIZE;
const FLEET_PAGE_SIZE = 50;
const STREAM_TIMEOUT_SECONDS = 30;
const STREAM_RECONNECT_BASE_MS = 1_000;
const STREAM_RECONNECT_MAX_MS = 8_000;
const STREAM_FAILURES_BEFORE_FALLBACK = 4;
const FALLBACK_POLL_MS = 10_000;
const SNAPSHOT_REFRESH_MS = 30_000;
const RUN_LIMIT = 20;
const EVENT_WINDOW = 50;
const WARNING_LIMIT = 25;
const PAYLOAD_VALUE_MAX_CHARS = 120;
const TIMELINE_PAYLOAD_FIELDS = 4;

const STREAM_LABELS: Record<StreamState, string> = {
  idle: "STREAM IDLE",
  connecting: "STREAM CONNECTING",
  live: "LIVE (SSE)",
  reconnecting: "STREAM RECONNECTING",
  fallback: "FALLBACK (BOUNDED REPLAY POLLING)",
};

const TOKEN_METRIC_KEYS = new Set([
  "input_tokens",
  "output_tokens",
  "cached_tokens",
  "fresh_tokens",
  "token_count",
  "token_budget",
  "token_savings",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isProjectHeadline(value: unknown): value is ProjectHeadline {
  return (
    isRecord(value) &&
    typeof value.project_id === "string" &&
    typeof value.name === "string" &&
    typeof value.relative_path === "string" &&
    typeof value.state === "string" &&
    Array.isArray(value.language_stack)
  );
}

function isFleetResponse(value: unknown): value is FleetResponse {
  return (
    isRecord(value) &&
    isRecord(value.state_counts) &&
    typeof value.project_count === "number" &&
    typeof value.max_projects === "number" &&
    typeof value.truncated === "boolean" &&
    typeof value.offset === "number" &&
    typeof value.limit === "number" &&
    typeof value.has_more === "boolean" &&
    (value.next_offset === null || typeof value.next_offset === "number") &&
    Array.isArray(value.projects) &&
    value.projects.every(isProjectHeadline)
  );
}

function compareCanonicalEvents(left: EventEnvelope, right: EventEnvelope): number {
  return (
    left.ordering_id - right.ordering_id || left.event_id.localeCompare(right.event_id)
  );
}

function boundedRunTimeline(map: Map<string, EventEnvelope>): {
  events: EventEnvelope[];
  dropped: number;
} {
  const ordered = Array.from(map.values()).sort(compareCanonicalEvents);
  const dropped = Math.max(0, ordered.length - RUN_TIMELINE_MAX);
  for (const event of ordered.slice(0, dropped)) map.delete(event.event_id);
  return { events: ordered.slice(dropped), dropped };
}

function isRunSummary(value: unknown): value is RunSummary {
  return (
    isRecord(value) &&
    typeof value.run_id === "string" &&
    typeof value.status === "string" &&
    typeof value.stage === "string" &&
    typeof value.event_count === "number"
  );
}

function isEventEnvelope(value: unknown): value is EventEnvelope {
  return (
    isRecord(value) &&
    typeof value.event_id === "string" &&
    typeof value.event_type === "string" &&
    typeof value.project_id === "string" &&
    typeof value.ordering_id === "number" &&
    typeof value.occurred_at === "string" &&
    typeof value.cursor === "string" &&
    isRecord(value.payload)
  );
}

function isEventWindow(value: unknown): value is EventWindow {
  return (
    isRecord(value) &&
    typeof value.scanned_events === "number" &&
    typeof value.max_events === "number" &&
    typeof value.truncated === "boolean"
  );
}

function isEventPage(value: unknown): value is EventPage {
  return (
    isRecord(value) &&
    Array.isArray(value.events) &&
    value.events.every(isEventEnvelope) &&
    typeof value.has_more === "boolean" &&
    typeof value.limit === "number"
  );
}

function isRunsResponse(value: unknown): value is RunsResponse {
  return (
    isRecord(value) &&
    Array.isArray(value.active) &&
    value.active.every(isRunSummary) &&
    Array.isArray(value.recent) &&
    value.recent.every(isRunSummary) &&
    typeof value.truncated === "boolean" &&
    isEventWindow(value.window)
  );
}

function isRunDetail(value: unknown): value is RunDetailResponse {
  return (
    isRecord(value) &&
    isRunSummary(value.run) &&
    Array.isArray(value.timeline) &&
    value.timeline.every(isEventEnvelope) &&
    typeof value.timeline_truncated === "boolean" &&
    typeof value.max_timeline_events === "number"
  );
}

function isTestRunStatus(value: unknown): value is TestRunStatus {
  return (
    isRecord(value) &&
    typeof value.run_id === "string" &&
    typeof value.status === "string" &&
    typeof value.test_started === "number" &&
    typeof value.test_finished === "number" &&
    typeof value.validation_passed === "number" &&
    typeof value.validation_failed === "number"
  );
}

function isTestStatus(value: unknown): value is TestStatusResponse {
  return (
    isRecord(value) &&
    isEventWindow(value.window) &&
    Array.isArray(value.runs) &&
    value.runs.every(isTestRunStatus) &&
    typeof value.runs_without_test_telemetry_in_window === "number"
  );
}

function isWarningItem(value: unknown): value is WarningItem {
  return (
    isRecord(value) &&
    typeof value.severity === "string" &&
    typeof value.kind === "string" &&
    typeof value.summary === "string"
  );
}

function isErrorsWarnings(value: unknown): value is ErrorsWarningsResponse {
  return (
    isRecord(value) &&
    isEventWindow(value.window) &&
    Array.isArray(value.errors) &&
    value.errors.every(isWarningItem) &&
    Array.isArray(value.warnings) &&
    value.warnings.every(isWarningItem) &&
    typeof value.truncated === "boolean"
  );
}

function isControlCenterHealth(value: unknown): value is ControlCenterHealth {
  return (
    isRecord(value) &&
    typeof value.status === "string" &&
    typeof value.version === "string" &&
    typeof value.environment === "string" &&
    typeof value.migration_head === "string" &&
    typeof value.canonical_store === "string" &&
    typeof value.hot_store === "string" &&
    typeof value.hot_store_canonical === "boolean" &&
    isRecord(value.checks) &&
    Array.isArray(value.unavailable_metrics)
  );
}

function isProjectDetail(value: unknown): value is ProjectDetailResponse {
  return (
    isRecord(value) &&
    isProjectHeadline(value.project) &&
    typeof value.active_run_count === "number" &&
    Array.isArray(value.recent_runs) &&
    value.recent_runs.every(isRunSummary) &&
    Array.isArray(value.recent_events) &&
    value.recent_events.every(isEventEnvelope) &&
    isEventWindow(value.window) &&
    isTestStatus(value.tests) &&
    isErrorsWarnings(value.errors)
  );
}

function apiErrorText(payload: unknown, fallback: string): string {
  if (isRecord(payload) && typeof payload.detail === "string") {
    return fallback + ": " + payload.detail;
  }
  return fallback;
}

function isTokenMetricKey(key: string): boolean {
  return TOKEN_METRIC_KEYS.has(key.toLowerCase());
}

function payloadScalarEntries(
  payload: Record<string, unknown>,
): [string, string | number | boolean][] {
  const entries: [string, string | number | boolean][] = [];
  for (const [key, value] of Object.entries(payload)) {
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
      entries.push([key, value]);
    }
  }
  entries.sort((left, right) => Number(isTokenMetricKey(right[0])) - Number(isTokenMetricKey(left[0])));
  return entries.slice(0, TIMELINE_PAYLOAD_FIELDS);
}

function formatPayloadValue(value: string | number | boolean): string {
  if (typeof value === "string") {
    return value.length > PAYLOAD_VALUE_MAX_CHARS
      ? value.slice(0, PAYLOAD_VALUE_MAX_CHARS - 3) + "..."
      : value;
  }
  return String(value);
}

function stateSlug(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-");
}

function applyRunOverrides(
  runs: RunSummary[],
  overrides: Record<string, RunOverride>,
): RunSummary[] {
  return runs.map((run) => {
    const override = overrides[run.run_id];
    if (override === undefined) return run;
    return {
      ...run,
      status: override.status,
      stage: override.last_event_type,
      last_event_type: override.last_event_type,
      last_event_at: override.last_event_at,
    };
  });
}

function overrideOnlyRuns(
  runs: RunsResponse | null,
  overrides: Record<string, RunOverride>,
  events: EventEnvelope[],
): RunSummary[] {
  const known = new Set<string>();
  for (const run of [...(runs?.active ?? []), ...(runs?.recent ?? [])]) known.add(run.run_id);
  const result: RunSummary[] = [];
  for (const [runId, override] of Object.entries(overrides)) {
    if (known.has(runId)) continue;
    const related = events.filter((event) => event.run_id === runId);
    if (related.length === 0) continue;
    const first = related[0];
    if (first === undefined) continue;
    result.push({
      run_id: runId,
      status: override.status,
      stage: override.last_event_type,
      last_event_type: override.last_event_type,
      last_event_at: override.last_event_at,
      first_event_at: first.occurred_at,
      event_count: related.length,
    });
  }
  return result;
}
export default function ControlCenter({
  selectedProjectId,
  onSelectProject,
}: ControlCenterProps) {
  const [view, setView] = useState<ControlViewId>("fleet");
  const [fleet, setFleet] = useState<FleetResponse | null>(null);
  const [fleetLoading, setFleetLoading] = useState(true);
  const [fleetError, setFleetError] = useState<string | null>(null);
  const [fleetOffset, setFleetOffset] = useState(0);
  const [health, setHealth] = useState<ControlCenterHealth | null>(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [detail, setDetail] = useState<ProjectDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [runs, setRuns] = useState<RunsResponse | null>(null);
  const [runsLoading, setRunsLoading] = useState(false);
  const [runsError, setRunsError] = useState<string | null>(null);
  const [tests, setTests] = useState<TestStatusResponse | null>(null);
  const [testsLoading, setTestsLoading] = useState(false);
  const [testsError, setTestsError] = useState<string | null>(null);
  const [errors, setErrors] = useState<ErrorsWarningsResponse | null>(null);
  const [errorsLoading, setErrorsLoading] = useState(false);
  const [errorsError, setErrorsError] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [runDetail, setRunDetail] = useState<RunDetailResponse | null>(null);
  const [runDetailLoading, setRunDetailLoading] = useState(false);
  const [runDetailError, setRunDetailError] = useState<string | null>(null);
  const [runTimeline, setRunTimeline] = useState<EventEnvelope[]>([]);
  const [runTimelineDropped, setRunTimelineDropped] = useState(0);
  const [events, setEvents] = useState<EventEnvelope[]>([]);
  const [droppedEvents, setDroppedEvents] = useState(0);
  const [runOverrides, setRunOverrides] = useState<Record<string, RunOverride>>({});
  const [streamState, setStreamState] = useState<StreamState>("idle");
  const [streamError, setStreamError] = useState<string | null>(null);
  const [replayWindow, setReplayWindow] = useState<ReplayWindow | null>(null);
  const [reconciledAt, setReconciledAt] = useState<string | null>(null);
  const eventsRef = useRef<Map<string, EventEnvelope>>(new Map());
  const cursorRef = useRef<string | null>(null);
  const runTimelineRef = useRef<Map<string, EventEnvelope>>(new Map());
  const selectedRunRef = useRef<string | null>(null);

  const mergeRunTimeline = useCallback((incoming: EventEnvelope[]) => {
    const runId = selectedRunRef.current;
    if (runId === null) return;
    const map = runTimelineRef.current;
    let added = 0;
    for (const event of incoming) {
      if (event.run_id !== runId || map.has(event.event_id)) continue;
      map.set(event.event_id, event);
      added += 1;
    }
    if (added === 0) return;
    const bounded = boundedRunTimeline(map);
    setRunTimeline(bounded.events);
    if (bounded.dropped > 0) {
      setRunTimelineDropped((previous) => previous + bounded.dropped);
    }
  }, []);

  const seedRunTimeline = useCallback((runId: string, seed: EventEnvelope[]) => {
    const map = new Map<string, EventEnvelope>();
    for (const event of seed) {
      if (event.run_id === runId) map.set(event.event_id, event);
    }
    for (const event of runTimelineRef.current.values()) {
      if (event.run_id === runId && !map.has(event.event_id)) {
        map.set(event.event_id, event);
      }
    }
    runTimelineRef.current = map;
    selectedRunRef.current = runId;
    const bounded = boundedRunTimeline(map);
    setRunTimeline(bounded.events);
    setRunTimelineDropped(bounded.dropped);
  }, []);

  const clearRunTimeline = useCallback(() => {
    selectedRunRef.current = null;
    runTimelineRef.current = new Map();
    setRunTimeline([]);
    setRunTimelineDropped(0);
  }, []);

  const applyEvents = useCallback((incoming: EventEnvelope[]) => {
    mergeRunTimeline(incoming);
    const terminalUpdates: { runId: string; event: EventEnvelope }[] = [];
    const map = eventsRef.current;
    let added = 0;
    for (const event of incoming) {
      if (!map.has(event.event_id)) {
        map.set(event.event_id, event);
        added += 1;
      }
      if (
        event.run_id !== null &&
        (event.event_type === "run.completed" || event.event_type === "run.failed")
      ) {
        terminalUpdates.push({ runId: event.run_id, event });
      }
    }
    if (added === 0 && terminalUpdates.length === 0) return;
    const ordered = Array.from(map.values()).sort(compareCanonicalEvents);
    if (ordered.length > EVENT_TIMELINE_MAX) {
      const overflow = ordered.length - EVENT_TIMELINE_MAX;
      for (const event of ordered.slice(0, overflow)) map.delete(event.event_id);
      setDroppedEvents((previous) => previous + overflow);
    }
    const bounded = ordered.slice(Math.max(0, ordered.length - EVENT_TIMELINE_MAX));
    const newest = bounded[bounded.length - 1];
    if (newest !== undefined) cursorRef.current = newest.cursor;
    setEvents(bounded);
    if (terminalUpdates.length > 0) {
      setRunOverrides((previous) => {
        const next = { ...previous };
        for (const { runId, event } of terminalUpdates) {
          next[runId] = {
            status: event.event_type === "run.completed" ? "COMPLETED" : "FAILED",
            last_event_type: event.event_type,
            last_event_at: event.occurred_at,
          };
        }
        return next;
      });
    }
  }, [mergeRunTimeline]);

  const resetOperationalState = useCallback(() => {
    eventsRef.current = new Map();
    cursorRef.current = null;
    setEvents([]);
    setDroppedEvents(0);
    setRunOverrides({});
    setSelectedRunId(null);
    setRunDetail(null);
    setRunDetailError(null);
    setDetail(null);
    setDetailError(null);
    setRuns(null);
    setRunsError(null);
    setTests(null);
    setTestsError(null);
    setErrors(null);
    setErrorsError(null);
    setReplayWindow(null);
    setReconciledAt(null);
    setStreamState("idle");
    setStreamError(null);
    clearRunTimeline();
  }, [clearRunTimeline]);

  const loadFleet = useCallback(
    async (offset?: number) => {
      const targetOffset = offset ?? fleetOffset;
      setFleetLoading(true);
      setFleetError(null);
      try {
        const response = await fetch(
          API_BASE_URL +
            "/api/v1/control-center/fleet?offset=" +
            targetOffset +
            "&limit=" +
            FLEET_PAGE_SIZE,
          { cache: "no-store" },
        );
        const payload: unknown = await response.json();
        if (!response.ok) {
          throw new Error(apiErrorText(payload, "Control Center fleet is unavailable"));
        }
        if (!isFleetResponse(payload)) {
          throw new Error("Control Center fleet payload is outside the bounded contract");
        }
        setFleetOffset(payload.offset);
        setFleet(payload);
      } catch (caught) {
        setFleet(null);
        setFleetError(
          caught instanceof Error ? caught.message : "Control Center fleet is unavailable",
        );
      } finally {
        setFleetLoading(false);
      }
    },
    [fleetOffset],
  );

  const loadHealth = useCallback(async () => {
    setHealthLoading(true);
    setHealthError(null);
    try {
      const response = await fetch(API_BASE_URL + "/api/v1/control-center/health", {
        cache: "no-store",
      });
      const payload: unknown = await response.json();
      if (!isControlCenterHealth(payload)) {
        throw new Error(apiErrorText(payload, "Control Center platform health is unavailable"));
      }
      setHealth(payload);
      if (!response.ok) {
        setHealthError(
          "Platform health reported " +
            payload.status +
            " with a bounded degraded response; no fabricated fallback state is rendered.",
        );
      }
    } catch (caught) {
      setHealth(null);
      setHealthError(
        caught instanceof Error ? caught.message : "Control Center platform health is unavailable",
      );
    } finally {
      setHealthLoading(false);
    }
  }, []);

  const loadDetail = useCallback(async () => {
    if (!selectedProjectId) return;
    setDetailLoading(true);
    setDetailError(null);
    try {
      const response = await fetch(
        API_BASE_URL +
          "/api/v1/control-center/projects/" +
          selectedProjectId +
          "?runs=" +
          RUN_LIMIT +
          "&events=" +
          EVENT_WINDOW +
          "&warnings=" +
          WARNING_LIMIT,
        { cache: "no-store" },
      );
      const payload: unknown = await response.json();
      if (!response.ok) {
        throw new Error(apiErrorText(payload, "Control Center project detail is unavailable"));
      }
      if (!isProjectDetail(payload)) {
        throw new Error("Control Center project detail payload is outside the bounded contract");
      }
      setDetail(payload);
      applyEvents(payload.recent_events);
    } catch (caught) {
      setDetail(null);
      setDetailError(
        caught instanceof Error ? caught.message : "Control Center project detail is unavailable",
      );
    } finally {
      setDetailLoading(false);
    }
  }, [selectedProjectId, applyEvents]);

  const loadRuns = useCallback(async () => {
    if (!selectedProjectId) return;
    setRunsLoading(true);
    setRunsError(null);
    try {
      const response = await fetch(
        API_BASE_URL +
          "/api/v1/control-center/projects/" +
          selectedProjectId +
          "/runs?limit=" +
          RUN_LIMIT,
        { cache: "no-store" },
      );
      const payload: unknown = await response.json();
      if (!response.ok) {
        throw new Error(apiErrorText(payload, "Control Center runs are unavailable"));
      }
      if (!isRunsResponse(payload)) {
        throw new Error("Control Center runs payload is outside the bounded contract");
      }
      setRuns(payload);
    } catch (caught) {
      setRuns(null);
      setRunsError(caught instanceof Error ? caught.message : "Control Center runs are unavailable");
    } finally {
      setRunsLoading(false);
    }
  }, [selectedProjectId]);

  const loadTests = useCallback(async () => {
    if (!selectedProjectId) return;
    setTestsLoading(true);
    setTestsError(null);
    try {
      const response = await fetch(
        API_BASE_URL +
          "/api/v1/control-center/projects/" +
          selectedProjectId +
          "/tests?events=" +
          EVENT_WINDOW +
          "&runs=" +
          RUN_LIMIT,
        { cache: "no-store" },
      );
      const payload: unknown = await response.json();
      if (!response.ok) {
        throw new Error(apiErrorText(payload, "Control Center test status is unavailable"));
      }
      if (!isTestStatus(payload)) {
        throw new Error("Control Center test status payload is outside the bounded contract");
      }
      setTests(payload);
    } catch (caught) {
      setTests(null);
      setTestsError(
        caught instanceof Error ? caught.message : "Control Center test status is unavailable",
      );
    } finally {
      setTestsLoading(false);
    }
  }, [selectedProjectId]);

  const loadErrors = useCallback(async () => {
    if (!selectedProjectId) return;
    setErrorsLoading(true);
    setErrorsError(null);
    try {
      const response = await fetch(
        API_BASE_URL +
          "/api/v1/control-center/projects/" +
          selectedProjectId +
          "/errors?events=" +
          EVENT_WINDOW +
          "&limit=" +
          WARNING_LIMIT,
        { cache: "no-store" },
      );
      const payload: unknown = await response.json();
      if (!response.ok) {
        throw new Error(apiErrorText(payload, "Control Center errors surface is unavailable"));
      }
      if (!isErrorsWarnings(payload)) {
        throw new Error("Control Center errors payload is outside the bounded contract");
      }
      setErrors(payload);
    } catch (caught) {
      setErrors(null);
      setErrorsError(
        caught instanceof Error ? caught.message : "Control Center errors surface is unavailable",
      );
    } finally {
      setErrorsLoading(false);
    }
  }, [selectedProjectId]);

  const loadRunDetail = useCallback(
    async (runId: string) => {
      if (!selectedProjectId) return;
      setSelectedRunId(runId);
      selectedRunRef.current = runId;
      runTimelineRef.current = new Map();
      setRunTimeline([]);
      setRunTimelineDropped(0);
      setRunDetailLoading(true);
      setRunDetailError(null);
      try {
        const response = await fetch(
          API_BASE_URL +
            "/api/v1/control-center/projects/" +
            selectedProjectId +
            "/runs/" +
            runId +
            "?events=" +
            STREAM_BATCH_SIZE,
          { cache: "no-store" },
        );
        const payload: unknown = await response.json();
        if (!response.ok) {
          throw new Error(apiErrorText(payload, "Control Center run detail is unavailable"));
        }
        if (!isRunDetail(payload)) {
          throw new Error("Control Center run detail payload is outside the bounded contract");
        }
        setRunDetail(payload);
        applyEvents(payload.timeline);
        seedRunTimeline(runId, payload.timeline);
      } catch (caught) {
        setRunDetail(null);
        setRunDetailError(
          caught instanceof Error ? caught.message : "Control Center run detail is unavailable",
        );
      } finally {
        setRunDetailLoading(false);
      }
    },
    [selectedProjectId, applyEvents, seedRunTimeline],
  );

  useEffect(() => {
    const initialLoad = window.setTimeout(() => {
      void loadFleet();
      void loadHealth();
    }, 0);
    return () => window.clearTimeout(initialLoad);
  }, [loadFleet, loadHealth]);

  useEffect(() => {
    let cancelled = false;
    void Promise.resolve().then(() => {
      if (!cancelled) resetOperationalState();
    });
    return () => {
      cancelled = true;
    };
  }, [selectedProjectId, resetOperationalState]);

  const activeLoader = useMemo<(() => Promise<void>) | null>(() => {
    if (view === "fleet") return loadFleet;
    if (view === "health") return loadHealth;
    if (!selectedProjectId) return null;
    if (view === "project") return loadDetail;
    if (view === "runs") return loadRuns;
    if (view === "tests") return loadTests;
    return loadErrors;
  }, [view, selectedProjectId, loadFleet, loadHealth, loadDetail, loadRuns, loadTests, loadErrors]);

  useEffect(() => {
    if (activeLoader === null) return;
    void activeLoader();
    const timer = window.setInterval(() => {
      void activeLoader();
    }, SNAPSHOT_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [activeLoader]);

  useEffect(() => {
    if (!selectedProjectId) return;
    let disposed = false;
    let source: EventSource | null = null;
    let reconnectTimer: number | null = null;
    let pollTimer: number | null = null;
    let failures = 0;

    const clearReconnect = () => {
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    };
    const stopPolling = () => {
      if (pollTimer !== null) {
        window.clearInterval(pollTimer);
        pollTimer = null;
      }
    };
    const reconcile = async () => {
      try {
        const response = await fetch(
          API_BASE_URL +
            "/api/v1/projects/" +
            selectedProjectId +
            "/events?limit=" +
            STREAM_BATCH_SIZE,
          { cache: "no-store" },
        );
        const payload: unknown = await response.json();
        if (disposed || !response.ok || !isEventPage(payload)) return;
        applyEvents(payload.events);
        setReplayWindow({ limit: payload.limit, hasMore: payload.has_more });
        setReconciledAt(new Date().toISOString());
      } catch {
        // The bounded reconciliation stays silent; the stream state is the signal.
      }
    };
    const startPolling = () => {
      if (pollTimer !== null) return;
      pollTimer = window.setInterval(() => {
        void reconcile();
      }, FALLBACK_POLL_MS);
    };
    const scheduleReconnect = () => {
      if (disposed) return;
      const delay = Math.min(
        STREAM_RECONNECT_BASE_MS * 2 ** Math.max(0, failures - 1),
        STREAM_RECONNECT_MAX_MS,
      );
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null;
        connect();
      }, delay);
    };
    const connect = () => {
      if (disposed) return;
      if (typeof EventSource === "undefined") {
        setStreamState("fallback");
        setStreamError(
          "This runtime does not expose EventSource; bounded durable replay polling is active.",
        );
        startPolling();
        return;
      }
      setStreamState(failures === 0 ? "connecting" : "reconnecting");
      const url = new URL(API_BASE_URL + "/api/v1/projects/" + selectedProjectId + "/events/stream");
      if (cursorRef.current !== null) url.searchParams.set("after", cursorRef.current);
      url.searchParams.set("max_events", String(STREAM_BATCH_SIZE));
      url.searchParams.set("timeout_seconds", String(STREAM_TIMEOUT_SECONDS));
      const opened = new EventSource(url.toString());
      source = opened;
      opened.onopen = () => {
        failures = 0;
        stopPolling();
        setStreamState("live");
        setStreamError(null);
      };
      const handleEvent = (raw: MessageEvent) => {
        try {
          const parsed: unknown = JSON.parse(String(raw.data));
          if (isEventEnvelope(parsed)) applyEvents([parsed]);
        } catch {
          // A malformed frame is ignored; durable replay reconciles canonical truth.
        }
      };
      for (const eventType of CANONICAL_EVENT_TYPES) {
        opened.addEventListener(eventType, handleEvent as EventListener);
      }
      opened.onerror = () => {
        opened.close();
        if (source === opened) source = null;
        if (disposed) return;
        failures += 1;
        if (failures >= STREAM_FAILURES_BEFORE_FALLBACK) {
          setStreamState("fallback");
          setStreamError(
            "The live SSE stream is unreachable; bounded durable replay polling is active.",
          );
          startPolling();
          void reconcile();
        } else {
          setStreamState("reconnecting");
        }
        scheduleReconnect();
      };
    };

    void (async () => {
      await reconcile();
      if (!disposed) connect();
    })();

    return () => {
      disposed = true;
      clearReconnect();
      stopPolling();
      source?.close();
    };
  }, [selectedProjectId, applyEvents]);

  const handleSelectProject = (projectId: string) => {
    setView(projectId ? "project" : "fleet");
    onSelectProject(projectId);
  };

  const handleTabKeys = (event: KeyboardEvent<HTMLDivElement>) => {
    const ids = CONTROL_VIEWS.map((definition) => definition.id);
    const currentIndex = ids.indexOf(view);
    let nextIndex: number | null = null;
    if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % ids.length;
    else if (event.key === "ArrowLeft") nextIndex = (currentIndex - 1 + ids.length) % ids.length;
    else if (event.key === "Home") nextIndex = 0;
    else if (event.key === "End") nextIndex = ids.length - 1;
    if (nextIndex === null) return;
    event.preventDefault();
    const nextId = ids[nextIndex];
    if (nextId === undefined) return;
    setView(nextId);
    event.currentTarget.querySelector<HTMLButtonElement>("#cc-tab-" + nextId)?.focus();
  };
  const boundedProjectOptions = useMemo<ProjectOption[]>(() => {
    const options: ProjectOption[] = [];
    const seen = new Set<string>();
    const addOption = (
      projectId: string,
      identity: { name: string; relative_path: string } | null,
    ) => {
      if (seen.has(projectId)) return;
      seen.add(projectId);
      options.push({
        project_id: projectId,
        label: identity === null ? projectId : identity.name + " · " + identity.relative_path,
      });
    };
    for (const project of fleet?.projects ?? []) {
      addOption(project.project_id, project);
    }
    if (selectedProjectId !== "" && !seen.has(selectedProjectId)) {
      const selectedIdentity =
        detail !== null && detail.project.project_id === selectedProjectId ? detail.project : null;
      addOption(selectedProjectId, selectedIdentity);
    }
    return options;
  }, [fleet, detail, selectedProjectId]);
  const detailRuns = detail ? applyRunOverrides(detail.recent_runs, runOverrides) : [];
  const detailActiveRuns = detailRuns.filter((run) => run.status === "ACTIVE");
  const detailRecentRuns = detailRuns.filter((run) => run.status !== "ACTIVE");
  const overriddenActiveRuns = runs ? applyRunOverrides(runs.active, runOverrides) : [];
  const overriddenRecentRuns = runs ? applyRunOverrides(runs.recent, runOverrides) : [];
  const recentRunIds = new Set(overriddenRecentRuns.map((run) => run.run_id));
  const terminalMovedRuns = overriddenActiveRuns.filter(
    (run) => run.status !== "ACTIVE" && !recentRunIds.has(run.run_id),
  );
  const liveActiveRuns = overriddenActiveRuns.filter((run) => run.status === "ACTIVE");
  const liveRecentRuns = runs
    ? [
        ...overriddenRecentRuns,
        ...terminalMovedRuns,
        ...overrideOnlyRuns(runs, runOverrides, events),
      ]
    : [];
  const replayWindowLabel =
    replayWindow === null
      ? ""
      : replayWindow.hasMore
        ? "Durable replay window is the newest " + replayWindow.limit + " canonical events; older canonical events remain in PostgreSQL."
        : "Durable replay returned every canonical event inside the newest " + replayWindow.limit + "-event window.";

  const openRun = (runId: string) => {
    setView("runs");
    void loadRunDetail(runId);
  };

  const renderFleet = () => (
    <div className="cc-stack">
      <p className="cc-note">
        Fleet state counts are exact counts over the complete durable Project Registry, never
        estimated. Each response stays bounded to at most {fleet?.max_projects ?? 200} projects and
        the list below renders only the current bounded window.
      </p>
      {fleetLoading && fleet === null ? (
        <p className="fleet-message" role="status">
          Loading operational fleet...
        </p>
      ) : fleetError !== null ? (
        <div className="fleet-message error-message" role="alert">
          <span>{fleetError}</span>
          <button className="secondary-button" onClick={() => void loadFleet()}>
            Refresh fleet
          </button>
        </div>
      ) : fleet === null ? (
        <p className="fleet-message">The operational fleet snapshot is unavailable.</p>
      ) : (
        <>
          <div className="cc-counts" aria-label="Exact project state counts">
            {FLEET_STATE_ORDER.map((state) => (
              <span key={state} className={"state-badge state-" + stateSlug(state)}>
                {state.toUpperCase()} {fleet.state_counts[state]}
              </span>
            ))}
          </div>
          <p className="cc-note">
            {fleet.project_count} registered project{fleet.project_count === 1 ? "" : "s"}
            {fleet.projects.length === 0
              ? " (empty bounded window)"
              : " (showing projects " +
                (fleet.offset + 1) +
                " to " +
                (fleet.offset + fleet.projects.length) +
                " of " +
                fleet.project_count +
                ")"}{" "}
            {"· generated "}
            {formatTimestamp(fleet.generated_at)}
          </p>
          <p className="cc-note">
            {fleet.projects.length === 0
              ? "This bounded fleet window contains no projects."
              : "Showing " +
                fleet.projects.length +
                " project" +
                (fleet.projects.length === 1 ? "" : "s") +
                " on this bounded window (hard maximum " +
                fleet.max_projects +
                " per response)."}{" "}
            {fleet.has_more
              ? "More registered projects remain reachable through the next bounded page."
              : fleet.project_count > fleet.projects.length
                ? "Earlier registered projects remain reachable through the previous bounded page."
                : "Every registered project is inside the current window."}
          </p>
          <div className="cc-pagination" aria-label="Fleet pagination">
            <button
              className="secondary-button"
              disabled={fleet.offset === 0}
              onClick={() => void loadFleet(Math.max(0, fleet.offset - FLEET_PAGE_SIZE))}
            >
              Previous page
            </button>
            <button
              className="secondary-button"
              disabled={!fleet.has_more || fleet.next_offset === null}
              onClick={() => {
                if (fleet.next_offset !== null) void loadFleet(fleet.next_offset);
              }}
            >
              Next page
            </button>
          </div>
          {fleet.project_count === 0 ? (
            <p className="fleet-message">The registry is empty; there is no project state to count.</p>
          ) : fleet.projects.length === 0 ? (
            <p className="fleet-message">
              This bounded window is past the end of the registry; use the previous page control to
              reach registered projects.
            </p>
          ) : (
            <ul className="cc-project-list">
              {fleet.projects.map((project) => (
                <li key={project.project_id} className="cc-project-row">
                  <div>
                    <h3>{project.name}</h3>
                    <p className="cc-muted">{project.relative_path}</p>
                    <p className="cc-muted">
                      {project.git_branch ?? (project.detached_head ? "detached HEAD" : "no branch")}
                      {" · "}
                      {project.short_head ?? "no HEAD"}
                      {" · last inspection "}
                      {formatTimestamp(project.last_inspected_at)}
                      {project.working_tree_clean === null
                        ? " · working tree: UNAVAILABLE"
                        : project.working_tree_clean
                          ? " · working tree clean"
                          : " · working tree dirty"}
                    </p>
                    {project.inspection_error !== null ? (
                      <p className="error-message">{project.inspection_error}</p>
                    ) : null}
                  </div>
                  <div className="cc-project-actions">
                    <StateBadge value={project.state} />
                    <button
                      className="secondary-button"
                      onClick={() => {
                        onSelectProject(project.project_id);
                        setView("project");
                      }}
                    >
                      Open project
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );

  const renderProject = () => {
    if (!selectedProjectId) {
      return <p className="fleet-message">Select an operational project to open its detail surface.</p>;
    }
    return (
      <div className="cc-stack">
        <p className="cc-note">
          Project detail is composed from the registry snapshot, bounded run aggregates and the
          canonical event window. Values that are absent stay UNAVAILABLE and are never rendered as
          zero.
        </p>
        {detailLoading && detail === null ? (
          <p className="fleet-message" role="status">
            Loading bounded project detail...
          </p>
        ) : detailError !== null ? (
          <div className="fleet-message error-message" role="alert">
            <span>{detailError}</span>
            <button className="secondary-button" onClick={() => void loadDetail()}>
              Refresh project detail
            </button>
          </div>
        ) : detail === null ? (
          <p className="fleet-message">The bounded project detail is unavailable.</p>
        ) : (
          <>
            <article className="cc-card">
              <div className="cc-card-heading">
                <div>
                  <h3>{detail.project.name}</h3>
                  <p className="cc-muted">{detail.project.relative_path}</p>
                </div>
                <StateBadge value={detail.project.state} />
              </div>
              <dl className="project-details">
                <div>
                  <dt>Branch</dt>
                  <dd>
                    {detail.project.git_branch ??
                      (detail.project.detached_head ? "detached HEAD" : "UNAVAILABLE")}
                  </dd>
                </div>
                <div>
                  <dt>HEAD</dt>
                  <dd>{detail.project.short_head ?? "UNAVAILABLE"}</dd>
                </div>
                <div>
                  <dt>Working tree</dt>
                  <dd>
                    {detail.project.working_tree_clean === null
                      ? "UNAVAILABLE"
                      : detail.project.working_tree_clean
                        ? "clean"
                        : "dirty"}
                  </dd>
                </div>
                <div>
                  <dt>Languages</dt>
                  <dd>
                    {detail.project.language_stack.length > 0
                      ? detail.project.language_stack.join(", ")
                      : "UNAVAILABLE"}
                  </dd>
                </div>
                <div>
                  <dt>Active runs (live)</dt>
                  <dd>{detailActiveRuns.length}</dd>
                </div>
                <div>
                  <dt>Recent runs</dt>
                  <dd>
                    {detailRecentRuns.length}
                    {detail.recent_runs_truncated ? " (truncated)" : ""}
                  </dd>
                </div>
                <div>
                  <dt>Event window</dt>
                  <dd>
                    {detail.window.scanned_events} of {detail.window.max_events}
                    {detail.window.truncated ? " (truncated)" : ""}
                  </dd>
                </div>
                <div>
                  <dt>Last inspection</dt>
                  <dd>{formatDateTime(detail.project.last_inspected_at)}</dd>
                </div>
              </dl>
              {detail.project.inspection_error !== null ? (
                <p className="error-message">{detail.project.inspection_error}</p>
              ) : null}
            </article>

            <div className="cc-columns">
              <section className="cc-card" aria-label="Recent runs">
                <div className="cc-card-heading">
                  <h3>Active and recent runs</h3>
                  <button
                    className="secondary-button"
                    onClick={() => {
                      setView("runs");
                      void loadRuns();
                    }}
                  >
                    Open runs
                  </button>
                </div>
                {detailRuns.length === 0 ? (
                  <p className="cc-muted">
                    No run telemetry is recorded for this project inside the bounded window.
                  </p>
                ) : (
                  <ul className="cc-run-list">
                    {detailActiveRuns.map((run) => (
                      <RunRow key={run.run_id} run={run} onOpen={openRun} bucket="active" />
                    ))}
                    {detailRecentRuns.map((run) => (
                      <RunRow key={run.run_id} run={run} onOpen={openRun} bucket="recent" />
                    ))}
                  </ul>
                )}
              </section>

              <section className="cc-card" aria-label="Tests and errors summary">
                <div className="cc-card-heading">
                  <h3>Tests and errors</h3>
                  <button className="secondary-button" onClick={() => setView("tests")}>
                    Open tests
                  </button>
                </div>
                <p className="cc-muted">
                  {detail.tests.runs.length === 0
                    ? "No test or validation telemetry inside the bounded window."
                    : detail.tests.runs
                        .map((run) => shortId(run.run_id) + ": " + run.status)
                        .join(" · ")}
                </p>
                <p className="cc-muted">
                  {detail.tests.last_validation_event_at === null
                    ? "Last validation event: NO VALIDATION EVENTS RECORDED (UNAVAILABLE, not zero)."
                    : "Last validation event: " +
                      formatDateTime(detail.tests.last_validation_event_at)}
                </p>
                <div className="cc-card-heading">
                  <h3>Errors and warnings</h3>
                  <button className="secondary-button" onClick={() => setView("errors")}>
                    Open errors
                  </button>
                </div>
                <p className="cc-muted">
                  {detail.errors.errors.length} error
                  {detail.errors.errors.length === 1 ? "" : "s"} · {detail.errors.warnings.length}{" "}
                  warning{detail.errors.warnings.length === 1 ? "" : "s"}
                  {detail.errors.truncated ? " (truncated)" : ""} inside the bounded window.
                </p>
                {detail.errors.errors[0] !== undefined ? (
                  <p className="error-message">{detail.errors.errors[0].summary}</p>
                ) : (
                  <p className="cc-muted">No error events recorded in the bounded window.</p>
                )}
              </section>
            </div>

            <section className="cc-card" aria-label="Project event timeline">
              <h3>Near-real-time event timeline</h3>
              <EventTimeline
                events={events}
                emptyLabel="No canonical events recorded for this project inside the bounded window."
                droppedEvents={droppedEvents}
                windowLabel={replayWindowLabel}
              />
            </section>
          </>
        )}
      </div>
    );
  };
  const renderFull = () => <ControlCenterFull selectedProjectId={selectedProjectId} />;
  const renderRuns = () => {
    if (!selectedProjectId) {
      return <p className="fleet-message">Select an operational project to open its run surfaces.</p>;
    }
    if (selectedRunId !== null) return renderRunDetail();
    return (
      <div className="cc-stack">
        <p className="cc-note">
          Active and recent runs are derived deterministically from durable telemetry run identity
          (executor.started, run.completed, run.failed) without a new migration. Terminal stream
          events move a run from active to recent immediately and idempotently.
        </p>
        {runsLoading && runs === null ? (
          <p className="fleet-message" role="status">
            Loading run aggregates...
          </p>
        ) : runsError !== null ? (
          <div className="fleet-message error-message" role="alert">
            <span>{runsError}</span>
            <button className="secondary-button" onClick={() => void loadRuns()}>
              Refresh runs
            </button>
          </div>
        ) : runs === null ? (
          <p className="fleet-message">The bounded run surface is unavailable.</p>
        ) : (
          <>
            <section className="cc-card" aria-label="Active runs">
              <h3>Active runs ({liveActiveRuns.length})</h3>
              {liveActiveRuns.length === 0 ? (
                <p className="cc-muted">No run is currently active for this project.</p>
              ) : (
                <ul className="cc-run-list">
                  {liveActiveRuns.map((run) => (
                    <RunRow key={run.run_id} run={run} onOpen={openRun} bucket="active" />
                  ))}
                </ul>
              )}
            </section>
            <section className="cc-card" aria-label="Recent runs">
              <h3>Recent runs ({liveRecentRuns.length})</h3>
              {liveRecentRuns.length === 0 ? (
                <p className="cc-muted">No recent run telemetry inside the bounded window.</p>
              ) : (
                <ul className="cc-run-list">
                  {liveRecentRuns.map((run) => (
                    <RunRow key={run.run_id} run={run} onOpen={openRun} bucket="recent" />
                  ))}
                </ul>
              )}
            </section>
            <p className="cc-note">
              Bounded to {RUN_LIMIT} most recent runs
              {runs.truncated ? " (truncated: older runs exist)" : ""}. Window scanned{" "}
              {runs.window.scanned_events} aggregates.
            </p>
          </>
        )}
      </div>
    );
  };

  const renderRunDetail = () => {
    const liveRun =
      runDetail === null
        ? null
        : (applyRunOverrides([runDetail.run], runOverrides)[0] ?? runDetail.run);
    return (
      <div className="cc-stack">
        <button
          className="secondary-button"
          onClick={() => {
            setSelectedRunId(null);
            clearRunTimeline();
            setRunDetail(null);
            setRunDetailError(null);
          }}
        >
          Back to runs
        </button>
        {runDetailLoading && runDetail === null ? (
          <p className="fleet-message" role="status">
            Loading bounded run detail...
          </p>
        ) : runDetailError !== null ? (
          <div className="fleet-message error-message" role="alert">
            <span>{runDetailError}</span>
            <button
              className="secondary-button"
              onClick={() => {
                if (selectedRunId !== null) void loadRunDetail(selectedRunId);
              }}
            >
              Refresh run
            </button>
          </div>
        ) : runDetail === null || liveRun === null ? (
          <p className="fleet-message">The bounded run detail is unavailable.</p>
        ) : (
          <>
            <article className="cc-card">
              <div className="cc-card-heading">
                <h3>Run {shortId(runDetail.run.run_id)}</h3>
                <StateBadge value={liveRun.status} />
              </div>
              <dl className="project-details">
                <div>
                  <dt>Stage</dt>
                  <dd>{liveRun.stage}</dd>
                </div>
                <div>
                  <dt>Events</dt>
                  <dd>{liveRun.event_count}</dd>
                </div>
                <div>
                  <dt>First event</dt>
                  <dd>{formatDateTime(liveRun.first_event_at)}</dd>
                </div>
                <div>
                  <dt>Last event</dt>
                  <dd>{formatDateTime(liveRun.last_event_at)}</dd>
                </div>
                <div>
                  <dt>Task</dt>
                  <dd>
                    {runDetail.task_id === null
                      ? "UNAVAILABLE (no task identity in the bounded timeline)"
                      : shortId(runDetail.task_id)}
                  </dd>
                </div>
                <div>
                  <dt>Executor</dt>
                  <dd>
                    {runDetail.executor_identity ??
                      "UNAVAILABLE (no executor.started payload in the bounded timeline)"}
                  </dd>
                </div>
              </dl>
            </article>
            <EventTimeline
              events={runTimeline}
              emptyLabel="No events recorded for this run inside the bounded window."
              droppedEvents={runTimelineDropped}
              bound={RUN_TIMELINE_MAX}
              windowLabel={
                runDetail.timeline_truncated
                  ? "Run timeline is bounded at " +
                    runDetail.max_timeline_events +
                    " events; additional run events remain in canonical PostgreSQL order."
                  : "Run timeline is complete inside the " +
                    runDetail.max_timeline_events +
                    "-event bound."
              }
            />
          </>
        )}
      </div>
    );
  };

  const renderHealth = () => (
    <div className="cc-stack">
      {healthLoading && health === null ? (
        <p className="fleet-message" role="status">
          Loading platform health...
        </p>
      ) : null}
      {healthError !== null ? (
        <div className="fleet-message error-message" role="alert">
          <span>{healthError}</span>
          <button className="secondary-button" onClick={() => void loadHealth()}>
            Refresh health surface
          </button>
        </div>
      ) : null}
      {health === null ? (
        healthError === null ? (
          <p className="fleet-message">Platform health is unavailable.</p>
        ) : null
      ) : (
        <>
          <div className="cc-counts" aria-label="Platform health summary">
            <StateBadge value={health.status.toUpperCase()} />
            <span className="state-badge">VERSION {health.version}</span>
            <span className="state-badge">ENV {health.environment.toUpperCase()}</span>
            <span className="state-badge">MIGRATION {health.migration_head}</span>
          </div>
          <p className="cc-note">
            Canonical store: {health.canonical_store} (structured truth). Hot store: {health.hot_store}{" "}
            ({health.hot_store_canonical ? "canonical" : "non-canonical"}) — Redis loss cannot remove
            canonical project/run/event truth from this snapshot.
          </p>
          <ul className="cc-project-list">
            {Object.entries(health.checks).map(([name, check]) => (
              <li key={name} className="cc-project-row">
                <div>
                  <h3>{name}</h3>
                  {check.reason !== null ? <p className="cc-muted">{check.reason}</p> : null}
                  <p className="cc-muted">
                    {Object.entries(check.details)
                      .map(([key, value]) => key + ": " + (value ? "true" : "false"))
                      .join(" · ") || "no bounded details exposed"}
                  </p>
                </div>
                <StateBadge value={check.status.toUpperCase()} />
              </li>
            ))}
          </ul>
          <section className="cc-card" aria-label="Not instrumented metrics">
            <h3>Estimated and unavailable metrics</h3>
            <p className="cc-note">
              These metrics have no real backend source in this increment. They render as
              UNAVAILABLE / NOT YET INSTRUMENTED and are never displayed as zero. Token counters are
              shown only when present in sanitized telemetry payloads, always with an ESTIMATED
              marker when the payload declares an estimate.
            </p>
            <ul className="cc-metrics">
              {health.unavailable_metrics.map((metric) => (
                <li key={metric}>
                  <span className="cc-chip cc-chip-unavailable">NOT YET INSTRUMENTED</span>
                  <span className="cc-muted">{metric}</span>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );

  const renderTests = () => {
    if (!selectedProjectId) {
      return (
        <p className="fleet-message">Select an operational project to open its test/validation surface.</p>
      );
    }
    return (
      <div className="cc-stack">
        <p className="cc-note">
          Test state is derived only from durable test.started / test.finished / validation.passed /
          validation.failed telemetry inside the bounded window. Missing telemetry stays
          UNAVAILABLE; it is never counted as zero.
        </p>
        {testsLoading && tests === null ? (
          <p className="fleet-message" role="status">
            Loading test telemetry...
          </p>
        ) : testsError !== null ? (
          <div className="fleet-message error-message" role="alert">
            <span>{testsError}</span>
            <button className="secondary-button" onClick={() => void loadTests()}>
              Refresh tests
            </button>
          </div>
        ) : tests === null ? (
          <p className="fleet-message">The bounded test surface is unavailable.</p>
        ) : (
          <>
            {tests.runs.length === 0 ? (
              <p className="fleet-message">
                No test or validation telemetry is recorded for this project inside the bounded
                window.
              </p>
            ) : (
              <ul className="cc-project-list">
                {tests.runs.map((run) => (
                  <li key={run.run_id} className="cc-project-row">
                    <div>
                      <h3>Run {shortId(run.run_id)}</h3>
                      <p className="cc-muted">
                        test.started {run.test_started} · test.finished {run.test_finished} ·
                        validation.passed {run.validation_passed} · validation.failed{" "}
                        {run.validation_failed}
                      </p>
                      <p className="cc-muted">
                        last event {run.last_event_type} · {formatDateTime(run.last_event_at)}
                      </p>
                    </div>
                    <StateBadge value={run.status} />
                  </li>
                ))}
              </ul>
            )}
            <p className="cc-note">
              Runs inside the window without test telemetry:{" "}
              {tests.runs_without_test_telemetry_in_window}. Window scanned{" "}
              {tests.window.scanned_events} of at most {tests.window.max_events} recent events
              {tests.window.truncated ? " (truncated)" : ""}.
            </p>
            <p className="cc-note">
              {tests.last_validation_event_at === null
                ? "Last validation event: NO VALIDATION EVENTS RECORDED (UNAVAILABLE, not zero)."
                : "Last validation event: " + formatDateTime(tests.last_validation_event_at) + "."}
            </p>
          </>
        )}
      </div>
    );
  };

  const renderErrors = () => {
    if (!selectedProjectId) {
      return (
        <p className="fleet-message">Select an operational project to open its errors/warnings surface.</p>
      );
    }
    return (
      <div className="cc-stack">
        <p className="cc-note">
          Errors come from run.failed / validation.failed canonical telemetry; warnings come from
          deterministic DEGRADED / BLOCKED registry state and degraded platform health checks.
        </p>
        {errorsLoading && errors === null ? (
          <p className="fleet-message" role="status">
            Loading errors and warnings...
          </p>
        ) : errorsError !== null ? (
          <div className="fleet-message error-message" role="alert">
            <span>{errorsError}</span>
            <button className="secondary-button" onClick={() => void loadErrors()}>
              Refresh errors
            </button>
          </div>
        ) : errors === null ? (
          <p className="fleet-message">The bounded errors surface is unavailable.</p>
        ) : (
          <>
            <section className="cc-card" aria-label="Errors">
              <h3>Errors ({errors.errors.length})</h3>
              {errors.errors.length === 0 ? (
                <p className="cc-muted">No error events recorded in the bounded window.</p>
              ) : (
                <ul className="cc-warning-list">
                  {errors.errors.map((item) => (
                    <WarningRow key={item.event_id ?? item.kind + item.summary} item={item} />
                  ))}
                </ul>
              )}
            </section>
            <section className="cc-card" aria-label="Warnings">
              <h3>Warnings ({errors.warnings.length})</h3>
              {errors.warnings.length === 0 ? (
                <p className="cc-muted">
                  No degraded registry state or health warning in the bounded window.
                </p>
              ) : (
                <ul className="cc-warning-list">
                  {errors.warnings.map((item) => (
                    <WarningRow key={item.kind + item.summary} item={item} />
                  ))}
                </ul>
              )}
            </section>
            <p className="cc-note">
              Window scanned {errors.window.scanned_events} of at most {errors.window.max_events}{" "}
              recent events{errors.window.truncated ? " (truncated)" : ""}
              {errors.truncated ? " · bounded list truncated" : ""}.
            </p>
          </>
        )}
      </div>
    );
  };
  return (
    <section className="control-center-section" aria-labelledby="control-center-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">OPERATIONAL CORE</p>
          <h2 id="control-center-title">Control Center</h2>
        </div>
        <span className={"stream-pill stream-" + streamState} role="status" aria-live="polite">
          {STREAM_LABELS[streamState]}
        </span>
      </div>

      <div className="cc-toolbar">
        <label className="project-picker">
          Operational project
          <select
            aria-label="Operational project"
            value={selectedProjectId}
            onChange={(event) => handleSelectProject(event.target.value)}
          >
            <option value="">Choose a project…</option>
            {boundedProjectOptions.map((project) => (
              <option key={project.project_id} value={project.project_id}>
                {project.label}
              </option>
            ))}
          </select>
        </label>
        <p className="cc-note cc-stream-note">
          {streamState === "live"
            ? "Live timeline connected through the real SSE transport with durable replay reconciliation."
            : streamState === "fallback"
              ? "SSE transport unreachable; bounded durable replay polling is active."
              : "Connecting to the real SSE transport and reconciling with durable replay..."}
          {reconciledAt !== null
            ? " Last reconciliation " +
              formatTimestamp(reconciledAt) +
              " (" +
              events.length +
              " events in the bounded live buffer)."
            : ""}
          {streamError !== null ? " " + streamError : ""}
        </p>
      </div>

      <div
        className="cc-nav"
        role="tablist"
        aria-label="Control Center surfaces"
        onKeyDown={handleTabKeys}
      >
        {CONTROL_VIEWS.map((definition) => (
          <button
            key={definition.id}
            id={"cc-tab-" + definition.id}
            role="tab"
            type="button"
            className={"cc-tab" + (view === definition.id ? " cc-tab-active" : "")}
            aria-selected={view === definition.id}
            aria-controls={"cc-panel-" + definition.id}
            tabIndex={view === definition.id ? 0 : -1}
            onClick={() => setView(definition.id)}
          >
            {definition.label}
          </button>
        ))}
      </div>

      <div
        className="cc-panel"
        role="tabpanel"
        id={"cc-panel-" + view}
        aria-labelledby={"cc-tab-" + view}
        tabIndex={0}
      >
        {view === "fleet" ? renderFleet() : null}
        {view === "project" ? renderProject() : null}
        {view === "full" ? renderFull() : null}
        {view === "runs" ? renderRuns() : null}
        {view === "health" ? renderHealth() : null}
        {view === "tests" ? renderTests() : null}
        {view === "errors" ? renderErrors() : null}
      </div>
    </section>
  );
}

const FLEET_STATE_ORDER: (keyof FleetStateCounts)[] = [
  "offline",
  "stale",
  "indexing",
  "ready",
  "active",
  "degraded",
  "blocked",
];

function StateBadge({ value }: { value: string }) {
  return <span className={"state-badge state-" + stateSlug(value)}>{value}</span>;
}

function RunRow({
  run,
  onOpen,
  bucket,
}: {
  run: RunSummary;
  onOpen: (runId: string) => void;
  bucket: "active" | "recent";
}) {
  return (
    <li className="cc-run-row" data-testid={"run-row-" + bucket}>
      <div className="cc-run-main">
        <StateBadge value={run.status} />
        <span className="cc-run-id">{shortId(run.run_id)}</span>
        <span className="cc-muted">{run.stage}</span>
        <span className="cc-muted">{formatDateTime(run.last_event_at)}</span>
        <span className="cc-muted">
          {run.event_count} event{run.event_count === 1 ? "" : "s"}
        </span>
      </div>
      <button className="secondary-button" onClick={() => onOpen(run.run_id)}>
        Open run
      </button>
    </li>
  );
}

function WarningRow({ item }: { item: WarningItem }) {
  return (
    <li className="cc-warning-row">
      <span className={"cc-chip severity-" + stateSlug(item.severity)}>{item.severity}</span>
      <div>
        <p className="cc-warning-summary">{item.summary}</p>
        <p className="cc-muted">
          {item.kind}
          {item.run_id !== null ? " · run " + shortId(item.run_id) : ""}
          {item.occurred_at !== null ? " · " + formatDateTime(item.occurred_at) : ""}
        </p>
      </div>
    </li>
  );
}

function PayloadSummary({ payload }: { payload: Record<string, unknown> }) {
  const entries = payloadScalarEntries(payload);
  if (entries.length === 0) {
    return (
      <p className="cc-muted cc-payload-empty">
        Sanitized payload exposes no scalar fields for this event.
      </p>
    );
  }
  const estimated = payload.estimated === true || payload.tokens_estimated === true;
  return (
    <ul className="cc-payload">
      {entries.map(([key, value]) => (
        <li key={key}>
          <span className="cc-payload-key">{key}</span>
          <span className="cc-payload-value">{formatPayloadValue(value)}</span>
          {estimated && isTokenMetricKey(key) ? (
            <span className="cc-chip cc-chip-estimated">ESTIMATED</span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function EventTimeline({
  events,
  emptyLabel,
  droppedEvents,
  windowLabel,
  bound = EVENT_TIMELINE_MAX,
}: {
  events: EventEnvelope[];
  emptyLabel: string;
  droppedEvents: number;
  windowLabel: string;
  bound?: number;
}) {
  if (events.length === 0) {
    return <p className="fleet-message">{emptyLabel}</p>;
  }
  return (
    <div className="cc-timeline-block">
      <p className="cc-note">
        Showing {events.length} event{events.length === 1 ? "" : "s"} in canonical order, bounded to{" "}
        {bound}.
        {droppedEvents > 0
          ? " " +
            droppedEvents +
            " older event" +
            (droppedEvents === 1 ? "" : "s") +
            " left this bounded live buffer; canonical history stays in PostgreSQL."
          : ""}
        {windowLabel ? " " + windowLabel : ""}
      </p>
      <ol className="cc-timeline">
        {events.map((event) => (
          <li key={event.event_id} data-testid="timeline-event" className="cc-timeline-item">
            <div className="cc-timeline-head">
              <span className="event-badge">{event.event_type}</span>
              <span className="cc-muted">{formatDateTime(event.occurred_at)}</span>
              <span className="cc-muted">#{event.ordering_id}</span>
              {event.run_id !== null ? (
                <span className="cc-muted">run {shortId(event.run_id)}</span>
              ) : null}
              {event.task_id !== null ? (
                <span className="cc-muted">task {shortId(event.task_id)}</span>
              ) : null}
            </div>
            <PayloadSummary payload={event.payload} />
          </li>
        ))}
      </ol>
    </div>
  );
}
