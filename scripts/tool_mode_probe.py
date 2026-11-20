#!/usr/bin/env python3
"""Which CLI variant stops the agent from reaching for its own tools?

Spawns `agy acp` with extra args, sends one tool-contract prompt, and reports
the session/update kinds seen plus whether a tool_call block came back.
"""
import importlib.util
import json
import os
import queue
import subprocess
import sys
import threading
import time

spec = importlib.util.spec_from_file_location("br", "/root/agy-bridge/bridge.py")
br = importlib.util.module_from_spec(spec)
sys.modules["br"] = br
spec.loader.exec_module(br)

EXTRA = sys.argv[1:]
TOOLS = [{"type": "function", "function": {
    "name": "terminal", "description": "Run a shell command and return its output.",
    "parameters": {"type": "object", "properties": {"command": {"type": "string"}},
                   "required": ["command"]}}}]
_USER = ("[System instruction]\nYou are an agent with tools.\n\n"
         "User: cek saldo: jalankan /usr/local/lib/hermes-agent/venv/bin/python "
         "/root/kkn_bot_helper.py saldo")
PROMPT = (br.tools_prompt(TOOLS) + "\n\n" + _USER
          if os.environ.get("PROBE_POSITION") == "prepend" else _USER + br.tools_prompt(TOOLS))

args = ["/root/.local/bin/agy", "acp", "--sandbox", "--app-data-dir", "agy-permainan10st"] + EXTRA
proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, cwd="/root/agy-bridge/work", text=True,
                        bufsize=1, env={**os.environ, "NO_COLOR": "1", "TERM": "dumb", "HOME": "/root"})
q = queue.Queue()
nid = [100]


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
            q.put(("note", m))
            continue
        if m.get("method"):
            if "id" in m:
                send({"jsonrpc": "2.0", "id": m["id"], "result": {}})
            q.put(("note", m))
        elif "id" in m:
            q.put(("resp", m))


threading.Thread(target=reader, daemon=True).start()


def rpc(method, params, timeout=90):
    mid = nid[0]
    nid[0] += 1
    t0 = time.time()
    send({"jsonrpc": "2.0", "id": mid, "method": method, "params": params})
    while time.time() - t0 < timeout:
        try:
            k, m = q.get(timeout=1)
        except queue.Empty:
            continue
        if k == "resp" and m.get("id") == mid:
            if "error" in m:
                raise RuntimeError(f"{method}: {m['error']}")
            return m.get("result", {})
    raise TimeoutError(method)


try:
    rpc("initialize", {"protocolVersion": 1,
                       "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False},
                                              "terminal": False},
                       "clientInfo": {"name": "probe", "version": "0"}})
    sid = rpc("session/new", {"cwd": "/root/agy-bridge/work", "mcpServers": []})["sessionId"]
    rpc("session/set_model", {"sessionId": sid, "modelId": "gemini-3.8-flash-medium"})
    mid = nid[0]
    nid[0] += 1
    t0 = time.time()
    send({"jsonrpc": "2.0", "id": mid, "method": "session/prompt",
          "params": {"sessionId": sid, "prompt": [{"type": "text", "text": PROMPT}]}})
    kinds, text, native = {}, [], []
    while time.time() - t0 < 150:
        try:
            k, m = q.get(timeout=1)
        except queue.Empty:
            continue
        if k == "note" and m.get("method") == "session/update":
            u = m.get("params", {}).get("update", {})
            kn = u.get("sessionUpdate")
            kinds[kn] = kinds.get(kn, 0) + 1
            if kn in ("tool_call", "tool_call_update"):
                native.append(u.get("name") or u.get("title"))
            c = u.get("content") or {}
            if kn == "agent_message_chunk" and c.get("type") == "text":
                text.append(c.get("text") or "")
        elif k == "resp" and m.get("id") == mid:
            break
    body = "".join(text)
    calls, cleaned = br.extract_tool_calls(body, {"terminal"})
    print(f"ARGS {EXTRA}")
    print(f"  {time.time()-t0:.1f}s updates={kinds}")
    print(f"  native_tools={sorted(set(native))}")
    print(f"  contract_calls={len(calls)} text={cleaned[:80]!r}")
except Exception as e:
    print(f"ARGS {EXTRA} -> ERROR {type(e).__name__}: {str(e)[:160]}")
finally:
    proc.kill()
