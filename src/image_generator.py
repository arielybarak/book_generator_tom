"""
Stable Diffusion image generation pipeline (used by FlowManager / CLI).

Responsibilities:
- _get_pipeline(): lazy singleton that loads the SD model once (segmind/SSD-1B)
- create_images(): full single-page pipeline — translates Hebrew, runs SD, applies
  edge detection + centering, saves image PNG, Hebrew text PNG, and Braille PNG.
- images_to_dxf(): converts the three PNGs produced by create_images() to DXF files.
"""

import torch
import cv2
import numpy as np
import matplotlib.pyplot as plt
from diffusers import AutoPipelineForText2Image

from src import language_funcs as lf
from src import image_funcs as imf
from src.config import cfg

# ── Lazy SD pipeline ───────────────────────────────────────────────────────────
_device = "cuda" if torch.cuda.is_available() else "cpu"
_pipe = None

def _get_pipeline():
    global _pipe
    if _pipe is None:
        sd_cfg = cfg["stable_diffusion"]
        model_id = sd_cfg.get("image_model_id", sd_cfg["model_id"])
        dtype = torch.float16 if _device == "cuda" else torch.float32
        print(f"Loading Stable Diffusion ({model_id}) on {_device}...")
        _pipe = AutoPipelineForText2Image.from_pretrained(
            model_id, torch_dtype=dtype
        ).to(_device)
    return _pipe


# ── Public API ─────────────────────────────────────────────────────────────────

PRINT_FRIENDLY_STYLE = (
    "icon, symbol, pictogram, single shape, basic geometric form, "
    "child's drawing, crayon sketch, stick figure style, "
    "ultra-minimal, flat solid shape, one color outline only, "
    "no details, no texture, bold thick line, plain white background"
)

PRINT_FRIENDLY_NEGATIVE = (
    "shading, gradients, texture, hatching, crosshatching, fill, solid color, "
    "photorealistic, complex background, decorative, small details, "
    "thin lines, clutter, noise, realistic lighting, busy composition, "
    "interior detail, internal lines, patterns, perspective, 3D effect, "
    "shadows, highlights, multiple objects, "
    "face, eyes, mouth, person, human features, anthropomorphic, character"
)

def build_print_friendly_prompt(image_desc: str, object_class: str | None = None) -> str:
    subject = f"{object_class}, " if object_class else ""
    return (
        f"{subject}{image_desc}, {PRINT_FRIENDLY_STYLE}, "
        "single subject, centered composition, children book outline style"
    )

def build_negative_prompt() -> str:
    return PRINT_FRIENDLY_NEGATIVE

def create_images(
    raw_text,
    variations,
    image_desc,
    object_class,
    image_output_location, text_output_location, braille_output_location
):
    """
    Full single-page pipeline (CLI / FlowManager use).
    Safely attempts nikud addition without crashing web / non-interactive contexts.
    """
    imf.ensure_font()

    eng_desc  = lf.hebrew_translator(raw_text)
    eng_class = lf.hebrew_translator(image_desc)

    sd_cfg = cfg["stable_diffusion"]
    prompt = build_print_friendly_prompt(eng_desc, eng_class or object_class)
    negative_prompt = build_negative_prompt()

    pipe = _get_pipeline()
    image = pipe(
        prompt=prompt,
        negative_prompt=negative_prompt,
        num_inference_steps=sd_cfg["inference_steps"],
        guidance_scale=sd_cfg["guidance_scale"],
    ).images[0]

    # ניסיון הוספת ניקוד עם מנגנון הגנה מקריסות
    try:
        hebrew_with_nikud = lf.add_nikud(raw_text)
    except (EOFError, Exception):
        hebrew_with_nikud = raw_text

    braille = lf.convert_to_braille(hebrew_with_nikud)

    # ── עיבוד התמונה: סף דק, סגירת רווחים וצינטור ─────────────────────────
    img_np = np.array(image)
    gray   = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)

    # 1. Threshold נמוך יותר ללכידת קווים דקים
    _, binary = cv2.threshold(gray, 130, 255, cv2.THRESH_BINARY_INV)

    # 2. חיבור רווחים בקווי המתאר
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel_close, iterations=2)

    # 3. הרחבה קלה לעובי הדפסה
    kernel_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    binary = cv2.dilate(binary, kernel_dilate, iterations=1)

    # 4. החלקת קצוות
    kernel_erode = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary = cv2.erode(binary, kernel_erode, iterations=1)

    # 5. ניקוי רעשים זעירים בלבד (שמירה על רכיבים מעל 30 פיקסלים)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    clean = np.zeros_like(binary)
    for i in range(1, num_labels):
        if stats[i, cv2.CC_STAT_AREA] >= 30:
            clean[labels == i] = 255

    # היפוך חזרה לקווים שחורים על רקע לבן
    edges = cv2.bitwise_not(clean)
    h, w  = edges.shape
    edges[h-1:h, w-1:w] = 255

    # צינטור התמונה
    ys, xs = np.where(edges[1:h-1, 1:w-1] == 0)
    if len(xs) > 0:
        shift_x = int(w / 2 - xs.mean())
        shift_y = int(h / 2 - ys.mean())
    else:
        shift_x = shift_y = 0
    centered = cv2.warpAffine(
        edges, np.float32([[1, 0, shift_x], [0, 1, shift_y]]), (w, h), borderValue=255
    )

    # שמירת תמונת ה-PNG
    cv2.imwrite(str(image_output_location), centered)

    # שמירת טקסט בעברית PNG
    plt.figure(figsize=(5, 5))
    plt.gca().set_facecolor("white")
    display_text = hebrew_with_nikud[::-1] if hebrew_with_nikud else ""
    base_size = 20
    # אם הטקסט ארוך מ-5 אותיות, הפונט יוקטן בהתאם
    dynamic_fontsize = max(14, base_size - max(0, len(display_text) - 5) * 2)

    plt.text(0.5, 0.1, display_text, fontsize=dynamic_fontsize, color='black',
             ha='center', va='center', fontweight='light', fontname='DejaVu Sans')
    plt.axis("off")
    plt.savefig(text_output_location, dpi=300, bbox_inches="tight", pad_inches=0)
    plt.close()

    # שמירת ברייל PNG
    plt.figure(figsize=(5, 5))
    plt.gca().set_facecolor("white")
    plt.text(0.5, 0.1, braille, fontsize=30, color='black',
             ha='center', va='center', fontweight='light', fontname='Noto Sans Symbols2')
    plt.axis("off")
    plt.savefig(braille_output_location, dpi=300, bbox_inches="tight", pad_inches=0)
    plt.close()


def images_to_dxf(image_location, text_location, braille_location):
    """Convert the three PNGs produced by create_images() to DXF files."""
    dxf_image   = str(image_location).replace('.png', '.dxf')
    dxf_text    = str(text_location).replace('.png', '.dxf')
    dxf_braille = str(braille_location).replace('.png', '.dxf')

    imf.image_to_dxf_exact(image_location, dxf_image)
    imf.png_to_dxf(text_location, dxf_text)
    imf.png_to_dxf(braille_location, dxf_braille)

    return dxf_image, dxf_text, dxf_braille