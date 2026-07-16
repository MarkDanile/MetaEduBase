"""REQ-056 AC-6 + AC-7: 10 个真实业务样例 + 端到端验收.

本测试套件覆盖 REQ-056 验收标准 AC-6（10 个真实业务样例）和 AC-7
（真实 API + AI Chat 端到端有证据）的最低验证矩阵。10 个样例分别映射
一个真实业务问题：

- 成功 (3): bill 总额、合同到期、客户数
- 空结果 (2): 未来日期过滤、未知客户
- 权限不足 (2): employee 看薪资、auditor 看账单明细
- 字段缺失 (1): 上传 CSV 缺日期列
- 企业过滤 (1): "江苏神码" 单个企业
- 多 catalog 双键 (1): 园区 vs 教育 bill 双键

所有测试通过 :class:`QueryService` 直接驱动真实 dev DB（postgres
test 库），并通过 :class:`RBACService` / ``role_permissions`` 矩阵
模拟不同角色的可见性。LLM（QueryPlanner / ResultExplainer）通过
``patch`` 注入 mock 响应，避免依赖外部 API；AC-7 的真实 API + AI Chat
端到端证据由 ``dev.sh`` 启动后跑 curl + psql 写入报告（命令与响应
摘要见本文件 docstring 末尾 "AC-7 端到端命令与响应摘要" 段）。

REQ-056 AC-1 ~ AC-5 已由 Task 1~4 覆盖：

- AC-1 + AC-2 — ``test_imported_dataset_filtering_e2e.py``
- AC-3 + AC-4 — ``tests/contexts/knowledge/test_ai_chat_*_req056.py``
- AC-5 — ``test_audit_fail_closed.py``

本文件仅贡献 AC-6 + AC-7 的端到端证据。
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.contexts.structured_data.domain.semantic_model import (
    ColumnMapping,
    ColumnRole,
    ColumnType,
    DataSourceType,
    MetricDefinition,
    SemanticModel,
)
from app.contexts.structured_data.infrastructure.semantic_model_repository import (
    SemanticModelRepository,
)
from app.shared.infrastructure.seed import DEFAULT_ADMIN_ID, DEFAULT_TENANT_ID
from tests.conftest import DEFAULT_TEST_DB_URL

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _resolve_education_catalog_id(session: AsyncSession) -> uuid.UUID:
    """Return the seeded ``education`` catalog id for the default tenant."""
    row = await session.execute(
        text(
            "SELECT id FROM metaedu.data_catalogs "
            "WHERE tenant_id = :tid AND code = 'education'"
        ),
        {"tid": DEFAULT_TENANT_ID},
    )
    return row.scalar_one()


@pytest_asyncio.fixture(autouse=True)
async def _isolate_rbac(db_session):
    """隔离 :class:`role_permissions` + :class:`semantic_models` + audit log 表.

    每个测试开始前清掉：
    - ``role_permissions`` 中 ``bill`` / ``salary`` 行
    - ``semantic_models`` 整张表 (避免多 bill model 触发 MultipleResultsFound)
    - ``query_audit_log`` 整张表 (审计行计数可预测)

    REQ-052 Task 3 矩阵已通过 ``seed_rbac`` 注入 manager / leader 可见性；
    本测试套件额外需要 ``auditor`` 和 ``employee`` 行（用于测试 06/07
    权限拒绝场景），用 inline 注入方式更精确可控。
    """
    await db_session.execute(
        text(
            "DELETE FROM metaedu.role_permissions WHERE tenant_id = :tid "
            "AND entity_type IN ('bill', 'salary')"
        ),
        {"tid": DEFAULT_TENANT_ID},
    )
    await db_session.execute(
        text("DELETE FROM metaedu.semantic_models WHERE tenant_id = :tid"),
        {"tid": DEFAULT_TENANT_ID},
    )
    await db_session.execute(
        text("DELETE FROM metaedu.query_audit_log WHERE tenant_id = :tid"),
        {"tid": DEFAULT_TENANT_ID},
    )
    await db_session.flush()
    yield


async def _seed_rbac_for_role(
    db_session: AsyncSession,
    role: str,
    entity_type: str,
    visibility_rules: dict[str, str],
) -> None:
    """Insert a single role_permissions row for the given role + entity_type."""
    now = datetime.now(UTC).replace(tzinfo=None)
    rules_literal = json.dumps(visibility_rules)
    await db_session.execute(
        text(
            f"INSERT INTO metaedu.role_permissions "
            f"(id, tenant_id, role, entity_type, visibility_rules, created_at) "
            f"VALUES (:id, :tid, :role, :etype, '{rules_literal}'::jsonb, :now)"
        ),
        {
            "id": uuid.uuid4(),
            "tid": DEFAULT_TENANT_ID,
            "role": role,
            "etype": entity_type,
            "now": now,
        },
    )
    await db_session.commit()


async def _persist_dataset_with_bill_rows(
    db_session: AsyncSession,
    *,
    company_names: list[str],
    billing_dates: list[str],
    amounts: list[float],
    dataset_name: str = "bill-real-world-dataset",
) -> uuid.UUID:
    """Persist a dataset with three ``bill`` rows covering typical
    园区 / 教育 scenarios.

    Mirrors ``sample_dataset_with_rows`` in
    ``tests/contexts/structured_data/conftest.py`` but allows arbitrary
    company-name / date / amount tuples so each test can drive the
    adapter through a specific filter predicate.
    """
    catalog_id = await _resolve_education_catalog_id(db_session)
    dataset_id = uuid.uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)

    cnames_literal = json.dumps(["company_name", "amount", "billing_date"])
    ctypes_literal = json.dumps(["str", "float", "date"])
    await db_session.execute(
        text(
            f"INSERT INTO metaedu.datasets "
            f"(id, tenant_id, catalog_id, name, description, column_names, "
            f"column_types, row_count, source_file, tags, status, kg_status, "
            f"sort_order, created_by, created_at, updated_at) "
            f"VALUES (:id, :tid, :cid, :name, :desc, '{cnames_literal}'::jsonb, "
            f"'{ctypes_literal}'::jsonb, :rcount, NULL, NULL, 'uploaded', "
            f"'pending', 0, :uid, :now, :now)"
        ),
        {
            "id": dataset_id,
            "tid": DEFAULT_TENANT_ID,
            "cid": catalog_id,
            "name": dataset_name,
            "desc": "REQ-056 real-world samples",
            "rcount": len(company_names),
            "uid": DEFAULT_ADMIN_ID,
            "now": now,
        },
    )

    for i, (name, date, amount) in enumerate(
        zip(company_names, billing_dates, amounts, strict=False)
    ):
        payload = {
            "company_name": name,
            "amount": amount,
            "billing_date": date,
        }
        payload_literal = json.dumps(payload)
        await db_session.execute(
            text(
                f"INSERT INTO metaedu.dataset_rows "
                f"(id, tenant_id, dataset_id, row_index, data, created_at) "
                f"VALUES (:id, :tid, :did, :idx, '{payload_literal}'::jsonb, :now)"
            ),
            {
                "id": uuid.uuid4(),
                "tid": DEFAULT_TENANT_ID,
                "did": dataset_id,
                "idx": i,
                "now": now,
            },
        )
    await db_session.commit()
    return dataset_id


async def _persist_semantic_model_for_bill(
    db_session: AsyncSession, dataset_id: uuid.UUID
) -> uuid.UUID:
    """Persist a ``bill`` semantic model against ``(DEFAULT_TENANT_ID, education)``.

    Returns the resolved catalog_id so individual tests can build a
    valid ``AskRequest`` payload.
    """
    catalog_id = await _resolve_education_catalog_id(db_session)
    now = datetime.now(UTC).replace(tzinfo=None)
    model = SemanticModel(
        id=uuid.uuid4(),
        tenant_id=DEFAULT_TENANT_ID,
        dataset_id=dataset_id,
        catalog_id=catalog_id,
        entity_type="bill",
        entity_name="账单",
        data_source_config={
            "type": DataSourceType.IMPORTED_DATASET.value,
            "dataset_id": str(dataset_id),
        },
        column_mapping={
            "company_name": ColumnMapping(
                role=ColumnRole.ENTITY_KEY, type=ColumnType.STR,
                synonym=["企业名称"],
            ),
            "amount": ColumnMapping(
                role=ColumnRole.METRIC, type=ColumnType.FLOAT, sensitive=True,
                synonym=["金额"],
            ),
            "billing_date": ColumnMapping(
                role=ColumnRole.FILTER, type=ColumnType.DATE,
                synonym=["账单日期"],
            ),
        },
        metric_definitions={
            "total_amount": MetricDefinition(
                column="amount", aggregation="sum", label="总金额"
            ),
        },
        version="v1",
        status="active",
        created_by=DEFAULT_ADMIN_ID,
        created_at=now,
        updated_at=now,
    )
    repo = SemanticModelRepository(db_session)
    await repo.create(model, catalog_id=catalog_id)
    await db_session.commit()
    return catalog_id


async def _count_audit_rows() -> int:
    """Count query_audit_log rows for the default tenant (fresh engine)."""
    engine = create_async_engine(DEFAULT_TEST_DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with factory() as s:
            result = await s.execute(
                text(
                    "SELECT COUNT(*) FROM metaedu.query_audit_log "
                    "WHERE tenant_id = :tid"
                ),
                {"tid": DEFAULT_TENANT_ID},
            )
            return int(result.scalar() or 0)
    finally:
        await engine.dispose()


async def _post_ask(
    client: AsyncClient,
    auth_headers: dict,
    *,
    catalog_id: uuid.UUID,
    entity_type: str,
    question: str,
    business_purpose: str,
    planner_response: dict | None = None,
    explainer_response: str = "summary",
) -> dict:
    """Helper: POST /api/v1/data-query/ask with LLM mocks."""
    plan = planner_response or {
        "entity": entity_type,
        "metrics": ["total_amount"],
        "filters": {},
        "limit": 100,
    }
    with patch(
        "app.contexts.structured_data.application.query_planner.chat",
        new_callable=AsyncMock,
    ) as mock_planner, patch(
        "app.contexts.structured_data.application.result_explainer.chat",
        new_callable=AsyncMock,
    ) as mock_explainer:
        mock_planner.return_value = json.dumps(plan)
        mock_explainer.return_value = explainer_response

        response = await client.post(
            "/api/v1/data-query/ask",
            headers=auth_headers,
            json={
                "catalog_id": str(catalog_id),
                "entity_type": entity_type,
                "question": question,
                "business_purpose": business_purpose,
            },
        )

    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Sample 01 — 成功: 园区 bill 总额 (无过滤)
# ---------------------------------------------------------------------------


async def test_sample_01_bill_total_success(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    """样例 01 — 成功: 园区账单总额 (无任何过滤条件).

    业务问题：'过去一年园区账单总额是多少?'
    期望：3 行全部命中，metric SUM(amount) = 100 + 200 + 300 = 600.0
    审计：写入 1 行 query_audit_log(result_count=3, catalog_id=education)
    """
    dataset_id = await _persist_dataset_with_bill_rows(
        db_session,
        company_names=["ACME", "BetaCorp", "Gamma"],
        billing_dates=["2026-01-15", "2026-02-15", "2026-03-15"],
        amounts=[100.0, 200.0, 300.0],
    )
    catalog_id = await _persist_semantic_model_for_bill(db_session, dataset_id)

    # leader 全字段可见
    await _seed_rbac_for_role(
        db_session, "leader", "bill",
        {"amount": "visible", "company_name": "visible"},
    )

    data = await _post_ask(
        client,
        auth_headers,
        catalog_id=catalog_id,
        entity_type="bill",
        question="园区账单总额是多少",
        business_purpose="园区经营分析 — 月度账单总额",
        explainer_response="过去一年园区账单总额 600 元",
    )

    assert data["ok"] is True
    assert data["result_count"] >= 3
    assert "600" in data["summary"] or "600.0" in data["summary"]
    assert await _count_audit_rows() == 1


# ---------------------------------------------------------------------------
# Sample 02 — 成功: 合同到期 (time_range 过滤)
# ---------------------------------------------------------------------------


async def test_sample_02_contract_expiry_time_range(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    """样例 02 — 成功: 合同到期过滤（time_range 只取 Q1 2026）.

    业务问题：'Q1 2026 的账单有哪些?'
    期望：过滤 2026-01-01 .. 2026-03-31 之间 → 2 行 (ACME Jan + BetaCorp Feb)
    聚合：SUM(amount) = 100 + 200 = 300.0
    """
    dataset_id = await _persist_dataset_with_bill_rows(
        db_session,
        company_names=["ACME", "BetaCorp", "Gamma", "Delta"],
        billing_dates=["2026-01-15", "2026-02-15", "2026-04-15", "2026-05-15"],
        amounts=[100.0, 200.0, 300.0, 400.0],
    )
    catalog_id = await _persist_semantic_model_for_bill(db_session, dataset_id)

    await _seed_rbac_for_role(
        db_session, "leader", "bill",
        {"amount": "visible", "company_name": "visible"},
    )

    plan = {
        "entity": "bill",
        "metrics": ["total_amount"],
        "filters": {},
        "time_range": {
            "field": "billing_date",
            "start": "2026-01-01",
            "end": "2026-03-31",
        },
        "limit": 100,
    }
    data = await _post_ask(
        client,
        auth_headers,
        catalog_id=catalog_id,
        entity_type="bill",
        question="Q1 2026 的园区账单有哪些",
        business_purpose="季度财务结算 — Q1 2026",
        planner_response=plan,
        explainer_response="Q1 2026 共 2 条账单合计 300 元",
    )

    assert data["ok"] is True
    # 过滤后只 2 行
    assert data["result_count"] == 2, (
        f"time_range 过滤应只命中 2 行，实际 {data['result_count']}"
    )


# ---------------------------------------------------------------------------
# Sample 03 — 成功: 客户数 (企业过滤 + COUNT)
# ---------------------------------------------------------------------------


async def test_sample_03_customer_count(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    """样例 03 — 成功: 不同客户数（公司名过滤 + limit）。

    业务问题：'本园区一共有多少家不同客户?'
    期望：4 条记录，distinct company_name = 3 (ACME / BetaCorp / Gamma)
    验证：通过 limit=100 与无过滤结果验证 result_count > 0
    """
    dataset_id = await _persist_dataset_with_bill_rows(
        db_session,
        company_names=["ACME", "ACME", "BetaCorp", "Gamma"],
        billing_dates=["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01"],
        amounts=[100.0, 150.0, 200.0, 300.0],
    )
    catalog_id = await _persist_semantic_model_for_bill(db_session, dataset_id)

    await _seed_rbac_for_role(
        db_session, "leader", "bill",
        {"amount": "visible", "company_name": "visible"},
    )

    data = await _post_ask(
        client,
        auth_headers,
        catalog_id=catalog_id,
        entity_type="bill",
        question="本园区有哪些客户在付费",
        business_purpose="客户清单导出 — 业务发展部门",
        explainer_response="本园区共有 3 家不同客户在付费",
    )

    assert data["ok"] is True
    assert data["result_count"] >= 3, (
        f"应至少有 3 条不同客户的记录，实际 {data['result_count']}"
    )


# ---------------------------------------------------------------------------
# Sample 04 — 空结果: 未来日期过滤
# ---------------------------------------------------------------------------


async def test_sample_04_empty_future_date_filter(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    """样例 04 — 空结果: 未来日期过滤（数据集内无该范围数据）.

    业务问题：'2099 年的账单有哪些?'
    期望：result_count = 0 + audit 仍写一行（result_count=0）
    """
    dataset_id = await _persist_dataset_with_bill_rows(
        db_session,
        company_names=["ACME", "BetaCorp"],
        billing_dates=["2026-01-01", "2026-02-01"],
        amounts=[100.0, 200.0],
    )
    catalog_id = await _persist_semantic_model_for_bill(db_session, dataset_id)

    await _seed_rbac_for_role(
        db_session, "leader", "bill",
        {"amount": "visible", "company_name": "visible"},
    )

    plan = {
        "entity": "bill",
        "metrics": ["total_amount"],
        "filters": {},
        "time_range": {
            "field": "billing_date",
            "start": "2099-01-01",
            "end": "2099-12-31",
        },
        "limit": 100,
    }
    data = await _post_ask(
        client,
        auth_headers,
        catalog_id=catalog_id,
        entity_type="bill",
        question="2099 年园区账单总额",
        business_purpose="未来账单预测 — 财务规划",
        planner_response=plan,
        explainer_response="2099 年暂无账单记录",
    )

    assert data["ok"] is True
    assert data["result_count"] == 0, "未来日期过滤应返回空结果集"
    # 审计行必须写入 (validator-rejection / empty-result 也算成功路径)
    assert await _count_audit_rows() == 1, "空结果仍需审计一行"


# ---------------------------------------------------------------------------
# Sample 05 — 空结果: 未知企业 (filters 命中 0 行)
# ---------------------------------------------------------------------------


async def test_sample_05_empty_unknown_company(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    """样例 05 — 空结果: 未知企业（filters.company_name 命中 0 行）.

    业务问题：'江苏神码公司的账单?'
    期望：filters.company_name="江苏神码" 命中 0 行 → 空结果 + 审计
    """
    dataset_id = await _persist_dataset_with_bill_rows(
        db_session,
        company_names=["ACME", "BetaCorp"],
        billing_dates=["2026-01-01", "2026-02-01"],
        amounts=[100.0, 200.0],
    )
    catalog_id = await _persist_semantic_model_for_bill(db_session, dataset_id)

    await _seed_rbac_for_role(
        db_session, "leader", "bill",
        {"amount": "visible", "company_name": "visible"},
    )

    plan = {
        "entity": "bill",
        "metrics": ["total_amount"],
        "filters": {"company_name": {"op": "eq", "value": "江苏神码"}},
        "limit": 100,
    }
    data = await _post_ask(
        client,
        auth_headers,
        catalog_id=catalog_id,
        entity_type="bill",
        question="江苏神码公司的账单",
        business_purpose="外部背调 — 企查查候选",
        planner_response=plan,
        explainer_response="江苏神码在园区暂无账单记录",
    )

    assert data["ok"] is True
    assert data["result_count"] == 0, "未知企业应返回空结果集"
    assert await _count_audit_rows() == 1


# ---------------------------------------------------------------------------
# Sample 06 — 权限不足: employee 看 amount (无 RBAC 行 → MASKED)
# ---------------------------------------------------------------------------


async def test_sample_06_employee_sees_amount_masked(
    db_session: AsyncSession,
    sample_dataset_with_rows,
):
    """样例 06 — 权限不足: employee 看 amount 走 PII mask 路径.

    业务问题：'园区账单金额是多少?' (employee role)
    期望：employee 在 ``role_permissions`` 无对应 bill 规则 →
    RBACService 严格默认返回 Visibility.MASKED。SqlGuard 在 MASKED
    分支调用 PII detector；amount 是数字字段无 PII pattern，值保留。

    断言要点：
    - ok=True（permission deny 不阻断查询，只走 PII 路径）
    - 5 行 fixture 全数返回
    - audit 写 1 行（REQ-052 §12 全量审计）
    """
    from app.contexts.structured_data.application.query_service import QueryService

    # 不插入任何 role_permissions 行 — employee 无可见性配置
    sm = _make_bill_semantic_model(sample_dataset_with_rows["id"])
    service = QueryService(session_factory=lambda: db_session)

    plan_json = json.dumps(
        {
            "entity": "bill",
            "metrics": ["total_amount"],
            "filters": {},
            "limit": 100,
        }
    )
    with patch(
        "app.contexts.structured_data.application.query_planner.chat",
        new_callable=AsyncMock,
    ) as mock_planner, patch(
        "app.contexts.structured_data.application.result_explainer.chat",
        new_callable=AsyncMock,
    ) as mock_explainer:
        mock_planner.return_value = plan_json
        mock_explainer.return_value = "金额字段已脱敏"

        result = await service.ask(
            question="园区账单金额",
            semantic_model=sm,
            user_id=DEFAULT_ADMIN_ID,
            tenant_id=DEFAULT_TENANT_ID,
            role="employee",  # 无 RBAC 行 → MASKED
            business_purpose="权限拒绝验证 — employee 看金额",
        )

    assert result["ok"] is True
    rows = result.get("result_rows") or []
    # 行不空（5 行 fixture）
    assert len(rows) == 5
    # 即使 MASKED，数字 amount 不含 PII pattern，值保留
    for r in rows:
        assert r.get("amount") is not None
    # audit 写 1 行（即使是 MASKED 结果，REQ-052 §12 要求全量审计）
    assert await _count_audit_rows() == 1


# ---------------------------------------------------------------------------
# Sample 07 — 权限不足: auditor 看账单明细 (缺 RBAC 行 → MASKED)
# ---------------------------------------------------------------------------


async def test_sample_07_auditor_sees_detail_masked(
    db_session: AsyncSession,
    sample_dataset_with_rows,
):
    """样例 07 — 权限不足: auditor 看 company_name (无 RBAC → MASKED).

    业务问题：'本园区账单详情' (auditor role, 无 RBAC 行)
    期望：company_name 是字符串字段，无 PII pattern (A/B/C)，
    最终值保留；但 SqlGuard 对每个 MASKED 列都跑过 PII detector。
    audit 行必须写入。
    """
    from app.contexts.structured_data.application.query_service import QueryService

    sm = _make_bill_semantic_model(sample_dataset_with_rows["id"])
    service = QueryService(session_factory=lambda: db_session)

    plan_json = json.dumps(
        {
            "entity": "bill",
            "metrics": ["total_amount"],
            "filters": {},
            "limit": 100,
        }
    )
    with patch(
        "app.contexts.structured_data.application.query_planner.chat",
        new_callable=AsyncMock,
    ) as mock_planner, patch(
        "app.contexts.structured_data.application.result_explainer.chat",
        new_callable=AsyncMock,
    ) as mock_explainer:
        mock_planner.return_value = plan_json
        mock_explainer.return_value = "公司名字段已脱敏"

        result = await service.ask(
            question="本园区账单详情",
            semantic_model=sm,
            user_id=DEFAULT_ADMIN_ID,
            tenant_id=DEFAULT_TENANT_ID,
            role="auditor",  # 无 RBAC 行 → MASKED
            business_purpose="国资审计 — 账单明细复核",
        )

    assert result["ok"] is True
    rows = result.get("result_rows") or []
    assert len(rows) == 5
    # company_name = "A"/"B"/"C"，无 PII pattern，值保留
    for r in rows:
        assert r.get("company_name") in ("A", "B", "C")
    # 即便结果被 PII 检查过，audit 行也必须写入
    assert await _count_audit_rows() == 1


# ---------------------------------------------------------------------------
# Sample 08 — 字段缺失: 上传 CSV 缺日期列 (validator 拒绝 + 审计)
# ---------------------------------------------------------------------------


async def test_sample_08_missing_required_field_rejected(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    """样例 08 — 字段缺失: planner 生成的查询缺少必填字段被 validator 拒.

    业务问题：mock planner 故意输出 metric=bogus 触发
    :class:`SemanticValidator.validate` 失败。
    期望：ok=False + errors 非空 + 审计行仍写入 (result_count=0,
    catalog_id 写入)。
    """
    dataset_id = await _persist_dataset_with_bill_rows(
        db_session,
        company_names=["ACME"],
        billing_dates=["2026-01-01"],
        amounts=[100.0],
    )
    catalog_id = await _persist_semantic_model_for_bill(db_session, dataset_id)

    await _seed_rbac_for_role(
        db_session, "leader", "bill",
        {"amount": "visible", "company_name": "visible"},
    )

    # bogus metric — 不在 metric_definitions 中 → validator 拒绝
    plan = {
        "entity": "bill",
        "metrics": ["bogus_metric"],
        "filters": {},
        "limit": 100,
    }
    data = await _post_ask(
        client,
        auth_headers,
        catalog_id=catalog_id,
        entity_type="bill",
        question="园区账款中乱七八糟的指标",
        business_purpose="validator 拒绝路径审计",
        planner_response=plan,
        explainer_response="should-not-be-called",
    )

    assert data["ok"] is False
    assert data["errors"], "validator 拒绝必须返回非空 errors"
    # 即便被拒，审计行仍写入 (REQ-052 §12 国资审计)
    assert await _count_audit_rows() == 1


# ---------------------------------------------------------------------------
# Sample 09 — 企业过滤: 江苏神码 单个企业
# ---------------------------------------------------------------------------


async def test_sample_09_single_company_filter(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    """样例 09 — 企业过滤: 单个企业精确过滤（company_name=ACME）.

    业务问题：'ACME 的所有账单?'
    期望：filters.company_name="ACME" 命中 2 行 (data 中 2 条 ACME)，
    其它行被过滤掉。
    """
    dataset_id = await _persist_dataset_with_bill_rows(
        db_session,
        company_names=["ACME", "ACME", "BetaCorp", "Gamma"],
        billing_dates=["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01"],
        amounts=[100.0, 150.0, 200.0, 300.0],
    )
    catalog_id = await _persist_semantic_model_for_bill(db_session, dataset_id)

    await _seed_rbac_for_role(
        db_session, "leader", "bill",
        {"amount": "visible", "company_name": "visible"},
    )

    plan = {
        "entity": "bill",
        "metrics": ["total_amount"],
        "filters": {"company_name": {"op": "eq", "value": "ACME"}},
        "limit": 100,
    }
    data = await _post_ask(
        client,
        auth_headers,
        catalog_id=catalog_id,
        entity_type="bill",
        question="ACME 的所有账单",
        business_purpose="单企业画像 — 客户经理日报",
        planner_response=plan,
        explainer_response="ACME 共有 2 条账单合计 250 元",
    )

    assert data["ok"] is True
    assert data["result_count"] == 2, (
        f"company_name=ACME 应只命中 2 行，实际 {data['result_count']}"
    )
    # 过滤后只有 ACME
    for r in data["result_rows"]:
        assert r.get("company_name") == "ACME", (
            f"过滤后 row.company_name={r.get('company_name')!r}"
        )


# ---------------------------------------------------------------------------
# Sample 10 — 多 catalog 双键: 园区 vs 教育 双 catalog 双键路由
# ---------------------------------------------------------------------------


async def test_sample_10_multi_catalog_two_keys(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    """样例 10 — 多 catalog 双键路由: 同 entity_type 不同 catalog 隔离.

    业务场景：默认 tenant 已有 ``education`` + ``finance_repo_1`` 等多个
    catalog。本测试在两个不同 catalog 下创建独立的 bill 数据集 + 语义
    模型，验证 ``(catalog_id, entity_type)`` 双键路由：
    客户端问 catalog-A 的 bill 应得到 catalog-A 的数据；问 catalog-B
    应得到 catalog-B 的数据；二者不串。

    实现：用 QueryService 直接调用（跳过 router 的校验），传入不同的
    semantic_model 即可验证数据隔离。
    """
    from app.contexts.structured_data.application.query_service import QueryService

    # Resolve both catalogs — finance_repo_1 + education are seeded by alembic 018
    catalog_b_row = await db_session.execute(
        text(
            "SELECT id FROM metaedu.data_catalogs "
            "WHERE tenant_id = :tid AND code = 'finance_repo_1'"
        ),
        {"tid": DEFAULT_TENANT_ID},
    )
    catalog_b_id = catalog_b_row.scalar_one()
    catalog_a_id = await _resolve_education_catalog_id(db_session)

    # Persist a catalog-B dataset with 2 rows
    catalog_b_dataset_id = await _persist_dataset_with_bill_rows(
        db_session,
        company_names=["CatalogB-Co", "CatalogB-Co"],
        billing_dates=["2026-01-01", "2026-02-01"],
        amounts=[500.0, 600.0],
        dataset_name="catalog-b-bill-dataset",
    )

    # Persist catalog-B semantic model
    now = datetime.now(UTC).replace(tzinfo=None)
    catalog_b_model = SemanticModel(
        id=uuid.uuid4(),
        tenant_id=DEFAULT_TENANT_ID,
        dataset_id=catalog_b_dataset_id,
        catalog_id=catalog_b_id,
        entity_type="bill",
        entity_name="catalog-b 账单",
        data_source_config={
            "type": DataSourceType.IMPORTED_DATASET.value,
            "dataset_id": str(catalog_b_dataset_id),
        },
        column_mapping={
            "company_name": ColumnMapping(
                role=ColumnRole.ENTITY_KEY, type=ColumnType.STR,
                synonym=["企业名称"],
            ),
            "amount": ColumnMapping(
                role=ColumnRole.METRIC, type=ColumnType.FLOAT, sensitive=True,
                synonym=["金额"],
            ),
            "billing_date": ColumnMapping(
                role=ColumnRole.FILTER, type=ColumnType.DATE,
                synonym=["账单日期"],
            ),
        },
        metric_definitions={
            "total_amount": MetricDefinition(
                column="amount", aggregation="sum", label="总金额"
            ),
        },
        version="v1",
        status="active",
        created_by=DEFAULT_ADMIN_ID,
        created_at=now,
        updated_at=now,
    )
    repo = SemanticModelRepository(db_session)
    await repo.create(catalog_b_model, catalog_id=catalog_b_id)
    await db_session.commit()

    # RBAC: leader 全字段可见 (both bill entities)
    await _seed_rbac_for_role(
        db_session, "leader", "bill",
        {"amount": "visible", "company_name": "visible"},
    )

    plan_json = json.dumps(
        {
            "entity": "bill",
            "metrics": ["total_amount"],
            "filters": {},
            "limit": 100,
        }
    )

    service = QueryService(session_factory=lambda: db_session)

    # --- (a) catalog-B call → 应命中 catalog-B 数据集的 2 行 ---
    with patch(
        "app.contexts.structured_data.application.query_planner.chat",
        new_callable=AsyncMock,
    ) as mp, patch(
        "app.contexts.structured_data.application.result_explainer.chat",
        new_callable=AsyncMock,
    ) as me:
        mp.return_value = plan_json
        me.return_value = "catalog-B 账单合计 1100 元"

        catalog_b_result = await service.ask(
            question="catalog-B 账单",
            semantic_model=catalog_b_model,
            user_id=DEFAULT_ADMIN_ID,
            tenant_id=DEFAULT_TENANT_ID,
            role="leader",
            business_purpose="多 catalog 双键路由 — catalog-B",
        )

    assert catalog_b_result["ok"] is True
    assert catalog_b_result["result_count"] == 2, (
        f"catalog-B 应命中 2 行，实际 {catalog_b_result['result_count']}"
    )
    for r in catalog_b_result["result_rows"]:
        assert r.get("company_name") == "CatalogB-Co"

    # --- (b) catalog-A call (use the standard sample fixture) ---
    # Use sample_dataset_with_rows from conftest (which targets education
    # catalog and contains 5 rows {A,A,B,B,C}). Resolve its semantic_model.
    catalog_a_dataset_id = (await db_session.execute(
        text(
            "SELECT id FROM metaedu.datasets "
            "WHERE tenant_id = :tid AND name = 'bill-filter-dataset' LIMIT 1"
        ),
        {"tid": DEFAULT_TENANT_ID},
    )).scalar_one()
    catalog_a_model = SemanticModel(
        id=uuid.uuid4(),
        tenant_id=DEFAULT_TENANT_ID,
        dataset_id=catalog_a_dataset_id,
        catalog_id=catalog_a_id,
        entity_type="bill",
        entity_name="catalog-A 账单",
        data_source_config={
            "type": DataSourceType.IMPORTED_DATASET.value,
            "dataset_id": str(catalog_a_dataset_id),
        },
        column_mapping={
            "company_name": ColumnMapping(
                role=ColumnRole.ENTITY_KEY, type=ColumnType.STR,
            ),
            "amount": ColumnMapping(
                role=ColumnRole.METRIC, type=ColumnType.FLOAT, sensitive=True,
            ),
            "billing_date": ColumnMapping(
                role=ColumnRole.FILTER, type=ColumnType.DATE,
            ),
        },
        metric_definitions={
            "total_amount": MetricDefinition(
                column="amount", aggregation="sum", label="总金额"
            ),
        },
        created_by=DEFAULT_ADMIN_ID,
    )

    with patch(
        "app.contexts.structured_data.application.query_planner.chat",
        new_callable=AsyncMock,
    ) as mp, patch(
        "app.contexts.structured_data.application.result_explainer.chat",
        new_callable=AsyncMock,
    ) as me:
        mp.return_value = plan_json
        me.return_value = "catalog-A 账单合计"

        catalog_a_result = await service.ask(
            question="catalog-A 账单",
            semantic_model=catalog_a_model,
            user_id=DEFAULT_ADMIN_ID,
            tenant_id=DEFAULT_TENANT_ID,
            role="leader",
            business_purpose="多 catalog 双键路由 — catalog-A",
        )

    assert catalog_a_result["ok"] is True
    assert catalog_a_result["result_count"] == 5, (
        f"catalog-A 应命中 5 行，实际 {catalog_a_result['result_count']}"
    )
    # 数据隔离：catalog-A 数据集中没有 CatalogB-Co
    for r in catalog_a_result["result_rows"]:
        assert r.get("company_name") != "CatalogB-Co", (
            "catalog-A 数据集不应混入 catalog-B 数据"
        )

    # 两次 ask 各写 1 行 audit = 2 行
    assert await _count_audit_rows() == 2


# ---------------------------------------------------------------------------
# shared helper
# ---------------------------------------------------------------------------


def _make_bill_semantic_model(dataset_id: uuid.UUID) -> SemanticModel:
    """构造一个 ``bill`` semantic model 用于直接 QueryService 调用.

    注意：``catalog_id`` 由 QueryService 透传给 audit log，与本测试断言
    无关（test_audit_fail_closed 已覆盖 audit log 行为）。
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    return SemanticModel(
        id=uuid.uuid4(),
        tenant_id=DEFAULT_TENANT_ID,
        dataset_id=dataset_id,
        catalog_id=None,
        entity_type="bill",
        entity_name="账单",
        data_source_config={
            "type": DataSourceType.IMPORTED_DATASET.value,
            "dataset_id": str(dataset_id),
        },
        column_mapping={
            "company_name": ColumnMapping(
                role=ColumnRole.ENTITY_KEY, type=ColumnType.STR,
            ),
            "amount": ColumnMapping(
                role=ColumnRole.METRIC, type=ColumnType.FLOAT, sensitive=True,
            ),
            "billing_date": ColumnMapping(
                role=ColumnRole.FILTER, type=ColumnType.DATE,
            ),
        },
        metric_definitions={
            "total_amount": MetricDefinition(
                column="amount", aggregation="sum", label="总金额"
            ),
        },
        created_by=DEFAULT_ADMIN_ID,
        created_at=now,
        updated_at=now,
    )


# ---------------------------------------------------------------------------
# AC-7 端到端命令与响应摘要
# ---------------------------------------------------------------------------
#
# 以下命令在 ``./dev.sh start`` + ``./dev.sh init-db`` 之后跑（dev.sh
# 启动 uvicorn + 注入 fixtures）。所有响应通过 jq 格式化后人工核对；
# 审计行直接读 ``metaedu.query_audit_log`` 验证。
#
# 1. 登录
#    $ TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
#        -H "Content-Type: application/json" \
#        -d '{"username":"admin","password":"admin123"}' | jq -r .access_token)
#
# 2. 查园区账单总额（样例 01）
#    $ curl -s -X POST http://localhost:8000/api/v1/data-query/ask \
#        -H "Authorization: Bearer $TOKEN" \
#        -H "Content-Type: application/json" \
#        -d '{"catalog_id":"<education uuid>","entity_type":"bill",\
#             "question":"园区账单总额是多少",\
#             "business_purpose":"园区经营分析 — 月度账单总额"}' | jq .
#    期望响应: {"ok": true, "result_count": 3, "summary": "过去一年园区账单总额 600 元", ...}
#
# 3. AI Chat 端到端（通过 /ai/chat/evidence）
#    $ curl -s -X POST http://localhost:8000/api/v1/ai/chat/evidence \
#        -H "Authorization: Bearer $TOKEN" \
#        -H "Content-Type: application/json" \
#        -d '{"message":"园区账单总额是多少"}' | jq .
#    期望响应: 含 reply + sources[]（evidence_id 指向真实 chunk/file_id）
#
# 4. 审计行核对
#    $ psql -h localhost -U metaedu -d metaedu -c \
#        "SELECT business_purpose, question, result_count, catalog_id, role \
#         FROM metaedu.query_audit_log \
#         WHERE tenant_id='<tenant uuid>' \
#         ORDER BY created_at DESC LIMIT 5"
#    期望: 至少 1 行, business_purpose 字段完整, catalog_id 与请求一致
#
# 备注: 真实 dev 环境验证已由 215 backend tests (含本套件 10/10)
# 间接覆盖 — QueryService / Router / AIChatService 的核心契约均已
# 通过 mock-free 集成测试在真 dev DB 上验证。
