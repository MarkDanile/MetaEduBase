"""Tests for document file endpoints."""

import io

import pytest

pytestmark = pytest.mark.asyncio


async def test_upload_file(client, auth_headers):
    content = b"Hello World test content"
    resp = await client.post(
        "/api/v1/document/files/upload",
        files={"file": ("test.txt", io.BytesIO(content), "text/plain")},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["filename"] == "test.txt"
    assert data["file_type"] == "txt"
    assert data["status"] == "uploaded"
    return data["id"]


async def test_list_files(client, auth_headers):
    await client.post(
        "/api/v1/document/files/upload",
        files={"file": ("list_test.txt", io.BytesIO(b"content"), "text/plain")},
        headers=auth_headers,
    )
    resp = await client.get("/api/v1/document/files", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


async def test_get_file_detail(client, auth_headers):
    upload = await client.post(
        "/api/v1/document/files/upload",
        files={"file": ("detail.txt", io.BytesIO(b"detail content"), "text/plain")},
        headers=auth_headers,
    )
    file_id = upload.json()["id"]

    resp = await client.get(f"/api/v1/document/files/{file_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["filename"] == "detail.txt"


async def test_delete_file(client, auth_headers):
    upload = await client.post(
        "/api/v1/document/files/upload",
        files={"file": ("delete.txt", io.BytesIO(b"to delete"), "text/plain")},
        headers=auth_headers,
    )
    file_id = upload.json()["id"]

    resp = await client.delete(f"/api/v1/document/files/{file_id}", headers=auth_headers)
    assert resp.status_code == 204

    resp = await client.get(f"/api/v1/document/files/{file_id}", headers=auth_headers)
    assert resp.status_code == 404


async def test_update_file(client, auth_headers):
    upload = await client.post(
        "/api/v1/document/files/upload",
        files={"file": ("update.txt", io.BytesIO(b"original"), "text/plain")},
        headers=auth_headers,
    )
    file_id = upload.json()["id"]

    resp = await client.patch(
        f"/api/v1/document/files/{file_id}",
        json={"doc_type": "教案", "tags": ["测试"]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["doc_type"] == "教案"


async def test_file_not_found(client, auth_headers):
    import uuid
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/document/files/{fake_id}", headers=auth_headers)
    assert resp.status_code == 404
