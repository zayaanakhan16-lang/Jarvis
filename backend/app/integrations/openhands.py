"""OpenHands Cloud adapter.

Targets the documented V1 app-server API, verified against
``https://app.all-hands.dev/api/v1``:

  * ``GET  /users/me``                        - validate credentials
  * ``GET  /app-conversations/search``        - list conversations
  * ``GET  /app-conversations``               - fetch conversations by id
  * ``POST /app-conversations``               - start a conversation
  * ``GET  /app-conversations/start-tasks``   - poll async startup
  * ``GET  /conversation/{id}/events/search`` - read conversation events
  * ``GET  /sandboxes/search``                - list sandboxes

Start-up is asynchronous: the POST may return a start-task whose
``app_conversation_id`` becomes available after polling. That distinction is
handled explicitly here because conflating the two produces 404s.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from app.integrations.base import ConnectionTest, Integration, IntegrationError


class OpenHandsIntegration(Integration):
    key = "openhands"
    name = "OpenHands"
    category = "coding_engine"
    description = (
        "Autonomous coding engine. JARVIS delegates repository work to OpenHands "
        "sandboxes and reads back tool activity, file changes and results."
    )
    docs_url = "https://docs.all-hands.dev/"
    required_env = ("OPENHANDS_API_KEY",)

    def __init__(self, token: str | None = None, base_url: str | None = None):
        super().__init__(token=token, base_url=base_url or "https://app.all-hands.dev")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _request(
        self, method: str, path: str, *, json_body: dict[str, Any] | None = None,
        timeout: float = 60.0,
    ) -> dict[str, Any]:
        if not self.configured:
            raise IntegrationError(
                "OpenHands is not configured: set OPENHANDS_API_KEY.",
                integration=self.key,
            )
        url = f"{self.base_url.rstrip('/')}{path}"
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(
                    method, url, headers=self._headers(), json=json_body
                )
        except httpx.HTTPError as exc:
            raise IntegrationError(
                f"Could not reach OpenHands: {exc}", integration=self.key, retryable=True
            ) from exc
        if response.status_code >= 400:
            raise self._error_from_response(response, self.name)
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {"raw": response.text[:2000]}

    # -- capability probes -------------------------------------------------
    async def test_connection(self) -> ConnectionTest:
        if not self.configured:
            return self._not_configured()
        started = time.perf_counter()
        try:
            me = await self._request("GET", "/api/v1/users/me", timeout=25.0)
        except IntegrationError as exc:
            return ConnectionTest(
                ok=False, status="error", message=str(exc),
                latency_ms=self._elapsed_ms(started),
            )
        latency = self._elapsed_ms(started)
        return ConnectionTest(
            ok=True,
            status="connected",
            message="Authenticated against the OpenHands Cloud API.",
            latency_ms=latency,
            details={
                "user_id": me.get("id") or me.get("user_id"),
                "github_login": me.get("github_login"),
                "base_url": self.base_url,
            },
        )

    # -- conversations -----------------------------------------------------
    async def list_conversations(self, limit: int = 10) -> list[dict[str, Any]]:
        payload = await self._request(
            "GET", f"/api/v1/app-conversations/search?limit={max(1, min(limit, 50))}"
        )
        items = payload.get("items")
        return items if isinstance(items, list) else []

    async def get_conversation(self, conversation_id: str) -> dict[str, Any]:
        payload = await self._request(
            "GET", f"/api/v1/app-conversations?ids={conversation_id}"
        )
        items = payload.get("items")
        if isinstance(items, list) and items:
            return items[0]
        raise IntegrationError(
            f"Conversation {conversation_id} was not found.", integration=self.key
        )

    async def start_conversation(
        self,
        *,
        task: str,
        repository: str | None = None,
        branch: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Start a conversation and resolve the real conversation id.

        Returns a dict with ``app_conversation_id``, ``start_task_id`` and
        ``ui_url``. Polling is bounded so a stuck sandbox surfaces as an error
        instead of hanging the request.
        """
        body: dict[str, Any] = {
            "initial_message": {"content": [{"type": "text", "text": task}]},
        }
        if repository:
            body["selected_repository"] = repository
        if branch:
            body["selected_branch"] = branch
        if title:
            body["title"] = title[:200]

        created = await self._request("POST", "/api/v1/app-conversations", json_body=body)
        start_task_id = created.get("id")
        conversation_id = created.get("app_conversation_id")

        if not conversation_id and start_task_id:
            conversation_id = await self._poll_start_task(str(start_task_id))
        if not conversation_id:
            raise IntegrationError(
                "OpenHands accepted the request but returned no conversation id. "
                f"Raw response keys: {sorted(created.keys())}",
                integration=self.key,
                retryable=True,
            )

        record = await self.get_conversation(str(conversation_id))
        ui_url = record.get("conversation_ui_url") or (
            f"{self.base_url.rstrip('/')}/conversations/{conversation_id}"
        )
        return {
            "app_conversation_id": str(conversation_id),
            "start_task_id": str(start_task_id) if start_task_id else None,
            "ui_url": ui_url,
            "sandbox_status": record.get("sandbox_status"),
            "execution_status": record.get("execution_status"),
            "record": record,
        }

    async def _poll_start_task(
        self, start_task_id: str, *, attempts: int = 12, delay: float = 2.5
    ) -> str | None:
        for _ in range(attempts):
            payload = await self._request(
                "GET", f"/api/v1/app-conversations/start-tasks?ids={start_task_id}"
            )
            items = payload.get("items") if isinstance(payload, dict) else None
            candidate = None
            if isinstance(items, list) and items:
                candidate = items[0]
            elif isinstance(payload, dict):
                candidate = payload
            if candidate:
                if candidate.get("app_conversation_id"):
                    return str(candidate["app_conversation_id"])
                if candidate.get("status") in ("ERROR", "FAILED"):
                    raise IntegrationError(
                        f"OpenHands failed to start the conversation: "
                        f"{candidate.get('error') or candidate.get('detail') or 'unknown error'}",
                        integration=self.key,
                    )
            await asyncio.sleep(delay)
        return None

    async def list_events(self, conversation_id: str, limit: int = 50) -> list[dict[str, Any]]:
        payload = await self._request(
            "GET",
            f"/api/v1/conversation/{conversation_id}/events/search?limit={max(1, min(limit, 200))}",
        )
        items = payload.get("items")
        return items if isinstance(items, list) else []

    async def event_count(self, conversation_id: str) -> int:
        payload = await self._request(
            "GET", f"/api/v1/conversation/{conversation_id}/events/count"
        )
        count = payload.get("count") if isinstance(payload, dict) else None
        return int(count) if isinstance(count, (int, float)) else 0

    async def list_sandboxes(self, limit: int = 10) -> list[dict[str, Any]]:
        payload = await self._request(
            "GET", f"/api/v1/sandboxes/search?limit={max(1, min(limit, 50))}"
        )
        items = payload.get("items")
        return items if isinstance(items, list) else []
