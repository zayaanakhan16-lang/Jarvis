"""Google Gemini (Generative Language API) adapter.

Uses the documented ``v1beta`` surface:
  * ``GET  /v1beta/models?key=...``                          -> list models
  * ``POST /v1beta/models/{model}:generateContent?key=...``   -> completion

The API key is passed as a query parameter because that is the documented
mechanism for the Generative Language API.
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


class GeminiProvider(ModelProvider):
    kind = "cloud"
    default_base_url = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        super().__init__(api_key=api_key, base_url=base_url or self.default_base_url)

    async def list_models(self) -> list[str]:
        url = f"{self.base_url.rstrip('/')}/models"
        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.get(url, params={"key": self.api_key or ""})
        self._raise_for_status(response, self.key, self.name)
        payload = response.json()
        names = []
        for item in payload.get("models", []):
            name = str(item.get("name", ""))
            methods = item.get("supportedGenerationMethods") or []
            if "generateContent" in methods and name:
                names.append(name.split("/")[-1])
        return sorted(names)

    async def probe(self) -> ProbeResult:
        if not self.configured:
            return ProbeResult(
                ok=False,
                status="not_configured",
                message=f"Missing {' or '.join(self.required_env)}.",
            )
        started = time.perf_counter()
        try:
            models = await self.list_models()
        except ProviderError as exc:
            return ProbeResult(
                ok=False, status="error", message=str(exc), latency_ms=self._elapsed_ms(started)
            )
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(
                ok=False,
                status="error",
                message=f"Could not reach {self.name}: {exc}",
                latency_ms=self._elapsed_ms(started),
            )
        if not models:
            return ProbeResult(
                ok=False,
                status="error",
                message="Reachable but no generateContent models were returned.",
                latency_ms=self._elapsed_ms(started),
            )
        return ProbeResult(
            ok=True,
            status="connected",
            message=f"Reachable. {len(models)} models available.",
            models=models,
            latency_ms=self._elapsed_ms(started),
        )

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        self._require_key()
        model = self.resolve_model(request.model)
        started = time.perf_counter()
        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": request.prompt}]}],
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            },
        }
        if request.system:
            body["systemInstruction"] = {"parts": [{"text": request.system}]}
        if request.json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"
        url = f"{self.base_url.rstrip('/')}/models/{model}:generateContent"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=20.0)) as client:
                response = await client.post(url, params={"key": self.api_key}, json=body)
            self._raise_for_status(response, self.key, self.name)
            payload = response.json()
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(
                f"{self.name} request failed: {exc}", provider=self.key, retryable=True
            ) from exc

        candidates = payload.get("candidates") or []
        text = ""
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)
        usage = payload.get("usageMetadata") or {}
        return self._finalise(
            text=text,
            model=model,
            prompt_text=(request.system or "") + request.prompt,
            usage={
                "prompt_tokens": usage.get("promptTokenCount"),
                "completion_tokens": usage.get("candidatesTokenCount"),
                "total_tokens": usage.get("totalTokenCount"),
            },
            started=started,
            raw={"finish_reason": candidates[0].get("finishReason") if candidates else None},
        )
