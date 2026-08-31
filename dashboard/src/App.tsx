import { useCallback, useEffect, useState } from "react";

type Check = {
  status: string;
  details: Record<string, boolean | string>;
};

type Health = {
  status: string;
  version: string;
  environment: string;
  timestamp: string;
  data_root: string;
  checks: Record<string, Check>;
};

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const checkLabels: Record<string, string> = {
  postgres: "PostgreSQL + pgvector",
  redis: "Redis hot cache",
  storage: "Canonical data root",
};

function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadHealth = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(API_BASE_URL + "/api/v1/health", {
        cache: "no-store",
      });
      const payload = (await response.json()) as Health;
      setHealth(payload);
      setError(response.ok ? null : "A fundação está degradada.");
    } catch {
      setHealth(null);
      setError("Não foi possível conectar à API HIVE.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadHealth();
    const timer = window.setInterval(() => void loadHealth(), 30_000);
    return () => window.clearInterval(timer);
  }, [loadHealth]);

  const isHealthy = health?.status === "ok";

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">HIVE CONTROL CENTER</p>
          <h1>Foundation health</h1>
          <p className="lede">
            Operational visibility for the local-first HIVE bootstrap.
          </p>
        </div>
        <div className={"status-pill " + (isHealthy ? "healthy" : "degraded")}>
          <span className="status-dot" />
          {loading ? "Checking" : isHealthy ? "Healthy" : "Degraded"}
        </div>
      </header>

      <section className="hero-card" aria-live="polite">
        <div>
          <p className="eyebrow">BOOTSTRAP VERTICAL SLICE</p>
          <h2>{isHealthy ? "HIVE is ready locally." : "HIVE needs attention."}</h2>
          <p>
            {error ??
              "All reported service checks are responding from the real API health endpoint."}
          </p>
        </div>
        <button className="refresh-button" onClick={() => void loadHealth()}>
          Refresh health
        </button>
      </section>

      <section className="check-grid" aria-label="Service health">
        {Object.entries(checkLabels).map(([key, label]) => {
          const check = health?.checks[key];
          const ok = check?.status === "ok";
          return (
            <article className="check-card" key={key}>
              <div className="card-heading">
                <span className={"service-icon " + (ok ? "ok" : "not-ok")}>
                  {ok ? "✓" : "!"}
                </span>
                <span>{label}</span>
              </div>
              <strong>{loading ? "Checking..." : check?.status ?? "Unavailable"}</strong>
              <p>
                {key === "postgres"
                  ? check?.details.pgvector
                    ? "Vector extension available"
                    : "Vector extension unavailable"
                  : key === "redis"
                    ? check?.details.canonical === false
                      ? "Non-canonical hot cache"
                      : "Connectivity unavailable"
                    : health?.data_root ?? "Path unavailable"}
              </p>
            </article>
          );
        })}
      </section>

      <footer className="footer">
        <span>Version {health?.version ?? "0.0.1-bootstrap"}</span>
        <span>{health ? "Last API update " + formatTimestamp(health.timestamp) : "No API data"}</span>
        <span>{health?.environment ?? "local"}</span>
      </footer>
    </main>
  );
}

function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat("en", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

export default App;
