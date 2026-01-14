import gradio as gr
import os
import re
import trimesh
import trimesh.creation
import numpy as np
import zipfile
import shutil
import json

# --- 1. Constants & Mappings (from TOM.ipynb) ---
HEBREW_MAP = {
        'א': '⠁',
    'ב': '⠧',
    'ג': '⠛',
    'ד': '⠙',
    'ה': '⠓',
    'ו': '⠺',   # ו רגילה
    'ז': '⠵',
    'ח': '⠭',
    'ט': '⠞',
    'י': '⠚',
    'כ': '⠡',
    'ל': '⠇',
    'מ': '⠍',
    'נ': '⠝',
    'ס': '⠎',
    'ע': '⠫',
    'פ': '⠋', #f
    'צ': '⠮',
    'ק': '⠟',
    'ר': '⠗',
    'ש': '⠩',  #sh
    'ת': '⠹',
    'ך': '⠡',
    'ם': '⠍',
    'ן': '⠝',
    'ף': '⠋',
    'ץ': '⠮',
}

# Map for applying user selections from UI
SPECIAL_REPLACEMENTS = {
    'ו': {'default': 'ו', 'holam': 'וֹ', 'shuruk': 'וּ'},
    'ש': {'shin': 'שׁ', 'sin': 'שׂ'},
    'ב': {'default': 'ב', 'dagesh': 'בּ'},
    'כ': {'default': 'כ', 'dagesh': 'כּ'},
    'פ': {'default': 'פ', 'dagesh': 'פּ'},
    'ך': {'default': 'ך', 'dagesh': 'ךּ'},
    'ף': {'default': 'ף', 'dagesh': 'ףּ'},
}

BRAILLE_DOTS = {
    1: (0, 2), 2: (0, 1), 3: (0, 0),
    4: (1, 2), 5: (1, 1), 6: (1, 0)
}

# --- 2. Classes & Core Functions (from TOM.ipynb) ---
class Letter:
    def __init__(self, char):
        self.char = char
        self.braille = HEBREW_MAP.get(char, '')
        self.dots = self._get_dots()

    def _get_dots(self):
        dots = []
        if not self.braille:
            return dots
        
        braille_val = ord(self.braille) - 0x2800
        for dot_num in BRAILLE_DOTS:
            if (braille_val >> (dot_num - 1)) & 1:
                dots.append(BRAILLE_DOTS[dot_num])
        return dots

class BrailleStlGenerator:
    def __init__(self, base_thickness=2, dot_height=1.5, dot_radius=0.8, font_size=10):
        self.base_thickness = base_thickness
        self.dot_height = dot_height
        self.dot_radius = dot_radius
        self.font_size = font_size
        # Fixed spacing constants based on standards relative to dot radius
        self.DOT_SPACING = self.dot_radius * 3.0  # Spacing between dots within a cell
        self.CELL_SPACING = self.dot_radius * 7.5 # Spacing between cells
        self.LINE_SPACING = self.dot_radius * 12.5 # Spacing between lines

    def create_dot(self, x, y, z):
        # Create a hemisphere for the dot
        dot = trimesh.creation.icosphere(radius=self.dot_radius, subdivisions=3)
        
        # Cut the sphere in half to make a hemisphere
        # Define a plane at z=0 with normal pointing down (0, 0, -1) to keep the top half
        plane_origin = [0, 0, 0]
        plane_normal = [0, 0, -1]
        dot = trimesh.intersections.slice_mesh_plane(dot, plane_normal, plane_origin)
        
        # Translate to final position, sitting on top of the base plate
        dot.apply_translation([x, y, z])
        return dot

    def generate_mesh(self, text):
        lines = text.split('\n')
        meshes = []

        # Calculate base plate dimensions based on text content
        max_line_len = max(len(line) for line in lines) if lines else 0
        num_lines = len(lines)
        
        # Calculate total width and height required for text content
        content_width = max_line_len * self.CELL_SPACING
        content_height = num_lines * self.LINE_SPACING
        
        # Add padding around the content
        padding = self.CELL_SPACING
        base_width = content_width + 2 * padding
        base_depth = content_height + 2 * padding

        # Create base plate
        # Center the base plate origin for easier positioning
        base = trimesh.creation.box(extents=[base_width, base_depth, self.base_thickness])
        base.apply_translation([base_width/2, -base_depth/2, self.base_thickness/2])
        meshes.append(base)

        # Start positioning text from top-left, accounting for padding
        current_y = -padding - self.LINE_SPACING/2
        
        for line in lines:
            current_x = padding + self.CELL_SPACING/2
            for char in line:
                letter = Letter(char)
                for col_idx, row_idx in letter.dots:
                    # Calculate dot position relative to cell origin
                    dot_x = current_x + col_idx * self.DOT_SPACING
                    dot_y = current_y - row_idx * self.DOT_SPACING # Subtract because y goes down
                    
                    # Create and position the dot on top of the base plate
                    dot = self.create_dot(dot_x, dot_y, self.base_thickness)
                    meshes.append(dot)
                current_x += self.CELL_SPACING
            current_y -= self.LINE_SPACING

        # Combine all parts into a single mesh
        combined_mesh = trimesh.util.concatenate(meshes)
        return combined_mesh

def text_to_braille(text):
    # Regex to match Hebrew letters with optional combining marks (niqqud/dagesh)
    # \u0590-\u05FF is the Hebrew block range
    # [\u05D0-\u05EA] matches basic Hebrew letters
    # [\u05B0-\u05BC\u05C1\u05C2]* matches zero or more combining marks
    hebrew_pattern = re.compile(r'([\u05D0-\u05EA][\u05B0-\u05BC\u05C1\u05C2]*|.)')
    
    # Find all matches (letters with their marks, or single other characters)
    tokens = hebrew_pattern.findall(text)
    
    braille_output = []
    for token in tokens:
        # Try to find the exact token (e.g., 'בּ') in the map
        if token in HEBREW_MAP:
            braille_output.append(HEBREW_MAP[token])
        # If not found (e.g., complex combination not in map), fall back to base letter
        elif token[0] in HEBREW_MAP:
             braille_output.append(HEBREW_MAP[token[0]])
        else:
            # Keep non-Hebrew characters as is, or handle as needed
            braille_output.append(token)
            
    return ''.join(braille_output)

def create_braille_stl(text, output_filename="output.stl", font_size=10, base_thickness=2, dot_height=1.5, dot_radius=0.8):
    generator = BrailleStlGenerator(base_thickness, dot_height, dot_radius, font_size)
    mesh = generator.generate_mesh(text)
    mesh.export(output_filename)
    print(f"Braille STL saved to {output_filename}")

def clean_text(text):
    # Remove standard niqqud (U+05B0 to U+05BB)
    text = re.sub(r'[\u05B0-\u05BB]', '', text)
    # Remove Shin/Sin dots (U+05C1, U+05C2)
    text = re.sub(r'[\u05C1-\u05C2]', '', text)
    # Remove Dagesh (U+05BC)
    text = re.sub(r'\u05BC', '', text)
    return text

# --- 3. New Helper for UI Integration ---
def apply_variations(raw_text, variations):
    """Replaces characters in raw_text based on user selections in variations map."""
    result_chars = list(raw_text)
    for index_str, variant_name in variations.items():
        try:
            index = int(index_str)
            if 0 <= index < len(result_chars):
                char = result_chars[index]
                if char in SPECIAL_REPLACEMENTS and variant_name in SPECIAL_REPLACEMENTS[char]:
                    result_chars[index] = SPECIAL_REPLACEMENTS[char][variant_name]
        except (ValueError, IndexError):
            continue # Ignore invalid indices
    return "".join(result_chars)

# --- 4. Main API Logic ---
def generate_stl_logic(json_input):
    """
    Main function called by the API.
    Expects a JSON string with a "pages" list.
    Returns the path to a ZIP file containing STLs for all pages.
    """
    try:
        data = json.loads(json_input)
        pages = data.get("pages", [])
    except json.JSONDecodeError:
        return "Error: Invalid JSON input"

    output_dir = "braille_output_temp"
    os.makedirs(output_dir, exist_ok=True)
    stl_files = []

    print(f"Processing {len(pages)} pages...")

    for i, page in enumerate(pages):
        raw_text = page.get("raw_text", "")
        variations = page.get("variations", {})
        page_num = page.get("page_number", i + 1)

        # 1. Apply user selections to get correct Hebrew unicode string
        processed_text = apply_variations(raw_text, variations)
        
        # 2. Convert to Braille
        braille_text = text_to_braille(processed_text)
        print(f"Page {page_num}: '{processed_text}' -> '{braille_text}'")

        # 3. Generate STL
        stl_filename = os.path.join(output_dir, f"page_{page_num}.stl")
        try:
            create_braille_stl(processed_text, output_filename=stl_filename)
            stl_files.append(stl_filename)
        except Exception as e:
            print(f"Error generating STL for page {page_num}: {e}")

    # 4. Create ZIP file
    zip_filename = "braille_book.zip"
    with zipfile.ZipFile(zip_filename, 'w') as zipf:
        for stl_file in stl_files:
            zipf.write(stl_file, os.path.basename(stl_file))
    
    print(f"Created {zip_filename} with {len(stl_files)} files.")

    # 5. Cleanup temp files
    shutil.rmtree(output_dir)

    return zip_filename

# --- 5. Launch Gradio Interface ---
iface = gr.Interface(
    fn=generate_stl_logic,
    inputs=gr.Textbox(label="JSON Input"), # Takes a JSON string
    outputs=gr.File(label="Download ZIP"), # Returns a file for download
    title="Hebrew Braille STL Generator API"
)

iface.launch()