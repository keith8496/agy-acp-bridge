#!/usr/bin/env python3
"""Reproduce the raw-JSON leak: caller tool named `terminal`, agent-style ask."""
import json
import sys
import time
import urllib.request

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:20130/v1/chat/completions"
STREAM = len(sys.argv) > 2 and sys.argv[2] == "stream"

TOOLS = [{
    "type": "function",
    "function": {
        "name": "terminal",
        "description": "Run a shell command and return its output.",
        "parameters": {"type": "object",
                       "properties": {"command": {"type": "string"}},
                       "required": ["command"]},
    },
}]
body = {
    "model": "gemini-3.8-flash-medium",
    "messages": [
        {"role": "system", "content": "You are an agent with tools. Use them when a task needs real data."},
        {"role": "user", "content": "cek saldo: jalankan /usr/local/lib/hermes-agent/venv/bin/python /root/kkn_bot_helper.py saldo"},
    ],
    "tools": TOOLS,
    "stream": STREAM,
}
req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST",
                             headers={"Content-Type": "application/json"})
t0 = time.time()
with urllib.request.urlopen(req, timeout=240) as r:
    if not STREAM:
        d = json.loads(r.read())
        ch = d["choices"][0]
        print(f"{time.time()-t0:.1f}s finish={ch.get('finish_reason')}")
        print("content:", repr(ch["message"].get("content"))[:600])
        print("tool_calls:", json.dumps(ch["message"].get("tool_calls"), ensure_ascii=False)[:600])
    else:
        text, tc = [], []
        for raw in r:
            s = raw.decode().strip()
            if not s.startswith("data:"):
                continue
            p = s[5:].strip()
            if p == "[DONE]":
                break
            d = json.loads(p)
            for ch in d.get("choices", []):
                dl = ch.get("delta") or {}
                if dl.get("content"):
                    text.append(dl["content"])
                if dl.get("tool_calls"):
                    tc.append(dl["tool_calls"])
        print(f"{time.time()-t0:.1f}s")
        print("content:", repr("".join(text))[:600])
        print("tool_calls:", json.dumps(tc, ensure_ascii=False)[:600])
