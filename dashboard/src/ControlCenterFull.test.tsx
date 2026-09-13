import { render, screen, waitFor } from "@testing-library/react";
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

afterEach(() => vi.unstubAllGlobals());

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
});
