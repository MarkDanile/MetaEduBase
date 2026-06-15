"""BUG-006 #4: GET /api/v1/knowledge/files/{file_id}/kg-bundle 端点测试.

锁 3 个不变量:
1. 端点存在 + 返 200 + DTO 形态正确
2. edges 的 source_id / target_id 必须都在 nodes 列表中（dangling 过滤）
3. 文件无 KG 节点时返 200 + 空 bundle (不返 404)
"""

from __future__ import annotations

import os
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.shared.infrastructure.seed import DEFAULT_TENANT_ID

KBASE_URL = "/api/v1/knowledge"

DEFAULT_TEST_DB_URL = (
    "postgresql+asyncpg://metaedu:dev_only_123@localhost:5432/metaedu_test"
)
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DB_URL)


async def _insert_node(
    session: AsyncSession,
    *,
    node_id: uuid.UUID,
    title: str,
    source_file_id: uuid.UUID,
) -> None:
    """Insert a knowledge_node directly via SQL (no edge POST API exists)."""
    await session.execute(
        text(
            "INSERT INTO metaedu.knowledge_nodes "
            "(id, tenant_id, title, domain, level, source_file_id, created_at) "
            "VALUES (:id, :tid, :title, 'education_sports', 'knowledge_point', :fid, NOW())"
        ),
        {"id": node_id, "tid": DEFAULT_TENANT_ID, "title": title, "fid": source_file_id},
    )


async def _insert_edge(
    session: AsyncSession,
    *,
    edge_id: uuid.UUID,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
) -> None:
    """Insert a knowledge_edge directly via SQL."""
    await session.execute(
        text(
            "INSERT INTO metaedu.knowledge_edges "
            "(id, tenant_id, source_id, target_id, relation_type, weight, created_at) "
            "VALUES (:id, :tid, :src, :tgt, 'rel', 1.0, NOW())"
        ),
        {"id": edge_id, "tid": DEFAULT_TENANT_ID, "src": source_id, "tgt": target_id},
    )


async def _cleanup(session: AsyncSession, file_ids: list[uuid.UUID]) -> None:
    """Delete nodes (cascades edges) for the test file_ids to keep DB clean."""
    if not file_ids:
        return
    await session.execute(
        text(
            "DELETE FROM metaedu.knowledge_edges "
            "WHERE source_id IN ("
            "  SELECT id FROM metaedu.knowledge_nodes "
            "  WHERE source_file_id = ANY(:fids)"
            ") OR target_id IN ("
            "  SELECT id FROM metaedu.knowledge_nodes "
            "  WHERE source_file_id = ANY(:fids)"
            ")"
        ),
        {"fids": file_ids},
    )
    await session.execute(
        text(
            "DELETE FROM metaedu.knowledge_nodes "
            "WHERE source_file_id = ANY(:fids)"
        ),
        {"fids": file_ids},
    )


async def _make_session() -> tuple[AsyncSession, object]:
    """Open a fresh AsyncSession against TEST_DB_URL."""
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return factory(), engine


@pytest.mark.asyncio
async def test_kg_bundle_returns_nodes_and_edges_for_file(
    client: AsyncClient,
    auth_headers: dict,
) -> None:
    """端点存在, 返 200 + {nodes: [...], edges: [...]} 形态."""
    fid = uuid.uuid4()
    n1 = uuid.uuid4()
    n2 = uuid.uuid4()
    edge_id = uuid.uuid4()

    session, engine = await _make_session()
    try:
        async with session.begin():
            await _insert_node(session, node_id=n1, title="node-A", source_file_id=fid)
            await _insert_node(session, node_id=n2, title="node-B", source_file_id=fid)
            await _insert_edge(session, edge_id=edge_id, source_id=n1, target_id=n2)
    finally:
        await session.close()
        await engine.dispose()

    try:
        resp = await client.get(
            f"{KBASE_URL}/files/{fid}/kg-bundle",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1
        assert {n["title"] for n in data["nodes"]} == {"node-A", "node-B"}
        assert data["edges"][0]["source_id"] == str(n1)
        assert data["edges"][0]["target_id"] == str(n2)
    finally:
        # cleanup
        cleanup_session, cleanup_engine = await _make_session()
        try:
            async with cleanup_session.begin():
                await _cleanup(cleanup_session, [fid])
        finally:
            await cleanup_session.close()
            await cleanup_engine.dispose()


@pytest.mark.asyncio
async def test_kg_bundle_excludes_dangling_edges(
    client: AsyncClient,
    auth_headers: dict,
) -> None:
    """关键不变量: edges 中不能出现 source/target 不在 nodes 列表的 edge.

    复现 BUG-006 #4 真实数据: 跨文件 edge (source 在 file A, target 在 file B)
    旧 list_edges_by_file OR 语义会返回这种边, 新端点必须过滤掉.
    """
    fid_a = uuid.uuid4()
    fid_b = uuid.uuid4()
    node_in_a = uuid.uuid4()
    node_in_b = uuid.uuid4()
    cross_edge_id = uuid.uuid4()

    session, engine = await _make_session()
    try:
        async with session.begin():
            await _insert_node(session, node_id=node_in_a, title="in-A", source_file_id=fid_a)
            await _insert_node(session, node_id=node_in_b, title="in-B", source_file_id=fid_b)
            # 跨文件 edge: source in A, target in B
            await _insert_edge(
                session,
                edge_id=cross_edge_id,
                source_id=node_in_a,
                target_id=node_in_b,
            )
    finally:
        await session.close()
        await engine.dispose()

    try:
        resp = await client.get(
            f"{KBASE_URL}/files/{fid_a}/kg-bundle",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data["nodes"]) == 1
        # 关键断言: 跨文件 edge 不应返回, 因 target 不在 file A 的 nodes 集合中
        assert len(data["edges"]) == 0, (
            f"dangling edge leaked: {data['edges']} "
            f"(target {node_in_b} not in file A's nodes)"
        )
    finally:
        cleanup_session, cleanup_engine = await _make_session()
        try:
            async with cleanup_session.begin():
                await _cleanup(cleanup_session, [fid_a, fid_b])
        finally:
            await cleanup_session.close()
            await cleanup_engine.dispose()


@pytest.mark.asyncio
async def test_kg_bundle_empty_for_file_with_no_kg(
    client: AsyncClient,
    auth_headers: dict,
) -> None:
    """文件存在但还没抽 KG: 返 200 + 空 bundle (不返 404)."""
    fid = uuid.uuid4()  # 不存在 KG 的随机 file_id

    resp = await client.get(
        f"{KBASE_URL}/files/{fid}/kg-bundle",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data == {"nodes": [], "edges": []}
