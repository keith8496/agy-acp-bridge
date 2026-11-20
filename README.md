# agy-acp-bridge

Use Google Antigravity models from any OpenAI-compatible client **without replaying an
OAuth token through a third-party HTTP stack** — the thing that gets accounts flagged.

The bridge speaks OpenAI `/v1/chat/completions` on the outside and drives the **official
`agy` CLI** over [Agent Client Protocol](https://agentclientprotocol.com) (JSON-RPC 2.0
over stdio) on the inside. Every request originates from Google's own binary, with its
own credentials and its own harness fingerprint — the same path Zed, JetBrains and other
ACP editors use, and the one Google documents at
[antigravity.google/docs/cli/acp](https://antigravity.google/docs/cli/acp).

```
your client ──HTTP──> bridge :20130 ──ACP/stdio──> agy acp ──> Google
                        (OpenAI in)                (official binary)
```

Optional: a patch that adds an **Antigravity ACP** provider card to
[9router](https://github.com/serenhope/9router), with an Accounts panel so you can add
Google accounts and test models from the dashboard instead of a terminal.

---

## Why this exists

Antigravity accounts connected through routers that store the OAuth token and call
`cloudcode-pa.googleapis.com` with their own HTTP client started returning:

> ⚠ This service has been disabled in this account for violation of Terms of Service.

The signal Google reacts to is **the harness, not the IP**. A proxy pool changes the
source address and leaves the fingerprint identical. Driving the real `agy` binary
removes the foreign-harness signal entirely.

**This makes traffic look legitimate. It does not make an account immortal.** One account
hammered 24/7 from a datacenter IP is still an unusual pattern. Use a primary + fallback,
not a round-robin across every account you own.

---

## Three account states — and why metadata probes lie

| status | meaning | action |
|---|---|---|
| `ok` | a real turn returned text | usable, enters rotation |
| `verify` | `403 VALIDATION_REQUIRED` — "Verify your account to continue" | **not banned.** Open the `validation_url` while signed in as that account, then re-test |
| `tos` | "service disabled for violation of ToS" | dead, needs an appeal |

`fetchAvailableModels` returns **200 with a full model list even for banned accounts**.
Only a real inference turn reveals the truth. Never trust a quota/metadata call as a
liveness check — `scripts/classify_all.py` does it properly and pulls the verification
link for anything in `verify`.

---

## Install

### 1. Antigravity CLI

```bash
curl -fsSL https://antigravity.google/cli/install.sh | bash   # -> ~/.local/bin/agy
agy acp --help                                                # confirm ACP support
```

### 2. Bridge

```bash
git clone https://github.com/rassyy/agy-acp-bridge
cd agy-acp-bridge
sudo install -m 644 agy-bridge.service /etc/systemd/system/agy-bridge.service
# edit the unit: set AGY_ADMIN_TOKEN to your own value
sudo systemctl daemon-reload
sudo systemctl enable --now agy-bridge
curl -s http://127.0.0.1:20130/health
```

Stdlib only — no pip installs.

### 3. Add an account

Open `http://<host>:20130/admin?t=<AGY_ADMIN_TOKEN>`:

1. type a profile name (the account email works well) → **start login**
2. open the Google URL, sign in, approve
3. you land on `antigravity.google/oauth-callback?...&code=...` — the page may look
   blank, that is normal. Copy the `code=` value
4. paste it → **submit** → **test turn**

`ok` means usable. `verify` means open the verification link. `tos` means dead.

### 4. Use it

```bash
curl -s http://127.0.0.1:20130/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"gemini-3.8-flash-medium",
       "messages":[{"role":"user","content":"hello"}]}'
```

`"model": "<profile>/<model>"` pins a specific account. Responses carry `profile` and
`fallback` so you can see which account served the turn.

---

## Routing: primary + fallback

One account carries all traffic. The next is touched **only when the primary fails**.

- `ok` profiles outrank untested ones
- `tos` and `verify` are never selected
- a 429/quota failure parks a profile for 5 minutes instead of demoting it permanently
- change the primary from the panel, `POST /admin/primary`, or `AGY_PRIMARY_PROFILE`

**Ban banners arrive as ordinary assistant text, not HTTP errors.** The bridge buffers
the first ~160 characters of every turn and inspects them: a ToS or verification notice
is never returned as an answer — the profile is marked and the turn is retried on the
next one.

---

## 9router provider card (optional)

Adds **Antigravity ACP** as a real provider card with its own model rows, per-model
**Test** button, and an **Accounts** panel (add account / test / set primary) that drives
the bridge through a server-side proxy route — the admin token never reaches the browser.

```bash
python3 9r-patch/apply.py /path/to/9router/build   # after git pull, BEFORE npm run build
cd /path/to/9router/build && npm run build
# then swap .next/standalone into your live install and restart
```

The provider list and dashboard are **compiled into the client chunks** — editing source
changes nothing until you rebuild. Verify with:

```bash
grep -rl 'Antigravity ACP' .next/static/chunks/
```

`apply.py` is idempotent and stops loudly if an upstream anchor moved, rather than
half-applying.

---

## Pitfalls that cost real time

1. **`--app-data-dir` takes a bare directory NAME, not a path.** An absolute path fails
   with `must not be absolute`. It resolves under `~/.gemini`, so use `agy-<account>`.
2. **`HOME` must be in the child env** or `session/new` dies with
   `language server failed to start: $HOME is not defined`. systemd units do not inherit it.
3. **OAuth codes are PKCE-bound** to the process that printed the URL. A code from an
   older link gives `invalid_grant`. Keep the login process alive while pasting.
4. **Never hold a non-reentrant lock across `rpc()` calls** — `chat()` takes the lock then
   calls `rpc()`, which takes it again, and the request hangs until the client times out.
   Use `RLock`.
5. **Registry `transport.baseUrl` is used verbatim.** 9router only appends
   `/chat/completions` for ids starting with `openai-compatible-`. A registry entry pointed
   at `.../v1` POSTs to `/v1` and gets a 404 wrapped as `model_not_found`. Use the full
   endpoint.
6. **Don't add a second session check inside a 9router `/api/*` route.** `dashboardGuard`
   already handles auth; an extra check 401s a dashboard running with require-login off.
7. **`session/set_model` is undocumented but implemented by `agy`.** Call it and tolerate
   failure rather than aborting the turn.

---

## Endpoints

| method | path | purpose |
|---|---|---|
| GET | `/health` | liveness + worker state |
| GET | `/v1/models` | models from the real CLI |
| POST | `/v1/chat/completions` | stream + non-stream |
| GET | `/admin?t=…` | account panel |
| GET | `/admin/profiles` | profiles + status + primary |
| GET | `/admin/logins` | in-flight logins |
| POST | `/admin/login/start` | `{profile}` → `{loginId, url}` |
| POST | `/admin/login/complete` | `{loginId, code}` |
| POST | `/admin/test` | `{profile, model}` → one real turn |
| POST | `/admin/primary` | `{profile}` |

## Environment

| var | default | meaning |
|---|---|---|
| `AGY_BIN` | `/root/.local/bin/agy` | CLI path |
| `AGY_BRIDGE_PORT` | `20130` | listen port |
| `AGY_BRIDGE_BIND` | `127.0.0.1` | set `0.0.0.0` to reach the panel remotely |
| `AGY_ADMIN_TOKEN` | *(unset = open)* | required as `?t=…` on `/admin*` |
| `AGY_APPDATA_ROOT` | `/root/.gemini` | where CLI profiles live |
| `AGY_WORKERS_PER_PROFILE` | `1` | parallel `agy acp` processes per account |
| `AGY_TURN_TIMEOUT` | `300` | seconds per turn |
| `AGY_PRIMARY_PROFILE` | *(unset)* | force the primary |

## Layout

```
bridge.py                  the bridge (stdlib only)
agy-bridge.service         systemd unit
9r-patch/
  antigravity-acp.js       provider registry entry
  AcpAccountsCard.js       Accounts panel component
  agy-acp-route.js         server-side bridge proxy (/api/agy-acp/*)
  apply.py                 idempotent installer
scripts/
  classify_all.py          real-turn liveness for every profile + verification links
  get_validation_url.py    pull one profile's VALIDATION_REQUIRED link
  latency_test.py          three turns of one conversation, per-turn timing
  long_convo_test.py       shows sent bytes vs growing client history
  bridge_memory_test.py    cache must not lose context (plant a fact, ask again)
  acp_bench.py             raw `agy acp` bench: fresh session vs one continued
  session_memory_check.py  does a continued ACP session really remember
  tools_test.py            function calling through the bridge
  vision_test.py           image round-trip through the bridge
  parallel_test.py         four concurrent turns
  disconnect_test.py       dropped client must not leak the worker lock
  audit_compare.py         behaviour + latency vs a normal OpenAI provider
```

## Tool calling

ACP has no OpenAI `tools` channel, so the caller's function schemas travel in
the prompt and the model answers with `tool_call` blocks in **OpenAI
function-call shape** (`id`, `type`, `function{name, arguments}`), where
`arguments` is a JSON **string**. The bridge extracts those blocks and removes
them from `content`, so raw JSON never reaches the client. Prose around the
blocks survives; several blocks become several calls.

Three ordered patterns are tried: tagged blocks, bare OpenAI-shaped JSON, then
the legacy `{"tool_calls":[...]}` envelope. Requiring `id`/`type`/`function` in
the bare-JSON pattern is what keeps a JSON-mode answer such as
`{"city":"Jakarta","temp":30}` from being eaten as a tool call.

Unknown function names are dropped against the caller's declared list. The
agent's own tools (`run_command`, ...) are **never** surfaced to a client that
declared its own functions.

### Keeping the agent from running its own tools

Prompt-level prohibition does not work: the agent's internal system prompt wins
and it still reaches for `run_command` on action-shaped requests. The reliable
lever is the CLI's own `PreToolUse` hook, which can hard-block execution and
whose `reason` string is fed back to the model.

Install the two files from `hooks/` into the **session working directory**
(the `cwd` passed to `session/new`, i.e. `AGY_CWD`), as `.agents/hooks.json` and
`.agents/deny_builtin.py`. Discovery walks up from that cwd, so putting them
next to `bridge.py` silently does nothing.

Denial is **conditional per session**: the bridge writes
`<AGY_CWD>/.bridge-mode/<sessionId>.json` when the request declared tools, and
the hook handler reads `conversationId` from its stdin payload to decide. With
client tools the built-in action tools are denied and the model emits the
caller's function; without client tools the agent keeps its own abilities.
Every decision is appended to `/var/log/agy-bridge-hooks.log`.

The matcher lists action tools explicitly and never uses a wildcard: the loop's
own control tools (e.g. `finish`) must stay allowed or a turn never terminates.

If the agent still produces only a native call and no text, the bridge corrects
it **inside the same session** (up to `AGY_TOOL_RETRIES`, default 1) — asking for
a contract block when the client declared tools, or for a plain-text answer when
it did not — and only then fails over or translates as a last resort.

Offline parser tests: `python3 scripts/tool_extract_test.py` (no model, no
network). Live probes: `scripts/tools_leak_test.py`, `scripts/tool_mode_probe.py`.

## Latency: live session reuse

A request that continues a conversation reuses the ACP session that already
holds its context, so only the new tail of the history is transmitted. Sessions
are keyed on model + message-hash chain (a branch or an edited history misses
and creates a fresh session), closed when idle or beyond `AGY_SESSION_MAX`, and
a turn whose upstream stream produces no event for `AGY_STALL_TIMEOUT` seconds
is cancelled instead of holding the worker for the full turn timeout.

Knobs: `AGY_SESSION_CACHE=0` disables reuse, `AGY_SESSION_IDLE` (seconds),
`AGY_SESSION_MAX` (per worker), `AGY_PREWARM=0` disables boot pre-warm,
`AGY_PREWARM_PROFILES`, `AGY_STALL_TIMEOUT` (seconds).

`GET /health` reports `cache: {hit, miss, closed, sessions}`. Each turn logs
`turn cache=hit|miss sent=NB new=Xms total=Ys`; `sent` is the prompt size
actually transmitted, so a hit is visible as a small constant.

## License

MIT
