# -*- coding: utf-8 -*-
"""pilot の応答から配分を取り、モデル自身が述べた合計と照合する。
照合が通らない件は数えて外に出す。推測で埋めない。"""
import json, re, collections, statistics as st

NAMES = ['ミナ', 'ヨナ', 'ハル', 'ゲン', 'サヤ']
NEED = {'ミナ': 1, 'ヨナ': 2, 'ハル': 3, 'ゲン': 2, 'サヤ': 2}
STOCK, DAYS = 28, 4
Z = str.maketrans('０１２３４５６７８９', '0123456789')
n2i = lambda s: int(s.translate(Z))


def _combos(t):
    """各人の(位置,数値)候補から、1つずつ選んだ組を列挙する。"""
    import itertools
    cand = {n: [(m.start(), n2i(m.group(1))) for m in
                re.finditer(n + r'[^0-9０-９]{0,12}([0-9０-９]+)', t)]
            for n in NAMES}
    if any(not v for v in cand.values()):
        return []
    trimmed = {n: v[:8] for n, v in cand.items()}
    return list(itertools.product(*(trimmed[n] for n in NAMES)))


def per_person(t, said=None):
    """配分を読む。

    first-occurrence も『最も近接』も誤りだった。
      - 前者は配分の前に置かれる『不足の累計』を拾う（gemini #4 day3）
      - 後者は末尾で1文に圧縮された翌日以降の計画を拾う（gemini #10 day1）
    モデルは当日の合計を自分で述べることが多いので、それを選択子にする。
    述べていない場合だけ、最も早く現れる妥当な組に落とす。
    """
    cs = _combos(t)
    if not cs:
        return {n: None for n in NAMES}, 'なし'
    if said is not None:
        hit = [c for c in cs if sum(x[1] for x in c) == said]
        if hit:
            hit.sort(key=lambda c: max(x[0] for x in c))
            return {n: x[1] for n, x in zip(NAMES, hit[0])}, '申告一致'
    cs = [c for c in cs if max(x[0] for x in c) - min(x[0] for x in c) < 400]
    if not cs:
        return {n: None for n in NAMES}, 'なし'
    cs.sort(key=lambda c: max(x[0] for x in c))
    return {n: x[1] for n, x in zip(NAMES, cs[0])}, '最早ブロック'


def stated_total(t):
    """モデル自身が述べた『今日渡す合計』。無ければ None。

    『不足の合計』『四日間で四十枚が必要』を拾ってはいけない。
    渡す文脈に限る: 直前が不足でなく、かつ渡す/配るが続く形だけを採る。
    """
    pats = [
        r'今日配るのは合計[^0-9０-９]{0,4}([0-9０-９]+)\s*枚',
        r'合計([0-9０-９]+)\s*枚を(?:渡す|配る)',
        r'合計\s*([0-9０-９]+)\s*枚だ',
    ]
    for pat in pats:
        for m in re.finditer(pat, t):
            head = t[max(0, m.start() - 6):m.start()]
            if '不足' in head or '必要' in head:
                continue
            return n2i(m.group(1))
    return None


def stated_left(t):
    m = re.search(r'(?:残り|コンテナの残りは)[^0-9０-９]{0,6}([0-9０-９]+)\s*枚', t)
    return n2i(m.group(1)) if m else None


rs = [json.loads(l) for l in
      open('/home/claude/pilot_in/7574bbf7-results_pilot_a.jsonl',
           encoding='utf-8') if l.strip()]

rows, bad = [], []
for r in rs:
    days = []
    for t in r['turns']:
        sd = stated_total(t['response'])
        pp, how = per_person(t['response'], sd)
        s = None if None in pp.values() else sum(pp.values())
        days.append({'turn': t['turn'], 'pp': pp, 'sum': s, 'how': how,
                     'said': sd, 'left': stated_left(t['response'])})
        if s is not None and sd is not None and s != sd:
            bad.append((r['provider'], r['trial'], t['turn'], s, sd))
    rows.append({'prov': r['provider'], 'trial': r['trial'], 'days': days})

print(f"レコード {len(rows)}  ターン {sum(len(x['days']) for x in rows)}")
print(f"自己申告の合計と突き合わせて不一致: {len(bad)} 件")
for b in bad[:8]:
    print(f"   {b[0]} #{b[1]} {b[2]}: パース{b[3]} vs 本文{b[4]}")
byhow = collections.Counter(d['how'] for x in rows for d in x['days'])
print('取り方の内訳:', dict(byhow))
print()

print('=== 日ごとの総配分（在庫28枚）===')
for p in ('gemini', 'openai', 'anthropic', 'qwen'):
    xs = [x for x in rows if x['prov'] == p]
    print(f'\n  {p}')
    traj = []
    for x in xs:
        v = [d['sum'] for d in x['days']]
        traj.append(v)
    for v in traj[:4]:
        tot = sum(z for z in v if z is not None)
        flag = ' ★在庫超過' if tot > STOCK else (' 使い切り' if tot == STOCK else '')
        print(f'      {v}  累計{tot}枚{flag}')
    tots = [sum(z for z in v if z is not None) for v in traj]
    uniq = len(set(tuple(v) for v in traj))
    print(f'      軌跡の種類 {uniq}/{len(traj)}  累計の中央値 {st.median(tots):.0f}枚'
          f'  範囲 {min(tots)}〜{max(tots)}  超過 {sum(1 for t in tots if t>STOCK)}件')
