/**
 * Creative Studio.
 *
 * Design work is produced by the creative agents and stored as artifacts. An
 * artifact must be approved before engineering agents should treat it as the
 * design system.
 */

import { useMemo, useState } from 'react'

import { IconCheck, IconPlay } from '@/components/icons'
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

const STUDIO_AGENTS = [
  {
    key: 'brand_strategist',
    label: 'Brand strategy',
    description: 'Positioning, personality and the promise the product makes.',
    taskType: 'branding',
    prompt:
      'Define the brand strategy: positioning statement, personality traits, tone of voice, and the single promise the product makes to its user.',
  },
  {
    key: 'naming_agent',
    label: 'Naming',
    description: 'Generate and evaluate candidate names.',
    taskType: 'branding',
    prompt:
      'Propose six product names. For each, give the rationale, likely domain availability considerations, and any obvious trademark or pronunciation risk. Rank them and justify the top choice.',
  },
  {
    key: 'visual_identity',
    label: 'Visual identity',
    description: 'Colour, typography and design tokens.',
    taskType: 'branding',
    prompt:
      'Define a visual identity: a colour palette with hex values and usage rules, a typography pairing with fallbacks, and design tokens for spacing, radius and elevation. Explain the reasoning behind each choice.',
  },
  {
    key: 'ui_ux_designer',
    label: 'UI/UX flows',
    description: 'User flows, information architecture and screen plans.',
    taskType: 'ui_design',
    prompt:
      'Design the primary user flows. For each, list the steps, the screen involved, the decision points, and the failure states. Then specify the screens needed for a first release.',
  },
  {
    key: 'prototype_designer',
    label: 'Prototype plan',
    description: 'A buildable prototype specification.',
    taskType: 'ui_design',
    prompt:
      'Produce a prototype specification for the main screen: layout regions, component inventory, interaction states, and the exact copy for primary actions.',
  },
]

export default function Studio() {
  const artifacts = useQuery(() => api.artifacts(), [], { pollMs: 20000 })
  const projects = useQuery(() => api.projects(), [])

  const [objective, setObjective] = useState('')
  const [projectId, setProjectId] = useState('')
  const [running, setRunning] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [results, setResults] = useState<Task[]>([])

  const designArtifacts = useMemo(
    () =>
      (artifacts.data ?? []).filter((a) =>
        ['branding', 'ui_design', 'design', 'prototype'].includes(a.kind),
      ),
    [artifacts.data],
  )

  const run = async (agentKey: string, taskType: string, agentPrompt: string) => {
    if (!objective.trim()) {
      setError('Describe the product first so the creative agents have context.')
      return
    }
    setRunning(agentKey)
    setError(null)
    setNotice(null)
    try {
      const task = await api.run({
        prompt: `${agentPrompt}\n\nProduct context: ${objective.trim()}`,
        task_type: taskType,
        agent_key: agentKey,
        project_id: projectId || undefined,
      })
      setResults((prev) => [task, ...prev])
      setNotice(
        task.status === 'completed'
          ? `${agentKey} produced output. Approve the artifact to lock it into project memory.`
          : `Task finished with status "${task.status}".`,
      )
      artifacts.reload()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.detail : 'Creative task failed.')
    } finally {
      setRunning(null)
    }
  }

  const approve = async (id: string) => {
    setError(null)
    try {
      await api.approveArtifact(id)
      setNotice('Artifact approved. Engineering agents will treat it as the design system.')
      artifacts.reload()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.detail : 'Could not approve the artifact.')
    }
  }

  return (
    <div>
      <PageHeader
        title="Creative Studio"
        description="Move from an idea to an approved visual direction: naming, brand, identity, UI and prototypes. Engineering follows the approved design system rather than inventing its own."
      />

      <div className="space-y-5 p-6">
        {error && (
          <Banner tone="error" title="Creative task failed">
            {error}
          </Banner>
        )}
        {notice && !error && <Banner tone="success">{notice}</Banner>}

        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard label="Design artifacts" value={designArtifacts.length} />
          <StatCard
            label="Approved"
            value={designArtifacts.filter((a) => a.approved).length}
            tone="good"
          />
          <StatCard
            label="Awaiting approval"
            value={designArtifacts.filter((a) => !a.approved).length}
            tone={designArtifacts.some((a) => !a.approved) ? 'warn' : 'default'}
          />
          <StatCard label="Studio runs" value={results.length} />
        </div>

        <Panel title="Product context" subtitle="Given to every creative agent">
          <textarea
            className="input min-h-[110px] resize-y leading-relaxed"
            placeholder="Describe the product: what it does, who it is for, and the feeling it should convey."
            value={objective}
            onChange={(event) => setObjective(event.target.value)}
          />
          <div className="mt-3 max-w-xs">
            <label className="label" htmlFor="studio-project">
              Attach to project
            </label>
            <select
              id="studio-project"
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
          title="Creative agents"
          subtitle="Each button dispatches a real task to the named agent"
        >
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {STUDIO_AGENTS.map((agent) => (
              <div
                key={agent.key}
                className="flex flex-col justify-between rounded-lg border border-white/[0.07] bg-navy-900/40 p-4"
              >
                <div>
                  <p className="text-[13px] font-medium text-slate-100">{agent.label}</p>
                  <p className="mt-1 text-[11.5px] leading-relaxed text-slate-500">
                    {agent.description}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    <Chip>{agent.key}</Chip>
                    <Chip>{agent.taskType}</Chip>
                  </div>
                </div>
                <button
                  type="button"
                  className="btn-secondary mt-3.5"
                  onClick={() => run(agent.key, agent.taskType, agent.prompt)}
                  disabled={running !== null || !objective.trim()}
                >
                  <IconPlay className="h-3.5 w-3.5" />
                  {running === agent.key ? 'Working…' : 'Run agent'}
                </button>
              </div>
            ))}
          </div>
        </Panel>

        {results.length > 0 && (
          <Panel title="Outputs from this session" bodyClassName="">
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
                  {task.result && (
                    <pre className="mono mt-2.5 max-h-72 overflow-auto whitespace-pre-wrap rounded-md border border-white/[0.06] bg-navy-950/70 p-3 text-slate-300">
                      {task.result}
                    </pre>
                  )}
                </li>
              ))}
            </ul>
          </Panel>
        )}

        <Panel
          title="Design artifacts"
          subtitle="Approve an artifact to make it the authoritative design system"
          bodyClassName=""
        >
          {artifacts.error ? (
            <ErrorState message={artifacts.error} onRetry={artifacts.reload} />
          ) : artifacts.loading && !artifacts.data ? (
            <LoadingState />
          ) : designArtifacts.length === 0 ? (
            <EmptyState
              title="No design artifacts"
              description="Run a creative agent above. Structured outputs are stored as artifacts you can approve."
            />
          ) : (
            <ul className="divide-y divide-white/[0.05]">
              {designArtifacts.map((artifact) => (
                <li key={artifact.id} className="px-5 py-3.5">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-[13px] text-slate-200">{artifact.title}</p>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5">
                        <Chip>{artifact.kind}</Chip>
                        <span className="text-[11px] text-slate-600">
                          {formatRelative(artifact.created_at)}
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <StatusBadge
                        status={artifact.approved ? 'completed' : 'waiting_approval'}
                        label={artifact.approved ? 'approved' : 'pending approval'}
                      />
                      {!artifact.approved && (
                        <button
                          type="button"
                          className="btn-primary text-xs"
                          onClick={() => approve(artifact.id)}
                        >
                          <IconCheck className="h-3.5 w-3.5" />
                          Approve
                        </button>
                      )}
                    </div>
                  </div>
                  <p className="mt-2 whitespace-pre-wrap text-[12px] leading-relaxed text-slate-400">
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
