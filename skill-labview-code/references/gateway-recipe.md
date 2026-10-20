# Gateway.vi - build sheet (one-time, ~10 minutes)

> **TOPIC INDEX (grep this file by section, do not read linearly - it
> is ~2000 lines of chronological session history):**
> build sheet v1 (ping/analyze) - L30; v2 `wires` spec - L170;
> v3 build sheet newvi/place/wire - L270; loop terminals/SR kinds - L400;
> tunnel verb + SELECT TYPE RULE - "v3.8"; arrread array in/out - "v3.9";
> FP objects inside structures + delete verb + UIDs - "v3.12";
> SHIFT REGISTERS (addSR, sli/slo/sri/sro) - "v3.13"; errors verb (IDE
> error list; VI Server cannot) - "v3.14"; wire isSource/Name response -
> "v3.15" + FP ITEM SIZE RULE; subVI placement (any:0<path>, cell
> numbering) - "v3.16" (pane tables in references/subvi-placement.md);
> getNode verb - "v3.17"; field notes (ForLoop-SR Terms, 1092/1093,
> autowire trap, proven order) - "v3.18"; FN per-instance rule +
> special constants (Pi/2pi) + branching tunnels - "v3.20"; wires
> terminal format `Label(UID) of Node{UID,Label}` - "v3.19". FN maps:
> "FN terminal map" (v3.7 area). Golden builds: pi_golden3/4 (v3.11),
> sr_golden (v3.13), sortArr (v3.9).

Gateway.vi is a tiny helper VI that runs **inside** LabVIEW and does the VI
Scripting work that external COM cannot reach directly (block-diagram
traversal, node properties). The agent drives it with
`scripts/lv_gateway.vbs` over COM: set controls -> run -> read `result`.

Protocol (deliberately strings-only - no JSON parsing nodes needed):

| Object | Kind | Meaning |
|---|---|---|
| `verb` | string control | `ping` \| `analyze` \| `wires` \| `listmem` \| `newvi` \| `place` \| `wire` |
| `vi path` | string control | target VI path (**string**, not Path control - the COM driver sets strings; convert with String To Path inside the VI). For `newvi` leave empty |
| `arg1` | string control | v1-v2: spare. v3: `newvi` save path, `place` type, `wire` `srcLabel\|dstLabel` |
| `arg2` | string control | v3 only: `place` `"x,y"` location or `"x,y,W,H"` (W,H = growable bounds / FP-item size, non-zero for FP objects), `wire` `srcKind\|srcIdx\|dstKind\|dstIdx` |
| `arg3` | string control | v3 only: `place` label for the new object (`-` = none) |
| `result` | string indicator | line-based reply, printed to stdout by the driver |

**Labels must match exactly** - the driver addresses controls by label
(`SetControlValue "verb"`, `GetControlValue "result"`).

**Golden rule: no dialog VIs inside the Gateway** - no Simple Error
Handler, no One/Two/Three Button Dialog, no File Dialog. A modal dialog
blocks the COM `Run` and hangs the whole pipeline (this is exactly how the
"Save changes?" orphan-dialog problem starts). Use **Clear Errors** and
write error text into `result` instead.

Save the VI as `C:\LabView skill\gateway\Gateway.vi` (create the folder).
Either LabVIEW bitness works for building it; the file is opened later by
the 64-bit instance that COM spawns.

## Front panel

1. String Control -> label `verb`
2. String Control -> label `vi path`
3. String Control -> label `arg1`
4. String Indicator -> label `result`; right-click -> Visible Items ->
   Vertical Scrollbar

## Block diagram

Place a **Case Structure** wired to `verb`, with cases `ping`, `analyze`,
`listmem`, and leave one case as the default (writes an error line for
unknown verbs).

Tunnel notes (classic stumbling block):

- The `vi path` control is used only by `analyze`; on the other cases leave
  the tunnel unwired and set right-click -> **Use Default If Unwired**.
- The `result` output tunnel must be wired in **all four** cases.

### Case `ping`

`result` <- Concatenate Strings("pong ", Get Date/Time String)

### Case `analyze` (the core)

1. **String To Path** (Programming > String): input <- `vi path` tunnel.
2. **Open VI Reference** (Programming > Application Control): path <- String
   To Path; leave `options` unwired (front panel stays closed); output:
   `vi ref`.
3. **Property Node**: wire `vi ref` in; select property **BlockDiagram**;
   output: `BD ref`.
4. **Traverse for GObjects.vi** - Programming > Application Control >
   **VI Scripting** palette (file:
   `vi.lib\Utility\traverseref.llb\Traverse for GObjects.vi`).
   Connector pane (verified from the LabVIEW 2020 documentation):

   | Side | Terminal | Wiring |
   |---|---|---|
   | in | `Other Refnum` | leave unwired |
   | in | `Traverse Target` (enum: 0=FP, 1=BD, 2=Other) | Create Constant -> select **BD** |
   | in | `VI Refnum` | <- `vi ref` |
   | in | `Class Name` (string) | constant **`GObject`** (= every object type; use `Function`, `Structure`, `Wire` to filter later) |
   | in | `error in` | <- error chain from Open VI Reference |
   | in | `Traverse Generated Code` | leave FALSE |
   | out | `dup VI Refnum` | unwired |
   | out | `References` (1D array of GObject refs) | -> For Loop auto-index |
   | out | `# of Refs` (I32) | -> header line |
   | out | `error out` | -> error capture (step 7) |

   `References` returns generic GObject refs - fine for ClassName / label.
   `To More Specific Class` is only needed for class-specific
   properties later (v2 wiring work).

   WARNING: do NOT read `Owner` here. For top-level BD objects the owner
   is the VI itself -> a VI-class refnum, and a GObject Property Node on
   it throws Error 1055 (0x41F object reference is invalid) as a modal
   dialog that blocks the COM Run. If owner info is ever needed, guard
   the read (Not A Number/Path/Refnum? + To More Specific Class to
   GObject) and fail soft.

5. **For Loop** with `References` auto-indexed at the border. Inside, per
   object:
   - **Property Node** (GObject ref) -> **ClassName** -> string.
   - **Get GObject Label.vi** (same VI Scripting palette, same
     `traverseref.llb`): GObject ref in -> label string out (equivalent to
     Label.Text). Wire its `error out` into **Clear Errors** so an object
     without a label cannot poison the error chain.
   - **Format Into String** - format string `%d: %s [%s]`, inputs:
     loop index `i`, ClassName, label -> line string
     (auto-indexed out of the loop).
   - **Close Reference** on the GObject ref (after the reads above).
   - Leave the loop-body property error clusters unwired (properties run
     regardless); only Get GObject Label gets Clear Errors. Keeps the build
     simple and dialog-free.
6. After the loop: **Array To Spreadsheet String** with delimiter = empty
   string constant -> joins the line strings with end-of-lines.
7. Error capture: Traverse `error out` -> **Unbundle By Name**
   (status, code, desc) -> **Select**: status TRUE ->
   Format Into String `"ERROR %d: %s"` (code, desc); FALSE -> the joined
   lines from step 6. That string goes toward `result`.
8. Header (recommended): **Concatenate Strings**
   `"verb=analyze  vi="`, `vi path`, `"  objects="`,
   **Number To Decimal String**(`# of Refs`), **End Of Line** constant,
   step-7 output -> `result`.
9. **Close Reference** on `BD ref`, then on `vi ref`.

### Case `listmem` (experimental)

1. **Property Node** with unwired input (class = this VI) -> property
   **Application** -> app ref.
2. **Property Node** (app ref) -> **AllVIsInMemory** -> array of paths.
3. **Array To Spreadsheet String** (empty delimiter) -> `result`.
4. **Close Reference** on the app ref; error out -> **Clear Errors**.

(AllVIsInMemory was denied 0x408 on the COM-side application object, but
running inside LabVIEW it may be allowed. If `result` comes back empty,
the verb simply stays experimental.)

### Default case

`result` <- Concatenate Strings("ERROR: unknown verb: ", `verb`)

## Connector pane (optional but recommended)

Right-click the pane (4x2x2x4 pattern): wire `verb`, `vi path`, `arg1` on
the left, `result` on the right. The COM driver does not need the pane,
but it makes the Gateway reusable as a subVI.

## Test checklist (the agent runs these)

```
cscript //nologo "C:\LabView skill\skill-labview-code\scripts\lv_gateway.vbs" "C:\LabView skill\gateway\Gateway.vi" ping
```
expect: `pong <date/time>`

```
cscript //nologo "C:\LabView skill\skill-labview-code\scripts\lv_gateway.vbs" "C:\LabView skill\gateway\Gateway.vi" analyze "C:\LabView skill\_service\extract\TMC current (copy).vi"
```
expect: one line per block-diagram object of the (copy of the) real VI.
Any VI works - including one open in the user's LabVIEW (live mode);
read verbs snapshot a temp copy internally.

Notes:

- The first call spawns a background 64-bit LabVIEW (15-30 s); later calls
  attach to it and are fast. The instance deliberately stays alive between
  calls (fast repeated queries).
- After **editing** Gateway.vi on disk, kill the background instance so the
  next call loads the fresh copy: `scripts/lv_procs.ps1` prints
  `pid=N path=...`; `taskkill /PID <pid> /F` the one under
  `C:\Program Files\National Instruments\` (64-bit).
- Any "Save changes?" prompt for Gateway.vi -> Don't Save is always safe.

## v2 - `wires` verb (IMPLEMENTED - wire-centric; revised after the first
node-centric design proved lossy)

Driver support is already in place (`lv_gateway.vbs` passes any verb
through; the MCP server accepts `wires`). Output: one line per wire - a
real directed connectivity graph.

### Implementation (as built)

Case `wires` (same opening as analyze: String To Path -> Open VI Reference
-> wire the VI refnum straight into Traverse `VI Refnum`, Target = BD) but
with **Class Name = `Wire`**:

1. **For Loop** over the wire references (auto-indexed):
   - **To More Specific Class**, target = Class Specifier Constant **Wire**.
     REQUIRED - Traverse returns generic GObjects and `Terminals[]` only
     exists on the Wire class. The Class Name constant and the cast target
     must describe the SAME class: with Class Name = `Wire` but the body
     still casting to Node, the cast raises error 1057 "Object cannot be
     cast to the specified type" at run time.
   - **Property Node** (Wire class): `Label.Text` (wires can carry a
     label), `Broken`, `Terminals[]`.
   - Wire-level format string `%s: label:"%s" broken: %d ->> `
     (ClassName "Wire", label, Broken through **Boolean To (0,1)**).
   - **Inner For Loop** over `Terminals[]` (auto-index). Per NI docs
     (Terminals[] property): "The first reference is the source if a
     source exists" - so terminal 0 is the source and the arrow prints in
     dataflow direction.
     a. **Not A Number/Path/Refnum?** on the terminal ref -> **Case**:
        TRUE -> constant string `null terminal`; FALSE -> continue.
     b. **Property Node** (Terminal class) -> `Owner`, `IsSource`, `Name`.
     c. `Owner` -> **To More Specific Class** (target = **Generic**) ->
        `ClassName` = the OwnerClassName field. Observed: `Function` for
        primitive/subVI terminals; `TopLevelDiagram` for front-panel
        control/indicator terminals (the terminal's owner reports as the
        diagram, NOT the control).
     d. **Get GObject Label.vi** (stock subVI) fed with the TERMINAL
        itself -> the Label field. For control terminals this returns the
        control's label (the terminal mirrors it); for primitive
        terminals usually "" - primitives' terminals carry no label, the
        terminal Name is the identity (`x`, `y` on Add; `x+y` = Add
        output; `abs(x)` = Absolute Value output). Error -> Clear Errors.
     e. Owner **Not A Refnum?** -> **Case**: TRUE -> `not_a_terminal`;
        FALSE -> **Format Into String** `%s [%s][%s] %s` (Name, Label,
        OwnerClassName, separator). Separator Select: `-->` + tab between
        terminals, `;` after the last one.
   - Per-wire strings -> array -> **Array To Spreadsheet String** (End Of
     Line), then the shared header pattern -> `result`:
     `verb=wires  vi=<path>  objects=<lines>`.
2. Close terminal/wire/BD/VI refs exactly once (same as analyze).

### Output format - how to interpret it

Verified on `gen\demo.vi` (A,B -> unlabeled Add -> C; plus unwired
leftover functions that correctly do NOT appear):

```
Wire: label:"" broken: 0 ->  B [B][TopLevelDiagram] -->	x [][Function] ;
Wire: label:"" broken: 0 ->  x+y [][Function] -->	C [C][TopLevelDiagram] ;
Wire: label:"" broken: 0 ->  A [A][TopLevelDiagram] -->	y [][Function] ;
```

- One wire per line; blank lines between entries are row-separator
  artifacts - ignore them.
- `label:"..."` - the wire's own label (usually ""; wires CAN be labeled).
- `broken: 0|1` - 1 = broken wire.
- Terminals in dataflow order: **first = source**, rest = sinks; `-->`
  separates them; the line ends with ` ;`.
- Each terminal is `Name [Label][OwnerClassName]`:
  - Primitive/subVI terminal: Name = the terminal's name as shown in
    Context Help; Label normally empty; OwnerClassName = `Function`.
  - Front-panel control/indicator terminal: Name = Label = the control's
    label; OwnerClassName = `TopLevelDiagram`.
  - `null terminal` / `not_a_terminal` replace a terminal whose refnum
    (or its owner) is invalid.
- So `A [A][TopLevelDiagram] --> x [][Function]` reads "control A feeds
  input x of a function". NOTE: the function's OWN label is not part of
  the line (only terminal names) - cross-reference `analyze` (or Mode 1
  extraction) when you need the node's label.
- `wires` lists only wired connectivity; `analyze` also lists unwired
  objects, so their object counts can legitimately differ.

### Self-inspection limitation (CONFIRMED)

`wires` (and any read verb) on **Gateway.vi itself** fails with modal
Error 1055 "Object reference is invalid" / Error 1320 "Property Node
(arg 3)". Root cause: the temp copy keeps the name `Gateway.vi`, which
collides with the running in-memory original, so traversal walks parts
of the LIVE VI -> stale/invalid references. Verified by running `wires`
on a renamed copy (`_service\deprecated\Gateway_Copy.vi`): identical code, clean complete
output, all `broken: 0`.

- NEVER run read verbs with `vi path` = Gateway.vi. Use a **renamed**
  copy instead (`copy_path` a copy, or ask the user).
- If the copy-to-temp fallback inside Gateway.vi is kept, it must RENAME
  the copy (e.g. `%TEMP%\lv_mcp\gwtmp_<name>.vi`), not just relocate it.
- Property-node error dialogs / error strings name the failing property
  as `(arg N)` - a 1-based index into the node's property list (e.g. on
  the Terminal PN: Owner=1, ISource=2, Label=3, ClassName=4, Name=5, so
  `(arg 3)` = a Label read).

## v3 build sheet - generation verbs (`newvi` / `place` / `wire`)

Driver and MCP server already pass `arg2` / `arg3` through; only the
Gateway VI needs work. Add two string controls to the front panel,
labeled exactly `arg2` and `arg3`, plus three new cases on the main verb
case structure.

Golden rules unchanged: no dialogs, close every ref exactly once, all
error paths either Clear Errors or land in the shared error-capture
`Select` -> `ERROR %d: %s` -> `result`.

### Case `newvi`  (arg1 = full save path)

1. **New VI** (VI Scripting palette): all inputs unwired -> `vi ref`.
2. **Invoke Node** (VI class): method **Save:Instrument**;
   `Path to saved file` <- **String To Path**(arg1); `Save a Copy` FALSE;
   `Without Diagram` FALSE. Saves the untitled VI to disk - no dialog when
   the path is explicit. If the file already exists and a replace prompt
   ever appears, that prompt is from here (not observed in testing).
3. Result: `newvi ok path=<arg1>` via the usual Select pattern.
4. **Close Reference** on `vi ref` (its own error -> Clear Errors).

### Case `place`  (vi_path = target VI, arg1 = type, arg2 = "x,y", arg3 = label or `-`)

1. String To Path -> **Open VI Reference** (options unwired - default is
   edit-capable; do NOT wire 0x04 prompt-to-save) -> `vi ref`.
2. Parse arg2: **Spreadsheet String To Array** (delimiter `,`) -> For Loop
   **Decimal String To Number** -> 1D I32 array -> **Index Array** 0 / 1.
   Empty arg2 defaults to 100,100.
3. **Bundle By Name** on an LVPoint constant (create it from the New VI
   Object `location` terminal; elements `Horizontal`/`Vertical`). If the
   elements have no selectable names, use a plain **Bundle** (order x, y).
4. **Inner Case on arg1** - one branch per supported type. ONLY the New VI
   Object node goes inside a branch; `location` and `error in` enter,
   `object refnum` and `error out` leave through tunnels. Each branch's
   **New VI Object** (VI Scripting palette):
   - `vi object class` = class specifier constant:
     `numctl` `numind` `strctl` `strind` `numconst` `strconst` ->
     **Generic\u00bbGObject\u00bbControl**;
     `add` `multiply` -> **Generic\u00bbGObject\u00bbNode\u00bbFunction**
   - `style` = constant from the style terminal (the giant palette ring) -
     select the matching item: Numeric Control (modern), Numeric Indicator
     (modern), String Control (modern), String Indicator (modern),
     Numeric Constant, String Constant, Add, Multiply. COPY the node from
     `Creating New VI From Scratch (copy).vi` and just re-pick the style -
     rebuilding that ring by hand is painful.
   - `owner refnum` <- `vi ref` (the NI example wires the VI ref for both
     FP and BD objects).
   - `auto wire?` = FALSE (NI recommends precise scripting wires instead).
   - `path` unwired (subVI placement is a later extension).
   - `function:%d` branch (added later): parses the style code from arg1
     (Scan `%[^:]:%d`), wires **Generic\u00bbGObject\u00bbNode\u00bbFunction** class and
     feeds `%d` into the giant style ring - this places ANY primitive by its
     style code. The full name\u2192code table lives in `style_codes.json` /
     `style_codes.json` (project root; JSON has `byName` and `byCode`).
     Style must be compatible with the class (docs: Add style + Boolean
     class = runtime error), so per-*category* classes are still needed:
     Function for `function:%d`, Control for panel styles, etc. - but never
     a branch per individual object.
   Default branch: `ERROR: unknown place type: <arg1>`.
5. Label (skip when arg3 = `-` - wrap in a Case on `Equal? arg3 "-"`):
   - Property Node (object refnum) -> **Label** -> Property Node (Label)
     -> **Text** (write) <- arg3.
   - Property Node (object refnum) -> **LblBdVisible** (write TRUE).
     MANDATORY: `wire` finds objects by label via Open VI Object
     Reference, which only works after the label was displayed at least
     once.
6. Save: **Invoke Node** (vi ref) -> **Save:Instrument** <- String To
   Path(vi_path).
7. Result: `place ok type=<arg1> label=<arg3> at <arg2>` or ERROR.
8. **Close Reference** object ref, then vi ref.

### place - VERIFIED syntax (post-1059 fix)

**Error 1059 root cause (fixed):** New VI Object rejects a WIRED but
invalid `path` input. Style-only calls (no subVI path) previously fed
`String To Path("")` into `path` unconditionally -> "Unexpected file
 type". Fix: the `path` input must be **physically not connected** when
unused (two NVO nodes sharing the downstream label/error chain, or
equivalent), NOT `<Not A Path>`.

Verified 2026-10-14 on `gen\anyfix.vi` (all placements confirmed by
analyze + extraction, For Loop bounds applied):

- `arg1` = `any:<stylecode>` - style-only placement. WORKS for every
  category: `any:2002` (For Loop), `any:1050` (Add), `any:21004`
  (Numeric Indicator, modern -> lands on FP, BD shows its terminal),
  `any:2005` (Numeric Constant). **`any:` is the canonical prefix for
  style-only calls.**
- `arg1` = `any:0<path>` (style code ignored when a path follows) -
  places a subVI/custom control: `any:0C:\LabView skill\gen\sumtest2.vi`
  -> ok, label=SumSubVI2.
- `arg2` = `H,V` or `H,V,W,H`. W/H are applied to resizable objects
  (For Loop 200,200,300,200 -> correct 300x200 loop) and are the
  FRONT-PANEL ITEM SIZE for FP objects (numind/numctl/etc.) - there
  they MUST be non-zero (see the v3.15 FP ITEM SIZE RULE). For
  fixed-size BD nodes W/H are simply ignored - 2-value form is fine.
- `arg3` = label or empty. Empty label: object gets NO label (FP
  indicator shows unlabeled).

**Legacy prefixes - also fixed (verified 2026-10-14):** `function:<code>`
and `ctrl:<code>` style-only calls place correctly after the same
path-unwired NVO fix was applied to their branches. All prefixes
(`any:` / `function:` / `ctrl:`) are now equivalent for style-only
calls; `any:` remains the only prefix that accepts a trailing path
(`any:0<path>` for subVIs).

### SubVI placement and wiring - see `references/subvi-placement.md`

SubVIs from NI-installed libraries (vi.lib, analysis LLBs) can be placed
with `any:0<path>` and wired like any node, but subVI `Terms[]` are
indexed by connector-pane CELL number (empty cells break wires), while
primitives are output-first - the full proven workflow, verified
terminal tables and gotchas live in `references/subvi-placement.md`.

### Case `wire`  (vi_path, arg1 = "srcLabel|dstLabel", arg2 = "srcKind|srcIdx|dstKind|dstIdx")

Kind `c` = control/constant/indicator terminal (via Control class);
kind `n` = function/node terminal via `Terms[]` index. Example:
arg1 `A|B`, arg2 `c|0|n|2` = control A -> terminal Terms[2] of function B.

1. Open VI Reference -> Property **BlockDiagram** -> `bd ref` (Open VI
   Object Reference wants a diagram/FP owner, not the VI ref).
2. Parse arg1: **Split String** `|` -> srcLabel, dstLabel. Parse arg2:
   Split String `|` -> 4 fields; **Decimal String To Number** the idx
   fields (default 0).
3. **Open VI Object Reference** twice: `owner refnum` <- `bd ref`,
   `vi object class` = class specifier constant **Generic\u00bbGObject**,
   `name/order` <- srcLabel / dstLabel -> src/dst GObject refs. Two
   objects with the same label: only one is returned - keep labels
   unique.
4. Per side, **Case on kind**:
   - `c`: **To More Specific Class** (target **Control**) -> Property
     **Terminal** -> terminal ref.
   - `n`: **To More Specific Class** (target **Node**) -> Property
     **Terms[]** -> **Index Array**(idx) -> terminal ref.
   Primitives order terminals inputs-first, output last: Add = 0:x, 1:y,
   2:x+y. Verify with the `wires` verb on the generated VI afterwards.
5. **Invoke Node** on the DST terminal (Terminal class): method
   **Connect Wire**, `Wire Source` <- src terminal ref; leave `Auto Wire?`
   (T) and `Auto Route?` (F) unwired/default; `Wiring Specs` unwired.
   Copy this invoke node from the NI example (right-hand side) instead of
   rebuilding it.
6. Save: Invoke Node (vi ref) -> Save:Instrument <- String To
   Path(vi_path).
7. Result: `wire ok <srcLabel> --> <dstLabel>` or ERROR (a broken/incompatible
   wire surfaces here - adjust the index and retry).
8. Close: terminals, GObjects, `bd ref`, `vi ref`.

### Loop terminals, tunnels, shift registers (empirical 2026-10-14)

Experiments on `gen\srtest*.vi` (scratch, now broken - discard):

- **Tunnels need NO verb**: Terminal:Connect Wire auto-creates a tunnel
  whenever a wire crosses a structure boundary (proven: `Sum -> Result`
  inside->outside produced a tunnel on the loop border). Do not try to
  place Tunnel objects - none exists in the style table.
- **ForLoop `Terms[]` map**: `Terms[0]` = **i** (InnerTerminal),
  `Terms[1]` = **N** (OuterTerminal). Wiring to `Terms[0]` from outside
  auto-tunnels (i is inner!). N is a SINK: as a wire source it raises
  1055; correct usage is dst: `wire "C100|Loop", "c|0|n|1"`.
- **ShiftRegister has no StyleID** - not a palette object, NVO cannot
  create it. Placeable substitute: **Feedback Node, `any:2353`** -
  verified: places inside the loop (coordinates within its bounds),
  labelable, class `FeedbackNode`. Its `Terms[]`: `[0]`=output (source),
  `[1]`=init (sink, triangle appears when wired), `[2]`=input - CANONICAL
  MAP in the "Feedback Node terminal map" section (run-verified
  end-to-end by pi_golden3.vi, see v3.11).
- **Auto Wire? caveat**: Gateway's Connect Wire invoke leaves
  `Auto Wire?` at default TRUE; with loop terminals / Feedback Node this
  misroutes wires (wires landed on wrong terminals / got merged through
  a reused tunnel, result `broken: 1`). Set **Auto Wire? = FALSE** on
  the Connect Wire invoke and retest before further terminal mapping.

### v3.3 - reference resolver in `vi_path` + `loop` verb (verified 2026-10-15)

- **Resolver syntax**: `vi_path = C:\path\file.vi%Class|Label[%NestedClass|NestedLabel...]`.
  The chain walks down into containers, so `place`/`wire`/`loop` can target
  objects INSIDE a structure (loop diagram, cluster, ...). The resolver goes
  in `vi_path` ONLY - never in `arg1` (arg1 stays the pure place spec,
  e.g. `any:2005` or `any:0C:\...\sub.vi`; resolver in arg1 fails).
- **`loop` verb**: `verb=loop`, vi_path = resolver pointing at the loop,
  `arg1=addSR`, `arg2` = Y position, **arg3 must be EMPTY** (a shift
  register cannot carry a label; passing one relabels the whole loop
  instead). Returns `Loop: , NewShiftReg, UID=<n>`.
- **UID returns**: `place` and `loop` return `UID=<n>` of the created
  element. Values appear deterministic per object type/session - candidate
  stable handle for future verbs.
- **Shift registers do NOT export as `<NODE>`** in extract_vi strings -
  verify them on the block diagram PNG (black square terminals on the
  loop borders), not in the strings export.
- **MCP server quirk (FIXED in server.py)**: the `gateway` MCP tool used
  to reject `%`-resolver vi_paths on read verbs AND on `loop` with
  "vi_path not found" - its `os.path.isfile()` check ran on the full
  resolver string. Fixed: `loop` added to WRITE_VERBS; read verbs now
  split the base path for the isfile/copy and re-attach the resolver to
  the temp copy's name. Requires an MCP server restart to take effect;
  terminal-direct cscript is the fallback until then.

### Copy list (from the NI example / shipping examples)

- `_service/deprecated/scripting_examples/Creating New VI From Scratch (copy).vi`: New VI
  Object + style ring, Terminal:Connect Wire invoke, Control:Terminal and
  Node:Terms[] property nodes, LVPoint cluster constant.
- `examples\Application Control\VI Scripting\Creating Objects\`:
  `Adding Objects.vi`, `Test - New VI Object.vi`,
  `New VI Object Location Argument.vi` (the three location argument
  forms), `Drop Add Function Inside While Loop.vi` (placing inside a
  structure - v3.1 material).
- The example's `Block Diagram Window:Open` invoke is NOT needed (we stay
  headless).

### Test sequence (agent runs after build; kill the spawned LabVIEW first)

```
newvi  "" arg1=C:\LabView skill\gen\demo.vi (path in arg1 slot!) -> newvi ok
place  vi_path=... arg1=numctl arg2=100,100 arg3=A -> place ok
place  vi_path=... arg1=add    arg2=300,100 arg3=SUM -> place ok
place  vi_path=... arg1=numind arg2=500,100 arg3=C -> place ok
wire   vi_path=... arg1=A|SUM   arg2=c|0|n|1       -> wire ok
wire   vi_path=... arg1=SUM|C   arg2=n|0|c|0       -> wire ok
wire   vi_path=... arg1=B|SUM   arg2=c|0|n|2       -> wire ok (2-input prim)
analyze vi_path=... (temp copy) -> 6+ objects, wires A/B --> SUM --> C
# function:%d end-to-end (verified on gen\functest.vi):
newvi  "" arg1=...\functest.vi -> place numctl A -> place function:1054 ABS
place numind C -> wire A|ABS c|0|n|1 -> wire ABS|C n|0|c|0  (all ok)
```

**Terminal index convention (primitives):** `n|0` is the **output**
(the `OverridableParameterTerminal` is traversed first), and
`n|1..n` are the **inputs** in order (`n|1` = first input, `n|2` =
second). This is the opposite of the "inputs first" assumption that
produces two-source/two-sink broken wires. Direction still matters:
wire control -> input first, then output -> indicator.
Then open `demo.vi` in the GUI and eyeball it. Server note: write verbs
edit and save the REAL path (no temp copy). Aiming them at a VI open in
the user's LabVIEW is the standard, live mode (see the co-editing
section).

## v3 test findings (2026-10-14, structest.vi / sumtest.vi)

Empirically verified on `gen\structest.vi` and `gen\sumtest.vi`:

- **Structures ARE placeable** through the shared style ring:
  `place function:2002` -> For Loop, `function:2001` -> Case Structure,
  `function:2003` -> While Loop, `function:2069` -> Flat Sequence.
  The Case Structure serializes as a `Select`-type node with two
  `BDCONTENT`s; the For Loop as `For Loop` with one empty `BDCONTENT`.
- **Inside-placement does NOT work**: `place` at coordinates inside a
  structure's bounds drops the object ON TOP of the structure (owner is
  always the VI). Confirmed via strings export: the Add stayed a child of
  the top-level BDCONTENT; the loop's BDCONTENT stayed empty.
- **Wire kinds**: `c` = ControlTerminal (FP control/indicator terminal on
  the BD, carries the control's name), `n` = node Terms[] index. Wiring
  function -> function -> indicator works (`n|0` out, `n|1/n|2` in).
  Wiring INTO or OUT OF a For Loop's terminals fails with 1055, and so
  does wiring FROM a constant - see root causes below.
- `wires` verb shows primitive terminal names for function terminals
  (e.g. `x/y` for Divide, `x+1` for Increment, `x*y` for Multiply).

### GetTerminal.vi - two known limitations (fix = small IDE edit)

`GetTerminal.vi` selects the `Traverse for GObjects.vi` **Class Name**
input from the kind letter: `"n"` -> `"Function"`, `"c"` ->
`"ControlTerminal"`, Default -> `"Terminal"`. The lvlib traverse matches
by class AND subclasses (Gateway's analyze passes `"GObject"` and gets
everything, and nothing's ClassName is literally `GObject`):

1. **Structures not found for kind `n`**: a For Loop's ClassName is
   `ForLoop`, which matches `"Function"` only exactly -> not found ->
   To More Specific Class on a NULL ref -> error 1055.
   **Fix**: in the Class Name case structure, case `"n"`: change the
   string constant `Function` -> `Node` (Node matches all structures +
   primitives; the existing cast to Node then works for all).
2. **Constants not resolvable for kind `c`**: a BD constant's ClassName
   is e.g. `DigitalNumericConstant`; the found object is the constant
   itself (its wireable Terminal child has an EMPTY label, so label
   lookup can never return it). Cast to ControlTerminal -> 1055.
   **Fix** (two parts):
   a) Class Name case `"c"`: change `ControlTerminal` -> `GObject`
      (so constants are found too).
   b) In the terminal-type case structure, case `"c"`: replace the bare
      `To More Specific Class -> ControlTerminal` with a ClassName
      check: Property Node (Generic\u00bbClassName) -> Equal? "ControlTerminal"
      -> inner case: TRUE = existing cast; FALSE = To More Specific Class
      -> Constant, then Property Node Constant\u00bbTerminal -> Terminal out.
      (`Constant\u00bbTerminal` is a read-only scripting property, lvscript
      docs.)

### Constant values - needs a new verb (v3.1)

`place numconst` creates a Dbl constant with **value 0**; the label is
not the value and there is no verb to set it. Needed for any meaningful
arithmetic codegen (sum 0..99 needs 99 and 2). Spec: new verb `setval`
(vi_path, arg1 = label, arg2 = value string): traverse BD Class Name
`Constant`, match label, To More Specific Class -> Constant, write
`Constant\u00bbValue` (variant; `Constant_Value.html`). Optionally extend to
FP controls (Control\u00bbDefault Val) so generated VIs can have defaults.

### GetTerminal fixes VERIFIED (both applied by user, 2026-10-14)

After fix 1+2, re-tested:

- **Constant wiring works**: `99|Inc c|0|n|1`, `99|Mul c|0|n|2`,
  `2|Div c|0|n|2` - all `wire ok`. Fan-out from one constant to two
  inputs works (one wire object with branches).
- **Structure wiring partially works**: wiring to a ForLoop's `Terms[0]`
  succeeds and AUTO-CREATES A TUNNEL on the loop border (`wires` shows
  the endpoint as ` [][Tunnel]`).
- **BUT `Terms[]` of a structure contains ONLY Tunnels.** Probing
  `Terms[1..3]` in both directions (and i->N, an exact-type legal wire)
  all fail with 1055 *at the Invoke Node* (Connect Wire) - i.e. the
  index resolved to an invalid refnum (out-of-range), so N and i are
  NOT addressable via `Terms[]`. To reach them (v3.1):
  - `Terminal\u00bbConnect Wire` (lvscript: invoked on the DESTINATION
    terminal; `Wire Source` "can be either another terminal or a node";
    with `Auto Wire? = TRUE` and a NODE as source, "a compatible source
    terminal is chosen automatically from the source node") - so pass
    the loop NODE as source to auto-wire from `i`.
  - Or resolve the loop's child terminals by child index (analyze child
    order: OuterTerminal, Diagram, Terminal(N), Terminal(i),
    InnerTerminal, Tunnel) and cast to Terminal.
  - `Wiring Specs` (2D array of "names of source and sink terminal
    pairs") may allow addressing N by name.
- **Sink-conflict behavior**: Connect Wire does NOT refuse an occupied
  sink - it creates a BROKEN wire (`broken: 1`). Wires to a full input
  must be avoided; there is no delete verb, so pollute nothing. (This
  is how `sumtest.vi` got a broken Inc->Div.y wire; rebuilt clean as
  `sumtest2.vi`.)
- Type note: all successful wires are Dbl->Dbl; Connect Wire showed no
  coercion (Add Dbl out -> loop N I32 failed, though that probe is
  also explained by the Terms[] finding).

### sumtest2.vi - sum of 0..99 via Gauss (99\u00b7100/2 = 4950)

Fully wired and verified (`wires`: 5 wire objects, all `broken: 0`):
`99 -> Inc.x`, `99 -> Mul.y`, `Inc -> Mul.x`, `Mul -> Div.x`,
`2 -> Div.y`, `Div -> Result`. Diagram image confirms the chain.
**Remaining**: constants hold value 0 -> either set 99/2 by hand to
verify (run = 4950), or add the `setval` verb. Loop-accumulator version
(add i inside a For Loop) additionally needs the loop N/i wiring above
plus inside-placement.

## v3.4 findings (2026-10-15, error-43 / 1055 session)

### ERROR 43 = "Operation cancelled by user" in `newvi`

> **ARGUMENT NOTE - newvi uses arg1, NOT vi_path!**
> `newvi` takes the full save path in **arg1**. `vi_path` must stay EMPTY
> for newvi. If the path is passed in vi_path (or arg1 is empty),
> `String To Path("")` feeds an EMPTY path to Save:Instrument -> the
> interactive Save-As dialog pops and is auto-cancelled in the COM run
> -> `ERROR 43: Operation cancelled by user` at the Invoke Node.
> Correct calls:
> - gateway tool:  verb=newvi, arg1="C:\\...\\new.vi"  (vi_path unset)
> - terminal:      lv_gateway.vbs Gateway.vi newvi "" "C:\\...\\new.vi"
>   (vi_path slot = "", arg1 = path)
> All OTHER verbs (place/wire/setval/loop/analyze/wires) use vi_path as
> the target VI; newvi is the only verb that takes its target in arg1.

`newvi` failed with `ERROR 43: Invoke Node ... Method Name: Save:Instrument`
for ANY path. Root cause (verified in the block-diagram extraction of
Gateway.vi): the **`Path to Saved File` input of the Save:Instrument invoke
in the newvi case was UNWIRED** (only `Save a Copy`=F and `Without
Diagram`=F were wired). With no path the invoke pops the interactive
Save-As dialog for the untitled VI; in the COM/scripting run context that
dialog is auto-cancelled -> error 43. Fix: wire `String To Path(arg1)` ->
`Path to Saved File`. Diagnosed by reading the error code from
`resource\\errors\\English\\LabVIEW-errors.txt` (grep `code="43"`).

### 1055 at Property Node - silent resolver failure (setval)

- `setval ...anytest.vi%DigitalNumericConstant|NoSuchLabel 123 dec`
  returned **`set: ok`** and SILENTLY WROTE 123 into `GWTEST43` (the only
  numeric constant on the diagram, different label) - verified in the
  extracted PNG. The resolver matched by CLASS and ignored the label
  mismatch; wrong-element writes are silent.
- `setval ...%StringControl|NoSuchLabel` (no such class on the diagram)
  -> `ERROR 1092: Invoke Node in TRef Traverse.vi->...->ReferenceResolver.vi`
  ("Traverse Initialization Failed") - properly reported.
- **Error 1055 at Property Node in Gateway.vi** (user's dialog) is what
  appears when an INVALID ref reaches a Property Node: e.g. `place`'s
  UID/Label property after New VI Object failed (malformed arg1 like
  `any:2005%ForLoop|Loop1`, or style/class mismatch), because errors are
  NOT checked between New VI Object and the property nodes.

### server.py

`setval` was missing from `WRITE_VERBS` (resolver-suffixed vi_path hit the
read-branch isfile check -> "vi_path not found"). Added; needs MCP server
restart to take effect. Terminal-direct cscript unaffected.

## v3.4 loop-terminal session (2026-10-15)

### ForLoop.Terms[] contains ONLY the N terminal (size 1)

- **`ForLoop.Terms[0]` = the N terminal. `Terms[1]` returns a NULL terminal
  reference** -> Connect Wire invoke 1055s ("Object reference is invalid").
  The **i terminal is NOT in `Terms[]` at all** — it is reachable only as a
  **GObject labeled `i`** (traversal finds it), but GetTerminal stage-2 has
  no case to pass an already-Terminal object through, so any
  `wire "i|Add1" ...` call fails:
  - `wire "i|Add1" "c|0|n|2"` -> `1055 Property Node in GetTerminal.vi->Gateway.vi`
  - `wire "i|Add1" "n|0|n|2"` -> `1055 To More Specific Class in GetTerminal.vi->Gateway.vi`
- **arg2 kind semantics (clarified)**: `n|<idx>` = index into the NODE's
  `Terms[]` array (only valid for kind n); `c|0` = the control/constant's
  own terminal. **Correct call for N**: `wire "NConst|Loop1" "c|0|n|0"`
  (verified in IDE).
- **SOLVED - terminal kind `i` (implemented after kind `t` proved
  insufficient)**: the loop counter terminal has **NO Label at all** (it is
  a GObject owned by the Diagram, not a labeled control), so `t` traversal
  by label "i" could never match it. New kind **`i`** in GetTerminal.vi
  links directly to the loop counter terminal of the loop named in arg1:
  - `wire "Loop1|Add1" "i|0|n|2"` -> wires Loop1's **i terminal** to Add1.x.
    **arg1's source label is the LOOP's label** (the loop whose index
    terminal is required), not "i". The `|0` index after `i` is a fixed 0.
  - Verified 2026-10-15 on sumtest7.vi: `wire ok` + on-disk wires shows
    `Wire: broken: 0 ->  [][Diagram] --> x [][Function]` — the i terminal
    appears with an EMPTY name and OwnerClass `Diagram`.
- Earlier failed attempts with kind `t` (kept for the record):
  - `wire "i|Add1" "c|0|n|2"` -> `1055 Property Node in GetTerminal.vi->Gateway.vi`
  - `wire "i|Add1" "n|0|n|2"` -> `1055 To More Specific Class in GetTerminal.vi->Gateway.vi`

### Verified terminal orders (re-verified this session)

| Node | Terms[] index | Terminal |
|---|---|---|
| Add | [0]=out, [1]=y, **[2]=x** | `c|0|n|2` lands x |
| Multiply | [0]=out, [1]=y, [2]=x | same convention (pimc.vi wires) |
| Comparison (Less Or Equal?) | [0]=out, [1]=y, [2]=x | same convention (probe + pimc.vi wires) |
| Feedback Node | order VARIES - see "FN terminal map" (two variants) | wire per Map A; if broken:1 delete + rewire per Map B |
| ForLoop | **[0]=N only** (size 1!) | NConst via `c|0|n|0` |
| Select | [0]=out, **[1]=f, [2]=s, [3]=t** | NOT [1]=s; mis-slotting cost a rebuild (bubble_a2) |
| GrowableFunction (Replace Array Subset) | [0]=array in, [1]=output array, [2]=new element/subarray, [3]=index | ONLY when placed WITH bounds (see v3.7); collapsed nodes expose garbage |

**Convention: 2-input primitives are consistently [1]=y, [2]=x.** Do NOT
rely on a remembered exception - when a primitive is NOT commutative
(Comparison, Divide, ...), probe or double-check the `wires` output
(terminal names x/y appear there) BEFORE trusting the result. A misread
probe cost one full rebuild (pimc.vi computes 1<=r^2 instead of r^2<=1).

(Older note "ForLoop Terms[0]=i, Terms[1]=N" was WRONG — do not reuse.)

### Wire persistence + auto-tunnel

- Wire case flow: Connect Wire invoke -> Save Instrument -> "wire ok".
  **A failed wire leaves NOTHING on disk** (verified: sumtest7.vi shows no
  wire even after a later successful setval save). Earlier "wire ok but no
  wire" confusion = in-memory-only wires + failed save.
- **Wiring across the loop border AUTO-CREATES a tunnel** inheriting the
  source label (seen: `NConst [LoopTunnel]`), even with Auto Wire?=F.

### Fixture state

- **sumtest7.vi (clean, no wires)**: Loop1 (ForLoop, UID 43, at 100,120),
  Add1 inside (UID 69, 160,180), NConst top-level (UID 72, value 100,
  20,150). `wiretest.vi` is polluted — discard.

### Sum-VI wire plan (CORRECTED - see v3.5 session below)

`NConst|Loop1 c|0|n|0` -> `Loop1|Add1 i|0|n|2` -> `Add1|FN1 n|0|n|2` ->
`Init0|FN1 c|0|n|1` -> **`Add1|Result n|0|c|0`** (NOT `FN1|Result` - the
FN output lags one cycle and gives 4851; see v3.5).

## v3.5 sum-VI completion session (2026-10-15) - RESULT=4950 VERIFIED

**sumtest9.vi is the golden fixture** - For Loop N=100, i -> Add.x,
FeedbackNode accumulator, Add out -> FN input AND -> Result. Run-verified
`Result = 4950` via COM. sumtest7 (Result on FN out) computes 4851;
sumtest8 has a broken border tunnel - both discard.

- **MCP server restarted and verified**: `ping` -> pong; `loop`, `setval`
  and kind-`i` wire calls all accepted with the new schema.
- **place for non-palette objects**: named arg1 types are only the small
  built-in set (`numctl numind strctl strind numconst strconst add
  multiply`); `Feedback Node` as a name -> `ERROR: unknown place type`.
  Use **`any:<stylecode>`** - `any:2353` places the Feedback Node
  (labelable, UID returned, places inside loop via resolver).
- **Feedback Node terminal order (verified by run)**: `[0]`=output,
  `[1]`=init, `[2]`=input.
- **Run-verify via COM** (`run_vi_get_value.vbs`):
  `CreateObject("LabVIEW.Application")` -> `app.GetVIReference(path)` ->
  `vi.Run True` -> `vi.GetControlValue("Result")`. NOTE: the
  VirtualInstrument ActiveX class has **no `FP` property** - controls are
  read/written with the `GetControlValue` / `SetControlValue` METHODS.
- **CRITICAL - `vi.Run True` is ASYNCHRONOUS (verified 2026-10-15, pimc3)**:
  it returns ~30 ms after starting the run, BEFORE the VI finishes. Reading
  a control immediately after `Run` samples a MID-RUN value. pimc3 (Monte-
  Carlo PI, 1e6 iterations) read `0.033676` = 4*8419/1e6 = value at
  iteration ~10 700 (~1% progress) and was falsely declared broken; the
  same VI 1 s later read `3.140772` (PASS). The VI wiring was correct all
  along - the checker was the bug. Also: `vi.Running` property is NOT
  supported on VirtualInstrument (raises error), so completion cannot be
  polled directly. **Fix (now in run_vi_get_value.vbs)**: after `Run`, poll
  `GetControlValue` every 500 ms until the value is identical on 2
  consecutive polls AND >=1.5 s elapsed; timeout 120 s. Diagnostic script
  with timestamps: `run_vi_get_value2.vbs`. Never trust a value read less
  than ~1 s after Run.
- **4851 vs 4950 lesson - Feedback Node one-cycle delay**: wiring the
  indicator to the **FN output** yields sum 0..98 = 4851 (FN out at the
  last iteration still holds the previous partial sum). The indicator
  must tap the **Add output** (which also feeds the FN input).
- **Node outputs CAN cross the loop border - but the tunnel must be set
  Regular first** (revised 2026-10-17; the old "never wire a NODE output
  across the border" rule predates the `loop tunnel:<i>;0` option):
  `Add1|Result n|0|c|0` with Result top-level auto-creates a tunnel that
  reads **broken: 1** UNTIL `loop tunnel:i;0` sets it Regular (verified
  end-to-end by pi_golden3.vi: FN1->PI0 exit went broken:1 -> broken:0
  and the VI computed PI correctly). Re-invoking the same wire call
  still makes it WORSE (second tunnel, tangles Add out) - set the
  tunnels instead, don't re-wire.
- **Working pattern**: place the indicator at top-level coords that lie
  INSIDE the loop frame - its BD terminal becomes owned by the loop's
  Diagram, and `Add1|Result n|0|c|0` then wires clean (broken: 0, no
  tunnel). (Placing `any:21004` via resolver `%ForLoop|Loop1` fails with
  **1060 wrong container**.)
- Auto-tunnels from *labeled constants* (NConst, Init0) across the border
  remain clean (broken: 0) and inherit the source label.

## Resolver class names for 'Class|Label' (setval / place / loop vi_path)

The resolver in `vi_path = path.vi%<Class>|<Label>` matches a **short class
name with NO spaces** - not the verbose ClassName shown by `analyze`
(`DigitalNumericConstant [NConst]` there does NOT work as a resolver
class). Wrong class name -> `ERROR 1092 ... (Traverse Initialization
Failed)` on setval (looks like a broken Gateway, but it is just the class
string).

**Verified list** (add to it as new cases are confirmed):

| Resolver class | Matches | Verified |
|---|---|---|
| `NumericConstant` | numeric constants (any style) | 2026-10-15 (pimc.vi setval x4) |
| `Constant` | generic alias - ANY constant | 2026-10-15 (user-confirmed) |
| `ForLoop` | For Loop structure | sumtest9/pimc place+loop resolver |

Rules of thumb: try the short palette-style name first (`NumericConstant`,
`StringConstant`, `BooleanConstant`, ...); if unsure whether a specific
case works, probe it with one cheap `setval` on a scratch constant before
relying on it.

## `place numconst` / `any:2005` creates an I32 integer constant

**Verified 2026-10-15 (pimc/pimc2 PI debugging).** A numeric constant
placed via the Gateway is **I32 (integer)** representation, not DBL:

- `setval arg2=frc` (fractional) on it **silently writes 0** - reported
  `set: ok`, no error, value stays 0. pimc2 read PI = 0 because of this.
- `setval arg2=dec` **truncates** to the integer part (0.0000004 -> 0).
- No Gateway verb changes a constant's representation.

Consequences for codegen:
- Only ever `setval` **integer** values into placed constants.
- For fractional math, build it from integer constants with an integer-
  safe chain (e.g. `Mul` -> `Div`: 4*count/N instead of a 0.25 factor),
  or use nodes whose outputs are DBL (Random Number (0-1), etc.).
- The user's revised pimc3 confirms: with integer constants only
  (1 000 000, 4, 1, 0) and DBL node outputs everywhere else, PI computes
  to 3.1436 at N=1e6.

## Live co-editing with the user's IDE open (VERIFIED 2026-10-15; THE STANDARD since 2026-10-19)

**POLICY (user decision 2026-10-19): working live in the user's
LabVIEW instance is a standard feature, not an exception.** The old
blanket warning "never point at a VI open in the user's LabVIEW" is
RETIRED. The user watches changes happen on screen and considers this
cool and useful. The separate copy-first rule still applies where it
always did: develop/debug UNPROVEN scripts on a copy, and keep runtime
verification runs on a copy so the user's control values are not
disturbed. The remaining genuine cautions:
- coordinate with the user before destructive edits (two editors, one
  file - the user sees every change);
- a background instance (no IDE open) produces STALE copies - the user
  must reload from disk before saving.

**The experiment** (sortArr_tmp.vi, open in the user's LabVIEW IDE):

1. `manage_processes list` -> exactly ONE labview.exe (pid 8716, the
   user's IDE). File baseline mtime 18:11:14, 6163 bytes.
2. Read `analyze` -> works (temp copy, IDE open is irrelevant).
3. Write `place any:2005 EditTest 400,300` -> `place ok` instantly, no
   error, no dialog.
4. Disk: mtime -> 18:14:00, size -> 6423 bytes (SAVE happened).
5. Read-back `analyze` -> `DigitalNumericConstant [EditTest]` present
   (disk state confirmed).
6. `manage_processes list` again -> STILL exactly one labview.exe, same
   pid 8716 -> the edit ran INSIDE the user's session, not a spawned
   background instance. The user confirmed the block diagram updated
   live on screen.

**Mechanism**: the driver's `CreateObject("LabVIEW.Application")`
ATTACHES to a running LabVIEW instance if one exists; it only spawns a
background instance when none is running. Therefore:

- **IDE open (normal case)**: write verbs mutate the user's IN-MEMORY VI
  and `Save:Instrument` writes disk from the same session. Edits appear
  LIVE on the user's block diagram. No stale-copy divergence. This is
  the ideal co-editing mode.
- **No IDE open**: a background instance does the work; disk is updated;
  nobody is watching.

**Side effect**: a target VI that is NOT already open gets opened
(possibly hidden) in the user's session - it will appear in the IDE's
Window menu after edits.

**Rules for the agent**:

- Read verbs (`analyze`/`wires`) are always safe - they temp-copy ...
  EXCEPT Gateway.vi self-inspection (name collision with the in-memory
  original, see the 1055 section - use a renamed copy).
- **Writing a VI that is open in the IDE is VERIFIED SAFE and preferred**
  when the live mode is active. This REVISES the old blanket warning
  "never point at a VI open in the user's LabVIEW" - that warning was
  written under the separate-instance assumption.
- Stale-copy hazard exists ONLY in background-instance mode: if edits do
  NOT appear live in the user's IDE, a background instance did the work
  and the IDE copy is stale relative to disk. Then the user must NOT
  save from the IDE (it would silently revert the edit) - reload from
  disk first. Detect by asking the user "did it appear live?".
- The user's UNSAVED in-editor changes never touch disk: in live mode
  they are part of the same memory the gateway edits (and get saved
  along); in stale mode a later IDE save would overwrite the disk edit.
- A modal dialog anywhere in the user's instance ("Save changes?", error
  popups) blocks the COM Run and hangs the pipeline - keep the IDE
  dialog-free during gateway calls (same root cause as the 1055
  orphan-dialog problem).
- No delete verb exists: test probes (EditTest) must be removed by the
  user manually. Label probes clearly.

**Live co-editing routine (recipe for both parties)**:

1. User opens the VI (FP and/or BD visible) and keeps the IDE
   dialog-free. Optional: state whether unsaved changes exist.
2. Agent: read `analyze`/`wires` first (safe, shows current disk state -
   in live mode disk == memory for a saved VI).
3. Agent: apply write verbs (`place`/`wire`/`setval`/`loop`) one at a
   time, sequential, never parallel on one file.
4. User watches the diagram update live; agent verifies with a read verb
   + file mtime/size when confirmation matters.
5. If the VI was NOT open before: it is now open-but-saved in the user's
   session; if the user wants it closed, close it manually (state is
   saved, no prompt).
6. If anything looks stale (edits not visible): stop, reload from disk,
   re-check process list for a second labview.exe.

## One-pass canonical build recipe (v3.5, verified on sumtest9.vi)

Template for ANY accumulator-in-loop VI. Replay these exact calls; do not
improvise names or terminal indices. Golden fixture: sumtest9.vi
(Result = 4950 run-verified).

### Style codes you will actually need (from style_codes.json byCode)

| Code | Object | Used for |
|---|---|---|
| 2002 | For Loop | the loop structure |
| 2005 | Numeric Constant | N, init value |
| 1050 | Add | accumulator primitive |
| 1051 | Subtract | same family |
| 2353 | Feedback Node | loop accumulator (NOT placeable by name - only `any:2353`) |
| 21003 | Numeric Control (modern) | front-panel control |
| 21004 | Numeric Indicator (modern) | front-panel indicator |

Named place types (`Add`, `Numeric Constant`, ...) are only the small
built-in set; anything else MUST use `any:<code>`.

### The call sequence (sumtest9.vi, exact)

```
1. newvi  arg1=C:\LabView skill\gen\sumtest9.vi
2. place  vi_path=sumtest9.vi                      arg1=any:2002  arg2=100,100  arg3=Loop1
   (record the returned UID - the resolver references the loop by LABEL, not UID)
3. place  vi_path=sumtest9.vi%ForLoop|Loop1        arg1=any:1050  arg2=160,180  arg3=Add1    (inside loop)
4. place  vi_path=sumtest9.vi%ForLoop|Loop1        arg1=any:2353  arg2=250,180  arg3=FN1     (inside loop)
5. place  vi_path=sumtest9.vi                      arg1=any:2005  arg2=20,150   arg3=NConst   (top level; auto-tunnels into the loop when wired)
6. setval vi_path=sumtest9.vi%NumericConstant|NConst  arg1=100  arg2=dec
7. place  vi_path=sumtest9.vi                      arg1=any:2005  arg2=60,320   arg3=Init0    (top level)
8. setval vi_path=sumtest9.vi%NumericConstant|Init0   arg1=0    arg2=dec
9. place  vi_path=sumtest9.vi                      arg1=any:21004 arg2=350,130  arg3=Result   (top-level coords INSIDE the loop frame - see border rule)
10. wire  vi_path=sumtest9.vi  arg1=NConst|Loop1   arg2=c|0|n|0    (N const -> loop N terminal; auto-tunnel)
11. wire  vi_path=sumtest9.vi  arg1=Loop1|Add1     arg2=i|0|n|2    (loop i terminal -> Add.x; kind i, source label = LOOP label)
12. wire  vi_path=sumtest9.vi  arg1=Add1|FN1        arg2=n|0|n|2    (Add out -> FN input [2])
13. wire  vi_path=sumtest9.vi  arg1=FN1|Add1        arg2=n|0|n|1    (FN output [0] -> Add.y [1])
14. wire  vi_path=sumtest9.vi  arg1=Init0|FN1       arg2=c|0|n|1    (Init0 -> FN init [1])
15. wire  vi_path=sumtest9.vi  arg1=Add1|Result     arg2=n|0|c|0    (Add out -> indicator; Result terminal owned by loop's Diagram)
16. wires verb -> grep for 'broken: 1' - must find NONE
17. cscript //nologo run_vi_get_value.vbs "C:\LabView skill\gen\sumtest9.vi" Result 4950
```

### Border rule (the #1 trap)

- **A wire crossing the loop border auto-creates an Auto-Index tunnel -
  set ALL tunnels Regular after the last border-crossing wire** (revised
  2026-10-17, supersedes the old "never wire a NODE output across the
  border" rule). ANY crossing - constant, node output, or FP terminal -
  reads **broken: 1** until `loop tunnel:i;0` sets it Regular (count
  first with `tunnel:0;-2`). Re-invoking a failed wire makes it WORSE
  (second tunnel) - the fixture is then polluted; set the tunnel mode
  instead, and if a rebuild is needed pick a new filename, never re-run
  into a polluted VI.
- Alternative: with Gateway v3.12+, place the indicator/FP object at
  **coordinates INSIDE the structure via the resolver** - its terminal is
  then owned by the loop's Diagram and wires clean with no tunnel
  (steps 9+15).
- *Labeled* constants (NConst, Init0) crossing the border are fine - the
  auto-tunnel inherits the label (steps 5, 7, 10, 14) - but they still
  need the Regular setting per the rule above when in doubt.
- Placing a modern indicator via resolver `%ForLoop|Loop1` fails with
  ERROR 1060 (wrong container) - do not try.

### Accumulator wiring rule (the #2 trap)

Tap the **Add output** for the result, NOT the Feedback Node output.
FN output lags one cycle (at the last iteration it still holds the
previous partial sum): FN-tapped indicator reads sum 0..98 = 4851,
Add-tapped reads 4950. The Add output feeds BOTH the FN input and the
indicator.

### Run-verify (parameterized)

```
cscript //nologo "C:\LabView skill\skill-labview-code\references\run_vi_get_value.vbs" "<vi path>" "<control name>" [expected value]
```

Echoes the control value; with a third argument it prints PASS/FAIL.
Uses `GetVIReference` -> `vi.Run True` -> `vi.GetControlValue(name)`
(the VirtualInstrument ActiveX class has NO `FP` property; PowerShell
`GetVIReference` returns null - VBScript/cscript only).

## v3.6 bubble-sort session (2026-10-15/16) - batch workflow + GrowableFunction blocker

Workflow: backup original -> iterate on fresh-name temp copies via
batch scripts (`lv_gateway_batch.vbs`, `!` prefix tolerates failures)
-> verify with `wires` on a fresh-name chk copy -> apply winner to the
real VI. Scripts: `bubble_a2.txt`, `bubble_a3.txt` (a3 = corrected
Select slots + fresh names sortTmp_3/chk_i3).

### Replace Array Subset 1055 - superseded by v3.7 (was NOT a GetTerminal limitation)

The 1055s on Terms[2]/[3] were an artifact of a COLLAPSED node:
`any:3910` placed WITHOUT bounds comes out chunk-starved (2-3
terminals instead of 4, no visible terminal rows, CRASHES LabVIEW on
click - exception at EIP 0x00007FF7159F3BD9, LV2020 20.0.1f1). See
v3.7 for the fix.

### Cascade rule for `broken: 1`

An untyped/broken node makes everything downstream read broken in
`wires` output: with Rep1/Rep2 missing index+subarray inputs, the
FN input wire, SEL0's tunnel segment and the FNA->OutputArray exit
tunnel ALL showed broken:1 even though each wire call returned "wire
ok". Expect them to resolve once the Replace inputs are wired manually.

### Batch exit code

`lv_gateway_batch.vbs` returns exit code 1 if ANY line errored (even
`!`-tolerated ones) but still runs the whole script and the trailing
`wires` - judge results from the log, not the exit code.

## v3.7 growable-node session (2026-10-16) - ROOT CAUSE: bounds is REQUIRED

**Growable nodes (Replace Array Subset 3910, Build Array 2041,
Insert Into Array 3911, Delete From Array 3912, ...) MUST be placed
with explicit W,H bounds** (arg2="x,y,W,H"). Without bounds the node is
created CHUNK-STARVED: glyph-only icon, 2-3 anonymous terminals, no
terminal rows. Touching it in the IDE crashes LV2020 (exception at
EIP 0x00007FF7159F3BD9). NI docs (New VI Object): "bounds specifies
the width and height of the new object if the new object is resizable".
NI's own example (Adding Objects.vi) uses the same recipe: style ring
constant + class Function, so the Gateway approach is correct - it
just must always pass bounds for resizable styles.

### Bounds height -> chunk count (Replace Array Subset, width 46)

| bounds H | terminals | chunks |
|---|---|---|
| 33 | 3 | corrupt |
| 40 | 4 | 1 (correct) |
| 46, 53 | 6 | 2 |
| 60, 64 | 8 | 3 |

With bounds, LabVIEW packs as many whole chunks as fit the height -
overshoot OVERGROWS the node (46x64 gave 3 chunks). Use h=40 for a
1-chunk Replace Array Subset. Plain non-growable styles are unaffected
(Add, Select, QR etc. placed plain work fine).

### Replace Array Subset (1-chunk, bounds 46x40) terminal map - VERIFIED

All three wires verified broken:0 (grow_t4.vi / chk_g4.vi):

    [0]=array (in)                    InputArray|Rep c|0|n|0
    [1]=output array (out)            Rep|OutputArray n|1|c|0
    [2]=new element/subarray (in)     ... c|0|n|2
    [3]=index (in)                    ... c|0|n|3

Note [0]/[1] are SWAPPED vs the usual primitive convention
([0]=out first) - the wires verb prints terminal names, trust those.
Each extra chunk adds one element/subarray + one index terminal.

### Rule for the wire verb

A GetTerminal 1055 on a growable node means the node was placed
without bounds. Never probe terminals of a collapsed node. Test
fixtures: grow_t1..t4.vi, chk_g3/g4.vi (junk, cleanup).

### THE AUTO-TUNNEL TRAP - auto-created border tunnels are AUTO-INDEXED (root cause of a5/a6, found by user 2026-10-16)

When `wire` crosses a loop border, the auto-created LoopTunnel is
**Auto Index (Index Mode=1)** for arrays. An array crossing the border
delivers its LAST ELEMENT (scalar) inside the loop, NOT the array.
This silently mistypes everything downstream:

- sumtest9 worked because Init0 is a SCALAR const (indexing N/A).
- fn_t3/sortTmp_6: InputArray (DBL array) -> FN init crossed the border
  -> FN init got DBL scalar -> FN typed scalar -> FN.out scalar -> every
  array input it fed broke (IndexA/B, Rep1). The a5 SEL0.t crossing had
  the same poison.
- Isolated probes passed because their FN terminals were fed from
  loop-resident nodes (no border crossing).

**Fix: set the tunnel to Regular** - LoopTunnel:Index Mode property
(0=Regular, 1=Auto Index; lvscript/LoopTunnel_Index_Mode.html, RW).
New Gateway verb `tunnel` (spec given to user, 2026-10-16):

    verb=tunnel
    vi_path = <file.vi>%ForLoop|Loop1    (loop whose tunnels to change)
    arg1    = off | on | get             (Index Mode 0/1/read)
    arg2    = empty (ALL tunnels) | tunnel label

Loop -> Structure:Tunnels[] -> cast LoopTunnel -> write Index Mode ->
save; log 'label: old->new' per tunnel. Scalar tunnels are unaffected
by Index Mode, so applying to ALL is safe.

### FN terminal map (RANDOM PER INSTANCE - always determine per FN)

The FN Terms[] order VARIES BETWEEN FN INSTANCES. Two rotations are
known (exact cyclic rotations); **the 2026-10-19 session observed two
gateway-placed FNs that were BOTH Map A, refuting the earlier
'creation path determines the map' theory. The order is effectively
random per instance - determine it for EVERY FN:**

- **Map A**: `[0]`=input (sink), `[1]`=output (source), `[2]`=init
  (sink).
- **Map B**: `[0]`=output (source), `[1]`=init (sink), `[2]`=input
  (sink).
- **DETERMINATION PROCEDURE (no broken-wire probing)**: run
  `getNode;<vi>%Node|<fnlabel>;terms` - the terminal with
  `isSource: 1` is the OUTPUT. source=[0] -> Map B; source=[1] ->
  Map A. Both remaining terminals are sinks, so once the source index
  is known the init/input assignment follows from the rotation
  (Map A: init=[2]; Map B: init=[1]). If the source is at [2], no
  verified rotation covers it - settle with a run test
  (init=100/input=7, expect 7). Wire accordingly; if a wire still comes
  back wrong, delete by the UID shown in `wires` (NOT by wire-command
  line number - branched-wire UIDs) and rewire.
- FN terminal names are empty/inherited on all variants - do not
  rely on them.
- Context Help does NOT show terminal indices for the FN - that is
  why this map lives here, not in LabVIEW.

- **History (superseded by the per-instance rule above, kept for
  evidence)**: Map A first verified on IDE-placed FNs (FN2/FN3:
  sink/source/sink wiring evidence); Map B run-verified on
  pi_golden3/4; 2026-10-18 re-test on a fresh gateway-placed FN gave
  Map B (run: init=100/input=7 -> FNOut=7); 2026-10-19 two
  gateway-placed FNs gave Map A - hence creation-path theory REFUTED.
  Deleting a wrong FN wire can leave orphan border tunnels
  ('undirected tunnel' errors) - verify with `errors`, prefer a fresh
  copy when rewiring across the border.
- Proper fix (suggested to the gateway author): make analyze/wires print
  FN terminal NAMES (input/output/init) so no map is needed at all.

## v3.8 session (2026-10-16) - tunnel verb + SELECT TYPE RULE - SORT VI VALID

### `loop` verb tunnel control (user-implemented, VERIFIED)

    verb=loop; vi_path=<file.vi>%ForLoop|Loop1; arg1=tunnel:<idx>|tunnel:U<UID>; arg2=<mode>
    arg2 = -2 -> total tunnel count ('Tunnels: N', index ignored)
    arg2 = -1 -> tunnel status ('Tunnel[0], IndexMode: 0, UID=193')
    arg2 >= 0 -> set IndexMode: 0=Regular, 1=Auto Index, 2=Concatenate (outputs)

Verified: fn_t4.vi - count 1, status IndexMode 1 (auto! the root cause),
set 0, verify 0, UID=193 usable as tunnel:U193. Setting ALL tunnels to 0
is safe (scalar tunnels unaffected).

### SELECT TYPE RULE (the a7 bug - my design error, not a gateway one)

**t and f must be the SAME TYPE; the bool (comparison output) goes to
s[2], NEVER to f[1].** Wiring bool->f + DBL->t/s conflicts the node and
breaks the f-wire (a4-a7 'x>y? -> f' / 'x=0? -> f' rows). Correct bubble
sort wiring: GT.out->SEL_A.s[2], IndexB.el->SEL_A.t[3], IndexA.el->
SEL_A.f[1] (and mirrored for SEL_B). After the swap (bubble_a8):
**ZERO broken wires - sortTmp_8.vi is a complete valid bubble sort**
(minus the intentional exit wire FNA.out->OutputArray).

### Attempt-8 confirmed maps (all broken:0)

- FN: [0]=out, [1]=init, [2]=input - the full feedback cycle resolves
  once the border tunnel is Regular.
- RAS chain Rep1->Rep2 via [1]->n|0 works; SEL outputs feed [2]
  (new element/subarray) of 1-chunk RAS (bounds 46,40).
- Index Array PLAIN is fine for element/index/array terminals (fn_t5).
- Border rule (FINAL, revised 2026-10-17): ANY crossing - array, scalar,
  constant or NODE OUTPUT - is fine IF all border tunnels are switched
  to Regular right after the last crossing wire (loop tunnel:i;0). The
  old 'never wire a node output across the border' rule is superseded -
  it predates the tunnel verb. See 'Border rule (the #1 trap)' and
  pi_golden3/4 verification.

### Remaining for the sorted-output test — DONE (v3.9, see below)

Superseded: the test ran, found a real algorithm bug, and the full
inject/run/read cycle is now automated (arrread.exe, see v3.9 and
SKILL.md "Runtime testing with array data"). See v3.9.

## v3.9 session (2026-10-16) - array injection + runtime sort test - SORT VERIFIED

### arrread.exe - the array injection/reader tool

Canonical copy: `%SKILL%\scripts\arrread.cs` + `arrread.exe` (also noted
in SKILL.md "Runtime testing with array data"). Rebuild with the .NET 4.8
framework csc (C# 5 only: no `is Type x` patterns, keep it simple):

    "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe" -nologo
      -out:arrread.exe -r:Microsoft.CSharp.dll arrread.cs

Under git-bash, csc's `/flags` and even path args get mangled - use `-style`
flags and MSYS2_ARG_CONV_EXCL="*" when invoking the exe. Modes:

    get   <vi> <ctl>          print rank/len/elements of an array control
    set   <vi> <ctl> "9,1,5"  inject double[] (VT_R8)
    setint<vi> <ctl> "3,1,2"  inject int[] (VT_I4) - LV coerces to DBL, WORKS
    run   <vi>                Run(true) + 3s sleep
    cycle <vi> <ctl> "..."    set+echo+run+read in ONE process (USE THIS)

### SetControlValue / GetControlValue on arrays - the facts

- All-double variant arrays: WORK (earlier KB claim of silent no-op was a
  misdiagnosis). VT_I4 int[] also works (coerced).
- GetControlValue returns VT_ARRAY|VT_R8 (TypeName "Double()", VarType 8197).
  WSH cannot index it: v(i), Join(), For Each all fail; JScript VBArray
  rejects non-VARIANT typed arrays ("argument is not a VBArray object").
  UBound/LBound/IsArray DO work (2-element UBound = the old discriminator).
  .NET marshals it to System.Array - read elements in C# only.

### THE CROSS-PROCESS PERSISTENCE TRAP (cost: one false-negative test run)

set in process A, run/get in process B FAILS if the target VI has no open
front-panel window: when the COM client exits, the VI (loaded by
GetVIReference) can leave memory and the injected value is lost; the next
process re-loads the file with empty FP. sortTmp_8 tolerated the 3-process
flow only because its window was open in the user's GUI (sortTmp_8 session
left it visible). ALWAYS use `cycle` (single process), or keep the VI's
window open. Symptom if bitten: InputArray reads back len=0 right after a
"SET OK".

### The sort bug the runtime test caught (zero broken wires, still wrong)

sortTmp_8 v1 passed [2,1]->[1,2] (luck: n=2 wrap always pairs (0,1)) but
produced ALL-MAX for n>=3 ([3,1,2]->[3,3,3]). Root cause: the build script
never wired QR1 -> Rep1 index [3]; an UNWIRED RAS index defaults to 0, so
every iteration wrote min->pos0, max->pos(j+1); a later pass compares two
equal maxima and writes max into pos0. Fix (one wire):

    wire;<vi>;QR1|Rep1;n|1|n|3

After the fix: [2,1],[3,1,2],[5,4,3,2,1],[9,1,5,3,7,.5],[1,2,3,4,5],[7] and
(on sortArr_tmp) [3,3,1,2,3],[10,-5,7,0,3] all sort correctly. Lesson:
"zero broken wires" proves nothing about runtime - the n=2 case is a
code-review trap; always test n>=3 with distinct values.

### sortArr_tmp.vi - final state (the real deliverable)

- Backup of the pristine pre-build VI: gen/sortArr_backup.vi.
- Built via gen/build_real.txt = bubble_a8 recipe (minus the copy line)
  + QR1->Rep1 index fix + FNA->OutputArray exit wire + all array tunnels
  Regular. Wire list identical to fixed sortTmp_8, zero broken wires.
- Verified end-to-end via arrread cycle: 6/6 inputs sorted correctly.
- N formula: (size-1)^2+1 iterations, j = i mod (size-1) (QR1),
  j+1 (Inc1); SEL_A=min@Rep1[j], SEL_B=max@Rep2[j+1]; FNA carries the array.

## v3.10 (2026-10-16) - MCP server now exposes arrread + tunnel control

`mcp-labview/server.py` is up to date with everything above:

- **New MCP tool `arrread`** - wraps arrread.exe (modes get/set/setint/
  run/cycle) so array-in/array-out runtime verification works directly
  through MCP, no shell needed. `cycle` is the recommended mode
  (set+run+read in one process; avoids the cross-process persistence
  trap, works with the VI window closed). Smoke-tested end-to-end:
  cycle on gen/sortArr_tmp.vi InputArray "5,1,3" -> out len=3 [1, 3, 5].
- **`gateway` arg1/arg2 docs updated** for the v3.8 `loop` tunnel
  control (arg1='tunnel:<idx>' or 'tunnel:U<uid>', arg2 -2/-1/0/1/2)
  plus the auto-tunnel trap note. Smoke-tested: loop tunnel:0;-1 on
  gen/sumtest9.vi%ForLoop|Loop1 -> 'Tunnel[0], IndexMode: 0, UID=160'.
- `WRITE_VERBS` no longer lists the unimplemented `delete` verb
  (roadmap-only); unknown verbs hit Gateway's default case anyway.
- Reminder: restart the Zed context server after editing server.py -
  Zed caches the tool list per session.

## v3.11 session (2026-10-16) - PI MONTE-CARLO GOLDEN BUILD + FP-OBJECT RULE + BORDER-EXIT RULE

A fresh-session rebuild of the Pi Monte-Carlo task was driven using ONLY
the documented harness (no visual analysis). Result: `gen\pi_golden3.vi`
built 100% via gateway verbs and RUN-VERIFIED: **PI = 3.1398 at N=1e6**
(PI0 = raw hit count). This section is the canonical playbook for this
difficulty level (loop + FN accumulator + Select + comparison + tunnels).
Golden scripts kept in gen\: pi_golden_place.txt, pi_golden_wire.txt,
pi_golden3*.txt. Discard pi_golden.vi / pi_golden2.vi (polluted).

### RULE 1 - FP objects (numind/numctl) are TOP-LEVEL ONLY (SUPERSEDED by v3.12)

(Superseded: Gateway v3.12 places FP objects inside structures - see
v3.12 section. Kept for history and because pre-v3.12 gateways still
behave this way.)

`place numind` with a `%ForLoop|Label` resolver -> **ERROR 1060: New VI
Object**, deterministically (5/5 attempts incl. a 3-object scratch VI).
Root cause (official docs, glang/New_VI_Object.html): "to add a new
control to the front panel of a VI, wire a reference to either the
relevant VI or the front panel of the relevant VI to owner refnum. To
place a new object inside of a For Loop, wire a reference to the diagram
of the relevant For Loop." Controls/indicators belong to the VI/FP; a
loop DIAGRAM is only a valid owner for BD nodes. An indicator can never
live "inside" a loop - its terminal is a top-level-diagram object.
Related trap: **placing a BD node with a resolver at coordinates OUTSIDE
the structure's bounds silently drops it TOP-LEVEL** (FN2 at 540,200 -
"place ok", wrong owner). After inside-placement, verify ownership with
`analyze` (children listed under the ForLoop) before wiring.

### RULE 2 - set ALL border tunnels Regular AFTER the last wire

ANY wire crossing the loop border (including a FN output -> top-level
indicator, and labeled-constant scalars) auto-creates an AUTO-INDEX
tunnel. Until set Regular the tunnel segment reads `broken: 1` even when
"wire ok" was reported. build_real.txt (sortArr) had the fix as lines
67-69; pi_golden1/2 missed it and their exits stayed broken. Canonical
fix sequence, AFTER the last wire:

    loop;<vi>%ForLoop|Loop1;tunnel:0;-2      -> tunnel count N
    loop;<vi>%ForLoop|Loop1;tunnel:i;0       -> for i in 0..N-1
    wires;<vi>                               -> verify ZERO broken:1

Verified: pi_golden3 exit `FN1 -> PI0` went broken:1 -> broken:0 purely
from this step. Design pattern that follows: keep the accumulator and
ALL arithmetic inside the loop, export ONLY via the FN output, and do
final scaling math (x4, /N) at TOP LEVEL where no crossing is needed.

### Pi Monte-Carlo golden recipe (N=1e6)

Nodes top-level: NConst(1000000), FourConst(4), ZeroConst(0), OneConst(1)
numconsts; MUL4 (multiply), DIV2 (any:1053), PI1 (numind) for final math;
PI0 (numind) debug = raw hits. Inside Loop1 (all coords within loop
bounds, loop at 80,100): RN1,RN2 (any:1070), SQX,SQY (multiply), R2 (add),
LE1 (any:1104), SEL1 (any:1516), ACC (add), FN1 (any:2353), P (multiply),
DIV (any:1053). Wires (terminal maps per the table above): RN->SQ x&y,
SQ->R2, R2->LE1[2] x, OneConst->LE1[1] y (r^2<=1), LE1->SEL1[2] s,
OneConst->SEL1[3] t, ZeroConst->SEL1[1] f (t/f same type I32 - SELECT
TYPE RULE), SEL1->ACC[1] y, FN1[0]->ACC[2] x, ACC->FN1[2] input,
ZeroConst->FN1[1] init (scalar crossing), NConst->Loop1 c|0|n|0 (N),
ACC->P[1], FourConst->P[2], P->DIV[2], NConst->DIV[1] (all inside),
FN1[0]->PI0 c|0 (exit), then top-level FN1[0]->MUL4[2], FourConst->MUL4[1],
MUL4->DIV2[2], NConst->DIV2[1], DIV2->PI1 c|0. setval integers only
(I32 constants). Then RULE 2. Then run_vi_get_value.vbs (async poll fix).

### Wire "ok" can be a FALSE POSITIVE

`wire ok DIV --> PI2` was reported, yet the wire NEVER persisted to disk
(the known in-memory-only wire + failed-save case, v3.4). Always
re-verify with `wires` after each batch and grep for `broken: 1`; do not
trust the absence of an ERROR line alone.

## v3.12 session (2026-10-17) - Gateway update: FP objects inside structures, delete verb, UIDs

User upgraded Gateway.vi. All verified on gen\fp4/fp5.vi:

### 1. Front-panel objects ARE now placeable inside structures

`place;<vi>%ForLoop|L1;any:21004;30,100;PI2` -> the gateway creates the
Numeric Indicator on the FP and MOVES ITS TERMINAL into the loop's
diagram. Verified: `any:21004` (indicator, modern), `any:21003`
(control, modern) and the classic named `numind` - all land inside as
`ControlTerminal [label]` and wire normally to nodes inside
(CTL1->A1 c|0|n|2 broken:0). This SUPERSEDES v3.11 RULE 1: indicators
can now live "inside" a loop, so the border-exit workaround (FN
export + top-level math) is no longer required - though it still works.
'Numeric Indicator (modern)'=21004, 'Numeric Control (modern)'=21003
(both in style_codes.json).

### 2. New verb `delete`

    delete;<vi_path>;arg1=Class;arg2=identifier
    vi_path = resolver of the CONTAINER (objects inside it) or plain
              VI path (top-level objects)
    arg1    = class name; 'GObject' matches ANY object, 'Wire' for wires
    arg2    = 'U:<uid>' or 'L:<label>'

Verified: L: inside structure, U: at top level, GObject base class,
Wire by UID. Saves automatically, prints 'Delete ok'.

### 3. UIDs everywhere

`analyze` now prints `UID: n` per object; `wires` prints `UID: n` per
wire. Use these for `delete ... U:`.

### TRAP: gateway_batch 'delete;<path>' meta-command shadows the verb

The batch runner has a script-level `delete;<path>` meta-command that
DELETES A FILE from disk (retry workflow). It used to match ANY line
starting with 'delete' and silently ate every delete-verb line - and
deleted the .vi named in vi_path instead (cost: pi_fp_test.vi, fp2.vi,
fp3.vi). FIXED: now only the exact 2-field form 'delete;<path>' is the
meta-command; 3+ field lines are routed to the Gateway verb. The
single-verb driver lv_gateway.vbs never had this problem.

### VI-state hazard: 1055 + 'VI Path' append = target file missing/gone

After a meta-delete ate pi_fp_test.vi, every place on it failed with
'ERROR 1055: New VI Object ... VI Path: <b>...</b>'. If place errors
suddenly carry a VI Path append, check the file still exists -
especially after delete experiments.

## v3.13 session (2026-10-18) - SHIFT REGISTERS: addSR + s-kind terminal wiring (RUN-VERIFIED)

User added shift-register wiring to the Gateway. Verified end-to-end on
gen\sr1.vi (sum via SR: Out1 = 10 for N=5, init=0).

### Workflow (SR must PRE-EXIST)

1. Create the SR first: `loop;<vi>%ForLoop|L1;addSR;<Y>;<Label>` ->
   'Loop: <Label>, NewShiftReg, UID=<n>'. One addSR = one SR (both
   sides). Repeat for stacked SRs (SR1, SR2, ... in creation order).
2. Wire with the s-kinds below.

### s-kind terminal identifier (wire arg2 fields: <srcKind>|<srcIdx>|<dstKind>|<dstIdx>)

Kind = 's' + side + io + input#; the IDX FIELD after '|' = WHICH shift
register (0-based, addSR creation order) when the loop has several:

| Kind | Terminal | Direction |
|---|---|---|
| `slo<i>` | left OUTSIDE (init) | **inout** - sink: wire the init value INTO it |
| `sli<i>` | left INSIDE (prev value) | **output** - source: wire FROM it |
| `sri<i>` | right INSIDE (current value) | **inout** - sink: wire the per-iteration value INTO it |
| `sro<i>` | right OUTSIDE (final value) | **output** - source: wire FROM it |

- The digit AFTER sli/slo (input#) selects the input of a MULTI-INPUT
  shift register. Regular SRs have exactly one input -> always 0.
  `sli1|0` (input #1 of SR0) -> ERROR 1055 Connect Wire. POSTPONED:
  work with regular (single-input) SRs only for now.
- Wrong-direction wires on s* terminals persist as broken:1 (e.g.
  Num1 -> sli0|1 'creates a wire' but broken) - check `wires`.
- Terminals appear in `wires` as classes `LeftShiftRegister` /
  `RightShiftRegister`.
- Canonical wiring (accumulator): `Num1|L1 c|0|slo0|0` (init),
  `L1|A1 sli0|0|n|2` (prev value -> Add.x), `i|0|n|1` (Add.y),
  `A1|L1 n|0|sri0|0` (Add.out -> right inside),
  `L1|Out1 sro0|0|c|0` (final -> indicator). RUN-VERIFIED: Out1=10.
- **CANONICAL ONE-PASS GOLDEN SCRIPT: gen\sr_golden.txt -> sr_golden.vi**
  (newvi -> place loop/Num1 ctl/Out1 ind/N5 const/A1 add -> addSR ->
  the 6 wires -> setval N5 -> done). Built in ONE batch, ZERO broken
  wires, RUN-VERIFIED Out1 = 10 (2026-10-18). Copy this script and adapt
  labels/coords - it is the reference for ANY SR code generation.
- **SR smoke test for a fresh session** (proves the gateway SR support
  works): run gen\sr_golden.txt via lv_gateway_batch.vbs under a NEW vi
  name, then `run_vi_get_value.vbs <vi> Out1` -> 10 with N5=5, Num1=0.
- Runtime control init (e.g. Num1) - setval does not support controls:
  use `arrread set <vi> Num1 <value>` (or cycle). Indicators read via
  run_vi_get_value.vbs / arrread get.

### setval does NOT support controls (yet)

`setval` resolver classes: NumericConstant/StringConstant/Constant work;
`NumControl|NumCtl|DigitalControl|NumericControl|Numeric|Control|`
`ControlTerminal|NumExControl` ALL FAIL on a numeric control (1092 /
1057 / SelectByLabel not-found - the resolver's class specifier is a
fixed set). To set a CONTROL value use **arrread** (set/cycle modes).
Reading works fine via run_vi_get_value.vbs (GetControlValue).

### Status note

sr1.vi reported 0x3EB not-executable after the sli1 probe - root cause
(user-identified): the probe's leftover node **A2 (Add) had unwired
required inputs**, which breaks the VI even though every WIRE reads
broken:0. `wires` cannot see unwired inputs - after placing nodes,
either wire ALL required inputs or delete the leftover
(`delete;<vi>%ForLoop|L1;GObject;U:<uid>`). With A2 deleted the VI runs
again: Out1 = 10. The 1055/1092/1057 class probes above were done on it
before that. SR2 remains with the user's test wires (Num1 -> slo0|1 and
Num1 -> sri0|1, both broken:0, harmless).

## v3.14 research (2026-10-18) - ERROR-LIST ACCESS: VI Server cannot; Gateway `errors` verb REQUIRED

### Verdict (empirically verified)

The IDE Error List / the REASON a VI is broken is **NOT accessible**
via raw VI Server COM (VBScript). Probe: `mcp-labview/scripts/test_errorlist.vbs`
against a copy of the broken sr1.vi (Add with unwired input):

```
vi.IsBroken   -> 0x1B6 member not found
vi.ErrorList  -> 0x1B6
vi.Errors     -> 0x1B6
vi.BlockDiagram -> 0x1B6   (raw COM cannot reach the BD at all)
```

Doc-mirror cross-check: `lvprop/VI_p.html` (full VI property table) and
`lvprop/VI_m.html` (full VI method table) contain **no** Is-Broken /
error-list member. Only these exist, and all need BD traversal:

- `lvscript/Terminal_Connected_Wire.html` - Terminal:Connected Wire
  (id 10308, read-only): NULL/invalid when the terminal is unwired.
- `lvscript/Wire_Is_Broken063.html` - Wire:Is Broken? (per-wire).
- `lvprop/VI_m.html` - VI method Block Diagram:Remove Bad Wires
  (cleanup only, not diagnostics).

Known-but-insufficient alternatives:
- `vi.Run` on a broken VI -> 0x3EB "VI is not executable" - tells THAT
  it is broken, not WHY.
- Gateway `wires` verb broken: flags - misses unwired NODE inputs
  (sr1.vi showed all broken:0 while genuinely broken, root cause A2).
- `extract_vi` PNGs - visual only, not greppable.

### PROBE TRAP: stale Err in VBScript probes

In the probe, reading `lv.LabVIEWVersion` raised 438 (member not found)
under On Error Resume Next; the stale Err.Number was then misattributed
to the NEXT check (`GetVIReference`), producing a phantom failure.
`Err.Clear` after EVERY probe read, before using Err.Number again.

Also: when probing, prefer a FILE COPY (`gen\sr1_probe_tmp.vi` pattern,
delete after) so the run does not disturb the user's control values -
not because the IDE-open VI is unsupported (it is the standard mode;
the original 0x1B6 here was a stale-Err bug, see above).

### SPEC: new Gateway verb `errors` (READ verb, awaiting implementation)

Purpose: reproduce the IDE Error List programmatically. Read-only -
goes through the temp-copy path in tool_gateway, like analyze/wires.

Implementation (VI-side, inside Gateway.vi, reusing the existing
traverse-for-GObjects infrastructure):

1. Traverse every diagram of the VI; for every Node, for every
   element of Terms[]:
   - Read Terminal:Connected Wire. If NULL/invalid AND the terminal is
     a REQUIRED INPUT -> emit
     `UNWIRED: <ClassName> [<Label>] Terms[<idx>] UID=<n>`.
2. For every Wire: if Wire:Is Broken? = TRUE -> emit
   `BROKEN WIRE: UID=<n> <src> --> <dst>`.
3. If nothing found: emit `VI CLEAN` (so empty output is unambiguous).

Output must stay machine-greppable, one line per finding, consistent
with analyze/wires. Optional (later): classify required vs optional
inputs so optional-only unwired terminals don't false-positive.

### IMPLEMENTED (user, 2026-10-18) - `errors` returns the IDE ERROR-WINDOW CONTENT

The shipped verb does NOT do BD traversal. It returns the content of
the IDE-embedded Error List window for the VI - even better for
analysis, because it is exactly what the IDE reports (all item types,
not just unwired terminals). VERIFIED output format:

```
Errors of <path>. Errors list = '<msg>;<msg>;
' Details = '<details>;<details>;
'
```

- Broken VI (1 error, sr1.vi): `Errors list = 'Contains unwired or
  bad terminal'`, `Details = 'One or more required inputs ...'`.
- Clean VI (sr_golden.vi): both strings EMPTY -> treat empty as VI CLEAN.
- Multi-error (2 unwired nodes): items are ';'-separated and
  index-aligned (msg[i] <-> details[i]).
- LIMITATION: the item text does NOT name the offending object (IDE
  shows e.g. 'Add: Contains unwired...'); locate the culprit by pairing
  `errors` with `analyze`/`wires`, or extract PNGs.

Workflow: `errors` -> if non-empty, pair with analyze/wires (or
extract) to find the culprit -> fix by UID (wire or delete) ->
re-run `errors` until empty -> run-verify via run_vi_get_value.vbs.
If the offending object is a leftover unwired node, `delete` it by UID.

Workflow once shipped: `errors` -> fix by UID (wire the listed
terminal or `delete;...;U:<uid>` the leftover node) -> re-run
`errors` until `VI CLEAN` -> then run-verify via run_vi_get_value.vbs.

### Rule for the agent (until `errors` ships)

A VI with all wires broken:0 can still be broken. After ANY `place`,
either wire all required inputs or `delete` the leftover node
immediately; verify by running the VI (0x3EB = broken) or by extract
PNG inspection.

## v3.15 (2026-10-18) - `wire` verb returns PER-TERMINAL isSource + Name AT CREATION

### New wire response format (user-implemented, verified)

Every `wire` call now reports both connected terminals right after
creating the wire (NOT in the `wires` verb - that keeps the old
`Name [Label][OwnerClass]` display without flags):

```
wire ok Num1 --> A1, Description: Terminal: Num1, type: c, index: 0isSource: 1, Name: Num1 -> Terminal: A1, type: n, index: 0isSource: 1, Name: x+y
```

(Note the cosmetic bug: no space between `index: N` and `isSource`.)

- **isSource: 1** = the terminal DRIVES the wire (node output,
  constant, control terminal); **isSource: 0** = sink (input).
- **Name** = the primitive's terminal name (Add: `x+y`/`y`/`x`), the
  control/constant label, or EMPTY for Feedback Node terminals.
- `wire ok` means the wire was CREATED, not that it is LEGAL - always
  read the flags in the response.

### LEGAL-PATTERN RULE (verified matrix, wt_test.txt)

| src isSource | dst isSource | verdict |
|---|---|---|
| 1 | 0 | legal - keep |
| 1 | 1 | output-to-output - wire comes back broken:1 |
| 0 | 0 | input-to-input - broken:1 (two sinks, zero sources) |

Verified: N5->Add[2] (1/0, legal, broken:0); Add[0]->Num1 (1/1,
broken:1); A1[2]x->Add[1]y (0/0, broken:1); Add[0]->Add[1] (1/0,
legal). Cross-check with `errors` verb matched.

### Terminal maps now self-document via Name

- **Add**: `[0]`=x+y (OUTPUT), `[1]`=y, `[2]`=x - confirms the golden
  recipe wiring (`FN1[0]->ACC[2]` = out->x; `SEL1->ACC[1]` = ->y).
- **Feedback Node**: Name is EMPTY - the map still comes from the
  v3.7 Map A/B knowledge (creation-path dependent). BUT isSource is a
  harmless role probe: wire `FN[0]-><any sink>` and read the response
  - if `isSource: 1` on FN[0] it is the output (Map B, gateway-placed
  FNs); the wire may still be broken and should then be deleted (with
  its orphan tunnels - see v3.14). isSource cannot distinguish
  input-vs-init (both sinks) - that still needs the run test.

### FP ITEM SIZE RULE (place arg2 W,H) - user-reported, visually verified 2026-10-18

For FRONT-PANEL objects (numctl/numind/strctl/strind/any:21003/
any:21004/...) arg2 W,H is the FRONT-PANEL ITEM SIZE and must be
**non-zero** (e.g. 80x32). With 0 (or omitted) the item is created
0-size: label only, no visible body on the FP -> unreadable there.

Verified: fp_size_tmp.vi (copy of sr_golden) - P1 placed with
`'x,y,80,32'` renders as a normal indicator; P0 placed with `'x,y'`
shows only the orphaned label. TRAP: COM GetControlValue still returns
the value from a 0-size item (P0 read 5 after run), so run tests do
NOT catch this - check with an extract FP PNG when it matters.

Note: sr_golden's own Num1/Out1 are also 0-size (placed before this
rule) - harmless for COM-driven testing, but re-place with W,H if a
human must read them on the panel.

## v3.16 (2026-10-18) - Placing and wiring NI library subVIs (gateway `place`, subVI mode)

Proven 2026-10-18 on `gen\GaussianRandom.vi` (Gaussian White Noise.vi from
`1siggen.llb`, mean 0.5 / sigma 0.1, statistically verified over 100 runs).

### Why subVIs

Style codes (`any:<code>`) cover only primitives. The rich functionality of
LabVIEW lives in **subVIs shipped with the IDE** (vi.lib, analysis LLBs,
DAQmx, ...). These can be placed on a generated VI's diagram with:

```
place;<target vi>;any:0<full path to subVI .vi or .llb member>;<x,y>;<label>
```

- `any:0` prefix = "style code ignored, place the file at this path".
  The `0` is literal: `any:0C:\Program Files\...`.
- LLB members: path straight into the .llb file, e.g.
  `any:0C:\Program Files\National Instruments\LabVIEW 2020\vi.lib\Analysis\1siggen.llb\Gaussian White Noise.vi`
- The subVI lands as a normal node; its terminals appear on the placed
  node and are wireable via `n|<index>` - but read the terminal-indexing
  section below first.

### Finding the subVI path

Search the installed LabVIEW tree (multiple versions are usually present -
pick the one the background COM instance runs, e.g. LabVIEW 2020 64-bit):

```
find "/c/Program Files/National Instruments/LabVIEW 2020" -iname "*.vi" | grep -i gaussian
```

Typical locations: `vi.lib\Analysis\*.llb`, `vi.lib\signalproc\...`,
`vi.lib\Utility\...`. When in doubt about which VI the gateway will load,
match the bitness/edition of the spawned LabVIEW instance
(`manage_processes` list shows the executable path).

### Learning the interface BEFORE wiring

Two reliable sources, in order:

0. **`getNode` terms on the subVI path (v3.17, preferred)** - see the
   v3.17 section: returns every connector-pane cell with label,
   indicator flag and wiring rule. No wiring, no probing. Use
   extract_vi for the DATA TYPES (getNode does not show them).
1. **extract_vi on the subVI** - works on a copy, lists every control and
   indicator with types (strings export: `CONTROL ID=80` = control,
   `ID=82` = array indicator, etc.) and the Context-Help descriptions.
2. **Context Help connector pane** (user can screenshot, or decompile
   `help\lvanls.chm` with 7-Zip: `"C:\Program Files\7-Zip\7z.exe" x
   -o<dir> "...\lvanls.chm" "*Gaussian*"` and read the HTML). The pane
   drawing shows the numbered cell of every terminal.

### CRITICAL: terminal indices are connector-pane CELL numbers, not logical order

For subVI nodes, `Terms[]` is indexed by the **connector pane cell
number** (the numbers NI shows in Context Help), NOT "inputs first,
output last". The 4x2x2x4 pane is numbered 0..11:
row1 (top) 0-3, row2 4-5, row3 6-7, row4 (bottom) 8-11.
**Wiring an empty pane cell creates a broken wire with NO name** - if
several probes all come back `broken:1` with empty `Name:`, you are
hitting empty cells, not wrong types.

Verified example - Gaussian White Noise.vi (4815):

| terminal | cell | type |
|---|---|---|
| error | 0 | I32 error **code** out (NOT an error cluster) |
| Gaussian noise pattern | 3 | 1D DBL array out |
| initialize? | 7 | Boolean in |
| seed | 9 | I32 in (<=0 or unwired = random reseed) |
| standard deviation | 10 | DBL in |
| samples | 11 | I32 in |

### Primitive terminal order is OUTPUT-FIRST (opposite of the subVI rule)

For arithmetic primitives the gateway observed (LV 2020):

- Add: `0`=x+y (out), `1`=y, `2`=x
- Divide: `0`=x/y (out), `1`=y, `2`=x
- Index Array: `0`=array in, `1`=element (out), `2`=index (in)

Do not trust "inputs first" folklore - read the `wire` response's `Name`
fields; a wire command returns both terminals' names and isSource flags,
and the `wires` verb lists every wire's terminals **source first** with a
`broken:` flag. That output is ground truth.

### Workflow that worked end-to-end

1. `newvi` the target, `place` the subVI via `any:0<path>` with a label.
2. `extract_vi` the subVI (copy) to learn controls/types; check Context
   Help pane numbers if available.
3. Wire data path; after each batch run `wires` and require **zero
   `broken:1`**. Fix by `delete;vi;Wire;U:<uid>` + rewire.
4. Probes: if a terminal's identity is unclear, wire it to a throwaway
   numind, run the VI, read the value (0.1 -> standard deviation,
   1 -> samples, -1 -> seed default). Delete probe wires+indicators
   afterwards (`delete;vi;GObject;L:P1` removes FP object + terminal).
5. Verify: gateway `errors` verb (empty = clean), then
   `run_vi_get_value.vbs "<vi>" "<control>"`, then a statistics loop
   (run N times, read indicator, compute mean/stdev) for anything random.
6. `extract_vi` the finished VI once more and view the diagram PNG as a
   final visual check.

### Constants: fractional values

Scripted numeric constants (`any:2005`) are I32; `setval ... frc`
silently writes 0 and `dec` truncates. Build DBL constants with integer
constants + Divide: 0.1 = 1/10, 0.5 = 1/2. Divide outputs DBL, which
coerces cleanly into DBL inputs (and I32 inputs take I32 constants
directly).

### Other gotchas

- A wire may come back "wire ok" but `broken:1` with reversed
  source/sink - "wire ok" only means created. Always read `wires`.
- Old LLB VIs often have an `error` terminal that is a plain I32 error
  **code** (wire it to Error Cluster From Error Code if needed) - do not
  assume an error cluster.
- `seed`/`initialize?` left unwired on signal-generation VIs give a fresh
  random sequence per call - usually what a "random number" VI wants.
- Deleting a wire whose UID was merged into a multi-branch wire tree
  returns "GObject with ID not found" - harmless; delete the root wire
  UID reported by `wires`.

## v3.17 (2026-10-18) - `getNode` verb: node terminal / connector-pane info (READ)

User-implemented; arg1 = type of info requested, currently only
`terms`. Two modes by vi_path form. Read verb - copies to temp like
analyze/wires (a vi.lib path is copied fine too).

### Mode A - a placed node: vi_path = `vi%Node|<label>`

```
getNode;<vi>%Node|A1;terms
Term[0] UID: 113, name='x+y', isSource: 1,  isHidden: 0, wireUID: 142, wireBroken: 0
Term[1] UID: 116, name='y', isSource: 0,  isHidden: 0, wireUID: 139, wireBroken: 0
Term[2] UID: 119, name='x', isSource: 0,  isHidden: 0, wireUID: 134, wireBroken: 0
```

- Shows EXACTLY what each terminal is for (names, direction) and its
  wiring state (wireUID/wireBroken, or 'No wire connected').
- VERIFIED: sr_golden A1 (Add, matches v3.15 map; wireUIDs match the
  known wires 142/139/134); pi_golden3 FN1 (Term[0] source -> Map B
  again, names inherited as known).

### Mode B - a subVI file: vi_path = plain .vi/.llb path

```
getNode;C:\...\1siggen.llb\Gaussian White Noise.vi;terms
Control[0]:  UID: 617, Label: error, Indicator: 1, IsOnConPanel: 1, Wiring rule: Recommended
Control[1]: not linked
...
```

- Returns the CONNECTOR PANE: cell index (= the Terms[] index used for
  wiring, v3.16), label, Indicator flag (1 = output), IsOnConPanel,
  and the wiring rule (Invalid Wire Rule / Required / Recommended /
  Optional / Dynamic Dispatch). 'not linked' = empty cell.
- VERIFIED: reproduces the v3.16 Gaussian White Noise table exactly
  (cells 0/3/7/9/10/11) - this REPLACES the empirical probe workflow
  from v3.16 (see the note added there).

### LIMITATION - Feedback Node

`getNode` on a FN shows the SOURCE terminal (isSource: 1) but init and
input are BOTH sinks (isSource: 0, empty names) - which sink is init
is still only known from the v3.7 Map A/B creation-path rule (or a
run test). FN output: gateway-placed FNs = Map B.

## v3.18 field notes (2026-10-19) - fresh-VI pi build: integration + Monte Carlo end-to-end

User-session lessons from building pi-integration and pi-Monte-Carlo
end-to-end in one session (Empty.vi, live in the user's IDE). These
correct/extend the notes above.

### Terminal maps (the biggest time sink)

- Arithmetic/primitives (Add, Multiply, Divide, Less Or Equal?, Select, ...)
  use OUTPUT-FIRST Terms[]: n|0 = output, n|1 = y (f on Select), n|2 = x
  (s on Select), n|3 = t (Select only). The wire response prints the terminal
  Name (x, y, x*y, "s? t:f") - trust it over documented indices.
- "wire ok" does NOT mean connected. Wrong-terminal wires still report ok.
  Check isSource flags (legal = src 1, dst 0) and confirm with `wires`
  (broken: 1 = wrong terminal).
- ForLoop Terms[] WITH a shift register (v3.12): [0] = N (count, sink,
  wire c|0|n|0), [1] = RightShiftRegister outer, [2] = LeftShiftRegister
  outer; n|3 and n|4 raise ERROR 1055. The older "[0]=i, [1]=N" note is
  wrong for v3.12; i is addressed by kind i|0, not n|.
  pi_golden3.vi (c|0|n|0 for the count) is the authoritative example.

### Labels and resolvers

- place takes EXACTLY 5 fields; label = arg3. A trailing 6th field is
  silently ignored -> unlabeled object -> every later setval/wire fails
  with ERROR 1092 "Traverse Initialization Failed".
- setval resolver class must be the SHORT name: %Constant|X works;
  verbose %Numeric Constant|X fails with 1092.
- Placed numeric constant is I32: setval integers only (frc silently
  writes 0). Build DBL constants from integer Divides - LabVIEW Divide
  promotes I32/I32 to DBL (0.5 = 1/2).

### Tunnels and the autowire trap

- A scalar wire crossing a loop border auto-creates an AUTO-INDEX tunnel:
  broken/undirected until loop ... tunnel:i;0 (Regular). Do border
  crossings LAST, then set the new tunnel Regular.
- Autowire (Auto Wire? = TRUE) can merge a new wire through an existing
  tunnel or onto the nearest terminal - "wire ok" but broken. If a wire
  lands wrong: delete the wire (UID from wires output) AND any segments
  through the tunnel before retrying.
- Deleting the RightShiftRegister (UID from addSR) removes the WHOLE
  shift register - clean way to redo SR wiring. SR kinds: sli0=read,
  sri0=write, sro0=final, slo0=init (unwired init = 0).

### UIDs and verification

- Write verbs return REAL UIDs; analyze/wires copy the VI to a temp copy -
  a UID taken from analyze output may fail to delete (ERROR 1093). UIDs
  from wires output are stable and delete correctly.
- The errors verb is ground truth: empty string = VI is clean. Never
  trust wire responses alone.
- Runtime check: copy the VI first, use run_vi_get_value.vbs;
  vi.Run(True) is ASYNCHRONOUS - poll until stable (2x500 ms). Running
  the IDE-open VI also works and the user watches it live - but
  copy-first keeps verification honest and does not disturb the user's
  control values.

### Proven order of operations (first-try success on the 2nd build)

place loop -> place nodes/constants inside -> setval -> wire loop count
(c|0|n|0) -> addSR -> wire SR terminals -> wire internals (out=n|0,
y=n|1, x=n|2) -> border crossings last + tunnel:0;0 -> wires + errors ->
run on a copy.

### Style codes used repeatedly

Add 1050 - Multiply 1052 - Divide 1053 - Random (0-1) 1070 -
Less Or Equal? 1104 - Select 1516 - For Loop 2002 - Numeric Constant 2005 -
Numeric Indicator (modern) 21004 - Feedback Node 2353.
Lowercase names (numconst, numind, multiply, add) also work as place types.

## v3.19 (2026-10-19) - `wires` output: terminals now carry UID + owning Node{UID, Label}

User-implemented. Every terminal in the `wires` output is now

```
Label(TermUID) [][OwnerClass] of Node{ UID, Label: <node label>}
```

Verified on gen\chk_fn6.vi (matches the author's example byte-for-byte):

```
Wire: label:"" broken: 0  UID:227->  FC(UID:141) [][BooleanConstant] of Node{ UID:142, Label: FC} -->
  f(UID:154) [][Function] of Node{ UID:139, Label: SEL_A};
  f(UID:184) [][Function] of Node{ UID:165, Label: SEL_C};
  s(UID:203) [][Function] of Node{ UID:180, Label: SEL_D};
  t(UID:213) [][Function] of Node{ UID:180, Label: SEL_D};
```

- Source FIRST, then ALL sinks separated by ';' - fan-outs are fully
  visible (FC drives 4 sinks on one wire tree).
- Cross-checked: getNode on SEL_D shows Term[2] s UID:203 wireUID:227,
  Term[3] t UID:213 wireUID:227; analyze shows Function SEL_D UID:180
  with ParameterTerminals 196/200/203/213 and wires 227/221/218. All
  three verbs agree.
- FN/SR caveat resolved: the terminal NAME may still be inherited
  (FN terminals), but the owning node's Label+UID is now explicit, so
  every terminal is attributable.

### Restoring a block diagram (the complete toolchain)

`analyze` (objects: ClassName, label, UID) + `getNode terms` per node
(terminal index -> name/isSource/UID/wire) + `wires` (connectivity with
broken flags) = the full block diagram in text: objects, terminals,
roles, wiring, direction and fan-out. Use `extract_vi` PNGs only for a
final visual sanity check.

## v3.20 (2026-10-19) - session report: FN randomization confirmed, special constants, behaviors

From the user's pi-integration/Monte-Carlo/histogram session (gateway
v3.12-era, Empty.vi). Full subVI pane tables + style-code terminal maps
live in `references/subvi-placement.md`; MCP fallback notes in
SKILL.md. The essentials recorded here:

### FEEDBACK NODE: order is RANDOM PER INSTANCE (rule revised)

Two gateway-placed FNs in this session were BOTH Map A - the earlier
'gateway-placed -> Map B' rule (and the 2026-10-18 creation-path
theory) is REFUTED. Current rule (recipe v3.7 section + SKILL.md):
`getNode;<vi>%Node|<fn>;terms` -> the isSource:1 terminal is the
output; source=[0] -> Map B, source=[1] -> Map A, init/input follow
from the rotation. Never assume; never trust FN terminal names.

### Special constants

- `any:23505` ("Pi Multiplied By 2") places a plain value-0 Numeric
  Constant, SILENTLY - the classic wrong-distribution bug.
- `any:23504` ("Pi") places a real FixedConstant (class FixedConstant
  in wires). 2pi = Pi x 2 through a Multiply.
- Diagnostic: decode the internal variable via chain rule
  (y=(z/10+1)/2 => sigma_z = 20*sigma_y, mean_z = 20*(2*mean_y-1)) and
  compare against the closed-form distribution - a Rayleigh (z-mean
  1.2533, z-sigma 0.6551) is the signature of a dead cos factor.
  20 quick runs detect 'wrong'; 1M samples via a histogram VI
  identify WHICH wrong.

### Constant data-type discrepancy (unresolved, verify per VI)

Earlier sessions: placed numeric constants are I32 (frc silently
writes 0). This session: constants behaved as DBL (any:2005), with
DBL->I32 coercion failing on already-typed I32 sinks ("The type of the
sink is long [32-bit integer]") while coercing fine on adaptive sinks
(loop N). setval dec writes integers correctly either way. Safe
practice: integers via dec; fractional values via integer Divides;
check the sink's expectation via errors text when in doubt.

### Behaviors confirmed

- Same source -> two destinations across a loop border: ONE wire
  object branches into two auto-index LoopTunnels (broken: 0) -
  correct for exporting an array from a loop; no tunnel-Regular fix
  when the outside sink wants an array.
- Fan-out from one constant to several sinks merges into one wire
  object (one UID).
- A subVI call inside a 1M-iteration loop is fine (~2 s).
- Wire kind `n` on a constant label -> ERROR 1055 (GetTerminal.vi);
  constants are kind `c`.
- Deleting the wrong UID (or misreading branched-wire UIDs) deletes
  GOOD wires - always delete by the UID shown in `wires`, never by the
  wire-command line number.
- The `errors` verb's details can be garbled/concatenated, but "The
  type of the sink is ..." reliably reveals element counts and types
  of both sides (this is how the Bundle element count was decoded).
- When statistics look wrong: isolate the generator (standalone check)
  before touching the data path; read the generator's strings export
  for node/constant types.

## v3.21 (2026-10-19) - composite helper scripts + lazy-error-list discovery

New one-call helpers in `mcp-labview/scripts` (all tested end-to-end on
a scaffolded loop + FN accumulator, run-verified; documented in
SKILL.md Mode 2):

- `lv_loop_scaffold.vbs` - loop + N + setval + N-wire + optional SR +
  tunnels Regular in ONE call.
- `lv_fn_wire.vbs` - getNode-based FN map detection + 3 wires +
  isSource legality checks. RUN-VERIFIED: detected Map B, init applied
  (N=1 run: FNO = init = 100).
- `lv_tunnels_regular.vbs` - count + set all Regular.
- `lv_verify.vbs` - wires + errors + compile check, exit-coded.
- `lv_runcheck.vbs` - copy-first run + GetControlValue + PASS/FAIL.

### Discoveries made while testing them

1. **The IDE error list is computed LAZILY.** `errors` returned EMPTY
   for a VI that vi.Run rejects with 0x3EB - the list populates only
   after a compile check (window open / run attempt). `wires` alone
   can also miss it (0 broken, still broken). Hence lv_verify's
   compile check: run a temp copy; 0x3EB = broken. NEVER trust a
   PASS from wires+errors alone - the compile check is mandatory.
2. **Error-list items go STALE**: after fixing the real problem
   (unwired SR deleted), `errors` still reported 'Feedback Node: data
   type is undefined' though the FN was fully wired and the VI ran.
   The list is not auto-refreshed. Trust the compile check + runtime
   value over stale error text.
3. **An unwired RIGHT SR terminal BREAKS the VI** ('unwired from
   inside the loop') - addSR must be followed immediately by wiring
   sri0, or the SR deleted whole (delete the RightShiftRegister UID).
   lv_loop_scaffold prints this warning.
4. `loop` verb arg convention: arg1='tunnel:<idx>', the MODE is arg2
   ('-2' count / '0' Regular). 'tunnel:i;0' merged into arg1 ->
   ERROR 1055 To More Specific Class (cost one test round).
5. FN accumulator sanity math: out[i] = stored[i-1] - the init only
   shows at out[0]. To verify init at runtime use N=1 (out[0]=init);
   with N>1 the last indicator value is independent of init.

## v3.22 (2026-10-19) - TUPLE-DESCRIPTION BUG: one malformed tool drops ALL MCP tools

**Incident**: a stray trailing comma in server.py's gateway description
(`"...knowledge base. ",` inside the parenthesized concatenation) turned
it into a 2-string TUPLE. JSON serialization then emitted
`"description": [...]` (array), violating the MCP spec (Tool.description
must be a string). The server handshaked and answered tools/list
perfectly - but Zed's strict deserializer rejected the whole response
(Zed.log: `invalid type: sequence, expected a string at ...` - the
column points INTO the tools/list response, NOT into settings.json) and
registered ZERO tools. Symptom: "MCP is running. No MCP tools are
exposed" - the trap that forced terminal-fallback driving of
lv_gateway.vbs.

**RULE (mandatory after EVERY edit to server.py tool definitions):**

```
python mcp-labview/scripts/validate_tools.py [path-to-server.py]
```

- Runs the real stdio handshake, checks EVERY tool: name non-empty
  string, description STRING, inputSchema object. Exit 0/1/2.
- Verified: fixed server -> 13 tools 0 invalid; the broken backup ->
  `INVALID gateway: description is list`.
- A syntactically valid server.py (ast.parse passes) is NOT enough -
  the bug was a runtime TYPE error only visible in the serialized JSON.

**Distributables discipline**: the 1.1.0 wheel/tar.gz carried the bug;
version bumped to 1.1.1, rebuilt, old dist removed from git, v1.1.0
GitHub release marked broken, v1.1.1 published with fresh assets.

## v3.23 (2026-10-19) - `connector` verb: agent-created subVIs are now FULLY usable

User-implemented. `connector;<plain vi path>;<arg1 EMPTY>;arg2;arg3`:
- arg2 = 'L:<FP control label>' | 'U:<FP-element UID>' | 'disconnect'
- arg3 = 0-based connector-pane cell index ('Control[i]'; cell 0 usable)

**CALL-SLOT TRAP (cost 6 failed tests)**: arg1 must be EMPTY - the spec
lives in arg2/arg3. Passing the spec in arg1 -> 'ERROR 85: Scan From
String (arg 1)'.

Verified on gen\conn_test.vi (sr_golden copy, Num1 control / Out1
indicator):
- L:Num1->1, L:Out1->2: getNode Mode B shows Control[1]=Num1
  (Indicator:0), Control[2]=Out1 (Indicator:1) - SAVED state.
- U:60 (the FP-element UID getNode reports) -> cell 3: OK.
- U:82 (the BD ControlTerminal UID analyze reports) -> 'ERROR -1:
  GObject with ID not found' - **U: needs the FP-element UID, NOT the
  BD terminal UID**. L: is the primary form; the FP UID is only
  known after a first L: connection (or from getNode on a saved file).
- disconnect '2' -> Control[2] 'not linked'.
- Connecting a control to another cell RELOCATES it (old cell clears).

### END-TO-END SUBVI PROOF (caller_test.vi)

Placed conn_test.vi into a copy of sr_golden via `any:0<path>`, wired
PC1(7) -> SUB1 Terms[1] (Name: Num1) and SUB1 Terms[0] (Name: Out1) ->
indicator, ran: **PO = 17 = 7 + 10** - input propagated through the
agent-created subVI, computed, returned. Pane cell == subVI Terms[]
index confirmed for agent-created panes.

### GOTCHA: copies of subVI callers need the SAME directory

caller_test.vi copies in %TEMP% fail 0x3EB 'SubVI is missing' (the
subVI reference resolves relative to the caller's directory); a copy in
the SAME directory runs fine. lv_verify/lv_runcheck now place their
check copies next to the original (gitignored *_chk.vi/*_run.vi).

## v3.24 (2026-10-19) - `analyze` arg1='FP': front-panel GObjects (FP UIDs for connector)

User-implemented. `analyze;<plain vi path>;FP` lists FP objects:

```
0: Panel [] UID: 10
1: Pane [Pane] UID: 12
2: Digital [Out1] UID: 68
3: Digital [Num1] UID: 60
```

- The element UIDs are the FRONT-PANEL element UIDs - exactly what the
  `connector` verb's `U:` form needs (verified: same 60/68 as getNode
  Mode B in the v3.23 test). This removes the L:-first chicken-and-egg:
  analyze FP -> connector U:<uid> directly.
- FP ClassNames differ from BD/analyze names (numeric control =
  'Digital', not 'DigitalNumericConstant'); Panel/Pane containers are
  listed too.
- Without arg1 (or any other arg1) analyze lists the BD as before
  (BD ControlTerminal UIDs - Num1=82/Out1=97 in the same VI - are NOT
  valid for connector U:).

## v3.25 (2026-10-19) - RULE: check the rich IDE libraries before building by hand

The IDE ships thousands of ready-made VIs under `<LV>\vi.lib\**`
(incl. .llb). Before generating primitive-node code for any non-trivial
computation, SEARCH for an existing VI first - one subVI call can
replace 10-20 primitives. Full rule + search command + the proven
Histogram.vi case (1e6 samples run-verified, wired in ONE batch):
`references/subvi-placement.md`. NEVER build a histogram/statistics
chain from Add/Divide/SR primitives when a library VI exists.

## v3.26 (2026-10-19) - finding a library VI's documentation (Linear Fit case study)

How to find the docs of any vi.lib VI: lv_extract2 the POLYMORPHIC
PARENT (instances often have empty DESC) -> its `_strings.txt` header
has HELP_PATH + HELP_TAG (e.g. gmath.chm / Linear_Fit.html) -> 7z x
that CHM -> read the HTML page (defaults, enum values, algorithm).
Online ni.com reference pages are JavaScript shells for the fetch
tool - the local CHM is the reliable source. Also: a fresh .llb member
load can fail ONCE with 0x3E8 "not in a state compatible" - retry.
Full case study + Linear Fit pane table (6fits.llb):
`references/subvi-placement.md`.

## v3.27 (2026-10-20) - universal FP value I/O (arrread v2) + typed-control zoo

Revised `arrread` into a UNIVERSAL front-panel value tool (set/get ALL
types; see SKILL.md 'Runtime value I/O'). Verified end-to-end:

- **Documented semantics** (axprop/SetControlValue.html, GetControlValue.html):
  value is a variant - numeric/Boolean/string/array; "a cluster is
  represented as an array of variants in ActiveX"; FIRST GetControlValue
  on a VI whose FP was never shown returns DEFAULT values (root cause of
  the cross-process set/get trap).
- **Type matrix verified**: every scalar variant type (i8..i64, u8..u64,
  sgl, dbl) coerces into numeric controls AND round-trips exactly on
  typed controls; string/bool; 1D arrays (bare double[], ai: coerced
  element-wise into DBL arrays, as: string arrays); 2D (a2:, reads back
  as rank-2 variant matrix); clusters c:(b:true,i32:42,s:boom) on a REAL
  error cluster; nested array-in-cluster c:(au8:[9,8,7],i32:42) resizes
  the inner array. Functional: cycle Sort 1D Array.vim [5,1,3] -> [1,3,5].
- **Wrong-type SetControlValue is SILENTLY IGNORED** (no COM error, value
  unchanged) - the tool prints an ECHO after every set; always check it.
- **Typed-control zoo trick**: the gateway `place any:0<.ctl path>` can
  place ANY stock control file - `vi.lib\functionblocks\FB Property\FB
  Overlay {I8,I16,I32,I64,U8,U16,U32,U64,SGL,DBL,String,Bool}.ctl` gives
  every numeric representation (regression zoo: gen\fpzoo.vi). Note:
  FB Overlay Bool.ctl reads back as UInt16 (65535) - it is not a plain
  boolean; use a toggle switch/LED for boolean tests.
- **Malleable .vim VIs are ready-made typed-array targets** (no FP
  building needed): Sort 1D Array.vim 'unsorted array'/'sorted array'
  (DBL 1D), Shuffle 2D Array.vim 'array' (DBL 2D). The tool can drive
  any vi.lib VI's FP controls in-memory (SetControlValue does NOT save
  the file) - Clear Errors.vi 'error in (no error)' = mixed cluster.
- **LIMITATION (feature request)**: placing elements INTO FP array/cluster
  shells via container resolver (`%Cluster|Clu1`) lands them on the PANE
  at absolute coords - the shells stay empty ("Control contains no
  elements", undefined type, broken 2-source wires). Gateway would need:
  for FP containers owner = the resolved GObject, not the Panel. BD
  structure placement is unaffected. Workaround: place a stock .ctl that
  already contains the array/cluster, or build the FP by hand.
- **Top-level FP wiring verified**: `wire;<vi>;<srcLabel>|<dstLabel>;<srcK>|<srcI>|<dstK>|<dstI>`
  e.g. `NumIn|NumOut;c|0|c|0` - kind 'c' covers control/indicator
  terminals; no container needed. (arg1 is src|dst labels, NOT two ids.)
- `Numeric.Representation` is scriptable Read/Write (lvscript, 0=EXT..14=
  FXP) - a possible future Gateway verb for changing representations.
- gen\fpzoo.vi = regression zoo (pass-through scalars + typed controls
  + DatumCtl nested-array cluster); errors empty; committed.

## v3.28 (2026-10-20) - While Loop stop terminal (st%d) + error-cluster scripting

New gateway wire kind `st%d` (user-added; WhileLoop only): wires the
conditional/Stop terminal. `arg2 = c|0|st1|0` - the trailing |0 is
IGNORED; st%d = the loop's "Stop if True" setting (st1 = stop when TRUE,
the common case; st0 = continue-if-true).

Verified end-to-end on gen\while_st.vi (4 WhileLoops, errors EMPTY,
ALL loops runtime-terminate; per-loop SR->LED termination proof):

- **Inside vs outside source**: a source INSIDE the loop wires directly
  to the st terminal (single wire, no tunnel); a source OUTSIDE creates
  an auto-tunnel pair typed by the source (error-cluster tunnels display
  as "error IO").
- **st terminal accepts Boolean OR error cluster - but an error cluster
  FORCES stop-on-error; the st%d setting is IGNORED**: a no-error
  cluster wired via st0 NEVER stopped (ran until abort); a real error
  via st1 stopped after iteration 1. Boolean cases behave per st%d.
- **Runtime proofs**: st0+FALSE-const -> 1 iteration (CountOut=1);
  st1+always-TRUE (Greater Or Equal To 0?, any:1114, i>=0) -> 1
  iteration (W2Count=True); st1+REAL error (code 42) -> stops
  (W3Count=True); final run CountOut=1, W2/W3/W4=True.
- **Scripted TRUE source**: BEFORE v3.29 setval could not set boolean
  constants - the workaround was `Greater Or Equal To 0?` (any:1114)
  with i|0 -> x (always TRUE inside a loop). NOW: `setval
  %BooleanConstant|X;1;bool` works (accepts 1 or true; FALSE const =
  any:2006). RUNTIME-VERIFIED (v3.29): BoolT <- 1;bool, wired to st1 ->
  loop stopped after 1 iteration (W2Count=True); a silent failure would
  have hung the loop. setval DOES set string constants with arg2
  format 'str' (verified: SrcC <- 'boom;str').
- **Error clusters with scripting** (the research ask):
  - 'Error Ring Constant' (any:2039) is NOT placeable via New VI Object
    (ERROR 1061, top-level AND inside structures): the Error Ring is a
    DIALOG-configured node (glang/Error_Ring_Constant.html: "Launches
    the Select Error dialog box").
  - Plain error-cluster CONTROL: place stock .ctl via `place any:0<path>`:
    `resource\importtools\sharedlib\Custom Control\error in (no
    error).ctl` and `...\error out.ctl` - placed, wired and set/read
    via arrread c:(b,i32,s) (ErrIn on gen\fpzoo.vi).
  - A REAL error for runtime tests: place subVI
    `vi.lib\Utility\error.llb\Error Cluster From Error Code.vi`
    (error code input = connector cell 9 (Required), error out = cell 0)
    + I32 constant. This replaced the Bundle approach.
  - Bundle (2049) element count follows placed HEIGHT (~8.7 px/element;
    H=40 -> 5 elements) - a 5-element cluster cannot wire into the
    3-element error sink; first input terminal is named 'cluster'.
- **Abort/run-state gotchas**: aborting a HUNG run leaves wires/errors
  verbs failing (1320 / 1073 Get Errors) until the VI is aborted again;
  Abort on an IDLE VI raises 0x3E8 "not in a state compatible" - usable
  as a "has it finished?" check. Tools: references\abort_vi.vbs (abort
  any VI by path); one-process run+poll+read pattern in run_poll.vbs
  (scratch) - same rule as arrread cycle: set/run/read in ONE process.
- gen\while_st.vi = st-regression zoo: WL1 st0+F-const+SR->CountOut;
  WL2 st1+GE(i>=0)+SR->W2Count; WL3 st1+ErrGen(42)+SR->W3Count;
  WL4 st0+F-const+GE->sri->W4Count.

## v3.29 (2026-10-20) - setval 'bool' format (boolean constants)

`setval %BooleanConstant|X;1;bool` (or 'true;bool') sets BD boolean
constants. Runtime-verified on while_st.vi: BoolT <- 1;bool wired to
WL2's st1 terminal -> loop terminated after 1 iteration (W2Count=True;
the old FALSE value would have hung it). Both '1' and 'true' accepted.
The GE(i>=0) TRUE-source workaround is no longer needed for constants
(but remains useful for auto-TRUE sources inside loops).

## v3.30 (2026-10-20) - `getval` verb + flattened-data converter (lv_flat.py)

**getval reads the value of ANY element** (BD constant or FP control) as
flattened data. `lv_gateway.vbs Gateway.vi getval "<vi>%<Class>|<Label>"`
- the FULL item identifier (path + `%Class|Label`) goes in the vi_path slot;
  a bare path gives ERROR 1055. The Gateway runs Variant To Flattened String
  and returns in `result`:

```text
Data type array: 60,16464,3,12,... (I16 array as CSV; 2 descriptor bytes per I16, BIG-endian)
Data string length: 21
Data string hex='01FFFFFFFF0000000C557365722773206572726F72'
```

**HEX TRANSPORT IS MANDATORY**: the data string passed through COM BSTR
mangles bytes >= 0x80 (verified: flattened -1 (FFFFFFFF) arrived as
F5F5F5F5). Type array is safe (CSV text). Gateway v3.30 hex-encodes the
data string in-LabVIEW - lossless. lv_getval_hex.vbs also accepts the old
raw `Data string='<binary>'` reply but that path is NOT reliable for high
bytes. CodeC I32 -1 round-trips ffffffff (was f5f5f5f5).

**Converter: `mcp-labview/scripts/lv_flat.py`** (regression tests:
test_lv_flat.py, all passing):
- `type <csv>` - descriptor tree; `decode <csv> <hex>` - value;
  `encode <csv> <expr>` - data hex; `reply <file>` - decode a getval reply
  (raw gateway string OR lv_getval_hex output; '-' = stdin).
- Formats (lvconcepts/Type_Descriptors.html + Flattened_Data.html): TD =
  [size:u16][code:u16][info][pascal name]; array TD adds ndims u16 + dims
  u32 + elem TD; cluster TD = elem TDs; each elem TD self-delimits via its
  own size. Data: big-endian; bool 01/00; string = u32 len + bytes; array =
  u32 dims + row-major elements; cluster = concatenated elements; enum =
  index (decoded to item name). Encoded grammar: `c:(b:true,i32:-1,s:text)`,
  `a:[1,2]`, `a:[[1,2],[3,4]]` (2D).
- Verified live: error-constant cluster {status,code,source} (encode
  round-trip == hand-computed hex), I32 -1, string, bool, U16 (BoolRepCtl),
  SGL, cluster{U8 array,I32} (DatumCtl).

**Resolver now searches BD AND FP (v3.30, BD first)**: `%Control|ErrIn`
works for FP controls (Control is FP-only); getval on a control reads its
VALUE. Verified on fpzoo.vi: ErrIn={status=False,code=0,source=""}.
**Known gaps**: (1) `setval` on a `%Control|` target still fails ERROR
1057 (its writer casts to a constant class - use arrread for FP writes);
(2) `getNode ... terms` on an ArrayConstant fails 1057 - an array constant
is a constant with no terminals; (3) PLACING AN ELEMENT INSIDE an array
constant shell (any:2070) does NOT nest - place puts it beside the shell
(shell stays 'undefined type'); nesting needs New VI Object with the shell
ref wired to the owner input (gateway upgrade, not yet implemented).

**MCP tool `getval`** (server.py v3.30): one call = lv_getval_hex.vbs +
lv_flat decode; returns `name = value` + descriptor tree + bytes consumed.
Run `python scripts/validate_tools.py server.py` after any server.py edit
(14 tools, 0 invalid as of this section).

## Roadmap (v3.1+, after v3 works)

- `place` branch for **SubVI** (New VI Object `path` input + class
  Generic\u00bbGObject\u00bbNode\u00bbSubVI).
- Placement inside structures (`Drop Add Function Inside While Loop.vi`
  pattern: owner = the structure's diagram).
- Connector-pane scripting (`Building connector panes` how-to) for subVI
  generation.
- `delete` verb (GObject method / Delete method).
