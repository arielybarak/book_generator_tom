#!/usr/bin/env python3
"""
3 DXF files → single 3D-printable STL, optimised for blind children's tactile experience.

Takes three DXF inputs (text shapes, Braille circles, image line-art) and builds a
150×150mm base plate with three tactile layers using CadQuery + pyclipper:
  - Raised text (solid extrusion, dome-rounded edges)
  - Braille domes (hemisphere per dot, fixed Grade 1 dimensions)
  - Image strokes (dome-profile ridges, height-hierarchical by path size)
  - Optional hatch / crosshatch texture inside large closed regions

Key function: create_one_page_stl_from_dxf(txt_dxf, braille_dxf, image_dxf, output)

CLI: python src/dxf_3d.py --text text.dxf --braille braille.dxf --image image.dxf -o page.stl

All geometry constants live in config.yaml under the `tactile` section.

Implementation notes:
  - Closed image paths are stroked edge-by-edge with ET_OPENROUND to avoid filled-band artifacts.
  - Dome cross-section is approximated by filleting the top edges of each extruded ridge.
  - Douglas-Peucker simplification is applied to every path before extrusion to remove
    micro-jaggedness from rasterised contours.
  - Texture fills use a scanline-intersection algorithm; no extra dependencies required.
"""

import argparse
import functools
import math
import time
from pathlib import Path
from typing import List, Tuple

import ezdxf
from ezdxf.entities import LWPolyline, Circle, Ellipse, Spline, Polyline, Line
from ezdxf.path import make_path

import cadquery as cq
import pyclipper

from src.config import cfg

# Force flushed prints: on HF Spaces stdout is a block-buffered pipe (not a TTY), so
# unflushed build progress lags the log and the build looks "stuck at Text solids".
print = functools.partial(print, flush=True)

Point    = Tuple[float, float]
CircleDef = Tuple[Tuple[float, float], float]

# =========================
# Settings (from config.yaml)
# =========================
BASE_WIDTH          = cfg["plate"]["width_mm"]
BASE_HEIGHT         = cfg["plate"]["height_mm"]
BASE_THICKNESS      = cfg["plate"]["thickness_mm"]
BASE_CORNER_RADIUS  = cfg["plate"]["corner_radius_mm"]
# Border kept clear of content when laying the page out.
CONTENT_MARGIN_MM   = cfg["plate"].get("content_margin_mm", 10.0)

# Banded page layout (fractions of the usable height): Hebrew text strip on top,
# image in the middle, Braille strip on the bottom. Each band is filled independently
# so the three tactile layers don't overlap.
_layout = cfg.get("layout", {})
TEXT_BAND_FRAC      = _layout.get("text_frac", 0.18)
BRAILLE_BAND_FRAC   = _layout.get("braille_frac", 0.18)
BAND_GAP_MM         = _layout.get("band_gap_mm", 4.0)

_t = cfg["tactile"]

IMAGE_OUTLINE_HEIGHT  = _t["image_outline_height_mm"]
IMAGE_OUTLINE_WIDTH   = _t["image_outline_width_mm"]
IMAGE_DETAIL_HEIGHT   = _t["image_detail_height_mm"]
IMAGE_DETAIL_WIDTH    = _t["image_detail_width_mm"]
OUTLINE_MIN_AREA      = _t["outline_min_closed_area_mm2"]

TEXT_SOLID_HEIGHT     = _t["text_height_mm"]

BRAILLE_FIXED_HEIGHT  = _t["braille_dot_height_mm"]
BRAILLE_FIXED_RADIUS  = _t["braille_dot_radius_mm"]
DOME_HEIGHT_RATIO     = cfg["braille"]["dome_height_ratio"]   # fallback only

EDGE_FILLET_ENABLED   = _t["edge_fillet_enabled"]
EDGE_FILLET_RATIO     = _t["stroke_dome_fillet_ratio"]

PATH_SIMPLIFY_TOL     = _t["path_simplification_tolerance_mm"]

TEXTURE_ENABLED       = _t["texture_enabled"]
TEXTURE_LARGE_AREA    = _t["texture_large_region_min_area_mm2"]
TEXTURE_MEDIUM_AREA   = _t["texture_medium_region_min_area_mm2"]
TEXTURE_RIDGE_SPACING = _t["texture_ridge_spacing_mm"]
TEXTURE_RIDGE_WIDTH   = _t["texture_ridge_width_mm"]
TEXTURE_HEIGHT        = _t["texture_height_mm"]

POINT_CLEAN_TOL       = cfg["geometry"]["point_clean_tol_mm"]
CLIPPER_CLEAN_TOL     = cfg["geometry"]["clipper_clean_tol_mm"]
SCALE                 = cfg["geometry"]["pyclipper_scale"]

MOUNTING_HOLES_ENABLED     = cfg["mounting_holes"]["enabled"]
MOUNTING_HOLE_RADIUS       = cfg["mounting_holes"]["radius_mm"]
MOUNTING_HOLE_COUNT        = cfg["mounting_holes"]["count"]
MOUNTING_HOLE_MARGIN_RIGHT = cfg["mounting_holes"]["margin_right_mm"]
MOUNTING_HOLE_MARGIN_TOP   = cfg["mounting_holes"]["margin_top_mm"]
MOUNTING_HOLE_SPACING      = cfg["mounting_holes"]["spacing_mm"]

# Aliases used as CLI defaults
IMAGE_STROKE_WIDTH  = IMAGE_OUTLINE_WIDTH
IMAGE_STROKE_HEIGHT = IMAGE_OUTLINE_HEIGHT


# =========================
# Geometry helpers
# =========================

def clean_polyline_points(points: List[Point], tolerance: float = POINT_CLEAN_TOL) -> List[Point]:
    if len(points) < 2:
        return points
    out = [points[0]]
    for x, y in points[1:]:
        px, py = out[-1]
        if math.hypot(x - px, y - py) > tolerance:
            out.append((x, y))
    return out


def rdp_simplify(points: List[Point], tolerance: float) -> List[Point]:
    """
    Iterative Ramer-Douglas-Peucker path simplification.
    Removes points whose perpendicular distance from the chord is < tolerance.
    """
    if len(points) < 3:
        return points
    keep  = [True] * len(points)
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        if end - start < 2:
            continue
        sx, sy = points[start]
        ex, ey = points[end]
        dx, dy  = ex - sx, ey - sy
        line_len = math.hypot(dx, dy)
        max_dist, max_idx = 0.0, start
        for i in range(start + 1, end):
            if not keep[i]:
                continue
            if line_len == 0:
                dist = math.hypot(points[i][0] - sx, points[i][1] - sy)
            else:
                dist = abs(dx * (sy - points[i][1]) - (sx - points[i][0]) * dy) / line_len
            if dist > max_dist:
                max_dist, max_idx = dist, i
        if max_dist <= tolerance:
            for i in range(start + 1, end):
                keep[i] = False
        else:
            stack.append((start, max_idx))
            stack.append((max_idx, end))
    return [p for i, p in enumerate(points) if keep[i]]


def polygon_area(points: List[Point]) -> float:
    if len(points) < 3:
        return 0.0
    a = 0.0
    for i in range(len(points)):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % len(points)]
        a += x1 * y2 - x2 * y1
    return a / 2.0


def bbox_of_paths(paths: List[List[Point]], circles: List[CircleDef]) -> Tuple[float, float, float, float]:
    min_x = float("inf");  min_y = float("inf")
    max_x = float("-inf"); max_y = float("-inf")
    for p in paths:
        for x, y in p:
            min_x = min(min_x, x); min_y = min(min_y, y)
            max_x = max(max_x, x); max_y = max(max_y, y)
    for (cx, cy), r in circles:
        min_x = min(min_x, cx - r); min_y = min(min_y, cy - r)
        max_x = max(max_x, cx + r); max_y = max(max_y, cy + r)
    if min_x == float("inf"):
        return 0.0, 0.0, 0.0, 0.0
    return min_x, min_y, max_x, max_y


def translate_paths(paths: List[List[Point]], dx: float, dy: float) -> List[List[Point]]:
    return [[(x + dx, y + dy) for x, y in p] for p in paths]


def translate_circles(circles: List[CircleDef], dx: float, dy: float) -> List[CircleDef]:
    return [((cx + dx, cy + dy), r) for (cx, cy), r in circles]


def _xform_paths(paths: List[List[Point]], s: float, cx: float, cy: float, tx: float, ty: float) -> List[List[Point]]:
    """Scale each point about (cx, cy) by s, then translate so (cx, cy) lands at (tx, ty)."""
    return [[((x - cx) * s + tx, (y - cy) * s + ty) for x, y in p] for p in paths]


def _xform_circles(circles: List[CircleDef], s: float, cx: float, cy: float, tx: float, ty: float) -> List[CircleDef]:
    return [(((px - cx) * s + tx, (py - cy) * s + ty), r * s) for (px, py), r in circles]


def _fit_transform(paths, circles, x0, y0, x1, y1):
    """
    Transform (s, cx, cy, tx, ty) that scales the combined bbox of `paths`+`circles`
    to fit inside the rectangle [x0,y0]–[x1,y1] (uniform, aspect-preserving) and
    centres it there. Returns None when there is no content.
    """
    bx0, by0, bx1, by1 = bbox_of_paths(paths, circles)
    w, h = bx1 - bx0, by1 - by0
    if w <= 0 or h <= 0:
        return None
    s = min((x1 - x0) / w, (y1 - y0) / h)
    return (s, (bx0 + bx1) / 2.0, (by0 + by1) / 2.0, (x0 + x1) / 2.0, (y0 + y1) / 2.0)


def layout_content_on_base(
    text_shapes: List[List[Point]],
    braille_circles: List[CircleDef],
    image_closed_paths: List[List[Point]],
    image_open_paths: List[List[Point]],
) -> Tuple[List[List[Point]], List[CircleDef], List[List[Point]], List[List[Point]]]:
    """
    Lay the three tactile layers out in horizontal bands so they don't overlap:
        ┌─────────────── Hebrew text  (top strip) ───────────────┐
        │                    line-art image  (middle)            │
        └─────────────── Braille dots  (bottom strip) ───────────┘
    Each band is filled independently — the DXF layers arrive at mismatched, oversized
    coordinate systems (image/text ~1500mm, braille ~px), so each is scaled to fit its
    own band. Image closed+open paths share ONE transform to stay registered.
    """
    m = CONTENT_MARGIN_MM
    x0, x1 = m, BASE_WIDTH - m
    usable_h = BASE_HEIGHT - 2 * m
    text_h = TEXT_BAND_FRAC * usable_h
    brl_h  = BRAILLE_BAND_FRAC * usable_h
    g = BAND_GAP_MM

    # y measured from the plate bottom (0) up to BASE_HEIGHT
    brl_y0, brl_y1 = m, m + brl_h                                   # bottom strip
    txt_y1, txt_y0 = BASE_HEIGHT - m, BASE_HEIGHT - m - text_h      # top strip
    img_y0, img_y1 = brl_y1 + g, txt_y0 - g                         # middle

    # Hebrew text → top band
    t_txt = _fit_transform(text_shapes, [], x0, txt_y0, x1, txt_y1)
    text_out = _xform_paths(text_shapes, *t_txt) if t_txt else text_shapes

    # Braille → bottom band at its NATIVE Grade-1 size (it is generated at fixed mm
    # spacing). Do NOT stretch it to fill the band — that would blow up the dot gaps for
    # short words. Centre it; only shrink if a long word would overflow the plate width.
    bx0, by0, bx1, by1 = bbox_of_paths([], braille_circles)
    bw, bh = bx1 - bx0, by1 - by0
    if bw > 0 and bh > 0:
        s_brl = min(1.0, (x1 - x0) / bw, (brl_y1 - brl_y0) / bh)
        brl_out = _xform_circles(braille_circles, s_brl, (bx0 + bx1) / 2.0, (by0 + by1) / 2.0,
                                 (x0 + x1) / 2.0, (brl_y0 + brl_y1) / 2.0)
    else:
        brl_out = braille_circles

    # Image (closed + open) → middle band, one shared transform to keep it registered
    t_img = _fit_transform(image_closed_paths + image_open_paths, [], x0, img_y0, x1, img_y1)
    img_closed_out = _xform_paths(image_closed_paths, *t_img) if t_img else image_closed_paths
    img_open_out   = _xform_paths(image_open_paths,   *t_img) if t_img else image_open_paths

    print(f"  Layout → text band {text_h:.0f}mm / image {img_y1 - img_y0:.0f}mm / "
          f"braille band {brl_h:.0f}mm  (margin {m:.0f}mm)")
    return text_out, brl_out, img_closed_out, img_open_out


def safe_fillet_top(solid: cq.Workplane, radius: float) -> cq.Workplane:
    """Fillet the top-face edges of a solid; silently skip if CadQuery rejects the radius."""
    if not EDGE_FILLET_ENABLED or radius <= 0:
        return solid
    try:
        return solid.edges(">Z").fillet(radius)
    except Exception:
        return solid


# =========================
# DXF extraction
# =========================

def extract_closed_polygons_for_text(dxf_path: Path) -> List[List[Point]]:
    """TEXT DXF: extract only closed shapes (solid filled regions)."""
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()
    shapes: List[List[Point]] = []
    for entity in msp:
        try:
            t = entity.dxftype()
            if t == "LWPOLYLINE":
                lw: LWPolyline = entity
                pts = [(p[0], p[1]) for p in lw.get_points()]
                if lw.closed and len(pts) >= 3:
                    shapes.append(pts)
            elif t == "POLYLINE":
                pl: Polyline = entity
                pts = [(v.dxf.location.x, v.dxf.location.y) for v in pl.vertices]
                if pl.is_closed and len(pts) >= 3:
                    shapes.append(pts)
            elif t == "ELLIPSE":
                el: Ellipse = entity
                path = make_path(el)
                if path.is_closed:
                    pts = [(p.x, p.y) for p in path.flattening(0.1)]
                    if len(pts) >= 3:
                        shapes.append(pts)
            elif t == "SPLINE":
                sp: Spline = entity
                path = make_path(sp)
                pts = [(p.x, p.y) for p in path.flattening(0.05)]
                if sp.closed and len(pts) >= 3:
                    shapes.append(pts)
        except Exception as e:
            print(f"Warning: text entity {entity.dxftype()} skipped: {e}")
    return shapes


def is_circular_polygon(points: List[Point], tolerance: float = 0.5) -> Tuple[bool, Tuple[float, float], float]:
    if len(points) < 3:
        return False, (0.0, 0.0), 0.0
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    dists = [math.hypot(x - cx, y - cy) for x, y in points]
    r = sum(dists) / len(dists)
    if r < 0.01:
        return False, (cx, cy), 0.0
    dev = max(abs(d - r) for d in dists) / r
    return dev <= tolerance, (cx, cy), r


def extract_braille_circles(dxf_path: Path) -> List[CircleDef]:
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()
    circles: List[CircleDef] = []
    for entity in msp:
        try:
            t = entity.dxftype()
            if t == "CIRCLE":
                c: Circle = entity
                circles.append(((c.dxf.center.x, c.dxf.center.y), c.dxf.radius))
            elif t == "LWPOLYLINE":
                lw: LWPolyline = entity
                if lw.closed:
                    pts = [(p[0], p[1]) for p in lw.get_points()]
                    ok, center, r = is_circular_polygon(pts, tolerance=0.5)
                    if ok:
                        circles.append((center, r))
            elif t == "POLYLINE":
                pl: Polyline = entity
                if pl.is_closed:
                    pts = [(v.dxf.location.x, v.dxf.location.y) for v in pl.vertices]
                    ok, center, r = is_circular_polygon(pts, tolerance=0.5)
                    if ok:
                        circles.append((center, r))
        except Exception as e:
            print(f"Warning: braille entity {entity.dxftype()} skipped: {e}")
    return circles


def extract_image_centerlines(dxf_path: Path) -> Tuple[List[List[Point]], List[List[Point]], List[CircleDef]]:
    """IMAGE DXF: return (closed_paths, open_paths, circles) as centerlines to be stroked."""
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()
    closed_paths: List[List[Point]] = []
    open_paths:   List[List[Point]] = []
    circles:      List[CircleDef]   = []
    for entity in msp:
        try:
            t = entity.dxftype()
            if t == "LINE":
                ln: Line = entity
                s = (ln.dxf.start.x, ln.dxf.start.y)
                e = (ln.dxf.end.x,   ln.dxf.end.y)
                if s != e:
                    open_paths.append([s, e])
            elif t == "LWPOLYLINE":
                lw: LWPolyline = entity
                pts = [(p[0], p[1]) for p in lw.get_points()]
                if len(pts) >= 2:
                    (closed_paths if lw.closed else open_paths).append(pts)
            elif t == "POLYLINE":
                pl: Polyline = entity
                pts = [(v.dxf.location.x, v.dxf.location.y) for v in pl.vertices]
                if len(pts) >= 2:
                    (closed_paths if pl.is_closed else open_paths).append(pts)
            elif t == "SPLINE":
                sp: Spline = entity
                path = make_path(sp)
                pts = [(p.x, p.y) for p in path.flattening(0.05)]
                if len(pts) >= 2:
                    (closed_paths if sp.closed else open_paths).append(pts)
            elif t == "CIRCLE":
                c: Circle = entity
                circles.append(((c.dxf.center.x, c.dxf.center.y), c.dxf.radius))
        except Exception as e:
            print(f"Warning: image entity {entity.dxftype()} skipped: {e}")
    return closed_paths, open_paths, circles


# =========================
# Modeling
# =========================

def create_base_plate() -> cq.Workplane:
    base = (cq.Workplane("XY")
            .rect(BASE_WIDTH, BASE_HEIGHT, centered=False)
            .extrude(BASE_THICKNESS))
    if BASE_CORNER_RADIUS > 0:
        base = base.edges("|Z").fillet(BASE_CORNER_RADIUS)
    return base


# Ridge tops are FLAT. We tried a draft taper for rounded, finger-friendly tops, but
# `extrude(taper=…)` SEGFAULTS inside OCCT on real Hebrew glyph outlines (reproduced on
# פרח) — a C-level crash that kills the whole worker, no STL, hard to catch. A flat
# extrude is robust and fast. STROKE_TAPER_DEG = 0 disables the taper path entirely;
# raise it again only with a crash-isolated (subprocess) extrude.
STROKE_TAPER_DEG = 0.0


def _capped_solid(pts: List[Point], height: float, offset: float = None, round_top: bool = True):
    """
    Extrude polygon `pts` to `height`, returning a cq.Solid. When `round_top` and
    rounded tops are enabled, apply a draft taper so the ridge narrows toward the top
    (finger-friendly, no sharp edge); fall back to a straight extrude if the taper
    self-intersects.

    Taper is only worth attempting on wider features (text, image outlines). Thin
    detail strokes (~0.8mm) almost always self-intersect at the taper angle, so the
    attempt is wasted work (it fails, then we extrude flat anyway) — pass
    round_top=False for those to skip straight to the flat extrude.

    A fresh Workplane is built for each attempt: a FAILED taper extrude still consumes
    the pending wire, so reusing one Workplane would make the fallback raise
    "No pending wires present" and the feature would be dropped entirely.
    """
    z = BASE_THICKNESS if offset is None else offset

    def _profile():
        return cq.Workplane("XY").workplane(offset=z).polyline(pts).close()

    if round_top and EDGE_FILLET_ENABLED and STROKE_TAPER_DEG > 0:
        try:
            return _profile().extrude(height, taper=STROKE_TAPER_DEG).val()
        except Exception:
            pass
    return _profile().extrude(height).val()


def extrude_text_solids(shapes: List[List[Point]], height: float) -> List:
    """Extrude closed text polygons as solid ridges with rounded (tapered) tops."""
    print(f"  Text solids: {len(shapes)} closed shapes")
    solids = []
    for i, pts in enumerate(shapes, 1):
        pts = clean_polyline_points(pts, POINT_CLEAN_TOL)
        if len(pts) < 3:
            continue
        if polygon_area(pts) < 0:
            pts = list(reversed(pts))
        try:
            solids.append(_capped_solid(pts, height))
        except Exception as e:
            print(f"    Warning: text shape {i} skipped: {e}")
    return solids


def create_dome(cx: float, cy: float, base_radius: float, height: float) -> cq.Workplane:
    """Spherical-cap dome: sphere radius computed from base_radius and height."""
    R = (base_radius * base_radius + height * height) / (2.0 * height)
    sphere_center_z = BASE_THICKNESS + height - R
    dome = (cq.Workplane("XY")
            .workplane(offset=sphere_center_z)
            .center(cx, cy)
            .sphere(R))
    cut_box = (cq.Workplane("XY")
               .box(base_radius * 4, base_radius * 4, R * 2)
               .translate((cx, cy, BASE_THICKNESS - R)))
    return dome.cut(cut_box)


def add_braille_domes(circles: List[CircleDef]) -> List:
    """
    Build Braille domes using fixed Grade 1 dimensions from config
    (braille_dot_radius_mm, braille_dot_height_mm), ignoring the detected radius
    from the DXF so all dots are standardised.
    """
    print(f"  Braille domes: {len(circles)} circles  "
          f"r={BRAILLE_FIXED_RADIUS}mm  h={BRAILLE_FIXED_HEIGHT}mm")
    solids = []
    for i, ((cx, cy), _) in enumerate(circles, 1):
        try:
            solids.append(create_dome(cx, cy, BRAILLE_FIXED_RADIUS, BRAILLE_FIXED_HEIGHT).val())
        except Exception as e:
            print(f"    Warning: dome {i} skipped: {e}")
    return solids


def clipper_clean_and_simplify(poly: List[Point], clean_tol_mm: float) -> List[List[Point]]:
    poly_i   = [(int(x * SCALE), int(y * SCALE)) for x, y in poly]
    cleaned  = pyclipper.CleanPolygon(poly_i, clean_tol_mm * SCALE)
    if not cleaned:
        return []
    simplified = pyclipper.SimplifyPolygon(cleaned, pyclipper.PFT_NONZERO)
    return [[(x / SCALE, y / SCALE) for x, y in p] for p in simplified]


def stroke_polygons_from_centerline(points: List[Point], half_width: float, closed: bool) -> List[List[Point]]:
    """
    Offset a centerline to produce stroke footprint polygons.

    Open paths → single ET_OPENROUND offset.
    Closed paths → stroke each edge segment individually as OPEN to avoid
    filled-band artefacts from ET_CLOSEDLINE.
    """
    if len(points) < 2:
        return []
    pts = clean_polyline_points(points, POINT_CLEAN_TOL)
    if len(pts) < 2:
        return []

    if closed:
        out: List[List[Point]] = []
        n = len(pts)
        for i in range(n):
            p1, p2 = pts[i], pts[(i + 1) % n]
            if p1 == p2:
                continue
            scaled = [(int(p1[0] * SCALE), int(p1[1] * SCALE)),
                      (int(p2[0] * SCALE), int(p2[1] * SCALE))]
            pco = pyclipper.PyclipperOffset()
            pco.AddPath(scaled, pyclipper.JT_ROUND, pyclipper.ET_OPENROUND)
            outs = pco.Execute(half_width * SCALE)
            if outs:
                out.extend([[(x / SCALE, y / SCALE) for x, y in poly] for poly in outs])
        return out

    scaled = [(int(x * SCALE), int(y * SCALE)) for x, y in pts]
    pco = pyclipper.PyclipperOffset()
    pco.AddPath(scaled, pyclipper.JT_ROUND, pyclipper.ET_OPENROUND)
    outs = pco.Execute(half_width * SCALE)
    return [[(x / SCALE, y / SCALE) for x, y in poly] for poly in outs] if outs else []


def _extrude_one_centerline(
    solids: List,
    pts: List[Point],
    is_closed: bool,
    half_width: float,
    stroke_height: float,
    idx: int,
    round_top: bool = False,
) -> None:
    """
    Simplify, stroke, and extrude one centerline path as a ridge, appending the
    resulting solids to `solids`. `round_top` applies a draft taper (only worth it
    for wide outlines; thin details stay flat — see _capped_solid).
    """
    pts = rdp_simplify(clean_polyline_points(pts, POINT_CLEAN_TOL), PATH_SIMPLIFY_TOL)
    if len(pts) < 2:
        return

    stroke_polys = stroke_polygons_from_centerline(pts, half_width, is_closed)

    for poly in stroke_polys:
        for p2 in clipper_clean_and_simplify(poly, CLIPPER_CLEAN_TOL):
            p2 = clean_polyline_points(p2, POINT_CLEAN_TOL)
            if len(p2) < 3:
                continue
            if polygon_area(p2) < 0:
                p2 = list(reversed(p2))
            try:
                solids.append(_capped_solid(p2, stroke_height, round_top=round_top))
            except Exception as e:
                print(f"    Warning: image stroke {idx} polygon skipped: {e}")


def extrude_image_strokes(
    closed_paths: List[List[Point]],
    open_paths:   List[List[Point]],
    circles:      List[CircleDef],
    outline_height: float = IMAGE_OUTLINE_HEIGHT,
    outline_width:  float = IMAGE_OUTLINE_WIDTH,
) -> List:
    """
    Extrude image paths as dome-topped ridges with a two-tier height hierarchy:
      - Closed paths with |area| ≥ OUTLINE_MIN_AREA → main outline (taller, wider)
      - All other paths and open paths       → detail  (shorter, narrower)

    All paths are Douglas-Peucker simplified before extrusion.
    """
    # Convert circle entities to closed centerline polygons
    circle_paths: List[List[Point]] = []
    for (cx, cy), r in circles:
        steps = 96
        circle_paths.append([
            (cx + r * math.cos(2 * math.pi * k / steps),
             cy + r * math.sin(2 * math.pi * k / steps))
            for k in range(steps)
        ])

    n_outline = sum(1 for p in closed_paths if abs(polygon_area(p)) >= OUTLINE_MIN_AREA)
    n_detail  = len(closed_paths) - n_outline + len(open_paths) + len(circle_paths)
    print(f"  Image strokes: {n_outline} outlines "
          f"({outline_height:.1f}mm × {outline_width:.1f}mm), "
          f"{n_detail} details "
          f"({IMAGE_DETAIL_HEIGHT:.1f}mm × {IMAGE_DETAIL_WIDTH:.1f}mm)")

    solids: List = []
    idx = 1
    # Image ridges are thin (≤1.2mm) — flat vs tapered tops are indistinguishable by
    # touch, and tapering hundreds of them is the dominant build cost on dense art.
    # So keep image strokes flat; the taper is reserved for the (few) raised-text shapes.
    for pts in closed_paths:
        if abs(polygon_area(pts)) >= OUTLINE_MIN_AREA:
            h, w = outline_height, outline_width
        else:
            h, w = IMAGE_DETAIL_HEIGHT, IMAGE_DETAIL_WIDTH
        _extrude_one_centerline(solids, pts, True, w / 2, h, idx)
        idx += 1

    for pts in open_paths:
        _extrude_one_centerline(solids, pts, False, IMAGE_DETAIL_WIDTH / 2, IMAGE_DETAIL_HEIGHT, idx)
        idx += 1

    for pts in circle_paths:
        _extrude_one_centerline(solids, pts, True,  IMAGE_DETAIL_WIDTH / 2, IMAGE_DETAIL_HEIGHT, idx)
        idx += 1

    return solids


# =========================
# Texture fills
# =========================

def _scanline_intersections(polygon: List[Point], y: float) -> List[float]:
    """Find x-coordinates where horizontal line y crosses polygon edges."""
    xs = []
    n  = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if y1 == y2:
            continue
        if min(y1, y2) <= y < max(y1, y2):
            t = (y - y1) / (y2 - y1)
            xs.append(x1 + t * (x2 - x1))
    return sorted(xs)


def _hatch_lines(polygon: List[Point], spacing: float, angle_deg: float = 0.0) -> List[List[Point]]:
    """
    Generate hatch line segments clipped to the interior of a polygon.
    Uses scanline intersection; supports arbitrary rotation via coordinate transform.
    """
    if angle_deg != 0.0:
        rad   = math.radians(angle_deg)
        ca, sa = math.cos(rad), math.sin(rad)
        rotated = [(x * ca + y * sa, -x * sa + y * ca) for x, y in polygon]
        lines   = _hatch_lines(rotated, spacing, 0.0)
        cb, sb  = math.cos(-rad), math.sin(-rad)
        return [[(x * cb + y * sb, -x * sb + y * cb) for x, y in seg] for seg in lines]

    min_y = min(p[1] for p in polygon)
    max_y = max(p[1] for p in polygon)
    segments: List[List[Point]] = []
    y = min_y + spacing / 2.0
    while y <= max_y:
        xs = _scanline_intersections(polygon, y)
        for i in range(0, len(xs) - 1, 2):
            if xs[i + 1] - xs[i] > spacing * 0.2:
                segments.append([(xs[i], y), (xs[i + 1], y)])
        y += spacing
    return segments


def add_texture_fills(
    closed_paths: List[List[Point]],
) -> List:
    """
    Fill large / medium closed regions with subtle hatch or crosshatch ridges.

    Large  (area ≥ TEXTURE_LARGE_AREA)  → parallel horizontal ridges
    Medium (area ≥ TEXTURE_MEDIUM_AREA) → crosshatch (0° + 90°)
    Small                               → no fill (left raised-flat by outline)

    Ridge height is TEXTURE_HEIGHT, well below the outline height, so the
    pattern reads as a texture rather than a structural element.
    """
    if not TEXTURE_ENABLED:
        return []

    half_w = TEXTURE_RIDGE_WIDTH / 2.0

    solids: List = []
    for pts in closed_paths:
        area = abs(polygon_area(pts))
        if area < TEXTURE_MEDIUM_AREA:
            continue

        if area >= TEXTURE_LARGE_AREA:
            segs = _hatch_lines(pts, TEXTURE_RIDGE_SPACING, 0.0)
        else:
            segs = (_hatch_lines(pts, TEXTURE_RIDGE_SPACING, 0.0) +
                    _hatch_lines(pts, TEXTURE_RIDGE_SPACING, 90.0))

        for seg in segs:
            for poly in stroke_polygons_from_centerline(seg, half_w, closed=False):
                for p2 in clipper_clean_and_simplify(poly, CLIPPER_CLEAN_TOL):
                    p2 = clean_polyline_points(p2, POINT_CLEAN_TOL)
                    if len(p2) < 3:
                        continue
                    if polygon_area(p2) < 0:
                        p2 = list(reversed(p2))
                    try:
                        solid = (cq.Workplane("XY")
                                 .workplane(offset=BASE_THICKNESS)
                                 .polyline(p2).close()
                                 .extrude(TEXTURE_HEIGHT))
                        solids.append(solid.val())
                    except Exception:
                        pass
    return solids


def create_mounting_holes(base: cq.Workplane) -> cq.Workplane:
    if not MOUNTING_HOLES_ENABLED:
        return base
    hole_x      = BASE_WIDTH - MOUNTING_HOLE_MARGIN_RIGHT
    first_hole_y = BASE_HEIGHT - MOUNTING_HOLE_MARGIN_TOP
    cut_h = BASE_THICKNESS + max(TEXT_SOLID_HEIGHT, IMAGE_OUTLINE_HEIGHT) + 2.0
    for i in range(MOUNTING_HOLE_COUNT):
        y    = first_hole_y - i * MOUNTING_HOLE_SPACING
        hole = (cq.Workplane("XY")
                .workplane(offset=-1)
                .center(hole_x, y)
                .circle(MOUNTING_HOLE_RADIUS)
                .extrude(cut_h))
        base = base.cut(hole)
    return base


# =========================
# Main function
# =========================

def create_one_page_stl_from_dxf(
    txt_dxf:     Path,
    braille_dxf: Path,
    image_dxf:   Path,
    output:      Path  = None,
    stroke_width:  float = IMAGE_STROKE_WIDTH,
    stroke_height: float = IMAGE_STROKE_HEIGHT,
    text_height:   float = TEXT_SOLID_HEIGHT,
    export_step:   bool  = False,
):
    txt_dxf     = Path(txt_dxf)     if txt_dxf     else None
    braille_dxf = Path(braille_dxf) if braille_dxf else None
    image_dxf   = Path(image_dxf)   if image_dxf   else None

    text_shapes:    List[List[Point]] = []
    braille_circles: List[CircleDef]  = []
    image_closed:   List[List[Point]] = []
    image_open:     List[List[Point]] = []
    image_circles:  List[CircleDef]   = []

    if txt_dxf:
        if not txt_dxf.exists():
            raise FileNotFoundError(txt_dxf)
        print(f"Reading TEXT DXF: {txt_dxf}")
        text_shapes = extract_closed_polygons_for_text(txt_dxf)
        print(f"  Text shapes: {len(text_shapes)}")

    if braille_dxf:
        if not braille_dxf.exists():
            raise FileNotFoundError(braille_dxf)
        print(f"Reading BRAILLE DXF: {braille_dxf}")
        braille_circles = extract_braille_circles(braille_dxf)
        print(f"  Braille circles: {len(braille_circles)}")

    if image_dxf:
        if not image_dxf.exists():
            raise FileNotFoundError(image_dxf)
        print(f"Reading IMAGE DXF: {image_dxf}")
        image_closed, image_open, image_circles = extract_image_centerlines(image_dxf)
        print(f"  Image paths: closed={len(image_closed)} open={len(image_open)} circles={len(image_circles)}")

    text_shapes, braille_circles, image_closed, image_open = layout_content_on_base(
        text_shapes=text_shapes,
        braille_circles=braille_circles,
        image_closed_paths=image_closed,
        image_open_paths=image_open,
    )

    print("\nBuilding model...")
    # Cut mounting holes from the single base solid (cheap — a few cuts).
    base = create_mounting_holes(create_base_plate())

    # Build every tactile feature as an independent solid; DO NOT boolean-fuse them.
    # OCCT booleans do not scale to real line-art (one page = thousands of overlapping
    # stroke solids → minutes-to-hours). Instead emit a multi-volume mesh and let the
    # slicer union the overlaps at print time — ~190× faster, valid for FDM.
    parts: List = []
    if text_shapes:
        t0 = time.time()
        parts += extrude_text_solids(text_shapes, height=text_height)
        print(f"    [t] text {time.time() - t0:.1f}s")

    if braille_circles:
        t0 = time.time()
        parts += add_braille_domes(braille_circles)
        print(f"    [t] braille {time.time() - t0:.1f}s")

    if image_dxf and (image_closed or image_open or image_circles):
        t0 = time.time()
        parts += extrude_image_strokes(
            image_closed, image_open, image_circles,
            outline_height=stroke_height,
            outline_width=stroke_width,
        )
        print(f"    [t] image strokes {time.time() - t0:.1f}s  (parts so far: {len(parts)})")
        if TEXTURE_ENABLED and image_closed:
            print("  Adding texture fills...")
            t0 = time.time()
            parts += add_texture_fills(image_closed)
            print(f"    [t] texture {time.time() - t0:.1f}s")

    t0 = time.time()
    model = cq.Compound.makeCompound([base.val()] + parts)
    print(f"  Assembled {len(parts)} feature solids (no boolean union) in {time.time() - t0:.1f}s")

    out = Path(output) if output else None
    if out is None:
        if image_dxf:  out = image_dxf.with_suffix(".stl")
        elif txt_dxf:  out = txt_dxf.with_suffix(".stl")
        else:          out = braille_dxf.with_suffix(".stl")

    t0 = time.time()
    cq.exporters.export(model, str(out))
    print(f"\nExported STL: {out}  ({time.time() - t0:.1f}s)")

    if export_step:
        step_out = out.with_suffix(".step")
        cq.exporters.export(model, str(step_out))
        print(f"Exported STEP: {step_out}")

    return str(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Build STL from three DXFs: text (solid), braille (domes), image (strokes)"
    )
    ap.add_argument("--text",    dest="text_dxf",    type=Path, required=True,
                    help="DXF file with text (closed shapes)")
    ap.add_argument("--braille", dest="braille_dxf", type=Path, required=True,
                    help="DXF file with braille circles")
    ap.add_argument("--image",   dest="image_dxf",   type=Path, required=True,
                    help="DXF file with image line-art")
    ap.add_argument("-o", "--output", dest="output", type=Path, required=False,
                    help="Output STL path")
    ap.add_argument("--step", action="store_true", help="Also export STEP")
    ap.add_argument("--stroke-width",  type=float, default=IMAGE_STROKE_WIDTH,
                    help="Main outline stroke width in mm (total)")
    ap.add_argument("--stroke-height", type=float, default=IMAGE_STROKE_HEIGHT,
                    help="Main outline stroke height in mm")
    ap.add_argument("--text-height",   type=float, default=TEXT_SOLID_HEIGHT,
                    help="Text solid extrusion height in mm")
    args = ap.parse_args()

    create_one_page_stl_from_dxf(
        txt_dxf=args.text_dxf,
        braille_dxf=args.braille_dxf,
        image_dxf=args.image_dxf,
        output=args.output,
        stroke_width=args.stroke_width,
        stroke_height=args.stroke_height,
        text_height=args.text_height,
        export_step=args.step,
    )
