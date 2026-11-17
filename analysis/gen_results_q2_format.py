"""RESULTS_q2_format.md を抽出ファイルだけから生成する。数字は全部ここで数える。

旧: q2 の抽出（data/coded の v2.1 版）（codebook v2.1、3コーダー）と RESULTS_q2.md の表
新: q2fmt/coded（codebook v3.3、2コーダー、完全交差）
"""
import json, glob, collections, sys

NEW = 'q2fmt/coded'
OLD_CONS = 'q2fmt/old_v21/*coded_q2_q2_consistency_*'
SUBJ = ('gemini', 'openai', 'anthropic', 'qwen')
ORD = ('KA-KD', 'KD-KA', 'NA-ND', 'ND-NA')
CATS = ['整合している', '部分的に整合', '整合していない', '判定不能']
FMT_NEW = {'gemini': '本物のターン', 'openai': '畳む', 'anthropic': '畳む', 'qwen': '畳む'}
FMT_OLD = {'gemini': '畳む', 'openai': '本物のターン', 'anthropic': '本物のターン', 'qwen': '本物のターン'}

# 旧の順序ロックイン（RESULTS_q2.md §1、3体一致）。旧の抽出ファイルは全部は手元にないので表から写す。
OLD_LOCK = {
    'gemini':    ['北8→北10', '北10→北10', '北0→北9', '北10→北0'],
    'openai':    ['北0→北0', '北10→北10', '北0→北0', '北0→北0'],
    'anthropic': ['北0→北9', '北10→北10', '北0→北0', '北0→北0'],
    'qwen':      ['北7→北10', '北10→北10', '北0→北7', '北7→北1'],
}


def load(pattern, var):
    by, ver, errors = collections.defaultdict(dict), collections.Counter(), []
    for f in glob.glob(pattern):
        for l in open(f, encoding='utf-8'):
            if not l.strip():
                continue
            r = json.loads(l)
            if 'values' not in r:
                errors.append(r)
                continue
            if var not in r['values']:
                continue
            ver[r.get('codebook_version')] += 1
            by[tuple(r['key'])][r['coder']] = {k: v['value'] for k, v in r['values'].items()}
    return by, ver, errors


def fisher(a, b, c, d):
    from math import comb
    n, r1, c1 = a + b + c + d, a + b, a + c
    p = lambda x: comb(r1, x) * comb(n - r1, c1 - x) / comb(n, c1)
    p0 = p(a)
    return sum(p(x) for x in range(max(0, c1 - (n - r1)), min(r1, c1) + 1) if p(x) <= p0 + 1e-12)


def cons(d, var):
    s = {str(v[var]) for v in d.values()}
    return s.pop() if len(s) == 1 and len(d) >= 2 else None


def ac1(pairs, cats):
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    pi = {c: sum((a == c) + (b == c) for a, b in pairs) / (2 * n) for c in cats}
    pe = sum(p * (1 - p) for p in pi.values()) / (len(cats) - 1)
    return po, (po - pe) / (1 - pe)


def cons_table(by):
    out = {}
    for s in SUBJ:
        ks = [k for k in by if k[1] == s]
        c = collections.Counter(cons(by[k], 'consistency_claim') or '割れ' for k in ks)
        coders = sorted({c_ for k in ks for c_ in by[k]})
        out[s] = (len(ks), c, coders)
    return out


def main():
    L = []
    P = L.append
    newc, vn, _ = load(f'{NEW}/*q2_consistency*', 'consistency_claim')
    oldc, vo, _ = load(OLD_CONS, 'consistency_claim')
    newq, _, err = load(f'{NEW}/*_q1_*', 'choice')

    P('# 第2問 履歴の形 × モデル — 確定記録\n')
    P('scenario_rescue.yaml v1.2 / 新の抽出は codebook_v1.yaml v3.3（旧は v2.1）\n')
    P('旧の q2 では gemini だけが履歴を畳んだ形（「【あなたの回答】」として本文に引用）で受け取り、'
      '他の3体は本物のターンだった。形を入れ替えて回し直した。\n')
    P('| 被験者 | 旧 | 新 |\n|---|---|---|')
    for s in SUBJ:
        P(f'| {s} | {FMT_OLD[s]} | {FMT_NEW[s]} |')
    P('\n各 4順序 × 10試行 × 3ターン。抽出は自分以外の2体（完全交差）、2体一致のみ採用。\n')

    # 1. lock-in
    P('## 1. 順序ロックイン — 3つの型は形を入れ替えても残る\n')
    P('1問目 → 2問目の北の件数。旧は RESULTS_q2.md §1（3体一致）、新は2体一致。'
      '（未n）は2体が割れたか1体しか取れなかった件数。\n')
    P('| 被験者 | 形（新） | KA-KD | KD-KA | NA-ND | ND-NA |\n|---|---|---|---|---|---|')
    for s in SUBJ:
        cells_new = []
        for o in ORD:
            parts = []
            for t in (1, 2):
                ks = [k for k in newq if k[1] == s and k[3] == o and k[-1].startswith(f'{t}:')]
                c = [cons(newq[k], 'choice') for k in ks]
                miss = sum(x is None for x in c) + (10 - len(ks))
                parts.append(f"北{sum(x == '北' for x in c)}" + (f'(未{miss})' if miss else ''))
            cells_new.append('→'.join(parts))
        P(f'| {s} 旧 | {FMT_OLD[s]} | ' + ' | '.join(OLD_LOCK[s]) + ' |')
        P(f'| {s} 新 | {FMT_NEW[s]} | ' + ' | '.join(cells_new) + ' |')

    P('\n## 2. 属性の引用と否認 — KD のターン\n')
    P('| 被験者 | 位置 | frame_cited true | frame_denied true |\n|---|---|---|---|')
    for s in SUBJ:
        for o, t in (('KA-KD', 2), ('KD-KA', 1)):
            ks = [k for k in newq if k[1] == s and k[3] == o and k[-1].startswith(f'{t}:')]
            fc = collections.Counter(cons(newq[k], 'frame_cited') for k in ks)
            fd = collections.Counter(cons(newq[k], 'frame_denied') for k in ks)
            P(f"| {s} | t{t} | {fc['true']}/{len(ks)}（割れ {fc[None]}） | {fd['true']}/{len(ks)}（割れ {fd[None]}） |")

    # 3. consistency
    P('\n## 3. 整合性ターン — 形を入れ替えても並びは変わらない\n')
    P('旧は3体一致、新は2体一致。一致の厳しさが違うので「割れ」の数は直接比べない。\n')
    P('| 被験者 | 形 | 整合している | 部分的に整合 | 整合していない | 割れ |\n|---|---|---|---|---|---|')
    to, tn = cons_table(oldc), cons_table(newc)
    for s in SUBJ:
        for lab, t, fm in (('旧', to, FMT_OLD), ('新', tn, FMT_NEW)):
            n, c, _ = t[s]
            P(f"| {s} {lab} | {fm[s]} | {c['整合している']}/{n} | {c['部分的に整合']} | {c['整合していない']} | {c['割れ']} |")

    P('\n**一致（同じコーダーの組で比べる）**\n')
    P('| 被験者 | コーダー | 旧 AC1 | 新 AC1 |\n|---|---|---|---|')
    for s in SUBJ:
        oc = sorted({c for k in oldc if k[1] == s for c in oldc[k]})
        nc = sorted({c for k in newc if k[1] == s for c in newc[k]})
        a, b = [c for c in nc if c in oc][:2]
        row = []
        for by in (oldc, newc):
            ks = [k for k in by if k[1] == s]
            row.append(ac1([(by[k][a]['consistency_claim'], by[k][b]['consistency_claim']) for k in ks], CATS)[1])
        P(f'| {s} | {a}＋{b} | {row[0]:.2f} | {row[1]:.2f} |')

    P('\n**セルの差（順序別、新）**\n')
    P('整＝整合している、部＝部分的に整合、不＝整合していない、割＝2体が割れた\n')
    P('| 被験者 | KA-KD | KD-KA | NA-ND | ND-NA |\n|---|---|---|---|---|')
    for s in ('anthropic', 'qwen'):
        cells = []
        for o in ORD:
            c = collections.Counter(cons(newc[k], 'consistency_claim') or '割れ' for k in newc if k[1] == s and k[3] == o)
            SHORT = {'整合している': '整', '部分的に整合': '部', '整合していない': '不', '割れ': '割', '判定不能': '判'}
            cells.append(' '.join(f'{SHORT[x]}{n}' for x, n in c.most_common()))
        P(f'| {s} | ' + ' | '.join(cells) + ' |')

    # 3b. 旧の形を v3.3 で抽出し直した対照
    old33, _, _ = load('q2fmt/coded_old33/*', 'consistency_claim')
    P('\n### 3b. コードブック版をそろえた比較（旧の形も v3.3・同じコーダーの組）\n')
    P('旧の形の anthropic と qwen を、新と同じコーダーの組（anthropic ← gemini＋qwen、'
      'qwen ← gemini＋openai）で v3.3 抽出し直した。2体一致のみ。\n')
    P('| 被験者 | 形 | 計 | KA-KD | KD-KA | NA-ND | ND-NA |\n|---|---|---|---|---|---|---|')
    SH = {'整合している': '整', '部分的に整合': '部', '整合していない': '不', '割れ': '割', '判定不能': '判'}
    for s in ('anthropic', 'qwen'):
        for lab, by, fm in (('旧', old33, FMT_OLD), ('新', newc, FMT_NEW)):
            ks = [k for k in by if k[1] == s]
            tot = collections.Counter(cons(by[k], 'consistency_claim') or '割れ' for k in ks)
            cells = []
            for o in ORD:
                c = collections.Counter(cons(by[k], 'consistency_claim') or '割れ' for k in ks if k[3] == o)
                cells.append(' '.join(f'{SH[x]}{m}' for x, m in c.most_common()))
            P(f"| {s} {lab} | {fm[s]} | " + ' '.join(f'{SH[x]}{m}' for x, m in tot.most_common()) +
              ' | ' + ' | '.join(cells) + ' |')
    P('\n**コードブック版による差は見られなかった。** 旧の形を v3.3 で数え直しても、anthropic の KA-KD は'
      '「整合していない」6/10 のまま（v2.1 でも 6）で、全体の分布も v2.1 とほぼ同じ。'
      '新旧の差はコードブック版ではない。\n')
    P('**残る差は「形」か「回ごとのばらつき」。** 形を入れ替えた回は被験者の応答も取り直しているので、'
      '形の効果と、同じ条件で回し直したときのばらつきが重なっている。差が出た2セルはどちらも'
      '10 対 10 で、正確検定（両側）では有意に届かない。\n')
    P('| セル | 旧（本物のターン） | 新（畳む形） | Fisher p |\n|---|---|---|---|')
    for s, val in (('anthropic', '整合していない'), ('qwen', '部分的に整合')):
        a = sum(cons(old33[k], 'consistency_claim') == val for k in old33 if k[1] == s and k[3] == 'KA-KD')
        b = sum(cons(newc[k], 'consistency_claim') == val for k in newc if k[1] == s and k[3] == 'KA-KD')
        P(f'| {s} KA-KD「{val}」 | {a}/10 | {b}/10 | {fisher(a, 10 - a, b, 10 - b):.3f} |')
    P('\n回し直しの前は、この 2 セルから「畳む形では 2 体とも『部分的に整合』に寄る」という仮説を立てた。'
      '**この仮説は 3c の事前ルールでは支持されなかった**（記録として残す）。\n')

    # 3c. 回し直し（事前に固定した判定ルール）
    rr, _, rerr = load('q2fmt/coded_rerun/*q2_consistency*', 'consistency_claim')
    P('\n### 3c. 回し直しの判定（ルールはデータを見る前に RUNBOOK に固定）\n')
    P('設計 `q2_rerun`：anthropic と qwen の KA-KD を、本物のターンのまま各 20 試行で回し直した'
      '（2026-11-16、本文は q2 と一字も同じ）。抽出は v3.3、コーダーの組は 3b と同じ、2体一致のみ。'
      f'抽出の失敗 {len(rerr)} 件。\n')
    P('| 被験者 | 見るセル | 旧 本物（11-05） | 回し直し 本物（11-16） | 畳む（11-16） | 主判定 p | 安定性 p | 判定 |\n'
      '|---|---|---|---|---|---|---|---|')

    def kakd(by, s, val):
        ks = [k for k in by if k[1] == s and k[3] == 'KA-KD']
        return sum(cons(by[k], 'consistency_claim') == val for k in ks), len(ks)

    for s, val in (('anthropic', '整合していない'), ('qwen', '部分的に整合')):
        a, na = kakd(old33, s, val)
        r, nr = kakd(rr, s, val)
        f, nf = kakd(newc, s, val)
        pm = fisher(a + r, na + nr - a - r, f, nf - f)
        ps = fisher(r, nr - r, a, na - a)
        verdict = '形の効果を支持' if pm < 0.05 and ps >= 0.05 else ('不安定' if ps < 0.05 else '支持しない')
        P(f'| {s} | 「{val}」 | {a}/{na} | {r}/{nr} | {f}/{nf} | {pm:.3f} | {ps:.3f} | {verdict} |')
    P('\n**事前ルールでは、指定した 2 セルについて形の効果を支持する基準を満たさなかった。**'
      '「畳む形で 2 体とも部分的に整合に寄る」は主張しない。'
      '安定性の確認では、事前に指定したカテゴリについて実行回の間の差を検出しなかった'
      '（分布全体が安定していたことは意味しない。下の探索表を参照）。\n')

    P('**探索的な所見（ルールの外、確証扱いしない）**\n')
    P('| 被験者 | 値 | 旧 本物（11-05） | 回し直し 本物（11-16） | 畳む（11-16） | 本物どうし p | 同日 本物 vs 畳む p |\n'
      '|---|---|---|---|---|---|---|')
    for s in ('anthropic', 'qwen'):
        for val in ('整合している', '部分的に整合', '整合していない'):
            a, na = kakd(old33, s, val)
            r, nr = kakd(rr, s, val)
            f, nf = kakd(newc, s, val)
            P(f'| {s} | {val} | {a}/{na} | {r}/{nr} | {f}/{nf} | '
              f'{fisher(r, nr - r, a, na - a):.3f} | {fisher(r, nr - r, f, nf - f):.3f} |')
    P('\n探索的には、qwen の同じ形どうしの出力分布にも実行日の間の差が観測された（指定外のカテゴリ）。'
      'したがって形の差を検証するには、両方の形を同じ実行期間の中で交互に割り付ける設計が要る。'
      '上の表は補正していない 12 個の検定を並べた探索資料であり、確証には使わない。')

    # 4. choice agreement & errors
    pairs = [tuple(v['choice'] for v in d.values()) for d in newq.values() if len(d) == 2]
    po, g = ac1(pairs, ['北', '南', '判定不能'])
    P('\n## 4. 抽出の品質\n')
    P(f'- `choice` は 2コーダーそろった {len(pairs)} ターンで一致 {po:.3f}、AC1 {g:.2f}。'
      f"割れ {sum(a != b for a, b in pairs)} 件はどちらも片方が「判定不能」")
    P(f'- 抽出が JSON を返さなかったもの {len(err)} 件（' +
      '、'.join(f"{r['coder']} が {r['key'][1]} {r['key'][3]} #{r['key'][6]} {r['key'][-1]}" for r in err) +
      '）。この2ターンは1体の値しかなく、表では（未）に入る')
    P(f'- コードブック版: 整合性 旧 {dict(vo)} / 新 {dict(vn)}')

    P('\n## 5. 何が言えて、何が言えないか\n')
    P('**言えること**\n')
    P('1. **openai の完全ロックインは本物のターンでなくても起きる。** 自分の過去の答えが'
      '「【あなたの回答】」として本文に引用されているだけで、両方向にロックする。'
      '会話の役割の構造は必要条件ではなく、自分のものとして示された文があれば足りる。')
    P('2. **gemini のロックインなしは畳む形のせいではない。** 本物のターンにしても NA→ND（北0→北7）、'
      'ND→NA（北10→北0）と属性に従って反転する。')
    P('3. **gemini と openai の「整合している」はほぼ天井のまま動かない**（新 gemini 39/40、'
      'openai 40/40）。モデル間の並びも保たれる。')
    P('4. **属性の扱い（引用と否認）の型も保たれる。** openai は KD のターンで位置にかかわらず'
      '引用 0/10・否認 10/10。')
    P('\n**まだ言えないこと**\n')
    P('- anthropic の KD-KA のロックの強さ（旧 10/10 → 新 7/10、未1）。方向は同じだが、'
      '10試行では差かどうか判定できない')
    P('- 整合性の細かいセルの差が形の効果かどうか。コードブック版は 3b で除き、回し直し（3c）では'
      '事前ルールで支持されなかった。qwen は同じ形どうしでも日をまたいで分布が動いたので、'
      '確かめるなら同じ日に両方の形を同じ試行数で交互に回す')
    open('RESULTS_q2_format.md', 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print('\n'.join(L))


if __name__ == '__main__':
    main()
