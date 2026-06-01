from __future__ import annotations

import re

import httpx

from app.shared.llm.protocol import ProviderUnavailable


class BaseProvider:
    """Base class for all LLM providers."""

    name: str = "base"

    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _build_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def _post(
        self,
        path: str,
        json_body: dict,
        timeout: float = 60.0,
    ) -> dict:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{self.base_url}{path}",
                    headers=self._build_headers(),
                    json=json_body,
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.TimeoutException as e:
            raise ProviderUnavailable(f"[{self.name}] request timeout") from e
        except httpx.HTTPStatusError as e:
            msg = f"[{self.name}] HTTP {e.response.status_code}: {e.response.text[:100]}"
            raise ProviderUnavailable(msg) from e
        except Exception as e:
            raise ProviderUnavailable(f"[{self.name}] {e}") from e


def _clean_response(content: str) -> str:
    """Strip markdown fences, thinking tags, and leading/trailing whitespace."""
    content = content.strip()
    # Remove markdown code fences
    content = re.sub(r"^```(?:json)?\s*\n?", "", content, count=1)
    content = re.sub(r"\n?```$", "", content, count=1)
    # Remove AI thinking tags (various Chinese/English patterns)
    content = re.sub(r"<(/?)think(\s|>).*?(<\1think)?>", "", content, flags=re.DOTALL)
    content = re.sub(r"<(/?)answer(\s|>).*?(<\1answer)?>", "", content, flags=re.DOTALL)
    # Remove leading markers
    content = re.sub(r"^[\n\r]+", "", content)
    return content.strip()
