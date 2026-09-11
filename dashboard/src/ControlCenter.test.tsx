import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ControlCenter from "./ControlCenter";
import { CANONICAL_EVENT_TYPES } from "./eventVocabulary";

const PROJECT_A_ID = "a1a1a1a1-0000-4000-8000-000000000001";
const PROJECT_B_ID = "b2b2b2b2-0000-4000-8000-000000000002";
const RUN_ACTIVE_ID = "aabbccdd-0000-4000-8000-0000000000a1";
const RUN_RECENT_ID = "eeff0011-0000-4000-8000-0000000000a2";
const TASK_ID = "dddddddd-0000-4000-8000-0000000000c1";
const EXECUTOR_IDENTITY = "codex/openai/gpt-5.6-luna-xhigh";
const GENERATED_AT = "2026-09-10T12:00:00.000Z";

const PROJECT_OPTIONS = [
  { project_id: PROJECT_A_ID, name: "Project Alpha", relative_path: "alpha" },
  { project_id: PROJECT_B_ID, name: "Project Beta", relative_path: "beta" },
];

class FakeEventSource {
  static instances: FakeEventSource[] = [];

  readonly url: string;
  closed = false;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  private readonly listeners = new Map<string, ((event: MessageEvent) => void)[]>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: EventListener): void {
    const existing = this.listeners.get(type) ?? [];
    existing.push(listener as (event: MessageEvent) => void);
    this.listeners.set(type, existing);
  }

  close(): void {
    this.closed = true;
  }

  open(): void {
    this.onopen?.();
  }

  fail(): void {
    this.onerror?.();
  }

  emit(type: string, payload: unknown): void {
    const event = { data: JSON.stringify(payload) } as MessageEvent;
    for (const listener of this.listeners.get(type) ?? []) listener(event);
  }
}

function envelope(overrides: {
  event_id: string;
  ordering_id: number;
  event_type?: string;
  run_id?: string | null;
  task_id?: string | null;
  payload?: Record<string, unknown>;
}) {
  return {
    event_id: overrides.event_id,
    envelope_version: "telemetry-event-bus-v1",
    event_type: overrides.event_type ?? "executor.started",
    project_id: PROJECT_A_ID,
    task_id: overrides.task_id ?? null,
    run_id: overrides.run_id ?? null,
    ordering_id: overrides.ordering_id,
    occurred_at: new Date(Date.UTC(2026, 8, 10, 12, 0, 0, overrides.ordering_id)).toISOString(),
    payload: overrides.payload ?? {},
    provenance: { source: "wo020-dashboard-contract-test" },
    cursor: String(overrides.ordering_id),
  };
}

function eventPage(events: unknown[], hasMore = false) {
  return { events, next_cursor: null, has_more: hasMore, limit: 100 };
}

function window_(scanned: number, truncated = false) {
  return { scanned_events: scanned, max_events: 100, truncated };
}

function headline(overrides: Record<string, unknown> = {}) {
  return {
    project_id: PROJECT_A_ID,
    name: "Project Alpha",
    relative_path: "alpha",
    state: "READY",
    git_branch: "main",
    git_head_sha: "1234567890abcdef1234567890abcdef12345678",
    short_head: "1234567",
    detached_head: false,
    repository_accessible: true,
    working_tree_clean: true,
    language_stack: ["python", "typescript"],
    inspection_error: null,
    last_inspected_at: GENERATED_AT,
    updated_at: GENERATED_AT,
    ...overrides,
  };
}

function runSummary(overrides: Record<string, unknown> = {}) {
  return {
    run_id: RUN_ACTIVE_ID,
    status: "ACTIVE",
    stage: "executor.started",
    last_event_type: "executor.started",
    last_event_at: GENERATED_AT,
    first_event_at: GENERATED_AT,
    event_count: 3,
    ...overrides,
  };
}

function fleetResponse(overrides: Record<string, unknown> = {}) {
  return {
    generated_at: GENERATED_AT,
    project_count: 2,
    state_counts: {
      offline: 0,
      stale: 0,
      indexing: 0,
      ready: 1,
      active: 1,
      degraded: 0,
      blocked: 0,
    },
    projects: [
      headline(),
      headline({
        project_id: PROJECT_B_ID,
        name: "Project Beta",
        relative_path: "beta",
        state: "ACTIVE",
        working_tree_clean: null,
      }),
    ],
    truncated: false,
    max_projects: 200,
    offset: 0,
    limit: 50,
    has_more: false,
    next_offset: null,
    ...overrides,
  };
}

function emptyFleetResponse() {
  return fleetResponse({
    project_count: 0,
    state_counts: { offline: 0, stale: 0, indexing: 0, ready: 0, active: 0, degraded: 0, blocked: 0 },
    projects: [],
  });
}

function healthResponse() {
  return {
    generated_at: GENERATED_AT,
    status: "ok",
    version: "0.0.1-bootstrap",
    environment: "test",
    migration_head: "0007_telemetry_events",
    canonical_store: "postgres",
    hot_store: "redis",
    hot_store_canonical: false,
    checks: {
      postgres: { status: "ok", details: { pgvector: true }, reason: null },
      redis: { status: "ok", details: { canonical: false }, reason: null },
      storage: { status: "ok", details: { writable: true }, reason: null },
    },
    unavailable_metrics: [
      "exact_live_token_usage",
      "exact_provider_cost",
      "cache_hit_rate",
      "context_signal_ratio",
    ],
  };
}

function testsResponse(overrides: Record<string, unknown> = {}) {
  return {
    generated_at: GENERATED_AT,
    project_id: PROJECT_A_ID,
    window: window_(4),
    runs: [
      {
        run_id: RUN_RECENT_ID,
        status: "PASSED",
        test_started: 2,
        test_finished: 2,
        validation_passed: 1,
        validation_failed: 0,
        last_event_type: "validation.passed",
        last_event_at: GENERATED_AT,
      },
    ],
    runs_without_test_telemetry_in_window: 1,
    last_validation_event_at: GENERATED_AT,
    ...overrides,
  };
}

function errorsResponse(overrides: Record<string, unknown> = {}) {
  return {
    generated_at: GENERATED_AT,
    project_id: PROJECT_A_ID,
    window: window_(6),
    errors: [
      {
        severity: "ERROR",
        kind: "run.failed",
        project_id: PROJECT_A_ID,
        run_id: RUN_RECENT_ID,
        event_id: "ffffffff-0000-4000-8000-0000000000e1",
        occurred_at: GENERATED_AT,
        summary: "run.failed: bounded failure summary",
      },
    ],
    warnings: [
      {
        severity: "WARNING",
        kind: "health.redis",
        project_id: PROJECT_A_ID,
        run_id: null,
        event_id: null,
        occurred_at: null,
        summary: "redis status is degraded: hot cache unreachable",
      },
    ],
    truncated: false,
    ...overrides,
  };
}

function detailResponse(overrides: Record<string, unknown> = {}) {
  return {
    generated_at: GENERATED_AT,
    project: headline(),
    active_run_count: 1,
    recent_runs: [runSummary()],
    recent_runs_truncated: false,
    recent_events: [],
    window: window_(3),
    tests: testsResponse({ runs: [], runs_without_test_telemetry_in_window: 1, last_validation_event_at: null }),
    errors: errorsResponse({ errors: [], warnings: [] }),
    ...overrides,
  };
}

function runsResponse(overrides: Record<string, unknown> = {}) {
  return {
    generated_at: GENERATED_AT,
    project_id: PROJECT_A_ID,
    active: [runSummary()],
    recent: [
      runSummary({
        run_id: RUN_RECENT_ID,
        status: "FAILED",
        stage: "run.failed",
        last_event_type: "run.failed",
        event_count: 5,
      }),
    ],
    truncated: false,
    window: window_(8),
    ...overrides,
  };
}

function runDetailResponse(overrides: Record<string, unknown> = {}) {
  return {
    generated_at: GENERATED_AT,
    project_id: PROJECT_A_ID,
    run: runSummary(),
    task_id: TASK_ID,
    executor_identity: EXECUTOR_IDENTITY,
    timeline: [
      envelope({ event_id: "aaaa1111-0000-4000-8000-000000000011", ordering_id: 11, run_id: RUN_ACTIVE_ID }),
      envelope({
        event_id: "aaaa1111-0000-4000-8000-000000000012",
        ordering_id: 12,
        event_type: "run.completed",
        run_id: RUN_ACTIVE_ID,
        payload: { status: "COMPLETED" },
      }),
    ],
    timeline_truncated: false,
    max_timeline_events: 100,
    ...overrides,
  };
}

type ApiState = {
  calls: string[];
  fleetStatus: number;
  fleet: unknown;
  fleetByOffset: Record<string, unknown>;
  fleetGate: Promise<void> | null;
  health: unknown;
  replay: unknown;
  detail: unknown;
  runs: unknown;
  tests: unknown;
  errors: unknown;
  runDetail: unknown;
};

function installApi(overrides: Partial<ApiState> = {}) {
  const state: ApiState = {
    calls: [],
    fleetStatus: 200,
    fleet: fleetResponse(),
    fleetByOffset: {},
    fleetGate: null,
    health: healthResponse(),
    replay: eventPage([]),
    detail: detailResponse(),
    runs: runsResponse(),
    tests: testsResponse(),
    errors: errorsResponse(),
    runDetail: runDetailResponse(),
    ...overrides,
  };
  const fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = input.toString();
    state.calls.push(url);
    const json = (payload: unknown, status = 200) =>
      Promise.resolve(
        new Response(JSON.stringify(payload), {
          status,
          headers: { "Content-Type": "application/json" },
        }),
      );
    if (url.includes("/api/v1/control-center/fleet")) {
      const offset = new URL(url, "http://localhost").searchParams.get("offset") ?? "0";
      const payload = state.fleetByOffset[offset] ?? state.fleet;
      if (state.fleetGate !== null) {
        return state.fleetGate.then(() => json(payload, state.fleetStatus));
      }
      return json(payload, state.fleetStatus);
    }
    if (url.includes("/api/v1/control-center/health")) return json(state.health);
    if (url.includes("/api/v1/control-center/projects/") && url.includes("/runs/")) {
      return json(state.runDetail);
    }
    if (url.includes("/api/v1/control-center/projects/") && url.includes("/runs?")) {
      return json(state.runs);
    }
    if (url.includes("/api/v1/control-center/projects/") && url.includes("/tests?")) {
      return json(state.tests);
    }
    if (url.includes("/api/v1/control-center/projects/") && url.includes("/errors?")) {
      return json(state.errors);
    }
    if (url.includes("/api/v1/control-center/projects/")) return json(state.detail);
    if (url.includes("/api/v1/projects/") && url.includes("/events?")) return json(state.replay);
    return json({ detail: "unmocked route: " + url }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { state, fetchMock };
}

function renderControlCenter(
  api: ReturnType<typeof installApi>,
  options: { selectedProjectId?: string } = {},
) {
  const onSelectProject = vi.fn();
  const utils = render(
    <ControlCenter
      projects={PROJECT_OPTIONS}
      selectedProjectId={options.selectedProjectId ?? ""}
      onSelectProject={onSelectProject}
    />,
  );
  return { ...utils, state: api.state, onSelectProject };
}

async function settle(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

function rowFor(text: string): HTMLElement {
  const row = screen.getByText(text).closest("li");
  if (row === null) throw new Error("expected a list row containing " + text);
  return row as HTMLElement;
}

function replayCalls(state: ApiState): string[] {
  return state.calls.filter(
    (url) => url.includes("/api/v1/projects/") && url.includes("/events?"),
  );
}

beforeEach(() => {
  vi.useFakeTimers({
    toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval", "Date"],
  });
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("ControlCenter operational surfaces", () => {
  it("renders the fleet with exact registry state counts and real records", async () => {
    const api = installApi();

    renderControlCenter(api);
    await settle();

    const counts = screen.getByLabelText("Exact project state counts");
    expect(within(counts).getByText("READY 1")).toBeInTheDocument();
    expect(within(counts).getByText("ACTIVE 1")).toBeInTheDocument();
    expect(within(counts).getByText("BLOCKED 0")).toBeInTheDocument();
    expect(screen.getByText(/2 registered projects/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Project Alpha" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Project Beta" })).toBeInTheDocument();
    expect(screen.getByText(/working tree clean/)).toBeInTheDocument();
    expect(screen.getByText(/working tree: UNAVAILABLE/)).toBeInTheDocument();
    expect(
      api.state.calls.filter((url) => url.includes("/api/v1/control-center/fleet")).length,
    ).toBeGreaterThan(0);
  });

  it("renders bounded project detail and run detail from real API payloads", async () => {
    const api = installApi();

    renderControlCenter(api, { selectedProjectId: PROJECT_A_ID });
    await settle();
    fireEvent.click(screen.getByRole("tab", { name: "Project detail" }));
    await settle();

    expect(
      screen.getByText(
        "Last validation event: NO VALIDATION EVENTS RECORDED (UNAVAILABLE, not zero).",
      ),
    ).toBeInTheDocument();

    const detailRuns = screen.getByLabelText("Recent runs");
    fireEvent.click(within(detailRuns).getByRole("button", { name: "Open run" }));
    await settle();

    expect(screen.getByRole("heading", { name: "Run aabbccdd" })).toBeInTheDocument();
    expect(screen.getByText("dddddddd")).toBeInTheDocument();
    expect(screen.getByText(EXECUTOR_IDENTITY)).toBeInTheDocument();
    const timelineItems = screen.getAllByTestId("timeline-event");
    expect(timelineItems).toHaveLength(2);
    expect(within(timelineItems[1] as HTMLElement).getByText("run.completed")).toBeInTheDocument();
    expect(within(timelineItems[1] as HTMLElement).getByText("COMPLETED")).toBeInTheDocument();
  });

  it("renders the bounded tests and errors/warnings surfaces from real payloads", async () => {
    const api = installApi();

    renderControlCenter(api, { selectedProjectId: PROJECT_A_ID });
    await settle();

    fireEvent.click(screen.getByRole("tab", { name: "Tests" }));
    await settle();
    expect(screen.getByText(/test.started 2/)).toBeInTheDocument();
    expect(screen.getByText("PASSED")).toBeInTheDocument();
    expect(screen.getByText(/Runs inside the window without test telemetry: 1/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Errors / warnings" }));
    await settle();
    expect(screen.getByRole("heading", { name: "Errors (1)" })).toBeInTheDocument();
    expect(screen.getByText("run.failed: bounded failure summary")).toBeInTheDocument();
    expect(screen.getByText(/redis status is degraded: hot cache unreachable/)).toBeInTheDocument();
  });

  it("shows explicit loading and a truthful empty fleet instead of fabricated counts", async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const api = installApi({ fleetGate: gate, fleet: emptyFleetResponse() });

    renderControlCenter(api);
    await settle();
    expect(screen.getByText("Loading operational fleet...")).toBeInTheDocument();

    release();
    await settle();
    expect(screen.getByText("The registry is empty; there is no project state to count.")).toBeInTheDocument();
    const counts = screen.getByLabelText("Exact project state counts");
    expect(within(counts).getByText("READY 0")).toBeInTheDocument();
    expect(within(counts).getByText("BLOCKED 0")).toBeInTheDocument();
  });

  it("surfaces a bounded fleet API failure and recovers through the refresh control", async () => {
    const api = installApi({
      fleetStatus: 503,
      fleet: { detail: "control center database unavailable" },
    });

    renderControlCenter(api);
    await settle();
    expect(
      screen.getByText(
        "Control Center fleet is unavailable: control center database unavailable",
      ),
    ).toBeInTheDocument();

    api.state.fleetStatus = 200;
    api.state.fleet = fleetResponse();
    fireEvent.click(screen.getByRole("button", { name: "Refresh fleet" }));
    await settle();

    expect(screen.queryByText(/Control Center fleet is unavailable/)).toBeNull();
    expect(within(screen.getByLabelText("Exact project state counts")).getByText("READY 1")).toBeInTheDocument();
  });

  it("selects an operational project through the real selector control", async () => {
    const api = installApi();

    const { onSelectProject } = renderControlCenter(api);
    await settle();
    fireEvent.change(screen.getByLabelText("Operational project"), {
      target: { value: PROJECT_A_ID },
    });
    await settle();

    expect(onSelectProject).toHaveBeenCalledWith(PROJECT_A_ID);
    expect(screen.getByRole("tab", { name: "Project detail" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });
});

describe("ControlCenter run detail dedicated timeline", () => {
  it("keeps an older selected run timeline independent from the saturated project buffer", async () => {
    const saturated = Array.from({ length: 200 }, (_, index) =>
      envelope({
        event_id: "77777777-0000-4000-8000-" + String(index + 1).padStart(12, "0"),
        ordering_id: 1000 + index,
        run_id: RUN_RECENT_ID,
      }),
    );
    const api = installApi({ replay: eventPage(saturated) });

    renderControlCenter(api, { selectedProjectId: PROJECT_A_ID });
    await settle();

    fireEvent.click(screen.getByRole("tab", { name: "Runs" }));
    await settle();
    fireEvent.click(
      within(screen.getByLabelText("Active runs")).getByRole("button", { name: "Open run" }),
    );
    await settle();

    let items = screen.getAllByTestId("timeline-event");
    expect(items).toHaveLength(2);
    expect(within(items[0] as HTMLElement).getByText("#11")).toBeInTheDocument();
    expect(within(items[1] as HTMLElement).getByText("#12")).toBeInTheDocument();
    expect(screen.getByText(/bounded to 100/)).toBeInTheDocument();

    const live = envelope({
      event_id: "aaaa1111-0000-4000-8000-000000000013",
      ordering_id: 13,
      event_type: "executor.started",
      run_id: RUN_ACTIVE_ID,
      payload: { adapter: EXECUTOR_IDENTITY },
    });
    FakeEventSource.instances[0]?.emit("executor.started", live);
    await settle();

    items = screen.getAllByTestId("timeline-event");
    expect(items).toHaveLength(3);
    expect(within(items[2] as HTMLElement).getByText("#13")).toBeInTheDocument();

    FakeEventSource.instances[0]?.emit("executor.started", live);
    await settle();
    expect(screen.getAllByTestId("timeline-event")).toHaveLength(3);

    FakeEventSource.instances[0]?.fail();
    await settle(1000);
    const reconnected = FakeEventSource.instances[1];
    expect(reconnected).toBeDefined();
    reconnected?.emit("executor.started", live);
    await settle();
    expect(screen.getAllByTestId("timeline-event")).toHaveLength(3);
    expect(
      screen.getAllByTestId("timeline-event").filter((item) => item.textContent?.includes("#13")),
    ).toHaveLength(1);
  });

  it("reseeds the dedicated timeline when the run or the project changes", async () => {
    const api = installApi();

    const view = renderControlCenter(api, { selectedProjectId: PROJECT_A_ID });
    await settle();
    fireEvent.click(screen.getByRole("tab", { name: "Runs" }));
    await settle();
    fireEvent.click(
      within(screen.getByLabelText("Active runs")).getByRole("button", { name: "Open run" }),
    );
    await settle();

    FakeEventSource.instances[0]?.emit(
      "executor.started",
      envelope({
        event_id: "aaaa1111-0000-4000-8000-000000000013",
        ordering_id: 13,
        event_type: "executor.started",
        run_id: RUN_ACTIVE_ID,
      }),
    );
    await settle();
    expect(screen.getAllByTestId("timeline-event")).toHaveLength(3);

    api.state.runDetail = runDetailResponse({
      run: runSummary({
        run_id: RUN_RECENT_ID,
        status: "FAILED",
        stage: "run.failed",
        last_event_type: "run.failed",
      }),
      timeline: [
        envelope({
          event_id: "bbbb2222-0000-4000-8000-000000000021",
          ordering_id: 21,
          run_id: RUN_RECENT_ID,
        }),
      ],
    });
    fireEvent.click(screen.getByRole("button", { name: "Back to runs" }));
    await settle();
    fireEvent.click(within(rowFor("eeff0011")).getByRole("button", { name: "Open run" }));
    await settle();

    const switched = screen.getAllByTestId("timeline-event");
    expect(switched).toHaveLength(1);
    expect(within(switched[0] as HTMLElement).getByText("#21")).toBeInTheDocument();
    expect(screen.queryByText("#13")).toBeNull();

    view.rerender(
      <ControlCenter
        projects={PROJECT_OPTIONS}
        selectedProjectId={PROJECT_B_ID}
        onSelectProject={vi.fn()}
      />,
    );
    await settle();

    expect(screen.queryByRole("heading", { name: /Run aabbccdd/ })).toBeNull();
    expect(screen.queryAllByTestId("timeline-event")).toHaveLength(0);
  });
});

describe("ControlCenter fleet pagination", () => {
  it("navigates bounded pages over more than one window with global counts", async () => {
    const globalCounts = {
      offline: 0,
      stale: 0,
      indexing: 0,
      ready: 1,
      active: 1,
      degraded: 0,
      blocked: 1,
    };
    const gammaId = "c3c3c3c3-0000-4000-8000-000000000003";
    const firstPage = fleetResponse({
      project_count: 3,
      state_counts: globalCounts,
      projects: [
        headline(),
        headline({
          project_id: PROJECT_B_ID,
          name: "Project Beta",
          relative_path: "beta",
          state: "ACTIVE",
          working_tree_clean: null,
        }),
      ],
      truncated: true,
      offset: 0,
      limit: 2,
      has_more: true,
      next_offset: 2,
    });
    const secondPage = fleetResponse({
      project_count: 3,
      state_counts: globalCounts,
      projects: [
        headline({
          project_id: gammaId,
          name: "Project Gamma",
          relative_path: "gamma",
          state: "BLOCKED",
          working_tree_clean: null,
        }),
      ],
      truncated: true,
      offset: 2,
      limit: 2,
      has_more: false,
      next_offset: null,
    });
    const api = installApi({ fleet: firstPage, fleetByOffset: { "2": secondPage } });

    renderControlCenter(api);
    await settle();

    expect(screen.getByRole("heading", { name: "Project Alpha" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Project Gamma" })).toBeNull();
    const counts = screen.getByLabelText("Exact project state counts");
    expect(within(counts).getByText("BLOCKED 1")).toBeInTheDocument();
    expect(screen.getByText(/3 registered projects/)).toBeInTheDocument();
    expect(screen.getByText(/showing projects 1 to 2 of 3/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    await settle();

    expect(screen.queryByRole("heading", { name: "Project Alpha" })).toBeNull();
    expect(screen.getByRole("heading", { name: "Project Gamma" })).toBeInTheDocument();
    expect(within(screen.getByLabelText("Exact project state counts")).getByText("BLOCKED 1")).toBeInTheDocument();
    expect(screen.getByText(/showing projects 3 to 3 of 3/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
    expect(
      api.state.calls.some((url) => url.includes("/api/v1/control-center/fleet?offset=2&limit=50")),
    ).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Previous page" }));
    await settle();

    expect(screen.getByRole("heading", { name: "Project Alpha" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Project Gamma" })).toBeNull();
    expect(screen.getByText(/showing projects 1 to 2 of 3/)).toBeInTheDocument();
  });
});

describe("ControlCenter event stream", () => {
  it("streams SSE updates over durable replay and reconciles reconnects without duplicates or loss", async () => {
    const api = installApi({
      replay: eventPage([
        envelope({
          event_id: "11111111-0000-4000-8000-000000000001",
          ordering_id: 1,
          run_id: RUN_ACTIVE_ID,
        }),
      ]),
    });

    renderControlCenter(api, { selectedProjectId: PROJECT_A_ID });
    await settle();

    const first = FakeEventSource.instances[0];
    expect(first).toBeDefined();
    expect(first?.url).toContain("/api/v1/projects/" + PROJECT_A_ID + "/events/stream");
    expect(first?.url).toContain("after=1");
    expect(first?.url).toContain("max_events=100");
    expect(first?.url).toContain("timeout_seconds=30");

    fireEvent.click(screen.getByRole("tab", { name: "Project detail" }));
    await settle();
    expect(screen.getAllByTestId("timeline-event")).toHaveLength(1);

    first?.open();
    await settle();
    expect(screen.getByText("LIVE (SSE)")).toBeInTheDocument();

    const streamed = envelope({
      event_id: "11111111-0000-4000-8000-000000000002",
      ordering_id: 2,
      event_type: "executor.started",
      run_id: RUN_ACTIVE_ID,
      payload: { adapter: EXECUTOR_IDENTITY },
    });
    first?.emit("executor.started", streamed);
    first?.emit("executor.started", streamed);
    await settle();
    expect(screen.getAllByTestId("timeline-event")).toHaveLength(2);

    first?.fail();
    await settle(1000);

    const second = FakeEventSource.instances[1];
    expect(second).toBeDefined();
    expect(first?.closed).toBe(true);
    expect(second?.url).toContain("after=2");
    expect(screen.getAllByTestId("timeline-event")).toHaveLength(2);
  });

  it("moves a run from active to recent when terminal telemetry arrives", async () => {
    const api = installApi();

    renderControlCenter(api, { selectedProjectId: PROJECT_A_ID });
    await settle();
    fireEvent.click(screen.getByRole("tab", { name: "Runs" }));
    await settle();

    expect(screen.getByRole("heading", { name: "Active runs (1)" })).toBeInTheDocument();
    expect(
      within(screen.getByLabelText("Active runs")).getByTestId("run-row-active"),
    ).toBeInTheDocument();

    FakeEventSource.instances[0]?.emit(
      "run.completed",
      envelope({
        event_id: "22222222-0000-4000-8000-000000000007",
        ordering_id: 7,
        event_type: "run.completed",
        run_id: RUN_ACTIVE_ID,
        payload: { status: "COMPLETED" },
      }),
    );
    await settle();

    expect(screen.getByRole("heading", { name: "Active runs (0)" })).toBeInTheDocument();
    expect(screen.getByText("No run is currently active for this project.")).toBeInTheDocument();
    const recent = screen.getByLabelText("Recent runs");
    expect(within(recent).getAllByTestId("run-row-recent")).toHaveLength(2);
    expect(within(recent).getByText("aabbccdd")).toBeInTheDocument();
    expect(within(recent).getByText("COMPLETED")).toBeInTheDocument();
    expect(within(recent).getByText("FAILED")).toBeInTheDocument();
  });

  it("falls back to bounded durable replay polling and recovers when the stream returns", async () => {
    const api = installApi();

    renderControlCenter(api, { selectedProjectId: PROJECT_A_ID });
    await settle();
    expect(replayCalls(api.state)).toHaveLength(1);

    FakeEventSource.instances[0]?.fail();
    await settle(1000);
    FakeEventSource.instances[1]?.fail();
    await settle(2000);
    FakeEventSource.instances[2]?.fail();
    await settle(4000);
    FakeEventSource.instances[3]?.fail();
    await settle(0);

    expect(screen.getByText("FALLBACK (BOUNDED REPLAY POLLING)")).toBeInTheDocument();
    expect(screen.getByText(/SSE transport unreachable; bounded durable replay polling is active./)).toBeInTheDocument();
    expect(
      screen.getByText(/The live SSE stream is unreachable; bounded durable replay polling is active./),
    ).toBeInTheDocument();
    expect(replayCalls(api.state).length).toBeGreaterThanOrEqual(2);

    await settle(8000);
    const recovered = FakeEventSource.instances[4];
    expect(recovered).toBeDefined();
    recovered?.open();
    await settle();

    expect(screen.getByText("LIVE (SSE)")).toBeInTheDocument();
    expect(
      screen.queryByText(/The live SSE stream is unreachable; bounded durable replay polling is active./),
    ).toBeNull();
  });
});

describe("ControlCenter truthful metric rendering", () => {
  it("distinguishes ESTIMATED, exact and unavailable metrics from zero", async () => {
    const api = installApi({
      detail: detailResponse({
        recent_events: [
          envelope({
            event_id: "33333333-0000-4000-8000-000000000001",
            ordering_id: 31,
            event_type: "cache.hit",
            payload: { input_tokens: 120, estimated: true },
          }),
          envelope({
            event_id: "33333333-0000-4000-8000-000000000002",
            ordering_id: 32,
            event_type: "cache.miss",
            payload: { input_tokens: 42 },
          }),
          envelope({
            event_id: "33333333-0000-4000-8000-000000000003",
            ordering_id: 33,
            event_type: "tool.called",
            payload: { latency_ms: 900, estimated: true },
          }),
        ],
      }),
    });

    renderControlCenter(api, { selectedProjectId: PROJECT_A_ID });
    await settle();
    fireEvent.click(screen.getByRole("tab", { name: "Project detail" }));
    await settle();

    expect(within(rowFor("120")).getByText("ESTIMATED")).toBeInTheDocument();
    expect(within(rowFor("42")).queryByText("ESTIMATED")).toBeNull();
    expect(within(rowFor("900")).queryByText("ESTIMATED")).toBeNull();

    fireEvent.click(screen.getByRole("tab", { name: "Platform health" }));
    await settle();

    expect(screen.getAllByText("NOT YET INSTRUMENTED")).toHaveLength(4);
    expect(within(rowFor("exact_provider_cost")).getByText("NOT YET INSTRUMENTED")).toBeInTheDocument();
    expect(screen.getByText(/are never displayed as zero/)).toBeInTheDocument();
  });
});

describe("ControlCenter bounds and navigation", () => {
  it("bounds the live timeline and reports events dropped from the bounded buffer", async () => {
    const api = installApi();

    renderControlCenter(api, { selectedProjectId: PROJECT_A_ID });
    await settle();
    FakeEventSource.instances[0]?.open();
    await settle();

    await act(async () => {
      for (let ordering = 1; ordering <= 250; ordering += 1) {
        FakeEventSource.instances[0]?.emit(
          "executor.started",
          envelope({
            event_id: "44444444-0000-4000-8000-" + String(ordering).padStart(12, "0"),
            ordering_id: ordering,
            run_id: RUN_ACTIVE_ID,
          }),
        );
      }
    });

    fireEvent.click(screen.getByRole("tab", { name: "Project detail" }));
    await settle();

    const items = screen.getAllByTestId("timeline-event");
    expect(items).toHaveLength(200);
    expect(screen.getByText(/Showing 200 events in canonical order, bounded to 200./)).toBeInTheDocument();
    expect(
      screen.getByText(/50 older events left this bounded live buffer; canonical history stays in PostgreSQL./),
    ).toBeInTheDocument();
    expect(within(items[0] as HTMLElement).getByText("#51")).toBeInTheDocument();
    expect(within(items[199] as HTMLElement).getByText("#250")).toBeInTheDocument();
  });

  it("supports keyboard navigation across the operational surfaces", async () => {
    const api = installApi();

    renderControlCenter(api);
    await settle();
    const fleetTab = screen.getByRole("tab", { name: "Fleet" });
    fleetTab.focus();
    fireEvent.keyDown(fleetTab, { key: "ArrowRight" });
    await settle();

    expect(screen.getByRole("tab", { name: "Project detail" })).toHaveAttribute(
      "aria-selected",
      "true",
    );

    fireEvent.keyDown(screen.getByRole("tab", { name: "Project detail" }), { key: "End" });
    await settle();
    expect(screen.getByRole("tab", { name: "Errors / warnings" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });
});

describe("ControlCenter backend parity", () => {
  it("keeps the dashboard event vocabulary identical to the canonical backend telemetry vocabulary", () => {
    let source: string | null = null;
    for (const candidate of ["../backend/app/telemetry.py", "../../backend/app/telemetry.py"]) {
      try {
        source = readFileSync(candidate, "utf8");
        break;
      } catch {
        // Try the next repository-relative candidate before failing the parity guard.
      }
    }
    if (source === null) throw new Error("backend telemetry source not found");
    const declaration = source.match(/CANONICAL_EVENT_TYPES\s*=\s*\(([\s\S]*?)\)/);
    expect(declaration).not.toBeNull();
    const backendTypes = [...(declaration?.[1] ?? "").matchAll(/"([^"]+)"/g)].map(
      (match) => match[1],
    );
    expect(backendTypes).toEqual([...CANONICAL_EVENT_TYPES]);
  });
});
