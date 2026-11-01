"""JARVIS API application.

Wires the routers, opens the database, seeds the agent registry, and exposes
the health endpoint the frontend uses to prove the backend is reachable.
"""

from __future__ import annotations

import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal, dispose_engine, init_models
from app.routers import (
    activity,
    agents,
    approvals,
    artifacts,
    hackathon,
    integrations,
    projects,
    providers,
    sessions,
    system,
    tasks,
    voice,
)
from app.routers._helpers import ensure_agents_seeded

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_models()
    async with SessionLocal() as session:
        await ensure_agents_seeded(session)
    yield
    await dispose_engine()


app = FastAPI(
    title="JARVIS API",
    description=(
        "Autonomous multi-model AI development platform. Coordinates specialised "
        "agents, model providers and coding engines."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_prefix = settings.api_prefix

app.include_router(system.router, prefix=api_prefix)
app.include_router(projects.router, prefix=api_prefix)
app.include_router(tasks.router, prefix=api_prefix)
app.include_router(agents.router, prefix=api_prefix)
app.include_router(providers.router, prefix=api_prefix)
app.include_router(integrations.router, prefix=api_prefix)
app.include_router(activity.router, prefix=api_prefix)
app.include_router(approvals.router, prefix=api_prefix)
app.include_router(artifacts.router, prefix=api_prefix)
app.include_router(hackathon.router, prefix=api_prefix)
app.include_router(sessions.router, prefix=api_prefix)
app.include_router(voice.router, prefix=api_prefix)


@app.get("/")
async def root() -> JSONResponse:
    return JSONResponse(
        {
            "name": "JARVIS",
            "description": "Autonomous Multi-Model AI Development Platform",
            "version": "1.0.0",
            "docs": "/docs",
            "health": f"{api_prefix}/health",
        }
    )
