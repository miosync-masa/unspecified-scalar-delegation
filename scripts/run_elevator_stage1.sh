#!/bin/sh
# Supplementary elevator, stage 1: norm check. 4 subjects x 25 trials = 100 calls.
# The gate (at least 23 yes of 25) was fixed in advance: docs/ANALYSIS_PLANS.md, "Supplementary: elevator".
set -e
export FJF_FLAT_HISTORY=""
R=results_elevator_norm.jsonl
python3 fjf_run.py --scenario scenario_elevator.yaml --design elevator_norm --out $R --workers 4
unset FJF_FLAT_HISTORY
for Q in elevator_norm; do
  python3 fjf_extract.py --in $R --cb $Q --coder anthropic --subject gemini openai    --workers 4
  python3 fjf_extract.py --in $R --cb $Q --coder openai    --subject gemini qwen      --workers 4
  python3 fjf_extract.py --in $R --cb $Q --coder gemini    --subject anthropic qwen   --workers 4
  python3 fjf_extract.py --in $R --cb $Q --coder qwen      --subject anthropic openai --workers 4
done
echo "stage 1: 100 runs, 4 extractions done"
