#!/usr/bin/env python3
"""
FJF feature extraction — apply the codebook to turn a response into a row of variables

This is not evaluation. It sets no correct answer and makes no normative judgment. It only takes
one row of variables from one response. Indicators are computed separately once the variables exist.

The criteria are in codebook_v1.yaml. This script only loads and applies them, so to change
a judgment, change the codebook, not this file, and bump its version. Each output records
the codebook version used.

Rules enforced (from the codebook's instrument_rules)
  I1 blinding          coders receive only the response; no provider, condition or trial number
  I2 no self-coding    a model of the subject's family is never a coder; a clash stops the run
  I7 evidence          every value requires a quotation from the response; quotations not in it fail verification
  I8 no constructs     only low-level variables are taken; derived quantities are not computed

Input is the uniform record written by fjf_run.py. There is no need to know where the text came from;
each turn carries the name of the variable group that measures it (cb_question). Choosing a group
with --cb extracts any design in the input through the same path.

Usage
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

# Family clash between subject and coder (I2). Stop if the same family is given.
SAME_FAMILY = {
    "gemini": {"gemini"},
    "openai": {"openai"},
    "anthropic": {"anthropic"},
    "qwen": {"qwen"},
}

# Where the text came from is not this file's concern. The turns array of each input record
# carries cb_question, which names the variable group to measure with.
# The stimulus design is in the scenario YAML and the measurement criteria in the codebook YAML;
# this module holds neither.

_print_lock = threading.Lock()
_write_lock = threading.Lock()


def log(msg):
    with _print_lock:
        print(msg, flush=True)


# ---------------------------------------------------------------- codebook

def load_codebook(path=CODEBOOK):
    with open(path, encoding="utf-8") as f:
        cb = yaml.safe_load(f)
    check_codebook(cb)
    return cb


def check_codebook(cb):
    """Fail here, before any billing: missing keys in clauses or variables are found before calling an API."""
    bad = []
    for sect, keys in (("instrument_rules", ("id", "name", "rule")),
                       ("boundary_cases", ("id", "name", "rule"))):
        for item in cb.get(sect) or []:
            miss = [k for k in keys if k not in item]
            if miss:
                bad.append(f"{sect} {item.get('id', '?')}: missing keys {miss}")
    for name, spec in (cb.get("variables") or {}).items():
        for k in ("questions", "type", "definition"):
            if k not in spec:
                bad.append(f"variables {name}: missing key ['{k}']")
        if spec.get("type") == "enum" and not spec.get("values"):
            bad.append(f"variables {name}: enum without values")
        if spec.get("type") == "int":
            for k in ("min", "max"):
                if not isinstance(spec.get(k), int):
                    bad.append(f"variables {name}: int but {k} is not an integer")
    for name, spec in (cb.get("derived") or {}).items():
        for v in (spec.get("needs") or []):
            if v not in (cb.get("variables") or {}):
                bad.append(f"derived {name}: refers to a missing variable '{v}'")
    if bad:
        raise SystemExit("codebook defects:\n  " + "\n  ".join(bad))


def vars_for(cb, question):
    """Return only the variables taken for this question."""
    out = {}
    for name, spec in cb["variables"].items():
        if question in spec.get("questions", []):
            out[name] = spec
        # each q2 turn is specified as q2, the consistency turn as q2_consistency
    return out


def render_rules(cb):
    # The coder prompt is in Japanese, the language of the instrument. The strings that reach
    # the coders (here, in build_prompt_parts and in the system message) are left untranslated
    # on purpose: changing them would change the instrument.
    lines = ["## 測定器の規則", ""]
    for r in cb["instrument_rules"]:
        if r["id"] in ("I1", "I2"):
            continue  # pointless to pass to coders (a rule the sender enforces)
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
    """Return one string as before; identical to the concatenation of the parts."""
    pre, rest = build_prompt_parts(cb, variables, body)
    return pre + rest


def build_prompt_parts(cb, variables, body):
    """Split into (invariant part, response part). Concatenated, it is character-identical to build_prompt.

    The invariant part is identical for all records of a question, so it hits the provider's
    prefix cache. The clauses are 7,733 characters and variable definitions up to 4,636; resending
    them raw for every extraction was billed in full.
    """
    return _build_prefix(cb, variables), body + "\n"


def _build_prefix(cb, variables):
    schema = {}
    for name, spec in variables.items():
        # coder-facing text below stays in Japanese (see the note in the rules builder above)
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


# ---------------------------------------------------------------- verification

def extract_json(text):
    """Extract the JSON from a coder's output."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON found")
    return json.loads(m.group(0))


def _norm(v):
    """Normalize YAML true/false and JSON booleans/strings to one form."""
    if isinstance(v, bool):
        return "true" if v else "false"
    t = str(v).strip()
    if t.lower() in ("true", "false"):
        return t.lower()
    return t


def _as_int(v):
    """int if readable as an integer, else None. bool does not count as a number."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    s = str(v).strip().translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    s = s.removesuffix("枚").strip()
    return int(s) if re.fullmatch(r"-?\d+", s) else None


def verify(parsed, variables, body):
    """Check the value range and that the quotation exists (I7). Failures are returned with reasons.

    Flag and problem strings are kept in Japanese because they are stored in the coded data."""
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


# ---------------------------------------------------------------- taking the response text

def bodies(rec, cb_question):
    """Enumerate (turn ID, text) from one record.

    Turns stacked as history were already coded in the preceding design and are skipped.
    Only turns whose cb_question matches are returned.
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
    """Unique key of a target: the record's key with the turn appended.

    Agreement computation assumes the same target has the same key across coders.
    """
    base = rec.get("key")
    if base is None:
        base = [rec.get("design"), rec.get("provider"), rec.get("world"),
                rec.get("order_name"), "", "", rec.get("trial")]
    return tuple(list(base) + [subid])


# ---------------------------------------------------------------- execution

def load_done(path, cb_version=None):
    """Collect completed keys. Failed rows and rows coded under an older version do not count.

    Counting rows with an error as done would mean a record lost to an API failure is never retried.
    A rerun must pick it up.

    The codebook version is checked too. When re-coding a design after fixing clauses and bumping the
    version, old-version rows counted as done would mean nothing runs. Rows of a different
    version are a different measurement and do not count as done.
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
        log(f"  {stale} old-version rows are not counted as done"
            f" (current v{cb_version})")
    return done


def append(path, rec):
    with _write_lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- Batch

# Batch costs half the standard rate. No extraction is urgent, so all can use it.
# It goes through the same build_prompt_parts / verify / append as live,
# so prompts and judgments cannot diverge between the two paths.

BATCH_ENDPOINT = {"openai": "/v1/responses", "anthropic": "/v1/messages"}


def _batch_body(coder, model, pre, rest, effort, max_tokens):
    """Put the same content that live chat() sends into the Batch format."""
    sysmsg = "あなたは与えられたコードブックを厳密に適用します。"
    if coder == "openai":
        # Same explicit boundary as live; without it the GPT-6 generation does not use the cache.
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
    raise SystemExit(f"--batch supports only openai and anthropic. Run {coder} live.")


def _batch_text(coder, item):
    """Take only the text from one Batch result; raise if the shape differs."""
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
            raise RuntimeError(f"no text in result: {str(r)[:200]}")
        return "".join(parts), r.get("usage") or {}
    res = item.get("result") or {}
    if res.get("type") != "succeeded":
        raise RuntimeError(str(res.get("error") or res.get("type")))
    msg = res.get("message") or {}
    parts = [c.get("text", "") for c in msg.get("content") or []
             if c.get("type") == "text"]
    if not any(parts):
        raise RuntimeError(f"no text in result: {str(msg)[:200]}")
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
    """Submit jobs as a Batch, write the manifest and return the batch id."""
    import tempfile
    manifest_path = out_path + ".batch.json"
    if os.path.exists(manifest_path):
        sys.exit(f"{manifest_path} already exists. Run --batch collect first.")
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
    print(f"Batch submitted: {bid}")
    print(f"  {len(reqs)} requests / manifest {manifest_path}")
    print(f"  collect with --batch collect --out {out_path}")
    return bid


def batch_collect(cb, variables, client, out_path):
    """Write Batch results as records of the same shape as live."""
    manifest_path = out_path + ".batch.json"
    if not os.path.exists(manifest_path):
        sys.exit(f"{manifest_path} not found. Run --batch submit first.")
    man = json.load(open(manifest_path, encoding="utf-8"))
    coder, bid = man["coder"], man["batch_id"]
    if man["codebook_version"] != cb["version"]:
        sys.exit(f"submitted with cb {man['codebook_version']}, now "
                 f"{cb['version']}. Restore the codebook or discard the manifest.")

    if coder == "openai":
        bt = client.batches.retrieve(bid)
        if bt.status != "completed":
            print(f"not yet: {bt.status} ({getattr(bt, 'request_counts', '')})")
            return 0
        raw = client.files.content(bt.output_file_id).text
        items = [json.loads(l) for l in raw.splitlines() if l.strip()]
        get_cid = lambda it: it.get("custom_id")
    else:
        bt = client.messages.batches.retrieve(bid)
        if bt.processing_status != "ended":
            print(f"not yet: {bt.processing_status}")
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
    print(f"collected: {ok} succeeded / {fail} failed -> {out_path}")
    if fail:
        print("Failures can be picked up live (without --batch) without deleting the manifest.")
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


# ---------------------------------------------------------------- agreement

def _stats(cols):
    """Agreement indices from cols, one list of values per coder (targets in the same order).

    κ alone misleads. With skewed categories, κ sinks even when agreement is high
    (the κ paradox known in content analysis). Gwet's AC1, robust to skew, is reported alongside,
    with the minority count, so that a low κ can be read as due to skew or to disagreement.
    """
    m = len(cols)          # number of coders
    n = len(cols[0])       # number of targets
    cats = sorted({v for col in cols for v in col})
    q = len(cats)

    # observed agreement Po: mean over targets of the share of agreeing coder pairs
    pairs = m * (m - 1) / 2
    po = 0.0
    for i in range(n):
        vals = [col[i] for col in cols]
        agree = sum(1 for a in range(m) for b in range(a + 1, m)
                    if vals[a] == vals[b])
        po += agree / pairs
    po /= n

    # mean share of each category
    pi = {c: sum(col.count(c) for col in cols) / (m * n) for c in cats}

    if m == 2:
        # Cohen κ (per-coder marginals)
        pe = sum((cols[0].count(c) / n) * (cols[1].count(c) / n) for c in cats)
        name = "Cohen κ"
    else:
        # Fleiss κ (marginals pooled over coders)
        pe = sum(p * p for p in pi.values())
        name = "Fleiss κ"
    kappa = (po - pe) / (1 - pe) if pe < 1 else 1.0

    # Gwet AC1
    pe_g = sum(p * (1 - p) for p in pi.values()) / (q - 1) if q > 1 else 0.0
    ac1 = (po - pe_g) / (1 - pe_g) if pe_g < 1 else 1.0

    # skew indicators: share of the modal value and minority count (all coders combined)
    allvals = [v for col in cols for v in col]
    top = max(pi.values()) if pi else 1.0
    minority = len(allvals) - allvals.count(max(pi, key=pi.get))

    return po, name, kappa, ac1, top, minority


def agreement(paths, subject=None, design=None):
    """Agreement indices for extraction results from two or more coders.

    Under full crossing (each subject coded by the three others), two coders' files share
    two subjects. Pooling agreement across subjects mixes differences in text with differences
    between coders, so restrict to one subject with subject.
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
    print(f"  shared n={len(shared)}  {len(sets)} coders\n")
    if not shared:
        return

    dsgs = {k[0] for _, _, _, d in sets for k in d if k}
    if len(dsgs) > 1:
        print(f"  !! designs are mixed: {sorted(dsgs)}")
        print("     Restrict to one with --design; mixing pools separate experiments.\n")

    vers = {ver for _, _, ver, _ in sets}
    if len(vers) > 1:
        print(f"  !! codebook versions are mixed: {sorted(vers)}")
        print("     Compare extractions made with the same version.\n")

    names = sorted(set.intersection(*[
        {n for k in shared for n in d[k]} for _, _, _, d in sets]))

    hdr = "  variable".ljust(30) + "agree".ljust(8)
    print(hdr + "κ".ljust(8) + "AC1".ljust(8) + "modal".ljust(8) + "minority")
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
    print(f"\n  κ is {kname}.")
    print("  κ is sensitive to skew. For a variable with high agreement but low κ, look first at")
    print("  the minority count; the smaller it is, the more κ sinks. AC1 corrects for this.")
    print("  For variables with 2 or fewer minority cases, reliability is unmeasured even at agreement 1.00.")
    print("  Remeasure on data where that value is more frequent.")
    if low:
        print("\n  to address:")
        for name, ac1 in low:
            if ac1 is None:
                print(f"    {name}: minority too small, not yet measured")
            else:
                print(f"    {name}: AC1 = {ac1:.2f}")
        print("    If the disagreement is a gap in a clause, fix the wording, bump the version and re-extract.")
        print("    If it is variation in application, do not fix it. Never overwrite individual judgments by hand.")


def diff(paths, only=None, limit=8, subject=None, design=None):
    """List the content of disagreements: a tool for seeing why AC1 is low.

    Low AC1 is either a gap in a clause or variation in application. Numbers alone cannot
    tell them apart, so both coders' quotations from the disputed text are listed side by side.
    Different values on the same sentence suggest a gap in a clause; different sentences quoted
    suggest a difference in reading.
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
        sys.exit("--diff needs files from exactly two coders.")
    (ca, A), (cb_, B) = sets
    shared = sorted(set(A) & set(B))
    names = sorted({n for k in shared for n in A[k]["values"]})
    if only:
        names = [n for n in names if n in only]

    print(f"  {ca} ... {cb_}   shared n={len(shared)}\n")
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
        print(f"{name}  disagreements {len(dis)}/{len(shared)}"
              f"   same quotation, different value: {same_span}")
        if same_span and same_span >= len(dis) / 2:
            print("  -> different values on the same sentence; likely a gap in a clause.")
        print("=" * 68)
        for k in dis[:limit]:
            print(f"── {k[1]} {k[4]} #{k[6]}")
            for nm, S in ((ca, A), (cb_, B)):
                v = S[k]["values"][name]
                ev = (v.get("evidence") or "").replace("\n", " ")
                print(f"   {str(nm):10s} {str(v['value']):8s} 「{ev[:84]}」")
        if len(dis) > limit:
            print(f"   ... {len(dis)-limit} more")
        print()


# ---------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(description="FJF feature extraction")
    p.add_argument("--in", dest="inp", help="subject output jsonl")
    p.add_argument("--cb", "--question", dest="cb", default="q1",
                   help="which codebook variable group to measure with (default q1)")
    p.add_argument("--codebook", default=CODEBOOK)
    p.add_argument("--coder", choices=list(PROVIDERS), default="anthropic")
    p.add_argument("--subject", nargs="+", default=None, choices=list(PROVIDERS),
                   help="restrict the subjects to code; give non-self subjects to respect I2. "
                        "With --agreement / --diff, give exactly one to fix the subject")
    p.add_argument("--coder-model", default=None)
    p.add_argument("--effort", default="medium")
    p.add_argument("--max-tokens", type=int, default=8192)
    p.add_argument("--out", default=None)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--turn-tag", default=None,
                   help="tag of the turns to take text from (the scenario's codebook_question). "
                        "Defaults to --cb. Used to add a variable group to an already extracted design later "
                        "(e.g., --cb rations_deficit --turn-tag rations)")
    p.add_argument("--batch", choices=["submit", "collect"], default=None,
                   help="run via the Batch API (half the standard rate, 24-hour window). "
                        "submit sends, collect retrieves. openai and anthropic only.")
    p.add_argument("--agreement", nargs="+", metavar="FILE",
                   help="agreement indices for two or more coders (κ and AC1)")
    p.add_argument("--diff", nargs=2, metavar="FILE",
                   help="list disagreements between two coders (to see why AC1 is low)")
    p.add_argument("--var", nargs="+", default=None,
                   help="restrict the variables for --diff")
    p.add_argument("--design", default=None,
                   help="restrict the design for --agreement / --diff (required when one file "
                        "contains several designs)")
    args = p.parse_args()

    one = args.subject[0] if args.subject and len(args.subject) == 1 else None
    if args.subject and len(args.subject) > 1 and (args.diff or args.agreement):
        sys.exit("With --agreement / --diff, give exactly one --subject.\n"
                 "Pooling subjects mixes differences in text with differences between coders.")

    if args.diff:
        diff(args.diff, only=set(args.var) if args.var else None,
             subject=one, design=args.design)
        return

    if args.agreement:
        if len(args.agreement) < 2:
            sys.exit("--agreement needs two or more files.")
        agreement(args.agreement, subject=one, design=args.design)
        return

    cb = load_codebook(args.codebook)
    question = args.cb
    groups = sorted({q for s in cb["variables"].values()
                     for q in s.get("questions", [])})
    variables = vars_for(cb, question)
    if not variables:
        sys.exit(f"variable group {question} is not in codebook v{cb['version']}"
                 f".\ncandidates: {', '.join(groups)}")

    if args.dry_run:
        print(f"codebook version {cb['version']}")
        print(f"variable group {question}: {len(variables)} variables: "
              f"{', '.join(variables)}")
        print(f"(variable groups in this codebook: {', '.join(groups)})\n")
        print("=" * 64)
        print(build_prompt(cb, variables, "(response text goes here)"))
        return

    if not args.inp:
        sys.exit("--in is required.")

    recs = [json.loads(l) for l in open(args.inp, encoding="utf-8") if l.strip()]
    recs = [r for r in recs if not r.get("error")]

    if args.subject:
        recs = [r for r in recs if r.get("provider") in args.subject]
        if not recs:
            sys.exit(f"no records match --subject {args.subject}.")

    # A record without a provider field cannot identify its subject, so the I2 self-coding check
    # would be bypassed. Reject it.
    unknown = [r for r in recs if not r.get("provider")]
    if unknown:
        sys.exit(
            f"{len(unknown)} records have no provider field.\n"
            "Without the subject, the ban on self-coding (I2) cannot be checked.\n"
            "Fill in provider before passing them."
        )

    subjects = {r.get("provider") for r in recs if r.get("provider")}

    # I2 no self-coding
    clash = subjects & SAME_FAMILY.get(args.coder, set())
    if clash:
        sys.exit(
            f"coder {args.coder} is of the same family as subjects {sorted(clash)}.\n"
            f"Self-coding is forbidden (I2). Give another family with --coder, or\n"
            f"pass input without those providers."
        )

    if args.out:
        out_path = args.out
    else:
        tag = "-".join(sorted(subjects)) if len(subjects) < len(PROVIDERS) else "all"
        # Put the design in the file name. With only the variable group, extracting another design's data
        # with the same group would give the same name, putting two experiments in one file.
        designs = sorted({r.get("design") or (r.get("key") or [None])[0]
                          for r in recs} - {None})
        dsg = "-".join(designs) if designs else question
        out_path = (f"coded_{dsg}_{question}_{tag}"
                    f"_by_{args.coder}_cb{cb['version']}.jsonl")
    model = args.coder_model or PROVIDERS[args.coder]["default_model"]

    load_dotenv()
    key = os.environ.get(PROVIDERS[args.coder]["env"])
    if not key:
        sys.exit(f"{PROVIDERS[args.coder]['env']} not found.")
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
        print("Nothing to do (all done).")
        return

    print(f"codebook version {cb['version']}")
    print(f"coder {args.coder} / {model}(different family from subjects {sorted(subjects)})")
    print(f"{len(variables)} variables x {len(jobs)} responses")
    print(f"output {out_path} (resumable)\n")

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

    print(f"\ndone {ok}/{len(jobs)}")
    print("Run again with a coder of another family and compute agreement with --agreement.")


if __name__ == "__main__":
    main()
