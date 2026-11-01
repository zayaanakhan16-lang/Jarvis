"""Activity feed and real-time WebSocket stream.

Events come from the persistent log only. There is no timer that fabricates
activity: if nothing is happening, the stream is silent.
"""

from __future__ import annotations

import asyncio
import contextlib

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal, get_session
from app.models import Event
from app.schemas import EventOut
from app.services.events import bus

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("", response_model=list[EventOut])
async def list_events(
    project_id: str | None = None,
    event_type: str | None = None,
    level: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[EventOut]:
    stmt = select(Event)
    if project_id:
        stmt = stmt.where(Event.project_id == project_id)
    if event_type:
        stmt = stmt.where(Event.type == event_type)
    if level:
        stmt = stmt.where(Event.level == level)
    stmt = stmt.order_by(desc(Event.created_at)).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return [EventOut.model_validate(row) for row in rows]


@router.get("/summary")
async def activity_summary(
    project_id: str | None = None, session: AsyncSession = Depends(get_session)
) -> dict:
    stmt = select(Event.type, func.count(Event.id)).group_by(Event.type)
    if project_id:
        stmt = stmt.where(Event.project_id == project_id)
    rows = (await session.execute(stmt)).all()
    return {"counts": {event_type: int(count) for event_type, count in rows}}


@router.websocket("/stream")
async def stream(websocket: WebSocket, project_id: str | None = None) -> None:
    await websocket.accept()
    queue = await bus.subscribe(project_id)
    try:
        await websocket.send_json(
            {"type": "connected", "project_id": project_id, "message": "Activity stream open."}
        )
        while True:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=25.0)
            except asyncio.TimeoutError:
                # Keep-alive only. This is not an activity event.
                await websocket.send_json({"type": "heartbeat"})
                continue
            await websocket.send_json({"type": "event", "event": payload})
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001 - the socket may already be gone
        pass
    finally:
        await bus.unsubscribe(queue, project_id)
        with contextlib.suppress(Exception):
            await websocket.close()
