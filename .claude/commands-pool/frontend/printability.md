---
description: >-
  Check whether the current page content will print correctly — text band length, watertight
  geometry indicators, plate size fit, estimated print time. Reads constraints from config.yaml
  (band fractions, plate mm). USE WHEN adding STL preview UX or implementing IMPROVEMENTS §3.
argument-hint: "[--stl PATH] [--text TEXT] [--lang hebrew|english]"
---

# /printability — browser-side printability check

Surfaces geometry constraints as user-facing UX (IMPROVEMENTS.md §3). The backend knows what
makes a page printable; this command exposes those invariants at the STL-preview step so the
user gets a warning before downloading, not after wasting filament.

**$ARGUMENTS** = `[--stl PATH] [--text TEXT] [--lang hebrew|english]`

## What makes a TOM page unprintable

All constants live in `config.yaml` (loaded via `src/config.py`). Check:

| Problem | Check | Fix |
|---|---|---|
| Text too long for band | `len(text) > ~20 chars` at 18mm plate | Shorten text |
| STL not watertight | negative Z verts or open edges | Geometry bug — [[tactile-stl-geometry]] |
| Out of plate bounds | any vertex outside `[0,W]×[0,H]` | Layout bug |
| Feature bands overlap | text Y range ∩ image Y range ≠ ∅ | config.yaml layout.* |
| Est. print time > threshold | `n_triangles > ~15000` → > 3 h | Too dense |

## Step 1 — parse config.yaml for live constraints

```python
import yaml, struct
from pathlib import Path

cfg = yaml.safe_load(Path('config.yaml').read_text())
W = cfg['plate']['width_mm']    # 150
H = cfg['plate']['height_mm']   # 150
margin = cfg['plate']['content_margin_mm']  # 10

layout = cfg['layout']
# Band y-ranges derived from layout fractions × (H - 2*margin)
content_h = H - 2 * margin   # 130
text_y0   = margin + content_h * layout['text']['y_start']
text_y1   = margin + content_h * layout['text']['y_end']
image_y0  = margin + content_h * layout['image']['y_start']
image_y1  = margin + content_h * layout['image']['y_end']
braille_y0= margin + content_h * layout['braille']['y_start']
braille_y1= margin + content_h * layout['braille']['y_end']

print(f"Plate: {W}×{H}mm, margin {margin}mm")
print(f"Bands: text=[{text_y0:.0f},{text_y1:.0f}] image=[{image_y0:.0f},{image_y1:.0f}] braille=[{braille_y0:.0f},{braille_y1:.0f}]")
```

## Step 2 — parse STL and run checks

```python
def parse_stl(path):
    data = Path(path).read_bytes()
    n = struct.unpack_from('<I', data, 80)[0]
    verts = []
    for i in range(n):
        off = 84 + i * 50 + 12
        for j in range(3):
            verts.append(struct.unpack_from('<fff', data, off + j*12))
    return verts, n

verts, n_tri = parse_stl(stl_path)
xs = [v[0] for v in verts]; ys = [v[1] for v in verts]; zs = [v[2] for v in verts]

warnings = []

# Plate fit
if min(xs) < 0 or max(xs) > W:
    warnings.append(f"X out of plate: [{min(xs):.1f}, {max(xs):.1f}]")
if min(ys) < 0 or max(ys) > H:
    warnings.append(f"Y out of plate: [{min(ys):.1f}, {max(ys):.1f}]")

# Watertight indicator: no negative Z
if min(zs) < 0:
    warnings.append(f"Negative Z ({min(zs):.2f}mm) — open geometry, may not slice correctly")

# Band presence
for band, (y0, y1), name in [
    (text_y0, text_y1, 'text'), (image_y0, image_y1, 'image'), (braille_y0, braille_y1, 'braille')
]:
    band_verts = [v for v in verts if y0 <= v[1] <= y1]
    if not band_verts:
        warnings.append(f"{name} band [{y0:.0f},{y1:.0f}] empty — layer missing from STL")

# Band overlap
if text_y0 < image_y1 and image_y0 < text_y1:
    warnings.append("text and image bands overlap — layout.* may be wrong")

# Print time estimate (rough: FDM at ~50mm/s, ~15k tris ≈ 3h)
est_h = n_tri / 5000
print(f"Triangles: {n_tri} (~{est_h:.1f}h estimated print time)")
if est_h > 4:
    warnings.append(f"Est. print time {est_h:.1f}h — very dense page, may exceed 3D printer limits")

# Text length
if text and len(text) > 20:
    warnings.append(f"Text length {len(text)} chars may overflow text band — test with /stl-bench")

if warnings:
    print("[WARN] Printability issues:")
    for w in warnings: print(f"  • {w}")
else:
    print("[OK] Page passes printability checks")
```

## Frontend UX integration (IMPROVEMENTS §3)

Once the checks are stable, surface them in the STL preview component:

```jsx
// web/src/components/StlViewer.jsx
// After STL loads, run printability check via a lightweight JS port
// of the geometry checks above, or a new /api/printability endpoint
<PrintabilityBadge warnings={printWarnings} />
```

The badge shows ✓ or ⚠ with plain-language explanations (no jargon — "the text might be too
long for the page" not "text band overflow"). Users can act before downloading.
