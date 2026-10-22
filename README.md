# LabVIEW MCP Workbench

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
