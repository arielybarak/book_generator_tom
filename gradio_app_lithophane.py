"""
Gradio web app — the DEPLOYED TOM entry point (set via app_file in README.md).

Full pipeline per page:
  Hebrew text → illustration image → 3 DXFs → CadQuery solid STL

Important:
- Basic geometric shapes are generated directly with OpenCV + DXF.
- Other objects still use Stable Diffusion.
"""

# ── ZeroGPU support ─────────────────────────────────────────────────────────────
try:
    import spaces
    _ON_ZEROGPU = True
except ImportError:
    _ON_ZEROGPU = False

    class _NoSpaces:
        @staticmethod
        def GPU(*args, **kwargs):
            if args and callable(args[0]):
                return args[0]
            return lambda fn: fn

    spaces = _NoSpaces()

import gradio as gr
import os
import time
import cv2
import torch
import numpy as np
import shutil
import uuid
import zipfile
import math
import unicodedata
import ezdxf
from pathlib import Path
from diffusers import AutoPipelineForText2Image

from src.language_funcs import (
    DISPLAY_MAPPING,
    hebrew_translator,
    text_to_braille,
    apply_variations,
    check_ambiguities,
)
from src.image_funcs import (
    ensure_font,
    image_to_dxf_exact,
    generate_text_dxf,
    generate_braille_dxf_from_text,
)
from src.dxf_3d import create_one_page_stl_from_dxf
from src.config import cfg

ensure_font()

# ── Stable Diffusion pipeline ──────────────────────────────────────────────────

if _ON_ZEROGPU:
    device = torch.device("cuda")
else:
    device = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")

_pipe = None


def predownload_weights():
    model_id = cfg["stable_diffusion"]["model_id"]
    try:
        from huggingface_hub import snapshot_download
        print(f"Pre-downloading {model_id} weights to disk cache...", flush=True)
        t0 = time.time()
        snapshot_download(model_id)
        print(f"Model weights cached in {time.time() - t0:.0f}s.", flush=True)
    except Exception as e:
        print(f"Model pre-download skipped ({e}); will load lazily on first request.", flush=True)


def get_pipeline():
    global _pipe
    if _pipe is None:
        model_id = cfg["stable_diffusion"]["model_id"]
        print(f"Loading Stable Diffusion ({model_id}) on {device}...")
        try:
            dtype = torch.float16 if device.type == "cuda" else torch.float32
            _pipe = AutoPipelineForText2Image.from_pretrained(
                model_id,
                torch_dtype=dtype,
            ).to(device)
        except Exception as e:
            print(f"Model load error: {e}", flush=True)
            return None

    return _pipe


@spaces.GPU(duration=30)
def run_sd_inference(prompt, negative_prompt, steps, guidance):
    pipe = get_pipeline()
    if pipe is None:
        return None

    with torch.inference_mode():
        return pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            num_inference_steps=steps,
            guidance_scale=guidance,
        ).images[0]


# ── Basic geometric shapes ─────────────────────────────────────────────────────

def normalize_shape_text(text):
    if not text:
        return ""

    text = str(text).strip().lower()

    # Remove Hebrew nikud / diacritics
    text = "".join(
        ch for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    )

    # Remove punctuation and invisible RTL/LTR marks
    for ch in [".", ",", "!", "?", ":", ";", '"', "'", "״", "׳", "\u200f", "\u200e"]:
        text = text.replace(ch, " ")

    return " ".join(text.split())


def detect_basic_shape(*texts):
    combined = " ".join(normalize_shape_text(t) for t in texts if t)

    if not combined:
        return None

    square_words = ["ריבוע", "רבוע", "מרובע", "square"]
    circle_words = ["עיגול", "עגול", "מעגל", "circle"]
    triangle_words = ["משולש", "triangle"]
    rectangle_words = ["מלבן", "rectangle"]

    if any(word in combined for word in square_words):
        return "square"

    if any(word in combined for word in circle_words):
        return "circle"

    if any(word in combined for word in triangle_words):
        return "triangle"

    if any(word in combined for word in rectangle_words):
        return "rectangle"

    return None


def create_basic_shape_png(shape_kind, img_path, size=512):
    """
    Creates a clean black-on-white preview PNG.
    Returns grayscale numpy image.
    """
    img = np.full((size, size), 255, dtype=np.uint8)

    thickness = 18
    margin = int(size * 0.23)

    if shape_kind == "square":
        cv2.rectangle(
            img,
            (margin, margin),
            (size - margin, size - margin),
            color=0,
            thickness=thickness,
            lineType=cv2.LINE_8,
        )

    elif shape_kind == "circle":
        cv2.circle(
            img,
            (size // 2, size // 2),
            int(size * 0.28),
            color=0,
            thickness=thickness,
            lineType=cv2.LINE_8,
        )

    elif shape_kind == "triangle":
        pts = np.array([
            [size // 2, margin],
            [size - margin, size - margin],
            [margin, size - margin],
        ], np.int32)

        cv2.polylines(
            img,
            [pts],
            isClosed=True,
            color=0,
            thickness=thickness,
            lineType=cv2.LINE_8,
        )

    elif shape_kind == "rectangle":
        cv2.rectangle(
            img,
            (int(size * 0.2), int(size * 0.32)),
            (int(size * 0.8), int(size * 0.68)),
            color=0,
            thickness=thickness,
            lineType=cv2.LINE_8,
        )

    else:
        raise ValueError(f"Unsupported basic shape: {shape_kind}")

    cv2.imwrite(img_path, img)
    return img


def add_polyline(msp, pts, closed=True):
    clean_pts = [(float(x), float(y)) for x, y in pts]
    if len(clean_pts) >= 2:
        msp.add_lwpolyline(clean_pts, close=closed, dxfattribs={"color": 7})


def create_basic_shape_dxf(shape_kind, dxf_path, canvas_cm=150):
    """
    Writes a clean DXF for basic shapes as OPEN continuous centerlines.

    Important:
    We intentionally do NOT use closed=True here.
    dxf_3d.py handles closed image paths edge-by-edge, which can create gaps
    or missing sides in the STL. Open continuous paths are stroked as one path.
    """
    canvas_mm = canvas_cm * 10.0

    doc = ezdxf.new(setup=True)
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()

    margin = canvas_mm * 0.23
    cx = canvas_mm / 2.0
    cy = canvas_mm / 2.0

    def add_open_path(points):
        # close=False on purpose.
        # We repeat the first point at the end so the visual shape is closed,
        # but the DXF entity is still an open path for the STL builder.
        msp.add_lwpolyline(
            [(float(x), float(y)) for x, y in points],
            close=False,
            dxfattribs={"color": 7},
        )

    if shape_kind == "square":
        pts = [
            (margin, margin),
            (canvas_mm - margin, margin),
            (canvas_mm - margin, canvas_mm - margin),
            (margin, canvas_mm - margin),
            (margin, margin),
        ]
        add_open_path(pts)

    elif shape_kind == "rectangle":
        x1 = canvas_mm * 0.2
        x2 = canvas_mm * 0.8
        y1 = canvas_mm * 0.32
        y2 = canvas_mm * 0.68

        pts = [
            (x1, y1),
            (x2, y1),
            (x2, y2),
            (x1, y2),
            (x1, y1),
        ]
        add_open_path(pts)

    elif shape_kind == "triangle":
        pts = [
            (cx, canvas_mm - margin),
            (canvas_mm - margin, margin),
            (margin, margin),
            (cx, canvas_mm - margin),
        ]
        add_open_path(pts)

    elif shape_kind == "circle":
        radius = canvas_mm * 0.28
        n = 160
        pts = []

        for i in range(n + 1):
            theta = 2.0 * math.pi * i / n
            x = cx + radius * math.cos(theta)
            y = cy + radius * math.sin(theta)
            pts.append((x, y))

        add_open_path(pts)

    else:
        raise ValueError(f"Unsupported basic shape: {shape_kind}")

    doc.saveas(dxf_path)

# ── Stable Diffusion image post-processing ─────────────────────────────────────

def sd_image_to_clean_line_art(image, img_path, dxf_img_path):
    image.save(img_path)

    gray = np.array(image.convert("L"))

    _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)

    kernel_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    binary = cv2.dilate(binary, kernel_dilate, iterations=2)

    kernel_erode = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary = cv2.erode(binary, kernel_erode, iterations=1)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    clean = np.zeros_like(binary)

    for i in range(1, num_labels):
        if stats[i, cv2.CC_STAT_AREA] >= 200:
            clean[labels == i] = 255

    gray = cv2.bitwise_not(clean)
    cv2.imwrite(img_path, gray)
    image_to_dxf_exact(gray, dxf_img_path, simplify_epsilon=3.5)

    return gray


# ── Per-page generation ────────────────────────────────────────────────────────

def generate_page_assets(page_data, output_dir):
    page_num = page_data["page_number"]
    raw_text = page_data["raw_text"]
    desc = page_data["image_description"]
    obj_class = page_data["object_class"]
    variations = page_data["variations"]
    language = page_data.get("language", "hebrew")

    is_english = language == "english"
    display_text = raw_text if is_english else apply_variations(raw_text, variations)
    braille_text = text_to_braille(display_text, language)

    base_name = f"page_{page_num}"
    img_path = os.path.join(output_dir, f"{base_name}.png")
    dxf_img_path = os.path.join(output_dir, f"{base_name}_image.dxf")
    dxf_braille_path = os.path.join(output_dir, f"{base_name}_braille.dxf")
    dxf_text_path = os.path.join(output_dir, f"{base_name}_text.dxf")
    stl_path = os.path.join(output_dir, f"{base_name}.stl")

    basic_shape = detect_basic_shape(raw_text, display_text, desc, obj_class)

    if basic_shape is not None:
        print(f"Basic shape detected for page {page_num}: {basic_shape}", flush=True)
        create_basic_shape_png(basic_shape, img_path)
        create_basic_shape_dxf(basic_shape, dxf_img_path)

    else:
        eng_desc = hebrew_translator(desc)
        eng_class = hebrew_translator(obj_class)

        style_prompt = (
            "icon, symbol, pictogram, single shape, basic geometric form, "
            "child's drawing, crayon sketch, stick figure style, "
            "ultra-minimal, flat solid shape, one color outline only, "
            "no details, no texture, bold thick line, plain white background"
        )

        negative_prompt = (
            "shading, gradients, texture, hatching, crosshatching, fill, solid color, "
            "photorealistic, complex background, decorative, small details, "
            "thin lines, clutter, noise, realistic lighting, busy composition, "
            "interior detail, internal lines, patterns, perspective, 3D effect, "
            "shadows, highlights, multiple objects"
        )

        final_prompt = (
            f"A single isolated {eng_desc} centered on a white background, "
            f"classified as {eng_class}. {style_prompt}"
        )

        try:
            sd_cfg = cfg["stable_diffusion"]
            image = run_sd_inference(
                final_prompt,
                negative_prompt,
                sd_cfg["inference_steps"],
                sd_cfg["guidance_scale"],
            )

            if image is not None:
                sd_image_to_clean_line_art(image, img_path, dxf_img_path)
            else:
                print(f"Pipeline unavailable — skipping image for page {page_num}.", flush=True)

        except Exception as e:
            print(f"Image generation failed for page {page_num}: {e}", flush=True)

    generate_braille_dxf_from_text(braille_text, dxf_braille_path)
    generate_text_dxf(display_text, dxf_text_path, rtl=not is_english)

    try:
        create_one_page_stl_from_dxf(
            txt_dxf=Path(dxf_text_path),
            braille_dxf=Path(dxf_braille_path),
            image_dxf=Path(dxf_img_path),
            output=Path(stl_path),
        )
    except Exception as e:
        print(f"STL generation failed for page {page_num}: {e}", flush=True)

    return [img_path, dxf_img_path, dxf_braille_path, dxf_text_path, stl_path]


def process_book(book_state_data):
    pages = book_state_data.get("pages", [])
    title = book_state_data.get("title", "braille_book")

    if not pages:
        return None

    session_id = str(uuid.uuid4())
    work_dir = os.path.join("temp_gen", session_id)
    os.makedirs(work_dir, exist_ok=True)

    generated_files = []

    for page in pages:
        files = generate_page_assets(page, work_dir)
        generated_files.extend(files)

    os.makedirs("output_zips", exist_ok=True)
    zip_path = os.path.join("output_zips", f"{title}_{session_id[:6]}.zip")

    with zipfile.ZipFile(zip_path, "w") as zipf:
        for f in generated_files:
            if os.path.exists(f):
                zipf.write(f, os.path.basename(f))

    shutil.rmtree(work_dir, ignore_errors=True)
    return zip_path


# ── Gradio UI ──────────────────────────────────────────────────────────────────

with gr.Blocks(title="Hebrew Braille Book Generator") as demo:
    book_state = gr.State({"pages": [], "title": ""})

    gr.Markdown("# 📚 Hebrew Braille & Illustration Generator")
    gr.Markdown(
        "Builds the STL as a true solid from three DXF layers — "
        "raised text, Braille domes, image ridges. Outputs a PNG, three DXFs, "
        "and an STL per page."
    )

    with gr.Group() as section_setup:
        gr.Markdown("### Step 1: Book Details / פרטי הספר")
        book_title_input = gr.Textbox(
            label="Book Name / שם הספר",
            placeholder="e.g., Ami_Vetami",
        )
        start_btn = gr.Button("Start Creating / התחל", variant="primary")

    with gr.Group(visible=False) as section_editor:
        gr.Markdown("### Step 2: Add Pages / הוספת עמודים")

        with gr.Row():
            with gr.Column(scale=2):
                page_text_input = gr.Textbox(
                    label="טקסט העמוד (Page Text)",
                    lines=3,
                    placeholder="הקלד כאן עברית...",
                )

                current_page_variations = gr.State({})

                @gr.render(inputs=page_text_input)
                def render_variations(text):
                    ambiguities = check_ambiguities(text)

                    if not ambiguities:
                        return

                    gr.Markdown("#### 🔍 Disambiguation / חידוד ניקוד")

                    with gr.Group():
                        for i in range(0, len(ambiguities), 3):
                            with gr.Row():
                                for amb in ambiguities[i:i + 3]:
                                    idx = amb["index"]
                                    char = amb["char"]
                                    raw_opts = amb["options"]
                                    display_opts = [
                                        (DISPLAY_MAPPING.get(v, v), v)
                                        for v in raw_opts
                                    ]

                                    def make_handler(index):
                                        def handler(val, current_vars):
                                            current_vars[str(index)] = val
                                            return current_vars
                                        return handler

                                    dd = gr.Dropdown(
                                        choices=display_opts,
                                        value="default" if "default" in raw_opts else raw_opts[0],
                                        label=f"תו '{char}' (מיקום {idx})",
                                        scale=1,
                                        min_width=150,
                                        interactive=True,
                                    )

                                    dd.change(
                                        make_handler(idx),
                                        inputs=[dd, current_page_variations],
                                        outputs=[current_page_variations],
                                    )

                page_text_input.change(lambda: {}, outputs=[current_page_variations])

            with gr.Column(scale=2):
                image_desc_input = gr.Textbox(
                    label="תיאור הציור (Visual Description)",
                    placeholder="תאור מילולי של התמונה (בעברית או אנגלית)",
                    lines=2,
                )

                object_class_input = gr.Textbox(
                    label="סיווג האובייקט (Object Class)",
                    placeholder="לדוגמה: כלב, בית, ילד",
                    lines=1,
                )

                add_page_btn = gr.Button("➕ Add Page / הוסף עמוד")

        gr.Markdown("---")
        pages_list_display = gr.Markdown("No pages added yet. / עדיין לא נוספו עמודים")

        gr.Markdown("---")
        generate_btn = gr.Button("🔨 Generate Book ZIP / צור והורד", variant="primary")
        output_file_wizard = gr.File(label="Download ZIP")

    def start_book(title):
        t = title.strip() or "braille_book"
        return {
            section_setup: gr.update(visible=False),
            section_editor: gr.update(visible=True),
            book_state: {"pages": [], "title": t},
        }

    start_btn.click(
        start_book,
        inputs=[book_title_input],
        outputs=[section_setup, section_editor, book_state],
    )

    def add_page(text, img_desc, obj_class, variations, current_state):
        if not text:
            return current_state, f"**Pages:** {len(current_state['pages'])}", "", "", ""

        new_page = {
            "page_number": len(current_state["pages"]) + 1,
            "raw_text": text,
            "image_description": img_desc,
            "object_class": obj_class,
            "variations": variations,
        }

        current_state["pages"].append(new_page)

        preview = "\n".join(
            f"{p['page_number']}. {p['raw_text'][:20]}... ({p['object_class']})"
            for p in current_state["pages"]
        )

        display_txt = f"**Total Pages:** {len(current_state['pages'])}\n\n{preview}"

        return current_state, display_txt, "", "", ""

    add_page_btn.click(
        add_page,
        inputs=[
            page_text_input,
            image_desc_input,
            object_class_input,
            current_page_variations,
            book_state,
        ],
        outputs=[
            book_state,
            pages_list_display,
            page_text_input,
            image_desc_input,
            object_class_input,
        ],
    )

    generate_btn.click(
        process_book,
        inputs=[book_state],
        outputs=[output_file_wizard],
    )

    # ── Hidden API for the external website ─────────────────────────────────────

    web_text = gr.Textbox(visible=False)
    web_vars = gr.JSON(visible=False)
    web_desc = gr.Textbox(visible=False)
    web_class = gr.Textbox(visible=False)
    web_lang = gr.Textbox(visible=False)
    web_out_img = gr.File(visible=False)
    web_out_stl = gr.File(visible=False)
    web_btn = gr.Button(visible=False)

    def generate_page_web(raw_text, variations, image_desc, object_class, language="hebrew"):
        page = {
            "page_number": 1,
            "raw_text": raw_text or "",
            "image_description": image_desc or "",
            "object_class": object_class or "",
            "variations": variations or {},
            "language": (language or "hebrew").lower(),
        }

        work_dir = os.path.join("temp_gen", str(uuid.uuid4()))
        os.makedirs(work_dir, exist_ok=True)

        files = generate_page_assets(page, work_dir)
        img_path, stl_path = files[0], files[-1]

        if not (img_path and os.path.exists(img_path)):
            raise gr.Error("יצירת הציור נכשלה. נסו שוב בעוד רגע.")

        if not (stl_path and os.path.exists(stl_path)):
            raise gr.Error("יצירת קובץ ההדפסה נכשלה. נסו שוב בעוד רגע.")

        return img_path, stl_path

    web_btn.click(
        generate_page_web,
        inputs=[web_text, web_vars, web_desc, web_class, web_lang],
        outputs=[web_out_img, web_out_stl],
        api_name="generate_page",
    )

    # ── CPU-only health checks ──────────────────────────────────────────────────

    web_ping_img = gr.File(visible=False)
    web_ping_stl = gr.File(visible=False)
    web_ping_btn = gr.Button(visible=False)

    def ping_assets():
        work_dir = os.path.join("temp_gen", str(uuid.uuid4()))
        os.makedirs(work_dir, exist_ok=True)

        png_path = os.path.join(work_dir, "ping.png")
        cv2.imwrite(png_path, np.full((64, 64, 3), 150, dtype=np.uint8))

        stl_path = os.path.join(work_dir, "ping.stl")
        with open(stl_path, "w") as f:
            f.write("solid ping\nendsolid ping\n")

        return png_path, stl_path

    web_ping_btn.click(
        ping_assets,
        outputs=[web_ping_img, web_ping_stl],
        api_name="ping_assets",
    )

    web_slow_img = gr.File(visible=False)
    web_slow_btn = gr.Button(visible=False)

    def slow_ping():
        time.sleep(22)

        work_dir = os.path.join("temp_gen", str(uuid.uuid4()))
        os.makedirs(work_dir, exist_ok=True)

        png_path = os.path.join(work_dir, "slow.png")
        cv2.imwrite(png_path, np.full((64, 64, 3), 150, dtype=np.uint8))

        return png_path

    web_slow_btn.click(
        slow_ping,
        outputs=[web_slow_img],
        api_name="slow_ping",
    )


if __name__ == "__main__":
    predownload_weights()
    demo.launch()