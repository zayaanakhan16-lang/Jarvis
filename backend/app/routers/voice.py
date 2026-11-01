"""Voice routes.

Speech recognition and synthesis are real service calls. When ElevenLabs is not
configured, the API says so explicitly and the frontend uses the browser's own
speech APIs instead of pretending a hosted voice exists.

Voice commands are interpreted by a model and then routed through the same
planning path as typed objectives, so nothing here bypasses approval rules.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_session
from app.integrations.base import IntegrationError
from app.integrations.voice import ElevenLabsIntegration
from app.schemas import SpeakRequest, VoiceCommandRequest, VoiceCommandResponse
from app.services import prompts
from app.services.json_utils import extract_json
from app.services.llm import get_llm_service
from app.services.orchestrator import PlanError, get_orchestrator

router = APIRouter(prefix="/voice", tags=["voice"])

DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # ElevenLabs "Rachel"

INTENT_SCHEMA = """{
  "intent": "research_hackathons|create_project|plan_objective|run_tests|check_status|explain|unknown",
  "objective": "the concrete objective to act on, or null",
  "spoken_response": "one or two sentences to say back to the user",
  "requires_approval": false
}"""


@router.get("/status")
async def voice_status() -> dict:
    """Report which speech capabilities are actually available."""
    settings = get_settings()
    adapter = ElevenLabsIntegration(token=settings.elevenlabs_api_key)
    configured = adapter.configured
    return {
        "elevenlabs_configured": configured,
        "browser_speech_supported": True,
        "text_to_speech": "elevenlabs" if configured else "browser",
        "speech_to_text": "browser",
        "note": (
            "Hosted voices are available."
            if configured
            else "ElevenLabs is not configured, so the browser's built-in speech "
            "synthesis and recognition are used. Set ELEVENLABS_API_KEY to enable "
            "hosted voices."
        ),
    }


@router.post("/speak")
async def speak(payload: SpeakRequest) -> Response:
    settings = get_settings()
    adapter = ElevenLabsIntegration(token=settings.elevenlabs_api_key)
    if not adapter.configured:
        raise HTTPException(
            status_code=503,
            detail=(
                "ElevenLabs is not configured. Set ELEVENLABS_API_KEY for hosted "
                "speech, or use the browser's SpeechSynthesis API."
            ),
        )
    try:
        audio = await adapter.synthesise(payload.text, payload.voice_id or DEFAULT_VOICE_ID)
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Response(content=audio, media_type="audio/mpeg")


@router.post("/command", response_model=VoiceCommandResponse)
async def voice_command(
    payload: VoiceCommandRequest, session: AsyncSession = Depends(get_session)
) -> VoiceCommandResponse:
    """Interpret a spoken instruction and, when asked, act on it."""
    llm = get_llm_service()
    system = prompts.system_prompt(
        agent_name="Chief Orchestrator",
        department="Executive",
        agent_description=(
            "You interpret a spoken instruction from the user and decide what JARVIS "
            "should do. You never claim an action succeeded."
        ),
        capabilities=["intent recognition", "task routing"],
        json_schema=INTENT_SCHEMA,
    )
    prompt = (
        f'The user said: "{payload.transcript}"\n\n'
        "Identify the intent and, if the request maps to a concrete objective, write "
        "that objective precisely in 'objective'. Keep 'spoken_response' short and "
        "plain. Set requires_approval true if acting would touch external systems or "
        "spend money."
    )
    try:
        outcome = await llm.execute(
            session,
            task_type="classification",
            prompt=prompt,
            system=system,
            temperature=0.2,
            max_tokens=600,
            json_mode=True,
            project_id=payload.project_id,
            agent_key="chief_orchestrator",
        )
    except Exception as exc:  # noqa: BLE001 - report the failure to the caller
        raise HTTPException(
            status_code=502,
            detail=f"Could not interpret the voice command: {exc}",
        ) from exc

    parsed, error = extract_json(outcome.result.text)
    if not isinstance(parsed, dict):
        return VoiceCommandResponse(
            understood=False,
            intent="unknown",
            response=f"I could not interpret that instruction ({error}).",
        )

    intent = str(parsed.get("intent") or "unknown")
    spoken = str(parsed.get("spoken_response") or "").strip()
    objective = parsed.get("objective")
    requires_approval = bool(parsed.get("requires_approval"))

    response = VoiceCommandResponse(
        understood=True,
        intent=intent,
        response=spoken or "Understood.",
        requires_approval=requires_approval,
    )

    if not payload.auto_execute or not objective or intent == "unknown":
        return response

    if requires_approval:
        response.response = (
            f"{response.response} This needs your approval before I proceed."
        )
        return response

    orchestrator = get_orchestrator()
    try:
        tasks = await orchestrator.create_plan(
            session,
            objective=str(objective),
            project_id=payload.project_id,
            max_tasks=6,
        )
    except PlanError as exc:
        response.response = f"{response.response} I could not create a plan: {exc}"
        return response

    response.plan_created = True
    response.task_ids = [task.id for task in tasks]
    response.response = (
        f"{response.response} I created a plan with {len(tasks)} task(s); "
        "review it before I execute."
    )
    return response
