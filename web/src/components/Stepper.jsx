import { COPY } from '../lib/copy'

/** Compact 4-step progress indicator. RTL-aware (flows right→left naturally). */
export function Stepper({ current }) {
  return (
    <nav aria-label="התקדמות" className="flex items-center justify-center gap-1 sm:gap-3">
      {COPY.steps.map((label, i) => {
        const done = i < current
        const active = i === current
        return (
          <div key={label} className="flex items-center gap-1 sm:gap-2">
            <div className="flex items-center gap-1 sm:gap-2">
              <span
                aria-current={active ? 'step' : undefined}
                className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold transition sm:h-8 sm:w-8 sm:text-sm ${
                  done
                    ? 'bg-accent text-white'
                    : active
                      ? 'bg-brand text-white'
                      : 'bg-brand-soft text-muted'
                }`}
              >
                {done ? '✓' : i + 1}
              </span>
              <span
                className={`hidden text-sm font-medium sm:inline ${
                  active ? 'text-ink' : 'text-muted'
                }`}
              >
                {label}
              </span>
            </div>
            {i < COPY.steps.length - 1 && (
              <span className="bg-line hidden h-px w-4 sm:inline-block sm:w-8" />
            )}
          </div>
        )
      })}
    </nav>
  )
}
