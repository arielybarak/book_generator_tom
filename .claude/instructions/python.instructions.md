---
description: Python coding conventions for this project
globs: ["**/*.py"]
alwaysApply: false
---

## Import convention

All `src/` imports use the `src.` prefix. Always run scripts from the repo root:

```python
from src import language_funcs as lf
from src.image_funcs import ensure_font, process_image_to_dxf
```

## Dependencies

- Use `opencv-contrib-python`, **not** `opencv-python` — the contrib build includes `cv2.ximgproc.thinning` (Zhang-Suen skeletonization) used in `image_to_dxf_exact()`. Without it, the code falls back to Canny edges (double lines).

## Style

- Formatter and linter: `ruff` for both. Run `ruff format` and `ruff check --fix`.
- Type hints on every public function (arguments and return type).
- Use modern syntax: `list[str]`, `X | None` — not `List[str]`, `Optional[X]`.
- No wildcard imports (`from module import *`).

## Design

- Default to functions over classes. Use a class only when you have genuine internal state that multiple instances need.
- Prefer composition over inheritance.
- Keep modules focused — avoid God Objects that mix I/O, business logic, and presentation.
