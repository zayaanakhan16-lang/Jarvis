"""OpenCode adapter (alternative coding engine).

OpenCode is an open-source terminal coding agent that exposes a local HTTP
server. JARVIS treats it as a *replaceable* coding engine alongside OpenHands.

Because a local OpenCode server is only reachable when the user runs one, this
adapter reports ``not_configured`` with an actionable message rather than
pretending to be connected. The base URL is configurable so a self-hosted or
remote instance can be used.

Endpoint shape is deliberately conservative: only ``GET /`` (health) and
``GET /doc`` (OpenAPI discovery) are used for the connection test, because those
are the paths a locally running server serves by default. Task submission is
implemented against a configurable path and returns a clear error if the running
version does not expose it.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.integrations.base import ConnectionTest, Integration, IntegrationError


class OpenCodeIntegration(Integration):
    key = "opencode"
    name = "OpenCode"
    category = "coding_engine"
    description = (
        "Alternative open-source coding engine. Requires a running OpenCode "
        "server; JARVIS reports honestly when none is reachable."
    )
    docs_url = "https://opencode.ai/docs/"
    required_env = ("OPENCODE_BASE_URL",)

    def __init__(
        self,
        token: str | None = None,
        base_url: str | None = None,
        *,
        session_path: str | None = None,
    ):
        super().__init__(token=token, base_url=base_url or "http://localhost:4096")
        self.session_path = session_path or "/session"

    @property
    def configured(self) -> bool:
        # Reachability, not a credential, decides whether OpenCode is usable.
        return True

    async def test_connection(self) -> ConnectionTest:
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(f"{self.base_url.rstrip('/')}/doc")
                reachable = response.status_code < 500
        except httpx.HTTPError as exc:
            return ConnectionTest(
                ok=False,
                status="not_configured",
                message=(
                    f"No OpenCode server responded at {self.base_url}. Start one with "
                    f"`opencode serve`, or set OPENCODE_BASE_URL to a running instance. ({exc})"
                ),
                latency_ms=self._elapsed_ms(started),
            )
        if not reachable:
            return ConnectionTest(
                ok=False, status="error",
                message=f"OpenCode server at {self.base_url} returned an error status.",
                latency_ms=self._elapsed_ms(started),
            )
        return ConnectionTest(
            ok=True,
            status="connected",
            message=f"OpenCode server reachable at {self.base_url}.",
            latency_ms=self._elapsed_ms(started),
            details={"base_url": self.base_url},
        )

    async def list_sessions(self) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f"{self.base_url.rstrip('/')}{self.session_path}")
        if response.status_code >= 400:
            raise self._error_from_response(response, self.name)
        payload = response.json()
        return payload if isinstance(payload, list) else payload.get("sessions", [])

    async def create_session(self, title: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url.rstrip('/')}{self.session_path}",
                json={"title": title[:200]},
            )
        if response.status_code >= 400:
            raise self._error_from_response(response, self.name)
        return response.json()

    async def send_message(self, session_id: str, text: str) -> dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}{self.session_path}/{session_id}/message"
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(url, json={"parts": [{"type": "text", "text": text}]})
        if response.status_code >= 400:
            raise IntegrationError(
                f"OpenCode did not accept the message at {url} "
                f"(HTTP {response.status_code}). This build of OpenCode may use a "
                f"different endpoint; check `GET {self.base_url.rstrip('/')}/doc`.",
                integration=self.key,
            )
        return response.json()
