# src/ — Core Library Modules

This directory contains the reusable library code for the tactile book generation pipeline.

## Module Overview

### `language_funcs.py`
Hebrew language utilities. Handles translation and Braille conversion.

**Key functions:**
- `hebrew_translator(text)` — Detects Hebrew input and translates to English
- `add_nikud(text)` — Interactively prompts for vowel marks (dagesh, holam, shuruk, hirik, shin dot)
- `convert_to_braille(text)` — Converts Hebrew text (with nikud) to Unicode Braille characters
- `letter_to_braille(base, marks)` — Maps a single letter + vowel marks to its Braille equivalent

**Note:** `add_nikud()` uses blocking `input()` calls, so it only works in CLI/notebook contexts, not in Gradio apps.

---

### `image_funcs.py`
Low-level image processing and PNG → DXF conversion.

**Key functions:**
- `image_to_dxf_exact(image_bw, out_path, canvas_cm=150)` — Converts a processed edge image to a DXF using polyline contours
- `png_to_dxf(png_path, dxf_path, canvas_cm=150)` — Converts any PNG to DXF by extracting and binarizing contours
- `plot_dxf(dxf_path)` — Quick matplotlib preview of a DXF file
- `convert_tensor_to_pil_img(tensor)` — Helper for torch tensors

**Output:** Each PNG becomes one DXF file with closed polylines.

---

### `image_generator.py`
Per-page image pipeline. Generates images via Stable Diffusion.

**Key functions:**
- `create_images(hebrew_prompt, picture_type, image_output_location, text_output_location, braille_output_location)` — Full pipeline:
  1. Loads Stable Diffusion (segmind/SSD-1B) on GPU or CPU
  2. Generates line-art image from Hebrew description
  3. Processes: edge detection → morphology → centering
  4. Saves three PNGs: image, Hebrew text, Braille text
- `images_to_dxf(image_location, text_location, braille_location)` — Converts all three PNGs to DXFs

**Output:** Three PNGs + three DXFs per page.

---

### `flow_manager.py`
Multi-page book orchestrator. Atomically processes pages and manages file output.

**Key class:**
- `FlowManager(book_name, pages, base_dir="books")` — Manages the full pipeline for a book
  - `run()` — Processes all pages; if a step fails, that page's state is not updated
  - Outputs land in `{base_dir}/{book_name}_{timestamp}/`
  - Returns `FlowResult` with image/STL locations

**Data models:**
- `PageState` — One page's metadata and file locations
- `FlowResult` — Result object with `pages_images` list and `stl_files` list

**Usage:**
```python
from src.flow_manager import FlowManager

pages = [
    {
        "page_number": 1,
        "image_description": "תפוח",
        "image_classification": "פרי",
        "generate_picture": True,
        "done": False,
    }
]

fm = FlowManager(book_name="my_book", pages=pages)
result = fm.run()
```

---

### `dxf_3d.py`
3D STL builder. Merges three DXFs (text, braille, image) into a single 3D model.

**Key function:**
- `create_one_page_stl_from_dxf(txt_dxf, braille_dxf, image_dxf, output=None, stroke_width=1.0, stroke_height=1.5, text_height=1.5, export_step=False)` — Builds the STL:
  1. Reads three DXFs
  2. Centers all content on a 150×150mm base plate
  3. Extrudes text as solid shapes (1.5mm height)
  4. Creates braille as spherical domes (height = radius × 0.5)
  5. Creates image as stroked ridges (1.0mm width × 1.5mm height)
  6. Exports to STL via CadQuery

**Constants (module-level):**
- `BASE_WIDTH / BASE_HEIGHT` — 150×150mm
- `BASE_THICKNESS` — 1.5mm
- `TEXT_SOLID_HEIGHT` — 1.5mm
- `IMAGE_STROKE_WIDTH / IMAGE_STROKE_HEIGHT` — 1.0mm / 1.5mm
- `DOME_HEIGHT_RATIO` — 0.5

**CLI usage:**
```bash
python src/dxf_3d.py --text text.dxf --braille braille.dxf --image image.dxf -o page1.stl
```

---

## Import Notes

All modules are imported from the root with the `src.` prefix:
```python
from src import language_funcs as lf
from src.dxf_3d import create_one_page_stl_from_dxf
```

Do not run scripts from inside `src/` — always run from the repo root.
