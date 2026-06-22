from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.logging_config import setup_logging
from app.modules.orchestrator.service import OrchestratorService
from app.modules.orchestrator.router import router as orchestrator_router
from app.modules.validator.router import router as validator_router
from app.modules.storage.router import router as storage_router
from app.storage.db import SessionLocal

setup_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.validate_runtime()
    db = SessionLocal()
    try:
        OrchestratorService().recover_interrupted_runs(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
    docs_url="/docs" if settings.api_docs_enabled else None,
    redoc_url="/redoc" if settings.api_docs_enabled else None,
    openapi_url="/openapi.json" if settings.api_docs_enabled else None,
)

if settings.normalized_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.normalized_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/")
def read_root():
    return {"status": "ok", "app": settings.app_name}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


app.include_router(orchestrator_router)
app.include_router(validator_router)
app.include_router(storage_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port)
