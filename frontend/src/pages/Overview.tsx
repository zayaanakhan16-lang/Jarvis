/** Overview dashboard. Every figure comes from the backend or is not shown. */

import { Link } from 'react-router-dom'

import PageHeader from '@/components/PageHeader'
import {
  Banner,
  EmptyState,
  ErrorState,
  LoadingState,
  Panel,
  ProgressBar,
  StatCard,
  StatusBadge,
  levelClass,
  LevelDot,
} from '@/components/ui'
import { api } from '@/lib/api'
import { formatCost, formatNumber, formatRelative } from '@/lib/format'
import { useActivityStream, useQuery } from '@/lib/hooks'

export default function Overview() {
  const overview = useQuery(() => api.overview(), [], { pollMs: 15000 })
  const projects = useQuery(() => api.projects(), [], { pollMs: 20000 })
  const approvals = useQuery(() => api.approvals('pending'), [], { pollMs: 15000 })
  const providers = useQuery(() => api.providers(), [], { pollMs: 30000 })
  const integrations = useQuery(() => api.integrations(), [], { pollMs: 30000 })
  const { events, connected } = useActivityStream()

  const stats = overview.data
  const recent = events.slice(0, 12)

  const providersReady = (providers.data ?? []).filter((p) => p.connected).length
  const providersConfigured = (providers.data ?? []).filter((p) => p.configured).length
  const noProviderConnected = providersConfigured > 0 && providersReady === 0
  const nothingConfigured = providersConfigured === 0

  return (
    <div className="space-y-0">
      <PageHeader
        title="Overview"
        description="Live state of the platform. Counts, providers and activity are read from the backend; nothing here is estimated."
        actions={
          <Link to="/workspace" className="btn-primary">
            Open AI Workspace
          </Link>
        }
      />

      <div className="space-y-5 p-6">
        {overview.error && (
          <ErrorState message={overview.error} onRetry={overview.reload} />
        )}

        {overview.loading && !stats && <LoadingState label="Reading system state" />}

        {stats && (
          <>
            {(nothingConfigured || noProviderConnected) && (
              <Banner
                tone="warn"
                title="No model provider is connected"
                action={
                  <Link to="/integrations" className="btn-secondary shrink-0">
                    Configure
                  </Link>
                }
              >
                {nothingConfigured
                  ? 'No model provider credentials are configured, so agents cannot execute tasks yet. Add a provider key or start a local Ollama daemon.'
                  : 'Providers are configured but none has passed a connection test. Run a connection test on the Integrations page before executing tasks.'}
              </Banner>
            )}

            {stats.recent_errors > 0 && (
              <Banner tone="error" title={`${stats.recent_errors} error(s) in the last 24 hours`}>
                Open the Activity page and filter by level "error" to see what failed.
              </Banner>
            )}

            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <StatCard
                label="Projects"
                value={formatNumber(stats.projects_total)}
                hint={`${stats.projects_active} active`}
              />
              <StatCard
                label="Tasks"
                value={formatNumber(stats.tasks_total)}
                hint={`${stats.tasks_completed} completed · ${stats.tasks_failed} failed`}
                tone={stats.tasks_failed > 0 ? 'warn' : 'default'}
              />
              <StatCard
                label="Agents busy"
                value={`${stats.agents_busy}/${stats.agents_total}`}
                hint="executing right now"
                tone={stats.agents_busy > 0 ? 'good' : 'default'}
              />
              <StatCard
                label="Pending approvals"
                value={formatNumber(stats.pending_approvals)}
                hint="waiting on you"
                tone={stats.pending_approvals > 0 ? 'warn' : 'default'}
              />
              <StatCard
                label="Providers connected"
                value={`${stats.providers_connected}/${stats.providers_configured}`}
                hint="tested successfully"
                tone={
                  stats.providers_connected > 0
                    ? 'good'
                    : stats.providers_configured > 0
                      ? 'warn'
                      : 'default'
                }
              />
              <StatCard
                label="Integrations connected"
                value={`${stats.integrations_connected}/${stats.integrations_configured}`}
                hint="external services"
              />
              <StatCard
                label="Artifacts"
                value={formatNumber(stats.artifacts_total)}
                hint="produced by tasks"
              />
              <StatCard
                label="Tokens used"
                value={formatNumber(stats.tokens_used)}
                hint={`cost ${formatCost(stats.estimated_cost_usd)}`}
              />
            </div>

            <div className="grid gap-5 lg:grid-cols-3">
              <Panel
                title="Projects"
                subtitle="Most recently updated"
                className="lg:col-span-2"
                bodyClassName=""
                actions={
                  <Link to="/projects" className="btn-ghost text-xs">
                    View all
                  </Link>
                }
              >
                {projects.loading && !projects.data ? (
                  <LoadingState />
                ) : projects.error ? (
                  <ErrorState message={projects.error} onRetry={projects.reload} />
                ) : (projects.data ?? []).length === 0 ? (
                  <EmptyState
                    title="No projects yet"
                    description="A project holds an objective, its tasks, memory and artifacts. Create one to give the agents something to work on."
                    action={
                      <Link to="/workspace" className="btn-primary">
                        Create a project
                      </Link>
                    }
                  />
                ) : (
                  <ul className="divide-y divide-white/[0.05]">
                    {projects.data!.slice(0, 5).map((project) => (
                      <li key={project.id} className="px-5 py-3.5">
                        <div className="flex items-center justify-between gap-4">
                          <Link
                            to={`/projects/${project.id}`}
                            className="min-w-0 flex-1 hover:text-accent-bright"
                          >
                            <p className="truncate text-[13px] font-medium text-slate-200">
                              {project.name}
                            </p>
                            <p className="mt-0.5 truncate text-[11px] text-slate-500">
                              {project.objective ?? project.description ?? 'No objective recorded'}
                            </p>
                          </Link>
                          <StatusBadge status={project.status} />
                        </div>
                        <div className="mt-2.5">
                          <ProgressBar
                            completed={project.completed_count}
                            total={project.task_count}
                          />
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>

              <Panel
                title="Pending approvals"
                subtitle="Actions waiting for your decision"
                bodyClassName=""
                actions={
                  <Link to="/activity" className="btn-ghost text-xs">
                    Activity
                  </Link>
                }
              >
                {approvals.loading && !approvals.data ? (
                  <LoadingState />
                ) : approvals.error ? (
                  <ErrorState message={approvals.error} onRetry={approvals.reload} />
                ) : (approvals.data ?? []).length === 0 ? (
                  <EmptyState
                    title="Nothing waiting"
                    description="JARVIS asks for approval before touching external systems, deploying or spending money. Requests appear here."
                  />
                ) : (
                  <ul className="divide-y divide-white/[0.05]">
                    {approvals.data!.slice(0, 5).map((approval) => (
                      <li key={approval.id} className="px-5 py-3.5">
                        <p className="text-[13px] font-medium text-slate-200">
                          {approval.title}
                        </p>
                        <p className="mt-1 text-[11px] text-slate-500">
                          {approval.action_type.replace(/_/g, ' ')} ·{' '}
                          {formatRelative(approval.created_at)}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
            </div>

            <Panel
              title="Recent activity"
              subtitle={
                connected
                  ? 'Streaming live from the backend event log'
                  : 'Stream disconnected - showing last fetched events'
              }
              bodyClassName=""
              actions={
                <Link to="/activity" className="btn-ghost text-xs">
                  Full log
                </Link>
              }
            >
              {recent.length === 0 ? (
                <EmptyState
                  title="No activity recorded yet"
                  description="Events appear here as soon as something real happens: a project is created, an agent starts, a tool runs, a task finishes. There is no simulated activity."
                />
              ) : (
                <ul className="divide-y divide-white/[0.05]">
                  {recent.map((event) => (
                    <li key={event.id} className="flex items-start gap-3 px-5 py-2.5">
                      <LevelDot level={event.level} />
                      <div className="min-w-0 flex-1">
                        <p className={`text-[13px] ${levelClass(event.level)}`}>
                          {event.message}
                        </p>
                        <p className="mt-0.5 flex flex-wrap items-center gap-2 text-[11px] text-slate-600">
                          <span className="mono">{event.type}</span>
                          {event.agent_key && <span>· {event.agent_key}</span>}
                          <span>· {formatRelative(event.created_at)}</span>
                        </p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>

            <div className="grid gap-5 lg:grid-cols-2">
              <Panel title="Model providers" subtitle="Connection state is measured, not assumed">
                {providers.error ? (
                  <ErrorState message={providers.error} onRetry={providers.reload} />
                ) : (
                  <ul className="space-y-2.5">
                    {(providers.data ?? []).map((provider) => (
                      <li
                        key={provider.key}
                        className="flex items-center justify-between gap-3 rounded-lg border border-white/[0.06] px-3.5 py-2.5"
                      >
                        <div className="min-w-0">
                          <p className="text-[13px] font-medium text-slate-200">
                            {provider.name}
                          </p>
                          <p className="truncate text-[11px] text-slate-500">
                            {provider.connected
                              ? `${provider.models.length} model(s) available`
                              : provider.configured
                                ? 'Configured, not yet tested'
                                : `Set ${provider.required_env.join(' or ')}`}
                          </p>
                        </div>
                        <StatusBadge status={provider.status} />
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>

              <Panel title="Integrations" subtitle="Coding engines, source control, deployment">
                {integrations.error ? (
                  <ErrorState message={integrations.error} onRetry={integrations.reload} />
                ) : (
                  <ul className="space-y-2.5">
                    {(integrations.data ?? []).map((integration) => (
                      <li
                        key={integration.key}
                        className="flex items-center justify-between gap-3 rounded-lg border border-white/[0.06] px-3.5 py-2.5"
                      >
                        <div className="min-w-0">
                          <p className="text-[13px] font-medium text-slate-200">
                            {integration.name}
                          </p>
                          <p className="truncate text-[11px] text-slate-500">
                            {String(
                              integration.details?.message ??
                                (integration.configured
                                  ? 'Configured, not yet tested'
                                  : `Set ${integration.required_env.join(' or ')}`),
                            )}
                          </p>
                        </div>
                        <StatusBadge status={integration.status} />
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
