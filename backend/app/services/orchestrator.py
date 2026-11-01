"""Orchestration engine.

Two responsibilities:

* ``create_plan`` turns a user objective into a persisted, dependency-aware task
  graph by asking a planning model, then validating the model's output against
  the real agent roster. Anything the model invents is corrected or dropped.
* ``execute_plan`` runs those tasks, honouring dependencies, parallelism,
  approval gates and failure isolation.

The orchestrator never depends on a specific vendor: all model access goes
through :class:`~app.services.llm.LLMService`.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import AGENT_BY_KEY, AGENTS, DEPARTMENT_BY_KEY, agent_for_task_type
from app.config import get_settings
from app.database import SessionLocal
from app.models import Agent, Approval, Artifact, Task
from app.providers.base import ProviderError
from app.services import events, prompts
from app.services.json_utils import as_list, as_str, clamp_int, extract_json
from app.services.llm import LLMService, get_llm_service

VALID_TASK_TYPES = set(prompts.TASK_TEMPLATES)


class PlanError(RuntimeError):
    """Raised when a plan cannot be produced."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Orchestrator:
    def __init__(self, llm: LLMService | None = None):
        self.llm = llm or get_llm_service()
        self.settings = get_settings()

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------
    def _roster_digest(self) -> str:
        """A compact description of the real roster for the planning prompt."""
        lines = []
        for department in DEPARTMENT_BY_KEY.values():
            lines.append(f"{department.name} ({department.key}):")
            for key in department.agents:
                spec = AGENT_BY_KEY[key]
                lines.append(f"  - {spec.key}: {spec.name} - {spec.description}")
        return "\n".join(lines)

    async def create_plan(
        self,
        session: AsyncSession,
        *,
        objective: str,
        project_id: str | None = None,
        context: dict[str, Any] | None = None,
        max_tasks: int = 10,
        explicit_provider: str | None = None,
        explicit_model: str | None = None,
    ) -> list[Task]:
        """Produce and persist a task graph for ``objective``."""
        if not objective.strip():
            raise PlanError("An objective is required to create a plan.")

        system = prompts.system_prompt(
            agent_name="Chief Orchestrator",
            department="Executive",
            agent_description=(
                "You decompose a high-level objective into a dependency-aware task "
                "graph and assign each task to a specialist agent from the roster."
            ),
            capabilities=["task decomposition", "dependency analysis", "agent assignment"],
            json_schema=prompts.PLANNING_SCHEMA,
        )
        context_block = prompts.project_context_block(context)
        prompt = (
            f"Objective:\n{objective.strip()}\n\n"
            f"Available agents (use these keys verbatim; do not invent agents):\n"
            f"{self._roster_digest()}\n\n"
            f"Produce at most {max_tasks} tasks. Prefer fewer, more substantial tasks "
            f"over many trivial ones. Set depends_on using the ids you define. "
            f"Use null for agent_key when no listed agent fits.\n"
        )
        if context_block:
            prompt = f"{prompt}\n{context_block}\n"

        try:
            outcome = await self.llm.execute(
                session,
                task_type="planning",
                prompt=prompt,
                system=system,
                explicit_provider=explicit_provider,
                explicit_model=explicit_model,
                temperature=0.3,
                max_tokens=4096,
                json_mode=True,
                project_id=project_id,
                agent_key="chief_orchestrator",
            )
        except ProviderError as exc:
            raise PlanError(str(exc)) from exc

        payload, error = extract_json(outcome.result.text)
        if payload is None or not isinstance(payload, dict):
            raise PlanError(
                f"The planning model did not return usable JSON ({error}). "
                f"Raw response started with: {outcome.result.text[:200]!r}"
            )

        raw_tasks = as_list(payload.get("tasks"))
        if not raw_tasks:
            raise PlanError("The planning model returned a plan with no tasks.")

        created = await self._persist_plan(
            session,
            project_id=project_id,
            objective=objective,
            payload=payload,
            raw_tasks=raw_tasks[:max_tasks],
            provider=outcome.decision.provider,
            model=outcome.decision.model,
        )
        return created

    async def _persist_plan(
        self,
        session: AsyncSession,
        *,
        project_id: str | None,
        objective: str,
        payload: dict[str, Any],
        raw_tasks: list[Any],
        provider: str,
        model: str,
    ) -> list[Task]:
        """Validate the model's plan against the real roster, then persist it."""
        # Map model-supplied ids to real task ids so depends_on survives.
        id_map: dict[str, str] = {}
        prepared: list[dict[str, Any]] = []

        for index, raw in enumerate(raw_tasks):
            if not isinstance(raw, dict):
                continue
            local_id = as_str(raw.get("id"), f"t{index + 1}")
            task_type = as_str(raw.get("task_type"), "analysis").strip().lower()
            if task_type not in VALID_TASK_TYPES:
                task_type = "analysis"

            # Resolve the agent: trust the model only when the key really exists.
            agent_key = raw.get("agent_key")
            agent_key = as_str(agent_key).strip() or None
            if agent_key and agent_key not in AGENT_BY_KEY:
                agent_key = None
            spec = AGENT_BY_KEY.get(agent_key) if agent_key else None
            if spec is None:
                spec = agent_for_task_type(task_type)
            if spec is None:
                # No agent can do this: skip rather than fabricate a worker.
                continue
            agent_key = spec.key

            department = as_str(raw.get("department")).strip().lower()
            if department not in DEPARTMENT_BY_KEY:
                department = spec.department

            title = as_str(raw.get("title"), f"Task {index + 1}").strip()[:300]
            description = as_str(raw.get("description")).strip()
            deliverable = as_str(raw.get("deliverable")).strip()
            if deliverable:
                description = f"{description}\n\nDeliverable: {deliverable}".strip()

            requires_approval = bool(raw.get("requires_approval")) or bool(
                spec.requires_approval_for
            )

            task_id = str(uuid.uuid4())
            id_map[local_id] = task_id
            prepared.append(
                {
                    "id": task_id,
                    "local_id": local_id,
                    "title": title,
                    "description": description,
                    "task_type": task_type,
                    "department": department,
                    "agent_key": agent_key,
                    "priority": clamp_int(raw.get("priority"), low=1, high=9, default=5),
                    "depends_on_raw": [as_str(d) for d in as_list(raw.get("depends_on"))],
                    "requires_approval": requires_approval,
                }
            )

        if not prepared:
            raise PlanError(
                "None of the planned tasks could be assigned to a real agent. "
                "Add an agent for the required work or rephrase the objective."
            )

        valid_ids = set(id_map.values())
        tasks: list[Task] = []
        for item in prepared:
            depends_on = [
                id_map[local] for local in item["depends_on_raw"] if local in id_map
            ]
            depends_on = [d for d in depends_on if d in valid_ids and d != item["id"]]
            task = Task(
                id=item["id"],
                project_id=project_id,
                title=item["title"],
                description=item["description"],
                task_type=item["task_type"],
                department=item["department"],
                agent_key=item["agent_key"],
                status="pending",
                priority=item["priority"],
                provider=provider,
                model=model,
                payload={"objective": objective, "local_id": item["local_id"]},
                depends_on=depends_on,
                requires_approval=item["requires_approval"],
            )
            session.add(task)
            tasks.append(task)

        await session.commit()

        summary = as_str(payload.get("summary"))
        risks = [as_str(r) for r in as_list(payload.get("risks"))]
        assumptions = [as_str(a) for a in as_list(payload.get("assumptions"))]

        await events.emit(
            session,
            events.PLAN_CREATED,
            f"Plan created with {len(tasks)} tasks for objective: {objective[:120]}",
            project_id=project_id,
            agent_key="chief_orchestrator",
            data={
                "summary": summary,
                "risks": risks,
                "assumptions": assumptions,
                "provider": provider,
                "model": model,
                "task_ids": [t.id for t in tasks],
            },
        )
        for task in tasks:
            await events.emit(
                session,
                events.TASK_CREATED,
                f"Task queued: {task.title}",
                project_id=project_id,
                task_id=task.id,
                agent_key=task.agent_key,
                data={
                    "task_type": task.task_type,
                    "department": task.department,
                    "depends_on": task.depends_on,
                    "requires_approval": task.requires_approval,
                },
            )
        return tasks

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    async def execute_plan(
        self,
        session: AsyncSession,
        *,
        task_ids: list[str] | None = None,
        project_id: str | None = None,
        max_parallel: int | None = None,
        explicit_provider: str | None = None,
        explicit_model: str | None = None,
    ) -> dict[str, Any]:
        """Execute a plan, respecting dependencies and approval gates.

        Returns a run summary with per-task outcomes. Tasks whose dependencies
        failed are marked ``skipped`` rather than silently ignored.
        """
        parallel = max_parallel or self.settings.max_parallel_tasks

        stmt = select(Task)
        if task_ids:
            stmt = stmt.where(Task.id.in_(task_ids))
        elif project_id:
            stmt = stmt.where(Task.project_id == project_id)
        else:
            raise PlanError("execute_plan requires task_ids or a project_id.")
        result = await session.execute(stmt.order_by(Task.priority.desc(), Task.created_at))
        tasks = list(result.scalars().all())

        executable = [t for t in tasks if t.status in ("pending", "queued", "failed")]
        if not executable:
            return {"executed": 0, "completed": 0, "failed": 0, "skipped": 0, "results": []}

        by_id = {t.id: t for t in tasks}
        status: dict[str, str] = {t.id: t.status for t in tasks}
        remaining = {t.id: t for t in executable}
        outcomes: list[dict[str, Any]] = []

        while remaining:
            # A task is ready when every dependency has finished successfully.
            ready: list[Task] = []
            blocked: list[Task] = []
            for task in remaining.values():
                deps = [d for d in (task.depends_on or []) if d in by_id]
                dep_status = [status.get(d, "pending") for d in deps]
                if any(s in ("failed", "cancelled", "skipped") for s in dep_status):
                    blocked.append(task)
                elif all(s == "completed" for s in dep_status):
                    ready.append(task)

            for task in blocked:
                task.status = "skipped"
                task.error = "A dependency failed, so this task was not run."
                task.finished_at = _now()
                status[task.id] = "skipped"
                remaining.pop(task.id, None)
                outcomes.append(
                    {"task_id": task.id, "title": task.title, "status": "skipped",
                     "error": task.error}
                )
                await events.emit(
                    session, events.TASK_CANCELLED,
                    f"Skipped '{task.title}': a dependency failed.",
                    project_id=task.project_id, task_id=task.id, agent_key=task.agent_key,
                    level="warning",
                )

            if not ready:
                if remaining and not blocked:
                    # A dependency cycle or dangling reference: fail loudly.
                    for task in remaining.values():
                        task.status = "failed"
                        task.error = "Unresolvable dependencies; the plan contains a cycle."
                        status[task.id] = "failed"
                        outcomes.append(
                            {"task_id": task.id, "title": task.title, "status": "failed",
                             "error": task.error}
                        )
                    remaining.clear()
                break

            ready.sort(key=lambda t: (-t.priority, t.created_at))
            batch = ready[:parallel]
            for task in batch:
                remaining.pop(task.id, None)

            results = await asyncio.gather(
                *(
                    self._run_task(
                        task,
                        explicit_provider=explicit_provider,
                        explicit_model=explicit_model,
                    )
                    for task in batch
                ),
                return_exceptions=True,
            )
            for task, outcome in zip(batch, results):
                if isinstance(outcome, BaseException):
                    status[task.id] = "failed"
                    outcomes.append(
                        {"task_id": task.id, "title": task.title, "status": "failed",
                         "error": str(outcome)}
                    )
                else:
                    status[task.id] = outcome["status"]
                    outcomes.append(outcome)

        completed = sum(1 for o in outcomes if o["status"] == "completed")
        failed = sum(1 for o in outcomes if o["status"] == "failed")
        skipped = sum(1 for o in outcomes if o["status"] == "skipped")
        waiting = sum(1 for o in outcomes if o["status"] == "waiting_approval")

        return {
            "executed": len(outcomes),
            "completed": completed,
            "failed": failed,
            "skipped": skipped,
            "waiting_approval": waiting,
            "results": outcomes,
        }

    # ------------------------------------------------------------------
    # Single task execution
    # ------------------------------------------------------------------
    async def _run_task(
        self,
        task: Task,
        *,
        explicit_provider: str | None = None,
        explicit_model: str | None = None,
    ) -> dict[str, Any]:
        """Execute one task on its own session, in isolation from the batch."""
        async with SessionLocal() as session:
            db_task = await session.get(Task, task.id)
            if db_task is None:
                return {"task_id": task.id, "title": task.title, "status": "failed",
                        "error": "Task disappeared before execution."}

            if db_task.requires_approval and db_task.status != "running":
                await self._request_approval(session, db_task)
                return {
                    "task_id": db_task.id,
                    "title": db_task.title,
                    "status": "waiting_approval",
                    "error": None,
                }

            spec = AGENT_BY_KEY.get(db_task.agent_key or "")
            if spec is None:
                db_task.status = "failed"
                db_task.error = f"No agent registered for key '{db_task.agent_key}'."
                db_task.finished_at = _now()
                await session.commit()
                return {"task_id": db_task.id, "title": db_task.title,
                        "status": "failed", "error": db_task.error}

            started = _now()
            db_task.status = "running"
            db_task.started_at = started
            db_task.attempts += 1
            await session.commit()
            await self._mark_agent(session, spec.key, status="running", task_id=db_task.id)
            await events.emit(
                session, events.TASK_STARTED,
                f"{spec.name} started '{db_task.title}'.",
                project_id=db_task.project_id, task_id=db_task.id, agent_key=spec.key,
                data={"task_type": db_task.task_type, "attempt": db_task.attempts},
            )
            await events.emit(
                session, events.AGENT_STARTED,
                f"{spec.name} is working.",
                project_id=db_task.project_id, task_id=db_task.id, agent_key=spec.key,
            )

            context = await self._memory_context(session, db_task.project_id)
            system = prompts.system_prompt(
                agent_name=spec.name,
                department=DEPARTMENT_BY_KEY[spec.department].name
                if spec.department in DEPARTMENT_BY_KEY
                else spec.department,
                agent_description=spec.description,
                capabilities=spec.capabilities,
                json_schema=prompts.template_for(db_task.task_type)[0],
                extra_rules=prompts.template_for(db_task.task_type)[1],
            )
            prompt = self._build_task_prompt(db_task, context)

            try:
                outcome = await self.llm.execute(
                    session,
                    task_type=db_task.task_type,
                    prompt=prompt,
                    system=system,
                    explicit_provider=explicit_provider or db_task.provider,
                    explicit_model=explicit_model or db_task.model,
                    project_id=db_task.project_id,
                    task_id=db_task.id,
                    agent_key=spec.key,
                )
            except ProviderError as exc:
                return await self._fail_task(session, db_task, spec.key, str(exc))

            result = outcome.result
            parsed, parse_error = extract_json(result.text)
            finished = _now()
            db_task.status = "completed"
            db_task.result = result.text
            db_task.result_data = {
                "parsed": parsed,
                "parse_error": parse_error,
                "provider": result.provider,
                "model": result.model,
                "tokens": result.total_tokens,
                "usage_reported": result.usage_reported,
                "attempts": outcome.attempts,
                "fallback_used": outcome.fallback_used,
            }
            db_task.provider = result.provider
            db_task.model = result.model
            db_task.tokens_used = result.total_tokens
            db_task.cost_usd = result.cost_usd
            db_task.duration_ms = int((finished - started).total_seconds() * 1000)
            db_task.finished_at = finished
            db_task.error = None
            await session.commit()

            await self._persist_artifact(session, db_task, parsed, result.text)
            await self._mark_agent(session, spec.key, status="idle", task_id=None, success=True)
            await events.emit(
                session, events.TASK_COMPLETED,
                f"{spec.name} completed '{db_task.title}'.",
                project_id=db_task.project_id, task_id=db_task.id, agent_key=spec.key,
                data={
                    "duration_ms": db_task.duration_ms,
                    "provider": result.provider,
                    "model": result.model,
                    "tokens": result.total_tokens,
                    "cost_usd": result.cost_usd,
                    "usage_reported": result.usage_reported,
                },
            )
            await events.emit(
                session, events.AGENT_FINISHED,
                f"{spec.name} finished.",
                project_id=db_task.project_id, task_id=db_task.id, agent_key=spec.key,
            )
            return {
                "task_id": db_task.id,
                "title": db_task.title,
                "status": "completed",
                "error": None,
                "provider": result.provider,
                "model": result.model,
                "duration_ms": db_task.duration_ms,
            }

    async def run_task(
        self,
        task: Task,
        *,
        explicit_provider: str | None = None,
        explicit_model: str | None = None,
    ) -> dict[str, Any]:
        """Public entry point for running a single task."""
        return await self._run_task(
            task,
            explicit_provider=explicit_provider,
            explicit_model=explicit_model,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _build_task_prompt(self, task: Task, context: dict[str, Any] | None) -> str:
        parts = [f"Task: {task.title}", "", task.description or "(no further detail given)"]
        objective = (task.payload or {}).get("objective")
        if objective:
            parts += ["", f"Overall objective this supports: {objective}"]
        if task.depends_on:
            parts += [
                "",
                "This task depends on earlier work whose outputs are listed above. "
                "Build on them rather than repeating them.",
            ]
        block = prompts.project_context_block(context)
        if block:
            parts += ["", block]
        return "\n".join(parts)

    async def _memory_context(
        self, session: AsyncSession, project_id: str | None
    ) -> dict[str, Any]:
        """Load project memory. Memory is strictly project-scoped."""
        if not project_id:
            return {}
        from app.models import MemoryEntry

        result = await session.execute(
            select(MemoryEntry)
            .where(MemoryEntry.project_id == project_id)
            .order_by(MemoryEntry.updated_at.desc())
            .limit(40)
        )
        context: dict[str, Any] = {}
        for entry in result.scalars().all():
            context[f"{entry.category}.{entry.key}"] = entry.value
        return context

    async def _fail_task(
        self, session: AsyncSession, task: Task, agent_key: str, error: str
    ) -> dict[str, Any]:
        task.status = "failed"
        task.error = error
        task.finished_at = _now()
        if task.started_at:
            task.duration_ms = int((task.finished_at - task.started_at).total_seconds() * 1000)
        await session.commit()
        await self._mark_agent(session, agent_key, status="failed", task_id=None, success=False,
                               error=error)
        await events.emit(
            session, events.TASK_FAILED,
            f"'{task.title}' failed: {error}",
            project_id=task.project_id, task_id=task.id, agent_key=agent_key,
            level="error", data={"error": error, "attempts": task.attempts},
        )
        return {"task_id": task.id, "title": task.title, "status": "failed", "error": error}

    async def _request_approval(self, session: AsyncSession, task: Task) -> Approval:
        existing = (
            await session.execute(
                select(Approval).where(
                    Approval.task_id == task.id, Approval.status == "pending"
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing

        spec = AGENT_BY_KEY.get(task.agent_key or "")
        approval = Approval(
            id=str(uuid.uuid4()),
            project_id=task.project_id,
            task_id=task.id,
            action_type=(spec.requires_approval_for[0] if spec and spec.requires_approval_for
                         else "task_execution"),
            title=f"Approve: {task.title}",
            description=(
                f"{spec.name if spec else 'An agent'} needs approval before running this task.\n\n"
                f"{task.description or 'No further detail.'}"
            ),
            payload={"task_type": task.task_type, "agent_key": task.agent_key,
                     "department": task.department},
            status="pending",
            requested_by=task.agent_key,
        )
        session.add(approval)
        task.status = "waiting_approval"
        task.approval_id = approval.id
        await session.commit()
        await self._mark_agent(session, task.agent_key or "", status="waiting_approval",
                               task_id=task.id)
        await events.emit(
            session, events.APPROVAL_REQUESTED,
            f"Approval requested for '{task.title}'.",
            project_id=task.project_id, task_id=task.id, agent_key=task.agent_key,
            level="warning",
            data={"approval_id": approval.id, "action_type": approval.action_type},
        )
        return approval

    async def resume_after_approval(
        self, session: AsyncSession, approval: Approval
    ) -> dict[str, Any]:
        """Continue a task once its approval has been granted."""
        if approval.task_id is None:
            return {"status": "noop", "reason": "Approval is not attached to a task."}
        task = await session.get(Task, approval.task_id)
        if task is None:
            return {"status": "noop", "reason": "Task no longer exists."}
        if approval.status != "approved":
            task.status = "cancelled"
            task.error = f"Approval {approval.status}: {approval.decision_note or 'no note'}"
            task.finished_at = _now()
            await session.commit()
            await events.emit(
                session, events.TASK_CANCELLED,
                f"'{task.title}' was not approved, so it did not run.",
                project_id=task.project_id, task_id=task.id, agent_key=task.agent_key,
                level="warning",
            )
            return {"status": "cancelled", "task_id": task.id}

        task.status = "queued"
        task.requires_approval = False
        await session.commit()
        return await self._run_task(task)

    async def _mark_agent(
        self,
        session: AsyncSession,
        agent_key: str,
        *,
        status: str,
        task_id: str | None,
        success: bool | None = None,
        error: str | None = None,
    ) -> None:
        if not agent_key:
            return
        record = await session.get(Agent, agent_key)
        if record is None:
            spec = AGENT_BY_KEY.get(agent_key)
            if spec is None:
                return
            record = Agent(
                key=spec.key,
                name=spec.name,
                department=spec.department,
                description=spec.description,
                capabilities=list(spec.capabilities),
                tools=list(spec.tools),
                task_types=[spec.task_type],
                permission_scope=list(spec.permission_scope),
            )
            session.add(record)
        record.status = status
        record.current_task_id = task_id
        record.last_active_at = _now()
        if success is True:
            record.tasks_completed += 1
            record.last_error = None
        elif success is False:
            record.tasks_failed += 1
            record.last_error = error
        await session.commit()

    async def _persist_artifact(
        self,
        session: AsyncSession,
        task: Task,
        parsed: Any,
        raw_text: str,
    ) -> Artifact:
        kind_map = {
            "planning": "plan",
            "research": "research_report",
            "analysis": "analysis",
            "architecture": "architecture",
            "code_review": "code_review",
            "security": "security_review",
            "ui_design": "design",
            "branding": "brand",
            "presentation": "presentation",
            "documentation": "documentation",
            "coding": "implementation_plan",
            "testing": "test_plan",
            "debugging": "diagnosis",
        }
        artifact = Artifact(
            id=str(uuid.uuid4()),
            project_id=task.project_id,
            task_id=task.id,
            kind=kind_map.get(task.task_type, "output"),
            title=task.title,
            content=raw_text,
            data=parsed if isinstance(parsed, dict) else {"value": parsed},
        )
        session.add(artifact)
        await session.commit()
        await events.emit(
            session, events.ARTIFACT_CREATED,
            f"Produced {artifact.kind.replace('_', ' ')}: {artifact.title}",
            project_id=task.project_id, task_id=task.id, agent_key=task.agent_key,
            data={"artifact_id": artifact.id, "kind": artifact.kind},
        )
        return artifact


_orchestrator: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator
