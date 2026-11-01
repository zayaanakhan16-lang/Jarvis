/**
 * Integrations: model providers and external services.
 *
 * A service is only shown as connected after a real network probe succeeds.
 * Unconfigured services state exactly which environment variable is missing.
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
} from '@/components/ui'
import { ApiError, api } from '@/lib/api'
import { formatRelative } from '@/lib/format'
import { useQuery } from '@/lib/hooks'
import type { Integration, ProbeResult, Provider } from '@/lib/types'

export default function Integrations() {
  const providers = useQuery(() => api.providers(), [], { pollMs: 30000 })
  const integrations = useQuery(() => api.integrations(), [], { pollMs: 30000 })

  const [testing, setTesting] = useState<string | null>(null)
  const [results, setResults] = useState<Record<string, ProbeResult | string>>({})

  const testProvider = async (provider: Provider) => {
    setTesting(provider.key)
    try {
      const result = await api.testProvider(provider.key)
      setResults((prev) => ({ ...prev, [provider.key]: result }))
      providers.reload()
    } catch (cause) {
      setResults((prev) => ({
        ...prev,
        [provider.key]: cause instanceof ApiError ? cause.detail : 'Connection test failed.',
      }))
    } finally {
      setTesting(null)
    }
  }

  const testIntegration = async (integration: Integration) => {
    setTesting(integration.key)
    try {
      const result = await api.testIntegration(integration.key)
      setResults((prev) => ({
        ...prev,
        [integration.key]: {
          key: result.key,
          ok: result.connected,
          status: result.status,
          message: String(result.details?.message ?? result.status),
          models: [],
          latency_ms: 0,
        },
      }))
      integrations.reload()
    } catch (cause) {
      setResults((prev) => ({
        ...prev,
        [integration.key]: cause instanceof ApiError ? cause.detail : 'Connection test failed.',
      }))
    } finally {
      setTesting(null)
    }
  }

  const providerList = providers.data ?? []
  const integrationList = integrations.data ?? []
  const connectedCount =
    providerList.filter((p) => p.connected).length +
    integrationList.filter((i) => i.connected).length
  const configuredCount =
    providerList.filter((p) => p.configured).length +
    integrationList.filter((i) => i.configured).length

  return (
    <div>
      <PageHeader
        title="Integrations"
        description="Model providers and external services. Credentials live server-side only; the browser sees configuration flags, never keys."
        actions={
          <button
            type="button"
            className="btn-secondary"
            onClick={() => {
              providers.reload()
              integrations.reload()
            }}
          >
            <IconRefresh className="h-4 w-4" />
            Refresh
          </button>
        }
      />

      <div className="space-y-5 p-6">
        <Banner tone="info" title="How connection state is determined">
          A provider or integration is marked connected only after JARVIS makes a real network
          request and it succeeds. Configured but untested services are shown as configured, never
          as connected.
        </Banner>

        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard label="Providers" value={providerList.length} />
          <StatCard
            label="Providers connected"
            value={providerList.filter((p) => p.connected).length}
            tone={providerList.some((p) => p.connected) ? 'good' : 'default'}
          />
          <StatCard label="Integrations" value={integrationList.length} />
          <StatCard
            label="Connected total"
            value={`${connectedCount}/${configuredCount}`}
            hint="connected / configured"
            tone={connectedCount > 0 ? 'good' : 'default'}
          />
        </div>

        <Panel
          title="Model providers"
          subtitle="Text generation for planning, coding, analysis and review"
        >
          {providers.error ? (
            <ErrorState message={providers.error} onRetry={providers.reload} />
          ) : providers.loading && !providers.data ? (
            <LoadingState />
          ) : (
            <ul className="space-y-3">
              {providerList.map((provider) => {
                const result = results[provider.key]
                return (
                  <li
                    key={provider.key}
                    className="rounded-lg border border-white/[0.07] bg-navy-900/40 p-4"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="text-[13px] font-medium text-slate-100">
                            {provider.name}
                          </p>
                          <Chip>{provider.kind}</Chip>
                        </div>
                        <p className="mt-1 text-[11px] text-slate-500">
                          {provider.configured
                            ? provider.connected
                              ? provider.models.length > 0
                                ? `${provider.models.length} model(s) reported by the provider`
                                : 'Reachable, but the provider returned no model list'
                              : 'Credentials present, awaiting a connection test'
                            : `Requires ${provider.required_env.join(' or ')}`}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <StatusBadge status={provider.status} />
                        <button
                          type="button"
                          className="btn-secondary text-xs"
                          onClick={() => testProvider(provider)}
                          disabled={testing === provider.key || !provider.configured}
                          title={
                            provider.configured
                              ? 'Make a real request to verify this provider'
                              : 'Set the credential first'
                          }
                        >
                          {testing === provider.key ? 'Testing…' : 'Test'}
                        </button>
                      </div>
                    </div>

                    {provider.models.length > 0 && (
                      <div className="mt-2.5">
                        <p className="label">Discovered models</p>
                        <div className="flex flex-wrap gap-1.5">
                          {provider.models.slice(0, 12).map((model) => (
                            <Chip key={model}>{model}</Chip>
                          ))}
                        </div>
                      </div>
                    )}

                    {provider.models.length === 0 && provider.catalogue.length > 0 && (
                      <div className="mt-2.5">
                        <p className="label">Suggested identifiers</p>
                        <div className="flex flex-wrap gap-1.5">
                          {provider.catalogue.slice(0, 12).map((model) => (
                            <Chip key={model}>{model}</Chip>
                          ))}
                        </div>
                        <p className="mt-1 text-[10.5px] text-slate-600">
                          Not verified. Run a connection test to see which models this provider
                          actually serves.
                        </p>
                      </div>
                    )}

                    <dl className="mt-3 grid gap-2.5 sm:grid-cols-3">
                      <Field
                        label="Base URL"
                        value={<Mono>{provider.base_url ?? 'default'}</Mono>}
                      />
                      <Field label="Last tested" value={formatRelative(provider.last_tested_at)} />
                      <Field
                        label="Required env"
                        value={<Mono>{provider.required_env.join(', ') || 'none'}</Mono>}
                      />
                    </dl>

                    {provider.last_error && (
                      <p className="mt-2 text-[11.5px] text-red-300">{provider.last_error}</p>
                    )}

                    {result && (
                      <div className="mt-2.5 rounded-md border border-white/[0.07] bg-navy-950/60 px-3 py-2">
                        {typeof result === 'string' ? (
                          <p className="text-[11.5px] text-red-300">{result}</p>
                        ) : (
                          <p
                            className={`text-[11.5px] ${
                              result.ok ? 'text-emerald-300' : 'text-amber-200'
                            }`}
                          >
                            {result.message}
                            {result.latency_ms > 0 && ` (${result.latency_ms}ms)`}
                          </p>
                        )}
                      </div>
                    )}

                    {provider.docs_url && (
                      <a
                        href={provider.docs_url}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-2.5 inline-flex items-center gap-1 text-[11px] text-accent hover:text-accent-bright"
                      >
                        Documentation <IconExternal className="h-3 w-3" />
                      </a>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </Panel>

        <Panel
          title="External services"
          subtitle="Coding engines, source control, research, voice and deployment"
        >
          {integrations.error ? (
            <ErrorState message={integrations.error} onRetry={integrations.reload} />
          ) : integrations.loading && !integrations.data ? (
            <LoadingState />
          ) : integrationList.length === 0 ? (
            <EmptyState
              title="No integrations registered"
              description="Integrations are registered by the backend."
            />
          ) : (
            <ul className="space-y-3">
              {integrationList.map((integration) => {
                const result = results[integration.key]
                const message = String(integration.details?.message ?? '')
                return (
                  <li
                    key={integration.key}
                    className="rounded-lg border border-white/[0.07] bg-navy-900/40 p-4"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="text-[13px] font-medium text-slate-100">
                            {integration.name}
                          </p>
                          <Chip>{integration.category}</Chip>
                        </div>
                        <p className="mt-1 text-[11.5px] leading-relaxed text-slate-500">
                          {integration.description}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <StatusBadge status={integration.status} />
                        <button
                          type="button"
                          className="btn-secondary text-xs"
                          onClick={() => testIntegration(integration)}
                          disabled={testing === integration.key}
                        >
                          {testing === integration.key ? 'Testing…' : 'Test'}
                        </button>
                      </div>
                    </div>

                    <dl className="mt-3 grid gap-2.5 sm:grid-cols-3">
                      <Field
                        label="Required env"
                        value={<Mono>{integration.required_env.join(', ') || 'none'}</Mono>}
                      />
                      <Field
                        label="Last tested"
                        value={formatRelative(integration.last_tested_at)}
                      />
                      <Field label="Configured" value={integration.configured ? 'yes' : 'no'} />
                    </dl>

                    {message && (
                      <p className="mt-2 text-[11.5px] leading-relaxed text-slate-400">
                        {message}
                      </p>
                    )}

                    {integration.last_error && (
                      <p className="mt-2 text-[11.5px] text-red-300">{integration.last_error}</p>
                    )}

                    {result && (
                      <div className="mt-2.5 rounded-md border border-white/[0.07] bg-navy-950/60 px-3 py-2">
                        {typeof result === 'string' ? (
                          <p className="text-[11.5px] text-red-300">{result}</p>
                        ) : (
                          <p
                            className={`text-[11.5px] ${
                              result.ok ? 'text-emerald-300' : 'text-amber-200'
                            }`}
                          >
                            {result.message}
                          </p>
                        )}
                      </div>
                    )}

                    {integration.docs_url && (
                      <a
                        href={integration.docs_url}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-2.5 inline-flex items-center gap-1 text-[11px] text-accent hover:text-accent-bright"
                      >
                        Documentation <IconExternal className="h-3 w-3" />
                      </a>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  )
}
