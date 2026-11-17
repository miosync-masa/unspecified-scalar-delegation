#!/bin/sh
# q2_count（「全3問の予告」＋「順に答える指示」のみ）と q2_eval（評価の体裁＋連番）を、
# 同じコードブック v3.3・同じコーダーの組で抽出する。q2_eval は v3.1 で抽出済みだが、
# 版をそろえるために抽出し直す（v3.1 の結果は RESULTS_q2_eval.md に歴史的結果として残す）。
# 両設計とも 2026-11-07 の同じ日に回っている。判定ルールは RUNBOOK「q2_count の事前登録」。
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
echo "抽出 16 本 完了"
