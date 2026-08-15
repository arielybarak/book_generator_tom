import { useEffect, useRef, useState } from 'react'
import { Button } from './ui/Button'
import { Card } from './ui/Card'
import { StepHeading } from './StepHeading'
import { generatePage } from '../api/hfClient'
import { useLang } from '../lib/i18n'
import {
  variantsOf,
  chosenVariant,
  selectedIndex,
  addVariant,
  selectVariant,
} from '../lib/pageResults'

/**
 * Step 3 — generate each page on the backend (sequentially, to be gentle on the
 * shared GPU), show the illustration as it lands, and allow per-page regenerate.
 */
export function GenerateStep({ book, results, setResults, onNext, onBack }) {
  const { t, lang } = useLang()
  const startedRef = useRef(false)
  const [status, setStatus] = useState({}) // pageId -> 'working' | 'queued' | 'error'
  const [timers, setTimers] = useState({}) // pageId -> { start, end }
  const [now, setNow] = useState(() => Date.now())

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
          language: lang,
        },
        (msg) => {
          // queue=true means the Space is still waking or other jobs are ahead
          const waking = msg?.stage === 'waking'
          const queued = !waking && (msg?.queue === true || (msg?.position ?? 0) > 0)
          setStatus((s) => ({ ...s, [page.id]: waking ? 'waking' : queued ? 'queued' : 'working' }))
        },
      )
      // Keep every attempt as a variant so a worse redraw can't destroy a good one;
      // auto-select the freshest drawing (the user can switch back in the catalog).
      setResults((r) => ({ ...r, [page.id]: addVariant(r[page.id], res) }))
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

  // Pick which saved drawing this page should use (its STL is what gets downloaded).
  function selectVariantFor(pageId, index) {
    setResults((r) => ({ ...r, [pageId]: selectVariant(r[pageId], index) }))
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

  // A page only counts as done when the chosen variant's printable STL is present.
  const allDone = book.pages.every((p) => chosenVariant(results[p.id])?.stlUrl)

  // One concise line for screen readers, announced via the aria-live region below.
  const total = book.pages.length
  const activeIdx = book.pages.findIndex((p) =>
    ['working', 'waking', 'queued'].includes(status[p.id]),
  )
  const errored = book.pages.some((p) => status[p.id] === 'error')
  const liveStatus = allDone
    ? t.generate.allReady
    : activeIdx >= 0
      ? `${t.generate.page} ${activeIdx + 1} ${t.common.of} ${total}`
      : errored
        ? t.generate.failed
        : ''

  return (
    <section className="mx-auto max-w-4xl px-6 py-10">
      <StepHeading className="text-ink mb-6 text-3xl font-bold">
        {book.title || t.appName}
      </StepHeading>
      <p className="sr-only" role="status" aria-live="polite">
        {liveStatus}
      </p>

      <div className="grid gap-5 sm:grid-cols-2">
        {book.pages.map((p, i) => {
          const res = results[p.id]
          const variants = variantsOf(res)
          const chosen = chosenVariant(res)
          const sel = selectedIndex(res)
          const st = status[p.id]
          const busy = ['working', 'waking', 'queued'].includes(st)
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
                    title={t.generate.elapsed}
                  >
                    <span aria-hidden="true">⏱</span> {fmtElapsed(timers[p.id], now, t.common.sec)}
                  </span>
                )}
              </div>

              <div className="bg-paper relative flex aspect-square items-center justify-center p-4">
                {chosen?.imageUrl ? (
                  <img
                    src={chosen.imageUrl}
                    alt={`${t.generate.page} ${i + 1}: ${p.picture || p.text}`}
                    className="max-h-full max-w-full object-contain"
                  />
                ) : st === 'error' ? (
                  <p className="text-muted px-4 text-center">{t.generate.failed}</p>
                ) : (
                  <div className="text-center">
                    <Spinner />
                    <p className="text-muted mt-3 text-sm">
                      {st === 'waking' || st === 'queued' ? t.generate.waking : t.generate.working}
                    </p>
                  </div>
                )}
                {/* Redrawing while an earlier drawing is still on screen — badge the wait. */}
                {busy && chosen?.imageUrl && (
                  <span className="bg-surface/85 text-muted absolute end-2 top-2 inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs shadow-sm">
                    <Spinner sm /> {t.generate.working}
                  </span>
                )}
              </div>

              {/* Catalog of saved drawings — every redraw is kept; pick your favourite. */}
              {variants.length > 1 && (
                <div className="border-line border-t p-3">
                  <p className="text-muted mb-2 text-center text-xs">{t.generate.chooseDrawing}</p>
                  <ul className="flex flex-wrap justify-center gap-2">
                    {variants.map((v, vi) => {
                      const isSel = vi === sel
                      return (
                        <li key={vi}>
                          <button
                            type="button"
                            onClick={() => selectVariantFor(p.id, vi)}
                            aria-pressed={isSel}
                            aria-label={`${t.generate.option} ${vi + 1}${isSel ? ` — ${t.generate.selected}` : ''}`}
                            className={`relative block h-16 w-16 overflow-hidden rounded-xl border-2 transition ${
                              isSel
                                ? 'border-brand ring-brand/30 ring-2'
                                : 'border-line hover:border-brand-soft'
                            }`}
                          >
                            {v.imageUrl ? (
                              <img src={v.imageUrl} alt="" className="h-full w-full object-cover" />
                            ) : (
                              <span className="text-muted flex h-full w-full items-center justify-center text-xs">
                                {vi + 1}
                              </span>
                            )}
                            {isSel && (
                              <span
                                aria-hidden="true"
                                className="bg-brand absolute end-0.5 top-0.5 flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-bold text-white"
                              >
                                ✓
                              </span>
                            )}
                            {!v.stlUrl && (
                              <span
                                aria-hidden="true"
                                title={t.generate.noStl}
                                className="absolute inset-x-0 bottom-0 bg-amber-400/90 text-center text-[10px] font-bold text-black"
                              >
                                !
                              </span>
                            )}
                          </button>
                        </li>
                      )
                    })}
                  </ul>
                </div>
              )}

              {(chosen || st === 'error') && (
                <div className="border-line border-t p-3 text-center">
                  {chosen?.imageUrl && !chosen?.stlUrl && (
                    <p className="text-muted mb-2 text-sm">{t.generate.noStl}</p>
                  )}
                  <Button size="sm" variant="ghost" onClick={() => generateOne(p)} disabled={busy}>
                    <span aria-hidden="true">↻</span>{' '}
                    {st === 'error' || (chosen && !chosen.stlUrl)
                      ? t.generate.retry
                      : t.generate.regenerate}
                  </Button>
                </div>
              )}
            </Card>
          )
        })}
      </div>

      <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
        <Button size="lg" variant="ghost" onClick={onBack}>
          <span aria-hidden="true">{t.common.arrowPrev}</span> {t.common.back}
        </Button>
        <Button size="lg" onClick={onNext} disabled={!allDone}>
          {t.generate.next} <span aria-hidden="true">{t.common.arrowNext}</span>
        </Button>
      </div>
    </section>
  )
}

function fmtElapsed(timer, now, sec = 's') {
  if (!timer) return null
  const s = Math.max(0, Math.floor(((timer.end || now) - timer.start) / 1000))
  return s >= 60 ? `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}` : `${s} ${sec}`
}

function Spinner({ sm = false }) {
  return (
    <span
      className={`border-brand-soft border-t-brand inline-block animate-spin rounded-full ${
        sm ? 'h-3.5 w-3.5 border-2' : 'h-8 w-8 border-4'
      }`}
      aria-hidden="true"
    />
  )
}
