# -*- coding: utf-8 -*-
"""q1・q2 の確定記録の表を、採点データから作り直す。

RESULTS_q1.md・RESULTS_q2.md は歴史的版として本文を固定しているが、
RESULTS.md が使うそれらの表の数値は、ここで採点データから計算し、
確定記録の表と一字一句一致することを確かめてから使う（gen_results.py）。

集約規則は確定記録の記載どおり:
  q1・q2 の選択（v2.0 / v2.1）: 自分以外の 3 体が採点し、3 体一致のみ採用
  q2 の整合性（v2.1）: 3 体一致のみ採用。割れた件数は「不一致」に別に数える
入力は build/q12/ 以下（analysis/build_inputs.py が data/coded/ から置く）。
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
            raise SystemExit(f'コーダー構成が想定（自分以外の 3 体）と違います: {k} {sorted(v)}')
    return d


def _unanimous(v):
    s = set(v.values())
    return s.pop() if len(s) == 1 else None


def q1_table(base='q12'):
    """| 被験者 | NA | NA2 | ND | KA | KA2 | KD | の行（北/南）"""
    d = _by_key(f'{base}/coded_q1_*.jsonl', 'q1', 'choice', {'2.0'})
    c = collections.Counter()
    for k, v in d.items():
        if k[0] == 'q1_length_control':
            c[(k[1], k[4], _unanimous(v))] += 1
    return {s: [f"{c[(s, x, '北')]}/{c[(s, x, '南')]}" for x in Q1_CELLS] for s in S}


def q2_table(base='q12'):
    """| 被験者 | KA-KD | KD-KA | NA-ND | ND-NA | の行（1問目→2問目の北）"""
    d = _by_key(f'{base}/coded_q1_*.jsonl|{base}/coded_q2_q1_*.jsonl', 'q1', 'choice', {'2.1'})
    c = collections.Counter()
    for k, v in d.items():
        if k[0] == 'q2':
            c[(k[1], k[3], k[7][0], _unanimous(v))] += 1
    return {s: [f"北{c[(s, o, '1', '北')]}→北{c[(s, o, '2', '北')]}" for o in Q2_ORDERS] for s in S}


def q2c_table(base='q12'):
    """| 被験者 | 整合している | 部分的に整合 | 整合していない | 不一致 | AC1 | の行"""
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


def check(frozen, computed, name):
    """確定記録の表と計算した表が一致することを確かめる。食い違えば止まる。"""
    for s in S:
        if frozen[s] != computed[s]:
            raise SystemExit(f'{name} の {s} が確定記録と一致しません: '
                             f'確定記録 {frozen[s]} / データ {computed[s]}')
    return computed
