#!/bin/sh
# Extract q2_count (only the three-question announcement and the instruction to answer in order) and
# q2_eval (assessment frame plus numbering) with the same codebook v3.3 and the same coder pairs. q2_eval was
# extracted with v3.1 before; it is re-extracted to match versions (v3.1 results stay in RESULTS_q2_eval.md).
# Both designs ran on the same day, 2026-11-07. Decision rules: docs/ANALYSIS_PLANS.md, "q2_count".
set -e
unset FJF_FLAT_HISTORY
for D in q2_count q2_eval; do
  for CB in q1 q2_consistency; do
    python3 fjf_extract.py --in results_$D.jsonl --cb $CB --coder anthropic --subject gemini openai    --workers 4
    python3 fjf_extract.py --in results_$D.jsonl --cb $CB --coder openai    --subject gemini qwen      --workers 4
    python3 fjf_extract.py --in results_$D.jsonl --cb $CB --coder gemini    --subject anthropic qwen   --workers 4
    python3 fjf_extract.py --in results_$D.jsonl --cb $CB --coder qwen      --subject anthropic openai --workers 4
  done
done
echo "16 extractions done"
