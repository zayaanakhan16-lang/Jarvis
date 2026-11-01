"""Persistent activity event bus.

Every event is written to the database first, then broadcast to connected
WebSocket clients. Nothing here generates events on a timer: an event exists
only because real work produced it.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal
from app.models import Event

# --- Event type vocabulary -------------------------------------------------
TASK_CREATED = "task.created"
TASK_ASSIGNED = "task.assigned"
TASK_STARTED = "task.started"
TASK_COMPLETED = "task.completed"
TASK_FAILED = "task.failed"
TASK_CANCELLED = "task.cancelled"
PLAN_CREATED = "plan.created"
AGENT_STARTED = "agent.started"
AGENT_FINISHED = "agent.finished"
TOOL_INVOKED = "tool.invoked"
PROVIDER_SELECTED = "provider.selected"
PROVIDER_FAILED = "provider.failed"
APPROVAL_REQUESTED = "approval.requested"
APPROVAL_DECIDED = "approval.decided"
ARTIFACT_CREATED = "artifact.created"
MEMORY_UPDATED = "memory.updated"
PROJECT_CREATED = "project.created"
PROJECT_UPDATED = "project.updated"
INTEGRATION_TESTED = "integration.tested"
SESSION_CREATED = "session.created"
SESSION_UPDATED = "session.updated"
ERROR = "error"


def _serialise(event: Event) -> dict[str, Any]:
    created = event.created_at
    return {
        "id": event.id,
        "project_id": event.project_id,
        "task_id": event.task_id,
        "agent_key": event.agent_key,
        "type": event.type,
        "level": event.level,
        "message": event.message,
        "data": event.data or {},
        "created_at": created.isoformat() if isinstance(created, datetime) else created,
    }


class EventBus:
    """Fan-out hub for activity events.

    Subscribers receive events for the project they asked about. A subscriber
    with ``project_id=None`` receives every event.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, project_id: str | None = None) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        key = project_id or "*"
        async with self._lock:
            self._subscribers.setdefault(key, set()).add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue, project_id: str | None = None) -> None:
        key = project_id or "*"
        async with self._lock:
            bucket = self._subscribers.get(key)
            if bucket:
                bucket.discard(queue)
                if not bucket:
                    self._subscribers.pop(key, None)

    async def publish(self, payload: dict[str, Any]) -> None:
        """Deliver an already-persisted event to local subscribers."""
        keys = {"*"}
        if payload.get("project_id"):
            keys.add(payload["project_id"])
        async with self._lock:
            targets: list[asyncio.Queue] = []
            for key in keys:
                targets.extend(self._subscribers.get(key, ()))
        for queue in targets:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                # A slow client must not stall execution; drop the oldest frame.
                try:
                    queue.get_nowait()
                    queue.put_nowait(payload)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass

    @property
    def subscriber_count(self) -> int:
        return sum(len(bucket) for bucket in self._subscribers.values())


bus = EventBus()


async def emit(
    session: AsyncSession,
    event_type: str,
    message: str,
    *,
    project_id: str | None = None,
    task_id: str | None = None,
    agent_key: str | None = None,
    level: str = "info",
    data: dict[str, Any] | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    """Persist an event and broadcast it. Returns the serialised payload."""
    event = Event(
        id=str(uuid.uuid4()),
        project_id=project_id,
        task_id=task_id,
        agent_key=agent_key,
        type=event_type,
        level=level,
        message=message,
        data=data or {},
    )
    session.add(event)
    if commit:
        await session.commit()
        await session.refresh(event)
    payload = _serialise(event)
    await bus.publish(payload)
    return payload


async def emit_detached(
    event_type: str,
    message: str,
    *,
    project_id: str | None = None,
    task_id: str | None = None,
    agent_key: str | None = None,
    level: str = "info",
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Emit from a background task that has no request-scoped session."""
    async with SessionLocal() as session:
        return await emit(
            session,
            event_type,
            message,
            project_id=project_id,
            task_id=task_id,
            agent_key=agent_key,
            level=level,
            data=data,
        )


async def recent(
    session: AsyncSession,
    *,
    project_id: str | None = None,
    limit: int = 50,
    event_types: Iterable[str] | None = None,
) -> list[Event]:
    stmt = select(Event)
    if project_id:
        stmt = stmt.where(Event.project_id == project_id)
    if event_types:
        stmt = stmt.where(Event.type.in_(list(event_types)))
    stmt = stmt.order_by(desc(Event.created_at)).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())
