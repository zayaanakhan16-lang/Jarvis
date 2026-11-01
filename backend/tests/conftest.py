"""Test fixtures.

Tests run against an isolated SQLite database and never touch the network
unless a test explicitly opts in.
"""

from __future__ import annotations

import os
import tempfile

import pytest

# Point the app at a throwaway database before importing it.
_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="jarvis-tests-"), "test.db")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP_DB}"
os.environ["ENVIRONMENT"] = "test"
for key in (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "DEEPSEEK_API_KEY",
    "MISTRAL_API_KEY",
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
    "TAVILY_API_KEY",
    "BRAVE_API_KEY",
    "SERPER_API_KEY",
    "ELEVENLABS_API_KEY",
    "VERCEL_TOKEN",
    "RAILWAY_TOKEN",
):
    os.environ.pop(key, None)
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:1"


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client():
    """An HTTP client bound to the real ASGI app with a fresh database."""
    import httpx

    from app.database import init_models
    from app.main import app

    await init_models()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def session():
    from app.database import SessionLocal, init_models

    await init_models()
    async with SessionLocal() as db:
        yield db
