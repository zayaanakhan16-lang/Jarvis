"""Task planning and execution routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Artifact, Task
from app.schemas import (
    ArtifactOut,
    ExecuteRequest,
    ExecutionResult,
    PlanRequest,
    PlanResponse,
    RunRequest,
    TaskOut,
)
from app.agents.registry import AGENT_BY_KEY, agent_for_task_type
from app.services import events
from app.services.orchestrator import PlanError, get_orchestrator

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    project_id: str | None = None,
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[TaskOut]:
    stmt = select(Task)
    if project_id:
        stmt = stmt.where(Task.project_id == project_id)
    if status:
        stmt = stmt.where(Task.status == status)
    stmt = stmt.order_by(desc(Task.created_at)).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return [TaskOut.model_validate(row) for row in rows]


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: str, session: AsyncSession = Depends(get_session)) -> TaskOut:
    task = await session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return TaskOut.model_validate(task)


@router.post("/plan", response_model=PlanResponse)
async def create_plan(
    payload: PlanRequest, session: AsyncSession = Depends(get_session)
) -> PlanResponse:
    orchestrator = get_orchestrator()
    try:
        tasks = await orchestrator.create_plan(
            session,
            objective=payload.objective,
            project_id=payload.project_id,
            context=payload.context,
            max_tasks=payload.max_tasks,
            explicit_provider=payload.provider,
            explicit_model=payload.model,
        )
    except PlanError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    summary = None
    if tasks:
        latest = await events.recent(
            session, project_id=payload.project_id, limit=1, event_types=[events.PLAN_CREATED]
        )
        if latest:
            summary = (latest[0].data or {}).get("summary")
    return PlanResponse(
        project_id=payload.project_id,
        tasks=[TaskOut.model_validate(task) for task in tasks],
        summary=summary,
    )


@router.post("/execute", response_model=ExecutionResult)
async def execute_plan(
    payload: ExecuteRequest, session: AsyncSession = Depends(get_session)
) -> ExecutionResult:
    if not payload.task_ids and not payload.project_id:
        raise HTTPException(
            status_code=422, detail="Provide task_ids or a project_id to execute."
        )
    orchestrator = get_orchestrator()
    try:
        summary = await orchestrator.execute_plan(
            session,
            task_ids=payload.task_ids,
            project_id=payload.project_id,
            max_parallel=payload.max_parallel,
            explicit_provider=payload.provider,
            explicit_model=payload.model,
        )
    except PlanError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ExecutionResult(**summary)


@router.post("/run", response_model=TaskOut)
async def run_single_task(
    payload: RunRequest, session: AsyncSession = Depends(get_session)
) -> TaskOut:
    """Create and immediately execute one task from a direct prompt."""
    spec = AGENT_BY_KEY.get(payload.agent_key) if payload.agent_key else None
    if payload.agent_key and spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown agent '{payload.agent_key}'.")
    if spec is None:
        spec = agent_for_task_type(payload.task_type)
    if spec is None:
        raise HTTPException(
            status_code=422, detail=f"No agent handles task type '{payload.task_type}'."
        )

    task = Task(
        id=__import__("uuid").uuid4().hex,
        project_id=payload.project_id,
        title=payload.prompt.strip().splitlines()[0][:280],
        description=payload.prompt.strip(),
        task_type=payload.task_type,
        department=spec.department,
        agent_key=spec.key,
        status="pending",
        provider=payload.provider,
        model=payload.model,
        payload={"direct": True},
        depends_on=[],
    )
    session.add(task)
    await session.commit()

    orchestrator = get_orchestrator()
    await orchestrator.run_task(
        task, explicit_provider=payload.provider, explicit_model=payload.model
    )
    await session.refresh(task)
    # A failed run is a valid API result, not a server error.
    return TaskOut.model_validate(task)


@router.get("/{task_id}/artifacts", response_model=list[ArtifactOut])
async def task_artifacts(
    task_id: str, session: AsyncSession = Depends(get_session)
) -> list[ArtifactOut]:
    rows = (
        await session.execute(
            select(Artifact).where(Artifact.task_id == task_id).order_by(Artifact.created_at)
        )
    ).scalars().all()
    return [ArtifactOut.model_validate(row) for row in rows]
