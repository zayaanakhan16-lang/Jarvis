/** Shared UI primitives. Presentational only, no data fetching. */

import type { ReactNode } from 'react'

// --- Status ---------------------------------------------------------------
const STATUS_STYLES: Record<string, string> = {
  idle: 'bg-slate-500/12 text-slate-400',
  queued: 'bg-violet-500/12 text-violet-300',
  pending: 'bg-slate-500/12 text-slate-400',
  running: 'bg-accent/15 text-accent-bright',
  starting: 'bg-accent/15 text-accent-bright',
  waiting_approval: 'bg-amber-500/12 text-amber-300',
  completed: 'bg-emerald-500/12 text-emerald-300',
  connected: 'bg-emerald-500/12 text-emerald-300',
  started: 'bg-emerald-500/12 text-emerald-300',
  configured: 'bg-sky-500/12 text-sky-300',
  active: 'bg-accent/15 text-accent-bright',
  planning: 'bg-violet-500/12 text-violet-300',
  failed: 'bg-red-500/12 text-red-300',
  error: 'bg-red-500/12 text-red-300',
  rejected: 'bg-red-500/12 text-red-300',
  cancelled: 'bg-slate-500/12 text-slate-500',
  skipped: 'bg-amber-500/12 text-amber-300',
  blocked: 'bg-red-500/12 text-red-300',
  not_configured: 'bg-slate-500/12 text-slate-500',
  unavailable: 'bg-slate-600/20 text-slate-500',
  archived: 'bg-slate-500/12 text-slate-500',
}

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const style = STATUS_STYLES[status] ?? 'bg-slate-500/12 text-slate-400'
  return (
    <span className={`badge ${style}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />
      {label ?? status.replace(/_/g, ' ')}
    </span>
  )
}

const LEVEL_STYLES: Record<string, string> = {
  info: 'text-slate-400',
  warning: 'text-amber-300',
  error: 'text-red-300',
}

export function LevelDot({ level }: { level: string }) {
  const colour =
    level === 'error' ? 'bg-red-400' : level === 'warning' ? 'bg-amber-400' : 'bg-accent'
  return <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${colour}`} aria-hidden />
}

export function levelClass(level: string): string {
  return LEVEL_STYLES[level] ?? 'text-slate-400'
}

// --- Layout ---------------------------------------------------------------
export function Panel({
  title,
  subtitle,
  actions,
  children,
  className = '',
  bodyClassName = 'p-5',
}: {
  title?: string
  subtitle?: string
  actions?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
}) {
  return (
    <section className={`panel ${className}`}>
      {(title || actions) && (
        <header className="panel-header">
          <div className="min-w-0">
            {title && <h2 className="panel-title">{title}</h2>}
            {subtitle && <p className="panel-subtitle mt-0.5">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={bodyClassName}>{children}</div>
    </section>
  )
}

export function StatCard({
  label,
  value,
  hint,
  tone = 'default',
}: {
  label: string
  value: ReactNode
  hint?: string
  tone?: 'default' | 'good' | 'warn' | 'bad'
}) {
  const toneClass = {
    default: 'text-slate-100',
    good: 'text-emerald-300',
    warn: 'text-amber-300',
    bad: 'text-red-300',
  }[tone]
  return (
    <div className="panel px-4 py-3.5">
      <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-1.5 text-2xl font-semibold tabular-nums ${toneClass}`}>{value}</p>
      {hint && <p className="mt-1 text-[11px] text-slate-500">{hint}</p>}
    </div>
  )
}

// --- Feedback -------------------------------------------------------------
export function Spinner({ className = '' }: { className?: string }) {
  return (
    <svg className={`h-4 w-4 animate-spin ${className}`} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-20" />
      <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}

export function LoadingState({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2.5 py-12 text-sm text-slate-500">
      <Spinner />
      {label}…
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
      <div className="rounded-full bg-red-500/10 p-2.5">
        <svg className="h-5 w-5 text-red-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="9" />
          <path d="M12 8v4M12 16h.01" strokeLinecap="round" />
        </svg>
      </div>
      <p className="max-w-md text-sm text-red-200">{message}</p>
      {onRetry && (
        <button type="button" className="btn-secondary" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string
  description: string
  action?: ReactNode
  icon?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
      {icon && <div className="rounded-full bg-white/[0.04] p-3 text-slate-500">{icon}</div>}
      <h3 className="text-sm font-medium text-slate-200">{title}</h3>
      <p className="max-w-md text-xs leading-relaxed text-slate-500">{description}</p>
      {action}
    </div>
  )
}

/** A value the system could not verify. Rendered plainly, never guessed. */
export function UnknownValue({ label = 'unknown' }: { label?: string }) {
  return (
    <span className="italic text-slate-500" title="Not verified by a source">
      {label}
    </span>
  )
}

export function Banner({
  tone = 'info',
  title,
  children,
  action,
}: {
  tone?: 'info' | 'warn' | 'error' | 'success'
  title?: string
  children: ReactNode
  action?: ReactNode
}) {
  const tones = {
    info: 'border-accent/25 bg-accent/[0.06] text-accent-bright',
    warn: 'border-amber-500/25 bg-amber-500/[0.06] text-amber-200',
    error: 'border-red-500/25 bg-red-500/[0.06] text-red-200',
    success: 'border-emerald-500/25 bg-emerald-500/[0.06] text-emerald-200',
  }
  return (
    <div className={`flex items-start justify-between gap-4 rounded-lg border px-4 py-3 text-sm ${tones[tone]}`}>
      <div className="min-w-0">
        {title && <p className="font-medium">{title}</p>}
        <div className="text-[13px] leading-relaxed opacity-90">{children}</div>
      </div>
      {action}
    </div>
  )
}

// --- Content --------------------------------------------------------------
export function Mono({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <code className={`mono text-slate-300 ${className}`}>{children}</code>
}

export function Chip({ children }: { children: ReactNode }) {
  return <span className="chip">{children}</span>
}

export function ProgressBar({ completed, total }: { completed: number; total: number }) {
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0
  return (
    <div className="flex items-center gap-2.5">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/[0.07]">
        <div
          className="h-full rounded-full bg-accent transition-[width] duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="shrink-0 tabular-nums text-[11px] text-slate-500">
        {completed}/{total}
      </span>
    </div>
  )
}

export function Field({
  label,
  value,
  mono = false,
}: {
  label: string
  value: ReactNode
  mono?: boolean
}) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className={`mt-0.5 break-words text-[13px] text-slate-300 ${mono ? 'mono' : ''}`}>
        {value}
      </dd>
    </div>
  )
}
