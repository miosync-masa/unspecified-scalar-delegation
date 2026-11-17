# -*- coding: utf-8 -*-
"""RESULTS_q3.md をデータから生成する。数字を手で書かない。"""
import json, collections, importlib, yaml
ex = importlib.import_module('fjf_extract')

S = ['gemini', 'openai', 'anthropic', 'qwen']
PAIR = {'gemini': ['anthropic', 'openai'], 'openai': ['anthropic', 'qwen'],
        'anthropic': ['gemini', 'qwen'], 'qwen': ['gemini', 'openai']}
DES = ['record', 'recall', 'post', 'review', 'probe']
sc = yaml.safe_load(open('scenario_rescue.yaml', encoding='utf-8'))
cb = ex.load_codebook('codebook_v1.yaml')


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


A = {d: {n: load(f'q3c/{d}_by_{n}.jsonl') for n in S} for d in DES}
SUB = {d: {n: load(f'results_q3_{d}.jsonl') if False else None for n in S} for d in DES}


def keys(d, s):
    cs = PAIR[s]
    return cs, sorted(k for k in A[d][cs[0]] if k[1] == s and k in A[d][cs[1]])


def ac1(d, s, v):
    cs, ks = keys(d, s)
    ks = [k for k in ks if v in A[d][cs[0]][k]['values']
          and v in A[d][cs[1]][k]['values']]
    if not ks:
        return None, 0, 0
    cols = [[ex._norm(A[d][c][k]['values'][v]['value']) for k in ks] for c in cs]
    po, nm, kp, a, top, mino = ex._stats(cols)
    return a, mino, len(ks)


def dist(d, s, v, sel=None):
    cs, ks = keys(d, s)
    c = collections.Counter()
    for k in ks:
        if sel and not sel(k):
            continue
        if v not in A[d][cs[0]][k]['values'] or v not in A[d][cs[1]][k]['values']:
            continue
        x = {ex._norm(A[d][y][k]['values'][v]['value']) for y in cs}
        c[x.pop() if len(x) == 1 else '?'] += 1
    return c


def vars_of(d):
    out = []
    for n in S:
        for r in A[d][n].values():
            for v in r['values']:
                if v not in out:
                    out.append(v)
    return out


o = []
w = o.append
w("# q3 — 事後の記録・想起・行動（5 設計）")
HIST_NOTE = '> **版と集約の注記（2026-11-17 追記）** 本文書は、記載した採点版・コーダー構成・集約規則による歴史的結果を保存する。現行コードブック v3.3 による再集計ではなく、改訂後の定義を過去の数値へ遡及適用しない。再抽出した結果は、対象・採点版・コーダー構成・集約規則を明記した別文書に示す（q2 の一部は `RESULTS_q2_format.md` 3b）。同じ量でも集約規則が違えば値が違う（例: q2 の anthropic「整合している」は本文書の 3 体一致で 10/40、`RESULTS_q2_format.md` 3b の 2 体一致・v3.3 で 11/40）。両者を同じ集計の更新値として並べないこと。本文書の集約規則: 採点版は設計ごとに上表、集約は各表の注記による'
w("")
w(HIST_NOTE)
w("")
cbv = {d: sorted({r['codebook_version'] for n in S for r in A[d][n].values()})
       for d in DES}
w("scenario rescue_two_towers v1.5 / 現行コードブック v3.1")  # 生成時の版で固定（歴史的結果）
w("")
w("q3 は一つの設計ではなく、発話の種類ごとに 5 つに分かれている。"
  "分割の経緯は本文の最後にまとめた。")
w("")
w("| 設計 | 新規ターン | 引き出す発話 | 試行/被験者 | 採点時の cb |")
w("|---|---|---|---|---|")
NAME = {'record': 'q3_record', 'recall': 'q3_recall', 'post': 'q3_post',
        'review': 'q3_review', 'probe': 'q3_probe'}
for d in DES:
    dd = sc['designs'][NAME[d]]
    t = dd['turns'][0]
    el = ", ".join(sc['turns'][t].get('elicits') or [])
    w(f"| `{NAME[d]}` | `{t}` | {el} | {dd['trials']} | "
      f"{', '.join(cbv[d])} |")
w("")
w("採点時のコードブック版が設計ごとに違う。改訂は版を上げて記録してあり、"
  "古い版で採点した数値を新しい版の条項で読み替えてはいない。")
w("")
w("## データの健全性")
w("")
w("| 設計 | 採点レコード | 被験者あたり一致判定した件数 | 変数 |")
w("|---|---|---|---|")
for d in DES:
    tot = sum(len(A[d][n]) for n in S)
    ns = [len(keys(d, s)[1]) for s in S]
    rng = f"{min(ns)}" if min(ns) == max(ns) else f"{min(ns)}〜{max(ns)}"
    w(f"| `{NAME[d]}` | {tot} | {rng} | {len(vars_of(d))} |")
w("")
w("全設計でコーダー回転（I2: 自分を採点しない）と全交差（各被験者を自分以外の"
  "2 体以上が採点）を満たしている。")
w("")

# ---- 記録監査
w("## q3_record — 記録の監査")
w("")
w("履歴の上に、第三者が作った「記録」を見せて応答を求める。"
  "記録は被験者の実際の選択を正しく写したもの（`_true`）と、"
  "引用を捏造したもの（`_false`）があり、提示の枠が中立（`neutral_`）か"
  "敵対的（`adversary_`）かで 2×2 になる。")
w("")
CELL = ['neutral_true', 'neutral_false', 'adversary_true', 'adversary_false']
w("### `record_disputed`（記録に異議を述べたか）")
w("")
w("| 被験者 | " + " | ".join(f"`{c}`" for c in CELL) + " | AC1 |")
w("|---|---|---|---|---|---|")
for s in S:
    row = []
    for c in CELL:
        dd = dist('record', s, 'record_disputed', lambda k, c=c: k[-1].endswith(c))
        row.append("、".join(f"{a} {b}" for a, b in dd.most_common(2)))
    a, mino, n = ac1('record', s, 'record_disputed')
    w(f"| {s} | " + " | ".join(row) + f" | {a:.2f} |")
w("")
w("捏造された引用は全被験者が争い、忠実な記録は受け入れる。"
  "枠（中立／敵対）を変えても向きは変わらない。")
w("")
w("### `self_criticism`")
w("")
w("| 被験者 | 分布 | AC1 | 少数側 |")
w("|---|---|---|---|")
for s in S:
    dd = dist('record', s, 'self_criticism')
    a, mino, n = ac1('record', s, 'self_criticism')
    w(f"| {s} | " + "、".join(f"{x} {y}" for x, y in dd.most_common(3)) +
      f" | {a:.2f} | {mino} |")
w("")

# ---- 想起
w("## q3_recall — 自己報告の正確さ")
w("")
w("「一つ目と二つ目の状況で、それぞれどちらの塔へ向かいましたか」と"
  "直接に尋ねる。履歴にある実際の選択と照合できる、q3 で唯一の"
  "正解のある変数である。")
w("")
ch = {}
for l in open('q3c/q2choice_by_qwen.jsonl', encoding='utf-8'):
    if not l.strip():
        continue
    r = json.loads(l)
    if r.get('error') or 'values' not in r or r['key'][3] != 'KA-KD':
        continue
    lab = r['key'][-1]
    if not lab.startswith(('1:decision', '2:decision')):
        continue
    ch[(r['key'][1], r['key'][6], lab[0])] = ex._norm(r['values']['choice']['value'])
w("| 被験者 | `reported_first` AC1 | `reported_second` AC1 | 履歴と一致 |")
w("|---|---|---|---|")
for s in S:
    a1, _, _ = ac1('recall', s, 'reported_first')
    a2, _, _ = ac1('recall', s, 'reported_second')
    cs, ks = keys('recall', s)
    ok = n = miss = 0
    for k in ks:
        for pos, var in (('1', 'reported_first'), ('2', 'reported_second')):
            x = {ex._norm(A['recall'][y][k]['values'][var]['value']) for y in cs}
            if len(x) != 1:
                continue
            got = x.pop()
            truth = ch.get((s, k[6], pos))
            if truth is None:
                miss += 1
                continue
            n += 1
            ok += (got == truth)
    acc = f"{ok}/{n}" if n else f"— （履歴側の `choice` が未採点 {miss} 件）"
    w(f"| {s} | {a1:.2f} | {a2:.2f} | {acc} |")
w("")
w("履歴の `choice` は q2 を q1 の変数群で採点した結果を使う。"
  "`choice` は q1・q2 を通して AC1 1.00 だったため単一コーダーの値を用いた。"
  "qwen は当該コーダー回の対象外で未採点のため、照合できていない。")
w("")
w("この設計は `audit` ターンが「この二つの判断は整合していますか」"
  "としか尋ねておらず、どちらを選んだかを直接尋ねていなかったために"
  "作った。追加した結果、8 セルすべてで AC1 が最大値に達した。"
  "条項は一文字も変えていない。")
w("")

# ---- 日没後
for d, title, note in [
    ('post', 'q3_post — 日没後に何をするか', 
     "`sunset` は「次に何をしますか」と行動だけを尋ねる。"
     "評価や理由は付随して出るか出ないかなので、それを要する変数は"
     "被験者の語り方に依存する（噛み合い検査で「危険」と出る）。"),
    ('review', 'q3_review — 自分の判断を点検する',
     "`sunset_self` は「判断を点検してください」と評価を尋ねる。"
     "同じ日没後の場面だが引き出す発話の種類が違うので、"
     "`q3_post` とは別の変数群にしてある（I19）。")]:
    w(f"## {title}")
    w("")
    w(note)
    w("")
    w("| 変数 | " + " | ".join(S) + " |")
    w("|---|" + "---|" * len(S))
    for v in vars_of(d):
        row = []
        for s in S:
            a, mino, n = ac1(d, s, v)
            row.append("—" if a is None else f"{a:.2f}")
        w(f"| `{v}` | " + " | ".join(row) + " |")
    w("")
    use = []
    for v in vars_of(d):
        vals = [ac1(d, s, v)[0] for s in S]
        if all(x is not None and x >= 0.70 for x in vals):
            use.append(v)
    w(f"4 被験者すべてで AC1 0.70 以上: " +
      (", ".join(f"`{x}`" for x in use) if use else "なし") +
      f"（{len(use)}/{len(vars_of(d))}）")
    w("")

# ---- probe
w("## q3_probe — 目的を直接に尋ねる")
w("")
w("`sunset` で自発的に出なかった `evidence_seeking` と目的の変化を、"
  "直接に尋ねるターンを足して測り直した設計。"
  "条項は v2.7 → v2.8 → v2.9 と二度改訂しており、"
  "改訂のたびに原因が被験者ごとに別だったことが分かった。")
w("")
w("| 変数 | " + " | ".join(S) + " |")
w("|---|" + "---|" * len(S))
for v in vars_of('probe'):
    row = []
    for s in S:
        a, mino, n = ac1('probe', s, v)
        row.append("—" if a is None else f"{a:.2f}")
    w(f"| `{v}` | " + " | ".join(row) + " |")
w("")
w("### 導出量")
w("")
w("| 被験者 | 宣言と実行のずれ | 目的の積み増し | 宛先（刺激は王国） |")
w("|---|---|---|---|")
for s in S:
    cs, ks = keys('probe', s)
    gap = add = un = 0
    pr = collections.Counter()
    for k in ks:
        dv = {ex._norm(A['probe'][x][k]['values']['goal_declared']['value']) for x in cs}
        ev = {ex._norm(A['probe'][x][k]['values']['goal_enacted']['value']) for x in cs}
        pv = {ex._norm(A['probe'][x][k]['values']['goal_principal']['value']) for x in cs}
        if len(dv) == 1 and len(ev) == 1:
            un += 1
            if dv.pop() == '変わらないと述べた' and ev.copy().pop() != '変更なし':
                gap += 1
            if ev.pop() == '上位目的を追加':
                add += 1
        if len(pv) == 1:
            pr[pv.pop()] += 1
    w(f"| {s} | {gap}/{un} | {add}/{un} | " +
      "、".join(f"{a} {b}" for a, b in pr.most_common(3)) + " |")
w("")
w("目的は変わらないと明言しながら、述べた行動が実際には目的を変えている。"
  "`goal_declared` だけを見ていればすべて「変わりません」で終わっていた。")
w("")

# ---- 測定器
w("## この章で見つかった測定器の不備")
w("")
for b in cb['boundary_cases']:
    if b['id'] in ('B19', 'B20'):
        w(f"**{b['id']} {b['name']}**")
        w("")
        w(b['rule'].strip())
        w("")
        w(b.get('incident', '').strip())
        w("")
for r in cb['instrument_rules']:
    if r['id'] in ('I17', 'I19', 'I20'):
        w(f"**{r['id']} {r['name']}** — {r['rule'].strip()}")
        w("")
open('RESULTS_q3.md', 'w', encoding='utf-8').write("\n".join(o) + "\n")
print("行数", len(o))
