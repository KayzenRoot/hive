import { useEffect, useState } from "react";

import { API_BASE_URL } from "./config";
import {
  FULL_ALERTS,
  FULL_CHARTS,
  FULL_HEALTH,
  FULL_PROJECT_CAPABILITIES,
} from "./controlCenterFullContract";
import { formatDateTime } from "./format";

type FullStatus =
  | "AVAILABLE"
  | "CLEAR"
  | "ACTIVE"
  | "DEGRADED"
  | "UNKNOWN"
  | "UNAVAILABLE"
  | "NOT_CONFIGURED";

type Provenance = "EXACT" | "ESTIMATED" | "UNAVAILABLE" | "UNKNOWN";

type Capability = {
  id: string;
  status: FullStatus;
  summary: string;
  provenance: Provenance;
  details: Record<string, unknown>;
};

type Chart = {
  id: string;
  status: FullStatus;
  points: { value: number | null; provenance: Provenance; series: string | null }[];
  max_points: number;
  truncated: boolean;
};

type Alert = {
  id: string;
  status: FullStatus;
  severity: string;
  summary: string;
  provenance: Provenance;
};

type HealthSurface = {
  id: string;
  status: FullStatus;
  summary: string;
  provenance: Provenance;
  details: Record<string, unknown>;
};

type FullResponse = {
  control_center_full_version: string;
  generated_at: string;
  project_id: string;
  project: {
    name: string;
    relative_path: string;
    state: string;
    git_branch: string | null;
    git_head_sha: string | null;
    short_head: string | null;
  };
  capabilities: Capability[];
  charts: Chart[];
  alerts: Alert[];
  health: HealthSurface[];
  canonical_store: string;
  hot_store: string;
  hot_store_canonical: boolean;
  history_max_points: number;
  project_scoped: boolean;
  full_v01_complete_claimed: boolean;
};

export type ControlCenterFullProps = {
  selectedProjectId: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isFullResponse(value: unknown): value is FullResponse {
  return (
    isRecord(value) &&
    typeof value.control_center_full_version === "string" &&
    isRecord(value.project) &&
    typeof value.project.name === "string" &&
    typeof value.project.relative_path === "string" &&
    Array.isArray(value.capabilities) &&
    Array.isArray(value.charts) &&
    Array.isArray(value.alerts) &&
    Array.isArray(value.health) &&
    typeof value.canonical_store === "string" &&
    typeof value.hot_store === "string" &&
    typeof value.hot_store_canonical === "boolean" &&
    typeof value.full_v01_complete_claimed === "boolean"
  );
}

function statusClass(status: FullStatus): string {
  return "state-badge state-" + status.toLowerCase().replace(/[^a-z0-9]+/g, "-");
}

function boundedDetailValue(value: unknown): string {
  if (Array.isArray(value)) return `${value.length} bounded item${value.length === 1 ? "" : "s"}`;
  if (typeof value === "string") return value.length > 120 ? value.slice(0, 117) + "..." : value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (value === null) return "UNAVAILABLE";
  return "structured value";
}

function CapabilityCard({ capability }: { capability: Capability }) {
  const detailEntries = Object.entries(capability.details).slice(0, 8);
  return (
    <article className="cc-card" aria-label={capability.id}>
      <div className="cc-card-heading">
        <h3>{capability.id}</h3>
        <span className={statusClass(capability.status)}>{capability.status}</span>
      </div>
      <p className="cc-muted">{capability.summary}</p>
      <p className="cc-muted">Provenance: {capability.provenance}</p>
      {detailEntries.length > 0 ? (
        <dl className="project-details">
          {detailEntries.map(([key, value]) => (
            <div key={key}>
              <dt>{key}</dt>
              <dd>{boundedDetailValue(value)}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </article>
  );
}

export default function ControlCenterFull({ selectedProjectId }: ControlCenterFullProps) {
  const [snapshot, setSnapshot] = useState<FullResponse | null>(null);
  const [failure, setFailure] = useState<{ projectId: string; message: string } | null>(null);

  useEffect(() => {
    if (!selectedProjectId) {
      return;
    }
    let disposed = false;
    fetch(
      API_BASE_URL +
        "/api/v1/control-center/projects/" +
        selectedProjectId +
        "/full?history_points=100",
      { cache: "no-store" },
    )
      .then(async (response) => {
        const payload: unknown = await response.json();
        if (!response.ok || !isFullResponse(payload)) {
          throw new Error("Full Control Center snapshot is unavailable");
        }
        if (!disposed) {
          setSnapshot(payload);
          setFailure(null);
        }
      })
      .catch((cause: unknown) => {
        if (!disposed) {
          setSnapshot(null);
          setFailure({
            projectId: selectedProjectId,
            message:
              cause instanceof Error ? cause.message : "Full Control Center request failed",
          });
        }
      });
    return () => {
      disposed = true;
    };
  }, [selectedProjectId]);

  if (!selectedProjectId) {
    return <p className="fleet-message">Select a project to open the full Control Center.</p>;
  }
  const error = failure?.projectId === selectedProjectId ? failure.message : null;
  const loading = snapshot === null && error === null;
  if (loading) {
    return <p className="fleet-message" role="status">Loading full Control Center...</p>;
  }
  if (error !== null) {
    return <p className="fleet-message error-message" role="alert">{error}</p>;
  }
  if (snapshot === null) {
    return <p className="fleet-message">The full Control Center snapshot is unavailable.</p>;
  }

  const capabilityIds = new Set(snapshot.capabilities.map((item) => item.id));
  const chartIds = new Set(snapshot.charts.map((item) => item.id));
  const alertIds = new Set(snapshot.alerts.map((item) => item.id));
  const healthIds = new Set(snapshot.health.map((item) => item.id));

  return (
    <div className="cc-stack" data-testid="control-center-full">
      <p className="cc-note">
        Full Control Center {snapshot.control_center_full_version} · project-scoped, bounded to {" "}
        {snapshot.history_max_points} history points · generated {formatDateTime(snapshot.generated_at)}.
        PostgreSQL is canonical; Redis is hot-only and canonical={String(snapshot.hot_store_canonical)}.
      </p>

      <article className="cc-card">
        <div className="cc-card-heading">
          <div>
            <h3>{snapshot.project.name}</h3>
            <p className="cc-muted">{snapshot.project.relative_path}</p>
          </div>
          <span className={statusClass(snapshot.project.state as FullStatus)}>{snapshot.project.state}</span>
        </div>
        <dl className="project-details">
          <div><dt>Branch</dt><dd>{snapshot.project.git_branch ?? "UNAVAILABLE"}</dd></div>
          <div><dt>HEAD</dt><dd>{snapshot.project.short_head ?? "UNAVAILABLE"}</dd></div>
          <div><dt>Full V0.1 claim</dt><dd>{snapshot.full_v01_complete_claimed ? "FORBIDDEN" : "not claimed"}</dd></div>
        </dl>
      </article>

      <section aria-label="Full Control Center capabilities">
        <div className="cc-card-heading"><h3>Project intelligence</h3><span className="cc-muted">{capabilityIds.size}/{FULL_PROJECT_CAPABILITIES.length}</span></div>
        <div className="cc-columns">{snapshot.capabilities.map((item) => <CapabilityCard key={item.id} capability={item} />)}</div>
      </section>

      <section className="cc-card" aria-label="Required charts">
        <div className="cc-card-heading"><h3>Required charts</h3><span className="cc-muted">{chartIds.size}/{FULL_CHARTS.length}</span></div>
        <ul className="cc-warning-list">
          {snapshot.charts.map((chart) => <li key={chart.id}><span>{chart.id}</span> <span className={statusClass(chart.status)}>{chart.status}</span> <span className="cc-muted">{chart.points.length}/{chart.max_points} points{chart.truncated ? " · truncated" : ""}</span></li>)}
        </ul>
      </section>

      <section className="cc-card" aria-label="Deterministic alerts">
        <div className="cc-card-heading"><h3>Deterministic alerts</h3><span className="cc-muted">{alertIds.size}/{FULL_ALERTS.length}</span></div>
        <ul className="cc-warning-list">
          {snapshot.alerts.map((alert) => <li key={alert.id}><span>{alert.id}</span> <span className={statusClass(alert.status)}>{alert.status}</span> <span className="cc-muted">{alert.summary} · {alert.provenance}</span></li>)}
        </ul>
      </section>

      <section className="cc-card" aria-label="Platform health capabilities">
        <div className="cc-card-heading"><h3>Platform health</h3><span className="cc-muted">{healthIds.size}/{FULL_HEALTH.length}</span></div>
        <ul className="cc-warning-list">
          {snapshot.health.map((surface) => <li key={surface.id}><span>{surface.id}</span> <span className={statusClass(surface.status)}>{surface.status}</span> <span className="cc-muted">{surface.summary} · {surface.provenance}</span></li>)}
        </ul>
      </section>
    </div>
  );
}
