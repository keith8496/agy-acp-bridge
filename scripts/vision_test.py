#!/usr/bin/env python3
"""Vision regression: send a real image and check the model actually reads it."""
import base64
import io
import json
import os
import sys
import time
import urllib.request

KEY = os.environ.get("ROUTER_API_KEY", "")
URL = os.environ.get("VISION_URL", "http://127.0.0.1:20128/v1/chat/completions")
MODEL = os.environ.get("VISION_MODEL", "agy-acp/gemini-3.8-flash-medium")

WORD = "ZEBRA47"


def make_png():
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (420, 140), "white")
    d = ImageDraw.Draw(img)
    d.text((30, 50), WORD, fill="black")
    d.rectangle([10, 10, 410, 130], outline="black", width=3)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


b64 = make_png()
body = {
    "model": MODEL,
    "messages": [{
        "role": "user",
        "content": [
            {"type": "text", "text": "What exact text is written in this image? Answer with just that text."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ],
    }],
}
req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST",
                             headers={"Authorization": f"Bearer {KEY}",
                                      "Content-Type": "application/json"})
t0 = time.time()
with urllib.request.urlopen(req, timeout=240) as r:
    d = json.loads(r.read())
txt = d["choices"][0]["message"]["content"] or ""
print(f"{time.time()-t0:.1f}s  profile={d.get('profile')}")
print("answer:", repr(txt)[:200])
print("PASS" if WORD in txt.upper() else "FAIL — image not seen")
