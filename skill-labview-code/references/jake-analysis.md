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

## Internet research (2026-10-22, public sources)

- **jki.net/jake** (official): Jake = "Your LabVIEW AI Assistant"; three
  pillars: Smart Assistant (Q&A), Error Detective, Resource Navigator
  (find example VIs, VIPM packages). Free tier + Pro $30/mo + Team.
  "Connect Jake to your LabVIEW IDE (desktop only)" confirms the
  desktop-app-to-IDE link.
- **Usage (kreiseder.org, 2024-11 beta + 2025-01 features)**: install via
  nipkg (NI Package Manager); in the IDE open Quick Drop (Ctrl+Space) and
  press **Ctrl+G** to open "Jake's LabVIEW Helper"; "launch jake" opens
  the web chat **connected to your VI** ("What LabVIEW version am I using?",
  "What do you see on the block diagram of my VI?"). Matches the
  QuickDrop-plugin + service architecture found in the binaries.
- **Release notes (support.jki.ai)**: 2024-11-07 beta through
  2025-03-22 "LabVIEW Example VI Search"; notable:
  Multi-VI Analysis (2024-12-12), Project Analysis (2024-12-20),
  DAQ/FPGA/RT/VISA knowledge drops, "Enhanced LabVIEW Connectivity"
  (2025-02-27, "status updates when Jake is using LabVIEW to analyze
  code").
- **User guide**: analysis/documentation/visualization focused (code
  review, performance analysis, state-machine and class-hierarchy
  diagrams via "Format Class Name for Mermaid"-style introspection) -
  NO code-generation claims anywhere.
- **NI forums (2025-04/09)**: "Jake cannot generate code"; NI's own
  codegen AI is **NIGEL** (shipped later, roadmap
  ni.com/en/shop/software-portfolio/software-roadmaps.html).

**Positioning vs labview-mcp**: Jake = commercial, cloud-LLM, analysis /
Q&A / review assistant with deep IDE introspection, but (at least through
2025) NO code generation. Our project is the opposite bet: agent-driven
CODE GENERATION and verification - rougher UX and fewer introspection
niceties, but it actually writes and runs VIs. Borrow-worthy: their
introspection verbs, per-object images, and the pre-flight
scripting-enabled check; ours to keep: the write-path verbs and the
knowledge base.

## Update 2026-10-22 (later): full LLB unpack - final verdict

The 4 member VIs + 1 .ctl of `jki-gaia.llb` were fully extracted with
LabVIEW COM (`GetVIReference` + `SaveInstrument saveACopy=True`; recipe in
labview-automation.md section 10, artifacts in `_service\tmp\jake_unpacked\`).

Result confirms the earlier assessment - **nothing new is reusable**:

- `jake_constants_cluster.vi/.ctl`: a config cluster only - paths to the
  helper launcher, helper ppl, app folder, app binary, service binary +
  `arch suffix` string. No ports/URLs (the "20008" seen in strings is
  `LVversion=20008000`, not a port).
- `gaia_launcher.vi` / `gaia_launcher_core.vi` / `G AI Assistant.vi`:
  QuickDrop plugin boilerplate (QD Launch VI Ref, error clusters). Their
  block diagrams are PASSWORD-LOCKED - `ExportVIStrings` returns front
  panel only, no `<BD>`/primitives. All real logic stays in the locked
  compressed PPL.

So the borrowable ideas remain the ones already listed above (per-object
images, live property introspection, pre-flight scripting check, TCP
listener); no Jake file is copied into the repo (proprietary, unusable
standalone).
