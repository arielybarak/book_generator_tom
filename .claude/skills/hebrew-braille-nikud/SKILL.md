---
name: hebrew-braille-nikud
description: >-
  TOM Hebrew+English→Braille+nikud in src/language_funcs.py — SPECIAL_REPLACEMENTS keys mirror
  DISPLAY_MAPPING and web/src/lib/nikud.js; text_to_braille(text, language) dispatches Hebrew
  (RTL→LTR reversed) and English Grade-1 (no reversal). USE WHEN editing translation, Braille,
  nikud, the language input, or /generate_page variations payload.
---

# Hebrew / English / Braille / nikud

`src/language_funcs.py` owns all language→Braille logic: `hebrew_translator()`,
`convert_to_braille()`, the nikud constants, the UI-disambiguation helpers, and (engine-2.0+)
`text_to_braille(text, language)` which dispatches to Hebrew or English Grade-1.

## When to Activate This Skill
- "add a nikud option", "vowel marks", "the dropdown doesn't change anything", "Braille is wrong"
- Editing `SPECIAL_REPLACEMENTS`, `DISPLAY_MAPPING`, `apply_variations`, `check_ambiguities`
- Touching `web/src/lib/nikud.js` or the `variations` field of the `/generate_page` API
- Adding English support / the `language` input / `ENGLISH_BRAILLE_MAP`

## text_to_braille(text, language) — the dispatch point
`generate_braille_dxf_from_text` ([[image-dxf-generation]]) calls this unified entry point.

```python
def text_to_braille(text: str, language: str) -> str:
    if language == "hebrew":
        return _hebrew_to_braille(text)   # uses HEBREW_MAP + reversal below
    elif language == "english":
        return _english_to_braille(text)  # uses ENGLISH_BRAILLE_MAP, no reversal
    raise ValueError(f"unsupported language: {language}")
```

`language` flows in from the `/generate_page` API 5th input (see [[web-backend-contract]]).

## Hebrew braille — RTL→LTR reversal
Hebrew text is **RTL**; Braille is always **LTR**. `_hebrew_to_braille` must **reverse** the
character order after translating. Without reversal, dots appear right-to-left and the cell
sequence is the mirror of what a Braille reader expects.

## English Grade-1 braille — no reversal
`ENGLISH_BRAILLE_MAP` is a `dict[str, str]` mapping ASCII printable characters (a–z, A–Z,
digits, common punctuation) to their Unicode Braille cell (U+2800–U+283F).

```python
ENGLISH_BRAILLE_MAP: dict[str, str] = {
    'a': '⠁', 'b': '⠃', 'c': '⠉', 'd': '⠙', 'e': '⠑',
    'f': '⠋', 'g': '⠛', 'h': '⠓', 'i': '⠊', 'j': '⠚',
    'k': '⠅', 'l': '⠇', 'm': '⠍', 'n': '⠝', 'o': '⠕',
    'p': '⠏', 'q': '⠟', 'r': '⠗', 's': '⠎', 't': '⠞',
    'u': '⠥', 'v': '⠧', 'w': '⠺', 'x': '⠭', 'y': '⠽',
    'z': '⠵',
    # digits use number indicator ⠼ prefix (Grade-1)
    ' ': '⠀',
}

def _english_to_braille(text: str) -> str:
    return ''.join(ENGLISH_BRAILLE_MAP.get(ch.lower(), '⠀') for ch in text)
```

No character reversal — English Braille reads left-to-right like English text.

## The nikud contract: three mirrored locations
`SPECIAL_REPLACEMENTS` maps a Hebrew letter (`ו ש ב כ פ ך ף`) → `{ key: glyph }`. The **keys**
(`default`, `holam`, `shuruk`, `shin`, `sin`, `dagesh`) are a contract shared by:
1. `SPECIAL_REPLACEMENTS` in `src/language_funcs.py` — the actual replacement (backend truth).
2. `DISPLAY_MAPPING` in the same file — the Hebrew labels for the Gradio dropdowns.
3. `NIKUD[...].options[].key` in `web/src/lib/nikud.js` — the frontend chips.

**Add or rename a key in one → update all three.** If the frontend sends a key the backend
doesn't know, `apply_variations()` silently leaves the letter unchanged — the user's choice is
**dropped with no error**. Run [[/check-sync]] to verify parity.

## Which function on which path
- **`apply_variations(raw_text, variations)`** — the UI/web path. `variations` is `{ "<charIndex>": "<key>" }` (exactly what `/generate_page` receives; see `web/CLAUDE.md`).
- **`check_ambiguities(text)`** — returns the letters with choices + `list(SPECIAL_REPLACEMENTS[char].keys())`; feeds the Gradio dropdowns / frontend chips.
- **`add_nikud(text)`** — **CLI-only**, it calls `input()`. Never invoke it from the Gradio/web path; it will hang the server. Use `apply_variations` instead.

## Gotchas
- Detection of which letters offer a choice runs client-side in `nikud.js` (`findChoices`), but the **replacement** is backend-only (`apply_variations`) — keep the two letter sets aligned, not just the keys.
- Hebrew is **RTL**; Braille is **LTR** — the reversal in `_hebrew_to_braille` is intentional and must not be applied to English.
- After editing `src/language_funcs.py`, run `./sync_to_space.sh` then push from `hf_space/` ([[hf-space-sync-deploy]]).
