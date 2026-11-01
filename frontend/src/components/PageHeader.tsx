import type { ReactNode } from 'react'

export default function PageHeader({
  title,
  description,
  actions,
}: {
  title: string
  description: string
  actions?: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4 border-b border-white/[0.07] px-6 py-5">
      <div className="min-w-0">
        <h1 className="text-lg font-semibold tracking-tight text-slate-100">{title}</h1>
        <p className="mt-1 max-w-3xl text-[13px] leading-relaxed text-slate-400">
          {description}
        </p>
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  )
}
