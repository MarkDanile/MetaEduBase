"""Tests for structured_data dataset endpoints."""

import io

import pytest

pytestmark = pytest.mark.asyncio


async def test_upload_dataset(client, auth_headers):
    resp = await client.post(
        "/api/v1/structured-data/datasets/upload?name=测试数据集",
        files={"file": ("test_data.xlsx", io.BytesIO(b"fake excel"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "测试数据集"
    assert data["status"] == "uploaded"
    return data["id"]


async def test_list_datasets(client, auth_headers):
    await client.post(
        "/api/v1/structured-data/datasets/upload",
        files={"file": ("list_test.xlsx", io.BytesIO(b"content"), "application/octet-stream")},
        headers=auth_headers,
    )
    resp = await client.get("/api/v1/structured-data/datasets", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


async def test_get_dataset_detail(client, auth_headers):
    upload = await client.post(
        "/api/v1/structured-data/datasets/upload",
        files={"file": ("detail.xlsx", io.BytesIO(b"detail"), "application/octet-stream")},
        headers=auth_headers,
    )
    ds_id = upload.json()["id"]

    resp = await client.get(f"/api/v1/structured-data/datasets/{ds_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "detail"


async def test_update_dataset(client, auth_headers):
    upload = await client.post(
        "/api/v1/structured-data/datasets/upload",
        files={"file": ("update.xlsx", io.BytesIO(b"original"), "application/octet-stream")},
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
    upload = await client.post(
        "/api/v1/structured-data/datasets/upload",
        files={"file": ("delete.xlsx", io.BytesIO(b"to delete"), "application/octet-stream")},
        headers=auth_headers,
    )
    ds_id = upload.json()["id"]

    resp = await client.delete(f"/api/v1/structured-data/datasets/{ds_id}", headers=auth_headers)
    assert resp.status_code == 204

    resp = await client.get(f"/api/v1/structured-data/datasets/{ds_id}", headers=auth_headers)
    assert resp.status_code == 404


async def test_dataset_not_found(client, auth_headers):
    import uuid
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/structured-data/datasets/{fake_id}", headers=auth_headers)
    assert resp.status_code == 404


async def test_kg_status(client, auth_headers):
    resp = await client.get("/api/v1/structured-data/knowledge-graph/status", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
