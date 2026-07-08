/**
 * Decorative illustration of a finished tactile page: raised Hebrew word (top),
 * a simple line-art drawing (middle), and a row of Braille cells (bottom).
 * Pure CSS/SVG — communicates the product on the landing page without assets.
 */

function BrailleCell({ dots }) {
  // dots: array of 6 booleans, order [1,4,2,5,3,6] (column-major like real Braille)
  return (
    <div className="grid grid-cols-2 grid-rows-3 gap-1">
      {dots.map((on, i) => (
        <span
          key={i}
          className={`h-2.5 w-2.5 rounded-full ${on ? 'bg-accent shadow-soft' : 'bg-line'}`}
        />
      ))}
    </div>
  )
}

const SAMPLE_CELLS = [
  [true, false, true, false, false, false],
  [true, true, false, true, false, false],
  [true, false, false, true, true, false],
]

function CatSvg() {
  return (
    <svg viewBox="0 0 120 120" className="text-ink h-full max-h-44 w-full">
      <g fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round">
        <path d="M35 30 L45 52" />
        <path d="M85 30 L75 52" />
        <circle cx="60" cy="68" r="30" />
        <circle cx="50" cy="64" r="2.5" fill="currentColor" />
        <circle cx="70" cy="64" r="2.5" fill="currentColor" />
        <path d="M60 72 l-4 5 h8 z" fill="currentColor" stroke="none" />
        <path d="M60 77 v6" />
        <path d="M30 70 h14 M30 78 h14" />
        <path d="M90 70 h-14 M90 78 h-14" />
      </g>
    </svg>
  )
}

function DogSvg() {
  return (
    <svg viewBox="0 0 120 120" className="text-ink h-full max-h-44 w-full">
      <g fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round">
        {/* body */}
        <ellipse cx="60" cy="72" rx="32" ry="22" />
        {/* head */}
        <circle cx="88" cy="52" r="18" />
        {/* ear */}
        <path d="M80 36 Q72 22 68 34" />
        {/* eye */}
        <circle cx="92" cy="48" r="2.5" fill="currentColor" />
        {/* nose */}
        <ellipse cx="100" cy="56" rx="4" ry="3" fill="currentColor" />
        {/* tail */}
        <path d="M28 68 Q14 50 22 40" />
        {/* legs */}
        <line x1="42" y1="92" x2="38" y2="108" />
        <line x1="55" y1="94" x2="53" y2="110" />
        <line x1="68" y1="94" x2="70" y2="110" />
        <line x1="80" y1="90" x2="82" y2="106" />
      </g>
    </svg>
  )
}

function FlowerSvg() {
  return (
    <svg viewBox="0 0 120 120" className="text-ink h-full max-h-44 w-full">
      <g fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round">
        {/* stem */}
        <line x1="60" y1="90" x2="60" y2="108" />
        {/* leaves */}
        <path d="M60 95 Q44 88 40 78 Q52 80 60 88" />
        <path d="M60 88 Q76 80 80 70 Q68 74 60 82" />
        {/* petals */}
        <ellipse cx="60" cy="58" rx="8" ry="18" />
        <ellipse cx="60" cy="58" rx="18" ry="8" />
        <ellipse cx="60" cy="58" rx="13" ry="16" transform="rotate(45 60 58)" />
        <ellipse cx="60" cy="58" rx="13" ry="16" transform="rotate(-45 60 58)" />
        {/* center */}
        <circle cx="60" cy="58" r="8" fill="currentColor" stroke="none" />
      </g>
    </svg>
  )
}

const ILLUSTRATIONS = {
  'חָתוּל': CatSvg,
  'כֶּלֶב': DogSvg,
  'פְּרָחִים': FlowerSvg,
}

export function TactilePageMock({ word = 'חָתוּל', className = '' }) {
  const Illustration = ILLUSTRATIONS[word] ?? CatSvg
  return (
    <div
      aria-hidden="true"
      className={`rounded-card border-line bg-surface shadow-card flex aspect-square w-full flex-col overflow-hidden border ${className}`}
    >
      {/* Hebrew text strip */}
      <div className="border-line bg-brand-soft flex items-center justify-center border-b py-4">
        <span className="text-brand-dark text-3xl font-bold">{word}</span>
      </div>

      {/* Line-art drawing */}
      <div className="flex flex-1 items-center justify-center p-6">
        <Illustration />
      </div>

      {/* Braille row */}
      <div className="border-line flex items-center justify-center gap-3 border-t py-4">
        {SAMPLE_CELLS.map((dots, i) => (
          <BrailleCell key={i} dots={dots} />
        ))}
      </div>
    </div>
  )
}
