import hashlib
import json
import os
import random
import re
import sys
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QCompleter,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

# ================= Configuration =================
INPUT_CSV = "modovintage_cube.csv"
OUTPUT_CSV = "modovintage_cube_edited.csv"
IMAGES_DIR = "./images"
CROPPED_DIR = "./images_cropped"
PLAYTEST_CARDS_DIR = "./playtest_cards"

CARD_WIDTH = 750
CARD_HEIGHT = 1050

CREAM_PAPER = (245, 241, 230)
INK_BLACK = (18, 20, 24)

# Reusable dummy drawing context for fast text metrics
DUMMY_IMG = Image.new("RGB", (1, 1))
DUMMY_DRAW = ImageDraw.Draw(DUMMY_IMG)


def reorder_summon_typeline(typeline: str) -> str:
    """If 'summon' appears in the typeline, moves it to be the very first word."""
    if not typeline:
        return ""
    faces = typeline.split(" // ")
    cleaned_faces = []
    for face in faces:
        tokens = face.strip().split()
        match_idx = -1
        for idx, tok in enumerate(tokens):
            if tok.lower() == "summon":
                match_idx = idx
                break
        if match_idx != -1:
            tokens.pop(match_idx)
            tokens.insert(0, "Summon")
        cleaned_faces.append(" ".join(tokens))
    return " // ".join(cleaned_faces)


def get_font(family: str, size: int, bold: bool = True) -> ImageFont.ImageFont:
    font_candidates = {
        "Arial": {
            True: [
                "C:/Windows/Fonts/arialbd.ttf",
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                "/System/Library/Fonts/Arial Bold.ttf",
                "/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                "arialbd.ttf",
            ],
            False: [
                "C:/Windows/Fonts/arial.ttf",
                "/System/Library/Fonts/Supplemental/Arial.ttf",
                "/System/Library/Fonts/Arial.ttf",
                "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                "arial.ttf",
            ],
        },
        "Times New Roman": {
            True: [
                "C:/Windows/Fonts/timesbd.ttf",
                "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
                "/System/Library/Fonts/Times Bold.ttf",
                "/Library/Fonts/Times New Roman Bold.ttf",
                "/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman_Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
                "timesbd.ttf",
            ],
            False: [
                "C:/Windows/Fonts/times.ttf",
                "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
                "/System/Library/Fonts/Times.ttf",
                "/Library/Fonts/Times New Roman.ttf",
                "/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
                "times.ttf",
            ],
        },
    }

    candidates = font_candidates.get(family, font_candidates["Arial"])[bold]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except IOError:
                continue

    try:
        font_name = "times" if "Times" in family else "arial"
        suffix = "bd.ttf" if bold else ".ttf"
        return ImageFont.truetype(f"{font_name}{suffix}", size)
    except IOError:
        return ImageFont.load_default()


def get_safe_filename(name: str) -> str:
    sanitized = "".join(c for c in name if c.isalnum() or c in (" ", "_", "-")).strip()
    return sanitized.replace(" ", "_")


def find_source_image(card_name: str) -> str | None:
    safe = get_safe_filename(card_name)
    variants = [safe, safe.lower(), card_name, card_name.replace(" ", "_")]
    exts = [".png", ".jpg", ".jpeg", ".webp", ".PNG", ".JPG", ".JPEG"]
    for v in variants:
        for ext in exts:
            p = os.path.join(IMAGES_DIR, f"{v}{ext}")
            if os.path.exists(p):
                return p
        direct = os.path.join(IMAGES_DIR, v)
        if os.path.isfile(direct):
            return direct
    return None


def apply_photocopy(img: Image.Image, brightness: float = 1.0, contrast: float = 2.2, invert: bool = False) -> Image.Image:
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    else:
        img = img.convert("RGB")

    if brightness != 1.0:
        img = ImageEnhance.Brightness(img).enhance(brightness)
    if contrast != 1.0:
        img = ImageEnhance.Contrast(img).enhance(contrast)

    gray = img.convert("L")
    if invert:
        gray = ImageOps.invert(gray)

    gray = ImageOps.autocontrast(gray, cutoff=2)
    sharpened = gray.filter(ImageFilter.SHARPEN)

    dithered = sharpened.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    dithered_gray = dithered.convert("L")
    return ImageOps.colorize(dithered_gray, black=INK_BLACK, white=CREAM_PAPER)


GRAIN_SHAPES = {
    1: [[(0, 0)]],
    2: [
        [(0, 0), (1, 0)],
        [(0, 0), (0, 1)],
        [(0, 0), (1, 1)],
        [(0, 0), (-1, 1)],
    ],
    3: [
        [(0, 0), (1, 0), (0, 1)],
        [(0, 0), (-1, 0), (0, 1)],
        [(0, 0), (1, 0), (0, -1)],
        [(0, 0), (-1, 0), (0, -1)],
        [(0, 0), (1, 0), (-1, 0)],
        [(0, 0), (0, 1), (0, -1)],
        [(0, 0), (1, 1), (-1, -1)],
        [(0, 0), (-1, 1), (1, -1)],
    ],
    4: [
        [(0, 0), (1, 0), (0, 1), (1, 1)],
        [(0, 0), (-1, 0), (1, 0), (0, 1)],
        [(0, 0), (-1, 0), (1, 0), (0, -1)],
        [(0, 0), (0, -1), (0, 1), (1, 0)],
        [(0, 0), (0, -1), (0, 1), (-1, 0)],
        [(0, 0), (0, 1), (0, 2), (1, 0)],
        [(0, 0), (0, 1), (0, 2), (-1, 0)],
        [(0, 0), (1, 0), (2, 0), (0, 1)],
        [(0, 0), (1, 0), (2, 0), (0, -1)],
        [(0, 0), (1, 0), (1, 1), (2, 1)],
        [(0, 0), (0, 1), (1, 1), (1, 2)],
        [(0, 0), (-1, 0), (-1, 1), (-2, 1)],
    ],
}


def add_photocopy_grain(card_img: Image.Image, seed_key: str = "card") -> Image.Image:
    seed = int(hashlib.md5(seed_key.encode("utf-8")).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    w, h = card_img.size

    arr = np.array(card_img, dtype=np.int16)
    paper_noise = rng.normal(0, 1.4, (h, w, 1)).astype(np.int16)
    arr = np.clip(arr + paper_noise, 0, 255)
    result = Image.fromarray(arr.astype(np.uint8))
    draw = ImageDraw.Draw(result)

    sizes = [1, 2, 3, 4]
    size_weights = [0.65, 0.22, 0.09, 0.04]

    def stamp_grain(x: int, y: int, gray: int):
        sz = rng.choice(sizes, p=size_weights)
        pool = GRAIN_SHAPES[sz]
        shape = pool[rng.integers(0, len(pool))]
        for dx, dy in shape:
            px, py = x + dx, y + dy
            if 0 <= px < w and 0 <= py < h:
                draw.point((px, py), fill=(gray, gray, gray))

    num_allover = rng.integers(300, 450)
    for _ in range(num_allover):
        stamp_grain(rng.integers(10, w - 10), rng.integers(10, h - 10), int(rng.integers(30, 130)))

    num_clusters = rng.integers(8, 13)
    for _ in range(num_clusters):
        cx, cy = rng.integers(30, w - 30), rng.integers(30, h - 30)
        spread_x, spread_y = rng.uniform(35, 75), rng.uniform(35, 75)
        for _ in range(rng.integers(30, 65)):
            px = int(rng.normal(cx, spread_x))
            py = int(rng.normal(cy, spread_y))
            if 5 <= px < w - 5 and 5 <= py < h - 5:
                stamp_grain(px, py, int(rng.integers(25, 115)))

    num_fibers = rng.integers(2, 5)
    for _ in range(num_fibers):
        fx, fy = rng.integers(20, w - 20), rng.integers(20, h - 20)
        draw.line([fx, fy, fx + int(rng.choice([-1, 0, 1])), fy + rng.integers(5, 12)], fill=int(rng.integers(45, 110)), width=1)

    return result


def wrap_text(text: str, font: ImageFont.ImageFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    lines = []
    for para in text.split("\n"):
        if not para.strip():
            lines.append("")
            continue
        words = para.split(" ")
        current_line = []
        for word in words:
            test_line = " ".join(current_line + [word])
            bbox = draw.textbbox((0, 0), test_line, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                current_line = [word]
        if current_line:
            lines.append(" ".join(current_line))
    return lines


# ================= Smart Layout Calculation =================
def compute_smart_card_layout(row: dict) -> dict:
    """Calculates balanced, non-overlapping bounding coordinates and optimal font sizes."""
    has_pt = bool(str(row.get("Power / Toughness", "")).strip())
    name = str(row.get("Name of the card", "")).strip()
    cost = str(row.get("Mana Cost", "")).strip()
    typeline = reorder_summon_typeline(str(row.get("Typeline", "")).strip())
    oracle_text = str(row.get("Oracle Text", "")).strip()
    pt = str(row.get("Power / Toughness", "")).strip()

    # 1. Cost Box
    c_font_name = row.get("cost_font", "Arial")
    c_bold = str(row.get("cost_bold", "True")).lower() == "true"
    c_size = int(float(row.get("cost_size", 78)))
    c_font = get_font(c_font_name, c_size, bold=c_bold)
    c_bbox = DUMMY_DRAW.textbbox((0, 0), cost, font=c_font) if cost else (0, 0, 80, 60)
    c_w = c_bbox[2] - c_bbox[0]
    c_h = c_bbox[3] - c_bbox[1]
    cost_right = 705
    cost_top = 25
    cost_width = max(80, c_w + 28) if cost else 80
    cost_left = max(450, cost_right - cost_width)
    cost_bottom = cost_top + max(c_h + 32, 85)

    # 2. Name Box (Dynamic down-scaling to avoid cost box collision)
    n_font_name = row.get("name_font", "Arial")
    n_bold = str(row.get("name_bold", "True")).lower() == "true"
    name_size = int(float(row.get("name_size", 78)))
    max_name_right = cost_left - 15
    avail_name_w = max_name_right - 45 - 28

    while name_size > 36:
        n_font = get_font(n_font_name, name_size, bold=n_bold)
        n_bbox = DUMMY_DRAW.textbbox((0, 0), name, font=n_font)
        if (n_bbox[2] - n_bbox[0]) <= avail_name_w:
            break
        name_size -= 2

    n_font = get_font(n_font_name, name_size, bold=n_bold)
    n_bbox = DUMMY_DRAW.textbbox((0, 0), name, font=n_font) if name else (0, 0, 150, 60)
    n_w = n_bbox[2] - n_bbox[0]
    n_h = n_bbox[3] - n_bbox[1]
    name_left = 45
    name_top = 25
    name_right = min(max_name_right, name_left + max(120, n_w + 28))
    name_bottom = name_top + max(n_h + 32, 85)

    # 3. Typeline Box
    t_font_name = row.get("type_font", "Arial")
    t_bold = str(row.get("type_bold", "True")).lower() == "true"
    type_size = int(float(row.get("type_size", 42)))
    t_font = get_font(t_font_name, type_size, bold=t_bold)
    t_bbox = DUMMY_DRAW.textbbox((0, 0), typeline, font=t_font) if typeline else (0, 0, 160, 40)
    t_w = t_bbox[2] - t_bbox[0]
    t_h = t_bbox[3] - t_bbox[1]
    type_left = 45
    type_top = 135
    type_right = min(705, type_left + max(120, t_w + 28))
    type_bottom = type_top + max(t_h + 24, 60)

    # 4. Power / Toughness Box
    pt_left, pt_top, pt_right, pt_bottom = 560, 920, 705, 995
    if has_pt:
        pt_font_name = row.get("pt_font", "Arial")
        pt_bold = str(row.get("pt_bold", "True")).lower() == "true"
        pt_size = int(float(row.get("pt_size", 68)))
        p_font = get_font(pt_font_name, pt_size, bold=pt_bold)
        p_bbox = DUMMY_DRAW.textbbox((0, 0), pt, font=p_font) if pt else (0, 0, 70, 50)
        p_w = p_bbox[2] - p_bbox[0]
        p_h = p_bbox[3] - p_bbox[1]
        pt_right = 705
        pt_bottom = 995
        pt_width = max(90, p_w + 28)
        pt_height = max(75, p_h + 28)
        pt_left = pt_right - pt_width
        pt_top = pt_bottom - pt_height

    # 5. Rules Box (Auto-sizing for overflow prevention and card-type width awareness)
    r_font_name = row.get("rules_font", "Arial")
    r_bold = str(row.get("rules_bold", "True")).lower() == "true"
    rules_size = int(float(row.get("rules_size", 28)))
    rules_left = 45
    rules_bottom = 995
    rules_right = (pt_left - 15) if has_pt else 705

    if oracle_text:
        if len(oracle_text) < 70:
            rules_size = max(rules_size, 36)
        usable_w = (rules_right - rules_left) - 20
        while rules_size > 18:
            r_font = get_font(r_font_name, rules_size, bold=r_bold)
            lines = wrap_text(oracle_text, r_font, usable_w, DUMMY_DRAW)
            line_height = int(rules_size * 1.35)
            text_h = len(lines) * line_height
            if text_h <= 430:
                break
            rules_size -= 2
        box_h = max(80, text_h + 36)
        rules_top = max(520, rules_bottom - box_h)
    else:
        rules_top = 760

    return {
        "name": (name_left, name_top, name_right, name_bottom, name_size),
        "cost": (cost_left, cost_top, cost_right, cost_bottom, c_size),
        "type": (type_left, type_top, type_right, type_bottom, type_size),
        "rules": (rules_left, rules_top, rules_right, rules_bottom, rules_size),
        "pt": (pt_left, pt_top, pt_right, pt_bottom, int(float(row.get("pt_size", 68)))),
    }


# ================= Central Card Rendering =================
def render_full_card(
    row: dict,
    art_image: Image.Image | None,
    cfg_name: dict,
    cfg_cost: dict,
    cfg_type: dict,
    cfg_rules: dict,
    cfg_pt: dict,
    brightness: float = 1.0,
    contrast: float = 2.2,
    rotation: float = 0.0,
    scale: float = 1.25,
    x_offset: int = 0,
    y_offset: int = -60,
    invert_art: bool = False,
) -> Image.Image:
    card = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), CREAM_PAPER)
    name = str(row.get("Name of the card", "")).strip()
    cost = str(row.get("Mana Cost", "")).strip()
    typeline = reorder_summon_typeline(str(row.get("Typeline", "")).strip())
    oracle_text = str(row.get("Oracle Text", "")).strip()
    pt = str(row.get("Power / Toughness", "")).strip()
    has_pt = bool(pt)

    # 1. Art Render
    if art_image:
        try:
            art = art_image.copy()
            art = apply_photocopy(art, brightness=brightness, contrast=contrast, invert=invert_art)

            if rotation != 0:
                art = art.rotate(
                    -rotation,
                    expand=True,
                    fillcolor=CREAM_PAPER,
                    resample=Image.Resampling.BICUBIC,
                )

            base_w = 640
            base_h = 500
            art.thumbnail((base_w, base_h), Image.Resampling.LANCZOS)

            if scale != 1.0:
                nw = max(10, int(art.width * scale))
                nh = max(10, int(art.height * scale))
                art = art.resize((nw, nh), Image.Resampling.LANCZOS)

            center_x = (CARD_WIDTH - art.width) // 2
            center_y = (CARD_HEIGHT - art.height) // 2
            final_x = center_x + x_offset
            final_y = center_y + y_offset

            card.paste(art, (final_x, final_y))
        except Exception as e:
            print(f"Error rendering art: {e}")

    # 2. Text Boxes
    def render_photocopied_box(cfg: dict, text: str, box_key: str, align: str = "left", multiline: bool = False):
        if not text:
            return

        b_left = min(cfg["left"], cfg["right"] - 10)
        b_right = max(cfg["right"], cfg["left"] + 10)
        b_top = min(cfg["top"], cfg["bottom"] - 10)
        b_bottom = max(cfg["bottom"], cfg["top"] + 10)

        box_w = b_right - b_left
        box_h = b_bottom - b_top

        tile = Image.new("L", (box_w, box_h), 255)
        tile_draw = ImageDraw.Draw(tile)
        font = get_font(cfg["font"], cfg["size"], bold=cfg["bold"])

        if multiline:
            usable_w = box_w - 20
            lines = wrap_text(text, font, usable_w, tile_draw)
            line_height = int(cfg["size"] * 1.35)
            cur_y = 10
            for line in lines:
                if cur_y + line_height > box_h:
                    break
                tile_draw.text((10, cur_y), line, fill=0, font=font)
                cur_y += line_height
        else:
            bbox = tile_draw.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            pos_y = max(0, (box_h - text_h) // 2) - bbox[1]

            if align == "right":
                pos_x = (box_w - text_w - 8) - bbox[0]
            elif align == "center":
                pos_x = max(0, (box_w - text_w) // 2) - bbox[0]
            else:
                pos_x = 8 - bbox[0]

            tile_draw.text((pos_x, pos_y), text, fill=0, font=font)

        blurred = tile.filter(ImageFilter.GaussianBlur(radius=0.6))
        seed = int(hashlib.md5(f"{name}_{box_key}".encode("utf-8")).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)

        arr = np.array(blurred, dtype=np.float32)
        noise = rng.normal(0, 22.0, arr.shape)
        arr_noisy = np.clip(arr + noise, 0, 255)

        is_paper = arr_noisy >= 120
        is_black = ~is_paper
        pinholes = rng.random(arr.shape) < 0.007
        is_paper[is_black & pinholes] = True

        mono = (is_paper.astype(np.uint8)) * 255
        tile_mono = Image.fromarray(mono, mode="L")
        colored = ImageOps.colorize(tile_mono, black=INK_BLACK, white=CREAM_PAPER)
        card.paste(colored, (b_left, b_top))

    render_photocopied_box(cfg_name, name, "name", align="left")
    render_photocopied_box(cfg_cost, cost, "cost", align="right")
    render_photocopied_box(cfg_type, typeline, "type", align="left")
    render_photocopied_box(cfg_rules, oracle_text, "rules", align="left", multiline=True)

    if has_pt:
        render_photocopied_box(cfg_pt, pt, "pt", align="center")

    return add_photocopy_grain(card, seed_key=name)


# ================= Reusable Text Box Control Widget =================
class TextBoxSettingsWidget(QWidget):
    def __init__(self, def_size: int, def_l: int, def_t: int, def_r: int, def_b: int, change_cb, max_size: int = 180):
        super().__init__()
        self.change_cb = change_cb
        layout = QFormLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self.combo_font = QComboBox()
        self.combo_font.addItems(["Arial", "Times New Roman"])
        self.combo_font.currentIndexChanged.connect(self.change_cb)
        layout.addRow("Font (Hotkeys 1/2):", self.combo_font)

        self.chk_bold = QCheckBox("Bold")
        self.chk_bold.setChecked(True)
        self.chk_bold.stateChanged.connect(self.change_cb)
        layout.addRow("", self.chk_bold)

        self.slider_size = self._make_slider(10, max_size, def_size)
        layout.addRow("Font Size (Scroll):", self.slider_size)

        self.slider_right = self._make_slider(50, 745, def_r)
        layout.addRow("Right X:", self.slider_right)

        self.slider_top = self._make_slider(5, 1030, def_t)
        layout.addRow("Top Y:", self.slider_top)

        self.slider_left = self._make_slider(5, 700, def_l)
        layout.addRow("Left X:", self.slider_left)

        self.slider_bottom = self._make_slider(20, 1045, def_b)
        layout.addRow("Bottom Y:", self.slider_bottom)

    def _make_slider(self, min_v, max_v, def_v):
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(min_v, max_v)
        s.setValue(def_v)
        s.valueChanged.connect(self.change_cb)
        return s

    def get_settings(self) -> dict:
        return {
            "font": self.combo_font.currentText(),
            "bold": self.chk_bold.isChecked(),
            "size": self.slider_size.value(),
            "left": self.slider_left.value(),
            "top": self.slider_top.value(),
            "right": self.slider_right.value(),
            "bottom": self.slider_bottom.value(),
        }

    def set_settings(self, font_name: str, bold: bool, size: int, left: int, top: int, right: int, bottom: int):
        self.combo_font.blockSignals(True)
        self.combo_font.setCurrentText(font_name)
        self.combo_font.blockSignals(False)

        self.chk_bold.blockSignals(True)
        self.chk_bold.setChecked(bold)
        self.chk_bold.blockSignals(False)

        for slider, val in [
            (self.slider_size, size),
            (self.slider_left, left),
            (self.slider_top, top),
            (self.slider_right, right),
            (self.slider_bottom, bottom),
        ]:
            slider.blockSignals(True)
            slider.setValue(val)
            slider.blockSignals(False)


# ================= Interactive Card WYSIWYG Canvas =================
class CardCanvas(QWidget):
    def __init__(self, parent_app):
        super().__init__()
        self.app = parent_app
        self.pixmap = None
        self.selected_elem = "name"
        self.drag_mode = None
        self.active_handle = None
        self.drag_start_screen = None
        self.drag_start_coords = None
        self.has_pt = True

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(460, 644)

    def set_pixmap(self, pixmap: QPixmap):
        self.pixmap = pixmap
        self.update()

    def get_scale_and_offsets(self):
        w, h = self.width(), self.height()
        if w == 0 or h == 0:
            return 1.0, 0, 0
        scale = min(w / float(CARD_WIDTH), h / float(CARD_HEIGHT))
        off_x = (w - (CARD_WIDTH * scale)) / 2.0
        off_y = (h - (CARD_HEIGHT * scale)) / 2.0
        return scale, off_x, off_y

    def card_to_widget(self, cx: float, cy: float) -> tuple[float, float]:
        scale, off_x, off_y = self.get_scale_and_offsets()
        return (cx * scale) + off_x, (cy * scale) + off_y

    def widget_to_card(self, wx: float, wy: float) -> tuple[float, float]:
        scale, off_x, off_y = self.get_scale_and_offsets()
        return (wx - off_x) / scale, (wy - off_y) / scale

    def get_element_rect(self, elem: str) -> tuple[int, int, int, int] | None:
        if elem == "art":
            x_off = self.app.slider_x.value()
            y_off = self.app.slider_y.value()
            scale = self.app.slider_scale.value() / 100.0
            base_w = int(640 * scale)
            base_h = int(500 * scale)
            cx = (CARD_WIDTH - base_w) // 2 + x_off
            cy = (CARD_HEIGHT - base_h) // 2 + y_off
            return cx, cy, cx + base_w, cy + base_h

        w_map = {
            "name": self.app.editor_name,
            "cost": self.app.editor_cost,
            "type": self.app.editor_type,
            "rules": self.app.editor_rules,
            "pt": self.app.editor_pt,
        }
        widget = w_map.get(elem)
        if not widget or (elem == "pt" and not self.has_pt):
            return None
        cfg = widget.get_settings()
        return cfg["left"], cfg["top"], cfg["right"], cfg["bottom"]

    def hit_test_handle(self, wx: float, wy: float, rect: tuple[int, int, int, int]) -> str | None:
        l, t, r, b = rect
        corners = {
            "tl": (l, t),
            "tr": (r, t),
            "bl": (l, b),
            "br": (r, b),
        }
        for handle, (cx, cy) in corners.items():
            sx, sy = self.card_to_widget(cx, cy)
            if abs(wx - sx) <= 8 and abs(wy - sy) <= 8:
                return handle
        return None

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        wx, wy = pos.x(), pos.y()
        self.drag_start_screen = pos

        # Check handles on current selection first
        cur_rect = self.get_element_rect(self.selected_elem)
        if cur_rect and self.selected_elem != "art":
            handle = self.hit_test_handle(wx, wy, cur_rect)
            if handle:
                self.drag_mode = "resize"
                self.active_handle = handle
                self.drag_start_coords = cur_rect
                return

        # Check all text boxes
        order = ["pt", "cost", "name", "type", "rules"] if self.has_pt else ["cost", "name", "type", "rules"]
        for elem in order:
            rect = self.get_element_rect(elem)
            if not rect:
                continue
            l, t, r, b = rect
            sx1, sy1 = self.card_to_widget(l, t)
            sx2, sy2 = self.card_to_widget(r, b)
            if min(sx1, sx2) <= wx <= max(sx1, sx2) and min(sy1, sy2) <= wy <= max(sy1, sy2):
                self.selected_elem = elem
                self.app.sync_tab_from_canvas(elem)
                self.drag_mode = "move"
                self.drag_start_coords = rect
                self.update()
                return

        # Check art
        art_rect = self.get_element_rect("art")
        if art_rect:
            al, at, ar, ab = art_rect
            asx1, asy1 = self.card_to_widget(al, at)
            asx2, asy2 = self.card_to_widget(ar, ab)
            if asx1 <= wx <= asx2 and asy1 <= wy <= asy2:
                self.selected_elem = "art"
                self.app.sync_tab_from_canvas("art")
                self.drag_mode = "move_art"
                self.drag_start_coords = (self.app.slider_x.value(), self.app.slider_y.value())
                self.update()

    def mouseMoveEvent(self, event):
        pos = event.position()
        wx, wy = pos.x(), pos.y()

        if not self.drag_mode:
            # Update cursors on hover
            cur_rect = self.get_element_rect(self.selected_elem)
            if cur_rect and self.selected_elem != "art":
                handle = self.hit_test_handle(wx, wy, cur_rect)
                if handle in ("tl", "br"):
                    self.setCursor(Qt.CursorShape.SizeFDiagCursor)
                    return
                elif handle in ("tr", "bl"):
                    self.setCursor(Qt.CursorShape.SizeBDiagCursor)
                    return
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        scale, _, _ = self.get_scale_and_offsets()
        dx = (wx - self.drag_start_screen.x()) / scale
        dy = (wy - self.drag_start_screen.y()) / scale

        if self.drag_mode == "move":
            l, t, r, b = self.drag_start_coords
            w = r - l
            h = b - t
            nl = max(5, min(745 - w, int(l + dx)))
            nt = max(5, min(1045 - h, int(t + dy)))
            self.app.set_element_coords(self.selected_elem, nl, nt, nl + w, nt + h)

        elif self.drag_mode == "resize":
            l, t, r, b = self.drag_start_coords
            if self.active_handle == "tl":
                nl = min(r - 20, max(5, int(l + dx)))
                nt = min(b - 20, max(5, int(t + dy)))
                self.app.set_element_coords(self.selected_elem, nl, nt, r, b)
            elif self.active_handle == "tr":
                nr = max(l + 20, min(745, int(r + dx)))
                nt = min(b - 20, max(5, int(t + dy)))
                self.app.set_element_coords(self.selected_elem, l, nt, nr, b)
            elif self.active_handle == "bl":
                nl = min(r - 20, max(5, int(l + dx)))
                nb = max(t + 20, min(1045, int(b + dy)))
                self.app.set_element_coords(self.selected_elem, nl, t, r, nb)
            elif self.active_handle == "br":
                nr = max(l + 20, min(745, int(r + dx)))
                nb = max(t + 20, min(1045, int(b + dy)))
                self.app.set_element_coords(self.selected_elem, l, t, nr, nb)

        elif self.drag_mode == "move_art":
            ox, oy = self.drag_start_coords
            self.app.slider_x.setValue(int(ox + dx))
            self.app.slider_y.setValue(int(oy + dy))

        self.update()

    def mouseReleaseEvent(self, event):
        self.drag_mode = None
        self.active_handle = None
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        step = 1 if delta > 0 else -1

        if self.selected_elem == "art":
            cur = self.app.slider_scale.value()
            self.app.slider_scale.setValue(max(20, min(300, cur + (step * 5))))
        else:
            w_map = {
                "name": self.app.editor_name,
                "cost": self.app.editor_cost,
                "type": self.app.editor_type,
                "rules": self.app.editor_rules,
                "pt": self.app.editor_pt,
            }
            widget = w_map.get(self.selected_elem)
            if widget:
                cur = widget.slider_size.value()
                widget.slider_size.setValue(max(10, min(180, cur + (step * 2))))

        self.update()
        event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(30, 30, 30))

        if not self.pixmap:
            painter.setPen(QColor(180, 180, 180))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No Preview")
            return

        scale, off_x, off_y = self.get_scale_and_offsets()
        target_rect = QRectF(off_x, off_y, CARD_WIDTH * scale, CARD_HEIGHT * scale)
        painter.drawPixmap(
            target_rect.toRect(),
            self.pixmap.scaled(
                target_rect.size().toSize(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ),
        )

        elements = ["name", "cost", "type", "rules"]
        if self.has_pt:
            elements.append("pt")
        if self.selected_elem == "art":
            elements.append("art")

        for elem in elements:
            rect = self.get_element_rect(elem)
            if not rect:
                continue
            l, t, r, b = rect
            sx1, sy1 = self.card_to_widget(l, t)
            sx2, sy2 = self.card_to_widget(r, b)
            box_rect = QRectF(sx1, sy1, sx2 - sx1, sy2 - sy1)

            if elem == self.selected_elem:
                painter.setPen(QPen(QColor(0, 220, 255), 2, Qt.PenStyle.SolidLine))
                painter.drawRect(box_rect)

                # Draw corner resize handles
                painter.setPen(QPen(QColor(0, 0, 0), 1))
                painter.setBrush(QColor(255, 255, 255))
                for hx, hy in [(sx1, sy1), (sx2, sy1), (sx1, sy2), (sx2, sy2)]:
                    painter.drawRect(QRectF(hx - 4, hy - 4, 8, 8))

                # Label tag
                tag_text = elem.upper()
                painter.fillRect(QRectF(sx1, max(0, sy1 - 18), 44, 16), QColor(0, 220, 255, 200))
                painter.setPen(QColor(0, 0, 0))
                font = QFont("Arial", 8, QFont.Weight.Bold)
                painter.setFont(font)
                painter.drawText(QRectF(sx1, max(0, sy1 - 18), 44, 16), Qt.AlignmentFlag.AlignCenter, tag_text)
            else:
                painter.setPen(QPen(QColor(120, 160, 255, 90), 1, Qt.PenStyle.DashLine))
                painter.drawRect(box_rect)


# ================= Crop Canvas =================
class CropCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pil_image = None
        self.qpixmap = None
        self.mode = "rect"
        self.rect_start = None
        self.rect_current = None
        self.drag_start_pos = None
        self.is_dragging = False
        self.poly_points = []
        self.current_mouse_pos = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(500, 500)

    def load_image(self, pil_img: Image.Image):
        self.pil_image = pil_img.convert("RGB")
        self.rect_start = None
        self.rect_current = None
        self.drag_start_pos = None
        self.is_dragging = False
        self.poly_points = []
        self.current_mouse_pos = None

        w, h = self.pil_image.size
        data = self.pil_image.tobytes("raw", "RGB")
        qimg = QImage(data, w, h, 3 * w, QImage.Format.Format_RGB888)
        self.qpixmap = QPixmap.fromImage(qimg)
        self.update()

    def get_scale_and_offsets(self):
        if not self.pil_image or self.width() == 0 or self.height() == 0:
            return 1.0, 0, 0
        img_w, img_h = self.pil_image.size
        scale = min(self.width() / img_w, self.height() / img_h)
        off_x = (self.width() - (img_w * scale)) / 2
        off_y = (self.height() - (img_h * scale)) / 2
        return scale, off_x, off_y

    def widget_to_img_coords(self, pt: QPointF):
        scale, off_x, off_y = self.get_scale_and_offsets()
        x = (pt.x() - off_x) / scale
        y = (pt.y() - off_y) / scale
        img_w, img_h = self.pil_image.size
        return max(0, min(img_w, x)), max(0, min(img_h, y))

    def mousePressEvent(self, event):
        if not self.pil_image:
            return
        pos = event.position()
        if event.button() == Qt.MouseButton.LeftButton:
            if self.mode == "rect":
                self.drag_start_pos = pos
            elif self.mode == "poly":
                img_x, img_y = self.widget_to_img_coords(pos)
                self.poly_points.append((img_x, img_y))
                self.update()

    def mouseMoveEvent(self, event):
        if not self.pil_image:
            return
        self.current_mouse_pos = event.position()
        if self.mode == "rect" and self.drag_start_pos:
            if not self.is_dragging:
                delta = (self.current_mouse_pos - self.drag_start_pos).manhattanLength()
                if delta > 4:
                    self.is_dragging = True
                    self.rect_start = self.drag_start_pos
            if self.is_dragging:
                self.rect_current = self.current_mouse_pos
                self.update()
        elif self.mode == "poly" and self.poly_points:
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start_pos = None
            self.is_dragging = False

    def mouseDoubleClickEvent(self, event):
        self.window().finish_crop()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(40, 40, 40))

        if not self.qpixmap:
            painter.setPen(QColor(180, 180, 180))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No Image Loaded")
            return

        scale, off_x, off_y = self.get_scale_and_offsets()
        target_rect = QRectF(off_x, off_y, self.pil_image.width * scale, self.pil_image.height * scale)
        painter.drawPixmap(
            target_rect.toRect(),
            self.qpixmap.scaled(
                target_rect.size().toSize(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ),
        )

        if self.mode == "rect" and self.rect_start and self.rect_current:
            r = QRectF(self.rect_start, self.rect_current).normalized()
            painter.setPen(QPen(QColor(0, 220, 255), 2, Qt.PenStyle.DashLine))
            painter.drawRect(r)

        if self.mode == "poly" and self.poly_points:
            painter.setPen(QPen(QColor(255, 80, 80), 2))
            screen_pts = []
            for px, py in self.poly_points:
                sx = (px * scale) + off_x
                sy = (py * scale) + off_y
                screen_pts.append(QPointF(sx, sy))
                painter.fillRect(QRectF(sx - 4, sy - 4, 8, 8).toRect(), QColor(255, 255, 0))

            for i in range(len(screen_pts) - 1):
                painter.drawLine(screen_pts[i], screen_pts[i + 1])

            if self.current_mouse_pos:
                painter.setPen(QPen(QColor(255, 180, 180), 1, Qt.PenStyle.DotLine))
                painter.drawLine(screen_pts[-1], self.current_mouse_pos)

    def get_cropped_image(self) -> tuple[Image.Image, dict]:
        if not self.pil_image:
            return None, {}
        img_w, img_h = self.pil_image.size

        if self.mode == "rect" and self.rect_start and self.rect_current:
            p1 = self.widget_to_img_coords(self.rect_start)
            p2 = self.widget_to_img_coords(self.rect_current)
            left = max(0, min(p1[0], p2[0]))
            top = max(0, min(p1[1], p2[1]))
            right = min(img_w, max(p1[0], p2[0]))
            bottom = min(img_h, max(p1[1], p2[1]))
            if (right - left) > 5 and (bottom - top) > 5:
                return self.pil_image.crop((left, top, right, bottom)), {"mode": "rect", "coords": [left, top, right, bottom]}

        elif self.mode == "poly" and len(self.poly_points) >= 3:
            mask = Image.new("L", (img_w, img_h), 0)
            draw = ImageDraw.Draw(mask)
            draw.polygon(self.poly_points, fill=255)
            white_bg = Image.new("RGB", (img_w, img_h), (255, 255, 255))
            masked = Image.composite(self.pil_image, white_bg, mask)
            bbox = mask.getbbox()
            return (masked.crop(bbox) if bbox else masked), {"mode": "poly", "coords": self.poly_points}

        return self.pil_image.copy(), {"mode": "none"}


class SearchLineEdit(QLineEdit):
    def focusInEvent(self, event):
        super().focusInEvent(event)
        QTimer.singleShot(0, self.selectAll)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.clearFocus()
            return
        super().keyPressEvent(event)


# ================= Main Studio Application =================
class CardEditorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MTG Playtest Card Studio")
        self.resize(1420, 940)

        os.makedirs(IMAGES_DIR, exist_ok=True)
        os.makedirs(CROPPED_DIR, exist_ok=True)
        os.makedirs(PLAYTEST_CARDS_DIR, exist_ok=True)

        self.df = self.load_dataset()
        self.current_idx = 0
        self.raw_source_image = None
        self.cropped_art_image = None
        self.crop_metadata = {}

        self.render_timer = QTimer()
        self.render_timer.setSingleShot(True)
        self.render_timer.setInterval(30)
        self.render_timer.timeout.connect(self.update_live_preview)

        self.setup_ui()
        QApplication.instance().installEventFilter(self)
        resume_idx = self.find_first_pending_idx()
        self.load_card(resume_idx)

    def find_first_pending_idx(self) -> int:
        for i in range(len(self.df)):
            if str(self.df.iloc[i].get("processed_status", "")).strip().lower() != "done":
                return i
        return 0

    def load_dataset(self) -> pd.DataFrame:
        csv_file = OUTPUT_CSV if os.path.exists(OUTPUT_CSV) else INPUT_CSV
        if not os.path.exists(csv_file):
            QMessageBox.critical(self, "Error", f"Could not find '{INPUT_CSV}'.")
            sys.exit(1)

        df = pd.read_csv(csv_file, dtype=str).fillna("")
        df["Typeline"] = df["Typeline"].apply(reorder_summon_typeline)

        if "processed_status" not in df.columns:
            df["processed_status"] = "Pending"

        is_done = df["processed_status"].str.strip().str.lower() == "done"
        num_pending = (~is_done).sum()

        box_size_defaults = {
            "name": "78",
            "cost": "78",
            "type": "42",
            "rules": "28",
            "pt": "68",
        }

        for prefix, def_sz in box_size_defaults.items():
            font_col = f"{prefix}_font"
            if font_col not in df.columns:
                df[font_col] = [random.choice(["Arial", "Times New Roman"]) for _ in range(len(df))]
            else:
                df[font_col] = df[font_col].apply(
                    lambda x: x if x in ("Arial", "Times New Roman") else random.choice(["Arial", "Times New Roman"])
                )

            # Keep randomized bolding for pending cards
            bold_col = f"{prefix}_bold"
            if bold_col not in df.columns:
                df[bold_col] = "True"
            if num_pending > 0:
                df.loc[~is_done, bold_col] = [str(random.choice([True, False])) for _ in range(num_pending)]

            size_col = f"{prefix}_size"
            if size_col not in df.columns:
                df[size_col] = def_sz
            else:
                df.loc[~is_done, size_col] = def_sz

        # Learned baseline values for new cards
        meta_defaults = {
            "brightness": "1.0",
            "contrast": "2.2",
            "rotation": "0",
            "scale": "1.25",
            "x_offset": "0",
            "y_offset": "-60",
            "invert_art": "False",
            "crop_data": "",
            "cropped_image_path": "",
        }
        for col, val in meta_defaults.items():
            if col not in df.columns:
                df[col] = val

        return df

    def setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        root_layout = QVBoxLayout(main_widget)

        top_bar = QHBoxLayout()
        self.lbl_status = QLabel("Card 1 / 1")
        self.lbl_status.setStyleSheet("font-size: 15px; font-weight: bold;")
        top_bar.addWidget(self.lbl_status)

        top_bar.addSpacing(15)
        btn_prev = QPushButton("◀ Previous")
        btn_prev.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_prev.clicked.connect(self.prev_card)
        top_bar.addWidget(btn_prev)

        self.spin_jump = QSpinBox()
        self.spin_jump.setMinimum(1)
        self.spin_jump.setMaximum(max(1, len(self.df)))
        self.spin_jump.valueChanged.connect(
            lambda val: self.load_card(val - 1) if (val - 1) != self.current_idx else None
        )
        top_bar.addWidget(QLabel("Jump to:"))
        top_bar.addWidget(self.spin_jump)

        btn_skip = QPushButton("Skip ▶")
        btn_skip.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_skip.clicked.connect(self.next_card)
        top_bar.addWidget(btn_skip)

        top_bar.addSpacing(15)
        self.chk_skip_done = QCheckBox("Skip Completed Cards")
        self.chk_skip_done.setChecked(True)
        self.chk_skip_done.setStyleSheet("font-weight: bold; color: #0d6efd;")
        top_bar.addWidget(self.chk_skip_done)

        top_bar.addSpacing(15)
        top_bar.addWidget(QLabel("Search Card:"))
        self.search_card_input = SearchLineEdit()
        self.search_card_input.setPlaceholderText("Type card name... (Ctrl+F)")
        self.search_card_input.setClearButtonEnabled(True)
        self.search_card_input.setFixedWidth(220)
        self.search_card_input.setStyleSheet("padding: 3px 6px; font-size: 13px;")

        card_names = [str(n).strip() for n in self.df["Name of the card"] if str(n).strip()]
        self.card_completer = QCompleter(card_names, self)
        self.card_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.card_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.card_completer.setMaxVisibleItems(15)
        self.search_card_input.setCompleter(self.card_completer)

        self.search_card_input.returnPressed.connect(lambda: self.go_to_card_by_name())
        self.card_completer.activated.connect(self.go_to_card_by_name)

        btn_find = QPushButton("Go")
        btn_find.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_find.clicked.connect(lambda: self.go_to_card_by_name())

        top_bar.addWidget(self.search_card_input)
        top_bar.addWidget(btn_find)

        self.search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.search_shortcut.activated.connect(self.focus_search_input)

        top_bar.addStretch()
        root_layout.addLayout(top_bar)

        self.stack = QStackedWidget()
        root_layout.addWidget(self.stack)

        # Page 0: Missing Image
        self.page_missing = QWidget()
        m_layout = QVBoxLayout(self.page_missing)
        self.lbl_missing_title = QLabel("No image found")
        self.lbl_missing_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_missing_title.setStyleSheet("font-size: 18px; color: #888;")
        btn_browse = QPushButton("📁 Browse / Upload Image for this Card")
        btn_browse.setStyleSheet("font-size: 16px; padding: 12px;")
        btn_browse.clicked.connect(self.browse_image)
        m_layout.addStretch()
        m_layout.addWidget(self.lbl_missing_title)
        m_layout.addWidget(btn_browse, alignment=Qt.AlignmentFlag.AlignCenter)
        m_layout.addStretch()
        self.stack.addWidget(self.page_missing)

        # Page 1: Crop Tool
        self.page_crop = QWidget()
        crop_layout = QHBoxLayout(self.page_crop)
        self.crop_canvas = CropCanvas()
        crop_layout.addWidget(self.crop_canvas, stretch=4)

        crop_panel = QFrame()
        crop_panel.setFrameShape(QFrame.Shape.StyledPanel)
        c_p_layout = QVBoxLayout(crop_panel)

        c_p_layout.addWidget(
            QLabel("<b>Cropping</b><br>• Polygon: click vertices, double-click to finish.<br>• Rectangle: drag box, double-click or Enter to finish.")
        )

        self.btn_mode_rect = QPushButton("🔲 Rectangle Crop Mode")
        self.btn_mode_rect.setCheckable(True)
        self.btn_mode_rect.setChecked(True)
        self.btn_mode_rect.clicked.connect(lambda: self.set_crop_mode("rect"))
        c_p_layout.addWidget(self.btn_mode_rect)

        self.btn_mode_poly = QPushButton("📐 Polygon Crop Mode")
        self.btn_mode_poly.setCheckable(True)
        self.btn_mode_poly.clicked.connect(lambda: self.set_crop_mode("poly"))
        c_p_layout.addWidget(self.btn_mode_poly)

        btn_clear_crop = QPushButton("Clear Selection")
        btn_clear_crop.clicked.connect(self.reset_crop_canvas)
        c_p_layout.addWidget(btn_clear_crop)

        c_p_layout.addSpacing(20)
        btn_raw = QPushButton("✔ Accept As Is (No Crop)")
        btn_raw.clicked.connect(self.accept_no_crop)
        c_p_layout.addWidget(btn_raw)

        btn_crop_done = QPushButton("Crop & Proceed ➔")
        btn_crop_done.setStyleSheet("background: #0d6efd; color: white; font-weight: bold; padding: 10px;")
        btn_crop_done.clicked.connect(self.finish_crop)
        c_p_layout.addWidget(btn_crop_done)
        c_p_layout.addStretch()
        crop_layout.addWidget(crop_panel, stretch=1)
        self.stack.addWidget(self.page_crop)

        # Page 2: Card Construction (WYSIWYG Interactive)
        self.page_construct = QWidget()
        construct_layout = QHBoxLayout(self.page_construct)

        self.card_canvas = CardCanvas(self)
        construct_layout.addWidget(self.card_canvas, stretch=3)

        editor_panel = QFrame()
        editor_panel.setFrameShape(QFrame.Shape.StyledPanel)
        editor_layout = QVBoxLayout(editor_panel)

        self.tabs = QTabWidget()

        # Art Tab
        tab_art = QWidget()
        art_layout = QFormLayout(tab_art)
        self.slider_bright = self._make_slider(20, 250, 100)
        art_layout.addRow("Brightness:", self.slider_bright)
        self.slider_contrast = self._make_slider(50, 400, 220)
        art_layout.addRow("Contrast:", self.slider_contrast)
        self.slider_rot = self._make_slider(-180, 180, 0)
        art_layout.addRow("Rotation (°):", self.slider_rot)
        self.slider_scale = self._make_slider(20, 300, 125)
        art_layout.addRow("Scale (% - Scroll):", self.slider_scale)
        self.slider_x = self._make_slider(-350, 350, 0)
        art_layout.addRow("X Offset (Drag Art):", self.slider_x)
        self.slider_y = self._make_slider(-350, 350, -60)
        art_layout.addRow("Y Offset (Drag Art):", self.slider_y)

        self.chk_invert = QCheckBox("Invert Polarity (Negative - 'I')")
        self.chk_invert.stateChanged.connect(self.on_adjustment_change)
        art_layout.addRow("", self.chk_invert)

        self.tabs.addTab(tab_art, "🎨 Art")

        # Text Box Tabs
        cb = self.on_adjustment_change
        self.editor_name = TextBoxSettingsWidget(78, 45, 25, 580, 115, cb, max_size=180)
        self.tabs.addTab(self.editor_name, "Name")

        self.editor_cost = TextBoxSettingsWidget(78, 590, 25, 705, 115, cb, max_size=180)
        self.tabs.addTab(self.editor_cost, "Cost")

        self.editor_type = TextBoxSettingsWidget(42, 45, 135, 350, 195, cb, max_size=140)
        self.tabs.addTab(self.editor_type, "Type")

        self.editor_rules = TextBoxSettingsWidget(28, 45, 760, 705, 995, cb, max_size=70)
        self.tabs.addTab(self.editor_rules, "Rules")

        self.editor_pt = TextBoxSettingsWidget(68, 560, 920, 705, 995, cb, max_size=160)
        self.tabs.addTab(self.editor_pt, "P/T")

        self.tabs.currentChanged.connect(self.on_tab_changed)
        editor_layout.addWidget(self.tabs)

        # On-Screen Speedrun Hotkey Reference Card
        cheat_sheet = QLabel(
            "<b>⚡ Speedrun Shortcuts:</b><br>"
            "• <b>Space</b> / <b>Ctrl+Enter</b>: Save & Next Card<br>"
            "• <b>Tab</b> / <b>Shift+Tab</b>: Cycle Selection (Art/Boxes)<br>"
            "• <b>Arrows</b> (<b>Shift+Arrows</b>): Nudge 1px (10px)<br>"
            "• <b>Scroll Wheel</b>: Scale Art or Change Font Size<br>"
            "• <b>1 / 2</b>: Set Font to Arial / Times New Roman<br>"
            "• <b>I</b>: Invert Art Polarity<br>"
            "• <b>Ctrl+F</b>: Search Card by Name"
        )
        cheat_sheet.setStyleSheet(
            "background: #2b2b2b; color: #ddd; padding: 10px; border-radius: 6px; font-size: 13px; line-height: 140%;"
        )
        editor_layout.addWidget(cheat_sheet)

        btn_back_crop = QPushButton("◀ Back to Recrop")
        btn_back_crop.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_back_crop.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        editor_layout.addWidget(btn_back_crop)

        self.btn_save_next = QPushButton("💾 Save & Next (Space) ▶")
        self.btn_save_next.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_save_next.setStyleSheet(
            "background-color: #198754; color: white; font-size: 16px; font-weight: bold; padding: 12px;"
        )
        self.btn_save_next.clicked.connect(self.save_and_next)
        editor_layout.addWidget(self.btn_save_next)

        construct_layout.addWidget(editor_panel, stretch=2)
        self.stack.addWidget(self.page_construct)

    def _make_slider(self, min_v, max_v, def_v):
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(min_v, max_v)
        s.setValue(def_v)
        s.valueChanged.connect(self.on_adjustment_change)
        return s

    def set_crop_mode(self, mode: str):
        self.crop_canvas.mode = mode
        self.btn_mode_rect.setChecked(mode == "rect")
        self.btn_mode_poly.setChecked(mode == "poly")
        self.crop_canvas.update()

    def reset_crop_canvas(self):
        self.crop_canvas.rect_start = None
        self.crop_canvas.rect_current = None
        self.crop_canvas.drag_start_pos = None
        self.crop_canvas.is_dragging = False
        self.crop_canvas.poly_points = []
        self.crop_canvas.update()

    def on_tab_changed(self, idx: int):
        tab_elem_map = {0: "art", 1: "name", 2: "cost", 3: "type", 4: "rules", 5: "pt"}
        self.card_canvas.selected_elem = tab_elem_map.get(idx, "name")
        self.card_canvas.update()

    def sync_tab_from_canvas(self, elem: str):
        elem_tab_map = {"art": 0, "name": 1, "cost": 2, "type": 3, "rules": 4, "pt": 5}
        idx = elem_tab_map.get(elem, 1)
        self.tabs.blockSignals(True)
        self.tabs.setCurrentIndex(idx)
        self.tabs.blockSignals(False)

    def set_element_coords(self, elem: str, left: int, top: int, right: int, bottom: int):
        w_map = {
            "name": self.editor_name,
            "cost": self.editor_cost,
            "type": self.editor_type,
            "rules": self.editor_rules,
            "pt": self.editor_pt,
        }
        widget = w_map.get(elem)
        if widget:
            for slider, val in [
                (widget.slider_left, left),
                (widget.slider_top, top),
                (widget.slider_right, right),
                (widget.slider_bottom, bottom),
            ]:
                slider.blockSignals(True)
                slider.setValue(val)
                slider.blockSignals(False)
            self.on_adjustment_change()

    def load_card(self, idx: int):
        if idx < 0 or idx >= len(self.df):
            return
        self.current_idx = idx
        row = self.df.iloc[idx].to_dict()
        name = row.get("Name of the card", "")
        status = row.get("processed_status", "Pending")
        is_done = str(status).strip().lower() == "done"
        has_pt = bool(str(row.get("Power / Toughness", "")).strip())

        self.card_canvas.has_pt = has_pt
        self.tabs.setTabEnabled(5, has_pt)

        pending_count = (self.df["processed_status"].str.strip().str.lower() != "done").sum()
        self.lbl_status.setText(
            f"Card {idx + 1} / {len(self.df)}: <b>{name}</b> ({status}) — <i>{pending_count} Remaining</i>"
        )
        self.spin_jump.blockSignals(True)
        self.spin_jump.setValue(idx + 1)
        self.spin_jump.blockSignals(False)
        self.chk_invert.blockSignals(True)
        self.chk_invert.setChecked(str(row.get("invert_art", "False")).lower() == "true")
        self.chk_invert.blockSignals(False)

        if hasattr(self, "search_card_input") and not self.search_card_input.hasFocus():
            self.search_card_input.blockSignals(True)
            self.search_card_input.setText(name)
            self.search_card_input.blockSignals(False)

        boxes = [
            ("name", self.editor_name, 78),
            ("cost", self.editor_cost, 78),
            ("type", self.editor_type, 42),
            ("rules", self.editor_rules, 28),
            ("pt", self.editor_pt, 68),
        ]

        # Use smart layout calculation for pending cards
        smart_layout = compute_smart_card_layout(row)

        for prefix, widget, def_sz in boxes:
            font_name = row.get(f"{prefix}_font", "Arial")
            bold = str(row.get(f"{prefix}_bold", "True")).lower() == "true"
            size = int(float(row.get(f"{prefix}_size", def_sz)))

            if is_done and f"{prefix}_left" in row and row[f"{prefix}_left"] != "":
                left = int(float(row[f"{prefix}_left"]))
                top = int(float(row[f"{prefix}_top"]))
                right = int(float(row[f"{prefix}_right"]))
                bottom = int(float(row[f"{prefix}_bottom"]))
            else:
                left, top, right, bottom, smart_size = smart_layout[prefix]
                size = smart_size

            widget.set_settings(
                font_name=font_name,
                bold=bold,
                size=size,
                left=left,
                top=top,
                right=right,
                bottom=bottom,
            )

        # Baseline art values for pending cards
        def_scale = 1.0 if is_done else 1.25
        def_y_off = 0 if is_done else -60

        self.slider_bright.setValue(int(float(row.get("brightness", 1.0)) * 100))
        self.slider_contrast.setValue(int(float(row.get("contrast", 2.2)) * 100))
        self.slider_rot.setValue(int(float(row.get("rotation", 0))))
        self.slider_scale.setValue(int(float(row.get("scale", def_scale)) * 100))
        self.slider_x.setValue(int(float(row.get("x_offset", 0))))
        self.slider_y.setValue(int(float(row.get("y_offset", def_y_off))))

        cropped_path = row.get("cropped_image_path", "")
        if cropped_path and os.path.exists(cropped_path):
            self.cropped_art_image = Image.open(cropped_path).convert("RGB")
            src = find_source_image(name)
            if src:
                self.raw_source_image = Image.open(src)
                self.crop_canvas.load_image(self.raw_source_image)
            self.stack.setCurrentIndex(2)
            self.update_live_preview()
            return

        source_path = find_source_image(name)
        if not source_path:
            self.lbl_missing_title.setText(f"No image found for '<b>{name}</b>' in ./images/")
            self.stack.setCurrentIndex(0)
            return

        self.raw_source_image = Image.open(source_path)
        self.crop_canvas.load_image(self.raw_source_image)
        self.stack.setCurrentIndex(1)

    def browse_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Image", IMAGES_DIR, "Images (*.png *.jpg *.jpeg *.webp)")
        if path:
            name = self.df.iloc[self.current_idx].get("Name of the card", "")
            safe = get_safe_filename(name)
            ext = os.path.splitext(path)[1]
            dest = os.path.join(IMAGES_DIR, f"{safe}{ext}")
            raw = Image.open(path)
            raw.save(dest)
            self.raw_source_image = raw
            self.crop_canvas.load_image(raw)
            self.stack.setCurrentIndex(1)

    def accept_no_crop(self):
        if not self.raw_source_image:
            return
        self.cropped_art_image = self.raw_source_image.copy()
        self.crop_metadata = {"mode": "none"}
        self.save_cropped_raw_art()
        self.stack.setCurrentIndex(2)
        self.update_live_preview()

    def finish_crop(self):
        cropped, meta = self.crop_canvas.get_cropped_image()
        if cropped:
            self.cropped_art_image = cropped
            self.crop_metadata = meta
            self.save_cropped_raw_art()
            self.stack.setCurrentIndex(2)
            self.update_live_preview()

    def save_cropped_raw_art(self):
        name = self.df.iloc[self.current_idx].get("Name of the card", "")
        safe = get_safe_filename(name)
        crop_path = os.path.join(CROPPED_DIR, f"{safe}_cropped.png")
        self.cropped_art_image.save(crop_path, "PNG")
        self.df.at[self.current_idx, "cropped_image_path"] = crop_path
        self.df.at[self.current_idx, "crop_data"] = json.dumps(self.crop_metadata)

    def on_adjustment_change(self):
        self.render_timer.start()

    def update_live_preview(self):
        if not self.cropped_art_image:
            return

        row = self.df.iloc[self.current_idx].to_dict()
        full_card = render_full_card(
            row=row,
            art_image=self.cropped_art_image,
            cfg_name=self.editor_name.get_settings(),
            cfg_cost=self.editor_cost.get_settings(),
            cfg_type=self.editor_type.get_settings(),
            cfg_rules=self.editor_rules.get_settings(),
            cfg_pt=self.editor_pt.get_settings(),
            brightness=self.slider_bright.value() / 100.0,
            contrast=self.slider_contrast.value() / 100.0,
            rotation=float(self.slider_rot.value()),
            scale=self.slider_scale.value() / 100.0,
            x_offset=self.slider_x.value(),
            y_offset=self.slider_y.value(),
            invert_art=self.chk_invert.isChecked(),
        )

        data = full_card.tobytes("raw", "RGB")
        qimg = QImage(data, CARD_WIDTH, CARD_HEIGHT, 3 * CARD_WIDTH, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(qimg)
        self.card_canvas.set_pixmap(pix)

    def save_and_next(self):
        row = self.df.iloc[self.current_idx].to_dict()
        name = row.get("Name of the card", "")
        safe = get_safe_filename(name)

        cfg_name = self.editor_name.get_settings()
        cfg_cost = self.editor_cost.get_settings()
        cfg_type = self.editor_type.get_settings()
        cfg_rules = self.editor_rules.get_settings()
        cfg_pt = self.editor_pt.get_settings()

        final_card = render_full_card(
            row=row,
            art_image=self.cropped_art_image,
            cfg_name=cfg_name,
            cfg_cost=cfg_cost,
            cfg_type=cfg_type,
            cfg_rules=cfg_rules,
            cfg_pt=cfg_pt,
            brightness=self.slider_bright.value() / 100.0,
            contrast=self.slider_contrast.value() / 100.0,
            rotation=float(self.slider_rot.value()),
            scale=self.slider_scale.value() / 100.0,
            x_offset=self.slider_x.value(),
            y_offset=self.slider_y.value(),
            invert_art=self.chk_invert.isChecked(),
        )
        out_png = os.path.join(PLAYTEST_CARDS_DIR, f"{safe}.png")
        final_card.save(out_png, "PNG")

        boxes = [
            ("name", cfg_name),
            ("cost", cfg_cost),
            ("type", cfg_type),
            ("rules", cfg_rules),
            ("pt", cfg_pt),
        ]
        for prefix, cfg in boxes:
            for k, v in cfg.items():
                self.df.at[self.current_idx, f"{prefix}_{k}"] = str(v)

        self.df.at[self.current_idx, "brightness"] = str(self.slider_bright.value() / 100.0)
        self.df.at[self.current_idx, "contrast"] = str(self.slider_contrast.value() / 100.0)
        self.df.at[self.current_idx, "rotation"] = str(self.slider_rot.value())
        self.df.at[self.current_idx, "scale"] = str(self.slider_scale.value() / 100.0)
        self.df.at[self.current_idx, "x_offset"] = str(self.slider_x.value())
        self.df.at[self.current_idx, "y_offset"] = str(self.slider_y.value())
        self.df.at[self.current_idx, "invert_art"] = str(self.chk_invert.isChecked())
        self.df.at[self.current_idx, "processed_status"] = "Done"

        self.df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
        self.next_card()

    def next_card(self):
        if self.chk_skip_done.isChecked():
            next_idx = None
            for i in range(self.current_idx + 1, len(self.df)):
                if str(self.df.iloc[i].get("processed_status", "")).strip().lower() != "done":
                    next_idx = i
                    break

            if next_idx is not None:
                self.load_card(next_idx)
                return

            earlier_idx = None
            for i in range(0, self.current_idx):
                if str(self.df.iloc[i].get("processed_status", "")).strip().lower() != "done":
                    earlier_idx = i
                    break

            if earlier_idx is not None:
                QMessageBox.information(self, "Notice", "No unfinished cards ahead. Looping back to earlier unfinished cards.")
                self.load_card(earlier_idx)
                return

            QMessageBox.information(self, "Complete", "All cards in the cube have been marked Done!")
        else:
            if self.current_idx < len(self.df) - 1:
                self.load_card(self.current_idx + 1)
            else:
                QMessageBox.information(self, "Complete", "You have reached the end of the cube list!")

    def prev_card(self):
        if self.chk_skip_done.isChecked():
            prev_idx = None
            for i in range(self.current_idx - 1, -1, -1):
                if str(self.df.iloc[i].get("processed_status", "")).strip().lower() != "done":
                    prev_idx = i
                    break
            if prev_idx is not None:
                self.load_card(prev_idx)
                return

            if self.current_idx > 0:
                self.load_card(self.current_idx - 1)
        else:
            if self.current_idx > 0:
                self.load_card(self.current_idx - 1)

    def focus_search_input(self):
        self.search_card_input.setFocus()
        self.search_card_input.selectAll()

    def find_card_by_name(self, query: str) -> int | None:
        query = query.strip().lower()
        if not query:
            return None

        names = self.df["Name of the card"].astype(str).str.strip().tolist()

        # 1. Exact match (case-insensitive)
        for idx, name in enumerate(names):
            if name.lower() == query:
                return idx

        # 2. Split face match (e.g. 'Fire // Ice' -> 'Fire' or 'Ice')
        for idx, name in enumerate(names):
            faces = [f.strip().lower() for f in name.split("//")]
            if query in faces:
                return idx

        # 3. Starts-with match
        for idx, name in enumerate(names):
            if name.lower().startswith(query):
                return idx

        # 4. Substring / contains match
        for idx, name in enumerate(names):
            if query in name.lower():
                return idx

        return None

    def go_to_card_by_name(self, card_name: str | None = None):
        if not card_name:
            card_name = self.search_card_input.text().strip()
        if not card_name:
            return

        idx = self.find_card_by_name(card_name)
        if idx is not None:
            self.load_card(idx)
            self.search_card_input.blockSignals(True)
            self.search_card_input.setText(self.df.iloc[idx].get("Name of the card", ""))
            self.search_card_input.selectAll()
            self.search_card_input.blockSignals(False)
        else:
            QMessageBox.information(
                self,
                "Card Not Found",
                f"Could not find any card matching:\n'{card_name}'",
            )

    # Global Key Handler (Speedrun Hotkeys)
    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.KeyPress:
            # Let text input controls process typing, spaces, arrows, and shortcuts directly
            if isinstance(source, QLineEdit):
                return super().eventFilter(source, event)

            if self.stack.currentIndex() == 2:
                # 1. Space or Ctrl+Enter -> Save & Next
                if event.key() == Qt.Key.Key_Space or (
                    event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                    and (event.modifiers() & Qt.KeyboardModifier.ControlModifier)
                ):
                    self.save_and_next()
                    return True

                # 2. Tab / Shift+Tab -> Cycle elements
                if event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
                    backwards = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier) or (event.key() == Qt.Key.Key_Backtab)
                    elems = ["art", "name", "cost", "type", "rules"]
                    if self.card_canvas.has_pt:
                        elems.append("pt")
                    cur = self.card_canvas.selected_elem
                    cur_idx = elems.index(cur) if cur in elems else 0
                    nxt_idx = (cur_idx - 1) % len(elems) if backwards else (cur_idx + 1) % len(elems)
                    next_elem = elems[nxt_idx]
                    self.card_canvas.selected_elem = next_elem
                    self.sync_tab_from_canvas(next_elem)
                    self.card_canvas.update()
                    return True

                # 3. Arrow Keys -> Nudge
                if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
                    step = 10 if (event.modifiers() & Qt.KeyboardModifier.ShiftModifier) else 1
                    dx = step if event.key() == Qt.Key.Key_Right else (-step if event.key() == Qt.Key.Key_Left else 0)
                    dy = step if event.key() == Qt.Key.Key_Down else (-step if event.key() == Qt.Key.Key_Up else 0)

                    elem = self.card_canvas.selected_elem
                    if elem == "art":
                        self.slider_x.setValue(self.slider_x.value() + dx)
                        self.slider_y.setValue(self.slider_y.value() + dy)
                    else:
                        rect = self.card_canvas.get_element_rect(elem)
                        if rect:
                            l, t, r, b = rect
                            self.set_element_coords(elem, l + dx, t + dy, r + dx, b + dy)
                    self.card_canvas.update()
                    return True

                # 4. Invert Art ('I')
                if event.key() == Qt.Key.Key_I:
                    self.chk_invert.setChecked(not self.chk_invert.isChecked())
                    return True

                # 5. Font Toggle (1: Arial, 2: Times New Roman)
                if event.key() in (Qt.Key.Key_1, Qt.Key.Key_2):
                    font_target = "Arial" if event.key() == Qt.Key.Key_1 else "Times New Roman"
                    w_map = {
                        "name": self.editor_name,
                        "cost": self.editor_cost,
                        "type": self.editor_type,
                        "rules": self.editor_rules,
                        "pt": self.editor_pt,
                    }
                    widget = w_map.get(self.card_canvas.selected_elem)
                    if widget:
                        widget.combo_font.setCurrentText(font_target)
                    return True

        return super().eventFilter(source, event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CardEditorApp()
    window.show()
    sys.exit(app.exec())