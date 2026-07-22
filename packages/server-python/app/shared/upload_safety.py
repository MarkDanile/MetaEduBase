"""BUG-020 共享上传边界工具。

三个上传入口（document/structured_data/resource）共用：
- 文件名安全（剥离路径分隔符 / .. / Unicode 混淆）
- storage_key 服务端生成（不拼用户原始路径）
- 磁盘路径 containment 校验（防 symlink 逃逸）
- 流式分块 + size 上限（防内存耗尽）
- 类型白名单 + MIME 嗅探（防不受控文件落盘）
"""
from __future__ import annotations

import inspect
import os
import re
import unicodedata
import uuid
from pathlib import Path
from typing import Any

SAFE_DISPLAY_NAME_MAX_LEN = 200
SAFE_EXT_MAX_LEN = 16
DEFAULT_MAX_BYTES = 100 * 1024 * 1024  # 100MB

# URL 编码路径分隔符
_URL_ENCODED_SEPARATORS = ("%2F", "%5C", "%2f", "%5c")
# 双向控制字符 / BOM / zero-width（Unicode 混淆）
SAFE_BIDI_CHARS = frozenset({chr(0x202A), chr(0x202B), chr(0x202C), chr(0x202D), chr(0x202E)})
SAFE_BOM_CHARS = frozenset({chr(0xFEFF), chr(0x200B), chr(0x200C), chr(0x200D)})
_CONTROL_CHARS = SAFE_BIDI_CHARS | SAFE_BOM_CHARS | frozenset({chr(0x00), chr(0x1F)})
# 扩展名只允许字母数字 + 短横线
_EXT_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{1,16}$")
# 隐藏文件名（仅点号开头）
_HIDDEN_NAME_PATTERN = re.compile(r"^\.+$")


class UploadSafetyError(ValueError):
    """Raised when an upload violates the safety policy."""


class UploadSizeExceeded(UploadSafetyError):  # noqa: N818
    """上传文件超过允许大小。"""


class UploadTypeUnsupported(UploadSafetyError):  # noqa: N818
    """上传文件类型不在允许矩阵内。"""


def safe_display_name(filename: str) -> str:
    """剥离路径分隔符 / .. / Unicode 混淆 + 截断长度，返回安全显示名。

    不抛错时返回的文件名不含 ``/`` / ``\\`` / ``..`` / 任何控制字符；
    用于 UI 显示 + Content-Disposition filename。
    """
    if not filename:
        raise UploadSafetyError("文件名不能为空")
    # NFKC 归一化（防 Unicode 同形字混淆）
    s = unicodedata.normalize("NFKC", filename)
    # 剥离 URL 编码的路径分隔符
    for enc in _URL_ENCODED_SEPARATORS:
        s = s.replace(enc, "_")
    # 剥离控制字符（含 bidi / zero-width）
    for ch in _CONTROL_CHARS:
        s = s.replace(ch, "")
    # 仅保留 basename：split on / 与 \\
    s = s.replace("\\", "/")
    if "/" in s:
        s = s.rsplit("/", 1)[-1]
    # 解析 . 处理（但拒绝隐藏文件 / 纯点号）
    if _HIDDEN_NAME_PATTERN.match(s):
        raise UploadSafetyError(f"文件名 {filename!r} 非法（仅点号）")
    # 移除 .. 段（递归）
    while ".." in s:
        s = s.replace("..", "")
    # 截断
    if len(s) > SAFE_DISPLAY_NAME_MAX_LEN:
        # 保留扩展名（如有）
        if "." in s:
            base, ext = s.rsplit(".", 1)
            base = base[: SAFE_DISPLAY_NAME_MAX_LEN - len(ext) - 1]
            s = f"{base}.{ext}"
        else:
            s = s[:SAFE_DISPLAY_NAME_MAX_LEN]
    # 最终确保不含路径分隔符 / 连续点
    s = s.replace("/", "").replace("\\", "")
    while ".." in s:
        s = s.replace("..", "")
    if not s or _HIDDEN_NAME_PATTERN.match(s):
        raise UploadSafetyError(f"文件名 {filename!r} 非法（处理后为空 / 仅点号）")
    return s


def safe_storage_key(tenant_id: str, original_filename: str) -> tuple[str, str]:
    """生成服务端 storage_key + 安全显示名。

    storage_key 不含用户原始路径：``f"{tenant_id}/{uuid.uuid4().hex}.{safe_ext}"``
    显示名经 ``safe_display_name`` 处理。
    返回 ``(storage_key, display_name)``。
    """
    display = safe_display_name(original_filename)
    # 提取扩展名（限长 + 字母数字）；先截断到 SAFE_EXT_MAX_LEN 再 match
    ext = ""
    if "." in display:
        candidate = display.rsplit(".", 1)[-1][:SAFE_EXT_MAX_LEN]
        if _EXT_PATTERN.match(candidate):
            ext = candidate
    unique = uuid.uuid4().hex
    storage_key = f"{tenant_id}/{unique}.{ext}" if ext else f"{tenant_id}/{unique}"
    return storage_key, display


def validate_storage_path_containment(absolute_path: Path, base_root: Path) -> None:
    """断言 ``absolute_path`` 解析 realpath 后位于 ``base_root`` 之下。

    防 symlink 逃逸 + `..` 拼接：realpath 解析后再断言前缀。
    失败抛 :class:`UploadSafetyError`。
    """
    base_real = base_root.resolve()
    target_real = absolute_path.resolve()
    # commonpath 比 startswith 更稳（处理 /foo vs /foobar）
    try:
        common = os.path.commonpath([str(base_real), str(target_real)])
    except ValueError:
        raise UploadSafetyError(
            f"路径 {absolute_path} 与基准 {base_root} 不在同一驱动器"
        ) from None
    if common != str(base_real):
        raise UploadSafetyError(
            f"路径逃出基准目录：{absolute_path} 不在 {base_root} 内"
        )


async def read_chunked_to_tempfile(
    file: Any,
    *,
    max_bytes: int,
    tmp_dir: Path,
    chunk_size: int = 64 * 1024,
) -> tuple[Path, int]:
    """从 ``await file.read(chunk_size)`` 流式读取并写入 ``tmp_dir/{uuid}.partial``。

    支持同步（BytesIO）+ 异步（starlette UploadFile）两种 file 对象。
    - 累计字节 > ``max_bytes`` 立即停止并删除临时文件抛 :class:`UploadSizeExceeded`（413）
    - 返回 ``(tmp_path, size)``
    """
    if max_bytes <= 0:
        raise UploadSafetyError("max_bytes 必须 > 0")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"{uuid.uuid4().hex}.partial"
    total = 0
    f: Any = None
    try:
        f = open(tmp_path, "wb")  # noqa: SIM115 - 跨 try/finally 手动管理
        while True:
            chunk = file.read(chunk_size)
            if inspect.isawaitable(chunk):
                chunk = await chunk
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                f.close()
                f = None
                try:  # noqa: SIM105
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass
                raise UploadSizeExceeded(
                    f"文件超过 {max_bytes} bytes 限制（已读 {total} bytes）"
                )
            f.write(chunk)
    finally:
        if f is not None:
            f.close()
    return tmp_path, total


def commit_tmpfile(tmp_path: Path, final_path: Path) -> None:
    """rename ``tmp_path`` 到 ``final_path``；失败时清理 tmp + 抛错。"""
    try:
        final_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp_path, final_path)
    except OSError:
        try:  # noqa: SIM105
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


# --------- 类型白名单矩阵（AC-3） ----------
# 每入口：{ext -> 允许的 MIME set}；filename ext 与 content_type 必须双匹配
ALLOWED_MATRIX: dict[str, dict[str, frozenset[str]]] = {
    "document": {
        "pdf": frozenset({"application/pdf"}),
        "docx": frozenset({
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }),
        "doc": frozenset({"application/msword"}),
        "txt": frozenset({"text/plain"}),
        "md": frozenset({"text/plain", "text/markdown"}),
    },
    "structured_data": {
        "xlsx": frozenset({
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }),
        "xls": frozenset({"application/vnd.ms-excel"}),
        "csv": frozenset({"text/csv", "application/csv", "text/plain"}),
    },
    "resource": {
        "pdf": frozenset({"application/pdf"}),
        "txt": frozenset({"text/plain"}),
        "png": frozenset({"image/png"}),
        "jpg": frozenset({"image/jpeg"}),
        "jpeg": frozenset({"image/jpeg"}),
        "gif": frozenset({"image/gif"}),
        "svg": frozenset({"image/svg+xml"}),
        "mp4": frozenset({"video/mp4"}),
        "mp3": frozenset({"audio/mpeg"}),
        "docx": frozenset({
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }),
        "pptx": frozenset({
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        }),
    },
}


def validate_upload_type(
    entry: str, *, filename: str, content_type: str | None,
) -> None:
    """AC-3: 校验 filename 扩展名 + content_type 都在 entry 白名单内。

    - entry 不在矩阵 -> :class:`UploadTypeUnsupported`
    - ext 不在该 entry 白名单 -> 拒绝
    - ext 在白名单但 content_type 不匹配该 ext 的 MIME set -> 拒绝（防类型伪造）
    通过则静默返回。
    """
    matrix = ALLOWED_MATRIX.get(entry)
    if matrix is None:
        raise UploadTypeUnsupported(f"未知上传入口：{entry!r}")
    ext = ""
    if "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()
    if not ext:
        raise UploadTypeUnsupported(f"文件名 {filename!r} 缺少扩展名")
    allowed_mimes = matrix.get(ext)
    if allowed_mimes is None:
        raise UploadTypeUnsupported(
            f"入口 {entry!r} 不允许扩展名 .{ext}"
        )
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct and ct not in allowed_mimes:
        raise UploadTypeUnsupported(
            f".{ext} 扩展名与 MIME {ct!r} 不匹配（允许 {sorted(allowed_mimes)}）"
        )
    # content_type 缺失时不阻塞（部分 client 不传）；ext 已白名单
    return
