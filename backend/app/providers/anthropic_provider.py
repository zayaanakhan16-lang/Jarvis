"""Anthropic Messages API adapter.

Uses the documented ``/v1/messages`` contract: a top-level ``system`` field and
an explicit ``max_tokens`` requirement.
"""

from __future__ import annotations

import time
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

# Anthropic has no cheap public list-models call for every account tier, so a
# curated catalogue is used for cost estimation. Probing still makes a real
# request and reports whatever the API says.
ANTHROPIC_CATALOGUE = (
    ModelInfo(
        "claude-sonnet-4-5",
        "Claude Sonnet 4.5",
        200_000,
        3.0,
        15.0,
        ["architecture", "coding", "analysis", "long-context"],
    ),
    ModelInfo(
        "claude-opus-4-1",
        "Claude Opus 4.1",
        200_000,
        15.0,
        75.0,
        ["architecture", "deep-reasoning"],
    ),
    ModelInfo(
        "claude-haiku-4-5",
        "Claude Haiku 4.5",
        200_000,
        1.0,
        5.0,
        ["fast", "classification", "summarisation"],
    ),
)


class AnthropicProvider(ModelProvider):
    kind = "cloud"
    catalogue = ANTHROPIC_CATALOGUE

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key or "",
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    async def probe(self) -> ProbeResult:
        if not self.configured:
            return ProbeResult(
                ok=False,
                status="not_configured",
                message=f"Missing {' or '.join(self.required_env)}.",
            )
        started = time.perf_counter()
        model = self.resolve_model(None)
        body = {
            "model": model,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "ping"}],
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url.rstrip('/')}/v1/messages",
                    headers=self._headers(),
                    json=body,
                )
            self._raise_for_status(response, self.key, self.name)
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
        return ProbeResult(
            ok=True,
            status="connected",
            message="Authenticated and reachable.",
            models=[info.id for info in self.catalogue],
            latency_ms=self._elapsed_ms(started),
        )

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        self._require_key()
        model = self.resolve_model(request.model)
        started = time.perf_counter()
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        if request.system:
            body["system"] = request.system
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=20.0)) as client:
                response = await client.post(
                    f"{self.base_url.rstrip('/')}/v1/messages",
                    headers=self._headers(),
                    json=body,
                )
            self._raise_for_status(response, self.key, self.name)
            payload = response.json()
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(
                f"{self.name} request failed: {exc}", provider=self.key, retryable=True
            ) from exc

        blocks = payload.get("content") or []
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        usage = payload.get("usage") or {}
        return self._finalise(
            text=text,
            model=model,
            prompt_text=(request.system or "") + request.prompt,
            usage={
                "prompt_tokens": usage.get("input_tokens"),
                "completion_tokens": usage.get("output_tokens"),
            },
            started=started,
            raw={"stop_reason": payload.get("stop_reason")},
        )
