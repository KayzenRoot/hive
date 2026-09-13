import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ControlCenterMetrics from "./ControlCenterMetrics";

const projectId = "00000000-0000-0000-0000-0000000000a1";

function metric(value: number | null, provenance = "EXACT") {
  return { value, provenance, source: "fixture" };
}

function metricsPayload(scope: "GLOBAL" | "PROJECT" = "GLOBAL") {
  return {
    metrics_evidence_version: "control-center-metrics-v1",
    generated_at: "2026-09-13T11:00:00Z",
    scope,
    project_id: scope === "PROJECT" ? projectId : null,
    project_count: scope === "PROJECT" ? 1 : 2,
    canonical_store: "postgres",
    hot_store: "redis",
    hot_store_canonical: false,
    scanned_events: 8,
    window_truncated: false,
    token: {
      input_tokens: metric(100, "ESTIMATED"),
      output_tokens: metric(20),
      cached_tokens: metric(40),
      fresh_tokens: metric(60),
      token_count: metric(null, "UNAVAILABLE"),
      token_budget: metric(null, "UNAVAILABLE"),
      token_savings: metric(null, "UNAVAILABLE"),
    },
    context: {
      before_tokens: metric(1000, "ESTIMATED"),
      after_tokens: metric(600, "ESTIMATED"),
      reduction_tokens: metric(400, "ESTIMATED"),
      reduction_ratio: metric(0.4, "ESTIMATED"),
    },
    cache: {
      hits: metric(null, "UNAVAILABLE"),
      misses: metric(null, "UNAVAILABLE"),
      observed_decisions: metric(null, "UNAVAILABLE"),
      hit_rate: metric(null, "UNAVAILABLE"),
    },
    storage: {
      logical_task_bytes: metric(2048),
      physical_referenced_bytes: metric(1024),
      saved_bytes: metric(1024),
      savings_ratio: metric(0.5),
      task_count: metric(2),
      referenced_blob_count: metric(1),
    },
    history: [],
    history_max_points: 100,
    cost_provenance: "UNAVAILABLE",
  };
}

function response(payload: unknown) {
  return Promise.resolve({
    ok: true,
    json: async () => payload,
  } as Response);
}

describe("ControlCenterMetrics", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/v1/projects")) {
          return response([{ project_id: projectId, name: "Alpha" }]);
        }
        if (url.includes("project_id=")) return response(metricsPayload("PROJECT"));
        return response(metricsPayload("GLOBAL"));
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("renders explicit provenance and does not render unavailable cache as zero", async () => {
    render(<ControlCenterMetrics />);

    expect(await screen.findByText("Control Center Metrics")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("ESTIMATED")).toBeInTheDocument());
    expect(screen.getAllByText("UNAVAILABLE").length).toBeGreaterThan(0);
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
  });

  it("switches from deterministic global aggregation to project scope", async () => {
    render(<ControlCenterMetrics />);

    const scope = await screen.findByLabelText("Metrics scope");
    fireEvent.change(scope, { target: { value: projectId } });

    await waitFor(() => {
      const calls = vi.mocked(fetch).mock.calls.map((call) => String(call[0]));
      expect(calls.some((url) => url.includes(`project_id=${projectId}`))).toBe(true);
    });
    expect(await screen.findByText(/Escopo:/)).toBeInTheDocument();
  });

  it("shows storage as logical versus physical evidence", async () => {
    render(<ControlCenterMetrics />);

    await screen.findByText("Storage");
    expect(screen.getByText("2.0 KiB")).toBeInTheDocument();
    expect(screen.getAllByText("1.0 KiB").length).toBeGreaterThanOrEqual(2);
  });
});
