"""Intelligent model routing.

Chooses a provider and model for a task based on what the task needs, which
providers are actually connected, and the user's configured preference order.
It never silently switches away from an explicit user choice.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.providers.base import ModelProvider, ProviderError
from app.providers.registry import SPEC_BY_KEY, SPECS

# Task type -> the capabilities that matter for it. Order matters: the router
# scores each connected provider's catalogue against this list.
TASK_REQUIREMENTS: dict[str, list[str]] = {
    "planning": ["reasoning", "long-context"],
    "research": ["long-context", "analysis", "reasoning"],
    "analysis": ["reasoning", "analysis"],
    "architecture": ["architecture", "reasoning", "long-context"],
    "coding": ["coding", "long-context"],
    "debugging": ["coding", "reasoning"],
    "code_review": ["coding", "reasoning", "analysis"],
    "testing": ["coding", "analysis"],
    "security": ["reasoning", "analysis"],
    "ui_design": ["reasoning"],
    "documentation": ["long-context", "general"],
    "summarisation": ["fast", "cheap", "summarisation"],
    "classification": ["fast", "cheap"],
    "branding": ["reasoning"],
    "presentation": ["general", "long-context"],
    "deployment": ["coding"],
    "default": ["general", "reasoning"],
}

# Providers that should be preferred for a given kind of work when several are
# equally capable. This encodes real trade-offs rather than vendor preference.
PROVIDER_AFFINITY: dict[str, list[str]] = {
    "coding": ["anthropic", "openai", "deepseek", "ollama"],
    "debugging": ["anthropic", "openai", "deepseek"],
    "architecture": ["anthropic", "openai", "gemini"],
    "research": ["gemini", "openai", "anthropic", "openrouter"],
    "summarisation": ["groq", "gemini", "openai", "mistral"],
    "classification": ["groq", "mistral", "openai"],
    "ui_design": ["anthropic", "openai", "gemini"],
}


@dataclass(slots=True)
class RoutingDecision:
    provider: str
    model: str
    reason: str
    alternatives: list[str]
    score: float


def _score_model(capabilities: list[str], requirements: list[str], kind: str) -> float:
    if not requirements:
        return 0.1
    hits = sum(1 for req in requirements if req in capabilities)
    score = hits / len(requirements)
    # Local models are free and private, so they win ties.
    if kind == "local":
        score += 0.05
    return score


class ModelRouter:
    """Selects the best available provider/model for a task."""

    def __init__(
        self,
        providers: dict[str, ModelProvider],
        *,
        connected: set[str] | None = None,
        preference_order: list[str] | None = None,
    ):
        self.providers = providers
        self.connected = connected or set()
        self.preference_order = preference_order or []

    def _is_available(self, key: str) -> bool:
        """A provider is usable when it is configured and (if probed) connected."""
        provider = self.providers.get(key)
        if provider is None:
            return False
        if not provider.configured:
            return False
        # If nothing has been probed yet, trust configuration alone so a first
        # run still works; a failed call falls back on the next candidate.
        if self.connected and key not in self.connected:
            return False
        return True

    def available_providers(self) -> list[str]:
        return [spec.key for spec in SPECS if self._is_available(spec.key)]

    def route(
        self,
        task_type: str,
        *,
        explicit_provider: str | None = None,
        explicit_model: str | None = None,
    ) -> RoutingDecision:
        if explicit_provider:
            if explicit_provider not in self.providers:
                raise ProviderError(
                    f"Unknown provider '{explicit_provider}'. "
                    f"Known providers: {sorted(self.providers)}.",
                    provider="router",
                    retryable=False,
                )
            # An explicit choice is honoured or refused, never silently replaced.
            if not self._is_available(explicit_provider):
                provider = self.providers[explicit_provider]
                reason = (
                    "not configured"
                    if not provider.configured
                    else "not connected (run a connection test)"
                )
                raise ProviderError(
                    f"Provider '{explicit_provider}' was selected but is {reason}.",
                    provider=explicit_provider,
                    retryable=False,
                )
            provider = self.providers[explicit_provider]
            model = explicit_model or provider.resolve_model(None)
            return RoutingDecision(
                provider=explicit_provider,
                model=model,
                reason=(
                    "Explicit user selection."
                    if explicit_model
                    else "Explicit provider selection; best model chosen for this task."
                ),
                alternatives=[],
                score=1.0,
            )

        requirements = TASK_REQUIREMENTS.get(task_type, TASK_REQUIREMENTS["default"])
        affinity = PROVIDER_AFFINITY.get(task_type, [])

        candidates: list[tuple[float, str, str, list[str]]] = []
        for spec in SPECS:
            if not self._is_available(spec.key):
                continue
            provider = self.providers[spec.key]
            catalogue = list(provider.catalogue) or list(spec.catalogue)
            if not catalogue:
                # No catalogue (e.g. OpenRouter auto) - still usable, low score.
                candidates.append((0.2, spec.key, provider.resolve_model(explicit_model), []))
                continue
            for info in catalogue:
                score = _score_model(info.strengths, requirements, provider.kind)
                if spec.key in affinity:
                    # Earlier affinity entries score slightly higher.
                    score += 0.08 * (len(affinity) - affinity.index(spec.key)) / len(affinity)
                if self.preference_order and spec.key in self.preference_order:
                    score += 0.05 * (
                        len(self.preference_order) - self.preference_order.index(spec.key)
                    ) / len(self.preference_order)
                candidates.append((score, spec.key, info.id, info.strengths))

        if not candidates:
            raise ProviderError(
                "No model provider is available. Configure at least one API key in Settings "
                "or start a local Ollama daemon.",
                provider="router",
                retryable=False,
            )

        candidates.sort(key=lambda item: item[0], reverse=True)
        best_score, best_provider, best_model, _ = candidates[0]
        alternatives = [
            f"{provider}:{model}" for _, provider, model, _ in candidates[1:4]
        ]
        reason = (
            f"Selected for '{task_type}' work: best capability match among "
            f"{len(self.available_providers())} available provider(s)."
        )
        return RoutingDecision(
            provider=best_provider,
            model=best_model,
            reason=reason,
            alternatives=alternatives,
            score=round(best_score, 4),
        )

    def fallback_chain(self, task_type: str, exclude: set[str] | None = None) -> list[tuple[str, str]]:
        """Ordered alternatives used when the primary provider call fails."""
        exclude = exclude or set()
        requirements = TASK_REQUIREMENTS.get(task_type, TASK_REQUIREMENTS["default"])
        chain: list[tuple[str, str]] = []
        for spec in SPECS:
            if spec.key in exclude or not self._is_available(spec.key):
                continue
            provider = self.providers[spec.key]
            catalogue = list(provider.catalogue) or list(spec.catalogue)
            if not catalogue:
                chain.append((spec.key, provider.resolve_model(None)))
                continue
            ranked = sorted(
                catalogue,
                key=lambda info: _score_model(info.strengths, requirements, provider.kind),
                reverse=True,
            )
            chain.append((spec.key, ranked[0].id))
        return chain


def describe_provider(key: str) -> dict[str, object]:
    spec = SPEC_BY_KEY.get(key)
    if spec is None:
        return {}
    return {
        "key": spec.key,
        "name": spec.name,
        "base_url": spec.base_url,
        "required_env": list(spec.required_env),
        "docs_url": spec.docs_url,
    }
