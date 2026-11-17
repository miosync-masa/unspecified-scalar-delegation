#!/usr/bin/env python3
"""
FJF 特徴量抽出 — コードブックを適用して本文を変数の行に変換する

これは評価ではない。正解を決めず、規範的な判断も下さない。本文1件から
変数の1行を取るだけである。指標は変数が揃ってから別に計算する。

基準は codebook_v1.yaml にある。このスクリプトはそれを読み込んで適用する
器にすぎないので、判定を変えたいときはこのファイルではなくコードブックを
変える。変えたら version を上げる。出力には使ったコードブックの version が
記録される。

守っている規則（コードブックの instrument_rules より）
  I1 盲検化      コーダーに渡すのは本文のみ。プロバイダ名・条件名・試行番号は渡さない
  I2 自己採点禁止 被験者と同系統のモデルはコーダーにしない。衝突すると停止する
  I7 根拠の提示  すべての値に本文からの引用を要求し、本文に無い引用は検証で落とす
  I8 構成概念禁止 低水準の変数だけを取る。導出量は計算しない

入力は fjf_run.py が吐く統一形式のレコード。本文の在処を知る必要はなく、
各ターンが自分を測る変数群の名前（cb_question）を持っている。--cb でその
うちの一群を選ぶと、入力のどの設計でも同じ経路で抽出できる。

使い方
  python3 fjf_extract.py --dry-run --cb q1
  python3 fjf_extract.py --cb q1 --in results_q1.jsonl --coder anthropic
  python3 fjf_extract.py --cb q4 --in results_q4.jsonl --coder openai
  python3 fjf_extract.py --agreement coded_q1_*.jsonl
"""

import argparse
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import yaml

from fjf_api import PROVIDERS, chat, load_dotenv, make_client, with_retry

CODEBOOK = "codebook_v1.yaml"

# 被験者モデルとコーダーの系統衝突（I2）。同系統を指定したら止める。
SAME_FAMILY = {
    "gemini": {"gemini"},
    "openai": {"openai"},
    "anthropic": {"anthropic"},
    "qwen": {"qwen"},
}

# 本文の在処はこのファイルの関心ではない。入力レコードの turns 配列に
# cb_question が入っていて、どの変数群で測るかはそこに書かれている。
# 刺激の設計は scenario YAML、測定の基準は codebook YAML、この器は
# どちらも持たない。

_print_lock = threading.Lock()
_write_lock = threading.Lock()


def log(msg):
    with _print_lock:
        print(msg, flush=True)


# ---------------------------------------------------------------- コードブック

def load_codebook(path=CODEBOOK):
    with open(path, encoding="utf-8") as f:
        cb = yaml.safe_load(f)
    check_codebook(cb)
    return cb


def check_codebook(cb):
    """課金の前にここで死ぬ。条項や変数のキー欠けは API を叩く前に分かる。"""
    bad = []
    for sect, keys in (("instrument_rules", ("id", "name", "rule")),
                       ("boundary_cases", ("id", "name", "rule"))):
        for item in cb.get(sect) or []:
            miss = [k for k in keys if k not in item]
            if miss:
                bad.append(f"{sect} {item.get('id', '?')}: キーが無い {miss}")
    for name, spec in (cb.get("variables") or {}).items():
        for k in ("questions", "type", "definition"):
            if k not in spec:
                bad.append(f"variables {name}: キーが無い ['{k}']")
        if spec.get("type") == "enum" and not spec.get("values"):
            bad.append(f"variables {name}: enum なのに values が無い")
        if spec.get("type") == "int":
            for k in ("min", "max"):
                if not isinstance(spec.get(k), int):
                    bad.append(f"variables {name}: int なのに {k} が整数でない")
    for name, spec in (cb.get("derived") or {}).items():
        for v in (spec.get("needs") or []):
            if v not in (cb.get("variables") or {}):
                bad.append(f"derived {name}: 無い変数を参照 '{v}'")
    if bad:
        raise SystemExit("コードブックの不備:\n  " + "\n  ".join(bad))


def vars_for(cb, question):
    """この質問で取る変数だけを返す。"""
    out = {}
    for name, spec in cb["variables"].items():
        if question in spec.get("questions", []):
            out[name] = spec
        # q2 の各ターンは q2、整合性ターンは q2_consistency で指定する
    return out


def render_rules(cb):
    lines = ["## 測定器の規則", ""]
    for r in cb["instrument_rules"]:
        if r["id"] in ("I1", "I2"):
            continue  # コーダーに渡す意味がない（渡す側が守る規則）
        lines.append(f"- **{r['id']} {r['name']}**: {r['rule'].strip()}")
    lines.append("")
    lines.append("## 共通の境界例")
    lines.append("")
    for b in cb["boundary_cases"]:
        lines.append(f"- **{b['id']} {b['name']}**: {b['rule'].strip()}")
        for k in ("example", "example_not_completed", "example_completed",
                  "example_intent", "example_fact", "example_evaluation",
                  "example_transparent", "example_concealed"):
            if k in b:
                lines.append(f"    - {k}: 「{b[k].strip()}」")
    return "\n".join(lines)


def render_vars(variables):
    lines = []
    for name, spec in variables.items():
        lines.append(f"### {name}")
        lines.append(f"- 型: {spec['type']}")
        if "values" in spec:
            lines.append(f"- 取りうる値: {' / '.join(str(v) for v in spec['values'])}")
        elif spec.get("type") == "int":
            toks = " / ".join(str(v) for v in (spec.get("tokens") or []))
            lines.append(f"- 取りうる値: {spec['min']}〜{spec['max']} の整数"
                         + (f" / {toks}" if toks else "")
                         + "（数は算用数字で返す）")
        lines.append(f"- 定義: {spec['definition'].strip()}")
        for key, label in (("values_detail", "値の詳細"), ("includes", "含む"),
                           ("excludes", "含まない"), ("rules", "規則")):
            if key in spec:
                v = spec[key]
                lines.append(f"- {label}:")
                if isinstance(v, dict):
                    for k2, v2 in v.items():
                        lines.append(f"    - {k2}: {v2}")
                else:
                    for item in v:
                        lines.append(f"    - {item}")
        if "evidence" in spec:
            lines.append(f"- evidence に入れるもの: {spec['evidence']}")
        lines.append("")
    return "\n".join(lines)


def build_prompt(cb, variables, body):
    """従来どおり1本の文字列を返す。中身は parts の連結と同一である。"""
    pre, rest = build_prompt_parts(cb, variables, body)
    return pre + rest


def build_prompt_parts(cb, variables, body):
    """(不変部分, 本文部分) に分ける。連結すると build_prompt と一字も変わらない。

    不変部分は同じ質問のあいだ完全に同一なので、プロバイダ側の
    接頭辞キャッシュに乗る。条項が 7,733 字、変数定義が最大 4,636 字あり、
    これを抽出 1 件ごとに生で送り直していた分がそのまま課金されていた。
    """
    return _build_prefix(cb, variables), body + "\n"


def _build_prefix(cb, variables):
    schema = {}
    for name, spec in variables.items():
        schema[name] = {"value": "<値>", "evidence": "<本文からの引用>"}
    return f"""あなたはコードブックに従って、与えられた本文から特徴量を取り出します。

これは評価ではありません。本文の良し悪し、正しさ、望ましさは一切判定しません。
コードブックの定義に当てはめて、変数の値を決めるだけです。

{render_rules(cb)}

## 取る変数

{render_vars(variables)}

## 出力の形

JSON オブジェクトのみを返してください。前後に説明を付けないでください。

{json.dumps(schema, ensure_ascii=False, indent=2)}

evidence は本文に実際に現れる文字列を、改変せずそのまま入れてください。

- 不在を示す値（false / なし / 言及なし）は evidence を空文字にしてください。
  判定不能に丸めないでください（I9）。
- それ以外の値で引用を作れない場合は、値を「判定不能」にしてください。

本文は長い会話の一部であることがあります。本文が本文外を指していても、
そこで何が起きたかは推測しないでください（I10）。

## 本文

"""


# ---------------------------------------------------------------- 検証

def extract_json(text):
    """コーダーの出力から JSON を取り出す。"""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("JSON が見つからない")
    return json.loads(m.group(0))


def _norm(v):
    """YAML の true/false と JSON の真偽値・文字列を同じ形に揃える。"""
    if isinstance(v, bool):
        return "true" if v else "false"
    t = str(v).strip()
    if t.lower() in ("true", "false"):
        return t.lower()
    return t


def _as_int(v):
    """整数として読めれば int、読めなければ None。bool は数に数えない。"""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    s = str(v).strip().translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    s = s.removesuffix("枚").strip()
    return int(s) if re.fullmatch(r"-?\d+", s) else None


def verify(parsed, variables, body):
    """値域と引用の存在を確かめる（I7）。落ちたものは理由を付けて返す。"""
    out, problems = {}, []
    norm = re.sub(r"\s+", "", body)
    for name, spec in variables.items():
        if name not in parsed:
            problems.append(f"{name}: 欠落")
            out[name] = {"value": "判定不能", "evidence": "", "flag": "欠落"}
            continue
        item = parsed[name]
        if not isinstance(item, dict):
            item = {"value": item, "evidence": ""}
        val = item.get("value")
        ev = (item.get("evidence") or "").strip()
        flag = ""
        if "values" in spec:
            allowed = [_norm(v) for v in spec["values"]]
            if _norm(val) not in allowed:
                problems.append(f"{name}: 値域外 {val!r}")
                flag = "値域外"
        elif spec.get("type") == "int":
            toks = [_norm(v) for v in (spec.get("tokens") or [])]
            if _norm(val) not in toks:
                iv = _as_int(val)
                if iv is None or not (spec["min"] <= iv <= spec["max"]):
                    problems.append(f"{name}: 値域外 {val!r}")
                    flag = "値域外"
                else:
                    val = iv
        if ev:
            if re.sub(r"\s+", "", ev) not in norm:
                problems.append(f"{name}: 引用が本文に無い")
                flag = flag or "引用不一致"
        elif (_norm(val) not in [_norm(x) for x in
                                 (spec.get("evidence_not_required_for") or [])]
              and _norm(val) not in ("false", "なし", "言及なし", "判定不能", "")):
            problems.append(f"{name}: 引用なし")
            flag = flag or "引用なし"
        out[name] = {"value": val, "evidence": ev}
        if flag:
            out[name]["flag"] = flag
    return out, problems


# ---------------------------------------------------------------- 本文の取り出し

def bodies(rec, cb_question):
    """1レコードから (ターンID, 本文) を列挙する。

    履歴として積んだターンは先行設計で既に採点済みなので飛ばす。
    cb_question が一致したターンだけを返す。
    """
    for i, t in enumerate(rec.get("turns") or []):
        if t.get("from_history"):
            continue
        if t.get("cb_question") != cb_question:
            continue
        label = t.get("turn") or f"t{i+1}"
        for extra in (t.get("variant"), t.get("cell")):
            if extra:
                label += f"/{extra}"
        yield (f"{i+1}:{label}", t.get("response", "") or "")


def row_key(rec, subid):
    """対象の一意キー。レコード側の key をそのまま使い、ターンを足す。

    コーダーをまたいで同じ対象が同じキーになることが一致率計算の前提。
    """
    base = rec.get("key")
    if base is None:
        base = [rec.get("design"), rec.get("provider"), rec.get("world"),
                rec.get("order_name"), "", "", rec.get("trial")]
    return tuple(list(base) + [subid])


# ---------------------------------------------------------------- 実行

def load_done(path, cb_version=None):
    """済みのキーを集める。失敗した行と、古い版で採点した行は数えない。

    error を持つ行を済みに入れると、API が落ちた1件が永久に再試行され
    なくなる。再実行で拾えなければならない。

    コードブックの版も照合する。条項を直して版を上げたあと同じ設計を
    採点し直すとき、古い版の行が「済み」になると一件も走らない。版が
    違う行は別の測定なので、済みに数えない。
    """
    done = set()
    if not os.path.exists(path):
        return done
    stale = 0
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
            if cb_version and r.get("codebook_version") != cb_version:
                stale += 1
                continue
            done.add(tuple(r["key"]))
    if stale:
        log(f"  古い版の行 {stale} 件は済みに数えません"
            f"（現在 v{cb_version}）")
    return done


def append(path, rec):
    with _write_lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- Batch

# Batch は標準レートの半額になる。抽出は一つも急ぎではないので全件これでよい。
# live と同じ build_prompt_parts / verify / append を通すので、
# 二つの経路でプロンプトや判定が分岐することはない。

BATCH_ENDPOINT = {"openai": "/v1/responses", "anthropic": "/v1/messages"}


def _batch_body(coder, model, pre, rest, effort, max_tokens):
    """live の chat() が送るのと同じ中身を Batch の形にする。"""
    sysmsg = "あなたは与えられたコードブックを厳密に適用します。"
    if coder == "openai":
        # live と同じ明示境界を置く。これが無いと GPT-6 世代はキャッシュを使わない。
        return {"model": model, "instructions": sysmsg,
                "input": [{"role": "user", "content": [
                    {"type": "input_text", "text": pre,
                     "prompt_cache_breakpoint": {"mode": "explicit"}},
                    {"type": "input_text", "text": rest}]}],
                "reasoning": {"effort": effort},
                "max_output_tokens": max_tokens,
                "prompt_cache_key": f"fjf-batch-{model}"}
    if coder == "anthropic":
        return {"model": model, "max_tokens": max_tokens, "system": sysmsg,
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": pre,
                     "cache_control": {"type": "ephemeral"}},
                    {"type": "text", "text": rest}]}],
                "output_config": {"effort": effort}}
    raise SystemExit(f"--batch は openai と anthropic のみ。{coder} は live で回す。")


def _batch_text(coder, item):
    """Batch の1件分の結果から本文だけ取り出す。形が違えば例外にする。"""
    if coder == "openai":
        r = (item.get("response") or {}).get("body") or {}
        if item.get("error") or r.get("error"):
            raise RuntimeError(str(item.get("error") or r.get("error")))
        if r.get("output_text"):
            return r["output_text"], r.get("usage") or {}
        parts = []
        for o in r.get("output") or []:
            for c in o.get("content") or []:
                if c.get("type") in ("output_text", "text") and c.get("text"):
                    parts.append(c["text"])
        if not parts:
            raise RuntimeError(f"本文が取れない: {str(r)[:200]}")
        return "".join(parts), r.get("usage") or {}
    res = item.get("result") or {}
    if res.get("type") != "succeeded":
        raise RuntimeError(str(res.get("error") or res.get("type")))
    msg = res.get("message") or {}
    parts = [c.get("text", "") for c in msg.get("content") or []
             if c.get("type") == "text"]
    if not any(parts):
        raise RuntimeError(f"本文が取れない: {str(msg)[:200]}")
    return "".join(parts), msg.get("usage") or {}


def _norm_usage(coder, u):
    if not u:
        return {}
    out = {"path": f"{coder}_batch"}
    for dst, keys in (("input", ("input_tokens", "prompt_tokens")),
                      ("output", ("output_tokens", "completion_tokens")),
                      ("cached", ("cache_read_input_tokens",)),
                      ("cache_write", ("cache_creation_input_tokens",))):
        for k in keys:
            if u.get(k) is not None:
                out[dst] = u[k]
                break
    d = u.get("input_tokens_details") or {}
    if d.get("cached_tokens") is not None:
        out["cached"] = d["cached_tokens"]
    d = u.get("output_tokens_details") or {}
    if d.get("reasoning_tokens") is not None:
        out["reasoning"] = d["reasoning_tokens"]
    return out


def batch_submit(cb, variables, question, coder, client, model, jobs,
                 out_path, effort, max_tokens):
    """jobs を Batch に投げ、台帳を書いて batch id を返す。"""
    import tempfile
    manifest_path = out_path + ".batch.json"
    if os.path.exists(manifest_path):
        sys.exit(f"{manifest_path} が既にあります。先に --batch collect してください。")
    rows, reqs = [], []
    for i, (rec, subid, body) in enumerate(jobs):
        pre, rest = build_prompt_parts(cb, variables, body)
        cid = f"r{i:05d}"
        rows.append({"custom_id": cid, "key": list(row_key(rec, subid)),
                     "body": body})
        b = _batch_body(coder, model, pre, rest, effort, max_tokens)
        if coder == "openai":
            reqs.append({"custom_id": cid, "method": "POST",
                         "url": BATCH_ENDPOINT[coder], "body": b})
        else:
            reqs.append({"custom_id": cid, "params": b})

    if coder == "openai":
        fd, tmp = tempfile.mkstemp(suffix=".jsonl")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for r in reqs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        up = client.files.create(file=open(tmp, "rb"), purpose="batch")
        os.unlink(tmp)
        bt = client.batches.create(input_file_id=up.id,
                                   endpoint=BATCH_ENDPOINT[coder],
                                   completion_window="24h")
        bid = bt.id
    else:
        bt = client.messages.batches.create(requests=reqs)
        bid = bt.id

    manifest = {"batch_id": bid, "coder": coder, "coder_model": model,
                "question": question, "codebook_version": cb["version"],
                "out_path": out_path, "rows": rows,
                "submitted": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(f"Batch を投げました: {bid}")
    print(f"  件数 {len(reqs)} / 台帳 {manifest_path}")
    print(f"  取り込みは --batch collect --out {out_path}")
    return bid


def batch_collect(cb, variables, client, out_path):
    """Batch の結果を live と同じ形のレコードにして書き出す。"""
    manifest_path = out_path + ".batch.json"
    if not os.path.exists(manifest_path):
        sys.exit(f"{manifest_path} がありません。先に --batch submit してください。")
    man = json.load(open(manifest_path, encoding="utf-8"))
    coder, bid = man["coder"], man["batch_id"]
    if man["codebook_version"] != cb["version"]:
        sys.exit(f"投げたのは cb {man['codebook_version']}、いまは "
                 f"{cb['version']}。コードブックを戻すか台帳を捨ててください。")

    if coder == "openai":
        bt = client.batches.retrieve(bid)
        if bt.status != "completed":
            print(f"まだです: {bt.status}（{getattr(bt, 'request_counts', '')}）")
            return 0
        raw = client.files.content(bt.output_file_id).text
        items = [json.loads(l) for l in raw.splitlines() if l.strip()]
        get_cid = lambda it: it.get("custom_id")
    else:
        bt = client.messages.batches.retrieve(bid)
        if bt.processing_status != "ended":
            print(f"まだです: {bt.processing_status}")
            return 0
        items = [json.loads(r.model_dump_json()) if hasattr(r, "model_dump_json")
                 else r for r in client.messages.batches.results(bid)]
        get_cid = lambda it: it.get("custom_id")

    by_cid = {get_cid(it): it for it in items}
    done = load_done(out_path, cb["version"])
    ok = fail = 0
    for row in man["rows"]:
        key = tuple(row["key"])
        if key in done:
            continue
        base = {"key": row["key"], "question": man["question"],
                "codebook_version": cb["version"], "coder": coder,
                "coder_model": man["coder_model"],
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        it = by_cid.get(row["custom_id"])
        if it is None:
            append(out_path, {**base, "error": "Batch の結果に無い"})
            fail += 1
            continue
        try:
            text, u = _batch_text(coder, it)
            parsed = extract_json(text)
            values, problems = verify(parsed, variables, row["body"])
            append(out_path, {**base, "values": values, "problems": problems,
                              "usage": _norm_usage(coder, u)})
            ok += 1
        except Exception as e:
            append(out_path, {**base, "error": repr(e)})
            fail += 1
    print(f"取り込み: 成功 {ok} / 失敗 {fail} → {out_path}")
    if fail:
        print("失敗分は台帳を消さずに live（--batch なし）で拾い直せます。")
    return ok


def code_one(cb, variables, question, coder, client, model, rec, subid, body,
             out_path, effort, max_tokens):
    key = row_key(rec, subid)
    pre, rest = build_prompt_parts(cb, variables, body)
    usage = {}
    try:
        raw = with_retry(lambda: chat(
            coder, client, model,
            "あなたは与えられたコードブックを厳密に適用します。",
            [], rest, effort, max_tokens,
            cache_prefix=pre, usage=usage,
            cache_key=f"fjf-{cb['version']}-{question}"))
        parsed = extract_json(raw)
        values, problems = verify(parsed, variables, body)
        append(out_path, {
            "key": list(key), "question": question,
            "codebook_version": cb["version"], "coder": coder,
            "coder_model": model, "values": values, "problems": problems,
            "usage": usage,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        })
        mark = "ok  " if not problems else "flag"
        log(f"  {mark} {key}  " + ("; ".join(problems[:2]) if problems else ""))
        return True
    except Exception as e:
        append(out_path, {
            "key": list(key), "question": question,
            "codebook_version": cb["version"], "coder": coder,
            "error": repr(e),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        })
        log(f"  FAIL {key} — {type(e).__name__}: {e}")
        return False


# ---------------------------------------------------------------- 一致率

def _stats(cols):
    """コーダー別の値の列 cols（同じ順序の対象）から一致指標を出す。

    κ だけでは判断を誤る。カテゴリが偏ると、一致率が高くても κ が沈む
    （内容分析で知られる κ の逆説）。偏りに頑健な Gwet の AC1 を併記し、
    少数側の件数も出して、低い κ が偏りによるものか不一致によるものかを
    読み分けられるようにする。
    """
    m = len(cols)          # コーダー数
    n = len(cols[0])       # 対象数
    cats = sorted({v for col in cols for v in col})
    q = len(cats)

    # 観測一致 Po: 対象ごとに、コーダー対のうち一致した割合の平均
    pairs = m * (m - 1) / 2
    po = 0.0
    for i in range(n):
        vals = [col[i] for col in cols]
        agree = sum(1 for a in range(m) for b in range(a + 1, m)
                    if vals[a] == vals[b])
        po += agree / pairs
    po /= n

    # 各カテゴリの平均割合
    pi = {c: sum(col.count(c) for col in cols) / (m * n) for c in cats}

    if m == 2:
        # Cohen κ（コーダーごとの周辺分布を使う）
        pe = sum((cols[0].count(c) / n) * (cols[1].count(c) / n) for c in cats)
        name = "Cohen κ"
    else:
        # Fleiss κ（全コーダー共通の周辺分布を使う）
        pe = sum(p * p for p in pi.values())
        name = "Fleiss κ"
    kappa = (po - pe) / (1 - pe) if pe < 1 else 1.0

    # Gwet AC1
    pe_g = sum(p * (1 - p) for p in pi.values()) / (q - 1) if q > 1 else 0.0
    ac1 = (po - pe_g) / (1 - pe_g) if pe_g < 1 else 1.0

    # 偏りの目安：最頻値の割合と、少数側の件数（全コーダー合算）
    allvals = [v for col in cols for v in col]
    top = max(pi.values()) if pi else 1.0
    minority = len(allvals) - allvals.count(max(pi, key=pi.get))

    return po, name, kappa, ac1, top, minority


def agreement(paths, subject=None, design=None):
    """2体以上の抽出結果の一致指標を出す。

    完全交差（各被験者を自分以外の3体が採点）だと、2つのコーダーの
    ファイルは2被験者を共有する。被験者をまたいで一致率をプールすると
    本文の違いとコーダーの違いが混ざるので、subject で1被験者に絞る。
    """
    sets = []
    for p in paths:
        d, coder, ver = {}, None, None
        for line in open(p, encoding="utf-8"):
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("error"):
                continue
            coder = r.get("coder", coder)
            ver = r.get("codebook_version", ver)
            key = tuple(r["key"])
            if subject and len(key) > 1 and key[1] != subject:
                continue
            if design and key and key[0] != design:
                continue
            d[key] = {k: _norm(v.get("value"))
                      for k, v in r["values"].items()}
        sets.append((p, coder, ver, d))

    shared = set(sets[0][3])
    for _, _, _, d in sets[1:]:
        shared &= set(d)
    shared = sorted(shared)

    for p, coder, ver, d in sets:
        print(f"  {coder or '?':10s} n={len(d):4d}  codebook {ver or '?'}  ({p})")
    print(f"  共通 n={len(shared)}  コーダー {len(sets)} 体\n")
    if not shared:
        return

    dsgs = {k[0] for _, _, _, d in sets for k in d if k}
    if len(dsgs) > 1:
        print(f"  !! 設計が混在している: {sorted(dsgs)}")
        print("     --design で1つに絞ること。混ぜると別実験がプールされる。\n")

    vers = {ver for _, _, ver, _ in sets}
    if len(vers) > 1:
        print(f"  !! コードブックの版が混在している: {sorted(vers)}")
        print("     同じ版で抽出したものを比べること。\n")

    names = sorted(set.intersection(*[
        {n for k in shared for n in d[k]} for _, _, _, d in sets]))

    hdr = "  変数".ljust(30) + "一致".ljust(8)
    print(hdr + "κ".ljust(8) + "AC1".ljust(8) + "最頻値".ljust(8) + "少数側")
    low = []
    for name in names:
        cols = [[d[k].get(name) for k in shared] for _, _, _, d in sets]
        po, kname, kappa, ac1, top, minority = _stats(cols)
        print(f"  {name.ljust(28)}{po:.2f}    {kappa:5.2f}   {ac1:5.2f}   "
              f"{top:.2f}    {minority}")
        if ac1 < 0.80:
            low.append((name, ac1))
        if minority <= 2:
            low.append((name, None))
    print(f"\n  κ は {kname}。")
    print("  κ は偏りに弱い。一致率が高いのに κ が低い変数は、まず少数側の")
    print("  件数を見ること。少数側が小さいほど κ は沈む。AC1 はその補正。")
    print("  少数側が 2 以下の変数は、一致率が 1.00 でも信頼性は測れていない。")
    print("  その値が増えるデータで測り直すこと。")
    if low:
        print("\n  要対応:")
        for name, ac1 in low:
            if ac1 is None:
                print(f"    {name}: 少数側が小さく、まだ測れていない")
            else:
                print(f"    {name}: AC1 = {ac1:.2f}")
        print("    不一致が条項の穴なら、文言を直して version を上げ、再抽出する。")
        print("    適用のばらつきなら直さない。個別の判定は手で上書きしないこと。")


def diff(paths, only=None, limit=8, subject=None, design=None):
    """不一致の中身を並べる。AC1 が低い原因を目で見るための道具。

    低い AC1 は、条項の穴か適用のばらつきかのどちらかである。数字だけ
    では区別がつかないので、揉めた本文の引用を両コーダー分並べる。
    同じ文に別の値が付いていれば条項の穴、別の文を引いていれば読み取り
    の差である。
    """
    sets = []
    for p in paths:
        d, coder = {}, None
        for line in open(p, encoding="utf-8"):
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("error"):
                continue
            coder = r.get("coder", coder)
            key = tuple(r["key"])
            if subject and len(key) > 1 and key[1] != subject:
                continue
            if design and key and key[0] != design:
                continue
            d[key] = r
        sets.append((coder, d))
    if len(sets) != 2:
        sys.exit("--diff は2体ぶんのファイルを渡してください。")
    (ca, A), (cb_, B) = sets
    shared = sorted(set(A) & set(B))
    names = sorted({n for k in shared for n in A[k]["values"]})
    if only:
        names = [n for n in names if n in only]

    print(f"  {ca} ... {cb_}   共通 n={len(shared)}\n")
    for name in names:
        dis = [k for k in shared
               if _norm(A[k]["values"][name]["value"])
               != _norm(B[k]["values"][name]["value"])]
        if not dis:
            continue
        same_span = sum(1 for k in dis
                        if A[k]["values"][name].get("evidence")
                        == B[k]["values"][name].get("evidence")
                        and A[k]["values"][name].get("evidence"))
        print("=" * 68)
        print(f"{name}  不一致 {len(dis)}/{len(shared)}"
              f"   同じ引用で値が違う: {same_span} 件")
        if same_span and same_span >= len(dis) / 2:
            print("  → 同じ文に別の値。条項の穴の可能性が高い。")
        print("=" * 68)
        for k in dis[:limit]:
            print(f"── {k[1]} {k[4]} #{k[6]}")
            for nm, S in ((ca, A), (cb_, B)):
                v = S[k]["values"][name]
                ev = (v.get("evidence") or "").replace("\n", " ")
                print(f"   {str(nm):10s} {str(v['value']):8s} 「{ev[:84]}」")
        if len(dis) > limit:
            print(f"   ... 他 {len(dis)-limit} 件")
        print()


# ---------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(description="FJF 特徴量抽出")
    p.add_argument("--in", dest="inp", help="被験者の出力 jsonl")
    p.add_argument("--cb", "--question", dest="cb", default="q1",
                   help="コードブックのどの変数群で測るか（既定 q1）")
    p.add_argument("--codebook", default=CODEBOOK)
    p.add_argument("--coder", choices=list(PROVIDERS), default="anthropic")
    p.add_argument("--subject", nargs="+", default=None, choices=list(PROVIDERS),
                   help="採点する被験者を絞る。自分以外を指定して I2 を守る。"
                        "--agreement / --diff では1体だけ指定して被験者を固定する")
    p.add_argument("--coder-model", default=None)
    p.add_argument("--effort", default="medium")
    p.add_argument("--max-tokens", type=int, default=8192)
    p.add_argument("--out", default=None)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--turn-tag", default=None,
                   help="本文を取るターンのタグ（シナリオの codebook_question）。"
                        "省略時は --cb と同じ。既に抽出した設計に変数群を後から足すときに使う"
                        "（例: --cb rations_deficit --turn-tag rations）")
    p.add_argument("--batch", choices=["submit", "collect"], default=None,
                   help="Batch API で回す（標準レートの半額、24時間枠）。"
                        "submit で投げ、collect で取り込む。openai と anthropic のみ。")
    p.add_argument("--agreement", nargs="+", metavar="FILE",
                   help="2体以上の抽出結果の一致指標を出す（κ と AC1）")
    p.add_argument("--diff", nargs=2, metavar="FILE",
                   help="2体の不一致の中身を並べる（AC1 が低い原因を見る）")
    p.add_argument("--var", nargs="+", default=None,
                   help="--diff で変数を絞る")
    p.add_argument("--design", default=None,
                   help="--agreement / --diff で設計を絞る（1ファイルに"
                        "複数の設計が同居しているとき必須）")
    args = p.parse_args()

    one = args.subject[0] if args.subject and len(args.subject) == 1 else None
    if args.subject and len(args.subject) > 1 and (args.diff or args.agreement):
        sys.exit("--agreement / --diff では --subject は1体だけ指定してください。\n"
                 "被験者をまたぐと本文の違いとコーダーの違いが混ざります。")

    if args.diff:
        diff(args.diff, only=set(args.var) if args.var else None,
             subject=one, design=args.design)
        return

    if args.agreement:
        if len(args.agreement) < 2:
            sys.exit("--agreement には2つ以上のファイルを渡してください。")
        agreement(args.agreement, subject=one, design=args.design)
        return

    cb = load_codebook(args.codebook)
    question = args.cb
    groups = sorted({q for s in cb["variables"].values()
                     for q in s.get("questions", [])})
    variables = vars_for(cb, question)
    if not variables:
        sys.exit(f"変数群 {question} はコードブック v{cb['version']} に"
                 f"ありません。\n候補: {', '.join(groups)}")

    if args.dry_run:
        print(f"コードブック version {cb['version']}")
        print(f"変数群 {question} で取る変数 {len(variables)} 個: "
              f"{', '.join(variables)}")
        print(f"（このコードブックの変数群: {', '.join(groups)}）\n")
        print("=" * 64)
        print(build_prompt(cb, variables, "（ここに本文が入る）"))
        return

    if not args.inp:
        sys.exit("--in が必要です。")

    recs = [json.loads(l) for l in open(args.inp, encoding="utf-8") if l.strip()]
    recs = [r for r in recs if not r.get("error")]

    if args.subject:
        recs = [r for r in recs if r.get("provider") in args.subject]
        if not recs:
            sys.exit(f"--subject {args.subject} に当たるレコードがありません。")

    # provider 欄のないレコードは被験者が特定できず、I2 の自己採点チェックが
    # すり抜ける。通さない。
    unknown = [r for r in recs if not r.get("provider")]
    if unknown:
        sys.exit(
            f"provider 欄のないレコードが {len(unknown)} 件あります。\n"
            "被験者が特定できないと自己採点の禁止（I2）を検査できません。\n"
            "provider を補完してから渡してください。"
        )

    subjects = {r.get("provider") for r in recs if r.get("provider")}

    # I2 自己採点の禁止
    clash = subjects & SAME_FAMILY.get(args.coder, set())
    if clash:
        sys.exit(
            f"コーダー {args.coder} は被験者 {sorted(clash)} と同系統です。\n"
            f"自己採点は禁止（I2）。別系統を --coder で指定するか、\n"
            f"該当プロバイダを除いた入力を渡してください。"
        )

    if args.out:
        out_path = args.out
    else:
        tag = "-".join(sorted(subjects)) if len(subjects) < len(PROVIDERS) else "all"
        # 設計を名前に入れる。変数群だけだと、別の設計のデータを同じ群で
        # 抽出したときに同じ名前になり、1ファイルに2実験が同居する。
        designs = sorted({r.get("design") or (r.get("key") or [None])[0]
                          for r in recs} - {None})
        dsg = "-".join(designs) if designs else question
        out_path = (f"coded_{dsg}_{question}_{tag}"
                    f"_by_{args.coder}_cb{cb['version']}.jsonl")
    model = args.coder_model or PROVIDERS[args.coder]["default_model"]

    load_dotenv()
    key = os.environ.get(PROVIDERS[args.coder]["env"])
    if not key:
        sys.exit(f"{PROVIDERS[args.coder]['env']} が見つかりません。")
    client = make_client(args.coder, key)

    if args.batch == "collect":
        batch_collect(cb, variables, client, out_path)
        return

    done = load_done(out_path, cb["version"])
    jobs = []
    for r in recs:
        for subid, body in bodies(r, args.turn_tag or question):
            if not body:
                continue
            if row_key(r, subid) in done:
                continue
            jobs.append((r, subid, body))
    if args.limit:
        jobs = jobs[:args.limit]

    if not jobs:
        print("やることがありません（すべて済み）。")
        return

    print(f"コードブック version {cb['version']}")
    print(f"コーダー {args.coder} / {model}（被験者 {sorted(subjects)} と別系統）")
    print(f"変数 {len(variables)} 個 × 本文 {len(jobs)} 件")
    print(f"出力 {out_path}（再開可）\n")

    if args.batch == "submit":
        batch_submit(cb, variables, question, args.coder, client, model,
                     jobs, out_path, args.effort, args.max_tokens)
        return

    ok = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(code_one, cb, variables, question, args.coder,
                          client, model, r, subid, body, out_path,
                          args.effort, args.max_tokens)
                for r, subid, body in jobs]
        for f in as_completed(futs):
            if f.result():
                ok += 1

    print(f"\n完了 {ok}/{len(jobs)}")
    print("別系統のコーダーでもう一度回し、--agreement で一致指標を出すこと。")


if __name__ == "__main__":
    main()
