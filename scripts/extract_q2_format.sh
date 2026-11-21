#!/bin/sh
# Extract the additional q2 data on history format. Fully crossed, no self-coding.
# Do not set FJF_FLAT_HISTORY for extraction (coders receive input in the same default form as before).
set -e
unset FJF_FLAT_HISTORY
N=results_q2_native-gemini.jsonl   # gemini, native turns
F=results_q2_flat.jsonl            # openai / anthropic / qwen, folded
for CB in q1 q2_consistency; do
  python3 fjf_extract.py --in $N --cb $CB --coder anthropic --subject gemini           --workers 4
  python3 fjf_extract.py --in $N --cb $CB --coder openai    --subject gemini           --workers 4
  python3 fjf_extract.py --in $F --cb $CB --coder anthropic --subject openai           --workers 4
  python3 fjf_extract.py --in $F --cb $CB --coder openai    --subject qwen             --workers 4
  python3 fjf_extract.py --in $F --cb $CB --coder gemini    --subject anthropic qwen   --workers 4
  python3 fjf_extract.py --in $F --cb $CB --coder qwen      --subject openai anthropic --workers 4
done
echo "12 extractions done"
