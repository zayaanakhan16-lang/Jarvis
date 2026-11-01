"""Hackathon intelligence routes.

Opportunities are stored only from real research output. Fields the research
agent could not verify stay null and are rendered as "unknown" in the UI; the
``verified`` flag is only true when at least one source URL was actually read.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import HackathonOpportunity, Task
from app.routers._helpers import new_id
from app.schemas import HackathonOut, RunRequest, TaskOut
from app.services import events
from app.services.json_utils import as_list, as_str
from app.services.orchestrator import get_orchestrator

router = APIRouter(prefix="/hackathons", tags=["hackathons"])


@router.get("", response_model=list[HackathonOut])
async def list_hackathons(
    project_id: str | None = None,
    verified_only: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> list[HackathonOut]:
    stmt = select(HackathonOpportunity)
    if project_id:
        stmt = stmt.where(HackathonOpportunity.project_id == project_id)
    if verified_only:
        stmt = stmt.where(HackathonOpportunity.verified.is_(True))
    stmt = stmt.order_by(desc(HackathonOpportunity.created_at)).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return [HackathonOut.model_validate(row) for row in rows]


@router.delete("/{hackathon_id}", status_code=204)
async def delete_hackathon(
    hackathon_id: str, session: AsyncSession = Depends(get_session)
) -> None:
    record = await session.get(HackathonOpportunity, hackathon_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Opportunity not found.")
    await session.delete(record)
    await session.commit()


@router.post("/research", response_model=TaskOut)
async def research_hackathons(
    payload: RunRequest, session: AsyncSession = Depends(get_session)
) -> TaskOut:
    """Run the discovery agent and persist every opportunity it can source."""
    task = Task(
        id=new_id(),
        project_id=payload.project_id,
        title=f"Hackathon research: {payload.prompt[:200]}",
        description=(
            f"{payload.prompt}\n\n"
            "For every opportunity you find, use only information you can attribute to a "
            "source URL you actually retrieved. Set any field you could not verify to "
            "\"unknown\" and set verified=false unless you read the official page. "
            "Never estimate participant numbers, prizes or competition level."
        ),
        task_type="research",
        department="hackathon",
        agent_key="hackathon_discovery",
        status="pending",
        provider=payload.provider,
        model=payload.model,
        payload={"direct": True, "kind": "hackathon_research"},
        depends_on=[],
    )
    session.add(task)
    await session.commit()

    orchestrator = get_orchestrator()
    await orchestrator.run_task(
        task, explicit_provider=payload.provider, explicit_model=payload.model
    )
    await session.refresh(task)

    if task.result_data and isinstance(task.result_data.get("parsed"), dict):
        saved = await _persist_opportunities(
            session, task.project_id, task.result_data["parsed"]
        )
        if saved:
            await events.emit(
                session,
                events.ARTIFACT_CREATED,
                f"Recorded {saved} hackathon opportunity(ies).",
                project_id=task.project_id,
                task_id=task.id,
                agent_key="hackathon_discovery",
                data={"saved": saved},
            )
    return TaskOut.model_validate(task)


def _clean(value) -> str | None:
    """Normalise an unverified field. 'unknown', '', 'n/a' all become None."""
    text = as_str(value).strip()
    if not text or text.lower() in {"unknown", "n/a", "none", "null", "not specified", "-"}:
        return None
    return text


async def _persist_opportunities(
    session: AsyncSession, project_id: str | None, parsed: dict
) -> int:
    opportunities = as_list(parsed.get("opportunities"))
    saved = 0
    for item in opportunities:
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("name"))
        if not name:
            continue
        sources = [s for s in (_clean(u) for u in as_list(item.get("source_urls"))) if s]
        # Only real, retrieved source URLs count as verification.
        verified = bool(sources) and bool(item.get("verified")) is not False
        record = HackathonOpportunity(
            id=new_id(),
            project_id=project_id,
            name=name,
            organizer=_clean(item.get("organizer")),
            url=_clean(item.get("url")),
            source_urls=sources,
            registration_deadline=_clean(item.get("registration_deadline")),
            event_start=_clean(item.get("event_start")),
            event_end=_clean(item.get("event_end")),
            location=_clean(item.get("location")),
            is_online=item.get("is_online") if isinstance(item.get("is_online"), bool) else None,
            age_restrictions=_clean(item.get("age_restrictions")),
            country_restrictions=_clean(item.get("country_restrictions")),
            team_requirements=_clean(item.get("team_requirements")),
            tracks=[t for t in (_clean(t) for t in as_list(item.get("tracks"))) if t],
            prizes=_clean(item.get("prizes")),
            submission_requirements=_clean(item.get("submission_requirements")),
            judging_criteria=_clean(item.get("judging_criteria")),
            eligibility_notes=_clean(item.get("eligibility_notes")),
            verified=bool(verified),
            verification_notes=_clean(item.get("verification_notes")),
            last_verified_at=datetime.now(timezone.utc) if sources else None,
        )
        session.add(record)
        saved += 1
    if saved:
        await session.commit()
    return saved
