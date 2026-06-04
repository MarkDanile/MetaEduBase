"""聚焦测试：app.shared.tasks.lifecycle helper。

每个测试都连接到 conftest.py 提供的 TEST_DATABASE_URL，依赖
`./dev.sh init-test-db` 一次性建好的 schema。所有写入的 document_tasks
行都在测试结束后清理，不污染其他测试。
"""

from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.shared.infrastructure.seed import DEFAULT_TENANT_ID
from app.shared.tasks.lifecycle import (
    _create_task,
    _run_in_session,
    _update_task_status,
    create_task,
    get_sync_session,
    run_in_session,
    update_task_status,
)

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", settings.database_url)


@asynccontextmanager
async def _session():
    """Open a fresh AsyncSession against TEST_DATABASE_URL, with cleanup semantics."""
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    async with _session() as s:
        yield s


@pytest_asyncio.fixture
async def task_row(session: AsyncSession):
    """Create a fresh document_tasks row and yield its id; cleanup at teardown."""
    task_id = await create_task(
        session, DEFAULT_TENANT_ID, file_id=uuid.uuid4(), task_type="lifecycle_test"
    )
    await session.commit()
    yield task_id
    # Cleanup: best-effort delete (task may not exist if test rolled back)
    try:
        await session.execute(
            text("DELETE FROM metaedu.document_tasks WHERE id = :tid"),
            {"tid": task_id},
        )
        await session.commit()
    except Exception:
        await session.rollback()


async def _fetch_row(session: AsyncSession, task_id: uuid.UUID) -> dict:
    result = await session.execute(
        text(
            "SELECT status, progress, error_message, started_at, completed_at, "
            "updated_at, file_id, dataset_id "
            "FROM metaedu.document_tasks WHERE id = :tid"
        ),
        {"tid": task_id},
    )
    return dict(result.mappings().first() or {})


# ---------------------------------------------------------------------------
# update_task_status
# ---------------------------------------------------------------------------


class TestUpdateTaskStatus:
    @pytest.mark.asyncio
    async def test_running_zero_progress_writes_started_at(
        self, session: AsyncSession, task_row: uuid.UUID
    ) -> None:
        before = datetime.now(UTC).replace(tzinfo=None)
        await update_task_status(session, task_row, "running", 0)
        await session.commit()

        row = await _fetch_row(session, task_row)
        assert row["status"] == "running"
        assert row["progress"] == 0
        assert row["started_at"] is not None
        assert row["completed_at"] is None
        assert row["error_message"] is None
        assert row["updated_at"] is not None
        # started_at should be at or after `before` (UTC, tz-naive)
        assert row["started_at"] >= before

    @pytest.mark.asyncio
    async def test_running_nonzero_progress_does_not_overwrite_started_at(
        self, session: AsyncSession, task_row: uuid.UUID
    ) -> None:
        await update_task_status(session, task_row, "running", 0)
        await session.commit()
        first = await _fetch_row(session, task_row)
        first_started = first["started_at"]

        await update_task_status(session, task_row, "running", 50)
        await session.commit()
        second = await _fetch_row(session, task_row)
        assert second["status"] == "running"
        assert second["progress"] == 50
        assert second["started_at"] == first_started
        assert second["completed_at"] is None

    @pytest.mark.asyncio
    async def test_success_writes_completed_at(
        self, session: AsyncSession, task_row: uuid.UUID
    ) -> None:
        await update_task_status(session, task_row, "running", 0)
        await session.commit()

        await update_task_status(session, task_row, "success", 100)
        await session.commit()

        row = await _fetch_row(session, task_row)
        assert row["status"] == "success"
        assert row["progress"] == 100
        assert row["completed_at"] is not None
        assert row["started_at"] is not None

    @pytest.mark.asyncio
    async def test_failed_writes_completed_at_and_error_message(
        self, session: AsyncSession, task_row: uuid.UUID
    ) -> None:
        await update_task_status(session, task_row, "running", 0)
        await session.commit()

        await update_task_status(session, task_row, "failed", 0, "boom")
        await session.commit()

        row = await _fetch_row(session, task_row)
        assert row["status"] == "failed"
        assert row["error_message"] == "boom"
        assert row["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_status_update_always_writes_updated_at(
        self, session: AsyncSession, task_row: uuid.UUID
    ) -> None:
        # structured_data 旧实现不写 updated_at；shared 版本必须永远写。
        await update_task_status(session, task_row, "running", 25)
        await session.commit()
        first = await _fetch_row(session, task_row)
        assert first["updated_at"] is not None

        # Sleep would be flaky; trust that any later status update bumps it
        await update_task_status(session, task_row, "running", 75)
        await session.commit()
        second = await _fetch_row(session, task_row)
        assert second["updated_at"] >= first["updated_at"]


# ---------------------------------------------------------------------------
# create_task
# ---------------------------------------------------------------------------


class TestCreateTask:
    @pytest.mark.asyncio
    async def test_creates_row_with_file_id(self, session: AsyncSession) -> None:
        file_id = uuid.uuid4()
        task_id = await create_task(
            session, DEFAULT_TENANT_ID, file_id=file_id, task_type="file_task"
        )
        await session.commit()

        row = await _fetch_row(session, task_id)
        assert row["status"] == "pending"
        assert row["progress"] == 0
        assert row["file_id"] == file_id
        assert row["dataset_id"] is None
        # cleanup
        await session.execute(
            text("DELETE FROM metaedu.document_tasks WHERE id = :tid"),
            {"tid": task_id},
        )
        await session.commit()

    @pytest.mark.asyncio
    async def test_creates_row_with_dataset_id(self, session: AsyncSession) -> None:
        dataset_id = uuid.uuid4()
        task_id = await create_task(
            session, DEFAULT_TENANT_ID, dataset_id=dataset_id, task_type="ds_task"
        )
        await session.commit()

        row = await _fetch_row(session, task_id)
        assert row["status"] == "pending"
        assert row["progress"] == 0
        assert row["dataset_id"] == dataset_id
        assert row["file_id"] is None
        # cleanup
        await session.execute(
            text("DELETE FROM metaedu.document_tasks WHERE id = :tid"),
            {"tid": task_id},
        )
        await session.commit()

    @pytest.mark.asyncio
    async def test_rejects_when_both_file_id_and_dataset_id_missing(
        self, session: AsyncSession
    ) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            await create_task(session, DEFAULT_TENANT_ID, task_type="oops")

    @pytest.mark.asyncio
    async def test_rejects_when_both_file_id_and_dataset_id_provided(
        self, session: AsyncSession
    ) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            await create_task(
                session,
                DEFAULT_TENANT_ID,
                file_id=uuid.uuid4(),
                dataset_id=uuid.uuid4(),
                task_type="oops",
            )


# ---------------------------------------------------------------------------
# run_in_session
# ---------------------------------------------------------------------------


class TestRunInSession:
    @pytest.mark.asyncio
    async def test_commits_when_coroutine_succeeds(self) -> None:
        marker_id = uuid.uuid4()

        async def work(session: AsyncSession):
            await create_task(
                session, DEFAULT_TENANT_ID, file_id=marker_id, task_type="commit_test"
            )
            return marker_id

        async with _session() as verify_session:
            # Pre-clean
            await verify_session.execute(
                text("DELETE FROM metaedu.document_tasks WHERE file_id = :fid"),
                {"fid": marker_id},
            )
            await verify_session.commit()

        result = await run_in_session(work)
        assert result == marker_id

        # Verify committed row is visible from a fresh session
        async with _session() as verify_session:
            result_rows = await verify_session.execute(
                text(
                    "SELECT id FROM metaedu.document_tasks WHERE file_id = :fid"
                ),
                {"fid": marker_id},
            )
            ids = [r["id"] for r in result_rows.mappings().all()]
            assert len(ids) == 1
            # cleanup
            await verify_session.execute(
                text("DELETE FROM metaedu.document_tasks WHERE file_id = :fid"),
                {"fid": marker_id},
            )
            await verify_session.commit()

    @pytest.mark.asyncio
    async def test_rolls_back_and_reraises_on_exception(self) -> None:
        marker_id = uuid.uuid4()

        async def failing(session: AsyncSession):
            await create_task(
                session,
                DEFAULT_TENANT_ID,
                file_id=marker_id,
                task_type="rollback_test",
            )
            raise RuntimeError("boom")

        # Pre-clean any stale rows
        async with _session() as pre:
            await pre.execute(
                text("DELETE FROM metaedu.document_tasks WHERE file_id = :fid"),
                {"fid": marker_id},
            )
            await pre.commit()

        with pytest.raises(RuntimeError, match="boom"):
            await run_in_session(failing)

        # Verify nothing was committed
        async with _session() as verify_session:
            result = await verify_session.execute(
                text("SELECT id FROM metaedu.document_tasks WHERE file_id = :fid"),
                {"fid": marker_id},
            )
            rows = [r["id"] for r in result.mappings().all()]
            assert rows == []


# ---------------------------------------------------------------------------
# Backwards-compatible alias surface
# ---------------------------------------------------------------------------


class TestAliases:
    def test_underscore_aliases_resolve_to_public_names(self) -> None:
        # Underscore-prefixed names exist purely for call-site compatibility;
        # the actual implementations are the public ones.
        assert _update_task_status is update_task_status
        assert _create_task is create_task
        assert _run_in_session is run_in_session
        # get_sync_session has no underscore alias in this module, but the
        # shared module also exports a synonym indirectly via lifecycle; we
        # check the public get_sync_session is a callable.
        assert callable(get_sync_session)
