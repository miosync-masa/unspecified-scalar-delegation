#!/bin/sh
# Second scenario, main run. 4 subjects x 4 conditions x 25 trials x 4 turns = 1600 calls.
# Conditions are interleaved in trial blocks (fjf_run.py default --order interleave).
# History format is native turns for all four (FJF_FLAT_HISTORY empty).
# Decision rules were fixed in advance: docs/ANALYSIS_PLANS.md, "Second scenario (rationing), main run".
set -e
export FJF_FLAT_HISTORY=""
R=results_rations.jsonl
python3 fjf_run.py --scenario scenario_rations.yaml --design rations --out $R --workers 4
# Extraction fully crossed (the two non-self coders). --cb rations also takes per-person shortfall.
unset FJF_FLAT_HISTORY
python3 fjf_extract.py --in $R --cb rations --coder anthropic --subject gemini openai --workers 4
python3 fjf_extract.py --in $R --cb rations --coder openai    --subject gemini qwen   --workers 4
python3 fjf_extract.py --in $R --cb rations --coder gemini    --subject anthropic qwen --workers 4
python3 fjf_extract.py --in $R --cb rations --coder qwen      --subject anthropic openai --workers 4
echo "400 runs, 4 extractions done"
