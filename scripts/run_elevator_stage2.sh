#!/bin/sh
# Supplementary elevator, stage 2: no norm (2 turns) and norm first (3 turns), interleaved within one run.
# 4 subjects x 3 probabilities x 2 conditions x 25 trials = 600 runs. Run after stage 1.
set -e
export FJF_FLAT_HISTORY=""
R=results_elevator.jsonl
python3 fjf_run.py --scenario scenario_elevator.yaml --design elevator_action elevator_prenorm --out $R --workers 4
unset FJF_FLAT_HISTORY
for Q in elevator_norm elevator_action elevator_reason; do
  python3 fjf_extract.py --in $R --cb $Q --coder anthropic --subject gemini openai    --workers 4
  python3 fjf_extract.py --in $R --cb $Q --coder openai    --subject gemini qwen      --workers 4
  python3 fjf_extract.py --in $R --cb $Q --coder gemini    --subject anthropic qwen   --workers 4
  python3 fjf_extract.py --in $R --cb $Q --coder qwen      --subject anthropic openai --workers 4
done
echo "stage 2: 600 runs, 12 extractions done"
