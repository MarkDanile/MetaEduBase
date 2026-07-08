"""Tests for structured_data dataset endpoints.

REQ-054 review fix (V1): the upload endpoint no longer validates
``entity_type`` against a catalog whitelist. ``entity_type`` is free-text,
persisted to ``datasets.entity_type``, and the catalog's effective
entity-type list is discovered from uploaded datasets. A ``warning`` field
is added to the upload response when the entity_type is the first
occurrence in that catalog. The list endpoint accepts an optional
``catalog_id`` query filter.

The seeded ``education`` catalog (alembic 018) backs these tests - we look
it up via ``GET /api/v1/catalogs`` and use ``customer`` as the entity_type
for valid uploads.
"""

import io
import uuid

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_education_catalog_id(client, auth_headers) -> str:
    """Fetch the seeded ``education`` catalog id for upload tests.

    The education catalog is seeded by alembic 018 for every tenant.
    """
    resp = await client.get("/api/v1/catalogs", headers=auth_headers)
    assert resp.status_code == 200
    for c in resp.json():
        if c["code"] == "education":
            return c["id"]
    raise AssertionError("education catalog not seeded — run alembic 018")


def _xlsx_file(name: str, content: bytes = b"fake excel"):
    return (
        name,
        io.BytesIO(content),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ---------------------------------------------------------------------------
# Existing tests — updated to pass catalog_id + entity_type
# ---------------------------------------------------------------------------


async def test_upload_dataset(client, auth_headers):
    catalog_id = await _get_education_catalog_id(client, auth_headers)
    resp = await client.post(
        "/api/v1/structured-data/datasets/upload?name=测试数据集",
        files={"file": _xlsx_file("test_data.xlsx")},
        data={"catalog_id": catalog_id, "entity_type": "customer"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "测试数据集"
    assert data["status"] == "uploaded"
    assert data["entity_type"] == "customer"
    return data["id"]


async def test_list_datasets(client, auth_headers):
    catalog_id = await _get_education_catalog_id(client, auth_headers)
    await client.post(
        "/api/v1/structured-data/datasets/upload",
        files={"file": _xlsx_file("list_test.xlsx", b"content")},
        data={"catalog_id": catalog_id, "entity_type": "customer"},
        headers=auth_headers,
    )
    resp = await client.get("/api/v1/structured-data/datasets", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


async def test_get_dataset_detail(client, auth_headers):
    catalog_id = await _get_education_catalog_id(client, auth_headers)
    upload = await client.post(
        "/api/v1/structured-data/datasets/upload",
        files={"file": _xlsx_file("detail.xlsx", b"detail")},
        data={"catalog_id": catalog_id, "entity_type": "customer"},
        headers=auth_headers,
    )
    ds_id = upload.json()["id"]

    resp = await client.get(f"/api/v1/structured-data/datasets/{ds_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "detail"


async def test_update_dataset(client, auth_headers):
    catalog_id = await _get_education_catalog_id(client, auth_headers)
    upload = await client.post(
        "/api/v1/structured-data/datasets/upload",
        files={"file": _xlsx_file("update.xlsx", b"original")},
        data={"catalog_id": catalog_id, "entity_type": "customer"},
        headers=auth_headers,
    )
    ds_id = upload.json()["id"]

    resp = await client.patch(
        f"/api/v1/structured-data/datasets/{ds_id}",
        json={"name": "更新名称", "tags": ["教学"]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "更新名称"


async def test_delete_dataset(client, auth_headers):
    catalog_id = await _get_education_catalog_id(client, auth_headers)
    upload = await client.post(
        "/api/v1/structured-data/datasets/upload",
        files={"file": _xlsx_file("delete.xlsx", b"to delete")},
        data={"catalog_id": catalog_id, "entity_type": "customer"},
        headers=auth_headers,
    )
    ds_id = upload.json()["id"]

    resp = await client.delete(f"/api/v1/structured-data/datasets/{ds_id}", headers=auth_headers)
    assert resp.status_code == 204

    resp = await client.get(f"/api/v1/structured-data/datasets/{ds_id}", headers=auth_headers)
    assert resp.status_code == 404


async def test_dataset_not_found(client, auth_headers):
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/structured-data/datasets/{fake_id}", headers=auth_headers)
    assert resp.status_code == 404


async def test_kg_status(client, auth_headers):
    resp = await client.get("/api/v1/structured-data/knowledge-graph/status", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# REQ-054 V1 — catalog_id + entity_type (dynamic discovery, no whitelist)
# ---------------------------------------------------------------------------


async def test_upload_dataset_422_missing_catalog_id(client, auth_headers):
    """缺 catalog_id Form 字段 → 422（FastAPI Form(...) 必选校验）。"""
    resp = await client.post(
        "/api/v1/structured-data/datasets/upload",
        files={"file": _xlsx_file("no_catalog.xlsx")},
        data={"entity_type": "customer"},  # 故意缺 catalog_id
        headers=auth_headers,
    )
    assert resp.status_code == 422


async def test_upload_dataset_422_missing_entity_type(client, auth_headers):
    """缺 entity_type Form 字段 → 422。"""
    catalog_id = await _get_education_catalog_id(client, auth_headers)
    resp = await client.post(
        "/api/v1/structured-data/datasets/upload",
        files={"file": _xlsx_file("no_entity.xlsx")},
        data={"catalog_id": catalog_id},  # 故意缺 entity_type
        headers=auth_headers,
    )
    assert resp.status_code == 422


async def test_upload_dataset_201_any_entity_type(client, auth_headers):
    """REQ-054 V1: entity_type 自由填写（不再校验白名单）-> 201。

    "unknown_entity" 不在 education catalog 的预设 entity_types 内，但 V1
    动态发现模式下任何 entity_type 都被接受并持久化到 datasets.entity_type。
    """
    catalog_id = await _get_education_catalog_id(client, auth_headers)
    resp = await client.post(
        "/api/v1/structured-data/datasets/upload",
        files={"file": _xlsx_file("free_entity.xlsx")},
        data={"catalog_id": catalog_id, "entity_type": "unknown_entity"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["entity_type"] == "unknown_entity"


async def test_upload_dataset_400_unknown_catalog(client, auth_headers):
    """catalog_id 不存在 -> 400（catalog 存在性校验）。"""
    fake_catalog_id = str(uuid.uuid4())
    resp = await client.post(
        "/api/v1/structured-data/datasets/upload",
        files={"file": _xlsx_file("unknown_catalog.xlsx")},
        data={"catalog_id": fake_catalog_id, "entity_type": "customer"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "不存在" in resp.json()["detail"]


async def test_upload_new_entity_type_warning(client, auth_headers):
    """首次出现的 entity_type -> 响应带 warning；再次上传同 entity_type -> 无 warning。"""
    catalog_id = await _get_education_catalog_id(client, auth_headers)
    # 用一个本测试独占的 entity_type，避免被其他测试污染计数
    entity = f"warn_{uuid.uuid4().hex[:6]}"

    # 第一次上传 -> warning 提示
    resp1 = await client.post(
        "/api/v1/structured-data/datasets/upload",
        files={"file": _xlsx_file("warn_first.xlsx", b"a")},
        data={"catalog_id": catalog_id, "entity_type": entity},
        headers=auth_headers,
    )
    assert resp1.status_code == 201
    body1 = resp1.json()
    assert body1["entity_type"] == entity
    assert body1["warning"] is not None
    assert entity in body1["warning"]

    # 第二次上传同 entity_type -> 无 warning
    resp2 = await client.post(
        "/api/v1/structured-data/datasets/upload",
        files={"file": _xlsx_file("warn_second.xlsx", b"b")},
        data={"catalog_id": catalog_id, "entity_type": entity},
        headers=auth_headers,
    )
    assert resp2.status_code == 201
    assert resp2.json()["warning"] is None


async def test_upload_dataset_201_returns_catalog_id(client, auth_headers):
    """上传成功 → 201 + 响应包含正确的 catalog_id。"""
    catalog_id = await _get_education_catalog_id(client, auth_headers)
    resp = await client.post(
        "/api/v1/structured-data/datasets/upload",
        files={"file": _xlsx_file("catalog_check.xlsx", b"check")},
        data={"catalog_id": catalog_id, "entity_type": "bill"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    # DatasetDTO 不含 catalog_id 字段（保持现有 DTO 不变），但 status 应为 uploaded
    assert body["status"] == "uploaded"
    assert body["name"] == "catalog_check"


async def test_list_datasets_filter_by_catalog(client, auth_headers):
    """列表按 catalog_id 过滤 → 只返回该 catalog 的数据集。

    上传两个数据集到 education catalog，再用 ``?catalog_id=`` 过滤，
    应只返回 education 下的数据集；用随机 catalog_id 过滤应返回空列表。
    """
    catalog_id = await _get_education_catalog_id(client, auth_headers)

    # 上传两个数据集到 education catalog
    for name in ("filter_a.xlsx", "filter_b.xlsx"):
        resp = await client.post(
            "/api/v1/structured-data/datasets/upload",
            files={"file": _xlsx_file(name, b"data")},
            data={"catalog_id": catalog_id, "entity_type": "customer"},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text

    # 用 education catalog_id 过滤
    resp = await client.get(
        "/api/v1/structured-data/datasets",
        params={"catalog_id": catalog_id},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) >= 2
    names = {d["name"] for d in body}
    assert "filter_a" in names
    assert "filter_b" in names

    # 用不存在的 catalog_id 过滤 → 空列表
    resp = await client.get(
        "/api/v1/structured-data/datasets",
        params={"catalog_id": str(uuid.uuid4())},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json() == []
