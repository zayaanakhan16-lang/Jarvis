"""Project and project-memory routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Artifact, MemoryEntry, Project, Task
from app.routers._helpers import new_id, project_task_counts, unique_slug
from app.schemas import (
    ArtifactOut,
    MemoryCreate,
    MemoryOut,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    TaskOut,
)
from app.services import events

router = APIRouter(prefix="/projects", tags=["projects"])

VALID_STATUSES = ("planning", "active", "blocked", "completed", "archived")


async def _to_out(session: AsyncSession, project: Project) -> ProjectOut:
    total, completed = await project_task_counts(session, project.id)
    data = ProjectOut.model_validate(project)
    data.task_count = total
    data.completed_count = completed
    return data


@router.get("", response_model=list[ProjectOut])
async def list_projects(
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[ProjectOut]:
    stmt = select(Project)
    if status:
        stmt = stmt.where(Project.status == status)
    stmt = stmt.order_by(desc(Project.updated_at)).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return [await _to_out(session, row) for row in rows]


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(
    payload: ProjectCreate, session: AsyncSession = Depends(get_session)
) -> ProjectOut:
    project = Project(
        id=new_id(),
        name=payload.name.strip(),
        slug=await unique_slug(session, payload.name),
        description=payload.description,
        objective=payload.objective,
        repository=payload.repository,
        coding_engine=payload.coding_engine,
        status="planning",
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    await events.emit(
        session,
        events.PROJECT_CREATED,
        f"Project '{project.name}' created.",
        project_id=project.id,
        data={"slug": project.slug},
    )
    return await _to_out(session, project)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: str, session: AsyncSession = Depends(get_session)
) -> ProjectOut:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return await _to_out(session, project)


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: str, payload: ProjectUpdate, session: AsyncSession = Depends(get_session)
) -> ProjectOut:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    updates = payload.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid project status.")
    for field, value in updates.items():
        setattr(project, field, value)
    await session.commit()
    await session.refresh(project)
    await events.emit(
        session,
        events.PROJECT_UPDATED,
        f"Project '{project.name}' updated.",
        project_id=project.id,
        data={"fields": sorted(updates)},
    )
    return await _to_out(session, project)


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: str, session: AsyncSession = Depends(get_session)
) -> None:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    await session.delete(project)
    await session.commit()


# --- Project memory -------------------------------------------------------
@router.get("/{project_id}/memory", response_model=list[MemoryOut])
async def list_memory(
    project_id: str, session: AsyncSession = Depends(get_session)
) -> list[MemoryOut]:
    rows = (
        await session.execute(
            select(MemoryEntry)
            .where(MemoryEntry.project_id == project_id)
            .order_by(desc(MemoryEntry.updated_at))
        )
    ).scalars().all()
    return [MemoryOut.model_validate(row) for row in rows]


@router.post("/{project_id}/memory", response_model=MemoryOut, status_code=201)
async def upsert_memory(
    project_id: str, payload: MemoryCreate, session: AsyncSession = Depends(get_session)
) -> MemoryOut:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    existing = (
        await session.execute(
            select(MemoryEntry).where(
                MemoryEntry.project_id == project_id,
                MemoryEntry.category == payload.category,
                MemoryEntry.key == payload.key,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = MemoryEntry(
            id=new_id(),
            project_id=project_id,
            category=payload.category,
            key=payload.key,
            value=payload.value,
            source=payload.source,
            approved=payload.approved,
        )
        session.add(existing)
    else:
        existing.value = payload.value
        existing.source = payload.source
        existing.approved = payload.approved
    await session.commit()
    await session.refresh(existing)
    await events.emit(
        session,
        events.MEMORY_UPDATED,
        f"Memory updated: {payload.category}.{payload.key}",
        project_id=project_id,
        data={"category": payload.category, "key": payload.key},
    )
    return MemoryOut.model_validate(existing)


@router.delete("/{project_id}/memory/{entry_id}", status_code=204)
async def delete_memory(
    project_id: str, entry_id: str, session: AsyncSession = Depends(get_session)
) -> None:
    result = await session.execute(
        delete(MemoryEntry).where(
            MemoryEntry.id == entry_id, MemoryEntry.project_id == project_id
        )
    )
    await session.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Memory entry not found.")


@router.get("/{project_id}/tasks", response_model=list[TaskOut])
async def project_tasks(
    project_id: str, session: AsyncSession = Depends(get_session)
) -> list[TaskOut]:
    rows = (
        await session.execute(
            select(Task).where(Task.project_id == project_id).order_by(Task.created_at)
        )
    ).scalars().all()
    return [TaskOut.model_validate(row) for row in rows]


@router.get("/{project_id}/artifacts", response_model=list[ArtifactOut])
async def project_artifacts(
    project_id: str, session: AsyncSession = Depends(get_session)
) -> list[ArtifactOut]:
    rows = (
        await session.execute(
            select(Artifact)
            .where(Artifact.project_id == project_id)
            .order_by(desc(Artifact.created_at))
        )
    ).scalars().all()
    return [ArtifactOut.model_validate(row) for row in rows]
