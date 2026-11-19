#!/usr/bin/env python3
"""Prove a dropped client no longer leaks the worker lock.

1. open a streaming turn, read the first chunk, then hang up mid-answer
2. immediately fire a normal turn — it must succeed, not queue until timeout
"""
import http.client
import json
import time

HOST, PORT = "127.0.0.1", 20130
BODY = json.dumps({
    "model": "gemini-3.8-flash-medium",
    "messages": [{"role": "user", "content": "hitung 1 sampai 20 perlahan"}],
    "stream": True,
})


def drop_midstream():
    c = http.client.HTTPConnection(HOST, PORT, timeout=60)
    c.request("POST", "/v1/chat/completions", body=BODY,
              headers={"Content-Type": "application/json"})
    r = c.getresponse()
    got = 0
    while got < 1:
        line = r.readline()
        if not line:
            break
        if line.startswith(b"data:") and b'"content"' in line:
            got += 1
    c.close()          # hang up while the turn is still running
    return got


def normal_turn():
    c = http.client.HTTPConnection(HOST, PORT, timeout=90)
    c.request("POST", "/v1/chat/completions",
              body=json.dumps({"model": "gemini-3.8-flash-medium",
                               "messages": [{"role": "user", "content": "balas: SEHAT"}]}),
              headers={"Content-Type": "application/json"})
    t0 = time.time()
    r = c.getresponse()
    d = json.loads(r.read())
    c.close()
    return time.time() - t0, d["choices"][0]["message"]["content"][:30]


print("chunks read before hanging up:", drop_midstream())
time.sleep(1)
dt, txt = normal_turn()
print(f"turn right after the drop: {dt:.1f}s -> {txt!r}")
print("PASS" if dt < 45 else "FAIL (lock likely still held)")
