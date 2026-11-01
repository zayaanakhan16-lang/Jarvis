"""Coding-engine session routes.

Delegating repository work to OpenHands creates a real sandbox and costs money,
so it is an explicit user action. Sessions are recorded so their status, UI link
and tool activity can be inspected afterwards.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_session
from app.integrations.base import IntegrationError
from app.integrations.opencode import OpenCodeIntegration
from app.integrations.openhands import OpenHandsIntegration
from app.models import CodingSession, Project
from app.routers._helpers import new_id
from app.schemas import SessionCreate, SessionOut
from app.services import events

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionOut])
async def list_sessions(
    project_id: str | None = None,
    engine: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> list[SessionOut]:
    stmt = select(CodingSession)
    if project_id:
        stmt = stmt.where(CodingSession.project_id == project_id)
    if engine:
        stmt = stmt.where(CodingSession.engine == engine)
    stmt = stmt.order_by(desc(CodingSession.created_at)).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return [SessionOut.model_validate(row) for row in rows]


@router.get("/{session_id}", response_model=SessionOut)
async def get_session_record(
    session_id: str, session: AsyncSession = Depends(get_session)
) -> SessionOut:
    record = await session.get(CodingSession, session_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return SessionOut.model_validate(record)


@router.post("", response_model=SessionOut, status_code=201)
async def create_session(
    payload: SessionCreate, session: AsyncSession = Depends(get_session)
) -> SessionOut:
    settings = get_settings()
    record = CodingSession(
        id=new_id(),
        project_id=payload.project_id,
        engine=payload.engine,
        title=payload.title or payload.task.strip().splitlines()[0][:200],
        repository=payload.repository,
        branch=payload.branch,
        status="starting",
    )
    session.add(record)
    await session.commit()

    try:
        if payload.engine == "openhands":
            engine = OpenHandsIntegration(
                token=settings.openhands_api_key, base_url=settings.openhands_base_url
            )
            result = await engine.start_conversation(
                task=payload.task,
                repository=payload.repository,
                branch=payload.branch,
                title=record.title,
            )
            record.remote_id = result["app_conversation_id"]
            record.ui_url = result["ui_url"]
            record.status = result.get("execution_status") or "started"
            record.details = {
                "start_task_id": result.get("start_task_id"),
                "sandbox_status": result.get("sandbox_status"),
            }
        elif payload.engine == "opencode":
            engine = OpenCodeIntegration(base_url=settings.opencode_base_url)
            probe = await engine.test_connection()
            if not probe.ok:
                raise IntegrationError(probe.message, integration="opencode")
            created = await engine.create_session(record.title)
            record.remote_id = str(created.get("id") or created.get("sessionID") or "")
            record.status = "started"
            record.details = {"raw": created}
        else:
            raise IntegrationError(
                f"Unknown coding engine '{payload.engine}'. Supported: openhands, opencode.",
                integration="sessions",
            )
    except IntegrationError as exc:
        record.status = "failed"
        record.details = {"error": str(exc)}
        await session.commit()
        await events.emit(
            session,
            events.ERROR,
            f"Could not start {payload.engine} session: {exc}",
            project_id=payload.project_id,
            level="error",
            data={"engine": payload.engine},
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    await session.commit()
    await session.refresh(record)
    await events.emit(
        session,
        events.SESSION_CREATED,
        f"{payload.engine} session started: {record.title}",
        project_id=record.project_id,
        data={
            "engine": record.engine,
            "remote_id": record.remote_id,
            "ui_url": record.ui_url,
        },
    )
    return SessionOut.model_validate(record)


@router.post("/{session_id}/sync", response_model=SessionOut)
async def sync_session(
    session_id: str, session: AsyncSession = Depends(get_session)
) -> SessionOut:
    """Refresh status and tool activity from the coding engine."""
    settings = get_settings()
    record = await session.get(CodingSession, session_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    if record.engine != "openhands" or not record.remote_id:
        raise HTTPException(
            status_code=422, detail="Only OpenHands sessions with a remote id can be synced."
        )
    engine = OpenHandsIntegration(
        token=settings.openhands_api_key, base_url=settings.openhands_base_url
    )
    try:
        conversation = await engine.get_conversation(record.remote_id)
        event_count = await engine.event_count(record.remote_id)
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    record.status = conversation.get("execution_status") or record.status
    record.details = {
        **(record.details or {}),
        "sandbox_status": conversation.get("sandbox_status"),
        "event_count": event_count,
        "llm_model": conversation.get("llm_model"),
    }
    from datetime import datetime, timezone

    record.last_synced_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(record)
    await events.emit(
        session,
        events.SESSION_UPDATED,
        f"Session synced: {record.title} ({record.status}, {event_count} events).",
        project_id=record.project_id,
        data={"engine": record.engine, "status": record.status, "events": event_count},
    )
    return SessionOut.model_validate(record)


@router.get("/{session_id}/events")
async def session_events(
    session_id: str, limit: int = 50, session: AsyncSession = Depends(get_session)
) -> dict:
    settings = get_settings()
    record = await session.get(CodingSession, session_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    if record.engine != "openhands" or not record.remote_id:
        raise HTTPException(
            status_code=422, detail="Only OpenHands sessions expose tool activity."
        )
    engine = OpenHandsIntegration(
        token=settings.openhands_api_key, base_url=settings.openhands_base_url
    )
    try:
        raw = await engine.list_events(record.remote_id, limit=limit)
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"session_id": record.id, "count": len(raw), "events": raw}
