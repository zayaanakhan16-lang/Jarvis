"""System, overview and settings routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import AGENTS, DEPARTMENTS
from app.config import get_settings
from app.database import get_session
from app.models import (
    Agent,
    Approval,
    Artifact,
    Event,
    HackathonOpportunity,
    Integration,
    Project,
    ProviderRecord,
    SettingRecord,
    Task,
    UsageRecord,
)
from app.schemas import HealthResponse, OverviewStats, SettingsOut, SettingsUpdate
from app.services.events import bus

router = APIRouter(tags=["system"])

APP_VERSION = "1.0.0"

ROUTING_KEY = "routing_preference"
PARALLEL_KEY = "max_parallel_tasks"
ENGINE_KEY = "default_engine"


async def _count(session: AsyncSession, model, *conditions) -> int:
    stmt = select(func.count()).select_from(model)
    for condition in conditions:
        stmt = stmt.where(condition)
    return int((await session.execute(stmt)).scalar_one() or 0)


@router.get("/health", response_model=HealthResponse)
async def health(session: AsyncSession = Depends(get_session)) -> HealthResponse:
    settings = get_settings()
    database = "ok"
    try:
        await session.execute(select(1))
    except Exception as exc:  # noqa: BLE001 - health must never raise
        database = f"error: {exc}"
    backend = "sqlite"
    if settings.database_url.startswith("postgres"):
        backend = "postgresql"
    return HealthResponse(
        status="ok" if database == "ok" else "degraded",
        app=settings.app_name,
        environment=settings.environment,
        database=f"{backend}: {database}",
        websocket_subscribers=bus.subscriber_count,
        version=APP_VERSION,
    )


@router.get("/overview", response_model=OverviewStats)
async def overview(session: AsyncSession = Depends(get_session)) -> OverviewStats:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    tokens = (
        await session.execute(select(func.coalesce(func.sum(UsageRecord.total_tokens), 0)))
    ).scalar_one()
    cost = (
        await session.execute(select(func.coalesce(func.sum(UsageRecord.cost_usd), 0.0)))
    ).scalar_one()
    return OverviewStats(
        projects_total=await _count(session, Project),
        projects_active=await _count(session, Project, Project.status == "active"),
        tasks_total=await _count(session, Task),
        tasks_running=await _count(session, Task, Task.status == "running"),
        tasks_completed=await _count(session, Task, Task.status == "completed"),
        tasks_failed=await _count(session, Task, Task.status == "failed"),
        tasks_waiting_approval=await _count(session, Task, Task.status == "waiting_approval"),
        agents_total=len(AGENTS),
        agents_busy=await _count(session, Agent, Agent.status == "running"),
        providers_configured=await _count(session, ProviderRecord, ProviderRecord.configured.is_(True)),
        providers_connected=await _count(session, ProviderRecord, ProviderRecord.connected.is_(True)),
        integrations_configured=await _count(session, Integration, Integration.configured.is_(True)),
        integrations_connected=await _count(session, Integration, Integration.connected.is_(True)),
        pending_approvals=await _count(session, Approval, Approval.status == "pending"),
        artifacts_total=await _count(session, Artifact),
        hackathons_tracked=await _count(session, HackathonOpportunity),
        tokens_used=int(tokens or 0),
        estimated_cost_usd=round(float(cost or 0.0), 4),
        recent_errors=await _count(
            session, Event, Event.level == "error", Event.created_at >= since
        ),
    )


@router.get("/settings", response_model=SettingsOut)
async def read_settings(session: AsyncSession = Depends(get_session)) -> SettingsOut:
    settings = get_settings()
    rows = {
        row.key: row.value
        for row in (await session.execute(select(SettingRecord))).scalars().all()
    }
    backend = "sqlite"
    if settings.database_url.startswith("postgres"):
        backend = "postgresql"
    return SettingsOut(
        routing_preference=(rows.get(ROUTING_KEY) or {}).get("value", []),
        max_parallel_tasks=int(
            (rows.get(PARALLEL_KEY) or {}).get("value", settings.max_parallel_tasks)
        ),
        default_engine=(rows.get(ENGINE_KEY) or {}).get("value", "openhands"),
        database_backend=backend,
        environment=settings.environment,
    )


async def _upsert_setting(session: AsyncSession, key: str, value) -> None:
    record = await session.get(SettingRecord, key)
    if record is None:
        session.add(SettingRecord(key=key, value={"value": value}))
    else:
        record.value = {"value": value}
    await session.commit()


@router.put("/settings", response_model=SettingsOut)
async def update_settings(
    payload: SettingsUpdate, session: AsyncSession = Depends(get_session)
) -> SettingsOut:
    if payload.routing_preference is not None:
        await _upsert_setting(session, ROUTING_KEY, payload.routing_preference)
    if payload.max_parallel_tasks is not None:
        await _upsert_setting(session, PARALLEL_KEY, payload.max_parallel_tasks)
    if payload.default_engine is not None:
        await _upsert_setting(session, ENGINE_KEY, payload.default_engine)
    return await read_settings(session)


@router.get("/departments")
async def list_departments(session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = (await session.execute(select(Agent))).scalars().all()
    by_department: dict[str, list[Agent]] = {}
    for agent in rows:
        by_department.setdefault(agent.department, []).append(agent)
    return [
        {
            "key": dept.key,
            "name": dept.name,
            "description": dept.description,
            "agent_count": len(dept.agents),
            "busy_count": sum(
                1 for a in by_department.get(dept.key, []) if a.status == "running"
            ),
        }
        for dept in DEPARTMENTS
    ]
