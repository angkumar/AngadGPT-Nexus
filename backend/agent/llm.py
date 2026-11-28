from dataclasses import dataclass, field
import logging
from typing import Any, Dict, List, Optional, Tuple

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
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)


class LLMProvider:
    name = "base"

    def generate(
        self,
        system: str,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> LLMResponse:
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

    def generate(
        self,
        system: str,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> LLMResponse:
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

    def generate(
        self,
        system: str,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> LLMResponse:
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
        supports_native_tools: bool = False,
        vision_model: Optional[str] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model or "local-model"
        # Used instead of `model` for turns that carry images, so a text-only
        # model such as gpt-oss is never asked to read a picture.
        self.vision_model = vision_model or None
        self.api_key = api_key
        # Hosted models such as Groq's gpt-oss are trained to emit native tool
        # calls. If the request declares no tools, Groq rejects the whole turn
        # with `tool_use_failed: Tool choice is none, but model called a tool`,
        # so forward the tool schemas instead of relying on JSON in the text.
        self.supports_native_tools = supports_native_tools

    @staticmethod
    def _has_image(messages: List[Dict[str, Any]]) -> bool:
        for message in messages:
            content = message.get("content")
            if isinstance(content, list) and any(
                isinstance(part, dict) and part.get("type") == "image_url"
                for part in content
            ):
                return True
        return False

    def generate(
        self,
        system: str,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> LLMResponse:
        model = self.model
        if self.vision_model and self._has_image(messages):
            model = self.vision_model
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [{"role": "system", "content": system}] + messages,
            "temperature": 0.2,
        }
        if tools and self.supports_native_tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
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
                message = data["choices"][0]["message"]
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise LLMProviderError(
                    f"{self.name} returned a response without message content."
                ) from exc
            content = message.get("content") or ""
            tool_calls = message.get("tool_calls") or []
            if not content and not tool_calls:
                raise LLMProviderError(
                    f"{self.name} returned a response without message content."
                )
        return LLMResponse(content=content, raw=data, tool_calls=tool_calls)
