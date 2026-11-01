"""Agent registry, department integrity and model routing."""

from __future__ import annotations

import pytest

from app.agents.registry import (
    AGENTS,
    AGENT_BY_KEY,
    DEPARTMENT_BY_KEY,
    DEPARTMENTS,
    agent_for_task_type,
)
from app.providers.base import ProviderError
from app.providers.registry import SPECS, SPEC_BY_KEY, build_all
from app.providers.router import ModelRouter
from app.services import prompts


def test_every_agent_key_is_unique():
    keys = [spec.key for spec in AGENTS]
    assert len(keys) == len(set(keys)), "duplicate agent keys"


def test_agent_lookup_matches_tuple():
    assert len(AGENT_BY_KEY) == len(AGENTS)
    for spec in AGENTS:
        assert AGENT_BY_KEY[spec.key] is spec


def test_every_agent_belongs_to_a_real_department():
    for spec in AGENTS:
        assert spec.department in DEPARTMENT_BY_KEY, (
            f"agent {spec.key} references unknown department {spec.department}"
        )


def test_every_department_agent_key_resolves():
    for department in DEPARTMENTS:
        assert department.agents, f"department {department.key} has no agents"
        for key in department.agents:
            assert key in AGENT_BY_KEY, (
                f"department {department.key} lists unknown agent {key}"
            )


def test_departments_cover_all_agents():
    listed = {key for dept in DEPARTMENTS for key in dept.agents}
    assert listed == set(AGENT_BY_KEY), "some agents are not in any department"


def test_every_agent_handles_a_known_task_type():
    for spec in AGENTS:
        assert spec.task_type in prompts.TASK_TEMPLATES, (
            f"agent {spec.key} declares unknown task type {spec.task_type}"
        )


def test_agents_have_capabilities_and_descriptions():
    for spec in AGENTS:
        assert spec.capabilities, f"agent {spec.key} has no capabilities"
        assert len(spec.description) > 10, f"agent {spec.key} description too short"


def test_agent_for_task_type_returns_a_real_agent():
    for task_type in prompts.TASK_TEMPLATES:
        spec = agent_for_task_type(task_type)
        assert spec is not None, f"no agent handles task type {task_type}"
        assert spec.key in AGENT_BY_KEY


def test_agent_for_unknown_task_type_returns_none():
    assert agent_for_task_type("definitely_not_a_task_type") is None


def test_roster_size_is_substantial():
    assert len(AGENTS) >= 30
    assert len(DEPARTMENTS) >= 8


# --- Provider registry ----------------------------------------------------
def test_every_provider_spec_is_unique():
    keys = [spec.key for spec in SPECS]
    assert len(keys) == len(set(keys))


def test_every_provider_has_a_required_env_or_local_default():
    for spec in SPECS:
        if spec.factory == "ollama":
            continue
        assert spec.required_env, f"provider {spec.key} declares no credential"


def test_catalogue_model_ids_are_non_empty():
    for spec in SPECS:
        for info in spec.catalogue:
            assert info.id and info.id == info.id.strip()


def test_build_all_returns_an_adapter_per_spec():
    from app.config import get_settings

    providers = build_all(get_settings())
    assert set(providers) == {spec.key for spec in SPECS}
    for spec in SPECS:
        assert providers[spec.key].key == spec.key


def test_unconfigured_providers_report_not_configured():
    from app.config import get_settings

    providers = build_all(get_settings())
    for spec in SPECS:
        if spec.factory == "ollama":
            continue
        assert providers[spec.key].configured is False, (
            f"{spec.key} should be unconfigured with no credentials set"
        )


def test_ollama_is_configured_without_a_credential():
    """Ollama is local: it needs no API key, only a reachable daemon."""
    from app.config import get_settings

    providers = build_all(get_settings())
    assert providers["ollama"].configured is True


# --- Routing --------------------------------------------------------------
def _router_with(connected: list[str]):
    """Build a router whose named providers are both configured and connected.

    Credentials are synthetic: no network call is made, the router only inspects
    configuration and the connected set.
    """
    from app.config import Settings

    settings = Settings(
        openai_api_key="test",
        anthropic_api_key="test",
        gemini_api_key="test",
        deepseek_api_key="test",
        mistral_api_key="test",
        groq_api_key="test",
        openrouter_api_key="test",
        ollama_base_url="http://127.0.0.1:1",
    )
    providers = build_all(settings)
    # Keep only the providers the test declares as connected, so availability
    # reflects a real probe result rather than "everything is configured".
    return ModelRouter(providers, connected=set(connected))


def _router_local_only():
    """Only the local Ollama daemon is a candidate: no cloud credential is set."""
    from app.config import Settings

    settings = Settings(ollama_base_url="http://127.0.0.1:1")
    return ModelRouter(build_all(settings), connected=set())


def test_local_only_routing_selects_ollama():
    """With no cloud credentials, Ollama is the sole candidate.

    Ollama is 'configured' without a key because it is local. Whether it can
    actually serve a request is decided by the real call, which reports the
    failure honestly rather than this router inventing a provider.
    """
    router = _router_local_only()
    decision = router.route("coding")
    assert decision.provider == "ollama"


def test_routing_never_returns_an_unconfigured_provider():
    router = _router_local_only()
    decision = router.route("coding")
    assert router.providers[decision.provider].configured is True


def test_configured_providers_are_usable_before_any_probe():
    """A first run must work: configuration alone is trusted until a probe runs."""
    router = _router_with([])
    decision = router.route("coding")
    assert decision.provider in {"openai", "anthropic", "gemini", "deepseek",
                                 "mistral", "groq", "openrouter"}


def test_probed_connected_set_restricts_available_providers():
    router = _router_with(["groq"])
    assert router.available_providers() == ["groq"]


def test_routing_prefers_a_connected_provider():
    router = _router_with(["openai"])
    decision = router.route("coding")
    assert decision.provider == "openai"
    assert decision.model
    assert decision.reason


def test_routing_respects_explicit_provider_choice():
    router = _router_with(["openai", "groq"])
    decision = router.route("coding", explicit_provider="groq")
    assert decision.provider == "groq"
    assert decision.model


def test_explicit_provider_and_model_are_both_honoured():
    router = _router_with(["openai", "groq"])
    decision = router.route(
        "coding", explicit_provider="groq", explicit_model="llama-3.3-70b-versatile"
    )
    assert decision.provider == "groq"
    assert decision.model == "llama-3.3-70b-versatile"


def test_routing_rejects_unknown_explicit_provider():
    router = _router_with(["openai"])
    with pytest.raises(ProviderError):
        router.route("coding", explicit_provider="does_not_exist")


def test_routing_rejects_explicit_provider_that_is_not_connected():
    router = _router_with(["openai"])
    with pytest.raises(ProviderError) as excinfo:
        router.route("coding", explicit_provider="groq")
    assert "not connected" in str(excinfo.value).lower()


def test_routing_is_deterministic():
    router = _router_with(["openai", "groq", "deepseek"])
    first = router.route("coding")
    second = router.route("coding")
    assert (first.provider, first.model) == (second.provider, second.model)


def test_every_task_type_can_be_routed_when_a_provider_is_connected():
    router = _router_with(["openai"])
    for task_type in prompts.TASK_TEMPLATES:
        decision = router.route(task_type)
        assert decision.model


def test_fallback_chain_excludes_the_primary():
    router = _router_with(["openai", "groq", "deepseek"])
    chain = router.fallback_chain("coding", exclude={"openai"})
    keys = [key for key, _model in chain]
    assert "openai" not in keys
    assert keys, "expected at least one fallback"
    assert all(key in SPEC_BY_KEY for key in keys)
    assert all(model for _key, model in chain)
