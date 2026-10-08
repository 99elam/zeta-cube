# MTG Playtest Card Studio

A complete Python and PyQt6 toolchain designed to fetch, format, manually crop, visually layout, batch-render, and compile retro-styled Magic: The Gathering playtest cubes into print-ready 300 DPI PDF slips.

Cards feature an analog aesthetic: typewriter/newsprint serif and sans-serif typography, dithered binarization, toner pinholes, cut-line pasteup outlines, and procedural scanner noise on cream-colored paper.

---

## Features

- **Automated Ingestion (`sheet_gen.py`):** Fetches card lists directly from CubeCobra, queries Scryfall's collection API in 75-card batches, flattens double-faced/split cards, and normalizes typelines (e.g., converting modern creature typelines to classic `Summon`).
- **Interactive WYSIWYG Editor (`card_editor_gui.py`):**
  - Live canvas previewing real-time toner shaders and paper noise.
  - Multi-mode art cropper supporting rectangular boxes and arbitrary polygon point masks.
  - Draggable, resizable bounding boxes with interactive corner handles for Name, Cost, Type, Rules, and P/T elements.
  - Smart collision detection and automatic font scaling to prevent text overflow.
  - Dedicated keyboard speedrun hotkeys for rapid curation across 500+ card cubes.
- **Headless Batch Renderer (`card_gen.py`):** Rasterization pipeline compiling all cube entries into 750×1050 px PNGs using layout coordinates saved in the CSV.
- **Print Sheet Compiler (`build_pdf.py`):** Assembles rendered card PNGs into 9-per-page 300 DPI Letter-sized PDFs (2550×3300 px) centered with precision crop and trim marks. Automatically appends customizable basic land stations.
- **Asset Optimizer (`batch_shrink_crops.py`):** Quantizes and downsamples cropped card art to 8-bit palette PNGs to keep repository sizes under 100 MB without visual quality loss.

---

## Repository Structure

```text
├── pdf/                         # Compiled 300 DPI print-ready PDF slips (split into 3 parts)
├── images/                      # Uncropped raw source art (local cache)
├── images_cropped/              # Active cropped art used during generation
├── playtest_cards/              # Generated 750x1050 px print PNGs
├── modovintage_cube.csv         # Raw cube dataset exported from Scryfall
├── modovintage_cube_edited.csv  # Working dataset containing custom layout coordinates
├── sheet_gen.py                 # CubeCobra & Scryfall data ingestion script
├── card_editor_gui.py           # Interactive PyQt6 studio GUI
├── card_gen.py                  # Headless batch renderer
├── build_pdf.py                 # 9-card PDF sheet layout compiler
├── batch_shrink_crops.py        # Asset downsampling and palette optimizer
├── requirements.txt             # Python dependencies
└── .gitignore                   # Excludes raw images, caches, and build buffers
```

---

## Installation & Setup

### 1. Prerequisites
- Python 3.10 or higher
- Windows, macOS, or Linux

### 2. Clone the Repository
```bash
git clone [https://github.com/](https://github.com/)<your-username>/<repo-name>.git
cd <repo-name>
```

### 3. Create a Virtual Environment
```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows (Command Prompt / PowerShell)
python -m venv .venv
.venv\Scripts\activate
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

---

## Workflow & Usage

### 1. Ingest Cube Data (Optional)
To pull fresh card lists from CubeCobra and populate oracle data from Scryfall:
```bash
python sheet_gen.py
```
This generates `modovintage_cube.csv` with standardized text, mana costs, and split-card handling.

### 2. Layout & Crop in the GUI Studio
Launch the visual editor to fine-tune art crops, nudge bounding boxes, and adjust typography:
```bash
python card_editor_gui.py
```

#### Speedrun Shortcuts (Studio Canvas)
| Shortcut | Action |
| :--- | :--- |
| `Space` or `Ctrl + Enter` | Save card layout to CSV, export PNG, and advance to next pending card |
| `Tab` / `Shift + Tab` | Cycle active element selection (`Art` → `Name` → `Cost` → `Type` → `Rules` → `P/T`) |
| `Arrow Keys` | Nudge selected element position by 1 pixel |
| `Shift + Arrow Keys` | Nudge selected element position by 10 pixels |
| `Mouse Scroll Wheel` | Scale art size (Art selected) or resize font (Text Box selected) |
| `1` / `2` | Toggle font family between **Arial** and **Times New Roman** |
| `I` | Invert art polarity (negative toner effect) |
| `Left Click + Drag` | Move text bounding box or pan cropped art |
| `Drag Handles` | Resize bounding box dimensions interactively |

### 3. Batch Render All Cards
To render the entire cube headlessly using the parameters stored in `modovintage_cube_edited.csv`:
```bash
python card_gen.py
```
Rendered cards are saved to `./playtest_cards/*.png` at standard poker ratio (750×1050 px).

### 4. Compile Print Sheets to PDF
To assemble the print queue into cut-ready sheets:
```bash
python build_pdf.py
```
- Outputs 3 multi-page PDFs in `./pdf/` (`playtest_cube_print_slips_part1.pdf`, `part2.pdf`, `part3.pdf`) formatted for 8.5" × 11" paper at 300 DPI.
- Split evenly into 3 parts (~26 sheets each, ~45–47 MB per file) to stay cleanly under GitHub's 50 MB recommendation and 100 MB file limit.
- Places 9 cards per sheet (3×3 grid, each card scaled to 690×990 px / 2.3" × 3.3" to slide inside card sleeves over bulk cards).
- Renders fine corner and edge crop marks along every margin.
- Automatically appends 30 copies of each basic land (Plains, Island, Swamp, Mountain, Forest) to the back of the print queue in Part 3.

---

## Dataset Schema (`modovintage_cube_edited.csv`)

The tracking spreadsheet stores all persistent layout decisions for reproducibility:

| Column Field | Description |
| :--- | :--- |
| `Name of the card` | Oracle card name. |
| `Mana Cost` | Plaintext symbols without brackets (e.g., `2WW`, `1UB`). |
| `Typeline` | Standardized typeline (`Summon Creature`, `Instant`, `Land`, etc.). |
| `Oracle Text` | Rules text with newline delimiters. |
| `Power / Toughness` | Creature base stats or Planeswalker starting loyalty. |
| `<box>_font`, `<box>_size`, `<box>_bold` | Typography settings for `name`, `cost`, `type`, `rules`, and `pt`. |
| `<box>_left`, `_top`, `_right`, `_bottom` | Absolute pixel boundaries within the 750×1050 canvas. |
| `brightness`, `contrast`, `rotation`, `scale` | Art transformation matrix values. |
| `x_offset`, `y_offset`, `invert_art` | Positional offset coordinates and art polarity flag. |
| `crop_data` | JSON coordinates storing polygon vertices or rectangular boundaries. |
| `cropped_image_path` | Relative path to the cropped art file in `./images_cropped/`. |
| `processed_status` | Status flag (`Pending` or `Done`) enabling batch resume. |

---

## Printing Guidelines

1. **Paper Selection:** Print onto 24 lb or 28 lb natural/cream paper or 65 lb light cardstock to complement the dithered ink color palette.
2. **Printer Scaling:** Set printer dialog scaling to **100% / Actual Size** (do not select "Fit to Page" or "Scale to Printable Area").
3. **Sleeving:** Cut along the tick marks and slip directly in front of standard Magic cards inside opaque sleeves.