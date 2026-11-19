#!/usr/bin/env python3
"""Latency probe: three sequential turns of ONE growing conversation.

Session reuse only pays off from turn 2 onward, so measure per turn.
Baseline (no cache): every turn creates a fresh ACP session.
Cached: turn 2/3 should only carry the new tail.
"""
import json
import os
import time
import urllib.request

URL = os.environ.get("BRIDGE_URL", "http://127.0.0.1:20130/v1/chat/completions")
MODEL = os.environ.get("AGY_MODEL", "gemini-3.8-flash-medium")
TOKEN = os.environ.get("BRIDGE_TOKEN", "")


def call(messages, stream=False, timeout=180):
    body = {"model": MODEL, "messages": messages, "stream": stream}
    headers = {"Content-Type": "application/json"}
    if TOKEN:
        headers["Authorization"] = "Bearer " + TOKEN
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST",
                                 headers=headers)
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read())
    dt = time.time() - t0
    ch = d["choices"][0]
    return dt, (ch["message"].get("content") or "").strip()


def main():
    msgs = [{"role": "system", "content": "Answer in one short word."}]
    questions = ["Say: satu", "Say: dua", "Say: tiga"]
    print(f"model={MODEL} url={URL}")
    # warm-up, not part of the conversation; keeps worker-spawn out of turn 1
    try:
        call([{"role": "user", "content": "Reply with exactly: WARM"}])
        print("warm-up ok")
    except Exception as e:
        print(f"warm-up failed: {e}")
    for i, q in enumerate(questions, 1):
        msgs.append({"role": "user", "content": q})
        try:
            dt, text = call(msgs)
            print(f"turn {i}: {dt:5.2f}s  {text[:60]!r}")
        except Exception as e:
            print(f"turn {i}: ERROR {e}")
            return
        msgs.append({"role": "assistant", "content": text})


if __name__ == "__main__":
    main()
