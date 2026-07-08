---
description: >-
  Generate a TOM tactile page via FlowManager (SD→DXF→STL) or dxf_3d.py CLI. USE WHEN
  creating or testing a page locally.
argument-hint: "<hebrew text> | <image description>"
---

Generate a tactile storybook page for: **$ARGUMENTS** (format: `<hebrew text> | <image description>`).

Pick the right entry point:

**A. Full pipeline (text → image → DXFs → STL), one or more pages → use `FlowManager`.**
`src/flow_manager.py` runs the whole pipeline and writes to `books/{book_name}_{timestamp}/`.
Pages are atomic — if a step throws, that page's state isn't updated. Construct pages as dicts and run:
```python
from src.flow_manager import FlowManager
pages = [{
    "page_number": 1,
    "image_description": "<from $ARGUMENTS>",
    "image_classification": "<object class>",
    "generate_picture": True,
    "done": False,
}]
FlowManager("my_book", pages).run()
```
Run from the **repo root** (imports use the `src.` prefix). This needs SD weights + GPU and will
download the Braille font on first run (see [[image-dxf-generation]]).

**B. STL only, from three existing DXFs → use the CLI** (no SD, fast, good for geometry iteration):
```bash
python src/dxf_3d.py --text text.dxf --braille braille.dxf --image image.dxf -o page.stl
```
Per-run geometry overrides: `--stroke-width`, `--stroke-height`, `--text-height` (persist real
changes in `config.yaml` instead — see [[tactile-stl-geometry]]).

Confirm which path fits the request, state the expected output location, then run it. Don't change
`config.yaml` or `src/` as a side effect; if you do, remind to `/deploy-hf`.
