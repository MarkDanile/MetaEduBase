"""REQ-058 Slice 3: DD 动作权限矩阵 + maker-checker（AC-1/AC-3/AC-6）。

权限矩阵（spec D-1 frozen design）：

| 动作           | leader | admin/data_admin | super_admin | 其他低权 |
|----------------|--------|------------------|-------------|----------|
| create         | ✓      | ✓                | ✗           | ✗        |
| run            | own+allotted 需 creator | ✗        | ✗           | allotted  |
| confirm/reject | ✗ (maker) | ✓ (≠generated_by) | ✗      | ✗        |
| archive        | ✗      | ✓                | ✗           | ✗        |
| configure      | ✗      | ✗                | ✓           | ✗        |

maker-checker（D-2）：所有报告强制制审分离 —— confirm/reject 需
admin/data_admin 且 user_id != report.generated_by。
"""
from __future__ import annotations

import uuid
from enum import StrEnum


class DdAction(StrEnum):
    """DD 动作枚举（spec D-1 frozen design）。"""

    CREATE = "create"
    READ = "read"
    RUN = "run"
    CONFIRM = "confirm"
    REJECT = "reject"
    ARCHIVE = "archive"
    CONFIGURE_TENANT = "configure_tenant"


class DdPermissionError(PermissionError):
    """Raised when caller lacks permission for a DD action."""


# 角色权限矩阵（leader=招商，admin/data_admin=合规，super_admin=平台）
_ACTION_ROLES: dict[DdAction, frozenset[str]] = {
    DdAction.CREATE: frozenset({"leader", "admin", "data_admin"}),
    DdAction.READ: frozenset({"leader", "admin", "data_admin", "super_admin"}),
    DdAction.RUN: frozenset({"leader", "admin", "data_admin"}),  # 需 creator/allotted 二次校验
    DdAction.CONFIRM: frozenset({"admin", "data_admin"}),  # 需 ≠ generator 二次校验
    DdAction.REJECT: frozenset({"admin", "data_admin"}),
    DdAction.ARCHIVE: frozenset({"admin", "data_admin"}),
    DdAction.CONFIGURE_TENANT: frozenset({"super_admin"}),
}


def can_perform(
    action: DdAction,
    *,
    role: str,
    is_creator: bool = False,
    is_assignee: bool = False,
) -> bool:
    """静态角色权限 + creator/assignee 二次校验。

    适用范围：read 始终按 role；create 只需 role；run 需 role + (creator OR assignee OR high-priv)；
    confirm 需 role + ≠generator（实际拒由 assert_can_confirm_report 抛异常）。
    """
    allowed = _ACTION_ROLES.get(action, frozenset())
    if role not in allowed:
        return False
    if action in (DdAction.READ, DdAction.CREATE, DdAction.ARCHIVE,
                  DdAction.CONFIGURE_TENANT, DdAction.CONFIRM, DdAction.REJECT):
        return True
    if action == DdAction.RUN:
        # spec D-1: run 仅 leader 创建者/分配对象；admin/data_admin/super_admin 永不 run
        if role != "leader":
            return False
        return is_creator or is_assignee
    return True


def assert_can_confirm_report(
    *, generator_id: uuid.UUID, confirmer_id: uuid.UUID, confirmer_role: str,
) -> None:
    """AC-3 maker-checker：confirm/reject 需 admin/data_admin 且 ≠ generated_by。

    抛 :class:`DdPermissionError` 含明确 reason（fail-closed）。
    """
    if confirmer_role not in _ACTION_ROLES[DdAction.CONFIRM]:
        raise DdPermissionError(
            f"角色 {confirmer_role!r} 无权 confirm/reject 报告（需 admin/data_admin）"
        )
    if confirmer_id == generator_id:
        raise DdPermissionError(
            f"报告生成者（{generator_id}）不能 confirm 自己生成的报告（AC-3 maker-checker）"
        )
