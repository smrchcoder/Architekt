from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.logging_config import setup_logging
from app.modules.ingestion.router import router as ingestion_router
from app.modules.orchestrator.router import router as orchestrator_router
from app.modules.extractor.router import router as extractor_router
from app.modules.validator.router import router as validator_router
from app.modules.storage.router import router as storage_router

setup_logging()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(",") if settings.cors_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Hi !!", "app": settings.app_name, "env": settings.environment}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": type(exc).__name__},
    )


app.include_router(ingestion_router)
app.include_router(orchestrator_router)
app.include_router(extractor_router)
app.include_router(validator_router)
app.include_router(storage_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port)
