"""
Stable Diffusion image generation pipeline (used by FlowManager / CLI).
Responsibilities:
- _get_pipeline(): lazy singleton that loads the SD model once (segmind/SSD-1B)
- create_images(): full single-page pipeline — translates Hebrew, runs SD, applies edge detection + centering, saves image PNG, Hebrew text PNG, and Braille PNG.
- images_to_dxf(): converts the three PNGs produced by create_images() to DXF files.
"""
import torch
import cv2
import numpy as np
import matplotlib.pyplot as plt
from diffusers import AutoPipelineForText2Image
from typing import Optional
import os
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
    image_output_location,
    text_output_location,
    braille_output_location
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
    img_np = np.array(image)  # Stable Diffusion מחזיר RGB
    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

    # טשטוש קטן בלבד
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # שחור = קו
    _, binary = cv2.threshold(blurred, 150, 255, cv2.THRESH_BINARY_INV)

    # ניקוי רעשים קטנים
    noise_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, noise_kernel, iterations=1)

    # סגירת רווחים קטנים ובינוניים כבר בשלב עיבוד ה-PNG
    bridge_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))  # שונה מ-7 ל-15
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, bridge_kernel, iterations=1)

    # ניקוי רכיבים זעירים בלבד (הורדה מ-40 ל-15 כדי לא למחוק אוזניים/זנב)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    clean = np.zeros_like(binary)
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if area >= 15:
            clean[labels == i] = 255

    # לבן = רקע, שחור = ציור
    centered_input = cv2.bitwise_not(clean)

    # הוספת שוליים לבנים מסביב לתמונה לפני מרכוז למניעת חיתוך בקצוות למעלה/למטה
    pad = 45
    centered_input = cv2.copyMakeBorder(
        centered_input, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255
    )
    h, w = centered_input.shape

    # ------------------------------------------------------------
    # Centering
    # ------------------------------------------------------------
    ys, xs = np.where(centered_input[1:h-1, 1:w-1] == 0)
    if len(xs) > 0:
        shift_x = int(w / 2 - xs.mean())
        shift_y = int(h / 2 - ys.mean())
    else:
        shift_x = 0
        shift_y = 0

    centered = cv2.warpAffine(
        centered_input,
        np.float32([[1, 0, shift_x], [0, 1, shift_y]]),
        (w, h),
        borderValue=255
    )
    cv2.imwrite(str(image_output_location), centered)

    # שמירת טקסט בעברית PNG
    plt.figure(figsize=(5, 5))
    plt.gca().set_facecolor("white")
    display_text = hebrew_with_nikud[::-1] if hebrew_with_nikud else ""
    base_size = 20
    # אם הטקסט ארוך מ-5 אותיות, הפונט יוקטן בהתאם
    dynamic_fontsize = max(14, base_size - max(0, len(display_text) - 5) * 2)
    plt.text(
        0.5, 0.1, display_text,
        fontsize=dynamic_fontsize, color='black',
        ha='center', va='center', fontweight='light', fontname='DejaVu Sans'
    )
    plt.axis("off")
    plt.savefig(text_output_location, dpi=250, bbox_inches="tight", pad_inches=0)
    plt.close()

    # שמירת ברייל PNG
    plt.figure(figsize=(5, 5))
    plt.gca().set_facecolor("white")
    plt.text(
        0.5, 0.1, braille,
        fontsize=30, color='black',
        ha='center', va='center', fontweight='light', fontname='Noto Sans Symbols2'
    )
    plt.axis("off")
    plt.savefig(braille_output_location, dpi=300, bbox_inches="tight", pad_inches=0)
    plt.close()

def center_and_scale_image(
    image: np.ndarray,
    margin_ratio: float = 0.05,
    border_value: int = 255
) -> np.ndarray:
    """
    ממרכזת ומכווננת את גודל האיור על גבי קנבס חדש תוך שמירה מלאה על יחס גובה-רוחב
    ומניעת חיתוך של קווי קצה.
    """
    if image is None or image.size == 0:
        return image

    # המרה לגווני אפור לצורך זיהוי מיקומי התוכן
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()

    # איתור פיקסלים של הציור (כל פיקסל שאינו רקע לבן)
    mask = gray < 240
    coords = cv2.findNonZero(mask.astype(np.uint8))

    if coords is None:
        return image

    # מציאת תיבת החסימה (Bounding Box) של התוכן הממשי
    x, y, w, h = cv2.boundingRect(coords)
    cropped_content = image[y:y+h, x:x+w]

    orig_h, orig_w = image.shape[:2]

    # חישוב שולי ביטחון (Padding)
    pad_x = int(orig_w * margin_ratio)
    pad_y = int(orig_h * margin_ratio)
    avail_w = max(1, orig_w - (2 * pad_x))
    avail_h = max(1, orig_h - (2 * pad_y))

    # חישוב יחס ההגדלה/הקטנה המקסימלי שנכנס בשטח הזמין
    scale = min(avail_w / w, avail_h / h)
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))

    # שינוי גודל התוכן תוך שמירה על יחס יבטים (Aspect Ratio)
    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
    resized_content = cv2.resize(cropped_content, (new_w, new_h), interpolation=interp)

    # יצירת קנבס נקי בגודל המקורי
    if len(image.shape) == 3:
        canvas = np.full((orig_h, orig_w, image.shape[2]), border_value, dtype=np.uint8)
    else:
        canvas = np.full((orig_h, orig_w), border_value, dtype=np.uint8)

    # מיקוד התוכן במרכז הקנבס
    start_x = (orig_w - new_w) // 2
    start_y = (orig_h - new_h) // 2

    canvas[start_y:start_y + new_h, start_x:start_x + new_w] = resized_content

    return canvas


def images_to_dxf(
    image_input: np.ndarray,
    output_dxf_path: str,
    margin_ratio: float = 0.05
) -> str:
    """
    ממירה תמונה מעובדת לקובץ DXF תוך שימוש בשוליים מצומצמים (0.05)
    כדי למנוע בזבוז שטח במרכז הלוח.
    """
    # 1. מרכוז ומניעת חיתוך קצוות
    centered_img = center_and_scale_image(image_input, margin_ratio=margin_ratio)

    # 2. ייצוא ל-DXF דרך הפונקציה הקיימת במיזם
    from src.dxf_utils import create_smooth_dxf_from_png

    create_smooth_dxf_from_png(
        centered_img,
        output_dxf_path,
        margin_ratio=margin_ratio
    )

    return output_dxf_path

# def images_to_dxf(image_location, text_location, braille_location):
#     dxf_image = str(image_location).replace('.png', '.dxf')
#     dxf_text = str(text_location).replace('.png', '.dxf')
#     dxf_braille = str(braille_location).replace('.png', '.dxf')
#
#     # המרה ל-DXF סגור עם שולי ביטחון (margin_ratio=0.15)
#     # כדי שלא ייגע בטקסט בעברית ובברייל ולא ייחתך בקצוות למעלה/למטה
#     imf.create_smooth_dxf_from_png(
#         image_location,
#         dxf_image,
#         canvas_cm=150,
#         thickness_boost=8,
#         smoothing=0.5,
#         margin_ratio=0.22
#     )
#
#     imf.png_to_dxf(text_location, dxf_text)
#     imf.png_to_dxf(braille_location, dxf_braille)
#
#     return dxf_image, dxf_text, dxf_braille