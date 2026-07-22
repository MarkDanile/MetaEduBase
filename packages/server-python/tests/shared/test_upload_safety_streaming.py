"""BUG-020 Slice 2: 流式分块上传 + 大小限制 + 类型白名单（AC-2/AC-3）。

- read_chunked_to_tempfile: 累计 > max_bytes 立即终止 + 删临时文件 + 抛 UploadSizeExceeded
- commit_tmpfile: rename .partial -> final；失败清理
- ALLOWED_MATRIX: document/structured_data/resource 三入口的 ext + MIME 白名单
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from app.shared.upload_safety import (
    DEFAULT_MAX_BYTES,
    UploadSafetyError,
    UploadSizeExceeded,
    UploadTypeUnsupported,
    commit_tmpfile,
    read_chunked_to_tempfile,
    validate_upload_type,
)


class _FakeUploadFile:
    """模拟 starlette UploadFile.read(chunk_size) -- 同步 read（async 兼容）。"""

    def __init__(self, data: bytes):
        self._buf = io.BytesIO(data)

    def read(self, size: int = -1) -> bytes:
        return self._buf.read(size)


@pytest.mark.asyncio
async def test_read_chunked_writes_full_file(tmp_path: Path):
    data = b"hello world" * 100
    f = _FakeUploadFile(data)
    tmp, size = await read_chunked_to_tempfile(f, max_bytes=DEFAULT_MAX_BYTES, tmp_dir=tmp_path)
    assert size == len(data)
    assert tmp.read_bytes() == data
    assert tmp.name.endswith(".partial")


@pytest.mark.asyncio
async def test_read_chunked_rejects_oversize_and_cleans_tmp(tmp_path: Path):
    """AC-2: 超 max_bytes 立即终止 + 删 .partial + 抛 UploadSizeExceeded。"""
    data = b"x" * (1024 + 1)  # 1025 bytes
    f = _FakeUploadFile(data)
    with pytest.raises(UploadSizeExceeded):
        await read_chunked_to_tempfile(f, max_bytes=1024, tmp_dir=tmp_path, chunk_size=64)
    # 临时文件应被删除
    partials = list(tmp_path.glob("*.partial"))
    assert partials == [], f"超限后应删 .partial，残留：{partials}"


@pytest.mark.asyncio
async def test_read_chunked_zero_max_bytes_rejected(tmp_path: Path):
    f = _FakeUploadFile(b"data")
    with pytest.raises(UploadSafetyError):
        await read_chunked_to_tempfile(f, max_bytes=0, tmp_dir=tmp_path)


def test_commit_tmpfile_renames_to_final(tmp_path: Path):
    tmp = tmp_path / "abc.partial"
    tmp.write_bytes(b"payload")
    final = tmp_path / "final" / "out.bin"
    commit_tmpfile(tmp, final)
    assert final.read_bytes() == b"payload"
    assert not tmp.exists()


def test_commit_tmpfile_failure_cleans_tmp(tmp_path: Path):
    """rename 失败（target 父目录不可写等）应清理 tmp。"""
    tmp = tmp_path / "abc.partial"
    tmp.write_bytes(b"payload")
    # 指向一个不可达路径（parent 是文件而非目录）触发 OSError
    blocker = tmp_path / "blocker"
    blocker.write_bytes(b"x")
    final = blocker / "out.bin"  # blocker 是文件，rename 必失败
    with pytest.raises(OSError):
        commit_tmpfile(tmp, final)
    assert not tmp.exists(), "失败后应清理 tmp"


# --------- 类型白名单 ----------

def test_validate_upload_type_document_allows_pdf():
    validate_upload_type("document", filename="report.pdf", content_type="application/pdf")


def test_validate_upload_type_document_rejects_exe():
    """AC-3: 不支持的类型 -> UploadTypeUnsupported（router 映射 415）。"""
    with pytest.raises(UploadTypeUnsupported):
        validate_upload_type(
            "document", filename="evil.exe", content_type="application/octet-stream",
        )


def test_validate_upload_type_structured_data_allows_xlsx_csv():
    validate_upload_type(
        "structured_data",
        filename="a.xlsx",
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )
    validate_upload_type("structured_data", filename="b.csv", content_type="text/csv")


def test_validate_upload_type_resource_allows_common():
    validate_upload_type("resource", filename="img.png", content_type="image/png")
    validate_upload_type("resource", filename="doc.pdf", content_type="application/pdf")


def test_validate_upload_type_rejects_unknown_entry():
    with pytest.raises(UploadTypeUnsupported):
        validate_upload_type("nonexistent", filename="a.pdf", content_type="application/pdf")


def test_validate_upload_type_rejects_mismatched_ext_and_mime():
    """扩展名 pdf 但 MIME 是 exe -> 拒绝（防类型伪造）。"""
    with pytest.raises(UploadTypeUnsupported):
        validate_upload_type(
            "document",
            filename="fake.pdf",
            content_type="application/x-msdownload",
        )
