import logging
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app.config import settings
from app.contexts.agent_workspace.interfaces.api.router import (
    router as agent_workspace_router,
)
from app.contexts.ai_app.interfaces.api.router import router as ai_app_router
from app.contexts.document.interfaces.api.router import router as document_router
from app.contexts.due_diligence.interfaces.api.dd_router import (
    router as due_diligence_router,
)
from app.contexts.identity.application.auth_service import (
    validate_production_jwt_secret,
)
from app.contexts.identity.interfaces.api.admin_router import router as identity_admin_router
from app.contexts.identity.interfaces.api.router import router as identity_router
from app.contexts.knowledge.interfaces.api.ai_router import router as ai_router
from app.contexts.knowledge.interfaces.api.graph_retrieve_router import (
    router as graph_retrieve_router,
)
from app.contexts.knowledge.interfaces.api.router import router as knowledge_router
from app.contexts.mcp_registry.interfaces.api.mcp_registry_router import (
    router as mcp_registry_router,
)
from app.contexts.resource.interfaces.api.router import router as resource_router
from app.contexts.skill_registry.interfaces.api.skill_registry_router import (
    router as skill_registry_router,
)
from app.contexts.structured_data.application.query_service import QueryService
from app.contexts.structured_data.interfaces.api.catalog_router import (
    router as catalog_router,
)
from app.contexts.structured_data.interfaces.api.query_router import (
    router as data_query_router,
)
from app.contexts.structured_data.interfaces.api.router import router as structured_data_router
from app.contexts.structured_data.interfaces.api.task_router import (
    router as structured_data_task_router,
)
from app.contexts.template.interfaces.api.router import router as template_router
from app.internal_mcp.server import router as internal_mcp_router
from app.shared.infrastructure import models as _registered_models  # noqa: F401
from app.shared.infrastructure.database import async_session_factory

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    """REQ-052 Task 5 — build a single :class:`QueryService` at startup.

    The service is stateless beyond its collaborators; building it once
    keeps the wiring code out of the request hot path. ``app.state`` is
    the FastAPI-native place for app-scoped state — the router reads
    it via ``request.app.state.query_service``.
    BUG-017 AC-3: production 启动前校验 JWT 密钥--缺失 / default / 低强度
    直接 fail-fast，不让进程带可伪造的根信任进入服务态。
    """
    validate_production_jwt_secret(settings)
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


@app.exception_handler(OperationalError)
async def _db_unavailable_handler(
    request: Request, exc: OperationalError
) -> JSONResponse:
    """BUG-013 — Map asyncpg / SQLAlchemy DB-down errors to 503, not 500.

    When the local PostgreSQL service is not running (e.g. after ``./dev.sh stop``
    or before ``./dev.sh infra``), asyncpg raises ``ConnectionDoesNotExistError``,
    which SQLAlchemy wraps as :class:`OperationalError`. Without this handler,
    FastAPI returns 500 Internal Server Error and the frontend shows a generic
    "网络错误" / blank page.

    Per RFC 7231, 503 Service Unavailable is the correct status for "currently
    down but might recover" — distinguishes infrastructure outages (transient,
    operator-fixable) from code bugs (500, requires code fix). The response
    detail explains the likely cause so the user can run ``./dev.sh infra``.
    """
    original = getattr(exc, "orig", None)
    is_conn_error = isinstance(
        original, (asyncpg.exceptions.PostgresConnectionError, ConnectionRefusedError)
    )
    if not is_conn_error:
        # Non-connection OperationalError (e.g. transaction deadlock, serialization
        # failure) is a real backend error — log it as such and return 500.
        logger.error(
            "DB operational error on %s %s: %r",
            request.method,
            request.url.path,
            exc,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "数据库操作失败，请稍后重试"},
        )

    logger.warning(
        "BUG-013: DB connection unavailable on %s %s: %r",
        request.method,
        request.url.path,
        exc,
    )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "detail": "数据库暂时不可用，请确认 PostgreSQL 已启动（./dev.sh infra）后重试",
            "retry_after_seconds": 5,
        },
    )

app.include_router(identity_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(agent_workspace_router)
app.include_router(identity_admin_router, prefix="/api/v1/admin", tags=["admin"])
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
app.include_router(catalog_router)
app.include_router(mcp_registry_router)
app.include_router(skill_registry_router)
app.include_router(
    data_query_router, tags=["data-query"]
)
app.include_router(template_router)
app.include_router(ai_app_router, prefix="/api/v1/ai-apps", tags=["ai-apps"])
app.include_router(due_diligence_router)
app.include_router(internal_mcp_router)


@app.get("/api/v1/health")
async def health_check():
    return {"status": "ok", "version": settings.app_version}
