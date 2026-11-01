"""Integration adapter contract.

Every external system is reached through a small adapter with the same shape:
a real connectivity test, an honest status, and typed methods. No adapter ever
reports itself connected without a successful network call.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

import httpx


class IntegrationError(RuntimeError):
    def __init__(self, message: str, *, integration: str = "", retryable: bool = False):
        super().__init__(message)
        self.integration = integration
        self.retryable = retryable


@dataclass(slots=True)
class ConnectionTest:
    ok: bool
    status: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0


class Integration(abc.ABC):
    key: str = ""
    name: str = ""
    category: str = "service"
    description: str = ""
    docs_url: str | None = None
    required_env: tuple[str, ...] = ()

    def __init__(self, token: str | None = None, base_url: str | None = None):
        self.token = token
        if base_url:
            self.base_url = base_url

    base_url: str | None = None

    @property
    def configured(self) -> bool:
        if not self.required_env:
            return True
        return bool(self.token)

    @abc.abstractmethod
    async def test_connection(self) -> ConnectionTest:
        """Perform a real request to verify credentials work."""

    def _client(self, timeout: float = 30.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout)

    @staticmethod
    def _elapsed_ms(start: float) -> int:
        import time

        return int((time.perf_counter() - start) * 1000)

    def _not_configured(self, hint: str | None = None) -> ConnectionTest:
        message = hint or f"Set {' or '.join(self.required_env)} to enable this integration."
        return ConnectionTest(ok=False, status="not_configured", message=message)

    @staticmethod
    def _error_from_response(response: httpx.Response, name: str) -> IntegrationError:
        retryable = response.status_code in (408, 429) or response.status_code >= 500
        detail = ""
        try:
            payload = response.json()
            if isinstance(payload, dict):
                detail = (
                    payload.get("message")
                    or payload.get("error_description")
                    or payload.get("detail")
                    or payload.get("error")
                    or ""
                )
                if isinstance(detail, dict):
                    detail = detail.get("message", "")
        except Exception:  # noqa: BLE001
            detail = response.text[:300]
        return IntegrationError(
            f"{name} returned HTTP {response.status_code}: {detail or 'no detail'}",
            integration=name,
            retryable=retryable,
        )
