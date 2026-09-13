import { useEffect, useState, type ReactNode } from "react";

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
  points: {
    observed_at: string | null;
    value: number | null;
    provenance: Provenance;
    source: string;
    series: string | null;
  }[];
  max_points: number;
  truncated: boolean;
};

type Alert = {
  id: string;
  status: FullStatus;
  severity: string;
  summary: string;
  provenance: Provenance;
  source: string;
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
  refreshSignal?: number;
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

function primitiveDetailValue(value: unknown): string {
  if (typeof value === "string") return value.length > 160 ? value.slice(0, 157) + "..." : value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (value === null) return "UNAVAILABLE";
  return "UNKNOWN";
}

function detailValue(value: unknown, depth = 0): ReactNode {
  if (Array.isArray(value)) {
    if (value.length === 0) return <span>UNAVAILABLE (no records)</span>;
    return (
      <ul className="cc-detail-list">
        {value.slice(0, 12).map((item, index) => (
          <li key={String(index)}>{detailValue(item, depth + 1)}</li>
        ))}
      </ul>
    );
  }
  if (isRecord(value) && depth < 4) {
    const entries = Object.entries(value).slice(0, 12);
    if (entries.length === 0) return <span>UNAVAILABLE</span>;
    return (
      <dl className="cc-detail-list">
        {entries.map(([key, nested]) => (
          <div key={key}>
            <dt>{key}</dt>
            <dd>{detailValue(nested, depth + 1)}</dd>
          </div>
        ))}
      </dl>
    );
  }
  return <span>{primitiveDetailValue(value)}</span>;
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
              <dd>{detailValue(value)}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </article>
  );
}

const CHART_WIDTH = 360;
const CHART_HEIGHT = 132;
const CHART_PADDING = 16;
const CHART_COLORS = ["#55d6be", "#f5b971", "#8ab4f8", "#f28b82"];

function ChartGraphic({ chart }: { chart: Chart }) {
  const series = new Map<string, number[]>();
  for (const point of chart.points) {
    if (typeof point.value !== "number" || !Number.isFinite(point.value)) continue;
    const name = point.series ?? "value";
    const values = series.get(name) ?? [];
    values.push(point.value);
    series.set(name, values);
  }
  const values = Array.from(series.values()).flat();
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const range = maximum - minimum || 1;
  const innerWidth = CHART_WIDTH - CHART_PADDING * 2;
  const innerHeight = CHART_HEIGHT - CHART_PADDING * 2;

  return (
    <svg
      className="cc-chart-graphic"
      data-chart-id={chart.id}
      role="img"
      aria-label={`${chart.id} bounded real-data chart`}
      viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
    >
      <title>{chart.id} bounded real-data chart</title>
      <line
        x1={CHART_PADDING}
        y1={CHART_HEIGHT - CHART_PADDING}
        x2={CHART_WIDTH - CHART_PADDING}
        y2={CHART_HEIGHT - CHART_PADDING}
        stroke="currentColor"
        opacity="0.35"
      />
      {Array.from(series.entries()).map(([name, points], seriesIndex) => {
        const coordinates = points
          .map((value, index) => {
            const x =
              CHART_PADDING +
              (points.length === 1 ? innerWidth / 2 : (index / (points.length - 1)) * innerWidth);
            const y = CHART_HEIGHT - CHART_PADDING - ((value - minimum) / range) * innerHeight;
            return `${x},${y}`;
          })
          .join(" ");
        const color = CHART_COLORS[seriesIndex % CHART_COLORS.length];
        return (
          <g key={name} data-series={name}>
            <polyline points={coordinates} fill="none" stroke={color} strokeWidth="2" />
            {points.map((value, index) => {
              const x =
                CHART_PADDING +
                (points.length === 1 ? innerWidth / 2 : (index / (points.length - 1)) * innerWidth);
              const y = CHART_HEIGHT - CHART_PADDING - ((value - minimum) / range) * innerHeight;
              return <circle key={`${name}-${index}`} cx={x} cy={y} r="3" fill={color} />;
            })}
          </g>
        );
      })}
    </svg>
  );
}

function ChartCard({ chart }: { chart: Chart }) {
  const numericPoints = chart.points.filter(
    (point) => typeof point.value === "number" && Number.isFinite(point.value),
  );
  const latest = numericPoints[numericPoints.length - 1];
  return (
    <article className="cc-card cc-chart-card" aria-label={`Chart ${chart.id}`}>
      <div className="cc-card-heading">
        <h4>{chart.id}</h4>
        <span className={statusClass(chart.status)}>{chart.status}</span>
      </div>
      {numericPoints.length > 0 ? (
        <ChartGraphic chart={chart} />
      ) : (
        <p className="cc-muted" data-testid={`chart-state-${chart.id}`}>
          {chart.status === "UNKNOWN" ? "UNKNOWN" : "UNAVAILABLE"} — no bounded canonical data
          is available for this chart.
        </p>
      )}
      <p className="cc-muted">
        {numericPoints.length}/{chart.max_points} real points{chart.truncated ? " · truncated" : ""}
        {latest ? ` · ${latest.provenance} · ${latest.source}` : ""}
      </p>
    </article>
  );
}

export default function ControlCenterFull({
  selectedProjectId,
  refreshSignal = 0,
}: ControlCenterFullProps) {
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
  }, [selectedProjectId, refreshSignal]);

  if (!selectedProjectId) {
    return <p className="fleet-message">Select a project to open the full Control Center.</p>;
  }
  const error = failure?.projectId === selectedProjectId ? failure.message : null;
  const currentSnapshot = snapshot?.project_id === selectedProjectId ? snapshot : null;
  const loading = currentSnapshot === null && error === null;
  if (loading) {
    return <p className="fleet-message" role="status">Loading full Control Center...</p>;
  }
  if (error !== null) {
    return <p className="fleet-message error-message" role="alert">{error}</p>;
  }
  if (currentSnapshot === null) {
    return <p className="fleet-message">The full Control Center snapshot is unavailable.</p>;
  }

  const capabilityIds = new Set(currentSnapshot.capabilities.map((item) => item.id));
  const chartIds = new Set(currentSnapshot.charts.map((item) => item.id));
  const alertIds = new Set(currentSnapshot.alerts.map((item) => item.id));
  const healthIds = new Set(currentSnapshot.health.map((item) => item.id));

  return (
    <div className="cc-stack" data-testid="control-center-full">
      <p className="cc-note">
        Full Control Center {currentSnapshot.control_center_full_version} · live refresh through the
        project SSE/replay seam · project-scoped, bounded to {" "}
        {currentSnapshot.history_max_points} history points · generated {formatDateTime(currentSnapshot.generated_at)}.
        PostgreSQL is canonical; Redis is hot-only and canonical={String(currentSnapshot.hot_store_canonical)}.
      </p>

      <article className="cc-card">
        <div className="cc-card-heading">
          <div>
            <h3>{currentSnapshot.project.name}</h3>
            <p className="cc-muted">{currentSnapshot.project.relative_path}</p>
          </div>
          <span className={statusClass(currentSnapshot.project.state as FullStatus)}>{currentSnapshot.project.state}</span>
        </div>
        <dl className="project-details">
          <div><dt>Branch</dt><dd>{currentSnapshot.project.git_branch ?? "UNAVAILABLE"}</dd></div>
          <div><dt>HEAD</dt><dd>{currentSnapshot.project.short_head ?? "UNAVAILABLE"}</dd></div>
          <div><dt>Full V0.1 claim</dt><dd>{currentSnapshot.full_v01_complete_claimed ? "FORBIDDEN" : "not claimed"}</dd></div>
        </dl>
      </article>

      <section aria-label="Full Control Center capabilities">
        <div className="cc-card-heading"><h3>Project intelligence</h3><span className="cc-muted">{capabilityIds.size}/{FULL_PROJECT_CAPABILITIES.length}</span></div>
        <div className="cc-columns">{currentSnapshot.capabilities.map((item) => <CapabilityCard key={item.id} capability={item} />)}</div>
      </section>

      <section className="cc-card" aria-label="Required charts">
        <div className="cc-card-heading"><h3>Required charts</h3><span className="cc-muted">{chartIds.size}/{FULL_CHARTS.length}</span></div>
        <div className="cc-columns">{currentSnapshot.charts.map((chart) => <ChartCard key={chart.id} chart={chart} />)}</div>
      </section>

      <section className="cc-card" aria-label="Deterministic alerts">
        <div className="cc-card-heading"><h3>Deterministic alerts</h3><span className="cc-muted">{alertIds.size}/{FULL_ALERTS.length}</span></div>
        <ul className="cc-warning-list">
          {currentSnapshot.alerts.map((alert) => <li key={alert.id}><span>{alert.id}</span> <span className={statusClass(alert.status)}>{alert.status}</span> <span className="cc-muted">{alert.summary} · {alert.provenance} · {alert.source}</span></li>)}
        </ul>
      </section>

      <section className="cc-card" aria-label="Platform health capabilities">
        <div className="cc-card-heading"><h3>Platform health</h3><span className="cc-muted">{healthIds.size}/{FULL_HEALTH.length}</span></div>
        <ul className="cc-warning-list">
          {currentSnapshot.health.map((surface) => (
            <li key={surface.id}>
              <span>{surface.id}</span> <span className={statusClass(surface.status)}>{surface.status}</span>{" "}
              <span className="cc-muted">{surface.summary} · {surface.provenance}</span>
              <div className="cc-health-details">{detailValue(surface.details)}</div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
