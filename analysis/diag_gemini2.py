# -*- coding: utf-8 -*-
"""Gemini interactions API に履歴を「本物のターン」として渡せる形を探す。
各候補 1 コール（全 7 コール）。正しく多ターンとして読めていれば、最後の答えは 5 になる
（1+1=2、それに3を足すと5）。畳んだテキストで読ませた場合と区別するため、
2 ターン目の自分の答えは「2です。」とだけ書く。
"""
import traceback
from fjf_api import clients_for

client, model = clients_for(["gemini"])["gemini"]
SYS = "あなたは短く、数字だけで答えます。"
cfg = {"max_output_tokens": 128, "thinking_level": "low"}
T = lambda s: [{"type": "text", "text": s}]


def attempt(label, **kw):
    print(f"\n=== {label} ===")
    try:
        r = client.interactions.create(model=model, system_instruction=SYS,
                                       generation_config=cfg, **kw)
        print(f"   成功  答え: {(r.output_text or '').strip()[:40]!r}  id: {getattr(r, 'id', None)}")
        return r
    except Exception as e:
        print(f"   失敗: {type(e).__name__}: {str(e).splitlines()[0][:200]}")
        msg = str(e)
        for line in msg.splitlines()[1:6]:
            print("     ", line[:200])
        return None


attempt("A) 単発・type 付きの部品", input=T("1+1は？"))
attempt("E1) ステップ列・content は部品のリスト",
        input=[{"type": "user_input", "content": T("1+1は？")},
               {"type": "model_output", "content": T("2です。")},
               {"type": "user_input", "content": T("それに3を足すと？")}])
attempt("E2) ステップ列・content は文字列",
        input=[{"type": "user_input", "content": "1+1は？"},
               {"type": "model_output", "content": "2です。"},
               {"type": "user_input", "content": "それに3を足すと？"}])
attempt("B) ターン列・role=user/model",
        input=[{"role": "user", "content": T("1+1は？")},
               {"role": "model", "content": T("2です。")},
               {"role": "user", "content": T("それに3を足すと？")}])
attempt("C) ターン列・role=user/assistant",
        input=[{"role": "user", "content": T("1+1は？")},
               {"role": "assistant", "content": T("2です。")},
               {"role": "user", "content": T("それに3を足すと？")}])
r1 = attempt("D1) 連鎖の1回目", input=T("1+1は？"))
if r1 is not None:
    attempt("D2) 連鎖の2回目（previous_interaction_id）",
            input=T("それに3を足すと？"), previous_interaction_id=r1.id)
