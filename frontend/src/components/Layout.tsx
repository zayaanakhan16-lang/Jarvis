/** Application shell: sidebar navigation, top bar, and live status. */

import { NavLink, Outlet } from 'react-router-dom'

import { api } from '@/lib/api'
import { formatRelative } from '@/lib/format'
import { useActivityStream, useQuery } from '@/lib/hooks'
import {
  IconActivity,
  IconAgents,
  IconEngineering,
  IconHackathon,
  IconIntegrations,
  IconOverview,
  IconProjects,
  IconResearch,
  IconSettings,
  IconStudio,
  IconWorkspace,
} from './icons'
import { StatusBadge } from './ui'

interface NavEntry {
  to: string
  label: string
  icon: (props: { className?: string }) => JSX.Element
  end?: boolean
}

const NAV: NavEntry[] = [
  { to: '/', label: 'Overview', icon: IconOverview, end: true },
  { to: '/workspace', label: 'AI Workspace', icon: IconWorkspace },
  { to: '/agents', label: 'Agents', icon: IconAgents },
  { to: '/hackathons', label: 'Hackathon Intelligence', icon: IconHackathon },
  { to: '/research', label: 'Product Research', icon: IconResearch },
  { to: '/studio', label: 'Creative Studio', icon: IconStudio },
  { to: '/engineering', label: 'Engineering', icon: IconEngineering },
  { to: '/projects', label: 'Projects', icon: IconProjects },
  { to: '/integrations', label: 'Integrations', icon: IconIntegrations },
  { to: '/activity', label: 'Activity', icon: IconActivity },
  { to: '/settings', label: 'Settings', icon: IconSettings },
]

function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <img
        src="/jarvis-logo.png"
        alt="JARVIS"
        width={32}
        height={32}
        className="h-8 w-8 rounded-lg object-contain"
      />
      <div className="leading-tight">
        <p className="text-sm font-semibold tracking-[0.18em] text-slate-100">JARVIS</p>
        <p className="text-[10px] uppercase tracking-wider text-slate-500">
          AI Development Platform
        </p>
      </div>
    </div>
  )
}

export default function Layout() {
  const health = useQuery(() => api.health(), [], { pollMs: 20000 })
  const { connected, error: streamError } = useActivityStream()

  const online = health.data?.status === 'ok'

  return (
    <div className="flex h-full bg-navy-950">
      <aside className="flex w-64 shrink-0 flex-col border-r border-white/[0.07] bg-navy-900/60">
        <div className="px-4 py-4">
          <Logo />
        </div>

        <nav className="flex-1 space-y-0.5 px-2.5 pb-4 scroll-area">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => `nav-item ${isActive ? 'nav-item-active' : ''}`}
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span className="truncate">{label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-white/[0.07] px-4 py-3.5">
          <div className="flex items-center justify-between">
            <span className="text-[11px] uppercase tracking-wide text-slate-500">Backend</span>
            <span className="flex items-center gap-1.5 text-[11px] text-slate-400">
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  online ? 'bg-emerald-400' : health.loading ? 'bg-slate-500' : 'bg-red-400'
                }`}
              />
              {online ? 'online' : health.loading ? 'checking' : 'offline'}
            </span>
          </div>
          <div className="mt-1.5 flex items-center justify-between">
            <span className="text-[11px] uppercase tracking-wide text-slate-500">Live events</span>
            <span className="flex items-center gap-1.5 text-[11px] text-slate-400">
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  connected ? 'animate-pulse-soft bg-accent' : 'bg-slate-600'
                }`}
              />
              {connected ? 'streaming' : 'disconnected'}
            </span>
          </div>
          {health.data && (
            <p className="mt-2 truncate text-[10px] text-slate-600" title={health.data.database}>
              {health.data.database}
            </p>
          )}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-white/[0.07] px-6">
          <div className="flex items-center gap-3">
            <StatusBadge
              status={online ? 'connected' : 'failed'}
              label={online ? 'System operational' : 'Backend unreachable'}
            />
            {health.data && (
              <span className="text-[11px] text-slate-500">
                v{health.data.version} · {health.data.environment}
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 text-[11px] text-slate-500">
            {health.data && (
              <span>
                {health.data.websocket_subscribers} stream subscriber
                {health.data.websocket_subscribers === 1 ? '' : 's'}
              </span>
            )}
            <span>
              checked {formatRelative(health.data ? new Date().toISOString() : null)}
            </span>
          </div>
        </header>

        {(health.error || streamError) && (
          <div className="border-b border-red-500/20 bg-red-500/[0.06] px-6 py-2 text-[12px] text-red-200">
            {health.error ?? streamError}
          </div>
        )}

        <main className="min-h-0 flex-1 scroll-area">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
