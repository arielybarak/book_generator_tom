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

    eng_desc = lf.hebrew_translator(raw_text)
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

    # ── עיבוד התמונה לקו נקי ──────────────────────────────────────

    img_np = np.array(image)

    # Stable Diffusion מחזיר RGB
    gray = cv2.cvtColor(
        img_np,
        cv2.COLOR_RGB2GRAY
    )

    # טשטוש קטן בלבד
    blurred = cv2.GaussianBlur(
        gray,
        (5, 5),
        0
    )

    # שחור = קו
    _, binary = cv2.threshold(
        blurred,
        150,
        255,
        cv2.THRESH_BINARY_INV
    )

    # ניקוי רעשים קטנים
    noise_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (3, 3)
    )

    binary = cv2.morphologyEx(
        binary,
        cv2.MORPH_OPEN,
        noise_kernel,
        iterations=1
    )

    # סגירת רווחים קטנים בלבד
    bridge_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (7, 7)
    )

    binary = cv2.morphologyEx(
        binary,
        cv2.MORPH_CLOSE,
        bridge_kernel,
        iterations=1
    )

    # ניקוי רכיבים קטנים
    num_labels, labels, stats, _ = (
        cv2.connectedComponentsWithStats(
            binary,
            connectivity=8
        )
    )

    clean = np.zeros_like(binary)

    for i in range(1, num_labels):
        area = stats[
            i,
            cv2.CC_STAT_AREA
        ]

        if area >= 40:
            clean[labels == i] = 255

    # לבן = רקע, שחור = ציור
    centered_input = cv2.bitwise_not(clean)

    h, w = centered_input.shape

    # ------------------------------------------------------------
    # Centering
    # ------------------------------------------------------------

    ys, xs = np.where(
        centered_input[1:h-1, 1:w-1] == 0
    )

    if len(xs) > 0:
        shift_x = int(w / 2 - xs.mean())
        shift_y = int(h / 2 - ys.mean())
    else:
        shift_x = 0
        shift_y = 0

    centered = cv2.warpAffine(
        centered_input,
        np.float32([
            [1, 0, shift_x],
            [0, 1, shift_y]
        ]),
        (w, h),
        borderValue=255
    )

    cv2.imwrite(
        str(image_output_location),
        centered
    )


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
    plt.savefig(text_output_location, dpi=250, bbox_inches="tight", pad_inches=0)
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
    dxf_image = str(image_location).replace('.png', '.dxf')
    dxf_text = str(text_location).replace('.png', '.dxf')
    dxf_braille = str(braille_location).replace('.png', '.dxf')

    # 1. הקטנת התמונה באמצע:
    # משנים את canvas_cm מ-150 לערך קטן יותר, למשל 100 או 120.
    imf.vectorize_with_padding_to_dxf(
        image_location,
        dxf_image,
        canvas_cm=100  # <--- שחקי עם המספר הזה כדי לשנות את גודל הציור
    )

    # 2. הקטנת הטקסט בעברית למעלה:
    # אנחנו מוסיפים את הפרמטר canvas_cm שעד עכשיו היה על ברירת מחדל של 150.
    # ערך כמו 70 או 80 יקטין אותו משמעותית.
    imf.png_to_dxf(
        text_location,
        dxf_text,
        canvas_cm=20   # <--- שחקי עם המספר הזה כדי לשנות את גודל הטקסט
    )

    # את הברייל נשאיר בינתיים על ברירת המחדל (150) או שתוכלי להקטין גם אותו באותה צורה
    imf.png_to_dxf(braille_location, dxf_braille)

    return dxf_image, dxf_text, dxf_braille