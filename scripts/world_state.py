"""Reactive world-state layer for Seasonfall.

This module is the demonstration piece of the Python build (Carry Forward 001):
world state changes as a consequence of player *outcomes*, not combat math.
Combat is stubbed. Nothing here computes damage.

The data lives in two places, split by who writes it:

* Region data (``data/regions/<id>.json``) is authored content: the map,
  the adjacency graph, the god's anchor, settlement identities and their
  base and degraded ratings. It is read-only at runtime. Nothing in this
  module ever writes to it.
* Save state (``saves/world_<slot>.json``) is runtime state: god
  resolutions, kill counts, stillness progress, and each settlement's
  current ratings. Every transition takes the region data and a save
  state and returns a new save state. World saves live beside the
  character system's ``saves/<slot>.json`` files but never share a path
  with them — the two schemas are incompatible.

Design constraints, deliberate:

* Pure functions. Every transition takes a state and returns a new state.
  Nothing mutates in place, so a save is a snapshot and a transition is
  reproducible. This is also what makes the port to C# a syntax exercise
  rather than a redesign.
* No Python-only idioms. Plain dicts, explicit loops, no comprehension
  cleverness, no dataclass magic. Everything here maps to a C# class with
  fields.
* Open canon threads raise instead of guessing. Three of the four resolution
  types have no ruled map consequence yet; the code says so rather than
  inventing one.
"""

from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict, List

# Game Bible 13.1, promoted to a system enum by Carry Forward 001.
RESOLUTIONS = ("killed", "redeemed", "absorbed", "manipulated")

# Carry Forward 003: the third god resolved arms the Eclipse, any resolution type.
ECLIPSE_ARM_THRESHOLD = 3

# Canon rules for what each resolution does to the map. CF 003 rules the
# killed branch only. The other three are open threads and are deliberately
# unimplemented. Do not fill these in without a Panel.
RESOLUTION_EFFECTS = {
    "killed": {
        "stillness_spread": True,
        "spread_step_on_resolve": 1,
    },
    "redeemed": {
        "stillness_spread": False,
        "counter_push": None,
        "awaiting_ruling": (
            "Is redemption's counter-push symmetrical with stillness-spread, "
            "or weaker? (CF 003 Part V, carried in CF 004.)"
        ),
    },
    "absorbed": {
        "awaiting_ruling": "Unspecified in corpus. CF 003 rules map consequence for killed only.",
    },
    "manipulated": {
        "awaiting_ruling": "Unspecified in corpus. CF 003 rules map consequence for killed only.",
    },
}

RegionData = Dict[str, Any]
SaveState = Dict[str, Any]


class UnruledCanon(Exception):
    """Raised when the code reaches a decision the project has not made yet.

    This is a feature. Silently picking a behaviour for an open thread is how
    a hook gets closed by accident.
    """


def load_region(path: str) -> RegionData:
    """Read authored region data from disk. Treat the result as read-only."""
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_save(path: str) -> SaveState:
    """Read a save state from disk."""
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def write_save(path: str, save: SaveState) -> None:
    """Write a save state to disk."""
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(save, handle, indent=2)


def new_save(regions: List[RegionData]) -> SaveState:
    """Build the start-of-game save state for the given authored regions.

    Current settlement ratings start at their authored base values; kills,
    resolutions and stillness all start at zero. This is the runtime half
    of what used to live in data/world_state.json.
    """
    save: SaveState = {
        "schema_version": 1,
        "global": {
            "gods_resolved": 0,
            "eclipse_armed": False,
            "eclipse_fired": False,
        },
        "regions": {},
    }
    for region in regions:
        kills: Dict[str, int] = {}
        for species_id in region["species"]:
            kills[species_id] = 0

        settlements: Dict[str, Any] = {}
        for settlement_id in region["settlements"]:
            authored = region["settlements"][settlement_id]
            settlements[settlement_id] = {
                "stability": authored["stability"],
                "prosperity": authored["prosperity"],
            }

        save["regions"][region["id"]] = {
            "god_resolution": "unresolved",
            "species_kills": kills,
            "stillness": {"step": 0, "stilled_nodes": []},
            "settlements": settlements,
        }
    return save


def record_kill(region: RegionData, save: SaveState, species_id: str, count: int = 1) -> SaveState:
    """Add kills to the region's species table and return the new save state.

    Feeds the affinity system and, later, the settlement-safety reactions:
    a heavily hunted region shows fewer attacks on locals.
    """
    region_id = region["id"]
    if species_id not in region["species"]:
        raise KeyError(f"{species_id} is not an authored species in {region_id}")
    new_state = copy.deepcopy(save)
    kills = new_state["regions"][region_id]["species_kills"]
    kills[species_id] = kills.get(species_id, 0) + count
    return new_state


def resolve_god(region: RegionData, save: SaveState, resolution: str) -> SaveState:
    """Apply a god resolution and return the new save state.

    This is the function Carry Forward 001 named as the build's first
    heartbeat. It does three things: records the resolution, updates the
    global counters that arm the Eclipse, and applies whatever map
    consequence the resolution has been ruled to have.

    Only ``killed`` has a ruled consequence (CF 003: stillness-spread).
    The other three raise ``UnruledCanon``.
    """
    if resolution not in RESOLUTIONS:
        raise ValueError(f"{resolution} is not one of {RESOLUTIONS}")

    region_id = region["id"]
    current = save["regions"][region_id]["god_resolution"]
    if current != "unresolved":
        raise ValueError(f"{region_id}'s god is already {current}")

    new_state = copy.deepcopy(save)
    new_state["regions"][region_id]["god_resolution"] = resolution

    resolved = new_state["global"]["gods_resolved"] + 1
    new_state["global"]["gods_resolved"] = resolved
    if resolved >= ECLIPSE_ARM_THRESHOLD:
        # Arming only. The rite fires on entry to an authored site, not here.
        new_state["global"]["eclipse_armed"] = True

    effects = RESOLUTION_EFFECTS[resolution]
    if "awaiting_ruling" in effects:
        raise UnruledCanon(f"{resolution}: {effects['awaiting_ruling']}")

    if effects.get("stillness_spread"):
        new_state = advance_stillness(
            region, new_state, steps=effects.get("spread_step_on_resolve", 1)
        )

    return new_state


def advance_stillness(region: RegionData, save: SaveState, steps: int = 1) -> SaveState:
    """Advance stillness outward from the god's anchor and return the new save state.

    Carry Forward 004 replaced the radius with an adjacency graph: stillness
    travels down watersheds, along roads and river courses, and is slowed by
    terrain. Each edge costs its ``resistance`` in steps, so a refuge sited
    uphill for distance is reached last — which is what it was sited for.

    A settlement reached by the spread swaps its current ratings to its
    authored degraded state. It does not receive a filter.
    """
    region_id = region["id"]
    new_state = copy.deepcopy(save)
    region_save = new_state["regions"][region_id]
    stillness = region_save["stillness"]
    stillness["step"] = stillness["step"] + steps

    reached = _nodes_within(region["adjacency"], region["god"]["anchor_node"], stillness["step"])
    for node_id in reached:
        if node_id in stillness["stilled_nodes"]:
            continue
        stillness["stilled_nodes"].append(node_id)
        authored = region["settlements"].get(node_id)
        if authored is None:
            continue  # the anchor itself, and any non-settlement node
        degraded = authored["degraded_state"]
        settlement = region_save["settlements"][node_id]
        settlement["stability"] = degraded["stability"]
        settlement["prosperity"] = degraded["prosperity"]

    return new_state


def _nodes_within(edges: List[Dict[str, Any]], origin: str, budget: int) -> List[str]:
    """Return every node reachable from origin within a resistance budget.

    Plain Dijkstra over a small hand-authored graph. Regions hold single
    figures of settlements, so cost does not matter and clarity does.
    """
    cost: Dict[str, int] = {origin: 0}
    changed = True
    while changed:
        changed = False
        for edge in edges:
            for start, end in ((edge["from"], edge["to"]), (edge["to"], edge["from"])):
                if start not in cost:
                    continue
                candidate = cost[start] + edge["resistance"]
                if end not in cost or candidate < cost[end]:
                    cost[end] = candidate
                    changed = True

    reached: List[str] = []
    for node_id in cost:
        if cost[node_id] <= budget:
            reached.append(node_id)
    return reached


def describe_region(region: RegionData, save: SaveState) -> str:
    """Human-readable snapshot. Debug rendering only — kept out of the logic."""
    region_save = save["regions"][region["id"]]
    stilled_nodes = region_save["stillness"]["stilled_nodes"]
    lines = [
        f"{region['display_name']} — god {region_save['god_resolution']}, "
        f"stillness step {region_save['stillness']['step']}"
    ]
    for settlement_id in region["settlements"]:
        authored = region["settlements"][settlement_id]
        current = region_save["settlements"][settlement_id]
        mark = "STILLED" if settlement_id in stilled_nodes else "      "
        lines.append(
            f"  {mark} {authored['display_name']:<12} "
            f"({authored['vintage']:<14}) "
            f"stab {current['stability']:>3}  prosp {current['prosperity']:>3}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    frostaris = load_region("data/regions/frostaris.json")
    save = new_save([frostaris])
    print(describe_region(frostaris, save))
    print()

    save = record_kill(frostaris, save, "ice_wolf", 12)
    save = resolve_god(frostaris, save, "killed")
    print(describe_region(frostaris, save))
    print()

    for _ in range(3):
        save = advance_stillness(frostaris, save)
    print(describe_region(frostaris, save))

    os.makedirs("saves", exist_ok=True)
    write_save("saves/world_slot1.json", save)
    print()
    print("Save state written to saves/world_slot1.json")
