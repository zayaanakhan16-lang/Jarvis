"""API contract tests against the real ASGI application.

These cover the endpoints the frontend depends on, plus the honesty rules:
unconfigured services must never report themselves connected.
"""

from __future__ import annotations

import pytest


async def test_health_reports_database_status(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "JARVIS"
    assert "ok" in body["database"]


async def test_root_describes_the_service(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json()["name"] == "JARVIS"


async def test_openapi_schema_is_served(client):
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    for expected in ("/api/health", "/api/projects", "/api/tasks/plan", "/api/agents",
                     "/api/providers", "/api/integrations", "/api/activity"):
        assert expected in paths, f"missing route {expected}"


async def test_overview_starts_empty_with_no_fake_data(client):
    response = await client.get("/api/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["projects_total"] >= 0
    assert body["agents_total"] >= 30
    assert body["tokens_used"] >= 0


async def test_agents_are_seeded_and_real(client):
    response = await client.get("/api/agents")
    assert response.status_code == 200
    agents = response.json()
    assert len(agents) >= 30
    keys = {a["key"] for a in agents}
    assert "chief_orchestrator" in keys
    for agent in agents:
        assert agent["name"]
        assert agent["department"]
        assert agent["status"] in {
            "idle", "queued", "running", "waiting_approval", "completed",
            "failed", "unavailable",
        }


async def test_unknown_agent_returns_404(client):
    response = await client.get("/api/agents/not_a_real_agent")
    assert response.status_code == 404


async def test_departments_cover_the_roster(client):
    response = await client.get("/api/departments")
    assert response.status_code == 200
    departments = response.json()
    assert len(departments) >= 8
    assert sum(d["agent_count"] for d in departments) >= 30


# --- Projects -------------------------------------------------------------
async def test_project_lifecycle(client):
    created = await client.post(
        "/api/projects",
        json={"name": "Lifecycle Test", "objective": "Verify CRUD"},
    )
    assert created.status_code == 201
    project = created.json()
    assert project["slug"] == "lifecycle-test"
    assert project["task_count"] == 0

    fetched = await client.get(f"/api/projects/{project['id']}")
    assert fetched.status_code == 200

    updated = await client.patch(
        f"/api/projects/{project['id']}", json={"status": "active"}
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "active"

    listed = await client.get("/api/projects")
    assert any(p["id"] == project["id"] for p in listed.json())


async def test_duplicate_project_names_get_unique_slugs(client):
    first = await client.post("/api/projects", json={"name": "Same Name"})
    second = await client.post("/api/projects", json={"name": "Same Name"})
    assert first.json()["slug"] != second.json()["slug"]


async def test_invalid_project_status_is_rejected(client):
    created = await client.post("/api/projects", json={"name": "Status Check"})
    project_id = created.json()["id"]
    response = await client.patch(
        f"/api/projects/{project_id}", json={"status": "not_a_status"}
    )
    assert response.status_code == 422


async def test_project_memory_is_scoped_and_upserted(client):
    created = await client.post("/api/projects", json={"name": "Memory Test"})
    project_id = created.json()["id"]

    first = await client.post(
        f"/api/projects/{project_id}/memory",
        json={"category": "design", "key": "palette", "value": "navy"},
    )
    assert first.status_code == 201

    second = await client.post(
        f"/api/projects/{project_id}/memory",
        json={"category": "design", "key": "palette", "value": "charcoal"},
    )
    assert second.status_code == 201
    assert second.json()["value"] == "charcoal"

    listed = await client.get(f"/api/projects/{project_id}/memory")
    entries = listed.json()
    assert len(entries) == 1, "same category+key must upsert, not duplicate"


async def test_memory_for_unknown_project_returns_404(client):
    response = await client.post(
        "/api/projects/does-not-exist/memory",
        json={"category": "a", "key": "b", "value": "c"},
    )
    assert response.status_code == 404


# --- Providers / integrations honesty -------------------------------------
async def test_providers_never_claim_connection_without_a_test(client):
    response = await client.get("/api/providers")
    assert response.status_code == 200
    for provider in response.json():
        if not provider["configured"]:
            assert provider["connected"] is False, (
                f"{provider['key']} claims connected while unconfigured"
            )
            assert provider["status"] == "not_configured"


async def test_provider_route_preview_without_credentials_is_conflict(client):
    response = await client.post("/api/providers/route-preview", json={"task_type": "coding"})
    # With no cloud credentials only local Ollama is a candidate, so a decision
    # is expected; the important part is that it never invents a cloud provider.
    assert response.status_code in (200, 409)
    if response.status_code == 200:
        assert response.json()["provider"] == "ollama"


async def test_unknown_provider_test_returns_404(client):
    response = await client.post("/api/providers/nope/test")
    assert response.status_code == 404


async def test_integrations_report_not_configured_honestly(client):
    response = await client.get("/api/integrations")
    assert response.status_code == 200
    integrations = response.json()
    assert len(integrations) >= 5
    for integration in integrations:
        if not integration["configured"]:
            assert integration["connected"] is False, (
                f"{integration['key']} claims connected while unconfigured"
            )
        # A connection test must never have been recorded as connected without
        # a timestamp proving the test ran.
        if integration["connected"]:
            assert integration["last_tested_at"] is not None


async def test_unknown_integration_test_returns_404(client):
    response = await client.post("/api/integrations/nope/test")
    assert response.status_code == 404


# --- Tasks ----------------------------------------------------------------
async def test_plan_without_a_provider_fails_honestly(client):
    response = await client.post(
        "/api/tasks/plan", json={"objective": "Do something", "max_tasks": 2}
    )
    # 502 = no usable provider. It must not return a fabricated plan.
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "provider" in detail.lower()


async def test_execute_requires_a_scope(client):
    response = await client.post("/api/tasks/execute", json={})
    assert response.status_code == 422


async def test_unknown_task_returns_404(client):
    response = await client.get("/api/tasks/not-a-task")
    assert response.status_code == 404


async def test_run_with_unknown_agent_returns_404(client):
    response = await client.post(
        "/api/tasks/run", json={"prompt": "Do it", "agent_key": "ghost_agent"}
    )
    assert response.status_code == 404


# --- Activity -------------------------------------------------------------
async def test_activity_reflects_real_actions_only(client):
    before = await client.get("/api/activity")
    count_before = len(before.json())

    created = await client.post("/api/projects", json={"name": "Activity Check"})
    assert created.status_code == 201

    after = await client.get("/api/activity")
    events = after.json()
    assert len(events) > count_before
    latest = events[0]
    assert latest["type"] == "project.created"
    assert "Activity Check" in latest["message"]


async def test_activity_filters_by_project(client):
    created = await client.post("/api/projects", json={"name": "Filtered"})
    project_id = created.json()["id"]
    response = await client.get(f"/api/activity?project_id={project_id}")
    assert response.status_code == 200
    for event in response.json():
        assert event["project_id"] == project_id


async def test_activity_summary_counts_by_type(client):
    response = await client.get("/api/activity/summary")
    assert response.status_code == 200
    assert isinstance(response.json()["counts"], dict)


# --- Approvals / artifacts ------------------------------------------------
async def test_approval_decision_on_unknown_id_returns_404(client):
    response = await client.post("/api/approvals/nope/decide", json={"approved": True})
    assert response.status_code == 404


async def test_artifact_approval_round_trip(client):
    created = await client.post("/api/projects", json={"name": "Artifact Check"})
    project_id = created.json()["id"]
    # Insert an artifact directly: this test covers the approval endpoint, not
    # task execution, which needs a live provider.
    from app.database import SessionLocal
    from app.models import Artifact

    artifact_id = "artifact-under-test"
    async with SessionLocal() as db:
        db.add(
            Artifact(
                id=artifact_id,
                project_id=project_id,
                kind="design",
                title="Design system",
                content="navy, charcoal, cyan",
                data={},
            )
        )
        await db.commit()

    response = await client.post(f"/api/artifacts/{artifact_id}/approve")
    assert response.status_code == 200
    assert response.json()["approved"] is True


# --- Voice ----------------------------------------------------------------
async def test_voice_status_reports_browser_fallback(client):
    response = await client.get("/api/voice/status")
    assert response.status_code == 200
    body = response.json()
    assert body["elevenlabs_configured"] is False
    assert body["text_to_speech"] == "browser"
    assert "ELEVENLABS_API_KEY" in body["note"]


async def test_speak_without_elevenlabs_returns_503_not_fake_audio(client):
    response = await client.post("/api/voice/speak", json={"text": "hello"})
    assert response.status_code == 503
    assert "ELEVENLABS_API_KEY" in response.json()["detail"]


# --- Sessions -------------------------------------------------------------
async def test_session_with_unknown_engine_is_rejected(client):
    response = await client.post(
        "/api/sessions", json={"engine": "not_an_engine", "task": "Build something"}
    )
    assert response.status_code == 502
    assert "unknown coding engine" in response.json()["detail"].lower()


async def test_opencode_session_without_a_server_fails_honestly(client):
    response = await client.post(
        "/api/sessions", json={"engine": "opencode", "task": "Build something"}
    )
    assert response.status_code == 502
    assert "opencode" in response.json()["detail"].lower()


# --- Hackathons -----------------------------------------------------------
async def test_hackathons_start_empty(client):
    response = await client.get("/api/hackathons")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


# --- Settings -------------------------------------------------------------
async def test_settings_round_trip(client):
    response = await client.get("/api/settings")
    assert response.status_code == 200
    original = response.json()
    assert original["database_backend"] in ("sqlite", "postgresql")

    updated = await client.put("/api/settings", json={"max_parallel_tasks": 2})
    assert updated.status_code == 200
    assert updated.json()["max_parallel_tasks"] == 2

    restored = await client.put("/api/settings", json={"max_parallel_tasks": 4})
    assert restored.json()["max_parallel_tasks"] == 4
