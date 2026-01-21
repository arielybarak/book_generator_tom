import gradio as gr
import os
import re
import cv2
import numpy as np
import ezdxf
import torch
import shutil
import json
import uuid
import zipfile
from PIL import Image
from deep_translator import GoogleTranslator
from diffusers import AutoPipelineForText2Image
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# ==========================================
# 1. Constants & Configuration
# ==========================================

# Unicode Constants for Niqqud/Marks
DAGESH = '\u05BC'
HIRIK = '\u05B4'
HOLAM = '\u05B9'
SHURUK = '\u05BB'
SHIN_DOT = '\u05C2'

# Braille Mappings (from TOM.ipynb)
HEBREW_MAP = {
    'א': '⠁', 'ב': '⠧', 'ג': '⠛', 'ד': '⠙', 'ה': '⠓',
    'ו': '⠺', 'ז': '⠵', 'ח': '⠭', 'ט': '⠞', 'י': '⠚',
    'כ': '⠡', 'ל': '⠇', 'מ': '⠍', 'נ': '⠝', 'ס': '⠎',
    'ע': '⠫', 'פ': '⠋', 'צ': '⠮', 'ק': '⠟', 'ר': '⠗',
    'ש': '⠩', 'ת': '⠹', 'ך': '⠡', 'ם': '⠍', 'ן': '⠝',
    'ף': '⠋', 'ץ': '⠮',
}

HEBREW_DAGESH_MAP = {
    'ב': '⠃', # B
    'כ': '⠅', # K
    'פ': '⠏', # P
}

# Values for user interactive selection
SPECIAL_REPLACEMENTS = {
    'ו': {'default': 'ו', 'holam': 'ו' + HOLAM, 'shuruk': 'ו' + SHURUK},
    'ש': {'shin': 'ש' + SHIN_DOT, 'sin': 'שׂ'}, # Sin usually has dot on left, mapped here for logic
    'ב': {'default': 'ב', 'dagesh': 'ב' + DAGESH},
    'כ': {'default': 'כ', 'dagesh': 'כ' + DAGESH},
    'פ': {'default': 'פ', 'dagesh': 'פ' + DAGESH},
    'ך': {'default': 'ך', 'dagesh': 'ך' + DAGESH},
    'ף': {'default': 'ף', 'dagesh': 'ף' + DAGESH},
}

# Display Mapping (Hebrew Only as requested)
DISPLAY_MAPPING = {
    'default': 'רגיל (ללא ניקוד)',
    'holam': 'חולם (וֹ)',
    'shuruk': 'שורוק (וּ)',
    'shin': 'שין ימנית (שׁ)',
    'sin': 'שין שמאלית (שׂ)',
    'dagesh': 'דגש (ּ)',
}

# Font setup for Braille (matches TOM.ipynb)
FONT_FILENAME = "NotoSansSymbols2-Regular.ttf"

def ensure_font():
    if not os.path.exists(FONT_FILENAME):
        try:
            print("Downloading font...")
            os.system(f"wget -O {FONT_FILENAME} https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSansSymbols2/NotoSansSymbols2-Regular.ttf")
            fm.fontManager.addfont(FONT_FILENAME)
            plt.rcParams['font.family'] = 'Noto Sans Symbols2'
        except Exception as e:
            print(f"Error downloading font: {e}")
    else:
        fm.fontManager.addfont(FONT_FILENAME)
        plt.rcParams['font.family'] = 'Noto Sans Symbols2'

ensure_font()

# ==========================================
# 2. Logic: Translation & Braille Conversion
# ==========================================

def hebrew_translator(user_prompt):
    """
    Translates Hebrew prompt to English using Google Translator.
    """
    if not user_prompt:
        return ""
    contains_hebrew = re.search(r"[\u0590-\u05FF]", user_prompt) is not None
    if contains_hebrew:
        try:
            return GoogleTranslator(source='auto', target='en').translate(user_prompt)
        except Exception as e:
            print(f"Translation error: {e}")
            return user_prompt
    return user_prompt

def letter_to_braille(base, marks):
    """
    Converts a single base letter + its marks to Braille char.
    """
    # Shin/Sin logic
    if base == 'ש':
        # If user selected SHIN_DOT (Right), check mark
        if SHIN_DOT in marks:
            return '⠱' # Specific Braille for Shin? (Map says '⠱' in logic)
        # Note: In standard Hebrew Braille, Shin is ⠩ (146), Sin is ⠳ (126) etc.
        # The notebook had: if SHIN_DOT in marks: return '⠱' else HEBREW_MAP['ש']
        # We stick to the provided notebook logic.
        return HEBREW_MAP['ש']

    # Dagesh logic
    if base in HEBREW_DAGESH_MAP and DAGESH in marks:
        return HEBREW_DAGESH_MAP[base]

    # Vuv Logic
    if base == 'ו':
        if HOLAM in marks: return '⠕'
        if SHURUK in marks: return '⠥'
        return HEBREW_MAP['ו']

    # Yud Logic
    if base == 'י':
        if HIRIK in marks: return '⠊'
        return HEBREW_MAP['י']

    return HEBREW_MAP.get(base, base)

def convert_to_braille(text):
    """
    Parses Hebrew text with Unicode marks and returns Braille string.
    """
    result = []
    i = 0
    while i < len(text):
        ch = text[i]
        if 'א' <= ch <= 'ת':
            base = ch
            marks = []
            i += 1
            # Collect subsequent nikud/marks
            while i < len(text) and '\u0591' <= text[i] <= '\u05C7':
                marks.append(text[i])
                i += 1
            result.append(letter_to_braille(base, marks))
        else:
            result.append(ch)
            i += 1
    # Braille is read left-to-right, but Hebrew is right-to-left. 
    # visual flip for rendering usually needed, notebook does `result[::-1]`
    return "".join(result[::-1])

def apply_variations(raw_text, variations):
    """
    Replaces characters in raw_text based on UI variations.
    This replaces the interactive `add_nikud` function.
    """
    if not variations:
        return raw_text
        
    result_chars = list(raw_text)
    for index_str, variant_name in variations.items():
        try:
            index = int(index_str)
            if 0 <= index < len(result_chars):
                char = result_chars[index]
                if char in SPECIAL_REPLACEMENTS and variant_name in SPECIAL_REPLACEMENTS[char]:
                    result_chars[index] = SPECIAL_REPLACEMENTS[char][variant_name]
        except (ValueError, IndexError):
            continue
    return "".join(result_chars)

# ==========================================
# 3. Logic: Image & DXF Generation
# ==========================================

# Initialize Model (Lazy load or global)
device = torch.device("cuda:0") if torch.cuda.is_available() else torch.device("cpu")
pipe = None

def get_pipeline():
    global pipe
    if pipe is None:
        print(f"Loading SD Pipeline on {device}...")
        try:
            model_id = "segmind/SSD-1B"
            dtype = torch.float16 if device.type == "cuda" else torch.float32
            pipe = AutoPipelineForText2Image.from_pretrained(model_id, torch_dtype=dtype)
            pipe.to(device)
        except Exception as e:
            print(f"Error loading model: {e}")
            return None
    return pipe

def process_image_to_dxf(img_array, output_path):
    """
    Converts an image array to DXF - Logic from 'img_to_dxf'
    """
    # Preprocessing
    gray_image = cv2.cvtColor(img_array, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray_image, (7, 7), 0)
    
    # Adaptive Threshold
    binary = cv2.adaptiveThreshold(
        blur, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        21, 3
    )

    # Morphology to close gaps
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    # Contours
    contours, _ = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)

    # EZDXF Setup
    doc = ezdxf.new()
    msp = doc.modelspace()
    height = img_array.shape[0]

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 80: continue # Remove noise

        # Simplification
        epsilon = 0.01 * cv2.arcLength(cnt, False)
        approx = cv2.approxPolyDP(cnt, epsilon, False)

        points = [(float(p[0][0]), float(height - p[0][1])) for p in approx]

        if len(points) > 2:
            msp.add_lwpolyline(points, close=False, dxfattribs={'color': 7})

    doc.saveas(output_path)

def generate_braille_dxf_from_text(braille_text, output_path):
    """
    Generates Braille DXF by first plotting text to image, then converting.
    Using 'braille_img_to_dxf' logic from notebook.
    """
    # 1. Plot Braille to Image
    plt.figure(figsize=(3.9, 3.9))
    # Using Font definition from setup
    plt.text(0.5, 0.5, braille_text, fontsize=30, color='black', 
             ha='center', va='center', fontweight='light', fontname='Noto Sans Symbols2')
    plt.axis("off")
    
    temp_img = f"temp_braille_{uuid.uuid4()}.png"
    plt.savefig(temp_img, dpi=300, bbox_inches="tight", pad_inches=0)
    plt.close()

    # 2. Convert Image to DXF (Blob detection logic)
    img = cv2.imread(temp_img, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return
        
    img_blur = cv2.GaussianBlur(img, (5, 5), 0)
    
    # Thresh
    binary = cv2.adaptiveThreshold(
        img_blur, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        15, 2
    )

    # Blob Detector
    params = cv2.SimpleBlobDetector_Params()
    params.filterByArea = True
    params.minArea = 30
    params.maxArea = 1500
    params.filterByCircularity = False
    params.filterByConvexity = False
    params.filterByInertia = False
    params.minThreshold = 0
    params.maxThreshold = 255
    params.thresholdStep = 5

    detector = cv2.SimpleBlobDetector_create(params)
    keypoints = detector.detect(binary)

    # DXF Creation
    doc = ezdxf.new()
    msp = doc.modelspace()
    height_px = img.shape[0]

    for kp in keypoints:
        x, y = kp.pt
        r = kp.size / 2
        # Flip Y for DXF coords
        msp.add_circle(center=(x, height_px - y), radius=r, dxfattribs={'color': 7})

    doc.saveas(output_path)
    
    # Cleanup
    if os.path.exists(temp_img):
        os.remove(temp_img)

def generate_page_assets(page_data, output_dir):
    """
    Orchestrates generation for a single page.
    """
    page_num = page_data['page_number']
    raw_text = page_data['raw_text']
    desc = page_data['image_description']
    obj_class = page_data['object_class']
    variations = page_data['variations']
    
    # 1. Prepare Text
    processed_hebrew = apply_variations(raw_text, variations)
    braille_text = convert_to_braille(processed_hebrew)
    
    # 2. Files Setup
    base_name = f"page_{page_num}"
    dxf_img_path = os.path.join(output_dir, f"{base_name}_image.dxf")
    dxf_braille_path = os.path.join(output_dir, f"{base_name}_braille.dxf")
    img_path = os.path.join(output_dir, f"{base_name}.png")

    # 3. Image Generation (Stable Diffusion)
    pipe = get_pipeline()
    if pipe:
        # Translate prompts
        eng_desc = hebrew_translator(desc)
        eng_class = hebrew_translator(obj_class)
        
        # Build prompt (from notebook)
        final_prompt = (
            f"A single vectorized clean line-art illustration of {eng_desc}, "
            f"classified as a {eng_class}. "
            "Minimalistic outline, high contrast white background, no shading, no texture, "
            "sharp edges, centered composition, no extra objects, no text, no noise."
        )
        
        try:
            image = pipe(final_prompt, num_inference_steps=25, guidance_scale=7.5).images[0]
            image.save(img_path)
            
            # Convert to numpy for OpenCV
            img_np = np.array(image)
            process_image_to_dxf(img_np, dxf_img_path)
            
        except Exception as e:
            print(f"Generation failed for page {page_num}: {e}")
    else:
        print("Pipeline unavailable, skipping image generation.")

    # 4. Braille DXF
    generate_braille_dxf_from_text(braille_text, dxf_braille_path)
    
    return [dxf_img_path, dxf_braille_path, img_path]


def process_book(book_state_data):
    """
    Main entry point for "Generate Book" button.
    """
    pages = book_state_data.get('pages', [])
    title = book_state_data.get('title', 'my_book')
    
    if not pages:
        return None
        
    # Create temp dir
    session_id = str(uuid.uuid4())
    work_dir = os.path.join("temp_gen", session_id)
    os.makedirs(work_dir, exist_ok=True)
    
    generated_files = []
    
    # Process each page
    for page in pages:
        files = generate_page_assets(page, work_dir)
        generated_files.extend(files)
        
    # Zip results
    zip_filename = f"{title}_{session_id[:6]}.zip"
    zip_path = os.path.join("output_zips", zip_filename) # Ensure directory exists
    os.makedirs("output_zips", exist_ok=True)
    
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for file in generated_files:
            if os.path.exists(file):
                zipf.write(file, os.path.basename(file))
                
    # Cleanup work dir
    shutil.rmtree(work_dir)
    
    return zip_path

# ==========================================
# 4. Helper for UI (Disambiguation)
# ==========================================

def check_ambiguities(text):
    """
    Scans text for characters with special replacements.
    """
    ambiguities = []
    if not text:
        return ambiguities
    for i, char in enumerate(text):
        if char in SPECIAL_REPLACEMENTS:
            options = list(SPECIAL_REPLACEMENTS[char].keys())
            ambiguities.append({
                "index": i,
                "char": char,
                "options": options
            })
    return ambiguities

# ==========================================
# 5. Gradio App Definition
# ==========================================

with gr.Blocks(title="Hebrew Braille Book Generator (DXF/Image)") as demo:
    
    # State to hold book data
    book_state = gr.State({"pages": [], "title": ""})
    
    gr.Markdown("# 📚 Interactive Hebrew Braille & Illustration Generator")
    gr.Markdown("Generates DXF files and Images for Tactile Books.")

    # --- Step 1: Book Setup ---
    with gr.Group() as section_setup:
        gr.Markdown("### Step 1: Book Details / פרטי הספר")
        book_title_input = gr.Textbox(label="Book Name (used for filename) / שם הספר", placeholder="e.g., Ami_Vetami")
        start_btn = gr.Button("Start Creating / התחל", variant="primary")

    # --- Step 2: Page Editor ---
    with gr.Group(visible=False) as section_editor:
        gr.Markdown("### Step 2: Add Pages / הוספת עמודים")
        
        with gr.Row():
            # Left Column: Text & Disambiguation
            with gr.Column(scale=2):
                page_text_input = gr.Textbox(
                    label="טקסט העמוד (Page Text)", 
                    lines=3,
                    placeholder="הקלד כאן עברית..."
                )
                
                # Dynamic Disambiguation
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
                                    idx = amb["index"]
                                    char = amb["char"]
                                    raw_opts = amb["options"]
                                    
                                    # Use Hebrew-only display mapping
                                    display_opts = []
                                    for val in raw_opts:
                                        label = DISPLAY_MAPPING.get(val, val)
                                        display_opts.append((label, val))

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
                                        interactive=True
                                    )
                                    dd.change(
                                        make_handler(idx),
                                        inputs=[dd, current_page_variations],
                                        outputs=[current_page_variations]
                                    )
                
                # Reset variations on text change
                page_text_input.change(lambda: {}, outputs=[current_page_variations])

            # Right Column: Image Metadata
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

        # Page List Display
        gr.Markdown("---")
        pages_list_display = gr.Markdown("No pages added yet. / עדיין לא נוספו עמודים")
        
        # Generation
        gr.Markdown("---")
        generate_btn = gr.Button("🔨 Generate Book ZIP / צור והורד", variant="primary")
        output_file_wizard = gr.File(label="Download ZIP")

    # --- Event Handlers ---

    def start_book(title):
        t = title.strip() or "braille_book"
        return {
            section_setup: gr.update(visible=False),
            section_editor: gr.update(visible=True),
            book_state: {"pages": [], "title": t}
        }

    start_btn.click(start_book, inputs=[book_title_input], outputs=[section_setup, section_editor, book_state])

    def add_page(text, img_desc, obj_class, variations, current_state):
        if not text:
            # Minimal check, user might want image only? Assuming text required for braille
            return current_state, f"**Pages:** {len(current_state['pages'])}", "", "", ""
        
        new_page = {
            "page_number": len(current_state["pages"]) + 1,
            "raw_text": text,
            "image_description": img_desc,
            "object_class": obj_class,
            "variations": variations
        }
        current_state["pages"].append(new_page)
        
        # Update Feed
        preview = "\n".join([f"{p['page_number']}. {p['raw_text'][:20]}... ({p['object_class']})" for p in current_state['pages']])
        display_txt = f"**Total Pages:** {len(current_state['pages'])}\n\n{preview}"
        
        return current_state, display_txt, "", "", ""

    add_page_btn.click(
        add_page,
        inputs=[page_text_input, image_desc_input, object_class_input, current_page_variations, book_state],
        outputs=[book_state, pages_list_display, page_text_input, image_desc_input, object_class_input]
    )

    generate_btn.click(
        process_book,
        inputs=[book_state],
        outputs=[output_file_wizard]
    )

if __name__ == "__main__":
    demo.launch()
