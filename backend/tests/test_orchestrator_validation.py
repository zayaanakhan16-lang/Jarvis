"""Plan validation: the orchestrator must never trust invented agents.

A planning model can hallucinate agent keys, task types and dependency ids.
These tests prove the orchestrator corrects or drops that output instead of
persisting a plan that references things which do not exist.
"""

from __future__ import annotations

import uuid

import pytest

from app.agents.registry import AGENT_BY_KEY, agent_for_task_type
from app.services.orchestrator import Orchestrator
from app.services.orchestrator import PlanError


class _StubOutcome:
    def __init__(self, text: str):
        self.result = type(
            "R", (), {"text": text, "provider": "stub", "model": "stub-model",
                      "total_tokens": 0, "usage_reported": False, "cost_usd": 0.0}
        )()
        self.decision = type("D", (), {"provider": "stub", "model": "stub-model"})()
        self.attempts = 1
        self.fallback_used = False


class _StubLLM:
    """An LLMService stand-in that returns a fixed plan.

    Only the network boundary is stubbed; all validation logic under test is the
    real orchestrator code.
    """

    def __init__(self, payload_text: str):
        self.payload_text = payload_text

    async def execute(self, *_args, **_kwargs):
        return _StubOutcome(self.payload_text)


def _orchestrator_with(payload_text: str) -> Orchestrator:
    return Orchestrator(llm=_StubLLM(payload_text))


@pytest.fixture
async def session():
    from app.database import SessionLocal, init_models

    await init_models()
    async with SessionLocal() as db:
        yield db


async def test_invented_agent_key_is_replaced_with_a_real_agent(session):
    payload = """{
      "tasks": [{
        "id": "t1", "title": "Do a thing", "description": "desc",
        "task_type": "coding", "agent_key": "totally_made_up_agent",
        "priority": 5, "depends_on": []
      }]
    }"""
    orch = _orchestrator_with(payload)
    tasks = await orch.create_plan(session, objective="Build a widget")
    assert len(tasks) == 1
    assert tasks[0].agent_key in AGENT_BY_KEY
    assert tasks[0].agent_key != "totally_made_up_agent"
    # It must have fallen back to the agent that really handles this task type.
    assert tasks[0].agent_key == agent_for_task_type("coding").key


async def test_unknown_task_type_falls_back_to_analysis(session):
    payload = """{
      "tasks": [{
        "id": "t1", "title": "Odd job", "description": "desc",
        "task_type": "interpretive_dance", "priority": 5, "depends_on": []
      }]
    }"""
    orch = _orchestrator_with(payload)
    tasks = await orch.create_plan(session, objective="Do something odd")
    assert len(tasks) == 1
    assert tasks[0].task_type == "analysis"


async def test_dependency_ids_are_remapped_to_real_task_ids(session):
    payload = """{
      "tasks": [
        {"id": "a", "title": "First", "description": "d", "task_type": "research",
         "agent_key": "problem_research", "priority": 5, "depends_on": []},
        {"id": "b", "title": "Second", "description": "d", "task_type": "coding",
         "agent_key": "frontend_engineer", "priority": 5, "depends_on": ["a"]}
      ]
    }"""
    orch = _orchestrator_with(payload)
    tasks = await orch.create_plan(session, objective="Two-step objective")
    assert len(tasks) == 2
    by_title = {t.title: t for t in tasks}
    second = by_title["Second"]
    first = by_title["First"]
    assert second.depends_on == [first.id], "dependency must point at the real task id"


async def test_dangling_dependency_is_dropped(session):
    payload = """{
      "tasks": [{
        "id": "t1", "title": "Only task", "description": "d",
        "task_type": "analysis", "priority": 5, "depends_on": ["does_not_exist"]
      }]
    }"""
    orch = _orchestrator_with(payload)
    tasks = await orch.create_plan(session, objective="Objective")
    assert tasks[0].depends_on == []


async def test_self_dependency_is_dropped(session):
    payload = """{
      "tasks": [{
        "id": "t1", "title": "Self referential", "description": "d",
        "task_type": "analysis", "priority": 5, "depends_on": ["t1"]
      }]
    }"""
    orch = _orchestrator_with(payload)
    tasks = await orch.create_plan(session, objective="Objective")
    assert tasks[0].depends_on == []


async def test_priority_is_clamped_to_a_sane_range(session):
    payload = """{
      "tasks": [{
        "id": "t1", "title": "Extreme", "description": "d",
        "task_type": "analysis", "priority": 9999, "depends_on": []
      }]
    }"""
    orch = _orchestrator_with(payload)
    tasks = await orch.create_plan(session, objective="Objective")
    assert 1 <= tasks[0].priority <= 9


async def test_approval_required_agents_produce_approval_tasks(session):
    """Agents whose permission scope demands approval must set the flag."""
    payload = """{
      "tasks": [{
        "id": "t1", "title": "Deploy it", "description": "d",
        "task_type": "deployment", "priority": 5, "depends_on": []
      }]
    }"""
    orch = _orchestrator_with(payload)
    tasks = await orch.create_plan(session, objective="Deploy the app")
    assert len(tasks) == 1
    spec = AGENT_BY_KEY[tasks[0].agent_key]
    if spec.requires_approval_for:
        assert tasks[0].requires_approval is True


async def test_plan_with_no_usable_tasks_raises(session):
    payload = '{"tasks": ["not an object", 42]}'
    orch = _orchestrator_with(payload)
    with pytest.raises(PlanError) as excinfo:
        await orch.create_plan(session, objective="Objective")
    assert "real agent" in str(excinfo.value).lower()


async def test_empty_task_list_raises(session):
    orch = _orchestrator_with('{"tasks": []}')
    with pytest.raises(PlanError):
        await orch.create_plan(session, objective="Objective")


async def test_non_json_response_raises_with_raw_excerpt(session):
    orch = _orchestrator_with("I am afraid I cannot do that.")
    with pytest.raises(PlanError) as excinfo:
        await orch.create_plan(session, objective="Objective")
    assert "usable json" in str(excinfo.value).lower()


async def test_blank_objective_is_rejected(session):
    orch = _orchestrator_with('{"tasks": []}')
    with pytest.raises(PlanError):
        await orch.create_plan(session, objective="   ")


async def test_plan_emits_activity_events(session):
    from sqlalchemy import select

    from app.models import Event

    payload = """{
      "tasks": [{
        "id": "t1", "title": "Tracked", "description": "d",
        "task_type": "analysis", "priority": 5, "depends_on": []
      }]
    }"""
    orch = _orchestrator_with(payload)
    project_id = str(uuid.uuid4())
    await orch.create_plan(session, objective="Tracked objective", project_id=project_id)
    rows = (
        await session.execute(select(Event).where(Event.project_id == project_id))
    ).scalars().all()
    types = {row.type for row in rows}
    assert "plan.created" in types
    assert "task.created" in types
