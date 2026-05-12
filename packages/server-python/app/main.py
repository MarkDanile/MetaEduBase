from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
import app.shared.infrastructure.models  # noqa: F401
from app.shared.infrastructure.seed import init_db_with_seed
from app.contexts.identity.interfaces.api.router import router as identity_router
from app.contexts.knowledge.interfaces.api.router import router as knowledge_router
from app.contexts.knowledge.interfaces.api.ai_router import router as ai_router
from app.contexts.resource.interfaces.api.router import router as resource_router


@asynccontextmanager
async def lifespan(application: FastAPI):
    await init_db_with_seed()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(identity_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(knowledge_router, prefix="/api/v1/knowledge", tags=["knowledge"])
app.include_router(ai_router, prefix="/api/v1/ai", tags=["ai"])
app.include_router(resource_router, prefix="/api/v1/resources", tags=["resources"])


@app.get("/api/v1/health")
async def health_check():
    return {"status": "ok", "version": settings.app_version}
