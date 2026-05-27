#!/usr/bin/env python3
"""
3-DXF → 3D STL builder (single file)

Inputs:
  --text    DXF with text shapes (solid)
  --braille DXF with circles (domes)
  --image   DXF with line-art (strokes from centerlines; open+closed)

IMPORTANT FIX:
  Closed IMAGE paths are NOT stroked using ET_CLOSEDLINE (can create "bands" that look filled).
  Instead, closed paths are split into segments and each segment is stroked as an OPEN path (ET_OPENROUND).
  This makes closed sleeve contours behave like "drawn lines" instead of filled solids.

Requires:
  ezdxf, cadquery, pyclipper

Example:
  python dxf_3files_stroke.py --text text.dxf --braille braille.dxf --image image.dxf -o out.stl
"""

import argparse
import math
from pathlib import Path
from typing import List, Tuple

import ezdxf
from ezdxf.entities import LWPolyline, Circle, Ellipse, Spline, Polyline, Line
from ezdxf.path import make_path

import cadquery as cq
import pyclipper


Point = Tuple[float, float]
CircleDef = Tuple[Tuple[float, float], float]

# =========================
# Defaults
# =========================
BASE_WIDTH = 150.0
BASE_HEIGHT = 150.0
BASE_THICKNESS = 1.5
BASE_CORNER_RADIUS = 10.0

TEXT_SOLID_HEIGHT = 1.5

# IMAGE STROKE SETTINGS (nozzle 0.4, min line 1mm => default stroke width = 1mm)
IMAGE_STROKE_WIDTH = 1.0       # total width in mm
IMAGE_STROKE_HEIGHT = 1.5

# Cleanup
POINT_CLEAN_TOL = 0.02         # remove near-duplicate points (mm)
CLIPPER_CLEAN_TOL = 0.05       # pyclipper CleanPolygon tol (mm)

# Braille
DOME_HEIGHT_RATIO = 0.5        # height = radius * ratio

# Optional mounting holes
MOUNTING_HOLES_ENABLED = False
MOUNTING_HOLE_RADIUS = 2.0
MOUNTING_HOLE_COUNT = 3
MOUNTING_HOLE_MARGIN_RIGHT = 7.0
MOUNTING_HOLE_MARGIN_TOP = 20.0
MOUNTING_HOLE_SPACING = 50.0

SCALE = 1000.0  # pyclipper integer scaling


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
    min_x = float("inf")
    min_y = float("inf")
    max_x = float("-inf")
    max_y = float("-inf")

    for p in paths:
        for x, y in p:
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)

    for (cx, cy), r in circles:
        min_x = min(min_x, cx - r)
        min_y = min(min_y, cy - r)
        max_x = max(max_x, cx + r)
        max_y = max(max_y, cy + r)

    if min_x == float("inf"):
        return 0.0, 0.0, 0.0, 0.0

    return min_x, min_y, max_x, max_y


def translate_paths(paths: List[List[Point]], dx: float, dy: float) -> List[List[Point]]:
    return [[(x + dx, y + dy) for x, y in p] for p in paths]


def translate_circles(circles: List[CircleDef], dx: float, dy: float) -> List[CircleDef]:
    return [((cx + dx, cy + dy), r) for (cx, cy), r in circles]


def center_all_content_on_base(
    text_shapes: List[List[Point]],
    braille_circles: List[CircleDef],
    image_closed_paths: List[List[Point]],
    image_open_paths: List[List[Point]],
) -> Tuple[List[List[Point]], List[CircleDef], List[List[Point]], List[List[Point]]]:
    all_paths: List[List[Point]] = []
    all_paths += text_shapes
    all_paths += image_closed_paths
    all_paths += image_open_paths

    min_x, min_y, max_x, max_y = bbox_of_paths(all_paths, braille_circles)
    width = max_x - min_x
    height = max_y - min_y

    print(f"  Overall content size: {width:.2f}mm x {height:.2f}mm")

    cx = (min_x + max_x) / 2.0
    cy = (min_y + max_y) / 2.0

    base_cx = BASE_WIDTH / 2.0
    base_cy = BASE_HEIGHT / 2.0
    dx = base_cx - cx
    dy = base_cy - cy

    text_shapes = translate_paths(text_shapes, dx, dy)
    braille_circles = translate_circles(braille_circles, dx, dy)
    image_closed_paths = translate_paths(image_closed_paths, dx, dy)
    image_open_paths = translate_paths(image_open_paths, dx, dy)

    return text_shapes, braille_circles, image_closed_paths, image_open_paths


# =========================
# DXF extraction
# =========================
def extract_closed_polygons_for_text(dxf_path: Path) -> List[List[Point]]:
    """
    TEXT DXF: only closed shapes as filled/solid regions.
    """
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
    """
    IMAGE DXF: return (closed_paths, open_paths, circles_as_defs)

    Closed polylines are treated as CENTERLINES to be stroked (but with the closed-path segment strategy).
    """
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()

    closed_paths: List[List[Point]] = []
    open_paths: List[List[Point]] = []
    circles: List[CircleDef] = []

    for entity in msp:
        try:
            t = entity.dxftype()

            if t == "LINE":
                ln: Line = entity
                s = (ln.dxf.start.x, ln.dxf.start.y)
                e = (ln.dxf.end.x, ln.dxf.end.y)
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


def extrude_text_solids(base: cq.Workplane, shapes: List[List[Point]], height: float) -> cq.Workplane:
    print(f"  Text solids: {len(shapes)} closed shapes")
    for i, pts in enumerate(shapes, 1):
        pts = clean_polyline_points(pts, POINT_CLEAN_TOL)
        if len(pts) < 3:
            continue
        if polygon_area(pts) < 0:
            pts = list(reversed(pts))
        try:
            solid = (cq.Workplane("XY")
                     .workplane(offset=BASE_THICKNESS)
                     .polyline(pts).close()
                     .extrude(height))
            base = base.union(solid)
        except Exception as e:
            print(f"    Warning: text shape {i} skipped: {e}")
    return base


def create_dome(cx: float, cy: float, base_radius: float, height: float) -> cq.Workplane:
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


def add_braille_domes(base: cq.Workplane, circles: List[CircleDef]) -> cq.Workplane:
    print(f"  Braille domes: {len(circles)} circles")
    for i, ((cx, cy), r) in enumerate(circles, 1):
        try:
            h = r * DOME_HEIGHT_RATIO
            base = base.union(create_dome(cx, cy, r, h))
        except Exception as e:
            print(f"    Warning: dome {i} skipped: {e}")
    return base


def clipper_clean_and_simplify(poly: List[Point], clean_tol_mm: float) -> List[List[Point]]:
    poly_i = [(int(x * SCALE), int(y * SCALE)) for x, y in poly]
    cleaned = pyclipper.CleanPolygon(poly_i, clean_tol_mm * SCALE)
    if not cleaned:
        return []
    simplified = pyclipper.SimplifyPolygon(cleaned, pyclipper.PFT_NONZERO)
    out: List[List[Point]] = []
    for p in simplified:
        out.append([(x / SCALE, y / SCALE) for x, y in p])
    return out


def stroke_polygons_from_centerline(points: List[Point], half_width: float, closed: bool) -> List[List[Point]]:
    """
    Create stroke polygons around a centerline.

    Key behavior:
      - open paths: offset once with ET_OPENROUND
      - closed paths: DO NOT use ET_CLOSEDLINE (can create overlapping bands -> looks filled).
        Instead stroke each edge segment as OPEN (ET_OPENROUND) and union results.
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
            p1 = pts[i]
            p2 = pts[(i + 1) % n]
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

    # open
    scaled = [(int(x * SCALE), int(y * SCALE)) for x, y in pts]
    pco = pyclipper.PyclipperOffset()
    pco.AddPath(scaled, pyclipper.JT_ROUND, pyclipper.ET_OPENROUND)
    outs = pco.Execute(half_width * SCALE)
    return [[(x / SCALE, y / SCALE) for x, y in poly] for poly in outs] if outs else []


def extrude_image_strokes(
    base: cq.Workplane,
    closed_paths: List[List[Point]],
    open_paths: List[List[Point]],
    circles: List[CircleDef],
    stroke_width: float,
    stroke_height: float,
) -> cq.Workplane:
    half = stroke_width / 2.0

    # circles -> approximate as closed centerlines
    circle_paths: List[List[Point]] = []
    for (cx, cy), r in circles:
        steps = 96
        circle_paths.append([
            (cx + r * math.cos(2 * math.pi * k / steps),
             cy + r * math.sin(2 * math.pi * k / steps))
            for k in range(steps)
        ])

    all_centerlines: List[Tuple[List[Point], bool]] = []
    all_centerlines += [(p, True) for p in closed_paths]
    all_centerlines += [(p, False) for p in open_paths]
    all_centerlines += [(p, True) for p in circle_paths]

    print(f"  Image strokes: {len(all_centerlines)} centerlines "
          f"(closed={len(closed_paths)+len(circle_paths)}, open={len(open_paths)}) "
          f"width={stroke_width:.2f}mm height={stroke_height:.2f}mm")

    for idx, (pts, is_closed) in enumerate(all_centerlines, 1):
        pts = clean_polyline_points(pts, POINT_CLEAN_TOL)
        if len(pts) < 2:
            continue

        stroke_polys = stroke_polygons_from_centerline(pts, half, is_closed)
        if not stroke_polys:
            continue

        for poly in stroke_polys:
            polys2 = clipper_clean_and_simplify(poly, CLIPPER_CLEAN_TOL)
            if not polys2:
                continue

            for p2 in polys2:
                p2 = clean_polyline_points(p2, POINT_CLEAN_TOL)
                if len(p2) < 3:
                    continue
                if polygon_area(p2) < 0:
                    p2 = list(reversed(p2))

                try:
                    solid = (cq.Workplane("XY")
                             .workplane(offset=BASE_THICKNESS)
                             .polyline(p2).close()
                             .extrude(stroke_height))
                    base = base.union(solid)
                except Exception as e:
                    print(f"    Warning: image stroke {idx} polygon skipped: {e}")

    return base


def create_mounting_holes(base: cq.Workplane) -> cq.Workplane:
    if not MOUNTING_HOLES_ENABLED:
        return base

    hole_x = BASE_WIDTH - MOUNTING_HOLE_MARGIN_RIGHT
    first_hole_y = BASE_HEIGHT - MOUNTING_HOLE_MARGIN_TOP
    cut_h = BASE_THICKNESS + max(TEXT_SOLID_HEIGHT, IMAGE_STROKE_HEIGHT) + 2.0

    for i in range(MOUNTING_HOLE_COUNT):
        y = first_hole_y - i * MOUNTING_HOLE_SPACING
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
def create_one_page_stl_from_dxf(txt_dxf: Path, braille_dxf: Path, image_dxf: Path):
    
    text_shapes: List[List[Point]] = []
    braille_circles: List[CircleDef] = []
    image_closed: List[List[Point]] = []
    image_open: List[List[Point]] = []
    image_circles: List[CircleDef] = []

    if args.text_dxf:
        if not args.text_dxf.exists():
            raise FileNotFoundError(args.text_dxf)
        print(f"Reading TEXT DXF: {args.text_dxf}")
        text_shapes = extract_closed_polygons_for_text(args.text_dxf)
        print(f"  Text shapes: {len(text_shapes)}")

    if args.braille_dxf:
        if not args.braille_dxf.exists():
            raise FileNotFoundError(args.braille_dxf)
        print(f"Reading BRAILLE DXF: {args.braille_dxf}")
        braille_circles = extract_braille_circles(args.braille_dxf)
        print(f"  Braille circles: {len(braille_circles)}")

    if args.image_dxf:
        if not args.image_dxf.exists():
            raise FileNotFoundError(args.image_dxf)
        print(f"Reading IMAGE DXF: {args.image_dxf}")
        image_closed, image_open, image_circles = extract_image_centerlines(args.image_dxf)
        print(f"  Image paths: closed={len(image_closed)} open={len(image_open)} circles={len(image_circles)}")

    # Center all content together on base plate
    text_shapes, braille_circles, image_closed, image_open = center_all_content_on_base(
        text_shapes=text_shapes,
        braille_circles=braille_circles,
        image_closed_paths=image_closed,
        image_open_paths=image_open,
    )

    # Build model
    print("\nBuilding model...")
    model = create_base_plate()

    if text_shapes:
        model = extrude_text_solids(model, text_shapes, height=args.text_height)

    if braille_circles:
        model = add_braille_domes(model, braille_circles)

    if args.image_dxf and (image_closed or image_open or image_circles):
        model = extrude_image_strokes(
            model,
            closed_paths=image_closed,
            open_paths=image_open,
            circles=image_circles,
            stroke_width=args.stroke_width,
            stroke_height=args.stroke_height,
        )

    model = create_mounting_holes(model)

    # Output path
    out = args.output
    if out is None:
        if args.image_dxf:
            out = args.image_dxf.with_suffix(".stl")
        elif args.text_dxf:
            out = args.text_dxf.with_suffix(".stl")
        else:
            out = args.braille_dxf.with_suffix(".stl")

    cq.exporters.export(model, str(out))
    print(f"\nExported STL: {out}")

    if args.step:
        step_out = out.with_suffix(".step")
        cq.exporters.export(model, str(step_out))
        print(f"Exported STEP: {step_out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build STL from three DXFs: text (solid), braille (domes), image (strokes)")
    ap.add_argument("--text", dest="text_dxf", type=Path, required=True, help="DXF file with text (closed shapes)")
    ap.add_argument("--braille", dest="braille_dxf", type=Path, required=True, help="DXF file with braille circles")
    ap.add_argument("--image", dest="image_dxf", type=Path, required=True, help="DXF file with image line-art")
    ap.add_argument("-o", "--output", dest="output", type=Path, required=False, help="Output STL path")
    ap.add_argument("--step", action="store_true", help="Also export STEP")
    ap.add_argument("--stroke-width", type=float, default=IMAGE_STROKE_WIDTH, help="Image stroke width in mm (total)")
    ap.add_argument("--stroke-height", type=float, default=IMAGE_STROKE_HEIGHT, help="Image stroke height in mm")
    ap.add_argument("--text-height", type=float, default=TEXT_SOLID_HEIGHT, help="Text solid extrusion height in mm")
    args = ap.parse_args()

    create_one_page_stl_from_dxf(args.text_dxf, args.braille_dxf, args.image_dxf)
