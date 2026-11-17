#!/bin/sh
# q2 の「履歴の渡し方」追加データを抽出する。自己採点を避けた完全交差。
# 抽出では FJF_FLAT_HISTORY を付けないこと（コーダーへの送り方は過去と同じ既定にする）。
set -e
unset FJF_FLAT_HISTORY
N=results_q2_native-gemini.jsonl   # gemini・本物のターン
F=results_q2_flat.jsonl            # openai / anthropic / qwen・畳んだ形
for CB in q1 q2_consistency; do
  python3 fjf_extract.py --in $N --cb $CB --coder anthropic --subject gemini           --workers 4
  python3 fjf_extract.py --in $N --cb $CB --coder openai    --subject gemini           --workers 4
  python3 fjf_extract.py --in $F --cb $CB --coder anthropic --subject openai           --workers 4
  python3 fjf_extract.py --in $F --cb $CB --coder openai    --subject qwen             --workers 4
  python3 fjf_extract.py --in $F --cb $CB --coder gemini    --subject anthropic qwen   --workers 4
  python3 fjf_extract.py --in $F --cb $CB --coder qwen      --subject openai anthropic --workers 4
done
echo "抽出 12 本 完了"
