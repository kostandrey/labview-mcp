# labview-mcp

Installable via `pip install .` (stdlib-only, zero dependencies; provides
the `labview-mcp` entry point; all asset paths anchored on the
`LABVIEW_SKILL_ROOT` env var, default `C:\LabView skill`). Distribution
artifacts: `python -m build` -> `dist/`.

An **installable MCP (Model Context Protocol) server** that lets any
AI-driven IDE (Zed, Claude Desktop, Cursor, ...) work with LabVIEW:
extract and read VI code, generate pseudocode inputs, search LabVIEW
documentation offline and live, and drive LabVIEW itself via COM/VI
Scripting.

Zero dependencies - pure Python 3 stdlib. No pip install, no build step.

## Install

Requirements: Python 3.8+ (tested on 3.13), Windows with LabVIEW 2020 SP1
(VI Scripting + VI Server + ActiveX enabled).

### Zed (`settings.json`)

```json
"context_servers": {
  "labview-mcp": {
    "source": "custom",
    "command": "python",
    "args": ["C:\\LabView skill\\mcp-labview\\server.py"]
  }
}
```

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "labview-mcp": {
      "command": "python",
      "args": ["C:\\LabView skill\\mcp-labview\\server.py"]
    }
  }
}
```

### Smoke test from a terminal

```
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"t","version":"0"}}}' '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | python "C:\LabView skill\mcp-labview\server.py"
```

## Tools

**Strict rule — user-provided VIs: copy first.** Never run gateway write
verbs (`newvi`/`place`/`wire`/`loop`/`setval`) directly on a user's
original VI. Develop and debug on a copy, verify clean (`wires`: zero
`broken: 1` + runtime check), then apply the proven script to the
original.

| Tool | What it does |
|---|---|
| `extract_vi` | **Primary analysis tool.** Copies a .vi, exports strings + HTML report + PNG of front panel, block diagram, and every case of every structure. Original untouched. |
| `list_artifacts` | List extraction output files (path, size, modified). |
| `crop_image` | Crop + upscale (3x default) a region of a diagram PNG to read labels/constants/wiring. |
| `stitch_cases` | Stitch per-case PNGs into contact sheets (`sheet0.png`, ...) for reviewing all cases at once. |
| `search_docs` | Full-text search over the **offline mirror** of the LabVIEW 2020 CHM docs (`C:\LabView skill\help`: glang, lvprop, lvhowto, lvconcepts, lvscript). |
| `read_doc` | Read one mirror page as plain text. |
| `search_ni_docs` | Web-search for ni.com LabVIEW doc pages (rate-limited; offline mirror is the fallback). |
| `fetch_ni_doc` | Fetch a live ni.com doc page as text via NI's **unofficial keyless backend** `docs-be.ni.com/bundle/<bundle>/page/<page>.html` (may break any time). |
| `gateway` | Live LabVIEW via COM: read verbs `ping` (sanity), `analyze` (one line per block-diagram object: index, ClassName, label, UID), `wires` (per-wire label/broken flag/UID + terminals as `Label(TermUID) [Class] of Node{ UID, Label}` - terminal and owning node identified; with analyze+getNode this restores the block diagram), `getNode` (v3.17: arg1=`terms`; vi_path=`%Node|<label>` -> per-terminal UID/name/isSource/isHidden/wire status, or a plain .vi/.llb path -> the subVI's connector-pane cells with wiring rules), `errors` (v3.14: the IDE Error-List content for the VI - `;`-separated, index-aligned msg/details pairs; empty = VI clean), `listmem`; write verbs `newvi`, `place` (incl. FP objects inside structures; for FP objects W,H in arg2 = front-panel item size and MUST be non-zero; subVIs via `any:0<full path to .vi/.llb member>` - subVI terminals are connector-pane CELL numbers), `wire` (response reports both terminals with `isSource` flags + `Name`: legal = src 1/dst 0; 1/1 = output-output, 0/0 = input-input), `delete` (GObject/wire by UID or label), `loop` (incl. `loop ... tunnel:<i>;...` tunnel IndexMode control), `setval` - edit and SAVE the real file. **Requires Gateway.vi** (one-time build, see below). **Composite helper scripts** in `scripts/` (prefer for frequent actions): `lv_loop_scaffold.vbs` (loop+N+SR one-shot), `lv_fn_wire.vbs` (FN auto-map+wiring), `lv_tunnels_regular.vbs`, `lv_verify.vbs` (wires+errors+compile check, exit-coded), `lv_runcheck.vbs` (copy-first run+read). |
| `gateway_batch` | Run a whole script of gateway commands in ONE LabVIEW session (one COM attach, N verbs) - much faster than one-by-one calls. |
| `arrread` | Set/read **array control values** on a saved .vi and run it (`arrread.exe` helper). `cycle` mode = set+run+read in one process - the reliable way to verify array-input VIs from MCP. |
| `manage_processes` | List/kill LabVIEW processes - the fix when COM fails with `ClassFactory cannot supply requested class` (orphan instance with a modal dialog). |
| `search_knowledge` | Full-text search over the agent knowledge base (skill-labview-code SKILL.md, gateway-recipe.md session history, reference docs, style_codes.json). Use FIRST when a verb errors, a terminal map is in question, or before experimental probing. |

## Gateway.vi prerequisite (for the `gateway` tool only)

`gateway` needs `C:\LabView skill\gateway\Gateway.vi` (v3.5+), built once
from the recipe
`C:\LabView skill\skill-labview-code\references\gateway-recipe.md`
(see that file for the full v3 code-generation verb set, the v3.8 loop
`tunnel:<i>` IndexMode control, and the runtime-verification / `arrread`
section). Everything else works without it. Code generation (Mode 3) is
**production-proven**: `newvi` + `place` + `wire` + `loop` + `setval`
build complete VIs from scratch (verified end-to-end: sumtest9.vi and a
bubble-sort VI, checked with `arrread` set/run/get on array controls).

## NI Nigel research summary (Oct 2026)

Question: is there an available way to get the information/documentation
Nigel uses?

- **Nigel** (NI Nigel AI / "AI Advisor") ships with **LabVIEW 2025 Q3+**,
  TestStand, FlexLogger, InstrumentStudio, NI MAX. Cloud-based (Azure,
  OpenAI models), license-gated, included in most subscriptions.
- **No public API.** There is no REST endpoint or SDK to query Nigel.
- **MCP support is inbound only**: Nigel acts as an **MCP client**
  (https://www.ni.com/docs/en-US/bundle/labview/page/mcp-server-nigel.html) -
  you register MCP servers *into* Nigel; NI does not publish a server that
  exposes Nigel's knowledge. (This MCP server could in principle be
  registered into Nigel on a LabVIEW+ license.)
- NI's docs live on a **Zoomin** tenant; the official Zoomin content API
  exists but is credential-gated to NI. No `llms.txt` (`ni.com/docs/llms.txt` → 404).
- **Partial workaround (verified Oct 2026):** the undocumented keyless
  backend `https://docs-be.ni.com/bundle/<bundle>/page/<page>.html` serves
  full doc-page HTML - wired into the `fetch_ni_doc` tool. Unofficial;
  may be locked down at any time.
- Bottom line: **no supported public access to Nigel's knowledge**; the
  docs-be endpoint + offline CHM mirror together cover documentation
  retrieval for this MCP server.

Sources: ni.com Nigel product page, NI KB "How to Access Nigel AI",
LabVIEW Wiki (Nigel AI Advisor), Hampel Software Engineering wiki,
EDN/Electronic Design (2026), Zoomin API docs, reddit r/labview NI Week
2026 keynote notes.

## Troubleshooting

- `ClassFactory cannot supply requested class` / COM hangs → orphan
  LabVIEW instance with a modal dialog: `manage_processes` list → kill the
  64-bit one (`C:\Program Files\National Instruments\...`).
- Clicking "Don't Save" on untitled scratch VIs is always safe - they are
  automation artifacts, never user data.
- First `extract_vi`/`gateway` call spawns a background 64-bit LabVIEW
  (~15-60 s); later calls attach and are fast.
- VI Server TCP ports: x64 = 3364, x86 = 3363 (irrelevant for this server;
  it uses COM, not TCP).
- Working on a VI that is currently open in the user's LabVIEW instance
  is the STANDARD mode: COM attaches to the running instance, edits
  appear LIVE on screen and save from the same session. Extraction and
  read verbs still snapshot copies internally (uniform behavior). The
  user sees every change - coordinate before destructive edits.
