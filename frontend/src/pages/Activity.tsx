/** Activity Center: the persistent event log, plus the approval queue. */

import { useMemo, useState } from 'react'

import PageHeader from '@/components/PageHeader'
import {
  Banner,
  Chip,
  EmptyState,
  Field,
  LevelDot,
  Mono,
  Panel,
  StatCard,
  StatusBadge,
  levelClass,
} from '@/components/ui'
import { api, ApiError } from '@/lib/api'
import { formatDateTime, formatRelative } from '@/lib/format'
import { useActivityStream, useQuery } from '@/lib/hooks'
import type { Approval } from '@/lib/types'

const LEVELS = ['', 'info', 'warning', 'error']

export default function Activity() {
  const { events, connected, error: streamError, clear } = useActivityStream()
  const approvals = useQuery(() => api.approvals(), [], { pollMs: 10000 })
  const summary = useQuery(() => api.activitySummary(), [], { pollMs: 20000 })
  const projects = useQuery(() => api.projects(), [])

  const [level, setLevel] = useState('')
  const [projectId, setProjectId] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState('')

  const filtered = useMemo(
    () =>
      events.filter(
        (event) =>
          (!level || event.level === level) &&
          (!projectId || event.project_id === projectId),
      ),
    [events, level, projectId],
  )

  const pending = (approvals.data ?? []).filter((a) => a.status === 'pending')

  const decide = async (approval: Approval, approved: boolean) => {
    setBusy(approval.id)
    setError(null)
    try {
      await api.decide(approval.id, approved, note.trim() || undefined)
      setNote('')
      approvals.reload()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.detail : 'Could not record the decision.')
    } finally {
      setBusy(null)
    }
  }

  const counts = summary.data?.counts ?? {}
  const totalEvents = Object.values(counts).reduce((sum, value) => sum + value, 0)
  const topTypes = Object.entries(counts)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 6)

  return (
    <div>
      <PageHeader
        title="Activity"
        description="A persistent log of everything the platform did, streamed live over a WebSocket. Approvals gate consequential actions."
        actions={
          <button type="button" className="btn-ghost" onClick={clear}>
            Clear view
          </button>
        }
      />

      <div className="space-y-5 p-6">
        {error && (
          <Banner tone="error" title="Action failed">
            {error}
          </Banner>
        )}
        {streamError && (
          <Banner tone="warn" title="Stream problem">
            {streamError}
          </Banner>
        )}

        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard
            label="Events in view"
            value={filtered.length}
            hint={connected ? 'live stream connected' : 'stream disconnected'}
            tone={connected ? 'good' : 'warn'}
          />
          <StatCard label="Total events" value={totalEvents} />
          <StatCard
            label="Pending approvals"
            value={pending.length}
            tone={pending.length > 0 ? 'warn' : 'default'}
          />
          <StatCard
            label="Errors in view"
            value={events.filter((e) => e.level === 'error').length}
            tone={events.some((e) => e.level === 'error') ? 'bad' : 'default'}
          />
        </div>

        {pending.length > 0 && (
          <Panel
            title="Approval queue"
            subtitle="JARVIS will not act on these until you decide"
            bodyClassName=""
          >
            <ul className="divide-y divide-white/[0.05]">
              {pending.map((approval) => (
                <li key={approval.id} className="px-5 py-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-[13px] font-medium text-slate-100">{approval.title}</p>
                      <p className="mt-1 whitespace-pre-wrap text-[12px] leading-relaxed text-slate-400">
                        {approval.description}
                      </p>
                      <div className="mt-2 flex flex-wrap items-center gap-1.5">
                        <Chip>{approval.action_type}</Chip>
                        {approval.requested_by && <Chip>{approval.requested_by}</Chip>}
                        <span className="text-[11px] text-slate-600">
                          {formatRelative(approval.created_at)}
                        </span>
                      </div>
                    </div>
                    <StatusBadge status={approval.status} />
                  </div>

                  {Object.keys(approval.payload ?? {}).length > 0 && (
                    <pre className="mono mt-3 max-h-40 overflow-auto rounded-md border border-white/[0.06] bg-navy-950/70 p-3 text-slate-400">
                      {JSON.stringify(approval.payload, null, 2)}
                    </pre>
                  )}

                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <input
                      className="input max-w-xs"
                      placeholder="Optional note"
                      value={note}
                      onChange={(event) => setNote(event.target.value)}
                    />
                    <button
                      type="button"
                      className="btn-primary"
                      onClick={() => decide(approval, true)}
                      disabled={busy === approval.id}
                    >
                      Approve
                    </button>
                    <button
                      type="button"
                      className="btn-danger"
                      onClick={() => decide(approval, false)}
                      disabled={busy === approval.id}
                    >
                      Reject
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </Panel>
        )}

        <Panel title="Filters">
          <div className="grid gap-3 sm:grid-cols-3">
            <div>
              <label className="label" htmlFor="act-level">
                Level
              </label>
              <select
                id="act-level"
                className="select"
                value={level}
                onChange={(event) => setLevel(event.target.value)}
              >
                {LEVELS.map((value) => (
                  <option key={value} value={value}>
                    {value || 'All levels'}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="act-project">
                Project
              </label>
              <select
                id="act-project"
                className="select"
                value={projectId}
                onChange={(event) => setProjectId(event.target.value)}
              >
                <option value="">All projects</option>
                {(projects.data ?? []).map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-end">
              <button
                type="button"
                className="btn-secondary"
                onClick={() => {
                  setLevel('')
                  setProjectId('')
                }}
              >
                Reset
              </button>
            </div>
          </div>
        </Panel>

        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
          <Panel
            title="Event log"
            subtitle={`${filtered.length} event${filtered.length === 1 ? '' : 's'}`}
            bodyClassName=""
          >
            {filtered.length === 0 ? (
              <EmptyState
                title="No events"
                description={
                  events.length === 0
                    ? 'Nothing has happened yet. Events are recorded only for real actions.'
                    : 'No events match the current filters.'
                }
              />
            ) : (
              <ul className="max-h-[600px] divide-y divide-white/[0.05] scroll-area">
                {filtered.map((event) => (
                  <li key={event.id} className="flex items-start gap-3 px-5 py-3">
                    <LevelDot level={event.level} />
                    <div className="min-w-0 flex-1">
                      <p className={`text-[13px] ${levelClass(event.level)}`}>{event.message}</p>
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-slate-600">
                        <span className="mono">{event.type}</span>
                        {event.agent_key && <span>· {event.agent_key}</span>}
                        <span title={formatDateTime(event.created_at)}>
                          · {formatRelative(event.created_at)}
                        </span>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel title="Event types" subtitle="All-time counts">
            {topTypes.length === 0 ? (
              <p className="text-[12px] text-slate-500">No events recorded yet.</p>
            ) : (
              <ul className="space-y-2">
                {topTypes.map(([type, count]) => (
                  <li key={type} className="flex items-center justify-between gap-2">
                    <span className="mono truncate text-slate-400">{type}</span>
                    <span className="tabular-nums text-[12px] text-slate-300">{count}</span>
                  </li>
                ))}
              </ul>
            )}
            <div className="divider" />
            <Field
              label="Stream status"
              value={<Mono>{connected ? 'connected' : 'disconnected'}</Mono>}
            />
          </Panel>
        </div>
      </div>
    </div>
  )
}
