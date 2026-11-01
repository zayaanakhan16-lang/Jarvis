"""Integration routes.

``POST /integrations/{key}/test`` performs a real connection test and persists
the result. ``connected`` is only ever true after such a test succeeds.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_session
from app.integrations.base import IntegrationError
from app.integrations.registry import SPECS, SPEC_BY_KEY, build_all
from app.models import Integration
from app.schemas import IntegrationOut
from app.services import events

router = APIRouter(prefix="/integrations", tags=["integrations"])


def _builders():
    return build_all(get_settings())


async def _sync_records(session: AsyncSession) -> list[Integration]:
    adapters = _builders()
    existing = {
        row.key: row for row in (await session.execute(select(Integration))).scalars().all()
    }
    changed = False
    for spec in SPECS:
        adapter = adapters[spec.key]
        record = existing.get(spec.key)
        if record is None:
            record = Integration(
                key=spec.key,
                name=spec.name,
                category=spec.category,
                description=spec.description,
                docs_url=spec.docs_url,
                required_env=list(spec.required_env),
                configured=adapter.configured,
                connected=False,
                status="configured" if adapter.configured else "not_configured",
            )
            session.add(record)
            existing[spec.key] = record
            changed = True
        else:
            if record.configured != adapter.configured:
                record.configured = adapter.configured
                if not adapter.configured:
                    record.connected = False
                    record.status = "not_configured"
                    record.last_error = None
                else:
                    record.status = "configured"
                changed = True
    if changed:
        await session.commit()
    return list(existing.values())


def _to_out(record: Integration) -> IntegrationOut:
    spec = SPEC_BY_KEY.get(record.key)
    return IntegrationOut(
        key=record.key,
        name=record.name,
        category=record.category,
        description=record.description,
        docs_url=record.docs_url,
        required_env=list(record.required_env or []),
        configured=record.configured,
        connected=record.connected,
        status=record.status,
        last_tested_at=record.last_tested_at,
        last_error=record.last_error,
        details=record.details or {},
    )


@router.get("", response_model=list[IntegrationOut])
async def list_integrations(
    session: AsyncSession = Depends(get_session),
) -> list[IntegrationOut]:
    records = await _sync_records(session)
    order = {spec.key: i for i, spec in enumerate(SPECS)}
    records.sort(key=lambda r: order.get(r.key, 999))
    return [_to_out(record) for record in records]


@router.post("/{key}/test", response_model=IntegrationOut)
async def test_integration(
    key: str, session: AsyncSession = Depends(get_session)
) -> IntegrationOut:
    if key not in SPEC_BY_KEY:
        raise HTTPException(status_code=404, detail=f"Unknown integration '{key}'.")
    adapters = _builders()
    adapter = adapters[key]
    try:
        result = await adapter.test_connection()
    except IntegrationError as exc:
        result = None
        error_message = str(exc)
    except Exception as exc:  # noqa: BLE001 - adapters should not crash the API
        result = None
        error_message = f"{type(exc).__name__}: {exc}"
    else:
        error_message = None

    await _sync_records(session)
    record = (
        await session.execute(select(Integration).where(Integration.key == key))
    ).scalar_one()

    record.configured = adapter.configured
    if result is None:
        record.connected = False
        record.status = "error"
        record.last_error = error_message
        record.details = {"message": error_message}
    else:
        record.connected = result.ok
        record.status = result.status
        record.last_error = None if result.ok else result.message
        record.details = {
            "message": result.message,
            "latency_ms": result.latency_ms,
            **result.details,
        }
    record.last_tested_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(record)

    await events.emit(
        session,
        events.INTEGRATION_TESTED,
        f"{record.name} connection test: {record.status}.",
        level="info" if record.connected else "warning",
        data={"integration": key, "connected": record.connected, "status": record.status},
    )
    return _to_out(record)
