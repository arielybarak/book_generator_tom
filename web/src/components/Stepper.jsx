import { useLang } from '../lib/i18n'

/**
 * Compact 4-step progress indicator. RTL-aware (flows right→left naturally).
 * Already-completed steps are clickable (via onStepClick) so users can go back
 * and edit; the current and future steps stay inert.
 */
export function Stepper({ current, onStepClick }) {
  const { t } = useLang()
  return (
    <nav aria-label={t.common.progress} className="flex items-center justify-center gap-1 sm:gap-3">
      {t.steps.map((label, i) => {
        const done = i < current
        const active = i === current
        const clickable = done && typeof onStepClick === 'function'
        const Inner = clickable ? 'button' : 'div'
        return (
          <div key={label} className="flex items-center gap-1 sm:gap-2">
            <Inner
              {...(clickable
                ? {
                    type: 'button',
                    onClick: () => onStepClick(i),
                    'aria-label': `${t.common.back}: ${label}`,
                  }
                : { 'aria-label': label, 'aria-current': active ? 'step' : undefined })}
              className={`flex items-center gap-1 sm:gap-2 ${clickable ? 'cursor-pointer rounded-full' : ''}`}
            >
              <span
                aria-hidden="true"
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
                aria-hidden="true"
                className={`hidden text-sm font-medium sm:inline ${
                  active ? 'text-ink' : 'text-muted'
                }`}
              >
                {label}
              </span>
            </Inner>
            {i < t.steps.length - 1 && (
              <span className="bg-line hidden h-px w-4 sm:inline-block sm:w-8" />
            )}
          </div>
        )
      })}
    </nav>
  )
}
