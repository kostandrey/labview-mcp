#!/usr/bin/env python3
"""labview-mcp: MCP stdio server wrapping LabVIEW extraction/scripting tools.

Zero dependencies (Python stdlib only). Implements the Model Context
Protocol over stdio: newline-delimited JSON-RPC 2.0.

Tools cover three capabilities:
  1. Static .vi analysis  - extract_vi, list_artifacts, crop_image, stitch_cases
  2. LabVIEW docs         - search_docs, read_doc (offline CHM mirror),
                            search_ni_docs, fetch_ni_doc (live ni.com backend)
  3. Live LabVIEW via COM - gateway (ping/analyze/listmem/wires/errors +
                            write verbs), gateway_batch, arrread (array
                            in/out runtime verification), manage_processes
"""
import html as html_mod
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import urllib.parse

# Paths. Everything is anchored on ONE root (default: the local project
# layout); override with env vars to install the server elsewhere:
#   LABVIEW_SKILL_ROOT      root of the LabView skill checkout (gateway,
#                           knowledge base, help mirror, style codes)
#   LABVIEW_MCP_SCRIPTS     driver scripts dir (default <root>/mcp-labview/scripts)
SKILL_ROOT = os.environ.get("LABVIEW_SKILL_ROOT", r"C:\LabView skill")
ROOT = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.environ.get("LABVIEW_MCP_SCRIPTS",
                         os.path.join(SKILL_ROOT, "mcp-labview", "scripts"))
WORKROOT = os.path.join(SKILL_ROOT, "_service", "extract")  # gitignored
HELP_DIR = os.path.join(SKILL_ROOT, "help")
GATEWAY_VI = os.path.join(SKILL_ROOT, "gateway", "Gateway.vi")
ARRREAD_EXE = os.path.join(SKILL_ROOT, "skill-labview-code",
                           "scripts", "arrread.exe")
SERVER_NAME = "labview-mcp"
SERVER_VERSION = "1.1.0"


def log(msg):
    print("[%s] %s" % (SERVER_NAME, msg), file=sys.stderr, flush=True)


def run(cmd, timeout=180):
    """Run a command, return combined readable output (never raises)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           errors="replace", timeout=timeout)
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        if r.returncode != 0:
            return "EXIT %s\nstdout:\n%s\nstderr:\n%s" % (r.returncode, out, err)
        return out if out else err
    except subprocess.TimeoutExpired:
        return "ERROR: command timed out after %ss" % timeout
    except Exception as e:
        return "ERROR: %s" % e


def strip_html(s):
    s = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", s)
    # Keep commented-out content: Zoomin pages (docs-be.ni.com) embed the whole
    # article inside one large HTML comment - only the markers must go.
    s = re.sub(r"<!--", " ", s)
    s = re.sub(r"-->", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html_mod.unescape(s)
    return re.sub(r"[ \t\r\f\v]+", " ", s)


def walk_files(root, limit=5000):
    out = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            try:
                st = os.stat(p)
            except OSError:
                continue
            out.append((p, st.st_size, st.st_mtime))
            if len(out) >= limit:
                return out
    return out


def cap(text, n):
    if len(text) <= n:
        return text
    return text[:n] + "\n... [truncated, %s chars total]" % len(text)


# --------------------------------------------------------------------------
# Tool implementations
# --------------------------------------------------------------------------

def tool_extract_vi(args):
    vi = args["vi_path"]
    if not os.path.isfile(vi):
        return "ERROR: source not found: %s" % vi
    base = os.path.splitext(os.path.basename(vi))[0]
    out = args.get("out_dir") or os.path.join(WORKROOT, base)
    os.makedirs(out, exist_ok=True)
    res = run(["cscript", "//nologo", os.path.join(SCRIPTS, "lv_extract2.vbs"), vi, out],
              timeout=420)
    files = walk_files(out)
    listing = "\n".join("  %-60s %9d bytes" % (os.path.relpath(p, out), sz)
                        for p, sz, _m in files)
    text = "extract_vi result for: %s\nwork dir: %s\n\n%s\n\n--- artifacts (%d) ---\n%s\n" % (
        vi, out, res, len(files), listing)
    strings_path = os.path.join(out, base + "_strings.txt")
    if os.path.isfile(strings_path):
        with open(strings_path, "r", errors="replace") as f:
            raw = f.read()
        text += ("\n--- strings export preview (%d of %d chars; full file: %s) ---\n%s"
                 % (min(len(raw), 60000), len(raw), strings_path, cap(raw, 60000)))
    bd = os.path.join(out, "images_" + base)
    if os.path.isdir(bd):
        text += ("\nNOTE: block diagram = images_%s\\*_reportb.png, front panel = "
                 "*_reportc.png; one PNG per case of every structure (filenames "
                 "encode the case path). Use crop_image / stitch_cases on them." % base)
    return text


def tool_list_artifacts(args):
    d = args["dir"]
    if not os.path.isdir(d):
        return "ERROR: directory not found: %s" % d
    files = walk_files(d)
    lines = ["%s  %10d  %s" % (os.path.relpath(p, d), sz,
                               __import__("datetime").datetime.fromtimestamp(m).isoformat(timespec="seconds"))
             for p, sz, m in files]
    return "directory: %s\n%d file(s)\n%s" % (d, len(files), "\n".join(lines))


def tool_crop_image(args):
    out = args.get("out") or args["src"].rsplit(".", 1)[0] + "_crop.png"
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
           os.path.join(SCRIPTS, "crop.ps1"),
           "-Src", args["src"], "-X", str(args["x"]), "-Y", str(args["y"]),
           "-W", str(args["w"]), "-H", str(args["h"]), "-Out", out]
    if args.get("scale"):
        cmd += ["-Scale", str(args["scale"])]
    return run(cmd, timeout=120)


def tool_stitch_cases(args):
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
           os.path.join(SCRIPTS, "stitch.ps1"), "-Dir", args["dir"]]
    if args.get("name_pattern"):
        cmd += ["-NamePattern", args["name_pattern"]]
    if args.get("cols"):
        cmd += ["-Cols", str(args["cols"])]
    if args.get("rows"):
        cmd += ["-Rows", str(args["rows"])]
    res = run(cmd, timeout=180)
    return res + "\nOutput sheets are written into the same directory as sheet0.png, sheet1.png, ..."


def tool_search_docs(args):
    query = args["query"].lower()
    max_results = int(args.get("max_results", 40))
    results = []
    searched = 0
    for p, sz, _m in walk_files(HELP_DIR):
        if not p.lower().endswith((".html", ".htm")) or sz > 3_000_000:
            continue
        searched += 1
        rel = os.path.relpath(p, HELP_DIR)
        try:
            with open(p, "r", errors="replace") as f:
                content = f.read()
        except OSError:
            continue
        if query in os.path.basename(p).lower():
            results.append((rel, "[filename match] " + strip_html(
                re.sub(r"(?s).*<TITLE>(.*?)</TITLE>.*", r"\1", content) if "<TITLE>" in content else rel)))
        low = content.lower()
        pos, hits = 0, 0
        while hits < 3:
            idx = low.find(query, pos)
            if idx < 0:
                break
            snippet = strip_html(content[max(0, idx - 120): idx + 260])
            results.append((rel, snippet))
            pos = idx + len(query)
            hits += 1
            if len(results) >= max_results:
                break
        if len(results) >= max_results:
            break
    if not results:
        return "No matches for %r in %d local doc files." % (query, searched)
    body = "\n".join("%s\n    %s" % (rel, snip.replace("\n", " ")) for rel, snip in results)
    return ("Matches for %r (searched %d files, showing %d):\n\n%s\n\n"
            "Read a full page with read_doc using the relative path."
            % (query, searched, len(results), body))


def tool_search_knowledge(args):
    terms = [t.lower() for t in (args.get("query") or "").split()]
    if not terms:
        return "ERROR: empty query"
    max_results = int(args.get("max_results", 30))
    roots = [os.path.join(SKILL_ROOT, "skill-labview-code"),
             os.path.join(SKILL_ROOT, "style_codes.json")]
    files = []
    for base in roots:
        if os.path.isfile(base):
            files.append(base)
        elif os.path.isdir(base):
            for root, _dirs, names in os.walk(base):
                for n in names:
                    if n.lower().endswith((".md", ".txt")):
                        files.append(os.path.join(root, n))
    results = []
    for p in sorted(files):
        try:
            with open(p, "r", errors="replace") as f:
                lines = f.read().splitlines()
        except OSError:
            continue
        rel = os.path.relpath(p, SKILL_ROOT)
        hits = 0
        for i, ln in enumerate(lines, 1):
            low = ln.lower()
            if all(t in low for t in terms):
                results.append("%s:%d: %s" % (rel, i, ln.strip()[:200]))
                hits += 1
                if hits >= 4 or len(results) >= max_results:
                    break
        if len(results) >= max_results:
            break
    if not results:
        return ("No knowledge matches for %r. Try single keywords - the "
                "knowledge base is large; e.g. 'tunnel', '1055', "
                "'connector pane'." % args["query"])
    return ("Knowledge matches for %r (%d shown; file:line in the "
            "skill-labview-code knowledge base):\n\n%s\n\n"
            "Read the file around the given line for full context."
            % (args["query"], len(results), "\n".join(results)))


def tool_read_doc(args):
    rel = args["path"].replace("/", os.sep)
    if not rel.lower().endswith(".html"):
        rel += ".html"
    full = os.path.abspath(os.path.join(HELP_DIR, rel))
    if not full.lower().startswith(HELP_DIR.lower()):
        return "ERROR: path outside the docs mirror"
    if not os.path.isfile(full):
        return "ERROR: not found: %s" % rel
    with open(full, "r", errors="replace") as f:
        raw = f.read()
    m = re.search(r"(?i)<TITLE>(.*?)</TITLE>", raw)
    title = m.group(1).strip() if m else rel
    return "TITLE: %s\nPATH: %s\n\n%s" % (title, rel, cap(strip_html(raw), 40000))


def tool_search_ni_docs(args):
    q = urllib.parse.quote(args["query"] + " ni.com docs labview")
    url = "https://html.duckduckgo.com/html/?q=" + q
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            page = r.read().decode("utf-8", "replace")
    except Exception as e:
        return "ERROR: search failed (%s). Search engines rate-limit bots - retry later or use search_docs on the offline mirror." % e
    links = [urllib.parse.unquote(m) for m in re.findall(r'uddg=([^&"]+)', page)]
    titles = [strip_html(t) for t in re.findall(r'result__a"[^>]*>(.*?)</a>', page)]
    seen, out = set(), []
    for i, link in enumerate(links):
        if "ni.com" not in link:
            continue
        if link in seen:
            continue
        seen.add(link)
        title = titles[i] if i < len(titles) else ""
        out.append("- %s\n  %s" % (title, link))
        if len(out) >= 15:
            break
    if not out:
        return "No ni.com results (search engines rate-limit bots). Fallback: search_docs on the offline mirror, or guess the page at docs-be.ni.com/bundle/<bundle>/page/<page>.html."
    return ("ni.com results for %r:\n\n%s\n\n"
            "Fetch full page text with fetch_ni_doc (bundle = the part after "
            "/bundle/, page = the part after /page/)." % (args["query"], "\n".join(out)))


def tool_fetch_ni_doc(args):
    if args.get("url"):
        url = args["url"]
    else:
        url = "https://docs-be.ni.com/bundle/%s/page/%s.html" % (args["bundle"], args["page"])
    host = urllib.parse.urlparse(url).netloc
    if not host.endswith("ni.com"):
        return "ERROR: only ni.com hosts are allowed"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8", "replace")
    except Exception as e:
        return ("ERROR: fetch failed (%s). Note: docs-be.ni.com is an UNOFFICIAL "
                "keyless backend and may be unavailable; the page may also not "
                "exist - check bundle/page spelling via search_ni_docs." % e)
    m = re.search(r"(?i)<TITLE>(.*?)</TITLE>", raw)
    title = m.group(1).strip() if m else url
    # Zoomin pages wrap the real article in <section class="section"> blocks;
    # everything outside is megabytes of navigation noise.
    sections = re.findall(r"(?is)<section\b.*?</section>", raw)
    body = "\n".join(strip_html(s) for s in sections) if sections else strip_html(raw)
    body = re.sub(r"\n{2,}", "\n", body).strip()
    return ("SOURCE: %s (unofficial keyless docs backend)\nTITLE: %s\n\n%s"
            % (url, title, cap(body, 60000)))


WRITE_VERBS = ("newvi", "place", "wire", "delete", "loop", "setval")


def tool_gateway(args):
    verb = args["verb"]
    if not os.path.isfile(GATEWAY_VI):
        return ("Gateway.vi is not built yet (%s missing). Build it once from "
                "C:\\LabView skill\\skill-labview-code\\references\\gateway-recipe.md "
                "(~10 minutes), then retry. Meanwhile use extract_vi for static "
                "VI analysis." % GATEWAY_VI)
    cmd = ["cscript", "//nologo", os.path.join(SCRIPTS, "lv_gateway.vbs"), GATEWAY_VI, verb]
    if args.get("vi_path"):
        vi = args["vi_path"]
        if verb in WRITE_VERBS:
            # Write verbs edit and save the REAL file (Save:Instrument inside
            # the Gateway). A temp copy would throw the edits away - pass the
            # path through unchanged. Targeting a VI that is open in the
            # user's LabVIEW instance is the STANDARD, supported mode: COM
            # attaches to the running instance, edits appear LIVE on screen
            # and save from the same session. Coordinate with the user -
            # two editors, one file, the user sees every change.
            cmd.append(vi)
        else:
            # vi_path may carry a reference-resolver suffix (path.vi%Class|Label);
            # only the file part exists on disk - check/copy the base, then
            # re-attach the resolver to the temp copy's name.
            base, sep, resolver = vi.partition("%")
            if not os.path.isfile(base):
                return "ERROR: vi_path not found: %s" % vi
            tmpdir = os.path.join(tempfile.gettempdir(), "lv_mcp")
            os.makedirs(tmpdir, exist_ok=True)
            dst = os.path.join(tmpdir, os.path.basename(base))
            if os.path.isfile(dst):
                os.remove(dst)
            shutil.copyfile(base, dst)
            cmd.append(dst + (sep + resolver if sep else ""))
            # read verbs snapshot a temp copy for uniform behavior; this is
            # not a ban - the user's IDE-open VI works live too (getNode /
            # errors / wires attach to the running instance)
    # Slot alignment: the VBS maps argv[2]->'vi path', argv[3]->arg1, ... .
    # newvi carries its save path in arg1 and has no vi_path, so without this
    # placeholder the path would land in the 'vi path' slot and arg1 would
    # stay empty (Save:Instrument then gets an empty path -> error 43).
    if verb == "newvi" and not args.get("vi_path"):
        cmd.append("")
    for key in ("arg1", "arg2", "arg3"):
        if args.get(key):
            cmd.append(args[key])
    return run(cmd, timeout=240)


def tool_gateway_batch(args):
    """Run a SCRIPT of gateway commands in ONE LabVIEW session.

    Script format: one command per line, fields ';'-separated:
      verb;vi_path;arg1;arg2;arg3      (trailing fields optional)
      !verb;...                       failure tolerated, keep going
      # comment / delete;<path> / copy;<src>;<dst> / echo;<text> / sleep;<ms>
    Stops at the first failing command unless the line starts with '!'.
    Tip for retries: prefer a FRESH vi name per attempt (newvi) over
    delete+recreate - the LabVIEW instance keeps deleted VIs in memory
    under their old name.
    """
    if not os.path.isfile(GATEWAY_VI):
        return ("Gateway.vi is not built yet (%s missing). Build it once from "
                "C:\\LabView skill\\skill-labview-code\\references\\gateway-recipe.md "
                "(~10 minutes)." % GATEWAY_VI)
    script = args.get("script") or ""
    if not script.strip():
        return "ERROR: empty script"
    tmpdir = os.path.join(tempfile.gettempdir(), "lv_mcp")
    os.makedirs(tmpdir, exist_ok=True)
    script_path = os.path.join(tmpdir, "batch_script.txt")
    with open(script_path, "w", encoding="ascii", errors="replace") as f:
        f.write(script.replace("\r\n", "\n") + "\n")
    timeout = int(args.get("timeout_s") or 600)
    cmd = ["cscript", "//nologo", os.path.join(SCRIPTS, "lv_gateway_batch.vbs"),
           GATEWAY_VI, script_path]
    return run(cmd, timeout=timeout)


def tool_arrread(args):
    """Set/read array (and scalar) control values on a saved .vi and run it,
    via the proven arrread.exe C# helper. The ONLY reliable way through MCP
    to verify array-input VIs: 'cycle' = set+run+read in ONE process, so it
    works even when the VI's window is closed (set and get in SEPARATE
    processes return stale/empty data - cross-process persistence trap).
    'values' is a comma-separated list, e.g. "5,1,3" (2D: rows via ';').
    """
    mode = args["mode"]
    vi = args["vi_path"]
    ctl = args["control"]
    values = args.get("values") or ""
    if not os.path.isfile(ARRREAD_EXE):
        return ("ERROR: arrread.exe not found at %s - see " % ARRREAD_EXE +
                "C:\\LabView skill\\skill-labview-code\\references\\"
                "gateway-recipe.md (runtime verification section)")
    if mode in ("set", "setint", "cycle") and not values:
        return "ERROR: mode %s requires 'values'" % mode
    cmd = [ARRREAD_EXE, mode, vi, ctl]
    if values:
        cmd.append(values)
    return run(cmd, timeout=180)


def tool_manage_processes(args):
    action = args["action"]
    if action == "list":
        return run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='LabVIEW.exe'\" "
                    "| Select-Object ProcessId,ExecutablePath | Format-List"])
    if action == "kill":
        pid = args.get("pid")
        if not pid:
            return "ERROR: kill requires pid (run action=list first)"
        return run(["powershell", "-NoProfile", "-Command",
                    "Stop-Process -Id %s -Force" % int(pid)])
    return "ERROR: action must be 'list' or 'kill'"


# --------------------------------------------------------------------------
# Tool metadata
# --------------------------------------------------------------------------

TOOLS = [
    {
        "name": "extract_vi",
        "description": (
            "Extract a LabVIEW .vi's code into analyzable artifacts: a strings "
            "export (every control, constant value, function name), an HTML "
            "report, and PNGs of the front panel, block diagram, and every case "
            "of every structure. Works on a copy - the original is never "
            "touched. PRIMARY tool for 'view VI code / pseudocode / explain "
            "this VI / talk with a VI' when a file path is known. Returns "
            "artifact paths plus a preview of the strings export. The first "
            "call in a session spawns a background LabVIEW (may take ~1 min)."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "vi_path": {"type": "string", "description": "Absolute path of the .vi file"},
                "out_dir": {"type": "string", "description": "Output directory (default: C:\\LabView skill\\_service\\extract\\<vi name> - a gitignored service area)"}
            },
            "required": ["vi_path"]
        }
    },
    {
        "name": "list_artifacts",
        "description": "List files (relative path, size, modified) in an extraction output directory.",
        "inputSchema": {
            "type": "object",
            "properties": {"dir": {"type": "string", "description": "Directory to list"}},
            "required": ["dir"]
        }
    },
    {
        "name": "crop_image",
        "description": "Crop and upscale a region of an extracted diagram PNG (nearest-neighbor, default 3x) so labels, constants and terminal wiring become readable.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "src": {"type": "string"}, "x": {"type": "integer"}, "y": {"type": "integer"},
                "w": {"type": "integer"}, "h": {"type": "integer"},
                "out": {"type": "string"}, "scale": {"type": "integer", "description": "default 3"}
            },
            "required": ["src", "x", "y", "w", "h"]
        }
    },
    {
        "name": "stitch_cases",
        "description": "Stitch per-case PNGs of a Case/Event structure into numbered contact sheets (sheet0.png, sheet1.png, ...) in the same directory, so every case can be reviewed at once. Filter with name_pattern (regex on the file base name).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dir": {"type": "string"},
                "name_pattern": {"type": "string"},
                "cols": {"type": "integer"}, "rows": {"type": "integer"}
            },
            "required": ["dir"]
        }
    },
    {
        "name": "search_docs",
        "description": (
            "Full-text search over the OFFLINE mirror of the LabVIEW 2020 CHM "
            "documentation (function reference 'glang', properties 'lvprop', "
            "how-to 'lvhowto', concepts 'lvconcepts', scripting 'lvscript). "
            "Best first stop for 'what does function X do', terminal orders, "
            "property semantics."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "read_doc",
        "description": "Read one page from the offline LabVIEW docs mirror as plain text. Path is relative to the help root, e.g. 'glang/Select.html' or 'TRef_Traverse_for_References.html'. Get paths from search_docs.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"]
        }
    },
    {
        "name": "search_ni_docs",
        "description": (
            "Web-search for ni.com LabVIEW documentation pages about a function "
            "or topic; returns candidate URLs. Rate-limited (bot detection) - "
            "use sparingly; prefer search_docs first. Follow up with "
            "fetch_ni_doc using the bundle/page parts of the URL."),
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"]
        }
    },
    {
        "name": "fetch_ni_doc",
        "description": (
            "Fetch a live ni.com LabVIEW documentation page as plain text from "
            "NI's UNOFFICIAL keyless docs backend "
            "(https://docs-be.ni.com/bundle/<bundle>/page/<page>.html). May "
            "break at any time; the offline mirror (search_docs/read_doc) is "
            "the reliable fallback."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "bundle": {"type": "string", "description": "e.g. 'labview'"},
                "page": {"type": "string", "description": "e.g. 'mcp-server-nigel'"},
                "url": {"type": "string", "description": "Full ni.com URL (alternative to bundle/page)"}
            },
            "required": []
        }
    },
    {
        "name": "gateway",
        "description": (
            "Run the Gateway.vi helper (v3.12) inside LabVIEW via COM/VI "
            "Scripting. STRICT RULE for user-provided VIs: never run write "
            "verbs (newvi/place/wire/delete/loop/setval) directly on the user's "
            "original VI. Copy it first (e.g. <name>_tmp.vi), develop and "
            "debug the script on the copy, verify it (wires: zero "
            "broken:1, plus a runtime value check), and only then apply "
            "the proven script to the original. Read verbs (ping/analyze/"
            "wires/listmem/errors) are safe on the original. "
            "Read verbs: ping (sanity check), analyze (one line "
            "per block-diagram object: index, ClassName, label, UID), wires (one "
            "line per wire: label, broken flag, UID, terminals as "
            "'Label(UID) [OwnerClass] of Node{ UID, Label}' - the terminal's "
            "label+UID and its owning node's UID+Label; source first, then "
            "all sinks separated by ';'; combined with analyze + getNode "
            "this restores the block diagram completely), "
            "listmem, errors (v3.14: returns the IDE Error-List "
            "content for the VI - 'Errors list = <msg>;<msg>;' 'Details = "
            "<details>;<details>;' - items and details are ';'-separated "
            "and index-aligned; EMPTY Errors list = VI is clean; the item "
            "text does NOT name the offending object, pair it with "
            "analyze/wires to locate it), getNode (v3.17: arg1='terms'. "
            "vi_path='%Node|<label>' -> per-terminal lines 'Term[i] UID, "
            "name, isSource, isHidden, wireUID/wireBroken | No wire "
            "connected'; vi_path=a .vi/.llb path -> the subVI's "
            "connector-pane 'Control[i]: UID, Label, Indicator, "
            "IsOnConPanel, Wiring rule' - read the interface BEFORE wiring "
            "instead of probing; FN terminals have empty names and the "
            "source flag does not reveal which sink is init vs input), "
            "analyze/wires to locate it). Write verbs (edit and SAVE the real file; if the user's "
            "LabVIEW is running, COM attaches to that instance and the edit "
            "appears LIVE in the open VI - safe and preferred; if edits do "
            "not appear live, a background instance was used and an IDE-open "
            "copy is stale: user must reload from disk before saving): newvi "
            "(arg1=full save path; vi_path stays EMPTY), place (vi_path="
            "target VI or resolver, arg1=type e.g. Add|Multiply|Numeric "
            "Control|String Constant, arg2='x,y' diagram location (or "
            "'x,y,W,H': W,H REQUIRED for growable nodes and for FP objects - "
            "it is the FRONT-PANEL ITEM SIZE; 0 makes the item unreadable "
            "on the FP), arg3="
            "label or '-'; returns UID). v3.12: FRONT-PANEL OBJECTS "
            "(numind/numctl/any:21003/any:21004/...) ARE placeable INSIDE "
            "structures via resolver - the gateway creates the FP object "
            "and moves its terminal into the loop diagram automatically "
            "(verified: any:21004 and any:21003; the terminal is then a "
            "normal c|0 terminal wireable to nodes inside). "
            "delete (v3.12): vi_path = resolver of the container structure "
            "(objects inside it) or plain VI path (top-level objects); "
            "arg1 = class name ('GObject' matches any object, 'Wire' for "
            "wires); arg2 = 'U:<uid>' or 'L:<label>'. Saves automatically. "
            "CAUTION: in gateway_batch scripts a 2-field line "
            "'delete;<path>' is the script-level FILE delete, not this "
            "verb (3+ field lines go to the gateway). "
            "loop (vi_path='path.vi%ForLoop|"
            "Label', arg1='addSR', arg2=Y position, arg3=Label; returns "
            "UID. v3.8 TUNNEL CONTROL: arg1='tunnel:<idx>' or "
            "'tunnel:U<uid>' (from the -1 status query), arg2=-2 = tunnel "
            "count, arg2=-1 = status ('Tunnel[0], IndexMode: 0, UID=..'), "
            "arg2 0/1/2 sets IndexMode (0=regular, 1=auto-index, "
            "2=concatenate). arg1='addSR', arg2=Y position, arg3=Label adds "
            "a SHIFT REGISTER to the loop (returns 'NewShiftReg, UID='; the "
            "SR must exist before wiring s* terminals - see wire arg2). "
            "TRAP: border auto-tunnels are created "
            "Auto-Index - always 'tunnel:i;0' array crossings or arrays "
            "scalarize element-wise), setval (vi_path='path.vi%Class|Label' "
            "resolver to the "
            "element - Class is a SHORT name without spaces, e.g. "
            "'NumericConstant'; generic 'Constant' also works; the verbose "
            "analyze ClassName like 'DigitalNumericConstant' does NOT - "
            "wrong class gives ERROR 1092; arg1=value, arg2=type: "
            "dec|frc|str. WARNING: a placed numeric constant (numconst/"
            "any:2005) is I32 integer - 'frc' on it SILENTLY writes 0 and "
            "'dec' truncates; setval integers only, build fractional math "
            "from DBL node outputs instead), wire (vi_path="
            "target VI, arg1='srcLabel|dstLabel', arg2='srcKind|srcIdx|"
            "dstKind|dstIdx' where kind c=control/constant terminal (c|0), "
            "n=Terms[] index of a node - ForLoop has ONLY n|0=N; kind i=loop "
            "counter terminal: arg1's source label is the LOOP's label (e.g. "
            "wire 'Loop1|Add1' 'i|0|n|2' wires Loop1's i to Add.x). The wire "
            "RESPONSE reports both terminals with isSource flags and Name: "
            "legal wire = src isSource:1 AND dst isSource:0; 1/1 = "
            "output-output, 0/0 = input-input (both broken:1). 'wire ok' = "
            "created, not legal - read the flags. "
            "place arg1 types: the small named set (Add, Numeric Constant, "
            "...) or 'any:<styleCode>' for anything else (Feedback Node = "
            "any:2353; codes in C:\\LabView skill\\style_codes.json). "
            "SUBVIs (vi.lib / .llb members shipped with the IDE): arg1 = "
            "'any:0<full path>' places the file at <path> (the 0 is "
            "literal). SubVI terminals are indexed by CONNECTOR-PANE CELL "
            "NUMBER (Context Help numbering), NOT inputs-first - wiring an "
            "empty cell gives broken:1 with empty Name; primitives are the "
            "opposite (output-first). Learn the interface with getNode on "
            "the subVI path + lv_extract2.vbs strings BEFORE wiring; "
            "verified pane tables and gotchas: references/subvi-placement.md "
            "in the skill-labview-code knowledge base. ", 
            "FEEDBACK NODE TERMINAL ORDER IS RANDOM PER INSTANCE - always "
            "determine it per FN (2026-10-19: two gateway-placed FNs in one "
            "session were both Map A, refuting the creation-path theory; "
            "earlier gateway-placed FNs were Map B). Procedure: getNode "
            "'<vi>%Node|<fnlabel>' terms - the terminal with isSource:1 is "
            "the OUTPUT; source=[0] -> Map B ([0]=out,[1]=init,[2]=in); "
            "source=[1] -> Map A ([0]=in,[1]=out,[2]=init). Both sinks "
            "accept wires, so init-vs-input follows from the rotation once "
            "the source index is known; if source=[2], run-test. If "
            "already wired wrong, delete (delete;vi;Wire;U:<uid> from the "
            "wires output) and rewire. "
            "BORDER RULE: any wire crossing a loop border auto-creates an "
            "Auto-Index tunnel - the tunnel segment reads broken:1 until "
            "you set it Regular (loop verb, tunnel:i;0). This includes "
            "NODE outputs: after the last border-crossing wire, set ALL "
            "tunnels Regular (tunnel:0;-2 for count, then tunnel:i;0) and "
            "verify with wires (zero broken:1). Never re-invoke a failed "
            "wire (second tunnel pollutes the VI - use a fresh name); "
            "constants may cross (tunnel inherits the label). Tap the Add "
            "output for the result, NOT the Feedback Node output (FN lags "
            "one cycle). Run-verify via "
            "references\\run_vi_get_value.vbs (GetControlValue, VBScript "
            "only). RESOLVER: vi_path may "
            "carry 'C:\\...\\file.vi%Class|Label' or nested "
            "'%Class|Label%Class|Label' suffixes to target an element "
            "inside a structure (used by place/loop/setval). analyze/wires "
            "copy the target to temp; write verbs do not. Recipe: "
            "C:\\LabView skill\\skill-labview-code\\references\\"
            "gateway-recipe.md. COMPOSITE HELPERS in mcp-labview/scripts "
            "(prefer for frequent actions): lv_loop_scaffold (loop+N+SR "
            "one-shot), lv_fn_wire (FN map detection + wiring), "
            "lv_tunnels_regular, lv_verify (wires+errors+compile check - "
            "the IDE error list is computed LAZILY, so errors alone can "
            "give a false PASS), lv_runcheck (copy-first run+read)."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "verb": {"type": "string", "enum": ["ping", "analyze", "listmem", "wires", "getNode", "errors", "newvi", "place", "wire", "delete", "loop", "setval"], "description": "Read verbs (incl. getNode = terminal/connector-pane info, errors = IDE Error-List content, empty = clean) copy the target to temp; write verbs (newvi/place/wire/delete/loop/setval) edit and save the real file"},
                "vi_path": {"type": "string", "description": "Target VI, optionally with %Class|Label resolver suffix (place/loop/setval). For newvi leave empty"},
                "arg1": {"type": "string", "description": "newvi: save path. place: object type. delete: class name ('GObject' works for any object, 'Wire' for wires). loop: 'addSR' or 'tunnel:<idx>'/'tunnel:U<uid>'. setval: value. wire: 'srcLabel|dstLabel'. getNode: 'terms' (only mode supported)"},
                "arg2": {"type": "string", "description": "place: 'x,y' or 'x,y,W,H' (W,H REQUIRED for growable nodes AND for FP objects - it is the FRONT-PANEL ITEM SIZE; 0 makes the item 0-size/unreadable on the FP). delete: 'U:<uid>' or 'L:<label>' (UIDs come from analyze/wires). loop: Y position, or for tunnel: arg1: -2=count, -1=status, 0/1/2=set IndexMode. setval: dec|frc|str. wire: 'srcKind|srcIdx|dstKind|dstIdx'. SHIFT REGISTERS: kind 's'+l|r+i|o+input# (slo=left outside INOUT/init-sink, sli=left inside OUTPUT, sri=right inside INOUT, sro=right outside OUTPUT); the IDX FIELD after '|' = which SR (0-based addSR order). Regular SRs: input# always 0 (sli1 = multi-input SR input #1 -> ERROR 1055). SR must pre-exist: create with loop addSR first. Ex: 'c|0|slo0|0' wires a control to SR0 init; 'sro0|0|c|0' wires SR0 final value out. Other kinds: c=terminal c|0, n=Terms[] index (ForLoop only n|0=N), i=loop counter"},
                "arg3": {"type": "string", "description": "place: label ('-' = none). loop: label. delete: unused"}
            },
            "required": ["verb"]
        }
    },
    {
        "name": "gateway_batch",
        "description": (
            "Run a SCRIPT of gateway commands in ONE LabVIEW session (much "
            "faster than one-by-one gateway calls; one COM attach, N verbs). "
            "Script = newline-separated commands, fields ';'-separated: "
            "'verb;vi_path;arg1;arg2;arg3' (trailing fields optional; empty "
            "field = empty arg). Meta-lines: '# comment', '!verb;...' (failure "
            "tolerated, keep going), 'delete;<path>', 'copy;<src>;<dst>' "
            "(fresh-name wires/analyze checks), 'echo;<text>', 'sleep;<ms>'. "
            "Stops at the first failing gateway command (result starts with "
            "ERROR) unless the line is prefixed '!'. Output: 'LINE <n> "
            "[<verb>]: <result>' per command. RETRY TIP: prefer a FRESH vi "
            "name per attempt (newvi bubble1.vi, bubble2.vi, ...) over "
            "delete+recreate - the LabVIEW instance keeps deleted VIs in "
            "memory under their old name, which confuses later reads. All "
            "gateway verb semantics apply unchanged (see the gateway tool). "
            "STRICT RULE for user-provided VIs: develop/debug the whole "
            "script on a COPY of the VI first; apply to the original only "
            "after the copy verifies clean (zero broken wires + runtime "
            "check). Prefer a FRESH newvi name per retry over deleting."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "script": {"type": "string", "description": "The script text, one command per line"},
                "timeout_s": {"type": "integer", "description": "Overall timeout, default 600"}
            },
            "required": ["script"]
        }
    },
    {
        "name": "arrread",
        "description": (
            "Set/read array (and scalar) control values on a SAVED .vi and "
            "run it, via the proven arrread.exe helper. The ONLY reliable "
            "way to verify array-input VIs from MCP. Modes: 'get' (read a "
            "control: rank=.. len=.. [..]), 'set' (write DBL values), "
            "'setint' (write I32), 'run' (run the VI), 'cycle' (set + run + "
            "read in ONE process - DEFAULT, works even with the VI window "
            "closed; set/get in separate processes hit the cross-process "
            "persistence trap and return stale/empty data). 'values' is "
            "comma-separated, e.g. \"5,1,3\"; required for "
            "set/setint/cycle. Example: cycle on "
            "gen\\sortArr_tmp.vi InputArray \"5,1,3\" -> out len=3 [1, 3, "
            "5]. Requires the VI to be saved and not open for edit in a "
            "stale background instance. set/setint/cycle WRITE control "
            "values - for user-provided VIs run them on a copy first per "
            "the gateway copy-first rule."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["get", "set", "setint", "run", "cycle"], "description": "cycle = set+run+read in one process (recommended)"},
                "vi_path": {"type": "string", "description": "Absolute path of the .vi file"},
                "control": {"type": "string", "description": "Control/terminal label, e.g. 'InputArray'"},
                "values": {"type": "string", "description": "Comma-separated values, e.g. '5,1,3' (required for set/setint/cycle)"}
            },
            "required": ["mode", "vi_path", "control"]
        }
    },
    {
        "name": "search_knowledge",
        "description": (
            "Full-text search over the accumulated LabVIEW code-generation "
            "knowledge (skill-labview-code SKILL.md, gateway-recipe.md "
            "versioned session history v3.x, reference docs, "
            "style_codes.json). Use this BEFORE probing anything "
            "experimentally or when a gateway verb errors - terminal maps, "
            "error causes and proven workflows are usually already recorded "
            "with verification evidence. Example queries: 'connector pane', "
            "'1055', 'Map B', 'FP ITEM SIZE'."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "space-separated words; ALL must appear on the line (case-insensitive)"},
                "max_results": {"type": "integer"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "manage_processes",
        "description": (
            "List running LabVIEW processes (pid + executable path, which "
            "reveals 32- vs 64-bit) or force-kill one by pid. Use when COM "
            "fails with 'ClassFactory cannot supply requested class' - usually "
            "an orphan instance with a modal dialog (e.g. 'Save changes?') is "
            "blocking COM activation."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "kill"]},
                "pid": {"type": "integer"}
            },
            "required": ["action"]
        }
    },
]

TOOLS_IMPL = {
    "extract_vi": tool_extract_vi,
    "list_artifacts": tool_list_artifacts,
    "crop_image": tool_crop_image,
    "stitch_cases": tool_stitch_cases,
    "search_docs": tool_search_docs,
    "read_doc": tool_read_doc,
    "search_ni_docs": tool_search_ni_docs,
    "fetch_ni_doc": tool_fetch_ni_doc,
    "gateway": tool_gateway,
    "gateway_batch": tool_gateway_batch,
    "arrread": tool_arrread,
    "manage_processes": tool_manage_processes,
    "search_knowledge": tool_search_knowledge,
}


# --------------------------------------------------------------------------
# MCP stdio plumbing (newline-delimited JSON-RPC 2.0)
# --------------------------------------------------------------------------

def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def handle(msg):
    method = msg.get("method")
    mid = msg.get("id")
    if mid is None:
        return  # notification - nothing to answer
    if method == "initialize":
        ver = (msg.get("params") or {}).get("protocolVersion") or "2024-11-05"
        send({"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": ver,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }})
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}})
    elif method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        impl = TOOLS_IMPL.get(name)
        if impl is None:
            send({"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text", "text": "ERROR: unknown tool %r" % name}],
                "isError": True}})
            return
        try:
            text = impl(args)
            send({"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text", "text": str(text)}]}})
        except Exception as e:
            log("tool %s failed: %r" % (name, e))
            send({"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text", "text": "ERROR: %r" % e}],
                "isError": True}})
    elif method in ("resources/list", "prompts/list"):
        send({"jsonrpc": "2.0", "id": mid, "result": {method.split("/")[0]: []}})
    elif method == "ping":
        send({"jsonrpc": "2.0", "id": mid, "result": {}})
    else:
        send({"jsonrpc": "2.0", "id": mid, "error": {
            "code": -32601, "message": "Method not found: %s" % method}})


def main():
    log("starting; scripts=%s help=%s gateway=%s" % (SCRIPTS, HELP_DIR, GATEWAY_VI))
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError as e:
            log("ignoring malformed line: %s" % e)
            continue
        try:
            handle(msg)
        except Exception as e:
            log("handler error: %r" % e)
            if msg.get("id") is not None:
                send({"jsonrpc": "2.0", "id": msg["id"], "error": {
                    "code": -32603, "message": "Internal error: %r" % e}})
    log("stdin closed - exiting")


if __name__ == "__main__":
    main()
