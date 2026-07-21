#!/usr/bin/env python3
"""Register and enable the in-process Internal Customer MCP server.

Only credential reference names are sent. The secret value remains in
``INTERNAL_MCP_TOKEN`` and is never read or printed by this script.
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request


def _request(url: str, token: str, method: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request) as response:  # noqa: S310
            payload = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise SystemExit(f"HTTP {exc.code}: {detail}") from exc
    return json.loads(payload) if payload else {}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--server-url", default="http://localhost:8000/internal-mcp")
    parser.add_argument("--token-env", default="METAEDU_ADMIN_TOKEN")
    args = parser.parse_args()

    admin_token = os.environ.get(args.token_env)
    if not admin_token:
        raise SystemExit(f"{args.token_env} is not set")

    payload = {
        "code": "internal_customer",
        "name": "园区内部客户数据 MCP",
        "description": "读取 tenant-scoped 园区 dataset_rows，聚合客户六维事实",
        "transport": "streamable_http",
        "server_url": args.server_url,
        "credential_ref": "INTERNAL_MCP_TOKEN",
        "allowed_roles": ["admin", "data_admin", "super_admin"],
        "timeout_ms": 30000,
    }
    try:
        server = _request(
            f"{args.base_url}/api/v1/mcp-servers", admin_token, "POST", payload
        )
    except SystemExit as exc:
        if not str(exc).startswith("HTTP 409:"):
            raise
        servers = _request(
            f"{args.base_url}/api/v1/mcp-servers", admin_token, "GET"
        )
        server = next(item for item in servers if item["code"] == "internal_customer")
    enabled = _request(
        f"{args.base_url}/api/v1/mcp-servers/{server['id']}/enable?probe=true",
        admin_token,
        "POST",
    )
    print(
        json.dumps(
            {
                "id": enabled["id"],
                "code": enabled["code"],
                "enabled": enabled["enabled"],
                "warning": enabled.get("warning"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
