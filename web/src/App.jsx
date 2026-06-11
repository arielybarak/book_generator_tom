import { lazy, Suspense, useState } from 'react'
import { Stepper } from './components/Stepper'
import { Landing } from './components/Landing'
import { BookBuilder } from './components/BookBuilder'
import { GenerateStep } from './components/GenerateStep'
import { COPY } from './lib/copy'

// three.js is ~700 kB — only load it when the user reaches the download step.
const DownloadStep = lazy(() => import('./components/DownloadStep'))

function Header({ step }) {
  return (
    <header className="border-line bg-paper/80 sticky top-0 z-10 border-b backdrop-blur">
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-6 py-4">
        <div className="flex items-center gap-2">
          <span className="bg-brand flex h-9 w-9 items-center justify-center rounded-2xl text-lg font-bold text-white">
            ✦
          </span>
          <span className="text-ink text-xl font-bold">{COPY.appName}</span>
        </div>
        <Stepper current={step} />
      </div>
    </header>
  )
}

export default function App() {
  const [step, setStep] = useState(0)
  const [book, setBook] = useState({ title: '', pages: [] })
  const [results, setResults] = useState({}) // pageId -> { imageUrl, stlUrl }

  function restart() {
    setBook({ title: '', pages: [] })
    setResults({})
    setStep(0)
  }

  return (
    <div className="flex min-h-dvh flex-col">
      <Header step={step} />
      <main className="flex-1" aria-label="תוכן ראשי">
        {step === 0 && <Landing onStart={() => setStep(1)} />}
        {step === 1 && <BookBuilder book={book} setBook={setBook} onGenerate={() => setStep(2)} />}
        {step === 2 && (
          <GenerateStep
            book={book}
            results={results}
            setResults={setResults}
            onNext={() => setStep(3)}
          />
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
      </main>
    </div>
  )
}
