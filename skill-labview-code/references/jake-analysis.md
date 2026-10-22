# JKI Jake ("GAIA") - black-box architecture analysis (2026-10-22)

How JKI's AI LabVIEW assistant ("Jake") works, from static analysis of the
local install `C:\Program Files\JKI\Jake` (strings export of the exes +
zlib-decompressed `ppl\win_64\gaia.lvlibp`; no source needed).

## Components

| File | Role |
|---|---|
| `jake.exe` | Tauri (Rust) desktop app: chat UI + a webview that renders the VI diagram (`/diagram/labview/index.html`); user-agent `gaia-jake-ai/0.1` |
| `jake-service.exe` | local agent service (LLM orchestration) |
| `llb\jki-gaia.llb` | **QuickDrop plugin** - the in-IDE entry point (installed to `Documents\LabVIEW Data\Quick Drop Plugins`) |
| `ppl\*\gaia.lvlibp` | the in-IDE workhorse library ("GAIA") - **this is their Gateway equivalent** |

## Answer: YES - same core approach as our Gateway

Strings in `gaia.lvlibp` (decompressed): *"VI Scripting is not enabled and is
required for this tool to work. Please enable it in the VI Server section of
the LabVIEW Options."* - identical prerequisite. It uses the same NI
primitives: **New VI Object**, **Connect Wire**, `Wire.Terms[]`,
`input to Traverse for GObjects.vi` (the SAME traversal primitive our
ReferenceResolver/GetTerminal chain uses), Front Panel/Block Diagram
property nodes, plus *"Check if VI Scripting is Enabled.vi"* (pre-flight
check) and *"Wait For / Generate Front Panel Activity"* +
*"Keep this VI running for LabVIEW Tools Support"* (a persistent in-IDE
process).

## Its transport and command vocabulary

The plugin runs a **TCP server inside the IDE**
(`TCP Server Launch Listener Process.vi`, `wait_on_command`,
`respond_to_command`, `start_service`) that the agent service drives.
Command/verb names found (snake_case, its "tool" API):

- context/introspection: `get_active_vi`, `get_active_vi_selection_list`,
  `get_selection_as_png`, `get_image_for_gobject`,
  `get_master_rectangle_of_gobjects`, `get_selection_area`,
  `get_class_schema`, `get_lv_class_information`,
  `get_object_methods`, `get_object_properties`,
  `vi_server_property_info`, `get_method_detailed_info`,
  `get_name_of_labview_datatype`, `get_project_information`
- object manipulation: `new_vi`, `new_vi_object`,
  `open_vi_reference_by_path/name`, `gobj_get_pos`/`gobj_set_pos`,
  `gobj_get_property_by_name`/`gobj_set_property_by_name`, `set_base_type`,
  `read_vi`, `test_if_tracked_vi`
- bridge: `python_command` (+ `jki_python_data_tools.lvlib` - Python
  String to LabVIEW Data) - it can call Python from inside the IDE.

## Comparison with our labview-mcp

| Aspect | Jake/GAIA | labview-mcp (ours) |
|---|---|---|
| Prerequisite | VI Scripting enabled | same |
| In-IDE code | QuickDrop plugin + PPL library + TCP server (persistent, event-driven) | `Gateway.vi`, one case per verb, driven per-call over COM |
| External driver | jake-service.exe (proprietary agent) | MCP server (any MCP client) + .vbs drivers |
| Wiring | `gobj_set_property_by_name`-style property manipulation | terminal-index wiring (`c/n/i/st/s*` kinds) with per-terminal isSource feedback |
| LLM context | rich introspection: PNG per object, rectangles, class schemas, JSON | whole-VI extract PNGs + strings exports + verified knowledge base |
| Verification | (not visible from strings) | wires/errors verbs, arrread run-verify, golden regression VIs |

## Ideas worth borrowing

1. `get_selection_as_png` / `get_image_for_gobject` - per-object images are
   much cheaper than whole-VI extracts for agent vision loops.
2. `get_class_schema` / `vi_server_property_info` - feed the model exact
   property/method names instead of hard-learned tables (we record them in
   style_codes.json / lv_knowledge.json; a live introspection verb would
   generalize this).
3. A persistent TCP listener in Gateway.vi would remove the per-call
   COM open/close overhead (minor - our attach is already fast after warm-up).
4. Pre-flight "is VI Scripting enabled" check with a clear error message.

(Black-box analysis: the .llb is just the launcher; all logic lives in the
compressed PPL. No decompilation of the block diagrams was done.)
