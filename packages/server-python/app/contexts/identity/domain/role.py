"""BUG-017: role 受控枚举与高权集合。

身份入口的 role 必须是受控枚举，不接受任意字符串。公开 register 只能
创建最低权限（teacher）；高权角色仅经管理员入口授予。
"""
from __future__ import annotations

from enum import StrEnum


class RoleEnum(StrEnum):
    """系统受控角色集合（现有已知值全集，含低权角色）。"""

    SUPER_ADMIN = "super_admin"
    DATA_ADMIN = "data_admin"
    ADMIN = "admin"
    LEADER = "leader"
    TEACHER = "teacher"
    EMPLOYEE = "employee"
    STUDENT = "student"


# 高权角色：可绕过模块 RBAC 的管理角色。公开 register 不得创建，仅管理员入口授予。
HIGH_PRIVILEGE_ROLES: frozenset[str] = frozenset(
    {RoleEnum.SUPER_ADMIN.value, RoleEnum.DATA_ADMIN.value, RoleEnum.ADMIN.value}
)

# 管理员入口可授予的角色全集（受控枚举边界）。
ASSIGNABLE_ROLES: frozenset[str] = frozenset(r.value for r in RoleEnum)


def is_valid_role(role: str) -> bool:
    """role 是否在受控枚举内（大小写敏感）。"""
    return role in ASSIGNABLE_ROLES
