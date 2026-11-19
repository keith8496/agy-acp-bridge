"""Pull the full VALIDATION_REQUIRED body (with untruncated validation_url)
for one agy profile, using the token that profile stored."""
import json
import sys
import urllib.error
import urllib.request

PROFILE = sys.argv[1] if len(sys.argv) > 1 else "rasyagame06"
TOK = f"/root/.gemini/agy-{PROFILE}/antigravity-oauth-token"

d = json.load(open(TOK))
tok = d.get("token") or {}
at = tok.get("access_token") or tok.get("accessToken")
print("email:", d.get("id_token_email"))
print("token keys:", list(tok.keys())[:8])

URL = "https://daily-cloudcode-pa.googleapis.com/v1internal:retrieveUserQuotaSummary"
req = urllib.request.Request(
    URL, data=b"{}", method="POST",
    headers={
        "Authorization": f"Bearer {at}",
        "Content-Type": "application/json",
        "User-Agent": "antigravity/cli/1.5.12 linux/amd64",
    })
try:
    with urllib.request.urlopen(req, timeout=25) as r:
        print("HTTP", r.status, r.read().decode()[:500])
except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8", "replace")
    print("HTTP", e.code)
    try:
        j = json.loads(body)
        err = j.get("error", {})
        print("message:", err.get("message"))
        for det in err.get("details", []):
            if "validation_url" in str(det):
                md = det.get("metadata", {})
                print()
                print("VALIDATION_URL:")
                print(md.get("validation_url"))
        if not any("validation_url" in str(x) for x in err.get("details", [])):
            print(body[:1500])
    except Exception:
        print(body[:1500])
except Exception as e:
    print("ERR", type(e).__name__, e)
