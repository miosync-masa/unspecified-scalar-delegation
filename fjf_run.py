#!/usr/bin/env python3
"""
FJF 実行 — シナリオ YAML が刺激を決める

    設計   scenario_rescue.yaml   どの文をどの順で投げるか
    測定器 codebook_v1.yaml       どの発話をどの変数で測るか
    実行   このファイル           読んで回すだけ
    API    fjf_api.py             プロバイダの差

プロンプトはコードに持たない。YAML を編集すれば送られる文が変わる。
逆に、YAML を編集しないと何も変わらない。

出力は設計をまたいで同じ形にする。ターンごとに codebook_question が
入っているので、抽出側は本文の在処を知る必要がない。

使い方
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

# q1〜pilot_a で使ってきた履歴の渡し方。gemini は畳んだ形、他は本物のターン。
# これと違う形で回したときだけ、設計名に印を付けてキーを分ける。
HISTORICAL_FORMAT = {"gemini": "flat", "openai": "native",
                     "anthropic": "native", "qwen": "native"}


def design_label(job):
    """設計名。過去と同じ履歴の形なら素の名前、違えば +flat / +native を付ける。
    過去のデータのキーは一つも変わらない。"""
    fmt = history_format(job["provider"])
    if fmt == HISTORICAL_FORMAT[job["provider"]]:
        return job["design"]
    return f'{job["design"]}+{fmt}'


from fjf_scenario import load as load_scenario, system_text, turn_text

CODEBOOK = "codebook_v1.yaml"
_write_lock = threading.Lock()


# ---------------------------------------------------------------- ジョブの展開

def variant_sets(sc, turn_ids):
    """設計のターン列から、変種の組み合わせを列挙する。

    変種を持つターンが複数あれば直積になる。持たないターンは None。
    返すのは [(turn_id, variant), ...] のリストの列。
    """
    pools = []
    for tid in turn_ids:
        v = sc["turns"][tid].get("variants")
        pools.append(list(v) if v else [None])
    for combo in itertools.product(*pools):
        yield list(zip(turn_ids, combo))


def expand(sc, design_id, providers, trials=None, history=None):
    """設計を 1 ジョブずつに展開する。1 ジョブ = 1 レコード。"""
    d = sc["designs"][design_id]
    n = trials or d.get("trials") or 10
    worlds = d.get("worlds") or ["solo"]

    # ターン列。extra_turns は「同じ履歴に対する別条件」なので、
    # turns と並べるのではなく、別のジョブ群として扱う。
    groups = [list(d.get("turns") or [])]
    for tid in (d.get("extra_turns") or []):
        groups.append([tid])

    # セル列（orders があれば順序名ごとに、なければ cells をそれぞれ）
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
                f"設計 {design_id} は {d['history_from']} の履歴を使います。"
                " --history で出力ファイルを渡してください。")
        want_order = d.get("history_order")
        for r in history:
            if r.get("error"):
                continue
            if want_order and r.get("order_name") != want_order:
                continue
            hist_by[(r["provider"], r["trial"])] = r
        # 履歴は刺激の一部である。先行設計の試行数より多く試行したいとき、
        # 履歴を巡回させて同じ刺激を複数回サンプリングする。他の設計で
        # 同じプロンプトを n 回投げるのと同じことで、入れ子（文脈 × 反復）
        # になる。巡回しないと、先行設計の試行数が後続の上限になる。
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
    """条件の比較を同じ時間帯に置くための並べ替え。

    条件をまとめて順に流すと、先に回した条件と後に回した条件のあいだに
    時間の差が入る。配信側の更新や混雑が条件の差に化ける（q2 の形の比較で、
    同じ本物のターンどうしが 11 日を隔てて動いたのが実例）。

    試行番号ごとに1ブロックを作り、ブロックの中に全被験者 × 全条件を並べる。
    ブロック内の条件の順は試行番号で回転させ、毎回同じ条件が先頭に来ないようにする。
    乱数は使わないので並びは再現できる。ジョブのキーは変わらないので再開にも影響しない。
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
    """履歴の由来を連鎖で持つ。履歴の履歴まで辿れないと、
    入れ子が3段（q4 → q3_post → q2）になったとき出発点が失われる。
    via は親より手前の由来を、近い順に並べたものである。"""
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
    """再開のための一意キー。"""
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


# ---------------------------------------------------------------- 実行

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
        # 履歴は逐語でそのまま文脈に積む。要約しない。
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
            # usage は成功した呼び出しの値で上書きされる（_put は成功後にしか書かない）
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
    p = argparse.ArgumentParser(description="FJF 実行（シナリオ YAML 駆動）")
    p.add_argument("--scenario", default="scenario_rescue.yaml")
    p.add_argument("--codebook", default=CODEBOOK)
    p.add_argument("--design", required=True, nargs="+",
                   help="複数を渡すと、全設計のジョブを一つの実行に混ぜて交互に並べる（同じ日・同じ時間帯で比べるため）")
    p.add_argument("--provider", nargs="+", default=list(PROVIDERS),
                   choices=list(PROVIDERS))
    p.add_argument("--model", nargs="+", default=None,
                   metavar="PROV=MODEL", help="既定モデルの上書き")
    p.add_argument("--trials", type=int, default=None)
    p.add_argument("--history", default=None, help="履歴を使う設計で必須")
    p.add_argument("--effort", default="medium")
    p.add_argument("--max-tokens", type=int, default=32768)
    p.add_argument("--out", default=None)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--order", choices=["interleave", "grouped"], default="interleave",
                   help="interleave: 試行番号ごとのブロックに全条件・全被験者を並べる（既定）。"
                        " grouped: 以前の並び（被験者→条件→試行）")
    args = p.parse_args()

    sc = load_scenario(args.scenario)
    bad = [d for d in args.design if d not in sc["designs"]]
    if bad:
        sys.exit(f"設計 {bad} がありません。"
                 f" 候補: {sorted(sc['designs'])}")
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
        print(f"設計 {d}: {sc['designs'][d].get('note','')}")

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
                print("[履歴] 先行設計の応答を逐語で文脈に積む\n")
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
        print(f"\nジョブ {len(jobs)} 件（試行をまとめると上の {len(seen)} 種）")
        return

    if not jobs:
        sys.exit("ジョブが 0 件です。履歴や設計を確認してください。")

    models = {}
    for spec in (args.model or []):
        k, v = spec.split("=", 1)
        models[k] = v
    cl = clients_for(sorted({j["provider"] for j in jobs}), models)

    out_path = args.out or f"results_{'+'.join(args.design)}.jsonl"
    done = load_done(out_path)
    todo = [j for j in jobs if job_key(j) not in done]

    calls = sum(len([t for t, _ in j["combo"]]) for j in todo)
    print(f"ジョブ {len(jobs)} 件 / 済み {len(jobs)-len(todo)} 件 / "
          f"実行 {len(todo)} 件")
    print(f"API 呼び出し 約 {calls} 回（並列 {args.workers}）")
    print(f"出力 {out_path}（再開可）\n")
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
    print(f"\n完了 {ok}/{len(todo)}")


if __name__ == "__main__":
    main()
