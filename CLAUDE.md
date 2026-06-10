# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project context

TOM generates **3D-printable tactile storybook pages** for blind children. The project was initiated with Eliya, an Israeli organization supporting blind children. Each page combines an AI-generated line-art image, raised Hebrew text (for a sighted adult reading alongside), and Braille (for the child) — all merged into a single STL file with distinct tactile height layers.

The backend is deployed on **Hugging Face Spaces** (GPU via ZeroGPU). The Space is its own git repo, vendored here as the **`hf_space/` submodule**; `hf_space/gradio_app.py` is the Gradio app that runs there. A dedicated frontend is planned. The notebooks are for development and experimentation only.

## Running the app

```bash
pip install -r hf_space/requirements.txt
cd hf_space && python gradio_app.py     # Gradio web UI (self-contained)
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

`hf_space/gradio_app.py` is the primary entry point. It imports from `src/` and adds the Gradio UI layer. The full pipeline is wired: per page it generates the image PNG, three DXFs (image/text/braille), and the final STL via `create_one_page_stl_from_dxf()`, then returns a ZIP. SD inference runs under a `@spaces.GPU` decorator (ZeroGPU); translation, DXF, and STL stay on CPU.

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

The app is **canonical in the `hf_space/` submodule** (HF Space repo: `MLightning/text2STL-engine-2.0-superMX-bottom`). It is self-contained — `hf_space/` bundles its own copies of `gradio_app.py`, `src/`, `config.yaml`, and `requirements.txt`. To change the app: edit inside `hf_space/`, then `git commit` + `git push` from that folder; HF auto-rebuilds. The entry point is set by `app_file: gradio_app.py` in `hf_space/README.md` (HF no longer requires the literal name `app.py`).

The repo-root `src/` is kept for the notebooks and CLI/FlowManager. `hf_space/` vendors a **copy** of `src/` + `config.yaml` (HF Spaces must be self-contained), so the two can drift. **After changing any `src/` module or `config.yaml` the app uses, run `./sync_to_space.sh`** from the repo root — it mirrors `src/` and `config.yaml` into `hf_space/` (rsync `--delete`, skips `__pycache__`). Then commit + push from inside `hf_space/` to redeploy.

## opencv dependency

Use `opencv-contrib-python`, not `opencv-python` — the contrib build includes `cv2.ximgproc.thinning` (Zhang-Suen skeletonization) used in `image_to_dxf_exact()`. Without it, the code falls back to Canny edges (double lines).
