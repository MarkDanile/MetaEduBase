"""聚焦测试：app.shared.llm.factory 新增的 resolver 公开面。

锁住 TD-020 引入的两个公开符号：
- `RESOLVER_PROVIDER_NAMES`：resolver 子集与顺序的事实源。
- `resolver_default_provider()`：把 `settings.llm_default_provider`
  归一化为 resolver 期望的 alias 名；不在子集则返回 `None`。

resolver 自身的行为见 `tests/shared/test_provider_resolver.py`。
"""

from __future__ import annotations

import pytest

from app.shared.llm import factory
from app.shared.llm.factory import RESOLVER_PROVIDER_NAMES


class TestResolverProviderNames:
    def test_resolver_provider_names_is_immutable(self) -> None:
        assert isinstance(RESOLVER_PROVIDER_NAMES, tuple)
        assert RESOLVER_PROVIDER_NAMES == ("minimax", "deepseek", "qwen")

    def test_resolver_provider_names_contains_no_factory_internal_alias(self) -> None:
        # dashscope / siliconflow are factory-internal names that do not
        # appear in the resolver subset; this prevents a future refactor
        # from silently leaking a factory-only provider into ai_router.
        for name in RESOLVER_PROVIDER_NAMES:
            assert name in {"minimax", "deepseek", "qwen"}


class TestResolverDefaultProvider:
    def test_returns_none_for_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(factory.settings, "llm_default_provider", "")
        assert factory.resolver_default_provider() is None

    def test_returns_none_for_whitespace_only(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(factory.settings, "llm_default_provider", "   ")
        assert factory.resolver_default_provider() is None

    def test_lowercases_minimax(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(factory.settings, "llm_default_provider", "Minimax")
        assert factory.resolver_default_provider() == "minimax"

    def test_lowercases_deepseek_with_whitespace(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(factory.settings, "llm_default_provider", " DeepSeek ")
        assert factory.resolver_default_provider() == "deepseek"

    def test_qwen_kept_as_qwen_alias(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Resolver-visible alias is `qwen`, not `dashscope`. ai_router
        # relies on this alias to render its Chinese guidance message.
        monkeypatch.setattr(factory.settings, "llm_default_provider", "qwen")
        assert factory.resolver_default_provider() == "qwen"

    def test_qwen_uppercase_with_whitespace_kept_as_qwen(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(factory.settings, "llm_default_provider", "  Qwen  ")
        assert factory.resolver_default_provider() == "qwen"

    def test_dashscope_is_not_a_resolver_alias(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # dashscope is a factory-internal name; resolver must not
        # synthesize a qwen win just because factory knows how to
        # normalize the spelling.
        monkeypatch.setattr(factory.settings, "llm_default_provider", "dashscope")
        assert factory.resolver_default_provider() is None

    def test_siliconflow_is_not_a_resolver_alias(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(factory.settings, "llm_default_provider", "siliconflow")
        assert factory.resolver_default_provider() is None

    def test_unknown_value_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(factory.settings, "llm_default_provider", "openai")
        assert factory.resolver_default_provider() is None
