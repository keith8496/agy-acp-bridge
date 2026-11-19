"""Classify every authenticated agy profile with one real turn, and pull the
VALIDATION_REQUIRED link for any that Google wants verified.

Read-only apart from one tiny prompt per profile. Writes profile-state.json
through the bridge's /admin/test, so the pool picks up the result.
"""
import glob
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

BRIDGE = "http://127.0.0.1:20130"
TOKEN = "CHANGE_ME"
MODEL = "gemini-3.8-flash-medium"


def post(path, payload, timeout=180):
    req = urllib.request.Request(
        f"{BRIDGE}{path}?t={TOKEN}",
        data=json.dumps(payload).encode(),
        method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def profiles():
    with urllib.request.urlopen(f"{BRIDGE}/admin/profiles?t={TOKEN}", timeout=20) as r:
        return [p["name"] for p in json.loads(r.read())["profiles"]]


def validation_url(profile):
    tok_path = f"/root/.gemini/agy-{profile}/antigravity-oauth-token"
    if not os.path.isfile(tok_path):
        return None
    at = json.load(open(tok_path))["token"]["access_token"]
    req = urllib.request.Request(
        "https://daily-cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary",
        data=b"{}", method="POST",
        headers={"Authorization": f"Bearer {at}", "Content-Type": "application/json",
                 "User-Agent": "antigravity/cli/1.5.12 linux/amd64"})
    try:
        urllib.request.urlopen(req, timeout=25).read()
        return None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            for det in json.loads(body)["error"].get("details", []):
                md = det.get("metadata") or {}
                if md.get("validation_url"):
                    return md["validation_url"]
        except Exception:
            pass
        return "HTTP %s (no validation_url)" % e.code
    except Exception as e:
        return f"err {e}"


names = [n for n in profiles() if not n.startswith("__legacy__")]
results = []
for n in names:
    try:
        r = post("/admin/test", {"profile": n, "model": MODEL})
        st = r.get("status") or ("ok" if r.get("ok") else "error")
        detail = (r.get("detail") or "").strip()[:90]
    except Exception as e:
        st, detail = "error", str(e)[:90]
    row = {"profile": n, "status": st, "detail": detail}
    if st == "verify":
        row["validation_url"] = validation_url(n)
    results.append(row)
    print(f"{n:20} {st:8} {detail}")
    if row.get("validation_url"):
        print(f"{'':20} -> {row['validation_url']}")

with open("/root/agy-bridge/liveness.json", "w") as f:
    json.dump(results, f, indent=2)
print("\nwritten /root/agy-bridge/liveness.json")
