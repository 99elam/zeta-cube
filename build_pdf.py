import glob
import os
from PIL import Image, ImageDraw

PLAYTEST_DIR = "./playtest_cards"
OUTPUT_PDF = "playtest_cube_print_slips.pdf"

PAGE_WIDTH = 2550
PAGE_HEIGHT = 3300

CARD_PRINT_WIDTH = 690
CARD_PRINT_HEIGHT = 990

LEFT_MARGIN = (PAGE_WIDTH - (3 * CARD_PRINT_WIDTH)) // 2   # 240 px
TOP_MARGIN = (PAGE_HEIGHT - (3 * CARD_PRINT_HEIGHT)) // 2   # 165 px

BASIC_LAND_COPIES = 30  # Adjust between 30 and 35


def draw_crop_marks(draw: ImageDraw.ImageDraw):
    col_coords = [
        LEFT_MARGIN,
        LEFT_MARGIN + CARD_PRINT_WIDTH,
        LEFT_MARGIN + (2 * CARD_PRINT_WIDTH),
        LEFT_MARGIN + (3 * CARD_PRINT_WIDTH),
    ]
    row_coords = [
        TOP_MARGIN,
        TOP_MARGIN + CARD_PRINT_HEIGHT,
        TOP_MARGIN + (2 * CARD_PRINT_HEIGHT),
        TOP_MARGIN + (3 * CARD_PRINT_HEIGHT),
    ]
    tick_length = 40
    line_color = (140, 140, 140)

    for x in col_coords:
        draw.line([(x, TOP_MARGIN - tick_length), (x, TOP_MARGIN - 10)], fill=line_color, width=2)
        draw.line([(x, TOP_MARGIN + (3 * CARD_PRINT_HEIGHT) + 10), (x, TOP_MARGIN + (3 * CARD_PRINT_HEIGHT) + tick_length)], fill=line_color, width=2)

    for y in row_coords:
        draw.line([(LEFT_MARGIN - tick_length, y), (LEFT_MARGIN - 10, y)], fill=line_color, width=2)
        draw.line([(LEFT_MARGIN + (3 * CARD_PRINT_WIDTH) + 10, y), (LEFT_MARGIN + (3 * CARD_PRINT_WIDTH) + tick_length, y)], fill=line_color, width=2)


def create_print_pdf():
    all_files = sorted(glob.glob(os.path.join(PLAYTEST_DIR, "*.png")))
    if not all_files:
        print(f"No cards found in '{PLAYTEST_DIR}'!")
        return

    land_names = ["Plains.png", "Island.png", "Swamp.png", "Mountain.png", "Forest.png"]
    cube_cards = [f for f in all_files if os.path.basename(f) not in land_names]
    land_cards = [f for f in all_files if os.path.basename(f) in land_names]

    # Assemble print queue: regular cards first, then duplicated land station
    print_queue = list(cube_cards)
    for land_path in land_cards:
        print_queue.extend([land_path] * BASIC_LAND_COPIES)

    print(f"Total cards to print: {len(print_queue)} ({len(cube_cards)} cube cards + {len(land_cards) * BASIC_LAND_COPIES} basic lands)")

    pages = []
    for i in range(0, len(print_queue), 9):
        chunk = print_queue[i : i + 9]
        page = Image.new("RGB", (PAGE_WIDTH, PAGE_HEIGHT), (255, 255, 255))
        draw = ImageDraw.Draw(page)

        for idx, card_path in enumerate(chunk):
            col = idx % 3
            row = idx // 3
            x = LEFT_MARGIN + (col * CARD_PRINT_WIDTH)
            y = TOP_MARGIN + (row * CARD_PRINT_HEIGHT)

            with Image.open(card_path) as card_img:
                resized = card_img.resize((CARD_PRINT_WIDTH, CARD_PRINT_HEIGHT), Image.Resampling.LANCZOS)
                page.paste(resized, (x, y))

        draw_crop_marks(draw)
        pages.append(page)

    if pages:
        pages[0].save(OUTPUT_PDF, save_all=True, append_images=pages[1:], resolution=300.0, quality=95)
        print(f"Successfully generated '{OUTPUT_PDF}' ({len(pages)} pages).")


if __name__ == "__main__":
    create_print_pdf()