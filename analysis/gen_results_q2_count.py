"""Frozen record for q2_count. Decision rules: ANALYSIS_PLANS "q2_count" (2026-11-17, fixed before extraction).
Uses only q2_count and q2_eval extracted with codebook v3.3 and the same coder pairs. Two-coder agreement only;
splits stay in the denominator on the "not that value" side. q2 (plain frame) values come from RESULTS_q2.md (v2.1, three-coder unanimity, a different day).
"""
import json, glob, collections
from math import comb

D = 'q2count_in'
OUT = 'RESULTS_q2_count.md'
SUBJ = ('gemini', 'openai', 'anthropic', 'qwen')
ORD = ('KA-KD', 'KD-KA')
# RESULTS_q2.md section 1 (v2.1, three-coder unanimity, 2026-11-05). Copied from the frozen record, not from coded files
Q2_BASE = {('gemini', 'KA-KD'): (8, 10), ('gemini', 'KD-KA'): (10, 10), ('openai', 'KA-KD'): (0, 0),
           ('openai', 'KD-KA'): (10, 10), ('anthropic', 'KA-KD'): (0, 9), ('anthropic', 'KD-KA'): (10, 10),
           ('qwen', 'KA-KD'): (7, 10), ('qwen', 'KD-KA'): (10, 10)}


def fisher(a, b, c, d):
    n, r1, c1 = a + b + c + d, a + b, a + c
    p = lambda x: comb(r1, x) * comb(n - r1, c1 - x) / comb(n, c1)
    p0 = p(a)
    return min(1.0, sum(p(x) for x in range(max(0, c1 - (n - r1)), min(r1, c1) + 1) if p(x) <= p0 + 1e-12))


def ac1(pairs, cats):
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    pi = {c: sum((a == c) + (b == c) for a, b in pairs) / (2 * n) for c in cats}
    pe = sum(p * (1 - p) for p in pi.values()) / max(1, len(cats) - 1)
    return po, (po - pe) / (1 - pe) if pe < 1 else 1.0


def load(design, cb, var):
    by, err = collections.defaultdict(dict), 0
    for f in glob.glob(f'{D}/coded_{design}_{cb}_*cb3.3.jsonl'):
        for l in open(f, encoding='utf-8'):
            if not l.strip():
                continue
            r = json.loads(l)
            if 'values' not in r:
                err += 1
                continue
            by[tuple(r['key'])][r['coder']] = str(r['values'][var]['value'])
    return by, err


def cons(d):
    s = set(d.values())
    return s.pop() if len(s) == 1 and len(d) == 2 else None


def north(by, s, o, t):
    ks = [k for k in by if k[1] == s and k[3] == o and str(k[-1]).startswith(f'{t}:')]
    return sum(cons(by[k]) == '北' for k in ks), len(ks), sum(cons(by[k]) is None for k in ks)


def main():
    L = []
    P = L.append
    q = {d: load(d, 'q1', 'choice') for d in ('q2_count', 'q2_eval')}
    c = {d: load(d, 'q2_consistency', 'consistency_claim') for d in ('q2_count', 'q2_eval')}

    P('# q2_count — control adding only the three-question announcement (frozen record)\n')
    P('scenario rescue_two_towers / codebook v3.3. Decision rules: ANALYSIS_PLANS "q2_count" '
      '(2026-11-17, fixed before extraction).\n')
    P('| Design | Sentence added to the system prompt | Run date | Extraction |\n|---|---|---|---|')
    P('| q2 | none | 2026-11-05 | v2.1, 3-coder unanimity (`RESULTS_q2.md`) |')
    P('| q2_count | "I will now ask you three questions. Please answer them in order." (「これから質問を3つします。順にお答えください。」) | 2026-11-07 | v3.3, 2-coder agreement (this document) |')
    P('| q2_eval | the above plus "to assess your aptitude as a hero" (「勇者としての適性を測るための」) and a 【質問N】 (Question N) header on each turn | 2026-11-07 | v3.3, 2-coder agreement (this document; v3.1 results are kept in `RESULTS_q2_eval.md`) |')
    P('\nSubject history format as before (folded for gemini, native turns for the other three).'
      '\nq2_count and q2_eval ran on the same day. q2 differs in run date, extraction version and aggregation rule, so comparisons with q2 are for reference only.\n')

    P('## 0. Extraction quality\n')
    P('| Design | Variable | Turns | Agreement | AC1 | Splits | Extraction failures |\n|---|---|---|---|---|---|---|')
    for d in ('q2_count', 'q2_eval'):
        for name, (by, err), cats in (('choice', q[d], ['北', '南', '判定不能']),
                                      ('consistency_claim', c[d], ['整合している', '部分的に整合', '整合していない', '判定不能'])):
            pairs = [tuple(v.values()) for v in by.values() if len(v) == 2]
            po, g = ac1(pairs, cats)
            P(f'| {d} | `{name}` | {len(by)} | {po:.3f} | {g:.2f} | {sum(a != b for a, b in pairs)} | {err} |')

    P('\n## 1. Primary analysis — north choices on gemini\'s first KA-KD question (KA)\n')
    a, na, sa = north(q['q2_count'][0], 'gemini', 'KA-KD', 1)
    b, nb, sb = north(q['q2_eval'][0], 'gemini', 'KA-KD', 1)
    q2a = Q2_BASE[('gemini', 'KA-KD')][0]
    p_ce = fisher(a, na - a, b, nb - b)
    p_cq = fisher(a, na - a, q2a, 10 - q2a)
    P('| q2 (11-05) | q2_count (11-07) | q2_eval (11-07) | p, q2_count vs q2_eval | p, q2_count vs q2 |\n|---|---|---|---|---|')
    fmt = lambda p: '< 0.001' if p < 0.001 else f'{p:.3f}'
    P(f'| north {q2a}/10 | north {a}/{na} ({sa} split) | north {b}/{nb} ({sb} split) | {fmt(p_ce)} | {fmt(p_cq)} |')
    if p_ce < 0.05:
        verdict = '**The assessment frame plus numbering had an effect.** q2_count ran on the same day as q2_eval and differed in the primary cell. Frame and numbering cannot be separated.'
    elif p_cq < 0.05:
        verdict = ('**The three-question announcement and ordering instruction alone reproduced it.** q2_count was indistinguishable from q2_eval and differed from q2. '
                   'q2, however, used a different day and extraction version, so a day effect cannot be ruled out.')
    else:
        verdict = '**Undetermined.** q2_count was indistinguishable from both q2_eval and q2.'
    P(f'\nVerdict under the prespecified rule: {verdict}\n')

    P('## 2. All choice cells (descriptive only)\n')
    P('North counts, first question -> second question. q2 values are from `RESULTS_q2.md`. (split n) is the number of turns where the two coders disagreed.\n')
    P('| Subject | Order | q2 (11-05) | q2_count (11-07) | q2_eval (11-07, v3.3) |\n|---|---|---|---|---|')
    for s in SUBJ:
        for o in ORD:
            cells = []
            for d in ('q2_count', 'q2_eval'):
                parts = []
                for t in (1, 2):
                    x, n, sp = north(q[d][0], s, o, t)
                    parts.append(f'{x}' + (f'(split {sp})' if sp else '') + ('' if n == 10 else f'/{n}'))
                cells.append('->'.join(parts))
            b0 = Q2_BASE[(s, o)]
            P(f'| {s} | {o} | {b0[0]}->{b0[1]} | {cells[0]} | {cells[1]} |')

    P('\n## 3. Consistency claims (descriptive only)\n')
    P('| Subject | Design | Consistent | Partly consistent | Inconsistent | Split |\n|---|---|---|---|---|---|')
    for s in SUBJ:
        for d in ('q2_count', 'q2_eval'):
            by = c[d][0]
            cnt = collections.Counter(cons(by[k]) or '割れ' for k in by if k[1] == s)
            n = sum(cnt.values())
            P(f"| {s} | {d} | {cnt['整合している']}/{n} | {cnt['部分的に整合']} | {cnt['整合していない']} | {cnt['割れ']} |")

    P('\n## 4. What this does not show\n')
    P('- The assessment frame and the 【質問N】 numbering were added together, so the q2_eval - q2_count difference cannot be attributed to either')
    P('- Comparisons with q2 differ in run date, extraction version and aggregation rule. They are reference only; differences from q2 are not called effects')
    P('- Secondary cells have 10 trials each and are untested')
    P('- (split n) includes turns where extraction failed and only one coder value exists (one q2_count choice turn)')

    open(OUT, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print('\n'.join(L))


if __name__ == '__main__':
    main()
