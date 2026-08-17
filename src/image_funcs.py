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

def heal_dxf_fragments(input_dxf, output_dxf, max_gap_mm=20.0, simplify_epsilon=1.5):
    """
    מנגנון "אריזת וואקום" (Shrink-Wrap): מנפח את כל המקטעים עד למיזוג מלא,
    מוצא את קו המתאר החיצוני ביותר, ומכווץ חזרה. מבטיח צורה אחת סגורה ורציפה.
    """

    try:
        doc = ezdxf.readfile(input_dxf)
    except IOError:
        print(f"Error: Could not read {input_dxf}")
        return

    msp = doc.modelspace()
    all_pts = []
    for entity in msp:
        if entity.dxftype() == 'LWPOLYLINE':
            all_pts.extend(entity.get_points('xy'))

    if not all_pts:
        return

    all_pts = np.array(all_pts)
    min_x, min_y = all_pts.min(axis=0)
    max_x, max_y = all_pts.max(axis=0)

    ppm = 10
    w_px = int((max_x - min_x) * ppm) + 100
    h_px = int((max_y - min_y) * ppm) + 100
    canvas = np.zeros((h_px, w_px), dtype=np.uint8)

    def to_px(x, y):
        return int((x - min_x) * ppm) + 50, int((y - min_y) * ppm) + 50

    # 1. ציור כל המקטעים השבורים בעובי ראשוני
    for entity in msp:
        if entity.dxftype() == 'LWPOLYLINE':
            pts = [to_px(p[0], p[1]) for p in entity.get_points('xy')]
            pts_arr = np.array(pts, np.int32)
            cv2.fillPoly(canvas, [pts_arr], 255)
            cv2.polylines(canvas, [pts_arr], True, 255, thickness=6)

    # 2. שלב הניפוח (Dilation) - ממזג הכל לגוש אחד
    gap_px = int(max_gap_mm * ppm)
    kernel_size = min(gap_px, 150)  # הגבלה כדי לא להעמיס על הזיכרון
    if kernel_size % 2 == 0:
        kernel_size += 1

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    fused = cv2.dilate(canvas, kernel, iterations=1)

    # 3. מילוי חורים פנימיים לחלוטין (מבטיח שלא יהיו חורים בתוך החתול)
    contours, _ = cv2.findContours(fused, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    fused_filled = np.zeros_like(fused)
    cv2.fillPoly(fused_filled, contours, 255)

    # 4. שלב הכיווץ חזרה (Erosion) - מחזיר את הצורה לגודל המקורי
    restored = cv2.erode(fused_filled, kernel, iterations=1)

    # החלקה אחרונה למראה טבעי ונעים למגע
    restored = cv2.GaussianBlur(restored, (11, 11), 0)
    _, restored = cv2.threshold(restored, 127, 255, cv2.THRESH_BINARY)

    # 5. חילוץ ושמירת קו המתאר *החיצוני היחיד* ל-DXF
    final_contours, _ = cv2.findContours(restored, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_TC89_KCOS)

    new_doc = ezdxf.new(setup=True)
    new_doc.units = ezdxf.units.MM
    new_msp = new_doc.modelspace()

    # ניקח רק את הצורה הגדולה ביותר כדי לסנן לכלוכים שנותרו בחוץ
    if final_contours:
        largest_contour = max(final_contours, key=cv2.contourArea)
        approx = cv2.approxPolyDP(largest_contour, epsilon=simplify_epsilon * ppm, closed=True)
        dxf_pts = []
        for p in approx:
            px, py = p[0]
            mx = ((px - 50) / ppm) + min_x
            my = ((py - 50) / ppm) + min_y
            dxf_pts.append((mx, my))

        if len(dxf_pts) > 2:
            new_msp.add_lwpolyline(dxf_pts, close=True, dxfattribs={"color": 7})

    new_doc.saveas(output_dxf)


def image_to_dxf_exact(image_bw, out_path, canvas_cm=150, simplify_epsilon=2.0, bridge_gaps=True):
    """
    Convert a grayscale/binary image OR image path to a smoother DXF polyline file.
    Good for tactile / 3D-printable image outlines.

    Main fixes:
    - accepts path or numpy array
    - aggressive gap bridging for fragmented/dashed lines (bridge_gaps=True)
    - smooths the binary mask before contour extraction
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

    # ── מנגנון התיקון והשלמת הקווים המקוטעים ──
    if bridge_gaps:
        # 1. סגירה אגרסיבית (Closing) לחיבור נתקים גדולים
        # מכיוון שהגדלנו פי 4, קרנל של 25x25 יסגור רווחים של כ-6 פיקסלים בתמונה המקורית
        close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (35, 35))
        bin_img = cv2.morphologyEx(bin_img, cv2.MORPH_CLOSE, close_kernel, iterations=1)

        # 2. הרחבה (Dilation) ולאחריה כיווץ (Erosion)
        # מותח את הקווים אחד לכיוון השני כדי להבטיח מגע, ואז מכווץ חזרה לשמירה על עובי הקו
        dilate_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
        erode_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))

        bin_img = cv2.dilate(bin_img, dilate_kernel, iterations=1)
        bin_img = cv2.erode(bin_img, erode_kernel, iterations=1)

        # 3. ניקוי רעשים (Opening) - מחיקת "איים" קטנים ולכלוכים
        open_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
        bin_img = cv2.morphologyEx(bin_img, cv2.MORPH_OPEN, open_kernel, iterations=1)

    else:
        # ההתנהגות הישנה (גישור חלש)
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

    gray = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (7, 7), 0)
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
        approx = cv2.approxPolyDP(cnt, epsilon, False)
        points = [(float(p[0][0]), float(height - p[0][1])) for p in approx]
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

    scale = canvas_mm / max(w_px, h_px)
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


def clean_uploaded_image_to_png(src_path, out_png_path, max_side=1600):
    """
    Best-effort cleanup of a *user-supplied* drawing (phone photo or scan, JPG or PNG)
    into a clean black-on-white line PNG that png_to_dxf() can trace.

    Unlike png_to_dxf's fixed threshold (fine for crisp digital line art), a photo has
    uneven lighting and paper texture, so we use an adaptive threshold + morphology +
    despeckle. Output is dark lines on a white ground (what png_to_dxf expects).
    """
    img = cv2.imread(src_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise RuntimeError(f"Could not load uploaded image {src_path}")

    # Downscale oversized photos — keeps tracing fast and stable (detail beyond this
    # is noise for tactile line art anyway).
    h, w = img.shape[:2]
    if max(h, w) > max_side:
        s = max_side / float(max(h, w))
        img = cv2.resize(img, (int(round(w * s)), int(round(h * s))), interpolation=cv2.INTER_AREA)

    blur = cv2.GaussianBlur(img, (5, 5), 0)
    # Dark strokes on light paper → INV gives white strokes on black for morphology.
    binary = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 7
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    binary = cv2.medianBlur(binary, 3)  # drop isolated specks from paper grain

    # png_to_dxf wants dark lines on white → invert back.
    cv2.imwrite(out_png_path, cv2.bitwise_not(binary))
    return out_png_path


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
    if np.mean(img) > 127:  # want white glyphs on black
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
    scale = canvas_mm / max(w_px, h_px)
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
BRAILLE_DOT_SPACING_MM = 2.5  # between dots within a cell (horizontal & vertical)
BRAILLE_CELL_SPACING_MM = 6.0  # between the same dot of adjacent cells
BRAILLE_DOT_RADIUS_MM = 0.75
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
        if code < 0 or code > 0xFF:  # space / non-Braille — advance one cell, no dots
            continue
        x0 = i * BRAILLE_CELL_SPACING_MM
        for bit, (col, row) in _BRAILLE_DOT_CELL.items():
            if code & (1 << bit):
                cx = x0 + col * dot
                cy = (2 - row) * dot  # y up: row 0 (top) is highest
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
                    x.append(x[0])
                    y.append(y[0])
                plt.plot(x, y, color='black', linewidth=1)
            elif entity.dxftype() == 'CIRCLE':
                cx, cy = entity.dxf.center.x, entity.dxf.center.y
                r = entity.dxf.radius
                theta = np.linspace(0, 2 * np.pi, 100)
                plt.plot(cx + r * np.cos(theta), cy + r * np.sin(theta),
                         color='black', linewidth=1)

        plt.axis('equal')
        plt.title(f"DXF: {dxf_path}")
        plt.axis('off')
        plt.show()
    except Exception as e:
        print(f"Could not plot DXF: {e}")

def thicken_png_lines(image_path, thickness=6):
    """
    קורא את תמונת ה-PNG, מעבה את הקווים השחורים, ושומר חזרה.
    זה שומר על הפרטים הפנימיים (כמו עיניים) אבל מונע שבירה של קווים דקים ב-DXF.
    """
    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return

    # הופכים את התמונה (כדי שהקווים יהיו לבנים והרקע שחור - כך הניפוח עובד)
    inverted = cv2.bitwise_not(img)

    # מעבים את הקווים (Dilation)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (thickness, thickness))
    thickened = cv2.dilate(inverted, kernel, iterations=1)

    # הופכים חזרה לשחור על לבן ושומרים
    final_img = cv2.bitwise_not(thickened)
    cv2.imwrite(str(image_path), final_img)

def create_smooth_dxf_from_png(image_path, out_path, canvas_cm=150, thickness_boost=3, smoothing=0.3):
    """
    ממיר תמונת PNG ל-DXF בצורה חלקה ומדויקת.
    - שומר על פרטים פנימיים (עיניים, קווים פנימיים).
    - מגשר על נתקים קטנים בלי להרוס את הצורה.
    - מייצר קווים עגולים וחלקים ללא אפקט "מדרגות".
    """

    canvas_mm = canvas_cm * 10.0

    # 1. טעינת התמונה
    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise RuntimeError(f"Could not load image: {image_path}")

    # המרה לשחור-לבן מוחלט (הקווים צריכים להיות לבנים על רקע שחור בשביל זיהוי אלגוריתמי)
    if np.mean(img) > 127:
        img = cv2.bitwise_not(img)
    _, bin_img = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY)

    # 2. איחוי נתקים עדין ועיבוי הקו
    # שימוש בקרנל קטן שסוגר חורים בלי להפוך את הציור לגוש אטום
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (thickness_boost, thickness_boost))
    bin_img = cv2.dilate(bin_img, kernel, iterations=1)

    # החלקה קלה לטשטוש הפיקסלים המרובעים
    bin_img = cv2.GaussianBlur(bin_img, (5, 5), 0)
    _, bin_img = cv2.threshold(bin_img, 127, 255, cv2.THRESH_BINARY)

    # 3. מציאת קווי המתאר (הפנימיים והחיצוניים כאחד!)
    # RETR_TREE מוודא שנקבל גם את קו המתאר החיצוני וגם את העיניים והאף של החתול
    contours, _ = cv2.findContours(bin_img, cv2.RETR_TREE, cv2.CHAIN_APPROX_TC89_KCOS)

    # סינון רעשים - התעלמות מנקודות קטנטנות
    contours = [c for c in contours if cv2.contourArea(c) >= 50]

    if not contours:
        print(f"Warning: no significant contours for {out_path}")
        return

    # 4. חישוב קנה מידה ומרכוז
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

    # 5. יצירת קובץ ה-DXF ושמירה
    doc = ezdxf.new(setup=True)
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()

    for c in contours:
        # epsilon קטן מאוד (0.3) מבטיח שהקו יהיה עגול וחלק ולא מדורג/משונן
        approx = cv2.approxPolyDP(c, epsilon=smoothing, closed=True)

        pts = [px_to_mm(p[0]) for p in approx]

        if len(pts) > 2:
            msp.add_lwpolyline(pts, close=True, dxfattribs={"color": 7})

    doc.saveas(out_path)


def create_pencil_dxf_from_png(
    image_path,
    out_path,
    canvas_cm=150,
    gap_size=31,
    simplify=1.0
):
    """
    PNG -> DXF סגור לחלוטין להדפסה תלת-ממדית.

    אין skeletonization.
    אין קווים פתוחים.
    כל contour מיוצא כ-polyline סגור.
    הנקודה הראשונה מתווספת שוב בסוף באופן מפורש,
    בנוסף ל-close=True, כדי להבטיח סגירה גם בתוכנות
    שמפרשות DXF בצורה לא מושלמת.
    """

    canvas_mm = canvas_cm * 10.0

    # ---------------------------------------------------------
    # 1. Load PNG
    # ---------------------------------------------------------
    img = cv2.imread(
        str(image_path),
        cv2.IMREAD_GRAYSCALE
    )

    if img is None:
        raise RuntimeError(
            f"Could not load image: {image_path}"
        )

    # ---------------------------------------------------------
    # 2. Black drawing -> white mask
    # ---------------------------------------------------------
    _, bw = cv2.threshold(
        img,
        180,
        255,
        cv2.THRESH_BINARY_INV
    )

    # ---------------------------------------------------------
    # 3. Remove tiny noise
    # ---------------------------------------------------------
    open_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (3, 3)
    )

    bw = cv2.morphologyEx(
        bw,
        cv2.MORPH_OPEN,
        open_kernel,
        iterations=1
    )

    # ---------------------------------------------------------
    # 4. IMPORTANT:
    # Close gaps BEFORE contour extraction
    # ---------------------------------------------------------
    close_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (gap_size, gap_size)
    )

    bw = cv2.morphologyEx(
        bw,
        cv2.MORPH_CLOSE,
        close_kernel,
        iterations=2
    )

    # ---------------------------------------------------------
    # 5. Small dilation to guarantee touching
    # ---------------------------------------------------------
    connect_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (5, 5)
    )

    bw = cv2.dilate(
        bw,
        connect_kernel,
        iterations=1
    )

    # ---------------------------------------------------------
    # 6. Smooth
    # ---------------------------------------------------------
    bw = cv2.GaussianBlur(
        bw,
        (5, 5),
        0
    )

    _, bw = cv2.threshold(
        bw,
        127,
        255,
        cv2.THRESH_BINARY
    )

    # ---------------------------------------------------------
    # 7. Find CLOSED contours
    # ---------------------------------------------------------
    contours, hierarchy = cv2.findContours(
        bw,
        cv2.RETR_TREE,
        cv2.CHAIN_APPROX_TC89_KCOS
    )

    if not contours:
        raise RuntimeError(
            f"No contours found in {image_path}"
        )

    # Remove tiny components
    contours = [
        c for c in contours
        if cv2.contourArea(c) >= 50
    ]

    if not contours:
        raise RuntimeError(
            f"No significant contours found in {image_path}"
        )

    # ---------------------------------------------------------
    # 8. Bounding box
    # ---------------------------------------------------------
    all_pts = np.vstack([
        c.reshape(-1, 2)
        for c in contours
    ])

    min_x, min_y = all_pts.min(axis=0)
    max_x, max_y = all_pts.max(axis=0)

    width = max_x - min_x + 1
    height = max_y - min_y + 1

    scale = canvas_mm / max(width, height)

    offset_x = (
        canvas_mm - width * scale
    ) / 2.0

    offset_y = (
        canvas_mm - height * scale
    ) / 2.0

    def px_to_mm(p):
        return (
            (float(p[0]) - min_x) * scale + offset_x,
            (max_y - float(p[1])) * scale + offset_y
        )

    # ---------------------------------------------------------
    # 9. Create DXF
    # ---------------------------------------------------------
    doc = ezdxf.new(setup=True)
    doc.units = ezdxf.units.MM

    msp = doc.modelspace()

    exported = 0

    for contour in contours:

        perimeter = cv2.arcLength(
            contour,
            True
        )

        if perimeter < 30:
            continue

        approx = cv2.approxPolyDP(
            contour,
            epsilon=simplify,
            closed=True
        )

        if len(approx) < 3:
            continue

        points = [
            px_to_mm(p[0])
            for p in approx
        ]

        # -----------------------------------------------------
        # CRITICAL:
        # Explicitly repeat first point at the end.
        # -----------------------------------------------------
        if points[0] != points[-1]:
            points.append(points[0])

        # DXF closed polyline
        msp.add_lwpolyline(
            points,
            close=True,
            dxfattribs={
                "color": 7
            }
        )

        exported += 1

    if exported == 0:
        raise RuntimeError(
            f"No usable closed contours found in {image_path}"
        )

    doc.saveas(out_path)

    print(
        f"Created CLOSED DXF: {out_path}"
    )
    print(
        f"Closed contours exported: {exported}"
    )

def repair_dxf_gaps(
    input_dxf,
    output_dxf,
    max_gap_mm=25.0,
    gap_factor=8.0,
    angle_tolerance_deg=50.0,
):
    """
    Repair geometric gaps inside DXF polylines.

    Unlike the old implementation, this function does NOT rely on
    whether the polyline is marked as open/closed.

    It detects unusually long segments between consecutive points.
    A segment is considered a possible gap when:

        1. Its length is <= max_gap_mm
        2. It is much longer than the local normal segment length
        3. The geometry before and after the gap has a similar direction

    The gap is repaired by inserting points along the missing segment,
    so the original polyline remains one continuous closed polyline.

    This is generic and does not assume the shape is a circle.
    """

    import math

    doc = ezdxf.readfile(input_dxf)
    msp = doc.modelspace()

    repaired_count = 0

    def distance(a, b):
        return float(np.linalg.norm(b - a))

    def angle_between(v1, v2):
        """
        Return angle between two vectors in degrees.
        """
        n1 = np.linalg.norm(v1)
        n2 = np.linalg.norm(v2)

        if n1 < 1e-9 or n2 < 1e-9:
            return 180.0

        cos_angle = np.dot(v1, v2) / (n1 * n2)
        cos_angle = np.clip(cos_angle, -1.0, 1.0)

        return math.degrees(math.acos(cos_angle))

    for entity in list(msp):

        if entity.dxftype() != "LWPOLYLINE":
            continue

        raw_points = list(entity.get_points("xy"))

        if len(raw_points) < 4:
            continue

        points = [
            np.array([float(p[0]), float(p[1])], dtype=float)
            for p in raw_points
        ]

        # ---------------------------------------------------------
        # Remove explicit duplicated last point if present.
        # close=True will handle the closing segment.
        # ---------------------------------------------------------

        if distance(points[0], points[-1]) < 1e-6:
            points.pop()

        if len(points) < 4:
            continue

        closed = entity.is_closed

        # ---------------------------------------------------------
        # Build list of segment lengths.
        #
        # For closed polylines we also inspect the last -> first
        # segment.
        # ---------------------------------------------------------

        segment_count = len(points) if closed else len(points) - 1

        lengths = []

        for i in range(segment_count):

            j = (i + 1) % len(points)

            lengths.append(
                distance(points[i], points[j])
            )

        if not lengths:
            continue

        # ---------------------------------------------------------
        # Robust local reference length.
        #
        # Very large gaps should not influence the median.
        # ---------------------------------------------------------

        normal_lengths = [
            x for x in lengths
            if x > 1e-6
        ]

        if not normal_lengths:
            continue

        median_length = float(
            np.median(normal_lengths)
        )

        # Prevent tiny DXF contours from producing ridiculous
        # sensitivity.
        reference_length = max(
            median_length,
            0.05
        )

        new_points = []
        changed = False

        # ---------------------------------------------------------
        # Walk through every segment.
        # ---------------------------------------------------------

        for i in range(segment_count):

            j = (i + 1) % len(points)

            p1 = points[i]
            p2 = points[j]

            segment_length = lengths[i]

            # Always keep current point.
            new_points.append(p1)

            # -----------------------------------------------------
            # Is this segment suspiciously long?
            # -----------------------------------------------------

            is_possible_gap = (
                segment_length <= max_gap_mm
                and
                segment_length >
                reference_length * gap_factor
            )

            if not is_possible_gap:
                continue

            # -----------------------------------------------------
            # We need geometry on both sides of the suspicious
            # segment.
            # -----------------------------------------------------

            prev_i = (i - 1) % len(points)
            next_j = (j + 1) % len(points)

            if not closed:
                if i == 0 or j == len(points) - 1:
                    continue

            prev_point = points[prev_i]
            next_point = points[next_j]

            incoming = p1 - prev_point
            outgoing = next_point - p2

            # -----------------------------------------------------
            # The two sides should continue in roughly the same
            # direction.
            #
            # For a missing section of a circle, the direction
            # changes gradually, so a fairly generous tolerance
            # is appropriate.
            # -----------------------------------------------------

            angle = angle_between(
                incoming,
                outgoing
            )

            if angle > angle_tolerance_deg:
                continue

            # -----------------------------------------------------
            # Estimate how many points should be inserted.
            #
            # We do NOT need to create hundreds of points.
            # The goal is simply to remove the giant jump.
            # -----------------------------------------------------

            target_spacing = max(
                reference_length,
                0.5
            )

            subdivisions = max(
                2,
                int(
                    math.ceil(
                        segment_length /
                        target_spacing
                    )
                )
            )

            # -----------------------------------------------------
            # Insert interpolated points along the missing section.
            # -----------------------------------------------------

            for k in range(1, subdivisions):

                t = k / subdivisions

                interpolated = (
                    p1 * (1.0 - t)
                    +
                    p2 * t
                )

                new_points.append(
                    interpolated
                )

            repaired_count += 1
            changed = True

        # ---------------------------------------------------------
        # Nothing suspicious was found.
        # ---------------------------------------------------------

        if not changed:
            continue

        # ---------------------------------------------------------
        # Remove old entity.
        # ---------------------------------------------------------

        msp.delete_entity(entity)

        # ---------------------------------------------------------
        # Convert points back to DXF format.
        # ---------------------------------------------------------

        dxf_points = [
            (
                float(p[0]),
                float(p[1])
            )
            for p in new_points
        ]

        if len(dxf_points) >= 3:

            msp.add_lwpolyline(
                dxf_points,
                close=closed,
                dxfattribs={
                    "color": 7
                }
            )

    doc.saveas(output_dxf)

    print(
        f"DXF geometric repair: "
        f"repaired {repaired_count} suspicious gaps"
    )


def repair_pencil_dxf(
    input_dxf,
    output_dxf,
    max_gap_mm=25.0,
    raster_resolution=4,
    line_thickness_px=5,
    simplify_mm=0.8,
):
    """
    Repairs broken DXF line drawings WITHOUT relying on DXF contours.

    Strategy:
        DXF geometry
            ↓
        rasterize every LINE / LWPOLYLINE segment
            ↓
        morphological gap closing
            ↓
        skeletonization
            ↓
        trace skeleton paths
            ↓
        new DXF

    This is especially useful after create_pencil_dxf_from_png(),
    where a visually broken line may already have been converted into
    several separate closed contours.

    max_gap_mm:
        Maximum physical gap that may be bridged.

    raster_resolution:
        Number of raster pixels per mm.

    line_thickness_px:
        Rasterization thickness.

    simplify_mm:
        Final DXF polyline simplification tolerance.
    """

    import math

    # ------------------------------------------------------------
    # 1. Read DXF
    # ------------------------------------------------------------

    try:
        doc = ezdxf.readfile(input_dxf)
    except IOError:
        raise RuntimeError(
            f"Could not read DXF: {input_dxf}"
        )

    msp = doc.modelspace()

    entities = [
        e for e in msp
        if e.dxftype() in ("LWPOLYLINE", "POLYLINE", "LINE")
    ]

    if not entities:
        raise RuntimeError(
            f"No drawable line entities found in {input_dxf}"
        )

    # ------------------------------------------------------------
    # 2. Extract ALL line segments
    #
    # Important:
    # We deliberately do not care whether the entity is closed.
    # A closed contour and an open line are treated identically.
    # ------------------------------------------------------------

    segments = []

    for entity in entities:

        if entity.dxftype() == "LINE":

            p1 = np.array([
                float(entity.dxf.start.x),
                float(entity.dxf.start.y)
            ])

            p2 = np.array([
                float(entity.dxf.end.x),
                float(entity.dxf.end.y)
            ])

            segments.append((p1, p2))

        elif entity.dxftype() == "LWPOLYLINE":

            pts = [
                np.array(
                    [float(p[0]), float(p[1])],
                    dtype=float
                )
                for p in entity.get_points("xy")
            ]

            if len(pts) < 2:
                continue

            for i in range(len(pts) - 1):
                segments.append(
                    (pts[i], pts[i + 1])
                )

            # Handle closed polyline geometrically.
            if entity.is_closed and len(pts) >= 3:
                segments.append(
                    (pts[-1], pts[0])
                )

        elif entity.dxftype() == "POLYLINE":

            pts = []

            for vertex in entity.vertices:
                pts.append(
                    np.array(
                        [
                            float(vertex.dxf.location.x),
                            float(vertex.dxf.location.y)
                        ],
                        dtype=float
                    )
                )

            if len(pts) < 2:
                continue

            for i in range(len(pts) - 1):
                segments.append(
                    (pts[i], pts[i + 1])
                )

            if entity.is_closed:
                segments.append(
                    (pts[-1], pts[0])
                )

    if not segments:
        raise RuntimeError(
            f"No usable line segments found in {input_dxf}"
        )

    # ------------------------------------------------------------
    # 3. Calculate bounding box
    # ------------------------------------------------------------

    all_points = np.vstack([
        np.vstack([a, b])
        for a, b in segments
    ])

    min_x, min_y = all_points.min(axis=0)
    max_x, max_y = all_points.max(axis=0)

    padding_mm = max_gap_mm + 10.0

    min_x -= padding_mm
    min_y -= padding_mm
    max_x += padding_mm
    max_y += padding_mm

    width_mm = max_x - min_x
    height_mm = max_y - min_y

    # ------------------------------------------------------------
    # 4. Build raster canvas
    # ------------------------------------------------------------

    ppm = float(raster_resolution)

    width_px = int(
        math.ceil(width_mm * ppm)
    )

    height_px = int(
        math.ceil(height_mm * ppm)
    )

    # Safety limit
    max_dimension = 12000

    if max(width_px, height_px) > max_dimension:

        scale_down = (
            max_dimension /
            max(width_px, height_px)
        )

        ppm *= scale_down

        width_px = int(
            math.ceil(width_mm * ppm)
        )

        height_px = int(
            math.ceil(height_mm * ppm)
        )

    canvas = np.zeros(
        (height_px, width_px),
        dtype=np.uint8
    )

    def mm_to_px(point):
        x, y = point

        px = int(
            round((x - min_x) * ppm)
        )

        py = int(
            round((max_y - y) * ppm)
        )

        return px, py

    # ------------------------------------------------------------
    # 5. Rasterize ALL geometry
    #
    # This is the critical difference from the old repair.
    #
    # We don't care whether the DXF contains:
    #
    #     contour A
    #     contour B
    #     contour C
    #
    # Everything becomes one binary geometric field.
    # ------------------------------------------------------------

    for p1, p2 in segments:

        a = mm_to_px(p1)
        b = mm_to_px(p2)

        cv2.line(
            canvas,
            a,
            b,
            255,
            thickness=max(1, int(line_thickness_px)),
            lineType=cv2.LINE_AA
        )

    # ------------------------------------------------------------
    # 6. Close gaps
    #
    # max_gap_mm is converted into pixels.
    #
    # Example:
    # max_gap_mm = 25
    # raster_resolution = 4
    #
    # → approximately 100 px gap-closing radius.
    # ------------------------------------------------------------

    gap_px = max(
        3,
        int(round(max_gap_mm * ppm))
    )

    # Don't create absurdly large kernels.
    # Multiple smaller closing operations are more stable.
    kernel_size = min(
        gap_px * 2 + 1,
        401
    )

    if kernel_size % 2 == 0:
        kernel_size += 1

    close_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (kernel_size, kernel_size)
    )

    repaired = cv2.morphologyEx(
        canvas,
        cv2.MORPH_CLOSE,
        close_kernel,
        iterations=1
    )

    # ------------------------------------------------------------
    # 7. Slight dilation before skeletonization
    #
    # This helps when two sides of a broken line are very close
    # but not actually touching after rasterization.
    # ------------------------------------------------------------

    connect_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (5, 5)
    )

    repaired = cv2.dilate(
        repaired,
        connect_kernel,
        iterations=1
    )

    # ------------------------------------------------------------
    # 8. Skeletonization
    #
    # OpenCV does not always contain ximgproc.
    # Try it first, then use a morphological fallback.
    # ------------------------------------------------------------

    skeleton = None

    if hasattr(cv2, "ximgproc") and hasattr(
        cv2.ximgproc,
        "thinning"
    ):
        skeleton = cv2.ximgproc.thinning(
            repaired
        )

    else:
        # Zhang-Suen style morphological skeleton fallback.
        skeleton = np.zeros_like(repaired)
        temp = repaired.copy()

        skel_kernel = cv2.getStructuringElement(
            cv2.MORPH_CROSS,
            (3, 3)
        )

        while True:

            eroded = cv2.erode(
                temp,
                skel_kernel
            )

            opened = cv2.dilate(
                eroded,
                skel_kernel
            )

            difference = cv2.subtract(
                temp,
                opened
            )

            skeleton = cv2.bitwise_or(
                skeleton,
                difference
            )

            temp = eroded.copy()

            if cv2.countNonZero(temp) == 0:
                break

    # ------------------------------------------------------------
    # 9. Remove isolated tiny noise
    # ------------------------------------------------------------

    num_labels, labels, stats, _ = (
        cv2.connectedComponentsWithStats(
            skeleton,
            connectivity=8
        )
    )

    cleaned_skeleton = np.zeros_like(skeleton)

    # Keep reasonably large connected structures.
    # Since the DXF is already cleaned, tiny components are noise.
    min_component_px = max(
        10,
        int(ppm * 2)
    )

    for i in range(1, num_labels):

        area = stats[
            i,
            cv2.CC_STAT_AREA
        ]

        if area >= min_component_px:
            cleaned_skeleton[
                labels == i
            ] = 255

    skeleton = cleaned_skeleton

    # ------------------------------------------------------------
    # 10. Convert skeleton pixels back into paths
    #
    # We trace connected skeleton components.
    # This is NOT contour-based repair.
    # Contours are not used to decide where gaps exist.
    # ------------------------------------------------------------

    num_labels, labels, stats, centroids = (
        cv2.connectedComponentsWithStats(
            skeleton,
            connectivity=8
        )
    )

    paths = []

    for label_id in range(1, num_labels):

        component = np.zeros_like(
            skeleton
        )

        component[
            labels == label_id
        ] = 255

        ys, xs = np.where(
            component > 0
        )

        if len(xs) < 5:
            continue

        # --------------------------------------------------------
        # Simplest robust tracing:
        # collect skeleton pixels and order them using nearest
        # neighbor traversal.
        # --------------------------------------------------------

        points_px = np.column_stack(
            [xs, ys]
        ).astype(float)

        if len(points_px) < 2:
            continue

        # Start from an endpoint when available.
        endpoint = None

        point_set = {
            (int(x), int(y))
            for x, y in points_px
        }

        for x, y in point_set:

            neighbours = 0

            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):

                    if dx == 0 and dy == 0:
                        continue

                    if (
                        x + dx,
                        y + dy
                    ) in point_set:
                        neighbours += 1

            if neighbours == 1:
                endpoint = np.array(
                    [x, y],
                    dtype=float
                )
                break

        if endpoint is None:
            endpoint = points_px[0]

        remaining = points_px.copy()

        ordered = [
            endpoint
        ]

        # Remove starting point.
        distances = np.linalg.norm(
            remaining - endpoint,
            axis=1
        )

        remaining = np.delete(
            remaining,
            np.argmin(distances),
            axis=0
        )

        current = endpoint

        while len(remaining) > 0:

            distances = np.linalg.norm(
                remaining - current,
                axis=1
            )

            idx = int(
                np.argmin(distances)
            )

            next_point = remaining[idx]

            # Stop if this is clearly a separate branch.
            if (
                np.linalg.norm(
                    next_point - current
                ) > 3.0
            ):
                break

            ordered.append(next_point)

            current = next_point

            remaining = np.delete(
                remaining,
                idx,
                axis=0
            )

        if len(ordered) >= 3:
            paths.append(
                np.array(
                    ordered,
                    dtype=float
                )
            )

    # ------------------------------------------------------------
    # 11. Convert paths back to DXF
    # ------------------------------------------------------------

    if not paths:
        raise RuntimeError(
            "Repair produced no usable geometry."
        )

    new_doc = ezdxf.new(setup=True)
    new_doc.units = ezdxf.units.MM

    new_msp = new_doc.modelspace()

    epsilon_px = max(
        0.1,
        simplify_mm * ppm
    )

    exported = 0

    for path in paths:

        # Remove duplicated consecutive points.
        filtered = [path[0]]

        for p in path[1:]:

            if np.linalg.norm(
                p - filtered[-1]
            ) >= 0.5:
                filtered.append(p)

        if len(filtered) < 3:
            continue

        # --------------------------------------------------------
        # Smooth/simplify skeleton path.
        # --------------------------------------------------------

        pts = np.array(
            filtered,
            dtype=np.float32
        )

        approx = cv2.approxPolyDP(
            pts.reshape(-1, 1, 2),
            epsilon=epsilon_px,
            closed=False
        )

        if len(approx) < 2:
            continue

        dxf_points = []

        for p in approx:

            px, py = p[0]

            x = (
                px / ppm
                + min_x
            )

            y = (
                max_y
                - py / ppm
            )

            dxf_points.append(
                (
                    float(x),
                    float(y)
                )
            )

        if len(dxf_points) >= 2:

            new_msp.add_lwpolyline(
                dxf_points,
                close=False,
                dxfattribs={
                    "color": 7
                }
            )

            exported += 1

    if exported == 0:
        raise RuntimeError(
            "Repair completed but no DXF paths were exported."
        )

    new_doc.saveas(output_dxf)

    print(
        f"DXF raster repair: "
        f"{exported} paths exported"
    )


def create_continuous_dxf(image_path, out_path, canvas_cm=150, simplify=0.5):
    """
    פונקציה חסרת פשרות ליצירת DXF רציף וסגור לחלוטין.
    מתעלמת מרעשים קטנים, סוגרת את הצורה בצורה אגרסיבית לפני זיהוי,
    ומייצאת רק פוליגונים הרמטיים.
    """
    canvas_mm = canvas_cm * 10.0

    # 1. קריאת התמונה
    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise RuntimeError(f"Could not load image: {image_path}")

    # 2. המרה לשחור-לבן (לבן = קו, שחור = רקע)
    if np.mean(img) > 127:
        img = cv2.bitwise_not(img)
    _, bw = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY)

    # 3. איחוי אגרסיבי של נתקים (Closing) + עיבוי (Dilation)
    # מבטיח רציפות מוחלטת של הקו בתמונה עצמה לפני המעבר לווקטור
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    kernel_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, kernel_close, iterations=2)
    bw = cv2.dilate(bw, kernel_dilate, iterations=1)

    # 4. מציאת קווי מתאר - RETR_TREE שומר גם על החלק הפנימי וגם החיצוני של העובי
    contours, hierarchy = cv2.findContours(bw, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    # סינון רעשים קטנים מאוד כדי למנוע קווים מרחפים ב-DXF
    valid_contours = [c for c in contours if cv2.contourArea(c) > 500]

    if not valid_contours:
        raise RuntimeError(f"No valid contours found in {image_path}")

    # 5. חישוב גבולות לקנה מידה
    all_pts = np.vstack([c.reshape(-1, 2) for c in valid_contours])
    min_x, min_y = all_pts.min(axis=0)
    max_x, max_y = all_pts.max(axis=0)

    width = max_x - min_x + 1
    height = max_y - min_y + 1
    scale = canvas_mm / max(width, height)

    offset_x = (canvas_mm - width * scale) / 2.0
    offset_y = (canvas_mm - height * scale) / 2.0

    def px_to_mm(p):
        return ((float(p[0]) - min_x) * scale + offset_x,
                (max_y - float(p[1])) * scale + offset_y)

    # 6. יצירת קובץ ה-DXF
    doc = ezdxf.new(setup=True)
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()

    for contour in valid_contours:
        approx = cv2.approxPolyDP(contour, epsilon=simplify, closed=True)

        if len(approx) < 3:
            continue

        points = [px_to_mm(p[0]) for p in approx]

        # 7. וידוא סגירה גיאומטרית מוחלטת
        if points[0] != points[-1]:
            points.append(points[0])

        # יצירת קו רציף סגור
        msp.add_lwpolyline(points, close=True, dxfattribs={"color": 7})

    doc.saveas(out_path)


def vectorize_with_padding_to_dxf(image_path, out_path, canvas_cm=150):
    """
    ממיר תמונה ל-DXF תוך הבטחה שהצורה מוקפת בשוליים ולכן תיסגר תמיד.
    בלי אלגוריתמים מסובכים של תיקון, רק מסגרת, זיהוי, והחלקה טבעית.
    """
    canvas_mm = canvas_cm * 10.0

    # 1. קריאת התמונה
    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise RuntimeError(f"Could not load image: {image_path}")

    # --- התיקון הקריטי: הוספת שוליים ---
    # מוסיף 50 פיקסלים של רקע לבן מכל צד.
    # זה מבטיח שאם הציור נחתך בקצה, עכשיו יהיה לו גבול ברור לסגור סביבו את הקו.
    padded_img = cv2.copyMakeBorder(
        img, 50, 50, 50, 50,
        cv2.BORDER_CONSTANT, value=255
    )

    # 2. המרה לשחור-לבן
    if np.mean(padded_img) > 127:
        padded_img = cv2.bitwise_not(padded_img)
    _, bw = cv2.threshold(padded_img, 127, 255, cv2.THRESH_BINARY)

    # 3. מציאת קווי המתאר
    # שימוש ב-TC89_KCOS עוזר ביצירת קווים עגולים וטבעיים יותר
    contours, _ = cv2.findContours(bw, cv2.RETR_TREE, cv2.CHAIN_APPROX_TC89_KCOS)

    # סינון רעשים קטנים
    valid_contours = [c for c in contours if cv2.contourArea(c) > 200]

    if not valid_contours:
        raise RuntimeError(f"No valid contours found in {image_path}")

    # 4. חישוב גבולות וקנה מידה למילימטרים
    all_pts = np.vstack([c.reshape(-1, 2) for c in valid_contours])
    min_x, min_y = all_pts.min(axis=0)
    max_x, max_y = all_pts.max(axis=0)

    width = max_x - min_x + 1
    height = max_y - min_y + 1
    scale = canvas_mm / max(width, height)

    offset_x = (canvas_mm - width * scale) / 2.0
    offset_y = (canvas_mm - height * scale) / 2.0

    def px_to_mm(p):
        return ((float(p[0]) - min_x) * scale + offset_x,
                (max_y - float(p[1])) * scale + offset_y)

    # 5. יצירת ה-DXF ושמירה
    doc = ezdxf.new(setup=True)
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()

    for contour in valid_contours:
        # epsilon=1.5 מעדן את הקו ומעלים את ה"מדרגות" בלי לעוות את הצורה
        approx = cv2.approxPolyDP(contour, epsilon=1.5, closed=True)

        if len(approx) < 3:
            continue

        points = [px_to_mm(p[0]) for p in approx]

        # כפיית סגירה גיאומטרית מוחלטת של הפוליגון
        if points[0] != points[-1]:
            points.append(points[0])

        msp.add_lwpolyline(points, close=True, dxfattribs={"color": 7})

    doc.saveas(out_path)