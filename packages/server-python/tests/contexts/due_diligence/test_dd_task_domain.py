"""Unit tests for the due-diligence task state machine + subject anchoring (AC-1).

Pure domain tests — no DB. Cover the legal transition graph, the AC-1 hard
invariant (run forbidden unless subject_confirmed), confirm_subject recording
the resolved subject verbatim, and rejection of illegal transitions.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.contexts.due_diligence.domain.dd_task import (
    DdTask,
    DdTaskStateError,
    SubjectCandidate,
    SubjectNotConfirmedError,
)


def _task(status: str = "subject_pending") -> DdTask:
    return DdTask(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        title="背调任务",
        subject_query="某企业简称",
        created_by=uuid.uuid4(),
        status=status,
    )


def _candidate() -> SubjectCandidate:
    return SubjectCandidate(company_name="某企业有限公司", credit_code="91XXXXXXXXXXXXXXXX")


# ---- AC-1: 主体未确认禁止运行 ----


def test_run_forbidden_when_subject_pending():
    task = _task("subject_pending")
    with pytest.raises(SubjectNotConfirmedError) as exc:
        task.assert_can_run()
    assert exc.value.error_code == "subject_not_confirmed"


def test_run_forbidden_blocks_mark_running():
    task = _task("subject_pending")
    with pytest.raises(SubjectNotConfirmedError):
        task.mark_running()
    assert task.status == "subject_pending"  # 状态未被破坏


def test_run_allowed_after_confirm():
    task = _task("subject_pending")
    task.confirm_subject(_candidate(), by=uuid.uuid4(), at=datetime.now(UTC))
    task.assert_can_run()  # 不抛
    task.mark_running()
    assert task.status == "running"


# ---- confirm_subject 记录解析后的主体 ----


def test_confirm_subject_records_subject_verbatim():
    task = _task("subject_pending")
    by = uuid.uuid4()
    at = datetime.now(UTC)
    task.confirm_subject(_candidate(), by=by, at=at)
    assert task.status == "subject_confirmed"
    assert task.confirmed_subject == {
        "company_name": "某企业有限公司",
        "credit_code": "91XXXXXXXXXXXXXXXX",
    }
    assert task.confirmed_by == by
    assert task.confirmed_at == at


def test_confirm_subject_without_credit_code():
    task = _task("subject_pending")
    task.confirm_subject(
        SubjectCandidate(company_name="某企业有限公司", credit_code=None),
        by=uuid.uuid4(),
        at=datetime.now(UTC),
    )
    assert task.confirmed_subject == {
        "company_name": "某企业有限公司",
        "credit_code": None,
    }


# ---- 状态机合法/非法迁移 ----


def test_full_happy_path():
    task = _task("subject_pending")
    task.confirm_subject(_candidate(), by=uuid.uuid4(), at=datetime.now(UTC))
    task.mark_running()
    task.mark_review()
    task.mark_archived()
    assert task.status == "archived"


def test_review_can_rerun():
    task = _task("review")
    task.confirmed_subject = {"company_name": "某企业有限公司", "credit_code": "X"}
    task.mark_running()  # review + 已确认主体 -> running 允许(重跑产生新版本)
    assert task.status == "running"


def test_review_without_subject_cannot_rerun():
    task = _task("review")
    task.confirmed_subject = None  # review 但主体丢失 -> 仍禁止运行
    with pytest.raises(SubjectNotConfirmedError):
        task.mark_running()


def test_illegal_transition_rejected():
    task = _task("subject_pending")
    with pytest.raises(DdTaskStateError) as exc:
        task.mark_review()  # pending 不能直接进 review
    assert exc.value.error_code == "invalid_transition"
    assert task.status == "subject_pending"


def test_archived_is_terminal():
    task = _task("archived")
    # archived 既过不了运行门(主体未确认/已归档),也无任何合法迁移
    with pytest.raises(SubjectNotConfirmedError):
        task.mark_running()
    with pytest.raises(DdTaskStateError):
        task.mark_review()


def test_failed_can_reset_to_pending():
    task = _task("running")
    task.mark_failed()
    assert task.status == "failed"
    task.confirm_subject(_candidate(), by=uuid.uuid4(), at=datetime.now(UTC))
    # failed -> subject_pending -> subject_confirmed 由 confirm 内部迁移承载
    assert task.status == "subject_confirmed"


def test_pending_to_running_rejected():
    task = _task("subject_pending")
    with pytest.raises(DdTaskStateError):
        task._transition("running")
