"""Seasonfall — world-state layer test harness.

Run from the repo root:

    python scripts/test_world_state.py

This locks the layer's current behaviour so that refactors have to prove
themselves. The demo block in ``world_state.py`` prints; it does not assert,
which means a regression there is silent. This file fails loudly instead.

Every test names the ruling it protects. If a test fails, either the code
broke or a ruling changed — and if it is the second, the test is what forces
the change to be deliberate.

Two known defects are recorded at the end as findings rather than failures.
They are open work, not regressions, and the harness reports them so they
cannot be quietly forgotten. A third — new_save snapshotting authored
ratings, CF 005's save-migration thread — was closed by CF 006 Part III's
delta storage and is now asserted fixed in section 12.

CF 006 Part III note: the storage rulings changed — the save records
divergence only, ratings resolve on read via settlement_state and
settlement_ratings, and the schema moved to v3. The checks below that read
ratings out of the save or named schema v2 were re-expressed against the
new storage with their labels, expected values and rulings unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import world_state as ws  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
REGION_PATH = REPO_ROOT / "data" / "regions" / "frostaris.json"

# Authored content for the ratings helper. Read-only, like everywhere else.
REGION = ws.load_region(str(REGION_PATH))

PASSED = 0
FINDINGS = []


def check(label: str, condition: bool, detail: str = "") -> None:
    """Assert and count. Fails the run on the first broken expectation."""
    global PASSED
    if not condition:
        raise AssertionError(f"{label}{(': ' + detail) if detail else ''}")
    PASSED += 1
    print(f"  ok  {label}")


def section(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def stilled(save, region_id="frostaris"):
    return sorted(save["regions"][region_id]["stillness"]["stilled_nodes"])


def restored(save, region_id="frostaris"):
    return sorted(save["regions"][region_id]["restoration"]["restored_nodes"])


def ratings(save, settlement_id, region_id="frostaris"):
    # CF 006 Part III: ratings are no longer stored in the save; they
    # resolve on read from the divergence record plus authored content.
    s = ws.settlement_ratings(REGION, save, settlement_id)
    return (s["stability"], s["prosperity"])


def main() -> int:
    region = ws.load_region(REGION_PATH)
    print(f"Region: {region['display_name']} "
          f"({len(region['settlements'])} settlements, "
          f"{len(region['adjacency'])} edges)")

    # ------------------------------------------------------------------ setup
    section("1. new_save — start of game")
    base = ws.new_save([region])
    check("schema version is 3", base["schema_version"] == ws.SAVE_SCHEMA_VERSION)
    check("god starts unresolved",
          base["regions"]["frostaris"]["god_resolution"] == "unresolved")
    check("nothing stilled at start", stilled(base) == [])
    check("eclipse not armed", base["global"]["eclipse_armed"] is False)
    check("Vaerholt starts at authored base", ratings(base, "vaerholt") == (70, 55))
    check("save stores no settlement ratings — divergence only (CF 006 III)",
          "settlements" not in base["regions"]["frostaris"])

    # ---------------------------------------------------------------- purity
    section("2. Purity — transitions never mutate their input")
    before = ws.new_save([region])
    snapshot = repr(before)
    _ = ws.resolve_god(region, before, "killed")
    check("resolve_god leaves the input save untouched", repr(before) == snapshot)
    _ = ws.advance_stillness(region, before, 3)
    check("advance_stillness leaves the input save untouched",
          repr(before) == snapshot)
    _ = ws.record_kill(region, before, "ice_wolf", 5)
    check("record_kill leaves the input save untouched", repr(before) == snapshot)
    _ = ws.settlement_ratings(region, before, "vaerholt")
    check("settlement_ratings leaves the input save untouched",
          repr(before) == snapshot)

    # ----------------------------------------------------- weighted spread
    section("3. KILLED — weighted spread order (D13, CF 004)")
    save = ws.resolve_god(region, ws.new_save([region]), "killed")
    check("resolve applies one spread step",
          save["regions"]["frostaris"]["stillness"]["step"] == 1)
    check("step 1 reaches the anchor and Stillhaven only",
          stilled(save) == ["astrael_anchor", "stillhaven"],
          str(stilled(save)))
    check("Stillhaven took its degraded ratings",
          ratings(save, "stillhaven") == (80, 5))
    check("Vaerholt is untouched at step 1", ratings(save, "vaerholt") == (70, 55))

    save = ws.advance_stillness(region, save)      # step 2
    check("step 2 reaches Stonecross", "stonecross" in stilled(save))
    save = ws.advance_stillness(region, save)      # step 3
    check("step 3 reaches Vaerholt", "vaerholt" in stilled(save))
    check("Vaerholt degraded", ratings(save, "vaerholt") == (25, 10))
    save = ws.advance_stillness(region, save)      # step 4
    check("step 4 reaches nothing new — the escarpment costs 3",
          "uphearth" not in stilled(save) and "greyfold" not in stilled(save))
    save = ws.advance_stillness(region, save)      # step 5
    check("step 5 reaches both refuges last",
          "uphearth" in stilled(save) and "greyfold" in stilled(save))

    check("devotion vintage fell first, refuge vintage fell last",
          stilled(ws.resolve_god(region, ws.new_save([region]), "killed"))
          == ["astrael_anchor", "stillhaven"])

    # -------------------------------------------------------------- absorbed
    section("4. ABSORBED — identical map consequence (D15)")
    killed = ws.advance_stillness(
        region, ws.resolve_god(region, ws.new_save([region]), "killed"), 4)
    absorbed = ws.advance_stillness(
        region, ws.resolve_god(region, ws.new_save([region]), "absorbed"), 4)
    check("absorbed produces the same stilled set", stilled(killed) == stilled(absorbed))
    same_ratings = True
    for settlement_id in region["settlements"]:
        if ratings(killed, settlement_id) != ratings(absorbed, settlement_id):
            same_ratings = False
    check("absorbed produces the same settlement ratings", same_ratings)
    check("only the resolution flag differs",
          absorbed["regions"]["frostaris"]["god_resolution"] == "absorbed")

    # -------------------------------------------------------------- redeemed
    section("5. REDEEMED — the anchor seals (R10a, R10b)")
    red = ws.resolve_god(region, ws.new_save([region]), "redeemed")
    check("resolve applies one restoration step",
          red["regions"]["frostaris"]["restoration"]["step"] == 1)
    check("restoration claims the anchor", "astrael_anchor" in restored(red))
    check("nothing stilled", stilled(red) == [])

    sealed = ws.advance_stillness(region, red, 5)
    check("stillness cannot spread from a restored anchor", stilled(sealed) == [],
          str(stilled(sealed)))
    check("settlement ratings unchanged by restoration",
          ratings(sealed, "vaerholt") == (70, 55))

    # ------------------------------------------------------ symmetric block
    section("6. BLOCKING — symmetric (R10b)")
    blocked = ws.resolve_god(region, ws.new_save([region]), "killed")
    blocked = ws.advance_stillness(region, blocked, 1)
    blocked = ws.advance_restoration(region, blocked, 5)
    check("restoration cannot start from a stilled anchor", restored(blocked) == [],
          str(restored(blocked)))
    check("a stilled node stays stilled", "stillhaven" in stilled(blocked))

    # ----------------------------------------------------------- manipulated
    section("7. MANIPULATED — entrenchment raises the queue (D16, P2)")
    raised = False
    message = ""
    try:
        ws.resolve_god(region, ws.new_save([region]), "manipulated")
    except ws.UnauthoredContent as exc:
        raised = True
        message = str(exc)
    check("entrenchment raises UnauthoredContent", raised)
    for settlement_id in region["settlements"]:
        check(f"queue names {settlement_id}", settlement_id in message)

    # --------------------------------------------------------------- eclipse
    section("8. ECLIPSE ARMING — god count, any type (D5)")
    armed = ws.new_save([region])
    armed["global"]["gods_resolved"] = 2
    armed = ws.resolve_god(region, armed, "redeemed")
    check("third resolution arms the Eclipse",
          armed["global"]["eclipse_armed"] is True)
    check("arming does not fire it", armed["global"]["eclipse_fired"] is False)

    # ----------------------------------------------------------------- kills
    section("9. KILL TABLE")
    hunted = ws.record_kill(region, ws.new_save([region]), "ice_wolf", 12)
    hunted = ws.record_kill(region, hunted, "ice_wolf", 3)
    check("kills accumulate",
          hunted["regions"]["frostaris"]["species_kills"]["ice_wolf"] == 15)
    rejected = False
    try:
        ws.record_kill(region, hunted, "not_a_species")
    except KeyError:
        rejected = True
    check("unauthored species rejected", rejected)

    # ------------------------------------------------------------ guardrails
    section("10. GUARDRAILS")
    twice = False
    try:
        once = ws.resolve_god(region, ws.new_save([region]), "killed")
        ws.resolve_god(region, once, "redeemed")
    except ValueError:
        twice = True
    check("a god cannot be resolved twice — resolution is permanent", twice)

    bad = False
    try:
        ws.resolve_god(region, ws.new_save([region]), "forgiven")
    except ValueError:
        bad = True
    check("unknown resolution type rejected", bad)

    # ---------------------------------------------------------------- schema
    section("11. SAVE SCHEMA")
    tmp = REPO_ROOT / "saves" / "_harness_tmp.json"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    stale = ws.new_save([region])
    stale["schema_version"] = 1
    ws.write_save(str(tmp), stale)
    old_rejected = False
    try:
        ws.load_save(str(tmp))
    except ValueError:
        old_rejected = True
    check("older save schema is rejected, not migrated", old_rejected)
    stale_v2 = ws.new_save([region])
    stale_v2["schema_version"] = 2
    ws.write_save(str(tmp), stale_v2)
    v2_rejected = False
    try:
        ws.load_save(str(tmp))
    except ValueError:
        v2_rejected = True
    check("v2 stored-ratings schema is rejected, not migrated (CF 006 III)",
          v2_rejected)
    ws.write_save(str(tmp), ws.new_save([region]))
    check("current save schema round-trips",
          ws.load_save(str(tmp))["schema_version"] == 3)
    tmp.unlink()

    # ----------------------------------------------------- delta storage
    section("12. DELTA STORAGE — resolution from divergence (CF 006 III)")

    grown = ws.load_region(REGION_PATH)
    grown["settlements"]["newholt"] = {
        "display_name": "Newholt", "vintage": "refuge", "type": "outpost",
        "stability": 30, "prosperity": 10, "siting_note": "added after the save",
        "degraded_state": {"stability": 5, "prosperity": 0, "text": "-"},
    }
    old_save = ws.new_save([region])  # written before Newholt was authored
    check("a settlement authored after the save resolves as base — no migration",
          ws.settlement_state(grown, old_save, "newholt") == "base")
    newholt = ws.settlement_ratings(grown, old_save, "newholt")
    check("its ratings are the authored base values",
          (newholt["stability"], newholt["prosperity"]) == (30, 10))

    forced = ws.new_save([region])
    forced["regions"]["frostaris"]["entrenched"] = True
    unauthored_raised = False
    try:
        ws.settlement_ratings(region, forced, "vaerholt")
    except ws.UnauthoredContent:
        unauthored_raised = True
    check("an unauthored state raises at resolution rather than rendering",
          unauthored_raised)

    # --------------------------------------------------------------- findings
    section("FINDINGS — open work, not regressions")

    r1 = ws.resolve_god(region, ws.new_save([region]), "redeemed")
    if ratings(r1, "vaerholt") == ratings(ws.new_save([region]), "vaerholt"):
        FINDINGS.append(
            "advance_restoration claims nodes but never changes ratings, so a "
            "restored settlement renders identically to an untouched one. R10's "
            "counter-push has no artifact, which P2 forbids. Needs restored_state "
            "as a fourth authored state alongside base, degraded and entrenched."
        )

    sh = region["settlements"]["stillhaven"]
    if sh["degraded_state"]["stability"] == sh["stability"]:
        FINDINGS.append(
            "Stillhaven's degraded_state holds stability at its base value and "
            "drops only prosperity, with text saying nothing changes. That is "
            "entrenchment (D16), not stillness. CF 005 Part XI recorded this and "
            "it is still in the file. The prose belongs in entrenched_state."
        )

    for i, finding in enumerate(FINDINGS, 1):
        print(f"  {i}. {finding}")

    print(f"\n{PASSED} checks passed, {len(FINDINGS)} finding(s) recorded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())