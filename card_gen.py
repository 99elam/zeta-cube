import hashlib
import json
import os
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

# ================= Configuration =================
CSV_PATH = "modovintage_cube_edited.csv"
FALLBACK_CSV = "modovintage_cube.csv"
IMAGES_DIR = "./images"
CROPPED_DIR = "./images_cropped"
OUTPUT_DIR = "./playtest_cards"

CARD_WIDTH = 750
CARD_HEIGHT = 1050

# Pure white background for printing on natural/cream cardstock
CREAM_PAPER = (255, 255, 255)
INK_BLACK = (0, 0, 0)

# CREAM_PAPER = (248, 245, 234)
# INK_BLACK = (11, 24, 34)

DUMMY_IMG = Image.new("RGB", (1, 1))
DUMMY_DRAW = ImageDraw.Draw(DUMMY_IMG)

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


def add_photocopy_grain(card_img: Image.Image, seed_key: str = "card") -> Image.Image:
    """Analog toner specks and scanner fibers without gray paper background noise."""
    seed = int(hashlib.md5(seed_key.encode("utf-8")).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    w, h = card_img.size

    result = card_img.copy()
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

    num_allover = rng.integers(250, 400)
    for _ in range(num_allover):
        stamp_grain(rng.integers(10, w - 10), rng.integers(10, h - 10), int(rng.integers(30, 130)))

    num_clusters = rng.integers(8, 13)
    for _ in range(num_clusters):
        cx, cy = rng.integers(30, w - 30), rng.integers(30, h - 30)
        spread_x, spread_y = rng.uniform(35, 75), rng.uniform(35, 75)
        for _ in range(rng.integers(25, 55)):
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
            if art_image.mode in ("RGBA", "LA") or (art_image.mode == "P" and "transparency" in art_image.info):
                bg = Image.new("RGB", art_image.size, (255, 255, 255))
                bg.paste(art_image, mask=art_image.split()[-1])
                art = bg
            else:
                art = art_image.convert("RGB")

            if brightness != 1.0:
                art = ImageEnhance.Brightness(art).enhance(brightness)
            if contrast != 1.0:
                art = ImageEnhance.Contrast(art).enhance(contrast)

            gray = art.convert("L")
            if invert_art:
                gray = ImageOps.invert(gray)

            gray = ImageOps.autocontrast(gray, cutoff=2)
            sharpened = gray.filter(ImageFilter.SHARPEN)

            if rotation != 0:
                sharpened = sharpened.rotate(
                    -rotation,
                    expand=True,
                    fillcolor=255,
                    resample=Image.Resampling.BICUBIC,
                )

            base_w = 640
            base_h = 500
            sharpened.thumbnail((base_w, base_h), Image.Resampling.LANCZOS)

            if scale != 1.0:
                nw = max(10, int(sharpened.width * scale))
                nh = max(10, int(sharpened.height * scale))
                sharpened = sharpened.resize((nw, nh), Image.Resampling.LANCZOS)

            dithered = sharpened.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
            dithered_gray = dithered.convert("L")

            blurred_art = dithered_gray.filter(ImageFilter.GaussianBlur(radius=0.6))
            art_seed = int(hashlib.md5(f"{name}_art".encode("utf-8")).hexdigest()[:8], 16)
            art_rng = np.random.default_rng(art_seed)

            arr_art = np.array(blurred_art, dtype=np.float32)
            noise_art = art_rng.normal(0, 22.0, arr_art.shape)
            arr_art_noisy = np.clip(arr_art + noise_art, 0, 255)

            art_is_paper = arr_art_noisy >= 120
            art_is_black = ~art_is_paper
            art_pinholes = art_rng.random(arr_art.shape) < 0.007
            art_is_paper[art_is_black & art_pinholes] = True

            art_mono = (art_is_paper.astype(np.uint8)) * 255
            art_tile_mono = Image.fromarray(art_mono, mode="L")
            art_colored = ImageOps.colorize(art_tile_mono, black=INK_BLACK, white=CREAM_PAPER)

            center_x = (CARD_WIDTH - art_colored.width) // 2
            center_y = (CARD_HEIGHT - art_colored.height) // 2
            final_x = center_x + x_offset
            final_y = center_y + y_offset

            card.paste(art_colored, (final_x, final_y))
        except Exception as e:
            print(f"Error rendering art for '{name}': {e}")

    # 2. Text Boxes with 1 in 5 Shadow Lines and Random (-2° to 2°) Rotations
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

        # Faint cut-line pasteup outline on 1 in 5 text boxes (20%)
        outline_seed = int(hashlib.md5(f"{name}_{box_key}_pasteup_outline".encode("utf-8")).hexdigest()[:8], 16)
        outline_rng = np.random.default_rng(outline_seed)
        if outline_rng.random() < 0.20:
            pair = outline_rng.choice(["top_right", "top_left", "bottom_right", "bottom_left"])

            def draw_faint_edge(p1, p2):
                x_start, y_start = p1
                x_end, y_end = p2
                if y_start == y_end:
                    y = y_start
                    curr = min(x_start, x_end)
                    stop = max(x_start, x_end)
                    while curr < stop:
                        seg = outline_rng.integers(2, 5)
                        tile_draw.line([(curr, y), (min(curr + seg - 1, stop), y)], fill=0, width=1)
                        curr += seg + outline_rng.integers(2, 5)
                else:
                    x = x_start
                    curr = min(y_start, y_end)
                    stop = max(y_start, y_end)
                    while curr < stop:
                        seg = outline_rng.integers(2, 5)
                        tile_draw.line([(x, curr), (x, min(curr + seg - 1, stop))], fill=0, width=1)
                        curr += seg + outline_rng.integers(2, 5)

            inset = 2
            if pair == "top_right":
                draw_faint_edge((0, inset), (box_w - 1, inset))
                draw_faint_edge((box_w - 1 - inset, 0), (box_w - 1 - inset, box_h - 1))
            elif pair == "top_left":
                draw_faint_edge((0, inset), (box_w - 1, inset))
                draw_faint_edge((inset, 0), (inset, box_h - 1))
            elif pair == "bottom_right":
                draw_faint_edge((0, box_h - 1 - inset), (box_w - 1, box_h - 1 - inset))
                draw_faint_edge((box_w - 1 - inset, 0), (box_w - 1 - inset, box_h - 1))
            elif pair == "bottom_left":
                draw_faint_edge((0, box_h - 1 - inset), (box_w - 1, box_h - 1 - inset))
                draw_faint_edge((inset, 0), (inset, box_h - 1))

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

        # Random float rotation between -2.0 and 2.0 degrees
        rot_seed = int(hashlib.md5(f"{name}_{box_key}_rot".encode("utf-8")).hexdigest()[:8], 16)
        rot_rng = np.random.default_rng(rot_seed)
        angle = float(rot_rng.uniform(-0.4, 0.4))

        slip_rgba = colored.convert("RGBA")
        rotated_slip = slip_rgba.rotate(
            -angle,
            expand=True,
            resample=Image.Resampling.BICUBIC,
            fillcolor=(255, 255, 255, 0),
        )

        center_x = b_left + (box_w / 2.0)
        center_y = b_top + (box_h / 2.0)
        paste_x = int(round(center_x - (rotated_slip.width / 2.0)))
        paste_y = int(round(center_y - (rotated_slip.height / 2.0)))

        card.paste(rotated_slip, (paste_x, paste_y), mask=rotated_slip.split()[-1])

    render_photocopied_box(cfg_name, name, "name", align="left")
    render_photocopied_box(cfg_cost, cost, "cost", align="right")
    render_photocopied_box(cfg_type, typeline, "type", align="left")
    render_photocopied_box(cfg_rules, oracle_text, "rules", align="left", multiline=True)

    if has_pt:
        render_photocopied_box(cfg_pt, pt, "pt", align="center")

    return add_photocopy_grain(card, seed_key=name)


def extract_box_config(row: dict, prefix: str, def_size: int, def_l: int, def_t: int, def_r: int, def_b: int) -> dict:
    return {
        "font": str(row.get(f"{prefix}_font", "Arial")),
        "bold": str(row.get(f"{prefix}_bold", "True")).lower() == "true",
        "size": int(float(row.get(f"{prefix}_size", def_size))),
        "left": int(float(row.get(f"{prefix}_left", def_l))),
        "top": int(float(row.get(f"{prefix}_top", def_t))),
        "right": int(float(row.get(f"{prefix}_right", def_r))),
        "bottom": int(float(row.get(f"{prefix}_bottom", def_b))),
    }


def compute_smart_layout(row_dict: dict):
    typeline = str(row_dict.get("Typeline", "")).strip()
    oracle_text = str(row_dict.get("Oracle Text", "")).strip()
    is_pw = "planeswalker" in typeline.lower()

    cfg_name = extract_box_config(row_dict, "name", 78, 45, 25, 580, 115)
    cfg_cost = extract_box_config(row_dict, "cost", 78, 590, 25, 705, 115)
    cfg_type = extract_box_config(row_dict, "type", 42, 45, 135, 350, 195)
    cfg_rules = extract_box_config(row_dict, "rules", 28, 45, 760, 705, 995)
    cfg_pt = extract_box_config(row_dict, "pt", 68, 560, 920, 705, 995)

    if is_pw:
        # 1. Restore full card width to rules box so text never wraps excessively
        cfg_rules["left"] = 45
        cfg_rules["right"] = 705
        cfg_rules["bottom"] = 995
        usable_w = (cfg_rules["right"] - cfg_rules["left"]) - 20

        # 2. Dynamically fit all text lines without truncation
        r_size = cfg_rules["size"]
        while r_size > 18:
            r_font = get_font(cfg_rules["font"], r_size, bold=cfg_rules["bold"])
            lines = wrap_text(oracle_text, r_font, usable_w, DUMMY_DRAW)
            line_h = int(r_size * 1.35)
            needed_h = (len(lines) * line_h) + 26
            if needed_h <= 400:  # Leaves room for the upper-right loyalty box
                break
            r_size -= 1

        r_font = get_font(cfg_rules["font"], r_size, bold=cfg_rules["bold"])
        lines = wrap_text(oracle_text, r_font, usable_w, DUMMY_DRAW)
        line_h = int(r_size * 1.35)
        needed_h = max(90, (len(lines) * line_h) + 26)

        cfg_rules["size"] = r_size
        cfg_rules["top"] = cfg_rules["bottom"] - needed_h

        # 3. Position loyalty box perched directly above the rules box on the upper right
        pt_w = 95
        pt_h = 70
        cfg_pt["right"] = 705
        cfg_pt["left"] = cfg_pt["right"] - pt_w
        cfg_pt["bottom"] = cfg_rules["top"] - 12
        cfg_pt["top"] = cfg_pt["bottom"] - pt_h
        cfg_pt["size"] = int(float(row_dict.get("pt_size", 64)))

    return cfg_name, cfg_cost, cfg_type, cfg_rules, cfg_pt


def main():
    target_csv = CSV_PATH if os.path.exists(CSV_PATH) else FALLBACK_CSV
    if not os.path.exists(target_csv):
        print(f"Error: Neither '{CSV_PATH}' nor '{FALLBACK_CSV}' was found.")
        return

    print(f"Loading data from '{target_csv}'...")
    df = pd.read_csv(target_csv, dtype=str).fillna("")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    rendered_count = 0
    skipped_count = 0

    for idx, row in df.iterrows():
        name = str(row.get("Name of the card", "")).strip()
        if not name:
            continue

        safe_name = get_safe_filename(name)
        status = str(row.get("processed_status", "")).strip().lower()

        cropped_path = str(row.get("cropped_image_path", "")).strip()
        art_image = None

        if cropped_path and os.path.exists(cropped_path):
            art_image = Image.open(cropped_path).convert("RGB")
        else:
            source_path = find_source_image(name)
            if source_path and os.path.exists(source_path):
                art_image = Image.open(source_path).convert("RGB")

        if not art_image:
            print(f"Skipping [{name}]: No image found.")
            skipped_count += 1
            continue

        row_dict = row.to_dict()

        # Compute smart layout with loyalty above the rules box for planeswalkers
        cfg_name, cfg_cost, cfg_type, cfg_rules, cfg_pt = compute_smart_layout(row_dict)

        # Synchronize corrected layout coordinates into dataframe
        if "planeswalker" in str(row_dict.get("Typeline", "")).lower():
            for prefix, cfg in [("rules", cfg_rules), ("pt", cfg_pt)]:
                for k, v in cfg.items():
                    df.at[idx, f"{prefix}_{k}"] = str(v)

        brightness = float(row.get("brightness", 1.0))
        contrast = float(row.get("contrast", 2.2))
        rotation = float(row.get("rotation", 0))
        scale = float(row.get("scale", 1.25))
        x_offset = int(float(row.get("x_offset", 0)))
        y_offset = int(float(row.get("y_offset", -60)))
        invert_art = str(row.get("invert_art", "False")).strip().lower() == "true"

        card_img = render_full_card(
            row=row_dict,
            art_image=art_image,
            cfg_name=cfg_name,
            cfg_cost=cfg_cost,
            cfg_type=cfg_type,
            cfg_rules=cfg_rules,
            cfg_pt=cfg_pt,
            brightness=brightness,
            contrast=contrast,
            rotation=rotation,
            scale=scale,
            x_offset=x_offset,
            y_offset=y_offset,
            invert_art=invert_art,
        )

        out_path = os.path.join(OUTPUT_DIR, f"{safe_name}.png")
        card_img.save(out_path, "PNG")
        rendered_count += 1
        print(f"[{rendered_count}] Rendered: {safe_name}.png (Status: {status or 'Unmarked'})")

    # Save synchronized planeswalker layout coordinates back to CSV
    df.to_csv(target_csv, index=False, encoding="utf-8-sig")
    print(f"\nDone! Rendered {rendered_count} cards to '{OUTPUT_DIR}'. ({skipped_count} skipped)")


if __name__ == "__main__":
    main()