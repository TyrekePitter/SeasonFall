from __future__ import annotations

import json
import os

# Base directory for the whole game (Seasonfall folder)
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
# Path to character template json
DATA_PATH = os.path.join(BASE_DIR, "data", "character_template.json")
# DIrectory that holds all save file
SAVE_DIR = os.path.join(BASE_DIR, "saves")
# Make sure the saves folder exists
os.makedirs(SAVE_DIR, exist_ok=True)

def get_save_path(slot: str) -> str:
    """Return full path to the given save slot, e.g. 'slot1' -> '.../saves/slot1.json'."""
    return os.path.join(SAVE_DIR, f"{slot}.json")

def load_json(path: str) -> dict:
    """Load JSON data from the given file path ."""
    with open(path, "r") as file:
        return json.load(file)
    
def save_json(path: str, data: dict) -> None:
    """Save Python data into JSON file at the given path."""
    with open(path, "w") as file:
        json.dump(data, file, indent=4)

def save_character_to_slot(character: dict) -> None:
    """Save the given character back to its save slot."""
    # Try to read the character from itself
    slot_name = character.get("save_slot")

    # Fallback if for some reason its missing
    if not slot_name:
        slot_name = "slot1"

    path = get_save_path(slot_name)
    save_json(path, {"character": character})
    print(f"\nGame saved to {slot_name}.")