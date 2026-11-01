"""Department and agent registry.

Every agent declared here is executable: it has a task type the runner knows how
to handle, a model preference the router understands, and a permission scope
that decides whether its actions need human approval.

Agents are added only when they can do real work. There are no decorative
entries.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AgentSpec:
    key: str
    name: str
    department: str
    description: str
    task_type: str
    capabilities: tuple[str, ...]
    tools: tuple[str, ...] = ()
    permission_scope: tuple[str, ...] = ("read",)
    requires_approval_for: tuple[str, ...] = ()
    model_preference: str | None = None


@dataclass(frozen=True, slots=True)
class DepartmentSpec:
    key: str
    name: str
    description: str
    agents: tuple[str, ...] = field(default_factory=tuple)


# (key, name, department, task_type, capabilities, tools, permissions, approvals)
# Kept as a compact table so the whole roster is readable at a glance.
_ROSTER: tuple[tuple, ...] = (
    (
        "chief_orchestrator", "Chief Orchestrator", "executive", "planning",
        "Decomposes a high-level objective into a dependency-aware task graph and "
        "assigns each task to a specialist agent.",
        ("task decomposition", "dependency analysis", "agent assignment"),
        ("planner", "task_registry"), ("read", "plan"), (),
    ),
    (
        "planning_agent", "Planning Agent", "executive", "planning",
        "Turns goals into structured, ordered, estimable tasks.",
        ("goal analysis", "sequencing", "complexity estimation"),
        ("planner",), ("read", "plan"), (),
    ),
    (
        "coordinator_agent", "Coordinator Agent", "executive", "analysis",
        "Manages task queues, parallel execution and dependency resolution.",
        ("queue management", "parallelism", "dependency resolution"),
        ("task_registry",), ("read", "plan"), (),
    ),
    (
        "memory_agent", "Memory Agent", "executive", "summarisation",
        "Retrieves and maintains project-scoped context so work is not repeated.",
        ("context retrieval", "summarisation", "deduplication"),
        ("project_memory",), ("read", "memory_write"), (),
    ),
    (
        "hackathon_discovery", "Hackathon Discovery Agent", "hackathon", "research",
        "Searches for hackathons matching the user's criteria and records only what "
        "it can source. Never invents prizes, dates or eligibility rules.",
        ("web research", "opportunity discovery", "source collection"),
        ("web_search", "url_fetch"), ("read", "network"), (),
    ),
    (
        "eligibility_agent", "Eligibility Agent", "hackathon", "analysis",
        "Checks age, country, format and team rules against official sources.",
        ("eligibility checking", "rule extraction"),
        ("url_fetch",), ("read", "network"), (),
    ),
    (
        "rules_analyst", "Rules Analyst", "hackathon", "analysis",
        "Extracts submission rules, deadlines and required deliverables.",
        ("rule extraction", "deadline analysis", "deliverable mapping"),
        ("url_fetch",), ("read", "network"), (),
    ),
    (
        "judging_criteria_agent", "Judging Criteria Agent", "hackathon", "analysis",
        "Analyses judging criteria and maps product requirements to them.",
        ("criteria analysis", "scoring alignment"),
        ("url_fetch",), ("read", "network"), (),
    ),
    (
        "problem_research", "Problem Research Agent", "research", "research",
        "Investigates whether a problem is real, who has it and how often.",
        ("problem validation", "user research", "evidence gathering"),
        ("web_search",), ("read", "network"), (),
    ),
    (
        "competitor_research", "Competitor Research Agent", "research", "research",
        "Studies existing solutions and identifies gaps.",
        ("competitor analysis", "gap identification"),
        ("web_search",), ("read", "network"), (),
    ),
    (
        "idea_development", "Idea Development Agent", "research", "analysis",
        "Generates differentiated product concepts and scores them honestly.",
        ("ideation", "differentiation", "scoring"),
        (), ("read",), (),
    ),
    (
        "feasibility_agent", "Technical Feasibility Agent", "research", "architecture",
        "Assesses build complexity, required technology and realistic scope.",
        ("feasibility analysis", "scope estimation", "technology selection"),
        (), ("read",), (),
    ),
    (
        "product_strategy", "Product Strategy Agent", "research", "planning",
        "Defines product direction, target users and feature scope.",
        ("product definition", "prioritisation", "user definition"),
        (), ("read",), (),
    ),
)


_ROSTER = _ROSTER + (
    (
        "brand_strategist", "Brand Strategist", "creative", "branding",
        "Defines brand positioning, voice and identity direction.",
        ("positioning", "voice", "identity strategy"),
        (), ("read", "memory_write"), (),
    ),
    (
        "naming_agent", "Naming Agent", "creative", "branding",
        "Generates and evaluates product names with rationale.",
        ("naming", "evaluation", "taglines"),
        (), ("read",), (),
    ),
    (
        "visual_identity_agent", "Visual Identity Agent", "creative", "ui_design",
        "Produces design tokens: palette, typography, spacing and elevation.",
        ("design tokens", "colour systems", "typography"),
        ("design_tokens",), ("read", "memory_write"), (),
    ),
    (
        "uiux_designer", "UI/UX Designer", "creative", "ui_design",
        "Plans user flows and screen-level interfaces.",
        ("user flows", "screen design", "information architecture"),
        ("design_tokens",), ("read",), (),
    ),
    (
        "prototype_designer", "Prototype Designer", "creative", "ui_design",
        "Turns approved design decisions into interactive prototype specs.",
        ("prototyping", "component specification"),
        ("design_tokens",), ("read",), (),
    ),
    (
        "frontend_engineer", "Frontend Engineer", "engineering", "coding",
        "Builds responsive interfaces from the approved design system.",
        ("frontend", "components", "accessibility"),
        ("coding_engine", "file_system", "terminal"), ("read", "write", "execute"), (),
    ),
    (
        "backend_engineer", "Backend Engineer", "engineering", "coding",
        "Builds APIs, services and persistence.",
        ("backend", "api design", "persistence"),
        ("coding_engine", "file_system", "terminal"), ("read", "write", "execute"), (),
    ),
    (
        "ai_integration_engineer", "AI Integration Engineer", "engineering", "coding",
        "Integrates model providers and AI services into a product.",
        ("ai integration", "prompt engineering", "provider wiring"),
        ("coding_engine", "file_system"), ("read", "write"), (),
    ),
    (
        "database_engineer", "Database Engineer", "engineering", "architecture",
        "Designs schemas, migrations and queries.",
        ("schema design", "migrations", "query optimisation"),
        ("coding_engine", "file_system"), ("read", "write"), (),
    ),
    (
        "fullstack_coding_agent", "Full-Stack Coding Agent", "engineering", "coding",
        "Coordinates end-to-end implementation through a coding engine.",
        ("full-stack implementation", "repository work", "task coordination"),
        ("coding_engine", "file_system", "terminal", "git"),
        ("read", "write", "execute"), ("push", "deploy"),
    ),
)


_ROSTER = _ROSTER + (
    (
        "code_reviewer", "Code Reviewer", "quality", "code_review",
        "Reviews architecture and code quality with concrete findings.",
        ("code review", "architecture review", "risk identification"),
        ("file_system",), ("read",), (),
    ),
    (
        "testing_agent", "Testing Agent", "quality", "testing",
        "Runs test suites and reports real pass/fail results.",
        ("test execution", "coverage analysis", "result reporting"),
        ("terminal", "coding_engine"), ("read", "execute"), (),
    ),
    (
        "debugging_agent", "Debugging Agent", "quality", "debugging",
        "Investigates failures, forms hypotheses and proposes fixes.",
        ("failure diagnosis", "root cause analysis", "fix proposals"),
        ("terminal", "file_system", "coding_engine"), ("read", "execute"), (),
    ),
    (
        "security_agent", "Security Agent", "quality", "security",
        "Reviews for injection, secret exposure, authz and data handling risks.",
        ("security review", "secret scanning", "authorisation review"),
        ("file_system",), ("read",), (),
    ),
    (
        "performance_agent", "Performance Agent", "quality", "analysis",
        "Identifies performance problems and proposes measurable fixes.",
        ("performance analysis", "profiling guidance", "optimisation"),
        ("terminal",), ("read", "execute"), (),
    ),
    (
        "github_agent", "GitHub Agent", "devops", "deployment",
        "Handles repository workflows. Push and PR creation require approval.",
        ("repository management", "branching", "pull requests"),
        ("github",), ("read", "write"),
        ("create_repository", "push", "open_pull_request"),
    ),
    (
        "deployment_agent", "Deployment Agent", "devops", "deployment",
        "Prepares deployment configuration and previews. Never deploys without approval.",
        ("deployment preparation", "environment configuration"),
        ("vercel", "railway"), ("read", "write"), ("deploy_production",),
    ),
    (
        "infrastructure_agent", "Infrastructure Agent", "devops", "deployment",
        "Manages configuration, containers and infrastructure definitions.",
        ("infrastructure as code", "container configuration"),
        ("file_system", "docker"), ("read", "write"), (),
    ),
    (
        "presentation_agent", "Presentation Agent", "media", "presentation",
        "Builds research-backed pitch deck content.",
        ("narrative structure", "slide content", "evidence linking"),
        (), ("read",), (),
    ),
    (
        "thumbnail_agent", "Thumbnail Agent", "media", "ui_design",
        "Prepares thumbnail concepts and specifications.",
        ("visual concepts", "thumbnail specification"),
        ("design_tokens",), ("read",), (),
    ),
    (
        "demo_agent", "Demo Agent", "media", "documentation",
        "Plans demo scripts, narration and recording sequences.",
        ("demo scripting", "narration", "recording planning"),
        (), ("read",), (),
    ),
    (
        "documentation_agent", "Documentation Agent", "media", "documentation",
        "Writes documentation grounded in the actual implementation.",
        ("technical writing", "readme generation", "api documentation"),
        ("file_system",), ("read", "write"), (),
    ),
    (
        "submission_agent", "Submission Agent", "media", "documentation",
        "Prepares the submission package. Submitting always requires approval.",
        ("submission preparation", "devpost packaging"),
        (), ("read",), ("submit_entry",),
    ),
)


AGENTS: tuple[AgentSpec, ...] = tuple(
    AgentSpec(
        key=row[0],
        name=row[1],
        department=row[2],
        task_type=row[3],
        description=row[4],
        capabilities=tuple(row[5]),
        tools=tuple(row[6]),
        permission_scope=tuple(row[7]),
        requires_approval_for=tuple(row[8]),
    )
    for row in _ROSTER
)

AGENT_BY_KEY: dict[str, AgentSpec] = {agent.key: agent for agent in AGENTS}


_DEPARTMENT_META: tuple[tuple[str, str, str], ...] = (
    ("executive", "Executive", "Orchestration, planning, coordination and memory."),
    ("hackathon", "Hackathon Intelligence", "Discovery, eligibility, rules and judging criteria analysis."),
    ("research", "Product Research", "Problem validation, competitor analysis, ideation and feasibility."),
    ("creative", "Creative Studio", "Branding, naming, visual identity, UI/UX and prototyping."),
    ("engineering", "Engineering", "Frontend, backend, AI integration, database and full-stack delivery."),
    ("quality", "Quality", "Code review, testing, debugging, security and performance."),
    ("devops", "DevOps", "Repositories, deployment preparation and infrastructure."),
    ("media", "Media and Submission", "Presentations, thumbnails, demos, documentation and submissions."),
)

DEPARTMENTS: tuple[DepartmentSpec, ...] = tuple(
    DepartmentSpec(
        key=key,
        name=name,
        description=description,
        agents=tuple(a.key for a in AGENTS if a.department == key),
    )
    for key, name, description in _DEPARTMENT_META
)

DEPARTMENT_BY_KEY: dict[str, DepartmentSpec] = {dept.key: dept for dept in DEPARTMENTS}


def agents_for_department(department: str) -> list[AgentSpec]:
    return [a for a in AGENTS if a.department == department]


def agent_for_task_type(task_type: str) -> AgentSpec | None:
    """Default agent for a task type, used when the planner names none."""
    for agent in AGENTS:
        if agent.task_type == task_type:
            return agent
    return None
