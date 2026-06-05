"""聚焦测试：app.shared.llm.provider_resolver.resolve_chat_provider。

通过 monkeypatch 替换 settings 字段，验证 7 类路径：
1. 无任何 key → None
2. 默认 provider 命中 → 该 provider config
3. 默认 provider 无 key，但其它 provider 有 key → 顺序回退
4. 默认 provider 是不在候选集里的值 → 忽略，按候选集顺序
5. 多个 provider 都有 key，按顺序选第一个
6. provider 缺 base_url / model 等不完整 → 跳过
7. 默认 provider 在候选集里时挪到顺序首位
8. 默认 provider 大小写 / 空白变体（`Qwen`、` deepseek `）应等价于小写
9. 默认 provider 是 `dashscope` → 仍走子集顺序（不归一化为 `qwen`）

`factory.resolver_default_provider` 与 `RESOLVER_PROVIDER_NAMES` 的
覆盖见 `tests/shared/test_factory.py`。
"""

from __future__ import annotations

import pytest

from app.shared.llm import provider_resolver
from app.shared.llm.factory import RESOLVER_PROVIDER_NAMES
from app.shared.llm.provider_resolver import resolve_chat_provider


def _set_settings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    llm_default_provider: str = "",
    minimax_api_key: str = "",
    deepseek_api_key: str = "",
    qwen_api_key: str = "",
) -> None:
    monkeypatch.setattr(
        provider_resolver.settings, "llm_default_provider", llm_default_provider
    )
    monkeypatch.setattr(
        provider_resolver.settings, "minimax_api_key", minimax_api_key
    )
    monkeypatch.setattr(
        provider_resolver.settings, "deepseek_api_key", deepseek_api_key
    )
    monkeypatch.setattr(provider_resolver.settings, "qwen_api_key", qwen_api_key)


class TestResolveChatProvider:
    def test_returns_none_when_no_api_key_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_settings(monkeypatch)
        assert resolve_chat_provider() is None

    def test_returns_minimax_when_default_is_minimax_and_key_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_settings(
            monkeypatch,
            llm_default_provider="minimax",
            minimax_api_key="mm-key",
            deepseek_api_key="ds-key",
            qwen_api_key="qwen-key",
        )
        cfg = resolve_chat_provider()
        assert cfg is not None
        assert cfg.provider_name == "minimax"
        assert cfg.api_key == "mm-key"

    def test_falls_back_to_other_provider_when_default_has_no_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Default is "minimax" but no key; deepseek has a key.
        _set_settings(
            monkeypatch,
            llm_default_provider="minimax",
            deepseek_api_key="ds-key",
        )
        cfg = resolve_chat_provider()
        assert cfg is not None
        assert cfg.provider_name == "deepseek"
        assert cfg.api_key == "ds-key"

    def test_ignores_default_provider_value_outside_candidate_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # "dashscope" is not in the resolver's candidate set; should be
        # ignored and resolver should fall through to the in-set order.
        _set_settings(
            monkeypatch,
            llm_default_provider="dashscope",
            qwen_api_key="qwen-key",
        )
        cfg = resolve_chat_provider()
        assert cfg is not None
        assert cfg.provider_name == "qwen"

    def test_uses_candidate_set_order_when_no_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # No default; minimax, deepseek, qwen all have keys.
        # Resolver order is minimax → deepseek → qwen.
        _set_settings(
            monkeypatch,
            minimax_api_key="mm-key",
            deepseek_api_key="ds-key",
            qwen_api_key="qwen-key",
        )
        cfg = resolve_chat_provider()
        assert cfg is not None
        assert cfg.provider_name == "minimax"

    def test_skips_providers_missing_required_config(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Only deepseek has a complete key+url+model; minimax has empty base_url.
        monkeypatch.setattr(
            provider_resolver.settings, "llm_default_provider", ""
        )
        monkeypatch.setattr(
            provider_resolver.settings, "minimax_api_key", "mm-key"
        )
        monkeypatch.setattr(
            provider_resolver.settings, "minimax_base_url", ""
        )
        monkeypatch.setattr(
            provider_resolver.settings, "deepseek_api_key", "ds-key"
        )
        monkeypatch.setattr(
            provider_resolver.settings, "deepseek_base_url", "https://api.deepseek.com/v1"
        )
        monkeypatch.setattr(
            provider_resolver.settings, "deepseek_model", "deepseek-chat"
        )
        cfg = resolve_chat_provider()
        assert cfg is not None
        assert cfg.provider_name == "deepseek"

    def test_default_qwen_moves_to_front_of_order(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Default is qwen; qwen has a key; minimax also has a key.
        # qwen should win because the default moves to the front.
        _set_settings(
            monkeypatch,
            llm_default_provider="qwen",
            minimax_api_key="mm-key",
            qwen_api_key="qwen-key",
        )
        cfg = resolve_chat_provider()
        assert cfg is not None
        assert cfg.provider_name == "qwen"

    def test_default_qwen_uppercase_with_whitespace_is_normalized(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # "Qwen" / " qwen " / "QWEN" should all move qwen to the front
        # just like the lowercased form.
        _set_settings(
            monkeypatch,
            llm_default_provider="  Qwen  ",
            minimax_api_key="mm-key",
            qwen_api_key="qwen-key",
        )
        cfg = resolve_chat_provider()
        assert cfg is not None
        assert cfg.provider_name == "qwen"

    def test_provider_name_is_always_a_resolver_alias(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Whichever provider wins, its `provider_name` must be one of the
        # resolver aliases; never "dashscope", never a factory-internal
        # name.
        _set_settings(
            monkeypatch,
            llm_default_provider="dashscope",
            minimax_api_key="mm-key",
            deepseek_api_key="ds-key",
            qwen_api_key="qwen-key",
        )
        cfg = resolve_chat_provider()
        assert cfg is not None
        assert cfg.provider_name in RESOLVER_PROVIDER_NAMES
        assert cfg.provider_name != "dashscope"

