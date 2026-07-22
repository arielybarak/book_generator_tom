import { lazy, Suspense, useEffect, useState } from 'react'
import { MotionConfig } from 'framer-motion'
import { Stepper } from './components/Stepper'
import { Landing } from './components/Landing'
import { BookBuilder } from './components/BookBuilder'
import { GenerateStep } from './components/GenerateStep'
import { AuthScreen } from './components/AuthScreen'
import { About } from './components/About'
import { useLang } from './lib/i18n'
import { useAuth } from './lib/auth'

// three.js is ~700 kB — only load it when the user reaches the download step.
const DownloadStep = lazy(() => import('./components/DownloadStep'))

// Persist the whole session so a refresh doesn't wipe the book or generated pages.
// NOTE: HF file URLs in `results` can expire if the Space restarts — a missing
// image then falls back to the regenerate path in GenerateStep.
const STORAGE_KEY = 'tom.v1'

function loadState() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || null
  } catch {
    return null
  }
}

function LanguageSwitcher() {
  const { lang, setLang, t } = useLang()
  return (
    <div
      role="group"
      aria-label={t.common.language}
      className="border-line bg-surface flex shrink-0 items-center gap-0.5 rounded-full border p-0.5 text-xs"
    >
      {[
        ['hebrew', 'עב'],
        ['english', 'EN'],
      ].map(([val, label]) => (
        <button
          key={val}
          type="button"
          onClick={() => setLang(val)}
          aria-pressed={lang === val}
          className={`rounded-full px-2.5 py-0.5 font-bold transition ${
            lang === val ? 'bg-brand text-white' : 'text-muted hover:text-ink'
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  )
}

function Header({ step, onStepClick, view, onToggleAbout }) {
  const { t } = useLang()
  const { session, signOut } = useAuth()
  const username = session?.user?.email?.split('@')[0] ?? null
  return (
    <header className="border-line bg-paper/80 sticky top-0 z-10 border-b backdrop-blur">
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-6 py-4">
        <div className="flex items-center gap-2">
          <img src="/tom-logo.png" alt="" className="h-9 w-auto" />
          <span className="text-ink text-xl font-bold">{t.appName}</span>
        </div>
        <div className="flex items-center gap-3">
          <Stepper current={step} onStepClick={onStepClick} />
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onToggleAbout}
              aria-current={view === 'about' ? 'page' : undefined}
              className={`text-xs font-semibold transition ${
                view === 'about' ? 'text-ink underline' : 'text-muted hover:text-ink'
              }`}
            >
              {t.about.navLabel}
            </button>
            <LanguageSwitcher />
            {session && (
              <div className="flex items-center gap-1.5">
                {username && (
                  <span className="text-muted hidden text-xs sm:inline">{username}</span>
                )}
                <button
                  type="button"
                  onClick={signOut}
                  className="text-muted hover:text-ink text-xs font-semibold transition"
                >
                  {t.auth.logout}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  )
}

function Footer() {
  const { t } = useLang()
  return (
    <footer className="border-line mt-12 border-t">
      <div className="text-muted mx-auto flex max-w-5xl items-center justify-center gap-3 px-6 py-6 text-sm">
        <img src="/tom-logo.png" alt="" className="h-6 w-auto" />
        <span>
          {t.footer.projectOf}{' '}
          <a
            href="https://tomglobal.org"
            target="_blank"
            rel="noopener noreferrer"
            className="text-accent font-semibold hover:underline"
          >
            TOM — Tikkun Olam Makers
          </a>
        </span>
      </div>
    </footer>
  )
}

export default function App() {
  const { session, loading: authLoading } = useAuth()
  const saved = loadState()
  const [step, setStep] = useState(saved?.step ?? 0)
  const [book, setBook] = useState(saved?.book ?? { title: '', pages: [] })
  const [results, setResults] = useState(saved?.results ?? {}) // pageId -> { imageUrl, stlUrl }
  // 'create' | 'about' — not persisted; a refresh always returns to the saved flow.
  const [view, setView] = useState('create')

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ step, book, results }))
    } catch {
      // ignore quota / private-mode write failures
    }
  }, [step, book, results])

  function restart() {
    try {
      localStorage.removeItem(STORAGE_KEY)
    } catch {
      // ignore
    }
    setBook({ title: '', pages: [] })
    setResults({})
    setStep(0)
  }

  // Navigate back to an already-completed step only (never forward past unvisited work).
  function goTo(target) {
    if (target < step) setStep(target)
  }

  return (
    <MotionConfig reducedMotion="user">
      <div className="flex min-h-dvh flex-col">
        <Header
          step={step}
          onStepClick={(n) => {
            setView('create')
            goTo(n)
          }}
          view={view}
          onToggleAbout={() => setView(view === 'about' ? 'create' : 'about')}
        />
        <main className="flex-1">
          {view === 'about' && <About onBack={() => setView('create')} />}
          <div hidden={view === 'about'}>
            {step === 0 && <Landing onStart={() => setStep(1)} />}
            {step === 1 && (
              <BookBuilder book={book} setBook={setBook} onGenerate={() => setStep(2)} />
            )}
            {step === 2 && (
              authLoading
                ? (
                  <div className="flex min-h-96 items-center justify-center">
                    <span
                      className="border-brand-soft border-t-brand inline-block h-10 w-10 animate-spin rounded-full border-4"
                      aria-label="…"
                    />
                  </div>
                )
                : session
                  ? (
                    <GenerateStep
                      book={book}
                      results={results}
                      setResults={setResults}
                      onNext={() => setStep(3)}
                      onBack={() => goTo(1)}
                    />
                  )
                  : <AuthScreen />
            )}
            {step === 3 && (
              <Suspense
                fallback={
                  <div className="flex min-h-96 items-center justify-center">
                    <span
                      className="border-brand-soft border-t-brand inline-block h-10 w-10 animate-spin rounded-full border-4"
                      aria-label="טוען…"
                    />
                  </div>
                }
              >
                <DownloadStep book={book} results={results} onRestart={restart} />
              </Suspense>
            )}
          </div>
        </main>
        <Footer />
      </div>
    </MotionConfig>
  )
}
