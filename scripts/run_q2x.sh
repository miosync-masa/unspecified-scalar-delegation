#!/bin/sh
# 評価の体裁 × 連番の 2×2。KA-KD のみ、4 被験者 × 4 セル × 15 試行 = 240 本・720 コール。
# 4 セルを一つの実行に混ぜ、試行ごとのブロックに交互に並べる（同じ日・同じ時間帯）。
# 履歴の形は q2_count・q2_eval と同じ既定（gemini は畳む形、他は本物のターン）。
# 角の 2 セルは q2_count・q2_eval と本文が一字も同じであることを確認済み。
# 判定ルールは RUNBOOK「体裁 × 連番 2×2 の事前登録」。
set -e
unset FJF_FLAT_HISTORY
R=results_q2x.jsonl
python3 fjf_run.py --design q2x_plain q2x_num --out $R --workers 4
# 抽出は選択（q1）だけ。2 コーダー完全交差。
python3 fjf_extract.py --in $R --cb q1 --coder anthropic --subject gemini openai    --workers 4
python3 fjf_extract.py --in $R --cb q1 --coder openai    --subject gemini qwen      --workers 4
python3 fjf_extract.py --in $R --cb q1 --coder gemini    --subject anthropic qwen   --workers 4
python3 fjf_extract.py --in $R --cb q1 --coder qwen      --subject anthropic openai --workers 4
echo "実行 240 本・抽出 4 本 完了"
