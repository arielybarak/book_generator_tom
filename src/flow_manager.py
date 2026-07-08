"""
Multi-page book orchestrator (CLI / programmatic use).

Accepts a list of page dicts and runs the full pipeline for each:
  Hebrew input → Stable Diffusion image → 3 PNGs → 3 DXFs → STL

Pages are processed atomically — if any step throws, that page's state is not updated.
Outputs land in books/{book_name}_{timestamp}/.

Main class: FlowManager(book_name, pages)
  fm = FlowManager("my_book", pages)
  result = fm.run()

Note: this module uses image_generator.py which calls add_nikud() (interactive input()).
It is CLI-only — the web app (hf_space/gradio_app.py) has its own generation pipeline.
"""

# ## we want flow manager, the flow manager knows to get a dict:
# ## pages: array of pages containing {page number:, image_description:, image_classification:,
#           generate_picture:, done:, images_locations: (DataClass of image location, braille location, text location), 
#           dxf_locations:(DataClass of image location, braille location, text location)
#           stl locations:()
#           user_inputs = {}
#            }
#           if one part failed or return error it doesnt update it
#           name of book + datetime - creating a folder for the book and save images there
#           class will return result object of: [pages_images:{page number, images_locations}
#                                               stl_file]

#   flow will go over each page, if needed will call function of Dana and will save it in specific place
from src.dxf_3d import create_one_page_stl_from_dxf
from src.image_generator import images_to_dxf, create_images
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import shutil
import traceback
import os
IMAGES_KEYS = ['main_image', 'text','braille']
# -----------------------------
# Data models
# -----------------------------

@dataclass
class PageState:
    page_number: int
    image_description: str
    image_classification: str
    generate_picture: bool
    done: bool = False

    images_locations: Dict[str, str] = field(default_factory=dict)
    dxf_locations: Dict[str, str] = field(default_factory=dict)
    stl_location: Optional[str] = None

    user_inputs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FlowResult:
    pages_images: List[Dict[str, Any]]
    stl_files: List[str]


# -----------------------------
# Flow Manager
# -----------------------------

class FlowManager:
    """
    Orchestrates page-wise generation of images, DXFs, and STLs.
    Ensures atomic updates: if a step fails, the page state is NOT updated.
    """

    def __init__(self, book_name: str, pages: List[Dict[str, Any]], base_dir: str = "books"):
        self.book_name = book_name
        self.created_at = datetime.now().strftime("%Y%m%d_%H%M%S")

        self.root_dir = Path(base_dir) / f"{book_name}_{self.created_at}"
        self.images_dir = self.root_dir / "images"
        self.dxf_dir = self.root_dir / "dxfs"
        self.stl_dir = self.root_dir / "stls"

        self._create_dirs()

        self.pages: List[PageState] = [
            PageState(**page_dict) for page_dict in pages
        ]

    # -------------------------
    # Public API
    # -------------------------

    def run(self) -> FlowResult:
        for page in self.pages:
            if page.done:
                continue

            try:
                self._process_page(page)
            except Exception as e:
                # Page is NOT updated if any part fails
                print(f"[ERROR] Page {page.page_number} failed: {e}")
                traceback.print_exc()
        # if all pages are done and there is stl to each of them build the result and send it, else send something else

        return self._build_result()

    # -------------------------
    # Page Processing
    # -------------------------

    def _process_page(self, page: PageState) -> None:
        """
        Runs all required steps for a single page.
        Uses temporary state and commits only on success.
        """
        
        if page.generate_picture:
            self.generate_images(page)
            self.generate_dxfs(page)
        
        if page.done:
            self.generate_stl(page,)


    # -------------------------
    # Generation steps
    # -------------------------

    def generate_images(self, page: PageState) -> Dict[str, str]:
        """
        Calls external image generator (e.g. Dana).
        """
            
        page_dir = self.images_dir / f"page_{page.page_number}"
        page_dir.mkdir(parents=True, exist_ok=True)
        hebrew_prompt, picture_type = page.image_description, page.image_classification
        # Placeholder for Dana call
        image_path = page_dir / "image.png"
        braille_path = page_dir / "braille.png"
        text_path = page_dir / "text.png"

        create_images(hebrew_prompt, picture_type, image_path, text_path, braille_path)
        # Example stub writes
        images = zip(IMAGES_KEYS, [image_path, text_path, braille_path])
        for key, path in images:
            if os.path.exists(str(path)):
                page.images_locations[key] = path
            else:
                page.images_locations[key] = None
        # page.images_locations = images_locations
            

    def generate_dxfs(
        self, page: PageState
    ) -> Dict[str, str]:
        
        if not page.generate_picture:
            return
        
        page_dir = self.images_dir / f"page_{page.page_number}"
        page_dir.mkdir(parents=True, exist_ok=True)
        
        image_location, text_location, braille_location = page.images_locations[IMAGES_KEYS[0]], page.images_locations[IMAGES_KEYS[1]], page.images_locations[IMAGES_KEYS[2]]
        if image_location is None or  text_location is None or braille_location is None:
            raise Exception("An image is missing try generating images again")
        dxf_image_location, dxf_text_location, dxf_braille_location = images_to_dxf(image_location, text_location, braille_location)
        images = zip(IMAGES_KEYS, [dxf_image_location, dxf_text_location, dxf_braille_location])
        for key, path in images:
            if os.path.exists(str(path)):
                page.dxf_locations[key] = path
            else:
                page.dxf_locations[key] = None
        

    def generate_stl(
        self, page: PageState
    ) -> str:
        stl_path = self.images_dir / f"page_{page.page_number}.stl"
        # stl_path.touch()
        dxf_image_location, dxf_text_location, dxf_braille_location = page.dxf_locations[IMAGES_KEYS[0]], page.dxf_locations[IMAGES_KEYS[1]], page.dxf_locations[IMAGES_KEYS[2]]
        page.stl_location = create_one_page_stl_from_dxf(dxf_text_location, dxf_braille_location, dxf_image_location, output=stl_path)
        # return stl_location

    # -------------------------
    # Helpers
    # -------------------------

    def _create_dirs(self):
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(exist_ok=True)
        self.dxf_dir.mkdir(exist_ok=True)
        self.stl_dir.mkdir(exist_ok=True)

    def _build_result(self) -> FlowResult:
        ### need to work with the ui about what should be here
        pages_images = [
            {
                "page_number": p.page_number,
                "images_locations": p.images_locations,
            }
            for p in self.pages
            if p.done
        ]

        stl_files = [
            p.stl_location for p in self.pages if p.done and p.stl_location
        ]

        return FlowResult(
            pages_images=pages_images,
            stl_files=stl_files,
        )