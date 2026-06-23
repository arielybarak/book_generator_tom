import { Button } from './ui/Button'
import { Card } from './ui/Card'
import { StlViewer } from './StlViewer'
import { StepHeading } from './StepHeading'
import { useLang } from '../lib/i18n'

async function downloadStl(url, filename) {
  try {
    const res = await fetch(url)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const blob = await res.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = filename
    a.click()
    URL.revokeObjectURL(a.href)
  } catch {
    // Cross-origin/CORS or network failure — open the file directly as a fallback.
    window.open(url, '_blank', 'noopener')
  }
}

/**
 * Step 4 — preview each finished page in 3D and download its printable STL.
 */
export default function DownloadStep({ book, results, onRestart }) {
  const { t } = useLang()
  const safeTitle = (book.title || 'page').replace(/\s+/g, '_')

  return (
    <section className="mx-auto max-w-4xl px-6 py-10">
      <StepHeading className="text-ink mb-2 text-3xl font-bold">{t.download.title}</StepHeading>
      <p className="text-muted mb-8 text-lg">{t.download.sub}</p>

      <div className="space-y-6">
        {book.pages.map((p, i) => {
          const res = results[p.id]
          if (!res?.stlUrl) return null
          return (
            <Card key={p.id} className="grid gap-4 p-4 sm:grid-cols-[1fr_auto] sm:items-center">
              <StlViewer url={res.stlUrl} className="h-64 w-full" />
              <div className="text-center sm:px-6 sm:text-start">
                <p className="text-muted mb-1 text-sm">
                  {t.generate.page} {i + 1} {t.common.of} {book.pages.length}
                </p>
                <p className="text-ink mb-4 font-semibold">{p.text}</p>
                <button
                  onClick={() => downloadStl(res.stlUrl, `${safeTitle}_${i + 1}.stl`)}
                  className="rounded-btn bg-brand shadow-soft hover:bg-brand-dark inline-flex items-center justify-center gap-2 px-6 py-3 font-semibold text-white transition"
                >
                  <span aria-hidden="true">⬇</span> {t.download.download}
                </button>
              </div>
            </Card>
          )
        })}
      </div>

      {/* Print guidance */}
      <Card className="bg-accent-soft mt-8 p-6">
        <h2 className="text-ink mb-2 text-lg font-bold">{t.download.printTitle}</h2>
        <p className="text-muted">{t.download.printBody}</p>
      </Card>

      <div className="mt-8 flex justify-center">
        <Button size="lg" variant="ghost" onClick={onRestart}>
          <span aria-hidden="true">＋</span> {t.download.startOver}
        </Button>
      </div>
    </section>
  )
}
