from __future__ import annotations
from typing import Dict
from data_io import save_json, get_save_path
from character_system import (
    apply_derived_stats,
    gain_xp,
    print_character_summary,
)

def autosave_character(character: dict) -> None:
    """Save the current character back to its save slot, if known"""
    slot_name = character.get("save_slot")
    if not slot_name:
        return
    
    path = get_save_path(slot_name)
    save_json(path, {"character": character})

# Run a simple in game menu for the current character
def game_loop(character: dict) -> None:
    """Very simple in game loop stub for Seasonfall."""
    while True:
        print("\n=== Seasonfall - In Game ===")
        print("1) View character sheet")
        print("2) Rest at camp")
        print("3) Spar with training dummy")
        print("4) Return to main menu")
        # Extension: add more actions here later
        #   5) Explore area
        #   6) Talk to NPC
        #   7) Start quest

        choice = input("> ").strip()

        if choice == "1":
            print_character_summary(character)
        elif choice == "2":
            rest_at_camp(character)
        elif choice == "3":
            spar_training_dummy(character)
        elif choice == "4":
            # Break out of game loop and go back to main menu
            save_slot = character.get("save_slot", "slot1")
            path = get_save_path(save_slot)
            save_json(path, {"character": character})
            print(f"\nGame saved to {save_slot}.")
            break
        else:
            print("Please choose (1-4).")

# Rest at camp 
def rest_at_camp(character: dict) -> None:
    """Simple in game action: restore health and stamina."""
    # Extension
    # - Advance in-game time
    # - Trigger campfire dialogue
    # - Random events
    stats = character.get("stats", {})
    stats["health"] = 100
    stats["stamina"] = 100
    autosave_character(character)
    print("\nYou rest at camp. Your health and stamina are restored.")

# Training dummy
def spar_training_dummy(character: dict) -> None:
    """Simple combat test: you trade blows with a training dummy."""

    # Extension:
    # - Replace later with real combat

    stats = character.get("stats", {})
    derived = character.get("derived_stats", {})

    health = stats.get("health", 0)
    stamina = stats.get("stamina", 0)

    # Cost to attack
    stamina_cost = 10

    # Base damge from the dummy
    base_damage = 15

    # Use resistances to reduce the damage a bit
    cold_res = derived.get("cold_resistance", 0)
    heat_res = derived.get("heat_resistance", 0)

    # Each 5 points of either resistance reduces damage by 1
    reduction = (cold_res // 5) + (heat_res // 5)
    damage_taken = max(1, base_damage - reduction)

    if stamina < stamina_cost:
        print("\nYou're too tired to train. Rest at camp first.")
        return
    
    # Spend stamina and take damage
    stamina -= stamina_cost
    health -= damage_taken
    if health < 0:
        health = 0

    # Save Changes
    stats["health"] = health
    stats["stamina"] = stamina

    gain_xp(character, 10)

    autosave_character(character)
    
    print("\nYou strike the training dummy again and again.")
    print(f"You spend {stamina_cost} stamina and take {damage_taken} damage in return")
    print(f"Current Health: {health}")
    print(f"Current Stamina: {stamina}")

    # Optional: auto-rest if you "drop to 0"
    if health == 0:
        print("\nYou collapse from the exhaustion and are carried back to camp...")
        rest_at_camp(character)


