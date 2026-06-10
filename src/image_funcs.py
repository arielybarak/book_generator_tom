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

def image_to_dxf_exact(image_bw, out_path, canvas_cm=150):
    """
    Convert a grayscale/binary numpy image to a DXF polyline file.
    Uses Zhang-Suen skeletonization for single-pixel-wide lines and
    approxPolyDP simplification for smaller, cleaner files.
    """
    canvas_mm = canvas_cm * 10.0

    img = image_bw.copy()
    if img.dtype != np.uint8:
        img = img.astype(np.uint8)

    # Normalise polarity: white lines on black background
    if np.mean(img) > 127:
        img = cv2.bitwise_not(img)

    _, bin_img = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY)

    # Skeletonize to single-pixel-wide lines (requires opencv-contrib)
    try:
        edges = cv2.ximgproc.thinning(bin_img, thinningType=cv2.ximgproc.THINNING_ZHANGSUEN)
    except AttributeError:
        print("Warning: cv2.ximgproc not found — falling back to Canny (double lines).")
        edges = cv2.Canny(bin_img, 50, 150)

    # Remove tiny noise specks
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(edges, connectivity=8)
    clean = np.zeros_like(edges)
    for i in range(1, num_labels):
        if stats[i, cv2.CC_STAT_AREA] >= 15:
            clean[labels == i] = 255
    edges = clean

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        print(f"Warning: no contours found for {out_path}")
        return

    y_coords, x_coords = np.nonzero(edges)
    if len(x_coords) == 0:
        return

    min_x, max_x = x_coords.min(), x_coords.max()
    min_y, max_y = y_coords.min(), y_coords.max()
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
        approx = cv2.approxPolyDP(c, epsilon=1.0, closed=True)
        pts = [px_to_mm(p[0]) for p in approx]
        if len(pts) > 1:
            msp.add_lwpolyline(pts, close=True)

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


def generate_hebrew_text_dxf(hebrew_text, output_path):
    """
    Render Hebrew text to a temp PNG via matplotlib, then export contours as DXF.
    Hebrew is RTL so the string is reversed before rendering.
    """
    temp_img = f"temp_hebrew_{uuid.uuid4()}.png"
    fig = Figure(figsize=(5, 2), facecolor="white")
    ax = fig.add_subplot(111)
    ax.set_facecolor("white")
    ax.text(0.5, 0.5, hebrew_text[::-1], fontsize=36, color='black',
            ha='center', va='center', fontweight='normal', fontname='DejaVu Sans')
    ax.axis("off")
    fig.savefig(temp_img, dpi=300, bbox_inches="tight", pad_inches=0.1,
                facecolor='white')

    try:
        img = cv2.imread(temp_img, cv2.IMREAD_GRAYSCALE)
        if img is not None:
            image_to_dxf_exact(img, output_path)
    finally:
        if os.path.exists(temp_img):
            os.remove(temp_img)


def generate_braille_dxf_from_text(braille_text, output_path):
    """
    Render Braille unicode text to a PNG via matplotlib, then detect
    the dot blobs and export their centres as DXF circles.
    """
    # Render Braille to a temp PNG
    temp_img = f"temp_braille_{uuid.uuid4()}.png"
    fig = Figure(figsize=(3.9, 3.9), facecolor="white")
    ax = fig.add_subplot(111)
    ax.text(0.5, 0.5, braille_text, fontsize=30, color='black',
            ha='center', va='center', fontweight='light', fontname='Noto Sans Symbols2')
    ax.axis("off")
    fig.savefig(temp_img, dpi=300, bbox_inches="tight", pad_inches=0)

    img = cv2.imread(temp_img, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return

    blur   = cv2.GaussianBlur(img, (5, 5), 0)
    binary = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 2
    )

    params = cv2.SimpleBlobDetector_Params()
    params.filterByArea        = True
    params.minArea             = 30
    params.maxArea             = 1500
    params.filterByCircularity = False
    params.filterByConvexity   = False
    params.filterByInertia     = False
    params.minThreshold        = 0
    params.maxThreshold        = 255
    params.thresholdStep       = 5
    detector  = cv2.SimpleBlobDetector_create(params)
    keypoints = detector.detect(binary)

    doc = ezdxf.new()
    msp = doc.modelspace()
    height_px = img.shape[0]
    for kp in keypoints:
        x, y = kp.pt
        r    = kp.size / 2
        msp.add_circle(center=(x, height_px - y), radius=r, dxfattribs={'color': 7})

    doc.saveas(output_path)

    if os.path.exists(temp_img):
        os.remove(temp_img)


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
