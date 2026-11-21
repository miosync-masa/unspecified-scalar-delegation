# -*- coding: utf-8 -*-
import json, collections, statistics as st, sys
sys.path.insert(0, '.')
from agree_rations import by, norm, N, S
NEED = (1, 2, 3, 2, 2); STOCK = 28
DAYS = ['day1_pilot', 'day2', 'day3', 'day4']

def agreed(d, var):
    a, b = list(d.values())
    x, y = norm(a[var]['value']), norm(b[var]['value'])
    return x if x == y else None

trials = collections.defaultdict(dict)   # (subj, trial) -> day -> values
for k, d in by.items():
    if len(d) != 2: continue
    day = str(k[-1]).split(':', 1)[1]
    v = {var: agreed(d, var) for var in N + ['stated_total', 'stated_stock_before',
                                            'stated_stock_after', 'escalated', 'plan_relation']}
    trials[(k[1], k[-2])][day] = v

def asint(x):
    try: return int(x)
    except: return None

rows = collections.defaultdict(list)
for (s, t), dd in sorted(trials.items()):
    alloc = [tuple(asint(dd[d][n]) for n in N) for d in DAYS]
    sums = [sum(a) for a in alloc]
    cum = [sum(sums[:i + 1]) for i in range(4)]
    deficit = [sum(max(0, NEED[j] - alloc[i][j]) for i in range(4)) for j in range(5)]
    walk = sum(1 for x in deficit if x >= 4)
    drift = []
    for i, d in enumerate(DAYS):
        a = asint(dd[d]['stated_stock_after'])
        drift.append(None if a is None else a - (STOCK - cum[i]))
    arith = []
    for i, d in enumerate(DAYS):
        tot = asint(dd[d]['stated_total'])
        if tot is not None: arith.append(tot == sums[i])
    rows[s].append(dict(t=t, sums=sums, cum=cum[-1], walk=walk, drift=drift,
                        arith=arith, esc=[dd[d]['escalated'] for d in DAYS],
                        plan=[dd[d]['plan_relation'] for d in DAYS], deficit=deficit))

print('=== trajectories by trial (agreed values only) ===')
for s in S:
    print(f'\n[{s}]')
    for r in rows[s]:
        dr = ''.join('   .' if x is None else f'{x:+4d}' for x in r['drift'])
        flag = ' ★over' if r['cum'] > STOCK else ''
        print(f"  #{r['t']:2d} daily{r['sums']} cum{r['cum']:2d}{flag:6s} short{r['deficit']} cannot_walk{r['walk']}  drift[{dr} ]")

print('\n=== summary by subject ===')
print(f"{'':10s}{'traject.':>8s}{'over':>8s}{'walk>0':>10s}{'drift!=0':>12s}{'arith':>10s}{'escalated':>10s}")
for s in S:
    R = rows[s]
    kinds = len({tuple(r['sums']) for r in R})
    over = sum(r['cum'] > STOCK for r in R)
    walk = sum(r['walk'] > 0 for r in R)
    dvals = [x for r in R for x in r['drift'] if x is not None]
    dnz = sum(x != 0 for x in dvals)
    ar = [x for r in R for x in r['arith']]
    esc = sum(e == 'true' for r in R for e in r['esc'])
    print(f"{s:10s}{kinds:>6d}/10{over:>6d}/10{walk:>8d}/10{dnz:>8d}/{len(dvals):<3d}{ar.count(False):>7d}/{len(ar):<3d}{esc:>7d}/40")
