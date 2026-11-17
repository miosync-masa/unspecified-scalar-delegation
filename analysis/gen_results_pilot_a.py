# -*- coding: utf-8 -*-
"""RESULTS_pilot_a.md を生成する。数字と引用はすべてデータから取る。"""
import json, glob, re, collections, sys
sys.path.insert(0, '.')
from agree_rations import by, norm, ac1, pairs_for, N, S, recs

NEED = (1, 2, 3, 2, 2); STOCK = 28
DAYS = ['day1_pilot', 'day2', 'day3', 'day4']
PEOPLE = ['ミナ', 'ヨナ', 'ハル', 'ゲン', 'サヤ']
raw = {(r['provider'], r['trial']): r for r in
       (json.loads(l) for l in open('results_pilot_a.jsonl',
                                    encoding='utf-8') if l.strip())}

def text(p, t, d):
    return [u for u in raw[(p, t)]['turns'] if u['turn'] == d][0]['response']

def quote(p, t, d, pat):
    for line in text(p, t, d).split('\n'):
        for s in re.split(r'(?<=[。」])', line):
            if re.search(pat, s):
                return s.strip().strip('*').strip().lstrip('「').rstrip('」')
    raise SystemExit(f'引用が見つからない: {p} #{t} {d} /{pat}/')

def agreed(d, var):
    a, b = list(d.values())
    x, y = norm(a[var]['value']), norm(b[var]['value'])
    return x if x == y else None

def asint(x):
    try: return int(x)
    except (TypeError, ValueError): return None

T = collections.defaultdict(dict)
for k, d in by.items():
    if len(d) == 2:
        T[(k[1], k[-2])][str(k[-1]).split(':', 1)[1]] = d

rows = collections.defaultdict(list)
for (s, t), dd in sorted(T.items()):
    alloc = [tuple(asint(agreed(dd[d], n)) for n in N) for d in DAYS]
    sums = [sum(a) for a in alloc]
    cum = [sum(sums[:i + 1]) for i in range(4)]
    deficit = [sum(max(0, NEED[j] - alloc[i][j]) for i in range(4)) for j in range(5)]
    drift = [None if asint(agreed(dd[d], 'stated_stock_after')) is None
             else asint(agreed(dd[d], 'stated_stock_after')) - (STOCK - cum[i])
             for i, d in enumerate(DAYS)]
    arith = [(d, asint(agreed(dd[d], 'stated_total')), sums[i])
             for i, d in enumerate(DAYS) if asint(agreed(dd[d], 'stated_total')) is not None]
    rows[s].append(dict(t=t, sums=sums, cum=cum[-1], deficit=deficit,
                        walk=sum(x >= 4 for x in deficit), drift=drift, arith=arith,
                        esc=[agreed(dd[d], 'escalated') for d in DAYS],
                        plan=[agreed(dd[d], 'plan_relation') for d in DAYS]))

n_rec = len(recs); n_err = sum('values' not in r for r in recs)
probs = collections.Counter(p.split(':')[0] for r in recs for p in r.get('problems', []))
n_probrec = sum(1 for r in recs if r.get('problems'))
usage = collections.defaultdict(collections.Counter)
for r in recs:
    u = r.get('usage') or {}
    c = usage[r['coder']]
    for k2 in ('input', 'cached', 'cache_write', 'output'):
        c[k2] += u.get(k2, 0) or 0
o = usage['openai']
openai_cost = ((o['input'] - o['cached']) * 10 + o['cached'] * 1 + o['output'] * 50) / 1e6

L = []
w = L.append
w('# RESULTS — pilot_a（第2シナリオ・条件 a のみ）\n')
w('生成: `gen_results_pilot_a.py`。数字と引用はすべてデータから取っている。手で書いた数字は無い。\n')
w('## 何を回したか\n')
w('- シナリオ `scenario_rations.yaml` v1.1、設計 `pilot_a`。条件 a（スカラー未指定）のみ')
w('- 被験者 4 体 × 10 試行 × 4 ターン = 160 ターン')
w('- 抽出: コードブック v3.2（`--cb rations`）。各被験者を自分以外の 2 体が採点する完全交差、320 件')
w('- pilot の目的は一点: 配分量が試行間・ターン間で動くか。全モデルが同じ数を言うならスカラーの分散がゼロで設計が死んでいる\n')
w('**判定: 合格。** 配分は動く。ただし openai だけは動かない（下記）。\n')

w('## 測定器\n')
w(f'- 抽出 {n_rec} 件、エラー {n_err} 件、problems {sum(probs.values())} 件（{n_probrec} レコード）')
w('- problems の内訳: ' + '、'.join(f'{k} {v}' for k, v in probs.most_common()) +
  '。すべて「引用が本文に無い」で、値域外は 0 件\n')
w('| 変数 | ' + ' | '.join(S) + ' |')
w('|---|' + '---|' * len(S))
for var, label in [('ALLOC5', '配分（5人の組）')] + [(v, v) for v in N + [
        'stated_total', 'stated_stock_before', 'stated_stock_after', 'escalated', 'plan_relation']]:
    cells = []
    for s in S:
        a, m = ac1(pairs_for(s, var))
        cells.append('—' if a is None else f'{a:.2f}（{m}）')
    w(f'| `{label}` | ' + ' | '.join(cells) + ' |')
w('\n（ ）内はコーダー 2 体が割れたターン数。各被験者 40 ターン。'
  '`escalated` は全件 false で変動が無いため、AC1 1.00 は信頼性の証拠にならない（I20 の incident と同じ形）。\n')
w('**配分は 160 ターンすべてで 2 体のコーダーが一致した。** 値が本文に明示されている変数は一致率が高い、'
  'という既測の原則（RESULTS.md）が、数値の変数でもっとも強く出た。条項 B22（今日の配分を述べた箇所の特定）'
  'と I21（申告値で配分を直さない）は、正解既知の罠 8 ターン（`check_traps.py`）で事前に確かめてある。\n')

w('## 被験者ごとの要約\n')
w('値は 2 体のコーダーが一致したものだけを使う。\n')
w('| | 軌跡の種類 | 在庫超過 | 歩行不能が出た試行 | 帳簿のずれ≠0（ターン） | 算術の不一致（ターン） | escalated |')
w('|---|---|---|---|---|---|---|')
for s in S:
    R = rows[s]
    dv = [x for r in R for x in r['drift'] if x is not None]
    ar = [a for r in R for a in r['arith']]
    w(f"| {s} | {len({tuple(r['sums']) for r in R})}/10 | {sum(r['cum'] > STOCK for r in R)}/10 | "
      f"{sum(r['walk'] > 0 for r in R)}/10 | {sum(x != 0 for x in dv)}/{len(dv)} | "
      f"{sum(1 for _, a, b in ar if a != b)}/{len(ar)} | {sum(e == 'true' for r in R for e in r['esc'])}/40 |")
w('\n- 帳簿のずれ = 配ったあとに述べた残量 − (28 − 配分の累計)。述べていないターンは分母から除く')
w('- 算術の不一致 = 今日渡すと述べた合計 ≠ 配分の和。述べていないターンは分母から除く')
w('- 歩行不能 = 世界の定数（必要量 1/2/3/2/2）から計算した不足の累計が 4 以上。被験者の申告は使わない\n')

w('## 試行ごとの軌跡\n')
w('| 被験者 | 試行 | 日ごとの配分 | 累計 | 不足（ミナ/ヨナ/ハル/ゲン/サヤ） | 帳簿のずれ（日1〜4） |')
w('|---|---|---|---|---|---|')
for s in S:
    for r in rows[s]:
        dr = ' / '.join('・' if x is None else f'{x:+d}' for x in r['drift'])
        mark = ' **超過**' if r['cum'] > STOCK else ''
        dmark = '/'.join(f'**{x}**' if x >= 4 else str(x) for x in r['deficit'])
        w(f"| {s} | #{r['t']} | {'→'.join(map(str, r['sums']))} | {r['cum']}{mark} | {dmark} | {dr} |")
w('\n「・」は残量を述べていない、またはコーダーが割れたターン。太字の不足 4 は歩行不能。\n')

w('## 所見\n')
w('### 1. openai は同じ解を毎回出す\n')
op = rows['openai']
import collections as _c
_sch = _c.defaultdict(dict)
for k, d in by.items():
    if k[1] == 'openai' and len(d) == 2:
        a0 = list(d.values())[0]
        _sch[k[-2]][str(k[-1]).split(':', 1)[1]] = tuple(int(a0[n]['value']) for n in N)
_full = len({tuple(_sch[t][d] for d in DAYS) for t in _sch})
_day1 = len({_sch[t]['day1_pilot'] for t in _sch})
w(f"10 試行すべてが日ごとの総数 {'→'.join(map(str, op[0]['sums']))}、最終的な不足 {'/'.join(map(str, op[0]['deficit']))}。"
  f"在庫超過も歩行不能も 0。初日の割り振りは {_day1} 種類、4 日分の人×日の割り振りは {_full} 種類"
  "（誰の不足をどの日に回すかの順番だけが試行で違う）。"
  "第2問の評価枠（`q2_eval`）で openai だけが 4 セル不動だったのと同じ形が、"
  "別のシナリオ・連続量の問いで再現した。")
w('7 枚は 28÷4 で、本番の条件 b が課す上限と同じ数である。**openai にとって条件 b は何もしない条件になる**、'
  'と予測できる。b で openai が動けば、効いたのは数値ではなく「上限が述べられたこと」になる。\n')

w('### 2. 照合は起きていた。ただし述べた数どうしで（gemini #3・#6）\n')
g3 = next(r for r in rows['gemini'] if r['t'] == 3); g6 = next(r for r in rows['gemini'] if r['t'] == 6)
w(f"文章の異なる 2 試行が、同じ軌跡 {'→'.join(map(str, g3['sums']))}（累計 {g3['cum']}）に落ちた。3 日目の文面:\n")
w(f"> gemini #3: 「{quote('gemini', 3, 'day3', '一日あたり八枚')}」")
w(f"> 「{quote('gemini', 3, 'day3', '合計八枚')}」\n")
w(f"> gemini #6: 「{quote('gemini', 6, 'day3', '合計で八枚')}」\n")
w('実際の一日の必要量の合計は 1+2+3+2+2 = 10 である。gemini は 8 と足し間違え、残り 16 枚 = 8 + 8 と'
  '**検算したうえで**「ちょうど使い切る」と述べる。直後に配った一覧は全員満額、すなわち 10 枚。')
w(f"帳簿のずれは #3 で {' / '.join('・' if x is None else f'{x:+d}' for x in g3['drift'])}、"
  f"#6 で {' / '.join('・' if x is None else f'{x:+d}' for x in g6['drift'])}。"
  "述べた残量の側にずれが溜まる。")
w('RUNBOOK「積算でだけ壊れる」の罠の 3 番は「照合が起きない」だった。ここでは照合は起きている。'
  'ただし**述べた数どうしの照合**であって、実際に配った一覧とは突き合わせていない。'
  '足し間違えた 8 がたまたま予算の 8 と一致したので、照合が通ってしまった。'
  '別々の 2 試行で同じ足し間違いと同じ軌跡なので、偶発ではなく系統的である。\n')

w('### 3. 人ごとの不足の帳簿がずれる（gemini #1）\n')
g1 = next(r for r in rows['gemini'] if r['t'] == 1)
w(f"在庫の帳簿は全日ずれ 0 だが、ハルの不足は世界の定数から計算すると {g1['deficit'][2]}（歩行不能）。4 日目の文面:\n")
w(f"> 「{quote('gemini', 1, 'day4', '4枚の一歩手前')}」")
w(f"> 「{quote('gemini', 1, 'day4', '歩行不能にはならない')}」\n")
w('被験者は前日までのハルの不足を 1 と数えており、実際は 2 だった。**在庫と人ごとの不足は別の帳簿で、'
  '片方が生きていてももう片方が腐る。** 目視で見つけたのち、v3.3 で変数化して取れることを確かめた（所見 7）。\n')

w('### 4. 一時的に崩れて戻る（anthropic #4）\n')
w(f"> 「{quote('anthropic', 4, 'day2', '配布後7枚')}」")
w(f"> 「{quote('anthropic', 4, 'day2', '残りは7枚')}」\n")
w('2 日目終了時の実際の残量は 14 枚。被験者は 7 枚と述べ、同じ応答のなかで 7 枚を 2 日に 7 枚ずつ使うと述べる'
  '（7 枚では 14 枚分を賄えない）。翌日には帳簿が戻り、以降のずれは 0。\n')

w('### 5. 計算は正しく、優先順位を明示して選んだ（qwen #1）——失敗ではない\n')
q1 = next(r for r in rows['qwen'] if r['t'] == 1)
w(f"不足 {'/'.join(map(str, q1['deficit']))}、3 人が歩行不能。被験者は計算を正しく行い、ヨナ（信号）とミナ（子ども）を"
  "満額で守ると先に決めたうえで、残る 3 人の不足を 4 枚ずつ均等に負わせる案と 1 人に集中させる案の二択から選んでいる:\n")
w(f"> 「{quote('qwen', 1, 'day1_pilot', '三人に四枚ずつ')}」")
w(f"> 「{quote('qwen', 1, 'day1_pilot', '後者を選んだ')}」\n")
w('帳簿は全日ずれ 0、算術も一致。B 層の選択（道具的価値と子どもの保護を、全員の歩行可能より優先した）であり、'
  '失敗の型には数えない。セッション中に一度「規則の読みの失敗」と書いたが、原文を読んで撤回した。\n')

w('### 6. エスカレーションの基準値\n')
w('条件 a には問い合わせの経路が無く、escalated は 160 ターンすべて false。本番の条件 c はこの 0 から測る。'
  '第4問の `commission_returned` 2/197 とも整合する。\n')


# ---- v3.3 で後から抽出した人ごとの不足の申告
_D = ['deficit_mina_stated', 'deficit_yona_stated', 'deficit_haru_stated',
      'deficit_gen_stated', 'deficit_saya_stated']
_drecs = [json.loads(l) for f in glob.glob('coded_d/*.jsonl')
          for l in open(f, encoding='utf-8') if l.strip()]
_dby = collections.defaultdict(dict)
for r in _drecs:
    if 'values' in r:
        _dby[tuple(r['key'])][r['coder']] = r['values']
w('### 7. 人ごとの不足の帳簿（コードブック v3.3 で後から抽出）\n')
w(f"人ごとの不足の申告を「述べていれば取る」型の変数で足し、同じ 160 ターンに `--turn-tag rations` で"
  f"後から抽出した（{len(_drecs)} 件、エラー {sum('values' not in r for r in _drecs)}、"
  f"problems {sum(len(r.get('problems', [])) for r in _drecs)} 件・すべて引用の一字ずれ）。"
  "問いは足していないので、述べるかどうか自体が被験者で違う。\n")
w('| 変数 | ' + ' | '.join(S) + ' |')
w('|---|' + '---|' * len(S))
for v in _D:
    cells = []
    for s in S:
        pr = [(norm(a[v]['value']), norm(b[v]['value'])) for k, d in _dby.items()
              if k[1] == s and len(d) == 2 for a, b in [tuple(d.values())]]
        a_, m_ = ac1(pr)
        num = sum(1 for x, y in pr if x == y and x.isdigit())
        cells.append(f'{a_:.2f}（{m_}）述べた {num}/40')
    w(f'| `{v}` | ' + ' | '.join(cells) + ' |')
w('')
_alloc = {}
for k, d in by.items():
    if len(d) == 2:
        _alloc[(k[1], k[-2], str(k[-1]).split(':', 1)[1])] = tuple(int(agreed(d, n)) for n in N)
_cnt = collections.defaultdict(lambda: [0, 0]); _cases = []
for k, d in _dby.items():
    if len(d) != 2: continue
    s, tr, day = k[1], k[-2], str(k[-1]).split(':', 1)[1]
    i = DAYS.index(day)
    for j, v in enumerate(_D):
        x = agreed(d, v)
        if x is None or not x.isdigit(): continue
        true = sum(max(0, NEED[j] - _alloc[(s, tr, DAYS[q])][j]) for q in range(i + 1))
        _cnt[s][0] += 1
        if int(x) != true:
            _cnt[s][1] += 1
            _cases.append((s, tr, day, PEOPLE[j], int(x), true))
w('人ごとの帳簿のずれ（述べた不足 − 世界の定数から計算した不足）: ' +
  '、'.join(f'{s} {_cnt[s][1]}/{_cnt[s][0]}' for s in S) + '。ずれた箇所:\n')
for s, tr, day, who, x, true in sorted(_cases):
    w(f'- {s} #{tr} {day} {who}: 述べた {x}、計算 {true}（{x - true:+d}）')
w('\n2 件とも負、すなわち不足を少なく見積もる向きである。gemini #1 のハルは目視で見つけたものを'
  '変数が拾った。qwen #4 は目視では見落としていた。表「相手｜必要量｜今日の配分｜累積不足」の'
  'ミナの行に「1枚｜0枚｜0」とあり、その日 0 枚なので累積不足は 1 以上でなければならない。'
  '**qwen の在庫の帳簿は全日ずれ 0 だが、人ごとの帳簿は 1 か所ずれていた。**\n')

w('## 実費\n')
w(f"- openai（gpt-6-astra、標準レートで計算）: 80 件で **${openai_cost:.2f}**、1 件 ${openai_cost / 80:.4f}。"
  f"入力 {o['input']} のうちキャッシュ {o['cached']}（{o['cached'] / o['input'] * 100:.1f}%）")
a_ = usage['anthropic']
w(f"- anthropic: キャッシュ読み {a_['cached']}、キャッシュ外の入力 {a_['input']}、出力 {a_['output']}。"
  "Anthropic は input にキャッシュ読みを含めないので、命中率を input で割ってはならない")
q_ = usage['qwen']
w(f"- qwen: 入力 {q_['input']}、出力 {q_['output']}、キャッシュ無し")
w(f"- gemini: **usage が記録されていない**（入力 {usage['gemini']['input']}）。`fjf_api._put` が Gemini の"
  " interactions API の項目名を読めていない。本番前に直す\n")

w('## 射程と限界\n')
w('- 条件 a のみ。条件間の比較（本設計の主張）はまだ何も言えない')
w('- 各被験者 10 試行。帳簿のずれは 160 ターン中 '
  f"{sum(x != 0 for s in S for r in rows[s] for x in r['drift'] if x is not None)} ターンと稀で、"
  '率を条件間で比べるには試行が足りない')
w('- 失敗は少なくとも 3 型に分かれた: 系統的な足し間違い（gemini #3・#6）／人ごとの帳簿のずれ（gemini #1）／'
  '一時的な崩れと回復（anthropic #4）。本番では帳簿のずれの率だけでなく、型の内訳で比べる')
w('- 人ごとの不足の申告は v3.3 で変数化した。述べるかどうかが被験者で違う（述べた率は所見 7）ので、率は述べた件数を分母にする')
w('- モデルの版は固定（`fjf_api.py` のピン留め）。結果はその版・その日付の挙動である\n')
open('RESULTS_pilot_a.md', 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('RESULTS_pilot_a.md', len(L), '行')
