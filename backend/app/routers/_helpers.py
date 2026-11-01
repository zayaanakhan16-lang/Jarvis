"""Shared router helpers."""

from __future__ import annotations

import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agent, Project, Task


def new_id() -> str:
    return str(uuid.uuid4())


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "project"


async def unique_slug(session: AsyncSession, base: str) -> str:
    slug = slugify(base)
    candidate = slug
    counter = 1
    while True:
        exists = (
            await session.execute(select(Project.id).where(Project.slug == candidate))
        ).scalar_one_or_none()
        if exists is None:
            return candidate
        counter += 1
        candidate = f"{slug}-{counter}"


async def project_task_counts(session: AsyncSession, project_id: str) -> tuple[int, int]:
    total = (
        await session.execute(
            select(func.count(Task.id)).where(Task.project_id == project_id)
        )
    ).scalar_one()
    completed = (
        await session.execute(
            select(func.count(Task.id)).where(
                Task.project_id == project_id, Task.status == "completed"
            )
        )
    ).scalar_one()
    return int(total or 0), int(completed or 0)


async def ensure_agents_seeded(session: AsyncSession) -> None:
    """Create agent rows for any registry entry that has none yet.

    Agents are real rows so status, counters and errors persist across restarts.
    """
    from app.agents.registry import AGENTS

    existing = set(
        (await session.execute(select(Agent.key))).scalars().all()
    )
    added = False
    for spec in AGENTS:
        if spec.key in existing:
            continue
        session.add(
            Agent(
                key=spec.key,
                name=spec.name,
                department=spec.department,
                description=spec.description,
                capabilities=list(spec.capabilities),
                tools=list(spec.tools),
                task_types=[spec.task_type],
                permission_scope=list(spec.permission_scope),
                status="idle",
            )
        )
        added = True
    if added:
        await session.commit()
