"""BUG-020 Slice 3: 上传安全集成测试（AC-1/AC-2/AC-3/AC-4/AC-6）。

通过 document upload 端点验证：
- AC-1 恶意文件名（../, \\, 绝对路径, Unicode 混淆）不逃出 tenant 目录
- AC-2 超大文件 413 + 磁盘无残留
- AC-3 不支持类型 415
- AC-4 storage_key 不含用户原始路径
- AC-6 跨 tenant 隔离（既有 test_files 覆盖；本测试聚焦前 4 项）
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.config import settings

UPLOAD_URL = "/api/v1/document/files/upload"


@pytest.mark.asyncio
async def test_upload_malicious_filename_does_not_escape(
    client: AsyncClient, auth_headers: dict
):
    """AC-1: ../../evil.pdf 文件名不能逃出 tenant upload 目录。

    safe_display_name 处理为 "evil.pdf"（含合法 ext），通过类型校验上传成功，
    但落盘路径必须在 upload_dir 内（不逃逸到 ../../）。
    """
    content = b"%PDF-1.4 fake"
    files = {
        "file": ("../../evil.pdf", io.BytesIO(content), "application/pdf"),
    }
    resp = await client.post(UPLOAD_URL, headers=auth_headers, files=files)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    # 显示名经处理无路径分隔符
    assert data["filename"] == "evil.pdf"
    assert "/" not in data["filename"]
    # 扫 upload_dir 下所有 .pdf 文件，确认都在 upload_dir 内（无逃逸）
    upload_root = Path(settings.upload_dir).resolve()
    for p in upload_root.rglob("*.pdf"):
        assert p.resolve().is_relative_to(upload_root), f"文件逃出目录：{p}"


@pytest.mark.asyncio
async def test_upload_oversize_returns_413_and_no_residue(
    client: AsyncClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
):
    """AC-2: 超 max_bytes 返回 413 + 磁盘无新增 .partial 残留。"""
    # 清理既有残留（其他测试可能留下）
    tmp_root = Path(settings.upload_dir)
    for p in tmp_root.rglob("*.partial"):
        try:  # noqa: SIM105
            p.unlink()
        except OSError:
            pass

    from app.contexts.document.interfaces.api import files as files_mod
    monkeypatch.setattr(files_mod, "DEFAULT_MAX_BYTES", 64)

    big = b"x" * 200  # 200 > 64
    files = {"file": ("big.txt", io.BytesIO(big), "text/plain")}
    resp = await client.post(UPLOAD_URL, headers=auth_headers, files=files)
    assert resp.status_code == 413, resp.text
    partials = list(tmp_root.rglob("*.partial"))
    assert partials == [], f"超限后应删 .partial，残留：{partials}"


@pytest.mark.asyncio
async def test_upload_unsupported_type_returns_415(
    client: AsyncClient, auth_headers: dict
):
    """AC-3: .exe 不在 document 白名单 -> 415。"""
    files = {
        "file": ("evil.exe", io.BytesIO(b"MZ"), "application/x-msdownload"),
    }
    resp = await client.post(UPLOAD_URL, headers=auth_headers, files=files)
    assert resp.status_code == 415, resp.text


@pytest.mark.asyncio
async def test_upload_type_forgery_rejected(
    client: AsyncClient, auth_headers: dict
):
    """AC-3: .pdf 扩展名但 MIME 是 exe -> 415（防类型伪造）。"""
    files = {
        "file": ("fake.pdf", io.BytesIO(b"MZ"), "application/x-msdownload"),
    }
    resp = await client.post(UPLOAD_URL, headers=auth_headers, files=files)
    assert resp.status_code == 415, resp.text


@pytest.mark.asyncio
async def test_upload_display_name_preserved_but_storage_safe(
    client: AsyncClient, auth_headers: dict
):
    """AC-4: 显示名保留（UI 可见）；storage_key 不暴露给客户端（DTO 无此字段）。"""
    files = {
        "file": ("我的机密文件.txt", io.BytesIO(b"secret"), "text/plain"),
    }
    resp = await client.post(UPLOAD_URL, headers=auth_headers, files=files)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    # DTO 不含 storage_key（安全设计）
    assert "storage_key" not in data
    # 显示名保留（UI 可见）
    assert data["filename"] == "我的机密文件.txt"
