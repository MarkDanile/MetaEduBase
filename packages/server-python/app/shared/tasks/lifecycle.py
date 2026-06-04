"""Shared Celery task lifecycle helpers.

集中 Celery 任务编排中重复的「任务生命周期」横切逻辑：

- `get_sync_session` / `run_in_session`：在 Celery worker 的独立事件循环中提供
  一次性 AsyncSession，统一 commit / rollback 语义。
- `update_task_status` / `create_task`：维护 `metaedu.document_tasks` 表，统一
  处理 `started_at` / `completed_at` / `updated_at` / `error_message` 列。

业务侧只需要 import 共享版本，避免在 `document/tasks.py` /
`structured_data/tasks.py` 等多个文件里维护相同的 helper 副本。

下划线开头的别名是为了兼容现有调用点（避免一次性改动两个文件的所有调用）。
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------


class _SyncSession:
    """一次性 AsyncSession context manager.

    Celery 任务在独立的事件循环里运行；这里按任务调用现场创建新的 engine + session
    factory，并在退出时 dispose engine，避免事件循环跨任务复用导致的 "attached to
    a different loop" 错误。
    """

    def __init__(self) -> None:
        self._engine = create_async_engine(settings.database_url, echo=False)
        self._factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> AsyncSession:
        self._session = self._factory()
        return self._session

    async def __aexit__(self, *exc) -> None:
        if self._session is not None:
            await self._session.close()
        await self._engine.dispose()


def get_sync_session() -> _SyncSession:
    """Return a fresh context manager wrapping an AsyncSession bound to a new event loop."""
    return _SyncSession()


async def run_in_session(coro):
    """Run an async coroutine that takes an AsyncSession, with commit/rollback semantics.

    The coroutine must accept a single `session` argument and return its result.
    On success, commits. On exception, rolls back and re-raises.
    """
    async with get_sync_session() as session:
        try:
            result = await coro(session)
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# document_tasks table helpers
# ---------------------------------------------------------------------------


async def update_task_status(
    session: AsyncSession,
    task_id: uuid.UUID,
    status: str,
    progress: int = 0,
    error_message: str | None = None,
) -> None:
    """Update a single row in `metaedu.document_tasks`.

    列写入规则：
    - 始终写 `status` / `progress` / `updated_at`
    - status='running' 且 progress=0 时额外写 `started_at`
    - status in ('success', 'failed') 时额外写 `completed_at`
    - error_message 非空时额外写 `error_message`
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    sets = ["status = :status", "progress = :progress", "updated_at = :now"]
    params: dict = {"tid": task_id, "status": status, "progress": progress, "now": now}
    if status == "running" and progress == 0:
        sets.append("started_at = :now")
    if status in ("success", "failed"):
        sets.append("completed_at = :now")
    if error_message:
        sets.append("error_message = :err")
        params["err"] = error_message
    await session.execute(
        text(f"UPDATE metaedu.document_tasks SET {', '.join(sets)} WHERE id = :tid"),
        params,
    )


async def create_task(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    file_id: uuid.UUID | None = None,
    dataset_id: uuid.UUID | None = None,
    task_type: str,
) -> uuid.UUID:
    """Insert a new row in `metaedu.document_tasks` and return its id.

    `file_id` 与 `dataset_id` 互斥：必须且只能传一个。
    """
    if (file_id is None) == (dataset_id is None):
        raise ValueError(
            "create_task requires exactly one of file_id or dataset_id (got "
            f"file_id={file_id!r}, dataset_id={dataset_id!r})"
        )

    task_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    target_column = "file_id" if file_id is not None else "dataset_id"
    target_value = file_id if file_id is not None else dataset_id

    # target_column is restricted to {"file_id", "dataset_id"} above and never
    # built from user input, so a f-string interpolation is safe here.
    await session.execute(
        text(
            f"INSERT INTO metaedu.document_tasks "
            f"(id, tenant_id, {target_column}, task_type, status, progress, created_at) "
            f"VALUES (:id, :tid, :target_value, :type, 'pending', 0, :now)"
        ),
        {
            "id": task_id,
            "tid": tenant_id,
            "target_value": target_value,
            "type": task_type,
            "now": now,
        },
    )
    return task_id


# ---------------------------------------------------------------------------
# Underscore-prefixed aliases for backwards compatibility with existing call sites.
# New code should prefer the public names above.
# ---------------------------------------------------------------------------

_get_sync_session = get_sync_session
_run_in_session = run_in_session
_update_task_status = update_task_status
_create_task = create_task
