"""
Gradio web app — EXPERIMENTAL lithophane-style STL variant of TOM.

Same UI and Stable Diffusion stage as gradio_app.py, but the final STL is built
WITHOUT CadQuery: all three layers (line-art image, Hebrew text, Braille) are
flattened into one grayscale heightmap, which is meshed directly into an STL
(see src/lithophane.py — a Python port of the 3dp.rocks/lithophane idea).

This is a side-by-side experiment for comparison against gradio_app.py; it does
not replace it. Run manually: `python gradio_app_lithophane.py`.

Full pipeline per page:
  Hebrew text → Stable Diffusion image → combined heightmap PNG → STL

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
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from diffusers import AutoPipelineForText2Image

from src.language_funcs import (
    DISPLAY_MAPPING,
    hebrew_translator, convert_to_braille,
    apply_variations, check_ambiguities,
)
from src.image_funcs import ensure_font
from src.lithophane import compose_heightmap, heightmap_to_stl
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


@spaces.GPU(duration=300)
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


# ── Per-page generation ────────────────────────────────────────────────────────

def generate_page_assets(page_data, output_dir):
    """Generate the SD image PNG, a combined heightmap PNG, and a lithophane STL."""
    page_num  = page_data['page_number']
    raw_text  = page_data['raw_text']
    desc      = page_data['image_description']
    obj_class = page_data['object_class']
    variations = page_data['variations']

    processed_hebrew = apply_variations(raw_text, variations)
    braille_text     = convert_to_braille(processed_hebrew)

    base_name      = f"page_{page_num}"
    img_path       = os.path.join(output_dir, f"{base_name}.png")
    heightmap_path = os.path.join(output_dir, f"{base_name}_heightmap.png")
    stl_path       = os.path.join(output_dir, f"{base_name}.stl")

    # Prompt building (translation is a CPU/network step — keep it off the GPU)
    eng_desc  = hebrew_translator(desc)
    eng_class = hebrew_translator(obj_class)

    style_prompt = (
        "Simple child's drawing, 2D flat design, outlines only, "
        "single thin black pen, minimalistic, continuous single pen draw, "
        "broad strokes, white background."
    )
    negative_prompt = (
        "background, scenery, environment, extra items, shading, shadows, "
        "gradients, grayscale, fine lines, intricate details, realistic texture, "
        "dots, 3D, depth, perspective, messy lines, broken lines."
    )
    final_prompt = (
        f"A single isolated {eng_desc} centered on a white background, "
        f"classified as {eng_class}. {style_prompt}"
    )

    # Stable Diffusion line-art (GPU). Fall back to a blank canvas if unavailable.
    gray = np.full((512, 512), 255, dtype=np.uint8)
    try:
        sd_cfg = cfg["stable_diffusion"]
        image = run_sd_inference(
            final_prompt, negative_prompt,
            sd_cfg["inference_steps"], sd_cfg["guidance_scale"],
        )
        if image is not None:
            image.save(img_path)
            gray = np.array(image.convert("L"))
        else:
            print(f"Pipeline unavailable — blank image layer for page {page_num}.")
    except Exception as e:
        print(f"Image generation failed for page {page_num}: {e}")

    # Flatten the three layers into one heightmap, then mesh it directly (no CadQuery)
    try:
        heightmap = compose_heightmap(gray, processed_hebrew, braille_text, cfg)
        cv2.imwrite(heightmap_path, heightmap)
        heightmap_to_stl(heightmap, stl_path, cfg)
    except Exception as e:
        print(f"Lithophane STL generation failed for page {page_num}: {e}")

    return [img_path, heightmap_path, stl_path]


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

with gr.Blocks(title="Hebrew Braille Book Generator — Lithophane (experimental)") as demo:

    book_state = gr.State({"pages": [], "title": ""})

    gr.Markdown("# 📚 Hebrew Braille & Illustration Generator — 🧪 Lithophane variant")
    gr.Markdown(
        "Experimental: builds the STL from a combined **heightmap** (no CadQuery). "
        "Outputs a PNG, a heightmap PNG, and an STL per page."
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
    web_out_img = gr.File(visible=False)
    web_out_stl = gr.File(visible=False)
    web_btn   = gr.Button(visible=False)

    def generate_page_web(raw_text, variations, image_desc, object_class):
        page = {
            "page_number": 1,
            "raw_text": raw_text or "",
            "image_description": image_desc or "",
            "object_class": object_class or "",
            "variations": variations or {},
        }
        work_dir = os.path.join("temp_gen", str(uuid.uuid4()))
        os.makedirs(work_dir, exist_ok=True)
        img_path, _heightmap_path, stl_path = generate_page_assets(page, work_dir)
        return img_path, stl_path

    web_btn.click(
        generate_page_web,
        inputs=[web_text, web_vars, web_desc, web_class],
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


# ── Plain REST API for the standalone web frontend ────────────────────────────
# The browser @gradio/client CANNOT drive a ZeroGPU job: the GPU is scheduled only
# when the page asks huggingface.co for ZeroGPU auth headers via the parent-iframe
# postMessage handshake (see `is_zerogpu_iframe` in @gradio/client). A third-party
# site (our Vercel app) isn't in that iframe, so /generate_page submits but never
# gets a GPU and the JS client hangs forever (the Python client works — different
# path). Fix: expose the SAME pipeline as a plain REST endpoint. The browser hits
# it with a normal fetch — no Gradio queue, no SSE, no iframe handshake — and the
# Space runs the GPU work in-process (it natively owns its ZeroGPU context).
API_OUTPUT_ROOT = os.path.abspath("api_outputs")
os.makedirs(API_OUTPUT_ROOT, exist_ok=True)

fastapi_app = FastAPI()
# Public Space → no credentials needed; the frontend sends credentials:'omit' for
# *.hf.space, so a wildcard origin is safe and avoids the preflight-credentials trap.
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _public_base(request: Request) -> str:
    """Absolute origin for building file URLs the browser can fetch."""
    host = os.environ.get("SPACE_HOST")  # set by HF, e.g. <slug>.hf.space
    if host:
        return f"https://{host}"
    return str(request.base_url).rstrip("/")  # local/dev fallback


@fastapi_app.post("/api/generate")
async def api_generate(request: Request):
    body = await request.json()
    page = {
        "page_number": 1,
        "raw_text": body.get("raw_text") or "",
        "image_description": body.get("image_desc") or "",
        "object_class": body.get("object_class") or "",
        "variations": body.get("variations") or {},
    }
    uid = str(uuid.uuid4())
    work_dir = os.path.join(API_OUTPUT_ROOT, uid)
    os.makedirs(work_dir, exist_ok=True)

    # Heavy GPU+CPU work — run off the event loop (matches how Gradio runs handlers).
    img_path, _heightmap_path, stl_path = await run_in_threadpool(
        generate_page_assets, page, work_dir
    )

    # SD failure leaves NO png (blank-canvas fallback inside generate_page_assets) —
    # surface it instead of silently returning a blank page.
    if not (img_path and os.path.exists(img_path)):
        return JSONResponse(
            {"error": "image_generation_failed",
             "detail": "Stable Diffusion did not produce an image (GPU unavailable?)."},
            status_code=502,
        )
    if not (stl_path and os.path.exists(stl_path)):
        return JSONResponse(
            {"error": "stl_generation_failed", "detail": "STL meshing failed."},
            status_code=502,
        )

    base = _public_base(request)
    return {
        "image_url": f"{base}/api/file/{uid}/{os.path.basename(img_path)}",
        "stl_url":   f"{base}/api/file/{uid}/{os.path.basename(stl_path)}",
    }


@fastapi_app.get("/api/file/{uid}/{fname}")
def api_file(uid: str, fname: str):
    if "/" in uid or ".." in uid or "/" in fname or ".." in fname:
        return JSONResponse({"error": "bad_path"}, status_code=400)
    path = os.path.join(API_OUTPUT_ROOT, uid, fname)
    if not os.path.isfile(path):
        return JSONResponse({"error": "not_found"}, status_code=404)
    media = ("image/png" if fname.endswith(".png")
             else "model/stl" if fname.endswith(".stl")
             else "application/octet-stream")
    return FileResponse(path, media_type=media, filename=fname)


@fastapi_app.get("/api/health")
def api_health():
    return {"ok": True}


# Mount the Gradio UI under the same FastAPI app; serve both with uvicorn. HF runs
# this file as __main__, so uvicorn binds the Space port and ZeroGPU still works.
demo.queue()  # explicit: keep the Gradio queue configured under the mounted app
app = gr.mount_gradio_app(fastapi_app, demo, path="/")

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("GRADIO_SERVER_PORT") or os.environ.get("PORT") or 7860)
    uvicorn.run(app, host="0.0.0.0", port=port)
