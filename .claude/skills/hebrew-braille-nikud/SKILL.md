---
name: hebrew-braille-nikud
description: >-
  TOM Hebrew→Braille+nikud in src/language_funcs.py — SPECIAL_REPLACEMENTS keys
  mirror DISPLAY_MAPPING and web/src/lib/nikud.js. USE WHEN editing translation,
  Braille, nikud, or /generate_page variations payload.
---

# Hebrew / Braille / nikud

`src/language_funcs.py` owns all Hebrew logic: `hebrew_translator()`, `convert_to_braille()`,
the nikud constants, and the UI-disambiguation helpers.

## When to Activate This Skill
- "add a nikud option", "vowel marks", "the dropdown doesn't change anything", "Braille is wrong"
- Editing `SPECIAL_REPLACEMENTS`, `DISPLAY_MAPPING`, `apply_variations`, `check_ambiguities`
- Touching `web/src/lib/nikud.js` or the `variations` field of the `/generate_page` API

## The contract: nikud keys live in THREE places and must match
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
- The detection of which letters offer a choice runs client-side in `nikud.js` (`findChoices`), but the **replacement** is backend-only (`apply_variations`) — keep the two letter sets aligned, not just the keys.
- Hebrew is **RTL**; `web/CLAUDE.md` warns the current `gradio_app_lithophane.py` had a direction quirk — verify text *and* Braille direction independently, don't trust it as a reference.
