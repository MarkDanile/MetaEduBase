"""Permission domain entities for REQ-052.

Two enums:

- :class:`Role` — five fixed roles from the REQ-052 spec:
  employee / manager / leader / data_admin / auditor.

- :class:`Visibility` — three field-level visibility outcomes:
  VISIBLE (raw text) / MASKED (redacted) / HIDDEN (column excluded).

These are string-valued enums (StrEnum) so they can be stored as-is in the
JSONB ``visibility_rules`` column on ``metaedu.role_permissions`` without
extra mapping. The string values are the contract with the database — do not
rename them without a coordinated migration.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """Five fixed roles defined by REQ-052 §12 (国资安全审查)."""

    EMPLOYEE = "employee"        # 普通员工
    MANAGER = "manager"          # 部门经理
    LEADER = "leader"            # 园区领导
    DATA_ADMIN = "data_admin"    # 数据管理员
    AUDITOR = "auditor"          # 审计员


class Visibility(StrEnum):
    """Three per-field outcomes enforced by the RBAC layer."""

    VISIBLE = "visible"   # 原文返回
    MASKED = "masked"     # 脱敏后返回
    HIDDEN = "hidden"     # 完全不返回该字段
