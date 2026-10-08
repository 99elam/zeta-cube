import pandas as pd

CSV_PATH = "modovintage_cube_edited.csv"
df = pd.read_csv(CSV_PATH, dtype=str).fillna("")

# Normalize Windows backslashes to universal forward slashes
df["cropped_image_path"] = df["cropped_image_path"].str.replace(
    "\\", "/", regex=False
)

df.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
print(
    "Paths normalized to cross-platform standard (e.g., ./images_cropped/card.png)."
)