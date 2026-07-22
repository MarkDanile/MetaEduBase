"""BUG-017 Slice 2: role 受控枚举策略（AC-1 前置）。

role 必须是受控枚举，不接受任意字符串；高权集合用于 register 降级和
管理员入口校验。
"""
from app.contexts.identity.domain.role import (
    HIGH_PRIVILEGE_ROLES,
    RoleEnum,
    is_valid_role,
)


def test_role_enum_contains_all_known_roles():
    assert {r.value for r in RoleEnum} == {
        "super_admin",
        "data_admin",
        "admin",
        "leader",
        "teacher",
        "employee",
        "student",
    }


def test_high_privilege_roles_exclude_low_privilege():
    assert {"super_admin", "data_admin", "admin"} == HIGH_PRIVILEGE_ROLES
    assert "teacher" not in HIGH_PRIVILEGE_ROLES
    assert "leader" not in HIGH_PRIVILEGE_ROLES


def test_is_valid_role_accepts_known_rejects_unknown():
    assert is_valid_role("teacher") is True
    assert is_valid_role("super_admin") is True
    assert is_valid_role("xxx") is False
    assert is_valid_role("") is False
    assert is_valid_role("ADMIN") is False  # 大小写敏感，不接受变体
