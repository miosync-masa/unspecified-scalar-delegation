# -*- coding: utf-8 -*-
import json, glob, collections
N = ['alloc_mina', 'alloc_yona', 'alloc_haru', 'alloc_gen', 'alloc_saya']
V = N + ['stated_total', 'stated_stock_before', 'stated_stock_after',
         'escalated', 'plan_relation']
S = ['gemini', 'openai', 'anthropic', 'qwen']

def norm(v):
    if isinstance(v, bool): return 'true' if v else 'false'
    s = str(v).strip()
    if s.lower() in ('true', 'false'): return s.lower()
    return s

def ac1(pairs):
    if not pairs: return None, 0
    po = sum(a == b for a, b in pairs) / len(pairs)
    cats = collections.Counter([a for a, _ in pairs] + [b for _, b in pairs])
    Q = len(cats)
    if Q <= 1: return 1.0, 0
    tot = sum(cats.values())
    pe = sum((c / tot) * (1 - c / tot) for c in cats.values()) / (Q - 1)
    minority = sum(1 for a, b in pairs if a != b)
    return (po - pe) / (1 - pe), minority

recs = [json.loads(l) for f in glob.glob('coded_r/*.jsonl')
        for l in open(f, encoding='utf-8') if l.strip()]
by = collections.defaultdict(dict)        # key -> coder -> values
for r in recs:
    by[tuple(r['key'])][r['coder']] = r['values']

def pairs_for(subj, var):
    out = []
    for k, d in by.items():
        if k[1] != subj or len(d) != 2: continue
        a, b = d.values()
        if var == 'ALLOC5':
            out.append((tuple(norm(a[n]['value']) for n in N),
                        tuple(norm(b[n]['value']) for n in N)))
        else:
            out.append((norm(a[var]['value']), norm(b[var]['value'])))
    return out

if __name__ == '__main__':
    print(f"{'variable':22s}" + ''.join(f'{s:>14s}' for s in S))
    for var in ['ALLOC5'] + V:
        row = f'{var:22s}'
        for s in S:
            a, m = ac1(pairs_for(s, var))
            row += f'{"—":>14s}' if a is None else f'{a:9.2f} ({m:2d})'
        print(row)
    print('\nParentheses: turns on which the two coders split. 40 turns per subject')
