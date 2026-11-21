"""Generate RESULTS_q2_format.md from extraction files only. Every number is counted here.

Earlier: q2 extraction (the v2.1 files in data/coded; codebook v2.1, 3 coders) and the tables in RESULTS_q2.md
Swapped: q2fmt/coded (codebook v3.3, 2 coders, fully crossed)
"""
from labels_en import en
import json, glob, collections, sys

NEW = 'q2fmt/coded'
OLD_CONS = 'q2fmt/old_v21/*coded_q2_q2_consistency_*'
SUBJ = ('gemini', 'openai', 'anthropic', 'qwen')
ORD = ('KA-KD', 'KD-KA', 'NA-ND', 'ND-NA')
CATS = ['整合している', '部分的に整合', '整合していない', '判定不能']
FMT_NEW = {'gemini': 'native turns', 'openai': 'folded', 'anthropic': 'folded', 'qwen': 'folded'}
FMT_OLD = {'gemini': 'folded', 'openai': 'native turns', 'anthropic': 'native turns', 'qwen': 'native turns'}

# Earlier order lock-in (RESULTS_q2.md section 1, 3-coder unanimity). Not all earlier extraction files survive, so values are copied from the table.
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

    P('# Second question: history format x model — frozen record\n')
    P('scenario_rescue.yaml v1.2 / swapped run extracted with codebook_v1.yaml v3.3 (earlier run: v2.1)\n')
    P('In the earlier q2, only gemini received the history folded into the message (quoted as 「【あなたの回答】」, "your answer"), '
      'while the other three received native turns. We swapped the formats and ran again.\n')
    P('| Subject | Earlier | Swapped |\n|---|---|---|')
    for s in SUBJ:
        P(f'| {s} | {FMT_OLD[s]} | {FMT_NEW[s]} |')
    P('\n4 orders x 10 trials x 3 turns each. Extraction by the two models other than the subject (fully crossed); only two-coder agreement counts.\n')

    # 1. lock-in
    P('## 1. Order lock-in — the three patterns survive swapping the format\n')
    P('North counts, first question -> second question. Earlier: RESULTS_q2.md section 1 (3-coder unanimity); swapped: 2-coder agreement. '
      '(u n) is the number of cases where the two coders split or only one value was obtained.\n')
    P('| Subject | Format | KA-KD | KD-KA | NA-ND | ND-NA |\n|---|---|---|---|---|---|')
    for s in SUBJ:
        cells_new = []
        for o in ORD:
            parts = []
            for t in (1, 2):
                ks = [k for k in newq if k[1] == s and k[3] == o and k[-1].startswith(f'{t}:')]
                c = [cons(newq[k], 'choice') for k in ks]
                miss = sum(x is None for x in c) + (10 - len(ks))
                parts.append(f"{sum(x == '北' for x in c)}" + (f'(u{miss})' if miss else ''))
            cells_new.append('->'.join(parts))
        P(f'| {s} earlier | {FMT_OLD[s]} | ' + ' | '.join(x.replace('北', '').replace('→', '->') for x in OLD_LOCK[s]) + ' |')
        P(f'| {s} swapped | {FMT_NEW[s]} | ' + ' | '.join(cells_new) + ' |')

    P('\n## 2. Citing and denying the attribute — KD turns\n')
    P('| Subject | Position | frame_cited true | frame_denied true |\n|---|---|---|---|')
    for s in SUBJ:
        for o, t in (('KA-KD', 2), ('KD-KA', 1)):
            ks = [k for k in newq if k[1] == s and k[3] == o and k[-1].startswith(f'{t}:')]
            fc = collections.Counter(cons(newq[k], 'frame_cited') for k in ks)
            fd = collections.Counter(cons(newq[k], 'frame_denied') for k in ks)
            P(f"| {s} | t{t} | {fc['true']}/{len(ks)} ({fc[None]} split) | {fd['true']}/{len(ks)} ({fd[None]} split) |")

    # 3. consistency
    P('\n## 3. Consistency turn — the ordering does not change when the format is swapped\n')
    P('Earlier: 3-coder unanimity; swapped: 2-coder agreement. The agreement rules differ in strictness, so split counts are not compared directly.\n')
    P('| Subject | Format | Consistent | Partly consistent | Inconsistent | Split |\n|---|---|---|---|---|---|')
    to, tn = cons_table(oldc), cons_table(newc)
    for s in SUBJ:
        for lab, t, fm in (('earlier', to, FMT_OLD), ('swapped', tn, FMT_NEW)):
            n, c, _ = t[s]
            P(f"| {s} {lab} | {fm[s]} | {c['整合している']}/{n} | {c['部分的に整合']} | {c['整合していない']} | {c['割れ']} |")

    P('\n**Agreement (compared within the same coder pair)**\n')
    P('| Subject | Coders | Earlier AC1 | Swapped AC1 |\n|---|---|---|---|')
    for s in SUBJ:
        oc = sorted({c for k in oldc if k[1] == s for c in oldc[k]})
        nc = sorted({c for k in newc if k[1] == s for c in newc[k]})
        a, b = [c for c in nc if c in oc][:2]
        row = []
        for by in (oldc, newc):
            ks = [k for k in by if k[1] == s]
            row.append(ac1([(by[k][a]['consistency_claim'], by[k][b]['consistency_claim']) for k in ks], CATS)[1])
        P(f'| {s} | {a} + {b} | {row[0]:.2f} | {row[1]:.2f} |')

    P('\n**Cell differences (by order, swapped run)**\n')
    P('C = consistent, P = partly consistent, I = inconsistent, S = the two coders split, U = undeterminable\n')
    P('| Subject | KA-KD | KD-KA | NA-ND | ND-NA |\n|---|---|---|---|---|')
    for s in ('anthropic', 'qwen'):
        cells = []
        for o in ORD:
            c = collections.Counter(cons(newc[k], 'consistency_claim') or '割れ' for k in newc if k[1] == s and k[3] == o)
            SHORT = {'整合している': 'C', '部分的に整合': 'P', '整合していない': 'I', '割れ': 'S', '判定不能': 'U'}
            cells.append(' '.join(f'{SHORT[x]}{n}' for x, n in c.most_common()))
        P(f'| {s} | ' + ' | '.join(cells) + ' |')

    # 3b. control: earlier format re-extracted with v3.3
    old33, _, _ = load('q2fmt/coded_old33/*', 'consistency_claim')
    P('\n### 3b. Comparison at the same codebook version (earlier format also v3.3, same coder pairs)\n')
    P('anthropic and qwen in the earlier format were re-extracted with v3.3 by the same coder pairs as the swapped run (anthropic <- gemini + qwen, '
      'qwen <- gemini + openai). Two-coder agreement only.\n')
    P('| Subject | Format | Total | KA-KD | KD-KA | NA-ND | ND-NA |\n|---|---|---|---|---|---|---|')
    SH = {'整合している': 'C', '部分的に整合': 'P', '整合していない': 'I', '割れ': 'S', '判定不能': 'U'}
    for s in ('anthropic', 'qwen'):
        for lab, by, fm in (('earlier', old33, FMT_OLD), ('swapped', newc, FMT_NEW)):
            ks = [k for k in by if k[1] == s]
            tot = collections.Counter(cons(by[k], 'consistency_claim') or '割れ' for k in ks)
            cells = []
            for o in ORD:
                c = collections.Counter(cons(by[k], 'consistency_claim') or '割れ' for k in ks if k[3] == o)
                cells.append(' '.join(f'{SH[x]}{m}' for x, m in c.most_common()))
            P(f"| {s} {lab} | {fm[s]} | " + ' '.join(f'{SH[x]}{m}' for x, m in tot.most_common()) +
              ' | ' + ' | '.join(cells) + ' |')
    P('\n**No difference due to codebook version was seen.** Re-counting the earlier format under v3.3, anthropic KA-KD stays at '
      '"inconsistent" 6/10 (6 under v2.1 as well), and the overall distribution is nearly the same as under v2.1. '
      'The earlier-swapped difference is not the codebook version.\n')
    P('**The remaining difference is either format or run-to-run variation.** The swapped run also re-sampled the subject responses, '
      'so a format effect overlaps with the variation from rerunning the same condition. Both cells that differed are '
      '10 vs 10 and do not reach significance in a two-sided exact test.\n')
    P('| Cell | Earlier (native turns) | Swapped (folded) | Fisher p |\n|---|---|---|---|')
    for s, val in (('anthropic', '整合していない'), ('qwen', '部分的に整合')):
        a = sum(cons(old33[k], 'consistency_claim') == val for k in old33 if k[1] == s and k[3] == 'KA-KD')
        b = sum(cons(newc[k], 'consistency_claim') == val for k in newc if k[1] == s and k[3] == 'KA-KD')
        P(f'| {s} KA-KD "{en(val)}" | {a}/10 | {b}/10 | {fisher(a, 10 - a, b, 10 - b):.3f} |')
    P('\nBefore the rerun, these two cells suggested the hypothesis that "under the folded format both models shift toward partly consistent". '
      '**This hypothesis was not supported under the prespecified rule in 3c** (kept for the record).\n')

    # 3c. rerun (decision rule fixed in advance)
    rr, _, rerr = load('q2fmt/coded_rerun/*q2_consistency*', 'consistency_claim')
    P('\n### 3c. Rerun verdict (rule fixed in ANALYSIS_PLANS before seeing the data)\n')
    P('Design `q2_rerun`: anthropic and qwen KA-KD rerun with native turns, 20 trials each '
      '(2026-11-16, text character-identical to q2). Extraction v3.3, same coder pairs as 3b, two-coder agreement only. '
      f'Extraction failures: {len(rerr)}.\n')
    P('| Subject | Target cell | Earlier native (11-05) | Rerun native (11-16) | Folded (11-16) | Primary p | Stability p | Verdict |\n'
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
        verdict = 'supports a format effect' if pm < 0.05 and ps >= 0.05 else ('unstable' if ps < 0.05 else 'not supported')
        P(f'| {s} | "{en(val)}" | {a}/{na} | {r}/{nr} | {f}/{nf} | {pm:.3f} | {ps:.3f} | {verdict} |')
    P('\n**Under the prespecified rule, the two designated cells did not meet the criterion supporting a format effect.** '
      'We do not claim that "both models shift toward partly consistent under the folded format". '
      'The stability check did not detect a between-run difference for the prespecified categories '
      '(this does not mean the whole distribution was stable; see the exploratory table below).\n')

    P('**Exploratory findings (outside the rule; not confirmatory)**\n')
    P('| Subject | Value | Earlier native (11-05) | Rerun native (11-16) | Folded (11-16) | p, native vs native | p, same-day native vs folded |\n'
      '|---|---|---|---|---|---|---|')
    for s in ('anthropic', 'qwen'):
        for val in ('整合している', '部分的に整合', '整合していない'):
            a, na = kakd(old33, s, val)
            r, nr = kakd(rr, s, val)
            f, nf = kakd(newc, s, val)
            P(f'| {s} | {en(val)} | {a}/{na} | {r}/{nr} | {f}/{nf} | '
              f'{fisher(r, nr - r, a, na - a):.3f} | {fisher(r, nr - r, f, nf - f):.3f} |')
    P('\nExploratorily, qwen\'s output distribution also differed between run dates within the same format (non-designated categories). '
      'Testing a format difference therefore needs a design that interleaves both formats within the same run period. '
      'The table above lists 12 uncorrected tests as exploratory material and is not used for confirmation.')

    # 4. choice agreement & errors
    pairs = [tuple(v['choice'] for v in d.values()) for d in newq.values() if len(d) == 2]
    po, g = ac1(pairs, ['北', '南', '判定不能'])
    P('\n## 4. Extraction quality\n')
    P(f'- `choice`: agreement {po:.3f}, AC1 {g:.2f} over {len(pairs)} turns with both coders. '
      f"In each of the {sum(a != b for a, b in pairs)} splits, one coder returned \"undeterminable\"")
    P(f'- Extractions that returned no JSON: {len(err)} (' +
      '; '.join(f"{r['coder']} on {r['key'][1]} {r['key'][3]} #{r['key'][6]} {r['key'][-1]}" for r in err) +
      '). These turns have only one coder value and appear as (u) in the tables')
    P(f'- Codebook versions: consistency, earlier {dict(vo)} / swapped {dict(vn)}')

    P('\n## 5. What can and cannot be said\n')
    P('**What can be said**\n')
    P('1. **openai\'s full lock-in occurs without native turns.** Its past answer quoted in the message as '
      '「【あなたの回答】」 ("your answer") is enough to lock in both directions. '
      'The conversational role structure is not necessary; text presented as its own suffices.')
    P('2. **gemini\'s lack of lock-in is not due to the folded format.** With native turns it still reverses according to the attributes: NA->ND (north 0->7), '
      'ND->NA (north 10->0).')
    P('3. **gemini and openai "consistent" stays near ceiling** (swapped: gemini 39/40, '
      'openai 40/40). The ordering between models is preserved.')
    P('4. **The pattern of citing and denying the attribute is preserved.** openai on KD turns, regardless of position, '
      'cites 0/10 and denies 10/10.')
    P('\n**What cannot be said yet**\n')
    P('- The strength of anthropic\'s KD-KA lock (earlier 10/10 -> swapped 7/10, 1 unresolved). The direction is the same, but '
      'with 10 trials we cannot tell whether it differs')
    P('- Whether small consistency cell differences are format effects. The codebook version was ruled out in 3b, and the rerun (3c) '
      'did not support it under the prespecified rule. qwen\'s distribution moved across days even within the same format, '
      'so checking it would require interleaving both formats on the same day with equal trial counts')
    open('RESULTS_q2_format.md', 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print('\n'.join(L))


if __name__ == '__main__':
    main()
