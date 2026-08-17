import os
from pathlib import Path
from typing import Optional, Union, Tuple
import cv2
import matplotlib.pyplot as plt
import numpy as np

import src.image_funcs as imf
import src.language_funcs as lf


def add_safety_padding(image: np.ndarray, pad_ratio: float = 0.08) -> np.ndarray:
    """מוסיפה שולי ביטחון לבנים מסביב לתמונה כדי למנוע נגיעה בקצוות וקטימת מסלולים."""
    if image is None or image.size == 0:
        return image

    h, w = image.shape[:2]
    pad_y = int(h * pad_ratio)
    pad_x = int(w * pad_ratio)
    border_val = [255, 255, 255] if len(image.shape) == 3 else 255

    return cv2.copyMakeBorder(
        image,
        top=pad_y,
        bottom=pad_y,
        left=pad_x,
        right=pad_x,
        borderType=cv2.BORDER_CONSTANT,
        value=border_val,
    )


def process_and_center_image(
    image_input: Union[np.ndarray, str, Path], margin_ratio: float = 0.05
) -> np.ndarray:
    """ממרכזת, מרופדת ומכווננת את התמונה כך שאינה נוגעת בקצוות הקנבס."""
    if isinstance(image_input, (str, Path)):
        image = cv2.imread(str(image_input))
        if image is None:
            raise RuntimeError(f"Could not load image from path: {image_input}")
    else:
        image = image_input

    if image is None or image.size == 0:
        return image

    # 1. הוספת רפוד היקפי ראשוני למניעת נגיעה בקצוות
    padded_img = add_safety_padding(image, pad_ratio=0.08)

    # 2. זיהוי גבולות התוכן הממשי
    if len(padded_img.shape) == 3:
        gray = cv2.cvtColor(padded_img, cv2.COLOR_BGR2GRAY)
    else:
        gray = padded_img.copy()

    mask = (gray < 240).astype(np.uint8)
    coords = cv2.findNonZero(mask)

    if coords is None:
        return padded_img

    x, y, w, h = cv2.boundingRect(coords)
    cropped = padded_img[y : y + h, x : x + w]

    # 3. חישוב סקאלה עם שוליים
    orig_h, orig_w = padded_img.shape[:2]
    pad_x = int(orig_w * margin_ratio)
    pad_y = int(orig_h * margin_ratio)

    avail_w = max(1, orig_w - (2 * pad_x))
    avail_h = max(1, orig_h - (2 * pad_y))

    scale = min(avail_w / w, avail_h / h)
    new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))

    interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
    resized = cv2.resize(cropped, (new_w, new_h), interpolation=interp)

    # 4. יצירת קנבס חדש ומיקום במרכז
    if len(padded_img.shape) == 3:
        canvas = np.full(
            (orig_h, orig_w, padded_img.shape[2]), 255, dtype=np.uint8
        )
    else:
        canvas = np.full((orig_h, orig_w), 255, dtype=np.uint8)

    start_x = (orig_w - new_w) // 2
    start_y = (orig_h - new_h) // 2
    canvas[start_y : start_y + new_h, start_x : start_x + new_w] = resized

    return canvas


def center_and_scale_image(
    image: np.ndarray, margin_ratio: float = 0.05
) -> np.ndarray:
    return process_and_center_image(image, margin_ratio=margin_ratio)


def create_images(
    hebrew_prompt: str,
    picture_type: str,
    image_path: Union[str, Path],
    text_path: Union[str, Path],
    braille_path: Union[str, Path],
) -> None:
    """ייצור ושמירת קבצי התמונות (PNG) עבור הציור, הטקסט בעברית והברייל."""
    imf.ensure_font()

    # 1. יצירת תמונת הציור הראשונית (סקיצה שחור-לבן)
    canvas = np.full((512, 512), 255, dtype=np.uint8)
    cv2.circle(canvas, (256, 256), 180, 0, 8)  # דוגמת עיגול/תוכן ברירת מחדל

    processed_img = process_and_center_image(canvas, margin_ratio=0.05)
    os.makedirs(os.path.dirname(image_path), exist_ok=True)
    cv2.imwrite(str(image_path), processed_img)

    # 2. שמירת תמונת הטקסט בעברית
    try:
        hebrew_text = lf.add_nikud(hebrew_prompt)
    except Exception:
        hebrew_text = hebrew_prompt

    display_text = hebrew_text[::-1] if hebrew_text else ""
    plt.figure(figsize=(5, 2))
    plt.gca().set_facecolor("white")
    plt.text(
        0.5,
        0.5,
        display_text,
        fontsize=16,
        color="black",
        ha="center",
        va="center",
    )
    plt.axis("off")
    os.makedirs(os.path.dirname(text_path), exist_ok=True)
    plt.savefig(text_path, dpi=200, bbox_inches="tight", pad_inches=0.3)
    plt.close()

    # 3. שמירת תמונת הברייל
    try:
        braille_text = lf.convert_to_braille(hebrew_text)
    except Exception:
        braille_text = hebrew_text

    plt.figure(figsize=(5, 2))
    plt.gca().set_facecolor("white")
    plt.text(
        0.5,
        0.5,
        braille_text,
        fontsize=24,
        color="black",
        ha="center",
        va="center",
    )
    plt.axis("off")
    os.makedirs(os.path.dirname(braille_path), exist_ok=True)
    plt.savefig(braille_path, dpi=200, bbox_inches="tight", pad_inches=0.3)
    plt.close()


def images_to_dxf(
    image_path: Union[str, Path],
    text_path: Union[str, Path],
    braille_path: Union[str, Path],
) -> Tuple[str, str, str]:
    """המרת תמונות ה-PNG לקבצי DXF."""
    dxf_image = str(image_path).replace(".png", ".dxf")
    dxf_text = str(text_path).replace(".png", ".dxf")
    dxf_braille = str(braille_path).replace(".png", ".dxf")

    # קריאה לפונקציה מ-src.image_funcs
    imf.create_smooth_dxf_from_png(image_path, dxf_image)

    try:
        lf.generate_hebrew_text_dxf(text_path, dxf_text)
    except Exception:
        imf.create_smooth_dxf_from_png(text_path, dxf_text)

    try:
        lf.generate_braille_dxf_from_text(braille_path, dxf_braille)
    except Exception:
        imf.create_smooth_dxf_from_png(braille_path, dxf_braille)

    return dxf_image, dxf_text, dxf_braille