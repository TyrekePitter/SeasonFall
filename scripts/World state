"""Reactive world-state layer for Seasonfall.

This module is the demonstration piece of the Python build (Carry Forward 001):
world state changes as a consequence of player *outcomes*, not combat math.
Combat is stubbed. Nothing here computes damage.

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
from typing import Any, Dict, List

# Game Bible 13.1, promoted to a system enum by Carry Forward 001.
RESOLUTIONS = ("killed", "redeemed", "absorbed", "manipulated")

# Carry Forward 003: the third god resolved arms the Eclipse, any resolution type.
ECLIPSE_ARM_THRESHOLD = 3

WorldState = Dict[str, Any]


class UnruledCanon(Exception):
    """Raised when the code reaches a decision the project has not made yet.

    This is a feature. Silently picking a behaviour for an open thread is how
    a hook gets closed by accident.
    """


def load_world_state(path: str) -> WorldState:
    """Read a world state from disk."""
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def save_world_state(path: str, state: WorldState) -> None:
    """Write a world state to disk."""
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)


def record_kill(state: WorldState, region_id: str, species_id: str, count: int = 1) -> WorldState:
    """Add kills to a region's species table and return the new state.

    Feeds the affinity system and, later, the settlement-safety reactions:
    a heavily hunted region shows fewer attacks on locals.
    """
    new_state = copy.deepcopy(state)
    kills = new_state["regions"][region_id]["species_kills"]
    if species_id not in kills:
        raise KeyError(f"{species_id} is not an authored species in {region_id}")
    kills[species_id] = kills[species_id] + count
    return new_state


def resolve_god(state: WorldState, region_id: str, resolution: str) -> WorldState:
    """Apply a god resolution and return the region's new state.

    This is the function Carry Forward 001 named as the build's first
    heartbeat. It does three things: records the resolution, updates the
    global counters that arm the Eclipse, and applies whatever map
    consequence the resolution has been ruled to have.

    Only ``killed`` has a ruled consequence (CF 003: stillness-spread).
    The other three raise ``UnruledCanon``.
    """
    if resolution not in RESOLUTIONS:
        raise ValueError(f"{resolution} is not one of {RESOLUTIONS}")

    region = state["regions"][region_id]
    if region["god"]["resolution"] != "unresolved":
        raise ValueError(f"{region_id}'s god is already {region['god']['resolution']}")

    new_state = copy.deepcopy(state)
    new_region = new_state["regions"][region_id]
    new_region["god"]["resolution"] = resolution

    resolved = new_state["global"]["gods_resolved"] + 1
    new_state["global"]["gods_resolved"] = resolved
    if resolved >= ECLIPSE_ARM_THRESHOLD:
        # Arming only. The rite fires on entry to an authored site, not here.
        new_state["global"]["eclipse_armed"] = True

    effects = new_state["resolution_effects"][resolution]
    if "awaiting_ruling" in effects:
        raise UnruledCanon(f"{resolution}: {effects['awaiting_ruling']}")

    if effects.get("stillness_spread"):
        new_state = advance_stillness(
            new_state, region_id, steps=effects.get("spread_step_on_resolve", 1)
        )

    return new_state


def advance_stillness(state: WorldState, region_id: str, steps: int = 1) -> WorldState:
    """Advance stillness outward from the god's anchor and return the new state.

    Carry Forward 004 replaced the radius with an adjacency graph: stillness
    travels down watersheds, along roads and river courses, and is slowed by
    terrain. Each edge costs its ``resistance`` in steps, so a refuge sited
    uphill for distance is reached last — which is what it was sited for.

    A settlement reached by the spread swaps to its authored degraded state.
    It does not receive a filter.
    """
    new_state = copy.deepcopy(state)
    region = new_state["regions"][region_id]
    stillness = region["stillness"]
    stillness["step"] = stillness["step"] + steps

    reached = _nodes_within(region["adjacency"], stillness["origin_node"], stillness["step"])
    for node_id in reached:
        if node_id in stillness["stilled_nodes"]:
            continue
        stillness["stilled_nodes"].append(node_id)
        settlement = region["settlements"].get(node_id)
        if settlement is None:
            continue  # the anchor itself, and any non-settlement node
        degraded = settlement["degraded_state"]
        settlement["stability"] = degraded["stability"]
        settlement["prosperity"] = degraded["prosperity"]
        settlement["stilled"] = True

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


def describe_region(state: WorldState, region_id: str) -> str:
    """Human-readable snapshot. Debug rendering only — kept out of the logic."""
    region = state["regions"][region_id]
    lines = [
        f"{region['display_name']} — god {region['god']['resolution']}, "
        f"stillness step {region['stillness']['step']}"
    ]
    for settlement_id in region["settlements"]:
        settlement = region["settlements"][settlement_id]
        mark = "STILLED" if settlement["stilled"] else "      "
        lines.append(
            f"  {mark} {settlement['display_name']:<12} "
            f"({settlement['vintage']:<14}) "
            f"stab {settlement['stability']:>3}  prosp {settlement['prosperity']:>3}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    world = load_world_state("data/world_state.json")
    print(describe_region(world, "frostaris"))
    print()

    world = record_kill(world, "frostaris", "ice_wolf", 12)
    world = resolve_god(world, "frostaris", "killed")
    print(describe_region(world, "frostaris"))
    print()

    for _ in range(3):
        world = advance_stillness(world, "frostaris")
    print(describe_region(world, "frostaris"))
