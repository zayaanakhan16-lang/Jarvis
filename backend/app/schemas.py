"""Pydantic request/response schemas.

These are the API contract. Response models only ever contain data that exists
in the database or was returned by a real service call.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- System ----------------------------------------------------------------
class HealthResponse(BaseModel):
    status: str
    app: str
    environment: str
    database: str
    websocket_subscribers: int
    version: str


class OverviewStats(BaseModel):
    projects_total: int
    projects_active: int
    tasks_total: int
    tasks_running: int
    tasks_completed: int
    tasks_failed: int
    tasks_waiting_approval: int
    agents_total: int
    agents_busy: int
    providers_configured: int
    providers_connected: int
    integrations_configured: int
    integrations_connected: int
    pending_approvals: int
    artifacts_total: int
    hackathons_tracked: int
    tokens_used: int
    estimated_cost_usd: float
    recent_errors: int


# --- Projects ---------------------------------------------------------------
class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    objective: str | None = None
    repository: str | None = None
    coding_engine: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = None
    objective: str | None = None
    status: str | None = None
    repository: str | None = None
    coding_engine: str | None = None


class ProjectOut(ORMModel):
    id: str
    name: str
    slug: str
    description: str | None
    objective: str | None
    status: str
    repository: str | None
    coding_engine: str | None
    created_at: datetime
    updated_at: datetime
    task_count: int = 0
    completed_count: int = 0


class MemoryCreate(BaseModel):
    category: str = Field(min_length=1, max_length=64)
    key: str = Field(min_length=1, max_length=200)
    value: str
    source: str | None = None
    approved: bool = False


class MemoryOut(ORMModel):
    id: str
    project_id: str
    category: str
    key: str
    value: str
    source: str | None
    approved: bool
    created_at: datetime
    updated_at: datetime


# --- Tasks ------------------------------------------------------------------
class PlanRequest(BaseModel):
    objective: str = Field(min_length=3)
    project_id: str | None = None
    max_tasks: int = Field(default=8, ge=1, le=20)
    provider: str | None = None
    model: str | None = None
    context: dict[str, Any] | None = None


class ExecuteRequest(BaseModel):
    task_ids: list[str] | None = None
    project_id: str | None = None
    max_parallel: int | None = Field(default=None, ge=1, le=8)
    provider: str | None = None
    model: str | None = None


class TaskOut(ORMModel):
    id: str
    project_id: str | None
    title: str
    description: str
    task_type: str
    department: str
    agent_key: str | None
    status: str
    priority: int
    provider: str | None
    model: str | None
    result: str | None
    result_data: dict[str, Any] | None
    error: str | None
    depends_on: list[str]
    requires_approval: bool
    attempts: int
    tokens_used: int
    cost_usd: float
    duration_ms: int | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class PlanResponse(BaseModel):
    project_id: str | None
    tasks: list[TaskOut]
    summary: str | None = None


class ExecutionResult(BaseModel):
    executed: int
    completed: int
    failed: int
    skipped: int
    waiting_approval: int = 0
    results: list[dict[str, Any]]


class RunRequest(BaseModel):
    """Direct single-task run, used by the workspace for one-off prompts."""

    prompt: str = Field(min_length=3)
    task_type: str = "analysis"
    agent_key: str | None = None
    project_id: str | None = None
    provider: str | None = None
    model: str | None = None
    use_tools: bool = False


# --- Agents -----------------------------------------------------------------
class AgentOut(ORMModel):
    key: str
    name: str
    department: str
    description: str
    capabilities: list[str]
    tools: list[str]
    task_types: list[str]
    permission_scope: list[str]
    status: str
    current_task_id: str | None
    tasks_completed: int
    tasks_failed: int
    last_error: str | None
    last_active_at: datetime | None


class DepartmentOut(BaseModel):
    key: str
    name: str
    description: str
    agent_count: int
    busy_count: int


# --- Providers --------------------------------------------------------------
class ProviderOut(BaseModel):
    key: str
    name: str
    kind: str
    base_url: str | None
    required_env: list[str]
    configured: bool
    connected: bool
    status: str
    # Models the provider itself reported. Empty until a probe succeeds, so the
    # UI can never present an unverified identifier as available.
    models: list[str]
    # Curated identifiers we suggest for this provider. Suggestions only.
    catalogue: list[str] = []
    default_model: str | None
    last_tested_at: datetime | None
    last_error: str | None
    details: dict[str, Any]
    docs_url: str | None = None


class ProbeResultOut(BaseModel):
    key: str
    ok: bool
    status: str
    message: str
    models: list[str]
    latency_ms: int


class RoutePreviewRequest(BaseModel):
    task_type: str


class RoutePreviewResponse(BaseModel):
    provider: str
    model: str
    reason: str
    alternatives: list[str]
    score: float


# --- Integrations -----------------------------------------------------------
class IntegrationOut(BaseModel):
    key: str
    name: str
    category: str
    description: str
    docs_url: str | None
    required_env: list[str]
    configured: bool
    connected: bool
    status: str
    last_tested_at: datetime | None
    last_error: str | None
    details: dict[str, Any]


# --- Activity ---------------------------------------------------------------
class EventOut(ORMModel):
    id: str
    project_id: str | None
    task_id: str | None
    agent_key: str | None
    type: str
    level: str
    message: str
    data: dict[str, Any]
    created_at: datetime


# --- Approvals --------------------------------------------------------------
class ApprovalOut(ORMModel):
    id: str
    project_id: str | None
    task_id: str | None
    action_type: str
    title: str
    description: str
    payload: dict[str, Any]
    status: str
    requested_by: str | None
    decided_by: str | None
    decision_note: str | None
    created_at: datetime
    decided_at: datetime | None


class ApprovalDecision(BaseModel):
    approved: bool
    note: str | None = None
    decided_by: str | None = None


# --- Artifacts --------------------------------------------------------------
class ArtifactOut(ORMModel):
    id: str
    project_id: str | None
    task_id: str | None
    kind: str
    title: str
    content: str
    data: dict[str, Any]
    approved: bool
    created_at: datetime


# --- Hackathon --------------------------------------------------------------
class HackathonOut(ORMModel):
    id: str
    project_id: str | None
    name: str
    organizer: str | None
    url: str | None
    source_urls: list[str]
    registration_deadline: str | None
    event_start: str | None
    event_end: str | None
    location: str | None
    is_online: bool | None
    age_restrictions: str | None
    country_restrictions: str | None
    team_requirements: str | None
    tracks: list[str]
    prizes: str | None
    submission_requirements: str | None
    judging_criteria: str | None
    eligibility_notes: str | None
    verified: bool
    verification_notes: str | None
    last_verified_at: datetime | None


# --- Coding sessions --------------------------------------------------------
class SessionOut(ORMModel):
    id: str
    project_id: str | None
    task_id: str | None
    engine: str
    remote_id: str | None
    title: str
    status: str
    repository: str | None
    branch: str | None
    workspace_dir: str | None
    ui_url: str | None
    details: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class SessionCreate(BaseModel):
    engine: str = "openhands"
    task: str = Field(min_length=3)
    project_id: str | None = None
    repository: str | None = None
    branch: str | None = None
    title: str | None = None


# --- Voice ------------------------------------------------------------------
class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    voice_id: str | None = None


class VoiceCommandRequest(BaseModel):
    transcript: str = Field(min_length=2)
    project_id: str | None = None
    auto_execute: bool = False


class VoiceCommandResponse(BaseModel):
    understood: bool
    intent: str
    response: str
    plan_created: bool = False
    task_ids: list[str] = []
    requires_approval: bool = False


# --- Settings ---------------------------------------------------------------
class SettingsOut(BaseModel):
    routing_preference: list[str]
    max_parallel_tasks: int
    default_engine: str
    database_backend: str
    environment: str


class SettingsUpdate(BaseModel):
    routing_preference: list[str] | None = None
    max_parallel_tasks: int | None = Field(default=None, ge=1, le=8)
    default_engine: str | None = None
