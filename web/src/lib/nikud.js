/**
 * Friendly Hebrew vowel-mark (nikud) choices for non-technical users.
 *
 * The OPTION KEYS here ('default' / 'holam' / 'shuruk' / 'shin' / 'sin' / 'dagesh')
 * MUST stay in sync with SPECIAL_REPLACEMENTS in `src/language_funcs.py` (the backend
 * re-applies them via apply_variations). Only the *labels* are friendlier here —
 * we show the actual letter-with-dot + a pronunciation hint + a familiar example,
 * never grammar jargon like "חולם/שורוק".
 *
 * Detection runs client-side (instant, no network round-trip per keystroke); the
 * chosen { index: key } map is sent to /generate_page, which does the real work.
 */

export const NIKUD = {
  ו: {
    prompt: 'איך הוגים את האות ו?',
    options: [
      { key: 'default', glyph: 'ו', sound: 'V', example: 'וֶרֶד' },
      { key: 'holam', glyph: 'וֹ', sound: 'O', example: 'אוֹר' },
      { key: 'shuruk', glyph: 'וּ', sound: 'U', example: 'חוּמוּס' },
    ],
  },
  ש: {
    prompt: 'איך הוגים את האות ש?',
    options: [
      { key: 'shin', glyph: 'שׁ', sound: 'SH', example: 'שֶׁמֶש' },
      { key: 'sin', glyph: 'שׂ', sound: 'S', example: 'שִׂמְלָה' },
    ],
  },
  ב: {
    prompt: 'איך הוגים את האות ב?',
    options: [
      { key: 'default', glyph: 'ב', sound: 'V', example: 'אַהֲבָה' },
      { key: 'dagesh', glyph: 'בּ', sound: 'B', example: 'בַּיִת' },
    ],
  },
  כ: {
    prompt: 'איך הוגים את האות כ?',
    options: [
      { key: 'default', glyph: 'כ', sound: 'KH', example: 'בְּרָכָה' },
      { key: 'dagesh', glyph: 'כּ', sound: 'K', example: 'כֶּלֶב' },
    ],
  },
  פ: {
    prompt: 'איך הוגים את האות פ?',
    options: [
      { key: 'default', glyph: 'פ', sound: 'F', example: 'יָפֶה' },
      { key: 'dagesh', glyph: 'פּ', sound: 'P', example: 'פִּיל' },
    ],
  },
  ך: {
    prompt: 'איך הוגים את האות ך?',
    options: [
      { key: 'default', glyph: 'ך', sound: 'KH', example: 'מֶלֶך' },
      { key: 'dagesh', glyph: 'ךּ', sound: 'K', example: '' },
    ],
  },
  ף: {
    prompt: 'איך הוגים את האות ף?',
    options: [
      { key: 'default', glyph: 'ף', sound: 'F', example: 'סוֹף' },
      { key: 'dagesh', glyph: 'ףּ', sound: 'P', example: '' },
    ],
  },
}

/**
 * Find letters in `text` that have a pronunciation choice.
 * Returns [{ index, char, prompt, options }] — feeds the friendly chips.
 */
export function findChoices(text) {
  const out = []
  if (!text) return out
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]
    if (NIKUD[ch]) out.push({ index: i, char: ch, ...NIKUD[ch] })
  }
  return out
}
