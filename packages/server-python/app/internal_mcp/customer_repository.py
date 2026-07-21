"""Tenant-scoped reads over imported park datasets for the internal MCP."""
from __future__ import annotations

import uuid

from sqlalchemy import String, bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

_LOOKUP_EXPRESSIONS = {
    "客户ID": "dr.data->>'客户ID'",
    "合同ID": "dr.data->>'合同ID'",
    "房间ID": "dr.data->>'房间ID'",
    "项目ID": "dr.data->>'项目ID'",
    "楼栋ID": "dr.data->>'楼栋ID'",
    "楼层ID": "dr.data->>'楼层ID'",
    "流水ID": "dr.data->>'流水ID'",
    "账单ID": "dr.data->>'账单ID'",
}


_LATEST_DATASET_JOIN = (
    "JOIN LATERAL ("
    "SELECT id, tenant_id, created_at FROM metaedu.datasets "
    "WHERE tenant_id = :tid AND entity_type = :entity_type "
    "AND status = 'processed' ORDER BY created_at DESC, id DESC LIMIT 1"
    ") ds ON ds.id = dr.dataset_id AND ds.tenant_id = dr.tenant_id "
)


class InternalCustomerRepository:
    """Read processed ``dataset_rows`` without crossing the tenant boundary."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def has_dataset(self, tenant_id: uuid.UUID, entity_type: str) -> bool:
        result = await self._session.scalar(
            text(
                "SELECT EXISTS ("
                "SELECT 1 FROM metaedu.datasets "
                "WHERE tenant_id = :tid AND entity_type = :entity_type "
                "AND status = 'processed'"
                ")"
            ),
            {"tid": tenant_id, "entity_type": entity_type},
        )
        return bool(result)

    async def find_subject(
        self,
        tenant_id: uuid.UUID,
        *,
        company_name: str,
        credit_code: str | None,
    ) -> dict | None:
        lookup_clause = (
            "dr.data->>'统一社会信用代码' = :lookup_value"
            if credit_code
            else "dr.data->>'客户名称' = :lookup_value"
        )
        result = await self._session.execute(
            text(
                "SELECT dr.data FROM metaedu.dataset_rows dr "
                + _LATEST_DATASET_JOIN
                + "WHERE dr.tenant_id = :tid AND "
                + lookup_clause
                + " ORDER BY dr.row_index LIMIT 1"
            ),
            {
                "tid": tenant_id,
                "entity_type": "customer",
                "lookup_value": credit_code or company_name,
            },
        )
        row = result.scalar_one_or_none()
        return dict(row) if row else None

    async def find_rows_by_keys(
        self,
        tenant_id: uuid.UUID,
        *,
        entity_type: str,
        lookups: dict[str, set[str]],
    ) -> list[dict]:
        """Find rows matching any of several fixed relation keys."""
        clauses: list[str] = []
        params: dict = {"tid": tenant_id, "entity_type": entity_type}
        statement = (
            "SELECT dr.data FROM metaedu.dataset_rows dr "
            + _LATEST_DATASET_JOIN
            + "WHERE dr.tenant_id = :tid AND ("
        )
        for index, (lookup_key, values) in enumerate(lookups.items()):
            if not values:
                continue
            try:
                expression = _LOOKUP_EXPRESSIONS[lookup_key]
            except KeyError as exc:
                raise ValueError(f"unsupported lookup key: {lookup_key}") from exc
            param_name = f"values_{index}"
            clauses.append(f"{expression} = ANY(:{param_name})")
            params[param_name] = sorted(values)
        if not clauses:
            return []
        query = text(
            statement + " OR ".join(clauses) + ") ORDER BY dr.row_index"
        )
        query = query.bindparams(
            *[
                bindparam(name, type_=ARRAY(String()))
                for name in params
                if name.startswith("values_")
            ]
        )
        result = await self._session.execute(query, params)
        return [dict(row) for row in result.scalars().all()]

    async def find_rows(
        self,
        tenant_id: uuid.UUID,
        *,
        entity_type: str,
        lookup_key: str,
        values: set[str],
    ) -> list[dict]:
        """Find rows by one of the fixed park-data relation keys."""
        return await self.find_rows_by_keys(
            tenant_id,
            entity_type=entity_type,
            lookups={lookup_key: values},
        )
