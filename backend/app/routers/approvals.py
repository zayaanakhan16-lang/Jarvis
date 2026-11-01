"""Human approval routes.

Consequential actions (creating public repositories, pushing, deploying,
submitting) are gated here. Approval grants execution; rejection cancels it.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import Approval
from app.schemas import ApprovalDecision, ApprovalOut
from app.services import events
from app.services.orchestrator import get_orchestrator

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("", response_model=list[ApprovalOut])
async def list_approvals(
    status: str | None = None,
    project_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[ApprovalOut]:
    stmt = select(Approval)
    if status:
        stmt = stmt.where(Approval.status == status)
    if project_id:
        stmt = stmt.where(Approval.project_id == project_id)
    stmt = stmt.order_by(desc(Approval.created_at)).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return [ApprovalOut.model_validate(row) for row in rows]


@router.post("/{approval_id}/decide", response_model=ApprovalOut)
async def decide(
    approval_id: str,
    payload: ApprovalDecision,
    session: AsyncSession = Depends(get_session),
) -> ApprovalOut:
    approval = await session.get(Approval, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found.")
    if approval.status != "pending":
        raise HTTPException(
            status_code=409, detail=f"This approval is already {approval.status}."
        )

    approval.status = "approved" if payload.approved else "rejected"
    approval.decided_at = datetime.now(timezone.utc)
    approval.decided_by = payload.decided_by or "user"
    approval.decision_note = payload.note
    await session.commit()
    await session.refresh(approval)

    await events.emit(
        session,
        events.APPROVAL_DECIDED,
        f"Approval {approval.status}: {approval.title}",
        project_id=approval.project_id,
        task_id=approval.task_id,
        level="info" if payload.approved else "warning",
        data={"approval_id": approval.id, "status": approval.status},
    )

    # Resuming runs the task (or cancels it) through the orchestrator.
    orchestrator = get_orchestrator()
    await orchestrator.resume_after_approval(session, approval)
    await session.refresh(approval)
    return ApprovalOut.model_validate(approval)
