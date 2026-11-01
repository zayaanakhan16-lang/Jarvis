"""Web research adapter.

Supports the common search APIs. When no key is configured the adapter reports
``not_configured`` and returns nothing rather than fabricating results - research
agents then state that they could not verify anything, which is the honest
outcome.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.integrations.base import ConnectionTest, Integration, IntegrationError


class WebSearchIntegration(Integration):
    key = "web_search"
    name = "Web Search"
    category = "research"
    description = (
        "Live web search and page retrieval for research agents. Works with "
        "Tavily, Brave Search or Serper."
    )
    docs_url = "https://docs.tavily.com/documentation/api-reference"
    required_env = ("TAVILY_API_KEY", "BRAVE_API_KEY", "SERPER_API_KEY")

    def __init__(
        self,
        token: str | None = None,
        *,
        provider: str | None = None,
        base_url: str | None = None,
    ):
        super().__init__(token=token, base_url=base_url)
        self.provider = provider or "tavily"

    @property
    def configured(self) -> bool:
        return bool(self.token)

    def _endpoint(self) -> str:
        if self.provider == "brave":
            return "https://api.search.brave.com/res/v1/web/search"
        if self.provider == "serper":
            return "https://google.serper.dev/search"
        return "https://api.tavily.com/search"

    async def test_connection(self) -> ConnectionTest:
        if not self.configured:
            return self._not_configured(
                "Set TAVILY_API_KEY, BRAVE_API_KEY or SERPER_API_KEY to enable live "
                "web research. Without it, research agents report that they could not "
                "verify external facts."
            )
        started = time.perf_counter()
        try:
            results = await self.search("OpenHands All Hands AI", max_results=1)
        except IntegrationError as exc:
            return ConnectionTest(ok=False, status="error", message=str(exc),
                                  latency_ms=self._elapsed_ms(started))
        return ConnectionTest(
            ok=True,
            status="connected",
            message=f"Search provider '{self.provider}' responded with {len(results)} result(s).",
            latency_ms=self._elapsed_ms(started),
            details={"provider": self.provider},
        )

    async def search(self, query: str, *, max_results: int = 5) -> list[dict[str, Any]]:
        if not self.configured:
            raise IntegrationError(
                "No web search provider is configured. Set TAVILY_API_KEY, "
                "BRAVE_API_KEY or SERPER_API_KEY.",
                integration=self.key,
            )
        headers: dict[str, str] = {"Content-Type": "application/json"}
        body: dict[str, Any] = {"query": query, "max_results": max_results}
        if self.provider == "brave":
            headers["X-Subscription-Token"] = self.token or ""
            params = {"q": query, "count": max_results}
            body = {}
        elif self.provider == "serper":
            headers["X-API-KEY"] = self.token or ""
            params = {}
            body = {"q": query, "num": max_results}
        else:
            params = {}
            body = {
                "api_key": self.token,
                "query": query,
                "max_results": max_results,
                "search_depth": "advanced",
                "include_answer": False,
            }
        try:
            async with httpx.AsyncClient(timeout=40.0) as client:
                if self.provider == "brave":
                    response = await client.get(
                        self._endpoint(), headers=headers, params=params
                    )
                else:
                    response = await client.post(
                        self._endpoint(), headers=headers, json=body
                    )
        except httpx.HTTPError as exc:
            raise IntegrationError(
                f"Search request failed: {exc}", integration=self.key, retryable=True
            ) from exc
        if response.status_code >= 400:
            raise self._error_from_response(response, self.name)
        payload = response.json()

        if self.provider == "brave":
            items = ((payload.get("web") or {}).get("results")) or []
            return [
                {
                    "title": i.get("title"),
                    "url": i.get("url"),
                    "snippet": i.get("description"),
                }
                for i in items
            ]
        if self.provider == "serper":
            items = payload.get("organic") or []
            return [
                {"title": i.get("title"), "url": i.get("link"), "snippet": i.get("snippet")}
                for i in items
            ]
        items = payload.get("results") or []
        return [
            {
                "title": i.get("title"),
                "url": i.get("url"),
                "snippet": i.get("content"),
                "score": i.get("score"),
            }
            for i in items
        ]

    async def fetch_page(self, url: str, *, max_chars: int = 8000) -> dict[str, Any]:
        """Retrieve a page's text. Used to verify claims against the source."""
        if not url.startswith(("http://", "https://")):
            raise IntegrationError("Only http(s) URLs can be fetched.", integration=self.key)
        try:
            async with httpx.AsyncClient(
                timeout=30.0, follow_redirects=True,
                headers={"User-Agent": "JARVIS/1.0 (+research verification)"},
            ) as client:
                response = await client.get(url)
        except httpx.HTTPError as exc:
            raise IntegrationError(
                f"Could not fetch {url}: {exc}", integration=self.key, retryable=True
            ) from exc
        if response.status_code >= 400:
            raise self._error_from_response(response, self.name)
        text = response.text
        # Strip scripts and styles so the model receives readable content.
        import re

        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.DOTALL | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return {
            "url": url,
            "status_code": response.status_code,
            "text": text[:max_chars],
            "truncated": len(text) > max_chars,
        }
