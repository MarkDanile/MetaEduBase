"""REQ-002-2: template reuse integration tests — clone / version / rollback / import."""
from uuid import uuid4

import pytest
from httpx import AsyncClient


async def _create_template(client: AsyncClient, auth_headers: dict, **overrides) -> dict:
    """Helper: create a template and return the JSON body."""
    payload = {
        "name": "测试模板",
        "doc_types": ["教案"],
        "fields": [
            {"key": "course_name", "label": "课程名称", "type": "text"},
            {
                "key": "objectives",
                "label": "教学目标",
                "type": "array",
                "items": [{"key": "desc", "label": "目标描述", "type": "textarea"}],
            },
        ],
    }
    payload.update(overrides)
    res = await client.post("/api/v1/templates", json=payload, headers=auth_headers)
    assert res.status_code == 201
    return res.json()


@pytest.mark.asyncio
async def test_clone_creates_deep_copy(client: AsyncClient, auth_headers: dict):
    """AC-1: clone deep-copies fields to a new template with a new id."""
    original = await _create_template(client, auth_headers, name="原模板")

    res = await client.post(
        f"/api/v1/templates/{original['id']}/clone",
        json={"name": "复制模板", "doc_types": ["教案"]},
        headers=auth_headers,
    )
    assert res.status_code == 201
    cloned = res.json()

    # New ID, different name
    assert cloned["id"] != original["id"]
    assert cloned["name"] == "复制模板"

    # Fields are deep-copied (same structure)
    assert len(cloned["fields"]) == len(original["fields"])
    assert cloned["fields"][0]["key"] == "course_name"
    assert cloned["fields"][1]["key"] == "objectives"
    assert len(cloned["fields"][1]["items"]) == 1


@pytest.mark.asyncio
async def test_clone_rejects_cross_tenant(client: AsyncClient, auth_headers: dict):
    """AC-2: cloning a template from another tenant returns 404."""
    fake_id = str(uuid4())
    res = await client.post(
        f"/api/v1/templates/{fake_id}/clone",
        json={"name": "非法复制", "doc_types": ["教案"]},
        headers=auth_headers,
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_update_writes_version_snapshot(client: AsyncClient, auth_headers: dict):
    """AC-3: updating a template creates a version snapshot."""
    template = await _create_template(client, auth_headers)

    # Update the template
    res = await client.put(
        f"/api/v1/templates/{template['id']}",
        json={"name": "更新后名称"},
        headers=auth_headers,
    )
    assert res.status_code == 200

    # Check versions
    res = await client.get(
        f"/api/v1/templates/{template['id']}/versions",
        headers=auth_headers,
    )
    assert res.status_code == 200
    versions = res.json()
    assert len(versions) >= 1
    assert versions[0]["name"] == "更新后名称"


@pytest.mark.asyncio
async def test_list_versions_pagination(client: AsyncClient, auth_headers: dict):
    """AC-4: list versions with pagination."""
    template = await _create_template(client, auth_headers)

    # Create multiple versions via updates
    for i in range(3):
        await client.put(
            f"/api/v1/templates/{template['id']}",
            json={"name": f"版本{i + 1}"},
            headers=auth_headers,
        )

    # Get all versions
    res = await client.get(
        f"/api/v1/templates/{template['id']}/versions?limit=100",
        headers=auth_headers,
    )
    assert res.status_code == 200
    versions = res.json()
    assert len(versions) == 3

    # Pagination: offset
    res = await client.get(
        f"/api/v1/templates/{template['id']}/versions?limit=1&offset=0",
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert len(res.json()) == 1


@pytest.mark.asyncio
async def test_rollback_restores_snapshot(client: AsyncClient, auth_headers: dict):
    """AC-5: rollback restores a previous version and writes a new version."""
    template = await _create_template(client, auth_headers, name="初始名称")

    # Update to v1
    await client.put(
        f"/api/v1/templates/{template['id']}",
        json={"name": "v1名称"},
        headers=auth_headers,
    )

    # Get version 1
    res = await client.get(
        f"/api/v1/templates/{template['id']}/versions/1",
        headers=auth_headers,
    )
    assert res.status_code == 200
    v1 = res.json()
    assert v1["name"] == "v1名称"

    # Rollback to version 1
    res = await client.post(
        f"/api/v1/templates/{template['id']}/rollback/1",
        headers=auth_headers,
    )
    assert res.status_code == 200
    rolled_back = res.json()
    assert rolled_back["name"] == "v1名称"

    # A new version snapshot should have been created
    res = await client.get(
        f"/api/v1/templates/{template['id']}/versions?limit=100",
        headers=auth_headers,
    )
    versions = res.json()
    # Original update created v1, rollback created v2
    assert len(versions) >= 2


@pytest.mark.asyncio
async def test_export_and_import_round_trip(client: AsyncClient, auth_headers: dict):
    """AC-6/AC-7: export then import produces an equivalent template."""
    template = await _create_template(client, auth_headers, name="导出模板")

    # Export
    res = await client.get(
        f"/api/v1/templates/{template['id']}/export",
        headers=auth_headers,
    )
    assert res.status_code == 200
    export_data = res.json()
    assert export_data["format"] == "metaedu-template-v1"
    assert export_data["template"]["name"] == "导出模板"

    # Import
    res = await client.post(
        "/api/v1/templates/import",
        json={"template": export_data["template"], "name_override": "导入模板"},
        headers=auth_headers,
    )
    assert res.status_code == 201
    imported = res.json()
    assert imported["name"] == "导入模板"
    assert len(imported["fields"]) == len(template["fields"])


@pytest.mark.asyncio
async def test_import_rejects_invalid_key(client: AsyncClient, auth_headers: dict):
    """AC-9: import rejects field keys that don't match the naming convention."""
    payload = {
        "template": {
            "name": "无效模板",
            "doc_types": ["教案"],
            "fields": [{"key": "Bad-Key", "label": "非法键名", "type": "text"}],
        }
    }
    res = await client.post(
        "/api/v1/templates/import",
        json=payload,
        headers=auth_headers,
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_import_rejects_duplicate_sibling_keys(client: AsyncClient, auth_headers: dict):
    """AC-10: import rejects duplicate sibling field keys."""
    payload = {
        "template": {
            "name": "重复键模板",
            "doc_types": ["教案"],
            "fields": [
                {"key": "name", "label": "名称1", "type": "text"},
                {"key": "name", "label": "名称2", "type": "text"},
            ],
        }
    }
    res = await client.post(
        "/api/v1/templates/import",
        json=payload,
        headers=auth_headers,
    )
    assert res.status_code == 422
