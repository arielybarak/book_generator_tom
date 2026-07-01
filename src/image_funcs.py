"""
Image processing and DXF export utilities.

Responsibilities:
- ensure_font(): download and register NotoSansSymbols2 for Braille rendering
- image_to_dxf_exact(): grayscale/binary image → DXF polylines via Zhang-Suen
  skeletonization + approxPolyDP simplification (single-pixel-wide, clean lines)
- process_image_to_dxf(): raw colour SD output → DXF (adaptive threshold pipeline)
- generate_hebrew_text_dxf(): render Hebrew text → temp PNG → DXF via matplotlib
- generate_braille_dxf_from_text(): Braille unicode → PNG → blob detection → DXF circles
- png_to_dxf(): generic PNG file → DXF via external contour extraction
- plot_dxf(): quick matplotlib preview of any DXF file
"""
import os
import uuid
import urllib.request
import torch
import cv2
import numpy as np
import ezdxf
import matplotlib
matplotlib.use("Agg")  # headless, thread-safe backend (no GUI / no global event loop)
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.figure import Figure
from PIL import Image

FONT_FILENAME = "NotoSansSymbols2-Regular.ttf"
FONT_URL = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansSymbols2/NotoSansSymbols2-Regular.ttf"


# ── Font setup ─────────────────────────────────────────────────────────────────

def ensure_font(font_path=None):
    """Load NotoSansSymbols2 for Braille rendering; download it if missing."""
    path = font_path or FONT_FILENAME
    if not os.path.exists(path):
        try:
            print(f"Downloading Braille font to {path}...")
            urllib.request.urlretrieve(FONT_URL, path)
        except Exception as e:
            print(f"Font download failed: {e}")
            return
    fm.fontManager.addfont(path)


# ── Tensor → PIL ───────────────────────────────────────────────────────────────

def convert_tensor_to_pil_img(tensor):
    """Convert a CxHxW tensor in [-1,1] to a PIL image in [0,255]."""
    image = (tensor / 2 + 0.5).clamp(0, 1).squeeze()
    image = (image.permute(1, 2, 0) * 255).round().to(torch.uint8).cpu().numpy()
    return Image.fromarray(image)


# ── Image → DXF ────────────────────────────────────────────────────────────────

def image_to_dxf_exact(image_bw, out_path, canvas_cm=150, simplify_epsilon=2.0):
    """
    Convert a grayscale/binary image OR image path to a smoother DXF polyline file.
    Good for tactile / 3D-printable image outlines.

    Main fixes:
    - accepts path or numpy array
    - smooths the binary mask before contour extraction
    - avoids keeping every pixel stair-step
    - exports closed continuous contours
    """
    canvas_mm = canvas_cm * 10.0

    # Accept either path or numpy array
    if isinstance(image_bw, (str, os.PathLike)):
        img = cv2.imread(str(image_bw), cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise RuntimeError(f"Could not load image: {image_bw}")
    else:
        img = image_bw.copy()
        if img.ndim == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    if img.dtype != np.uint8:
        img = img.astype(np.uint8)

    # We want white object/lines on black background
    if np.mean(img) > 127:
        img = cv2.bitwise_not(img)

    _, bin_img = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY)

    # Smooth pixel staircase before contour extraction
    # Upscaling gives the contour more room to become smooth.
    upscale = 4
    bin_img = cv2.resize(
        bin_img,
        None,
        fx=upscale,
        fy=upscale,
        interpolation=cv2.INTER_CUBIC,
    )

    # Blur + threshold removes jagged pixel steps
    bin_img = cv2.GaussianBlur(bin_img, (5, 5), 0)
    _, bin_img = cv2.threshold(bin_img, 127, 255, cv2.THRESH_BINARY)

    # Close tiny gaps and smooth corners
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    bin_img = cv2.morphologyEx(bin_img, cv2.MORPH_CLOSE, kernel, iterations=1)
    bin_img = cv2.morphologyEx(bin_img, cv2.MORPH_OPEN, kernel, iterations=1)

    # Use TC89 instead of CHAIN_APPROX_NONE to avoid exporting every pixel step
    contours, _ = cv2.findContours(
        bin_img,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_TC89_KCOS,
    )

    contours = [c for c in contours if cv2.contourArea(c) >= 100 * upscale * upscale]
    if not contours:
        print(f"Warning: no significant contours for {out_path}")
        return

    all_pts = np.vstack([c.reshape(-1, 2) for c in contours])
    min_x, min_y = all_pts.min(axis=0)
    max_x, max_y = all_pts.max(axis=0)

    w_px = max_x - min_x + 1
    h_px = max_y - min_y + 1

    scale = canvas_mm / max(w_px, h_px)
    offset_x = (canvas_mm - w_px * scale) / 2
    offset_y = (canvas_mm - h_px * scale) / 2

    def px_to_mm(p):
        return (
            (p[0] - min_x) * scale + offset_x,
            (max_y - p[1]) * scale + offset_y,
        )

    doc = ezdxf.new(setup=True)
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()

    for c in contours:
        # epsilon is multiplied because we upscaled the image
        epsilon = simplify_epsilon * upscale
        approx = cv2.approxPolyDP(c, epsilon=epsilon, closed=True)

        pts = [px_to_mm(p[0]) for p in approx]

        if len(pts) > 2:
            msp.add_lwpolyline(pts, close=True, dxfattribs={"color": 7})

    doc.saveas(out_path)

def process_image_to_dxf(img_array, output_path, canvas_cm=150):
    """
    Convert a raw colour numpy image (from Stable Diffusion) to a DXF.
    Applies colour→gray, adaptive threshold, morphological close, then DXF export.
    """
    canvas_mm = canvas_cm * 10.0

    gray  = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY)
    blur  = cv2.GaussianBlur(gray, (7, 7), 0)
    binary = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 21, 3
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)

    doc = ezdxf.new()
    msp = doc.modelspace()
    height = img_array.shape[0]

    for cnt in contours:
        if cv2.contourArea(cnt) < 80:
            continue
        epsilon = 0.01 * cv2.arcLength(cnt, False)
        approx  = cv2.approxPolyDP(cnt, epsilon, False)
        points  = [(float(p[0][0]), float(height - p[0][1])) for p in approx]
        if len(points) > 2:
            msp.add_lwpolyline(points, close=False, dxfattribs={'color': 7})

    doc.saveas(output_path)


def png_to_dxf(png_path, dxf_path, canvas_cm=150):
    """Convert a PNG file to a DXF using external contour extraction."""
    canvas_mm = canvas_cm * 10.0

    img = cv2.imread(png_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise RuntimeError(f"Could not load {png_path}")

    _, bw = cv2.threshold(img, 200, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        raise RuntimeError(f"No contours found in {png_path}")

    all_pts = np.vstack([c.reshape(-1, 2) for c in contours])
    min_x, min_y = all_pts.min(axis=0)
    max_x, max_y = all_pts.max(axis=0)
    w_px = max_x - min_x + 1
    h_px = max_y - min_y + 1

    scale    = canvas_mm / max(w_px, h_px)
    offset_x = (canvas_mm - w_px * scale) / 2
    offset_y = (canvas_mm - h_px * scale) / 2

    def px_to_mm(p):
        return ((p[0] - min_x) * scale + offset_x,
                (max_y - p[1]) * scale + offset_y)

    doc = ezdxf.new(setup=True)
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()

    for c in contours:
        pts = [px_to_mm(p[0]) for p in c]
        if len(pts) > 1:
            msp.add_lwpolyline(pts, close=True)

    doc.saveas(dxf_path)


def _filled_glyphs_to_dxf(image_bw, out_path, canvas_cm=150):
    """
    Convert a rendered-text image to a DXF of SOLID glyph outlines.

    Unlike image_to_dxf_exact (which skeletonizes line-art to centerlines), text must
    stay solid — skeletonizing letters leaves thin, broken strokes that barely read as
    raised text. So we take the FILLED outer contours (RETR_EXTERNAL) of the letters and
    export them as closed polylines, which dxf_3d then extrudes as solid raised glyphs.
    """
    canvas_mm = canvas_cm * 10.0
    img = image_bw.copy()
    if img.dtype != np.uint8:
        img = img.astype(np.uint8)
    if np.mean(img) > 127:                       # want white glyphs on black
        img = cv2.bitwise_not(img)
    _, bin_img = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY)

    contours, _ = cv2.findContours(bin_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        print(f"Warning: no glyph contours found for {out_path}")
        return

    all_pts = np.vstack([c.reshape(-1, 2) for c in contours])
    min_x, min_y = all_pts.min(axis=0)
    max_x, max_y = all_pts.max(axis=0)
    w_px, h_px = (max_x - min_x + 1), (max_y - min_y + 1)
    scale    = canvas_mm / max(w_px, h_px)
    offset_x = (canvas_mm - w_px * scale) / 2
    offset_y = (canvas_mm - h_px * scale) / 2

    def px_to_mm(p):
        return ((p[0] - min_x) * scale + offset_x,
                (max_y - p[1]) * scale + offset_y)

    doc = ezdxf.new(setup=True)
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()
    for c in contours:
        approx = cv2.approxPolyDP(c, epsilon=1.0, closed=True)
        pts = [px_to_mm(p[0]) for p in approx]
        if len(pts) > 2:
            msp.add_lwpolyline(pts, close=True)
    doc.saveas(out_path)


def generate_text_dxf(text, output_path, rtl=True):
    """
    Render text to a temp PNG via matplotlib, then export SOLID glyph outlines as DXF.
    Hebrew is RTL (matplotlib has no bidi, so the string is reversed); English is LTR.
    """
    render_text = text[::-1] if rtl else text
    temp_img = f"temp_text_{uuid.uuid4()}.png"
    fig = Figure(figsize=(5, 2), facecolor="white")
    ax = fig.add_subplot(111)
    ax.set_facecolor("white")
    ax.text(0.5, 0.5, render_text, fontsize=36, color='black',
            ha='center', va='center', fontweight='normal', fontname='DejaVu Sans')
    ax.axis("off")
    fig.savefig(temp_img, dpi=300, bbox_inches="tight", pad_inches=0.1,
                facecolor='white')

    try:
        img = cv2.imread(temp_img, cv2.IMREAD_GRAYSCALE)
        if img is not None:
            _filled_glyphs_to_dxf(img, output_path)
    finally:
        if os.path.exists(temp_img):
            os.remove(temp_img)


def generate_hebrew_text_dxf(hebrew_text, output_path):
    """Backwards-compatible Hebrew (RTL) wrapper around generate_text_dxf."""
    generate_text_dxf(hebrew_text, output_path, rtl=True)


# ── Braille geometry (Grade-1, millimetres) ───────────────────────────────────────
# Fixed physical spacing, independent of word length. Cells are laid out left-to-right
# (Hebrew Braille is read LTR). Dot size here only sets the DXF circle; dxf_3d overrides
# the dome radius/height from config when building the STL.
BRAILLE_DOT_SPACING_MM  = 2.5    # between dots within a cell (horizontal & vertical)
BRAILLE_CELL_SPACING_MM = 6.0    # between the same dot of adjacent cells
BRAILLE_DOT_RADIUS_MM   = 0.75
# Unicode Braille bit (0–5) → (col, row) in the 2×3 cell; row 0 is the top row.
_BRAILLE_DOT_CELL = {0: (0, 0), 1: (0, 1), 2: (0, 2), 3: (1, 0), 4: (1, 1), 5: (1, 2)}


def generate_braille_dxf_from_text(braille_text, output_path):
    """
    Emit Braille dots as DXF circles at FIXED Grade-1 spacing (mm), computed directly
    from the Unicode Braille string (U+2800–U+28FF). No PNG render / blob detection, so
    spacing is correct regardless of word length, and there is no Braille-font dependency.
    """
    doc = ezdxf.new()
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()
    dot = BRAILLE_DOT_SPACING_MM
    for i, ch in enumerate(braille_text):
        code = ord(ch) - 0x2800
        if code < 0 or code > 0xFF:      # space / non-Braille — advance one cell, no dots
            continue
        x0 = i * BRAILLE_CELL_SPACING_MM
        for bit, (col, row) in _BRAILLE_DOT_CELL.items():
            if code & (1 << bit):
                cx = x0 + col * dot
                cy = (2 - row) * dot      # y up: row 0 (top) is highest
                msp.add_circle(center=(cx, cy), radius=BRAILLE_DOT_RADIUS_MM,
                               dxfattribs={'color': 7})
    doc.saveas(output_path)


# ── DXF preview ────────────────────────────────────────────────────────────────

def plot_dxf(dxf_path):
    """Quick matplotlib preview of a DXF file."""
    try:
        doc = ezdxf.readfile(dxf_path)
        msp = doc.modelspace()
        plt.figure(figsize=(6, 6))

        for entity in msp:
            if entity.dxftype() == 'LWPOLYLINE':
                points = entity.get_points()
                x = [p[0] for p in points]
                y = [p[1] for p in points]
                if entity.is_closed:
                    x.append(x[0]); y.append(y[0])
                plt.plot(x, y, color='black', linewidth=1)
            elif entity.dxftype() == 'CIRCLE':
                cx, cy = entity.dxf.center.x, entity.dxf.center.y
                r      = entity.dxf.radius
                theta  = np.linspace(0, 2 * np.pi, 100)
                plt.plot(cx + r * np.cos(theta), cy + r * np.sin(theta),
                         color='black', linewidth=1)

        plt.axis('equal')
        plt.title(f"DXF: {dxf_path}")
        plt.axis('off')
        plt.show()
    except Exception as e:
        print(f"Could not plot DXF: {e}")
