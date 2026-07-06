"""Test PIIDetector: 5 PII types (id_card / phone / bank_card / email / address).

REQ-052 Task 3: each test covers a detection + mask behaviour. The detector
is the last defense — it must work on free-form Chinese text where PII may be
glued to CJK characters (no \b word boundary on CN side). Tests use realistic
input shaped like real user-supplied free text.
"""

from __future__ import annotations

import pytest

from app.contexts.structured_data.application.pii_detector import PIIDetector


@pytest.fixture
def detector() -> PIIDetector:
    return PIIDetector()


# ---------------------------------------------------------------------------
# detect() — return list of PII types present in the value
# ---------------------------------------------------------------------------


def test_detect_id_card_with_space(detector):
    """常规中文 + 空格 + 18 位身份证 → detect。"""
    pii_types = detector.detect("张三的身份证是 110101199003078813")
    assert "id_card" in pii_types


def test_detect_id_card_glued_to_chinese(detector):
    """身份证号紧贴中文字符（无空格、无标点）→ 仍能 detect。

    这是 \b 边界的典型失败场景；我们必须使用字符 lookaround 才能识别。
    """
    pii_types = detector.detect("张三的身份证是110101199003078813")
    assert "id_card" in pii_types


def test_detect_id_card_with_x_suffix(detector):
    """末位 X 的身份证仍能被识别。"""
    pii_types = detector.detect("身份证号 11010119900307881X")
    assert "id_card" in pii_types


def test_detect_phone_chinese_context(detector):
    """中文上下文中的 11 位手机号。"""
    pii_types = detector.detect("联系电话 13812345678")
    assert "phone" in pii_types


def test_detect_phone_no_separator(detector):
    """紧贴中文字符的手机号。"""
    pii_types = detector.detect("联系电话13812345678")
    assert "phone" in pii_types


def test_detect_bank_card(detector):
    """19 位银行卡号。"""
    pii_types = detector.detect("银行卡 6222021234567890123")
    assert "bank_card" in pii_types


def test_detect_email(detector):
    """email 地址。"""
    pii_types = detector.detect("邮箱 admin@example.com")
    assert "email" in pii_types


def test_detect_address_with_province(detector):
    """含省级地址字段。"""
    pii_types = detector.detect("江苏省南京市江宁区")
    assert "address" in pii_types


def test_detect_address_with_road(detector):
    """含道路字段。"""
    pii_types = detector.detect("地址：江宁区将军大道 88 号")
    assert "address" in pii_types


def test_detect_no_pii_clean_text(detector):
    """普通业务文本：无 PII。"""
    text = "江苏神码信息技术有限公司欠费 5000 元"
    pii_types = detector.detect(text)
    assert len(pii_types) == 0


def test_detect_non_string_returns_empty(detector):
    """非字符串输入返回空列表（不抛错）。"""
    assert detector.detect(None) == []
    assert detector.detect(12345) == []
    assert detector.detect(["13812345678"]) == []
    assert detector.detect({"x": 1}) == []


def test_detect_empty_string_returns_empty(detector):
    """空字符串返回空列表。"""
    assert detector.detect("") == []


# ---------------------------------------------------------------------------
# mask() — apply masking transform per PII type
# ---------------------------------------------------------------------------


def test_mask_id_card_keeps_first6_and_last4(detector):
    """mask_id_card: 18 位 → 前 6 + * * * * * * * * + 后 4。"""
    masked = detector.mask("110101199003078813", "id_card")
    assert masked == "110101********8813"


def test_mask_phone_keeps_first3_and_last4(detector):
    """mask_phone: 11 位 → 前 3 + **** + 后 4。"""
    masked = detector.mask("13812345678", "phone")
    assert masked == "138****5678"


def test_mask_bank_card_keeps_first4_and_last4(detector):
    """mask_bank_card: 19 位 → 前 4 + 11 颗星 (19-4-4) + 后 4。

    Total length stays 19 (4 + 11 + 4).
    """
    masked = detector.mask("6222021234567890123", "bank_card")
    assert masked == "6222***********0123"
    assert len(masked) == 19


def test_mask_email_keeps_local_prefix(detector):
    """mask_email: 保留用户名前 2 字符 + *** + @domain。"""
    masked = detector.mask("admin@example.com", "email")
    assert masked == "ad***@example.com"


def test_mask_email_short_local(detector):
    """email 本地部分 < 2 字符时仅保留 1 字符。"""
    masked = detector.mask("a@example.com", "email")
    # 1 char + *** + @example.com → "a***@example.com"
    assert masked.endswith("@example.com")
    assert "*" in masked


def test_mask_address_long_string_redacts(detector):
    """长地址 → 完全 ***。"""
    masked = detector.mask("江苏省南京市江宁区将军大道 88 号", "address")
    assert "*" in masked
    assert "江苏省" not in masked


def test_mask_unknown_type_falls_back_to_stars(detector):
    """未知 PII 类型 → 兜底 ***（不抛错）。"""
    masked = detector.mask("hello", "ssn")
    assert masked == "***"


def test_mask_non_string_returns_as_is(detector):
    """非字符串输入按原样返回（不抛错）。"""
    assert detector.mask(None, "phone") is None
    assert detector.mask(12345, "phone") == 12345
    assert detector.mask([], "phone") == []


# ---------------------------------------------------------------------------
# detect_and_mask_dict() — recursively walk dict and mask string values
# ---------------------------------------------------------------------------


def test_detect_and_mask_dict_top_level_strings(detector):
    """顶层 string 值含 PII → 脱敏。"""
    data = {
        "name": "张三",
        "id_card": "110101199003078813",
        "company": "ACME",
    }
    out = detector.detect_and_mask_dict(data)
    assert out["name"] == "张三"  # no PII → unchanged
    assert out["id_card"] == "110101********8813"
    assert out["company"] == "ACME"


def test_detect_and_mask_dict_recurses_into_nested(detector):
    """嵌套 dict 中的 string 值也被脱敏。"""
    data = {
        "company": {
            "name": "ACME",
            "billing_contact": {
                "phone": "13812345678",
                "note": "no PII here",
            },
        },
        "metadata": {
            "created_by": "auto",
        },
    }
    out = detector.detect_and_mask_dict(data)
    assert out["company"]["name"] == "ACME"
    assert out["company"]["billing_contact"]["phone"] == "138****5678"
    assert out["company"]["billing_contact"]["note"] == "no PII here"
    assert out["metadata"]["created_by"] == "auto"


def test_detect_and_mask_dict_preserves_non_string_values(detector):
    """数字 / None / 列表 → 原样保留。"""
    data = {
        "amount": 5000.0,
        "count": 0,
        "tags": ["urgent", "Q2"],
        "note": None,
    }
    out = detector.detect_and_mask_dict(data)
    assert out["amount"] == 5000.0
    assert out["count"] == 0
    assert out["tags"] == ["urgent", "Q2"]
    assert out["note"] is None


def test_detect_and_mask_dict_returns_new_dict(detector):
    """输入 dict 不被就地修改。"""
    data = {"phone": "13812345678"}
    out = detector.detect_and_mask_dict(data)
    assert out is not data
    assert data["phone"] == "13812345678"  # untouched
