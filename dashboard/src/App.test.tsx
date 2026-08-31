import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const healthPayload = {
  status: "ok",
  version: "0.0.1-bootstrap",
  environment: "test",
  timestamp: "2026-08-31T12:00:00Z",
  data_root: "/var/lib/hive",
  checks: {
    postgres: { status: "ok", details: { pgvector: true } },
    redis: { status: "ok", details: { canonical: false } },
    storage: { status: "ok", details: { writable: true } },
  },
};

const project = {
  project_id: "00000000-0000-0000-0000-000000000001",
  name: "HIVE",
  relative_path: "hive",
  git_branch: "main",
  git_head_sha: "1234567890abcdef1234567890abcdef12345678",
  detached_head: false,
  repository_accessible: true,
  working_tree_clean: true,
  language_stack: ["python", "typescript"],
  state: "READY",
  inspection_error: null,
  created_at: "2026-08-31T12:00:00Z",
  updated_at: "2026-08-31T12:00:00Z",
  last_inspected_at: "2026-08-31T12:00:00Z",
};

function response(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function installFetch(projects: unknown[] = []) {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = input.toString();
    if (url.endsWith("/projects") && init?.method !== "POST") {
      return Promise.resolve(response(projects));
    }
    if (url.endsWith("/health")) return Promise.resolve(response(healthPayload));
    return Promise.resolve(response(project));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("renders service health returned by the API", async () => {
    installFetch();

    render(<App />);

    await waitFor(() => expect(screen.getByText("HIVE is ready locally.")).toBeInTheDocument());
    expect(screen.getByText("Vector extension available")).toBeInTheDocument();
    expect(screen.getByText("Non-canonical hot cache")).toBeInTheDocument();
    expect(screen.getByText("/var/lib/hive")).toBeInTheDocument();
  });

  it("renders an explicit empty Project Fleet state", async () => {
    installFetch();

    render(<App />);

    expect(await screen.findByText("No projects registered yet.")).toBeInTheDocument();
    expect(screen.getByText("0 registered")).toBeInTheDocument();
  });

  it("registers through the real API and refreshes the fleet", async () => {
    let registered = false;
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = input.toString();
      if (url.endsWith("/health")) return Promise.resolve(response(healthPayload));
      if (url.endsWith("/projects") && init?.method === "POST") {
        registered = true;
        return Promise.resolve(response(project, 201));
      }
      return Promise.resolve(response(registered ? [project] : []));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await screen.findByText("No projects registered yet.");
    fireEvent.change(screen.getByLabelText("Project name"), { target: { value: "HIVE" } });
    fireEvent.change(screen.getByLabelText("Relative path"), { target: { value: "hive" } });
    fireEvent.click(screen.getByRole("button", { name: "Register project" }));

    expect(await screen.findByText("1234567")).toBeInTheDocument();
    expect(screen.getByText("python, typescript")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/projects"),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("updates a project after manual re-inspection", async () => {
    const updated = { ...project, git_head_sha: "abcdef1234567890abcdef1234567890abcdef12" };
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = input.toString();
      if (url.endsWith("/health")) return Promise.resolve(response(healthPayload));
      if (init?.method === "POST" && url.endsWith("/inspect")) return Promise.resolve(response(updated));
      return Promise.resolve(response([project]));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await screen.findByText("1234567");
    fireEvent.click(screen.getByRole("button", { name: "Re-inspect" }));

    expect(await screen.findByText("abcdef1")).toBeInTheDocument();
  });

  it("renders the fleet API failure state", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      if (input.toString().endsWith("/health")) return Promise.resolve(response(healthPayload));
      return Promise.resolve(response({ detail: "database unavailable" }, 503));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(await screen.findByText("database unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry fleet" })).toBeInTheDocument();
  });
});
