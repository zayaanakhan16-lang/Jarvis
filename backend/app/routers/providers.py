"""Model provider routes.

``POST /providers/{key}/test`` performs a real network probe and persists the
result. Nothing in this router sets ``connected`` without that call succeeding.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import ProviderRecord
from app.providers.base import ProviderError
from app.providers.registry import SPECS, SPEC_BY_KEY
from app.providers.router import ModelRouter
from app.schemas import ProbeResultOut, ProviderOut, RoutePreviewRequest, RoutePreviewResponse
from app.services import events
from app.services.llm import get_llm_service

router = APIRouter(prefix="/providers", tags=["providers"])


async def _sync_records(session: AsyncSession) -> list[ProviderRecord]:
    """Ensure a row exists for every registered provider, with current config."""
    service = get_llm_service()
    existing = {
        row.key: row
        for row in (await session.execute(select(ProviderRecord))).scalars().all()
    }
    changed = False
    for spec in SPECS:
        provider = service.providers[spec.key]
        record = existing.get(spec.key)
        if record is None:
            record = ProviderRecord(
                key=spec.key,
                name=spec.name,
                kind=provider.kind,
                base_url=provider.base_url,
                required_env=list(spec.required_env),
                configured=provider.configured,
                status="configured" if provider.configured else "not_configured",
                # Nothing is discovered until a probe succeeds, so the
                # catalogue is never presented as the live model list.
                models=[],
                default_model=None,
            )
            session.add(record)
            existing[spec.key] = record
            changed = True
        else:
            if record.configured != provider.configured:
                record.configured = provider.configured
                if not provider.configured:
                    record.connected = False
                    record.status = "not_configured"
                    record.last_error = None
                else:
                    record.status = "configured"
                changed = True
    if changed:
        await session.commit()
    return list(existing.values())


def _to_out(record: ProviderRecord) -> ProviderOut:
    spec = SPEC_BY_KEY.get(record.key)
    return ProviderOut(
        key=record.key,
        name=record.name,
        kind=record.kind,
        base_url=record.base_url,
        required_env=list(record.required_env or []),
        configured=record.configured,
        connected=record.connected,
        status=record.status,
        models=list(record.models or []),
        catalogue=[info.id for info in spec.catalogue] if spec else [],
        default_model=record.default_model,
        last_tested_at=record.last_tested_at,
        last_error=record.last_error,
        details=record.details or {},
        docs_url=spec.docs_url if spec else None,
    )


@router.get("", response_model=list[ProviderOut])
async def list_providers(session: AsyncSession = Depends(get_session)) -> list[ProviderOut]:
    records = await _sync_records(session)
    order = {spec.key: i for i, spec in enumerate(SPECS)}
    records.sort(key=lambda r: order.get(r.key, 999))
    return [_to_out(record) for record in records]


@router.post("/{key}/test", response_model=ProbeResultOut)
async def test_provider(
    key: str, session: AsyncSession = Depends(get_session)
) -> ProbeResultOut:
    if key not in SPEC_BY_KEY:
        raise HTTPException(status_code=404, detail=f"Unknown provider '{key}'.")
    service = get_llm_service()
    try:
        record = await service.probe_provider(session, key)
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    await events.emit(
        session,
        events.INTEGRATION_TESTED,
        f"{record.name} connection test: {'connected' if record.connected else record.status}.",
        level="info" if record.connected else "warning",
        data={"provider": key, "connected": record.connected, "status": record.status},
    )
    return ProbeResultOut(
        key=key,
        ok=record.connected,
        status=record.status,
        message=(record.details or {}).get("message", record.last_error or ""),
        models=list(record.models or []),
        latency_ms=int((record.details or {}).get("latency_ms", 0)),
    )


@router.post("/route-preview", response_model=RoutePreviewResponse)
async def route_preview(
    payload: RoutePreviewRequest, session: AsyncSession = Depends(get_session)
) -> RoutePreviewResponse:
    """Show which provider/model the router would pick, without calling it."""
    service = get_llm_service()
    connected = await service.connected_providers(session)
    router_ = ModelRouter(service.providers, connected=connected)
    try:
        decision = router_.route(payload.task_type)
    except ProviderError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RoutePreviewResponse(
        provider=decision.provider,
        model=decision.model,
        reason=decision.reason,
        alternatives=decision.alternatives,
        score=decision.score,
    )
