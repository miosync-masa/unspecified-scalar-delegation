"""Assemble from data/ the working layout (build/) that the result generators read.

The generators were written against the working directories used during the research (q3c/, q4c/, qe/,
rations_main/ and so on). This script rebuilds that layout from the records in data/. These tables
(SUBSETS and COPIES) are the complete account of which subset comes from which record.

    python3 analysis/build_inputs.py      # rebuild build/
    sh analysis/make_all.sh               # build build/, run every generator and update results/

A subset selects records by (design = key[0], variable group = question, coder, codebook version).
Only successful rows are written, in file-name and line order of data/coded/.
"""
import json, os, shutil, glob
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
BUILD = ROOT / 'build'
CODERS = ('anthropic', 'gemini', 'openai', 'qwen')

# file name read by a generator -> how records are selected (design, variable group, codebook version); the coder follows from the name
SUBSETS = {}
for n in CODERS:
    SUBSETS[f'q3c/record_by_{n}.jsonl'] = ('q3', 'q3_record', '2.4', n)
    SUBSETS[f'q3c/recall_by_{n}.jsonl'] = ('q3_recall', 'q3_recall', '2.5', n)
    SUBSETS[f'q3c/post_by_{n}.jsonl'] = ('q3_post', 'q3_post', '2.5', n)
    SUBSETS[f'q3c/review_by_{n}.jsonl'] = ('q3_review', 'q3_review', '2.5', n)
    SUBSETS[f'q3c/probe_by_{n}.jsonl'] = ('q3_probe', 'q3_probe', '2.9', n)
    SUBSETS[f'q3c/cons_by_{n}.jsonl'] = ('q2', 'q2_consistency', '2.1', n)
    SUBSETS[f'q4c/by_{n}.jsonl'] = ('q4', 'q4', '3.0', n)
    SUBSETS[f'qe/q1_by_{n}.jsonl'] = ('q2_eval', 'q1', '3.1', n)
    SUBSETS[f'qe/cons_by_{n}.jsonl'] = ('q2_eval', 'q2_consistency', '3.1', n)
SUBSETS['q3c/q2choice_by_qwen.jsonl'] = ('q2', 'q1', '2.1', 'qwen')

# location read by a generator -> files in data/ (glob), copied as whole files
COPIES = {
    'q4full.jsonl': 'raw/results_q4.jsonl',
    'q2eval.jsonl': 'raw/results_q2_eval.jsonl',
    'results_q2_new.jsonl': 'raw/results_q2_early_20261104.jsonl',
    'results_q3_probe.jsonl': 'raw/results_q3_probe.jsonl',
    'results_pilot_a.jsonl': 'raw/results_pilot_a.jsonl',
    'coded_r/': 'coded/coded_pilot_a_rations_{anthropic-openai_by_qwen,anthropic-qwen_by_gemini,gemini-openai_by_anthropic,gemini-qwen_by_openai}_cb3.2.jsonl',
    'coded_d/': 'coded/coded_pilot_a_rations_deficit_*_cb3.3.jsonl',
    'q2fmt/coded/': 'coded/coded_q2+*_cb3.3.jsonl',
    'q2fmt/coded_old33/': 'coded/coded_q2_q2_consistency_*_cb3.3.jsonl',
    'q2fmt/coded_rerun/': 'coded/coded_q2_rerun_*_cb3.3.jsonl',
    'q2fmt/old_v21/': 'coded/coded_q2_q2_consistency_*-*-*_by_*[a-z].jsonl',
    'rations_main/': 'coded/coded_rations*_cb3.3.jsonl',
    'rations_main/results_rations.jsonl': 'raw/results_rations.jsonl',
    'q2count_in/': 'coded/coded_q2_[ce][ov][ua]*_cb3.3.jsonl',
    'q2x/': 'coded/coded_q2x*_cb3.3.jsonl',
    'q2x/results_q2x.jsonl': 'raw/results_q2x.jsonl',
    'elevator/': 'coded/coded_elevator*_cb3.4.jsonl',
    'elevator/results_elevator.jsonl': 'raw/results_elevator.jsonl',
    'elevator/results_elevator_norm.jsonl': 'raw/results_elevator_norm.jsonl',
    'elevator/': 'coded/coded_elevator_*_cb3.4.jsonl',
    'elevator/results_elevator.jsonl': 'raw/results_elevator.jsonl',
    'elevator/results_elevator_norm.jsonl': 'raw/results_elevator_norm.jsonl',
    'q12/': 'coded/{coded_q1_*-*-*_by_*[a-z],coded_q2_q1_*-*-*_by_*[a-z],coded_q2_q2_consistency_*-*-*_by_*[a-z]}.jsonl',
}
# modules the generators import, and the frozen records and definitions they read as input
LINKS = ['fjf_extract.py', 'fjf_api.py', 'fjf_scenario.py', 'scenario_rescue.yaml',
         'scenario_rations.yaml', 'codebook_v1.yaml']


def coded_records():
    for f in sorted((DATA / 'coded').glob('*.jsonl')):
        for l in open(f, encoding='utf-8'):
            if l.strip():
                yield json.loads(l)


def main():
    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir()
    out = {p: [] for p in SUBSETS}
    want = {}
    for p, (design, q, ver, coder) in SUBSETS.items():
        want.setdefault((design, q, ver, coder), []).append(p)
    for r in coded_records():
        if 'values' not in r or r.get('error'):
            continue
        k = (r['key'][0], r.get('question'), str(r.get('codebook_version')), r.get('coder'))
        for p in want.get(k, []):
            out[p].append(r)
    for p, rs in out.items():
        dst = BUILD / p
        dst.parent.mkdir(parents=True, exist_ok=True)
        with open(dst, 'w', encoding='utf-8') as f:
            for r in rs:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
        if not rs:
            raise SystemExit(f'empty subset: {p} {SUBSETS[p]}')
    for dst, pat in COPIES.items():
        pats = [pat]
        if '{' in pat:
            head, rest = pat.split('{', 1)
            alts, tail = rest.split('}', 1)
            pats = [head + a + tail for a in alts.split(',')]
        srcs = sorted(x for q in pats for x in glob.glob(str(DATA / q)))
        if not srcs:
            raise SystemExit(f'not found in data/: {pat}')
        if dst.endswith('/'):
            (BUILD / dst).mkdir(parents=True, exist_ok=True)
            for s in srcs:
                shutil.copy(s, BUILD / dst / Path(s).name)
        else:
            (BUILD / dst).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(srcs[0], BUILD / dst)
    for name in LINKS:
        shutil.copy(ROOT / name, BUILD / name)
    for f in (ROOT / 'results').glob('*.md'):
        shutil.copy(f, BUILD / f.name)
    for f in (ROOT / 'analysis').glob('*.py'):
        shutil.copy(f, BUILD / f.name)
    print(f'built build/ ({len(out)} subsets, {len(COPIES)} copy groups)')


if __name__ == '__main__':
    main()
