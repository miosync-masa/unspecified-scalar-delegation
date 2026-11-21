#!/usr/bin/env python3
"""
FJF runner — the scenario YAML decides the stimuli

    design      scenario_rescue.yaml   which text is sent, in which order
    instrument  codebook_v1.yaml       which utterance is measured by which variable
    runner      this file              only reads and runs
    API         fjf_api.py             provider differences

No prompt lives in the code. Editing the YAML changes the text that is sent;
nothing changes unless the YAML is edited.

Output has the same shape across designs. Each turn carries its codebook_question,
so the extractor does not need to know where the text came from.

Usage
  python3 fjf_run.py --design q1 --provider gemini openai anthropic qwen
  python3 fjf_run.py --design q2 --provider gemini openai anthropic qwen
  python3 fjf_run.py --design q3 --history results_q2.jsonl
  python3 fjf_run.py --design q4 --history results_q2.jsonl
  python3 fjf_run.py --design q1 --dry-run
"""

import argparse
import itertools
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import yaml

from fjf_api import PROVIDERS, chat, clients_for, log, with_retry, history_format

# History format used from q1 to pilot_a: folded for gemini, native turns for the others.
# Only runs with a different format get a marker in the design name, so keys stay separate.
HISTORICAL_FORMAT = {"gemini": "flat", "openai": "native",
                     "anthropic": "native", "qwen": "native"}


def design_label(job):
    """Design name. The plain name when the history format matches the past; otherwise +flat / +native.
    Keys of past data are unchanged."""
    fmt = history_format(job["provider"])
    if fmt == HISTORICAL_FORMAT[job["provider"]]:
        return job["design"]
    return f'{job["design"]}+{fmt}'


from fjf_scenario import load as load_scenario, system_text, turn_text

CODEBOOK = "codebook_v1.yaml"
_write_lock = threading.Lock()


# ---------------------------------------------------------------- job expansion

def variant_sets(sc, turn_ids):
    """Enumerate variant combinations over a design's turn list.

    Several turns with variants give their product; turns without variants give None.
    Returns a sequence of lists [(turn_id, variant), ...].
    """
    pools = []
    for tid in turn_ids:
        v = sc["turns"][tid].get("variants")
        pools.append(list(v) if v else [None])
    for combo in itertools.product(*pools):
        yield list(zip(turn_ids, combo))


def expand(sc, design_id, providers, trials=None, history=None):
    """Expand a design into jobs. One job = one record."""
    d = sc["designs"][design_id]
    n = trials or d.get("trials") or 10
    worlds = d.get("worlds") or ["solo"]

    # Turn list. extra_turns are "another condition on the same history", so they
    # are handled as a separate group of jobs rather than appended to turns.
    groups = [list(d.get("turns") or [])]
    for tid in (d.get("extra_turns") or []):
        groups.append([tid])

    # Cell list (per order name if orders exist, otherwise each of cells)
    if d.get("orders"):
        cellsets = [(name, [tuple(c) for c in seq])
                    for name, seq in d["orders"].items()]
    elif d.get("cells"):
        cellsets = [(None, [tuple(c)]) for c in d["cells"]]
    else:
        cellsets = [(None, [])]

    hist_by = {}
    if d.get("history_from"):
        if history is None:
            raise SystemExit(
                f"design {design_id} uses the history of {d['history_from']}."
                " Pass its output file with --history.")
        want_order = d.get("history_order")
        for r in history:
            if r.get("error"):
                continue
            if want_order and r.get("order_name") != want_order:
                continue
            hist_by[(r["provider"], r["trial"])] = r
        # History is part of the stimulus. To run more trials than the preceding design had,
        # cycle through the histories, sampling the same stimulus several times. This is the same
        # as sending one prompt n times in another design, nested (context x repetition).
        # Without cycling, the preceding design's trial count caps the later one.
        hist_trials = {}
        for (pv, t) in hist_by:
            hist_trials.setdefault(pv, []).append(t)
        for pv in hist_trials:
            hist_trials[pv].sort()

    for prov in providers:
        for world in worlds:
            for turn_ids in groups:
                for combo in variant_sets(sc, turn_ids):
                    for order_name, cells in cellsets:
                        for t in range(1, n + 1):
                            src = None
                            rep = 1
                            if d.get("history_from"):
                                hts = hist_trials.get(prov) or []
                                if not hts:
                                    continue
                                ht = hts[(t - 1) % len(hts)]
                                rep = (t - 1) // len(hts) + 1
                                src = hist_by.get((prov, ht))
                                if src is None:
                                    continue
                            yield {
                                "design": design_id, "provider": prov,
                                "world": world, "trial": t,
                                "order_name": order_name, "cells": cells,
                                "combo": combo, "history_src": src,
                                "replicate": rep,
                            }


def interleave(jobs):
    """Reordering that puts the compared conditions in the same time window.

    Running conditions as blocks in sequence inserts a time gap between earlier and later
    conditions; provider updates or load turn into condition differences (in the q2 format
    comparison, the same native-turn condition moved across an 11-day gap).

    One block per trial number, containing every subject x every condition.
    The order of conditions within a block rotates with the trial number, so the same condition is not always first.
    No randomness, so the order is reproducible. Job keys are unchanged, so resuming is unaffected.
    """
    def sig(j):
        return (j["design"], "+".join(f"{t}:{v}" for t, v in j["combo"]), j["order_name"] or "",
                j["world"], "+".join("".join(c) for c in j["cells"]))
    conds = []
    for j in jobs:
        s = sig(j)
        if s not in conds:
            conds.append(s)
    provs = []
    for j in jobs:
        if j["provider"] not in provs:
            provs.append(j["provider"])

    def key(j):
        t = j["trial"]
        ci = conds.index(sig(j))
        rot = (ci - (t - 1)) % len(conds)
        return (t, rot, provs.index(j["provider"]))
    return sorted(jobs, key=key)


def chain_src(src, replicate):
    """Keep the provenance of the history as a chain. Without tracing the history's own history,
    the starting point is lost when nesting reaches 3 levels (q4 -> q3_post -> q2).
    via lists the provenance before the parent, nearest first."""
    via = []
    node = src.get("history_src")
    seen = 0
    while node and seen < 8:
        via.append({k: node.get(k) for k in
                    ("design", "trial", "order_name", "replicate")
                    if node.get(k) is not None})
        node = node.get("via")
        node = node[0] if isinstance(node, list) and node else None
        seen += 1
    out = {"design": src["design"], "trial": src["trial"],
           "order_name": src.get("order_name"),
           "scenario_version": src.get("scenario_version"),
           "replicate": replicate}
    if via:
        out["via"] = via
    return out


def job_key(job):
    """Unique key for resuming."""
    return (design_label(job), job["provider"], job["world"], job["order_name"],
            "+".join("".join(c) for c in job["cells"]),
            "+".join(f"{t}:{v}" for t, v in job["combo"]),
            job["trial"])


def job_tag(job):
    parts = [job["provider"], job["design"]]
    if job["order_name"]:
        parts.append(job["order_name"])
    elif job["cells"]:
        parts.append("".join(job["cells"][0]))
    for tid, v in job["combo"]:
        parts.append(f"{tid}/{v}" if v else tid)
    return "|".join(parts)


# ---------------------------------------------------------------- execution

def append_record(path, rec):
    with _write_lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load_done(path):
    done = set()
    if not os.path.exists(path):
        return done
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("error"):
                continue
            done.add(tuple(r["key"]))
    return done


def run_one(sc, cb_ver, job, client, model, effort, max_tokens, out_path):
    prov = job["provider"]
    sys_inst = system_text(sc, job["world"])
    tag = job_tag(job)
    started = time.time()

    history = []
    turns_out = []

    src = job["history_src"]
    if src:
        # History is stacked into the context verbatim. Never summarized.
        for t in src["turns"]:
            history.append((t["prompt"], t["response"]))
            turns_out.append({**t, "from_history": True})

    try:
        cells = list(job["cells"])
        ci = 0
        qn = 0
        for turn_id, variant in job["combo"]:
            turn = sc["turns"][turn_id]
            cell = None
            if turn.get("slots"):
                cell = cells[ci] if ci < len(cells) else cells[-1]
                ci += 1
            qn += 1
            prompt = turn_text(sc, turn_id, world=job["world"],
                               cell=cell, variant=variant, qn=qn)
            if prompt is None:
                continue
            # usage is overwritten by the successful call's values (_put writes only after success)
            u = {}
            ans = with_retry(lambda p=prompt: chat(
                prov, client, model, sys_inst, history, p, effort, max_tokens,
                usage=u))
            history.append((prompt, ans))
            turns_out.append({
                "turn": turn_id,
                "variant": variant,
                "cell": "".join(cell) if cell else None,
                "cb_question": turn["codebook_question"],
                "prompt": prompt,
                "response": ans,
                "from_history": False,
                "usage": u,
            })

        append_record(out_path, {
            "key": list(job_key(job)),
            "scenario": sc["scenario"], "scenario_version": sc["version"],
            "codebook_version": cb_ver,
            "design": design_label(job), "provider": prov, "model": model,
            "history_format": history_format(prov),
            "world": job["world"], "trial": job["trial"],
            "order_name": job["order_name"],
            "cells": ["".join(c) for c in job["cells"]],
            "variants": {t: v for t, v in job["combo"] if v},
            "effort": effort,
            "system_instruction": sys_inst,
            "history_src": (chain_src(src, job["replicate"]) if src else None),
            "turns": turns_out,
            "elapsed_sec": round(time.time() - started, 2),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        })
        new = [t for t in turns_out if not t["from_history"]]
        lens = "/".join(str(len(t["response"])) for t in new)
        log(f"  ok   {tag} #{job['trial']}  "
            f"({round(time.time()-started,1)}s, {lens} chars)")
        return True
    except Exception as e:
        append_record(out_path, {
            "key": list(job_key(job)), "design": design_label(job),
            "provider": prov, "trial": job["trial"], "error": repr(e),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        })
        log(f"  FAIL {tag} #{job['trial']} — {type(e).__name__}: {e}")
        return False


# ---------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(description="FJF runner (driven by the scenario YAML)")
    p.add_argument("--scenario", default="scenario_rescue.yaml")
    p.add_argument("--codebook", default=CODEBOOK)
    p.add_argument("--design", required=True, nargs="+",
                   help="with several designs, mix all their jobs into one run, interleaved (to compare on the same day and time window)")
    p.add_argument("--provider", nargs="+", default=list(PROVIDERS),
                   choices=list(PROVIDERS))
    p.add_argument("--model", nargs="+", default=None,
                   metavar="PROV=MODEL", help="override the default model")
    p.add_argument("--trials", type=int, default=None)
    p.add_argument("--history", default=None, help="required for designs that use a history")
    p.add_argument("--effort", default="medium")
    p.add_argument("--max-tokens", type=int, default=32768)
    p.add_argument("--out", default=None)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--order", choices=["interleave", "grouped"], default="interleave",
                   help="interleave: one block per trial number with every condition and subject (default)."
                        " grouped: the earlier order (subject -> condition -> trial)")
    args = p.parse_args()

    sc = load_scenario(args.scenario)
    bad = [d for d in args.design if d not in sc["designs"]]
    if bad:
        sys.exit(f"design {bad} does not exist."
                 f" candidates: {sorted(sc['designs'])}")
    try:
        cb_ver = yaml.safe_load(open(args.codebook, encoding="utf-8"))["version"]
    except Exception:
        cb_ver = None

    hist = None
    if args.history:
        hist = [json.loads(l) for l in open(args.history, encoding="utf-8")
                if l.strip()]

    jobs = [j for d in args.design for j in expand(sc, d, args.provider, args.trials, hist)]
    if args.order == "interleave":
        jobs = interleave(jobs)

    print(f"scenario {sc['scenario']} v{sc['version']} / codebook v{cb_ver}")
    for d in args.design:
        print(f"design {d}: {sc['designs'][d].get('note','')}")

    if args.dry_run:
        seen = set()
        for job in jobs:
            sig = (job["world"], job["order_name"],
                   "+".join("".join(c) for c in job["cells"]),
                   "+".join(f"{t}:{v}" for t, v in job["combo"]))
            if sig in seen:
                continue
            seen.add(sig)
            print(f"\n{'#'*64}\n  {job_tag(job)}\n{'#'*64}")
            print(f"[system] {system_text(sc, job['world'])}\n")
            if job["history_src"]:
                print("[history] stacking the preceding design's responses verbatim into the context\n")
            cells = list(job["cells"]); ci = 0; qn = 0
            for turn_id, variant in job["combo"]:
                turn = sc["turns"][turn_id]
                cell = None
                if turn.get("slots"):
                    cell = cells[ci] if ci < len(cells) else cells[-1]
                    ci += 1
                qn += 1
                txt = turn_text(sc, turn_id, world=job["world"],
                                cell=cell, variant=variant, qn=qn)
                vq = turn["codebook_question"]
                print(f"--- turn {turn_id}"
                      f"{'/'+variant if variant else ''} -> {vq}")
                print(txt, "\n")
        print(f"\n{len(jobs)} jobs ({len(seen)} kinds above, collapsing trials)")
        return

    if not jobs:
        sys.exit("0 jobs. Check the history and the design.")

    models = {}
    for spec in (args.model or []):
        k, v = spec.split("=", 1)
        models[k] = v
    cl = clients_for(sorted({j["provider"] for j in jobs}), models)

    out_path = args.out or f"results_{'+'.join(args.design)}.jsonl"
    done = load_done(out_path)
    todo = [j for j in jobs if job_key(j) not in done]

    calls = sum(len([t for t, _ in j["combo"]]) for j in todo)
    print(f"{len(jobs)} jobs / {len(jobs)-len(todo)} done / "
          f"{len(todo)} to run")
    print(f"about {calls} API calls ({args.workers} workers)")
    print(f"output {out_path} (resumable)\n")
    if not todo:
        return

    ok = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(run_one, sc, cb_ver, j, *cl[j["provider"]],
                          args.effort, args.max_tokens, out_path)
                for j in todo]
        for f in as_completed(futs):
            if f.result():
                ok += 1
    print(f"\ndone {ok}/{len(todo)}")


if __name__ == "__main__":
    main()
