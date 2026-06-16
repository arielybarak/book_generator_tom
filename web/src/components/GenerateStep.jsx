import { useEffect, useRef, useState } from 'react'
import { Button } from './ui/Button'
import { Card } from './ui/Card'
import { generatePage } from '../api/hfClient'
import { COPY } from '../lib/copy'

/**
 * Step 3 — generate each page on the backend (sequentially, to be gentle on the
 * shared GPU), show the illustration as it lands, and allow per-page regenerate.
 */
export function GenerateStep({ book, results, setResults, onNext }) {
  const startedRef = useRef(false)
  const [status, setStatus] = useState({}) // pageId -> 'working' | 'queued' | 'error'

  async function generateOne(page) {
    setStatus((s) => ({ ...s, [page.id]: 'working' }))
    try {
      const res = await generatePage(
        {
          text: page.text,
          variations: page.variations,
          imageDesc: page.picture,
          objectClass: page.picture,
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

  const allDone = book.pages.every((p) => results[p.id])

  return (
    <section className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-ink mb-6 text-3xl font-bold">{book.title || COPY.appName}</h1>

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
                  <Button size="sm" variant="ghost" onClick={() => generateOne(p)}>
                    <span aria-hidden="true">↻</span>{' '}
                    {st === 'error' ? COPY.generate.retry : COPY.generate.regenerate}
                  </Button>
                </div>
              )}
            </Card>
          )
        })}
      </div>

      <div className="mt-8 flex justify-center">
        <Button size="lg" onClick={onNext} disabled={!allDone}>
          {COPY.generate.next} <span aria-hidden="true">←</span>
        </Button>
      </div>
    </section>
  )
}

function Spinner() {
  return (
    <span
      className="border-brand-soft border-t-brand inline-block h-8 w-8 animate-spin rounded-full border-4"
      aria-hidden="true"
    />
  )
}
