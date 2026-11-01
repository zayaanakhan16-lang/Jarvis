"""Integration registry.

One place that knows which external systems exist, what credentials each needs,
and how to build its adapter. Adding an integration means adding one entry.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.integrations.base import Integration
from app.integrations.deployment import RailwayIntegration, VercelIntegration
from app.integrations.github import GitHubIntegration
from app.integrations.opencode import OpenCodeIntegration
from app.integrations.openhands import OpenHandsIntegration
from app.integrations.research import WebSearchIntegration
from app.integrations.voice import ElevenLabsIntegration


@dataclass(frozen=True, slots=True)
class IntegrationSpec:
    key: str
    name: str
    category: str
    description: str
    required_env: tuple[str, ...]
    docs_url: str | None = None


SPECS: tuple[IntegrationSpec, ...] = (
    IntegrationSpec(
        key="openhands",
        name="OpenHands",
        category="coding_engine",
        description=(
            "Autonomous coding engine for repository work: sessions, tool activity, "
            "file changes, terminal output and results."
        ),
        required_env=("OPENHANDS_API_KEY",),
        docs_url="https://docs.all-hands.dev/",
    ),
    IntegrationSpec(
        key="opencode",
        name="OpenCode",
        category="coding_engine",
        description=(
            "Open-source alternative coding engine. Needs a running OpenCode server."
        ),
        required_env=("OPENCODE_BASE_URL",),
        docs_url="https://opencode.ai/docs/",
    ),
    IntegrationSpec(
        key="github",
        name="GitHub",
        category="source_control",
        description=(
            "Repositories, branches and pull requests. Writes require approval."
        ),
        required_env=("GITHUB_TOKEN",),
        docs_url="https://docs.github.com/en/rest",
    ),
    IntegrationSpec(
        key="web_search",
        name="Web Search",
        category="research",
        description=(
            "Live search and page retrieval for the research and hackathon agents."
        ),
        required_env=("TAVILY_API_KEY", "BRAVE_API_KEY", "SERPER_API_KEY"),
        docs_url="https://docs.tavily.com/documentation/api-reference",
    ),
    IntegrationSpec(
        key="elevenlabs",
        name="ElevenLabs",
        category="voice",
        description=(
            "Hosted speech synthesis and transcription. Browser speech APIs work "
            "without a key."
        ),
        required_env=("ELEVENLABS_API_KEY",),
        docs_url="https://elevenlabs.io/docs/api-reference",
    ),
    IntegrationSpec(
        key="vercel",
        name="Vercel",
        category="deployment",
        description="Preview and production deployments. Production needs approval.",
        required_env=("VERCEL_TOKEN",),
        docs_url="https://vercel.com/docs/rest-api",
    ),
    IntegrationSpec(
        key="railway",
        name="Railway",
        category="deployment",
        description="Backend and database hosting. Deploys require approval.",
        required_env=("RAILWAY_TOKEN",),
        docs_url="https://docs.railway.app/reference/public-api",
    ),
)

SPEC_BY_KEY = {spec.key: spec for spec in SPECS}


def _first_present(settings: Settings, names: tuple[str, ...]) -> str | None:
    for name in names:
        value = getattr(settings, name.lower(), None)
        if value:
            return value
    return None


def build_integration(key: str, settings: Settings) -> Integration:
    if key == "openhands":
        return OpenHandsIntegration(
            token=settings.openhands_api_key, base_url=settings.openhands_base_url
        )
    if key == "opencode":
        return OpenCodeIntegration(base_url=settings.opencode_base_url)
    if key == "github":
        return GitHubIntegration(token=settings.github_token)
    if key == "web_search":
        return WebSearchIntegration(
            token=_first_present(settings, ("TAVILY_API_KEY", "BRAVE_API_KEY", "SERPER_API_KEY")),
            provider=settings.search_provider,
        )
    if key == "elevenlabs":
        return ElevenLabsIntegration(token=settings.elevenlabs_api_key)
    if key == "vercel":
        return VercelIntegration(token=settings.vercel_token)
    if key == "railway":
        return RailwayIntegration(token=settings.railway_token)
    raise KeyError(f"Unknown integration '{key}'. Known: {sorted(SPEC_BY_KEY)}")


def build_all(settings: Settings) -> dict[str, Integration]:
    return {spec.key: build_integration(spec.key, settings) for spec in SPECS}
