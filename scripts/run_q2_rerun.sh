#!/bin/sh
# Rerun q2 KA-KD with native turns (anthropic and qwen, 20 trials each, 120 calls),
# then extract with v3.3 using the same coder pairs as the swapped run (q1 and q2_consistency, 2 coders each).
# Decision rules were fixed in advance: docs/ANALYSIS_PLANS.md, "History-format rerun".
set -e
unset FJF_FLAT_HISTORY          # anthropic and qwen get native turns (same form as the earlier q2)
R=results_q2_rerun.jsonl
python3 fjf_run.py --design q2_rerun --provider anthropic qwen --out $R --workers 4
for CB in q2_consistency q1; do
  python3 fjf_extract.py --in $R --cb $CB --coder gemini --subject anthropic qwen --workers 4
  python3 fjf_extract.py --in $R --cb $CB --coder qwen   --subject anthropic      --workers 4
  python3 fjf_extract.py --in $R --cb $CB --coder openai --subject qwen           --workers 4
done
echo "40 runs, 6 extractions done"
