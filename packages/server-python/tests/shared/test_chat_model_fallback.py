"""聚焦测试：app.shared.llm.chat_with_fallback 助手。

不连接真实 LLM：通过 monkeypatch 替换 chat() 函数，验证
chat_with_model_fallback 的 fast → fallback 行为是否与设计一致。
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.shared.llm import chat_with_fallback
from app.shared.llm.chat_with_fallback import chat_with_model_fallback
from app.shared.llm.protocol import ProviderUnavailable


def _install_chat_mock(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Replace chat_with_fallback.chat with an AsyncMock; return it for assertions."""
    mock = AsyncMock()
    monkeypatch.setattr(chat_with_fallback, "chat", mock)
    return mock


class TestChatWithModelFallback:
    @pytest.mark.asyncio
    async def test_returns_fast_result_when_fast_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock = _install_chat_mock(monkeypatch)
        mock.return_value = "fast-ok"

        result = await chat_with_model_fallback(
            messages=[{"role": "user", "content": "hi"}],
            fast_provider="deepseek",
            fast_model="deepseek-v4-flash",
            fallback_provider="deepseek",
            fallback_model="deepseek-chat",
            temperature=0.5,
            max_tokens=1234,
            timeout=42.0,
        )

        assert result == "fast-ok"
        # Fast succeeded, fallback should NOT have been called
        assert mock.call_count == 1
        kwargs = mock.call_args.kwargs
        assert kwargs["provider"] == "deepseek"
        assert kwargs["model"] == "deepseek-v4-flash"
        assert kwargs["temperature"] == 0.5
        assert kwargs["max_tokens"] == 1234
        assert kwargs["timeout"] == 42.0

    @pytest.mark.asyncio
    async def test_falls_back_to_default_model_when_fast_raises_provider_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock = _install_chat_mock(monkeypatch)
        # First call raises ProviderUnavailable; second returns fallback content
        mock.side_effect = [
            ProviderUnavailable("deepseek-v4-flash unavailable"),
            "fallback-ok",
        ]

        result = await chat_with_model_fallback(
            messages=[{"role": "user", "content": "hi"}],
        )

        assert result == "fallback-ok"
        assert mock.call_count == 2
        first_kwargs = mock.call_args_list[0].kwargs
        second_kwargs = mock.call_args_list[1].kwargs
        # First attempt: fast model
        assert first_kwargs["provider"] == "deepseek"
        assert first_kwargs["model"] == "deepseek-v4-flash"
        # Second attempt: fallback model (default = settings.deepseek_model)
        assert second_kwargs["provider"] == "deepseek"
        assert second_kwargs["model"] == settings.deepseek_model

    @pytest.mark.asyncio
    async def test_raises_provider_unavailable_when_both_attempts_fail(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock = _install_chat_mock(monkeypatch)
        mock.side_effect = [
            ProviderUnavailable("fast fail"),
            ProviderUnavailable("fallback fail"),
        ]

        with pytest.raises(ProviderUnavailable, match="fallback fail"):
            await chat_with_model_fallback(
                messages=[{"role": "user", "content": "hi"}],
            )

        assert mock.call_count == 2

    @pytest.mark.asyncio
    async def test_uses_settings_deepseek_model_when_fallback_model_omitted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock = _install_chat_mock(monkeypatch)
        mock.side_effect = [ProviderUnavailable("fast"), "ok"]

        await chat_with_model_fallback(
            messages=[{"role": "user", "content": "hi"}],
            fast_provider="deepseek",
            fast_model="deepseek-v4-flash",
            fallback_provider="deepseek",
            # fallback_model omitted → settings.deepseek_model
        )

        assert mock.call_args_list[1].kwargs["model"] == settings.deepseek_model

    @pytest.mark.asyncio
    async def test_propagates_non_provider_unavailable_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Non-ProviderUnavailable errors (e.g. ValueError from unknown provider)
        # should propagate, not be swallowed as "fast failure".
        mock = _install_chat_mock(monkeypatch)
        mock.side_effect = ValueError("unknown provider")

        with pytest.raises(ValueError, match="unknown provider"):
            await chat_with_model_fallback(
                messages=[{"role": "user", "content": "hi"}],
            )

        # Only one chat() call should have happened
        assert mock.call_count == 1

    @pytest.mark.asyncio
    async def test_messages_passed_through_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock = _install_chat_mock(monkeypatch)
        mock.return_value = "ok"

        messages = [
            {"role": "system", "content": "you are a helper"},
            {"role": "user", "content": "hello"},
        ]
        await chat_with_model_fallback(messages=messages)

        # First positional arg should be the messages list
        args, _ = mock.call_args
        assert args[0] == messages
