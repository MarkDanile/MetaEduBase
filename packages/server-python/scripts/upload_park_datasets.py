#!/usr/bin/env python3
"""Upload the REQ-046 park XLSX bundle through the governed dataset API.

The script creates/reuses a ``park_operations`` catalog, uploads each workbook
with its declared ``entity_type``, and never reads or prints workbook rows.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import uuid
from pathlib import Path
from urllib import error, request

WORKBOOKS = {
    "01_资产_项目.xlsx": "asset_project",
    "02_资产_楼栋.xlsx": "asset_building",
    "03_资产_楼层.xlsx": "asset_floor",
    "04_资产_房间.xlsx": "asset_room",
    "05_客户.xlsx": "customer",
    "06_合同_基本信息.xlsx": "contract",
    "07_合同_物业位置.xlsx": "contract_property",
    "08_合同_租赁条款价格.xlsx": "lease_term",
    "09_合同_租赁账单.xlsx": "bill",
    "10_流水.xlsx": "payment",
    "11_流水核销账单.xlsx": "payment_allocation",
    "12_物业工单.xlsx": "ticket",
    "13_客户_合作跟进记录_待审核.xlsx": "cooperation_note",
}


def _json_request(
    url: str, token: str, method: str, body: dict | None = None
) -> dict | list[dict]:
    payload = json.dumps(body).encode() if body is not None else None
    req = request.Request(
        url,
        data=payload,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with request.urlopen(req) as response:  # noqa: S310
            return json.loads(response.read() or b"{}")
    except error.HTTPError as exc:
        raise SystemExit(f"HTTP {exc.code}: {exc.read().decode(errors='replace')}") from exc


def _multipart(file_path: Path, catalog_id: str, entity_type: str) -> tuple[bytes, str]:
    boundary = f"metaedu-{uuid.uuid4().hex}"
    mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    chunks: list[bytes] = []
    for name, value in (("catalog_id", catalog_id), ("entity_type", entity_type)):
        chunks.append(
            (
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\""
                f"\r\n\r\n{value}\r\n"
            ).encode()
        )
    chunks.append(
        (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            f"filename=\"{file_path.name}\"\r\nContent-Type: {mime}\r\n\r\n"
        ).encode()
    )
    chunks.append(file_path.read_bytes())
    chunks.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(chunks), boundary


def _upload(
    base_url: str,
    token: str,
    file_path: Path,
    catalog_id: str,
    entity_type: str,
) -> dict:
    body, boundary = _multipart(file_path, catalog_id, entity_type)
    req = request.Request(
        f"{base_url}/api/v1/structured-data/datasets/upload?name={entity_type}",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    try:
        with request.urlopen(req) as response:  # noqa: S310
            return json.loads(response.read())
    except error.HTTPError as exc:
        raise SystemExit(
            f"{file_path.name}: HTTP {exc.code}: {exc.read().decode(errors='replace')}"
        ) from exc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--token-env", default="METAEDU_ADMIN_TOKEN")
    parser.add_argument(
        "--force",
        action="store_true",
        help="upload even when a non-failed dataset with the entity_type exists",
    )
    args = parser.parse_args()

    token = os.environ.get(args.token_env)
    if not token:
        raise SystemExit(f"{args.token_env} is not set")
    missing = [name for name in WORKBOOKS if not (args.directory / name).is_file()]
    if missing:
        raise SystemExit(f"missing workbook(s): {', '.join(missing)}")

    catalogs = _json_request(f"{args.base_url}/api/v1/catalogs", token, "GET")
    if not isinstance(catalogs, list):
        raise SystemExit("catalog list endpoint returned a non-list response")
    catalog = next((item for item in catalogs if item["code"] == "park_operations"), None)
    if catalog is None:
        catalog = _json_request(
            f"{args.base_url}/api/v1/catalogs",
            token,
            "POST",
            {
                "code": "park_operations",
                "name": "园区运营测试数据库",
                "description": "REQ-046 企业 360 背调内部数据",
            },
        )
        if not isinstance(catalog, dict):
            raise SystemExit("catalog create endpoint returned a non-object response")

    existing = _json_request(
        f"{args.base_url}/api/v1/structured-data/datasets?catalog_id={catalog['id']}&limit=100",
        token,
        "GET",
    )
    if not isinstance(existing, list):
        raise SystemExit("dataset list endpoint returned a non-list response")
    existing_entity_types = {
        item.get("entity_type")
        for item in existing
        if item.get("status") in {"uploaded", "processing", "processed"}
    }

    uploaded = []
    for filename, entity_type in WORKBOOKS.items():
        if not args.force and entity_type in existing_entity_types:
            uploaded.append(
                {"filename": filename, "entity_type": entity_type, "status": "skipped"}
            )
            continue
        result = _upload(
            args.base_url,
            token,
            args.directory / filename,
            str(catalog["id"]),
            entity_type,
        )
        uploaded.append(
            {"filename": filename, "entity_type": entity_type, "dataset_id": result["id"]}
        )
    print(
        json.dumps(
            {"catalog_id": catalog["id"], "uploaded": uploaded},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
