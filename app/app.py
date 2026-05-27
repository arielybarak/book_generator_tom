"""
Gradio web application — primary entry point for TOM.

Deployed on Hugging Face Spaces (GPU). Provides a multi-step browser UI:
  1. Enter book title
  2. Add pages: Hebrew text + optional nikud disambiguation + image description
  3. Generate → downloads a ZIP containing per-page DXFs, PNGs, and STL files

Full pipeline per page:
  Hebrew text → Stable Diffusion image → 3 DXFs (image, text, braille) → STL

Key functions:
- get_pipeline(): lazy singleton that loads the SD model once
- generate_page_assets(page_data, output_dir): runs the full pipeline for one page
- process_book(book_state): loops over all pages, zips outputs, returns ZIP path
"""
import gradio as gr
import os
import torch
import numpy as np
import shutil
import uuid
import zipfile
from pathlib import Path
from diffusers import AutoPipelineForText2Image

from src.language_funcs import (
    DISPLAY_MAPPING,
    hebrew_translator, convert_to_braille,
    apply_variations, check_ambiguities,
)
from src.image_funcs import (
    ensure_font, process_image_to_dxf,
    generate_braille_dxf_from_text, generate_hebrew_text_dxf,
)
from src.dxf_3d import create_one_page_stl_from_dxf
from src.config import cfg

ensure_font()

# ── Stable Diffusion pipeline (lazy-loaded) ────────────────────────────────────

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


# ── Per-page generation ────────────────────────────────────────────────────────

def generate_page_assets(page_data, output_dir):
    """Generate image PNG, image DXF and Braille DXF for one page."""
    page_num  = page_data['page_number']
    raw_text  = page_data['raw_text']
    desc      = page_data['image_description']
    obj_class = page_data['object_class']
    variations = page_data['variations']

    processed_hebrew = apply_variations(raw_text, variations)
    braille_text     = convert_to_braille(processed_hebrew)

    base_name        = f"page_{page_num}"
    dxf_img_path     = os.path.join(output_dir, f"{base_name}_image.dxf")
    dxf_braille_path = os.path.join(output_dir, f"{base_name}_braille.dxf")
    dxf_text_path    = os.path.join(output_dir, f"{base_name}_text.dxf")
    stl_path         = os.path.join(output_dir, f"{base_name}.stl")
    img_path         = os.path.join(output_dir, f"{base_name}.png")

    pipe = get_pipeline()
    if pipe:
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

        try:
            sd_cfg = cfg["stable_diffusion"]
            image = pipe(
                prompt=final_prompt,
                negative_prompt=negative_prompt,
                num_inference_steps=sd_cfg["inference_steps"],
                guidance_scale=sd_cfg["guidance_scale"],
            ).images[0]
            image.save(img_path)
            process_image_to_dxf(np.array(image), dxf_img_path)
        except Exception as e:
            print(f"Image generation failed for page {page_num}: {e}")
    else:
        print("Pipeline unavailable — skipping image generation.")

    generate_braille_dxf_from_text(braille_text, dxf_braille_path)
    generate_hebrew_text_dxf(processed_hebrew, dxf_text_path)

    # Build the final 3D-printable STL from the three DXFs
    try:
        create_one_page_stl_from_dxf(
            txt_dxf=Path(dxf_text_path),
            braille_dxf=Path(dxf_braille_path),
            image_dxf=Path(dxf_img_path),
            output=Path(stl_path),
        )
    except Exception as e:
        print(f"STL generation failed for page {page_num}: {e}")

    return [dxf_img_path, dxf_braille_path, dxf_text_path, stl_path, img_path]


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

    gr.Markdown("# 📚 Interactive Hebrew Braille & Illustration Generator")
    gr.Markdown("Generates DXF files and images for tactile books.")

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


if __name__ == "__main__":
    demo.launch()
