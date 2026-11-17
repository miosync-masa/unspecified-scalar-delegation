#!/bin/sh
# 第2シナリオ本番。4被験者 × 4条件 × 25試行 × 4ターン = 1600 コール。
# 条件は試行ごとのブロックに交互に並ぶ（fjf_run.py の既定 --order interleave）。
# 履歴の形は 4 体とも本物のターンにそろえる（FJF_FLAT_HISTORY を空にする）。
# 判定ルールは RUNBOOK「第2シナリオ本番の事前登録」に先に書いてある。
set -e
export FJF_FLAT_HISTORY=""
R=results_rations.jsonl
python3 fjf_run.py --scenario scenario_rations.yaml --design rations --out $R --workers 4
# 抽出は完全交差（自分以外の2体）。--cb rations で人ごとの不足も一緒に取れる。
unset FJF_FLAT_HISTORY
python3 fjf_extract.py --in $R --cb rations --coder anthropic --subject gemini openai --workers 4
python3 fjf_extract.py --in $R --cb rations --coder openai    --subject gemini qwen   --workers 4
python3 fjf_extract.py --in $R --cb rations --coder gemini    --subject anthropic qwen --workers 4
python3 fjf_extract.py --in $R --cb rations --coder qwen      --subject anthropic openai --workers 4
echo "実行 400 本・抽出 4 本 完了"
