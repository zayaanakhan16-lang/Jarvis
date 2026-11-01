/**
 * Hackathon Intelligence.
 *
 * Every opportunity shows its source links and last verification date. Fields
 * the platform could not verify from an official source are labelled as
 * unverified rather than filled with a plausible guess.
 */

import { useState } from 'react'

import { IconExternal, IconRefresh } from '@/components/icons'
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
  UnknownValue,
} from '@/components/ui'
import { ApiError, api } from '@/lib/api'
import { formatDateTime, formatRelative } from '@/lib/format'
import { useQuery } from '@/lib/hooks'

function valueOrUnknown(value: string | null | undefined) {
  return value && value.trim() ? value : <UnknownValue label="not verified" />
}

export default function Hackathons() {
  const hackathons = useQuery(() => api.hackathons(), [], { pollMs: 30000 })
  const [researching, setResearching] = useState(false)
  const [prompt, setPrompt] = useState(
    'Find currently open online hackathons suitable for an individual developer. For each, report the official registration page, deadlines, eligibility rules and judging criteria. Cite the official source for every field.',
  )
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)

  const runResearch = async () => {
    setResearching(true)
    setError(null)
    setNotice(null)
    try {
      const task = await api.researchHackathons(prompt)
      setNotice(
        task.status === 'completed'
          ? 'Research task completed. Findings appear below if the model returned verified sources.'
          : `Research task finished with status "${task.status}".`,
      )
      hackathons.reload()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.detail : 'Research request failed.')
    } finally {
      setResearching(false)
    }
  }

  const list = hackathons.data ?? []
  const verified = list.filter((h) => h.verified).length
  const current = list.find((h) => h.id === selected) ?? null

  return (
    <div>
      <PageHeader
        title="Hackathon Intelligence"
        description="Discover opportunities, verify eligibility against official sources, and analyse judging criteria. Nothing is invented: unverified fields say so."
        actions={
          <button type="button" className="btn-secondary" onClick={hackathons.reload}>
            <IconRefresh className="h-4 w-4" />
            Refresh
          </button>
        }
      />

      <div className="space-y-5 p-6">
        {error && (
          <Banner tone="error" title="Research failed">
            {error}
          </Banner>
        )}
        {notice && !error && <Banner tone="success">{notice}</Banner>}

        <Banner tone="warn" title="Verification policy">
          JARVIS only records a field when an official source states it. Deadlines, prizes and
          eligibility rules change often, so always confirm on the organiser's own page before
          relying on them.
        </Banner>

        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard label="Tracked" value={list.length} />
          <StatCard label="Verified" value={verified} tone={verified > 0 ? 'good' : 'default'} />
          <StatCard label="Unverified" value={list.length - verified} tone={list.length - verified > 0 ? 'warn' : 'default'} />
          <StatCard label="Online" value={list.filter((h) => h.is_online === true).length} />
        </div>

        <Panel
          title="Run discovery research"
          subtitle="Uses the research agent with your configured model and a real search provider"
        >
          <textarea
            className="input min-h-[90px] resize-y leading-relaxed"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            disabled={researching}
          />
          <div className="mt-3 flex flex-wrap items-center gap-2.5">
            <button
              type="button"
              className="btn-primary"
              onClick={runResearch}
              disabled={researching || !prompt.trim()}
            >
              {researching ? 'Researching…' : 'Start research task'}
            </button>
            <p className="text-[11px] text-slate-500">
              Results are stored with their source URLs. Findings without a source are kept
              unverified.
            </p>
          </div>
        </Panel>

        {hackathons.error && <ErrorState message={hackathons.error} onRetry={hackathons.reload} />}
        {hackathons.loading && !hackathons.data && <LoadingState label="Loading opportunities" />}

        {hackathons.data && list.length === 0 && (
          <Panel>
            <EmptyState
              title="No opportunities recorded"
              description="Run a discovery research task above. JARVIS will only store fields that an official source supports; everything else is left blank and labelled."
            />
          </Panel>
        )}

        {list.length > 0 && (
          <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
            <Panel title="Opportunities" bodyClassName="" subtitle={`${list.length} tracked`}>
              <ul className="divide-y divide-white/[0.05]">
                {list.map((hackathon) => (
                  <li key={hackathon.id}>
                    <button
                      type="button"
                      className={`w-full px-5 py-3.5 text-left transition-colors hover:bg-white/[0.025] ${
                        selected === hackathon.id ? 'bg-accent/[0.06]' : ''
                      }`}
                      onClick={() => setSelected(hackathon.id)}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-[13px] font-medium text-slate-200">
                            {hackathon.name}
                          </p>
                          <p className="mt-0.5 text-[11px] text-slate-500">
                            {hackathon.organizer ?? 'organiser unknown'}
                          </p>
                          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                            <Chip>
                              {hackathon.is_online === null
                                ? 'format unknown'
                                : hackathon.is_online
                                  ? 'online'
                                  : 'in person'}
                            </Chip>
                            <Chip>
                              deadline{' '}
                              {hackathon.registration_deadline
                                ? formatDateTime(hackathon.registration_deadline)
                                : 'unknown'}
                            </Chip>
                          </div>
                        </div>
                        <StatusBadge
                          status={hackathon.verified ? 'completed' : 'waiting_approval'}
                          label={hackathon.verified ? 'verified' : 'unverified'}
                        />
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            </Panel>

            <div className="space-y-5">
              {!current ? (
                <Panel title="Details">
                  <EmptyState
                    title="Select an opportunity"
                    description="Choose one to see its eligibility rules, deliverables and source links."
                  />
                </Panel>
              ) : (
                <Panel
                  title={current.name}
                  subtitle={current.organizer ?? 'Organiser not verified'}
                  actions={
                    <StatusBadge
                      status={current.verified ? 'completed' : 'waiting_approval'}
                      label={current.verified ? 'verified' : 'unverified'}
                    />
                  }
                >
                  <dl className="space-y-3">
                    <Field label="Registration deadline" value={valueOrUnknown(current.registration_deadline)} />
                    <Field label="Event start" value={valueOrUnknown(current.event_start)} />
                    <Field label="Event end" value={valueOrUnknown(current.event_end)} />
                    <Field label="Location" value={valueOrUnknown(current.location)} />
                    <Field
                      label="Format"
                      value={
                        current.is_online === null ? (
                          <UnknownValue label="not verified" />
                        ) : current.is_online ? (
                          'Online'
                        ) : (
                          'In person'
                        )
                      }
                    />
                    <Field label="Age restrictions" value={valueOrUnknown(current.age_restrictions)} />
                    <Field
                      label="Country restrictions"
                      value={valueOrUnknown(current.country_restrictions)}
                    />
                    <Field
                      label="Team requirements"
                      value={valueOrUnknown(current.team_requirements)}
                    />
                    <Field label="Prizes" value={valueOrUnknown(current.prizes)} />
                    <Field
                      label="Submission requirements"
                      value={valueOrUnknown(current.submission_requirements)}
                    />
                    <Field
                      label="Judging criteria"
                      value={valueOrUnknown(current.judging_criteria)}
                    />
                    <Field label="Eligibility notes" value={valueOrUnknown(current.eligibility_notes)} />
                    <Field
                      label="Last verified"
                      value={
                        current.last_verified_at
                          ? `${formatDateTime(current.last_verified_at)} (${formatRelative(
                              current.last_verified_at,
                            )})`
                          : 'never verified'
                      }
                    />
                  </dl>

                  {current.tracks.length > 0 && (
                    <div className="mt-4">
                      <p className="label">Tracks</p>
                      <div className="flex flex-wrap gap-1.5">
                        {current.tracks.map((track) => (
                          <Chip key={track}>{track}</Chip>
                        ))}
                      </div>
                    </div>
                  )}

                  {current.verification_notes && (
                    <p className="mt-4 text-[11.5px] leading-relaxed text-slate-400">
                      {current.verification_notes}
                    </p>
                  )}

                  <div className="divider" />

                  <p className="label">Sources</p>
                  {current.source_urls.length === 0 ? (
                    <p className="text-[12px] text-slate-500">
                      No source recorded. Treat every field above as unconfirmed.
                    </p>
                  ) : (
                    <ul className="space-y-1.5">
                      {current.source_urls.map((url) => (
                        <li key={url}>
                          <a
                            href={url}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1.5 break-all text-[11.5px] text-accent hover:text-accent-bright"
                          >
                            {url} <IconExternal className="h-3 w-3 shrink-0" />
                          </a>
                        </li>
                      ))}
                    </ul>
                  )}

                  {current.url && (
                    <a
                      href={current.url}
                      target="_blank"
                      rel="noreferrer"
                      className="btn-secondary mt-4"
                    >
                      Open official page <IconExternal className="h-3.5 w-3.5" />
                    </a>
                  )}

                  <p className="mt-3 text-[11px] text-slate-600">
                    Record id <Mono>{current.id}</Mono>
                  </p>
                </Panel>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
