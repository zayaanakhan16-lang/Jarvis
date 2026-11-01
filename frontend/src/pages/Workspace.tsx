/**
 * AI Workspace: the primary interface.
 *
 * The flow is deliberately two-step. A plan is produced and reviewed first;
 * execution only starts when the user asks for it. Nothing here claims a task
 * succeeded unless the backend reported it.
 */

import { useEffect, useMemo, useState } from 'react'

import { IconMic, IconPlay, IconRefresh } from '@/components/icons'
import PageHeader from '@/components/PageHeader'
import {
  Banner,
  Chip,
  EmptyState,
  Field,
  LevelDot,
  LoadingState,
  Mono,
  Panel,
  StatusBadge,
  levelClass,
} from '@/components/ui'
import { ApiError, api } from '@/lib/api'
import { formatDuration, formatNumber, formatRelative } from '@/lib/format'
import { useActivityStream, useQuery } from '@/lib/hooks'
import type { ExecutionResult, PlanResponse, Task } from '@/lib/types'

const TASK_TYPES = [
  'planning',
  'research',
  'analysis',
  'architecture',
  'coding',
  'ui_design',
  'branding',
  'testing',
  'debugging',
  'code_review',
  'security',
  'documentation',
  'presentation',
  'deployment',
]

export default function Workspace() {
  const projects = useQuery(() => api.projects(), [])
  const providers = useQuery(() => api.providers(), [])
  const agents = useQuery(() => api.agents(), [])
  const voice = useQuery(() => api.voiceStatus(), [])
  const { events, connected } = useActivityStream()

  const [projectId, setProjectId] = useState('')
  const [newProjectName, setNewProjectName] = useState('')
  const [objective, setObjective] = useState('')
  const [maxTasks, setMaxTasks] = useState(6)
  const [providerKey, setProviderKey] = useState('')
  const [agentKey, setAgentKey] = useState('')
  const [taskType, setTaskType] = useState('analysis')

  const [plan, setPlan] = useState<PlanResponse | null>(null)
  const [execution, setExecution] = useState<ExecutionResult | null>(null)
  const [busy, setBusy] = useState<null | 'plan' | 'execute' | 'run' | 'project'>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [listening, setListening] = useState(false)

  const connectedProviders = useMemo(
    () => (providers.data ?? []).filter((p) => p.connected),
    [providers.data],
  )
  const selectedProject = useMemo(
    () => (projects.data ?? []).find((p) => p.id === projectId) ?? null,
    [projects.data, projectId],
  )

  useEffect(() => {
    if (!projectId && (projects.data ?? []).length > 0) {
      setProjectId(projects.data![0].id)
    }
  }, [projects.data, projectId])

  const handleError = (cause: unknown) => {
    setError(
      cause instanceof ApiError
        ? cause.detail
        : cause instanceof Error
          ? cause.message
          : 'Unknown error',
    )
  }

  const createProject = async () => {
    if (!newProjectName.trim()) return
    setBusy('project')
    setError(null)
    try {
      const project = await api.createProject({
        name: newProjectName.trim(),
        objective: objective.trim() || undefined,
      })
      setProjectId(project.id)
      setNewProjectName('')
      setNotice(`Project "${project.name}" created.`)
      projects.reload()
    } catch (cause) {
      handleError(cause)
    } finally {
      setBusy(null)
    }
  }

  const requestPlan = async () => {
    if (!objective.trim()) return
    setBusy('plan')
    setError(null)
    setNotice(null)
    setExecution(null)
    try {
      const result = await api.plan({
        objective: objective.trim(),
        project_id: projectId || undefined,
        max_tasks: maxTasks,
        provider: providerKey || undefined,
      })
      setPlan(result)
      setNotice(
        `Plan ready with ${result.tasks.length} task${
          result.tasks.length === 1 ? '' : 's'
        }. Review it, then execute.`,
      )
      projects.reload()
    } catch (cause) {
      setPlan(null)
      handleError(cause)
    } finally {
      setBusy(null)
    }
  }

  const executePlan = async () => {
    if (!plan) return
    setBusy('execute')
    setError(null)
    try {
      const result = await api.execute({ task_ids: plan.tasks.map((t) => t.id) })
      setExecution(result)
      const parts = [
        `Executed ${result.executed} task(s)`,
        `${result.completed} completed`,
        `${result.failed} failed`,
      ]
      if (result.skipped) parts.push(`${result.skipped} skipped`)
      if (result.waiting_approval) parts.push(`${result.waiting_approval} awaiting approval`)
      setNotice(`${parts.join(', ')}.`)

      // Re-read each task so the plan shows the status the backend actually
      // recorded, rather than the stale pre-execution snapshot.
      const refreshed = await Promise.all(
        plan.tasks.map((task) => api.task(task.id).catch(() => task)),
      )
      setPlan({ project_id: plan.project_id, summary: plan.summary, tasks: refreshed })
      projects.reload()
    } catch (cause) {
      handleError(cause)
    } finally {
      setBusy(null)
    }
  }

  const runDirect = async () => {
    if (!objective.trim()) return
    setBusy('run')
    setError(null)
    setNotice(null)
    setExecution(null)
    try {
      const task = await api.run({
        prompt: objective.trim(),
        task_type: taskType,
        agent_key: agentKey || undefined,
        project_id: projectId || undefined,
        provider: providerKey || undefined,
      })
      setNotice(
        task.status === 'completed'
          ? `Task completed by ${task.agent_key} using ${task.provider}/${task.model}.`
          : `Task finished with status "${task.status}".`,
      )
      setPlan({ project_id: task.project_id, summary: null, tasks: [task] })
      projects.reload()
    } catch (cause) {
      handleError(cause)
    } finally {
      setBusy(null)
    }
  }

  const startListening = () => {
    const win = window as unknown as {
      SpeechRecognition?: new () => SpeechRecognitionLike
      webkitSpeechRecognition?: new () => SpeechRecognitionLike
    }
    const Recognition = win.SpeechRecognition ?? win.webkitSpeechRecognition

    if (!Recognition) {
      setError(
        'This browser does not expose the Web Speech API, so voice input is unavailable here. Type the objective instead.',
      )
      return
    }

    const recognition = new Recognition()
    recognition.lang = 'en-US'
    recognition.interimResults = false
    recognition.onresult = (event) => {
      const transcript = event.results?.[0]?.[0]?.transcript ?? ''
      if (transcript) setObjective(transcript)
    }
    recognition.onerror = (event) => setError(`Speech recognition error: ${event.error}`)
    recognition.onend = () => setListening(false)
    recognition.start()
    setListening(true)
  }

  const executeDisabled =
    !plan || busy !== null || plan.tasks.every((task) => task.status === 'completed')

  return (
    <div>
      <PageHeader
        title="AI Workspace"
        description="Give JARVIS an objective. It will research, plan, assign specialist agents, execute and report back. Review the plan before anything runs."
        actions={
          <span className="flex items-center gap-2 text-[11px] text-slate-500">
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                connected ? 'animate-pulse-soft bg-accent' : 'bg-slate-600'
              }`}
            />
            {connected ? 'live' : 'offline'}
          </span>
        }
      />

      <div className="grid gap-5 p-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-5">
          {error && (
            <Banner tone="error" title="Request failed">
              {error}
            </Banner>
          )}
          {notice && !error && <Banner tone="success">{notice}</Banner>}

          <Panel
            title="Objective"
            subtitle="Describe the outcome you want, not the steps"
            actions={
              <button
                type="button"
                className={listening ? 'btn-primary' : 'btn-secondary'}
                onClick={startListening}
                disabled={listening || busy !== null}
                title={
                  voice.data?.browser_speech_supported
                    ? 'Dictate the objective'
                    : 'Voice input is unavailable in this browser'
                }
              >
                <IconMic className="h-3.5 w-3.5" />
                {listening ? 'Listening…' : 'Dictate'}
              </button>
            }
          >
            <textarea
              className="input min-h-[130px] resize-y leading-relaxed"
              placeholder="Example: Research current online hackathons I am eligible for, analyse their judging criteria, propose three differentiated product ideas, and recommend one with a realistic scope."
              value={objective}
              onChange={(event) => setObjective(event.target.value)}
              disabled={busy !== null}
            />

            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <label className="label" htmlFor="ws-provider">
                  Model provider
                </label>
                <select
                  id="ws-provider"
                  className="select"
                  value={providerKey}
                  onChange={(event) => setProviderKey(event.target.value)}
                  disabled={busy !== null}
                >
                  <option value="">Automatic routing</option>
                  {connectedProviders.map((provider) => (
                    <option key={provider.key} value={provider.key}>
                      {provider.name}
                    </option>
                  ))}
                </select>
                {connectedProviders.length === 0 && (
                  <p className="mt-1 text-[11px] text-amber-300/80">
                    No provider has passed a connection test yet.
                  </p>
                )}
              </div>

              <div>
                <label className="label" htmlFor="ws-tasks">
                  Max tasks
                </label>
                <input
                  id="ws-tasks"
                  type="number"
                  min={1}
                  max={20}
                  className="input"
                  value={maxTasks}
                  onChange={(event) => setMaxTasks(Number(event.target.value))}
                  disabled={busy !== null}
                />
              </div>

              <div>
                <label className="label" htmlFor="ws-agent">
                  Direct task agent
                </label>
                <select
                  id="ws-agent"
                  className="select"
                  value={agentKey}
                  onChange={(event) => setAgentKey(event.target.value)}
                  disabled={busy !== null}
                >
                  <option value="">Auto-select by task type</option>
                  {(agents.data ?? []).map((agent) => (
                    <option key={agent.key} value={agent.key}>
                      {agent.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="label" htmlFor="ws-type">
                  Task type
                </label>
                <select
                  id="ws-type"
                  className="select"
                  value={taskType}
                  onChange={(event) => setTaskType(event.target.value)}
                  disabled={busy !== null}
                >
                  {TASK_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {type.replace(/_/g, ' ')}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-2.5">
              <button
                type="button"
                className="btn-primary"
                onClick={requestPlan}
                disabled={!objective.trim() || busy !== null}
              >
                {busy === 'plan' ? (
                  <IconRefresh className="h-4 w-4 animate-spin" />
                ) : (
                  <IconPlay className="h-4 w-4" />
                )}
                {busy === 'plan' ? 'Planning…' : 'Create plan'}
              </button>
              <button
                type="button"
                className="btn-secondary"
                onClick={executePlan}
                disabled={executeDisabled}
              >
                {busy === 'execute' ? 'Executing…' : 'Execute plan'}
              </button>
              <button
                type="button"
                className="btn-ghost"
                onClick={runDirect}
                disabled={!objective.trim() || busy !== null}
              >
                Run as single task
              </button>
              <button
                type="button"
                className="btn-ghost"
                onClick={() => {
                  setPlan(null)
                  setExecution(null)
                  setNotice(null)
                  setError(null)
                }}
                disabled={busy !== null}
              >
                Clear
              </button>
            </div>
            <p className="mt-2.5 text-[11px] leading-relaxed text-slate-500">
              "Create plan" asks a model to decompose the objective and assigns each task to a
              real agent. "Execute plan" runs them in dependency order. Nothing is pushed to
              GitHub, deployed or published without your explicit approval.
            </p>
          </Panel>

          {plan && (
            <Panel
              title="Execution plan"
              subtitle={
                plan.summary ??
                'Dependency-ordered tasks. Every assignment is validated against the real agent roster.'
              }
              bodyClassName=""
              actions={
                <span className="text-[11px] text-slate-500">
                  {plan.tasks.length} task{plan.tasks.length === 1 ? '' : 's'}
                </span>
              }
            >
              <ul className="divide-y divide-white/[0.05]">
                {plan.tasks.map((task) => (
                  <TaskRow key={task.id} task={task} />
                ))}
              </ul>
            </Panel>
          )}

          {execution && (
            <Panel title="Execution result" subtitle="Reported by the orchestrator">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Field label="Executed" value={execution.executed} />
                <Field label="Completed" value={execution.completed} />
                <Field label="Failed" value={execution.failed} />
                <Field label="Skipped" value={execution.skipped} />
              </div>
              {execution.waiting_approval > 0 && (
                <p className="mt-3 text-[12px] text-amber-200">
                  {execution.waiting_approval} task(s) are waiting for your approval. Decide on
                  the Activity page.
                </p>
              )}
            </Panel>
          )}

          <Panel
            title="Live activity"
            subtitle="Only real events recorded by the backend"
            bodyClassName=""
          >
            {events.length === 0 ? (
              <EmptyState
                title="Nothing has happened yet"
                description="Activity appears when a plan is created or a task runs. There is no simulated feed."
              />
            ) : (
              <ul className="max-h-[360px] divide-y divide-white/[0.05] scroll-area">
                {events.slice(0, 40).map((event) => (
                  <li key={event.id} className="flex items-start gap-3 px-5 py-2.5">
                    <LevelDot level={event.level} />
                    <div className="min-w-0 flex-1">
                      <p className={`text-[13px] ${levelClass(event.level)}`}>{event.message}</p>
                      <p className="mt-0.5 text-[11px] text-slate-600">
                        <span className="mono">{event.type}</span> ·{' '}
                        {formatRelative(event.created_at)}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>

        <div className="space-y-5">
          <Panel title="Project" subtitle="Plans and memory are scoped to a project">
            {projects.loading && !projects.data ? (
              <LoadingState />
            ) : (
              <>
                <label className="label" htmlFor="ws-project">
                  Active project
                </label>
                <select
                  id="ws-project"
                  className="select"
                  value={projectId}
                  onChange={(event) => setProjectId(event.target.value)}
                  disabled={busy !== null}
                >
                  <option value="">No project (unscoped)</option>
                  {(projects.data ?? []).map((project) => (
                    <option key={project.id} value={project.id}>
                      {project.name}
                    </option>
                  ))}
                </select>

                {selectedProject && (
                  <dl className="mt-3.5 space-y-2">
                    <Field
                      label="Progress"
                      value={`${selectedProject.completed_count} of ${selectedProject.task_count} tasks`}
                    />
                    <Field label="Status" value={<StatusBadge status={selectedProject.status} />} />
                    <Field label="Repository" value={selectedProject.repository ?? 'not linked'} />
                  </dl>
                )}

                <div className="divider" />

                <label className="label" htmlFor="ws-new-project">
                  Create a project
                </label>
                <div className="flex gap-2">
                  <input
                    id="ws-new-project"
                    className="input"
                    placeholder="Project name"
                    value={newProjectName}
                    onChange={(event) => setNewProjectName(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') void createProject()
                    }}
                    disabled={busy !== null}
                  />
                  <button
                    type="button"
                    className="btn-secondary shrink-0"
                    onClick={createProject}
                    disabled={!newProjectName.trim() || busy !== null}
                  >
                    Create
                  </button>
                </div>
              </>
            )}
          </Panel>

          <Panel title="Voice" subtitle="Real speech services only">
            {voice.data ? (
              <div className="space-y-2.5">
                <Field label="Text to speech" value={voice.data.text_to_speech} />
                <Field label="Speech to text" value={voice.data.speech_to_text} />
                <p className="text-[11px] leading-relaxed text-slate-500">{voice.data.note}</p>
              </div>
            ) : (
              <LoadingState />
            )}
          </Panel>

          <Panel title="Routing preview" subtitle="Which model would handle this task type">
            <RoutePreview taskType={taskType} />
          </Panel>
        </div>
      </div>
    </div>
  )
}

interface SpeechRecognitionLike {
  lang: string
  interimResults: boolean
  onresult: (event: { results: Array<Array<{ transcript: string }>> }) => void
  onerror: (event: { error: string }) => void
  onend: () => void
  start: () => void
}

function TaskRow({ task }: { task: Task }) {
  const [open, setOpen] = useState(false)
  const parsed = task.result_data?.parsed as Record<string, unknown> | undefined

  return (
    <li className="px-5 py-3.5">
      <button
        type="button"
        className="flex w-full items-start justify-between gap-4 text-left"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        <div className="min-w-0 flex-1">
          <p className="text-[13px] font-medium text-slate-200">{task.title}</p>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <Chip>{task.task_type}</Chip>
            {task.agent_key && <Chip>{task.agent_key}</Chip>}
            {task.depends_on.length > 0 && <Chip>depends on {task.depends_on.length}</Chip>}
            {task.requires_approval && <Chip>needs approval</Chip>}
            {task.provider && (
              <Chip>
                {task.provider}/{task.model}
              </Chip>
            )}
          </div>
        </div>
        <StatusBadge status={task.status} />
      </button>

      {open && (
        <div className="mt-3 space-y-3 rounded-lg border border-white/[0.06] bg-navy-900/40 p-3.5">
          <p className="whitespace-pre-wrap text-[12.5px] leading-relaxed text-slate-400">
            {task.description || 'No description recorded.'}
          </p>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Field label="Duration" value={formatDuration(task.duration_ms)} />
            <Field label="Tokens" value={formatNumber(task.tokens_used)} />
            <Field label="Attempts" value={task.attempts} />
            <Field label="Priority" value={task.priority} />
          </div>

          {task.error && (
            <div className="rounded-md border border-red-500/25 bg-red-500/[0.06] px-3 py-2">
              <p className="text-[11px] font-medium uppercase tracking-wide text-red-300">
                Error
              </p>
              <p className="mt-0.5 text-[12.5px] text-red-200">{task.error}</p>
            </div>
          )}

          {task.result && (
            <div>
              <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-slate-500">
                Result
              </p>
              <pre className="mono max-h-72 overflow-auto whitespace-pre-wrap rounded-md border border-white/[0.06] bg-navy-950/70 p-3 text-slate-300">
                {task.result}
              </pre>
            </div>
          )}

          {parsed && (
            <div>
              <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-slate-500">
                Parsed output
              </p>
              <pre className="mono max-h-60 overflow-auto rounded-md border border-white/[0.06] bg-navy-950/70 p-3 text-slate-400">
                {JSON.stringify(parsed, null, 2)}
              </pre>
            </div>
          )}

          <p className="text-[11px] text-slate-600">
            Task id <Mono>{task.id}</Mono>
          </p>
        </div>
      )}
    </li>
  )
}

function RoutePreview({ taskType }: { taskType: string }) {
  const [result, setResult] = useState<{ provider: string; model: string; reason: string } | null>(
    null,
  )
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const check = async () => {
    setLoading(true)
    setError(null)
    try {
      const preview = await api.routePreview(taskType)
      setResult(preview)
    } catch (cause) {
      setResult(null)
      setError(cause instanceof ApiError ? cause.detail : 'Routing check failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Chip>{taskType}</Chip>
        <button type="button" className="btn-ghost text-xs" onClick={check} disabled={loading}>
          {loading ? 'Checking…' : 'Check routing'}
        </button>
      </div>
      {error && <p className="text-[12px] text-amber-200">{error}</p>}
      {result && (
        <div className="space-y-1.5">
          <p className="text-[13px] text-slate-200">
            <Mono>
              {result.provider}/{result.model}
            </Mono>
          </p>
          <p className="text-[11px] text-slate-500">{result.reason}</p>
        </div>
      )}
    </div>
  )
}
