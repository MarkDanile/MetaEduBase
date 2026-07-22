"""REQ-058 Slice 5: AC-7 真实企业样例在新权限模型下 creator->runner->reviewer 闭环。

验证 REQ-046 既有 e2e 流程在新 RBAC + maker-checker 下仍可跑通：
- leader 创建任务 + run（生成报告）
- admin（不同用户）confirm 报告（maker-checker 通过）
- super_admin 读报告只看 status（AC-5 平台隔离）

用 mock 避免 QCC/LLM 真实调用（与 test_dd_run_router 同模式）。
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.contexts.identity._helpers import register_and_login


def _uname(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


async def _register_park_skill(client: AsyncClient, token: str) -> None:
    """复用 test_dd_run_router 的 V0 skill fixture（含 leader allowed_roles + enable）。"""
    from tests.contexts.due_diligence.test_dd_run_router import _register_park_skill as _reg
    await _reg(client, token)


@pytest.mark.asyncio
async def test_creator_runner_reviewer_closed_loop(client: AsyncClient):
    """AC-7: leader create+run -> admin confirm 闭环在新权限模型下通过。"""
    leader = await register_and_login(client, username=_uname("ac7_leader"), role="leader")
    admin = await register_and_login(client, username=_uname("ac7_admin"), role="admin")
    await _register_park_skill(client, admin)

    # leader 创建任务
    resp = await client.post(
        "/api/v1/dd/tasks",
        json={"title": "AC-7 闭环", "subject_query": "测试企业"},
        headers={"Authorization": f"Bearer {leader}"},
    )
    assert resp.status_code == 201, resp.text
    task_id = resp.json()["id"]

    # leader confirm subject（V0 流程；AC-7 不改 subject confirm 语义）
    resp = await client.post(
        f"/api/v1/dd/tasks/{task_id}/confirm-subject",
        json={"company_name": "测试企业", "credit_code": None},
        headers={"Authorization": f"Bearer {leader}"},
    )
    assert resp.status_code in (200, 201), resp.text

    # leader run（生成报告）
    from tests.contexts.due_diligence.test_dd_run_router import _run_mocks
    inv_patch, report_patch = _run_mocks()
    with inv_patch, report_patch:
        resp = await client.post(
            f"/api/v1/dd/tasks/{task_id}/run",
            headers={"Authorization": f"Bearer {leader}"},
        )
    assert resp.status_code == 201, resp.text
    report_id = resp.json()["id"]

    # leader 不能 confirm 自己的报告（AC-3 maker-checker）
    resp = await client.post(
        f"/api/v1/dd/reports/{report_id}/confirm",
        headers={"Authorization": f"Bearer {leader}"},
    )
    assert resp.status_code == 403, f"leader 不应能 confirm 自己报告，got {resp.status_code}"

    # admin（不同人）confirm（AC-3 checker）
    resp = await client.post(
        f"/api/v1/dd/reports/{report_id}/confirm",
        headers={"Authorization": f"Bearer {admin}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "confirmed"


@pytest.mark.asyncio
async def test_super_admin_reads_status_only(client: AsyncClient):
    """AC-5: super_admin 读报告只看 status，不返 report_json/markdown。"""
    leader = await register_and_login(client, username=_uname("ac7_lead2"), role="leader")
    admin = await register_and_login(client, username=_uname("ac7_adm2"), role="admin")
    super_admin = await register_and_login(
        client, username=_uname("ac7_super"), role="super_admin",
    )
    await _register_park_skill(client, admin)

    resp = await client.post(
        "/api/v1/dd/tasks",
        json={"title": "AC-5 平台隔离", "subject_query": "测试企业"},
        headers={"Authorization": f"Bearer {leader}"},
    )
    task_id = resp.json()["id"]
    await client.post(
        f"/api/v1/dd/tasks/{task_id}/confirm-subject",
        json={"company_name": "测试企业", "credit_code": None},
        headers={"Authorization": f"Bearer {leader}"},
    )
    from tests.contexts.due_diligence.test_dd_run_router import _run_mocks
    inv_patch, report_patch = _run_mocks()
    with inv_patch, report_patch:
        resp = await client.post(
            f"/api/v1/dd/tasks/{task_id}/run",
            headers={"Authorization": f"Bearer {leader}"},
        )
    report_id = resp.json()["id"]

    # super_admin 读报告 -> status only（report_json 空 / markdown 空）
    resp = await client.get(
        f"/api/v1/dd/reports/{report_id}",
        headers={"Authorization": f"Bearer {super_admin}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "status" in body
    assert body["report_json"] == {} or not body["report_json"]
    assert body["report_markdown"] == ""
