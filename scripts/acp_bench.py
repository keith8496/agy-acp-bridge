#!/usr/bin/env python3
"""Micro-bench: cost of a FRESH ACP session vs continuing an existing one.

Talks straight to `agy acp` (no bridge, no 9r) so the numbers are the CLI's
own. Phase A mimics the current bridge (session/new per request). Phase B
mimics the planned cache (one session, one prompt per turn).

    python3 acp_bench.py [turns]
"""
import json
import os
import queue
import subprocess
import sys
import threading
import time

AGY = os.environ.get("AGY_BIN", "/root/.local/bin/agy")
PROFILE = os.environ.get("AGY_BENCH_PROFILE", "permainan10st")
MODEL = os.environ.get("AGY_BENCH_MODEL", "gemini-3.8-flash-medium")
WORKDIR = "/root/agy-bridge/work"
PROMPTS = ["Say: satu", "Say: dua", "Say: tiga", "Say: empat", "Say: lima"]


class Acp:
    def __init__(self):
        args = [AGY, "acp", "--sandbox"]
        if PROFILE != "default":
            args += ["--app-data-dir", "agy-" + PROFILE]
        self.proc = subprocess.Popen(
            args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, cwd=WORKDIR, text=True, bufsize=1,
            env={**os.environ, "NO_COLOR": "1", "TERM": "dumb",
                 "HOME": os.environ.get("HOME", "/root")})
        self.q = queue.Queue()
        self.next_id = 100
        self.done = {}
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception:
                continue
            method = msg.get("method")
            if method == "session/request_permission":
                opts = msg.get("params", {}).get("options", []) or []
                reject = next((o.get("optionId") for o in opts
                               if str(o.get("kind", "")).startswith("reject")), None)
                self._send({"jsonrpc": "2.0", "id": msg.get("id"),
                            "result": {"outcome": {"outcome": "selected",
                                                   "optionId": reject}}
                            if reject else {"outcome": {"outcome": "cancelled"}}})
                continue
            if method:
                if "id" in msg:
                    self._send({"jsonrpc": "2.0", "id": msg["id"], "result": {}})
                self.q.put(("note", msg))
                continue
            if "id" in msg:
                self.q.put(("resp", msg))

    def _send(self, obj):
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()

    def rpc(self, method, params, timeout=120):
        mid = self.next_id
        self.next_id += 1
        t0 = time.time()
        self._send({"jsonrpc": "2.0", "id": mid, "method": method, "params": params})
        while True:
            left = timeout - (time.time() - t0)
            if left <= 0:
                raise TimeoutError(method)
            try:
                kind, msg = self.q.get(timeout=left)
            except queue.Empty:
                raise TimeoutError(method)
            if kind == "resp" and msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def prompt(self, sid, text, timeout=180):
        """Send one prompt, wait for the response. Returns (first_chunk_s, total_s)."""
        mid = self.next_id
        self.next_id += 1
        t0 = time.time()
        first = None
        self._send({"jsonrpc": "2.0", "id": mid, "method": "session/prompt",
                    "params": {"sessionId": sid,
                               "prompt": [{"type": "text", "text": text}]}})
        while True:
            left = timeout - (time.time() - t0)
            if left <= 0:
                raise TimeoutError("turn")
            try:
                kind, msg = self.q.get(timeout=min(left, 1.0))
            except queue.Empty:
                continue
            if kind == "note" and msg.get("method") == "session/update":
                u = msg.get("params", {}).get("update", {})
                if u.get("sessionUpdate") == "agent_message_chunk" and first is None:
                    first = time.time() - t0
            if kind == "resp" and msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(str(msg["error"]))
                return first, time.time() - t0


def main():
    turns = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    heavy = len(sys.argv) > 2 and sys.argv[2] == "heavy"
    sys_prompt = ("You are a careful assistant. Answer in one short word only. "
                  + ("Context padding sentence kept for realism. " * 140)) if heavy else \
                 "Answer in one short word."
    user_texts = []
    for i in range(turns):
        body = f"Question {i+1}. " + ("Filler detail line that a real client would send. " * (40 if heavy else 0))
        user_texts.append(body + f" Reply with: {PROMPTS[i % len(PROMPTS)].split(': ')[1]}")

    a = Acp()
    t_init = time.time()
    a.rpc("initialize", {"protocolVersion": 1,
                         "clientCapabilities": {"fs": {"readTextFile": False,
                                                       "writeTextFile": False},
                                                "terminal": False},
                         "clientInfo": {"name": "acp-bench", "version": "0"}},
          timeout=120)
    print(f"initialize: {time.time() - t_init:5.2f}s   profile={PROFILE} model={MODEL}"
          f"  heavy={heavy}  sys_chars={len(sys_prompt)}")

    history = [{"role": "system", "content": sys_prompt}]

    def flat(msgs):
        out = []
        for m in msgs:
            if m["role"] == "system":
                out.append("[System instruction]\n" + m["content"])
            elif m["role"] == "assistant":
                out.append("Assistant: " + m["content"])
            else:
                out.append("User: " + m["content"])
        return "\n\n".join(out)

    print("\nphase A — fresh session per turn (current bridge)")
    a_tot = []
    for i in range(turns):
        history.append({"role": "user", "content": user_texts[i]})
        t0 = time.time()
        sid = a.rpc("session/new", {"cwd": WORKDIR, "mcpServers": []}, 60)["sessionId"]
        t_new = time.time() - t0
        a.rpc("session/set_model", {"sessionId": sid, "modelId": MODEL}, 30)
        first, total = a.prompt(sid, flat(history))
        a_tot.append(total)
        history.append({"role": "assistant", "content": PROMPTS[i % len(PROMPTS)].split(': ')[1]})
        print(f"  turn {i+1}: session/new {t_new*1000:6.0f}ms  first {first or -1:5.2f}s"
              f"  total {total:5.2f}s  prompt_chars={len(flat(history))}")
        try:
            a.rpc("session/close", {"sessionId": sid}, 20)
        except Exception as e:
            print(f"    close failed: {e}")

    print("\nphase B — one session, tail prompts (planned cache)")
    sid = a.rpc("session/new", {"cwd": WORKDIR, "mcpServers": []}, 60)["sessionId"]
    a.rpc("session/set_model", {"sessionId": sid, "modelId": MODEL}, 30)
    b_tot = []
    b_hist = [{"role": "system", "content": sys_prompt}]
    for i in range(turns):
        b_hist.append({"role": "user", "content": user_texts[i]})
        tail = flat(b_hist[1:]) if i == 0 else ("User: " + user_texts[i]) if False else flat(
            [{"role": "user", "content": user_texts[i]}])
        first, total = a.prompt(sid, tail if i else flat(b_hist))
        b_tot.append(total)
        b_hist.append({"role": "assistant", "content": PROMPTS[i % len(PROMPTS)].split(': ')[1]})
        print(f"  turn {i+1}: first {first or -1:5.2f}s  total {total:5.2f}s"
              f"  prompt_chars={len(tail) if i else len(flat(b_hist))}")
    try:
        a.rpc("session/close", {"sessionId": sid}, 20)
    except Exception as e:
        print(f"  close failed: {e}")

    def med(x):
        s = sorted(x)
        return s[len(s) // 2] if s else 0
    print(f"\nmedian total — fresh {med(a_tot):.2f}s | reuse {med(b_tot):.2f}s")


if __name__ == "__main__":
    main()
