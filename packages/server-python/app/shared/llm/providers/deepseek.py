from __future__ import annotations

from app.config import settings
from app.shared.llm.protocol import ChatOptions
from app.shared.llm.providers.base import BaseProvider, _clean_response


class DeepSeekProvider(BaseProvider):
    name = "deepseek"

    def __init__(self):
        super().__init__(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
        self.model = settings.deepseek_model

    def is_available(self) -> bool:
        return bool(settings.deepseek_api_key)

    async def chat(self, messages: list[dict], options: ChatOptions) -> str:
        body = {
            "model": options.model or self.model,
            "messages": messages,
            "temperature": options.temperature,
        }
        if options.max_tokens:
            body["max_tokens"] = options.max_tokens

        data = await self._post("/chat/completions", body, timeout=options.timeout)
        content = data["choices"][0]["message"]["content"]
        return _clean_response(content)
