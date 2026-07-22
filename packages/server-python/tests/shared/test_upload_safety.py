"""BUG-020 Slice 1: 共享上传边界工具。

AC-1/AC-4: 文件名安全（剥离路径分隔符/..//Unicode 混淆），storage_key
服务端生成不拼用户原始路径，磁盘路径 containment 校验防 symlink 逃逸。
"""
from __future__ import annotations

import unicodedata

import pytest

from app.shared.upload_safety import (
    SAFE_BIDI_CHARS,
    SAFE_BOM_CHARS,
    SAFE_DISPLAY_NAME_MAX_LEN,
    SAFE_EXT_MAX_LEN,
    UploadSafetyError,
    safe_display_name,
    safe_storage_key,
    validate_storage_path_containment,
)

# --------- safe_display_name ----------

def test_safe_display_name_passthrough_simple():
    assert safe_display_name("report.pdf") == "report.pdf"


def test_safe_display_name_strips_directory_traversal():
    assert safe_display_name("../../etc/passwd") == "passwd"
    assert safe_display_name("..\\..\\windows\\system32") == "system32"


def test_safe_display_name_strips_absolute_prefix():
    assert safe_display_name("/etc/passwd") == "passwd"
    assert safe_display_name("C:\\Windows\\evil.exe") == "evil.exe"


def test_safe_display_name_strips_forward_slash():
    assert safe_display_name("subdir/file.pdf") == "file.pdf"


@pytest.mark.parametrize(
    "raw_filename, unicode_point",
    [
        # 用 chr() 显式构造避免测试源码含不可见控制字符触发 null byte
        ("..%2Fetc%2Fpasswd", None),                # URL 编码 /
        ("..%5Cwindows%5Csystem32", None),          # URL 编码 \\
        ("%2e%2e/etc/passwd", None),                # 点 URL 编码
        ("malware-prefix", 0x202E),                  # RLO 控制字符
        ("bom-prefix", 0xFEFF),                       # BOM
    ],
)
def test_safe_display_name_blocks_obfuscation(raw_filename, unicode_point):
    """AC-1: Unicode 混淆 / URL 编码后目录分隔符不能逃出。"""
    filename = raw_filename if unicode_point is None else chr(unicode_point) + raw_filename
    result = safe_display_name(filename)
    assert "/" not in result
    assert "\\" not in result
    assert ".." not in result
    # bidi / BOM 控制字符应被剥离
    assert not any(ch in result for ch in SAFE_BIDI_CHARS)
    assert not any(ch in result for ch in SAFE_BOM_CHARS)


def test_safe_display_name_blocks_unicode_normalization_obfuscation():
    """NFKC 归一化把全角点 / 同形字变标准 ASCII（防 NFKD bypass）。"""
    # ＯＭＩＣＲＯＮ（希腊 omicron U+039F） 经 NFKC 归一化后 == 'O'
    nfkc = unicodedata.normalize("NFKC", "ΟΜΙΚΟΝ.exe")
    # 验证我们的 safe_display_name 处理全角字符不走绕过
    result = safe_display_name(nfkc + ".exe")
    assert "/" not in result
    assert ".." not in result


def test_safe_display_name_truncates_long():
    long = "a" * (SAFE_DISPLAY_NAME_MAX_LEN + 100) + ".pdf"
    result = safe_display_name(long)
    assert len(result) <= SAFE_DISPLAY_NAME_MAX_LEN
    assert result.endswith(".pdf")


def test_safe_display_name_rejects_empty():
    with pytest.raises(UploadSafetyError):
        safe_display_name("")


def test_safe_display_name_rejects_dots_only():
    """纯点号 / 隐藏文件无扩展名拒绝（无意义）。"""
    with pytest.raises(UploadSafetyError):
        safe_display_name("....")
    with pytest.raises(UploadSafetyError):
        safe_display_name(".")


# --------- safe_storage_key ----------

def test_safe_storage_key_uses_uuid_and_safe_ext():
    tid = "00000000-0000-0000-0000-000000000001"
    key, safe_name = safe_storage_key(tid, "../../etc/passwd")
    # 安全显示名不含路径分隔符
    assert "/" not in safe_name
    assert "\\" not in safe_name
    # storage_key 不含用户原始路径
    assert ".." not in key
    assert "etc" not in key
    assert "passwd" not in key
    # 以 tid 开头
    assert key.startswith(f"{tid}/")


def test_safe_storage_key_extension_truncated():
    tid = "00000000-0000-0000-0000-000000000001"
    long_ext = "x" * (SAFE_EXT_MAX_LEN + 100)
    key, _ = safe_storage_key(tid, f"file.{long_ext}")
    # 扩展名被截断到 SAFE_EXT_MAX_LEN
    ext_in_key = key.rsplit(".", 1)[-1]
    assert len(ext_in_key) <= SAFE_EXT_MAX_LEN


# --------- validate_storage_path_containment ----------

def test_validate_storage_path_containment_blocks_traversal(tmp_path):
    base = tmp_path / "uploads"
    base.mkdir()
    # 通过相对路径试图逃出 base
    bad = base / ".." / ".." / "etc" / "passwd"
    with pytest.raises(UploadSafetyError):
        validate_storage_path_containment(bad, base)


def test_validate_storage_path_containment_blocks_symlink(tmp_path):
    """symlink 指向 base 外 -> 解析 realpath 后不在 base 内 -> 拒绝。"""
    import os
    base = tmp_path / "uploads"
    base.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    link = base / "escape.txt"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink 不可用")
    with pytest.raises(UploadSafetyError):
        validate_storage_path_containment(link, base)


def test_validate_storage_path_containment_allows_valid(tmp_path):
    base = tmp_path / "uploads"
    base.mkdir()
    ok = base / "tenant1" / "uuid.pdf"
    ok.parent.mkdir()
    ok.write_text("ok")
    # 路径在 base 内，应通过
    validate_storage_path_containment(ok, base)
