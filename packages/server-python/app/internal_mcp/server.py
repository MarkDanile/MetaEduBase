"""In-process streamable-HTTP MCP server for internal customer datasets."""
from __future__ import annotations

import secrets
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.internal_mcp.customer_service import InternalCustomerService
from app.shared.infrastructure.database import get_session

router = APIRouter(prefix="/internal-mcp", tags=["internal-customer-mcp"])

_TOOL = {
    "name": "get_customer_360",
    "description": "按已确认企业主体汇总园区内部客户六维事实",
    "inputSchema": {
        "type": "object",
        "required": ["company_name"],
        "properties": {
            "company_name": {"type": "string", "minLength": 1},
            "credit_code": {"type": ["string", "null"]},
        },
        "additionalProperties": False,
    },
}


class JsonRpcRequest(BaseModel):
    jsonrpc: str = Field(pattern=r"^2\.0$")
    id: int | str | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


def _require_auth(authorization: str | None) -> None:
    token = settings.internal_mcp_token
    if not token:
        raise HTTPException(status_code=503, detail="Internal MCP token 未配置")
    expected = f"Bearer {token}".encode()
    provided = (authorization or "").encode()
    if not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Internal MCP 鉴权失败")


def _tenant_id() -> uuid.UUID:
    try:
        return uuid.UUID(settings.internal_mcp_tenant_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=503, detail="INTERNAL_MCP_TENANT_ID 未配置或非法"
        ) from exc


def _result(request_id: int | str | None, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: int | str | None, code: int, message: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


@router.post("")
async def handle_mcp(
    request: JsonRpcRequest,
    response: Response,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),  # noqa: B008
):
    _require_auth(authorization)
    response.headers["Mcp-Session-Id"] = uuid.uuid4().hex

    if request.method == "initialize":
        return _result(
            request.id,
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "metaedu-internal-customer", "version": "1.0"},
            },
        )
    if request.method == "notifications/initialized":
        response.status_code = 204
        return Response(status_code=204)
    if request.method == "tools/list":
        return _result(request.id, {"tools": [_TOOL]})
    if request.method != "tools/call":
        return _error(request.id, -32601, f"Method not found: {request.method}")

    tool_name = request.params.get("name")
    arguments = request.params.get("arguments")
    if tool_name != "get_customer_360":
        return _error(request.id, -32601, f"Tool not found: {tool_name}")
    if not isinstance(arguments, dict):
        return _error(request.id, -32602, "tools/call arguments 必须是 object")
    company_name = arguments.get("company_name")
    credit_code = arguments.get("credit_code")
    if not isinstance(company_name, str) or not company_name.strip():
        return _error(request.id, -32602, "company_name 必须是非空字符串")
    if credit_code is not None and not isinstance(credit_code, str):
        return _error(request.id, -32602, "credit_code 必须是字符串或 null")

    payload = await InternalCustomerService(session).get_customer_360(
        tenant_id=_tenant_id(),
        company_name=company_name.strip(),
        credit_code=credit_code.strip() if isinstance(credit_code, str) else None,
    )
    return _result(
        request.id,
        {
            "content": [
                {
                    "type": "text",
                    "text": "园区内部客户事实已按导入数据集聚合",
                }
            ],
            "structuredContent": payload,
            "isError": False,
        },
    )
