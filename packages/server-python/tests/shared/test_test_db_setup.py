"""聚焦测试：测试数据库初始化安全。

不依赖真实 PostgreSQL：覆盖数据库名白名单校验、旧 conftest create_all
形态判定这两个纯函数路径。
"""

from __future__ import annotations

import pytest

from app.shared.infrastructure.test_db_setup import (
    _LEGACY_TABLES_FROM_CREATE_ALL,
    DatabaseNameError,
    _has_legacy_create_all_columns,
    _is_legacy_create_all_shape,
    _validate_database_name,
)


class TestValidateDatabaseName:
    @pytest.mark.parametrize(
        "name",
        [
            "metaedu_test",
            "MetaEduTest",
            "_underscore_start",
            "a",
            "a1b2c3",
            "x" * 63,  # PostgreSQL identifier 上限
        ],
    )
    def test_accepts_valid_identifiers(self, name: str) -> None:
        assert _validate_database_name(name) == name

    @pytest.mark.parametrize(
        "name",
        [
            'metaedu";DROP DATABASE metaedu;--',  # 注入尝试
            "metaedu_test;evil",
            'has"quote',
            "has space",
            "has-dash",
            "1starts_with_digit",
            "",
            "x" * 64,  # 超过 63 字节
        ],
    )
    def test_rejects_invalid_identifiers(self, name: str) -> None:
        with pytest.raises(DatabaseNameError):
            _validate_database_name(name)

    def test_rejects_none(self) -> None:
        with pytest.raises(DatabaseNameError):
            _validate_database_name(None)


class TestLegacyCreateAllShape:
    def test_matches_when_all_core_tables_exist_without_version(self) -> None:
        # 旧 conftest create_all 形态：所有核心表都存在，alembic_version 缺失。
        existing = set(_LEGACY_TABLES_FROM_CREATE_ALL)
        assert _is_legacy_create_all_shape(existing, missing_version=True) is True

    def test_misses_when_one_core_table_missing(self) -> None:
        existing = set(_LEGACY_TABLES_FROM_CREATE_ALL)
        existing.discard("knowledge_edges")
        assert _is_legacy_create_all_shape(existing, missing_version=True) is False

    def test_misses_when_alembic_version_exists(self) -> None:
        # 已有 alembic_version 说明走过 Alembic 路径，不属于遗留 create_all 形态。
        existing = set(_LEGACY_TABLES_FROM_CREATE_ALL)
        assert _is_legacy_create_all_shape(existing, missing_version=False) is False

    def test_misses_on_empty_schema(self) -> None:
        # 新环境零业务表，缺版本：不应被当作 legacy 触发 stamp。
        assert _is_legacy_create_all_shape(set(), missing_version=True) is False

    def test_misses_when_only_partial_tables_exist(self) -> None:
        # 残缺 schema：只建了少量表，缺版本。旧逻辑会误判为 legacy 触发 stamp；
        # 新逻辑必须拒绝 stamp，让后续 alembic upgrade head 显式失败。
        existing = {"tenants", "users", "templates"}
        assert _is_legacy_create_all_shape(existing, missing_version=True) is False


class TestLegacyColumnShape:
    """INSERT 目标表（tenants / users）的关键代表列必须齐全。"""

    def test_matches_when_required_columns_present(self) -> None:
        existing = {
            "tenants": {
                "id", "name", "school_name", "isolation",
                "is_active", "created_at", "updated_at",
            },
            "users": {
                "id", "tenant_id", "username", "email",
                "password_hash", "role", "clearance_level",
                "is_active", "created_at", "updated_at",
            },
        }
        assert _has_legacy_create_all_columns(existing) is True

    def test_misses_when_tenants_missing_school_name(self) -> None:
        # 真实回归：tenants 是 conftest INSERT 必填表；school_name 缺失
        # 会让 stamp head 掩盖 INSERT 失败。
        existing = {
            "tenants": {"id", "name", "created_at"},  # 缺 school_name
            "users": {
                "id", "tenant_id", "username", "password_hash", "created_at",
            },
        }
        assert _has_legacy_create_all_columns(existing) is False

    def test_misses_when_users_missing_tenant_id(self) -> None:
        # 真实回归：users.tenant_id 是 FK + NOT NULL；缺失会让 stamp head
        # 掩盖关系完整性错误。
        existing = {
            "tenants": {"id", "name", "school_name", "created_at"},
            "users": {
                "id", "username", "password_hash", "created_at",  # 缺 tenant_id
            },
        }
        assert _has_legacy_create_all_columns(existing) is False

    def test_misses_when_users_missing_password_hash(self) -> None:
        # 真实回归：users.password_hash 是 conftest INSERT 必填。
        existing = {
            "tenants": {"id", "name", "school_name", "created_at"},
            "users": {
                "id", "tenant_id", "username", "created_at",  # 缺 password_hash
            },
        }
        assert _has_legacy_create_all_columns(existing) is False

    def test_misses_when_only_one_required_column_dropped(self) -> None:
        # 即使只少一个代表列也必须拒绝。
        existing = {
            "tenants": {
                "id", "name", "school_name", "isolation",
                "is_active", "updated_at",  # 缺 created_at
            },
            "users": {
                "id", "tenant_id", "username", "password_hash", "created_at",
            },
        }
        assert _has_legacy_create_all_columns(existing) is False

    def test_treats_missing_target_table_as_inert(self) -> None:
        # 目标表不在字典里说明连表都没建到；这种情况由表集合检查负责，
        # 列级检查不应单独把"缺表"误判为"残缺列"。
        existing = {"users": {
            "id", "tenant_id", "username", "password_hash", "created_at",
        }}
        assert _has_legacy_create_all_columns(existing) is True

    def test_returns_true_for_empty_input(self) -> None:
        # 没有目标表的字典（schema 全新）应保持 True，让表集合检查去判定。
        assert _has_legacy_create_all_columns({}) is True
