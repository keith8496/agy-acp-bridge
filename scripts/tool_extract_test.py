#!/usr/bin/env python3
"""Offline unit tests for the tool-call extractor (no model, no network)."""
import importlib.util
import json
import sys

spec = importlib.util.spec_from_file_location("br", "/root/agy-bridge/bridge.py")
br = importlib.util.module_from_spec(spec)
sys.modules["br"] = br
spec.loader.exec_module(br)

O, C = "<" + "tool_call>", "<" + "/tool_call>"
ALLOWED = {"terminal", "get_weather"}
fails = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (("  " + str(extra)) if not cond else ""))
    if not cond:
        fails.append(name)


# 1. OpenAI-shaped block + prose around it
txt = "Let me check that.\n" + O + json.dumps({
    "id": "call_1", "type": "function",
    "function": {"name": "terminal", "arguments": json.dumps({"command": "echo hi"})}}) + C + "\nDone."
calls, cleaned = br.extract_tool_calls(txt, ALLOWED)
check("block parsed", len(calls) == 1 and calls[0]["function"]["name"] == "terminal", calls)
check("arguments is string", isinstance(calls[0]["function"]["arguments"], str))
check("id kept", calls[0]["id"] == "call_1")
check("prose kept, json gone", cleaned == "Let me check that.\nDone." and O not in cleaned, repr(cleaned))

# 2. two blocks
txt2 = O + json.dumps({"function": {"name": "get_weather", "arguments": {"city": "Jakarta"}}}) + C + \
       O + json.dumps({"function": {"name": "terminal", "arguments": {"command": "date"}}}) + C
calls2, cleaned2 = br.extract_tool_calls(txt2, ALLOWED)
check("two calls", len(calls2) == 2, calls2)
check("ids generated", all(c["id"].startswith("call_") for c in calls2))
check("object args -> string", json.loads(calls2[0]["function"]["arguments"]) == {"city": "Jakarta"})
check("content empty", cleaned2 == "", repr(cleaned2))

# 3. legacy envelope (the shape that used to leak)
legacy = json.dumps({"tool_calls": [{"name": "terminal", "arguments": {"command": "python x.py saldo"}}]})
calls3, cleaned3 = br.extract_tool_calls(legacy, ALLOWED)
check("legacy normalized", len(calls3) == 1 and calls3[0]["type"] == "function"
      and "function" in calls3[0], calls3)
check("legacy args string", isinstance(calls3[0]["function"]["arguments"], str))
check("legacy content cleaned", cleaned3 == "", repr(cleaned3))

# 4. bare OpenAI JSON, no tags
bare = json.dumps({"id": "call_9", "type": "function",
                   "function": {"name": "terminal", "arguments": "{\"command\":\"ls\"}"}})
calls4, cleaned4 = br.extract_tool_calls(bare, ALLOWED)
check("bare json parsed", len(calls4) == 1 and calls4[0]["id"] == "call_9", calls4)

# 5. plain answer untouched
calls5, cleaned5 = br.extract_tool_calls("Saldo kamu 12000.", ALLOWED)
check("plain text no calls", calls5 == [] and cleaned5 == "Saldo kamu 12000.", (calls5, cleaned5))

# 6. unknown function filtered
bad = O + json.dumps({"function": {"name": "run_command", "arguments": {"CommandLine": "ls"}}}) + C
calls6, cleaned6 = br.extract_tool_calls(bad, ALLOWED)
check("unknown name dropped", calls6 == [], calls6)

# 7. json-mode answer must NOT be eaten as a tool call
jm = '{"city":"Jakarta","temp":30}'
calls7, cleaned7 = br.extract_tool_calls(jm, ALLOWED)
check("json mode untouched", calls7 == [] and cleaned7 == jm, (calls7, cleaned7))

# 8. contract mentions the delimiter and the string-arguments rule
p = br.tools_prompt([{"type": "function", "function": {"name": "terminal", "parameters": {}}}],
                    tool_choice="auto")
check("contract has delimiter", O in p and C in p)
check("contract demands string args", "JSON string" in p)
check("contract forbids builtins", "run_command" in p)
check("tool_choice hint", "auto" in p)

print("\n" + ("ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}"))
sys.exit(1 if fails else 0)
