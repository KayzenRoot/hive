from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

import psycopg
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import ensure_schema_current
from .health import HealthResponse, collect_health
from .registry import (
    ProjectConflictError,
    ProjectCreateRequest,
    ProjectPathError,
    ProjectResponse,
    get_project,
    inspect_registered_project,
    list_projects,
    register_project,
)
from .repository_indexer import router as repository_index_router
from .retrieval import router as retrieval_router
from .semantic_retrieval import router as semantic_retrieval_router
from .tasks_api import router as task_router

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    ensure_schema_current(settings)
    yield


app = FastAPI(
    title="HIVE API",
    description="Local-first HIVE foundation, Project Registry and repository indexing.",
    version=settings.version,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(task_router)
app.include_router(repository_index_router)
app.include_router(retrieval_router)
app.include_router(semantic_retrieval_router)


@app.get("/", tags=["meta"])
def root() -> dict[str, str]:
    return {"service": "hive-api", "version": settings.version}


@app.get("/api/v1/health", response_model=HealthResponse, tags=["health"])
def health(response: Response) -> HealthResponse:
    result = collect_health(settings)
    if result.status != "ok":
        response.status_code = 503
    return result


@app.get("/api/v1/status", response_model=HealthResponse, tags=["health"])
def status(response: Response) -> HealthResponse:
    return health(response)


def _registry_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail=f"project registry database unavailable ({type(exc).__name__})",
    )


@app.post("/api/v1/projects", response_model=ProjectResponse, status_code=201, tags=["projects"])
def create_project(request: ProjectCreateRequest) -> ProjectResponse:
    try:
        return register_project(settings, request)
    except ProjectPathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProjectConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise _registry_unavailable(exc) from exc


@app.get("/api/v1/projects", response_model=list[ProjectResponse], tags=["projects"])
def get_projects() -> list[ProjectResponse]:
    try:
        return list_projects(settings)
    except psycopg.Error as exc:
        raise _registry_unavailable(exc) from exc


@app.get("/api/v1/projects/{project_id}", response_model=ProjectResponse, tags=["projects"])
def get_project_by_id(project_id: UUID) -> ProjectResponse:
    try:
        project = get_project(settings, project_id)
    except psycopg.Error as exc:
        raise _registry_unavailable(exc) from exc
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return project


@app.post(
    "/api/v1/projects/{project_id}/inspect",
    response_model=ProjectResponse,
    tags=["projects"],
)
def inspect_project_by_id(project_id: UUID) -> ProjectResponse:
    try:
        project = inspect_registered_project(settings, project_id)
    except ProjectPathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except psycopg.Error as exc:
        raise _registry_unavailable(exc) from exc
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return project
