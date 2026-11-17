#!/bin/sh
# 旧 q2（本物のターン）の anthropic と qwen の整合性ターンを v3.3 で抽出し直す。
# コーダーの組は新（畳む形）と同じにする: anthropic ← gemini＋qwen、qwen ← gemini＋openai。
# これで「形の違い」と「コードブック版の違い」を切り分ける。
# 入力は 160 本そろった旧の本番ファイル（md5 先頭 e6c278c0）。手元の名前に合わせて O を直すこと。
set -e
unset FJF_FLAT_HISTORY
O=results_q2.jsonl
python3 fjf_extract.py --in $O --cb q2_consistency --coder gemini --subject anthropic qwen --workers 4
python3 fjf_extract.py --in $O --cb q2_consistency --coder qwen   --subject anthropic      --workers 4
python3 fjf_extract.py --in $O --cb q2_consistency --coder openai --subject qwen           --workers 4
echo "抽出 3 本（160 コール）完了"
