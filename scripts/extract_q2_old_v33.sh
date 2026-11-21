#!/bin/sh
# Re-extract the consistency turns of anthropic and qwen from the earlier q2 (native turns) with v3.3.
# Same coder pairs as the swapped (folded) run: anthropic <- gemini + qwen, qwen <- gemini + openai.
# This separates the format difference from the codebook-version difference.
# Input is the complete earlier main-run file with 160 runs (md5 prefix e6c278c0). Adjust O to the local file name.
set -e
unset FJF_FLAT_HISTORY
O=results_q2.jsonl
python3 fjf_extract.py --in $O --cb q2_consistency --coder gemini --subject anthropic qwen --workers 4
python3 fjf_extract.py --in $O --cb q2_consistency --coder qwen   --subject anthropic      --workers 4
python3 fjf_extract.py --in $O --cb q2_consistency --coder openai --subject qwen           --workers 4
echo "3 extractions (160 calls) done"
