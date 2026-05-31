from fastapi import FastAPI

from app.core.config import settings
from app.modules.ingestion.router import router as ingestion_router
from app.modules.orchestrator.router import router as orchestrator_router
from app.modules.extractor.router import router as extractor_router
from app.modules.validator.router import router as validator_router
from app.modules.storage.router import router as storage_router

app = FastAPI(title=settings.app_name)

@app.get('/')
def read_root():
    return {"message": "Hi !!", "app": settings.app_name, "env": settings.environment}


app.include_router(ingestion_router)
app.include_router(orchestrator_router)
app.include_router(extractor_router)
app.include_router(validator_router)
app.include_router(storage_router)

