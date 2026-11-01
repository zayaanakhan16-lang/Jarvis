"""Deployment integrations: Vercel and Railway.

Both are preparation-first. Connection tests and read operations run directly;
deploying is always returned as a prepared action that needs approval.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.integrations.base import ConnectionTest, Integration, IntegrationError


class VercelIntegration(Integration):
    key = "vercel"
    name = "Vercel"
    category = "deployment"
    description = (
        "Preview and production deployments. JARVIS prepares deployments; "
        "publishing to production always requires approval."
    )
    docs_url = "https://vercel.com/docs/rest-api"
    required_env = ("VERCEL_TOKEN",)

    def __init__(self, token: str | None = None, base_url: str | None = None):
        super().__init__(token=token, base_url=base_url or "https://api.vercel.com")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    async def _get(self, path: str, timeout: float = 25.0) -> Any:
        if not self.configured:
            raise IntegrationError("Vercel is not configured: set VERCEL_TOKEN.", integration=self.key)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(
                    f"{self.base_url.rstrip('/')}{path}", headers=self._headers()
                )
        except httpx.HTTPError as exc:
            raise IntegrationError(
                f"Could not reach Vercel: {exc}", integration=self.key, retryable=True
            ) from exc
        if response.status_code >= 400:
            raise self._error_from_response(response, self.name)
        try:
            return response.json()
        except ValueError:
            return {}

    async def test_connection(self) -> ConnectionTest:
        if not self.configured:
            return self._not_configured()
        started = time.perf_counter()
        try:
            user = await self._get("/v2/user")
        except IntegrationError as exc:
            return ConnectionTest(ok=False, status="error", message=str(exc),
                                  latency_ms=self._elapsed_ms(started))
        account = user.get("user") if isinstance(user, dict) else {}
        return ConnectionTest(
            ok=True,
            status="connected",
            message=f"Authenticated as {account.get('username') or account.get('email') or 'account'}.",
            latency_ms=self._elapsed_ms(started),
            details={"username": account.get("username"), "email": account.get("email")},
        )

    async def list_projects(self, limit: int = 20) -> list[dict[str, Any]]:
        payload = await self._get(f"/v9/projects?limit={max(1, min(limit, 100))}")
        projects = payload.get("projects") if isinstance(payload, dict) else None
        if not isinstance(projects, list):
            return []
        return [
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "framework": p.get("framework"),
                "updated_at": p.get("updatedAt"),
            }
            for p in projects
        ]

    def prepare_deployment(self, project: str, *, target: str = "preview") -> dict[str, Any]:
        return {
            "integration": self.key,
            "action": "deploy",
            "requires_approval": target == "production",
            "target": target,
            "project": project,
            "note": (
                "Production deployments require approval. Preview deployments are safe to "
                "run once you have reviewed the build."
            ),
        }


class RailwayIntegration(Integration):
    key = "railway"
    name = "Railway"
    category = "deployment"
    description = (
        "Backend and database hosting. Connection uses the Railway GraphQL API; "
        "deploying a service requires approval."
    )
    docs_url = "https://docs.railway.app/reference/public-api"
    required_env = ("RAILWAY_TOKEN",)

    def __init__(self, token: str | None = None, base_url: str | None = None):
        super().__init__(
            token=token, base_url=base_url or "https://backboard.railway.app/graphql/v2"
        )

    async def _graphql(self, query: str, variables: dict[str, Any] | None = None,
                       timeout: float = 25.0) -> dict[str, Any]:
        if not self.configured:
            raise IntegrationError(
                "Railway is not configured: set RAILWAY_TOKEN.", integration=self.key
            )
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    self.base_url, headers=headers, json={"query": query, "variables": variables or {}}
                )
        except httpx.HTTPError as exc:
            raise IntegrationError(
                f"Could not reach Railway: {exc}", integration=self.key, retryable=True
            ) from exc
        if response.status_code >= 400:
            raise self._error_from_response(response, self.name)
        payload = response.json()
        if payload.get("errors"):
            message = "; ".join(e.get("message", "unknown") for e in payload["errors"])
            raise IntegrationError(f"Railway API error: {message}", integration=self.key)
        return payload.get("data") or {}

    async def test_connection(self) -> ConnectionTest:
        if not self.configured:
            return self._not_configured()
        started = time.perf_counter()
        try:
            data = await self._graphql("query { me { id email name } }")
        except IntegrationError as exc:
            return ConnectionTest(ok=False, status="error", message=str(exc),
                                  latency_ms=self._elapsed_ms(started))
        me = data.get("me") or {}
        if not me:
            return ConnectionTest(
                ok=False, status="error",
                message="Railway responded but returned no account. The token may lack access.",
                latency_ms=self._elapsed_ms(started),
            )
        return ConnectionTest(
            ok=True,
            status="connected",
            message=f"Authenticated as {me.get('email') or me.get('name') or 'account'}.",
            latency_ms=self._elapsed_ms(started),
            details={"id": me.get("id"), "email": me.get("email"), "name": me.get("name")},
        )

    async def list_projects(self) -> list[dict[str, Any]]:
        data = await self._graphql(
            "query { me { projects { edges { node { id name } } } } }"
        )
        edges = ((data.get("me") or {}).get("projects") or {}).get("edges") or []
        return [{"id": e["node"].get("id"), "name": e["node"].get("name")} for e in edges]

    def prepare_deployment(self, service_id: str, environment_id: str) -> dict[str, Any]:
        return {
            "integration": self.key,
            "action": "deploy",
            "requires_approval": True,
            "service_id": service_id,
            "environment_id": environment_id,
            "note": "Deploying to Railway changes a running service and requires approval.",
        }
