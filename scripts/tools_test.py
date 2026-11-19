#!/usr/bin/env python3
"""Reproduce the empty-content case: a client payload with a system prompt and tools."""
import json
import os
import sys
import time
import urllib.request

KEY = os.environ.get("ROUTER_API_KEY", "")
URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:20128/v1/chat/completions"
MODEL = sys.argv[2] if len(sys.argv) > 2 else "agy-acp/gemini-3.8-flash-medium"

TOOLS = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the weather for a city",
        "parameters": {"type": "object",
                       "properties": {"city": {"type": "string"}},
                       "required": ["city"]},
    },
}]

body = {
    "model": MODEL,
    "messages": [
        {"role": "system", "content": "You are a terse assistant. Answer in one short line."},
        {"role": "user", "content": "What is the weather in Jakarta? Use the tool if you need to."},
    ],
    "tools": TOOLS,
    "max_tokens": 200,
}

req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST",
                             headers={"Authorization": f"Bearer {KEY}",
                                      "Content-Type": "application/json"})
t0 = time.time()
with urllib.request.urlopen(req, timeout=180) as r:
    d = json.loads(r.read())
msg = d["choices"][0]["message"]
print(f"{time.time()-t0:.1f}s  profile={d.get('profile')}")
print("content:", repr(msg.get("content"))[:200])
print("tool_calls:", json.dumps(msg.get("tool_calls"))[:200])
print("finish:", d["choices"][0].get("finish_reason"))
