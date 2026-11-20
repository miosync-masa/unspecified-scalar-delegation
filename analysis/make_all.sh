#!/bin/sh
# data/ から結果文書をすべて作り直す。リポジトリのルートで実行する。
# q1・q2 の確定記録（RESULTS_q1.md / RESULTS_q2.md）は歴史的版として本文を固定している。
# 他の文書が使うその表は analysis/q12_tables.py が採点データから計算し、確定記録と照合する。
#   sh analysis/make_all.sh            # results/ を上書きする
#   sh analysis/make_all.sh --check    # results/ は触らず、作り直した版との差分だけ表示する
set -e
cd "$(dirname "$0")/.."
python3 analysis/build_inputs.py
cd build
for g in gen_results_q3 gen_results_q4 gen_results_q2_eval gen_results gen_exhibits \
         gen_results_pilot_a gen_results_q2_format gen_results_rations gen_results_q2_count gen_results_q2x gen_results_elevator; do
  python3 $g.py > /dev/null
  echo "  $g"
done
cd ..
OUTS="RESULTS.md RESULTS_q3.md RESULTS_q4.md RESULTS_q2_eval.md EXHIBITS.md RESULTS_pilot_a.md \
      RESULTS_q2_format.md RESULTS_rations.md RESULTS_q2_count.md RESULTS_q2x.md RESULTS_elevator.md"
if [ "$1" = "--check" ]; then
  ST=0
  for f in $OUTS; do
    if diff -q results/$f build/$f > /dev/null; then echo "一致  $f"; else echo "差分  $f"; ST=1; fi
  done
  exit $ST
fi
for f in $OUTS; do cp build/$f results/$f; done
echo "results/ を更新しました"
