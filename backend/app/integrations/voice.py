"""Voice integrations.

ElevenLabs provides text-to-speech and speech-to-text. Browser-native Web Speech
APIs are also supported by the frontend, so voice works without any credential;
this adapter covers the higher-quality hosted option.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.integrations.base import ConnectionTest, Integration, IntegrationError


class ElevenLabsIntegration(Integration):
    key = "elevenlabs"
    name = "ElevenLabs"
    category = "voice"
    description = (
        "Hosted text-to-speech and speech-to-text. Without a key, JARVIS falls "
        "back to the browser's built-in speech APIs."
    )
    docs_url = "https://elevenlabs.io/docs/api-reference"
    required_env = ("ELEVENLABS_API_KEY",)

    def __init__(self, token: str | None = None, base_url: str | None = None):
        super().__init__(token=token, base_url=base_url or "https://api.elevenlabs.io")

    def _headers(self) -> dict[str, str]:
        return {"xi-api-key": self.token or "", "Accept": "application/json"}

    async def test_connection(self) -> ConnectionTest:
        if not self.configured:
            return self._not_configured(
                "Set ELEVENLABS_API_KEY for hosted voices. The browser's built-in "
                "speech synthesis and recognition work without a key."
            )
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                response = await client.get(
                    f"{self.base_url.rstrip('/')}/v1/voices", headers=self._headers()
                )
        except httpx.HTTPError as exc:
            return ConnectionTest(ok=False, status="error",
                                  message=f"Could not reach ElevenLabs: {exc}",
                                  latency_ms=self._elapsed_ms(started))
        if response.status_code >= 400:
            error = self._error_from_response(response, self.name)
            return ConnectionTest(ok=False, status="error", message=str(error),
                                  latency_ms=self._elapsed_ms(started))
        payload = response.json()
        voices = payload.get("voices") if isinstance(payload, dict) else None
        count = len(voices) if isinstance(voices, list) else 0
        return ConnectionTest(
            ok=True,
            status="connected",
            message=f"Authenticated. {count} voices available.",
            latency_ms=self._elapsed_ms(started),
            details={"voice_count": count},
        )

    async def list_voices(self) -> list[dict[str, Any]]:
        if not self.configured:
            raise IntegrationError(
                "ElevenLabs is not configured: set ELEVENLABS_API_KEY.", integration=self.key
            )
        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.get(
                f"{self.base_url.rstrip('/')}/v1/voices", headers=self._headers()
            )
        if response.status_code >= 400:
            raise self._error_from_response(response, self.name)
        voices = response.json().get("voices") or []
        return [
            {"voice_id": v.get("voice_id"), "name": v.get("name"),
             "category": v.get("category")}
            for v in voices
        ]

    async def synthesise(self, text: str, voice_id: str) -> bytes:
        """Return MP3 audio bytes for ``text``."""
        if not self.configured:
            raise IntegrationError(
                "ElevenLabs is not configured: set ELEVENLABS_API_KEY.", integration=self.key
            )
        url = f"{self.base_url.rstrip('/')}/v1/text-to-speech/{voice_id}"
        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(
                url,
                headers={**self._headers(), "Accept": "audio/mpeg",
                         "Content-Type": "application/json"},
                json={
                    "text": text[:5000],
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
                },
            )
        if response.status_code >= 400:
            raise self._error_from_response(response, self.name)
        return response.content
