import io
import uuid

import pytest
from httpx import AsyncClient

RES_URL = "/api/v1/resources"


@pytest.mark.asyncio
async def test_upload_resource(client: AsyncClient, auth_headers: dict):
    file_content = b"Hello, this is a test file for MetaEduBase resource upload."
    files = {"file": ("test_document.txt", io.BytesIO(file_content), "text/plain")}
    data = {
        "title": "测试文档",
        "resource_type": "document",
        "domain": "electronics_info",
        "description": "测试上传",
    }

    resp = await client.post(
        f"{RES_URL}/upload",
        headers=auth_headers,
        files=files,
        data=data,
    )
    assert resp.status_code == 201
    result = resp.json()
    assert result["title"] == "测试文档"
    assert result["resource_type"] == "document"
    assert result["file_size"] == len(file_content)
    assert result["file_type"] == "txt"
    return result["id"]


@pytest.mark.asyncio
async def test_upload_without_auth(client: AsyncClient):
    files = {"file": ("unauth.txt", io.BytesIO(b"unauth"), "text/plain")}
    data = {"title": "未授权上传"}
    resp = await client.post(f"{RES_URL}/upload", files=files, data=data)
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_list_resources(client: AsyncClient, auth_headers: dict):
    file_content = b"List test file content"
    files = {"file": ("list_test.txt", io.BytesIO(file_content), "text/plain")}
    data = {"title": "列表测试资源", "resource_type": "document"}

    await client.post(f"{RES_URL}/upload", headers=auth_headers, files=files, data=data)

    resp = await client.get(f"{RES_URL}/", headers=auth_headers)
    assert resp.status_code == 200
    result = resp.json()
    assert "total" in result
    assert "items" in result
    assert result["total"] >= 1


@pytest.mark.asyncio
async def test_list_resources_with_filters(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        f"{RES_URL}/",
        headers=auth_headers,
        params={"resource_type": "document", "limit": 10, "offset": 0},
    )
    assert resp.status_code == 200
    result = resp.json()
    for item in result["items"]:
        assert item["resource_type"] == "document"


@pytest.mark.asyncio
async def test_get_resource(client: AsyncClient, auth_headers: dict):
    file_content = b"Get resource test"
    files = {"file": ("get_test.txt", io.BytesIO(file_content), "text/plain")}
    data = {"title": "获取测试资源", "resource_type": "document"}

    upload_resp = await client.post(f"{RES_URL}/upload", headers=auth_headers, files=files, data=data)
    resource_id = upload_resp.json()["id"]

    resp = await client.get(f"{RES_URL}/{resource_id}", headers=auth_headers)
    assert resp.status_code == 200
    result = resp.json()
    assert result["title"] == "获取测试资源"
    assert result["id"] == resource_id


@pytest.mark.asyncio
async def test_get_resource_not_found(client: AsyncClient, auth_headers: dict):
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"{RES_URL}/{fake_id}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_download_resource(client: AsyncClient, auth_headers: dict):
    file_content = b"Download test content for MetaEduBase"
    files = {"file": ("download_test.txt", io.BytesIO(file_content), "text/plain")}
    data = {"title": "下载测试资源", "resource_type": "document"}

    upload_resp = await client.post(f"{RES_URL}/upload", headers=auth_headers, files=files, data=data)
    resource_id = upload_resp.json()["id"]

    resp = await client.get(f"{RES_URL}/{resource_id}/download", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.content == file_content


@pytest.mark.asyncio
async def test_download_not_found(client: AsyncClient, auth_headers: dict):
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"{RES_URL}/{fake_id}/download", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_resource(client: AsyncClient, auth_headers: dict):
    file_content = b"Delete test"
    files = {"file": ("delete_test.txt", io.BytesIO(file_content), "text/plain")}
    data = {"title": "待删除资源", "resource_type": "document"}

    upload_resp = await client.post(f"{RES_URL}/upload", headers=auth_headers, files=files, data=data)
    resource_id = upload_resp.json()["id"]

    resp = await client.delete(f"{RES_URL}/{resource_id}", headers=auth_headers)
    assert resp.status_code == 204

    get_resp = await client.get(f"{RES_URL}/{resource_id}", headers=auth_headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_already_deleted(client: AsyncClient, auth_headers: dict):
    file_content = b"Double delete"
    files = {"file": ("dbl_del.txt", io.BytesIO(file_content), "text/plain")}
    data = {"title": "二次删除资源", "resource_type": "document"}

    upload_resp = await client.post(f"{RES_URL}/upload", headers=auth_headers, files=files, data=data)
    resource_id = upload_resp.json()["id"]

    await client.delete(f"{RES_URL}/{resource_id}", headers=auth_headers)

    resp = await client.delete(f"{RES_URL}/{resource_id}", headers=auth_headers)
    assert resp.status_code == 404
