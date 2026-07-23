from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.slow


import pytest

from app.contexts.knowledge.application.embedding_service import (
    get_embedding,
    get_embedding_with_timeout,
)


@pytest.mark.asyncio
async def test_get_embedding_no_api_key():
    with patch("app.contexts.knowledge.application.embedding_service.settings") as mock_settings:
        mock_settings.qwen_api_key = ""
        with patch.dict("os.environ", {"DASHSCOPE_API_KEY": ""}):
            result = await get_embedding("测试文本")
            assert result is None


@pytest.mark.asyncio
async def test_get_embedding_with_api_key():
    fake_embedding = [0.1] * 1536
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [{"embedding": fake_embedding}],
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.contexts.knowledge.application.embedding_service.settings") as mock_settings:
        mock_settings.qwen_api_key = "test-key"
        mock_settings.qwen_base_url = "https://test.example.com/v1"
        mock_settings.embedding_model = "test-model"

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await get_embedding("测试文本")
            assert result == fake_embedding
            assert len(result) == 1536


@pytest.mark.asyncio
async def test_get_embedding_api_failure():
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=Exception("API Error"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.contexts.knowledge.application.embedding_service.settings") as mock_settings:
        mock_settings.qwen_api_key = "test-key"
        mock_settings.qwen_base_url = "https://test.example.com/v1"
        mock_settings.embedding_model = "test-model"

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await get_embedding("测试文本")
            assert result is None


# TD-070: get_embedding_with_timeout — outer hard timeout for vector recall.


@pytest.mark.asyncio
async def test_get_embedding_with_timeout_success_passthrough():
    """Fast get_embedding → helper returns the embedding unchanged."""
    fake_embedding = [0.1] * 4096

    async def _fast(_text: str) -> list[float]:
        return fake_embedding

    with patch(
        "app.contexts.knowledge.application.embedding_service.get_embedding",
        side_effect=_fast,
    ):
        result = await get_embedding_with_timeout("测试", timeout=60.0)
    assert result == fake_embedding


@pytest.mark.asyncio
async def test_get_embedding_with_timeout_returns_none_on_timeout():
    """Slow get_embedding (>timeout) → helper returns None (keyword fallback)."""
    import asyncio as _asyncio

    async def _slow(_text: str) -> list[float]:
        await _asyncio.sleep(10.0)
        return [0.1] * 4096

    with patch(
        "app.contexts.knowledge.application.embedding_service.get_embedding",
        side_effect=_slow,
    ):
        result = await get_embedding_with_timeout("测试", timeout=0.1)
    assert result is None


@pytest.mark.asyncio
async def test_get_embedding_with_timeout_none_passthrough():
    """get_embedding returning None (no key / all providers fail) → helper
    returns None without raising (preserves existing contract)."""
    with patch(
        "app.contexts.knowledge.application.embedding_service.get_embedding",
        return_value=None,
    ):
        result = await get_embedding_with_timeout("测试", timeout=60.0)
    assert result is None


# TD-071: get_embeddings_with_timeout_batch — batch variant using provider's native batch API.


@pytest.mark.asyncio
async def test_get_embeddings_batch_success():
    """Batch API returns all embeddings aligned with input texts."""
    fake_embeddings = [[0.1] * 4096, [0.2] * 4096, [0.3] * 4096]
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [{"embedding": e} for e in fake_embeddings],
    }
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "app.contexts.knowledge.application.embedding_service.settings"
    ) as mock_settings:
        mock_settings.qwen_api_key = "test-key"
        mock_settings.qwen_base_url = "https://test.example.com/v1"
        mock_settings.embedding_model = "test-model"

        with patch("httpx.AsyncClient", return_value=mock_client):
            from app.contexts.knowledge.application.embedding_service import (
                get_embeddings_with_timeout_batch,
            )

            texts = ["alpha", "beta", "gamma"]
            result = await get_embeddings_with_timeout_batch(texts, batch_size=10)

    assert len(result) == 3
    assert result == fake_embeddings
    # Verify batch was actually used (single HTTP call, multi-element input)
    assert mock_client.post.call_count == 1
    call_kwargs = mock_client.post.call_args.kwargs
    assert call_kwargs["json"]["input"] == ["alpha", "beta", "gamma"]


@pytest.mark.asyncio
async def test_get_embeddings_batch_partial_failure_falls_back():
    """Batch HTTP returns wrong count → per-text fallback for that batch."""
    # First batch (size 2) fails: HTTP raises; fallback per-text uses get_embedding.
    # We mock get_embedding to return per-text embeddings.
    fake_emb_a = [0.1] * 4096
    fake_emb_b = [0.2] * 4096

    async def _per_text(t: str) -> list[float] | None:
        return fake_emb_a if t == "a" else fake_emb_b

    failing_client = AsyncMock()
    failing_client.post = AsyncMock(side_effect=Exception("HTTP Error"))
    failing_client.__aenter__ = AsyncMock(return_value=failing_client)
    failing_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "app.contexts.knowledge.application.embedding_service.settings"
    ) as mock_settings:
        mock_settings.qwen_api_key = "test-key"
        mock_settings.qwen_base_url = "https://test.example.com/v1"
        mock_settings.embedding_model = "test-model"

        with patch("httpx.AsyncClient", return_value=failing_client), patch(
            "app.contexts.knowledge.application.embedding_service.get_embedding",
            side_effect=_per_text,
        ):
            from app.contexts.knowledge.application.embedding_service import (
                get_embeddings_with_timeout_batch,
            )

            texts = ["a", "b"]
            result = await get_embeddings_with_timeout_batch(texts, batch_size=10)

    assert result == [fake_emb_a, fake_emb_b]


@pytest.mark.asyncio
async def test_get_embeddings_batch_all_providers_unavailable():
    """No provider configured → returns [None] * len(texts)."""
    with patch(
        "app.contexts.knowledge.application.embedding_service.settings"
    ) as mock_settings:
        mock_settings.qwen_api_key = ""
        with patch.dict("os.environ", {"DASHSCOPE_API_KEY": ""}):
            mock_settings.siliconflow_api_key = ""
            mock_settings.minimax_api_key = ""

            from app.contexts.knowledge.application.embedding_service import (
                get_embeddings_with_timeout_batch,
            )

            result = await get_embeddings_with_timeout_batch(
                ["x", "y"], batch_size=10
            )

    assert result == [None, None]


@pytest.mark.asyncio
async def test_get_embeddings_batch_outer_timeout_falls_back():
    """asyncio.wait_for times out the batch call → per-text fallback for the batch."""
    import asyncio as _asyncio

    # Batch call hangs forever; per-text fallback returns immediately.
    fake_emb = [0.5] * 4096

    async def _hang(*_a, **_kw):
        await _asyncio.sleep(10.0)
        return MagicMock()

    async def _per_text(_t: str) -> list[float]:
        return fake_emb

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=_hang)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch(
        "app.contexts.knowledge.application.embedding_service.settings"
    ) as mock_settings:
        mock_settings.qwen_api_key = "test-key"
        mock_settings.qwen_base_url = "https://test.example.com/v1"
        mock_settings.embedding_model = "test-model"

        with patch("httpx.AsyncClient", return_value=mock_client), patch(
            "app.contexts.knowledge.application.embedding_service.get_embedding",
            side_effect=_per_text,
        ):
            from app.contexts.knowledge.application.embedding_service import (
                get_embeddings_with_timeout_batch,
            )

            # Note: outer timeout on per-text fallback is 60s default; we
            # override via timeout=0.2 to keep test fast.
            result = await get_embeddings_with_timeout_batch(
                ["p"], batch_size=10, timeout=0.2
            )

    assert result == [fake_emb]
