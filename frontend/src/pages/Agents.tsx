/** Agent Control Center: the real roster, with real execution state. */

import { useMemo, useState } from 'react'

import PageHeader from '@/components/PageHeader'
import {
  Chip,
  EmptyState,
  ErrorState,
  Field,
  LoadingState,
  Panel,
  StatCard,
  StatusBadge,
} from '@/components/ui'
import { api } from '@/lib/api'
import { formatRelative } from '@/lib/format'
import { useQuery } from '@/lib/hooks'

export default function Agents() {
  const agents = useQuery(() => api.agents(), [], { pollMs: 10000 })
  const departments = useQuery(() => api.departments(), [])
  const [department, setDepartment] = useState('')
  const [status, setStatus] = useState('')
  const [selected, setSelected] = useState<string | null>(null)

  const filtered = useMemo(() => {
    return (agents.data ?? []).filter(
      (agent) =>
        (!department || agent.department === department) &&
        (!status || agent.status === status),
    )
  }, [agents.data, department, status])

  const busy = (agents.data ?? []).filter((a) => a.status === 'running').length
  const failed = (agents.data ?? []).filter((a) => a.status === 'failed').length

  const selectedAgent = (agents.data ?? []).find((a) => a.key === selected) ?? null
  const agentTasks = useQuery(
    () => (selected ? api.agentTasks(selected) : Promise.resolve([])),
    [selected],
  )

  return (
    <div>
      <PageHeader
        title="Agents"
        description="Every agent is a registered worker with a department, declared capabilities and a permission scope. Status reflects real execution, not decoration."
      />

      <div className="space-y-5 p-6">
        {agents.error && <ErrorState message={agents.error} onRetry={agents.reload} />}
        {agents.loading && !agents.data && <LoadingState label="Loading roster" />}

        {agents.data && (
          <>
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <StatCard label="Agents" value={agents.data.length} hint="registered" />
              <StatCard label="Departments" value={(departments.data ?? []).length} />
              <StatCard
                label="Running"
                value={busy}
                tone={busy > 0 ? 'good' : 'default'}
                hint="executing now"
              />
              <StatCard
                label="Failed"
                value={failed}
                tone={failed > 0 ? 'bad' : 'default'}
                hint="needs attention"
              />
            </div>

            <Panel title="Filters">
              <div className="grid gap-3 sm:grid-cols-3">
                <div>
                  <label className="label" htmlFor="agent-dept">
                    Department
                  </label>
                  <select
                    id="agent-dept"
                    className="select"
                    value={department}
                    onChange={(event) => setDepartment(event.target.value)}
                  >
                    <option value="">All departments</option>
                    {(departments.data ?? []).map((dept) => (
                      <option key={dept.key} value={dept.key}>
                        {dept.name} ({dept.agent_count})
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="label" htmlFor="agent-status">
                    Status
                  </label>
                  <select
                    id="agent-status"
                    className="select"
                    value={status}
                    onChange={(event) => setStatus(event.target.value)}
                  >
                    <option value="">Any status</option>
                    {['idle', 'queued', 'running', 'waiting_approval', 'completed', 'failed'].map(
                      (value) => (
                        <option key={value} value={value}>
                          {value.replace(/_/g, ' ')}
                        </option>
                      ),
                    )}
                  </select>
                </div>
                <div className="flex items-end">
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => {
                      setDepartment('')
                      setStatus('')
                    }}
                  >
                    Reset
                  </button>
                </div>
              </div>
            </Panel>

            <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
              <Panel
                title="Roster"
                subtitle={`${filtered.length} of ${agents.data.length} agents`}
                bodyClassName=""
              >
                {filtered.length === 0 ? (
                  <EmptyState
                    title="No agents match"
                    description="Adjust the filters to see the roster."
                  />
                ) : (
                  <ul className="divide-y divide-white/[0.05]">
                    {filtered.map((agent) => (
                      <li key={agent.key}>
                        <button
                          type="button"
                          className={`flex w-full items-start justify-between gap-4 px-5 py-3.5 text-left transition-colors hover:bg-white/[0.025] ${
                            selected === agent.key ? 'bg-accent/[0.06]' : ''
                          }`}
                          onClick={() => setSelected(agent.key)}
                        >
                          <div className="min-w-0 flex-1">
                            <p className="text-[13px] font-medium text-slate-200">
                              {agent.name}
                            </p>
                            <p className="mt-0.5 line-clamp-2 text-[11px] leading-relaxed text-slate-500">
                              {agent.description}
                            </p>
                            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                              <Chip>{agent.department}</Chip>
                              {agent.capabilities.slice(0, 3).map((capability) => (
                                <Chip key={capability}>{capability}</Chip>
                              ))}
                            </div>
                          </div>
                          <StatusBadge status={agent.status} />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>

              <div className="space-y-5">
                {selectedAgent ? (
                  <>
                    <Panel
                      title={selectedAgent.name}
                      subtitle={selectedAgent.department}
                      actions={<StatusBadge status={selectedAgent.status} />}
                    >
                      <p className="text-[12.5px] leading-relaxed text-slate-400">
                        {selectedAgent.description}
                      </p>

                      <dl className="mt-4 space-y-2.5">
                        <Field
                          label="Task types"
                          value={selectedAgent.task_types.join(', ') || 'not declared'}
                        />
                        <Field
                          label="Tools"
                          value={
                            selectedAgent.tools.length > 0 ? (
                              <span className="flex flex-wrap gap-1.5">
                                {selectedAgent.tools.map((tool) => (
                                  <Chip key={tool}>{tool}</Chip>
                                ))}
                              </span>
                            ) : (
                              'none'
                            )
                          }
                        />
                        <Field
                          label="Permission scope"
                          value={
                            selectedAgent.permission_scope.length > 0
                              ? selectedAgent.permission_scope.join(', ')
                              : 'read-only'
                          }
                        />
                        <Field label="Completed" value={selectedAgent.tasks_completed} />
                        <Field label="Failed" value={selectedAgent.tasks_failed} />
                        <Field
                          label="Last active"
                          value={formatRelative(selectedAgent.last_active_at)}
                        />
                        {selectedAgent.last_error && (
                          <Field
                            label="Last error"
                            value={
                              <span className="text-red-300">{selectedAgent.last_error}</span>
                            }
                          />
                        )}
                      </dl>
                    </Panel>

                    <Panel title="Task history" subtitle="Real task records" bodyClassName="">
                      {agentTasks.loading && !agentTasks.data ? (
                        <LoadingState />
                      ) : (agentTasks.data ?? []).length === 0 ? (
                        <EmptyState
                          title="No tasks yet"
                          description="This agent has not been assigned any work."
                        />
                      ) : (
                        <ul className="divide-y divide-white/[0.05]">
                          {agentTasks.data!.slice(0, 15).map((task) => (
                            <li
                              key={task.id}
                              className="flex items-center justify-between gap-3 px-5 py-2.5"
                            >
                              <div className="min-w-0">
                                <p className="truncate text-[12.5px] text-slate-300">
                                  {task.title}
                                </p>
                                <p className="text-[11px] text-slate-600">
                                  {task.task_type} · {formatRelative(task.created_at)}
                                </p>
                              </div>
                              <StatusBadge status={task.status} />
                            </li>
                          ))}
                        </ul>
                      )}
                    </Panel>
                  </>
                ) : (
                  <Panel title="Agent detail">
                    <EmptyState
                      title="Select an agent"
                      description="Choose an agent from the roster to see its capabilities, permission scope and task history."
                    />
                  </Panel>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
