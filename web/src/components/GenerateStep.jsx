import { useEffect, useRef, useState } from 'react'
import { Button } from './ui/Button'
import { Card } from './ui/Card'
import { StepHeading } from './StepHeading'
import { generatePage } from '../api/hfClient'
import { COPY } from '../lib/copy'

/**
 * Step 3 — generate each page on the backend (sequentially, to be gentle on the
 * shared GPU), show the illustration as it lands, and allow per-page regenerate.
 */
export function GenerateStep({ book, results, setResults, onNext, onBack }) {
  const startedRef = useRef(false)
  const [status, setStatus] = useState({}) // pageId -> 'working' | 'queued' | 'error'
  const [timers, setTimers] = useState({}) // pageId -> { start, end }
  const [now, setNow] = useState(Date.now())

  // Tick once a second while any page is still generating, so the elapsed timer counts up.
  useEffect(() => {
    const running = Object.values(timers).some((t) => t && !t.end)
    if (!running) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [timers])

  async function generateOne(page) {
    setStatus((s) => ({ ...s, [page.id]: 'working' }))
    setTimers((t) => ({ ...t, [page.id]: { start: Date.now(), end: null } }))
    try {
      const res = await generatePage(
        {
          text: page.text,
          variations: page.variations,
          imageDesc: page.picture,
          objectClass: page.picture,
          language: book.language || 'hebrew',
        },
        (msg) => {
          // queue=true means the Space is still waking or other jobs are ahead
          const waking = msg?.stage === 'waking'
          const queued = !waking && (msg?.queue === true || (msg?.position ?? 0) > 0)
          setStatus((s) => ({ ...s, [page.id]: waking ? 'waking' : queued ? 'queued' : 'working' }))
        },
      )
      setResults((r) => ({ ...r, [page.id]: res }))
      setStatus((s) => {
        const rest = { ...s }
        delete rest[page.id]
        return rest
      })
    } catch (e) {
      console.error('generate failed', e)
      setStatus((s) => ({ ...s, [page.id]: 'error' }))
    } finally {
      setTimers((t) => (t[page.id] ? { ...t, [page.id]: { ...t[page.id], end: Date.now() } } : t))
    }
  }

  useEffect(() => {
    if (startedRef.current) return
    startedRef.current = true
    ;(async () => {
      for (const page of book.pages) {
        if (!results[page.id]) await generateOne(page)
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // A page only counts as done when its printable STL is present, not just the image.
  const allDone = book.pages.every((p) => results[p.id]?.stlUrl)

  // One concise line for screen readers, announced via the aria-live region below.
  const total = book.pages.length
  const activeIdx = book.pages.findIndex((p) =>
    ['working', 'waking', 'queued'].includes(status[p.id]),
  )
  const errored = book.pages.some((p) => status[p.id] === 'error')
  const liveStatus = allDone
    ? COPY.generate.allReady
    : activeIdx >= 0
      ? `מציירים עמוד ${activeIdx + 1} מתוך ${total}`
      : errored
        ? COPY.generate.failed
        : ''

  return (
    <section className="mx-auto max-w-4xl px-6 py-10">
      <StepHeading className="text-ink mb-6 text-3xl font-bold">
        {book.title || COPY.appName}
      </StepHeading>
      <p className="sr-only" role="status" aria-live="polite">
        {liveStatus}
      </p>

      <div className="grid gap-5 sm:grid-cols-2">
        {book.pages.map((p, i) => {
          const res = results[p.id]
          const st = status[p.id]
          return (
            <Card key={p.id} className="overflow-hidden">
              <div className="border-line flex items-center gap-3 border-b p-4">
                <span className="bg-brand-soft text-brand-dark flex h-8 w-8 items-center justify-center rounded-full font-bold">
                  {i + 1}
                </span>
                <p className="text-ink truncate font-semibold">{p.text}</p>
                {timers[p.id] && (
                  <span
                    className="text-muted ms-auto shrink-0 font-mono text-sm tabular-nums"
                    title="זמן היצירה"
                  >
                    ⏱ {fmtElapsed(timers[p.id], now)}
                  </span>
                )}
              </div>

              <div className="bg-paper flex aspect-square items-center justify-center p-4">
                {res?.imageUrl ? (
                  <img
                    src={res.imageUrl}
                    alt={`ציור לעמוד ${i + 1}: ${p.picture || p.text}`}
                    className="max-h-full max-w-full object-contain"
                  />
                ) : st === 'error' ? (
                  <p className="text-muted px-4 text-center">{COPY.generate.failed}</p>
                ) : (
                  <div className="text-center">
                    <Spinner />
                    <p className="text-muted mt-3 text-sm">
                      {st === 'waking' ? COPY.generate.waking : st === 'queued' ? COPY.generate.waking : COPY.generate.working}
                    </p>
                  </div>
                )}
              </div>

              {(res || st === 'error') && (
                <div className="border-line border-t p-3 text-center">
                  {res?.imageUrl && !res?.stlUrl && (
                    <p className="text-muted mb-2 text-sm">{COPY.generate.noStl}</p>
                  )}
                  <Button size="sm" variant="ghost" onClick={() => generateOne(p)}>
                    <span aria-hidden="true">↻</span>{' '}
                    {st === 'error' || (res && !res.stlUrl)
                      ? COPY.generate.retry
                      : COPY.generate.regenerate}
                  </Button>
                </div>
              )}
            </Card>
          )
        })}
      </div>

      <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
        <Button size="lg" variant="ghost" onClick={onBack}>
          <span aria-hidden="true">→</span> {COPY.generate.backToEdit}
        </Button>
        <Button size="lg" onClick={onNext} disabled={!allDone}>
          {COPY.generate.next} <span aria-hidden="true">←</span>
        </Button>
      </div>
    </section>
  )
}

function fmtElapsed(timer, now) {
  if (!timer) return null
  const s = Math.max(0, Math.floor(((timer.end || now) - timer.start) / 1000))
  return s >= 60 ? `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}` : `${s} ש׳`
}

function Spinner() {
  return (
    <span
      className="border-brand-soft border-t-brand inline-block h-8 w-8 animate-spin rounded-full border-4"
      aria-hidden="true"
    />
  )
}
