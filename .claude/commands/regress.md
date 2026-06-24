---
description: >-
  Run golden fixture invariants against the STL pipeline — parse saved fixtures and assert
  triangle counts, band presence, Z heights, and braille dot spacing haven't regressed. USE
  after geometry changes to catch silent regressions before HF deploy.
---

# /regress — golden fixture regression check

Validates that a known-good STL fixture still passes structural invariants. Catches silent
geometry regressions (changed extrusion heights, missing bands, dot spacing drift) without
running the full pipeline. Complements [[/stl-bench]] (which runs the live pipeline).

## Usage

```bash
# Check all saved fixtures in bench/fixtures/
python -c "import regress; regress.run_all()"

# Or check a specific STL against saved invariants
python -c "import regress; regress.check('bench/fixtures/hebrew_peh_dense.stl')"
```

## Fixture format — `bench/fixtures/<name>.json`

Save a golden fixture after a confirmed-good build:

```json
{
  "stl": "bench/fixtures/hebrew_peh_dense.stl",
  "n_triangles": 12840,
  "z_max": 3.0,
  "bands": {
    "text":    {"y_min": 117, "y_max": 140, "min_tris": 200},
    "image":   {"y_min":  37, "y_max": 113, "min_tris": 100},
    "braille": {"y_min":  10, "y_max":  33, "min_tris":  60}
  },
  "braille_dot_spacing_mm": [2.3, 2.7]
}
```

## Invariant checks

```python
import json, struct
from pathlib import Path

def check(fixture_path: str):
    spec = json.loads(Path(fixture_path).read_text())
    verts = _parse_stl(spec["stl"])

    # triangle count within ±5%
    n = len(verts) // 3
    assert abs(n - spec["n_triangles"]) / spec["n_triangles"] < 0.05, \
        f"tri count regressed: {n} vs golden {spec['n_triangles']}"

    # Z max
    zs = [v[2] for v in verts]
    assert max(zs) <= spec["z_max"] + 0.2, \
        f"Z_max regressed: {max(zs):.2f} vs golden {spec['z_max']}"

    # bands
    for band, b in spec["bands"].items():
        band_verts = [v for v in verts if b["y_min"] <= v[1] <= b["y_max"]]
        assert len(band_verts) >= b["min_tris"] * 3, \
            f"{band} band underpopulated: {len(band_verts)//3} tris (min {b['min_tris']})"

    # braille dot spacing (sample pairwise distances in braille band)
    br_verts = [v for v in verts if 10 <= v[1] <= 33]
    if br_verts and "braille_dot_spacing_mm" in spec:
        _check_dot_spacing(br_verts, spec["braille_dot_spacing_mm"])

    print(f"[OK] {Path(spec['stl']).name}: {n} tris, Z={max(zs):.2f}mm, all bands pass")

def _parse_stl(path: str):
    data = Path(path).read_bytes()
    n = struct.unpack_from("<I", data, 80)[0]
    verts = []
    for i in range(n):
        off = 84 + i * 50 + 12
        for j in range(3):
            verts.append(struct.unpack_from("<fff", data, off + j*12))
    return verts

def _check_dot_spacing(br_verts, spacing_range):
    import math
    # centroid of each z-peak cluster approximates dot centers
    # simple: just check min pairwise XY distance is in range
    pts = list({(round(v[0],1), round(v[1],1)) for v in br_verts})[:50]
    dists = []
    for i in range(len(pts)):
        for j in range(i+1, len(pts)):
            d = math.dist(pts[i], pts[j])
            if spacing_range[0]*0.5 < d < spacing_range[1]*3:
                dists.append(d)
    if dists:
        med = sorted(dists)[len(dists)//2]
        lo, hi = spacing_range
        assert lo <= med <= hi, f"braille dot spacing regressed: {med:.2f}mm (expected {lo}–{hi})"
```

## Saving a new fixture

After [[/stl-bench]] passes on a confirmed-good STL:

```python
import json, struct
from pathlib import Path

stl_path = "bench_out.stl"
verts = _parse_stl(stl_path)
fixture = {
    "stl": f"bench/fixtures/{name}.stl",
    "n_triangles": len(verts) // 3,
    "z_max": round(max(v[2] for v in verts), 2),
    "bands": {
        "text":    {"y_min": 117, "y_max": 140, "min_tris": len([v for v in verts if 117<=v[1]<=140])//3//2},
        "image":   {"y_min":  37, "y_max": 113, "min_tris": len([v for v in verts if 37<=v[1]<=113])//3//2},
        "braille": {"y_min":  10, "y_max":  33, "min_tris": len([v for v in verts if 10<=v[1]<=33])//3//2},
    },
    "braille_dot_spacing_mm": [2.3, 2.7],
}
Path(f"bench/fixtures/{name}.json").write_text(json.dumps(fixture, indent=2))
```

Store the `.stl` + `.json` pair under `bench/fixtures/` (gitignore the STL if large; keep
the JSON as the invariant record).
