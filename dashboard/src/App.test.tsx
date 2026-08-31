import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import App from "./App";

describe("App", () => {
  it("renders service health returned by the API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
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
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    render(<App />);

    await waitFor(() => expect(screen.getByText("HIVE is ready locally.")).toBeInTheDocument());
    expect(screen.getByText("Vector extension available")).toBeInTheDocument();
    expect(screen.getByText("Non-canonical hot cache")).toBeInTheDocument();
    expect(screen.getByText("/var/lib/hive")).toBeInTheDocument();
  });
});
