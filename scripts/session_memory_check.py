#!/usr/bin/env python3
"""Does a continued ACP session actually remember earlier prompts?

Two prompts in ONE session: plant a fact, then ask for it. If the answer is
not 47, session reuse would silently lose context and the cache idea is dead.
"""
import json
import os
import queue
import subprocess
import threading
import time

AGY = os.environ.get("AGY_BIN", "/root/.local/bin/agy")
PROFILE = os.environ.get("AGY_BENCH_PROFILE", "permainan10st")
MODEL = os.environ.get("AGY_BENCH_MODEL", "gemini-3.8-flash-medium")
WORKDIR = "/root/agy-bridge/work"

proc = subprocess.Popen(
    [AGY, "acp", "--sandbox", "--app-data-dir", "agy-" + PROFILE],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    cwd=WORKDIR, text=True, bufsize=1,
    env={**os.environ, "NO_COLOR": "1", "TERM": "dumb", "HOME": "/root"})
q = queue.Queue()
next_id = [100]


def send(o):
    proc.stdin.write(json.dumps(o) + "\n")
    proc.stdin.flush()


def reader():
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            m = json.loads(line)
        except Exception:
            continue
        if m.get("method") == "session/request_permission":
            opts = m.get("params", {}).get("options", []) or []
            rej = next((o.get("optionId") for o in opts
                        if str(o.get("kind", "")).startswith("reject")), None)
            send({"jsonrpc": "2.0", "id": m.get("id"),
                  "result": {"outcome": {"outcome": "selected", "optionId": rej}}
                  if rej else {"outcome": {"outcome": "cancelled"}}})
            continue
        if m.get("method"):
            if "id" in m:
                send({"jsonrpc": "2.0", "id": m["id"], "result": {}})
            q.put(("note", m))
        elif "id" in m:
            q.put(("resp", m))


threading.Thread(target=reader, daemon=True).start()


def rpc(method, params, timeout=120):
    mid = next_id[0]
    next_id[0] += 1
    t0 = time.time()
    send({"jsonrpc": "2.0", "id": mid, "method": method, "params": params})
    while time.time() - t0 < timeout:
        try:
            kind, m = q.get(timeout=1)
        except queue.Empty:
            continue
        if kind == "resp" and m.get("id") == mid:
            if "error" in m:
                raise RuntimeError(f"{method}: {m['error']}")
            return m.get("result", {})
    raise TimeoutError(method)


def turn(sid, text, timeout=180):
    mid = next_id[0]
    next_id[0] += 1
    t0 = time.time()
    send({"jsonrpc": "2.0", "id": mid, "method": "session/prompt",
          "params": {"sessionId": sid, "prompt": [{"type": "text", "text": text}]}})
    out = []
    first = None
    while time.time() - t0 < timeout:
        try:
            kind, m = q.get(timeout=1)
        except queue.Empty:
            continue
        if kind == "note" and m.get("method") == "session/update":
            u = m.get("params", {}).get("update", {})
            if u.get("sessionUpdate") == "agent_message_chunk" and first is None:
                first = time.time() - t0
            c = u.get("content") or {}
            if u.get("sessionUpdate") == "agent_message_chunk" and c.get("type") == "text":
                out.append(c.get("text") or "")
        elif kind == "resp" and m.get("id") == mid:
            return "".join(out), first, time.time() - t0
    raise TimeoutError("turn")


rpc("initialize", {"protocolVersion": 1,
                   "clientCapabilities": {"fs": {"readTextFile": False,
                                                 "writeTextFile": False},
                                          "terminal": False},
                   "clientInfo": {"name": "memcheck", "version": "0"}})
sid = rpc("session/new", {"cwd": WORKDIR, "mcpServers": []})["sessionId"]
rpc("session/set_model", {"sessionId": sid, "modelId": MODEL})

text1, f1, t1 = turn(sid, "My favourite number is 47. Remember it. Reply with OK.")
print(f"turn1 {t1:5.2f}s  {text1[:80]!r}")
text2, f2, t2 = turn(sid, "What is my favourite number? Answer with the digits only.")
print(f"turn2 {t2:5.2f}s  {text2[:80]!r}")
print("MEMORY OK" if "47" in text2 else "MEMORY LOST")
try:
    rpc("session/close", {"sessionId": sid}, 20)
except Exception as e:
    print("close:", e)
