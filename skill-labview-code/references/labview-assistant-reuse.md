# labview_assistant - reuse study (2026-10-26, code fully readable)

Companion to `labview-assistant-analysis.md`. After the LV2026->LV2020
one-hop downconvert (242/242 files, `_service\tmp\lva_2020_tree`) every
VI of https://github.com/JanGoebel/labview_assistant is readable with our
standard tooling. This doc answers: what is worth implementing, which
FILES can be reused instead of modifying Gateway.vi, and what is not
worth taking.

## 1. Architecture (decides reusability)

    MCP tool VI (add_object.vi etc., DQMH request + wait for reply)
      -> Scripting Server module (Main.vi, DQMH MHL, runs IN the IDE)
        -> "Do X.vi" WORKER VIs (the actual scripting logic)
             args: "<tool> Argument" cluster (typed .ctl)
                   + "Data Cluster in/out"  (module state = ID->ref map)
             out:  tool-specific outputs (object_id, new reference, ...)
      helpers: Add New Reference.vi, Get VI By ID.vi, Is Same Object.vi
               (the integer-ID indirection), Load VI.vi, Create New VI.vi

Key fact: the workers are NOT pure functions - they thread the module
state cluster through. But the state is just {References[], Current ID,
Status}; a caller can maintain it externally (start empty, feed refs via
Add New Reference). So the workers ARE reusable standalone.

## 2. Worker inventory (connector + verified internals)

| Worker | Key scripting calls (verified via strings/PNGs) | Verdict |
|---|---|---|
| Do Enclose Selection | `Diagram.Make Selection(Objects[])` -> `Diagram.EncloseSelection2(EnclosureType)`; on error deletes the struct | GOLD - capability we lack; needs LV2024+ runtime |
| Wire Two Objects | `Get Terminals.vi` + `Connect Wire` (Wire Source, Auto Wire?, Wiring Specs, Auto Route?) | same as our `wire` verb; DQMH-flavored - keep ours |
| Do Create Control | `Get Terminals` -> `Term.IsSource` case -> `Create Indicator` / control / constant on the terminal -> `Add New Reference` | GOLD - auto-typed constant/control from terminal (we hand-pick types today) |
| clean up vis blockdiagram | `VI.BlockDiagram` -> `BD.CleanUp` | GOLD - one call, zero risk, big readability win |
| Do Get VI Blockdiagram / Frontpanel Picture | `BD.Get Image Scaled` + `Draw Flattened Pixmap.vi` -> picture of BD/FP/subdiagram | GOLD - agent self-verification; `Get Image` is scripting-only (NOT in axprop COM list) |
| Do Get Object Help | `Node.GetObjHelp/HelpPath/HelpTag` | WEAK - author's own `#todone`: "help property only outputs empty help path for basic nodes" - our CHM mirror is better |
| Do Get Structure Diagram | picture of a structure's subdiagram (Get Image family) | useful variant of screenshots |
| Do Get Cond/Loop Iteration Terminal | traverse loop border terminals | minor (we wire st1/i directly) |
| Do Add Subvi | `New VI Object` with subVI path + position | matches our `place` subVI mode |
| Do Get Library | enumerate project/lib content | nice introspection (our lv_extract2 is offline equivalent) |
| Do Set Value / Rename / Delete Object | property writes / GObject.Delete | we have setval/delete |
| Do Get Open VIs | app windows | minor |

Also present: full palette-name catalog (get-available-objects ring)
- a NAME-based alternative to our style codes; `Set Allowed Paths.vi`
whitelist (security idea for server.py); `Test_*.vi` examples.

## 3. Reuse paths (ranked)

**A. Drive the worker VIs via COM - ZERO Gateway.vi changes.**
`GetVIReference(worker)` -> setval XML the Argument cluster (v3.31
supports clusters) -> `Run` -> `GetControlValue` outputs. Because the VI
runs INSIDE LabVIEW, its scripting invoke nodes execute natively - same
trick as our Gateway, but reusing their code. Works in the 2020 instance
for everything EXCEPT enclose (`EncloseSelection2` needs LV2024+
runtime: run that one in the 2026 instance while it exists; long-term
needs a 2024+ runtime or a Gateway verb after upgrade).
Feasibility proven by existing tooling: arrread cycle + setval XML +
run_vi_get_value.vbs.

**B. Copy the workers into the gateway project as subVIs** (user wires
each once; static, no dynamic-ref typing problems). Cleanest long-term
but requires the user's LabVIEW work - do it only for the 3-4 keepers.

**C. Native Gateway verbs** for: `screenshot` (BD.Get Image Scaled),
`enclose` (Make Selection + EncloseSelection2), `cleanupBD`
(BD.CleanUp), `createControl` (terminal-typed). Same runtime caveat for
enclose. Only worth it if A proves the value during the trial.

**Not reusable**: the DQMH request wrappers (wait-for-reply -> need
their module running), MCP-over-HTTP server (we have stdio), Tools/
(MCP-toolkit boilerplate), the Python bridge.

## 4. Recommended first move (during the trial)

1. Prove path A on 3 workers in the 2026 instance: `clean up vis
   blockdiagram` (trivial), `Do Get VI Blockdiagram` (screenshot!),
   `Do Enclose Selection` (the crown jewel - verify EncloseSelection2
   actually runs and what EnclosureType wants: a Structure-class ref).
2. If proven: ask for ONE generic Gateway verb `RunWorker(<path>,
   <argClusterXML>, <outCtrl>)` = open+set+run+read in one process -
   then all 28 tools become available without per-verb Gateway work.
3. Adopt in server.py regardless: allowed-paths whitelist idea.
4. Skip: get_object_help (our CHM stack wins), ID-map (labels are
   LLM-friendlier).

## Artifacts

- Converted readable tree: `_service\tmp\lva_2020_tree` (2020, opens clean)
- Strings (FP+BD): `_service\tmp\lva_strings_all` (242 files)
- zlib token dumps: `_service\tmp\lva_zlib_all` (244 files)
- Extracted reports/PNGs of 10 key workers: `_service\tmp\lva_extracted`
- Scripts: `lva_strings_all.vbs`, `lva_extract_inplace.vbs`,
  `lv_batch_saveprev.vbs`, `lva_zlib_all.py` (all `_service\tmp`)

## 5. Enclose-chain field test (2026-10-26, LV2020 runners) - RESULT

Tested the crown-jewel chain natively in LV2020 with gateway-built runners
(exp13-17, `_service\tmp`):

- **OpenVI -> AddSubvi -> AddToSelection -> EncloseSelection: ALL WORK**
  (ErrCode taps 0; subVI placed + enclosed on the real target - hierarchy
  print proves it). The runner pattern: FP arg-cluster controls set via
  COM (Empty for 0x70 notifier elements), Run True, Sleep 12-15s, read
  ErrCode taps. Details: gateway-recipe v3.35.
- **Do Save VI is BROKEN**: Save:Instrument -> 1026 "VI Reference is
  invalid" (pristine wiring) or 1507 "Cannot change the name or path..."
  (after any rewiring), reproducibly, in LV2020 AND LV2026. The disk
  target is never written. ~10 input combinations tested
  (path wired/empty/unwired x Save a Copy T/F). Wired-empty path =
  silent no-op; UNWIRED path = 1026 despite docs claiming
  "default = current location".
- Stopped per the "works incorrectly -> user checks the code" rule.
  Prime suspect: the tunnel/argument delivery into Do Save VI's Invoke
  node; needs manual IDE review of `Do Save VI.vi` (and possibly
  `Do Open Vi.vi`'s Open VI Reference options).

## 6. Do Save VI ROOT CAUSE + FIX (2026-10-26 evening, autonomous)

**Root cause (proven, present in the SOURCE library itself, NOT
conversion damage):** `Do Save VI.vi` unbundles `save_vi Argument`
into `vi_id` + `path` and wires ONLY `path` (-> String To Path).
**`vi_id` is left UNWIRED**, so `Get VI By ID.vi`'s `ID` input
defaults to 0. `Get VI By ID` looks up
`Get Variant Attribute(References, Number To Decimal String(ID))`
= attribute "0" - never exists (Add New Reference stores under the
POST-increment Current ID: keys "1","2","3"...) -> empty variant ->
coerces to **Not A Refnum 0x00** -> Save:Instrument -> **1026**.
The user's probe confirmed: References map had '1'->FA90001C etc.,
yet Get VI By ID output Not A Refnum.

Red herrings (both measured, neither causal):
- The case-structure tunnel into the Invoke is fine; the 1026->1507
  change seen after a tunnel rewire was just a different failure of
  the same null ref + wired path.
- `Forbidden=True` probe: with an EMPTY Allowed Paths list
  `Is Allowed Path` returns allowed=True, so the save case correctly
  executes.

**The fix is ONE WIRE:** `vi_id` (Unbundle By Name output) ->
`Get VI By ID.vi` `ID` input. On the BD node: Unbundle By Name
Term[1]='vi_id' -> Get VI By ID node Term[10]='ID'
(wire verb: `Unbundle By Name|Get VI By ID.vi n|1|n|10`).

Applied + verified autonomously (no user in the loop):
- `lva_2020_tree\Scripting Server\Do Save VI.vi` edited via the
  repaired 2020 Gateway (see gateway-recipe v3.36); backup:
  `_service\tmp\DoSaveVI_backup_pre_fix.vi`.
- Full chain rerun (exp13 runner, 32-bit background 2020):
  ErrCode1-5 = **0**, LastID=3, **DISK target written** (mtime
  changed), saved target contains 1x while_st.vi inside the enclose
  case + the pre-existing Case1 (gateway analyze on the saved file).
- Wired-EMPTY path to Save:Instrument is still a silent no-op ->
  always pass an EXPLICIT path in save_vi Argument (the runner now
  does; the runner script sets ArgSave=Array(1,<abs path>,Empty,False)).
- **The 2026 SOURCE tree (`_service\tmp\labview_assistant`) still
  has the bug.** If the tree is ever re-converted from source,
  re-apply this wire (or fix the source first). Same applies to any
  fresh lv_batch_saveprev conversion.

Worker internals verified this round:
- `Do Save VI`: save_vi Argument={vi_id,path,WaitNotifier,wait};
  Invoke Save:Instrument(Path to saved file, Save a Copy, Without
  Diagram); path element goes through String To Path; Is Allowed Path
  gates the True case.
- `Do Add To Selection`: Get VI By ID + Get GObject by ID ->
  Property Diagram.SelList[] + Invoke Make Selection(Objects).
- `Do Enclose Selection`: Get VI By ID -> Diagram; New VI Object
  (Structure class specifier); Make Selection; EncloseSelection2
  (EnclosureType = the created structure ref); **Struct.Delete** (the
  temp structure); Add New Reference. NOTE: enclose leaves the target
  in a state where ANY wired-path save returns 1507 (measured), so
  save-after-enclose needs its own fix once Do Save VI works at all.
