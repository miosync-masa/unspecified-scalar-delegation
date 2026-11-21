#!/usr/bin/env python3
"""
Provider layer — confines API differences to this module

The experiment design lives in scenario_rescue.yaml, the instrument in codebook_v1.yaml, and execution in
fjf_run.py. This module only sends text and receives text.

Adding a provider touches only four places: PROVIDERS / make_client / invoke / chat.

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
        "default_model": "gpt-6-astra",   # effort="none" returns 400
        "pip": "openai",
    },
    "anthropic": {
        "env": "ANTHROPIC_API_KEY",
        "default_model": "claude-opus-5-5",
        "pip": "anthropic",
    },
    # qwen3.8-max is a model on the multimodal API side and does not work with
    # Generation.call. content is passed as a list [{"text": ...}].
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
    """Read .env in the same directory. Existing environment variables are not overwritten."""
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


# Providers that receive history folded into one text message. Others receive native
# conversation turns. Default is gemini only: gemini in q1-pilot_a always received the folded form,
# the other three native turns (ANALYSIS_PLANS section 2, "History-format discovery").
#   FJF_FLAT_HISTORY=""              -> native turns for all 4 (gemini as a step list)
#   FJF_FLAT_HISTORY="openai,qwen"   -> openai and qwen in folded form
# The form used is recorded in usage.path (<provider>_flat / gemini_steps / <provider>) and
# in history_format of each trial record.
FLAT_HISTORY = {p.strip() for p in
                os.environ.get("FJF_FLAT_HISTORY", "gemini").split(",") if p.strip()}
_bad = FLAT_HISTORY - {"gemini", "openai", "anthropic", "qwen"}
if _bad:
    raise SystemExit(f"FJF_FLAT_HISTORY names an unknown provider: {sorted(_bad)}")


def history_format(provider):
    return "flat" if provider in FLAT_HISTORY else "native"


def fold_history(history, last):
    """Fold history into one message. Character-identical to the string gemini received in q1-pilot_a."""
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
        # dashscope keeps configuration module-wide. There is no client instance, so
        # return the module itself and pass api_key on each call.
        import dashscope
        dashscope.base_http_api_url = PROVIDERS["qwen"]["base_url"]
        dashscope.api_key = api_key
        return dashscope
    raise ValueError(provider)


def clients_for(providers, models=None):
    """Build clients and model names from a list of provider names."""
    load_dotenv()
    out = {}
    for prov in providers:
        key = os.environ.get(PROVIDERS[prov]["env"])
        if not key:
            raise SystemExit(f"{PROVIDERS[prov]['env']} not found.")
        model = (models or {}).get(prov) or PROVIDERS[prov]["default_model"]
        out[prov] = (make_client(prov, key), model)
    return out


# ---------------------------------------------------------------- qwen helper

def _qwen_msg(role, text):
    return {"role": role, "content": [{"text": text}]}


def _qwen_call(dashscope, model, messages, effort, max_tokens, usage=None):
    """Call MultiModalConversation once and return only the text.

    reasoning_effort and thinking_budget cannot be set together (error).
    effort is used to match the other providers; budget is not passed.
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


# ---------------------------------------------------------------- calls

def _put(usage, r, path):
    """Normalize the SDK usage into one shape and put it in the usage dict.

    Each caller passes its own dict per thread, so there is no contention.
    Fields that cannot be obtained are omitted (no fabricated 0).
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
    # OpenAI nests it
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
    """Append user_msg to history = [(user, assistant), ...] and call once.

    An empty history is a single-turn call. Single and multi-turn share one path.

    cache_prefix is an invariant part placed before user_msg. The string the model sees is
    cache_prefix + user_msg, character-identical to the call without it.
    Only anthropic needs an explicit cache boundary here, so it is
    sent as a separate block. Others rely on automatic prefix caching.

    If a dict is passed as usage, the call's token counts are written into it.
    """
    pre = cache_prefix or ""
    flat = provider in FLAT_HISTORY
    if flat:
        # The folded form is the same string for every provider. Separating format effects from model
        # effects requires the stimulus strings themselves to be identical.
        user_msg = fold_history(history, pre + user_msg)
        history, pre = [], ""
    if provider == "anthropic":
        msgs = []
        for u, a in history:
            msgs.append({"role": "user", "content": u})
            msgs.append({"role": "assistant", "content": a})
        if pre:
            # Put the invariant part in its own block with the cache boundary at its end.
            # The model reads the same string as the concatenation.
            msgs.append({"role": "user", "content": [
                {"type": "text", "text": pre,
                 "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": user_msg},
            ]})
        else:
            if msgs:
                # Boundary at the end of the history; the next turn builds on it.
                last = msgs[-1]
                if isinstance(last["content"], str):
                    last["content"] = [
                        {"type": "text", "text": last["content"],
                         "cache_control": {"type": "ephemeral"}}]
            msgs.append({"role": "user", "content": user_msg})
        # With large max_tokens the SDK refuses non-streaming, so always stream
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
        # The GPT-6 generation does not use the cache without an explicit boundary;
        # cached_tokens stays 0 unless a boundary is set.
        # prompt_cache_key is a routing hint, not a switch.
        if pre:
            items.append({"role": "user", "content": [
                {"type": "input_text", "text": pre,
                 "prompt_cache_breakpoint": {"mode": "explicit"}},
                {"type": "input_text", "text": user_msg},
            ]})
        elif items:
            # With history, put the boundary just before the last turn; the next turn builds on it.
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
            # Dropping silently would hide the cause again. Always report it.
            flat = []
            for it in items:
                c = it["content"]
                flat.append({"role": it["role"],
                             "content": c if isinstance(c, str)
                             else "".join(x["text"] for x in c)})
            sys.stderr.write(
                f"[cache] sending with an explicit boundary failed; resending as plain text. "
                f"No caching. Reason: {type(e).__name__}: {e}\n")
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
            # user_msg is already folded by fold_history (the same string as earlier gemini)
            r = client.interactions.create(
                model=model, input=user_msg,
                system_instruction=system_instruction,
                generation_config=cfg,
            )
            _put(usage, r, "gemini_flat")
            return r.output_text
        # Native turns (diagnostic E1, 2026-11-16). Each element is a step with a type;
        # its content is a list of type: text parts.
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
    """Persist on transient failures; give up at once on permanent ones.

    Waits are 1,2,4,8,16,32,64 s (+jitter), a little over 2 minutes in total. Quota
    throttling and 5xx can last from tens of seconds to minutes, beyond a short budget.
    During q2 extraction DashScope returned 403 for 2 minutes; 4 retries totalling 15 s
    all fell inside that window and 94 records were lost.

    Conversely, a wrong key, a wrong model name or a refusal requiring payment never fixes itself.
    Errors containing such text are abandoned after one attempt, so as not to waste 2 minutes per record.
    The AccessDenied.Unpurchased DashScope returned in q2 was a quota limit,
    not temporary throttling: the kind that stays until someone pays.
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
                    hint = " (check billing / usage quota)"
                raise RuntimeError(
                    f"judged a permanent failure, not retrying{hint}: {e}")
            if i == max_retries - 1:
                break
            w = (2 ** i) + random.uniform(0, 1)
            log(f"    retry {i+1}/{max_retries} after {w:.1f}s — "
                f"{type(e).__name__}: {e}")
            time.sleep(w)
    raise RuntimeError(f"failed all {max_retries} attempts: {last}")
