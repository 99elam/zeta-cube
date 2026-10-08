# import json
# import os
# import urllib.parse
# import urllib.request
# import pandas as pd
# from PIL import Image, ImageDraw, ImageFont

# CSV_PATH = "modovintage_cube_edited.csv"
# DUMMY_IMG = Image.new("RGB", (1, 1))
# DUMMY_DRAW = ImageDraw.Draw(DUMMY_IMG)

# # Built-in lookup for Vintage Cube staples (avoids unnecessary API calls)
# KNOWN_LOYALTY = {
#     "Jace, the Mind Sculptor": "3",
#     "Dack Fayden": "3",
#     "Oko, Thief of Crowns": "4",
#     "Teferi, Time Raveler": "4",
#     "Teferi, Hero of Dominaria": "4",
#     "Liliana of the Veil": "3",
#     "Liliana, the Last Hope": "3",
#     "Wrenn and Six": "3",
#     "Narset, Parter of Veils": "5",
#     "Minsc & Boo, Timeless Heroes": "3",
#     "Karn Liberated": "6",
#     "Karn, Scion of Urza": "5",
#     "Ugin, the Spirit Dragon": "7",
#     "Chandra, Torch of Defiance": "4",
#     "Elspeth, Sun's Champion": "4",
#     "Grist, the Hunger Tide": "3",
#     "Comet, Stellar Pup": "5",
#     "Saheeli, Sublime Artificer": "5",
#     "Ashiok, Nightmare Weaver": "3",
#     "Daretti, Ingenious Iconoclast": "3",
#     "Tamiyo, Inquisitive Student": "2",
#     "Ajani, Nacatl Pariah": "3",
#     "Sorin, Imperious Bloodlord": "4",
# }


# def fetch_scryfall_loyalty(card_name: str) -> str:
#     clean_name = card_name.split("//")[0].strip()
#     if clean_name in KNOWN_LOYALTY:
#         return KNOWN_LOYALTY[clean_name]

#     url = f"https://api.scryfall.com/cards/named?exact={urllib.parse.quote(clean_name)}"
#     req = urllib.request.Request(url, headers={"User-Agent": "MTGPlaytestStudio/1.0"})
#     try:
#         with urllib.request.urlopen(req) as resp:
#             data = json.loads(resp.read().decode("utf-8"))
#             if "loyalty" in data and data["loyalty"]:
#                 return str(data["loyalty"])
#             if "card_faces" in data:
#                 for face in data["card_faces"]:
#                     if "loyalty" in face and face["loyalty"]:
#                         return str(face["loyalty"])
#     except Exception as e:
#         print(f"Could not fetch loyalty for '{clean_name}': {e}")
#     return "3"  # Standard fallback


# def get_font(family: str, size: int, bold: bool = True) -> ImageFont.ImageFont:
#     font_file = "timesbd.ttf" if "Times" in family else "arialbd.ttf"
#     try:
#         return ImageFont.truetype(font_file, size)
#     except IOError:
#         return ImageFont.load_default()


# def calculate_safe_placement(row: dict, loyalty: str):
#     oracle_text = str(row.get("Oracle Text", "")).strip()
#     r_font_name = row.get("rules_font", "Arial")
#     r_bold = str(row.get("rules_bold", "True")).lower() == "true"
#     r_size = int(float(row.get("rules_size", 28)))
#     font = get_font(r_font_name, r_size, bold=r_bold)

#     r_left = int(float(row.get("rules_left", 45)))
#     r_top = int(float(row.get("rules_top", 760)))
#     r_right = int(float(row.get("rules_right", 705)))
#     r_bottom = int(float(row.get("rules_bottom", 995)))

#     pt_w = 95
#     pt_h = 75
#     target_pt_right = 705
#     target_pt_bottom = 995
#     target_pt_left = target_pt_right - pt_w
#     target_pt_top = target_pt_bottom - pt_h

#     # Check if text lines fit if we constrain the rules box to the left of loyalty
#     narrow_usable_w = (target_pt_left - 15) - r_left - 20
#     lines = []
#     for para in oracle_text.split("\n"):
#         words = para.split(" ")
#         cur = []
#         for w in words:
#             test = " ".join(cur + [w])
#             bbox = DUMMY_DRAW.textbbox((0, 0), test, font=font)
#             if bbox[2] - bbox[0] <= narrow_usable_w:
#                 cur.append(w)
#             else:
#                 if cur:
#                     lines.append(" ".join(cur))
#                 cur = [w]
#         if cur:
#             lines.append(" ".join(cur))

#     total_h = len(lines) * int(r_size * 1.35)

#     if (r_top + total_h) <= target_pt_bottom:
#         # Fits with room to spare: narrow the rules box horizontally
#         return target_pt_left, target_pt_top, target_pt_right, target_pt_bottom, target_pt_left - 15, r_bottom
#     else:
#         # Overflow risk: keep wide width and tuck loyalty directly beneath the text
#         safe_top = min(920, max(r_top + total_h + 10, 850))
#         return target_pt_left, safe_top, target_pt_right, safe_top + pt_h, r_right, safe_top - 10


# def update_planeswalkers():
#     if not os.path.exists(CSV_PATH):
#         print(f"Error: '{CSV_PATH}' not found.")
#         return

#     df = pd.read_csv(CSV_PATH, dtype=str).fillna("")
#     count = 0

#     for idx, row in df.iterrows():
#         typeline = str(row.get("Typeline", "")).lower()
#         if "planeswalker" in typeline:
#             name = str(row.get("Name of the card", "")).strip()
#             loyalty = fetch_scryfall_loyalty(name)

#             pt_l, pt_t, pt_r, pt_b, new_r_right, new_r_bottom = calculate_safe_placement(row.to_dict(), loyalty)

#             df.at[idx, "Power / Toughness"] = loyalty
#             df.at[idx, "pt_font"] = row.get("name_font", "Arial")
#             df.at[idx, "pt_bold"] = "True"
#             df.at[idx, "pt_size"] = "68"
#             df.at[idx, "pt_left"] = str(pt_l)
#             df.at[idx, "pt_top"] = str(pt_t)
#             df.at[idx, "pt_right"] = str(pt_r)
#             df.at[idx, "pt_bottom"] = str(pt_b)

#             df.at[idx, "rules_right"] = str(new_r_right)
#             df.at[idx, "rules_bottom"] = str(new_r_bottom)
#             count += 1
#             print(f"Configured Loyalty {loyalty} for [{name}]")

#     df.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
#     print(f"\nDone! Updated {count} planeswalkers in '{CSV_PATH}'.")


# if __name__ == "__main__":
#     update_planeswalkers()

import os
import pandas as pd

CSV_PATH = "modovintage_cube_edited.csv"

BASIC_LANDS = [
    {
        "Name of the card": "Plains",
        "Mana Cost": "",
        "Typeline": "Basic Land — Plains",
        "Oracle Text": "({T}: Add {W}.)",
        "Power / Toughness": "",
    },
    {
        "Name of the card": "Island",
        "Mana Cost": "",
        "Typeline": "Basic Land — Island",
        "Oracle Text": "({T}: Add {U}.)",
        "Power / Toughness": "",
    },
    {
        "Name of the card": "Swamp",
        "Mana Cost": "",
        "Typeline": "Basic Land — Swamp",
        "Oracle Text": "({T}: Add {B}.)",
        "Power / Toughness": "",
    },
    {
        "Name of the card": "Mountain",
        "Mana Cost": "",
        "Typeline": "Basic Land — Mountain",
        "Oracle Text": "({T}: Add {R}.)",
        "Power / Toughness": "",
    },
    {
        "Name of the card": "Forest",
        "Mana Cost": "",
        "Typeline": "Basic Land — Forest",
        "Oracle Text": "({T}: Add {G}.)",
        "Power / Toughness": "",
    },
]

if os.path.exists(CSV_PATH):
    df = pd.read_csv(CSV_PATH, dtype=str).fillna("")
    existing_names = df["Name of the card"].str.strip().tolist()

    for land in BASIC_LANDS:
        card_name = land["Name of the card"]
        if card_name in existing_names:
            # If already present, reset status to Pending so GUI loads it
            idx = df[df["Name of the card"].str.strip() == card_name].index[0]
            df.at[idx, "processed_status"] = "Pending"
        else:
            # Append as a fresh pending row
            row_data = {col: "" for col in df.columns}
            row_data.update(land)
            row_data.update(
                {
                    "processed_status": "Pending",
                    "name_font": "Arial",
                    "name_bold": "True",
                    "name_size": "78",
                    "cost_font": "Arial",
                    "cost_bold": "True",
                    "cost_size": "78",
                    "type_font": "Arial",
                    "type_bold": "True",
                    "type_size": "42",
                    "rules_font": "Arial",
                    "rules_bold": "True",
                    "rules_size": "36",
                    "brightness": "1.0",
                    "contrast": "2.2",
                    "rotation": "0",
                    "scale": "1.25",
                    "x_offset": "0",
                    "y_offset": "-60",
                    "invert_art": "False",
                }
            )
            df = pd.concat([df, pd.DataFrame([row_data])], ignore_index=True)

    df.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    print("Basic lands are now set to 'Pending' at the end of the CSV.")