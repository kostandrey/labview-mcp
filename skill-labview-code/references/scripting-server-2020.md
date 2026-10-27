# Scripting Server 2020 (Jan Goebel "labview_assistant" converted to LV2020)

Location in this repo: `scripting-server\` (RENAME 2026-10-27: the
folder was `scripting-server-2020\`; the 2020 mark was dropped since
this repo now keeps only LV2020-format VIs — newer LabVIEW opens them
if needed). It is the complete LV2020
conversion of https://github.com/JanGoebel/labview_assistant, made
2026-10-26 with `lv_batch_saveprev.vbs` "20.0", 242/242 files ok.
Upstream source clone: `_service\tmp\labview_assistant` (2025-format,
gitignored). **License: none upstream = all rights reserved.** Copied
into this LOCAL repo on explicit user instruction 2026-10-26; do NOT
push to any public remote. A `README.md` in the folder states this.

## 1. Dependence clarification (the two projects are fully independent)

| | `gateway\` (ours) | `scripting-server\` (theirs) |
|---|---|---|
| Purpose | generic VI-scripting verb host (analyze/wires/place/wire/loop/...) | DQMH module = session server: keeps an open-VI registry (Data Cluster: References variant + Current ID) and exposes 28 MCP tools |
| Runs | inside LabVIEW via COM (`SetControlValue`/`Run`), driven by our `server.py` | as a runnable app (`vi-scripting-server.vi`, HTTP MCP on port 36987) OR worker-by-worker via the same COM runner pattern |
| SubVI deps | `Clear Errors`, `ReferenceResolver`, `GetTerminal`, `SelectByUID/Label`, `Error_to_string`, `Get Errors Method` + native vi.lib (`Traverse for GObjects` in `traverseref.llb`) | only its own lvlib members + native vi.lib |

- **Gateway does NOT reference the Scripting Server** and vice versa
  (verified: Gateway subVI list vs Scripting Server lvlib members).
- `gateway2020\` (untracked, morning-session duplicate) was the SAME
  Gateway rev 183 converted again - both ping-verified; moved to
  `_service\tmp\gateway2020_duplicate\`. Canonical home: `gateway\`.
  2026-10-27: the repo keeps ONLY the LV2020-format `gateway\Gateway.vi`
  (the 2026-format original is backed up in
  `_service\tmp\Gateway2026_backup\`, git history has it too); the
  2020 mark was dropped from the name.
- The 2020 copy CONTAINS the Do Save VI fix (vi_id -> ID wire,
  verified `wires` on the copy). The upstream 2025 source still has
  the unfixed `Do Save VI`.

## 2. Ways to use it

1. **As the original MCP server**: open
   `scripting-server\VI Scripting Server.lvproj` in LabVIEW 2020,
   run `vi-scripting-server.vi`; point an MCP client at
   `http://127.0.0.1:36987/mcp/server` (see its readme.md). Not
   integrated with our `server.py` (they are two parallel MCP
   implementations).
2. **Worker-by-worker via COM** (the pattern proven in
   `labview-assistant-reuse.md` section 5): each `Do *.vi` worker has
   front-panel controls `Do X Argument` + `Data Cluster in/out`;
   `SetControlValue("<x> Argument", Array(...))` + `Run True` +
   Sleep 12-15s + read back. **Limitation discovered 2026-10-26:**
   workers RUN fine standalone (verified `Do Get Open VIs.vi`,
   run 0x0, argument readable) but session-dependent outputs are
   empty/meaningless outside the server context - the Data Cluster
   (open-VI registry with live refnums) cannot be created through COM
   variant arrays. Anything needing a vi_id/object_id chain requires
   an in-LabVIEW runner VI (like `exp13_runner.vi`), not a script.
   **Evening follow-up:** plain API members (`get-available-objects.vi`,
   `get_allowed_paths.vi`, ...) are NOT standalone-runnable at all -
   `Run True` fails 0x3EB (subVI not located / DQMH API context). Only
   the `Do *.vi` wrappers execute standalone. For the full 28-tool API
   run `vi-scripting-server.vi`.
3. **From our MCP server (v1.3.0+)**: the `lva_worker` tool wraps
   `mcp-labview/scripts/lva_worker.vbs` (32-bit cscript -> background
   32-bit LV2020) with the same set/read/sleep grammar; resolves bare
   filenames in `Scripting Server\`. Verified end-to-end 2026-10-26:
   `lva_worker Do Get Open VIs.vi` attached 20.0.1, ran, read back
   `[0; False]` (empty outside server, as expected).
4. **Adopted into OUR harness (2026-10-27, PROVEN)**: the workers are
   self-contained (no DQMH module needed) and the session is just the
   Data Cluster - so a gateway-built session runner VI (Feedback Node
   holds the cluster) can drive them per-call via COM. Spike
   `_service\tmp\lva_spike.vi`: two runs in one instance gave
   ViId=1 then ViId=2 (session works). Full recipe + codegen facts:
   gateway-recipe v3.37. Session caveat: the LabVIEW instance must
   stay alive between calls (user's open IDE = fine).

## 3. Capability comparison vs our Gateway

**Extra in the Scripting Server (no Gateway equivalent):**
- `run_vi` (Run VI Argument {VI ID, open_frontpanel}) - run an open
  session VI from the API
- `rename_object` ({new_label_name, label_visible}) - Gateway has no
  rename
- `get_object_help` (live Context-Help string; we use the offline CHM)
- `get-available-objects` (live full palette catalog; we use static
  `style_codes.json`)
- `get_vi_description`, `get_library`, `create_project`
- live screenshots: `get_vi_blockdiagram`, `Get VI Frontpanel Picture`,
  `get_structure_diagram` (per-subdiagram, via `BD.Get Image Scaled`)
- `get_allowed_paths` / `Set Allowed Paths` + the `config.json`
  Allowed Paths whitelist (guardrail idea for our server.py)
- `create_control` {Object ID, Terminal Index, Constant} - auto-typed
  control/constant from a terminal (Gateway: manual per-type wiring)
- `cleanup_vi` (block-diagram cleanup)
- persistent selection list (add_to/remove_from/clear) across calls
- ID-based object handles (survives duplicate labels)

**Extra in our Gateway (no server equivalent):** `wires` (broken
flags/isSource/UIDs), `getNode` per-terminal maps, `errors` (IDE error
list), `loop` verb (shift registers, tunnel index modes), setval XML +
representation codes, `arrread` typed FP I/O on saved VIs (cycle mode),
analyze class hierarchy. Addressing differs: Gateway resolves by
`%Class|Label` (+ `Case#`), server by integer IDs.

**Overlap, verified equivalent:** enclose (server: selection +
`EncloseSelection2`; Gateway: `Case#` resolver), wire (Get Terminals +
Connect Wire vs wire verb), delete, connect_to_pane (connector verb),
loop terminals (get/show cond/iteration verbs).

## 4. Argument clusters (module level; element order matters)

Dumped 2026-10-26 from `lva_strings_all\*Argument--cluster.ctl.txt`
(dump script `_service\tmp\dump_args.py`). Standard tail elements
(`Wait Notifier` 0x70 + `wait for reply`) omitted below; every worker
also has `Data Cluster in/out` + `error in/out` on its connector.

| tool | inputs | outputs |
|---|---|---|
| open_vi | vi_path:String | vi_id |
| new_vi | Open Frontpanel:Boolean | VI Reference:Numeric, Result:String |
| save_vi | vi_id:Numeric, path:String | path_out:String |
| run_vi | VI ID:Numeric, open_frontpanel:Boolean | - |
| set_value | object_id:Numeric, value:String | - |
| add_object | Object Name:String, position_x/y:Numeric | Object ID:Numeric, Result:String |
| add_subvi | diagram_id:Numeric, subvi_path:String, position_x/y | subvi_id:Numeric |
| connect_objects | from/to object reference + terminal index | - |
| delete_object | object_id:Numeric | - |
| rename_object | new_label_name:String, label_visible:Boolean | object_id:Numeric |
| create_control | Object ID, Terminal Index, Constant:Boolean | Value:String |
| add_to_selection | object_id:Numeric | Current Selection:Array, vi_id |
| remove_from_selection | vi_id, object_id | current_selection:Array |
| enclose_selection | vi_id:Numeric, structure_type:String | object_id:Numeric |
| connect_to_pane | control_id, connector_pane_index | - |
| get_object_terminals | object_id | terminals description:String |
| get_vi_error_list | vi id | error list:String |
| Get VI Blockdiagram / Frontpanel Picture | VI ID | (image) |
| get_structure_diagram | structure_id, index | diagram_id:Numeric |
| get_object_help | object_id | help_string:String |
| get-available-objects | - | available objects:String |
| get_vi_description | vi_id | Description:String |
| Get Library | Library Path:String | Library Content:String |
| get_allowed_paths | - | Allowed Paths:String |
| get_loop_conditional/iteration_terminal | loop_id | conditional/iteration_terminal_id |
| create_project | File Path:String | project_id:Numeric |

**Verified flat runner arrays** (driving `Do *.vi` FP Argument controls
directly via COM - see `exp13_run.vbs`):
- `open_vi Argument` = `Array(abs_path, Empty, False)`
- `save_vi Argument` = `Array(1, abs_path, Empty, False)` (explicit
  path MANDATORY - wired-empty is a silent no-op)
- `add_subvi Argument` = `Array(1, subvi_path, Empty, False, 200, 100)`
- `add_to_selection Argument` = `Array(2, Empty, False, 1)`
- `enclose_selection Argument` = `Array(1, "Case Structure", Empty, False)`

## 5. Correction to labview-assistant-analysis.md

The claim "EncloseSelection2 ... treat as 2024+ only" is WRONG. The
full chain (Open -> Add Subvi -> Add to Selection -> Enclose ->
Save) ran with ErrCode4=0 in a background 32-bit LV2020 and the SAVED
target contains the enclosed structure (`EncloseSelection2` resolves
in LV2020). See gateway-recipe v3.35/v3.36 and reuse section 6.

## 6. Verification of the copy (2026-10-26)

- `Do Open Vi.vi`, `Do Save VI.vi` analyze clean in 32-bit LV2020;
  `Do Save VI.vi` errors EMPTY + fix wire present (UID 595).
- `vi-scripting-server.vi` opens clean (no connector pane - GetControlValue
  by name not applicable, expected).
- Standalone `Do Get Open VIs.vi` run 0x0, argument readable, but
  output empty outside server context (see section 2 limitation).

## 7. What was borrowed into our harness (2026-10-26 evening)

- **`lva_worker` MCP tool** (server.py v1.3.0): wraps
  `mcp-labview/scripts/lva_worker.vbs`; drives one `Do *.vi` worker per
  call in the background 32-bit LV2020 (see section 2.3).
- **Allowed-paths guardrail**: `mcp-labview/allowed_paths.json`
  (whitelist of case-insensitive dir prefixes, default: the project +
  `%TEMP%\lv_mcp`) gates gateway write verbs, gateway_batch write
  lines and `delete;`/`copy;` meta-lines - borrowed from this
  server's `config.json` `Allowed Paths` whitelist. Delete the file
  (or empty the list) to run unrestricted.

## 8. Persistent session server REPLACES per-call worker runs (2026-10-27)

Section 2's limitation ("session-dependent workers return EMPTY
outside the server context") is SOLVED not by running
vi-scripting-server.vi but by our own persistent server:
`gateway\LVA\LVA Session.vi` (full story: gateway-recipe v3.38).
Workers `Do Open Vi.vi` / `Do Save VI.vi` run as subVIs inside a
while-loop server; the Data Cluster (vi_id registry) survives between
COM calls because a keeper process (lva_keeper.vbs) holds the
LabVIEW instance alive. MCP tool: `lva_session` (open_vi / save_vi).
Adding a lane = copy a boolean case + place the worker + an Argument
control inside the case + extend lva_call.vbs.

Gotcha carried over: the session VI must be driven with 64-BIT cscript
(32-bit client fails SetControlValue with 0x1B6 on it) - the opposite
of the single-worker lva_worker path which used SysWOW64.
