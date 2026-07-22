"""REQ-058 Slice 3: DD 动作权限矩阵 + maker-checker（AC-1/AC-3/AC-6）。

权限矩阵（D-1）：leader=招商、admin/data_admin=合规、super_admin=平台。
所有报告强制 maker-checker：confirm/reject 需 admin/data_admin 且 ≠ generated_by。
"""
from __future__ import annotations

import uuid

import pytest

from app.contexts.due_diligence.application.dd_permissions import (
    DdAction,
    DdPermissionError,
    assert_can_confirm_report,
    can_perform,
)

GENERATOR = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
CONFIRMER = uuid.UUID("00000000-0000-0000-0000-0000000000a2")
OTHER_USER = uuid.UUID("00000000-0000-0000-0000-0000000000a3")


# --------- can_perform 动作矩阵 ---------


def test_leader_can_create():
    assert can_perform(DdAction.CREATE, role="leader") is True


def test_admin_can_create():
    assert can_perform(DdAction.CREATE, role="admin") is True


def test_data_admin_can_create():
    assert can_perform(DdAction.CREATE, role="data_admin") is True


def test_super_admin_cannot_create():
    """super_admin 是平台运维，不应能创建 DD 任务（AC-5 仅看 status）。"""
    assert can_perform(DdAction.CREATE, role="super_admin") is False


def test_teacher_cannot_create():
    assert can_perform(DdAction.CREATE, role="teacher") is False


def test_leader_can_run_own():
    assert can_perform(DdAction.RUN, role="leader", is_creator=True) is True


def test_non_creator_non_high_privilege_cannot_run():
    assert can_perform(DdAction.RUN, role="leader", is_creator=False) is False


def test_admin_cannot_run_creator_action():
    """admin（合规复核）不能 run 任务（run 由创建者完成）。"""
    assert can_perform(DdAction.RUN, role="admin", is_creator=False) is False


def test_admin_can_confirm():
    assert can_perform(DdAction.CONFIRM, role="admin") is True


def test_data_admin_can_confirm():
    assert can_perform(DdAction.CONFIRM, role="data_admin") is True


def test_leader_cannot_confirm():
    """AC-3: leader（maker）不能 confirm 自己生成的报告。"""
    assert can_perform(DdAction.CONFIRM, role="leader") is False


def test_super_admin_cannot_confirm():
    """AC-5: 平台管理员不能 confirm。"""
    assert can_perform(DdAction.CONFIRM, role="super_admin") is False


def test_admin_can_archive():
    assert can_perform(DdAction.ARCHIVE, role="admin") is True


def test_leader_cannot_archive():
    assert can_perform(DdAction.ARCHIVE, role="leader") is False


def test_only_super_admin_can_configure_tenant():
    assert can_perform(DdAction.CONFIGURE_TENANT, role="super_admin") is True
    assert can_perform(DdAction.CONFIGURE_TENANT, role="admin") is False
    assert can_perform(DdAction.CONFIGURE_TENANT, role="leader") is False


# --------- maker-checker: report confirm -------


def test_confirm_rejects_same_user_as_generator():
    """AC-3: 生成者不能 confirm 自己生成的报告（即使角色是 admin）。"""
    with pytest.raises(DdPermissionError) as exc:
        assert_can_confirm_report(
            generator_id=GENERATOR, confirmer_id=GENERATOR,
            confirmer_role="admin",
        )
    assert "maker" in str(exc.value).lower() or "self" in str(exc.value).lower()


def test_confirm_rejects_non_high_privilege_role():
    """leader/student/teacher 不能 confirm（AC-3 制审分离）。"""
    for role in ("leader", "teacher", "employee", "student"):
        with pytest.raises(DdPermissionError):
            assert_can_confirm_report(
                generator_id=GENERATOR, confirmer_id=CONFIRMER,
                confirmer_role=role,
            )


def test_confirm_rejects_super_admin():
    """AC-5: super_admin 不能 confirm（只读状态）。"""
    with pytest.raises(DdPermissionError):
        assert_can_confirm_report(
            generator_id=GENERATOR, confirmer_id=OTHER_USER,
            confirmer_role="super_admin",
        )


def test_confirm_allows_different_admin():
    """admin != generator 时可 confirm。"""
    # 不抛错
    assert_can_confirm_report(
        generator_id=GENERATOR, confirmer_id=CONFIRMER,
        confirmer_role="admin",
    )
