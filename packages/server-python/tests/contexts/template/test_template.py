"""Template API integration tests."""
from uuid import uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_templates_empty(client: AsyncClient, auth_headers: dict):
    """List templates when none exist returns empty list."""
    res = await client.get("/api/v1/templates", headers=auth_headers)
    assert res.status_code == 200
    assert res.json() == []


@pytest.mark.asyncio
async def test_create_and_list_template(client: AsyncClient, auth_headers: dict):
    """Create a template and list it."""
    payload = {
        "name": "教案模板",
        "doc_types": ["教案"],
        "fields": [
            {"key": "course_name", "label": "课程名称", "type": "text"},
            {"key": "objectives", "label": "教学目标", "type": "textarea"},
        ],
    }
    res = await client.post("/api/v1/templates", json=payload, headers=auth_headers)
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "教案模板"
    assert data["doc_types"] == ["教案"]
    assert len(data["fields"]) == 2

    # List templates
    res = await client.get("/api/v1/templates", headers=auth_headers)
    assert res.status_code == 200
    assert len(res.json()) == 1


@pytest.mark.asyncio
async def test_get_template(client: AsyncClient, auth_headers: dict):
    """Get a specific template by ID."""
    payload = {
        "name": "测试模板",
        "doc_types": ["试卷"],
        "fields": [{"key": "title", "label": "标题", "type": "text"}],
    }
    res = await client.post("/api/v1/templates", json=payload, headers=auth_headers)
    template_id = res.json()["id"]

    res = await client.get(f"/api/v1/templates/{template_id}", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["name"] == "测试模板"


@pytest.mark.asyncio
async def test_get_template_not_found(client: AsyncClient, auth_headers: dict):
    """Get non-existent template returns 404."""
    fake_id = str(uuid4())
    res = await client.get(f"/api/v1/templates/{fake_id}", headers=auth_headers)
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_update_template(client: AsyncClient, auth_headers: dict):
    """Update an existing template."""
    payload = {
        "name": "原始名称",
        "doc_types": ["教案"],
        "fields": [{"key": "k1", "label": "字段1", "type": "text"}],
    }
    res = await client.post("/api/v1/templates", json=payload, headers=auth_headers)
    template_id = res.json()["id"]

    res = await client.put(
        f"/api/v1/templates/{template_id}",
        json={"name": "新名称", "doc_types": ["课件"]},
        headers=auth_headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "新名称"
    assert data["doc_types"] == ["课件"]
    # fields should be unchanged
    assert data["fields"][0]["key"] == "k1"


@pytest.mark.asyncio
async def test_delete_template(client: AsyncClient, auth_headers: dict):
    """Delete a template."""
    payload = {
        "name": "待删除模板",
        "doc_types": ["教案"],
        "fields": [],
    }
    res = await client.post("/api/v1/templates", json=payload, headers=auth_headers)
    template_id = res.json()["id"]

    res = await client.delete(f"/api/v1/templates/{template_id}", headers=auth_headers)
    assert res.status_code == 204

    # Verify deleted
    res = await client.get(f"/api/v1/templates/{template_id}", headers=auth_headers)
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_check_doc_type_used(client: AsyncClient, auth_headers: dict):
    """Check if a doc type is already used by a template."""
    payload = {
        "name": "教案模板",
        "doc_types": ["教案"],
        "fields": [],
    }
    await client.post("/api/v1/templates", json=payload, headers=auth_headers)

    res = await client.get("/api/v1/templates/check-doc-type?doc_type=教案", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data["used"] is True
    assert len(data["templates"]) == 1

    res = await client.get("/api/v1/templates/check-doc-type?doc_type=课件", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["used"] is False


@pytest.mark.asyncio
async def test_template_requires_auth(client: AsyncClient):
    """Template endpoints require authentication."""
    res = await client.get("/api/v1/templates")
    assert res.status_code in (401, 403)


@pytest.mark.asyncio
async def test_nested_fields(client: AsyncClient, auth_headers: dict):
    """Templates with nested object/array/table fields are stored correctly."""
    payload = {
        "name": "复杂模板",
        "doc_types": ["教案"],
        "fields": [
            {
                "key": "info",
                "label": "基本信息",
                "type": "object",
                "children": [
                    {"key": "name", "label": "名称", "type": "text"},
                    {"key": "desc", "label": "描述", "type": "textarea"},
                ],
            },
            {
                "key": "schedule",
                "label": "课程表",
                "type": "table",
                "columns": [
                    {"key": "time", "label": "时间", "type": "text"},
                    {"key": "activity", "label": "活动", "type": "textarea"},
                ],
            },
        ],
    }
    res = await client.post("/api/v1/templates", json=payload, headers=auth_headers)
    assert res.status_code == 201
    data = res.json()

    # Verify nested structure preserved
    info_field = next(f for f in data["fields"] if f["key"] == "info")
    assert info_field["type"] == "object"
    assert len(info_field["children"]) == 2

    schedule_field = next(f for f in data["fields"] if f["key"] == "schedule")
    assert schedule_field["type"] == "table"
    assert len(schedule_field["columns"]) == 2
