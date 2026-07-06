from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.shared.infrastructure.models  # noqa: F401
from app.config import settings
from app.contexts.ai_app.interfaces.api.router import router as ai_app_router
from app.contexts.document.interfaces.api.router import router as document_router
from app.contexts.identity.interfaces.api.router import router as identity_router
from app.contexts.knowledge.interfaces.api.ai_router import router as ai_router
from app.contexts.knowledge.interfaces.api.graph_retrieve_router import (
    router as graph_retrieve_router,
)
from app.contexts.knowledge.interfaces.api.router import router as knowledge_router
from app.contexts.resource.interfaces.api.router import router as resource_router
from app.contexts.structured_data.application.query_service import QueryService
from app.contexts.structured_data.interfaces.api.query_router import (
    router as data_query_router,
)
from app.contexts.structured_data.interfaces.api.router import router as structured_data_router
from app.contexts.structured_data.interfaces.api.task_router import (
    router as structured_data_task_router,
)
from app.contexts.template.interfaces.api.router import router as template_router
from app.shared.infrastructure.database import async_session_factory


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    """REQ-052 Task 5 — build a single :class:`QueryService` at startup.

    The service is stateless beyond its collaborators; building it once
    keeps the wiring code out of the request hot path. ``app.state`` is
    the FastAPI-native place for app-scoped state — the router reads
    it via ``request.app.state.query_service``.
    """
    app.state.query_service = QueryService(
        session_factory=async_session_factory,
    )
    try:
        yield
    finally:
        # No resources to release — ``async_session_factory`` shares
        # the engine owned by ``app.shared.infrastructure.database``,
        # which is disposed at process exit.
        app.state.query_service = None


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
app.include_router(
    graph_retrieve_router,
    prefix="/api/v1/knowledge",
    tags=["knowledge-graph"],
)
app.include_router(ai_router, prefix="/api/v1/ai", tags=["ai"])
app.include_router(
    resource_router, prefix="/api/v1/resources", tags=["resources"]
)
app.include_router(
    document_router, prefix="/api/v1/document", tags=["documents"]
)
app.include_router(
    structured_data_router,
    prefix="/api/v1/structured-data",
    tags=["structured-data"],
)
app.include_router(
    structured_data_task_router,
    prefix="/api/v1/structured-data",
    tags=["structured-data-tasks"],
)
app.include_router(
    data_query_router, tags=["data-query"]
)
app.include_router(template_router)
app.include_router(ai_app_router, prefix="/api/v1/ai-apps", tags=["ai-apps"])


@app.get("/api/v1/health")
async def health_check():
    return {"status": "ok", "version": settings.app_version}
