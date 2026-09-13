import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ControlCenterFull from "./ControlCenterFull";
import {
  FULL_ALERTS,
  FULL_CHARTS,
  FULL_HEALTH,
  FULL_PROJECT_CAPABILITIES,
} from "./controlCenterFullContract";

const snapshot = {
  control_center_full_version: "control-center-full-v1",
  generated_at: "2026-09-13T12:00:00Z",
  project_id: "project-a",
  project: {
    name: "Project A",
    relative_path: "project-a",
    state: "READY",
    git_branch: "main",
    git_head_sha: "a".repeat(40),
    short_head: "aaaaaaa",
  },
  capabilities: FULL_PROJECT_CAPABILITIES.map((id) => ({
    id,
    status: "AVAILABLE",
    summary: id + " observed",
    provenance: "EXACT",
    details: { count: 1 },
  })),
  charts: FULL_CHARTS.map((id) => ({
    id,
    status: id === "cost-over-time" ? "UNAVAILABLE" : "AVAILABLE",
    points: [],
    max_points: 100,
    truncated: false,
  })),
  alerts: FULL_ALERTS.map((id) => ({
    id,
    status: id === "unexpected-cost-spike" ? "UNAVAILABLE" : "CLEAR",
    severity: "WARNING",
    summary: id + " observed",
    provenance: "EXACT",
  })),
  health: FULL_HEALTH.map((id) => ({
    id,
    status: "AVAILABLE",
    summary: id + " observed",
    provenance: "EXACT",
    details: {},
  })),
  canonical_store: "postgres",
  hot_store: "redis",
  hot_store_canonical: false,
  history_max_points: 100,
  project_scoped: true,
  full_v01_complete_claimed: false,
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ControlCenterFull", () => {
  it("renders the closed capability, chart, alert and health contract", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => snapshot }));

    render(<ControlCenterFull selectedProjectId="project-a" />);

    await waitFor(() => expect(screen.getByTestId("control-center-full")).toBeInTheDocument());
    expect(screen.getByText(/Full Control Center control-center-full-v1/)).toBeInTheDocument();
    expect(screen.getByText("project-intelligence")).toBeInTheDocument();
    expect(screen.getByText("tokens-over-time")).toBeInTheDocument();
    expect(screen.getByText("unexpected-cost-spike")).toBeInTheDocument();
    expect(screen.getByText("platform-resource-health")).toBeInTheDocument();
    expect(screen.getAllByText("UNAVAILABLE").length).toBeGreaterThan(0);
  });

  it("renders real chart geometry and bounded project records", async () => {
    const actualSnapshot = {
      ...snapshot,
      capabilities: snapshot.capabilities.map((capability) =>
        capability.id === "latest-commits"
          ? {
              ...capability,
              details: {
                commits: [{ sha: "a".repeat(40), subject: "fixture commit" }],
              },
            }
          : capability,
      ),
      charts: snapshot.charts.map((chart) =>
        chart.id === "tokens-over-time"
          ? {
              ...chart,
              points: [
                {
                  observed_at: "2026-09-13T12:00:00Z",
                  value: 42,
                  provenance: "EXACT",
                  source: "test:telemetry",
                  series: "input_tokens",
                },
                {
                  observed_at: "2026-09-13T12:01:00Z",
                  value: 50,
                  provenance: "ESTIMATED",
                  source: "test:telemetry",
                  series: "input_tokens",
                },
              ],
            }
          : chart,
      ),
      health: snapshot.health.map((surface) =>
        surface.id === "platform-resource-health"
          ? {
              ...surface,
              details: {
                observations: {
                  cpu: { status: "AVAILABLE", value: 0.5, source: "test:cpu" },
                },
              },
            }
          : surface,
      ),
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => actualSnapshot }));

    render(<ControlCenterFull selectedProjectId="project-a" />);

    await waitFor(() => expect(screen.getByTestId("control-center-full")).toBeInTheDocument());
    expect(document.querySelector('[data-chart-id="tokens-over-time"]')).toBeInTheDocument();
    expect(screen.getByText("fixture commit")).toBeInTheDocument();
    expect(screen.getByText("test:cpu")).toBeInTheDocument();
    expect(screen.getByTestId("chart-state-cost-over-time")).toHaveTextContent("UNAVAILABLE");
  });

  it("refreshes the same selected tab when the existing event signal advances", async () => {
    const initial = {
      ...snapshot,
      project: { ...snapshot.project, state: "READY" },
    };
    const refreshed = {
      ...snapshot,
      project: { ...snapshot.project, state: "ACTIVE" },
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => initial })
      .mockResolvedValueOnce({ ok: true, json: async () => refreshed });
    vi.stubGlobal("fetch", fetchMock);

    const { rerender } = render(
      <ControlCenterFull selectedProjectId="project-a" refreshSignal={0} />,
    );
    await waitFor(() => expect(screen.getByTestId("control-center-full")).toBeInTheDocument());
    const tab = screen.getByTestId("control-center-full");

    rerender(<ControlCenterFull selectedProjectId="project-a" refreshSignal={1} />);

    await waitFor(() => expect(screen.getByText("ACTIVE")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(screen.getByTestId("control-center-full")).toBe(tab);
  });
});
