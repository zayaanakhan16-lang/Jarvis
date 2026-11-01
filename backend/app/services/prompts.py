"""Prompt library.

Each agent task type has a system prompt that encodes the honesty rules the
product depends on: never invent facts, label unknowns, cite sources. These are
not decorative strings - they are the contract that keeps output trustworthy.
"""

from __future__ import annotations

import json
from typing import Any

HONESTY_RULES = """
Non-negotiable accuracy rules:
- Never invent facts, statistics, dates, prizes, deadlines, prices, benchmarks
  or eligibility rules. If you do not know something, write "unknown".
- When you state a factual claim that comes from a source, give the URL. If you
  have no source, say the claim is unverified.
- Do not describe work as complete, tested or working unless you were told so.
- Prefer "I could not verify X" over a confident guess.
- Be concrete. Avoid filler, marketing language and vague adjectives.
""".strip()


def _json_contract(schema_hint: str) -> str:
    return (
        "Respond with a single valid JSON object and nothing else. No markdown "
        "fences, no commentary.\n\nRequired shape:\n"
        f"{schema_hint}"
    )


PLANNING_SCHEMA = """{
  "summary": "one paragraph describing the approach",
  "assumptions": ["assumption you are making"],
  "risks": ["risk and its mitigation"],
  "tasks": [
    {
      "id": "t1",
      "title": "short imperative title",
      "description": "what to do and what done looks like",
      "task_type": "research|analysis|architecture|planning|coding|code_review|testing|debugging|security|ui_design|branding|presentation|documentation|deployment|summarisation",
      "department": "executive|hackathon|research|creative|engineering|quality|devops|media",
      "agent_key": "agent key from the roster, or null",
      "depends_on": ["t1"],
      "priority": 1,
      "requires_approval": false,
      "deliverable": "the concrete artifact this task produces"
    }
  ]
}"""

RESEARCH_SCHEMA = """{
  "summary": "what you found",
  "findings": [
    {"claim": "a specific factual claim", "evidence": "how you know", "source": "url or unknown", "confidence": "high|medium|low"}
  ],
  "unknowns": ["things you could not verify"],
  "recommendations": ["what to do next"]
}"""

IDEATION_SCHEMA = """{
  "ideas": [
    {
      "name": "product concept name",
      "one_liner": "what it is in one sentence",
      "problem": "the specific problem it solves",
      "target_user": "who exactly has this problem",
      "differentiation": "why this is not a generic clone",
      "core_features": ["feature"],
      "feasible_scope": "what is realistically buildable in the stated time",
      "scores": {"originality": 0, "usefulness": 0, "feasibility": 0, "user_clarity": 0, "data_availability": 0, "build_complexity": 0, "demo_potential": 0, "track_fit": 0},
      "risks": ["risk"]
    }
  ],
  "recommended": "name of the idea you recommend",
  "reasoning": "why, including honest trade-offs"
}"""

BRANDING_SCHEMA = """{
  "names": [{"name": "candidate", "rationale": "why it works", "risks": "domain/trademark considerations you cannot verify"}],
  "recommended_name": "name",
  "taglines": ["tagline"],
  "positioning": "one paragraph",
  "voice": {"tone": "description", "avoid": ["thing to avoid"]}
}"""

DESIGN_TOKENS_SCHEMA = """{
  "concept": "the visual concept in one paragraph",
  "colors": {
    "background": "#hex", "surface": "#hex", "border": "#hex",
    "primary": "#hex", "primary_soft": "#hex", "accent": "#hex",
    "text_primary": "#hex", "text_muted": "#hex",
    "success": "#hex", "warning": "#hex", "danger": "#hex"
  },
  "typography": {
    "heading_font": "font family", "body_font": "font family",
    "mono_font": "font family",
    "scale": {"display": "px", "h1": "px", "h2": "px", "h3": "px", "body": "px", "caption": "px"}
  },
  "spacing": {"unit": "px", "scale": [4, 8, 12, 16, 24, 32, 48]},
  "radius": {"sm": "px", "md": "px", "lg": "px", "full": "9999px"},
  "rationale": "why these choices suit the product"
}"""

UI_FLOWS_SCHEMA = """{
  "primary_flow": {"name": "flow name", "steps": [{"screen": "name", "purpose": "why", "key_elements": ["element"], "empty_state": "what shows with no data"}]},
  "secondary_flows": [{"name": "flow name", "steps": ["step"]}],
  "component_inventory": [{"name": "component", "purpose": "why it exists", "states": ["default", "loading", "empty", "error"]}],
  "accessibility_notes": ["note"]
}"""

CODE_REVIEW_SCHEMA = """{
  "summary": "overall assessment",
  "findings": [
    {"severity": "critical|high|medium|low", "category": "correctness|security|performance|maintainability", "location": "file:line or area", "issue": "what is wrong", "recommendation": "concrete fix"}
  ],
  "tested": "what you actually inspected versus assumed",
  "blocking": true
}"""

SECURITY_SCHEMA = """{
  "summary": "overall risk posture",
  "findings": [
    {"severity": "critical|high|medium|low", "category": "injection|secrets|authz|data_exposure|dependencies|configuration", "location": "where", "issue": "the risk", "remediation": "specific fix"}
  ],
  "verified_absent": ["risk you specifically checked for and did not find"],
  "not_reviewed": ["area you could not assess and why"]
}"""

HACKATHON_SCHEMA = """{
  "opportunities": [
    {
      "name": "exact event name",
      "organizer": "name or unknown",
      "url": "official url or unknown",
      "source_urls": ["url you actually saw this on"],
      "registration_deadline": "date or unknown",
      "event_start": "date or unknown",
      "event_end": "date or unknown",
      "location": "place or unknown",
      "is_online": null,
      "age_restrictions": "text or unknown",
      "country_restrictions": "text or unknown",
      "team_requirements": "text or unknown",
      "tracks": ["track"],
      "prizes": "text or unknown",
      "submission_requirements": "text or unknown",
      "judging_criteria": "text or unknown",
      "eligibility_notes": "your assessment for this specific user",
      "verified": false,
      "verification_notes": "what you could and could not confirm"
    }
  ],
  "search_summary": "what you searched and what you found",
  "caveats": ["important limitation of this result"]
}"""

PRESENTATION_SCHEMA = """{
  "title": "deck title",
  "tagline": "one line",
  "slides": [
    {"title": "slide title", "purpose": "why this slide exists", "bullets": ["point"], "speaker_notes": "what to say", "evidence": "source or unknown"}
  ],
  "demo_script": {"duration_seconds": 0, "beats": [{"at_seconds": 0, "action": "what to show", "narration": "what to say"}]},
  "submission_package": {
    "devpost_title": "title", "tagline": "tagline", "short_description": "text",
    "full_description": "markdown", "built_with": ["technology"],
    "screenshots_needed": ["description of shot"],
    "track_suggestions": ["track"],
    "incomplete_or_unverified": ["claim that still needs verification before submitting"]
  }
}"""

DOCUMENTATION_SCHEMA = """{
  "title": "doc title",
  "summary": "what this documents",
  "sections": [{"heading": "heading", "body": "markdown body"}],
  "verified_against": "what you actually read to write this",
  "gaps": ["thing not documented and why"]
}"""

TEXT_TASK_PROMPT = """You are the {agent_name} in the {department} department of JARVIS.

{agent_description}

Capabilities you are expected to apply: {capabilities}

{rules}
"""


def system_prompt(
    *,
    agent_name: str,
    department: str,
    agent_description: str,
    capabilities: list[str] | tuple[str, ...] = (),
    json_schema: str | None = None,
    extra_rules: str | None = None,
) -> str:
    base = TEXT_TASK_PROMPT.format(
        agent_name=agent_name,
        department=department,
        agent_description=agent_description,
        capabilities=", ".join(capabilities) or "general analysis",
        rules=HONESTY_RULES,
    )
    if extra_rules:
        base = f"{base}\n\n{extra_rules.strip()}"
    if json_schema:
        base = f"{base}\n\n{_json_contract(json_schema)}"
    return base


def project_context_block(context: dict[str, Any] | None) -> str:
    """Render retrieved project memory for inclusion in a prompt."""
    if not context:
        return ""
    lines = ["Project context retrieved from memory (use it, do not contradict it):"]
    for key, value in context.items():
        if value in (None, "", [], {}):
            continue
        rendered = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        lines.append(f"- {key}: {rendered}")
    return "\n".join(lines) if len(lines) > 1 else ""


# Task type -> (schema, extra rules)
TASK_TEMPLATES: dict[str, tuple[str | None, str | None]] = {
    "planning": (
        PLANNING_SCHEMA,
        "Produce a task graph that a real system can execute. Every task must have a "
        "concrete deliverable. Mark tasks that touch external systems or spend money "
        "with requires_approval=true.",
    ),
    "research": (RESEARCH_SCHEMA, None),
    "analysis": (RESEARCH_SCHEMA, None),
    "architecture": (RESEARCH_SCHEMA, None),
    "coding": (
        None,
        "Produce implementation guidance precise enough to hand to a coding engine: "
        "file paths, function signatures, data shapes and the acceptance check.",
    ),
    "debugging": (
        None,
        "List ranked hypotheses, the specific evidence that would confirm or eliminate "
        "each one, and the smallest change that would test it.",
    ),
    "code_review": (CODE_REVIEW_SCHEMA, None),
    "testing": (
        None,
        "Describe the test cases that matter: the exact command, the expected result, "
        "and what a failure would indicate.",
    ),
    "security": (SECURITY_SCHEMA, None),
    "ui_design": (UI_FLOWS_SCHEMA, None),
    "branding": (BRANDING_SCHEMA, None),
    "presentation": (PRESENTATION_SCHEMA, None),
    "documentation": (DOCUMENTATION_SCHEMA, None),
    "deployment": (None, None),
    "summarisation": (None, "Compress without losing the decisions and the open questions."),
}


def template_for(task_type: str) -> tuple[str | None, str | None]:
    return TASK_TEMPLATES.get(task_type, (None, None))
