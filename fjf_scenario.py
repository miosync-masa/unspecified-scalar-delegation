#!/usr/bin/env python3
"""
Read the scenario YAML and build prompts, plus a check against the retired scripts

The stimuli live in scenario_rescue.yaml and the instrument in codebook_v1.yaml. This module
only reads the former and builds the text.

The retired fjf_q1-q4 embedded prompts in code. Before replacing them, we checked that the text
built from the YAML matches the old text character for character. A mismatch means the design
is incomplete, and the check stops there.

Usage
  python3 fjf_scenario.py --verify          check identity with the retired scripts
  python3 fjf_scenario.py --show q1         print the prompts of design q1
  python3 fjf_scenario.py --lint            lint the stimuli (length imbalance, leaking words)
"""

import argparse
import sys
import os

import yaml

SCENARIO = "scenario_rescue.yaml"


def load(path=SCENARIO):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------- building

def system_text(sc, world):
    w = sc["worlds"][world]
    return "".join(sc["systems"][k] for k in w["system"])


def turn_text(sc, turn_id, world="solo", cell=None, variant=None,
              first=None, second=None, qn=None):
    """Return the text of one turn."""
    turn = sc["turns"][turn_id]

    if "variants" in turn:
        if variant is None:
            raise ValueError(f"{turn_id} needs a variant")
        spec = turn["variants"][variant]
        tname = spec["template"]
    else:
        spec = turn
        tname = turn["template"]
        byw = turn.get("template_by_world") or {}
        tname = byw.get(world, tname)

    body = sc["templates"][tname]["body"]

    # slots (north and south)
    if "{north}" in body:
        if cell is None:
            raise ValueError(f"{turn_id} needs a cell")
        n, s = cell
        body = body.replace("{north}", sc["slots"]["north"][n]["text"])
        body = body.replace("{south}", sc["slots"]["south"][s]["text"])

    # question number (only for designs presented with numbering)
    if "{qn}" in body:
        if qn is None:
            raise ValueError(f"{turn_id} needs qn")
        body = body.replace("{qn}", str(qn))

    # world-specific paragraph
    if "{extra}" in body:
        extra = sc["worlds"][world].get("extra")
        body = body.replace("{extra}", extra if extra is not None else "")

    # claim for the audit
    if "{claim}" in body:
        cl = sc["claims"][spec["claim"]]
        text = cl["text"]
        if cl.get("requires_flip"):
            if first is None or second is None:
                raise ValueError("true-type claims need first/second")
            if first == second or "?" in (first, second):
                return None          # cannot be built for a history without a reversal
            labels = cl["labels"]
            text = text.replace("{first_label}", labels[first])
            text = text.replace("{second_label}", labels[second])
        body = body.replace("{claim}", text)

    # shared scene text (only for designs reusing one scene verbatim across turns)
    if "{scene}" in body:
        body = body.replace("{scene}", sc["templates"]["scene"]["body"])

    # messenger arrival and order
    if "{arrival}" in body:
        body = body.replace("{arrival}", sc["arrivals"][spec["arrival"]])
    if "{order}" in body:
        body = body.replace("{order}", sc["orders"][spec["order"]])

    return body


# ---------------------------------------------------------------- verification

def verify(sc):
    """Does the text match the retired scripts' prompts character for character?"""
    # The old scripts are retired to superseded/ and no longer on any execution path.
    # Only this check refers to them (as the reference to compare against).
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "superseded"))
    try:
        import fjf_q1, fjf_q2, fjf_q3, fjf_q4
    except ImportError as e:
        print(f"reference scripts not found (check superseded/): {e}")
        return

    ok = bad = 0

    def check(label, got, want):
        nonlocal ok, bad
        if got == want:
            ok += 1
            return
        bad += 1
        print(f"  ✗ {label}")
        if got is None:
            print("      the YAML side returned None")
            return
        for i, (a, b) in enumerate(zip(got, want)):
            if a != b:
                print(f"      differs from character {i}")
                print(f"      YAML : ...{got[max(0,i-25):i+25]!r}")
                print(f"      old  : ...{want[max(0,i-25):i+25]!r}")
                break
        else:
            print(f"      lengths differ: YAML {len(got)} / old {len(want)}")

    print("=== system instructions ===")
    for world in fjf_q1.SYSTEM_INSTRUCTION:
        check(f"system[{world}]", system_text(sc, world),
              fjf_q1.SYSTEM_INSTRUCTION[world])

    print("=== decision turns (all worlds x all cells) ===")
    for world in fjf_q1.SYSTEM_INSTRUCTION:
        for n in sc["slots"]["north"]:
            for s in sc["slots"]["south"]:
                check(f"decision[{world}/{n}{s}]",
                      turn_text(sc, "decision", world=world, cell=(n, s)),
                      fjf_q1.build_prompt(n, s, "none", world))

    print("=== consistency turn ===")
    check("consistency", turn_text(sc, "consistency"), fjf_q2.CONSISTENCY_PROMPT)

    print("=== after sunset ===")
    check("sunset", turn_text(sc, "sunset"), fjf_q3._STATIC_PROBES["none"])
    check("sunset_self", turn_text(sc, "sunset_self"), fjf_q3._STATIC_PROBES["self"])
    check("sunset(q4)", turn_text(sc, "sunset"), fjf_q4.SUNSET_PROMPT)

    print("=== record audit ===")
    for v in ("neutral_false", "adversary_false"):
        check(f"audit[{v}]", turn_text(sc, "audit", variant=v),
              fjf_q3._STATIC_PROBES[v])
    for v in ("neutral_true", "adversary_true"):
        check(f"audit[{v}]", turn_text(sc, "audit", variant=v),
              fjf_q3._STATIC_PROBES[v])

    print("=== second messenger ===")
    for v in fjf_q4.PROBES:
        check(f"order[{v}]", turn_text(sc, "order", variant=v), fjf_q4.PROBES[v])

    print(f"\nmatch {ok} / mismatch {bad}")
    return bad == 0


# ---------------------------------------------------------------- lint

def mesh(sc, cb_path="codebook_v1.yaml"):
    """Check the fit between what a turn elicits and what a variable requires.

    The pipeline runs variable design -> scenario and question wording -> response -> instrument.
    When agreement does not improve, looking only downstream cannot trace an upstream
    mismatch. This is the upstream check (codebook I19).

    Three levels: intersecting elicits is OK; only permits is risky (whether it appears
    depends on how the subject narrates); intersecting neither is a design error.
    """
    cb = yaml.safe_load(open(cb_path, encoding="utf-8"))
    print(f"\n=== fit check (codebook v{cb['version']}) ===")
    out, risk, intended = [], [], []
    for tid, t in sc["turns"].items():
        el = set(t.get("elicits") or [])
        pm = set(t.get("permits") or [])
        q = t.get("codebook_question")
        if not el:
            out.append((tid, None, "elicits not declared"))
            continue
        for name, spec in cb["variables"].items():
            if q not in spec.get("questions", []):
                continue
            req = set(spec.get("requires") or [])
            if not req:
                out.append((tid, name, "requires not declared"))
            elif req & el:
                continue
            elif req & pm:
                risk.append((tid, name, sorted(req), sorted(el), sorted(pm)))
            elif spec.get("mismatch_note"):
                intended.append((tid, name, sorted(req), sorted(el)))
            else:
                out.append((tid, name,
                            f"requires {sorted(req)} intersects neither elicits {sorted(el)} / "
                            f"permits {sorted(pm)}"))
    if out:
        print(f"  ★ {len(out)} design errors — the stimulus does not elicit that information")
        for tid, name, why in out:
            print(f"    turn {tid}" + (f" / {name}" if name else "") + f": {why}")
    else:
        print("  no design errors")
    if risk:
        print(f"\n  ! {len(risk)} risky — in permits but not asked directly. "
              "Whether it appears depends on narration, so check empirically")
        for tid, name, req, el, pm in risk:
            print(f"    turn {tid} / {name}: requires {req}（elicits {el}）")
    if intended:
        print(f"\n  ○ {len(intended)} intended mismatches — measured on a turn that does not elicit it, "
              "to measure spontaneity (mismatch_note present)")
        for tid, name, req, el in intended:
            print(f"    turn {tid} / {name}: requires {req}（elicits {el}）")
    byq = {}
    for tid, t in sc["turns"].items():
        byq.setdefault(t.get("codebook_question"), []).append(
            (tid, tuple(sorted(t.get("elicits") or []))))
    for q, lst in byq.items():
        if len({e for _, e in lst}) > 1:
            print(f"\n  ★ variable group {q} mixes turns that ask for different things directly. "
                  "Split the group")
            for tid, e in lst:
                print(f"      {tid}: elicits {list(e)}")
    return out, risk, intended


def lint(sc):
    print("=== slot lengths ===")
    for side in ("north", "south"):
        print(f"  {side}")
        for k, v in sc["slots"][side].items():
            actual = len(v["text"])
            flag = "" if actual == v.get("chars") else f"  !! chars={v.get('chars')} but actually {actual}"
            print(f"    {k:3s} {actual:3d} chars  {v['text']}{flag}")

    print("\n=== length differences of south slots (confounds other than the attribute) ===")
    s = sc["slots"]["south"]
    base = len(s["A"]["text"])
    for k, v in s.items():
        d = len(v["text"]) - base
        mark = "  <- large difference from A" if abs(d) >= 7 else ""
        print(f"    {k:3s} vs A {d:+3d} chars  guilt={v.get('guilt')}{mark}")
    print("    Comparisons with unequal lengths cannot separate the attribute effect from the amount of description.")
    print("    designs.q1_length_control adds A2 to separate them.")

    print("\n=== do audit claims reuse words from the stimulus? ===")
    # An audit claim quoting words from the task text touches I3 (prompt words leaking)
    dec = turn_text(sc, "decision", world="solo", cell=("N", "A"))
    for cid, cl in sc["claims"].items():
        shared = [w for w in ("北の塔", "南の塔", "伝令", "日没", "国王陛下")
                  if w in cl["text"] and w in dec]
        if shared:
            print(f"    {cid}: words shared with the task text {shared}")
    print("    Audit claims naturally contain task words, but these words")
    print("    must not be used as cues for judgment (codebook I3).")

    print("\n=== turns vs instrument ===")
    try:
        cb = yaml.safe_load(open("codebook_v1.yaml", encoding="utf-8"))
        known = {q for v in cb["variables"].values()
                 for q in v.get("questions", [])}
    except Exception as e:
        print(f"    could not read codebook_v1.yaml: {e}")
        known = set()
    for tid, t in sc["turns"].items():
        q = t.get("codebook_question")
        mark = "" if (not known or q in known) else "  !! no such variable in the codebook"
        print(f"    {tid:14s} -> {q}{mark}")
    if known:
        missing = sorted(known - {t.get("codebook_question")
                                 for t in sc["turns"].values()})
        if missing:
            print(f"    variable groups used by no turn: {missing}")


def check(sc):
    """Check the scenario's own structure: broken references, unused definitions, design defects.

    --verify checks "does it produce the same text as the old code"; this checks
    "is the design coherent". They are separate checks.
    """
    err, warn = [], []

    T, SL, TP = sc["turns"], sc["slots"], sc["templates"]
    CL, AR, OR = sc.get("claims", {}), sc.get("arrivals", {}), sc.get("orders", {})
    W, D = sc["worlds"], sc["designs"]

    used_t, used_tp, used_cl, used_ar, used_or = set(), set(), set(), set(), set()
    used_slot = {"north": set(), "south": set()}
    used_w = set()

    # --- worlds
    for w, spec in W.items():
        for k in spec["system"]:
            if k not in sc["systems"]:
                err.append(f"worlds.{w}.system refers to undefined systems.{k}")

    # --- turns
    for tid, t in T.items():
        qs = t.get("codebook_question")
        if not qs:
            err.append(f"turns.{tid} has no codebook_question")
        variants = t.get("variants")
        specs = list(variants.values()) if variants else [t]
        for spec in specs:
            tn = spec.get("template")
            if tn is None:
                err.append(f"turns.{tid} has no template")
                continue
            if tn not in TP:
                err.append(f"turns.{tid} refers to undefined templates.{tn}")
            else:
                used_tp.add(tn)
            for key, pool, bag, label in (("claim", CL, used_cl, "claims"),
                                          ("arrival", AR, used_ar, "arrivals"),
                                          ("order", OR, used_or, "orders")):
                if key in spec:
                    if spec[key] not in pool:
                        err.append(f"turns.{tid} refers to undefined {label}.{spec[key]}")
                    else:
                        bag.add(spec[key])
        for w, tn in (t.get("template_by_world") or {}).items():
            if w not in W:
                err.append(f"turns.{tid}.template_by_world refers to undefined world {w}")
            if tn not in TP:
                err.append(f"turns.{tid}.template_by_world refers to undefined template {tn}")
            else:
                used_tp.add(tn)
        # are the placeholders the template requires filled?
        for spec in specs:
            tn = spec.get("template")
            if tn not in TP:
                continue
            body = TP[tn]["body"]
            if "{claim}" in body and "claim" not in spec:
                err.append(f"turns.{tid}: {tn} requires claim but none is given")
            if "{arrival}" in body and "arrival" not in spec:
                err.append(f"turns.{tid}: {tn} requires arrival but none is given")
            if "{order}" in body and "order" not in spec:
                err.append(f"turns.{tid}: {tn} requires order but none is given")
            if "{north}" in body and not t.get("slots"):
                err.append(f"turns.{tid}: {tn} requires slots but no slots are declared")

    # --- designs
    for did, d in D.items():
        tl = list(d.get("turns") or []) + list(d.get("extra_turns") or [])
        if not tl:
            err.append(f"designs.{did} has no turns")
        for tid in tl:
            if tid not in T:
                err.append(f"designs.{did} refers to undefined turns.{tid}")
            else:
                used_t.add(tid)
        for w in d.get("worlds") or []:
            if w not in W:
                err.append(f"designs.{did} refers to undefined world {w}")
            used_w.add(w)
        # cells
        cells = list(d.get("cells") or [])
        for seq in (d.get("orders") or {}).values():
            cells += [list(c) for c in seq]
        for c in cells:
            if len(c) != 2:
                err.append(f"designs.{did}: cell {c} does not have 2 elements")
                continue
            n, s_ = c
            if n not in SL["north"]:
                err.append(f"designs.{did} refers to undefined north slot {n}")
            else:
                used_slot["north"].add(n)
            if s_ not in SL["south"]:
                err.append(f"designs.{did} refers to undefined south slot {s_}")
            else:
                used_slot["south"].add(s_)
        # history references
        hf = d.get("history_from")
        if hf:
            if hf not in D:
                err.append(f"designs.{did}.history_from refers to undefined design {hf}")
            else:
                ho = d.get("history_order")
                src_orders = (D[hf].get("orders") or {})
                if ho and ho not in src_orders:
                    err.append(f"designs.{did}.history_order={ho} is not among the orders of {hf}")
                if not ho and src_orders:
                    warn.append(f"designs.{did} uses the history of {hf} but history_order is not set")
        # a turn requires slots but the design has no cells
        needs_cell = any("slots" in T.get(tid, {}) for tid in tl)
        if needs_cell and not cells:
            err.append(f"designs.{did} contains a turn needing slots but has no cells")
        if not needs_cell and cells:
            warn.append(f"designs.{did} has cells but no turn uses slots")
        if needs_cell and not (d.get("worlds")):
            warn.append(f"designs.{did} has no worlds (runs with the default solo)")
        # a design using one turn several times needs to tell the occurrences apart
        for tid in set(tl):
            if tl.count(tid) > 1 and not d.get("orders"):
                warn.append(f"designs.{did} uses {tid} {tl.count(tid)} times but has no orders, so the order is undetermined")

    # --- unused definitions
    for label, defined, used in (("templates", set(TP), used_tp),
                                 ("claims", set(CL), used_cl),
                                 ("arrivals", set(AR), used_ar),
                                 ("orders", set(OR), used_or),
                                 ("turns", set(T), used_t),
                                 ("worlds", set(W), used_w)):
        unused = sorted(defined - used)
        if unused:
            warn.append(f"{label} used by no design: {unused}")
    for side in ("north", "south"):
        unused = sorted(set(SL[side]) - used_slot[side])
        if unused:
            warn.append(f"{side} slots used by no design: {unused}")

    # --- comparison with the actual data
    import glob, json as _json, collections as _c
    seen = _c.defaultdict(set)
    for f in sorted(glob.glob("results*.jsonl")):
        for line in open(f, encoding="utf-8"):
            if not line.strip():
                continue
            r = _json.loads(line)
            if r.get("error"):
                continue
            if r.get("stake") and r.get("frame"):
                seen["cells"].add(r["stake"] + r["frame"])
            if r.get("order"):
                seen["orders"].add(r["order"])
            if r.get("probe"):
                seen["probes"].add(r["probe"])
            if r.get("world"):
                seen["worlds"].add(r["world"])

    print("=== structure check ===")
    if not err:
        print("  no broken references or defects")
    for e in err:
        print(f"  ✗ {e}")
    print()
    print("=== warnings ===")
    if not warn:
        print("  none")
    for w in warn:
        print(f"  ! {w}")
    print()
    print("=== conditions present in local data ===")
    for k in ("worlds", "cells", "orders", "probes"):
        if seen[k]:
            print(f"  {k}: {sorted(seen[k])}")
    # a condition in the data but not in the scenario = the design does not describe what was run
    sc_cells = set()
    for d in D.values():
        for c in (d.get("cells") or []):
            sc_cells.add("".join(c))
        for seq in (d.get("orders") or {}).values():
            for c in seq:
                sc_cells.add("".join(c))
    miss = sorted(seen["cells"] - sc_cells)
    if miss:
        print(f"  ! cells in the data but in no design: {miss}")
    sc_orders = {o for d in D.values() for o in (d.get("orders") or {})}
    miss = sorted(seen["orders"] - sc_orders)
    if miss:
        print(f"  ! orders in the data but in no design: {miss}")
    sc_probes = {v for t in T.values() for v in (t.get("variants") or {})}
    sc_probes |= {tid for tid in T}
    miss = sorted(seen["probes"] - sc_probes)
    if miss:
        print(f"  ! probes in the data but not in the scenario: {miss}")
    sc_worlds = set(W)
    miss = sorted(seen["worlds"] - sc_worlds)
    if miss:
        print(f"  ! worlds in the data but not in the scenario: {miss}")
    return not err


# ---------------------------------------------------------------- main

def show(sc, design):
    d = sc["designs"][design]
    print(f"### design {design}: {d.get('note','')}\n")
    worlds = d.get("worlds", ["solo"])
    for world in worlds:
        print(f"[system / {world}]\n{system_text(sc, world)}\n")
    if "cells" in d:
        for cell in d["cells"]:
            print("=" * 60)
            print(f"  cell {''.join(cell)}")
            print("=" * 60)
            print(turn_text(sc, "decision", world=worlds[0], cell=tuple(cell)))
            print()
    for tid in d["turns"] + d.get("extra_turns", []):
        t = sc["turns"][tid]
        if "variants" in t:
            for v in t["variants"]:
                print("=" * 60)
                print(f"  {tid} / {v}  -> {t['codebook_question']}")
                print("=" * 60)
                txt = turn_text(sc, tid, variant=v, first="南", second="北")
                print(txt if txt is not None else "(this combination is not possible)")
                print()
        elif tid != "decision":
            print("=" * 60)
            print(f"  {tid}  -> {t['codebook_question']}")
            print("=" * 60)
            print(turn_text(sc, tid, world=worlds[0]))
            print()


def main():
    p = argparse.ArgumentParser(description="FJF scenario")
    p.add_argument("--scenario", default=SCENARIO)
    p.add_argument("--verify", action="store_true", help="does it match the retired scripts?")
    p.add_argument("--check", action="store_true", help="structure check of the scenario")
    p.add_argument("--mesh", action="store_true",
                   help="check the fit between turn elicits and variable requires")
    p.add_argument("--lint", action="store_true", help="lint the stimuli")
    p.add_argument("--show", metavar="DESIGN", help="print the prompts of a design")
    args = p.parse_args()

    sc = load(args.scenario)
    print(f"scenario {sc['scenario']} version {sc['version']} ({sc['language']})\n")

    if args.check:
        sys.exit(0 if check(sc) else 1)
    if args.verify:
        sys.exit(0 if verify(sc) else 1)
    if args.mesh:
        mesh(sc)
        return

    if args.lint:
        lint(sc)
        return
    if args.show:
        show(sc, args.show)
        return
    print("Specify one of --check / --verify / --lint / --show DESIGN.")


if __name__ == "__main__":
    main()
