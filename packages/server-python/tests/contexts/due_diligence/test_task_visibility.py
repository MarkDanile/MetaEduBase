"""REQ-058 Slice 2: DdTask assignee_id + 可见性策略（AC-1/AC-2/AC-5）。

- DdTask 加 assignee_id 字段（spec D-3）
- DdTask.visible_to(user_id, role) -> bool：本人+分配对象+高权可见
- DdTaskService.list_tasks 改 WHERE created_by OR assignee_id OR HIGH_PRIVILEGE
- DdTaskService.get_by_id 跨 tenant/不可见 -> None（404）
- super_admin 看 status only（不动此 slice，留 Slice 3 报告层）

迁移 026：dd_tasks 加 assignee_id UUID NULL。
"""
from __future__ import annotations

import uuid

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.contexts.due_diligence.domain.dd_task import DdTask
from app.contexts.identity.domain.role import HIGH_PRIVILEGE_ROLES

CREATOR = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
ASSIGNEE = uuid.UUID("00000000-0000-0000-0000-0000000000a2")
OTHER_USER = uuid.UUID("00000000-0000-0000-0000-0000000000a3")
PLATFORM_ADMIN = uuid.UUID("00000000-0000-0000-0000-0000000000a4")

_TEST_DB_URL = (
    "postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test"
)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(_TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


def _make_task(*, creator=CREATOR, assignee: uuid.UUID | None = None) -> DdTask:
    return DdTask(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        title="test",
        subject_query="q",
        created_by=creator,
        assignee_id=assignee,
    )


def test_visible_to_creator():
    task = _make_task(creator=CREATOR)
    assert task.visible_to(CREATOR, role="leader") is True


def test_visible_to_assignee():
    task = _make_task(assignee=ASSIGNEE)
    assert task.visible_to(ASSIGNEE, role="leader") is True


def test_visible_to_high_privilege_role():
    task = _make_task()
    for role in HIGH_PRIVILEGE_ROLES:
        assert task.visible_to(OTHER_USER, role=role) is True, role


def test_not_visible_to_other_low_privilege_user():
    task = _make_task()
    assert task.visible_to(OTHER_USER, role="leader") is False


def test_not_visible_to_other_assigned_to_other():
    """不是创建者也不是分配对象且非高权 -> 不可见。"""
    task = _make_task(creator=CREATOR, assignee=ASSIGNEE)
    assert task.visible_to(OTHER_USER, role="leader") is False


def test_visible_to_assignee_with_role_teacher():
    """teacher/student 等被分配后仍可读+run allotted。"""
    task = _make_task(assignee=OTHER_USER)
    assert task.visible_to(OTHER_USER, role="teacher") is True
    assert task.visible_to(OTHER_USER, role="employee") is True
    assert task.visible_to(OTHER_USER, role="student") is True


def test_visible_to_none_assignee_low_privilege():
    task = _make_task()  # 无 assignee
    assert task.visible_to(OTHER_USER, role="leader") is False
