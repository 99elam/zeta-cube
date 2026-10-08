import re
import time
import pandas as pd
import requests

CUBE_ID = "modovintage"
CUBECOBRA_URL = f"https://cubecobra.com/cube/api/cubelist/{CUBE_ID}"
SCRYFALL_COLLECTION_URL = "https://api.scryfall.com/cards/collection"
HEADERS = {"User-Agent": "CubeExportScript/1.0", "Accept": "*/*"}

# Layouts representing true double-sided cards in Scryfall
DOUBLE_FACED_LAYOUTS = {"transform", "modal_dfc", "reversible_card"}


def format_wubrg_text(text: str) -> str:
    """Converts bracketed symbols like {W}, {U}, {T} into plain text."""
    if not text:
        return ""
    return re.sub(r"\{([^}]+)\}", r"\1", text)


def format_typeline(typeline: str) -> str:
    """Converts 'Creature — Bird' to 'Summon Bird' and strips all dashes."""
    if not typeline:
        return ""

    faces = typeline.split(" // ")
    cleaned_faces = []

    for face in faces:
        if re.search(r"\bCreature\b\s*[—–-]\s*", face):
            face = re.sub(r"\bCreature\b\s*[—–-]\s*", "Summon ", face)
        elif re.search(r"\bCreature\b", face):
            face = re.sub(r"\bCreature\b", "Summon", face)

        # Remove any other dashes
        face = re.sub(r"\s*[—–-]\s*", " ", face)
        face = re.sub(r"\s+", " ", face).strip()
        cleaned_faces.append(face)

    return " // ".join(cleaned_faces)


def fetch_cube_card_names(cube_id: str) -> list[str]:
    """Fetches list of card names from CubeCobra."""
    print(f"Fetching cube list for '{cube_id}' from CubeCobra...")
    resp = requests.get(CUBECOBRA_URL, headers=HEADERS)
    resp.raise_for_status()

    card_names = [
        line.strip() for line in resp.text.splitlines() if line.strip()
    ]
    seen = set()
    unique_names = [x for x in card_names if not (x in seen or seen.add(x))]
    print(f"Found {len(unique_names)} unique cards in the cube.")
    return unique_names


def fetch_scryfall_card_data(card_names: list[str]) -> list[dict]:
    """Queries Scryfall's /cards/collection endpoint in batches of 75."""
    cards_data = []
    batch_size = 75

    for i in range(0, len(card_names), batch_size):
        batch = [{"name": name} for name in card_names[i : i + batch_size]]
        print(
            f"Querying Scryfall for cards {i+1} to {min(i + batch_size, len(card_names))}..."
        )

        response = requests.post(
            SCRYFALL_COLLECTION_URL, json={"identifiers": batch}, headers=HEADERS
        )
        if response.status_code == 200:
            cards_data.extend(response.json().get("data", []))
        else:
            print(f"Failed batch: HTTP {response.status_code}")

        time.sleep(0.1)

    return cards_data


def process_cards(cards: list[dict]) -> pd.DataFrame:
    rows = []

    for card in cards:
        layout = card.get("layout", "")
        card_faces = card.get("card_faces")

        # 1. Double-sided cards (Transform cards, MDFCs, etc.) -> Split into 2 separate rows
        if layout in DOUBLE_FACED_LAYOUTS and card_faces and len(card_faces) >= 2:
            for face in card_faces:
                face_name = face.get("name", "")
                face_mana = format_wubrg_text(face.get("mana_cost", ""))
                face_oracle = format_wubrg_text(face.get("oracle_text", ""))
                raw_typeline = face.get("type_line", "")
                formatted_type = format_typeline(raw_typeline)

                pt = ""
                if (
                    ("Creature" in raw_typeline or "Vehicle" in raw_typeline)
                    and "power" in face
                    and "toughness" in face
                ):
                    pt = f"{face['power']}/{face['toughness']}"

                rows.append(
                    {
                        "Name of the card": face_name,
                        "Mana Cost": face_mana,
                        "Oracle Text": face_oracle,
                        "Typeline": formatted_type,
                        "Power / Toughness": pt,
                    }
                )

        # 2. Single-sided cards with multiple faces on one card (e.g. Split cards like Fire // Ice)
        elif card_faces and not card.get("oracle_text"):
            name = card.get("name")
            mana_costs = [
                format_wubrg_text(f.get("mana_cost", "")) for f in card_faces
            ]
            typelines = [
                format_typeline(f.get("type_line", "")) for f in card_faces
            ]
            oracle_texts = [
                format_wubrg_text(f.get("oracle_text", "")) for f in card_faces
            ]

            pt_list = []
            for f in card_faces:
                if "power" in f and "toughness" in f:
                    pt_list.append(f"{f['power']}/{f['toughness']}")
                else:
                    pt_list.append("-")

            rows.append(
                {
                    "Name of the card": name,
                    "Mana Cost": " // ".join(mana_costs).strip(),
                    "Oracle Text": "\n//\n".join(oracle_texts).strip(),
                    "Typeline": " // ".join(typelines).strip(),
                    "Power / Toughness": (
                        " // ".join(pt_list)
                        if any(pt != "-" for pt in pt_list)
                        else ""
                    ),
                }
            )

        # 3. Standard single-faced cards
        else:
            name = card.get("name")
            mana_cost = format_wubrg_text(card.get("mana_cost", ""))
            oracle_text = format_wubrg_text(card.get("oracle_text", ""))
            raw_typeline = card.get("type_line", "")
            typeline = format_typeline(raw_typeline)

            pt = ""
            if (
                ("Creature" in raw_typeline or "Vehicle" in raw_typeline)
                and "power" in card
                and "toughness" in card
            ):
                pt = f"{card['power']}/{card['toughness']}"

            rows.append(
                {
                    "Name of the card": name,
                    "Mana Cost": mana_cost,
                    "Oracle Text": oracle_text,
                    "Typeline": typeline,
                    "Power / Toughness": pt,
                }
            )

    return pd.DataFrame(rows)


def main():
    names = fetch_cube_card_names(CUBE_ID)
    scryfall_cards = fetch_scryfall_card_data(names)
    df = process_cards(scryfall_cards)

    output_filename = "modovintage_cube.csv"
    df.to_csv(output_filename, index=False, encoding="utf-8-sig")
    print(f"\nDone! Exported {len(df)} rows to '{output_filename}'.")


if __name__ == "__main__":
    main()