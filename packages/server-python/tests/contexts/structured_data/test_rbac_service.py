"""Test RBAC service: 5 roles + field-level visibility + cross-tenant + audit.

REQ-052 Task 3: each test covers a behaviour of :class:`RBACService`. The
``db_session`` and ``seed_rbac`` fixtures come from
``tests/contexts/structured_data/conftest.py``.

Fixtures:
- ``seed_rbac`` pre-populates ``metaedu.role_permissions`` with visibility
  rules for ``manager`` and ``leader`` on ``bill``/``amount`` (VISIBLE) and
  ``bill``/``company_name`` (manager: MASKED, leader: VISIBLE). Other roles
  have no row, exercising the strict-default MASKED path.
"""

from __future__ import annotations

import json as _json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from app.contexts.structured_data.application.rbac_service import RBACService
from app.contexts.structured_data.domain.permissions import Role, Visibility
from app.contexts.structured_data.infrastructure.semantic_models_models import (
    QueryAuditLogModel,
    TenantAccessGrantModel,
)
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Field-level visibility (5-role matrix)
# ---------------------------------------------------------------------------


async def test_employee_sees_sensitive_field_masked(db_session, seed_rbac):
    """普通员工 (no row configured) → strict-default MASKED for sensitive.

    Employee has no row in role_permissions, so the strict-default path
    treats ``amount`` (a sensitive column) as MASKED.
    """
    rbac = RBACService(db_session)
    visibility = await rbac.get_field_visibility(
        tenant_id=DEFAULT_TENANT_ID,
        role=Role.EMPLOYEE,
        entity_type="bill",
        column_name="amount",
    )
    assert visibility == Visibility.MASKED


async def test_manager_sees_sensitive_field_visible(db_session, seed_rbac):
    """部门经理看 amount → VISIBLE（seed_rbac grants VISIBLE to manager）。"""
    rbac = RBACService(db_session)
    visibility = await rbac.get_field_visibility(
        tenant_id=DEFAULT_TENANT_ID,
        role=Role.MANAGER,
        entity_type="bill",
        column_name="amount",
    )
    assert visibility == Visibility.VISIBLE


async def test_manager_sees_company_name_masked(db_session, seed_rbac):
    """部门经理看 company_name → MASKED（per-field granularity check）。"""
    rbac = RBACService(db_session)
    visibility = await rbac.get_field_visibility(
        tenant_id=DEFAULT_TENANT_ID,
        role=Role.MANAGER,
        entity_type="bill",
        column_name="company_name",
    )
    assert visibility == Visibility.MASKED


async def test_leader_sees_sensitive_field_visible(db_session, seed_rbac):
    """园区领导看 amount → VISIBLE（leader 全字段可见）。"""
    rbac = RBACService(db_session)
    visibility = await rbac.get_field_visibility(
        tenant_id=DEFAULT_TENANT_ID,
        role=Role.LEADER,
        entity_type="bill",
        column_name="amount",
    )
    assert visibility == Visibility.VISIBLE


async def test_leader_sees_company_name_visible(db_session, seed_rbac):
    """园区领导看 company_name → VISIBLE。"""
    rbac = RBACService(db_session)
    visibility = await rbac.get_field_visibility(
        tenant_id=DEFAULT_TENANT_ID,
        role=Role.LEADER,
        entity_type="bill",
        column_name="company_name",
    )
    assert visibility == Visibility.VISIBLE


async def test_data_admin_no_rule_defaults_to_masked(db_session, seed_rbac):
    """data_admin no rule → MASKED (strict default)。"""
    rbac = RBACService(db_session)
    visibility = await rbac.get_field_visibility(
        tenant_id=DEFAULT_TENANT_ID,
        role=Role.DATA_ADMIN,
        entity_type="bill",
        column_name="amount",
    )
    assert visibility == Visibility.MASKED


async def test_auditor_no_rule_defaults_to_masked(db_session, seed_rbac):
    """auditor no rule → MASKED (strict default)。"""
    rbac = RBACService(db_session)
    visibility = await rbac.get_field_visibility(
        tenant_id=DEFAULT_TENANT_ID,
        role=Role.AUDITOR,
        entity_type="bill",
        column_name="amount",
    )
    assert visibility == Visibility.MASKED


async def test_visibility_resolves_to_hidden_when_configured(db_session):
    """当显式配置 'hidden' → 返回 HIDDEN（覆盖默认）。"""
    rbac = RBACService(db_session)
    # Clean any row from a prior run before inserting with our unique entity.
    unique_entity = "bill_hidden_test"
    await db_session.execute(
        text(
            "DELETE FROM metaedu.role_permissions "
            "WHERE tenant_id = :tid AND role = 'employee' AND entity_type = :et"
        ),
        {"tid": DEFAULT_TENANT_ID, "et": unique_entity},
    )
    rules = _json.dumps({"ssn": "hidden"})
    now = datetime.now(UTC).replace(tzinfo=None)
    await db_session.execute(
        text(
            f"INSERT INTO metaedu.role_permissions "
            f"(id, tenant_id, role, entity_type, visibility_rules, created_at) "
            f"VALUES (:id, :tid, 'employee', :et, '{rules}'::jsonb, :now)"
        ),
        {
            "id": uuid.uuid4(),
            "tid": DEFAULT_TENANT_ID,
            "et": unique_entity,
            "now": now,
        },
    )
    await db_session.flush()

    visibility = await rbac.get_field_visibility(
        tenant_id=DEFAULT_TENANT_ID,
        role=Role.EMPLOYEE,
        entity_type=unique_entity,
        column_name="ssn",
    )
    assert visibility == Visibility.HIDDEN


# ---------------------------------------------------------------------------
# Cross-tenant access control
# ---------------------------------------------------------------------------


async def test_default_cross_tenant_blocked(db_session, seed_rbac):
    """无 grant 时跨租户访问 → 拒绝。"""
    rbac = RBACService(db_session)
    other_tenant = uuid.UUID("00000000-0000-0000-0000-000000000002")
    allowed = await rbac.check_tenant_access(
        tenant_id=DEFAULT_TENANT_ID,
        grantee_tenant_id=other_tenant,
        entity_type="bill",
    )
    assert allowed is False


async def test_same_tenant_short_circuits_to_allowed(db_session, seed_rbac):
    """tenant_id == grantee_tenant_id → True（仓库同租户直接放行，无 DB 查询）。"""
    rbac = RBACService(db_session)
    allowed = await rbac.check_tenant_access(
        tenant_id=DEFAULT_TENANT_ID,
        grantee_tenant_id=DEFAULT_TENANT_ID,
        entity_type="bill",
    )
    assert allowed is True


async def test_cross_tenant_allowed_with_active_grant(db_session, seed_rbac):
    """存在未过期 grant → True。"""
    rbac = RBACService(db_session)
    other_tenant = uuid.UUID("00000000-0000-0000-0000-000000000003")
    grant = TenantAccessGrantModel(
        tenant_id=DEFAULT_TENANT_ID,
        grantee_tenant_id=other_tenant,
        entity_type="bill",
        approved_by=DEFAULT_ADMIN_ID,
        expires_at=None,  # never expires
    )
    db_session.add(grant)
    await db_session.flush()

    allowed = await rbac.check_tenant_access(
        tenant_id=DEFAULT_TENANT_ID,
        grantee_tenant_id=other_tenant,
        entity_type="bill",
    )
    assert allowed is True


async def test_cross_tenant_expired_grant_blocked(db_session, seed_rbac):
    """已过期 grant → False。"""
    rbac = RBACService(db_session)
    other_tenant = uuid.UUID("00000000-0000-0000-0000-000000000004")
    expired_time = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
    grant = TenantAccessGrantModel(
        tenant_id=DEFAULT_TENANT_ID,
        grantee_tenant_id=other_tenant,
        entity_type="bill",
        approved_by=DEFAULT_ADMIN_ID,
        expires_at=expired_time,
    )
    db_session.add(grant)
    await db_session.flush()

    allowed = await rbac.check_tenant_access(
        tenant_id=DEFAULT_TENANT_ID,
        grantee_tenant_id=other_tenant,
        entity_type="bill",
    )
    assert allowed is False


async def test_cross_tenant_grant_for_other_entity_does_not_apply(
    db_session, seed_rbac
):
    """Grant 仅对 entity_type 生效 — 不同 entity → 拒绝。"""
    rbac = RBACService(db_session)
    other_tenant = uuid.UUID("00000000-0000-0000-0000-000000000005")
    grant = TenantAccessGrantModel(
        tenant_id=DEFAULT_TENANT_ID,
        grantee_tenant_id=other_tenant,
        entity_type="contract",  # different entity_type
        approved_by=DEFAULT_ADMIN_ID,
        expires_at=None,
    )
    db_session.add(grant)
    await db_session.flush()

    allowed = await rbac.check_tenant_access(
        tenant_id=DEFAULT_TENANT_ID,
        grantee_tenant_id=other_tenant,
        entity_type="bill",  # ask for bill, grant was for contract
    )
    assert allowed is False


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


async def test_log_query_persists_row(db_session, seed_rbac):
    """log_query 应写入 query_audit_log 一行。"""
    rbac = RBACService(db_session)
    await rbac.log_query(
        user_id=DEFAULT_ADMIN_ID,
        tenant_id=DEFAULT_TENANT_ID,
        role=Role.MANAGER.value,
        business_purpose="账单核对 2026Q2",
        question="2026年第二季度各企业欠费金额是多少？",
        query_plan={"intent": "metric_query", "entity": "bill"},
        data_source_type="imported_dataset",
        data_source_ref="dataset-test-ref",
        result_count=12,
        duration_ms=234,
        ip="127.0.0.1",
        user_agent="pytest",
    )
    await db_session.flush()

    stmt = select(QueryAuditLogModel).where(
        QueryAuditLogModel.tenant_id == DEFAULT_TENANT_ID,
        QueryAuditLogModel.user_id == DEFAULT_ADMIN_ID,
    )
    rows = (await db_session.execute(stmt)).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.business_purpose == "账单核对 2026Q2"
    assert row.role == "manager"
    assert row.result_count == 12
    assert row.duration_ms == 234
    assert row.query_plan["intent"] == "metric_query"


async def test_log_query_enforces_business_purpose(db_session, seed_rbac):
    """business_purpose 是审计必填字段 — 空字符串 / 纯空白必须拒绝。"""
    rbac = RBACService(db_session)

    with pytest.raises(ValueError, match="business_purpose"):
        await rbac.log_query(
            user_id=DEFAULT_ADMIN_ID,
            tenant_id=DEFAULT_TENANT_ID,
            role=Role.EMPLOYEE.value,
            business_purpose="",  # empty -> reject
            question="some question",
            query_plan={},
            data_source_type="imported_dataset",
            data_source_ref=None,
            result_count=0,
            duration_ms=None,
            ip=None,
            user_agent=None,
        )

    with pytest.raises(ValueError, match="business_purpose"):
        await rbac.log_query(
            user_id=DEFAULT_ADMIN_ID,
            tenant_id=DEFAULT_TENANT_ID,
            role=Role.EMPLOYEE.value,
            business_purpose="   ",  # whitespace only -> reject
            question="some question",
            query_plan={},
            data_source_type="imported_dataset",
            data_source_ref=None,
            result_count=0,
            duration_ms=None,
            ip=None,
            user_agent=None,
        )
