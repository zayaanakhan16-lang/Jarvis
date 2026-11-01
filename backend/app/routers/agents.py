"""Agent control centre routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import AGENTS, AGENT_BY_KEY
from app.database import get_session
from app.models import Agent, Task
from app.routers._helpers import ensure_agents_seeded
from app.schemas import AgentOut, TaskOut

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[AgentOut])
async def list_agents(
    department: str | None = None,
    status: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[AgentOut]:
    await ensure_agents_seeded(session)
    stmt = select(Agent)
    if department:
        stmt = stmt.where(Agent.department == department)
    if status:
        stmt = stmt.where(Agent.status == status)
    order = {spec.key: i for i, spec in enumerate(AGENTS)}
    rows = (await session.execute(stmt)).scalars().all()
    rows.sort(key=lambda row: order.get(row.key, 999))
    return [AgentOut.model_validate(row) for row in rows]


@router.get("/{key}", response_model=AgentOut)
async def get_agent(key: str, session: AsyncSession = Depends(get_session)) -> AgentOut:
    if key not in AGENT_BY_KEY:
        raise HTTPException(status_code=404, detail=f"Unknown agent '{key}'.")
    await ensure_agents_seeded(session)
    agent = await session.get(Agent, key)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Unknown agent '{key}'.")
    return AgentOut.model_validate(agent)


@router.get("/{key}/tasks", response_model=list[TaskOut])
async def agent_tasks(
    key: str, limit: int = 25, session: AsyncSession = Depends(get_session)
) -> list[TaskOut]:
    if key not in AGENT_BY_KEY:
        raise HTTPException(status_code=404, detail=f"Unknown agent '{key}'.")
    rows = (
        await session.execute(
            select(Task)
            .where(Task.agent_key == key)
            .order_by(desc(Task.created_at))
            .limit(limit)
        )
    ).scalars().all()
    return [TaskOut.model_validate(row) for row in rows]
