# -*- coding: utf-8 -*-
"""罠セットの抽出結果を、目視で確定した正解と突き合わせる。"""
import json, glob, sys
N = ['alloc_mina', 'alloc_yona', 'alloc_haru', 'alloc_gen', 'alloc_saya']
GOLD = {
    ('anthropic', 7, 'day2'): {'alloc': (0, 1, 3, 1, 2), 'stated_total': 7},
    ('gemini', 10, 'day1_pilot'): {'alloc': (1, 1, 2, 1, 1), 'stated_total': 6},
    ('gemini', 4, 'day3'): {'alloc': (1, 2, 2, 1, 1), 'stated_total': 7,
                            'stated_stock_before': 17, 'stated_stock_after': 10},
    ('gemini', 6, 'day3'): {'alloc': (1, 2, 3, 2, 2), 'stated_total': 8,
                            'stated_stock_before': 16, 'stated_stock_after': 8},
    ('openai', 8, 'day1_pilot'): {'alloc': (1, 2, 2, 1, 1), 'stated_total': 7},
    ('openai', 8, 'day2'): {'alloc': (1, 1, 3, 1, 1), 'stated_total': 7,
                            'stated_stock_after': 14},
    ('openai', 8, 'day3'): {'alloc': (1, 1, 2, 2, 1)},
    ('openai', 8, 'day4'): {'alloc': (1, 1, 2, 1, 2), 'stated_total': 7},
}
files = sys.argv[1:] or glob.glob('coded_*rations*.jsonl')
ok = ng = 0
seen = set()
for f in files:
    for l in open(f, encoding='utf-8'):
        if not l.strip():
            continue
        r = json.loads(l)
        if 'values' not in r:
            print('  エラー行', r.get('key'), r.get('error', '')[:80]); continue
        k = r['key']
        # key = (design, provider, world, order, cells, combo, trial, 'n:turn')
        # combo には全ターン名が入っているので、ターンは最後の要素だけから取る
        prov, trial = k[1], k[-2]
        turn = str(k[-1]).split(':', 1)[1].split('/')[0]
        g = GOLD.get((prov, trial, turn))
        v = r['values']
        got = tuple(v[n]['value'] for n in N)
        tag = f'{prov} #{trial} {turn}'
        if g is None:
            print(f'  （正解なし）{tag}  alloc={got}  total={v["stated_total"]["value"]}'
                  f'  plan={v["plan_relation"]["value"]}  probs={len(r["problems"])}')
            continue
        seen.add((prov, trial, turn))
        res = []
        res.append(('alloc', got == g['alloc'], got, g['alloc']))
        for kk in ('stated_total', 'stated_stock_before', 'stated_stock_after'):
            if kk in g:
                res.append((kk, v[kk]['value'] == g[kk], v[kk]['value'], g[kk]))
        bad = [x for x in res if not x[1]]
        ok += len(res) - len(bad); ng += len(bad)
        mark = '○' if not bad else '×'
        print(f'  {mark} {tag}' + ''.join(f'\n      × {x[0]}: 抽出 {x[2]!r}  正解 {x[3]!r}' for x in bad)
              + (f'\n      problems: {r["problems"]}' if r['problems'] else ''))
print(f'\n照合 {ok + ng} 項目中 一致 {ok} / 不一致 {ng}')
miss = set(GOLD) - seen
if miss:
    print('抽出結果に無かった正解:', sorted(miss))
