"""
Lithophane-style STL generation (experimental, CadQuery-free).

Ports the heightmap->mesh idea used by the open-source 3dp.rocks/lithophane tool
into Python: a grayscale image is treated as a height field (pixel brightness ->
Z height) and turned directly into a watertight STL solid. No CadQuery, no
external website.

Polarity here is OUR convention, not the lithophane "dark = thick" one:
positive relief — background (gray 0) is the flat base, brighter pixels are taller.

Two steps:
  compose_heightmap()  -- flatten the three page layers (line-art image, Hebrew
                          text, Braille) into ONE grayscale heightmap, each layer
                          painted at its own gray level (= its target height).
  heightmap_to_stl()   -- height field -> watertight triangle mesh -> binary STL.

Used by hf_space/gradio_app_lithophane.py (the experimental app variant).
"""
import os
import struct
import numpy as np
import cv2
import matplotlib
matplotlib.use("Agg")  # headless, thread-safe
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
import matplotlib.font_manager as fm

from src.image_funcs import ensure_font, FONT_FILENAME


# ── Layer rasterization ──────────────────────────────────────────────────────────

def _render_text_mask(text, fontprop, width_px, height_px):
    """
    Render `text` centered on a generous canvas, then downscale to (height_px,
    width_px). Returns a boolean ink mask. `fontprop` is a matplotlib
    FontProperties (use fname=... for the Braille font for robust resolution).
    Rendering big then resizing avoids text overflowing a thin target strip.
    """
    rw, rh = 1000, 300
    fig = Figure(figsize=(rw / 100.0, rh / 100.0), dpi=100, facecolor="white")
    ax = fig.add_subplot(111)
    ax.set_facecolor("white")
    ax.text(0.5, 0.5, text, fontsize=120, color="black",
            ha="center", va="center", fontproperties=fontprop)
    ax.axis("off")
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    canvas = FigureCanvasAgg(fig)
    canvas.draw()
    rgba = np.asarray(canvas.buffer_rgba())              # rh x rw x 4
    gray = cv2.cvtColor(rgba, cv2.COLOR_RGBA2GRAY)
    ink = ((gray < 128).astype(np.uint8)) * 255          # ink = dark pixels
    ink = cv2.resize(ink, (width_px, height_px), interpolation=cv2.INTER_AREA)
    return ink > 127



def compose_heightmap(text_img: np.ndarray, drawing_img: np.ndarray, braille_img: np.ndarray, layout_info: dict,
                      canvas_shape: tuple) -> np.ndarray:
    """משלבת את כל האלמנטים למפת גבהים אחת תוך התאמה מלאה לשטח התמונה המעודכן."""
    canvas = np.zeros(canvas_shape, dtype=np.float32)

    # 1. טקסט עליון
    tx, ty, tw, th = layout_info['text_bbox_px']
    if text_img is not None and text_img.size > 0:
        canvas[ty:ty + th, tx:tx + tw] = cv2.resize(text_img, (tw, th))

    # 2. ציור מרכזי
    ix, iy, iw, ih = layout_info['image_bbox_px']
    if drawing_img is not None and drawing_img.size > 0:
        canvas[iy:iy + ih, ix:ix + iw] = cv2.resize(drawing_img, (iw, ih))

    # 3. ברייל תחתון
    bx, by, bw, bh = layout_info['braille_bbox_px']
    if braille_img is not None and braille_img.size > 0:
        canvas[by:by + bh, bx:bx + bw] = cv2.resize(braille_img, (bw, bh))

    return canvas


# ── Heightmap → watertight binary STL ────────────────────────────────────────────

_STL_DTYPE = np.dtype([
    ("normal", "<3f4"),
    ("v0", "<3f4"), ("v1", "<3f4"), ("v2", "<3f4"),
    ("attr", "<u2"),
])


def _quads_to_tris(a, b, c, d):
    """Two triangles (a,b,c) and (a,c,d) for each quad. Inputs are (M,3) arrays."""
    return np.concatenate([
        np.stack([a, b, c], axis=1),
        np.stack([a, c, d], axis=1),
    ], axis=0)


def _write_binary_stl(path, tris):
    """tris: (T, 3, 3) float array of triangle vertices → binary STL file."""
    v0, v1, v2 = tris[:, 0], tris[:, 1], tris[:, 2]
    normals = np.cross(v1 - v0, v2 - v0)
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    lengths[lengths == 0] = 1.0
    normals = normals / lengths

    data = np.zeros(len(tris), dtype=_STL_DTYPE)
    data["normal"] = normals
    data["v0"], data["v1"], data["v2"] = v0, v1, v2

    with open(path, "wb") as f:
        f.write(b"\0" * 80)                      # 80-byte header
        f.write(struct.pack("<I", len(tris)))    # triangle count
        data.tofile(f)


def heightmap_to_stl(heightmap, out_path, cfg):
    """
    Convert a grayscale heightmap (NxN uint8) into a watertight binary STL solid.

    z = base_thickness + (gray/255) * relief_height. XY spans the plate size.
    """
    lc    = cfg["lithophane"]
    plate = cfg["plate"]
    base   = float(lc["base_thickness_mm"])
    relief = float(lc["relief_height_mm"])
    w_mm   = float(plate["width_mm"])
    h_mm   = float(plate["height_mm"])

    # Heightmap rows go top→bottom (image convention), but we map row→Y which
    # points UP in the STL. Without flipping, the relief comes out vertically
    # inverted (Hebrew text upside-down) in every STL viewer/slicer. Flip rows so
    # heightmap-top → +Y-top: text reads upright, layout stays text-top/braille-bottom.
    hm = np.flipud(heightmap).astype(np.float64)
    rows, cols = hm.shape

    xs = np.linspace(0.0, w_mm, cols)
    ys = np.linspace(0.0, h_mm, rows)
    X, Y = np.meshgrid(xs, ys)                   # (rows, cols)
    Z = base + (hm / 255.0) * relief

    top = np.stack([X, Y, Z], axis=-1)                       # (rows, cols, 3)
    bot = np.stack([X, Y, np.zeros_like(Z)], axis=-1)

    # Quad corners must be passed in CYCLIC boundary order (not diagonal order),
    # otherwise adjacent cells don't share grid edges and the mesh isn't closed.

    # Top surface (faces up): t00 → t01 → t11 → t10 (CCW from above)
    t00 = top[:-1, :-1].reshape(-1, 3); t01 = top[:-1, 1:].reshape(-1, 3)
    t11 = top[1:, 1:].reshape(-1, 3);   t10 = top[1:, :-1].reshape(-1, 3)
    top_tris = _quads_to_tris(t00, t01, t11, t10)

    # Bottom plane (faces down — reverse order)
    b00 = bot[:-1, :-1].reshape(-1, 3); b01 = bot[:-1, 1:].reshape(-1, 3)
    b11 = bot[1:, 1:].reshape(-1, 3);   b10 = bot[1:, :-1].reshape(-1, 3)
    bot_tris = _quads_to_tris(b00, b10, b11, b01)

    # Four side walls (each quad in cyclic order, stitching top edge to bottom edge)
    walls = np.concatenate([
        _quads_to_tris(top[:-1, 0],  top[1:, 0],   bot[1:, 0],  bot[:-1, 0]),   # left  (j=0)
        _quads_to_tris(top[:-1, -1], bot[:-1, -1], bot[1:, -1], top[1:, -1]),   # right (j=-1)
        _quads_to_tris(top[0, :-1],  bot[0, :-1],  bot[0, 1:],  top[0, 1:]),    # front (i=0)
        _quads_to_tris(top[-1, :-1], top[-1, 1:],  bot[-1, 1:], bot[-1, :-1]),  # back  (i=-1)
    ], axis=0)

    tris = np.concatenate([top_tris, bot_tris, walls], axis=0)
    _write_binary_stl(out_path, tris)
    return out_path
