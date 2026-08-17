"""
Image processing and DXF export utilities with explicit vertical positioning.
Responsibilities:
- ensure_font(): download and register NotoSansSymbols2 for Braille rendering
- export_png_to_dxf_placed(): exports PNGs into specific Y-zones on a 150mm canvas to prevent overlaps and holes.
- create_smooth_dxf_from_png(): wrapper maintaining backwards compatibility.
"""
import os
import uuid
import urllib.request
import torch
import cv2
import numpy as np
import ezdxf

import matplotlib
matplotlib.use("Agg")  # headless, thread-safe backend
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


# ── Placed DXF Exporter (Fixes holes & overlaps) ──────────────────────────────
def export_png_to_dxf_placed(
    png_path,
    dxf_path,
    y_min_mm,
    y_max_mm,
    canvas_mm=150.0,
    is_drawing=False,
    thickness_boost=4,
    smoothing=0.3
):
    """
    ממיר PNG ל-DXF וממקם אותו במדויק בתוך טווח אנכי מוגדר [y_min_mm, y_max_mm]
    על גבי משטח של canvas_mm. מונע חפייה, נגיעות וחורים בציור ובטקסט.
    """
    img = cv2.imread(str(png_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise RuntimeError(f"Could not load image: {png_path}")

    # הוספת שוליים לבנים רחבים סביב התמונה למניעת קטיעת קווים בפריים
    pad = 40
    img = cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)

    # המרה לשחור-לבן מוחלט (255 = קו/טקסט, 0 = רקע)
    if np.mean(img) > 127:
        img = cv2.bitwise_not(img)
    _, bin_img = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY)

    # סגירת חורים ופתחים בקצוות הקווים
    close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    bin_img = cv2.morphologyEx(bin_img, cv2.MORPH_CLOSE, close_kernel, iterations=1)

    if is_drawing:
        # עיבוי קל לציור כדי להבטיח דפנות חזקות להדפסת 3D
        dilate_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (thickness_boost, thickness_boost))
        bin_img = cv2.dilate(bin_img, dilate_kernel, iterations=1)
        bin_img = cv2.GaussianBlur(bin_img, (5, 5), 0)
        _, bin_img = cv2.threshold(bin_img, 127, 255, cv2.THRESH_BINARY)

    contours, _ = cv2.findContours(bin_img, cv2.RETR_TREE, cv2.CHAIN_APPROX_TC89_KCOS)
    contours = [c for c in contours if cv2.contourArea(c) >= 20]

    if not contours:
        print(f"Warning: no contours found for {dxf_path}")
        return

    all_pts = np.vstack([c.reshape(-1, 2) for c in contours])
    min_x, min_y = all_pts.min(axis=0)
    max_x, max_y = all_pts.max(axis=0)

    w_px = max_x - min_x + 1
    h_px = max_y - min_y + 1

    target_height_mm = y_max_mm - y_min_mm
    target_width_mm = canvas_mm - 20.0  # מרווח של 10 מ"מ מימין ומשמאל

    scale = min(target_width_mm / w_px, target_height_mm / h_px)

    # חישוב אופסט למרכוז אופקי ולאזור האנכי המיועד
    offset_x = (canvas_mm - w_px * scale) / 2.0
    offset_y = y_min_mm + (target_height_mm - h_px * scale) / 2.0

    def px_to_mm(p):
        x_mm = (p[0] - min_x) * scale + offset_x
        # הפיכת ציר Y מ-OpenCV (שבו 0 זה למעלה) ל-DXF (שבו 0 זה למטה)
        y_mm = offset_y + (max_y - p[1]) * scale
        return (x_mm, y_mm)

    doc = ezdxf.new(setup=True)
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()

    epsilon = smoothing if is_drawing else 0.4
    for c in contours:
        approx = cv2.approxPolyDP(c, epsilon=epsilon, closed=True)
        pts = [px_to_mm(p[0]) for p in approx]
        if len(pts) > 2:
            msp.add_lwpolyline(pts, close=True, dxfattribs={"color": 7})

    doc.saveas(dxf_path)


def create_smooth_dxf_from_png(image_path, out_path, canvas_cm=150, thickness_boost=4, smoothing=0.3, margin_ratio=0.15):
    """ Backwards compatible function calling export_png_to_dxf_placed """
    export_png_to_dxf_placed(
        image_path,
        out_path,
        y_min_mm=28.0,
        y_max_mm=122.0,
        canvas_mm=canvas_cm * 1.0,
        is_drawing=True,
        thickness_boost=thickness_boost,
        smoothing=smoothing
    )


def png_to_dxf(png_path, dxf_path, canvas_cm=150):
    """ Backwards compatible function calling export_png_to_dxf_placed """
    export_png_to_dxf_placed(
        png_path,
        dxf_path,
        y_min_mm=128.0,
        y_max_mm=144.0,
        canvas_mm=canvas_cm * 1.0,
        is_drawing=False
    )