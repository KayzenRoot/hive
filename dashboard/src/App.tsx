import {
  useCallback,
  useEffect,
  useState,
  type ChangeEvent,
  type FormEvent,
} from "react";

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

type Task = {
  task_id: string;
  project_id: string;
  title: string | null;
  source_type: string;
  intake_status: string;
  original_blob_sha256: string;
  original_filename: string | null;
  media_type: string;
  logical_size: number;
  compressed_size: number;
  extracted_text_available: boolean;
  extraction_method: string;
  extraction_version: string;
  extraction_error: string | null;
  page_count: number | null;
  created_at: string;
  updated_at: string;
};

type StorageStats = {
  task_count: number;
  referenced_logical_bytes: number;
  unique_logical_bytes: number;
  physical_cas_bytes: number;
  unique_blob_count: number;
  deduplication_delta_bytes: number;
  compression_delta_bytes: number;
  compression_ratio: number | null;
  compression_savings_bytes: number | null;
  compression_delta_label: string;
};

type RetrievalRun = {
  run_id: string;
  project_id: string;
  status: string;
  completed_at: string | null;
  repository_source_count: number;
  task_source_count: number;
  chunk_count: number;
  reference_count: number;
  repository_reference_count: number;
  task_reference_count: number;
  new_chunk_count: number;
  reused_chunk_count: number;
  new_reference_count: number;
  reused_reference_count: number;
  removed_reference_count: number;
  error: string | null;
};

type RetrievalCorpus = {
  project_id: string;
  state: string;
  last_successful_sync: string | null;
  latest_run: RetrievalRun | null;
  chunk_count: number;
  reference_count: number;
  repository_reference_count: number;
  task_reference_count: number;
};

type LexicalResult = {
  reference_id: string;
  source_kind: string;
  lexical_score: number;
  snippet: string;
  path: string | null;
  title: string | null;
  qualified_symbol: string | null;
  source_content_sha256: string;
  start_line: number;
  end_line: number;
  start_char: number;
  end_char: number;
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
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [storageStats, setStorageStats] = useState<StorageStats | null>(null);
  const [intakeLoading, setIntakeLoading] = useState(false);
  const [intakeError, setIntakeError] = useState<string | null>(null);
  const [intakeMessage, setIntakeMessage] = useState<string | null>(null);
  const [intakeTitle, setIntakeTitle] = useState("");
  const [intakeFile, setIntakeFile] = useState<File | null>(null);
  const [textInput, setTextInput] = useState("");
  const [textFormat, setTextFormat] = useState<"text" | "markdown">("text");
  const [previewTaskId, setPreviewTaskId] = useState<string | null>(null);
  const [previewText, setPreviewText] = useState<string | null>(null);
  const [retrievalCorpus, setRetrievalCorpus] = useState<RetrievalCorpus | null>(null);
  const [retrievalResults, setRetrievalResults] = useState<LexicalResult[]>([]);
  const [retrievalQuery, setRetrievalQuery] = useState("");
  const [retrievalTopK, setRetrievalTopK] = useState(5);
  const [retrievalSourceKind, setRetrievalSourceKind] = useState("");
  const [retrievalLoading, setRetrievalLoading] = useState(false);
  const [retrievalMessage, setRetrievalMessage] = useState<string | null>(null);
  const [retrievalError, setRetrievalError] = useState<string | null>(null);

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

  const loadTaskSurface = useCallback(async (projectId: string) => {
    setIntakeLoading(true);
    setIntakeError(null);
    try {
      const [tasksResponse, storageResponse, corpusResponse] = await Promise.all([
        fetch(API_BASE_URL + "/api/v1/projects/" + projectId + "/tasks", { cache: "no-store" }),
        fetch(API_BASE_URL + "/api/v1/storage", { cache: "no-store" }),
        fetch(API_BASE_URL + "/api/v1/projects/" + projectId + "/retrieval/corpus", {
          cache: "no-store",
        }),
      ]);
      const tasksPayload = (await tasksResponse.json()) as unknown;
      const storagePayload = (await storageResponse.json()) as unknown;
      const corpusPayload = (await corpusResponse.json()) as unknown;
      if (!tasksResponse.ok) {
        throw new Error(readApiError(tasksPayload, "Não foi possível carregar as tarefas."));
      }
      if (!storageResponse.ok) {
        throw new Error(readApiError(storagePayload, "Não foi possível carregar o storage."));
      }
      if (!corpusResponse.ok) {
        throw new Error(readApiError(corpusPayload, "Não foi possível carregar o corpus."));
      }
      setTasks(tasksPayload as Task[]);
      setStorageStats(storagePayload as StorageStats);
      setRetrievalCorpus(corpusPayload as RetrievalCorpus);
    } catch (caught) {
      setTasks([]);
      setStorageStats(null);
      setIntakeError(caught instanceof Error ? caught.message : "Falha ao carregar o intake.");
    } finally {
      setIntakeLoading(false);
    }
  }, []);

  const selectIntakeProject = (event: ChangeEvent<HTMLSelectElement>) => {
    const projectId = event.target.value;
    setSelectedProjectId(projectId);
    setPreviewTaskId(null);
    setPreviewText(null);
    if (projectId) void loadTaskSurface(projectId);
    else {
      setTasks([]);
      setStorageStats(null);
      setRetrievalCorpus(null);
      setRetrievalResults([]);
    }
  };

  const syncRetrieval = async () => {
    if (!selectedProjectId) return;
    setRetrievalLoading(true);
    setRetrievalError(null);
    setRetrievalMessage(null);
    try {
      const response = await fetch(
        API_BASE_URL + "/api/v1/projects/" + selectedProjectId + "/retrieval/corpus/sync",
        { method: "POST" },
      );
      const payload = (await response.json()) as unknown;
      if (!response.ok) throw new Error(readApiError(payload, "Falha ao sincronizar o corpus."));
      setRetrievalMessage("Corpus sincronizado com dados derivados determinísticos.");
      await loadTaskSurface(selectedProjectId);
    } catch (caught) {
      setRetrievalError(caught instanceof Error ? caught.message : "Falha ao sincronizar o corpus.");
    } finally {
      setRetrievalLoading(false);
    }
  };

  const queryLexical = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedProjectId || !retrievalQuery.trim()) {
      setRetrievalError("Escolha um projeto e informe uma consulta lexical.");
      return;
    }
    setRetrievalLoading(true);
    setRetrievalError(null);
    setRetrievalMessage(null);
    try {
      const response = await fetch(
        API_BASE_URL + "/api/v1/projects/" + selectedProjectId + "/retrieval/lexical",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query: retrievalQuery,
            top_k: retrievalTopK,
            ...(retrievalSourceKind ? { source_kind: retrievalSourceKind } : {}),
          }),
        },
      );
      const payload = (await response.json()) as unknown;
      if (!response.ok) throw new Error(readApiError(payload, "Falha na consulta lexical."));
      setRetrievalResults((payload as { results: LexicalResult[] }).results);
    } catch (caught) {
      setRetrievalResults([]);
      setRetrievalError(caught instanceof Error ? caught.message : "Falha na consulta lexical.");
    } finally {
      setRetrievalLoading(false);
    }
  };

  const submitUpload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedProjectId || !intakeFile) {
      setIntakeError("Escolha um projeto e um arquivo PDF, Markdown ou TXT.");
      return;
    }
    setIntakeLoading(true);
    setIntakeError(null);
    setIntakeMessage(null);
    const formData = new FormData();
    formData.append("file", intakeFile);
    if (intakeTitle.trim()) formData.append("title", intakeTitle.trim());
    try {
      const response = await fetch(
        API_BASE_URL + "/api/v1/projects/" + selectedProjectId + "/tasks/upload",
        { method: "POST", body: formData },
      );
      const payload = (await response.json()) as unknown;
      if (!response.ok) throw new Error(readApiError(payload, "Falha ao aceitar o arquivo."));
      setIntakeFile(null);
      setIntakeTitle("");
      setIntakeMessage("Arquivo aceito e armazenado no CAS.");
      await loadTaskSurface(selectedProjectId);
    } catch (caught) {
      setIntakeError(caught instanceof Error ? caught.message : "Falha ao enviar o arquivo.");
      setIntakeLoading(false);
    }
  };

  const submitText = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedProjectId || !textInput.trim()) {
      setIntakeError("Escolha um projeto e informe o texto estruturado.");
      return;
    }
    setIntakeLoading(true);
    setIntakeError(null);
    setIntakeMessage(null);
    try {
      const response = await fetch(
        API_BASE_URL + "/api/v1/projects/" + selectedProjectId + "/tasks/text",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            title: intakeTitle.trim() || null,
            text: textInput,
            format: textFormat,
          }),
        },
      );
      const payload = (await response.json()) as unknown;
      if (!response.ok) throw new Error(readApiError(payload, "Falha ao aceitar o texto."));
      setTextInput("");
      setIntakeTitle("");
      setIntakeMessage("Texto aceito e armazenado no CAS.");
      await loadTaskSurface(selectedProjectId);
    } catch (caught) {
      setIntakeError(caught instanceof Error ? caught.message : "Falha ao enviar o texto.");
      setIntakeLoading(false);
    }
  };

  const previewTask = async (taskId: string) => {
    if (!selectedProjectId) return;
    setPreviewTaskId(taskId);
    setPreviewText(null);
    try {
      const response = await fetch(
        API_BASE_URL + "/api/v1/projects/" + selectedProjectId + "/tasks/" + taskId + "/text",
        { cache: "no-store" },
      );
      const payload = (await response.json()) as unknown;
      if (!response.ok) throw new Error(readApiError(payload, "Texto derivado indisponível."));
      setPreviewText((payload as { text: string }).text);
    } catch (caught) {
      setPreviewText(caught instanceof Error ? caught.message : "Texto derivado indisponível.");
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

      <section className="intake-section" aria-labelledby="intake-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">DURABLE TASK / PROMPT INTAKE</p>
            <h2 id="intake-title">Task Intake + CAS</h2>
          </div>
          <span className="fleet-count">Original bytes + Zstd</span>
        </div>
        <label className="project-picker">
          Registered project
          <select aria-label="Registered project" value={selectedProjectId} onChange={selectIntakeProject}>
            <option value="">Choose a project…</option>
            {projects.map((project) => (
              <option key={project.project_id} value={project.project_id}>
                {project.name} · {project.relative_path}
              </option>
            ))}
          </select>
        </label>
        <div className="intake-grid">
          <form className="intake-card" onSubmit={(event) => void submitUpload(event)}>
            <h3>Upload artifact</h3>
            <p>PDF with text layer, Markdown or UTF-8 TXT. OCR is not used.</p>
            <label>
              Optional title
              <input value={intakeTitle} onChange={(event) => setIntakeTitle(event.target.value)} />
            </label>
            <label>
              File
              <input
                required
                type="file"
                accept=".pdf,.md,.markdown,.txt,application/pdf,text/markdown,text/plain"
                onChange={(event) => setIntakeFile(event.target.files?.[0] ?? null)}
              />
            </label>
            <button className="refresh-button" disabled={intakeLoading} type="submit">
              {intakeLoading ? "Accepting..." : "Accept file"}
            </button>
          </form>
          <form className="intake-card" onSubmit={(event) => void submitText(event)}>
            <h3>Structured text</h3>
            <p>Text is normalized only in the derived representation.</p>
            <label>
              Format
              <select value={textFormat} onChange={(event) => setTextFormat(event.target.value as "text" | "markdown")}>
                <option value="text">TXT</option>
                <option value="markdown">Markdown</option>
              </select>
            </label>
            <label>
              Text
              <textarea required value={textInput} onChange={(event) => setTextInput(event.target.value)} />
            </label>
            <button className="refresh-button" disabled={intakeLoading} type="submit">
              {intakeLoading ? "Accepting..." : "Accept text"}
            </button>
          </form>
        </div>
        {intakeMessage ? <p className="success-message" role="status">{intakeMessage}</p> : null}
        {intakeError ? <p className="error-message" role="alert">{intakeError}</p> : null}
        {selectedProjectId ? (
          <>
            <div className="storage-summary" aria-label="Storage summary">
              {storageStats ? (
                <>
                  <span>{storageStats.task_count} tasks</span>
                  <span>{formatBytes(storageStats.unique_logical_bytes)} unique logical</span>
                  <span>{formatBytes(storageStats.physical_cas_bytes)} physical CAS</span>
                  <span>{storageStats.unique_blob_count} blobs</span>
                  <span>{formatBytes(storageStats.deduplication_delta_bytes)} dedup delta</span>
                  <span>
                    Compression {storageStats.compression_ratio === null ? "—" : `${(storageStats.compression_ratio * 100).toFixed(1)}%`} ({storageStats.compression_delta_label})
                  </span>
                </>
              ) : intakeLoading ? <span>Loading real storage metrics...</span> : null}
            </div>
            <div className="task-list" aria-live="polite">
              {tasks.length === 0 && !intakeLoading ? (
                <p className="fleet-message">No tasks accepted for this project yet.</p>
              ) : (
                tasks.map((task) => (
                  <article className="task-card" key={task.task_id}>
                    <div className="project-card-heading">
                      <div>
                        <h3>{task.title ?? task.original_filename ?? "Untitled task"}</h3>
                        <p>{task.source_type} · {task.original_blob_sha256.slice(0, 12)}</p>
                      </div>
                      <span className={"state-badge state-" + task.intake_status.toLowerCase()}>{task.intake_status}</span>
                    </div>
                    <dl className="project-details task-details">
                      <div><dt>Logical</dt><dd>{formatBytes(task.logical_size)}</dd></div>
                      <div><dt>Compressed</dt><dd>{formatBytes(task.compressed_size)}</dd></div>
                      <div><dt>File</dt><dd>{task.original_filename ?? "structured input"}</dd></div>
                      <div><dt>Created</dt><dd>{formatTimestamp(task.created_at)}</dd></div>
                    </dl>
                    {task.extraction_error ? <p className="error-message">{task.extraction_error}</p> : null}
                    <div className="task-actions">
                      <a className="secondary-button" href={API_BASE_URL + "/api/v1/projects/" + selectedProjectId + "/tasks/" + task.task_id + "/artifact"}>Download original</a>
                      {task.extracted_text_available ? <button className="secondary-button" onClick={() => void previewTask(task.task_id)}>Preview extracted text</button> : null}
                    </div>
                    {previewTaskId === task.task_id && previewText !== null ? <pre className="text-preview">{previewText}</pre> : null}
                  </article>
                ))
              )}
            </div>
          </>
        ) : <p className="fleet-message">Select a registered project to inspect durable intake state.</p>}
      </section>

      <section className="retrieval-section" aria-labelledby="retrieval-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">PROJECT-SCOPED DERIVED CONTEXT</p>
            <h2 id="retrieval-title">Retrieval Corpus</h2>
          </div>
          {selectedProjectId ? (
            <button
              className="refresh-button"
              disabled={retrievalLoading}
              onClick={() => void syncRetrieval()}
            >
              {retrievalLoading ? "Syncing..." : "Sync corpus"}
            </button>
          ) : null}
        </div>
        {!selectedProjectId ? (
          <p className="fleet-message">Select a registered project to inspect retrieval state.</p>
        ) : retrievalCorpus ? (
          <>
            <div className="retrieval-summary" aria-label="Retrieval corpus summary">
              <span className={"state-badge state-" + retrievalCorpus.state.toLowerCase()}>
                {retrievalCorpus.state}
              </span>
              <span>{retrievalCorpus.chunk_count} chunks</span>
              <span>{retrievalCorpus.reference_count} references</span>
              <span>{retrievalCorpus.repository_reference_count} repository</span>
              <span>{retrievalCorpus.task_reference_count} task</span>
              <span>
                Last sync {retrievalCorpus.last_successful_sync ? formatTimestamp(retrievalCorpus.last_successful_sync) : "—"}
              </span>
            </div>
            {retrievalCorpus.latest_run ? (
              <dl className="retrieval-run-details">
                <div><dt>Latest run</dt><dd>{retrievalCorpus.latest_run.status}</dd></div>
                <div><dt>New / reused chunks</dt><dd>{retrievalCorpus.latest_run.new_chunk_count} / {retrievalCorpus.latest_run.reused_chunk_count}</dd></div>
                <div><dt>New / reused refs</dt><dd>{retrievalCorpus.latest_run.new_reference_count} / {retrievalCorpus.latest_run.reused_reference_count}</dd></div>
                <div><dt>Removed refs</dt><dd>{retrievalCorpus.latest_run.removed_reference_count}</dd></div>
              </dl>
            ) : null}
            {retrievalCorpus.latest_run?.error ? (
              <p className="error-message" role="alert">{retrievalCorpus.latest_run.error}</p>
            ) : null}
          </>
        ) : retrievalLoading ? (
          <p className="fleet-message" role="status">Loading retrieval corpus state...</p>
        ) : (
          <p className="fleet-message">Retrieval corpus state is unavailable.</p>
        )}
      </section>

      <section className="retrieval-section" aria-labelledby="lab-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">DETERMINISTIC POSTGRESQL SEARCH</p>
            <h2 id="lab-title">Lexical Retrieval Lab</h2>
          </div>
          <span className="fleet-count">No semantic ranking</span>
        </div>
        <form className="lexical-form" onSubmit={(event) => void queryLexical(event)}>
          <label>
            Query
            <input
              required
              maxLength={512}
              value={retrievalQuery}
              onChange={(event) => setRetrievalQuery(event.target.value)}
              placeholder="OrderService.get_project_order"
            />
          </label>
          <label>
            Top-k
            <select value={retrievalTopK} onChange={(event) => setRetrievalTopK(Number(event.target.value))}>
              {[1, 5, 10, 20].map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
          <label>
            Source type
            <select value={retrievalSourceKind} onChange={(event) => setRetrievalSourceKind(event.target.value)}>
              <option value="">All sources</option>
              <option value="REPOSITORY_FILE">Repository file</option>
              <option value="REPOSITORY_SYMBOL">Repository symbol</option>
              <option value="TASK">Task text</option>
            </select>
          </label>
          <button className="refresh-button" disabled={!selectedProjectId || retrievalLoading} type="submit">
            {retrievalLoading ? "Searching..." : "Search lexical"}
          </button>
        </form>
        {retrievalMessage ? <p className="success-message" role="status">{retrievalMessage}</p> : null}
        {retrievalError ? <p className="error-message" role="alert">{retrievalError}</p> : null}
        <div className="retrieval-results" aria-live="polite">
          {!selectedProjectId ? (
            <p className="fleet-message">Select a project to query its isolated corpus.</p>
          ) : retrievalResults.length === 0 ? (
            <p className="fleet-message">No lexical results yet.</p>
          ) : (
            retrievalResults.map((result) => (
              <article className="retrieval-result" key={result.reference_id}>
                <div className="project-card-heading">
                  <div>
                    <h3>{result.qualified_symbol ?? result.path ?? result.title ?? "Derived source"}</h3>
                    <p>{result.source_kind} · score {result.lexical_score.toFixed(3)}</p>
                  </div>
                  <span className="state-badge">{result.path ?? result.title ?? "task text"}</span>
                </div>
                <pre className="retrieval-snippet">{result.snippet}</pre>
                <p className="retrieval-provenance">
                  {result.qualified_symbol ? result.qualified_symbol + " · " : ""}
                  Lines {result.start_line}-{result.end_line} · chars {result.start_char}-{result.end_char} · source {result.source_content_sha256.slice(0, 12)}
                </p>
              </article>
            ))
          )}
        </div>
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

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export default App;
