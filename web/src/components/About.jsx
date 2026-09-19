import { Button } from './ui/Button'
import { Card } from './ui/Card'
import { StepHeading } from './StepHeading'
import { useLang } from '../lib/i18n'

/** The three people who built TOM. Language-neutral, so it lives outside copy.js. */
const TEAM = [
  {
    name: 'Barak Ariely',
    email: 'barakari07@gmail.com',
    linkedin: 'https://www.linkedin.com/in/barak-ariely/',
  },
  {
    name: 'Danna Weinzinger',
    email: 'dusha98@yahoo.com',
    linkedin: 'https://www.linkedin.com/in/danna-weinzinger-5800aa265/',
  },
  {
    name: 'Noga Yaakov',
    email: 'nogayaakov03@gmail.com',
    linkedin: 'https://linkedin.com/in/noga-yaakov-b3270b294',
  },
]

function MailIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      className="h-4 w-4"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="m3 7 9 6 9-6" />
    </svg>
  )
}

function LinkedInIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="h-4 w-4" fill="currentColor">
      <path d="M20.45 20.45h-3.56v-5.57c0-1.33-.02-3.04-1.85-3.04-1.85 0-2.14 1.45-2.14 2.94v5.67H9.35V9h3.41v1.56h.05c.48-.9 1.64-1.85 3.37-1.85 3.6 0 4.27 2.37 4.27 5.46v6.28zM5.34 7.43a2.06 2.06 0 1 1 0-4.13 2.06 2.06 0 0 1 0 4.13zM7.12 20.45H3.56V9h3.56v11.45zM22.22 0H1.77C.79 0 0 .77 0 1.73v20.54C0 23.22.79 24 1.77 24h20.45c.98 0 1.78-.78 1.78-1.73V1.73C24 .77 23.2 0 22.22 0z" />
    </svg>
  )
}

/** Full About view — swapped in for the step flow via App's `view` state. */
export function About({ onBack }) {
  const { t } = useLang()
  return (
    <section className="mx-auto max-w-3xl px-6 py-10">
      <img src="/tom-logo-full.png" alt={t.about.logoAlt} className="mx-auto mb-8 h-24 w-auto" />
      <StepHeading className="text-ink mb-8 text-center text-3xl font-bold">
        {t.about.title}
      </StepHeading>

      <Card className="mb-6 p-6">
        <h2 className="text-ink mb-2 text-xl font-bold">{t.about.missionTitle}</h2>
        <p className="text-muted">{t.about.missionBody}</p>
      </Card>
      <Card className="mb-8 p-6">
        <h2 className="text-ink mb-2 text-xl font-bold">{t.about.eliyaTitle}</h2>
        <p className="text-muted">{t.about.eliyaBody}</p>
      </Card>

      <div className="mb-8">
        <h2 className="text-muted mb-4 text-center text-sm font-semibold tracking-wide">
          {t.about.teamTitle}
        </h2>
        <ul className="flex flex-wrap items-start justify-center gap-x-10 gap-y-4">
          {TEAM.map((person) => (
            <li key={person.email} className="flex flex-col items-center gap-1.5">
              <span className="text-ink text-sm font-medium">{person.name}</span>
              <span className="text-muted flex items-center gap-3">
                <a
                  href={`mailto:${person.email}`}
                  aria-label={`${t.about.emailLabel}: ${person.name}`}
                  className="hover:text-accent-text transition"
                >
                  <MailIcon />
                </a>
                <a
                  href={person.linkedin}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label={`LinkedIn: ${person.name}`}
                  className="hover:text-accent-text transition"
                >
                  <LinkedInIcon />
                </a>
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div className="flex flex-col items-center gap-4">
        <a
          href="https://tomglobal.org"
          target="_blank"
          rel="noopener noreferrer"
          className="text-accent-text font-semibold hover:underline"
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
