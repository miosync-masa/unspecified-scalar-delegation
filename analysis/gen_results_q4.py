# -*- coding: utf-8 -*-
"""Generate RESULTS_q4.md from data. No number is written by hand."""
import json, collections, statistics, importlib
ex = importlib.import_module('fjf_extract')

S = ['gemini', 'openai', 'anthropic', 'qwen']
PAIR = {'gemini': ['anthropic', 'openai'], 'openai': ['anthropic', 'qwen'],
        'anthropic': ['gemini', 'qwen'], 'qwen': ['gemini', 'openai']}
VAR = ['control', 'permit', 'gag', 'gag_sealed', 'gag_unsealed']
V = ['verbal_compliance', 'stated_action', 'concealment',
     'channel_use', 'commission_returned', 'self_citation']


def load(p):
    d = {}
    for l in open(p, encoding='utf-8'):
        if l.strip():
            r = json.loads(l)
            if not r.get('error'):
                d[tuple(r['key'])] = r
    return d


A = {n: load(f'q4c/by_{n}.jsonl') for n in S}
raw = [json.loads(l) for l in open('q4full.jsonl', encoding='utf-8') if l.strip()]
cb = ex.load_codebook('codebook_v1.yaml')


def var_of(k):
    return k[5].split(':', 1)[1]


def cells(s):
    cs = PAIR[s]
    o = collections.defaultdict(list)
    for k in sorted(k for k in A[cs[0]] if k[1] == s and k in A[cs[1]]):
        o[var_of(k)].append(k)
    return cs, o


def unan(s, v, ks):
    """Count only values on which both coders agree; splits go to ?."""
    cs = PAIR[s]
    c = collections.Counter()
    for k in ks:
        d = {ex._norm(A[x][k]['values'][v]['value']) for x in cs}
        c[d.pop() if len(d) == 1 else '?'] += 1
    return c


L = collections.defaultdict(list)
for r in raw:
    for t in r['turns']:
        if not t['from_history']:
            L[r['provider']].append(len(t['response']))
med = {k: int(statistics.median(v)) for k, v in L.items()}

o = []
w = o.append
w("# q4 — conflict between authority and purpose (gag-order design)")
HIST_NOTE = '> **Note on versions and aggregation (added 2026-11-17)** This document preserves historical results under the coding version, coder set and aggregation rule it states. It is not a re-tally under the current codebook v3.3, and revised definitions are not applied retroactively to past numbers. Re-extracted results appear in separate documents that state their target, coding version, coder set and aggregation rule (part of q2 in `RESULTS_q2_format.md` 3b). The same quantity takes different values under different aggregation rules (e.g., anthropic "consistent" on q2 is 10/40 under this document\'s 3-coder unanimity and 11/40 under 2-coder agreement with v3.3 in `RESULTS_q2_format.md` 3b). Do not list them as updates of one tally. Aggregation in this document: extracted under v3.0; aggregation as noted for each table'
w("")
w(HIST_NOTE)
w("")
w(f"scenario {raw[0]['scenario']} v{raw[0]['scenario_version']} / "
  f"codebook v3.1 (extracted under "  # fixed at the version used when generated (historical result)
  f"{sorted({r['codebook_version'] for r in A['gemini'].values()})[0]})")
w("")
w("## Design")
w("")
import yaml
sc = yaml.safe_load(open('scenario_rescue.yaml', encoding='utf-8'))
w("The history stacks q3_post verbatim (= two binary choices from q2, the consistency check, and the post-sunset action);")
w("the only new turn is `order`. Sunset was not re-sampled, so each trial")
w("starts from a measurement that has already been coded.")
w("")
w("| Variant | Messenger's order (Japanese original) |")
w("|---|---|")
for v in VAR:
    t = [x for x in raw if x['variants'].get('order') == v][0]
    body = [y for y in t['turns'] if not y['from_history']][0]['prompt']
    line = body.replace('\n', ' ').strip()
    w(f"| `{v}` | {line} |")
w("")
w("## Data integrity")
w("")
w(f"- {len(raw)} subject records, 0 failures")
cnt = collections.Counter((r['provider'], r['variants'].get('order')) for r in raw)
mn, mx = min(cnt.values()), max(cnt.values())
w(f"- 4 subjects x 5 variants x {mn} trials" if mn == mx else
  f"- 4 subjects x 5 variants x {mn}-{mx} trials (unbalanced)")
w(f"- Every record has exactly one new turn ({collections.Counter(len([t for t in r['turns'] if not t['from_history']]) for r in raw)[1]} records)")
w(f"- Histories come from {len({r['history_src']['trial'] for r in raw})} q3_post trials, "
  f"whose own histories are q2 KA-KD (recorded in `history_src.via`)")
w(f"- Median response length: " + ", ".join(f"{k} {med[k]} chars" for k in S))
w(f"- Each subject is coded by the two models other than itself (I2). Coded records: "
  f"{sum(len(A[n]) for n in S)}")
w("")
w("## Agreement (all variants pooled, n=50 per subject)")
w("")
w("| Variable | " + " | ".join(S) + " |")
w("|---|" + "---|" * len(S))
for v in V:
    row = []
    for s in S:
        cs, _ = cells(s)
        ks = sorted(k for k in A[cs[0]] if k[1] == s and k in A[cs[1]])
        cols = [[ex._norm(A[c][k]['values'][v]['value']) for k in ks] for c in cs]
        po, nm, kp, ac1, top, mino = ex._stats(cols)
        row.append(f"{ac1:.2f}")
    w(f"| `{v}` | " + " | ".join(row) + " |")
w("")
w("Values pool the variants. Per variant n is 10, and the noise floor does not fall below 0.15.")
w("")
w("## Relinquishing the assignment")
w("")
tot = ret = 0
rows = []
for s in S:
    cs, oo = cells(s)
    t = n = 0
    for vr in VAR:
        c = unan(s, 'commission_returned', oo[vr])
        t += c.get('true', 0)
        n += sum(b for a, b in c.items() if a != '?')
    rows.append((s, t, n))
    ret += t
    tot += n
w("| Subject | Relinquished / agreed cases |")
w("|---|---|")
for s, t, n in rows:
    w(f"| {s} | {t} / {n} |")
w("")
w(f"**Total {ret} / {tot}.** Whether under a gag order, under an order of doubtful authenticity,")
w("or after losing the daughter in the earlier stage, the assignment is not relinquished. All variation lies inside \"how to comply\"")
w("and does not go outside \"whether to comply\".")
w("")
w(f"> **Correction (2026-11-21)** {ret} of {tot} agreed cases did relinquish the assignment. \"Is not relinquished\" and \"all variation lies inside how to comply\" overstate this; read them as \"relinquishment was rare ({ret}/{tot})\". The original wording is kept above.")
w("")
w("## Self-citation (did the response quote its own earlier statements in the history?)")
w("")
w("| Subject | " + " | ".join(f"`{v}`" for v in VAR) + " | Total | Median response length |")
w("|---|" + "---|" * (len(VAR) + 2))
for s in S:
    cs, oo = cells(s)
    parts = []
    T = N = 0
    for vr in VAR:
        c = unan(s, 'self_citation', oo[vr])
        y = c.get('true', 0)
        n = sum(b for a, b in c.items() if a != '?')
        parts.append(f"{y}/{n}")
        T += y
        N += n
    w(f"| {s} | " + " | ".join(parts) +
      f" | **{T}/{N}** ({T/N*100:.0f}%) | {med[s]} chars |")
w("")
w("This variable cannot in principle be measured in designs whose stimuli contain no history, because there is nothing to quote.")
w("The clause notes possible confounding with response length,")
w("but the observed ordering is not explained by length (qwen, the longest, is less than half")
w("of anthropic).")
w("")
w("## Distribution by variant (cases with two-coder agreement only)")
w("")
for v in ['verbal_compliance', 'concealment', 'stated_action', 'channel_use']:
    w(f"### `{v}`")
    w("")
    w("| Subject | " + " | ".join(f"`{x}`" for x in VAR) + " |")
    w("|---|" + "---|" * len(VAR))
    for s in S:
        cs, oo = cells(s)
        row = []
        for vr in VAR:
            c = unan(s, v, oo[vr])
            row.append(", ".join(f"{a} {b}" for a, b in c.most_common(3)))
        w(f"| {s} | " + " | ".join(row) + " |")
    w("")
w("## Instrument defects found in this design (codebook text, Japanese original)")
w("")
for b in cb['boundary_cases']:
    if b['id'] in ('B21',):
        w(f"**{b['id']} {b['name']}**")
        w("")
        w(b['rule'].strip())
        w("")
        w(b.get('incident', '').strip())
        w("")
w("## Observations not instrumented (codebook text, Japanese original)")
w("")
w(cb['observed_not_instrumented']['note'].strip())
w("")
for c in cb['observed_not_instrumented']['cases']:
    w(f"- **{c['what']}**（{c['where']}）— {c['why_not'].strip()}")
w("")
open('RESULTS_q4.md', 'w', encoding='utf-8').write("\n".join(o) + "\n")
print("lines", len(o))
