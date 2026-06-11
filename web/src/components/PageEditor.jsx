import { useMemo, useState } from 'react'
import { Button } from './ui/Button'
import { NikudChooser } from './NikudChooser'
import { findChoices } from '../lib/nikud'
import { COPY } from '../lib/copy'

/**
 * Form for composing one page: a Hebrew sentence + a short picture description,
 * with an optional collapsible "pronunciation" panel (nikud chips). Calls
 * onAdd({ text, picture, variations }) and resets.
 */
export function PageEditor({ onAdd }) {
  const [text, setText] = useState('')
  const [picture, setPicture] = useState('')
  const [variations, setVariations] = useState({})
  const [showNikud, setShowNikud] = useState(false)

  const choices = useMemo(() => findChoices(text), [text])

  function reset() {
    setText('')
    setPicture('')
    setVariations({})
    setShowNikud(false)
  }

  function submit(e) {
    e.preventDefault()
    if (!text.trim()) return
    onAdd({ text: text.trim(), picture: picture.trim(), variations })
    reset()
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div>
        <label htmlFor="page-text" className="text-ink mb-1 block font-semibold">
          {COPY.builder.sentenceLabel}
        </label>
        <textarea
          id="page-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={2}
          placeholder={COPY.builder.sentencePlaceholder}
          className="border-line bg-surface focus:border-brand w-full resize-none rounded-2xl border px-4 py-3 text-lg outline-none"
        />
      </div>

      {choices.length > 0 && (
        <div>
          <button
            type="button"
            onClick={() => setShowNikud((s) => !s)}
            aria-expanded={showNikud}
            className="text-accent text-sm font-semibold hover:underline"
          >
            {showNikud ? '▾ ' : '▸ '}
            {COPY.builder.soundQuestion} ({choices.length})
          </button>
          {showNikud && (
            <div className="mt-3 space-y-2">
              {choices.map((c) => (
                <NikudChooser
                  key={c.index}
                  choice={c}
                  value={variations[c.index]}
                  onChange={(key) => setVariations((v) => ({ ...v, [c.index]: key }))}
                />
              ))}
            </div>
          )}
        </div>
      )}

      <div>
        <label htmlFor="page-picture" className="text-ink mb-1 block font-semibold">
          {COPY.builder.pictureLabel}
        </label>
        <input
          id="page-picture"
          value={picture}
          onChange={(e) => setPicture(e.target.value)}
          placeholder={COPY.builder.picturePlaceholder}
          className="border-line bg-surface focus:border-brand w-full rounded-2xl border px-4 py-3 text-lg outline-none"
        />
      </div>

      <Button type="submit" variant="soft" disabled={!text.trim()}>
        <span aria-hidden="true">＋</span> {COPY.builder.addPage}
      </Button>
    </form>
  )
}
