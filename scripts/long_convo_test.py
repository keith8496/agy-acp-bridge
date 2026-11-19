#!/usr/bin/env python3
"""Long conversation through the bridge: what the session cache actually saves.

Each turn reports elapsed time and the size of the FULL history the client
sends. Compare that with `sent=NB` in /var/log/agy-bridge.log: a cache hit only
carries the tail, so sent stays small while the history keeps growing.
"""
import json
import os
import time
import urllib.request

URL = os.environ.get("BRIDGE_URL", "http://127.0.0.1:20130/v1/chat/completions")
MODEL = os.environ.get("AGY_MODEL", "gemini-3.8-flash-medium")
TURNS = int(os.environ.get("TURNS", "5"))

SYSTEM = ("You are a precise engineering assistant. Answer in one short sentence. "
          + ("Background context line kept for realism. " * 160))
FILLER = ("Here is some project context. The service binds to a local port and stores "
          "state in a small sqlite file. Logs rotate daily. " * 14)


def call(messages):
    body = {"model": MODEL, "messages": messages, "stream": False}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=240) as r:
        d = json.loads(r.read())
    return time.time() - t0, (d["choices"][0]["message"].get("content") or "").strip()


def hist_chars(msgs):
    return sum(len(str(m.get("content") or "")) for m in msgs)


msgs = [{"role": "system", "content": SYSTEM}]
print(f"system={len(SYSTEM)}B  model={MODEL}")
for i in range(1, TURNS + 1):
    msgs.append({"role": "user", "content": f"Turn {i}. {FILLER} Answer with just: OK{i}."})
    try:
        dt, text = call(msgs)
    except Exception as e:
        print(f"turn {i}: ERROR {e}")
        break
    print(f"turn {i}: {dt:5.2f}s  history={hist_chars(msgs):6}B  ans={text[:30]!r}")
    msgs.append({"role": "assistant", "content": text})
