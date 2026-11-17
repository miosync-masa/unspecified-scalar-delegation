# -*- coding: utf-8 -*-
"""RESULTS_q4.md をデータから生成する。数字を手で書かない。"""
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
    """2体が一致した値だけ数える。割れたものは ? に送る。"""
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
w("# q4 — 権限と目的の衝突（箝口令設計）")
HIST_NOTE = '> **版と集約の注記（2026-11-17 追記）** 本文書は、記載した採点版・コーダー構成・集約規則による歴史的結果を保存する。現行コードブック v3.3 による再集計ではなく、改訂後の定義を過去の数値へ遡及適用しない。再抽出した結果は、対象・採点版・コーダー構成・集約規則を明記した別文書に示す（q2 の一部は `RESULTS_q2_format.md` 3b）。同じ量でも集約規則が違えば値が違う（例: q2 の anthropic「整合している」は本文書の 3 体一致で 10/40、`RESULTS_q2_format.md` 3b の 2 体一致・v3.3 で 11/40）。両者を同じ集計の更新値として並べないこと。本文書の集約規則: 抽出時 v3.0、集約は各表の注記による'
w("")
w(HIST_NOTE)
w("")
w(f"scenario {raw[0]['scenario']} v{raw[0]['scenario_version']} / "
  f"codebook v3.1（抽出時 "  # 生成時の版で固定（歴史的結果）
  f"{sorted({r['codebook_version'] for r in A['gemini'].values()})[0]}）")
w("")
w("## 設計")
w("")
import yaml
sc = yaml.safe_load(open('scenario_rescue.yaml', encoding='utf-8'))
w("履歴は q3_post（= q2 の二択2回＋整合性確認＋日没後の行動）を逐語で積み、")
w("新規ターンは `order` 1本のみ。sunset を取り直していないので、各試行の")
w("出発点は既に採点済みの測定値である。")
w("")
w("| 変種 | 伝令の命令 |")
w("|---|---|")
for v in VAR:
    t = [x for x in raw if x['variants'].get('order') == v][0]
    body = [y for y in t['turns'] if not y['from_history']][0]['prompt']
    line = body.replace('\n', ' ').strip()
    w(f"| `{v}` | {line} |")
w("")
w("## データの健全性")
w("")
w(f"- 被験者レコード {len(raw)} 件、失敗 0 件")
cnt = collections.Counter((r['provider'], r['variants'].get('order')) for r in raw)
mn, mx = min(cnt.values()), max(cnt.values())
w(f"- 4 被験者 × 5 変種 × {mn} 試行" if mn == mx else
  f"- 4 被験者 × 5 変種 × {mn}〜{mx} 試行（不均衡）")
w(f"- 新規ターンは全レコード 1 本（{collections.Counter(len([t for t in r['turns'] if not t['from_history']]) for r in raw)[1]} 件）")
w(f"- 履歴の由来は q3_post の {len({r['history_src']['trial'] for r in raw})} 試行、"
  f"さらにその履歴は q2 の KA-KD（`history_src.via` に記録）")
w(f"- 応答長の中位値: " + "、".join(f"{k} {med[k]}字" for k in S))
w(f"- コーダーは自分以外の 2 体が各被験者を採点（I2）。採点レコード "
  f"{sum(len(A[n]) for n in S)} 件")
w("")
w("## 一致（全変種を込み、n=50／被験者）")
w("")
w("| 変数 | " + " | ".join(S) + " |")
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
w("変種をまとめた値である。変種ごとの n は 10 で、ノイズ床は 0.15 を下回らない。")
w("")
w("## 任務の返上")
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
w("| 被験者 | 返上した / 一致件数 |")
w("|---|---|")
for s, t, n in rows:
    w(f"| {s} | {t} / {n} |")
w("")
w(f"**全体 {ret} / {tot}。** 箝口令を受けても、真正性の疑わしい命令を受けても、")
w("前段で娘を失っていても、任務は返上されない。変動はすべて「どう従うか」の")
w("内側にあり、「従うか」の外へは出ない。")
w("")
w("## 自己引用（履歴にある自分の発言を引いたか）")
w("")
w("| 被験者 | " + " | ".join(f"`{v}`" for v in VAR) + " | 計 | 応答長の中位値 |")
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
      f" | **{T}/{N}**（{T/N*100:.0f}%） | {med[s]}字 |")
w("")
w("この変数は履歴を刺激に含めない設計では原理的に測れない。引く対象が")
w("存在しないからである。条項には応答長との交絡を注意として書いたが、")
w("観測された順序は長さでは説明されない（最も長い qwen が anthropic の")
w("半分以下である）。")
w("")
w("## 変種ごとの分布（2 体が一致した件のみ）")
w("")
for v in ['verbal_compliance', 'concealment', 'stated_action', 'channel_use']:
    w(f"### `{v}`")
    w("")
    w("| 被験者 | " + " | ".join(f"`{x}`" for x in VAR) + " |")
    w("|---|" + "---|" * len(VAR))
    for s in S:
        cs, oo = cells(s)
        row = []
        for vr in VAR:
            c = unan(s, v, oo[vr])
            row.append("、".join(f"{a} {b}" for a, b in c.most_common(3)))
        w(f"| {s} | " + " | ".join(row) + " |")
    w("")
w("## 測定器の不備（この設計で見つかったもの）")
w("")
for b in cb['boundary_cases']:
    if b['id'] in ('B21',):
        w(f"**{b['id']} {b['name']}**")
        w("")
        w(b['rule'].strip())
        w("")
        w(b.get('incident', '').strip())
        w("")
w("## 測っていない観測")
w("")
w(cb['observed_not_instrumented']['note'].strip())
w("")
for c in cb['observed_not_instrumented']['cases']:
    w(f"- **{c['what']}**（{c['where']}）— {c['why_not'].strip()}")
w("")
open('RESULTS_q4.md', 'w', encoding='utf-8').write("\n".join(o) + "\n")
print("行数", len(o))
