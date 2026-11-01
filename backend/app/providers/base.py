"""Model provider abstraction.

Design goals
------------
* The orchestrator depends on :class:`ModelProvider`, never on a vendor SDK.
* ``connected`` is only ever true after a real network probe succeeds.
* Failures are reported, not swallowed.
"""

from __future__ import annotations

import abc
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx


class ProviderError(RuntimeError):
    """Raised when a provider call fails.

    ``retryable`` tells the router whether falling back to another provider is
    appropriate. Authentication and bad-request failures are not retryable.
    """

    def __init__(self, message: str, *, provider: str = "", retryable: bool = False):
        super().__init__(message)
        self.provider = provider
        self.retryable = retryable


@dataclass(slots=True)
class ModelInfo:
    id: str
    label: str
    context_window: int | None = None
    input_cost_per_mtok: float | None = None
    output_cost_per_mtok: float | None = None
    strengths: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CompletionRequest:
    prompt: str
    system: str | None = None
    model: str | None = None
    temperature: float = 0.4
    max_tokens: int = 2048
    json_mode: bool = False


@dataclass(slots=True)
class CompletionResult:
    text: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    #: True when the provider returned real token accounting; false when the
    #: numbers are a local estimate. The UI surfaces this distinction.
    usage_reported: bool = False
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProbeResult:
    ok: bool
    status: str
    message: str
    models: list[str] = field(default_factory=list)
    latency_ms: int = 0


def estimate_tokens(text: str) -> int:
    """Rough token estimate used only when a provider reports no usage."""
    if not text:
        return 0
    return max(1, len(text) // 4)


class ModelProvider(abc.ABC):
    """Base class for every provider adapter."""

    key: str = ""
    name: str = ""
    kind: str = "cloud"
    base_url: str | None = None
    docs_url: str | None = None
    required_env: tuple[str, ...] = ()
    supports_streaming: bool = True
    #: Static catalogue used when a provider has no cheap list-models endpoint.
    catalogue: tuple[ModelInfo, ...] = ()

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key
        if base_url:
            self.base_url = base_url

    # -- lifecycle ---------------------------------------------------------
    @property
    def configured(self) -> bool:
        """True when the credentials this adapter needs are present."""
        return bool(self.api_key)

    @abc.abstractmethod
    async def probe(self) -> ProbeResult:
        """Perform a real, cheap request to confirm the provider works."""

    # -- inference ---------------------------------------------------------
    @abc.abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResult:
        """Run a single non-streaming completion."""

    async def stream(self, request: CompletionRequest) -> AsyncIterator[str]:
        """Stream a completion. Default implementation degrades to one chunk."""
        result = await self.complete(request)
        yield result.text

    def resolve_model(self, requested: str | None) -> str:
        if requested:
            return requested
        if self.catalogue:
            return self.catalogue[0].id
        return ""

    def model_info(self, model_id: str) -> ModelInfo | None:
        for info in self.catalogue:
            if info.id == model_id:
                return info
        return None

    def estimate_cost(self, model_id: str, prompt_tokens: int, completion_tokens: int) -> float:
        info = self.model_info(model_id)
        if not info or info.input_cost_per_mtok is None:
            return 0.0
        inp = (prompt_tokens / 1_000_000) * info.input_cost_per_mtok
        out = (completion_tokens / 1_000_000) * (info.output_cost_per_mtok or 0.0)
        return round(inp + out, 6)

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _elapsed_ms(start: float) -> int:
        return int((time.perf_counter() - start) * 1000)

    def _finalise(
        self,
        *,
        text: str,
        model: str,
        prompt_text: str,
        usage: dict[str, Any] | None,
        started: float,
        raw: dict[str, Any] | None = None,
    ) -> CompletionResult:
        reported = bool(usage and (usage.get("total_tokens") or usage.get("prompt_tokens")))
        if reported:
            prompt_tokens = int(usage.get("prompt_tokens") or 0)
            completion_tokens = int(usage.get("completion_tokens") or 0)
            total = int(usage.get("total_tokens") or prompt_tokens + completion_tokens)
        else:
            prompt_tokens = estimate_tokens(prompt_text)
            completion_tokens = estimate_tokens(text)
            total = prompt_tokens + completion_tokens
        return CompletionResult(
            text=text,
            provider=self.key,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            cost_usd=self.estimate_cost(model, prompt_tokens, completion_tokens),
            latency_ms=self._elapsed_ms(started),
            usage_reported=reported,
            raw=raw or {},
        )

    def _require_key(self) -> str:
        if not self.api_key:
            raise ProviderError(
                f"{self.name} is not configured: set {' or '.join(self.required_env)}.",
                provider=self.key,
                retryable=False,
            )
        return self.api_key

    @staticmethod
    def _raise_for_status(response: httpx.Response, provider: str, name: str) -> None:
        if response.status_code < 400:
            return
        retryable = response.status_code in (408, 409, 425, 429) or response.status_code >= 500
        detail = ""
        try:
            body = response.json()
            detail = (
                body.get("error", {}).get("message")
                if isinstance(body.get("error"), dict)
                else body.get("error") or body.get("message") or body.get("detail") or ""
            )
        except Exception:  # noqa: BLE001 - body may not be JSON
            detail = response.text[:300]
        raise ProviderError(
            f"{name} returned HTTP {response.status_code}: {detail or 'no detail'}",
            provider=provider,
            retryable=retryable,
        )
