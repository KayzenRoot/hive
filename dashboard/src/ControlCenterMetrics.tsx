import { useCallback, useEffect, useMemo, useState } from "react";

import { API_BASE_URL } from "./config";

type MetricProvenance = "EXACT" | "ESTIMATED" | "UNAVAILABLE" | "UNKNOWN";

type MetricValue = {
  value: number | null;
  provenance: MetricProvenance;
  source: string;
};

type MetricsPayload = {
  metrics_evidence_version: string;
  generated_at: string;
  scope: "PROJECT" | "GLOBAL";
  project_id: string | null;
  project_count: number;
  canonical_store: string;
  hot_store: string;
  hot_store_canonical: boolean;
  scanned_events: number;
  window_truncated: boolean;
  token: Record<string, MetricValue>;
  context: Record<string, MetricValue>;
  cache: Record<string, MetricValue>;
  storage: Record<string, MetricValue>;
  history: Array<Record<string, unknown>>;
  history_max_points: number;
  cost_provenance: MetricProvenance;
};

type ProjectOption = {
  project_id: string;
  name: string;
};

const refreshIntervalMs = 15_000;

function formatNumber(metric: MetricValue | undefined): string {
  if (!metric || metric.value === null) return "—";
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 }).format(metric.value);
}

function formatPercent(metric: MetricValue | undefined): string {
  if (!metric || metric.value === null) return "—";
  return new Intl.NumberFormat("pt-BR", {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(metric.value);
}

function formatBytes(metric: MetricValue | undefined): string {
  if (!metric || metric.value === null) return "—";
  const bytes = metric.value;
  if (bytes < 1024) return `${formatNumber(metric)} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KiB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MiB`;
  return `${(bytes / 1024 ** 3).toFixed(1)} GiB`;
}

function MetricLine({
  label,
  metric,
  kind = "number",
}: {
  label: string;
  metric: MetricValue | undefined;
  kind?: "number" | "percent" | "bytes";
}) {
  const rendered =
    kind === "percent"
      ? formatPercent(metric)
      : kind === "bytes"
        ? formatBytes(metric)
        : formatNumber(metric);
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(0, 1fr) auto",
        gap: "0.75rem",
        alignItems: "baseline",
        padding: "0.38rem 0",
      }}
    >
      <span>{label}</span>
      <span style={{ textAlign: "right" }}>
        <strong>{rendered}</strong>{" "}
        <small data-provenance={metric?.provenance ?? "UNAVAILABLE"}>
          {metric?.provenance ?? "UNAVAILABLE"}
        </small>
      </span>
    </div>
  );
}

export default function ControlCenterMetrics() {
  const [projects, setProjects] = useState<ProjectOption[]>([]);
  const [projectId, setProjectId] = useState("");
  const [metrics, setMetrics] = useState<MetricsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const metricsUrl = useMemo(() => {
    if (projectId) {
      return `${API_BASE_URL}/api/v1/control-center/metrics?project_id=${encodeURIComponent(projectId)}`;
    }
    return `${API_BASE_URL}/api/v1/control-center/metrics/global`;
  }, [projectId]);

  const loadProjects = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/projects`, { cache: "no-store" });
      if (!response.ok) return;
      const payload = (await response.json()) as ProjectOption[];
      setProjects(payload);
    } catch {
      // Metrics continue to work in global mode even when this convenience list is unavailable.
    }
  }, []);

  const loadMetrics = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(metricsUrl, { cache: "no-store" });
      const payload = (await response.json()) as MetricsPayload | { detail?: string };
      if (!response.ok) {
        const detail = "detail" in payload && payload.detail ? payload.detail : "Falha ao carregar métricas.";
        throw new Error(detail);
      }
      setMetrics(payload as MetricsPayload);
      setError(null);
    } catch (caught) {
      setMetrics(null);
      setError(caught instanceof Error ? caught.message : "Falha ao carregar métricas.");
    } finally {
      setLoading(false);
    }
  }, [metricsUrl]);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

  useEffect(() => {
    void loadMetrics();
    const interval = window.setInterval(() => void loadMetrics(), refreshIntervalMs);
    return () => window.clearInterval(interval);
  }, [loadMetrics]);

  useEffect(() => {
    if (!projectId || typeof EventSource === "undefined") return undefined;
    const source = new EventSource(
      `${API_BASE_URL}/api/v1/control-center/projects/${encodeURIComponent(projectId)}/events/stream`,
    );
    source.onmessage = () => void loadMetrics();
    source.onerror = () => {
      // The bounded polling cadence remains the fallback; no metric is invented from transport state.
    };
    return () => source.close();
  }, [loadMetrics, projectId]);

  return (
    <section className="control-center-section" aria-labelledby="control-center-metrics-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">OBSERVABILITY</p>
          <h2 id="control-center-metrics-title">Control Center Metrics</h2>
          <p>
            Token, contexto, cache e storage com proveniência explícita. Valores ausentes nunca são
            convertidos em zero.
          </p>
        </div>
        <label>
          Escopo{" "}
          <select
            aria-label="Metrics scope"
            value={projectId}
            onChange={(event) => setProjectId(event.target.value)}
          >
            <option value="">Global</option>
            {projects.map((project) => (
              <option key={project.project_id} value={project.project_id}>
                {project.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {loading && !metrics ? <p>Carregando métricas reais…</p> : null}
      {error ? <p role="alert">{error}</p> : null}

      {metrics ? (
        <>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))",
              gap: "1rem",
              marginTop: "1rem",
            }}
          >
            <article className="service-card">
              <h3>Tokens</h3>
              <MetricLine label="Entrada" metric={metrics.token.input_tokens} />
              <MetricLine label="Saída" metric={metrics.token.output_tokens} />
              <MetricLine label="Cacheados" metric={metrics.token.cached_tokens} />
              <MetricLine label="Frescos" metric={metrics.token.fresh_tokens} />
              <MetricLine label="Economia" metric={metrics.token.token_savings} />
            </article>

            <article className="service-card">
              <h3>Contexto</h3>
              <MetricLine label="Antes" metric={metrics.context.before_tokens} />
              <MetricLine label="Depois" metric={metrics.context.after_tokens} />
              <MetricLine label="Redução" metric={metrics.context.reduction_tokens} />
              <MetricLine
                label="Taxa de redução"
                metric={metrics.context.reduction_ratio}
                kind="percent"
              />
            </article>

            <article className="service-card">
              <h3>Cache</h3>
              <MetricLine label="Hits" metric={metrics.cache.hits} />
              <MetricLine label="Misses" metric={metrics.cache.misses} />
              <MetricLine label="Decisões observadas" metric={metrics.cache.observed_decisions} />
              <MetricLine label="Hit rate" metric={metrics.cache.hit_rate} kind="percent" />
            </article>

            <article className="service-card">
              <h3>Storage</h3>
              <MetricLine
                label="Lógico"
                metric={metrics.storage.logical_task_bytes}
                kind="bytes"
              />
              <MetricLine
                label="Físico referenciado"
                metric={metrics.storage.physical_referenced_bytes}
                kind="bytes"
              />
              <MetricLine label="Economia" metric={metrics.storage.saved_bytes} kind="bytes" />
              <MetricLine
                label="Taxa de economia"
                metric={metrics.storage.savings_ratio}
                kind="percent"
              />
            </article>
          </div>

          <p style={{ marginTop: "0.9rem" }}>
            Escopo: <strong>{metrics.scope}</strong> · projetos: {metrics.project_count} · eventos
            observados: {metrics.scanned_events} · histórico limitado a {metrics.history_max_points}
            pontos · PostgreSQL canônico · Redis não canônico · custo: {metrics.cost_provenance}
            {metrics.window_truncated ? " · janela truncada" : ""}
          </p>
        </>
      ) : null}
    </section>
  );
}
