from dataclasses import dataclass
from typing import Any, Dict, List

import httpx

from backend.core.config import LMSTUDIO_BASE_URL, LMSTUDIO_MODEL, TINYLLM_MODEL_PATH


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
            "\"TinyLLM offline. Echo: "
            + last.replace("\"", "'")
            + "\"}"
        )
        return LLMResponse(content=content, raw={"mock": True})


class OpenAICompatibleProvider(LLMProvider):
    name = "openai_compatible"

    def __init__(self, base_url: str = LMSTUDIO_BASE_URL, model: str = LMSTUDIO_MODEL) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model or "local-model"

    def generate(self, system: str, messages: List[Dict[str, str]]) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}] + messages,
            "temperature": 0.2,
        }
        with httpx.Client(timeout=180) as client:
            response = client.post(f"{self.base_url}/v1/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
        content = data["choices"][0]["message"]["content"]
        return LLMResponse(content=content, raw=data)
