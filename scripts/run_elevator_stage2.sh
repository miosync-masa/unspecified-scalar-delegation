#!/bin/sh
# SI elevator 段階 2：規範なし（2 ターン）と規範あり（3 ターン）を同じ実行で交互に割り付ける。
# 4 被験者 × 3 確率 × 2 条件 × 25 試行 = 600 本。段階 1 の後に回す。
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
echo "段階 2：実行 600 本・抽出 12 本 完了"
