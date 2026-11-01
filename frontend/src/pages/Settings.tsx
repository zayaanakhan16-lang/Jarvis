/**
 * Settings.
 *
 * Shows real backend configuration and explains exactly which environment
 * variable enables each capability. Secrets are never sent to the browser.
 */

import { useEffect, useState } from 'react'

import { IconCheck, IconRefresh } from '@/components/icons'
import PageHeader from '@/components/PageHeader'
import {
  Banner,
  Chip,
  ErrorState,
  Field,
  LoadingState,
  Mono,
  Panel,
  StatCard,
  StatusBadge,
} from '@/components/ui'
import { ApiError, api } from '@/lib/api'
import { useQuery } from '@/lib/hooks'

export default function Settings() {
  const settings = useQuery(() => api.settings(), [])
  const health = useQuery(() => api.health(), [], { pollMs: 20000 })
  const providers = useQuery(() => api.providers(), [])
  const integrations = useQuery(() => api.integrations(), [])
  const voice = useQuery(() => api.voiceStatus(), [])

  const [routing, setRouting] = useState('')
  const [maxParallel, setMaxParallel] = useState(4)
  const [engine, setEngine] = useState('openhands')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (!settings.data) return
    setRouting(settings.data.routing_preference.join(', '))
    setMaxParallel(settings.data.max_parallel_tasks)
    setEngine(settings.data.default_engine)
  }, [settings.data])

  const save = async () => {
    setBusy(true)
    setError(null)
    setSaved(false)
    try {
      await api.updateSettings({
        routing_preference: routing
          .split(',')
          .map((value) => value.trim())
          .filter(Boolean),
        max_parallel_tasks: maxParallel,
        default_engine: engine,
      })
      setSaved(true)
      settings.reload()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.detail : 'Could not save settings.')
    } finally {
      setBusy(false)
    }
  }

  const missingEnv = [
    ...(providers.data ?? []).filter((p) => !p.configured),
    ...(integrations.data ?? []).filter((i) => !i.configured && i.required_env.length > 0),
  ]

  return (
    <div>
      <PageHeader
        title="Settings"
        description="Runtime configuration and the exact environment variables that enable each capability. Credentials are read server-side only."
        actions={
          <button type="button" className="btn-secondary" onClick={save} disabled={busy}>
            <IconCheck className="h-4 w-4" />
            {busy ? 'Saving…' : 'Save'}
          </button>
        }
      />

      <div className="space-y-5 p-6">
        {error && (
          <Banner tone="error" title="Could not save">
            {error}
          </Banner>
        )}
        {saved && !error && <Banner tone="success">Settings saved.</Banner>}

        {settings.error && <ErrorState message={settings.error} onRetry={settings.reload} />}
        {settings.loading && !settings.data && <LoadingState />}

        {settings.data && (
          <>
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <StatCard
                label="Database"
                value={settings.data.database_backend}
                hint={health.data?.database ?? ''}
              />
              <StatCard label="Environment" value={settings.data.environment} />
              <StatCard
                label="Providers configured"
                value={(providers.data ?? []).filter((p) => p.configured).length}
              />
              <StatCard
                label="Integrations configured"
                value={(integrations.data ?? []).filter((i) => i.configured).length}
              />
            </div>

            <Panel title="Orchestration">
              <div className="grid gap-3 sm:grid-cols-3">
                <div>
                  <label className="label" htmlFor="set-routing">
                    Routing preference
                  </label>
                  <input
                    id="set-routing"
                    className="input"
                    value={routing}
                    onChange={(event) => setRouting(event.target.value)}
                    placeholder="openai, anthropic, ollama"
                  />
                  <p className="mt-1 text-[11px] text-slate-500">
                    Comma-separated provider keys. Ties in capability scoring are broken in this
                    order.
                  </p>
                </div>
                <div>
                  <label className="label" htmlFor="set-parallel">
                    Max parallel tasks
                  </label>
                  <input
                    id="set-parallel"
                    type="number"
                    min={1}
                    max={16}
                    className="input"
                    value={maxParallel}
                    onChange={(event) => setMaxParallel(Number(event.target.value))}
                  />
                  <p className="mt-1 text-[11px] text-slate-500">
                    Independent tasks run concurrently up to this limit.
                  </p>
                </div>
                <div>
                  <label className="label" htmlFor="set-engine">
                    Default coding engine
                  </label>
                  <select
                    id="set-engine"
                    className="select"
                    value={engine}
                    onChange={(event) => setEngine(event.target.value)}
                  >
                    <option value="openhands">OpenHands</option>
                    <option value="opencode">OpenCode</option>
                  </select>
                </div>
              </div>
            </Panel>

            <Panel title="Voice" subtitle="Real speech services only">
              {voice.data ? (
                <div className="space-y-2.5">
                  <Field
                    label="Text to speech"
                    value={
                      <span className="flex items-center gap-2">
                        <StatusBadge
                          status={voice.data.elevenlabs_configured ? 'connected' : 'not_configured'}
                          label={voice.data.text_to_speech}
                        />
                      </span>
                    }
                  />
                  <Field label="Speech to text" value={voice.data.speech_to_text} />
                  <p className="text-[11.5px] leading-relaxed text-slate-400">{voice.data.note}</p>
                </div>
              ) : (
                <LoadingState />
              )}
            </Panel>

            <Panel
              title="Capabilities awaiting configuration"
              subtitle="Set these environment variables to enable more of the platform"
            >
              {missingEnv.length === 0 ? (
                <p className="text-[12.5px] text-emerald-300">
                  Every registered provider and integration has credentials configured.
                </p>
              ) : (
                <ul className="divide-y divide-white/[0.05]">
                  {missingEnv.map((item) => (
                    <li
                      key={item.key}
                      className="flex flex-wrap items-center justify-between gap-3 py-2.5"
                    >
                      <div className="min-w-0">
                        <p className="text-[12.5px] text-slate-200">{item.name}</p>
                        <p className="text-[11px] text-slate-500">
                          {item.required_env.length > 0
                            ? `Set ${item.required_env.join(' or ')}`
                            : 'No credential required'}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {item.required_env.map((name) => (
                          <Chip key={name}>{name}</Chip>
                        ))}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>

            <Panel title="System information">
              <dl className="grid gap-4 sm:grid-cols-3">
                <Field label="Application" value={health.data?.app ?? 'JARVIS'} />
                <Field label="Version" value={health.data?.version ?? 'unknown'} />
                <Field
                  label="Database status"
                  value={
                    <Mono>{health.data?.database ?? 'unknown'}</Mono>
                  }
                />
                <Field
                  label="Stream subscribers"
                  value={health.data?.websocket_subscribers ?? 0}
                />
                <Field label="API prefix" value={<Mono>/api</Mono>} />
                <Field
                  label="CORS origins"
                  value={<Mono>see backend CORS_ORIGINS</Mono>}
                />
              </dl>
              <div className="divider" />
              <button type="button" className="btn-secondary" onClick={health.reload}>
                <IconRefresh className="h-4 w-4" />
                Re-check health
              </button>
            </Panel>
          </>
        )}
      </div>
    </div>
  )
}
