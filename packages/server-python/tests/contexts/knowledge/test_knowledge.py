import uuid

import pytest
from httpx import AsyncClient

KBASE_URL = "/api/v1/knowledge"


@pytest.mark.asyncio
async def test_create_node(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        f"{KBASE_URL}/nodes",
        headers=auth_headers,
        json={
            "title": "测试专业节点",
            "description": "这是一个测试描述",
            "domain": "electronics_info",
            "level": "professional",
            "tags": ["测试"],
            "metadata": {"source": "test"},
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "测试专业节点"
    assert data["domain"] == "electronics_info"
    assert data["level"] == "professional"
    assert data["description"] == "这是一个测试描述"
    assert "id" in data
    assert "path" in data
    return data["id"]


@pytest.mark.asyncio
async def test_create_node_without_auth(client: AsyncClient):
    resp = await client.post(
        f"{KBASE_URL}/nodes",
        json={
            "title": "无认证节点",
            "domain": "electronics_info",
            "level": "professional",
        },
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_create_child_node(client: AsyncClient, auth_headers: dict):
    parent_resp = await client.post(
        f"{KBASE_URL}/nodes",
        headers=auth_headers,
        json={"title": "父节点", "domain": "smart_manufacturing", "level": "professional"},
    )
    assert parent_resp.status_code == 201
    parent_id = parent_resp.json()["id"]

    child_resp = await client.post(
        f"{KBASE_URL}/nodes",
        headers=auth_headers,
        json={
            "title": "子课程节点",
            "domain": "smart_manufacturing",
            "level": "course",
            "parent_id": parent_id,
        },
    )
    assert child_resp.status_code == 201
    child_data = child_resp.json()
    assert child_data["parent_id"] == parent_id
    assert parent_id[:8] in child_data["path"]


@pytest.mark.asyncio
async def test_create_node_invalid_parent(client: AsyncClient, auth_headers: dict):
    fake_id = str(uuid.uuid4())
    resp = await client.post(
        f"{KBASE_URL}/nodes",
        headers=auth_headers,
        json={
            "title": "无效父节点",
            "domain": "electronics_info",
            "level": "course",
            "parent_id": fake_id,
        },
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_nodes(client: AsyncClient, auth_headers: dict):
    await client.post(
        f"{KBASE_URL}/nodes",
        headers=auth_headers,
        json={"title": "列表测试节点A", "domain": "finance_commerce", "level": "professional"},
    )
    await client.post(
        f"{KBASE_URL}/nodes",
        headers=auth_headers,
        json={"title": "列表测试节点B", "domain": "finance_commerce", "level": "course"},
    )

    resp = await client.get(
        f"{KBASE_URL}/nodes",
        headers=auth_headers,
        params={"domain": "finance_commerce"},
    )
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)
    assert len(items) >= 2


@pytest.mark.asyncio
async def test_list_nodes_filter_by_domain(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        f"{KBASE_URL}/nodes",
        headers=auth_headers,
        params={"domain": "medical_health"},
    )
    assert resp.status_code == 200
    items = resp.json()
    assert all(n["domain"] == "medical_health" for n in items)


@pytest.mark.asyncio
async def test_get_node(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        f"{KBASE_URL}/nodes",
        headers=auth_headers,
        json={"title": "获取测试节点", "domain": "civil_engineering", "level": "professional"},
    )
    node_id = create_resp.json()["id"]

    resp = await client.get(
        f"{KBASE_URL}/nodes/{node_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "获取测试节点"


@pytest.mark.asyncio
async def test_get_node_not_found(client: AsyncClient, auth_headers: dict):
    fake_id = str(uuid.uuid4())
    resp = await client.get(
        f"{KBASE_URL}/nodes/{fake_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_node(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        f"{KBASE_URL}/nodes",
        headers=auth_headers,
        json={"title": "更新前标题", "domain": "art_design", "level": "professional"},
    )
    node_id = create_resp.json()["id"]

    resp = await client.patch(
        f"{KBASE_URL}/nodes/{node_id}",
        headers=auth_headers,
        json={"title": "更新后标题", "description": "新增描述"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "更新后标题"
    assert data["description"] == "新增描述"


@pytest.mark.asyncio
async def test_update_node_not_found(client: AsyncClient, auth_headers: dict):
    fake_id = str(uuid.uuid4())
    resp = await client.patch(
        f"{KBASE_URL}/nodes/{fake_id}",
        headers=auth_headers,
        json={"title": "不存在"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_node(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        f"{KBASE_URL}/nodes",
        headers=auth_headers,
        json={"title": "待删除节点", "domain": "agriculture", "level": "professional"},
    )
    node_id = create_resp.json()["id"]

    resp = await client.delete(
        f"{KBASE_URL}/nodes/{node_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 204

    get_resp = await client.get(
        f"{KBASE_URL}/nodes/{node_id}",
        headers=auth_headers,
    )
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_node_not_found(client: AsyncClient, auth_headers: dict):
    fake_id = str(uuid.uuid4())
    resp = await client.delete(
        f"{KBASE_URL}/nodes/{fake_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_search_keyword(client: AsyncClient, auth_headers: dict):
    await client.post(
        f"{KBASE_URL}/nodes",
        headers=auth_headers,
        json={
            "title": "汽车检测与维修技术",
            "description": "交通运输类专业",
            "domain": "transportation",
            "level": "professional",
        },
    )

    resp = await client.post(
        f"{KBASE_URL}/search",
        headers=auth_headers,
        json={"query": "汽车", "search_mode": "keyword"},
    )
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) >= 1
    assert any("汽车" in r["node"]["title"] for r in results)


@pytest.mark.asyncio
async def test_search_with_domain_filter(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        f"{KBASE_URL}/search",
        headers=auth_headers,
        json={"query": "测试", "domain": "transportation", "search_mode": "keyword"},
    )
    assert resp.status_code == 200
    results = resp.json()
    for r in results:
        assert r["node"]["domain"] == "transportation"


@pytest.mark.asyncio
async def test_tree_root(client: AsyncClient, auth_headers: dict):
    await client.post(
        f"{KBASE_URL}/nodes",
        headers=auth_headers,
        json={"title": "树根节点", "domain": "public_service", "level": "professional"},
    )

    resp = await client.get(
        f"{KBASE_URL}/tree/root",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)


@pytest.mark.asyncio
async def test_tree_children(client: AsyncClient, auth_headers: dict):
    parent_resp = await client.post(
        f"{KBASE_URL}/nodes",
        headers=auth_headers,
        json={"title": "树结构父", "domain": "education_sports", "level": "professional"},
    )
    parent_id = parent_resp.json()["id"]

    await client.post(
        f"{KBASE_URL}/nodes",
        headers=auth_headers,
        json={
            "title": "树结构子1",
            "domain": "education_sports",
            "level": "course",
            "parent_id": parent_id,
        },
    )

    resp = await client.get(
        f"{KBASE_URL}/tree/{parent_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
