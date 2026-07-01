"""
Gradio web app — the DEPLOYED TOM entry point (set via app_file in README.md).

Carries the production web wiring: the hidden /generate_page API, the
ping_assets / slow_ping CPU health endpoints, gr.Error clean-fail when SD
produces no image, and gr.File serving (image-403 fix). The final STL is built
with the CadQuery solid engine (src/dxf_3d.py): each page's three layers
(line-art image, Hebrew text, Braille) are exported as three DXFs, then assembled
into one solid STL by create_one_page_stl_from_dxf().

(Filename keeps the historical "_lithophane" suffix; the heightmap engine in
src/lithophane.py is engine 2, no longer used by this app.)

Full pipeline per page:
  Hebrew text → Stable Diffusion image → 3 DXFs → CadQuery solid STL

Key functions:
- run_sd_inference(): @spaces.GPU-decorated Stable Diffusion call
- generate_page_assets(page_data, output_dir): runs the full pipeline for one page
- process_book(book_state): loops over all pages, zips outputs, returns ZIP path
"""
# ── ZeroGPU support ─────────────────────────────────────────────────────────────
# `spaces` MUST be imported before torch/diffusers — it errors if CUDA was already
# initialized. It exists only on HF Spaces; a no-op fallback keeps local runs working.
try:
    import spaces
    _ON_ZEROGPU = True
except ImportError:
    _ON_ZEROGPU = False

    class _NoSpaces:
        @staticmethod
        def GPU(*args, **kwargs):
            # Support both @spaces.GPU and @spaces.GPU(duration=...)
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
from pathlib import Path
from diffusers import AutoPipelineForText2Image

from src.language_funcs import (
    DISPLAY_MAPPING,
    hebrew_translator, convert_to_braille, text_to_braille,
    apply_variations, check_ambiguities,
)
from src.image_funcs import (
    ensure_font, image_to_dxf_exact,
    generate_text_dxf, generate_braille_dxf_from_text,
)
from src.dxf_3d import create_one_page_stl_from_dxf
from src.config import cfg

ensure_font()

# ── Stable Diffusion pipeline (lazy-loaded) ────────────────────────────────────

# On ZeroGPU the GPU is only attached inside @spaces.GPU calls, so
# torch.cuda.is_available() is False at import time — force CUDA there.
if _ON_ZEROGPU:
    device = torch.device("cuda")
else:
    device = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
_pipe = None

def predownload_weights():
    """
    Pre-fetch the SD weights to the on-disk HF cache at startup (CPU, no GPU).

    The first @spaces.GPU request otherwise has to DOWNLOAD ~9GB inside the 30s GPU
    window — ZeroGPU kills it, so the first user after every rebuild/sleep gets a
    cold-start error. Downloading here (outside the GPU window, no time limit) means
    the first request only loads disk→GPU (fast). Safe to skip on failure.
    """
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
                model_id, torch_dtype=dtype
            ).to(device)
        except Exception as e:
            print(f"Model load error: {e}")
    return _pipe


# duration = the GPU reservation; ZeroGPU reserves ~duration×1.5 and debits it
# from the caller's daily quota. An A10G 25-step SSD-1B run is ~20-30s, so 30
# (→~45s reserved) keeps real headroom while stretching the quota (~33 pages/day
# on PRO's ~25min). Don't drop much lower — a cold/slow run that exceeds it is killed.
@spaces.GPU(duration=30)
def run_sd_inference(prompt, negative_prompt, steps, guidance):
    """
    Run Stable Diffusion and return a PIL image.

    Decorated for HF ZeroGPU: the GPU is attached only for the duration of this
    call. The model is loaded lazily here (inside GPU context) so the weights
    land on the GPU. Everything else (translation, DXF, STL) stays on CPU.
    """
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

def make_simple_shape_image(*shape_names, size=512):
    """
    Create clean black-on-white geometric shapes as grayscale numpy images.
    Returns None if the text is not a known simple shape.
    """
    words = []
    for shape_name in shape_names:
        if not shape_name:
            continue
        name = str(shape_name).strip().lower()
        for ch in [".", ",", "!", "?", ":", ";", '"', "'", "״", "׳"]:
            name = name.replace(ch, "")
        words.append(name)

    square_words = {"ריבוע", "רבוע", "מרובע", "square"}
    circle_words = {"עיגול", "מעגל", "circle"}
    triangle_words = {"משולש", "triangle"}
    rectangle_words = {"מלבן", "rectangle"}

    matched = None
    for name in words:
        if name in square_words:
            matched = "square"
            break
        if name in circle_words:
            matched = "circle"
            break
        if name in triangle_words:
            matched = "triangle"
            break
        if name in rectangle_words:
            matched = "rectangle"
            break

    if matched is None:
        return None

    img = np.full((size, size), 255, dtype=np.uint8)

    thickness = 14
    margin = int(size * 0.22)

    if matched == "square":
        cv2.rectangle(
            img,
            (margin, margin),
            (size - margin, size - margin),
            color=0,
            thickness=thickness,
            lineType=cv2.LINE_AA,
        )

    elif matched == "circle":
        cv2.circle(
            img,
            (size // 2, size // 2),
            int(size * 0.28),
            color=0,
            thickness=thickness,
            lineType=cv2.LINE_AA,
        )

    elif matched == "triangle":
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
            lineType=cv2.LINE_AA,
        )

    elif matched == "rectangle":
        cv2.rectangle(
            img,
            (int(size * 0.2), int(size * 0.32)),
            (int(size * 0.8), int(size * 0.68)),
            color=0,
            thickness=thickness,
            lineType=cv2.LINE_AA,
        )

    return img

# ── Per-page generation ────────────────────────────────────────────────────────

def generate_page_assets(page_data, output_dir):
    """Generate the SD image PNG, three DXFs, and the CadQuery solid STL."""
    page_num  = page_data['page_number']
    raw_text  = page_data['raw_text']
    desc      = page_data['image_description']
    obj_class = page_data['object_class']
    variations = page_data['variations']
    language  = page_data.get('language', 'hebrew')

    # Hebrew: apply nikud, render RTL. English: use the text as-is, render LTR, no nikud.
    is_english   = language == 'english'
    display_text = raw_text if is_english else apply_variations(raw_text, variations)
    braille_text = text_to_braille(display_text, language)

    base_name        = f"page_{page_num}"
    img_path         = os.path.join(output_dir, f"{base_name}.png")
    dxf_img_path     = os.path.join(output_dir, f"{base_name}_image.dxf")
    dxf_braille_path = os.path.join(output_dir, f"{base_name}_braille.dxf")
    dxf_text_path    = os.path.join(output_dir, f"{base_name}_text.dxf")
    stl_path         = os.path.join(output_dir, f"{base_name}.stl")

    # Prompt building (translation is a CPU/network step — keep it off the GPU)
    eng_desc  = hebrew_translator(desc)
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

    # Stable Diffusion line-art (GPU). Fall back to a blank canvas if unavailable.
    # Image line-art.
    # Simple geometric shapes are generated directly, without Stable Diffusion.
    gray = np.full((512, 512), 255, dtype=np.uint8)

    simple_shape = make_simple_shape_image(raw_text, desc, obj_class)

    if simple_shape is not None:
        gray = simple_shape
        cv2.imwrite(img_path, gray)
        image_to_dxf_exact(gray, dxf_img_path, simplify_epsilon=3.5)

    else:
        # Stable Diffusion line-art (GPU). Fall back to a blank canvas if unavailable.
        try:
            sd_cfg = cfg["stable_diffusion"]
            image = run_sd_inference(
                final_prompt, negative_prompt,
                sd_cfg["inference_steps"], sd_cfg["guidance_scale"],
            )

            if image is not None:
                image.save(img_path)

                # Convert to grayscale, thicken lines, remove small details
                gray = np.array(image.convert("L"))

                # Use threshold instead of skeletonization for bolder, simpler shapes
                _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)

                # Dilate to thicken lines
                kernel_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
                binary = cv2.dilate(binary, kernel_dilate, iterations=2)

                # Erode slightly to clean up
                kernel_erode = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
                binary = cv2.erode(binary, kernel_erode, iterations=1)

                # Remove small noise (keep only major shapes)
                num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
                clean = np.zeros_like(binary)
                for i in range(1, num_labels):
                    if stats[i, cv2.CC_STAT_AREA] >= 200:
                        clean[labels == i] = 255

                gray = cv2.bitwise_not(clean)
                image_to_dxf_exact(gray, dxf_img_path, simplify_epsilon=3.5)

            else:
                print(f"Pipeline unavailable — skipping image for page {page_num}.")

        except Exception as e:
            print(f"Image generation failed for page {page_num}: {e}")

    generate_braille_dxf_from_text(braille_text, dxf_braille_path)
    generate_text_dxf(display_text, dxf_text_path, rtl=not is_english)

    # Build the final 3D-printable STL from the three DXFs (CadQuery, CPU)
    try:
        create_one_page_stl_from_dxf(
            txt_dxf=Path(dxf_text_path),
            braille_dxf=Path(dxf_braille_path),
            image_dxf=Path(dxf_img_path),
            output=Path(stl_path),
        )
    except Exception as e:
        print(f"STL generation failed for page {page_num}: {e}")

    return [img_path, dxf_img_path, dxf_braille_path, dxf_text_path, stl_path]


def process_book(book_state_data):
    """Generate all pages and return a ZIP file path."""
    pages = book_state_data.get('pages', [])
    title = book_state_data.get('title', 'braille_book')

    if not pages:
        return None

    session_id = str(uuid.uuid4())
    work_dir   = os.path.join("temp_gen", session_id)
    os.makedirs(work_dir, exist_ok=True)

    generated_files = []
    for page in pages:
        files = generate_page_assets(page, work_dir)
        generated_files.extend(files)

    os.makedirs("output_zips", exist_ok=True)
    zip_path = os.path.join("output_zips", f"{title}_{session_id[:6]}.zip")
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for f in generated_files:
            if os.path.exists(f):
                zipf.write(f, os.path.basename(f))

    shutil.rmtree(work_dir)
    return zip_path


# ── Gradio UI ──────────────────────────────────────────────────────────────────

with gr.Blocks(title="Hebrew Braille Book Generator") as demo:

    book_state = gr.State({"pages": [], "title": ""})

    gr.Markdown("# 📚 Hebrew Braille & Illustration Generator")
    gr.Markdown(
        "Builds the STL as a true solid (CadQuery) from three DXF layers — "
        "raised text, Braille domes, image ridges. Outputs a PNG, three DXFs, "
        "and an STL per page."
    )

    with gr.Group() as section_setup:
        gr.Markdown("### Step 1: Book Details / פרטי הספר")
        book_title_input = gr.Textbox(
            label="Book Name / שם הספר",
            placeholder="e.g., Ami_Vetami"
        )
        start_btn = gr.Button("Start Creating / התחל", variant="primary")

    with gr.Group(visible=False) as section_editor:
        gr.Markdown("### Step 2: Add Pages / הוספת עמודים")

        with gr.Row():
            with gr.Column(scale=2):
                page_text_input = gr.Textbox(
                    label="טקסט העמוד (Page Text)",
                    lines=3,
                    placeholder="הקלד כאן עברית..."
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
                                for amb in ambiguities[i:i+3]:
                                    idx      = amb["index"]
                                    char     = amb["char"]
                                    raw_opts = amb["options"]
                                    display_opts = [
                                        (DISPLAY_MAPPING.get(v, v), v) for v in raw_opts
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
                                        scale=1, min_width=150, interactive=True
                                    )
                                    dd.change(
                                        make_handler(idx),
                                        inputs=[dd, current_page_variations],
                                        outputs=[current_page_variations]
                                    )

                page_text_input.change(lambda: {}, outputs=[current_page_variations])

            with gr.Column(scale=2):
                image_desc_input = gr.Textbox(
                    label="תיאור הציור (Visual Description)",
                    placeholder="תאור מילולי של התמונה (בעברית או אנגלית)",
                    lines=2
                )
                object_class_input = gr.Textbox(
                    label="סיווג האובייקט (Object Class)",
                    placeholder="לדוגמה: כלב, בית, ילד",
                    lines=1
                )
                add_page_btn = gr.Button("➕ Add Page / הוסף עמוד")

        gr.Markdown("---")
        pages_list_display = gr.Markdown("No pages added yet. / עדיין לא נוספו עמודים")

        gr.Markdown("---")
        generate_btn     = gr.Button("🔨 Generate Book ZIP / צור והורד", variant="primary")
        output_file_wizard = gr.File(label="Download ZIP")

    # ── Event handlers ─────────────────────────────────────────────────────────

    def start_book(title):
        t = title.strip() or "braille_book"
        return {
            section_setup:  gr.update(visible=False),
            section_editor: gr.update(visible=True),
            book_state:     {"pages": [], "title": t},
        }

    start_btn.click(start_book,
                    inputs=[book_title_input],
                    outputs=[section_setup, section_editor, book_state])

    def add_page(text, img_desc, obj_class, variations, current_state):
        if not text:
            return current_state, f"**Pages:** {len(current_state['pages'])}", "", "", ""
        new_page = {
            "page_number":       len(current_state["pages"]) + 1,
            "raw_text":          text,
            "image_description": img_desc,
            "object_class":      obj_class,
            "variations":        variations,
        }
        current_state["pages"].append(new_page)
        preview = "\n".join(
            f"{p['page_number']}. {p['raw_text'][:20]}... ({p['object_class']})"
            for p in current_state['pages']
        )
        display_txt = f"**Total Pages:** {len(current_state['pages'])}\n\n{preview}"
        return current_state, display_txt, "", "", ""

    add_page_btn.click(
        add_page,
        inputs=[page_text_input, image_desc_input, object_class_input,
                current_page_variations, book_state],
        outputs=[book_state, pages_list_display,
                 page_text_input, image_desc_input, object_class_input]
    )

    generate_btn.click(process_book, inputs=[book_state], outputs=[output_file_wizard])

    # ── Hidden API for the external website (web/) — not shown in the Gradio UI ───
    # A stable endpoint the React frontend calls via @gradio/client. It reuses the
    # existing single-page pipeline and returns the illustration PNG + the STL as
    # served file URLs. Both are gr.File OUTPUTS: gr.File copies the returned file
    # into Gradio's own served temp dir (/tmp/gradio), so the /file= route always
    # serves them. (gr.Image serves the PNG in-place from temp_gen/, which gradio
    # 6.x's stricter route 403s on HF Spaces — the STL never hit this because it
    # was already gr.File. The frontend just reads the file URL, so .png is fine.)
    web_text  = gr.Textbox(visible=False)
    web_vars  = gr.JSON(visible=False)          # {char_index: variant_key}
    web_desc  = gr.Textbox(visible=False)
    web_class = gr.Textbox(visible=False)
    web_lang  = gr.Textbox(visible=False)       # "hebrew" | "english"
    web_out_img = gr.File(visible=False)
    web_out_stl = gr.File(visible=False)
    web_btn   = gr.Button(visible=False)

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
        # If SD failed, no PNG is written. Fail cleanly (gr.Error) instead of
        # letting gr.File crash on Path(missing).stat() -> raw 500 to the client.
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

    # ── CPU-only health check (no GPU) ────────────────────────────────────────────
    # Mirrors /generate_page's outputs (image + STL as gr.File) but returns tiny
    # dummy files instantly, with no Stable Diffusion / GPU. Lets us verify the web
    # plumbing end-to-end — @gradio/client connect, CORS, and gr.File serving —
    # without burning GPU time or waiting on ZeroGPU. Not used by the production UI flow.
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

    # CPU-only ~22s job: same shape as ping_assets but sleeps first, to reproduce a
    # *long* request through HF's edge proxy WITHOUT the GPU. Used to test whether a
    # given @gradio/client version survives the long idle queue/data SSE that the real
    # SD generation triggers (the JS client hangs on it while the Python client doesn't).
    web_slow_img = gr.File(visible=False)
    web_slow_btn = gr.Button(visible=False)

    def slow_ping():
        time.sleep(22)
        work_dir = os.path.join("temp_gen", str(uuid.uuid4()))
        os.makedirs(work_dir, exist_ok=True)
        png_path = os.path.join(work_dir, "slow.png")
        cv2.imwrite(png_path, np.full((64, 64, 3), 150, dtype=np.uint8))
        return png_path

    web_slow_btn.click(slow_ping, outputs=[web_slow_img], api_name="slow_ping")


# The standalone web frontend (Vercel) does NOT use @gradio/client — that client
# can't drive a ZeroGPU job from outside the huggingface.co iframe (the GPU token
# handshake never happens, so /generate_page hangs). Instead the frontend calls
# Gradio's built-in REST API directly with a plain fetch:
#   POST /gradio_api/call/generate_page  {"data": [...]}  -> {"event_id"}
#   GET  /gradio_api/call/generate_page/<event_id>        -> SSE 'complete' + data
# That path goes through the normal queue (same as the Python client), so ZeroGPU
# schedules it and the file URLs come back ready. Nothing extra is needed here.
if __name__ == "__main__":
    predownload_weights()   # warm the on-disk weight cache before serving (avoids cold-start GPU-timeout)
    demo.launch()
