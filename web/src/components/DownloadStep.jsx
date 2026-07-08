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
 * Filesystem-safe STL filename from the page's own text: strip nikud marks,
 * first 3 words, keep letters/digits/_/- (Hebrew is valid in filenames),
 * append page number for uniqueness. Empty text -> page_N.stl.
 */
function pageFilename(text, pageNo) {
  const slug = (text || '')
    .replace(/[֑-ׇ]/g, '') // nikud + cantillation combining marks
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 3)
    .join('_')
    .replace(/[^\p{L}\p{N}_-]+/gu, '')
    .slice(0, 40)
  return slug ? `${slug}_${pageNo}.stl` : `page_${pageNo}.stl`
}

/**
 * Step 4 — preview each finished page in 3D and download its printable STL.
 */
export default function DownloadStep({ book, results, onRestart }) {
  const { t } = useLang()

  return (
    <section className="mx-auto max-w-4xl px-6 py-10">
      <StepHeading className="text-ink mb-2 text-3xl font-bold">{t.download.title}</StepHeading>
      <p className="text-muted mb-8 text-lg">{t.download.sub}</p>

      <div className="space-y-6">
        {book.pages.map((p, i) => {
          const res = results[p.id]
          if (!res?.stlUrl) return null
          return (
            <Card key={p.id} className="p-4">
              <StlViewer url={res.stlUrl} className="h-80 w-full sm:h-96" />
              <div className="mt-4 flex flex-col items-center gap-4 text-center sm:flex-row sm:justify-between sm:text-start">
                <div>
                  <p className="text-muted mb-1 text-sm">
                    {t.generate.page} {i + 1} {t.common.of} {book.pages.length}
                  </p>
                  <p className="text-ink font-semibold">{p.text}</p>
                </div>
                <button
                  onClick={() => downloadStl(res.stlUrl, pageFilename(p.text, i + 1))}
                  className="rounded-btn bg-brand shadow-soft hover:bg-brand-dark inline-flex shrink-0 items-center justify-center gap-2 px-6 py-3 font-semibold text-white transition"
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
