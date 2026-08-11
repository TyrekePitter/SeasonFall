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
* Open threads raise instead of guessing. All four resolution types now
  have ruled map consequences, but the pattern remains: a future open
  ruling raises ``UnruledCanon``, and a ruled mechanic whose authored
  content does not exist yet raises ``UnauthoredContent``.
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

# Canon rules for what each resolution does to the map. All four branches
# are now ruled: killed and absorbed spread stillness, redeemed counter-pushes
# restoration, manipulated entrenches. A future open thread gets an
# "awaiting_ruling" entry here, and resolve_god raises UnruledCanon for it.
RESOLUTION_EFFECTS = {
    "killed": {
        "stillness_spread": True,
        "spread_step_on_resolve": 1,
    },
    "redeemed": {
        "stillness_spread": False,
        "counter_push": True,
    },
    "absorbed": {
        "stillness_spread": True,
        "spread_step_on_resolve": 1,
    },
    "manipulated": {
        "entrenchment": True,
    },
}

# Bumped to 2 when restoration and entrenchment state joined the save.
SAVE_SCHEMA_VERSION = 2

RegionData = Dict[str, Any]
SaveState = Dict[str, Any]


class UnruledCanon(Exception):
    """Raised when the code reaches a decision the project has not made yet.

    This is a feature. Silently picking a behaviour for an open thread is how
    a hook gets closed by accident.
    """


class UnauthoredContent(Exception):
    """Raised when a ruled mechanic needs authored content that does not exist.

    Sibling of UnruledCanon: there the ruling is missing, here the ruling
    exists but a region's content has not been authored to support it.
    Defaulting would close an authoring decision by accident.
    """


def load_region(path: str) -> RegionData:
    """Read authored region data from disk. Treat the result as read-only."""
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_save(path: str) -> SaveState:
    """Read a save state from disk.

    Raises ``ValueError`` for a save written under a different schema
    version, rather than failing later with an incidental KeyError deep
    inside a transition. There is no migration path; old saves are dev
    artifacts and are started over with ``new_save``.
    """
    with open(path, "r", encoding="utf-8") as handle:
        save = json.load(handle)
    version = save.get("schema_version")
    if version != SAVE_SCHEMA_VERSION:
        raise ValueError(
            f"{path}: save schema version {version} is not supported "
            f"(this build reads {SAVE_SCHEMA_VERSION}); start over with new_save"
        )
    return save


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
        "schema_version": SAVE_SCHEMA_VERSION,
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
            "restoration": {"step": 0, "restored_nodes": []},
            "entrenched": False,
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

    All four resolutions are ruled: killed and absorbed spread stillness,
    redeemed counter-pushes restoration, and manipulated entrenches —
    raising ``UnauthoredContent`` while the region's entrenched states are
    not authored yet. A future open thread's ``awaiting_ruling`` entry in
    ``RESOLUTION_EFFECTS`` raises ``UnruledCanon`` here.
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

    if effects.get("counter_push"):
        new_state = advance_restoration(region, new_state, steps=1)

    if effects.get("entrenchment"):
        new_state = entrench_region(region, new_state)

    return new_state


def advance_stillness(region: RegionData, save: SaveState, steps: int = 1) -> SaveState:
    """Advance stillness outward from the god's anchor and return the new save state.

    Carry Forward 004 replaced the radius with an adjacency graph: stillness
    travels down watersheds, along roads and river courses, and is slowed by
    terrain. Each edge costs its ``resistance`` in steps, so a refuge sited
    uphill for distance is reached last — which is what it was sited for.

    A settlement reached by the spread swaps its current ratings to its
    authored degraded state. It does not receive a filter.

    Restored nodes are immune to stillness and block it from travelling
    through them; a restored anchor seals the spread at its source.
    """
    region_id = region["id"]
    new_state = copy.deepcopy(save)
    region_save = new_state["regions"][region_id]
    stillness = region_save["stillness"]
    stillness["step"] = stillness["step"] + steps

    reached = _nodes_within(
        region["adjacency"],
        region["god"]["anchor_node"],
        stillness["step"],
        region_save["restoration"]["restored_nodes"],
    )
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


def advance_restoration(region: RegionData, save: SaveState, steps: int = 1) -> SaveState:
    """Advance restoration outward from the god's anchor and return the new save state.

    Redemption's counter-push. Restoration walks the same adjacency graph
    as stillness and the two block each other symmetrically: a stilled node
    cannot be restored and blocks restoration's travel, just as a restored
    node is immune to stillness and blocks its travel. Whichever force
    claims the anchor first seals the other out of the region.

    Restoration never changes a settlement's ratings. It protects; it does
    not repair.
    """
    region_id = region["id"]
    new_state = copy.deepcopy(save)
    region_save = new_state["regions"][region_id]
    restoration = region_save["restoration"]
    restoration["step"] = restoration["step"] + steps

    stilled_nodes = region_save["stillness"]["stilled_nodes"]
    reached = _nodes_within(
        region["adjacency"],
        region["god"]["anchor_node"],
        restoration["step"],
        stilled_nodes,
    )
    for node_id in reached:
        if node_id in restoration["restored_nodes"]:
            continue
        if node_id in stilled_nodes:
            continue  # a stilled node cannot be restored
        restoration["restored_nodes"].append(node_id)

    return new_state


def entrench_region(region: RegionData, save: SaveState) -> SaveState:
    """Apply every settlement's authored entrenched state and return the new save state.

    Manipulation's map consequence. Each settlement swaps its current
    ratings to its authored ``entrenched_state``.

    Raises ``UnauthoredContent`` if any settlement lacks an authored
    ``entrenched_state`` — inventing ratings here would close an authoring
    decision by accident. The input save is untouched on the raise.
    """
    region_id = region["id"]
    missing: List[str] = []
    for settlement_id in region["settlements"]:
        if "entrenched_state" not in region["settlements"][settlement_id]:
            missing.append(settlement_id)
    if missing:
        raise UnauthoredContent(
            f"{region_id}: entrenched_state is not authored for: " + ", ".join(missing)
        )

    new_state = copy.deepcopy(save)
    region_save = new_state["regions"][region_id]
    region_save["entrenched"] = True
    for settlement_id in region["settlements"]:
        entrenched = region["settlements"][settlement_id]["entrenched_state"]
        settlement = region_save["settlements"][settlement_id]
        settlement["stability"] = entrenched["stability"]
        settlement["prosperity"] = entrenched["prosperity"]

    return new_state


def _nodes_within(edges: List[Dict[str, Any]], origin: str, budget: int, blocked: List[str]) -> List[str]:
    """Return every node reachable from origin within a resistance budget.

    Plain Dijkstra over a small hand-authored graph. Regions hold single
    figures of settlements, so cost does not matter and clarity does.

    Blocked nodes are never entered: they take no cost, so no path may
    continue through them, and a blocked origin reaches nothing at all.
    """
    if origin in blocked:
        return []

    cost: Dict[str, int] = {origin: 0}
    changed = True
    while changed:
        changed = False
        for edge in edges:
            for start, end in ((edge["from"], edge["to"]), (edge["to"], edge["from"])):
                if start not in cost:
                    continue
                if end in blocked:
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
    restored_nodes = region_save["restoration"]["restored_nodes"]
    lines = [
        f"{region['display_name']} — god {region_save['god_resolution']}, "
        f"stillness step {region_save['stillness']['step']}"
    ]
    for settlement_id in region["settlements"]:
        authored = region["settlements"][settlement_id]
        current = region_save["settlements"][settlement_id]
        if settlement_id in stilled_nodes:
            mark = "STILLED"
        elif settlement_id in restored_nodes:
            mark = "RESTORED"
        elif region_save["entrenched"]:
            mark = "ENTRENCHED"
        else:
            mark = "      "
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

    print()
    print("redeemed — the counter-push seals stillness at its source:")
    save = new_save([frostaris])
    save = resolve_god(frostaris, save, "redeemed")
    for _ in range(3):
        save = advance_stillness(frostaris, save)
    print(describe_region(frostaris, save))

    print()
    print("absorbed — same map consequence as killed:")
    save = new_save([frostaris])
    save = resolve_god(frostaris, save, "absorbed")
    print(describe_region(frostaris, save))

    print()
    print("manipulated — entrenchment awaits authored content:")
    save = new_save([frostaris])
    try:
        save = resolve_god(frostaris, save, "manipulated")
    except UnauthoredContent as error:
        print(f"UnauthoredContent: {error}")
