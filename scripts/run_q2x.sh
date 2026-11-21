#!/bin/sh
# Assessment frame x numbering 2x2. KA-KD only, 4 subjects x 4 cells x 15 trials = 240 runs, 720 calls.
# The four cells are mixed in one run and interleaved in trial blocks (same day, same time window).
# History format is the default used for q2_count and q2_eval (folded for gemini, native turns for the others).
# The two diagonal cells were confirmed character-identical to q2_count and q2_eval.
# Decision rules: docs/ANALYSIS_PLANS.md, "Frame x numbering 2x2".
set -e
unset FJF_FLAT_HISTORY
R=results_q2x.jsonl
python3 fjf_run.py --design q2x_plain q2x_num --out $R --workers 4
# Extract choice (q1) only. Two coders, fully crossed.
python3 fjf_extract.py --in $R --cb q1 --coder anthropic --subject gemini openai    --workers 4
python3 fjf_extract.py --in $R --cb q1 --coder openai    --subject gemini qwen      --workers 4
python3 fjf_extract.py --in $R --cb q1 --coder gemini    --subject anthropic qwen   --workers 4
python3 fjf_extract.py --in $R --cb q1 --coder qwen      --subject anthropic openai --workers 4
echo "240 runs, 4 extractions done"
