import math
from typing import Dict, Any, Tuple, Optional


def layout_content_on_base(
    base_width_mm: float, base_height_mm: float, config: dict
) -> dict:
    """
    מחשבת את החלוקה הפיזית של הלוח עם שטח מוגדל לרצועת התמונה המרכזית.
    """
    layout_cfg = config.get("layout", {})
    text_frac = layout_cfg.get("text_frac", 0.12)
    braille_frac = layout_cfg.get("braille_frac", 0.12)
    band_gap_mm = layout_cfg.get("band_gap_mm", 2.0)
    margin_mm = layout_cfg.get("margin_mm", 5.0)

    text_height_mm = base_height_mm * text_frac
    braille_height_mm = base_height_mm * braille_frac

    used_vertical_space = (
        (margin_mm * 2)
        + text_height_mm
        + braille_height_mm
        + (band_gap_mm * 2)
    )
    image_height_mm = max(10.0, base_height_mm - used_vertical_space)

    text_y = base_height_mm - margin_mm - text_height_mm
    image_y = text_y - band_gap_mm - image_height_mm
    braille_y = margin_mm

    return {
        "text_bbox": (
            margin_mm,
            text_y,
            base_width_mm - 2 * margin_mm,
            text_height_mm,
        ),
        "image_bbox": (
            margin_mm,
            image_y,
            base_width_mm - 2 * margin_mm,
            image_height_mm,
        ),
        "braille_bbox": (
            margin_mm,
            braille_y,
            base_width_mm - 2 * margin_mm,
            braille_height_mm,
        ),
    }


def fit_dxf_to_bounding_box(
    dxf_bounds: Tuple[float, float, float, float],
    target_bbox: Tuple[float, float, float, float],
    safety_factor: float = 0.85,
) -> Tuple[float, Tuple[float, float]]:
    """
    מחשבת סקאלה והזזה עבור DXF תוך כיווץ של 15% (safety_factor=0.85) למניעת קטימה.
    """
    min_x, min_y, max_x, max_y = dxf_bounds
    dxf_w = max_x - min_x
    dxf_h = max_y - min_y

    target_x, target_y, target_w, target_h = target_bbox

    if dxf_w <= 0 or dxf_h <= 0:
        return 1.0, (target_x, target_y)

    safe_target_w = target_w * safety_factor
    safe_target_h = target_h * safety_factor

    scale = min(safe_target_w / dxf_w, safe_target_h / dxf_h)

    scaled_w = dxf_w * scale
    scaled_h = dxf_h * scale

    shift_x = target_x + (target_w - scaled_w) / 2.0 - (min_x * scale)
    shift_y = target_y + (target_h - scaled_h) / 2.0 - (min_y * scale)

    return scale, (shift_x, shift_y)


def apply_dxf_layout(
    dxf_model: Any,
    target_bbox: Tuple[float, float, float, float],
    safety_factor: float = 0.85,
) -> Any:
    """
    מפעילה את חישוב המיקום והסקאלה על אובייקט ה-DXF ב-3D.
    """
    if hasattr(dxf_model, "get_bounds"):
        bounds = dxf_model.get_bounds()
    elif hasattr(dxf_model, "bounds"):
        min_b, max_b = dxf_model.bounds[:2]
        bounds = (min_b[0], min_b[1], max_b[0], max_b[1])
    else:
        bounds = (0, 0, 100, 100)

    scale, (shift_x, shift_y) = fit_dxf_to_bounding_box(
        bounds, target_bbox, safety_factor=safety_factor
    )

    if hasattr(dxf_model, "scale"):
        dxf_model.scale(scale)
    if hasattr(dxf_model, "translate"):
        dxf_model.translate(shift_x, shift_y)

    return dxf_model