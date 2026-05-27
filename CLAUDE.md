# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project context

TOM generates **3D-printable tactile storybook pages** for blind children. The project was initiated with Eliya, an Israeli organization supporting blind children. Each page combines an AI-generated line-art image, raised Hebrew text (for a sighted adult reading alongside), and Braille (for the child) — all merged into a single STL file with distinct tactile height layers.

The backend is deployed on **Hugging Face Spaces** (GPU). `app/app.py` is the Gradio app that runs there. A dedicated frontend is planned. The notebooks are for development and experimentation only.

## Running the app

```bash
pip install -r requirements.txt
python app/app.py          # Gradio web UI
```

The font (`NotoSansSymbols2-Regular.ttf`) auto-downloads on first run via `ensure_font()` in `src/image_funcs.py`.

## Pipeline

One page flows through four stages:

```
Hebrew input
  → src/image_generator.py    Stable Diffusion (segmind/SSD-1B) → 3 PNGs
  → src/image_funcs.py        PNG → DXF (one DXF per PNG)
  → src/dxf_3d.py             3 DXFs → single STL via CadQuery
```

`src/flow_manager.py` wraps this for multi-page books. Pages are processed atomically — if any step throws, that page's state is not updated. Outputs land in `books/{name}_{timestamp}/`.

`app/app.py` is the primary entry point. It imports from `src/` and adds the Gradio UI layer. It currently outputs DXF + PNG per page (ZIP download) — **STL generation via `src/dxf_3d.py` is not yet wired into the app**.

## Module responsibilities

- **`src/language_funcs.py`** — All Hebrew/Braille logic: constants (`HEBREW_MAP`, `SPECIAL_REPLACEMENTS`, `DISPLAY_MAPPING`), `hebrew_translator()`, `convert_to_braille()`, `apply_variations()` (UI-safe nikud), `check_ambiguities()` (feeds the Gradio disambiguation dropdowns), `add_nikud()` (CLI-only, uses `input()`)
- **`src/image_funcs.py`** — Image processing and DXF export: `image_to_dxf_exact()` (skeletonization + polygon simplification), `process_image_to_dxf()` (colour image → DXF), `generate_braille_dxf_from_text()` (blob detection for Braille dots), `ensure_font()`, `png_to_dxf()`, `plot_dxf()`
- **`src/dxf_3d.py`** — Builds the final STL from 3 DXFs. Also works as a standalone CLI: `python src/dxf_3d.py --text t.dxf --braille b.dxf --image i.dxf -o page.stl`
- **`src/image_generator.py`** — Wraps Stable Diffusion + image processing into `create_images()` and `images_to_dxf()` (used by FlowManager)

## Key constants in src/dxf_3d.py

All geometry is controlled by module-level constants:
- `BASE_WIDTH / BASE_HEIGHT` — 150×150mm base plate
- `BASE_THICKNESS` — 1.5mm
- `TEXT_SOLID_HEIGHT` — 1.5mm extrusion for Hebrew text
- `IMAGE_STROKE_WIDTH / IMAGE_STROKE_HEIGHT` — 1.0mm / 1.5mm for image ridges
- `DOME_HEIGHT_RATIO` — Braille dome height = radius × 0.5

## Import convention

All `src/` imports use the `src.` prefix. Always run scripts from the repo root:
```python
from src import language_funcs as lf
from src.image_funcs import ensure_font, process_image_to_dxf
```

## HF Spaces deployment note

Hugging Face Spaces expects `app.py` at the repo root. When deploying, copy or symlink `app/app.py` to the root, or configure the Space entry point. `app_colab.ipynb` is the same app adapted to run on Colab with `share=True`.

## opencv dependency

Use `opencv-contrib-python`, not `opencv-python` — the contrib build includes `cv2.ximgproc.thinning` (Zhang-Suen skeletonization) used in `image_to_dxf_exact()`. Without it, the code falls back to Canny edges (double lines).
