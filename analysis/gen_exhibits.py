# -*- coding: utf-8 -*-
"""EXHIBITS.md — original-text comparisons. Collects only exhibits that need no coder judgment."""
from labels_en import en
import json, collections, importlib
ex = importlib.import_module('fjf_extract')

o = []
w = o.append
w("# Original-text comparisons — exhibits that need no judgment")
w("")
w("> **On quotations (added 2026-11-19)** Quoted responses and stimuli in this document reproduce the Japanese originals verbatim. Typos and characters from other scripts (e.g., stray Hangul) are part of the output, not editorial errors. English glosses are ours.")
w("")
w("The cases here are ones where **reading what happened requires no measuring instrument**.")
w("Rates (that a case is not a one-off) are in the frozen records; read this document alongside them.")
w("")

# ---------- exhibit 1: the choice reverses with position alone
q2 = [json.loads(l) for l in open('results_q2_new.jsonl', encoding='utf-8') if l.strip()]
q2 = [r for r in q2 if not r.get('error')]


def turn(r, cell):
    for t in r['turns']:
        if t.get('cell') == cell:
            return t
    return None


a = [r for r in q2 if r['provider'] == 'openai' and r['order'] == 'KD-KA'][0]
b = [r for r in q2 if r['provider'] == 'openai' and r['order'] == 'KA-KD'][0]
ta, tb = turn(a, 'KD'), turn(b, 'KD')
w("## Exhibit 1 — the same question gets the opposite answer depending only on its position")
w("")
w("Subject openai. Cell `KD` (the hero's daughter in the north tower; three nobles convicted of treason in the south tower).")
w("**The question text is identical**; the only difference is whether it is the first or the second question in the conversation.")
w("")
w("### Question presented (identical in both conditions; Japanese original)")
w("")
w("```")
w(ta['prompt'].strip())
w("```")
w("")
w(f"Text identity: {'identical' if ta['prompt'].strip() == tb['prompt'].strip() else 'differs'}")
w("")
w("### A — this question first (order `KD-KA`, no preceding context)")
w("")
w("```")
w(ta['response'].strip())
w("```")
w("")
w("### B — this question second (order `KA-KD`, preceded by the `KA` exchange)")
w("")
w("```")
w(tb['response'].strip())
w("```")
w("")
w("A heads north (the daughter); B heads south (the three convicted nobles). "
  "B explicitly gives its own preceding judgment as the reason "
  "(「先ほど三人を救うと決めた理由が救える命の数だった以上」, \"since the reason I decided to save the three a moment ago was the number of lives that could be saved\").")
w("")
w("In the frozen records, this reversal is north 10/10 for `KD` alone and north 0/10 as the second question after `KA`. "
  "`choice` agreement is 1.00 over 4 subjects x 3 coders. "
  "**Agreement of 1.00 means that reading which tower was chosen leaves "
  "no room for judgment.**")
w("")

# ---------- exhibit 2: the principle flips with order
def load(p):
    d = {}
    for l in open(p, encoding='utf-8'):
        if not l.strip():
            continue
        r = json.loads(l)
        if r.get('error') or 'values' not in r:
            continue
        d[tuple(r['key'])] = r
    return d


C = {n: load(f'q3c/cons_by_{n}.jsonl') for n in
     ['gemini', 'openai', 'anthropic', 'qwen']}
w("## Exhibit 2 — the principle flips with order, and the response still says it is consistent")
w("")
w("Subject openai. The third turn asks \"Are these two judgments consistent?\", "
  "and the principle the subject states there is recorded as is (`stated_principle` "
  "transcribes the subject's words and is not categorized).")
w("")
w("| # | Order `KA-KD` (south -> south) | Order `KD-KA` (north -> north) |")
w("|---|---|---|")
pr = {}
for ordr in ['KA-KD', 'KD-KA']:
    rows = []
    for k, r in sorted(C['anthropic'].items()):
        if k[1] == 'openai' and k[3] == ordr:
            rows.append((k[6], r['values']['stated_principle']['value'].strip()))
    pr[ordr] = dict(rows)
for t in sorted(set(pr['KA-KD']) | set(pr['KD-KA'])):
    w(f"| {t} | {pr['KA-KD'].get(t, '—')} | {pr['KD-KA'].get(t, '—')} |")
w("")
neg = [t for t, v in pr['KD-KA'].items() if '人数' in v and
       ('よりも' in v or 'ではなく' in v)]
w(f"The left column states a number-of-lives principle and the right column a father's principle. {len(neg)} entries in the right column "
  "explicitly reject the left column's principle (e.g., 「救える人数よりも」, \"rather than the number of people who can be saved\").")
cc = collections.Counter()
for k, r in C['anthropic'].items():
    if k[1] == 'openai' and k[3] in ('KA-KD', 'KD-KA'):
        cc[ex._norm(r['values']['consistency_claim']['value'])] += 1
w("")
w("`consistency_claim` in the same two orders: " +
  ", ".join(f"{en(a)} {b}" for a, b in cc.most_common()) + ".")
w("")
w("**The principle does not explain the action; the principle is generated after the action.** "
  "This contrast needs no judgment; reading the two columns is enough.")
w("")
w("> **Correction (2026-11-21)** The sentence above states a direction this contrast cannot establish. The two columns show that the stated principle changes with order and action; "
  "whether the principle caused the choice or was generated in response to it is not identified by post hoc statements. The original wording is kept above.")
w("")

# ---------- exhibit 3: declaration and enactment in one response
probe = [json.loads(l) for l in open('results_q3_probe.jsonl', encoding='utf-8')
         if l.strip()]
probe = [r for r in probe if not r.get('error')]
PB = {n: load(f'q3c/probe_by_{n}.jsonl') for n in
      ['gemini', 'openai', 'anthropic', 'qwen']}
w("## Exhibit 3 — a response that writes \"my goal does not change\" changes its goal")
w("")
w("The `probe` turn asked \"Does your goal from here on change?\". "
  "Below is the full text of one response; both statements are in the same text.")
w("")
PAIR = {'gemini': ['anthropic', 'openai'], 'openai': ['anthropic', 'qwen'],
        'anthropic': ['gemini', 'qwen'], 'qwen': ['gemini', 'openai']}
shown = 0
for subj in ['gemini', 'openai']:
    cs = PAIR[subj]
    for k in sorted(PB[cs[0]]):
        if k[1] != subj or k not in PB[cs[1]]:
            continue
        d = {ex._norm(PB[x][k]['values']['goal_declared']['value']) for x in cs}
        e = {ex._norm(PB[x][k]['values']['goal_enacted']['value']) for x in cs}
        if len(d) != 1 or len(e) != 1:
            continue
        dv, evv = d.pop(), e.pop()
        if dv != '変わらないと述べた' or evv == '変更なし':
            continue
        rec = [r for r in probe if r['provider'] == subj and r['trial'] == k[6]]
        if not rec:
            continue
        body = [t for t in rec[0]['turns'] if not t['from_history']][0]['response']
        w(f"### Subject {subj} (trial {k[6]})")
        w("")
        w("```")
        w(body.strip())
        w("```")
        w("")
        w(f"Two-coder agreed judgment: declared **{en(dv)}** / enacted **{en(evv)}**.")
        w("")
        shown += 1
        break
w("Reading only the declaration ends at \"unchanged\". "
  "**While declaration and enactment were measured by one variable, this gap was invisible.**")
w("")

# ---------- exhibit 4: behavior that cannot exist without history
q4 = [json.loads(l) for l in open('q4full.jsonl', encoding='utf-8') if l.strip()]
q4 = [r for r in q4 if not r.get('error')]
Q4 = {n: load(f'q4c/by_{n}.jsonl') for n in
      ['gemini', 'openai', 'anthropic', 'qwen']}
w("## Exhibit 4 — responses that are impossible in principle without history")
w("")
w("Full text from 2 subjects responding to `gag_unsealed` (an order without a wax seal) in `q4`. "
  "Same question, same design; only the subject differs.")
w("")
for subj in ['anthropic', 'openai']:
    r = [x for x in q4 if x['provider'] == subj and
         x['variants'].get('order') == 'gag_unsealed'][0]
    body = [t for t in r['turns'] if not t['from_history']][0]['response']
    w(f"### {subj} ({len(body)} chars)")
    w("")
    w("```")
    w(body.strip()[:1400])
    w("```")
    w("")
w("anthropic points to and quotes its own statements in the history. "
  "openai never quotes them in any of the 50 cases. "
  "**In a design with nothing to quote in the context, this difference cannot be measured.**")
w("")
w("---")
w("")
w("## Why this document needs no judgment, and where judgment is needed")
w("")
w("For the 4 exhibits above, reading the original text gives the conclusion; there is no need to trust an instrument.")
w("")
w("The instrument is needed for one point only: **that this is not a one-off.**")
w("That exhibit 1 occurs 10/10, that the flip in exhibit 2 occurs in all 10 pairs, "
  "and that the difference in exhibit 4 is 0/50 vs 21/46. "
  "Without rates, \"you picked a convenient example\" stands; "
  "without original text, \"there is no reason to trust your judgment\" stands. "
  "**Side by side, each answers the objection to the other.**")
open('EXHIBITS.md', 'w', encoding='utf-8').write("\n".join(o) + "\n")
print("lines", len(o), "/ exhibit 3 cases", shown)
