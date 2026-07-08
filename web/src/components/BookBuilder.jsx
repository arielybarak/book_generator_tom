import { AnimatePresence, motion } from 'framer-motion'
import { Button } from './ui/Button'
import { Card } from './ui/Card'
import { PageEditor } from './PageEditor'
import { StepHeading } from './StepHeading'
import { useLang } from '../lib/i18n'

/**
 * Step 2 — build the book: a title, an add-page form, and the list of pages.
 * Book state is lifted to App; this is a controlled view. The page language
 * follows the global UI language (header switcher), so there's no per-book toggle.
 */
export function BookBuilder({ book, setBook, onGenerate }) {
  const { t } = useLang()

  function setTitle(title) {
    setBook((b) => ({ ...b, title }))
  }

  function addPage(page) {
    setBook((b) => ({ ...b, pages: [...b.pages, { id: crypto.randomUUID(), ...page }] }))
  }

  function removePage(id) {
    setBook((b) => ({ ...b, pages: b.pages.filter((p) => p.id !== id) }))
  }

  const canGenerate = book.pages.length > 0

  return (
    <section className="mx-auto max-w-3xl px-6 py-10">
      <StepHeading className="text-ink mb-6 text-3xl font-bold">{t.builder.title}</StepHeading>

      <Card className="mb-6 p-6">
        <label htmlFor="book-name" className="text-ink mb-1 block font-semibold">
          {t.builder.bookNameLabel}
        </label>
        <input
          id="book-name"
          value={book.title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={t.builder.bookNamePlaceholder}
          className="border-line bg-surface focus:border-brand w-full rounded-2xl border px-4 py-3 text-lg outline-none"
        />
      </Card>

      <Card className="mb-6 p-6">
        <PageEditor onAdd={addPage} />
      </Card>

      {/* Pages list */}
      <h2 className="text-ink mb-3 text-xl font-bold">
        {t.builder.pagesTitle}{' '}
        <span className="text-muted text-base font-normal">({book.pages.length})</span>
      </h2>
      {book.pages.length === 0 ? (
        <p className="border-line bg-surface/60 text-muted rounded-2xl border border-dashed p-6 text-center">
          {t.builder.empty}
        </p>
      ) : (
        <ul className="space-y-3">
          <AnimatePresence initial={false}>
            {book.pages.map((p, i) => (
              <motion.li
                key={p.id}
                layout
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, x: 20 }}
              >
                <Card className="flex items-center gap-4 p-4">
                  <span className="bg-brand-soft text-brand-dark flex h-9 w-9 shrink-0 items-center justify-center rounded-full font-bold">
                    {i + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-ink truncate font-semibold">{p.text}</p>
                    {p.picture && <p className="text-muted truncate text-sm">🖼 {p.picture}</p>}
                  </div>
                  <button
                    type="button"
                    onClick={() => removePage(p.id)}
                    aria-label={`${t.common.remove} עמוד ${i + 1}`}
                    className="text-muted hover:bg-brand-soft hover:text-brand-dark rounded-full px-3 py-1 text-sm"
                  >
                    {t.common.remove}
                  </button>
                </Card>
              </motion.li>
            ))}
          </AnimatePresence>
        </ul>
      )}

      <div className="mt-8 flex justify-center">
        <Button size="lg" onClick={onGenerate} disabled={!canGenerate}>
          {t.builder.generate} <span aria-hidden="true">{t.common.arrowNext}</span>
        </Button>
      </div>
    </section>
  )
}
