import { Button } from './ui/Button'
import { Card } from './ui/Card'
import { StepHeading } from './StepHeading'
import { useLang } from '../lib/i18n'

/** Full About view — swapped in for the step flow via App's `view` state. */
export function About({ onBack }) {
  const { t } = useLang()
  return (
    <section className="mx-auto max-w-3xl px-6 py-10">
      <img src="/tom-logo-full.png" alt={t.about.logoAlt} className="mx-auto mb-8 h-24 w-auto" />
      <StepHeading className="text-ink mb-4 text-center text-3xl font-bold">
        {t.about.title}
      </StepHeading>
      <p className="text-muted mb-8 text-center text-lg">{t.about.intro}</p>

      <Card className="mb-6 p-6">
        <h2 className="text-ink mb-2 text-xl font-bold">{t.about.missionTitle}</h2>
        <p className="text-muted">{t.about.missionBody}</p>
      </Card>
      <Card className="mb-8 p-6">
        <h2 className="text-ink mb-2 text-xl font-bold">{t.about.eliyaTitle}</h2>
        <p className="text-muted">{t.about.eliyaBody}</p>
      </Card>

      <div className="flex flex-col items-center gap-4">
        <a
          href="https://tomglobal.org"
          target="_blank"
          rel="noopener noreferrer"
          className="text-accent font-semibold hover:underline"
        >
          {t.about.linkCta}
        </a>
        <Button size="lg" variant="ghost" onClick={onBack}>
          {t.about.back}
        </Button>
      </div>
    </section>
  )
}
