"""
Image processing and DXF export utilities.
"""

import os
import uuid
import urllib.request
import torch
import cv2
import numpy as np
import ezdxf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.figure import Figure
from PIL import Image

FONT_FILENAME = "NotoSansSymbols2-Regular.ttf"
FONT_URL = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansSymbols2/NotoSansSymbols2-Regular.ttf"


def ensure_font(font_path=None):
    path = font_path or FONT_FILENAME
    if not os.path.exists(path):
        try:
            print(f"Downloading Braille font to {path}...")
            urllib.request.urlretrieve(FONT_URL, path)
        except Exception as e:
            print(f"Font download failed: {e}")
            return
    fm.fontManager.addfont(path)


def convert_tensor_to_pil_img(tensor):
    image = (tensor / 2 + 0.5).clamp(0, 1).squeeze()
    image = (image.permute(1, 2, 0) * 255).round().to(torch.uint8).cpu().numpy()
    return Image.fromarray(image)


def image_to_dxf_exact(image_bw, out_path, canvas_cm=150, simplify_epsilon=0.8):
    """
    ממירה תמונה ל-DXF חלק, עגול ורציף ללא חורים וללא שברים בקירות ה-3D.
    """
    canvas_mm = canvas_cm * 10.0

    if isinstance(image_bw, (str, os.PathLike)):
        img = cv2.imread(str(image_bw), cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise RuntimeError(f"Could not load image: {image_bw}")
    else:
        img = image_bw.copy()
        if img.ndim == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    h, w = img.shape

    # 1. המרה לבינארי
    if np.mean(img) > 127:
        _, bw = cv2.threshold(img, 200, 255, cv2.THRESH_BINARY_INV)
    else:
        _, bw = cv2.threshold(img, 50, 255, cv2.THRESH_BINARY)

    # 2. איחוי חורים חזק (Kernel 11x11) לגישור על כל נתק בקו
    kernel_bridge = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, kernel_bridge, iterations=2)

    # 3. עיבוי הקו ליציבות הדפסה
    kernel_thick = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    bw = cv2.dilate(bw, kernel_thick, iterations=1)

    # 4. ביטול זיגזגים (Upscale + Blur)
    scale_factor = 4
    bw_large = cv2.resize(bw, (w * scale_factor, h * scale_factor), interpolation=cv2.INTER_CUBIC)
    bw_large = cv2.GaussianBlur(bw_large, (7, 7), 0)
    _, bw_smooth = cv2.threshold(bw_large, 127, 255, cv2.THRESH_BINARY)

    # 5. חילוץ קווי מעטפת
    contours, _ = cv2.findContours(bw_smooth, cv2.RETR_TREE, cv2.CHAIN_APPROX_TC89_KCOS)
    if not contours:
        print(f"Warning: no contours found for {out_path}")
        return

    full_area = (w * scale_factor) * (h * scale_factor)
    filtered_contours = [
        c for c in contours
        if cv2.contourArea(c) < (full_area * 0.98) and cv2.contourArea(c) >= (15 * scale_factor * scale_factor)
    ]
    if not filtered_contours:
        filtered_contours = contours

    # 6. חישוב מידות
    all_pts = np.vstack([c.reshape(-1, 2) for c in filtered_contours])
    min_x, min_y = all_pts.min(axis=0)
    max_x, max_y = all_pts.max(axis=0)
    w_px = max_x - min_x + 1
    h_px = max_y - min_y + 1

    scale = canvas_mm / max(w_px, h_px) if max(w_px, h_px) > 0 else 1.0
    offset_x = (canvas_mm - w_px * scale) / 2
    offset_y = (canvas_mm - h_px * scale) / 2

    def px_to_mm(p):
        return (
            (p[0] - min_x) * scale + offset_x,
            (max_y - p[1]) * scale + offset_y
        )

    doc = ezdxf.new(setup=True)
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()

    # 7. יצירת פוליגונים סגורים
    for c in filtered_contours:
        approx = cv2.approxPolyDP(c, epsilon=simplify_epsilon * scale_factor, closed=True)
        pts = [px_to_mm(p[0]) for p in approx]
        if len(pts) > 2:
            msp.add_lwpolyline(pts, close=True, dxfattribs={'color': 7})

    doc.saveas(out_path)


def process_image_to_dxf(img_array, output_path, canvas_cm=150):
    image_to_dxf_exact(img_array, output_path, canvas_cm)


def png_to_dxf(png_path, dxf_path, canvas_cm=150):
    image_to_dxf_exact(png_path, dxf_path, canvas_cm)


def _filled_glyphs_to_dxf(image_bw, out_path, canvas_cm=150):
    canvas_mm = canvas_cm * 10.0
    img = image_bw.copy()
    if img.dtype != np.uint8:
        img = img.astype(np.uint8)
    if np.mean(img) > 127:
        img = cv2.bitwise_not(img)
    _, bin_img = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY)

    contours, _ = cv2.findContours(bin_img, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        print(f"Warning: no glyph contours found for {out_path}")
        return

    all_pts = np.vstack([c.reshape(-1, 2) for c in contours])
    min_x, min_y = all_pts.min(axis=0)
    max_x, max_y = all_pts.max(axis=0)
    w_px, h_px = (max_x - min_x + 1), (max_y - min_y + 1)
    scale = canvas_mm / max(w_px, h_px) if max(w_px, h_px) > 0 else 1.0
    offset_x = (canvas_mm - w_px * scale) / 2
    offset_y = (canvas_mm - h_px * scale) / 2

    def px_to_mm(p):
        return (
            (p[0] - min_x) * scale + offset_x,
            (max_y - p[1]) * scale + offset_y
        )

    doc = ezdxf.new(setup=True)
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()
    for c in contours:
        approx = cv2.approxPolyDP(c, epsilon=0.5, closed=True)
        pts = [px_to_mm(p[0]) for p in approx]
        if len(pts) > 2:
            msp.add_lwpolyline(pts, close=True)
    doc.saveas(out_path)


def generate_text_dxf(text, output_path, rtl=True):
    render_text = text[::-1] if rtl else text
    temp_img = f"temp_text_{uuid.uuid4()}.png"
    fig = Figure(figsize=(5, 2), facecolor="white")
    ax = fig.add_subplot(111)
    ax.set_facecolor("white")
    ax.text(
        0.5, 0.5, render_text, fontsize=36, color='black',
        ha='center', va='center', fontweight='normal', fontname='DejaVu Sans'
    )
    ax.axis("off")
    fig.savefig(
        temp_img, dpi=300, bbox_inches="tight", pad_inches=0.1, facecolor='white'
    )

    try:
        img = cv2.imread(temp_img, cv2.IMREAD_GRAYSCALE)
        if img is not None:
            _filled_glyphs_to_dxf(img, output_path)
    finally:
        if os.path.exists(temp_img):
            os.remove(temp_img)


def generate_hebrew_text_dxf(hebrew_text, output_path):
    generate_text_dxf(hebrew_text, output_path, rtl=True)


BRAILLE_DOT_SPACING_MM = 2.5
BRAILLE_CELL_SPACING_MM = 6.0
BRAILLE_DOT_RADIUS_MM = 0.75
_BRAILLE_DOT_CELL = {0: (0, 0), 1: (0, 1), 2: (0, 2), 3: (1, 0), 4: (1, 1), 5: (1, 2)}


def generate_braille_dxf_from_text(braille_text, output_path):
    doc = ezdxf.new(setup=True)
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()
    dot = BRAILLE_DOT_SPACING_MM
    for i, ch in enumerate(braille_text):
        code = ord(ch) - 0x2800
        if code < 0 or code > 0xFF:
            continue
        x0 = i * BRAILLE_CELL_SPACING_MM
        for bit, (col, row) in _BRAILLE_DOT_CELL.items():
            if code & (1 << bit):
                cx = x0 + col * dot
                cy = (2 - row) * dot
                msp.add_circle(
                    center=(cx, cy), radius=BRAILLE_DOT_RADIUS_MM, dxfattribs={'color': 7}
                )
    doc.saveas(output_path)


def plot_dxf(dxf_path):
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
                    x.append(x[0])
                    y.append(y[0])
                plt.plot(x, y, color='black', linewidth=1)
            elif entity.dxftype() == 'CIRCLE':
                cx, cy = entity.dxf.center.x, entity.dxf.center.y
                r = entity.dxf.radius
                theta = np.linspace(0, 2 * np.pi, 100)
                plt.plot(
                    cx + r * np.cos(theta), cy + r * np.sin(theta),
                    color='black', linewidth=1
                )

        plt.axis('equal')
        plt.title(f"DXF: {dxf_path}")
        plt.axis('off')
        plt.show()
    except Exception as e:
        print(f"Could not plot DXF: {e}")