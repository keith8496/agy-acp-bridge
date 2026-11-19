#!/usr/bin/env python3
"""Side-by-side behaviour audit: agy-acp bridge vs a normal OpenAI provider.

Same payloads, both models, so a difference is a bridge gap rather than a model
quirk. Each probe prints what it asked for and what came back.
"""
import base64
import io
import json
import os
import time
import urllib.error
import urllib.request

KEY = os.environ.get("ROUTER_API_KEY") or os.environ.get(
    "ROUTER_API_KEY", "")
URL = "http://127.0.0.1:20128/v1/chat/completions"
A = "agy-acp/gemini-3.8-flash-medium"
B = os.environ.get("REF_MODEL", "nous/qwen/qwen4-max:free")


def call(model, body_extra, timeout=180, stream=False):
    body = {"model": model, "stream": stream}
    body.update(body_extra)
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {KEY}",
                                          "Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if not stream:
                d = json.loads(r.read())
                ch = d["choices"][0]
                return {"t": time.time() - t0, "text": ch["message"].get("content") or "",
                        "tools": ch["message"].get("tool_calls"),
                        "finish": ch.get("finish_reason"), "usage": d.get("usage")}
            text, tools, finish = [], [], None
            for raw in r:
                s = raw.decode("utf-8", "replace").strip()
                if not s.startswith("data:"):
                    continue
                p = s[5:].strip()
                if p == "[DONE]":
                    break
                try:
                    d = json.loads(p)
                except Exception:
                    continue
                for ch in d.get("choices", []):
                    dl = ch.get("delta") or {}
                    if dl.get("content"):
                        text.append(dl["content"])
                    if dl.get("tool_calls"):
                        tools.append(dl["tool_calls"])
                    if ch.get("finish_reason"):
                        finish = ch["finish_reason"]
            return {"t": time.time() - t0, "text": "".join(text),
                    "tools": tools or None, "finish": finish, "usage": None}
    except urllib.error.HTTPError as e:
        return {"t": time.time() - t0, "err": f"HTTP {e.code}: {e.read().decode()[:120]}"}
    except Exception as e:
        return {"t": time.time() - t0, "err": f"{type(e).__name__}: {str(e)[:120]}"}


def png(word):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (420, 140), "white")
    ImageDraw.Draw(img).text((30, 50), word, fill="black")
    b = io.BytesIO()
    img.save(b, format="PNG")
    return base64.b64encode(b.getvalue()).decode()


WEATHER_TOOL = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get current weather for a city. Always use this for weather questions.",
        "parameters": {"type": "object",
                       "properties": {"city": {"type": "string", "description": "city name"}},
                       "required": ["city"]},
    },
}]

PROBES = [
    ("plain text", {"messages": [{"role": "user", "content": "Reply with exactly: PONG"}]}, False),
    ("stream", {"messages": [{"role": "user", "content": "Count 1 to 5, comma separated."}]}, True),
    ("system prompt obeyed", {"messages": [
        {"role": "system", "content": "You must answer in Indonesian only. Never use English."},
        {"role": "user", "content": "What is 2+2? One short sentence."}]}, False),
    ("multi-turn memory", {"messages": [
        {"role": "user", "content": "My favourite number is 47. Remember it."},
        {"role": "assistant", "content": "Noted, 47."},
        {"role": "user", "content": "What is my favourite number? Answer with the digits only."}]}, False),
    ("function calling", {"messages": [
        {"role": "user", "content": "What is the weather in Jakarta right now?"}],
        "tools": WEATHER_TOOL, "tool_choice": "auto"}, False),
    ("json mode", {"messages": [
        {"role": "user", "content": 'Return JSON only: {"city":"Jakarta","temp":30}'}],
        "response_format": {"type": "json_object"}}, False),
    ("max_tokens=8", {"messages": [
        {"role": "user", "content": "Write a 300 word essay about the sea."}],
        "max_tokens": 8}, False),
    ("stop sequence", {"messages": [
        {"role": "user", "content": "Count: one two three four five"}],
        "stop": ["three"]}, False),
]


def show(name, res):
    if "err" in res:
        return f"    {name:22} ERROR {res['err']}"
    txt = (res["text"] or "").replace("\n", " ")[:70]
    extra = ""
    if res.get("tools"):
        extra = f"  tool_calls={len(res['tools'])}"
    return f"    {name:22} {res['t']:5.1f}s finish={str(res['finish']):11} {txt!r}{extra}"


for label, model in (("AGY-ACP", A), ("REFERENCE " + B, B)):
    print(f"\n=== {label} ===")
    for name, extra, stream in PROBES:
        print(show(name, call(model, extra, stream=stream)))

print("\n=== vision ===")
b64 = png("KIWI88")
vbody = {"messages": [{"role": "user", "content": [
    {"type": "text", "text": "What exact text is in this image? Just that text."},
    {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}}]}]}
for label, model in (("AGY-ACP", A), ("REFERENCE", B)):
    print(show(label, call(model, vbody)))
