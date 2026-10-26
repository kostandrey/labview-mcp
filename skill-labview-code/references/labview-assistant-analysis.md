# Jan Goebel's "labview_assistant" (VI Scripting MCP Server) - analysis (2026-10-23)

Source: https://github.com/JanGoebel/labview_assistant (13 stars, 6 forks, 4
commits 2025-12-15 .. 2026-02-26, no LICENSE file). Local clone:
`_service\tmp\labview_assistant` (gitignored; study only - do not redistribute,
no license = all rights reserved).

**What it is**: a second independent implementation of the same idea as this
project - an MCP server that lets an LLM (tested with Claude Desktop) write
LabVIEW code through VI Scripting. Confirms the concept; worth mining for
techniques.

## Architecture (vs ours)

| | labview_assistant | labview-mcp (ours) |
|---|---|---|
| MCP endpoint | **pure LabVIEW** HTTP server (`MCP Server.lvlib`, port 36987, url `/mcp/server`), bridged to stdio clients via `npx mcp-remote` | Python `server.py` + COM to `Gateway.vi` |
| Scripting host | LabVIEW runs the server VI **in-IDE** (DQMH module, VI Scripting required) | Gateway runs inside LabVIEW via COM; edits appear live |
| Object addressing | integer **object IDs** (server keeps ID->ref map: `Add New Reference.vi`, `Get VI By ID.vi`, `Is Same Object.vi`) | resolver `%Class\|Label` paths |
| Security | **allowed-paths whitelist** (`config.json` Allowed Paths, checked on open/save) | none yet |
| Module pattern | DQMH request/reply events with `wait for reply` + timeout | sequential Gateway verbs |

## The 28 MCP tools (recovered from `Init MCP.vi` + Argument clusters)

new_vi, open_vi, save_vi, run_vi, set_value, add_object, add_subvi,
connect_objects, get_object_terminals, create_control, delete_object,
rename_object, cleanup_vi, add_to_selection / remove_from_selection /
clear_selection_list, **enclose_selection**, connect_to_pane,
get_vi_error_list, get_vi_blockdiagram (BD screenshot), Get VI Frontpanel
Picture, get_structure_diagram (subdiagram screenshot), get_object_help,
get-available-objects (full palette catalog), get_vi_description,
get_library (project/lib content), get_allowed_paths,
get_loop_conditional_terminal / get_loop_iteration_terminal /
show_conditional_terminal, create_project.

## Advanced techniques found (zlib-decompressed VI sections)

1. **enclose_selection - "wrap existing code in a structure"**: builds a
   selection from the ID list (`Make Selection`, `SelList[]`), then calls a
   scripting method named **`EncloseSelection2`** with `structure_type` +
   `location` (Horizontal/Vertical). `EncloseSelection2` does NOT exist in
   LV2020/2023 vi.lib - it is a newer (LV2024/2025) scripting primitive.
   This is the one capability neither our Gateway nor the plain
   `New VI Object` path has (we can only place into an EMPTY structure).
2. **Wiring** (`Wire Two Objects.vi`): `Get Terminals.vi` + **`Connect Wire`**
   with `Wire Source`, `Auto Wire? (T)`, `Wiring Specs`, `Auto Route? (F)`
   - same NI primitives as our Gateway `wire` verb. Comment in their code:
   "currently only supports wiring nodes or terminals".
3. **Screenshots**: `Do Get VI Blockdiagram.vi` = Diagram-class method
   **`BD.Get Image Scaled`** + `Draw Flattened Pixmap.vi` -> picture of ANY
   diagram/FP/structure subdiagram, returned to the LLM. We do this only via
   offline `extract_vi`; a live `screenshot` gateway verb would let the
   agent SEE the diagram it just edited.
4. **add_object by NAME**: drops objects using a `Class Specifier Constant`
   + the palette-name catalog (get-available-objects) - no style codes
   needed (ours: `any:<code>`).
5. **create_control(object_id, terminal_index, constant reply)**: creates a
   control/constant **auto-typed from a terminal** - generalizes our
   hand-picked per-type constant wiring.
6. **get_object_help**: live Context-Help text of any object in the IDE
   (we use the offline CHM mirror instead).
7. `Do Enclose Selection.vi` also embeds the full primitives catalog as a
   ring (the "what can I add" list).

## Verification limits

All VIs are saved in **LabVIEW 2025** (RSRC header `LVversion` 25.0; commit
dates line up). This PC has 2017-2023 only: `GetVIReference` fails with
0x465 "File version is later than the current LabVIEW version", so no
strings export / no local run. Analysis above is from binary zlib streams
(same technique as the Jake PPL: `lva_zlib.py` -> `lva_zlib\*_zlib.txt`).

## Ideas worth borrowing (roadmap candidates)

- **`screenshot` verb** for Gateway.vi (Diagram.Get Image Scaled -> PNG)
  - highest value: agent self-check of generated code.
- **auto-typed constant/control creation** from a terminal index.
- **allowed-paths whitelist** in server.py/Gateway (guardrail).
- `enclose_selection` - requires LV2025 `EncloseSelection2`; park until the
  dev PC has LV2025+.
- ID-based object handles: not needed for us (labels work and are
  LLM-friendlier), but the `Get VI By ID` pattern shows how to survive
  duplicate labels.
