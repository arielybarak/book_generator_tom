import { useMemo, useRef, useState } from 'react'
import { Button } from './ui/Button'
import { NikudChooser } from './NikudChooser'
import { findChoices } from '../lib/nikud'
import { fileToCompressedDataUrl } from '../lib/image'
import { useLang } from '../lib/i18n'

/**
 * Form for composing one page: a sentence, a nikud panel (Hebrew only), and the
 * page's picture source — auto-generated, uploaded, or none. Calls
 * onAdd({ text, picture, variations, imageMode, uploadedImage }) and resets.
 */
export function PageEditor({ onAdd }) {
  const { t, lang } = useLang()
  const [text, setText] = useState('')
  const [picture, setPicture] = useState('')
  const [variations, setVariations] = useState({})
  const [showNikud, setShowNikud] = useState(false)

  const [imageMode, setImageMode] = useState('generate') // 'generate' | 'upload' | 'none'
  const [upload, setUpload] = useState('') // compressed data URL
  const [uploadBusy, setUploadBusy] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [dragging, setDragging] = useState(false)
  const fileRef = useRef(null)

  const isEnglish = lang === 'english'
  // Nikud only applies to Hebrew; English text never triggers it.
  const choices = useMemo(() => (isEnglish ? [] : findChoices(text)), [text, isEnglish])

  const modes = [
    ['generate', t.builder.modeGenerate, '✎'],
    ['upload', t.builder.modeUpload, '⬆'],
    ['none', t.builder.modeNone, '∅'],
  ]

  function reset() {
    setText('')
    setPicture('')
    setVariations({})
    setShowNikud(false)
    setImageMode('generate')
    setUpload('')
    setUploadError('')
    if (fileRef.current) fileRef.current.value = ''
  }

  async function handleFile(file) {
    if (!file) return
    if (!/^image\/(png|jpeg)$/i.test(file.type)) {
      setUploadError(t.builder.uploadError)
      return
    }
    setUploadError('')
    setUploadBusy(true)
    try {
      setUpload(await fileToCompressedDataUrl(file))
    } catch {
      setUploadError(t.builder.uploadError)
    } finally {
      setUploadBusy(false)
    }
  }

  function onDrop(e) {
    e.preventDefault()
    setDragging(false)
    handleFile(e.dataTransfer.files?.[0])
  }

  function clearUpload() {
    setUpload('')
    setUploadError('')
    if (fileRef.current) fileRef.current.value = ''
  }

  const uploadMissing = imageMode === 'upload' && !upload
  // Picture description drives the auto-drawing prompt — keep it to <=2 words.
  const pictureWordCount = picture.trim() ? picture.trim().split(/\s+/).length : 0
  const pictureTooLong = imageMode === 'generate' && pictureWordCount > 2

  function submit(e) {
    e.preventDefault()
    if (!text.trim() || uploadMissing || uploadBusy || pictureTooLong) return
    onAdd({
      text: text.trim(),
      picture: picture.trim(),
      variations,
      imageMode,
      uploadedImage: imageMode === 'upload' ? upload : undefined,
    })
    reset()
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div>
        <label htmlFor="page-text" className="text-ink mb-1 block font-semibold">
          {t.builder.sentenceLabel}
        </label>
        <textarea
          id="page-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={2}
          placeholder={t.builder.sentencePlaceholder}
          className="border-line bg-surface focus:border-brand w-full resize-none rounded-2xl border px-4 py-3 text-lg outline-none"
        />
      </div>

      {choices.length > 0 && (
        <div>
          <button
            type="button"
            onClick={() => setShowNikud((s) => !s)}
            aria-expanded={showNikud}
            className="text-accent-text text-sm font-semibold hover:underline"
          >
            {showNikud ? '▾ ' : '▸ '}
            {t.builder.soundQuestion} ({choices.length})
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

      {/* Picture source: auto-generate, upload a drawing, or none */}
      <div>
        <span className="text-ink mb-1 block font-semibold">{t.builder.imageModeLabel}</span>
        <div
          role="radiogroup"
          aria-label={t.builder.imageModeLabel}
          className="bg-brand-soft/60 grid grid-cols-3 gap-1 rounded-2xl p-1"
        >
          {modes.map(([val, label, icon]) => {
            const active = imageMode === val
            return (
              <button
                key={val}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => setImageMode(val)}
                className={`rounded-xl px-2 py-2 text-sm font-semibold transition ${
                  active ? 'bg-brand shadow-soft text-white' : 'text-brand-dark hover:bg-white/60'
                }`}
              >
                <span aria-hidden="true">{icon}</span> {label}
              </button>
            )
          })}
        </div>
      </div>

      {imageMode === 'generate' && (
        <div>
          <label htmlFor="page-picture" className="text-ink mb-1 block font-semibold">
            {t.builder.pictureLabel}{' '}
            <span className="text-muted text-sm font-normal">({t.builder.pictureHint})</span>
          </label>
          <input
            id="page-picture"
            value={picture}
            onChange={(e) => setPicture(e.target.value)}
            placeholder={t.builder.picturePlaceholder}
            aria-invalid={pictureTooLong}
            aria-describedby={pictureTooLong ? 'page-picture-err' : undefined}
            className={`bg-surface w-full rounded-2xl border px-4 py-3 text-lg outline-none ${
              pictureTooLong ? 'border-red-500 focus:border-red-500' : 'border-line focus:border-brand'
            }`}
          />
          {pictureTooLong && (
            <p id="page-picture-err" role="alert" className="mt-1 text-sm text-red-600">
              {t.builder.pictureTooLong}
            </p>
          )}
        </div>
      )}

      {imageMode === 'upload' && (
        <div>
          <div
            onDragOver={(e) => {
              e.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            className={`rounded-2xl border-2 border-dashed p-5 text-center transition ${
              dragging ? 'border-brand bg-brand-soft/40' : 'border-line'
            }`}
          >
            {upload ? (
              <div className="flex flex-col items-center gap-3">
                <img
                  src={upload}
                  alt={t.builder.uploadImageAlt}
                  className="border-line max-h-40 rounded-lg border bg-white"
                />
                <div className="flex gap-2">
                  <Button type="button" size="sm" variant="ghost" onClick={() => fileRef.current?.click()}>
                    {t.builder.uploadReplace}
                  </Button>
                  <Button type="button" size="sm" variant="ghost" onClick={clearUpload}>
                    {t.builder.uploadRemove}
                  </Button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                className="text-brand-dark hover:text-brand flex w-full flex-col items-center gap-1 py-2"
              >
                <span aria-hidden="true" className="text-2xl">
                  🖼️
                </span>
                <span className="font-semibold">
                  {uploadBusy ? t.builder.uploadProcessing : t.builder.uploadCta}
                </span>
                <span className="text-muted text-xs">{t.builder.uploadHint}</span>
              </button>
            )}
            <input
              ref={fileRef}
              type="file"
              accept="image/png,image/jpeg"
              onChange={(e) => handleFile(e.target.files?.[0])}
              aria-label={t.builder.modeUpload}
              className="sr-only"
            />
          </div>
          {uploadError && (
            <p role="alert" className="mt-2 text-sm text-red-600">
              {uploadError}
            </p>
          )}
          <div className="bg-accent-soft mt-3 rounded-2xl p-4">
            <p className="text-ink mb-1 font-semibold">{t.builder.instructionsTitle}</p>
            <ul className="text-muted list-disc space-y-0.5 ps-5 text-sm">
              {t.builder.instructions.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {imageMode === 'none' && (
        <p className="border-line bg-surface/60 text-muted rounded-2xl border border-dashed p-4 text-sm">
          {t.builder.noneNote}
        </p>
      )}

      <Button
        type="submit"
        variant="soft"
        disabled={!text.trim() || uploadMissing || uploadBusy || pictureTooLong}
      >
        <span aria-hidden="true">＋</span> {t.builder.addPage}
      </Button>
    </form>
  )
}
