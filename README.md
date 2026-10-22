# LabVIEW MCP Workbench

> **Status: early-stage proof of concept.** This is a working toy that
> demonstrates the usage concept - it is far from fully functional or
> polished. The API, verbs and behavior may change at any time.
> **Community contributions are very welcome!**

Self-driving LabVIEW code generation: an MCP server (`mcp-labview/`) plus a
VI Scripting gateway (`gateway/Gateway.vi`) that let an AI agent create,
wire, verify and run LabVIEW VIs over COM - with an accumulated, verified
knowledge base (`skill-labview-code/`) covering terminal maps, error
causes, and proven build workflows.

## Video tutorials

Walkthroughs of the whole workflow (agent builds and debugs VIs live) are
on YouTube, playlist [**LabView MCP Server**](https://www.youtube.com/playlist?list=PLYLVsMsTUfQQ):

1. [01 Create vi and Pi calculation](https://www.youtube.com/watch?v=O2NeHFttuLk)
2. [02 Adding code to the same vi](https://www.youtube.com/watch?v=AKD4gJnjtME)
3. [03 RND with given PDF](https://www.youtube.com/watch?v=J5HpZgKXJW8)
4. [04 Getting the vi pseudocode](https://www.youtube.com/watch?v=7wYE4Ucc8dg)
5. [05 SumCalc](https://www.youtube.com/watch?v=yYM8KXf6l_M)
6. [06 FixError](https://www.youtube.com/watch?v=IZdGrHqf40s)

## How it works (inner architecture)

```
MCP client (Zed, Claude, ...)
   |  JSON-RPC over stdio (zero dependencies, Python stdlib only)
   v
mcp-labview/server.py  - 15 tools (gateway, gateway_batch, arrread,
   |                     extract_vi, getval, docs & knowledge lookups, ...)
   |  cscript drivers -> COM: CreateObject("LabVIEW.Application")
   v
gateway/Gateway.vi  - runs INSIDE the LabVIEW IDE
   |  VI Scripting primitives (New VI Object, Terms[], Connect Wire, ...)
   v
target .vi files - created, wired, set, analyzed and run
```

- **VI Scripting is the foundation.** The server accesses the LabVIEW IDE
  through its VI Scripting functionality, which must be enabled in the
  LabVIEW settings (*Tools > Options > VI Server > Enable VI Scripting*).
  These scripting primitives only execute *inside* LabVIEW - external COM
  cannot call them. That is exactly why the `Gateway.vi` helper exists:
  it is a small VI running inside the IDE whose front panel is driven over
  COM (`SetControlValue` -> `Run` -> read `result`).
- **Gateway.vi is currently the main limiting factor.** It implements one
  block-diagram case per verb (`place`, `wire`, `setval`, `getval`,
  `analyze`, `wires`, `errors`, `delete`, `loop`, `connector`, ...). To
  support a new tool/capability, a new case has to be created *there* -
  this is where contributors with LabVIEW skills are most valuable.
- **Drivers**: `lv_gateway.vbs` (single verb) and `lv_gateway_batch.vbs`
  (scripts: `verb;vi_path;arg1;arg2;arg3` lines) attach to (or spawn) the
  user's 64-bit LabVIEW instance, so edits appear live in IDE-open VIs.
  Read verbs snapshot a temp copy of the target `.vi` first; write verbs
  edit and save the real file (`Save:Instrument`).
- **`arrread.exe`** (C#, dynamic IDispatch) handles typed front-panel
  value I/O - any numeric representation, strings, booleans, 1D/2D
  arrays, clusters. Its `cycle` mode does set + echo + run + poll-read in
  ONE process (the only reliable pattern for live FP values).
- **Element values travel as flattened data**: `getval`/`setval` use
  *Variant To Flattened String* - a type-descriptor I16 array plus the
  data bytes HEX-encoded in an XML reply, decoded by `lv_flat.py` (any
  type: scalars, strings, paths, enums, arrays, clusters).
- **Static analysis**: `extract_vi` runs `lv_extract2.vbs` (VI strings
  export + HTML report + a PNG of the front panel, block diagram and
  every case) on a temp copy - never the original.
- **Documentation stack**: an offline mirror of the installed LabVIEW
  CHM help (`search_docs`/`read_doc`), NI's web documentation via an
  unofficial keyless backend (`search_ni_docs`/`fetch_ni_doc`, used
  sparingly), and the verified knowledge base
  (`search_knowledge`/`lv_reference` over `skill-labview-code/`).

## Layout

| Path | Purpose |
|---|---|
| `mcp-labview/server.py` | MCP stdio server (13 tools: gateway, gateway_batch, arrread, extract_vi, search_docs, search_knowledge, ...) |
| `mcp-labview/scripts/` | Gateway drivers (`lv_gateway.vbs`, `lv_gateway_batch.vbs`) and composite helpers (`lv_loop_scaffold`, `lv_fn_wire`, `lv_tunnels_regular`, `lv_verify`, `lv_runcheck`, `lv_extract2`) |
| `gateway/` | `Gateway.vi` + subVIs (GetTerminal, ReferenceResolver, SelectByUID/Label, Error_to_string) - the VI Scripting workhorse |
| `skill-labview-code/` | The skill: `SKILL.md` (operational rules), `references/gateway-recipe.md` (versioned session history + build sheets), `references/subvi-placement.md`, driver scripts, `arrread` |
| `gen/` | Golden generated VIs (`pi_golden3/4`, `sr_golden`) and their build scripts - the regression examples |
| `style_codes.json` | LabVIEW style-code table (byName/byCode) for `place any:<code>` |
| `help/` | Offline NI documentation mirror (gitignored - see below) |
| `_service/` | Gitignored service area: extract results, temp copies, deprecated items |

## Setup

1. LabVIEW (2020+, 64-bit) with VI Scripting enabled.
2. Install the MCP server (stdlib-only, no dependencies):

   ```
   pip install mcp-labview/
   ```

   This provides the `labview-mcp` command. All asset paths are anchored on
   `LABVIEW_SKILL_ROOT` (default `C:\LabView skill`) - set it if the checkout
   lives elsewhere. You can also run the server in-place without installing:
   `python mcp-labview/server.py`.

3. Register the MCP server in the client (e.g. Zed `context_servers`):

   ```json
   "context_servers": {
     "labview-mcp": {
       "source": "custom",
       "command": "<python.exe>",
       "args": ["C:\\LabView skill\\mcp-labview\\server.py"]
     }
   }
   ```

   or, when installed, `"command": "labview-mcp"` with empty args.

4. Read `skill-labview-code/SKILL.md` before generating any code.

## Note on `help/`

`help/` is a local mirror of the installed LabVIEW documentation used by
`search_docs`/`read_doc`. It is gitignored (size/copyright) - keep it
local; the rest of the toolset works without it.
