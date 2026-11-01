/** Projects: objectives, tasks, memory and artifacts. */

import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import PageHeader from '@/components/PageHeader'
import {
  Chip,
  EmptyState,
  ErrorState,
  Field,
  LoadingState,
  Mono,
  Panel,
  ProgressBar,
  StatCard,
  StatusBadge,
} from '@/components/ui'
import { api, ApiError } from '@/lib/api'
import { formatDateTime, formatRelative } from '@/lib/format'
import { useQuery } from '@/lib/hooks'

export default function Projects() {
  const { projectId } = useParams<{ projectId?: string }>()
  const projects = useQuery(() => api.projects(), [], { pollMs: 15000 })
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const [objective, setObjective] = useState('')
  const [repository, setRepository] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const selectedId = projectId ?? projects.data?.[0]?.id ?? ''
  const selected = useMemo(
    () => (projects.data ?? []).find((p) => p.id === selectedId) ?? null,
    [projects.data, selectedId],
  )

  const tasks = useQuery(() => (selectedId ? api.projectTasks(selectedId) : Promise.resolve([])), [selectedId])
  const memory = useQuery(
    () => (selectedId ? api.projectMemory(selectedId) : Promise.resolve([])),
    [selectedId],
  )
  const artifacts = useQuery(
    () => (selectedId ? api.projectArtifacts(selectedId) : Promise.resolve([])),
    [selectedId],
  )

  const create = async () => {
    if (!name.trim()) return
    setBusy(true)
    setError(null)
    try {
      await api.createProject({
        name: name.trim(),
        objective: objective.trim() || undefined,
        repository: repository.trim() || undefined,
      })
      setName('')
      setObjective('')
      setRepository('')
      setCreating(false)
      projects.reload()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.detail : 'Could not create the project.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <PageHeader
        title="Projects"
        description="A project binds an objective to its tasks, approved decisions, memory and artifacts. Memory is scoped per project."
        actions={
          <button type="button" className="btn-primary" onClick={() => setCreating((v) => !v)}>
            {creating ? 'Cancel' : 'New project'}
          </button>
        }
      />

      <div className="space-y-5 p-6">
        {error && <ErrorState message={error} />}

        {creating && (
          <Panel title="New project">
            <div className="grid gap-3 sm:grid-cols-3">
              <div>
                <label className="label" htmlFor="p-name">
                  Name
                </label>
                <input
                  id="p-name"
                  className="input"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Hackathon entry"
                />
              </div>
              <div>
                <label className="label" htmlFor="p-repo">
                  Repository (optional)
                </label>
                <input
                  id="p-repo"
                  className="input"
                  value={repository}
                  onChange={(e) => setRepository(e.target.value)}
                  placeholder="owner/repo"
                />
              </div>
              <div>
                <label className="label" htmlFor="p-obj">
                  Objective (optional)
                </label>
                <input
                  id="p-obj"
                  className="input"
                  value={objective}
                  onChange={(e) => setObjective(e.target.value)}
                  placeholder="What should this project achieve?"
                />
              </div>
            </div>
            <button
              type="button"
              className="btn-primary mt-4"
              onClick={create}
              disabled={!name.trim() || busy}
            >
              {busy ? 'Creating…' : 'Create project'}
            </button>
          </Panel>
        )}

        {projects.error && <ErrorState message={projects.error} onRetry={projects.reload} />}
        {projects.loading && !projects.data && <LoadingState label="Loading projects" />}

        {projects.data && projects.data.length === 0 && !creating && (
          <Panel>
            <EmptyState
              title="No projects yet"
              description="Create a project to group an objective, its tasks and everything the agents learn along the way."
              action={
                <button type="button" className="btn-primary" onClick={() => setCreating(true)}>
                  Create the first project
                </button>
              }
            />
          </Panel>
        )}

        {projects.data && projects.data.length > 0 && (
          <div className="grid gap-5 xl:grid-cols-[320px_minmax(0,1fr)]">
            <Panel title="All projects" bodyClassName="" subtitle={`${projects.data.length} total`}>
              <ul className="divide-y divide-white/[0.05]">
                {projects.data.map((project) => (
                  <li key={project.id}>
                    <Link
                      to={`/projects/${project.id}`}
                      className={`block px-5 py-3 transition-colors hover:bg-white/[0.025] ${
                        project.id === selectedId ? 'bg-accent/[0.06]' : ''
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <p className="truncate text-[13px] font-medium text-slate-200">
                          {project.name}
                        </p>
                        <StatusBadge status={project.status} />
                      </div>
                      <p className="mt-1 truncate text-[11px] text-slate-500">
                        {project.objective ?? 'No objective recorded'}
                      </p>
                      <div className="mt-2">
                        <ProgressBar
                          completed={project.completed_count}
                          total={project.task_count}
                        />
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            </Panel>

            <div className="space-y-5">
              {!selected ? (
                <Panel>
                  <EmptyState title="Select a project" description="Choose a project to inspect." />
                </Panel>
              ) : (
                <>
                  <Panel
                    title={selected.name}
                    subtitle={selected.objective ?? 'No objective recorded'}
                    actions={<StatusBadge status={selected.status} />}
                  >
                    <dl className="grid gap-4 sm:grid-cols-3">
                      <Field label="Slug" value={<Mono>{selected.slug}</Mono>} />
                      <Field label="Repository" value={selected.repository ?? 'not linked'} />
                      <Field label="Coding engine" value={selected.coding_engine ?? 'not set'} />
                      <Field label="Created" value={formatDateTime(selected.created_at)} />
                      <Field label="Updated" value={formatDateTime(selected.updated_at)} />
                      <Field
                        label="Progress"
                        value={`${selected.completed_count}/${selected.task_count} tasks`}
                      />
                    </dl>
                  </Panel>

                  <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                    <StatCard label="Tasks" value={selected.task_count} />
                    <StatCard label="Completed" value={selected.completed_count} tone="good" />
                    <StatCard label="Memory entries" value={(memory.data ?? []).length} />
                    <StatCard label="Artifacts" value={(artifacts.data ?? []).length} />
                  </div>

                  <Panel title="Tasks" bodyClassName="" subtitle="Dependency-ordered work">
                    {tasks.loading && !tasks.data ? (
                      <LoadingState />
                    ) : (tasks.data ?? []).length === 0 ? (
                      <EmptyState
                        title="No tasks yet"
                        description="Use the AI Workspace to plan this objective into tasks."
                        action={
                          <Link to="/workspace" className="btn-primary">
                            Open workspace
                          </Link>
                        }
                      />
                    ) : (
                      <ul className="divide-y divide-white/[0.05]">
                        {tasks.data!.map((task) => (
                          <li key={task.id} className="px-5 py-3">
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0">
                                <p className="text-[13px] text-slate-200">{task.title}</p>
                                <div className="mt-1 flex flex-wrap items-center gap-1.5">
                                  <Chip>{task.task_type}</Chip>
                                  {task.agent_key && <Chip>{task.agent_key}</Chip>}
                                  {task.provider && (
                                    <Chip>
                                      {task.provider}/{task.model}
                                    </Chip>
                                  )}
                                </div>
                              </div>
                              <StatusBadge status={task.status} />
                            </div>
                            {task.error && (
                              <p className="mt-2 text-[12px] text-red-300">{task.error}</p>
                            )}
                          </li>
                        ))}
                      </ul>
                    )}
                  </Panel>

                  <Panel
                    title="Project memory"
                    subtitle="Approved decisions and facts the agents reuse"
                    bodyClassName=""
                  >
                    {(memory.data ?? []).length === 0 ? (
                      <EmptyState
                        title="No memory recorded"
                        description="Memory is written when tasks record durable decisions, such as an approved design system."
                      />
                    ) : (
                      <ul className="divide-y divide-white/[0.05]">
                        {memory.data!.map((entry) => (
                          <li key={entry.id} className="px-5 py-3">
                            <div className="flex items-center justify-between gap-3">
                              <p className="text-[12.5px] text-slate-200">
                                <span className="mono text-accent-bright">{entry.category}</span>
                                <span className="text-slate-500"> / </span>
                                {entry.key}
                              </p>
                              <span className="text-[11px] text-slate-600">
                                {formatRelative(entry.updated_at)}
                              </span>
                            </div>
                            <p className="mt-1 whitespace-pre-wrap text-[12px] text-slate-400">
                              {entry.value}
                            </p>
                          </li>
                        ))}
                      </ul>
                    )}
                  </Panel>

                  <Panel title="Artifacts" bodyClassName="" subtitle="Outputs produced by tasks">
                    {(artifacts.data ?? []).length === 0 ? (
                      <EmptyState
                        title="No artifacts yet"
                        description="Artifacts are produced when a task generates a design, plan, report or document."
                      />
                    ) : (
                      <ul className="divide-y divide-white/[0.05]">
                        {artifacts.data!.map((artifact) => (
                          <li key={artifact.id} className="px-5 py-3">
                            <div className="flex items-center justify-between gap-3">
                              <p className="text-[13px] text-slate-200">{artifact.title}</p>
                              <div className="flex items-center gap-2">
                                <Chip>{artifact.kind}</Chip>
                                <StatusBadge
                                  status={artifact.approved ? 'completed' : 'waiting_approval'}
                                  label={artifact.approved ? 'approved' : 'pending'}
                                />
                              </div>
                            </div>
                          </li>
                        ))}
                      </ul>
                    )}
                  </Panel>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
