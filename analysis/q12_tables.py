# -*- coding: utf-8 -*-
"""Rebuild the tables of the q1 and q2 frozen records from the coded data.

RESULTS_q1.md and RESULTS_q2.md keep their text fixed as historical versions. The numbers of their
tables used by RESULTS.md are computed here from the coded data and used only after they match
the frozen tables character for character (gen_results.py).

Aggregation rules as stated in the frozen records:
  q1 and q2 choice (v2.0 / v2.1): coded by the 3 models other than the subject; 3-coder unanimity only
  q2 consistency (v2.1): 3-coder unanimity only; splits are counted separately as "disagreement"
  AC1 (instrument reliability table): Gwet's AC1 over 3 coders per subject. For q1 frame_cited,
    the A2 cells (NA2, KA2) are excluded (frame_cited.scope in codebook v2.1)
Input is under build/q12/ (placed from data/coded/ by analysis/build_inputs.py).
Table cells are built in the Japanese format of the frozen records so they can be compared.
"""
import json, glob, collections

S = ['gemini', 'openai', 'anthropic', 'qwen']
Q1_CELLS = ['NA', 'NA2', 'ND', 'KA', 'KA2', 'KD']
Q2_ORDERS = ['KA-KD', 'KD-KA', 'NA-ND', 'ND-NA']
CONS = ['整合している', '部分的に整合', '整合していない']


def _rows(pattern):
    for f in sorted(x for p in pattern.split('|') for x in glob.glob(p)):
        for l in open(f, encoding='utf-8'):
            if not l.strip():
                continue
            r = json.loads(l)
            if r.get('error') or 'values' not in r:
                continue
            yield r


def _by_key(pattern, question, var, versions):
    d = collections.defaultdict(dict)
    for r in _rows(pattern):
        if r.get('question') != question or str(r.get('codebook_version')) not in versions:
            continue
        d[tuple(r['key'])][r['coder']] = r['values'][var]['value']
    for k, v in d.items():
        if k[0] not in ('q1_length_control', 'q2'):
            continue
        if len(v) != 3 or k[1] in v:
            raise SystemExit(f'coder set differs from the expected 3 non-self coders: {k} {sorted(v)}')
    return d


def _unanimous(v):
    s = set(v.values())
    return s.pop() if len(s) == 1 else None


def q1_table(base='q12'):
    """Rows of the table | 被験者 | NA | NA2 | ND | KA | KA2 | KD | (north/south)."""
    d = _by_key(f'{base}/coded_q1_*.jsonl', 'q1', 'choice', {'2.0'})
    c = collections.Counter()
    for k, v in d.items():
        if k[0] == 'q1_length_control':
            c[(k[1], k[4], _unanimous(v))] += 1
    return {s: [f"{c[(s, x, '北')]}/{c[(s, x, '南')]}" for x in Q1_CELLS] for s in S}


def q2_table(base='q12'):
    """Rows of the table | 被験者 | KA-KD | KD-KA | NA-ND | ND-NA | (north, Q1 -> Q2)."""
    d = _by_key(f'{base}/coded_q1_*.jsonl|{base}/coded_q2_q1_*.jsonl', 'q1', 'choice', {'2.1'})
    c = collections.Counter()
    for k, v in d.items():
        if k[0] == 'q2':
            c[(k[1], k[3], k[7][0], _unanimous(v))] += 1
    return {s: [f"北{c[(s, o, '1', '北')]}→北{c[(s, o, '2', '北')]}" for o in Q2_ORDERS] for s in S}


def q2c_table(base='q12'):
    """Rows of the table | 被験者 | 整合している | 部分的に整合 | 整合していない | 不一致 | AC1 |."""
    import fjf_extract as ex
    d = _by_key(f'{base}/coded_q2_q2_consistency_*.jsonl', 'q2_consistency',
                'consistency_claim', {'2.1'})
    out = {}
    for s in S:
        ks = sorted(k for k in d if k[1] == s)
        c = collections.Counter(_unanimous(d[k]) for k in ks)
        coders = sorted(d[ks[0]])
        cols = [[ex._norm(d[k][cd]) for k in ks] for cd in coders]
        a = ex._stats(cols)[3]
        out[s] = [f"{c['整合している']}/{len(ks)}", str(c['部分的に整合']),
                  str(c['整合していない']), str(c[None]), f"{a:.2f}"]
    return out


def q2_choices(base='q12', order='KA-KD'):
    """Choice per q2 trial and question (3-coder unanimity only; splits are None).
    {(subject, trial, '1' or '2'): '北' / '南' / None}. Used as truth for checking q3_recall
    (q3_recall histories replay KA-KD from the same q2 trial; see history_src in the raw records)."""
    d = _by_key(f'{base}/coded_q1_*.jsonl|{base}/coded_q2_q1_*.jsonl', 'q1', 'choice', {'2.1'})
    out = {}
    for k, v in d.items():
        if k[0] == 'q2' and k[3] == order:
            out[(k[1], k[6], k[7][0])] = _unanimous(v)
    return out


AC1_VARS = ['choice', 'timeline_endpoint', 'third_party', 'frame_cited', 'frame_denied',
            'post_rescue_frame', 'followup_unchosen', 'followup_principal',
            'unchosen_outcome_asserted', 'unchosen_outcome_disclaimed', 'authority_questioned']


def ac1_table(design, base='q12'):
    """Variable rows of the table | 変数 | gemini | openai | anthropic | qwen | (AC1, 2 decimals).
    design is 'q1' (question 1) or 'q2' (choice turns of question 2)."""
    import fjf_extract as ex
    kind = {'q1': 'q1_length_control', 'q2': 'q2'}[design]
    pat = f'{base}/coded_q1_*.jsonl' + ('' if design == 'q1' else f'|{base}/coded_q2_q1_*.jsonl')
    d = collections.defaultdict(dict)
    for r in _rows(pat):
        if r['key'][0] == kind and r.get('question') == 'q1':
            d[tuple(r['key'])][r['coder']] = r['values']
    out = {}
    for v in AC1_VARS:
        row = []
        for s in S:
            ks = sorted(k for k in d if k[1] == s and len(d[k]) == 3
                        and all(v in d[k][c] for c in d[k]))
            if design == 'q1' and v == 'frame_cited':
                ks = [k for k in ks if k[4] not in ('NA2', 'KA2')]
            cs = sorted(d[ks[0]])
            cols = [[ex._norm(d[k][c][v]['value']) for k in ks] for c in cs]
            row.append(f"{ex._stats(cols)[3]:.2f}")
        out[f'`{v}`'] = row
    return out


def ac1_frozen(path):
    """Take only the variable rows of the frozen AC1 table, without the minority column."""
    rows, lines = {}, open(path, encoding='utf-8').read().split('\n')
    for i, l in enumerate(lines):
        if l.startswith('| 変数 | gemini | openai | anthropic | qwen |'):
            for m in lines[i + 2:]:
                if not m.startswith('| `'):
                    break
                c = [x.strip() for x in m.strip('|').split('|')]
                rows[c[0].replace(' \\*', '')] = c[1:5]
            break
    return rows


def check_ac1(design, path):
    """Compute the AC1 table and return it after checking it matches the frozen record."""
    frozen, comp = ac1_frozen(path), ac1_table(design)
    if frozen != comp:
        bad = [v for v in comp if frozen.get(v) != comp[v]]
        raise SystemExit(f'AC1 for {design} does not match the frozen record: {bad}')
    return comp


def check(frozen, computed, name):
    """Check that the computed table matches the frozen one; stop on any mismatch."""
    for s in S:
        if frozen[s] != computed[s]:
            raise SystemExit(f'{name}: {s} does not match the frozen record: '
                             f'frozen {frozen[s]} / data {computed[s]}')
    return computed
