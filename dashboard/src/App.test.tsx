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

const task = {
  task_id: "00000000-0000-0000-0000-000000000101",
  project_id: project.project_id,
  title: "Prompt task",
  source_type: "STRUCTURED_TEXT",
  intake_status: "READY",
  original_blob_sha256: "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
  original_filename: null,
  media_type: "text/plain",
  logical_size: 12,
  compressed_size: 21,
  extracted_text_available: true,
  extraction_method: "hive-text-normalizer",
  extraction_version: "1",
  extraction_error: null,
  page_count: null,
  created_at: "2026-08-31T12:00:00Z",
  updated_at: "2026-08-31T12:00:00Z",
};

const storage = {
  task_count: 1,
  referenced_logical_bytes: 12,
  unique_logical_bytes: 12,
  physical_cas_bytes: 21,
  unique_blob_count: 1,
  deduplication_delta_bytes: 0,
  compression_delta_bytes: -9,
  compression_ratio: 1.75,
  compression_savings_bytes: null,
  compression_delta_label: "overhead",
};

const retrievalCorpus = {
  project_id: project.project_id,
  state: "CURRENT",
  last_successful_sync: "2026-08-31T12:00:00Z",
  latest_run: {
    run_id: "00000000-0000-0000-0000-000000000201",
    project_id: project.project_id,
    status: "COMPLETED",
    completed_at: "2026-08-31T12:00:00Z",
    repository_source_count: 4,
    task_source_count: 1,
    chunk_count: 5,
    reference_count: 8,
    repository_reference_count: 6,
    task_reference_count: 2,
    new_chunk_count: 5,
    reused_chunk_count: 0,
    new_reference_count: 8,
    reused_reference_count: 0,
    removed_reference_count: 0,
    error: null,
  },
  chunk_count: 5,
  reference_count: 8,
  repository_reference_count: 6,
  task_reference_count: 2,
};

const semanticStatus = {
  project_id: project.project_id,
  state: "CURRENT",
  enabled: true,
  configured: true,
  profile: {
    adapter_kind: "openai-compatible-http",
    model: "fixture",
    model_revision: "v1",
    dimensions: 8,
    distance_metric: "cosine",
    identity_fingerprint: "a".repeat(64),
  },
  current_corpus_run_id: retrievalCorpus.latest_run.run_id,
  latest_run: {
    status: "COMPLETED",
    current_chunk_count: 5,
    newly_embedded_count: 5,
    reused_embedding_count: 0,
    failed_count: 0,
    provider_request_count: 3,
    error: null,
  },
  total_current_chunks: 5,
  embedded_chunk_count: 5,
  missing_chunk_count: 0,
  last_error: null,
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
    if (url.endsWith("/retrieval/corpus")) return Promise.resolve(response(retrievalCorpus));
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

  it("loads real intake state and submits structured text for a selected project", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = input.toString();
      if (url.endsWith("/health")) return Promise.resolve(response(healthPayload));
      if (url.endsWith("/projects") && init?.method !== "POST") {
        return Promise.resolve(response([project]));
      }
      if (url.endsWith("/tasks/text") && init?.method === "POST") {
        return Promise.resolve(response(task, 201));
      }
      if (url.endsWith("/tasks")) return Promise.resolve(response([task]));
      if (url.endsWith("/storage")) return Promise.resolve(response(storage));
      if (url.endsWith("/retrieval/corpus")) return Promise.resolve(response(retrievalCorpus));
      return Promise.resolve(response({ text: "derived text" }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await screen.findByRole("option", { name: /HIVE/ });
    fireEvent.change(screen.getByLabelText("Registered project"), {
      target: { value: project.project_id },
    });

    expect(await screen.findByText("Prompt task")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Text"), { target: { value: "new prompt" } });
    fireEvent.click(screen.getByRole("button", { name: "Accept text" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/v1/projects/" + project.project_id + "/tasks/text"),
        expect.objectContaining({ method: "POST" }),
      );
    });
    expect(await screen.findByText("Texto aceito e armazenado no CAS.")).toBeInTheDocument();
  });

  it("syncs the selected corpus and renders bounded lexical results", async () => {
    const result = {
      reference_id: "00000000-0000-0000-0000-000000000301",
      source_kind: "REPOSITORY_SYMBOL",
      lexical_score: 4.2,
      snippet: "def get_project_order():\n    return order",
      path: "src/order_service.py",
      title: null,
      qualified_symbol: "OrderService.get_project_order",
      source_content_sha256: "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
      start_line: 1,
      end_line: 2,
      start_char: 0,
      end_char: 42,
    };
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = input.toString();
      if (url.endsWith("/health")) return Promise.resolve(response(healthPayload));
      if (url.endsWith("/projects") && init?.method !== "POST") {
        return Promise.resolve(response([project]));
      }
      if (url.endsWith("/tasks")) return Promise.resolve(response([]));
      if (url.endsWith("/storage")) return Promise.resolve(response(storage));
      if (url.endsWith("/retrieval/corpus/sync")) return Promise.resolve(response(retrievalCorpus));
      if (url.endsWith("/retrieval/semantic/sync")) return Promise.resolve(response({ status: "COMPLETED" }));
      if (url.endsWith("/retrieval/semantic")) return Promise.resolve(response({
        ...semanticStatus,
        results: [{ ...result, semantic_run_id: "run", semantic_score: 0.9, semantic_distance: 0.1 }],
      }));
      if (url.endsWith("/retrieval/lexical")) {
        return Promise.resolve(response({
          project_id: project.project_id,
          query: "OrderService.get_project_order",
          normalized_query: "order service get project order",
          top_k: 5,
          results: [result],
        }));
      }
      if (url.endsWith("/retrieval/corpus")) return Promise.resolve(response(retrievalCorpus));
      return Promise.resolve(response({ text: "derived text" }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    await screen.findByRole("option", { name: /HIVE/ });
    fireEvent.change(await screen.findByLabelText("Registered project"), {
      target: { value: project.project_id },
    });
    expect(await screen.findByText("CURRENT")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Sync corpus" }));
    expect(await screen.findByText("Corpus sincronizado com dados derivados determinísticos.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Query"), {
      target: { value: "OrderService.get_project_order" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search lexical" }));

    expect(await screen.findByText("OrderService.get_project_order")).toBeInTheDocument();
    expect(screen.getByText(/Lines 1-2/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Mode"), { target: { value: "semantic" } });
    fireEvent.click(screen.getByRole("button", { name: "Search semantic" }));
    expect(await screen.findByText(/score 0.900/)).toBeInTheDocument();
  });
});
