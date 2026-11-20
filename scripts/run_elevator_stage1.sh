#!/bin/sh
# SI elevator 段階 1：規範の確認。4 被験者 × 25 試行 = 100 コール。
# 関門（yes が 25 中 23 以上）は RUNBOOK「SI: elevator の事前登録」に先に書いてある。
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
echo "段階 1：実行 100 本・抽出 4 本 完了"
