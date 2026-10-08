import argparse
import os
import pandas as pd
from PIL import Image

TARGET_DIR = "./images_cropped"
CSV_PATH = "modovintage_cube_edited.csv"
MAX_DIM = 700  # Exceeds the 640x500 thumbnail box in card_gen.py


def shrink_crops(output_format: str):
    if not os.path.exists(TARGET_DIR):
        print(f"Error: Directory '{TARGET_DIR}' not found.")
        return

    files = [
        f
        for f in os.listdir(TARGET_DIR)
        if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
    ]
    total_before = 0
    total_after = 0
    processed_count = 0

    print(
        f"Processing {len(files)} images to '{output_format.upper()}' (Max Dimension: {MAX_DIM}px)...\n"
    )

    for filename in sorted(files):
        src_path = os.path.join(TARGET_DIR, filename)
        size_bytes = os.path.getsize(src_path)
        total_before += size_bytes

        with Image.open(src_path) as img:
            # Flatten any alpha layers onto white
            if (
                img.mode in ("RGBA", "LA")
                or (img.mode == "P" and "transparency" in img.info)
            ):
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[-1])
                img = bg
            else:
                img = img.convert("RGB")

            # Scale down to 700px maximum dimension
            if img.width > MAX_DIM or img.height > MAX_DIM:
                img.thumbnail((MAX_DIM, MAX_DIM), Image.Resampling.LANCZOS)

            if output_format == "jpg":
                base_name = os.path.splitext(filename)[0]
                dest_path = os.path.join(TARGET_DIR, f"{base_name}.jpg")
                img.save(dest_path, format="JPEG", quality=85, optimize=True)
                if dest_path != src_path and os.path.exists(src_path):
                    os.remove(src_path)
                final_path = dest_path

            else:  # PNG-8 (256 colors)
                temp_path = src_path + ".tmp"
                quantized = img.quantize(
                    colors=256, method=Image.Resampling.LANCZOS
                )
                quantized.save(temp_path, format="PNG", optimize=True)
                os.replace(temp_path, src_path)
                final_path = src_path

        new_size = os.path.getsize(final_path)
        total_after += new_size
        processed_count += 1

    # Update CSV if format switched to JPG
    if output_format == "jpg" and os.path.exists(CSV_PATH):
        df = pd.read_csv(CSV_PATH, dtype=str).fillna("")
        df["cropped_image_path"] = (
            df["cropped_image_path"].str.replace("\\", "/", regex=False)
        )
        df["cropped_image_path"] = df["cropped_image_path"].apply(
            lambda p: os.path.splitext(p)[0] + ".jpg" if p else ""
        )
        df.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
        print(f"Updated '{CSV_PATH}' image paths to .jpg.")

    mb_before = total_before / (1024 * 1024)
    mb_after = total_after / (1024 * 1024)
    print(
        f"\nDone! Processed {processed_count} images."
    )
    print(
        f"Folder size: {mb_before:.1f} MB -> {mb_after:.1f} MB (-{100 - (mb_after / mb_before * 100):.1f}%)"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Shrink cropped card assets.")
    parser.add_argument(
        "--format",
        choices=["png", "jpg"],
        default="png",
        help="Output format: 'png' (~80MB, no CSV updates needed) or 'jpg' (~42MB, updates CSV)",
    )
    args = parser.parse_args()
    shrink_crops(args.format)