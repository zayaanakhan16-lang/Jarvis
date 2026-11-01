"""Provider registry: the single place that knows which adapters exist.

Adding a provider means adding one entry here. The orchestrator, the routing
service, and the integrations API all read from this registry, so a new
provider becomes available everywhere at once.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.providers.anthropic_provider import AnthropicProvider
from app.providers.base import ModelInfo, ModelProvider
from app.providers.gemini_provider import GeminiProvider
from app.providers.ollama_provider import OllamaProvider
from app.providers.openai_compatible import OpenAICompatibleProvider

# Curated catalogues. Model identifiers are intentionally limited to families
# whose names are stable; ``probe()`` reports the live list, which the UI shows
# alongside the curated default so nothing is invented.
OPENAI_CATALOGUE = (
    ModelInfo("gpt-4o", "GPT-4o", 128_000, 2.5, 10.0, ["reasoning", "coding", "multimodal"]),
    ModelInfo("gpt-4o-mini", "GPT-4o mini", 128_000, 0.15, 0.6, ["fast", "cheap", "summarisation"]),
    ModelInfo("gpt-4.1", "GPT-4.1", 1_000_000, 2.0, 8.0, ["coding", "long-context"]),
    ModelInfo("o4-mini", "o4-mini", 200_000, 1.1, 4.4, ["reasoning", "maths"]),
)

DEEPSEEK_CATALOGUE = (
    ModelInfo("deepseek-chat", "DeepSeek Chat", 64_000, 0.27, 1.1, ["coding", "cheap"]),
    ModelInfo("deepseek-reasoner", "DeepSeek Reasoner", 64_000, 0.55, 2.19, ["reasoning"]),
)

MISTRAL_CATALOGUE = (
    ModelInfo("mistral-large-latest", "Mistral Large", 128_000, 2.0, 6.0, ["reasoning", "coding"]),
    ModelInfo("mistral-small-latest", "Mistral Small", 128_000, 0.2, 0.6, ["fast", "cheap"]),
)

GROQ_CATALOGUE = (
    ModelInfo("llama-3.3-70b-versatile", "Llama 3.3 70B", 128_000, 0.59, 0.79, ["fast", "general"]),
    ModelInfo("llama-3.1-8b-instant", "Llama 3.1 8B", 128_000, 0.05, 0.08, ["fast", "cheap"]),
)

OPENROUTER_CATALOGUE = (
    ModelInfo("openrouter/auto", "OpenRouter Auto", None, None, None, ["routing"]),
)


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    key: str
    name: str
    factory: str
    base_url: str | None
    required_env: tuple[str, ...]
    catalogue: tuple[ModelInfo, ...] = ()
    docs_url: str | None = None
    category: str = "model_provider"


SPECS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        key="openai",
        name="OpenAI",
        factory="openai_compatible",
        base_url="https://api.openai.com/v1",
        required_env=("OPENAI_API_KEY",),
        catalogue=OPENAI_CATALOGUE,
        docs_url="https://platform.openai.com/docs/api-reference",
    ),
    ProviderSpec(
        key="anthropic",
        name="Anthropic Claude",
        factory="anthropic",
        base_url="https://api.anthropic.com",
        required_env=("ANTHROPIC_API_KEY",),
        docs_url="https://docs.anthropic.com/en/api/messages",
    ),
    ProviderSpec(
        key="gemini",
        name="Google Gemini",
        factory="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        required_env=("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        docs_url="https://ai.google.dev/api/generate-content",
    ),
    ProviderSpec(
        key="deepseek",
        name="DeepSeek",
        factory="openai_compatible",
        base_url="https://api.deepseek.com/v1",
        required_env=("DEEPSEEK_API_KEY",),
        catalogue=DEEPSEEK_CATALOGUE,
        docs_url="https://api-docs.deepseek.com/",
    ),
    ProviderSpec(
        key="mistral",
        name="Mistral AI",
        factory="openai_compatible",
        base_url="https://api.mistral.ai/v1",
        required_env=("MISTRAL_API_KEY",),
        catalogue=MISTRAL_CATALOGUE,
        docs_url="https://docs.mistral.ai/api/",
    ),
    ProviderSpec(
        key="groq",
        name="Groq",
        factory="openai_compatible",
        base_url="https://api.groq.com/openai/v1",
        required_env=("GROQ_API_KEY",),
        catalogue=GROQ_CATALOGUE,
        docs_url="https://console.groq.com/docs/api-reference",
    ),
    ProviderSpec(
        key="openrouter",
        name="OpenRouter",
        factory="openai_compatible",
        base_url="https://openrouter.ai/api/v1",
        required_env=("OPENROUTER_API_KEY",),
        catalogue=OPENROUTER_CATALOGUE,
        docs_url="https://openrouter.ai/docs/api-reference/overview",
    ),
    ProviderSpec(
        key="ollama",
        name="Ollama (local)",
        factory="ollama",
        base_url="http://localhost:11434",
        required_env=(),
        docs_url="https://github.com/ollama/ollama/blob/main/docs/api.md",
    ),
)

SPEC_BY_KEY = {spec.key: spec for spec in SPECS}


def _base_url_for(spec: ProviderSpec, settings: Settings) -> str | None:
    """Resolve a provider's base URL, honouring an explicit override.

    ``<PROVIDER>_BASE_URL`` lets a deployment point an OpenAI-compatible
    provider at a self-hosted gateway or proxy instead of the vendor endpoint.
    """
    override = getattr(settings, f"{spec.key}_base_url", None)
    if override:
        return override
    return spec.base_url


def _credential_for(spec: ProviderSpec, settings: Settings) -> str | None:
    """Resolve the credential for a provider from settings."""
    lookup = {
        "OPENAI_API_KEY": settings.openai_api_key,
        "ANTHROPIC_API_KEY": settings.anthropic_api_key,
        "GEMINI_API_KEY": settings.effective_gemini_key,
        "GOOGLE_API_KEY": settings.effective_gemini_key,
        "DEEPSEEK_API_KEY": settings.deepseek_api_key,
        "MISTRAL_API_KEY": settings.mistral_api_key,
        "GROQ_API_KEY": settings.groq_api_key,
        "OPENROUTER_API_KEY": settings.openrouter_api_key,
    }
    for env_name in spec.required_env:
        value = lookup.get(env_name)
        if value:
            return value
    return None


def build_provider(key: str, settings: Settings) -> ModelProvider:
    """Instantiate the adapter for ``key`` using the given settings."""
    spec = SPEC_BY_KEY.get(key)
    if spec is None:
        raise KeyError(f"Unknown provider '{key}'. Known providers: {sorted(SPEC_BY_KEY)}")
    credential = _credential_for(spec, settings)
    base_url = _base_url_for(spec, settings)
    if spec.factory == "anthropic":
        provider: ModelProvider = AnthropicProvider(api_key=credential, base_url=base_url)
    elif spec.factory == "gemini":
        provider = GeminiProvider(api_key=credential, base_url=base_url)
    elif spec.factory == "ollama":
        provider = OllamaProvider(base_url=settings.ollama_base_url)
    else:
        provider = OpenAICompatibleProvider(
            api_key=credential, base_url=base_url, catalogue=spec.catalogue
        )
    # Identity always comes from the registry, so an adapter cannot misreport
    # which provider it is.
    provider.key = spec.key
    provider.name = spec.name
    provider.docs_url = spec.docs_url
    provider.required_env = spec.required_env
    return provider


def build_all(settings: Settings) -> dict[str, ModelProvider]:
    return {spec.key: build_provider(spec.key, settings) for spec in SPECS}
