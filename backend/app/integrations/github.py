"""GitHub adapter.

Uses the REST API v3. Write operations (creating repositories, pushing,
opening pull requests) are exposed as *preparation* methods that return the
exact request JARVIS would make; the caller must go through the approval flow
before anything is sent. Read operations execute directly.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.integrations.base import ConnectionTest, Integration, IntegrationError


class GitHubIntegration(Integration):
    key = "github"
    name = "GitHub"
    category = "source_control"
    description = (
        "Repositories, branches and pull requests. Read operations run directly; "
        "creating repositories, pushing and opening pull requests require approval."
    )
    docs_url = "https://docs.github.com/en/rest"
    required_env = ("GITHUB_TOKEN",)

    def __init__(self, token: str | None = None, base_url: str | None = None):
        super().__init__(token=token, base_url=base_url or "https://api.github.com")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def _request(
        self, method: str, path: str, *, json_body: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> Any:
        if not self.configured:
            raise IntegrationError(
                "GitHub is not configured: set GITHUB_TOKEN.", integration=self.key
            )
        url = f"{self.base_url.rstrip('/')}{path}"
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(
                    method, url, headers=self._headers(), json=json_body
                )
        except httpx.HTTPError as exc:
            raise IntegrationError(
                f"Could not reach GitHub: {exc}", integration=self.key, retryable=True
            ) from exc
        if response.status_code >= 400:
            raise self._error_from_response(response, self.name)
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {"raw": response.text[:2000]}

    async def test_connection(self) -> ConnectionTest:
        if not self.configured:
            return self._not_configured()
        started = time.perf_counter()
        try:
            user = await self._request("GET", "/user", timeout=20.0)
        except IntegrationError as exc:
            return ConnectionTest(
                ok=False, status="error", message=str(exc),
                latency_ms=self._elapsed_ms(started),
            )
        latency = self._elapsed_ms(started)
        scopes = ""
        return ConnectionTest(
            ok=True,
            status="connected",
            message=f"Authenticated as {user.get('login', 'unknown user')}.",
            latency_ms=latency,
            details={
                "login": user.get("login"),
                "name": user.get("name"),
                "public_repos": user.get("public_repos"),
                "scopes": scopes,
            },
        )

    # -- read --------------------------------------------------------------
    async def list_repositories(self, limit: int = 20) -> list[dict[str, Any]]:
        repos = await self._request(
            "GET", f"/user/repos?per_page={max(1, min(limit, 100))}&sort=updated"
        )
        if not isinstance(repos, list):
            return []
        return [
            {
                "full_name": repo.get("full_name"),
                "private": repo.get("private"),
                "default_branch": repo.get("default_branch"),
                "html_url": repo.get("html_url"),
                "description": repo.get("description"),
                "updated_at": repo.get("updated_at"),
            }
            for repo in repos
        ]

    async def get_repository(self, full_name: str) -> dict[str, Any]:
        return await self._request("GET", f"/repos/{full_name}")

    async def list_branches(self, full_name: str, limit: int = 50) -> list[str]:
        branches = await self._request(
            "GET", f"/repos/{full_name}/branches?per_page={max(1, min(limit, 100))}"
        )
        if not isinstance(branches, list):
            return []
        return [b.get("name", "") for b in branches if b.get("name")]

    async def list_pull_requests(self, full_name: str, limit: int = 20) -> list[dict[str, Any]]:
        prs = await self._request(
            "GET",
            f"/repos/{full_name}/pulls?state=all&per_page={max(1, min(limit, 100))}",
        )
        if not isinstance(prs, list):
            return []
        return [
            {
                "number": pr.get("number"),
                "title": pr.get("title"),
                "state": pr.get("state"),
                "html_url": pr.get("html_url"),
                "head": (pr.get("head") or {}).get("ref"),
                "base": (pr.get("base") or {}).get("ref"),
                "created_at": pr.get("created_at"),
            }
            for pr in prs
        ]

    # -- writes (approval required) ---------------------------------------
    def prepare_create_repository(
        self, name: str, *, description: str = "", private: bool = True
    ) -> dict[str, Any]:
        return {
            "integration": self.key,
            "action": "create_repository",
            "requires_approval": True,
            "method": "POST",
            "path": "/user/repos",
            "body": {"name": name, "description": description, "private": private},
            "note": "This creates a repository on your GitHub account.",
        }

    def prepare_pull_request(
        self,
        full_name: str,
        *,
        title: str,
        head: str,
        base: str = "main",
        body: str = "",
        draft: bool = True,
    ) -> dict[str, Any]:
        return {
            "integration": self.key,
            "action": "open_pull_request",
            "requires_approval": True,
            "method": "POST",
            "path": f"/repos/{full_name}/pulls",
            "body": {"title": title, "head": head, "base": base, "body": body, "draft": draft},
            "note": "This opens a pull request on the repository.",
        }
