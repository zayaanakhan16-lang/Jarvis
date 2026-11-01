"""Ollama adapter for local models.

Ollama needs no API key, so ``configured`` reflects reachability of the local
daemon rather than the presence of a credential. A local daemon that is not
running reports ``not_configured`` with an explanatory message instead of a
misleading "connected".
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.providers.base import (
    CompletionRequest,
    CompletionResult,
    ModelProvider,
    ProbeResult,
    ProviderError,
)


class OllamaProvider(ModelProvider):
    kind = "local"
    default_base_url = "http://localhost:11434"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        # api_key is unused by Ollama; base_url carries the daemon address.
        super().__init__(api_key="local", base_url=base_url or self.default_base_url)

    async def list_models(self) -> list[str]:
        url = f"{self.base_url.rstrip('/')}/api/tags"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
        self._raise_for_status(response, self.key, self.name)
        payload = response.json()
        return sorted(m.get("name", "") for m in payload.get("models", []) if m.get("name"))

    async def probe(self) -> ProbeResult:
        started = time.perf_counter()
        try:
            models = await self.list_models()
        except Exception as exc:  # noqa: BLE001 - daemon down is the common case
            return ProbeResult(
                ok=False,
                status="not_configured",
                message=(
                    f"Ollama daemon not reachable at {self.base_url}. "
                    f"Start it with `ollama serve`. ({exc})"
                ),
                latency_ms=self._elapsed_ms(started),
            )
        if not models:
            return ProbeResult(
                ok=False,
                status="not_configured",
                message="Ollama is running but no models are pulled. Try `ollama pull llama3.2`.",
                latency_ms=self._elapsed_ms(started),
            )
        return ProbeResult(
            ok=True,
            status="connected",
            message=f"Local daemon reachable. {len(models)} models installed.",
            models=models,
            latency_ms=self._elapsed_ms(started),
        )

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        model = self.resolve_model(request.model)
        if not model:
            raise ProviderError(
                "No Ollama model selected and none installed.", provider=self.key
            )
        started = time.perf_counter()
        body: dict[str, Any] = {
            "model": model,
            "prompt": request.prompt,
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }
        if request.system:
            body["system"] = request.system
        if request.json_mode:
            body["format"] = "json"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=10.0)) as client:
                response = await client.post(
                    f"{self.base_url.rstrip('/')}/api/generate", json=body
                )
            self._raise_for_status(response, self.key, self.name)
            payload = response.json()
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(
                f"Ollama request failed: {exc}", provider=self.key, retryable=True
            ) from exc
        return self._finalise(
            text=payload.get("response", ""),
            model=model,
            prompt_text=(request.system or "") + request.prompt,
            usage={
                "prompt_tokens": payload.get("prompt_eval_count"),
                "completion_tokens": payload.get("eval_count"),
            },
            started=started,
            raw={"done_reason": payload.get("done_reason")},
        )
