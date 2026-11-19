#!/usr/bin/env python3
"""Heavy agent-style payload: long system prompt + tools + stream, like a real client."""
import json
import os
import time
import urllib.request

KEY = os.environ.get("ROUTER_API_KEY", "")
URL = "http://127.0.0.1:20128/v1/chat/completions"

SYSTEM = ("You are a precise engineering assistant operating inside a tool-using agent. "
          "You have access to tools. Always think before acting. "
          "When a task requires information you do not have, call a tool rather than guessing. ") * 60

TOOLS = [{
    "type": "function",
    "function": {
        "name": f"tool_{i}",
        "description": "Read a file from the workspace",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"}},
                       "required": ["path"]},
    },
} for i in range(12)]

body = {
    "model": "agy-acp/gemini-3.8-flash-medium",
    "messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "List the files in the current directory."},
    ],
    "tools": TOOLS,
    "stream": True,
    "max_tokens": 1024,
}

req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST",
                             headers={"Authorization": f"Bearer {KEY}",
                                      "Content-Type": "application/json"})
t0 = time.time()
text, tools_seen, finish = [], [], None
with urllib.request.urlopen(req, timeout=240) as r:
    for raw in r:
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            d = json.loads(payload)
        except Exception:
            continue
        for ch in d.get("choices", []):
            delta = ch.get("delta") or {}
            if delta.get("content"):
                text.append(delta["content"])
            if delta.get("tool_calls"):
                tools_seen.append(delta["tool_calls"])
            if ch.get("finish_reason"):
                finish = ch["finish_reason"]

print(f"{time.time()-t0:.1f}s  finish={finish}")
print("text:", repr("".join(text))[:200])
print("tool_calls:", len(tools_seen))
