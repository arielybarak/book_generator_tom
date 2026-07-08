# PROGRESS — TOM (CadQuery tactile-page engine + bilingual website)

Living status snapshot. Durable conventions live in `CLAUDE.md`, `web/CLAUDE.md`, and
`.claude/skills/`; this file tracks **what changed, why, and known caveats.**

_Last updated: 2026-06-23._

## Current state — LIVE

- **Deployed engine: CadQuery solid** (`src/dxf_3d.py`) via `hf_space/gradio_app_lithophane.py`
  (filename keeps the historical suffix; the heightmap engine in `src/lithophane.py` is engine-2,
  unused in prod). Produces a 150×150mm plate, three non-overlapping tactile bands.
- **Bilingual** — Hebrew/English across UI (header switcher, RTL↔LTR) and generated content
  (text + Braille). Per-page **generation timer** in the web UI.
- Web frontend on Vercel; backend on HF Space (ZeroGPU, owner PRO quota via the `/api/generate` proxy).

---

## 2026-06-23 — CadQuery migration + bug log (focus: how each bug was solved)

Switched the deployed product from the lithophane **heightmap** engine to the CadQuery
**solid** engine. Chose to swap the engine *inside* the deployed app rather than flip
`app_file` to `gradio_app.py` — that app was 3 commits stale and would have regressed
`ping_assets`/`slow_ping`, the `gr.Error` clean-fail, and the `gr.File` image-403 fix.

Each bug below was found by measuring on a **real** SD image (`outputs/output.png`, 559 paths),
not a toy — the toy cases hid every one of them.

| # | Bug (symptom) | Root cause | Fix |
|---|---|---|---|
| 1 | STL build took **minutes→hours**, site hung | `base.union(solid)` **per piece** (text/dot/stroke/texture) — each fuse re-triangulates the whole growing model → ~O(N²); real page = thousands of overlapping solids | First batched into one compound + single fuse; but at 559 paths even one general fuse = **2.4 hr**. Real fix: **no boolean at all** — emit a multi-volume mesh (`cq.Compound.makeCompound`) and let the **slicer** union overlaps at print time. **2.4hr → ~60s (~190×).** |
| 2 | Even no-fuse build still slow on busy art | OCCT **fillet** (rounded ridge tops) = ~88% of build time | Replaced fillet with a draft **taper** at extrude time (cheap rounded top). |
| 3 | Text/strokes silently **dropped** (`No pending wires present`) | A *failed* taper extrude still consumes the Workplane's pending wire, so the flat-extrude fallback found nothing | Build a **fresh** Workplane per attempt (`_capped_solid`). |
| 4 | Live worker **crashed**, log died after `Text solids: 3`; user saw "שגיאה" | `extrude(taper=)` **segfaults OCCT** on real Hebrew glyph outlines (reproduced on פרח) — a C-level crash that kills the whole process | **Disabled taper → flat tops** (`STROKE_TAPER_DEG = 0`). Robust; rounded tops would need a crash-isolated subprocess. |
| 5 | First generation after every deploy **errored (~3 min)** | Rebuild wipes the 8.9 GB SD model cache; `from_pretrained` re-downloads **inside** the 30 s `@spaces.GPU` window → ZeroGPU kills it | **Pre-download weights at startup** (`predownload_weights()`, CPU, outside the GPU window). |
| 6 | Logs "stuck at Text solids" (looked hung) | HF stdout is a **block-buffered pipe**; prints lagged the actual progress | `print = functools.partial(print, flush=True)` + per-stage `[t]` timing in `dxf_3d.py`. |
| 7 | Drawing **10× too big**, sprawled off the plate | The 3 DXF layers arrive at mismatched, huge coords (image/text ~1500mm via `canvas_cm*10`, Braille in px); assembler only **centered**, never scaled | `layout_content_on_base` now **scales to fit** the plate (margin) — and lays out **bands**. |
| 8 | Layers **overlapped** in the center | No layout — all three centered on the same point | **Banded layout**: Hebrew text (top) / image (middle) / Braille (bottom), each fit to its band, 4 mm gaps. |
| 9 | Braille dots **stretched** for short words | Dots came from blob-detecting a rendered PNG, then scaled to fill the band | Generate dots **programmatically from the Unicode Braille bits** at **fixed Grade-1 mm** (2.5 mm dot / 6 mm cell). Verified 2.50 mm regardless of word length; also drops the Braille-font dependency. |
| 10 | Hebrew text **invisible / "split"** | `generate_hebrew_text_dxf` ran text through `image_to_dxf_exact`, which **skeletonizes** → thin broken stroke-skeletons | New `_filled_glyphs_to_dxf` (RETR_EXTERNAL) → **solid filled glyph outlines** extruded as solid letters. |
| 11 | GPU couldn't speed up CadQuery | OCCT is a **CPU B-rep kernel** — no GPU backend; `@spaces.GPU` only attaches a GPU for the torch SD call | Confirmed CPU-only; CadQuery runs outside the GPU budget. Lever is solid-count / algorithm, not hardware. |

### Features added the same session
- **English support** — `language` param threaded frontend → `/api/generate` proxy → `/generate_page`
  (5th input) → `generate_page_assets`. English = Grade-1 braille map, LTR `generate_text_dxf(rtl=False)`,
  no nikud, no Hebrew→English translation.
- **Full UI i18n** — `web/src/lib/i18n.jsx` (`LanguageProvider`/`useLang`, persisted, flips `<html dir>`),
  `copy.js` → `{ hebrew, english }`, header `עב|EN` switcher, direction-aware arrows, localized a11y labels.
- **Generation timer** — live per-page elapsed in `GenerateStep`.

---

## Geometry / engine reference (current `src/dxf_3d.py`)
- **No boolean union** — features are independent solids in one `Compound`; the slicer fuses them.
- **Flat tops** — taper disabled (segfault risk on glyphs).
- **Bands** — `layout.text_frac` / `braille_frac` / `band_gap_mm`, `plate.content_margin_mm` (config.yaml).
- **Braille** — fixed Grade-1 mm from Unicode bits (`image_funcs.generate_braille_dxf_from_text`).
- **Text** — solid filled glyphs (`_filled_glyphs_to_dxf`), RTL reversed for Hebrew.
- Typical page (~50 paths) ≈ seconds; pathological dense art (~560 paths) ≈ 60–80 s.

## ⚠ Caveats / next refinements
- **No rounded ridge tops** — flat (taper crashes OCCT). Re-add only via a crash-isolated subprocess.
- **Braille spacing fixed; line-wrapping not handled** — a very long word overflows-then-shrinks; multi-line Braille not implemented.
- **Glyph holes filled** — letters with counters (ם, ס, ק…) print solid (RETR_EXTERNAL). Fine for raised reading; open counters would need hole handling.
- **Dense images slow** — solid-count scales with SD line complexity; no cap yet.
- **i18n parity** — `copy.js` `hebrew`/`english` keys must stay in sync; no automated check yet.

## Run / verify
```bash
cd web && npm run build && npm run lint     # frontend
python src/dxf_3d.py --text t.dxf --braille b.dxf --image i.dxf -o page.stl   # engine CLI
# deploy: backend first (hf_space push → HF), then frontend (web/ push → Vercel)
```
