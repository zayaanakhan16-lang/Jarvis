/**
 * Engineering Workspace.
 *
 * Coding engines run in isolated sessions. JARVIS creates the session and
 * records its identifier, but never presents a session as producing working
 * code unless the engine reported real file activity.
 */

import { useState } from 'react'

import { IconExternal, IconRefresh, IconTerminal } from '@/components/icons'
import PageHeader from '@/components/PageHeader'
import {
  Banner,
  Chip,
  EmptyState,
  ErrorState,
  Field,
  LoadingState,
  Mono,
  Panel,
  StatCard,
  StatusBadge,
} from '@/components/ui'
import { ApiError, api } from '@/lib/api'
import { formatDateTime, formatRelative } from '@/lib/format'
import { useQuery } from '@/lib/hooks'
import type { CodingSession } from '@/lib/types'

const ENGINES = [
  {
    key: 'openhands',
    label: 'OpenHands',
    description:
      'Autonomous coding agent. Runs in its own sandbox with a terminal and file editing tools.',
  },
  {
    key: 'opencode',
    label: 'OpenCode',
    description:
      'Local coding server. Requires an OpenCode server to be running and reachable.',
  },
]

export default function Engineering() {
  const sessions = useQuery(() => api.sessions(), [], { pollMs: 10000 })
  const projects = useQuery(() => api.projects(), [])
  const integrations = useQuery(() => api.integrations(), [], { pollMs: 30000 })

  const [engine, setEngine] = useState('openhands')
  const [task, setTask] = useState('')
  const [repository, setRepository] = useState('')
  const [branch, setBranch] = useState('')
  const [projectId, setProjectId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [eventsFor, setEventsFor] = useState<string | null>(null)
  const [events, setEvents] = useState<unknown[]>([])

  const engineStatus = (key: string) =>
    (integrations.data ?? []).find((i) => i.key === key) ?? null

  const create = async () => {
    if (!task.trim()) return
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const session = await api.createSession({
        engine,
        task: task.trim(),
        repository: repository.trim() || undefined,
        branch: branch.trim() || undefined,
        project_id: projectId || undefined,
      })
      setNotice(
        `Session created on ${session.engine}${
          session.remote_id ? ` (remote id ${session.remote_id})` : ''
        }.`,
      )
      setTask('')
      sessions.reload()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.detail : 'Could not create the session.')
    } finally {
      setBusy(false)
    }
  }

  const sync = async (session: CodingSession) => {
    setError(null)
    try {
      await api.syncSession(session.id)
      sessions.reload()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.detail : 'Could not sync the session.')
    }
  }

  const loadEvents = async (session: CodingSession) => {
    setEventsFor(session.id)
    setError(null)
    try {
      const result = await api.sessionEvents(session.id)
      setEvents(result.events)
    } catch (cause) {
      setEvents([])
      setError(cause instanceof ApiError ? cause.detail : 'Could not load session events.')
    }
  }

  const list = sessions.data ?? []
  const running = list.filter((s) => s.status === 'running' || s.status === 'starting').length

  return (
    <div>
      <PageHeader
        title="Engineering"
        description="Run coding engines in isolated sessions. JARVIS tracks each session's real status; it does not claim code was written unless the engine reported it."
        actions={
          <button type="button" className="btn-secondary" onClick={sessions.reload}>
            <IconRefresh className="h-4 w-4" />
            Refresh
          </button>
        }
      />

      <div className="space-y-5 p-6">
        {error && (
          <Banner tone="error" title="Engineering action failed">
            {error}
          </Banner>
        )}
        {notice && !error && <Banner tone="success">{notice}</Banner>}

        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard label="Sessions" value={list.length} />
          <StatCard
            label="Running"
            value={running}
            tone={running > 0 ? 'good' : 'default'}
          />
          <StatCard
            label="Failed"
            value={list.filter((s) => s.status === 'failed').length}
            tone={list.some((s) => s.status === 'failed') ? 'bad' : 'default'}
          />
          <StatCard
            label="Engines ready"
            value={ENGINES.filter((e) => engineStatus(e.key)?.connected).length}
            hint={`of ${ENGINES.length}`}
          />
        </div>

        <Panel title="Coding engines" subtitle="Connection state is measured with a real probe">
          <div className="grid gap-3 md:grid-cols-2">
            {ENGINES.map((item) => {
              const status = engineStatus(item.key)
              return (
                <div
                  key={item.key}
                  className="rounded-lg border border-white/[0.07] bg-navy-900/40 p-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-[13px] font-medium text-slate-100">{item.label}</p>
                      <p className="mt-1 text-[11.5px] leading-relaxed text-slate-500">
                        {item.description}
                      </p>
                    </div>
                    <StatusBadge status={status?.status ?? 'unavailable'} />
                  </div>
                  {status && (
                    <p className="mt-2.5 text-[11.5px] leading-relaxed text-slate-400">
                      {String(status.details?.message ?? '')}
                    </p>
                  )}
                  {status?.docs_url && (
                    <a
                      href={status.docs_url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-2.5 inline-flex items-center gap-1 text-[11px] text-accent hover:text-accent-bright"
                    >
                      Documentation <IconExternal className="h-3 w-3" />
                    </a>
                  )}
                </div>
              )
            })}
          </div>
        </Panel>

        <Panel title="New session" subtitle="Submits a coding task to the selected engine">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="label" htmlFor="eng-engine">
                Coding engine
              </label>
              <select
                id="eng-engine"
                className="select"
                value={engine}
                onChange={(event) => setEngine(event.target.value)}
                disabled={busy}
              >
                {ENGINES.map((item) => (
                  <option key={item.key} value={item.key}>
                    {item.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="eng-project">
                Project
              </label>
              <select
                id="eng-project"
                className="select"
                value={projectId}
                onChange={(event) => setProjectId(event.target.value)}
                disabled={busy}
              >
                <option value="">No project</option>
                {(projects.data ?? []).map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="eng-repo">
                Repository (optional)
              </label>
              <input
                id="eng-repo"
                className="input"
                placeholder="owner/repo"
                value={repository}
                onChange={(event) => setRepository(event.target.value)}
                disabled={busy}
              />
            </div>
            <div>
              <label className="label" htmlFor="eng-branch">
                Branch (optional)
              </label>
              <input
                id="eng-branch"
                className="input"
                placeholder="feature/my-branch"
                value={branch}
                onChange={(event) => setBranch(event.target.value)}
                disabled={busy}
              />
            </div>
          </div>

          <div className="mt-3">
            <label className="label" htmlFor="eng-task">
              Task
            </label>
            <textarea
              id="eng-task"
              className="input min-h-[100px] resize-y leading-relaxed"
              placeholder="Describe the coding work, including the acceptance criteria and how it should be tested."
              value={task}
              onChange={(event) => setTask(event.target.value)}
              disabled={busy}
            />
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2.5">
            <button
              type="button"
              className="btn-primary"
              onClick={create}
              disabled={busy || !task.trim()}
            >
              <IconTerminal className="h-4 w-4" />
              {busy ? 'Creating…' : 'Create session'}
            </button>
            <p className="text-[11px] text-slate-500">
              Sessions are isolated. JARVIS will not push branches or open pull requests without
              your approval.
            </p>
          </div>
        </Panel>

        {sessions.error && <ErrorState message={sessions.error} onRetry={sessions.reload} />}
        {sessions.loading && !sessions.data && <LoadingState label="Loading sessions" />}

        {sessions.data && list.length === 0 && (
          <Panel>
            <EmptyState
              title="No coding sessions"
              description="Create a session above. The engine must be reachable; if it is not, the request fails with the real reason rather than pretending to work."
            />
          </Panel>
        )}

        {list.length > 0 && (
          <Panel title="Sessions" bodyClassName="" subtitle={`${list.length} total`}>
            <ul className="divide-y divide-white/[0.05]">
              {list.map((session) => (
                <li key={session.id} className="px-5 py-3.5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-[13px] font-medium text-slate-200">{session.title}</p>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5">
                        <Chip>{session.engine}</Chip>
                        {session.remote_id && <Chip>{session.remote_id}</Chip>}
                        {session.repository && <Chip>{session.repository}</Chip>}
                        {session.branch && <Chip>{session.branch}</Chip>}
                        <span className="text-[11px] text-slate-600">
                          {formatRelative(session.created_at)}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <StatusBadge status={session.status} />
                      <button
                        type="button"
                        className="btn-secondary text-xs"
                        onClick={() => sync(session)}
                      >
                        Sync
                      </button>
                      <button
                        type="button"
                        className="btn-ghost text-xs"
                        onClick={() => loadEvents(session)}
                      >
                        Events
                      </button>
                    </div>
                  </div>

                  <dl className="mt-3 grid gap-2.5 sm:grid-cols-3">
                    <Field label="Workspace" value={<Mono>{session.workspace_dir ?? 'not set'}</Mono>} />
                    <Field label="Created" value={formatDateTime(session.created_at)} />
                    <Field label="Updated" value={formatDateTime(session.updated_at)} />
                  </dl>

                  {session.ui_url && (
                    <a
                      href={session.ui_url}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-2.5 inline-flex items-center gap-1 text-[11px] text-accent hover:text-accent-bright"
                    >
                      Open session UI <IconExternal className="h-3 w-3" />
                    </a>
                  )}

                  {eventsFor === session.id && (
                    <div className="mt-3">
                      <p className="label">Session events</p>
                      {events.length === 0 ? (
                        <p className="text-[12px] text-slate-500">
                          No events reported by the engine yet.
                        </p>
                      ) : (
                        <pre className="mono max-h-64 overflow-auto rounded-md border border-white/[0.06] bg-navy-950/70 p-3 text-slate-400">
                          {JSON.stringify(events, null, 2)}
                        </pre>
                      )}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </Panel>
        )}
      </div>
    </div>
  )
}
