import {
  CONNECTOR_FILTER_OPTIONS,
  type ProviderSourceFilter,
  type ProviderSourceType,
  formatSourceTypeBadge,
} from '../types'

interface ConnectorFilterBarProps {
  activeFilter: ProviderSourceFilter
  counts: Record<ProviderSourceFilter, number>
  onSelectFilter: (filter: ProviderSourceFilter) => void
  ariaLabel?: string
}

export function ConnectorFilterBar({
  activeFilter,
  counts,
  onSelectFilter,
  ariaLabel = 'Filter by connector',
}: ConnectorFilterBarProps) {
  return (
    <div role="group" aria-label={ariaLabel} className="flex flex-wrap items-center gap-2">
      {CONNECTOR_FILTER_OPTIONS.map((option) => {
        const isActive = activeFilter === option.id
        const count = counts[option.id] ?? 0
        return (
          <button
            key={option.id}
            type="button"
            aria-pressed={isActive}
            onClick={() => onSelectFilter(option.id)}
            className={`inline-flex items-center gap-2 rounded-xl border px-3 py-1.5 text-xs font-semibold transition tabular-nums ${
              isActive
                ? 'border-blue-600 bg-blue-600 text-white shadow-xs dark:border-blue-500 dark:bg-blue-500'
                : 'border-zinc-200 bg-zinc-50 text-zinc-700 hover:border-zinc-300 hover:bg-white dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300 dark:hover:border-zinc-700'
            }`}
          >
            <span>{option.label}</span>
            <span
              className={`rounded-md px-1.5 py-0.5 font-mono text-[11px] tabular-nums ${
                isActive
                  ? 'bg-blue-700/80 text-white dark:bg-blue-600'
                  : 'bg-zinc-200/80 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400'
              }`}
            >
              {count}
            </span>
          </button>
        )
      })}
    </div>
  )
}

export function ConnectorBadge({ sourceType }: { sourceType: ProviderSourceType }) {
  const badgeStyles: Record<ProviderSourceType, string> = {
    sdmx: 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800/60',
    central_bank:
      'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-800/60',
    financial:
      'bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-950/60 dark:text-sky-300 dark:border-sky-800/60',
    dbnomics:
      'bg-zinc-100 text-zinc-600 border-zinc-200 dark:bg-zinc-800/80 dark:text-zinc-300 dark:border-zinc-700',
  }

  return (
    <span
      className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-semibold tracking-wide uppercase ${badgeStyles[sourceType]}`}
    >
      {formatSourceTypeBadge(sourceType)}
    </span>
  )
}
