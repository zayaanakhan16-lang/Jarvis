<div align="center">

<img src="assets/jarvis-logo.png" alt="JARVIS" width="150" />

# JARVIS

**Autonomous multi-model AI development platform**

Give JARVIS an objective. It plans, assigns specialist agents, executes with real
models, and reports back — honestly.

</div>

---

## What this is

JARVIS coordinates specialised AI agents, multiple model providers and external
tools to take a software objective from idea to a finished, reviewed artifact.

It is not a chatbot wrapper and not a dashboard mockup. Every number on screen is
read from the backend, every provider state is the result of a real network
probe, and every agent status reflects actual execution. When something is not
configured or not verified, the interface says so instead of inventing a value.

## Design commitments

These are enforced in code, not just documented:

- **No fabricated state.** A provider is shown as *connected* only after a real
  request succeeds. Configured-but-untested is shown as *configured*. Anything
  unknown is labelled *not verified*.
- **No silent provider switching.** If you pin a provider, JARVIS uses it or
  fails with the reason. It never quietly routes your task to a different vendor.
- **Real activity only.** The event log is written by the orchestrator as work
  happens. There are no timers generating fake activity.
- **Approval gates.** Pushing code, opening pull requests, deploying, spending
  money and submitting entries are prepared, then held for your explicit
  approval.
- **Failures are reported.** A task that cannot run returns the real error, not
  a plausible-looking placeholder.

## Screens

| Section | What it does |
|---|---|
| **Overview** | Live system state: projects, tasks, agents, provider health, pending approvals |
| **AI Workspace** | The primary surface — state an objective, review the plan, execute it |
| **Agents** | The full roster: 36 agents across 8 departments with real execution state |
| **Hackathon Intelligence** | Discover opportunities and verify eligibility against official sources |
| **Product Research** | Dispatch research agents to validate problems and develop ideas |
| **Creative Studio** | Naming, brand, visual identity, UI flows and prototypes |
| **Engineering** | Isolated coding-engine sessions with real status tracking |
| **Projects** | Objectives, tasks, project memory and artifacts |
| **Integrations** | Providers and services with real connection tests |
| **Activity** | Persistent event log streamed over WebSocket, plus the approval queue |
| **Settings** | Runtime configuration and the exact env var that enables each capability |

## Architecture

```
frontend/                    React 18 + TypeScript + Tailwind (Vite)
  src/lib/api.ts             Typed API client — the only place that talks to the backend
  src/lib/hooks.ts           useQuery + WebSocket activity stream
  src/pages/                 One component per navigation section

backend/                     FastAPI + SQLAlchemy (async)
  app/providers/             Model provider adapters + capability router
  app/agents/registry.py     The agent roster: departments, capabilities, permissions
  app/services/orchestrator.py   Planning, execution, dependency ordering
  app/integrations/          Coding engines, GitHub, research, voice, deployment
  app/routers/               HTTP + WebSocket API
```

### Model provider layer

Nine providers behind one interface: OpenAI, Anthropic, Gemini, DeepSeek,
Mistral, Groq, OpenRouter, Ollama and any OpenAI-compatible endpoint. Each
adapter handles streaming, timeouts, retries and rate limits. The router selects
a model per task type from capability, context limits, cost and latency — and it
never crosses a provider boundary you have pinned.

Models are **discovered**, not hardcoded. The model list for each provider is
fetched from that provider's own API.

### Agent execution layer

36 agents in 8 departments (Executive, Hackathon Intelligence, Product Research,
Creative Studio, Engineering, Quality, DevOps, Media and Submission). Each
declares its capabilities, permitted tools and permission scope. Tasks run in
dependency order, independent tasks run in parallel up to a configured limit, and
project memory is scoped per project so context never leaks between them.

## Getting started

### Requirements

- Python 3.11+
- Node.js 18+

### Run it

```bash
git clone https://github.com/zayaanakhan16-lang/Jarvis.git
cd Jarvis
cp .env.example .env      # optional — it starts with nothing configured
./run.sh
```

- Frontend → http://127.0.0.1:3000
- Backend → http://127.0.0.1:8000
- API docs → http://127.0.0.1:8000/docs

### Configure a model

JARVIS starts and reports that no provider is connected. To run tasks, set at
least one key in `.env`:

```bash
OPENAI_API_KEY=sk-...
# or ANTHROPIC_API_KEY, GEMINI_API_KEY, DEEPSEEK_API_KEY,
#    MISTRAL_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY
```

Or run a local model with no key at all:

```bash
ollama serve
ollama pull llama3.1
```

Then open **Integrations** and press **Test** on that provider. It performs a
real request; only on success does it show as connected.

### Optional capabilities

| Capability | Environment variable |
|---|---|
| Web search (research agents) | `TAVILY_API_KEY` / `BRAVE_API_KEY` / `SERPER_API_KEY` |
| OpenHands coding engine | `OPENHANDS_API_KEY` |
| GitHub | `GITHUB_TOKEN` |
| Hosted voice | `ELEVENLABS_API_KEY` |
| Deployment prep | `VERCEL_TOKEN` / `RAILWAY_TOKEN` |
| PostgreSQL instead of SQLite | `DATABASE_URL` |

## Development

```bash
# Backend tests
cd backend && ./.venv/bin/python -m pytest -q

# Frontend typecheck and build
cd frontend && npx tsc --noEmit && npx vite build
```

## Database

SQLite by default — no setup required. For PostgreSQL, set `DATABASE_URL` to a
`postgresql+asyncpg://` URL and restart. Schema is created on startup.

## Security

- Credentials are read server-side from the environment only. No key is ever
  sent to the browser; the API returns configuration flags, not secrets.
- Input is validated with Pydantic at every boundary.
- Code execution runs in isolated workspaces, never against the host.
- Actions with external effect require approval and are recorded in the audit log.
- `.env` is gitignored; `.env.example` documents every variable with no values.

## Licence

MIT
