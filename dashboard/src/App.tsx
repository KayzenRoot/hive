import { useCallback, useEffect, useState, type FormEvent } from "react";

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

type Project = {
  project_id: string;
  name: string;
  relative_path: string;
  git_branch: string | null;
  git_head_sha: string | null;
  detached_head: boolean;
  repository_accessible: boolean;
  working_tree_clean: boolean | null;
  language_stack: string[];
  state: string;
  inspection_error: string | null;
  created_at: string;
  updated_at: string;
  last_inspected_at: string;
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const checkLabels: Record<string, string> = {
  postgres: "PostgreSQL + pgvector",
  redis: "Redis hot cache",
  storage: "Canonical data root",
};

function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [projectError, setProjectError] = useState<string | null>(null);
  const [projectName, setProjectName] = useState("");
  const [projectPath, setProjectPath] = useState("");
  const [registering, setRegistering] = useState(false);
  const [inspectingProjectId, setInspectingProjectId] = useState<string | null>(null);

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

  const loadProjects = useCallback(async () => {
    setProjectsLoading(true);
    setProjectError(null);
    try {
      const response = await fetch(API_BASE_URL + "/api/v1/projects", {
        cache: "no-store",
      });
      const payload = (await response.json()) as unknown;
      if (!response.ok) {
        throw new Error(readApiError(payload, "Não foi possível carregar os projetos."));
      }
      setProjects(payload as Project[]);
    } catch (caught) {
      setProjectError(caught instanceof Error ? caught.message : "Falha ao carregar projetos.");
    } finally {
      setProjectsLoading(false);
    }
  }, []);

  useEffect(() => {
    const initialLoad = window.setTimeout(() => {
      void loadHealth();
      void loadProjects();
    }, 0);
    const timer = window.setInterval(() => {
      void loadHealth();
      void loadProjects();
    }, 30_000);
    return () => {
      window.clearTimeout(initialLoad);
      window.clearInterval(timer);
    };
  }, [loadHealth, loadProjects]);

  const registerProject = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setRegistering(true);
    setProjectError(null);
    try {
      const response = await fetch(API_BASE_URL + "/api/v1/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: projectName, relative_path: projectPath }),
      });
      const payload = (await response.json()) as unknown;
      if (!response.ok) {
        throw new Error(readApiError(payload, "Não foi possível registrar o projeto."));
      }
      setProjectName("");
      setProjectPath("");
      await loadProjects();
    } catch (caught) {
      setProjectError(caught instanceof Error ? caught.message : "Falha ao registrar projeto.");
    } finally {
      setRegistering(false);
    }
  };

  const inspectProject = async (projectId: string) => {
    setInspectingProjectId(projectId);
    setProjectError(null);
    try {
      const response = await fetch(API_BASE_URL + "/api/v1/projects/" + projectId + "/inspect", {
        method: "POST",
      });
      const payload = (await response.json()) as unknown;
      if (!response.ok) {
        throw new Error(readApiError(payload, "Não foi possível inspecionar o projeto."));
      }
      const updated = payload as Project;
      setProjects((current) =>
        current.map((project) => (project.project_id === updated.project_id ? updated : project)),
      );
    } catch (caught) {
      setProjectError(caught instanceof Error ? caught.message : "Falha ao inspecionar projeto.");
    } finally {
      setInspectingProjectId(null);
    }
  };

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

      <section className="fleet-section" aria-labelledby="fleet-title" aria-busy={projectsLoading}>
        <div className="section-heading">
          <div>
            <p className="eyebrow">DURABLE REGISTRY</p>
            <h2 id="fleet-title">Project Fleet</h2>
          </div>
          <span className="fleet-count" aria-label={`${projects.length} registered projects`}>
            {projects.length} registered
          </span>
        </div>

        <form className="register-form" onSubmit={(event) => void registerProject(event)}>
          <label>
            Project name
            <input
              required
              maxLength={120}
              value={projectName}
              onChange={(event) => setProjectName(event.target.value)}
              placeholder="HIVE"
            />
          </label>
          <label>
            Relative path
            <input
              required
              maxLength={1024}
              value={projectPath}
              onChange={(event) => setProjectPath(event.target.value)}
              placeholder="my-project"
            />
          </label>
          <button className="refresh-button" disabled={registering} type="submit">
            {registering ? "Registering..." : "Register project"}
          </button>
        </form>

        {projectsLoading ? (
          <p className="fleet-message" role="status">
            Loading registered projects...
          </p>
        ) : projectError ? (
          <div className="fleet-message error-message" role="alert">
            <span>{projectError}</span>
            <button className="secondary-button" onClick={() => void loadProjects()}>
              Retry fleet
            </button>
          </div>
        ) : projects.length === 0 ? (
          <p className="fleet-message">No projects registered yet.</p>
        ) : (
          <div className="project-list">
            {projects.map((project) => (
              <article className="project-card" key={project.project_id}>
                <div className="project-card-heading">
                  <div>
                    <h3>{project.name}</h3>
                    <p>{project.relative_path}</p>
                  </div>
                  <span className={"state-badge state-" + project.state.toLowerCase()}>
                    {project.state}
                  </span>
                </div>
                <dl className="project-details">
                  <div>
                    <dt>Branch</dt>
                    <dd>{project.git_branch ?? (project.detached_head ? "Detached HEAD" : "—")}</dd>
                  </div>
                  <div>
                    <dt>HEAD</dt>
                    <dd title={project.git_head_sha ?? undefined}>
                      {project.git_head_sha?.slice(0, 7) ?? "—"}
                    </dd>
                  </div>
                  <div>
                    <dt>Languages</dt>
                    <dd>{project.language_stack.length ? project.language_stack.join(", ") : "—"}</dd>
                  </div>
                  <div>
                    <dt>Last inspection</dt>
                    <dd>{formatTimestamp(project.last_inspected_at)}</dd>
                  </div>
                </dl>
                <button
                  className="secondary-button"
                  disabled={inspectingProjectId === project.project_id}
                  onClick={() => void inspectProject(project.project_id)}
                >
                  {inspectingProjectId === project.project_id ? "Inspecting..." : "Re-inspect"}
                </button>
              </article>
            ))}
          </div>
        )}
      </section>

      <footer className="footer">
        <span>Version {health?.version ?? "0.0.1-bootstrap"}</span>
        <span>{health ? "Last API update " + formatTimestamp(health.timestamp) : "No API data"}</span>
        <span>{health?.environment ?? "local"}</span>
      </footer>
    </main>
  );
}

function readApiError(payload: unknown, fallback: string): string {
  if (typeof payload === "object" && payload !== null && "detail" in payload) {
    const detail = payload.detail;
    if (typeof detail === "string") return detail;
  }
  return fallback;
}

function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat("en", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

export default App;
