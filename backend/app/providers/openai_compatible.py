"""OpenAI-compatible chat-completions adapter.

Used for OpenAI itself and for the many providers that expose the same
``/chat/completions`` contract (DeepSeek, Mistral, Groq, OpenRouter, Ollama).
One implementation, several configurations.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.providers.base import (
    CompletionRequest,
    CompletionResult,
    ModelInfo,
    ModelProvider,
    ProbeResult,
    ProviderError,
)


class OpenAICompatibleProvider(ModelProvider):
    kind = "cloud"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        catalogue: tuple[ModelInfo, ...] = (),
    ):
        super().__init__(api_key=api_key, base_url=base_url)
        if catalogue:
            self.catalogue = catalogue

    # -- headers -----------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    # -- catalogue ---------------------------------------------------------
    async def list_models(self) -> list[str]:
        url = f"{self.base_url.rstrip('/')}/models"
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(url, headers=self._headers())
            self._raise_for_status(response, self.key, self.name)
            payload = response.json()
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(
                f"Could not reach {self.name}: {exc}", provider=self.key, retryable=True
            ) from exc
        items = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            return []
        return sorted({str(item.get("id")) for item in items if item.get("id")})

    async def probe(self) -> ProbeResult:
        if not self.configured:
            return ProbeResult(
                ok=False,
                status="not_configured",
                message=f"Missing {' or '.join(self.required_env)}.",
            )
        import time

        started = time.perf_counter()
        try:
            models = await self.list_models()
        except ProviderError as exc:
            return ProbeResult(
                ok=False,
                status="error",
                message=str(exc),
                latency_ms=self._elapsed_ms(started),
            )
        latency = self._elapsed_ms(started)
        if not models:
            return ProbeResult(
                ok=False,
                status="error",
                message="Provider reachable but returned no models.",
                latency_ms=latency,
            )
        return ProbeResult(
            ok=True,
            status="connected",
            message=f"Reachable. {len(models)} models available.",
            models=models,
            latency_ms=latency,
        )

    # -- inference ---------------------------------------------------------
    def _payload(self, request: CompletionRequest, stream: bool) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.resolve_model(request.model),
            "messages": [],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": stream,
        }
        if request.system:
            body["messages"].append({"role": "system", "content": request.system})
        body["messages"].append({"role": "user", "content": request.prompt})
        if request.json_mode:
            body["response_format"] = {"type": "json_object"}
        return body

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        import time

        key = self._require_key()
        model = self.resolve_model(request.model)
        started = time.perf_counter()
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=20.0)) as client:
                response = await client.post(
                    url, headers=self._headers(), json=self._payload(request, stream=False)
                )
            self._raise_for_status(response, self.key, self.name)
            payload = response.json()
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(
                f"{self.name} request failed: {exc}", provider=self.key, retryable=True
            ) from exc

        choices = payload.get("choices") or []
        if not choices:
            raise ProviderError(
                f"{self.name} returned no choices.", provider=self.key, retryable=True
            )
        message = choices[0].get("message") or {}
        text = message.get("content") or ""
        if isinstance(text, list):
            text = "".join(part.get("text", "") for part in text if isinstance(part, dict))
        return self._finalise(
            text=text,
            model=model,
            prompt_text=(request.system or "") + request.prompt,
            usage=payload.get("usage"),
            started=started,
            raw={"id": payload.get("id"), "finish_reason": choices[0].get("finish_reason")},
        )
