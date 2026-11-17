#!/usr/bin/env python3
"""
シナリオ YAML を読んでプロンプトを組み立てる + 既存スクリプトとの一致検算

刺激は scenario_rescue.yaml、測定器は codebook_v1.yaml が持つ。このモジュールは
前者を読んで文を組み立てるだけの器である。

退役した fjf_q1〜q4 はプロンプトをコードに埋め込んでいた。差し替える前に、
YAML から組んだ文が既存の文と一字一句一致することを確かめる。一致しなければ
設計が足りていないので、そこで止まる。

使い方
  python3 fjf_scenario.py --verify          既存スクリプトとの一致を検算
  python3 fjf_scenario.py --show q1         設計 q1 のプロンプトを出す
  python3 fjf_scenario.py --lint            刺激側の点検（字数の偏り・語の混入）
"""

import argparse
import sys
import os

import yaml

SCENARIO = "scenario_rescue.yaml"


def load(path=SCENARIO):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------- 組み立て

def system_text(sc, world):
    w = sc["worlds"][world]
    return "".join(sc["systems"][k] for k in w["system"])


def turn_text(sc, turn_id, world="solo", cell=None, variant=None,
              first=None, second=None, qn=None):
    """ターン1つ分の本文を返す。"""
    turn = sc["turns"][turn_id]

    if "variants" in turn:
        if variant is None:
            raise ValueError(f"{turn_id} には variant が必要")
        spec = turn["variants"][variant]
        tname = spec["template"]
    else:
        spec = turn
        tname = turn["template"]
        byw = turn.get("template_by_world") or {}
        tname = byw.get(world, tname)

    body = sc["templates"][tname]["body"]

    # スロット（北と南）
    if "{north}" in body:
        if cell is None:
            raise ValueError(f"{turn_id} には cell が必要")
        n, s = cell
        body = body.replace("{north}", sc["slots"]["north"][n]["text"])
        body = body.replace("{south}", sc["slots"]["south"][s]["text"])

    # 質問番号（連番で提示する設計でのみ使う）
    if "{qn}" in body:
        if qn is None:
            raise ValueError(f"{turn_id} には qn が必要")
        body = body.replace("{qn}", str(qn))

    # world 固有の段落
    if "{extra}" in body:
        extra = sc["worlds"][world].get("extra")
        body = body.replace("{extra}", extra if extra is not None else "")

    # 追及の主張
    if "{claim}" in body:
        cl = sc["claims"][spec["claim"]]
        text = cl["text"]
        if cl.get("requires_flip"):
            if first is None or second is None:
                raise ValueError("true 系の claim には first/second が必要")
            if first == second or "?" in (first, second):
                return None          # 反転していない履歴には作れない
            labels = cl["labels"]
            text = text.replace("{first_label}", labels[first])
            text = text.replace("{second_label}", labels[second])
        body = body.replace("{claim}", text)

    # 伝令の到着と命令
    if "{arrival}" in body:
        body = body.replace("{arrival}", sc["arrivals"][spec["arrival"]])
    if "{order}" in body:
        body = body.replace("{order}", sc["orders"][spec["order"]])

    return body


# ---------------------------------------------------------------- 検算

def verify(sc):
    """既存スクリプトのプロンプトと一字一句一致するか。"""
    # 旧スクリプトは superseded/ に退役済み。実行経路はもう通らない。
    # ここだけが参照する（照合の相手として）。
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "superseded"))
    try:
        import fjf_q1, fjf_q2, fjf_q3, fjf_q4
    except ImportError as e:
        print(f"照合相手が見つかりません（superseded/ を確認）: {e}")
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
            print("      YAML 側が None を返した")
            return
        for i, (a, b) in enumerate(zip(got, want)):
            if a != b:
                print(f"      {i} 文字目から違う")
                print(f"      YAML : ...{got[max(0,i-25):i+25]!r}")
                print(f"      既存 : ...{want[max(0,i-25):i+25]!r}")
                break
        else:
            print(f"      長さが違う: YAML {len(got)} / 既存 {len(want)}")

    print("=== 系の指示 ===")
    for world in fjf_q1.SYSTEM_INSTRUCTION:
        check(f"system[{world}]", system_text(sc, world),
              fjf_q1.SYSTEM_INSTRUCTION[world])

    print("=== 判断のターン（全 world × 全セル）===")
    for world in fjf_q1.SYSTEM_INSTRUCTION:
        for n in sc["slots"]["north"]:
            for s in sc["slots"]["south"]:
                check(f"decision[{world}/{n}{s}]",
                      turn_text(sc, "decision", world=world, cell=(n, s)),
                      fjf_q1.build_prompt(n, s, "none", world))

    print("=== 整合性のターン ===")
    check("consistency", turn_text(sc, "consistency"), fjf_q2.CONSISTENCY_PROMPT)

    print("=== 日没後 ===")
    check("sunset", turn_text(sc, "sunset"), fjf_q3._STATIC_PROBES["none"])
    check("sunset_self", turn_text(sc, "sunset_self"), fjf_q3._STATIC_PROBES["self"])
    check("sunset(q4)", turn_text(sc, "sunset"), fjf_q4.SUNSET_PROMPT)

    print("=== 記録の追及 ===")
    for v in ("neutral_false", "adversary_false"):
        check(f"audit[{v}]", turn_text(sc, "audit", variant=v),
              fjf_q3._STATIC_PROBES[v])
    for v in ("neutral_true", "adversary_true"):
        check(f"audit[{v}]", turn_text(sc, "audit", variant=v),
              fjf_q3._STATIC_PROBES[v])

    print("=== 二人目の伝令 ===")
    for v in fjf_q4.PROBES:
        check(f"order[{v}]", turn_text(sc, "order", variant=v), fjf_q4.PROBES[v])

    print(f"\n一致 {ok} / 不一致 {bad}")
    return bad == 0


# ---------------------------------------------------------------- 点検

def mesh(sc, cb_path="codebook_v1.yaml"):
    """ターンが引き出すものと変数が必要とするものの噛み合いを検査する。

    パイプラインは 変数設計 → シナリオの決定と聞き方 → 応答 → 測定器
    の順に流れる。一致率が上がらないとき下流だけを見ると、上流の
    噛み合わせの誤りを追えない。これは上流の検査である（codebook I19）。

    3段で判定する。elicits と交わればOK。permits だけなら危険（出るかが
    被験者の語り方次第）。どちらとも交わらなければ設計の誤り。
    """
    cb = yaml.safe_load(open(cb_path, encoding="utf-8"))
    print(f"\n=== 噛み合い検査（codebook v{cb['version']}）===")
    out, risk, intended = [], [], []
    for tid, t in sc["turns"].items():
        el = set(t.get("elicits") or [])
        pm = set(t.get("permits") or [])
        q = t.get("codebook_question")
        if not el:
            out.append((tid, None, "elicits が宣言されていない"))
            continue
        for name, spec in cb["variables"].items():
            if q not in spec.get("questions", []):
                continue
            req = set(spec.get("requires") or [])
            if not req:
                out.append((tid, name, "requires が宣言されていない"))
            elif req & el:
                continue
            elif req & pm:
                risk.append((tid, name, sorted(req), sorted(el), sorted(pm)))
            elif spec.get("mismatch_note"):
                intended.append((tid, name, sorted(req), sorted(el)))
            else:
                out.append((tid, name,
                            f"requires {sorted(req)} が elicits {sorted(el)} / "
                            f"permits {sorted(pm)} のどちらとも交わらない"))
    if out:
        print(f"  ★ 設計の誤り {len(out)} 件 — 刺激がその情報を引き出していない")
        for tid, name, why in out:
            print(f"    turn {tid}" + (f" / {name}" if name else "") + f": {why}")
    else:
        print("  設計の誤りなし")
    if risk:
        print(f"\n  ! 危険 {len(risk)} 件 — permits にはあるが直接は尋ねていない。"
              "出るかが語り方次第なので実測で確かめる")
        for tid, name, req, el, pm in risk:
            print(f"    turn {tid} / {name}: requires {req}（elicits {el}）")
    if intended:
        print(f"\n  ○ 意図された不一致 {len(intended)} 件 — 自発性を測るために"
              "引き出さないターンで測っている（mismatch_note あり）")
        for tid, name, req, el in intended:
            print(f"    turn {tid} / {name}: requires {req}（elicits {el}）")
    byq = {}
    for tid, t in sc["turns"].items():
        byq.setdefault(t.get("codebook_question"), []).append(
            (tid, tuple(sorted(t.get("elicits") or []))))
    for q, lst in byq.items():
        if len({e for _, e in lst}) > 1:
            print(f"\n  ★ 変数群 {q} に直接尋ねるものが違うターンが混在。"
                  "群を分けること")
            for tid, e in lst:
                print(f"      {tid}: elicits {list(e)}")
    return out, risk, intended


def lint(sc):
    print("=== スロットの字数 ===")
    for side in ("north", "south"):
        print(f"  {side}")
        for k, v in sc["slots"][side].items():
            actual = len(v["text"])
            flag = "" if actual == v.get("chars") else f"  !! chars={v.get('chars')} だが実際は {actual}"
            print(f"    {k:3s} {actual:3d}字  {v['text']}{flag}")

    print("\n=== 南スロットの字数差（属性以外の交絡）===")
    s = sc["slots"]["south"]
    base = len(s["A"]["text"])
    for k, v in s.items():
        d = len(v["text"]) - base
        mark = "  ← A との差が大きい" if abs(d) >= 7 else ""
        print(f"    {k:3s} A比 {d:+3d}字  guilt={v.get('guilt')}{mark}")
    print("    字数が揃っていない比較は、属性の効果と記述量の効果を分離できない。")
    print("    designs.q1_length_control が A2 を入れてその切り分けをする。")

    print("\n=== 追及文が刺激側の語を使っていないか ===")
    # 課題文に出る語を追及文が引用していると、I3（プロンプト語の混入）に触れる
    dec = turn_text(sc, "decision", world="solo", cell=("N", "A"))
    for cid, cl in sc["claims"].items():
        shared = [w for w in ("北の塔", "南の塔", "伝令", "日没", "国王陛下")
                  if w in cl["text"] and w in dec]
        if shared:
            print(f"    {cid}: 課題文と共通の語 {shared}")
    print("    追及文が課題文の語を含むのは自然だが、これらの語を")
    print("    判定の手がかりに使ってはならない（codebook I3）。")

    print("\n=== ターンと測定器の対応 ===")
    try:
        cb = yaml.safe_load(open("codebook_v1.yaml", encoding="utf-8"))
        known = {q for v in cb["variables"].values()
                 for q in v.get("questions", [])}
    except Exception as e:
        print(f"    codebook_v1.yaml を読めなかった: {e}")
        known = set()
    for tid, t in sc["turns"].items():
        q = t.get("codebook_question")
        mark = "" if (not known or q in known) else "  !! コードブックに変数がない"
        print(f"    {tid:14s} -> {q}{mark}")
    if known:
        missing = sorted(known - {t.get("codebook_question")
                                 for t in sc["turns"].values()})
        if missing:
            print(f"    どのターンからも使われていない変数群: {missing}")


def check(sc):
    """シナリオ自身の構造を検査する。参照の切れ、未使用の定義、設計の不備。

    --verify は「既存コードと同じ文が出るか」を見る。こちらは
    「設計として筋が通っているか」を見る。別の検査である。
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
                err.append(f"worlds.{w}.system が未定義の systems.{k} を参照")

    # --- turns
    for tid, t in T.items():
        qs = t.get("codebook_question")
        if not qs:
            err.append(f"turns.{tid} に codebook_question がない")
        variants = t.get("variants")
        specs = list(variants.values()) if variants else [t]
        for spec in specs:
            tn = spec.get("template")
            if tn is None:
                err.append(f"turns.{tid} に template がない")
                continue
            if tn not in TP:
                err.append(f"turns.{tid} が未定義の templates.{tn} を参照")
            else:
                used_tp.add(tn)
            for key, pool, bag, label in (("claim", CL, used_cl, "claims"),
                                          ("arrival", AR, used_ar, "arrivals"),
                                          ("order", OR, used_or, "orders")):
                if key in spec:
                    if spec[key] not in pool:
                        err.append(f"turns.{tid} が未定義の {label}.{spec[key]} を参照")
                    else:
                        bag.add(spec[key])
        for w, tn in (t.get("template_by_world") or {}).items():
            if w not in W:
                err.append(f"turns.{tid}.template_by_world が未定義の world {w} を参照")
            if tn not in TP:
                err.append(f"turns.{tid}.template_by_world が未定義の template {tn} を参照")
            else:
                used_tp.add(tn)
        # 文型が要求するプレースホルダが埋まるか
        for spec in specs:
            tn = spec.get("template")
            if tn not in TP:
                continue
            body = TP[tn]["body"]
            if "{claim}" in body and "claim" not in spec:
                err.append(f"turns.{tid} の {tn} は claim を要求するが指定がない")
            if "{arrival}" in body and "arrival" not in spec:
                err.append(f"turns.{tid} の {tn} は arrival を要求するが指定がない")
            if "{order}" in body and "order" not in spec:
                err.append(f"turns.{tid} の {tn} は order を要求するが指定がない")
            if "{north}" in body and not t.get("slots"):
                err.append(f"turns.{tid} の {tn} はスロットを要求するが slots の宣言がない")

    # --- designs
    for did, d in D.items():
        tl = list(d.get("turns") or []) + list(d.get("extra_turns") or [])
        if not tl:
            err.append(f"designs.{did} に turns がない")
        for tid in tl:
            if tid not in T:
                err.append(f"designs.{did} が未定義の turns.{tid} を参照")
            else:
                used_t.add(tid)
        for w in d.get("worlds") or []:
            if w not in W:
                err.append(f"designs.{did} が未定義の world {w} を参照")
            used_w.add(w)
        # セル
        cells = list(d.get("cells") or [])
        for seq in (d.get("orders") or {}).values():
            cells += [list(c) for c in seq]
        for c in cells:
            if len(c) != 2:
                err.append(f"designs.{did} のセル {c} が2要素でない")
                continue
            n, s_ = c
            if n not in SL["north"]:
                err.append(f"designs.{did} が未定義の north スロット {n} を参照")
            else:
                used_slot["north"].add(n)
            if s_ not in SL["south"]:
                err.append(f"designs.{did} が未定義の south スロット {s_} を参照")
            else:
                used_slot["south"].add(s_)
        # 履歴の参照
        hf = d.get("history_from")
        if hf:
            if hf not in D:
                err.append(f"designs.{did}.history_from が未定義の設計 {hf} を参照")
            else:
                ho = d.get("history_order")
                src_orders = (D[hf].get("orders") or {})
                if ho and ho not in src_orders:
                    err.append(f"designs.{did}.history_order={ho} が {hf} の orders にない")
                if not ho and src_orders:
                    warn.append(f"designs.{did} は {hf} の履歴を使うが history_order 未指定")
        # スロットを要求するターンがあるのにセルがない
        needs_cell = any("slots" in T.get(tid, {}) for tid in tl)
        if needs_cell and not cells:
            err.append(f"designs.{did} はスロットを要す turn を含むがセルが無い")
        if not needs_cell and cells:
            warn.append(f"designs.{did} はセルを持つがスロットを使う turn が無い")
        if needs_cell and not (d.get("worlds")):
            warn.append(f"designs.{did} に worlds の指定がない（既定 solo で動く）")
        # 同じ turn を複数回使う設計は、何回目かの区別が要る
        for tid in set(tl):
            if tl.count(tid) > 1 and not d.get("orders"):
                warn.append(f"designs.{did} は {tid} を {tl.count(tid)} 回使うが orders が無く順序が決まらない")

    # --- 未使用の定義
    for label, defined, used in (("templates", set(TP), used_tp),
                                 ("claims", set(CL), used_cl),
                                 ("arrivals", set(AR), used_ar),
                                 ("orders", set(OR), used_or),
                                 ("turns", set(T), used_t),
                                 ("worlds", set(W), used_w)):
        unused = sorted(defined - used)
        if unused:
            warn.append(f"どの設計からも使われていない {label}: {unused}")
    for side in ("north", "south"):
        unused = sorted(set(SL[side]) - used_slot[side])
        if unused:
            warn.append(f"どの設計からも使われていない {side} スロット: {unused}")

    # --- 実データとの突き合わせ
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

    print("=== 構造検査 ===")
    if not err:
        print("  参照の切れ・不備なし")
    for e in err:
        print(f"  ✗ {e}")
    print()
    print("=== 注意 ===")
    if not warn:
        print("  なし")
    for w in warn:
        print(f"  ! {w}")
    print()
    print("=== 手元のデータに現れる条件 ===")
    for k in ("worlds", "cells", "orders", "probes"):
        if seen[k]:
            print(f"  {k}: {sorted(seen[k])}")
    # シナリオに無い条件がデータにある＝設計が実績を表せていない
    sc_cells = set()
    for d in D.values():
        for c in (d.get("cells") or []):
            sc_cells.add("".join(c))
        for seq in (d.get("orders") or {}).values():
            for c in seq:
                sc_cells.add("".join(c))
    miss = sorted(seen["cells"] - sc_cells)
    if miss:
        print(f"  ! データにあるがどの設計にも無いセル: {miss}")
    sc_orders = {o for d in D.values() for o in (d.get("orders") or {})}
    miss = sorted(seen["orders"] - sc_orders)
    if miss:
        print(f"  ! データにあるがどの設計にも無い順序: {miss}")
    sc_probes = {v for t in T.values() for v in (t.get("variants") or {})}
    sc_probes |= {tid for tid in T}
    miss = sorted(seen["probes"] - sc_probes)
    if miss:
        print(f"  ! データにあるがシナリオに無い probe: {miss}")
    sc_worlds = set(W)
    miss = sorted(seen["worlds"] - sc_worlds)
    if miss:
        print(f"  ! データにあるがシナリオに無い world: {miss}")
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
                print(txt if txt is not None else "（この組み合わせは成立しない）")
                print()
        elif tid != "decision":
            print("=" * 60)
            print(f"  {tid}  -> {t['codebook_question']}")
            print("=" * 60)
            print(turn_text(sc, tid, world=worlds[0]))
            print()


def main():
    p = argparse.ArgumentParser(description="FJF シナリオ")
    p.add_argument("--scenario", default=SCENARIO)
    p.add_argument("--verify", action="store_true", help="既存スクリプトと一致するか")
    p.add_argument("--check", action="store_true", help="シナリオの構造検査")
    p.add_argument("--mesh", action="store_true",
                   help="ターンの elicits と変数の requires の噛み合いを検査")
    p.add_argument("--lint", action="store_true", help="刺激側の点検")
    p.add_argument("--show", metavar="DESIGN", help="設計のプロンプトを出す")
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
    print("--check / --verify / --lint / --show DESIGN のいずれかを指定してください。")


if __name__ == "__main__":
    main()
