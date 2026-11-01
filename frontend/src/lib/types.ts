/** Types mirroring the backend response models exactly. */

export interface Health {
  status: string
  app: string
  environment: string
  database: string
  websocket_subscribers: number
  version: string
}

export interface OverviewStats {
  projects_total: number
  projects_active: number
  tasks_total: number
  tasks_running: number
  tasks_completed: number
  tasks_failed: number
  tasks_waiting_approval: number
  agents_total: number
  agents_busy: number
  providers_configured: number
  providers_connected: number
  integrations_configured: number
  integrations_connected: number
  pending_approvals: number
  artifacts_total: number
  hackathons_tracked: number
  tokens_used: number
  estimated_cost_usd: number
  recent_errors: number
}

export interface Project {
  id: string
  name: string
  slug: string
  description: string | null
  objective: string | null
  status: string
  repository: string | null
  coding_engine: string | null
  created_at: string
  updated_at: string
  task_count: number
  completed_count: number
}

export interface MemoryEntry {
  id: string
  project_id: string
  category: string
  key: string
  value: string
  source: string | null
  approved: boolean
  created_at: string
  updated_at: string
}

export interface Task {
  id: string
  project_id: string | null
  title: string
  description: string
  task_type: string
  department: string
  agent_key: string | null
  status: string
  priority: number
  provider: string | null
  model: string | null
  result: string | null
  result_data: Record<string, unknown> | null
  error: string | null
  depends_on: string[]
  requires_approval: boolean
  attempts: number
  tokens_used: number
  cost_usd: number
  duration_ms: number | null
  started_at: string | null
  finished_at: string | null
  created_at: string
}

export interface PlanResponse {
  project_id: string | null
  tasks: Task[]
  summary: string | null
}

export interface ExecutionResult {
  executed: number
  completed: number
  failed: number
  skipped: number
  waiting_approval: number
  results: Array<Record<string, unknown>>
}

export interface Agent {
  key: string
  name: string
  department: string
  description: string
  capabilities: string[]
  tools: string[]
  task_types: string[]
  permission_scope: string[]
  status: string
  current_task_id: string | null
  tasks_completed: number
  tasks_failed: number
  last_error: string | null
  last_active_at: string | null
}

export interface Department {
  key: string
  name: string
  description: string
  agent_count: number
  busy_count: number
}

export interface Provider {
  key: string
  name: string
  kind: string
  base_url: string | null
  required_env: string[]
  configured: boolean
  connected: boolean
  status: string
  /** Models the provider reported. Empty until a probe succeeds. */
  models: string[]
  /** Curated suggestions for this provider. Not verified as available. */
  catalogue: string[]
  default_model: string | null
  last_tested_at: string | null
  last_error: string | null
  details: Record<string, unknown>
  docs_url: string | null
}

export interface ProbeResult {
  key: string
  ok: boolean
  status: string
  message: string
  models: string[]
  latency_ms: number
}

export interface RoutePreview {
  provider: string
  model: string
  reason: string
  alternatives: string[]
  score: number
}

export interface Integration {
  key: string
  name: string
  category: string
  description: string
  docs_url: string | null
  required_env: string[]
  configured: boolean
  connected: boolean
  status: string
  last_tested_at: string | null
  last_error: string | null
  details: Record<string, unknown>
}

export interface ActivityEvent {
  id: string
  project_id: string | null
  task_id: string | null
  agent_key: string | null
  type: string
  level: string
  message: string
  data: Record<string, unknown>
  created_at: string
}

export interface Approval {
  id: string
  project_id: string | null
  task_id: string | null
  action_type: string
  title: string
  description: string
  payload: Record<string, unknown>
  status: string
  requested_by: string | null
  decided_by: string | null
  decision_note: string | null
  created_at: string
  decided_at: string | null
}

export interface Artifact {
  id: string
  project_id: string | null
  task_id: string | null
  kind: string
  title: string
  content: string
  data: Record<string, unknown>
  approved: boolean
  created_at: string
}

export interface Hackathon {
  id: string
  project_id: string | null
  name: string
  organizer: string | null
  url: string | null
  source_urls: string[]
  registration_deadline: string | null
  event_start: string | null
  event_end: string | null
  location: string | null
  is_online: boolean | null
  age_restrictions: string | null
  country_restrictions: string | null
  team_requirements: string | null
  tracks: string[]
  prizes: string | null
  submission_requirements: string | null
  judging_criteria: string | null
  eligibility_notes: string | null
  verified: boolean
  verification_notes: string | null
  last_verified_at: string | null
}

export interface CodingSession {
  id: string
  project_id: string | null
  task_id: string | null
  engine: string
  remote_id: string | null
  title: string
  status: string
  repository: string | null
  branch: string | null
  workspace_dir: string | null
  ui_url: string | null
  details: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface VoiceStatus {
  elevenlabs_configured: boolean
  browser_speech_supported: boolean
  text_to_speech: string
  speech_to_text: string
  note: string
}

export interface VoiceCommandResult {
  understood: boolean
  intent: string
  response: string
  plan_created: boolean
  task_ids: string[]
  requires_approval: boolean
}

export interface AppSettings {
  routing_preference: string[]
  max_parallel_tasks: number
  default_engine: string
  database_backend: string
  environment: string
}
