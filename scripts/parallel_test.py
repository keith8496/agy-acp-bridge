#!/usr/bin/env python3
"""Fire N concurrent turns through 9router and report per-request outcome."""
import concurrent.futures as cf
import json
import os
import time
import urllib.request

KEY = os.environ.get("ROUTER_API_KEY", "")
URL = "http://127.0.0.1:20128/v1/chat/completions"


def one(i):
    body = json.dumps({
        "model": "agy-acp/gemini-3.8-flash-medium",
        "messages": [{"role": "user", "content": "balas satu kata: PARALEL"}],
        "max_tokens": 20,
    }).encode()
    req = urllib.request.Request(URL, data=body, method="POST", headers={
        "Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read())
        txt = d["choices"][0]["message"]["content"][:30]
        return f"#{i} {time.time()-t0:5.1f}s  {d.get('profile')}  {txt!r}"
    except Exception as e:
        return f"#{i} {time.time()-t0:5.1f}s  FAIL {type(e).__name__}: {str(e)[:90]}"


with cf.ThreadPoolExecutor(max_workers=4) as ex:
    for line in ex.map(one, range(1, 5)):
        print(line)
