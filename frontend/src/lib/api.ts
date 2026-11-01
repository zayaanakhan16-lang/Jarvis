/**
 * Typed API client.
 *
 * Every call surfaces the backend's real error message. There are no fallbacks
 * to placeholder data: if the backend is unreachable the UI shows that fact
 * rather than inventing numbers.
 */

import type {
  ActivityEvent,
  Agent,
  AppSettings,
  Approval,
  Artifact,
  CodingSession,
  Department,
  ExecutionResult,
  Hackathon,
  Health,
  Integration,
  MemoryEntry,
  OverviewStats,
  PlanResponse,
  ProbeResult,
  Project,
  Provider,
  RoutePreview,
  Task,
  VoiceCommandResult,
  VoiceStatus,
} from './types'

const API_BASE =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ??
  '/api'

export class ApiError extends Error {
  readonly status: number
  readonly detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    })
  } catch (cause) {
    throw new ApiError(
      0,
      `Cannot reach the JARVIS API at ${API_BASE}. Is the backend running? (${
        cause instanceof Error ? cause.message : 'network error'
      })`,
    )
  }

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}.`
    try {
      const body = await response.json()
      if (typeof body?.detail === 'string') detail = body.detail
      else if (Array.isArray(body?.detail)) {
        detail = body.detail
          .map((item: { loc?: unknown[]; msg?: string }) =>
            `${(item.loc ?? []).slice(1).join('.')}: ${item.msg ?? 'invalid'}`,
          )
          .join('; ')
      }
    } catch {
      // Non-JSON error body: keep the status-based message.
    }
    throw new ApiError(response.status, detail)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

export const api = {
  // System ---------------------------------------------------------------
  health: () => request<Health>('/health'),
  overview: () => request<OverviewStats>('/overview'),
  departments: () => request<Department[]>('/departments'),
  settings: () => request<AppSettings>('/settings'),
  updateSettings: (payload: Partial<AppSettings>) =>
    request<AppSettings>('/settings', { method: 'PUT', body: JSON.stringify(payload) }),

  // Projects -------------------------------------------------------------
  projects: () => request<Project[]>('/projects'),
  project: (id: string) => request<Project>(`/projects/${id}`),
  createProject: (payload: {
    name: string
    description?: string
    objective?: string
    repository?: string
    coding_engine?: string
  }) => post<Project>('/projects', payload),
  updateProject: (id: string, payload: Partial<Project>) =>
    request<Project>(`/projects/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteProject: (id: string) =>
    request<void>(`/projects/${id}`, { method: 'DELETE' }),
  projectTasks: (id: string) => request<Task[]>(`/projects/${id}/tasks`),
  projectArtifacts: (id: string) => request<Artifact[]>(`/projects/${id}/artifacts`),
  projectMemory: (id: string) => request<MemoryEntry[]>(`/projects/${id}/memory`),
  saveMemory: (
    id: string,
    payload: { category: string; key: string; value: string; approved?: boolean },
  ) => post<MemoryEntry>(`/projects/${id}/memory`, payload),
  deleteMemory: (id: string, entryId: string) =>
    request<void>(`/projects/${id}/memory/${entryId}`, { method: 'DELETE' }),

  // Tasks ----------------------------------------------------------------
  tasks: (params?: { project_id?: string; status?: string }) => {
    const query = new URLSearchParams()
    if (params?.project_id) query.set('project_id', params.project_id)
    if (params?.status) query.set('status', params.status)
    const suffix = query.toString() ? `?${query}` : ''
    return request<Task[]>(`/tasks${suffix}`)
  },
  task: (id: string) => request<Task>(`/tasks/${id}`),
  plan: (payload: {
    objective: string
    project_id?: string
    max_tasks?: number
    provider?: string
    model?: string
  }) => post<PlanResponse>('/tasks/plan', payload),
  execute: (payload: {
    task_ids?: string[]
    project_id?: string
    max_parallel?: number
  }) => post<ExecutionResult>('/tasks/execute', payload),
  run: (payload: {
    prompt: string
    task_type?: string
    agent_key?: string
    project_id?: string
    provider?: string
    model?: string
  }) => post<Task>('/tasks/run', payload),

  // Agents ---------------------------------------------------------------
  agents: (params?: { department?: string; status?: string }) => {
    const query = new URLSearchParams()
    if (params?.department) query.set('department', params.department)
    if (params?.status) query.set('status', params.status)
    const suffix = query.toString() ? `?${query}` : ''
    return request<Agent[]>(`/agents${suffix}`)
  },
  agent: (key: string) => request<Agent>(`/agents/${key}`),
  agentTasks: (key: string) => request<Task[]>(`/agents/${key}/tasks`),

  // Providers ------------------------------------------------------------
  providers: () => request<Provider[]>('/providers'),
  testProvider: (key: string) => post<ProbeResult>(`/providers/${key}/test`),
  routePreview: (taskType: string) =>
    post<RoutePreview>('/providers/route-preview', { task_type: taskType }),

  // Integrations ---------------------------------------------------------
  integrations: () => request<Integration[]>('/integrations'),
  testIntegration: (key: string) => post<Integration>(`/integrations/${key}/test`),

  // Activity -------------------------------------------------------------
  activity: (params?: { project_id?: string; level?: string; limit?: number }) => {
    const query = new URLSearchParams()
    if (params?.project_id) query.set('project_id', params.project_id)
    if (params?.level) query.set('level', params.level)
    if (params?.limit) query.set('limit', String(params.limit))
    const suffix = query.toString() ? `?${query}` : ''
    return request<ActivityEvent[]>(`/activity${suffix}`)
  },
  activitySummary: () => request<{ counts: Record<string, number> }>('/activity/summary'),

  // Approvals ------------------------------------------------------------
  approvals: (status?: string) =>
    request<Approval[]>(`/approvals${status ? `?status=${status}` : ''}`),
  decide: (id: string, approved: boolean, note?: string) =>
    post<Approval>(`/approvals/${id}/decide`, { approved, note }),

  // Artifacts ------------------------------------------------------------
  artifacts: (params?: { project_id?: string; kind?: string }) => {
    const query = new URLSearchParams()
    if (params?.project_id) query.set('project_id', params.project_id)
    if (params?.kind) query.set('kind', params.kind)
    const suffix = query.toString() ? `?${query}` : ''
    return request<Artifact[]>(`/artifacts${suffix}`)
  },
  approveArtifact: (id: string) => post<Artifact>(`/artifacts/${id}/approve`),

  // Hackathons -----------------------------------------------------------
  hackathons: (params?: { project_id?: string; verified_only?: boolean }) => {
    const query = new URLSearchParams()
    if (params?.project_id) query.set('project_id', params.project_id)
    if (params?.verified_only) query.set('verified_only', 'true')
    const suffix = query.toString() ? `?${query}` : ''
    return request<Hackathon[]>(`/hackathons${suffix}`)
  },
  researchHackathons: (prompt: string, projectId?: string) =>
    post<Task>('/hackathons/research', { prompt, project_id: projectId }),
  deleteHackathon: (id: string) =>
    request<void>(`/hackathons/${id}`, { method: 'DELETE' }),

  // Coding sessions ------------------------------------------------------
  sessions: (projectId?: string) =>
    request<CodingSession[]>(`/sessions${projectId ? `?project_id=${projectId}` : ''}`),
  createSession: (payload: {
    engine: string
    task: string
    project_id?: string
    repository?: string
    branch?: string
    title?: string
  }) => post<CodingSession>('/sessions', payload),
  syncSession: (id: string) => post<CodingSession>(`/sessions/${id}/sync`),
  sessionEvents: (id: string) =>
    request<{ session_id: string; count: number; events: unknown[] }>(
      `/sessions/${id}/events`,
    ),

  // Voice ----------------------------------------------------------------
  voiceStatus: () => request<VoiceStatus>('/voice/status'),
  voiceCommand: (transcript: string, projectId?: string, autoExecute = false) =>
    post<VoiceCommandResult>('/voice/command', {
      transcript,
      project_id: projectId,
      auto_execute: autoExecute,
    }),
  speak: async (text: string): Promise<Blob> => {
    const response = await fetch(`${API_BASE}/voice/speak`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    })
    if (!response.ok) {
      let detail = `Speech synthesis failed with status ${response.status}.`
      try {
        const body = await response.json()
        if (typeof body?.detail === 'string') detail = body.detail
      } catch {
        /* keep default */
      }
      throw new ApiError(response.status, detail)
    }
    return response.blob()
  },
}

/** Build the WebSocket URL for the activity stream. */
export function activitySocketUrl(projectId?: string): string {
  const base = API_BASE.startsWith('http')
    ? API_BASE
    : `${window.location.origin}${API_BASE}`
  const url = new URL(`${base}/activity/stream`)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  if (projectId) url.searchParams.set('project_id', projectId)
  return url.toString()
}
