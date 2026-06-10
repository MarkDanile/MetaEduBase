"""REQ-002-4: template maintainability integration tests.

Covers schema_version evolution (AC-2 ~ AC-8), deprecation (AC-9 ~ AC-11),
field-naming validation (AC-12 ~ AC-14), and clone/import integration
(AC-15).
"""
import pytest
from httpx import AsyncClient

# ─── Helpers ────────────────────────────────────────────────────────────────


async def _create_template(client: AsyncClient, auth_headers: dict, **overrides) -> dict:
    """Create a template and return JSON body with default fields."""
    payload = {
        "name": "可维护性测试模板",
        "doc_types": ["教案"],
        "fields": [
            {"key": "course_name", "label": "课程名称", "type": "text"},
            {"key": "objectives", "label": "教学目标", "type": "textarea"},
        ],
    }
    payload.update(overrides)
    res = await client.post("/api/v1/templates", json=payload, headers=auth_headers)
    assert res.status_code == 201, f"create failed: {res.status_code} {res.text}"
    return res.json()


async def _update(client: AsyncClient, auth_headers: dict, template_id: str, **body):
    return await client.put(
        f"/api/v1/templates/{template_id}", json=body, headers=auth_headers
    )


# ─── AC-2 / AC-3 / AC-4: schema_version non-bump cases ─────────────────────


@pytest.mark.asyncio
async def test_schema_version_no_bump_leaf_type_change(
    client: AsyncClient, auth_headers: dict
):
    """AC-2: text ⇄ textarea ⇄ number is non-destructive; schema_version unchanged."""
    t = await _create_template(client, auth_headers)

    res = await _update(
        client, auth_headers, t["id"],
        fields=[
            {"key": "course_name", "label": "课程名称", "type": "textarea"},
            {"key": "objectives", "label": "教学目标", "type": "number"},
        ],
    )
    assert res.status_code == 200
    assert res.json()["schema_version"] == 1

    # Snapshot also records the unchanged schema_version
    res = await client.get(
        f"/api/v1/templates/{t['id']}/versions?limit=5", headers=auth_headers
    )
    assert all(v["schema_version"] == 1 for v in res.json())


@pytest.mark.asyncio
async def test_schema_version_no_bump_add_field(
    client: AsyncClient, auth_headers: dict
):
    """AC-3: adding a new field does not bump schema_version."""
    t = await _create_template(client, auth_headers)

    res = await _update(
        client, auth_headers, t["id"],
        fields=[
            {"key": "course_name", "label": "课程名称", "type": "text"},
            {"key": "objectives", "label": "教学目标", "type": "textarea"},
            {"key": "duration_minutes", "label": "课时", "type": "number"},
        ],
    )
    assert res.status_code == 200
    assert res.json()["schema_version"] == 1


@pytest.mark.asyncio
async def test_schema_version_no_bump_drag_reorder(
    client: AsyncClient, auth_headers: dict
):
    """AC-4: drag-reorder (same fields, new order) does not bump schema_version.

    Reorder-only is treated as non-destructive because the destructive
    detection flattens fields by path (order-insensitive).
    """
    t = await _create_template(
        client, auth_headers,
        fields=[
            {"key": "course_name", "label": "课程名称", "type": "text"},
            {"key": "objectives", "label": "教学目标", "type": "textarea"},
        ],
    )

    res = await _update(
        client, auth_headers, t["id"],
        fields=[
            # Reversed order
            {"key": "objectives", "label": "教学目标", "type": "textarea"},
            {"key": "course_name", "label": "课程名称", "type": "text"},
        ],
    )
    assert res.status_code == 200
    assert res.json()["schema_version"] == 1


# ─── AC-5 / AC-6 / AC-7: schema_version bump cases ─────────────────────────


@pytest.mark.asyncio
async def test_schema_version_bump_container_mutual_conversion(
    client: AsyncClient, auth_headers: dict
):
    """AC-5: object ⇄ table ⇄ array mutual conversion bumps schema_version."""
    t = await _create_template(
        client, auth_headers,
        fields=[
            {"key": "course_name", "label": "课程名称", "type": "text"},
            {
                "key": "objectives",
                "label": "教学目标",
                "type": "object",
                "children": [
                    {"key": "desc", "label": "目标描述", "type": "text"},
                ],
            },
        ],
    )

    res = await _update(
        client, auth_headers, t["id"],
        fields=[
            {"key": "course_name", "label": "课程名称", "type": "text"},
            {
                "key": "objectives",
                "label": "教学目标",
                "type": "array",
                "items": [
                    {"key": "desc", "label": "目标描述", "type": "text"},
                ],
            },
        ],
    )
    assert res.status_code == 200
    assert res.json()["schema_version"] == 2


@pytest.mark.asyncio
async def test_schema_version_bump_delete_field(
    client: AsyncClient, auth_headers: dict
):
    """AC-6: deleting a field bumps schema_version."""
    t = await _create_template(client, auth_headers)

    res = await _update(
        client, auth_headers, t["id"],
        fields=[
            {"key": "course_name", "label": "课程名称", "type": "text"},
        ],
    )
    assert res.status_code == 200
    assert res.json()["schema_version"] == 2


@pytest.mark.asyncio
async def test_schema_version_bump_rename_key(
    client: AsyncClient, auth_headers: dict
):
    """AC-7: renaming a leaf key bumps schema_version."""
    t = await _create_template(client, auth_headers)

    res = await _update(
        client, auth_headers, t["id"],
        fields=[
            {"key": "course_name_v2", "label": "课程名称", "type": "text"},
            {"key": "objectives", "label": "教学目标", "type": "textarea"},
        ],
    )
    assert res.status_code == 200
    assert res.json()["schema_version"] == 2


# ─── AC-8: force_schema_bump override ─────────────────────────────────────


@pytest.mark.asyncio
async def test_force_schema_bump_overrides_non_destructive(
    client: AsyncClient, auth_headers: dict
):
    """AC-8: force_schema_bump=true on a non-destructive edit still bumps."""
    t = await _create_template(client, auth_headers)

    res = await _update(
        client, auth_headers, t["id"],
        fields=[
            {"key": "course_name", "label": "课程名称", "type": "text"},
            {"key": "objectives", "label": "教学目标", "type": "textarea"},
        ],
        force_schema_bump=True,
    )
    assert res.status_code == 200
    assert res.json()["schema_version"] == 2


# ─── AC-9 ~ AC-11: deprecation lifecycle ──────────────────────────────────


@pytest.mark.asyncio
async def test_deprecate_marks_template_and_writes_snapshot(
    client: AsyncClient, auth_headers: dict
):
    """AC-9: deprecate sets is_deprecated=true + writes a version snapshot."""
    t = await _create_template(client, auth_headers)

    res = await client.post(
        f"/api/v1/templates/{t['id']}/deprecate",
        json={"reason": "被新模板替代"},
        headers=auth_headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["is_deprecated"] is True
    assert body["deprecated_reason"] == "被新模板替代"
    assert body["deprecated_at"] is not None

    # A version snapshot is written
    res = await client.get(
        f"/api/v1/templates/{t['id']}/versions?limit=5", headers=auth_headers
    )
    assert res.status_code == 200
    assert len(res.json()) >= 1


@pytest.mark.asyncio
async def test_deprecated_template_excluded_from_default_list(
    client: AsyncClient, auth_headers: dict
):
    """AC-9 + list: include_deprecated=false hides deprecated templates."""
    t = await _create_template(client, auth_headers)

    # Deprecate it
    res = await client.post(
        f"/api/v1/templates/{t['id']}/deprecate",
        json={"reason": "测试"},
        headers=auth_headers,
    )
    assert res.status_code == 200

    # Default list: excluded
    res = await client.get("/api/v1/templates", headers=auth_headers)
    assert res.status_code == 200
    assert all(item["id"] != t["id"] for item in res.json())

    # include_deprecated=true: included
    res = await client.get(
        "/api/v1/templates?include_deprecated=true", headers=auth_headers
    )
    assert res.status_code == 200
    assert any(item["id"] == t["id"] for item in res.json())


@pytest.mark.asyncio
async def test_undeprecate_clears_flags_and_writes_snapshot(
    client: AsyncClient, auth_headers: dict
):
    """AC-11: undeprecate clears the deprecation fields and writes a snapshot."""
    t = await _create_template(client, auth_headers)
    await client.post(
        f"/api/v1/templates/{t['id']}/deprecate",
        json={"reason": "临时"},
        headers=auth_headers,
    )

    res = await client.post(
        f"/api/v1/templates/{t['id']}/undeprecate", headers=auth_headers
    )
    assert res.status_code == 200
    body = res.json()
    assert body["is_deprecated"] is False
    assert body["deprecated_at"] is None
    assert body["deprecated_reason"] is None

    # Snapshot is written (now we have deprecate-snapshot + undeprecate-snapshot)
    res = await client.get(
        f"/api/v1/templates/{t['id']}/versions?limit=10", headers=auth_headers
    )
    assert len(res.json()) >= 2


# ─── AC-12 / AC-13 / AC-14: field naming validation ────────────────────────


@pytest.mark.asyncio
async def test_validate_rejects_invalid_key_pattern(
    client: AsyncClient, auth_headers: dict
):
    """AC-12: create rejects field.key that fails ^[a-z][a-z0-9_]*$ (422)."""
    res = await client.post(
        "/api/v1/templates",
        json={
            "name": "非法键名",
            "doc_types": ["教案"],
            "fields": [{"key": "Invalid-Key", "label": "坏键", "type": "text"}],
        },
        headers=auth_headers,
    )
    assert res.status_code == 422
    assert "Invalid-Key" in res.json()["detail"]


@pytest.mark.asyncio
async def test_validate_rejects_duplicate_sibling_key(
    client: AsyncClient, auth_headers: dict
):
    """AC-13: sibling field keys must be unique (422)."""
    res = await client.post(
        "/api/v1/templates",
        json={
            "name": "重复键",
            "doc_types": ["教案"],
            "fields": [
                {"key": "course_name", "label": "课程1", "type": "text"},
                {"key": "course_name", "label": "课程2", "type": "text"},
            ],
        },
        headers=auth_headers,
    )
    assert res.status_code == 422
    assert "duplicate" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_validate_rejects_reserved_meta_key(
    client: AsyncClient, auth_headers: dict
):
    """AC-14: field.key must not collide with REQ-002-3 reserved meta keys (422)."""
    for reserved in ("id", "version", "layer", "matched_type", "confidence", "reason"):
        res = await client.post(
            "/api/v1/templates",
            json={
                "name": f"保留键-{reserved}",
                "doc_types": ["教案"],
                "fields": [{"key": reserved, "label": "保留", "type": "text"}],
            },
            headers=auth_headers,
        )
        assert res.status_code == 422, f"{reserved} should be rejected"
        assert "reserved" in res.json()["detail"].lower()


# ─── AC-15: clone / import integration ────────────────────────────────────


@pytest.mark.asyncio
async def test_clone_inherits_validation(
    client: AsyncClient, auth_headers: dict
):
    """AC-15: clone is gated by _validate_fields; a template with reserved
    keys cannot be created (so clone of such a template is impossible).

    The actual inheritance behaviour is exercised through the service
    path — we verify the success path here (clone of a valid template
    produces a new template with schema_version=1).
    """
    t = await _create_template(client, auth_headers)
    res = await client.post(
        f"/api/v1/templates/{t['id']}/clone",
        json={"name": "克隆品", "doc_types": ["教案"]},
        headers=auth_headers,
    )
    assert res.status_code == 201
    cloned = res.json()
    assert cloned["schema_version"] == 1
    assert cloned["is_deprecated"] is False


@pytest.mark.asyncio
async def test_import_rejects_reserved_key_payload(
    client: AsyncClient, auth_headers: dict
):
    """AC-15: import also runs _validate_fields; reserved keys → 422."""
    res = await client.post(
        "/api/v1/templates/import",
        json={
            "template": {
                "name": "非法导入",
                "doc_types": ["教案"],
                "fields": [{"key": "id", "label": "保留", "type": "text"}],
            }
        },
        headers=auth_headers,
    )
    assert res.status_code == 422
    assert "reserved" in res.json()["detail"].lower()


# ─── AC-22 / AC-23: REQ-002-2 + REQ-002-3 compatibility ─────────────────────


@pytest.mark.asyncio
async def test_update_writes_schema_version_into_snapshot(
    client: AsyncClient, auth_headers: dict
):
    """AC-22/23: bumping schema_version on update is reflected in snapshot."""
    t = await _create_template(client, auth_headers)
    # Bump: delete a field
    await _update(
        client, auth_headers, t["id"],
        fields=[{"key": "course_name", "label": "课程名称", "type": "text"}],
    )

    res = await client.get(
        f"/api/v1/templates/{t['id']}/versions?limit=5", headers=auth_headers
    )
    assert res.status_code == 200
    versions = res.json()
    # Newest snapshot (destructive delete) has schema_version=2
    assert versions[0]["schema_version"] == 2
