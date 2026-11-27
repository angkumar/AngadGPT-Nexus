from dataclasses import dataclass
import logging
from typing import Any, Dict, List

import httpx

from backend.core.config import (
    LLM_TIMEOUT_SECONDS,
    LMSTUDIO_BASE_URL,
    LMSTUDIO_MODEL,
    TINYLLM_MODEL_PATH,
)

logger = logging.getLogger("agent.llm")


class LLMProviderError(Exception):
    """Raised when a configured model provider rejects a request."""


@dataclass
class LLMResponse:
    content: str
    raw: Dict[str, Any]


class LLMProvider:
    name = "base"

    def generate(self, system: str, messages: List[Dict[str, str]]) -> LLMResponse:
        raise NotImplementedError


class TinyLLMProvider(LLMProvider):
    name = "tinyllm"

    def __init__(self, model_path: str = TINYLLM_MODEL_PATH) -> None:
        self.model_path = model_path
        self._client = None

    def _load(self) -> None:
        if self._client:
            return
        try:
            import tinyllm  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "tinyllm package is not installed. Install it or swap provider."
            ) from exc
        if not self.model_path:
            raise RuntimeError("TINYLLM_MODEL_PATH is not set.")
        self._client = tinyllm.Client(model_path=self.model_path)

    def generate(self, system: str, messages: List[Dict[str, str]]) -> LLMResponse:
        self._load()
        payload = {
            "system": system,
            "messages": messages,
        }
        result = self._client.generate(payload)  # type: ignore
        content = result.get("content", "")
        return LLMResponse(content=content, raw=result)


class MockLLMProvider(LLMProvider):
    name = "mock"

    def generate(self, system: str, messages: List[Dict[str, str]]) -> LLMResponse:
        last = messages[-1]["content"] if messages else ""
        content = (
            "{\"action\": \"respond\", \"content\": "
            "\"The model provider is offline. Echo: "
            + last.replace("\"", "'")
            + "\"}"
        )
        return LLMResponse(content=content, raw={"mock": True})


class OpenAICompatibleProvider(LLMProvider):
    name = "openai_compatible"

    def __init__(
        self,
        base_url: str = LMSTUDIO_BASE_URL,
        model: str = LMSTUDIO_MODEL,
        api_key: str = "",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model or "local-model"
        self.api_key = api_key

    def generate(self, system: str, messages: List[Dict[str, str]]) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}] + messages,
            "temperature": 0.2,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        with httpx.Client(timeout=LLM_TIMEOUT_SECONDS) as client:
            response = client.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload,
                headers=headers,
            )
            if response.is_error:
                try:
                    error_data = response.json().get("error", {})
                    error_message = error_data.get("message", "")
                except (ValueError, AttributeError):
                    error_message = ""
                detail = error_message[:300] or response.reason_phrase or "no detail"
                logger.error(
                    "LLM provider returned HTTP %s: %s", response.status_code, detail
                )
                raise LLMProviderError(
                    f"{self.name} rejected the request (HTTP {response.status_code}): {detail}"
                )
            try:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise LLMProviderError(
                    f"{self.name} returned a response without message content."
                ) from exc
        return LLMResponse(content=content, raw=data)
