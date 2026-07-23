"""Regression tests: cascade cleanup deletes knowledge edges before nodes.

TD-002 requires that file/dataset deletion and re-initialization share the same
cleanup logic, and that knowledge edges referencing file-derived nodes are cleaned
before the nodes themselves (RESTRICT FK constraint).
"""

import io
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.shared.infrastructure.seed import DEFAULT_TENANT_ID
from tests.conftest import TEST_DB_URL

pytestmark = pytest.mark.asyncio

_DEFAULT_TENANT = DEFAULT_TENANT_ID  # already a uuid.UUID


def _test_engine():
    return create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)


async def _get_education_catalog_id(client, auth_headers) -> str:
    """Fetch the seeded ``education`` catalog id for upload tests.

    The education catalog is seeded by alembic 018 for every tenant.
    REQ-054 made catalog_id + entity_type required for dataset upload.
    """
    resp = await client.get("/api/v1/catalogs", headers=auth_headers)
    assert resp.status_code == 200
    for c in resp.json():
        if c["code"] == "education":
            return c["id"]
    raise AssertionError("education catalog not seeded - run alembic 018")


async def _insert_kg_for_file(
    file_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Insert two knowledge nodes + one edge linked to a file.

    Returns (node_a, node_b, edge_id).
    """
    engine = _test_engine()
    factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        node_a = uuid.uuid4()
        node_b = uuid.uuid4()
        edge_id = uuid.uuid4()
        now = datetime.now(UTC).replace(tzinfo=None)

        for nid, title in [(node_a, "Node A"), (node_b, "Node B")]:
            await session.execute(
                text(
                    "INSERT INTO metaedu.knowledge_nodes "
                    "(id, tenant_id, title, domain, level, "
                    "source_file_id, tags, metadata, "
                    "created_at, updated_at) "
                    "VALUES (:id, :tid, :title, 'test', 'concept', "
                    ":fid, '[]'::jsonb, '{}'::jsonb, :now, :now)"
                ),
                {
                    "id": nid, "tid": tenant_id,
                    "title": title, "fid": file_id, "now": now,
                },
            )

        await session.execute(
            text(
                "INSERT INTO metaedu.knowledge_edges "
                "(id, tenant_id, source_id, target_id, "
                "relation_type, weight, metadata, created_at) "
                "VALUES (:id, :tid, :src, :tgt, 'related', "
                "1.0, '{}'::jsonb, :now)"
            ),
            {
                "id": edge_id, "tid": tenant_id,
                "src": node_a, "tgt": node_b, "now": now,
            },
        )
        await session.commit()
    await engine.dispose()
    return node_a, node_b, edge_id


async def _insert_kg_for_dataset(
    dataset_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Insert two knowledge nodes + one edge linked to a dataset.

    Returns (node_a, node_b, edge_id).
    """
    engine = _test_engine()
    factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        node_a = uuid.uuid4()
        node_b = uuid.uuid4()
        edge_id = uuid.uuid4()
        now = datetime.now(UTC).replace(tzinfo=None)

        for nid, title in [(node_a, "DS Node A"), (node_b, "DS Node B")]:
            await session.execute(
                text(
                    "INSERT INTO metaedu.knowledge_nodes "
                    "(id, tenant_id, title, domain, level, "
                    "source_dataset_id, tags, metadata, "
                    "created_at, updated_at) "
                    "VALUES (:id, :tid, :title, 'test', 'concept', "
                    ":did, '[]'::jsonb, '{}'::jsonb, :now, :now)"
                ),
                {
                    "id": nid, "tid": tenant_id,
                    "title": title, "did": dataset_id, "now": now,
                },
            )

        await session.execute(
            text(
                "INSERT INTO metaedu.knowledge_edges "
                "(id, tenant_id, source_id, target_id, "
                "relation_type, weight, metadata, created_at) "
                "VALUES (:id, :tid, :src, :tgt, 'related', "
                "1.0, '{}'::jsonb, :now)"
            ),
            {
                "id": edge_id, "tid": tenant_id,
                "src": node_a, "tgt": node_b, "now": now,
            },
        )
        await session.commit()
    await engine.dispose()
    return node_a, node_b, edge_id


async def _assert_kg_cleaned(
    *,
    file_id: uuid.UUID | None = None,
    dataset_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
) -> None:
    """Assert all knowledge edges and nodes for the given source are gone."""
    if tenant_id is None:
        tenant_id = _DEFAULT_TENANT
    engine = _test_engine()
    factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        if file_id:
            edge_count = await session.execute(
                text(
                    "SELECT COUNT(*) FROM metaedu.knowledge_edges e "
                    "JOIN metaedu.knowledge_nodes n1 ON e.source_id = n1.id "
                    "JOIN metaedu.knowledge_nodes n2 ON e.target_id = n2.id "
                    "WHERE e.tenant_id = :tid "
                    "AND (n1.source_file_id = :fid "
                    "OR n2.source_file_id = :fid)"
                ),
                {"tid": tenant_id, "fid": file_id},
            )
            node_count = await session.execute(
                text(
                    "SELECT COUNT(*) FROM metaedu.knowledge_nodes "
                    "WHERE tenant_id = :tid AND source_file_id = :fid"
                ),
                {"tid": tenant_id, "fid": file_id},
            )
        elif dataset_id:
            edge_count = await session.execute(
                text(
                    "SELECT COUNT(*) FROM metaedu.knowledge_edges e "
                    "JOIN metaedu.knowledge_nodes n1 ON e.source_id = n1.id "
                    "JOIN metaedu.knowledge_nodes n2 ON e.target_id = n2.id "
                    "WHERE e.tenant_id = :tid "
                    "AND (n1.source_dataset_id = :did "
                    "OR n2.source_dataset_id = :did)"
                ),
                {"tid": tenant_id, "did": dataset_id},
            )
            node_count = await session.execute(
                text(
                    "SELECT COUNT(*) FROM metaedu.knowledge_nodes "
                    "WHERE tenant_id = :tid AND source_dataset_id = :did"
                ),
                {"tid": tenant_id, "did": dataset_id},
            )
        else:
            raise ValueError("Must provide file_id or dataset_id")

        assert edge_count.scalar() == 0, "Knowledge edges should be deleted"
        assert node_count.scalar() == 0, "Knowledge nodes should be deleted"
    await engine.dispose()


async def test_delete_file_cleans_knowledge_edges_before_nodes(
    client, auth_headers
):
    """When a file is deleted, knowledge_edges referencing its nodes
    must be removed before the nodes themselves (RESTRICT FK)."""
    # 1. Upload a file
    resp = await client.post(
        "/api/v1/document/files/upload",
        files={
            "file": (
                "cascade_test.txt",
                io.BytesIO(b"test content"),
                "text/plain",
            )
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    file_id = uuid.UUID(resp.json()["id"])

    # 2. Insert knowledge nodes + edges linked to that file
    await _insert_kg_for_file(file_id, _DEFAULT_TENANT)

    # 3. Delete — if edges aren't deleted before nodes, FK RESTRICT raises
    resp = await client.delete(
        f"/api/v1/document/files/{file_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 204

    # 4. Verify edges and nodes are gone
    await _assert_kg_cleaned(file_id=file_id)


async def test_reinitialize_file_cleans_knowledge_edges_before_nodes(
    client, auth_headers
):
    """When a file is re-initialized, knowledge_edges referencing its nodes
    must be removed before the nodes themselves (RESTRICT FK)."""
    # 1. Upload a file
    resp = await client.post(
        "/api/v1/document/files/upload",
        files={
            "file": (
                "reinit_test.txt",
                io.BytesIO(b"reinit content"),
                "text/plain",
            )
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    file_id = uuid.UUID(resp.json()["id"])

    # 2. Insert knowledge nodes + edges linked to that file
    await _insert_kg_for_file(file_id, _DEFAULT_TENANT)

    # 3. Reinitialize — if edges aren't deleted first, FK RESTRICT raises
    resp = await client.post(
        f"/api/v1/document/files/{file_id}/reinitialize",
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # 4. Verify edges and nodes are gone
    await _assert_kg_cleaned(file_id=file_id)


async def test_delete_dataset_cleans_knowledge_edges_before_nodes(
    client, auth_headers
):
    """When a dataset is deleted, knowledge_edges referencing its nodes
    must be removed before the nodes themselves (RESTRICT FK).
    Regression test for the bug where delete_dataset skipped edge deletion."""
    # 1. Upload a dataset
    catalog_id = await _get_education_catalog_id(client, auth_headers)
    resp = await client.post(
        "/api/v1/structured-data/datasets/upload",
        files={
            "file": (
                "cascade_ds.csv",
                io.BytesIO(b"col1,col2\na,b"),
                "text/csv",
            )
        },
        data={"catalog_id": catalog_id, "entity_type": "test"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    dataset_id = uuid.UUID(resp.json()["id"])

    # 2. Insert knowledge nodes + edges linked to that dataset
    await _insert_kg_for_dataset(dataset_id, _DEFAULT_TENANT)

    # 3. Delete — if edges aren't deleted before nodes, FK RESTRICT raises
    resp = await client.delete(
        f"/api/v1/structured-data/datasets/{dataset_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 204

    # 4. Verify edges and nodes are gone
    await _assert_kg_cleaned(dataset_id=dataset_id)


async def test_reinitialize_dataset_cleans_knowledge_edges_before_nodes(
    client, auth_headers
):
    """When a dataset is re-initialized, knowledge_edges referencing its
    nodes must be removed before the nodes themselves (RESTRICT FK)."""
    # 1. Upload a dataset
    catalog_id = await _get_education_catalog_id(client, auth_headers)
    resp = await client.post(
        "/api/v1/structured-data/datasets/upload",
        files={
            "file": (
                "reinit_ds.csv",
                io.BytesIO(b"col1,col2\nc,d"),
                "text/csv",
            )
        },
        data={"catalog_id": catalog_id, "entity_type": "test"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    dataset_id = uuid.UUID(resp.json()["id"])

    # 2. Insert knowledge nodes + edges linked to that dataset
    await _insert_kg_for_dataset(dataset_id, _DEFAULT_TENANT)

    # 3. Reinitialize — if edges aren't deleted first, FK RESTRICT raises
    resp = await client.post(
        f"/api/v1/structured-data/datasets/{dataset_id}/reinitialize",
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # 4. Verify edges and nodes are gone
    await _assert_kg_cleaned(dataset_id=dataset_id)
