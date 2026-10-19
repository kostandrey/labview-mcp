# validate_tools.py - post-edit validation for the MCP server tool definitions.
# WHY: a single malformed tool (e.g. a stray comma turning a parenthesized
# string concatenation into a tuple) makes strict clients like Zed drop ALL
# tools ("invalid type: sequence, expected a string" in Zed.log) while the
# server itself handshakes perfectly. Run this after EVERY edit to
# server.py tool definitions.
#
# Usage:  python validate_tools.py [server.py path]
# Exit 0 = all tools valid; 1 = violation found; 2 = handshake failed.
import json, subprocess, sys

server = sys.argv[1] if len(sys.argv) > 1 else None
cmd = [sys.executable, server] if server else [sys.executable, "-m", "server"]

init = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-10-07","capabilities":{},"clientInfo":{"name":"validate","version":"0"}}}'
initd = '{"jsonrpc":"2.0","method":"notifications/initialized"}'
tl = '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'

proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
out, _ = proc.communicate(init + "\n" + initd + "\n" + tl + "\n", timeout=30)

tools = None
for line in out.splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
    except ValueError:
        continue
    if msg.get("id") == 2:
        tools = msg["result"]["tools"]

if tools is None:
    print("FAIL: no tools/list response")
    sys.exit(2)

bad = 0
for t in tools:
    name = t.get("name")
    problems = []
    if not isinstance(name, str) or not name:
        problems.append("name is not a non-empty string")
    if not isinstance(t.get("description"), str):
        problems.append("description is %s (must be a string)" % type(t.get("description")).__name__)
    if not isinstance(t.get("inputSchema"), dict):
        problems.append("inputSchema is %s (must be an object)" % type(t.get("inputSchema")).__name__)
    if problems:
        bad += 1
        print("INVALID %s: %s" % (name, "; ".join(problems)))

print("%d tools checked, %d invalid" % (len(tools), bad))
sys.exit(1 if bad else 0)
