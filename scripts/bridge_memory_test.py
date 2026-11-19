#!/usr/bin/env python3
"""End-to-end memory check through the bridge + session cache.

Turn 2 is served from the cached ACP session with only the tail prompt, so a
wrong answer here means the cache silently lost context.
"""
import json
import os
import urllib.request

URL = os.environ.get("BRIDGE_URL", "http://127.0.0.1:20130/v1/chat/completions")
MODEL = os.environ.get("AGY_MODEL", "gemini-3.8-flash-medium")


def call(messages):
    req = urllib.request.Request(URL, data=json.dumps(
        {"model": MODEL, "messages": messages}).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.loads(r.read())
    return (d["choices"][0]["message"].get("content") or "").strip()


msgs = [{"role": "user", "content": "My favourite number is 47. Remember it. Reply with OK."}]
print("turn1:", repr(call(msgs)[:60]))
msgs.append({"role": "assistant", "content": "OK."})
msgs.append({"role": "user", "content": "What is my favourite number? Answer with digits only."})
ans = call(msgs)
print("turn2:", repr(ans[:60]))
print("BRIDGE MEMORY OK" if "47" in ans else "BRIDGE MEMORY LOST")
