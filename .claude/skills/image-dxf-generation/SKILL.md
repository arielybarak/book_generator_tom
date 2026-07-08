---
name: image-dxf-generation
description: >-
  TOM PNG/text→DXF in src/image_funcs.py (engine-2.0) — text via FILLED glyph contours
  (_filled_glyphs_to_dxf, RETR_EXTERNAL) not skeletonization; braille placed programmatically from
  Unicode bits, not blob detection. USE WHEN editing DXF generation or debugging invisible text /
  broken strokes / stretched braille / empty DXF.
---

# Image / text / braille → DXF (engine-2.0)

`src/image_funcs.py` turns each layer into a DXF that `src/dxf_3d.py` extrudes
([[tactile-stl-geometry]]). The engine-2.0 rewrite changed HOW text and braille become geometry —
the old skeletonization / blob-detection approaches are now **wrong** and produce silent garbage.

## When to Activate This Skill
- "text is invisible / broken strokes", "braille is stretched", "DXF is empty", "glyphs missing"
- Editing `image_to_dxf_exact`, `generate_text_dxf`, or `generate_braille_dxf_from_text`

## Text = FILLED glyph contours, NOT skeletonization
`generate_text_dxf(text, out, rtl=)` builds **filled glyph contours** via `_filled_glyphs_to_dxf`
(OpenCV `RETR_EXTERNAL` on the rasterized glyph). **Do not skeletonize letters** — Zhang-Suen
thinning on filled glyphs produces invisible, broken single-pixel strokes (the old bug). Filled
contours extrude into solid, legible raised letters.

## Braille = programmatic from Unicode bits, NOT blob detection
`generate_braille_dxf_from_text(braille_unicode, out)` places dots **programmatically from the
Unicode braille bit pattern at fixed Grade-1 spacing (≈2.5 mm)**. Do NOT recover braille by
blob-detecting a rendered image — that stretched short words (variable spacing). The Unicode string
comes from `text_to_braille(text, language)` in `src/language_funcs.py` ([[hebrew-braille-nikud]]).

## Entry points (used by [[/stl-bench]])
- `image_to_dxf_exact(gray, out)` — image line-art → DXF (the picture band).
- `generate_text_dxf(text, out, rtl=)` — Hebrew (`rtl=True`) / English (`rtl=False`).
- `generate_braille_dxf_from_text(braille_unicode, out)` — braille dots.

`ensure_font()` still downloads the glyph font on first use (needs network); missing glyphs on a
fresh env usually means that download failed, not a logic bug. After editing `src/`, run
`./sync_to_space.sh` then deploy ([[hf-space-sync-deploy]]).
