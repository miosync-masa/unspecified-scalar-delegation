"""data/ から、結果文書の生成スクリプトが読む作業レイアウト（build/）を組み立てる。

生成スクリプトは研究中の作業ディレクトリの構成（q3c/、q4c/、qe/、rations_main/ など）を
前提に書かれている。ここで、その構成を data/ の記録から再現する。どの部分集合が
どの記録から来たかは、この表（SUBSETS と COPIES）がすべてである。

    python3 analysis/build_inputs.py      # build/ を作り直す
    sh analysis/make_all.sh               # build/ を作って全生成スクリプトを回し、results/ を更新する

部分集合は (設計名=key[0], 変数群=question, コーダー, コードブック版) で記録を選ぶ。
成功した行だけを、data/coded/ のファイル名順・行順で書き出す。
"""
import json, os, shutil, glob
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
BUILD = ROOT / 'build'
CODERS = ('anthropic', 'gemini', 'openai', 'qwen')

# 生成スクリプトが読むファイル名 → 記録の選び方（設計名, 変数群, コードブック版）。コーダーは名前から決まる
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

# 生成スクリプトが読む場所 → data/ のファイル（glob）。ファイルごとそのまま置く
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
    'q12/': 'coded/{coded_q1_*-*-*_by_*[a-z],coded_q2_q1_*-*-*_by_*[a-z],coded_q2_q2_consistency_*-*-*_by_*[a-z]}.jsonl',
}
# 生成スクリプトが import するモジュールと、入力として読む確定記録・定義
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
            raise SystemExit(f'部分集合が空です: {p} {SUBSETS[p]}')
    for dst, pat in COPIES.items():
        pats = [pat]
        if '{' in pat:
            head, rest = pat.split('{', 1)
            alts, tail = rest.split('}', 1)
            pats = [head + a + tail for a in alts.split(',')]
        srcs = sorted(x for q in pats for x in glob.glob(str(DATA / q)))
        if not srcs:
            raise SystemExit(f'data/ に見つかりません: {pat}')
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
    print(f'build/ を作りました（部分集合 {len(out)} 本、コピー {len(COPIES)} 組）')


if __name__ == '__main__':
    main()
