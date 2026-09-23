import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DashboardRoot from "./DashboardRoot";

vi.mock("./ControlCenter", () => ({
  default: (props: { selectedProjectId: string; onSelectProject: (value: string) => void }) => (
    <main>
      <label>
        Operational project
        <input
          aria-label="Operational project"
          value={props.selectedProjectId}
          onChange={(event) => props.onSelectProject(event.target.value)}
        />
      </label>
    </main>
  ),
}));

describe("operational dashboard root", () => {
  const values = new Map<string, string>();
  const storage = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string): void => {
      values.set(key, value);
    },
    removeItem: (key: string): void => {
      values.delete(key);
    },
    clear: () => values.clear(),
    key: (index: number) => Array.from(values.keys())[index] ?? null,
    get length() {
      return values.size;
    },
  } as Storage;

  beforeEach(() => {
    values.clear();
    Object.defineProperty(window, "localStorage", { configurable: true, value: storage });
  });
  afterEach(() => cleanup());

  it("starts on the operational project selector without task-intake UI", () => {
    render(<DashboardRoot />);

    expect(screen.getByRole("main")).toBeTruthy();
    expect(screen.getByLabelText("Operational project")).toHaveValue("");
    expect(screen.queryByText(/task intake|upload task|retrieval lab/i)).toBeNull();
  });

  it("persists the selected project when browser storage is available", () => {
    render(<DashboardRoot />);
    fireEvent.change(screen.getByLabelText("Operational project"), {
      target: { value: "project-42" },
    });

    expect(storage.getItem("hive.control-center.project")).toBe("project-42");
  });
});
