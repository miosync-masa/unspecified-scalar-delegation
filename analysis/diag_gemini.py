# -*- coding: utf-8 -*-
"""Gemini の interactions API で何が起きているかを確かめる（3コール、出力は短い）。

1) 構造化の単発   … fjf_api が最初に試す形。落ちるなら例外をそのまま出す
2) 構造化の多ターン … 被験者側の履歴つき呼び出しと同じ形
3) 畳んだテキスト  … 予備の経路。応答の属性と usage の在処を全部出す
"""
import os, json, traceback
from fjf_api import clients_for

client, model = clients_for(["gemini"])["gemini"]
SYS = "あなたは短く答えます。"
cfg = {"max_output_tokens": 256, "thinking_level": "low"}


def show(r, label):
    print(f"--- {label}: 応答の型 {type(r).__name__}")
    print("   公開属性:", [a for a in dir(r) if not a.startswith('_')][:60])
    d = None
    for m in ("model_dump", "to_dict", "dict"):
        if hasattr(r, m):
            try:
                d = getattr(r, m)()
                break
            except Exception:
                pass
    if d is None:
        print("   辞書化できない"); return

    def walk(x, path=""):
        if isinstance(x, dict):
            for k, v in x.items():
                p = f"{path}.{k}" if path else k
                if any(w in k.lower() for w in ("usage", "token", "cache")):
                    print(f"   {p} = {json.dumps(v, ensure_ascii=False, default=str)[:300]}")
                walk(v, p)
        elif isinstance(x, list):
            for i, v in enumerate(x[:3]):
                walk(v, f"{path}[{i}]")
    walk(d)
    print("   本文:", (getattr(r, "output_text", None) or "")[:60])


def attempt(label, **kw):
    print(f"\n=== {label} ===")
    try:
        r = client.interactions.create(model=model, system_instruction=SYS,
                                       generation_config=cfg, **kw)
        print("   成功")
        show(r, label)
    except Exception as e:
        print(f"   失敗: {type(e).__name__}: {e}")
        traceback.print_exc(limit=3)


attempt("1) 構造化・単発",
        input=[{"role": "user", "content": "1+1は？"}])
attempt("2) 構造化・多ターン",
        input=[{"role": "user", "content": "1+1は？"},
               {"role": "assistant", "content": "2です。"},
               {"role": "user", "content": "それに3を足すと？"}])
attempt("3) 畳んだテキスト（予備の経路）",
        input="【状況】\n1+1は？")
