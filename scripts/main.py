from character_system import (
    choose_race,
    choose_origin,
    choose_appearance,
    create_character_from_template,
    load_existing_character,
    print_character_summary,
    choose_save_slot,
    get_save_path
)
from data_io import get_save_path, save_json
from game_actions import game_loop

def create_new_character_flow() -> dict:
    """Handle character creation and saving to a chosen slot."""
    # 1. Ask player for basic info
    name = input("Enter a name for your character: ").strip()

    # 2. Choose race, origin and appearance
    race_info = choose_race()
    origin_info = choose_origin()
    appearance_info = choose_appearance()

    # 3. Build the character from the template and choices
    character = create_character_from_template(
        name,
        race_info,
        origin_info,
        appearance_info,
    )

    print("\n=== New Character Created ===")
    print_character_summary(character)

    # 4. Ask which slot to save in
    slot_name = choose_save_slot()

    character["save_slot"] = slot_name

    path = get_save_path(slot_name)

    # 5. Save to disk
    save_json(path, {"character": character})
    print(f"\nCharacter saved to {slot_name}.")

    return character

# Create main menu
def main_menu():
    """Simple text main menu for Seasonfall."""
    while True:
        print("\n=== Seasonfall ===")
        print("1) Create new character")
        print("2) Load existing character")
        print("3) Quit")
        # Extension: Later add options like:
        # - 4) Options/Settings
        # - 5) Credits/lore

        choice = input(". ").strip()

        if choice == "1":
            # Run character creation flow
            character = create_new_character_flow()
            if character is not None:
                game_loop(character)

        elif choice == "2":
            # Try to load and show saved character
            character = load_existing_character()
            if character:
                # Jump into the in-game loop using the loaded character
                game_loop(character)
        elif choice == "3":
            print("\nGoodbye, Bearer of Seasonfall")
            break
        else:
            print("Please choose 1, 2, or 3.")

def main() -> None:
    """Entry point for the program."""
    main_menu()

if __name__ == "__main__":
    main()