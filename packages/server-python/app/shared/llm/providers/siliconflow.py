from __future__ import annotations

import httpx

from app.config import settings
from app.shared.llm.protocol import ChatOptions, ProviderUnavailable
from app.shared.llm.providers.base import BaseProvider, _clean_response


class SiliconFlowProvider(BaseProvider):
    name = "siliconflow"

    def __init__(self):
        super().__init__(
            api_key=settings.siliconflow_api_key,
            base_url=settings.siliconflow_base_url,
        )
        self.chat_model = getattr(settings, "siliconflow_chat_model", "Qwen/Qwen2.5-7B-Instruct")
        self.embedding_model = settings.siliconflow_embedding_model

    def is_available(self) -> bool:
        return bool(settings.siliconflow_api_key)

    async def chat(self, messages: list[dict], options: ChatOptions) -> str:
        body = {
            "model": options.model or self.chat_model,
            "messages": messages,
            "temperature": options.temperature,
        }
        if options.max_tokens:
            body["max_tokens"] = options.max_tokens

        data = await self._post("/chat/completions", body, timeout=options.timeout)
        content = data["choices"][0]["message"]["content"]
        return _clean_response(content)

    async def embed(self, texts: list[str], timeout: float = 60.0) -> list[list[float]]:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/embeddings",
                    headers=self._build_headers(),
                    json={
                        "model": self.embedding_model,
                        "input": texts,
                    },
                )
                resp.raise_for_status()
                return [item["embedding"] for item in resp.json()["data"]]
        except httpx.TimeoutException as e:
            raise ProviderUnavailable(f"[{self.name}] embedding timeout") from e
        except httpx.HTTPStatusError as e:
            raise ProviderUnavailable(f"[{self.name}] HTTP {e.response.status_code}") from e
        except Exception as e:
            raise ProviderUnavailable(f"[{self.name}] embedding failed: {e}") from e
