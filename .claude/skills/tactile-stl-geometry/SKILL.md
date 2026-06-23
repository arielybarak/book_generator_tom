---
name: tactile-stl-geometry
description: >-
  TOM tactile page geometry in config.yaml/src/dxf_3d.py — three layers (raised text,
  image ridges, Braille domes) must stay distinct and FDM-printable. USE WHEN changing
  dimensions, dome height, or debugging STL geometry.
---

# Tactile STL geometry

A page merges **three tactile layers** into one STL: raised Hebrew text, raised image line-art
ridges, and Braille hemisphere domes. Plate size and every height live in `config.yaml`
(CLAUDE.md lists the committed defaults) — this skill is about the *rules* that keep those
numbers printable and legible, not the numbers themselves.

## When to Activate This Skill
- "change the dome height", "make the strokes thicker", "plate size", "layer too short/tall"
- Editing geometry, debugging an STL that won't print or whose layers feel indistinct
- Touching `config.yaml`, `src/dxf_3d.py`, or the lithophane heightmap path

## The one move that matters
**Change geometry in `config.yaml`, never the constants in code.** The module-level names in
`src/dxf_3d.py` (`BASE_THICKNESS`, `TEXT_SOLID_HEIGHT`, `IMAGE_STROKE_WIDTH/HEIGHT`,
`DOME_HEIGHT_RATIO`, the `geometry.*` tolerances) are **read from `cfg`** via
`from src.config import cfg` — editing the Python assignment is pointless. Map:
`plate.thickness_mm`, `text.extrusion_height_mm`, `image_strokes.width_mm`/`height_mm`,
`braille.dome_height_ratio`. After editing `config.yaml`, **run `./sync_to_space.sh` to deploy**
(see [[hf-space-sync-deploy]]).

## Two STL backends read DIFFERENT config sections
- **CadQuery** (`src/dxf_3d.py` → `create_one_page_stl_from_dxf()`, used by `gradio_app.py` + the CLI) reads `plate` / `text` / `image_strokes` / `braille` / `geometry`.
- **Lithophane heightmap** (`gradio_app_lithophane.py`, the **currently deployed** app) reads the `lithophane:` section (`resolution_px`, `base_thickness_mm`, `relief_height_mm`, `layout`, `levels`) — no CadQuery, just a grayscale heightmap meshed directly.
- **Edit the section the deployed app actually uses.** Changing `image_strokes.height_mm` does nothing to the lithophane STL; change `lithophane.levels.image` instead.

## Printability gotchas (where geometry goes wrong)
- `image_strokes.width_mm` has a **~1 mm FDM floor** — thinner strokes won't print as solid ridges.
- **Braille must rise above text and image.** Text and image ridges share a height *by design* — they're kept apart by spatial bands (lithophane `layout`), so equal text/image height is fine. The Braille layer is the child's reading surface and must stand taller: `braille.dome_height_ratio` on the CadQuery path, and `lithophane.levels.braille` **>** `levels.text`/`levels.image` on the deployed app. If Braille collapses to the others' height a blind reader can't find it — that's a correctness bug, not cosmetic.
- CLI per-run overrides exist (`python src/dxf_3d.py --stroke-width/--stroke-height/--text-height …`) but they're for experiments; persist a real change in `config.yaml`.
- `geometry.*` (point/clipper tolerances, `pyclipper_scale`, `skeletonization_min_area_px`, `polygon_simplification_epsilon`) affect mesh fidelity — change only deliberately.
