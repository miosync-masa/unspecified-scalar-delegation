#!/bin/sh
# Rebuild every result document from data/. Run from the repository root.
# The q1 and q2 frozen records (RESULTS_q1.md / RESULTS_q2.md) keep their text fixed as historical versions.
# Their tables used by other documents are computed from coded data by analysis/q12_tables.py and checked against them.
#   sh analysis/make_all.sh            # overwrite results/
#   sh analysis/make_all.sh --check    # leave results/ untouched and only report differences from the rebuilt version
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
    if diff -q results/$f build/$f > /dev/null; then echo "match  $f"; else echo "DIFF   $f"; ST=1; fi
  done
  exit $ST
fi
for f in $OUTS; do cp build/$f results/$f; done
echo "results/ updated"
