from __future__ import annotations
import os
from data_io import DATA_PATH, load_json, save_json, get_save_path

# Save slots
SLOTS = {
    "1": "slot1",
    "2": "slot2",
    "3": "slot3",
}

RACES = {
    # Winter races
    "1": {
        "name": "Winterborn",
        "description": "Chidren of Astael's cold stars. Calm, calculating, endure harsh climates.",
        "affinity_bonus": {"winter": 10}
    },
    "2": {
        "name": "Shardbound",
        "description": "Frontier folk hardened by ice and ruin, blunt and resilent.",
        "affinity_bonus": {"winter": 7, "fall": 3}
    },
    # Spring Races
    "3": {
        "name": "Springtouched",
        "description": "Blessed by Serapha's bloom. Hopeful, curious, strong with healing and growth.",
        "affinity_bonus": {"spring": 10}
    },
    "4": {
        "name": "Thornkin",
        "description": "Bramble-scarred wardens of wild groves, protective and stubborn.",
        "affinity_bonus": {"spring": 7, "summer": 3}
    },
    # Summer Races
    "5": {
        "name": "Sunforged",
        "description": "Hardened in Sol'Kavash's heat. Competitive, fierce, strong offensive power.",
        "affinity_bonus": {"summer": 10}
    },
    "6": {
        "name": "Miragewalker",
        "descrip`tion": "Clever desert nomads who use mirage, speed and tricks to survive.",
        "affinity_bonus": {"summer": 7, "spring": 3}
    },
    # Fall Races
    "7": {
        "name": "Veilmarked",
        "description": "Shaped by Mor'Thallan's dusk. Thoughtful, stubburn, tied to decay and endings.",
        "affinity_bonus": {"fall": 10}
    
    },
    "8": {
        "name": "Carrionbound",
        "description": "Grave-tenders and death-priests, comfortable with decayand memory.",
        "affinity_bonus": {"fall": 7, "winter": 3}
    }
}

ORIGINS = {

    "1": {
        "name": "Astrael's Domain",
        "season": "winter",
        "patron_god": "Astrael of the still sky",
        "description": "Snowbound citadels, star-watching towers, and aurora-lit roads."
    },
    "2": {
        "name": "Seraha's Bloomfields",
        "season": "spring",
        "patron_god": "Serapha Bloomwhisper",
        "description": "Verdant valleys, moving flower-towns, and rivers lined with blossoms."
    },
    "3": {
        "name": "Sol'Kavash Expanse",
        "season": "summer",
        "patron_god": "Sol'kavash the Burning Bloom",
        "description": "Desert bastions, mirage-markets, and fiery sun alters."
    },
    "4": {
        "name": "Mor'Thallan Vale",
        "season": "fall",
        "patron_god": "Mor'Thallan the Duskwalker",
        "description": "Foggy townlands, necropolises, and thoughtful dusk processions."
    }
}

def apply_derived_stats(character: dict) -> None:
    """Update derived stats based on current affinities."""
    affinities = character.get("affinity", {})
    derived = character.setdefault("derived_stats", {})

    # Extension:
    # - armor / equipment
    # - temporary buffs and debuffs
    # - status effects (poison, burning, etc.)

    winter = affinities.get("winter", 0)
    summer = affinities.get("summer", 0)

    # Simple formula for now: base 10 + affinity
    derived["cold_resistance"] = 10 + winter
    derived["heat_resistance"] = 10 + summer

def choose_origin():
    """Ask the player to pick a homeland / region and return the origin data."""
    print("\nChoose your origin region:")
    for key, origin in ORIGINS.items():
        desc = origin.get("description", "")
        print(f"{key}) {origin['name']} - {desc}")

    choice = input("> ").strip()

    while choice not in ORIGINS:
        print("Please choose a valid option (1-4).")
        choice = input("> ").strip()

    return ORIGINS[choice]



def choose_race():
    """Ask the player to pick a race and return the chosen race data."""
    print("\nChoose your race:")
    for key, race in RACES.items():
        desc = race.get("description", "")
        print(f"{key} {race['name']} - {desc}")

    choice = input("> ").strip()

    while choice not in RACES:
        print("Please choose a valid option (1-4).")
        choice = input("> ").strip()

    return RACES[choice]

def choose_save_slot() -> str:
    """Ask the layer which save slot to use and return its internal name (e.ge 'slot1')."""
    print("\nChoose a save slot:")
    for key, slot_name in SLOTS.items():
        path = get_save_path(slot_name)
        # Default label is just the raw slot name
        label = slot_name

        if os.path.exists(path):
            try:
                data = load_json(path)
                character = data.get("character", {})
                name = character.get("name", "Unnamed")
                race = character.get("race", "Unknown race")
                # Example: slot1 - Ty (Winterborn)
                label = f"{slot_name} - {name} ({race})"
            except Exception:
                # If the file is broken for some reason
                label = f"{slot_name} - <corrupted>"

        else:
            # No file yet
            label = f"{slot_name} - <empty>"

        print(f"{key}) {label}")
   
   
    choice = input("> ").strip()

    while choice not in SLOTS:
        print("Please choose 1, 2, or 3.")
        choice = input("> ").strip()

    return SLOTS[choice]

def create_character_from_template(name: str, race_info: dict, origin_info: dict, appearance_info: dict) -> dict:
    """Create a new character based on the template and give it a name, race and origin."""
    character_data = load_json(DATA_PATH)
    template = character_data["character"]

    character = dict(template)

    # Set name and race
    character["name"] = name
    character["race"] = race_info["name"]

    # Set origin region and starting religion/god
    character["origin_region"] = origin_info["name"]
    character["patron"] = origin_info["patron_god"]

    # Small extra affinity bonus from homeland season
    origin_season = origin_info["season"]
    if origin_season in character["affinity"]:
        character["affinity"][origin_season] += 3

    # Apply starting affinity bonus from race
    bonus = race_info.get("affinity_bonus", {})
    for season, amount in bonus.items():
        character["affinity"][season] += amount
    
    # Extension: 
    # - Class / Job bonuses and disadvantages
    # - Background / story traits
    # - Starting items / equipment
    
    # Recalculate derived stats after all affinity changes
    apply_derived_stats(character)

    # Save to disk
    slot_id = choose_save_slot()
    path = get_save_path(slot_id)
    save_json(path, character_data)
    return character

# HElper Function Ask player for appearance
def choose_appearance() -> dict:
    """Ask the player to describe their character's appearance."""
    print("\nDescribe your character's appearance.")

    body_type = input("Body type (slim, athlethic, heavy, etc): ").strip()
    face = input("Face details (sharp, round, scarred, etc): ").strip()
    hair = input("Hair (style/color): ").strip()
    markings = input("Markings / tattoos (or 'none'): ").strip()
    scars = input("Scars (or 'none'): ").strip()

    return {
        "body_type": body_type,
        "face": face,
        "hair": hair,
        "markings": markings,
        "scars": scars,
    }

#
def print_character_summary(character: dict) -> None:
    """Print a simple, readable summary of the character."""
    print("\n=== Character Summary ===")
    print(f"Name:   {character['name']}")
    print(f"Race:   {character['race']}")
    print(f"Origin: {character['origin_region']}")
    print(f"Patron: {character['religion_origin']}")

    # Extension
    # - Equipped weapon / armor
    # - active effects (buffs / debuffs)
    # - current quest / location

    print("\nAffinities:")
    for season, value in character["affinity"].items():
        print(f"    {season.title()}: {value}")

    # Only print derived stats if they exist
    if "derived_stats" in character:
        print("\nDerived Stats:")
        for stat, value in character["derived_stats"].items():
            label = stat.replace("_", " ").title()
            print(f"    {label}: {value}")

        print("\nCore Stats:")
        stats = character["stats"]
        for stat_name in ["health", "stamina", "mana", "level"]:
            label = stat_name.title()
            print(f"  {label}: {stats[stat_name]}")

    # XP section

    xp = stats.get("xp", 0)
    needed = xp_needed_for_next_level(stats["level"])
    xp_to_next = max(0, needed - xp)

    print(f"\nXP: {xp}")
    print(f"XP to next level: {xp_to_next}")
    print("=========================\n")

def xp_needed_for_next_level(level: int) -> int:
    """Return how much XP is needed to reach the next level."""
    # Simple curve: 100 for each level 1 -> 2
    # Then +50 more for each level
    return 100 + (level - 1) * 50

def level_up(character: dict) -> None:
    """Increase character level and improve stats."""
    stats = character["stats"]

    stats["level"] += 1
    print(f"\n*** You reached level {stats['level']}! ***")
    print("Your health and stamina increase.")


    # Basic stat bonuses per level - tweak to taste
    stats["health"] += 10
    stats["stamina"] += 10
    stats["mana"] += 5

    # Recalculate derived stats if you want them to react to level
    apply_derived_stats(character)

def gain_xp(character: dict, amount: int) -> None:
    """Give XP and handle level ups."""
    stats = character["stats"]

    # Make sure xp exists
    current_xp = stats.get("xp", 0)
    current_xp += amount
    stats["xp"] = current_xp

    # Check for level ups (loop in case we gain more than 1 level)
    while True:
        needed = xp_needed_for_next_level(stats["level"])
        if current_xp < needed:
            break

        current_xp -= needed
        level_up(character)

    stats["xp"] = current_xp



# Load existing character
def load_existing_character() -> dict | None:
    """Load a saved character from the disk and show the summary."""
    
    print("\nWhich save slot do you want to load?")
    for key, slot_name in SLOTS.items():
        path = get_save_path(slot_name)
        label = slot_name

        if os.path.exists(path):
            try:
                data = load_json(path)
                character = data.get("character", {})
                name = character.get("name", "Unnamed")
                race = character.get("race", "Unknown race")
                label = f"{slot_name} - {name} ({race})"
            except Exception:
                label = f"{slot_name} - <corrupted>"
        else:
            label = f"{slot_name} - <empty>"
        
        print(f"{key}) {label}")

    choice = input("> ").strip()
    while choice not in SLOTS:
        print("Please choose 1, 2, or 3.")
        choice = input("> ").strip()

    slot_name = SLOTS[choice]
    path = get_save_path(slot_name)

    # If there is no saved file yet, tell the player to stop.
    if not os.path.exists(path):
        print("\nNo save file found. Create a character first.")
        return None
    
    # Read JSON save file
    data = load_json(path)
    character = data.get("character")

    if not isinstance(character, dict):
        print("\nSave file is empty or corrupted.")
        return None

    # Re aply derived stats (in case formulas changed)
    apply_derived_stats(character)

    print("\nLoaded saved character:")
    print_character_summary(character)

    return character