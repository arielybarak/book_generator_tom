---
name: image-dxf-generation
description: >-
  TOM's image generation + PNG→DXF stage in src/image_funcs.py and
  src/image_generator.py — Stable Diffusion line-art, skeletonization to single-stroke
  DXF, and Braille-dot blobs. Requires opencv-contrib-python and auto-downloads a font.
  USE WHEN editing image generation, PNG→DXF export, thinning/skeletonization, the
  Braille font, or debugging double-line / missing-glyph / empty-DXF output.
---

# Image generation → DXF

The middle of the pipeline: Stable Diffusion makes line-art PNGs, then `src/image_funcs.py`
turns each PNG into a single-stroke DXF (image, text, Braille) that `src/dxf_3d.py` extrudes.

## When to Activate This Skill
- "double lines in the image", "the DXF is empty", "Braille glyphs missing", "font error"
- Editing `image_to_dxf_exact`, `process_image_to_dxf`, `png_to_dxf`, `generate_braille_dxf_from_text`, `generate_hebrew_text_dxf`, or `src/image_generator.py`
- Changing the SD model or inference params

## The trap that bites silently: opencv-contrib
`image_to_dxf_exact()` calls `cv2.ximgproc.thinning(..., THINNING_ZHANGSUEN)` for single-pixel
skeletonization. That lives **only in `opencv-contrib-python`** — with plain `opencv-python` the
code prints `Warning: cv2.ximgproc not found — falling back to Canny (double lines)` and produces
**doubled outlines** instead of clean single strokes. The warning scrolls past; the bad DXF looks
plausible. If you see double lines, check the install (`opencv-contrib-python`, not `opencv-python`
— also in `.claude/instructions/python.instructions.md`). On the Space, fix it in
`hf_space/requirements.txt`.

## The other first-run trap: the Braille font
`ensure_font()` downloads **`NotoSansSymbols2-Regular.ttf`** (from `FONT_URL`) on first use for
Braille rendering. First run needs network and is slow; if Braille glyphs are missing, the font
download failed — check connectivity / the URL, not the Braille logic.

## Conventions
- SD config comes from `config.yaml` → `stable_diffusion` (`model_id: segmind/SSD-1B`, `inference_steps: 25`, `guidance_scale: 8.5`). Needs ~6 GB GPU; on the Space it runs under `@spaces.GPU` (ZeroGPU).
- DXF canvas defaults to `canvas_cm=150` across `*_to_dxf` functions — keep it consistent with the plate size in [[tactile-stl-geometry]].
- After editing `src/`, **run `./sync_to_space.sh`** to deploy the change (see [[hf-space-sync-deploy]]).
