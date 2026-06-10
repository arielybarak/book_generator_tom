"""
Stable Diffusion image generation pipeline (used by FlowManager / CLI).

Responsibilities:
- _get_pipeline(): lazy singleton that loads the SD model once (segmind/SSD-1B)
- create_images(): full single-page pipeline — translates Hebrew, runs SD, applies
  edge detection + centering, saves image PNG, Hebrew text PNG, and Braille PNG.
  Uses add_nikud() which calls input() — CLI-only, not suitable for web context.
- images_to_dxf(): converts the three PNGs produced by create_images() to DXF files.

Note: the web app (hf_space/gradio_app.py) has its own SD pipeline and does NOT use this module.
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
        model_id = cfg["stable_diffusion"]["model_id"]
        dtype = torch.float16 if _device == "cuda" else torch.float32
        print(f"Loading Stable Diffusion ({model_id}) on {_device}...")
        _pipe = AutoPipelineForText2Image.from_pretrained(
            model_id, torch_dtype=dtype
        ).to(_device)
    return _pipe


# ── Public API ─────────────────────────────────────────────────────────────────

def create_images(hebrew_prompt, picture_type,
                  image_output_location, text_output_location, braille_output_location):
    """
    Full single-page pipeline (CLI / FlowManager use).
    Calls add_nikud() which uses interactive input() — not suitable for web context.
    """
    imf.ensure_font()

    eng_desc  = lf.hebrew_translator(hebrew_prompt)
    eng_class = lf.hebrew_translator(picture_type)

    sd_cfg = cfg["stable_diffusion"]
    prompt = (
        f"A single isolated {eng_desc} centered on a white background, "
        f"classified as {eng_class}. "
        "Simple child's drawing, 2D flat design, outlines only, single thin black pen, "
        "minimalistic, continuous single pen draw, broad strokes, white background."
    )
    negative_prompt = (
        "background, scenery, extra items, shading, shadows, gradients, "
        "fine lines, intricate details, realistic texture, 3D, depth, broken lines."
    )

    pipe  = _get_pipeline()
    image = pipe(
        prompt=prompt,
        negative_prompt=negative_prompt,
        num_inference_steps=sd_cfg["inference_steps"],
        guidance_scale=sd_cfg["guidance_scale"],
    ).images[0]

    # Braille conversion (requires interactive nikud input)
    hebrew_with_nikud = lf.add_nikud(hebrew_prompt)
    braille = lf.convert_to_braille(hebrew_with_nikud)

    # Image processing: edge detection → centering
    img_np     = np.array(image)
    gray       = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
    edges      = cv2.Canny(gray, 50, 200)
    kernel     = np.ones((5, 5), np.uint8)
    edges      = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
    edges      = cv2.bitwise_not(edges)
    h, w       = edges.shape
    edges[h-1:h, w-1:w] = 255

    ys, xs = np.where(edges[1:h-1, 1:w-1] == 0)
    shift_x = int(w / 2 - xs.mean())
    shift_y = int(h / 2 - ys.mean())
    centered = cv2.warpAffine(
        edges, np.float32([[1, 0, shift_x], [0, 1, shift_y]]), (w, h), borderValue=255
    )

    # Save image PNG
    plt.figure(figsize=(5, 5))
    plt.imshow(centered, cmap="gray")
    plt.axis("off")
    plt.savefig(image_output_location, dpi=300, bbox_inches="tight", pad_inches=0)
    plt.close()

    # Save Hebrew text PNG
    plt.figure(figsize=(5, 5))
    plt.gca().set_facecolor("white")
    plt.text(0.5, 0.9, hebrew_with_nikud[::-1], fontsize=30, color='black',
             ha='center', va='center', fontweight='light', fontname='DejaVu Sans')
    plt.axis("off")
    plt.savefig(text_output_location, dpi=300, bbox_inches="tight", pad_inches=0)
    plt.close()

    # Save Braille PNG
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
