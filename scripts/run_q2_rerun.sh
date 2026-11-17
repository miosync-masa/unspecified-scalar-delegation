#!/bin/sh
# q2 の KA-KD を本物のターンのまま回し直す（anthropic・qwen、各20試行、120 コール）。
# 続けて、新と同じコーダーの組で v3.3 抽出（q1 と q2_consistency、各 2 体）。
# 判定ルールは RUNBOOK「gemini だけ刺激の形が違っていた」節に先に書いてある。
set -e
unset FJF_FLAT_HISTORY          # anthropic と qwen は本物のターン（過去の q2 と同じ形）
R=results_q2_rerun.jsonl
python3 fjf_run.py --design q2_rerun --provider anthropic qwen --out $R --workers 4
for CB in q2_consistency q1; do
  python3 fjf_extract.py --in $R --cb $CB --coder gemini --subject anthropic qwen --workers 4
  python3 fjf_extract.py --in $R --cb $CB --coder qwen   --subject anthropic      --workers 4
  python3 fjf_extract.py --in $R --cb $CB --coder openai --subject qwen           --workers 4
done
echo "実行 40 本・抽出 6 本 完了"
