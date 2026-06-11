/**
 * Friendly per-letter pronunciation chooser. Shows the letter-with-dot, a sound
 * hint (V/O/U…), and a familiar example word — never grammar terms. The selected
 * `key` is what gets sent to the backend (must match SPECIAL_REPLACEMENTS).
 */
export function NikudChooser({ choice, value, onChange }) {
  const current = value ?? choice.options[0].key
  return (
    <div className="border-line bg-brand-soft/50 rounded-2xl border p-3">
      <p className="text-ink mb-2 text-sm font-semibold">
        {choice.prompt} <span className="text-muted font-normal">(לא חובה)</span>
      </p>
      <div className="flex flex-wrap gap-2">
        {choice.options.map((o) => {
          const selected = current === o.key
          return (
            <button
              key={o.key}
              type="button"
              aria-pressed={selected}
              onClick={() => onChange(o.key)}
              className={`flex items-center gap-2 rounded-xl border px-3 py-2 transition ${
                selected
                  ? 'border-brand bg-brand text-white'
                  : 'border-line bg-surface text-ink hover:border-brand'
              }`}
            >
              <span className="text-2xl leading-none">{o.glyph}</span>
              <span className={`text-xs ${selected ? 'text-white/90' : 'text-muted'}`}>
                {o.sound}
                {o.example ? ` · ${o.example}` : ''}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
