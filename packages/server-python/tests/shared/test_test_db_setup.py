"""聚焦测试：测试数据库初始化安全。

不依赖真实 PostgreSQL：覆盖数据库名白名单校验、旧 conftest create_all
形态判定这两个纯函数路径。
"""

from __future__ import annotations

import pytest

from app.shared.infrastructure.test_db_setup import (
    _LEGACY_TABLES_FROM_CREATE_ALL,
    DatabaseNameError,
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
