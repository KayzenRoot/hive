from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .health import HealthResponse, collect_health

settings = get_settings()
app = FastAPI(
    title="HIVE API",
    description="Minimal HIVE bootstrap health vertical slice.",
    version=settings.version,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


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
