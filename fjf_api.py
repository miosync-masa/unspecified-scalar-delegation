#!/usr/bin/env python3
"""
プロバイダ層 — API の差をここだけに閉じ込める

実験の設計は scenario_rescue.yaml、測定器は codebook_v1.yaml、実行は
fjf_run.py が持つ。このモジュールは「文を投げて文を受け取る」だけを担う。

プロバイダを足すときに触るのは PROVIDERS / make_client / invoke / chat の
4 箇所だけ。
"""

import os
import sys
import random
import threading
import time

PROVIDERS = {
    "gemini": {
        "env": "GEMINI_API_KEY",
        "default_model": "models/gemini-4-argon",
        "pip": "google-genai",
    },
    "openai": {
        "env": "OPENAI_API_KEY",
        "default_model": "gpt-6-astra",   # effort="none" は 400 になる
        "pip": "openai",
    },
    "anthropic": {
        "env": "ANTHROPIC_API_KEY",
        "default_model": "claude-opus-5-5",
        "pip": "anthropic",
    },
    # qwen3.8-max はマルチモーダル API 側のモデルで、Generation.call では
    # 通らない。content を [{"text": ...}] のリストで渡す。
    "qwen": {
        "env": "DASHSCOPE_API_KEY",
        "default_model": "qwen3.8-max",
        "pip": "dashscope",
        "base_url": "https://ap-southeast-1.maas.qwencloudapi.com/api/v1",
    },
}

_print_lock = threading.Lock()


def log(msg):
    with _print_lock:
        print(msg, flush=True)


# ---------------------------------------------------------------- .env

def load_dotenv(*candidates):
    """同じディレクトリの .env を読む。既存の環境変数は上書きしない。"""
    here = os.path.dirname(os.path.abspath(__file__))
    paths = list(candidates) or [
        os.path.join(os.getcwd(), ".env"),
        os.path.join(here, ".env"),
    ]
    for path in paths:
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                os.environ.setdefault(k, v)
        return path
    return None


# 履歴を1通のテキストに畳んで渡すプロバイダの一覧。畳まないものは本物の会話の
# ターンとして渡す。既定は gemini だけ: q1〜pilot_a の gemini はすべて畳んだ形で、
# 他の3体は本物のターンで取っている（RUNBOOK「gemini だけ刺激の形が違っていた」）。
#   FJF_FLAT_HISTORY=""              → 4体とも本物のターン（gemini はステップ列）
#   FJF_FLAT_HISTORY="openai,qwen"   → openai と qwen を畳んだ形で
# どの形で取ったかは usage.path（<provider>_flat / gemini_steps / <provider>）と
# 試行レコードの history_format に残る。
FLAT_HISTORY = {p.strip() for p in
                os.environ.get("FJF_FLAT_HISTORY", "gemini").split(",") if p.strip()}
_bad = FLAT_HISTORY - {"gemini", "openai", "anthropic", "qwen"}
if _bad:
    raise SystemExit(f"FJF_FLAT_HISTORY に知らないプロバイダ: {sorted(_bad)}")


def history_format(provider):
    return "flat" if provider in FLAT_HISTORY else "native"


def fold_history(history, last):
    """履歴を1通に畳む。q1〜pilot_a の gemini が受け取っていた文字列と一字も同じ。"""
    parts = [f"【状況】\n{u}\n\n【あなたの回答】\n{a}" for u, a in history]
    parts.append(f"【状況】\n{last}")
    return "\n\n---\n\n".join(parts)


def make_client(provider, api_key):
    if provider == "gemini":
        from google import genai
        return genai.Client(api_key=api_key)
    if provider == "openai":
        from openai import OpenAI
        return OpenAI(api_key=api_key)
    if provider == "anthropic":
        from anthropic import Anthropic
        return Anthropic(api_key=api_key)
    if provider == "qwen":
        # dashscope はモジュール全体で設定を持つ。クライアント実体がないので
        # モジュールそのものを返し、api_key は呼び出しごとに渡す。
        import dashscope
        dashscope.base_http_api_url = PROVIDERS["qwen"]["base_url"]
        dashscope.api_key = api_key
        return dashscope
    raise ValueError(provider)


def clients_for(providers, models=None):
    """プロバイダ名のリストからクライアントとモデル名を作る。"""
    load_dotenv()
    out = {}
    for prov in providers:
        key = os.environ.get(PROVIDERS[prov]["env"])
        if not key:
            raise SystemExit(f"{PROVIDERS[prov]['env']} が見つかりません。")
        model = (models or {}).get(prov) or PROVIDERS[prov]["default_model"]
        out[prov] = (make_client(prov, key), model)
    return out


# ---------------------------------------------------------------- qwen 補助

def _qwen_msg(role, text):
    return {"role": role, "content": [{"text": text}]}


def _qwen_call(dashscope, model, messages, effort, max_tokens, usage=None):
    """MultiModalConversation を1回叩いて本文だけ返す。

    reasoning_effort と thinking_budget は同時に指定できない（エラーになる）。
    他プロバイダと揃えるため effort 側を使い、budget は渡さない。
    """
    r = dashscope.MultiModalConversation.call(
        api_key=dashscope.api_key,
        model=model,
        messages=messages,
        result_format="message",
        enable_thinking=True,
        reasoning_effort=effort,
        max_tokens=max_tokens,
    )
    if getattr(r, "status_code", 200) != 200:
        raise RuntimeError(
            f"dashscope {r.status_code} {getattr(r, 'code', '')}: "
            f"{getattr(r, 'message', '')}"
        )
    _put(usage, r, "qwen")
    content = r.output.choices[0].message.content
    if isinstance(content, str):
        return content
    parts = []
    for c in content:
        if isinstance(c, dict) and "text" in c:
            parts.append(c["text"])
        elif isinstance(c, str):
            parts.append(c)
    return "".join(parts)


# ---------------------------------------------------------------- 呼び出し

def _put(usage, r, path):
    """SDK の usage を一つの形に揃えて usage dict に入れる。

    呼び出し元がスレッドごとに自分の dict を渡すので競合しない。
    取れなかった項目は入れない（0 を捏造しない）。
    """
    if usage is None or r is None:
        return
    u = getattr(r, "usage", None) or getattr(r, "usage_metadata", None)
    if u is None:
        return
    g = (lambda k: getattr(u, k, None) if not isinstance(u, dict)
         else u.get(k))
    for dst, keys in (
            ("input", ("input_tokens", "prompt_tokens",
                       "prompt_token_count", "total_input_tokens")),
            ("output", ("output_tokens", "completion_tokens",
                        "candidates_token_count", "total_output_tokens")),
            ("cached", ("cached_input_tokens", "cache_read_input_tokens",
                        "cached_content_token_count", "total_cached_tokens")),
            ("cache_write", ("cache_creation_input_tokens",)),
            ("reasoning", ("reasoning_tokens", "thoughts_token_count",
                           "total_thought_tokens")),
    ):
        for k in keys:
            v = g(k)
            if v is not None:
                usage[dst] = v
                break
    # OpenAI は入れ子に置く
    d = g("input_tokens_details") or g("prompt_tokens_details")
    if d is not None:
        c = (d.get("cached_tokens") if isinstance(d, dict)
             else getattr(d, "cached_tokens", None))
        if c is not None:
            usage["cached"] = c
    d = g("output_tokens_details") or g("completion_tokens_details")
    if d is not None:
        c = (d.get("reasoning_tokens") if isinstance(d, dict)
             else getattr(d, "reasoning_tokens", None))
        if c is not None:
            usage["reasoning"] = c
    usage["path"] = path


def chat(provider, client, model, system_instruction, history, user_msg,
         effort="medium", max_tokens=32768, cache_prefix=None, usage=None,
         cache_key=None):
    """history = [(user, assistant), ...] に user_msg を足して1回呼ぶ。

    history が空なら単発の呼び出しになる。単発と多ターンで経路を分けない。

    cache_prefix は user_msg の前に置く不変部分である。モデルが見る文字列は
    cache_prefix + user_msg であり、指定しない場合と一字も変わらない。
    anthropic だけはここに明示のキャッシュ境界を置く必要があるため、
    別のブロックとして送る。他は接頭辞の自動キャッシュに任せる。

    usage に dict を渡すと、その呼び出しのトークン数を入れて返す。
    """
    pre = cache_prefix or ""
    flat = provider in FLAT_HISTORY
    if flat:
        # 畳んだ形は全プロバイダで同じ文字列にする。形の効果とモデルの効果を
        # 分けるには、刺激の文字列そのものがそろっていなければならない。
        user_msg = fold_history(history, pre + user_msg)
        history, pre = [], ""
    if provider == "anthropic":
        msgs = []
        for u, a in history:
            msgs.append({"role": "user", "content": u})
            msgs.append({"role": "assistant", "content": a})
        if pre:
            # 不変部分を別ブロックにして、その末尾にキャッシュ境界を置く。
            # 連結した文字列と同じものをモデルは読む。
            msgs.append({"role": "user", "content": [
                {"type": "text", "text": pre,
                 "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": user_msg},
            ]})
        else:
            if msgs:
                # 履歴の末尾に境界を置く。次のターンがここから乗る。
                last = msgs[-1]
                if isinstance(last["content"], str):
                    last["content"] = [
                        {"type": "text", "text": last["content"],
                         "cache_control": {"type": "ephemeral"}}]
            msgs.append({"role": "user", "content": user_msg})
        # max_tokens が大きいと SDK が非ストリーミングを拒否するため常に stream
        with client.messages.stream(
            model=model, max_tokens=max_tokens, system=system_instruction,
            messages=msgs, output_config={"effort": effort},
        ) as stream:
            m = stream.get_final_message()
        _put(usage, m, "anthropic_flat" if flat else "anthropic")
        return "".join(b.text for b in m.content
                       if getattr(b, "type", None) == "text")

    if provider == "openai":
        items = []
        for u, a in history:
            items.append({"role": "user", "content": u})
            items.append({"role": "assistant", "content": a})
        # GPT-6 世代は明示の境界が無いとキャッシュを使わない。
        # 境界を置かない限り cached_tokens は 0 のままになる。
        # prompt_cache_key は経路のヒントであって、スイッチではない。
        if pre:
            items.append({"role": "user", "content": [
                {"type": "input_text", "text": pre,
                 "prompt_cache_breakpoint": {"mode": "explicit"}},
                {"type": "input_text", "text": user_msg},
            ]})
        elif items:
            # 履歴がある場合は直前までを境界にする。次のターンがそこから乗る。
            last = items[-2] if len(items) >= 2 else None
            if last is not None and isinstance(last.get("content"), str):
                last["content"] = [
                    {"type": "input_text", "text": last["content"],
                     "prompt_cache_breakpoint": {"mode": "explicit"}}]
            items.append({"role": "user", "content": user_msg})
        else:
            items.append({"role": "user", "content": user_msg})
        kw = {}
        if cache_key:
            kw["prompt_cache_key"] = cache_key
        try:
            r = client.responses.create(
                model=model, instructions=system_instruction, input=items,
                reasoning={"effort": effort}, max_output_tokens=max_tokens,
                **kw,
            )
        except Exception as e:
            # 黙って落とすと、今度こそ原因が分からなくなる。必ず言う。
            flat = []
            for it in items:
                c = it["content"]
                flat.append({"role": it["role"],
                             "content": c if isinstance(c, str)
                             else "".join(x["text"] for x in c)})
            sys.stderr.write(
                f"[cache] 明示境界つきの送信が通らなかったので平文で再送する。"
                f"キャッシュは効かない。理由: {type(e).__name__}: {e}\n")
            r = client.responses.create(
                model=model, instructions=system_instruction, input=flat,
                reasoning={"effort": effort}, max_output_tokens=max_tokens,
            )
        _put(usage, r, "openai_flat" if flat else "openai")
        return r.output_text

    if provider == "qwen":
        msgs = [_qwen_msg("system", system_instruction)]
        for u, a in history:
            msgs.append(_qwen_msg("user", u))
            msgs.append(_qwen_msg("assistant", a))
        msgs.append(_qwen_msg("user", pre + user_msg))
        out = _qwen_call(client, model, msgs, effort, max_tokens, usage)
        if flat and usage is not None and "path" in usage:
            usage["path"] = "qwen_flat"
        return out

    if provider == "gemini":
        cfg = {"max_output_tokens": max_tokens, "thinking_level": effort}
        if flat:
            # user_msg は既に fold_history で畳んである（以前の gemini と同じ文字列）
            r = client.interactions.create(
                model=model, input=user_msg,
                system_instruction=system_instruction,
                generation_config=cfg,
            )
            _put(usage, r, "gemini_flat")
            return r.output_text
        # 本物のターン（2026-11-16 の診断 E1）。各要素は type を持つステップで、
        # 中身は type: text の部品のリスト。
        T = lambda s: [{"type": "text", "text": s}]
        steps = []
        for u, a in history:
            steps.append({"type": "user_input", "content": T(u)})
            steps.append({"type": "model_output", "content": T(a)})
        steps.append({"type": "user_input", "content": T(pre + user_msg)})
        r = client.interactions.create(
            model=model, input=steps,
            system_instruction=system_instruction,
            generation_config=cfg,
        )
        _put(usage, r, "gemini_steps")
        return r.output_text

    raise ValueError(provider)


def with_retry(fn, max_retries=7, give_up_on=(
        "invalid_api_key", "authentication", "unauthorized", "401",
        "invalid x-api-key", "permission_denied", "model_not_found",
        "does not exist", "invalid_request_error",
        "unpurchased", "accessdenied", "insufficient_quota",
        "billing", "credit balance")):
    """一時的な失敗は粘り、恒久的な失敗は即諦める。

    待ち時間は 1,2,4,8,16,32,64 秒（+ジッタ）で合計 2分強。クォータの
    絞りや 5xx は数十秒から数分続くことがあり、短い予算では越えられない。
    第2問の抽出で DashScope が 2分間 403 を返し、4回・計15秒の retry が
    全部その窓に収まって 94件が落ちた。

    逆に鍵の誤りやモデル名の誤り、課金が必要な拒否は何回待っても直らない。
    その種の文面を含むエラーは1回で諦める。2分 × 件数を無駄にしないため。
    第2問で DashScope が AccessDenied.Unpurchased を返したのは枠の上限で、
    一時的な絞りではなかった。人が課金するまで直らない種類である。
    """
    last = None
    for i in range(max_retries):
        try:
            return fn()
        except Exception as e:
            last = e
            msg = f"{type(e).__name__}: {e}".lower()
            if any(k in msg for k in give_up_on):
                hint = ""
                if any(k in msg for k in ("unpurchased", "accessdenied",
                                          "insufficient_quota", "billing",
                                          "credit balance")):
                    hint = "（課金・利用枠を確認してください）"
                raise RuntimeError(
                    f"恒久的な失敗と判断、retry しません{hint}: {e}")
            if i == max_retries - 1:
                break
            w = (2 ** i) + random.uniform(0, 1)
            log(f"    retry {i+1}/{max_retries} after {w:.1f}s — "
                f"{type(e).__name__}: {e}")
            time.sleep(w)
    raise RuntimeError(f"{max_retries}回とも失敗: {last}")
