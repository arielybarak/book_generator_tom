---
description: >-
  Offline bench for the tactile STL pipeline — runs per-stage timing, parses the binary STL
  (bbox/band/braille validation), and catches OCCT segfaults via subprocess isolation. No GPU,
  no deploy needed. USE before pushing to HF to confirm geometry is correct after src/ edits.
---

# /stl-bench — offline STL pipeline bench

Runs the full generation pipeline locally (CPU-only, no GPU, no deploy) and validates the
output STL structurally. Use after editing `src/image_funcs.py`, `src/dxf_3d.py`,
`src/language_funcs.py`, or `config.yaml` — before `./sync_to_space.sh` and HF push.

## Flags

```
--lang   hebrew | english          (default: hebrew)
--text   "TEXT"                    Hebrew or English string to render
--image  PATH                      PNG/JPG for the image band (optional; uses placeholder if omitted)
--time-budget  SECONDS             Fail if total pipeline exceeds this (default: 120)
```

## What it runs (per-stage timing)

```python
import time, subprocess, struct
from pathlib import Path
from src.image_funcs import image_to_dxf_exact, generate_text_dxf, generate_braille_dxf_from_text
from src.dxf_3d import create_one_page_stl_from_dxf
from src.language_funcs import text_to_braille

t0 = time.perf_counter()

# Stage 1: text DXF
generate_text_dxf(text, "bench_text.dxf", rtl=(lang == "hebrew"))
print(f"[t] text DXF: {time.perf_counter()-t0:.1f}s")

# Stage 2: braille DXF
braille_str = text_to_braille(text, lang)
generate_braille_dxf_from_text(braille_str, "bench_braille.dxf")
print(f"[t] braille DXF: {time.perf_counter()-t0:.1f}s")

# Stage 3: image DXF (subprocess — segfault-safe)
r = subprocess.run(
    ["python", "-c",
     "from src.image_funcs import image_to_dxf_exact; import cv2; "
     f"img=cv2.imread('{image_path}',0); image_to_dxf_exact(img,'bench_image.dxf')"],
    timeout=60
)
if r.returncode in (-11, 139):
    print("[WARN] image DXF: SIGSEGV — using empty placeholder")
else:
    print(f"[t] image DXF: {time.perf_counter()-t0:.1f}s")

# Stage 4: STL assembly (subprocess — segfault-safe, key rule: no boolean union)
r = subprocess.run(
    ["python", "-c",
     "from src.dxf_3d import create_one_page_stl_from_dxf; "
     "create_one_page_stl_from_dxf('bench_text.dxf','bench_braille.dxf','bench_image.dxf','bench_out.stl')"],
    timeout=120
)
if r.returncode in (-11, 139):
    print("[FAIL] STL assembly SIGSEGV — OCCT crash (check taper/boolean union)")
    raise SystemExit(1)
print(f"[t] STL assembly: {time.perf_counter()-t0:.1f}s")

total = time.perf_counter() - t0
print(f"[t] total: {total:.1f}s")
if total > time_budget:
    print(f"[FAIL] exceeds --time-budget {time_budget}s — boolean union crept in?")
```

## Binary STL validation

After the pipeline, parse `bench_out.stl` and assert:

```python
def parse_stl(path: str):
    data = Path(path).read_bytes()
    # 80-byte header, uint32 tri count, then N × (12-byte normal + 3×12-byte verts + 2-byte attr)
    n_tri = struct.unpack_from("<I", data, 80)[0]
    expected = 80 + 4 + n_tri * 50
    assert len(data) == expected, f"STL truncated: expected {expected}B got {len(data)}B"
    verts = []
    for i in range(n_tri):
        off = 84 + i * 50 + 12          # skip normal
        for j in range(3):
            x, y, z = struct.unpack_from("<fff", data, off + j*12)
            verts.append((x, y, z))
    return verts

verts = parse_stl("bench_out.stl")
xs = [v[0] for v in verts]; ys = [v[1] for v in verts]; zs = [v[2] for v in verts]

# Plate-fit: all verts within [0,150]×[0,150] (10mm margin bands included)
assert 0 <= min(xs) and max(xs) <= 150, f"X out of plate: [{min(xs):.1f}, {max(xs):.1f}]"
assert 0 <= min(ys) and max(ys) <= 150, f"Y out of plate: [{min(ys):.1f}, {max(ys):.1f}]"

# Band presence: triangles in each band y-range (from config.yaml layout.*)
# text≈[117,140], image≈[37,113], braille≈[10,33] for 150mm plate / 10mm margin
text_verts   = [v for v in verts if 117 <= v[1] <= 140]
image_verts  = [v for v in verts if  37 <= v[1] <= 113]
braille_verts= [v for v in verts if  10 <= v[1] <=  33]
assert text_verts,    "[FAIL] no triangles in text band [117,140]"
assert image_verts,   "[FAIL] no triangles in image band [37,113]"
assert braille_verts, "[FAIL] no triangles in braille band [10,33]"
print(f"[OK] bands populated: text={len(text_verts)} img={len(image_verts)} br={len(braille_verts)} tris")

# Z sanity: max height ≤ base_thickness (1.5) + tallest feature (~3mm)
assert max(zs) <= 5.0, f"Z too tall: {max(zs):.2f}mm — extrusion constant changed?"
print(f"[OK] STL valid: {len(verts)//3} triangles, Z_max={max(zs):.2f}mm")
```

## Performance interpretation

| Total time | Diagnosis |
|---|---|
| < 30 s | Normal (sparse page) |
| 60–80 s | Normal (dense Hebrew, ~560 paths) |
| > 2 min | Boolean union crept back — find the `.union()` / `.fuse()` call |
| Hangs indefinitely | O(N²) boolean — kill and fix before deploying |

OCCT segfaults: see [[occt-crash-isolation]]. Geometry rules: [[tactile-stl-geometry]].
