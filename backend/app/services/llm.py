"""LLM execution service.

Wraps provider calls with routing, retry and fallback, and records real usage.
Every attempt is logged, so a fallback is visible in the activity feed rather
than silent.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.models import ProviderRecord, UsageRecord
from app.providers.base import (
    CompletionRequest,
    CompletionResult,
    ModelProvider,
    ProviderError,
)
from app.providers.registry import build_all
from app.providers.router import ModelRouter, RoutingDecision
from app.services import events


@dataclass(slots=True)
class ExecutionOutcome:
    result: CompletionResult
    decision: RoutingDecision
    attempts: list[str]
    fallback_used: bool


class LLMService:
    """Resolves providers, routes work and executes completions."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.providers: dict[str, ModelProvider] = build_all(self.settings)

    # -- routing -----------------------------------------------------------
    async def connected_providers(self, session: AsyncSession) -> set[str]:
        """Providers that a previous probe confirmed working.

        A provider that has never been probed is not in this set; the router
        treats an unprobed-but-configured provider as usable so a first run is
        not blocked, and a failure falls through to the next candidate.
        """
        from sqlalchemy import select

        result = await session.execute(
            select(ProviderRecord).where(ProviderRecord.connected.is_(True))
        )
        return {record.key for record in result.scalars().all()}

    def build_router(
        self, connected: set[str] | None = None, preference_order: list[str] | None = None
    ) -> ModelRouter:
        return ModelRouter(
            self.providers, connected=connected or set(), preference_order=preference_order
        )

    # -- execution ---------------------------------------------------------
    async def execute(
        self,
        session: AsyncSession,
        *,
        task_type: str,
        prompt: str,
        system: str | None = None,
        explicit_provider: str | None = None,
        explicit_model: str | None = None,
        temperature: float = 0.4,
        max_tokens: int = 2048,
        json_mode: bool = False,
        project_id: str | None = None,
        task_id: str | None = None,
        agent_key: str | None = None,
        allow_fallback: bool = True,
    ) -> ExecutionOutcome:
        connected = await self.connected_providers(session)
        router = self.build_router(connected=connected)

        decision = router.route(
            task_type, explicit_provider=explicit_provider, explicit_model=explicit_model
        )

        attempts: list[str] = []
        tried: set[str] = set()
        queue: list[tuple[str, str]] = [(decision.provider, decision.model)]
        if allow_fallback and not explicit_provider:
            queue.extend(router.fallback_chain(task_type, exclude={decision.provider}))

        last_error: ProviderError | None = None
        for index, (provider_key, model) in enumerate(queue):
            if provider_key in tried:
                continue
            tried.add(provider_key)
            provider = self.providers.get(provider_key)
            if provider is None or not provider.configured:
                attempts.append(f"{provider_key}: skipped (not configured)")
                continue
            request = CompletionRequest(
                prompt=prompt,
                system=system,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=json_mode,
            )
            label = f"{provider_key}:{model}"
            try:
                result = await provider.complete(request)
            except ProviderError as exc:
                last_error = exc
                attempts.append(f"{label}: failed - {exc}")
                await events.emit(
                    session,
                    events.PROVIDER_FAILED,
                    f"{provider.name} call failed: {exc}",
                    project_id=project_id,
                    task_id=task_id,
                    agent_key=agent_key,
                    level="warning",
                    data={"provider": provider_key, "model": model, "retryable": exc.retryable},
                )
                if not allow_fallback:
                    raise
                continue
            except Exception as exc:  # noqa: BLE001 - unexpected adapter failure
                last_error = ProviderError(str(exc), provider=provider_key, retryable=True)
                attempts.append(f"{label}: failed - {exc}")
                if not allow_fallback:
                    raise last_error
                continue

            attempts.append(f"{label}: ok")
            await self._record_usage(
                session,
                result,
                project_id=project_id,
                task_id=task_id,
            )
            if index > 0:
                await events.emit(
                    session,
                    events.PROVIDER_SELECTED,
                    f"Fell back to {provider.name} ({model}) after a provider failure.",
                    project_id=project_id,
                    task_id=task_id,
                    agent_key=agent_key,
                    level="warning",
                    data={"provider": provider_key, "model": model, "fallback": True},
                )
            else:
                await events.emit(
                    session,
                    events.PROVIDER_SELECTED,
                    f"{provider.name} ({model}) handled this {task_type} task.",
                    project_id=project_id,
                    task_id=task_id,
                    agent_key=agent_key,
                    data={
                        "provider": provider_key,
                        "model": model,
                        "reason": decision.reason,
                        "fallback": False,
                    },
                )
            return ExecutionOutcome(
                result=result,
                decision=RoutingDecision(
                    provider=provider_key,
                    model=model,
                    reason=decision.reason,
                    alternatives=decision.alternatives,
                    score=decision.score,
                ),
                attempts=attempts,
                fallback_used=index > 0,
            )

        message = (
            f"No provider could complete this {task_type} task. "
            f"Attempts: {'; '.join(attempts) or 'none configured'}"
        )
        if last_error is not None:
            message = f"{message}. Last error: {last_error}"
        raise ProviderError(message, provider="llm_service", retryable=False)

    async def _record_usage(
        self,
        session: AsyncSession,
        result: CompletionResult,
        *,
        project_id: str | None,
        task_id: str | None,
    ) -> None:
        session.add(
            UsageRecord(
                id=str(uuid.uuid4()),
                project_id=project_id,
                task_id=task_id,
                provider=result.provider,
                model=result.model,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                total_tokens=result.total_tokens,
                cost_usd=result.cost_usd,
                latency_ms=result.latency_ms,
                reported=result.usage_reported,
            )
        )
        await session.commit()

    # -- probes ------------------------------------------------------------
    async def probe_provider(self, session: AsyncSession, key: str) -> ProviderRecord:
        """Run a real connectivity test and persist the outcome."""
        from datetime import datetime, timezone

        from sqlalchemy import select

        provider = self.providers.get(key)
        if provider is None:
            raise KeyError(f"Unknown provider '{key}'")

        record = (
            await session.execute(select(ProviderRecord).where(ProviderRecord.key == key))
        ).scalar_one_or_none()
        if record is None:
            record = ProviderRecord(
                key=key,
                name=provider.name,
                kind=provider.kind,
                base_url=provider.base_url,
                required_env=list(provider.required_env),
                configured=provider.configured,
            )
            session.add(record)

        probe = await provider.probe()
        record.configured = provider.configured
        record.connected = probe.ok
        record.status = probe.status
        record.last_error = None if probe.ok else probe.message
        record.last_tested_at = datetime.now(timezone.utc)
        if probe.models:
            record.models = probe.models
            record.default_model = probe.models[0]
        else:
            # Reachable but no model list returned. Keep the discovered list
            # empty rather than substituting the curated catalogue, which the
            # provider never confirmed.
            record.models = []
            record.default_model = None
        record.details = {
            "message": probe.message,
            "latency_ms": probe.latency_ms,
            "base_url": provider.base_url,
            "catalogue": [info.id for info in provider.catalogue],
        }
        await session.commit()
        await session.refresh(record)
        return record


_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
