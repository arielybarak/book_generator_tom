import os
import cv2
import numpy as np
from typing import Optional, Union, Tuple


def add_safety_padding(image: np.ndarray, pad_ratio: float = 0.08) -> np.ndarray:
    """
    מוסיפה שולי ביטחון לבנים מסביב לתמונה כדי למנוע נגיעה בקצוות וקטימת מסלולים.
    """
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
    image: np.ndarray, margin_ratio: float = 0.05
) -> np.ndarray:
    """
    ממרכזת, מרופדת ומכווננת את התמונה כך שאינה נוגעת בקצוות הקנבס.
    """
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
    """
    פונקציית מעטפת לשמירה על תאימות מלאה מול קריאות בקבצים אחרים.
    """
    return process_and_center_image(image, margin_ratio=margin_ratio)


def create_images(
    image_input: np.ndarray, margin_ratio: float = 0.05
) -> np.ndarray:
    """
    מעבדת את התמונה ומחזירה קנבס מרוכז ומרופד.
    """
    return process_and_center_image(image_input, margin_ratio=margin_ratio)


def images_to_dxf(
    image_input: np.ndarray,
    output_dxf_path: str,
    margin_ratio: float = 0.05,
) -> str:
    """
    מעבדת את התמונה וממירה אותה ל-DXF תוך שמירה על רפוד בטיחות מלא.
    """
    processed_img = process_and_center_image(
        image_input, margin_ratio=margin_ratio
    )

    from src.dxf_utils import create_smooth_dxf_from_png

    os.makedirs(os.path.dirname(output_dxf_path), exist_ok=True)
    create_smooth_dxf_from_png(
        processed_img, output_dxf_path, margin_ratio=margin_ratio
    )

    return output_dxf_path