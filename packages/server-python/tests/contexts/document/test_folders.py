"""Tests for document folder endpoints."""

import pytest

pytestmark = pytest.mark.asyncio


async def test_create_folder(client, auth_headers):
    resp = await client.post(
        "/api/v1/document/folders",
        json={"name": "测试文件夹"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "测试文件夹"
    assert data["parent_id"] is None
    return data["id"]


async def test_list_folders(client, auth_headers):
    await client.post(
        "/api/v1/document/folders",
        json={"name": "文件夹A"},
        headers=auth_headers,
    )
    resp = await client.get("/api/v1/document/folders", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1


async def test_create_subfolder(client, auth_headers):
    parent = await client.post(
        "/api/v1/document/folders",
        json={"name": "父文件夹"},
        headers=auth_headers,
    )
    parent_id = parent.json()["id"]

    resp = await client.post(
        "/api/v1/document/folders",
        json={"name": "子文件夹", "parent_id": parent_id},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["parent_id"] == parent_id


async def test_update_folder(client, auth_headers):
    folder = await client.post(
        "/api/v1/document/folders",
        json={"name": "原名"},
        headers=auth_headers,
    )
    folder_id = folder.json()["id"]

    resp = await client.patch(
        f"/api/v1/document/folders/{folder_id}",
        json={"name": "新名"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "新名"


async def test_move_folder(client, auth_headers):
    folder = await client.post(
        "/api/v1/document/folders",
        json={"name": "移动目标"},
        headers=auth_headers,
    )
    folder_id = folder.json()["id"]

    target = await client.post(
        "/api/v1/document/folders",
        json={"name": "新父级"},
        headers=auth_headers,
    )
    target_id = target.json()["id"]

    resp = await client.patch(
        f"/api/v1/document/folders/{folder_id}/move",
        json={"parent_id": target_id},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["parent_id"] == target_id


async def test_delete_empty_folder(client, auth_headers):
    folder = await client.post(
        "/api/v1/document/folders",
        json={"name": "待删除"},
        headers=auth_headers,
    )
    folder_id = folder.json()["id"]

    resp = await client.delete(
        f"/api/v1/document/folders/{folder_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 204
