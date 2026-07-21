"""Customer 360 aggregation over governed imported park datasets."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.internal_mcp.customer_repository import InternalCustomerRepository

_DIMENSION_ENTITIES = {
    "contract_history": ("contract",),
    "lease_history": ("contract_property", "lease_term"),
    "payment_history": ("bill", "payment", "payment_allocation"),
    "service_tickets": ("ticket",),
    "cooperation_notes": ("cooperation_note",),
}


def _not_connected(entity_types: tuple[str, ...]) -> dict[str, str]:
    joined = ", ".join(entity_types)
    return {
        "status": "not_connected",
        "note": f"{joined} 数据集未接入或未处理完成",
    }


class InternalCustomerService:
    """Join customer, contract, lease, payment, ticket and follow-up facts."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = InternalCustomerRepository(session)

    async def get_customer_360(
        self,
        *,
        tenant_id: uuid.UUID,
        company_name: str,
        credit_code: str | None = None,
    ) -> dict:
        subject = await self._repo.find_subject(
            tenant_id,
            company_name=company_name,
            credit_code=credit_code,
        )
        if subject is None and credit_code:
            subject = await self._repo.find_subject(
                tenant_id,
                company_name=company_name,
                credit_code=None,
            )
        if subject is None:
            return {
                "source_type": "imported_dataset",
                "subject": {
                    "status": "not_connected",
                    "company_name": company_name,
                    "credit_code": credit_code,
                    "note": "customer 数据集未接入、未处理完成或主体未匹配",
                },
                **{
                    dimension: _not_connected(entity_types)
                    for dimension, entity_types in _DIMENSION_ENTITIES.items()
                },
            }

        customer_ids = {subject.get("客户ID", "")} - {""}
        contracts = await self._repo.find_rows(
            tenant_id,
            entity_type="contract",
            lookup_key="客户ID",
            values=customer_ids,
        )
        contract_ids = {row.get("合同ID", "") for row in contracts} - {""}
        properties = await self._repo.find_rows(
            tenant_id,
            entity_type="contract_property",
            lookup_key="合同ID",
            values=contract_ids,
        )
        room_ids = {row.get("房间ID", "") for row in properties} - {""}
        lease_terms = await self._repo.find_rows(
            tenant_id,
            entity_type="lease_term",
            lookup_key="合同ID",
            values=contract_ids,
        )
        bills = await self._repo.find_rows(
            tenant_id,
            entity_type="bill",
            lookup_key="客户ID",
            values=customer_ids,
        )
        payments = await self._repo.find_rows(
            tenant_id,
            entity_type="payment",
            lookup_key="客户ID",
            values=customer_ids,
        )
        bill_ids = {row.get("账单ID", "") for row in bills} - {""}
        payment_ids = {row.get("流水ID", "") for row in payments} - {""}
        allocations = await self._repo.find_rows_by_keys(
            tenant_id,
            entity_type="payment_allocation",
            lookups={"流水ID": payment_ids, "账单ID": bill_ids},
        )
        project_ids = {
            row.get("项目ID", "") for row in contracts + properties
        } - {""}
        building_ids = {
            row.get("楼栋ID", "") for row in contracts + properties
        } - {""}
        floor_ids = {
            row.get("楼层ID", "") for row in contracts + properties
        } - {""}
        tickets = await self._repo.find_rows_by_keys(
            tenant_id,
            entity_type="ticket",
            lookups={
                "房间ID": room_ids,
                "项目ID": project_ids,
                "楼栋ID": building_ids,
                "楼层ID": floor_ids,
            },
        )
        notes = await self._repo.find_rows(
            tenant_id,
            entity_type="cooperation_note",
            lookup_key="客户ID",
            values=customer_ids,
        )

        rows_by_dimension = {
            "contract_history": self._tag("contract", contracts),
            "lease_history": self._tag("contract_property", properties)
            + self._tag("lease_term", lease_terms),
            "payment_history": self._tag("bill", bills)
            + self._tag("payment", payments)
            + self._tag("payment_allocation", allocations),
            "service_tickets": tickets,
            "cooperation_notes": notes,
        }
        response: dict = {
            "source_type": "imported_dataset",
            "subject": subject,
        }
        for dimension, entity_types in _DIMENSION_ENTITIES.items():
            statuses = [
                await self._repo.has_dataset(tenant_id, entity)
                for entity in entity_types
            ]
            response[dimension] = (
                rows_by_dimension[dimension]
                if all(statuses)
                else _not_connected(entity_types)
            )
        return response

    @staticmethod
    def _tag(record_type: str, rows: list[dict]) -> list[dict]:
        return [{"record_type": record_type, **row} for row in rows]
