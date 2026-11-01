"""Artifact routes: structured outputs produced by tasks."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Artifact
from app.schemas import ArtifactOut

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.get("", response_model=list[ArtifactOut])
async def list_artifacts(
    project_id: str | None = None,
    kind: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[ArtifactOut]:
    stmt = select(Artifact)
    if project_id:
        stmt = stmt.where(Artifact.project_id == project_id)
    if kind:
        stmt = stmt.where(Artifact.kind == kind)
    stmt = stmt.order_by(desc(Artifact.created_at)).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return [ArtifactOut.model_validate(row) for row in rows]


@router.get("/{artifact_id}", response_model=ArtifactOut)
async def get_artifact(
    artifact_id: str, session: AsyncSession = Depends(get_session)
) -> ArtifactOut:
    artifact = await session.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    return ArtifactOut.model_validate(artifact)


@router.post("/{artifact_id}/approve", response_model=ArtifactOut)
async def approve_artifact(
    artifact_id: str, session: AsyncSession = Depends(get_session)
) -> ArtifactOut:
    """Mark a design or plan artifact as approved for downstream use."""
    artifact = await session.get(Artifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    artifact.approved = True
    await session.commit()
    await session.refresh(artifact)
    return ArtifactOut.model_validate(artifact)
