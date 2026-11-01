/**
 * Product Research.
 *
 * Research tasks are dispatched to specialist agents. Outputs are stored as
 * artifacts so a finding can be traced back to the task and model that
 * produced it.
 */

import { useState } from 'react'

import { IconPlay } from '@/components/icons'
import PageHeader from '@/components/PageHeader'
import {
  Banner,
  Chip,
  EmptyState,
  ErrorState,
  LoadingState,
  Panel,
  StatCard,
  StatusBadge,
} from '@/components/ui'
import { ApiError, api } from '@/lib/api'
import { formatRelative } from '@/lib/format'
import { useQuery } from '@/lib/hooks'
import type { Task } from '@/lib/types'

const RESEARCH_AGENTS = [
  {
    key: 'problem_research',
    label: 'Problem research',
    description: 'Investigate whether the problem is real and who experiences it.',
    prompt:
      'Research the problem domain. Identify who experiences the problem, how often, and what evidence exists that it is worth solving. Cite sources.',
  },
  {
    key: 'competitor_research',
    label: 'Competitor research',
    description: 'Survey existing solutions and find the gaps they leave.',
    prompt:
      'Survey existing solutions in this space. For each, describe what it does well and which user need it leaves unmet. Cite sources.',
  },
  {
    key: 'idea_development',
    label: 'Idea development',
    description: 'Generate differentiated product concepts.',
    prompt:
      'Propose three differentiated product concepts. For each, state the target user, the core mechanism, why it is different from existing tools, and the smallest version that would demonstrate value.',
  },
  {
    key: 'technical_feasibility',
    label: 'Technical feasibility',
    description: 'Assess build complexity and available technology.',
    prompt:
      'Assess the technical feasibility of these concepts. For each, list the required components, the hardest technical risk, and a realistic build scope for a small team.',
  },
  {
    key: 'product_strategy',
    label: 'Product strategy',
    description: 'Define direction, features and target users.',
    prompt:
      'Define a product strategy for the strongest concept: target user, core loop, feature set for a first release, and how success would be measured.',
  },
]

export default function Research() {
  const artifacts = useQuery(() => api.artifacts({ kind: 'research' }), [], { pollMs: 20000 })
  const tasks = useQuery(() => api.tasks(), [], { pollMs: 15000 })
  const projects = useQuery(() => api.projects(), [])

  const [objective, setObjective] = useState('')
  const [projectId, setProjectId] = useState('')
  const [running, setRunning] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [results, setResults] = useState<Task[]>([])

  const run = async (agentKey: string, agentPrompt: string) => {
    const context = objective.trim()
    if (!context) {
      setError('Describe your objective first so the research agents have context.')
      return
    }
    setRunning(agentKey)
    setError(null)
    setNotice(null)
    try {
      const task = await api.run({
        prompt: `${agentPrompt}\n\nObjective: ${context}`,
        task_type: 'research',
        agent_key: agentKey,
        project_id: projectId || undefined,
      })
      setResults((prev) => [task, ...prev])
      setNotice(
        task.status === 'completed'
          ? `${agentKey} completed the research task.`
          : `Task finished with status "${task.status}".`,
      )
      artifacts.reload()
      tasks.reload()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.detail : 'Research task failed.')
    } finally {
      setRunning(null)
    }
  }

  const researchTasks = (tasks.data ?? []).filter((task) => task.task_type === 'research')

  return (
    <div>
      <PageHeader
        title="Product Research"
        description="Dispatch specialist research agents to validate a problem, survey competitors, develop ideas and test feasibility. Every finding is traceable to the task and model that produced it."
      />

      <div className="space-y-5 p-6">
        {error && (
          <Banner tone="error" title="Research failed">
            {error}
          </Banner>
        )}
        {notice && !error && <Banner tone="success">{notice}</Banner>}

        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard label="Research tasks" value={researchTasks.length} />
          <StatCard
            label="Completed"
            value={researchTasks.filter((t) => t.status === 'completed').length}
            tone="good"
          />
          <StatCard
            label="Failed"
            value={researchTasks.filter((t) => t.status === 'failed').length}
            tone={researchTasks.some((t) => t.status === 'failed') ? 'bad' : 'default'}
          />
          <StatCard label="Research artifacts" value={(artifacts.data ?? []).length} />
        </div>

        <Panel title="Research brief" subtitle="Context every agent will receive">
          <textarea
            className="input min-h-[110px] resize-y leading-relaxed"
            placeholder="Describe the product idea or problem area you want researched."
            value={objective}
            onChange={(event) => setObjective(event.target.value)}
          />
          <div className="mt-3 max-w-xs">
            <label className="label" htmlFor="res-project">
              Attach to project
            </label>
            <select
              id="res-project"
              className="select"
              value={projectId}
              onChange={(event) => setProjectId(event.target.value)}
            >
              <option value="">No project (unscoped)</option>
              {(projects.data ?? []).map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          </div>
        </Panel>

        <Panel
          title="Research agents"
          subtitle="Each button dispatches a real task to the named agent"
        >
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {RESEARCH_AGENTS.map((agent) => (
              <div
                key={agent.key}
                className="flex flex-col justify-between rounded-lg border border-white/[0.07] bg-navy-900/40 p-4"
              >
                <div>
                  <p className="text-[13px] font-medium text-slate-100">{agent.label}</p>
                  <p className="mt-1 text-[11.5px] leading-relaxed text-slate-500">
                    {agent.description}
                  </p>
                  <div className="mt-2">
                    <Chip>{agent.key}</Chip>
                  </div>
                </div>
                <button
                  type="button"
                  className="btn-secondary mt-3.5"
                  onClick={() => run(agent.key, agent.prompt)}
                  disabled={running !== null || !objective.trim()}
                >
                  <IconPlay className="h-3.5 w-3.5" />
                  {running === agent.key ? 'Running…' : 'Run agent'}
                </button>
              </div>
            ))}
          </div>
          {!objective.trim() && (
            <p className="mt-3 text-[11px] text-amber-300/80">
              Enter a research brief above to enable these agents.
            </p>
          )}
        </Panel>

        <Panel title="Results from this session" bodyClassName="">
          {results.length === 0 ? (
            <EmptyState
              title="No research run yet"
              description="Run an agent above. Its output appears here with the model that produced it and the time it took."
            />
          ) : (
            <ul className="divide-y divide-white/[0.05]">
              {results.map((task) => (
                <li key={task.id} className="px-5 py-3.5">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-[13px] text-slate-200">{task.title}</p>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5">
                        <Chip>{task.agent_key}</Chip>
                        {task.provider && (
                          <Chip>
                            {task.provider}/{task.model}
                          </Chip>
                        )}
                        <span className="text-[11px] text-slate-600">
                          {formatRelative(task.created_at)}
                        </span>
                      </div>
                    </div>
                    <StatusBadge status={task.status} />
                  </div>
                  {task.error && (
                    <p className="mt-2 text-[12px] text-red-300">{task.error}</p>
                  )}
                  {task.result && (
                    <pre className="mono mt-2.5 max-h-64 overflow-auto whitespace-pre-wrap rounded-md border border-white/[0.06] bg-navy-950/70 p-3 text-slate-300">
                      {task.result}
                    </pre>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel
          title="Research artifacts"
          subtitle="Stored findings, kept with their provenance"
          bodyClassName=""
        >
          {artifacts.error ? (
            <ErrorState message={artifacts.error} onRetry={artifacts.reload} />
          ) : artifacts.loading && !artifacts.data ? (
            <LoadingState />
          ) : (artifacts.data ?? []).length === 0 ? (
            <EmptyState
              title="No research artifacts"
              description="Artifacts are written when a research task returns a structured finding."
            />
          ) : (
            <ul className="divide-y divide-white/[0.05]">
              {artifacts.data!.map((artifact) => (
                <li key={artifact.id} className="px-5 py-3.5">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-[13px] text-slate-200">{artifact.title}</p>
                    <StatusBadge
                      status={artifact.approved ? 'completed' : 'waiting_approval'}
                      label={artifact.approved ? 'approved' : 'pending'}
                    />
                  </div>
                  <p className="mt-1.5 whitespace-pre-wrap text-[12px] leading-relaxed text-slate-400">
                    {artifact.content}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  )
}
