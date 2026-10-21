---
name: labview-code
description: Work with LabVIEW VI code from the AI IDE - view VI code, generate pseudocode, answer questions about a VI ("talk with a VI"), and generate new LabVIEW code. Use when the user mentions a .vi file path or asks about LabVIEW code, block diagrams, VI structure, live VI queries, or LabVIEW code generation.
---

# LabVIEW Code Workbench (skill: labview-code)

Drive LabVIEW from Zed in three modes. In the command examples below,
`%SKILL%` is a placeholder - substitute this skill's directory (absolute
path) when running commands. If this skill is installed globally that is
`C:\Users\<user>\.agents\skills\labview-code`; while staged in the
workspace it is `C:\LabView skill\skill-labview-code`.

| You want... | Mode | Requires |
|---|---|---|
| Pseudocode / description / Q&A for a .vi file | 1 - Static extraction | just the file path |
| Live, machine-readable inventory of a VI | 2 - Gateway | Gateway.vi built once |
| Generate LabVIEW code (place nodes, wire them) | 3 - Gateway v3 | Gateway.vi v3 |

Decision tree: **file path available -> Mode 1** (always works, zero risk
to the original). Modes 2/3 need the one-time Gateway VI - if
`C:\LabView skill\gateway\Gateway.vi` does not exist yet, tell the user to
build it from `references/gateway-recipe.md` (5-10 minutes) before
promising live queries or generation.

## Mode 1 - Static analysis of a .vi file (default)

The extraction script copies the VI, then exports: a strings file (every
control, constant value, function name, structure content), an HTML report,
and PNGs of the front panel, the block diagram, and **every case of every
structure**. The original file is never touched.

```
cscript //nologo "%SKILL%\scripts\lv_extract2.vbs" "C:\path\to\TMC current.vi" "C:\LabView skill\_service\extract\<VI name>"
```

Artifacts land in the work dir:

- `<VI name>_strings.txt` - text of everything; grep this first
- `<VI name>_report.html` - browser-renderable report
- `images_<VI name>\` - `*_reportb.png` = block diagram, `*_reportc.png` =
  front panel, plus one image per case of every structure (filenames encode
  the case path)

Then:

1. Grep the strings export for labels, constants, subVI names.
2. View the block-diagram PNG with `read_file` (images are supported).
3. For case structures, stitch the case images into contact sheets first,
   then read the sheets:
   ```
   powershell -ExecutionPolicy Bypass -File "%SKILL%\scripts\stitch.ps1" -Dir "<images dir>" -NamePattern "<structure label or pattern>"
   ```
   To zoom into a detail:
   ```
   powershell -ExecutionPolicy Bypass -File "%SKILL%\scripts\crop.ps1" -Src "<png>" -X <x> -Y <y> -W <w> -H <h> -Out "<out png>" [-Scale 3]
   ```
4. Verify non-obvious function semantics against the local CHM mirror at
   `C:\LabView skill\help\` (`glang`, `lvprop`, `lvhowto`, `lvscript`,
   `lvconcepts`) or ni.com via search-result snippets (ni.com pages are
   JS-rendered; a direct fetch returns only the navigation shell).
5. Write the answer using the standard structure: **Summary / Elements
   table / Data-flow narrative / Pseudocode / Notes & uncertainties**
   (same format as the `read-block-diagram` skill, Step 5).

Strings-export gotchas (full list in `references/labview-automation.md`):

- Case order in `<BDCONTENT>` is NOT guaranteed (`[True,False]` was
  observed exported as `[False,True]`) - map cases by position in the
  images, never by export order.
- Constants can carry meaningless `name=` values (`x`, `f`, `t`); the value
  attribute is what matters.
- Enum/ring item text exports empty; enum case names are readable only in
  the images.
- Formula Node / Formula Box source code appears only in the images.
- Exports reflect the **saved** state of the VI; unsaved in-memory edits do
  not show.
- The script runs on a copy in its own spawned LabVIEW instance, so it is
  safe even while the user has the original open.

## Mode 2 - Gateway (live queries)

Gateway.vi is a small helper VI that runs *inside* LabVIEW and performs the
VI Scripting work external COM cannot reach (block-diagram traversal, node
properties). The driver sets its controls, runs it, and prints its
`result` string:

```
cscript //nologo "%SKILL%\scripts\lv_gateway.vbs" "C:\LabView skill\gateway\Gateway.vi" ping
cscript //nologo "%SKILL%\scripts\lv_gateway.vbs" "C:\LabView skill\gateway\Gateway.vi" analyze "C:\path\to\copy of target.vi"
```

**MCP fallback (session-verified 2026-10-19)**: if the MCP tools are
not exposed in the session, drive the pipeline directly -
`lv_gateway.vbs <Gateway.vi> <verb> [vi_path] [arg1] [arg2] [arg3]`
for single ops, `lv_gateway_batch.vbs <Gateway.vi> <scriptfile>` for
scripts. Batch format: `verb;vi_path;arg1;arg2;arg3`, `#` comments,
`!` prefix tolerates failure, otherwise stops at first error (good for
pinpointing). `newvi` takes the path in arg1 with vi_path empty
(`lv_gateway.vbs Gateway.vi newvi "" "C:\...\X.vi"`). Read verbs
(getNode/wires/analyze) run on temp copies of the DISK file - they
reveal the SAVED state, not unsaved IDE edits.

**Composite helper scripts (mcp-labview/scripts, gateway v3.21-era,
all tested 2026-10-19 - prefer these over raw verb sequences):**
- `validate_tools.py [server.py]` - MANDATORY after every edit to
  server.py tool definitions: runs the stdio handshake and checks every
  tool (name/description must be strings, inputSchema an object). One
  malformed tool (e.g. a stray comma making the description a tuple ->
  JSON array) makes strict clients like Zed drop ALL tools while the
  server itself handshakes fine (recipe v3.22). Exit 0=valid.
- `lv_loop_scaffold.vbs <gw> <vi> <loopLabel> <x,y[,W,H]> <NconstLabel> <Nvalue> [SRlabel [SRy [Nxy]]]`
  - one-shot loop skeleton: place ForLoop + N constant + setval + wire
    N (c|0|n|0) + optional addSR + set tunnels Regular. WARNING it
    prints: an unwired SR BREAKS the VI (unwired right terminal) -
    wire sri0 or delete the SR (UID in output) immediately.
- `lv_fn_wire.vbs <gw> <vi> <FNlabel> "inLabel|kind|idx" "outLabel|kind|idx" "initLabel|kind|idx"`
  - auto-detects the FN map via getNode (isSource:1 = output;
    source=[0]->Map B, [1]->Map A) and wires input/output/init with
    legality checks. Run-verified. Then lv_tunnels_regular if a wire
    crossed the border.
- `lv_tunnels_regular.vbs <gw> <vi> <ForLoopLabel>` - counts tunnels
  (tunnel:0;-2) and sets ALL Regular (arg1='tunnel:<i>', arg2='0' -
  the mode is arg2, NOT 'tunnel:i;0' in arg1).
- `lv_verify.vbs <gw> <vi>` - wires broken-flags + errors + a
  COMPILE CHECK (runs a temp copy; 0x3EB = broken = FAIL). Exit
  0=clean/1=broken. WHY the compile check: the IDE error list is
  computed LAZILY - `errors` returns EMPTY for a VI whose list was
  never populated (false PASS possible); the run attempt forces it.
  Error-list items can also be STALE (list is not auto-refreshed
  after fixing - e.g. 'Feedback Node: data type is undefined'
  persisted after the FN was fully wired).
- `lv_runcheck.vbs <vi> <control> [expected]` - copy-first runtime
  check: copies to %TEMP%\lv_mcp\<name>_run.vi, runs THE COPY, polls
  GetControlValue stable, PASS/FAIL vs expected. The user's control
  values stay undisturbed.

- `ping` - sanity check; expect `pong <timestamp>`.
- `analyze` - one line per block-diagram object:
  `i: ClassName [label] owner=OwnerClass` - enough for a structural
  pseudocode skeleton (terminals, functions, structures, nesting via
  owner). Combine with Mode 1 images for exact wiring.
- `wires` (wire-centric; full spec in the recipe) - one line per wire:
  `Wire: label:"..." broken:0|1 UID:<n> -> <terminal> --> <terminal> ;`
  where each terminal is `Label(TermUID) [][OwnerClass] of Node{ UID,
  Label: <node label>}` (gateway v3.19+; fan-outs list all sinks
  separated by ';'). The **first terminal is the source**, the rest are
  sinks. You get the terminal's label AND UID plus the owning node's
  UID and label - so `wires` + `analyze` (object UIDs) + `getNode`
  (per-terminal roles) together restore a block diagram completely.
  For primitives OwnerClass is `Function`/`Comparison`; for FP
  terminals the node IS the control (e.g. `FC(UID:141) [][Boolean
  Constant] of Node{ UID:142, Label: FC}`). Blank lines between entries
  are formatting artifacts - ignore them. Only wired connectivity is
  listed (unwired objects appear in `analyze`/`getNode` only).
- `listmem` (experimental) - VIs in memory of the spawned instance.

Rules:

- `analyze` works on any VI, including one open in the user's LabVIEW
  (the gateway attaches to the running instance; read verbs snapshot a
  temp copy internally). Use a scratch copy when the run would disturb
  the user's control values.
- The first COM call spawns a background 64-bit LabVIEW (15-30 s); later
  calls attach to it and are fast. That instance stays alive by design.
- If Gateway.vi was just edited on disk, kill the background instance first
  so the fresh copy loads:
  `powershell -ExecutionPolicy Bypass -File "%SKILL%\scripts\lv_procs.ps1"`
  then `taskkill /PID <pid> /F` for the pid whose path is under
  `C:\Program Files\National Instruments\` (64-bit).
- "Talk with a VI" = Mode 1 artifacts + Mode 2 inventory combined. Answer
  strictly from those facts and mark anything inferred as inference.

## Mode 3 - Code generation (Gateway v3)

**STRICT RULE - user-provided VIs: copy first.** Develop, test and debug
every script on a COPY of the VI (`<name>_tmp.vi` or a fresh `newvi`).
Apply the script to the user's original VI only after the copy verifies
clean: `wires` shows zero `broken: 1`, and a runtime check returns the
expected value (run_vi_get_value.vbs / arrread). Read verbs (analyze/
wires) may run on the original directly.

**Worked golden example for hard tasks** (loop + Feedback Node
accumulator + Select + comparison + border tunnels): Pi Monte-Carlo,
`gen\pi_golden3.vi` - built 100% by gateway verbs, run-verified
PI = 3.1398 @ N=1e6. Full recipe + the two hard rules (FP objects are
top-level only; set ALL border tunnels Regular after the last wire) in
`references/gateway-recipe.md` section v3.11. Read it BEFORE attempting
any loop/accumulator generation task.

Gateway v3 verbs (build sheet in `references/gateway-recipe.md`, section
"v3 build sheet"):

- `delete` - remove a GObject/wire: vi_path = container resolver (or
  plain for top-level), arg1 = class ('GObject' = any, 'Wire'), arg2 =
  'U:<uid>' or 'L:<label>'. `analyze`/`wires` print UIDs. NOTE: in batch
  scripts a 2-field `delete;<path>` line is the FILE-delete meta-command,
  not this verb (since the runner fix, 3+ field lines go to the gateway).
- FP objects (numind/numctl, any:21003/any:21004) place INSIDE structures
  via resolver (Gateway v3.12+); the terminal lands in the loop diagram
  and wires like any c|0 terminal.
- **Shift registers**: create first with `loop;<vi>%ForLoop|L1;addSR;<Y>;<Label>`,
  then wire s-kinds: `slo<i>` = left-outside INOUT (wire init INTO it),
  `sli<i>` = left-inside OUTPUT (previous-iteration value), `sri<i>` =
  right-inside INOUT (wire per-iteration value INTO it), `sro<i>` =
  right-outside OUTPUT (final value). The IDX FIELD after '|' selects
  WHICH SR (0-based addSR order); the digit after sli/slo is the
  multi-input-SR input number - always 0 for regular SRs (`sli1|0` ->
  ERROR 1055). GOLDEN one-pass script: `gen\sr_golden.txt` ->
  `gen\sr_golden.vi` (zero broken wires, run-verified Out1=10) - copy
  and adapt it for any SR code generation. Full recipe + gotchas
  (unwired-node breakage, control setval): gateway-recipe.md v3.13.
- **While Loop stop terminal** (Gateway v3.28): `wire;<vi>;<src>|<WhileLoop>;<srcK>|<srcI>|st1|0`
  wires the loop's conditional terminal; st%d = the "Stop if True"
  setting (st1 = stop when TRUE - the common case; st0 = continue-if-
  true); the trailing |0 is IGNORED. Source INSIDE the loop wires
  directly (no tunnel); source OUTSIDE auto-creates a tunnel pair typed
  by the source. The st terminal accepts Boolean OR error cluster -
  BUT an error cluster FORCES stop-on-error (the st setting is ignored;
  no-error cluster + st0 never stops - verified). Scripted TRUE source:
  place `Greater Or Equal To 0?` (any:1114) and wire i|0 -> x (i>=0 is
  always TRUE); FALSE constant = any:2006. Boolean constants are now
  settable: `setval %BooleanConstant|X;1;bool` (v3.29, accepts 1/true;
  runtime-verified).
  Runtime proof pattern: SR per loop -> LED indicator, read all in ONE
  process (references\abort_vi.vbs aborts hung runs; a hung-run Abort
  leaves wires/errors verbs failing 1320/1073 until re-aborted). Full
  story + gen\while_st.vi regression: recipe v3.28.
- **Error clusters with scripting**: 'Error Ring Constant' (any:2039)
  is NOT placeable via New VI Object (ERROR 1061) - the Error Ring is a
  DIALOG-configured node (glang/Error_Ring_Constant.html). Plain error
  cluster control: place stock .ctl `resource\importtools\sharedlib\
  Custom Control\error in (no error).ctl` (or error out.ctl) via
  `place any:0<path>` - settable/readable via arrread c:(b,i32,s).
  A REAL error for runtime tests: place `vi.lib\Utility\error.llb\
  Error Cluster From Error Code.vi` (error code input = cell 9,
  error out = cell 0) + I32 constant. setval string constants: arg2
  format 'str' (verified). Recipe v3.28.
- **Diagnosing a broken VI** (recipe v3.14): `errors` verb (Gateway
  v3.14+) returns the IDE Error-List content for the VI ('Errors list
  = ...; Details = ...'; ';'-separated, index-aligned; EMPTY = VI
  clean; item text does NOT name the object - pair with
  analyze/wires/extract to locate the culprit). Not a BD traversal -
  it reads the IDE-embedded error window, so it catches everything the
  IDE catches. Raw VI Server COM has no equivalent (vi.IsBroken/
  ErrorList/BlockDiagram all 0x1B6). `wires` broken-flags alone MISS
  unwired node inputs. After any `place`, wire required inputs or
  `delete` the leftover by UID immediately; verify with `errors` + a
  runtime check.

- `newvi` - save path in **arg1**; leave the vi-path slot empty.
- `place` - arg1 = type: the small named set
  (`numctl numind strctl strind numconst strconst add multiply`) OR
  **`any:<styleCode>` for anything else** (code table in `style_codes.json`
  byName/byCode; e.g. Feedback Node = `any:2353` - it is NOT placeable by
  name). arg2 = `"x,y"` or `"x,y,W,H"`. **W,H is REQUIRED for growable
  nodes** - array ops like Replace Array Subset 3910, Build Array 2041,
  Index Array 2042: without bounds the node is chunk-starved and
  CRASHES LabVIEW on click; RAS 1 chunk = 46x40, each extra chunk
  ~+13px H) - **and for FRONT-PANEL OBJECTS (numctl/numind/strctl/
  strind/any:21003/any:21004) W,H IS the front-panel item size and
  MUST be non-zero** (e.g. 80x32): with 0 the item is created 0-size -
  label only, no visible body on the FP, unreadable there (COM
  GetControlValue still works, so the defect hides from run tests -
  verified visually via extract FP PNG, recipe v3.15).
  arg3 = label. vi_path may carry a resolver suffix
  `path.vi%Class|Label` (nested `%Class|Label%Class|Label`) to drop the
  object INSIDE that structure. Returns the new element's UID.
- **`getNode` - terminal/connector-pane info (Gateway v3.17+)**: arg1 =
  `terms`. Two modes: (a) vi_path = `vi%Node|<label>` -> one line per
  terminal: `Term[i] UID: <n>, name='<...>', isSource: 0|1, isHidden:
  0|1, wireUID: <n>, wireBroken: 0|1` (or 'No wire connected') - shows
  EXACTLY what each terminal is for (Add: `[0]`=x+y out, `[1]`=y,
  `[2]`=x) and which are already wired; (b) vi_path = a plain .vi/.llb
  path -> the subVI's CONNECTOR PANE: `Control[i]: UID, Label,
  Indicator, IsOnConPanel, Wiring rule (Required/Recommended/...)` -
  read a subVI's interface BEFORE wiring instead of empirical probing
  (replaces most of the old probe workflow; recipe v3.17).
- **CHECK THE RICH IDE LIBRARIES FIRST (2026-10-19)**: the LabVIEW IDE
  ships THOUSANDS of ready-made, tested VIs under
  `<LV>\vi.lib\**` (incl. .llb libraries). Before generating
  primitive-node code for any non-trivial computation (statistics,
  histogram, filters, array ops, signal generation, file I/O...),
  SEARCH for an existing VI first - one placed subVI call can replace
  10-20 primitives. NEVER build a histogram/statistics chain from
  Add/Divide/SR primitives when a library VI exists. Search + workflow +
  verified pane tables: `references/subvi-placement.md` (proven:
  Histogram.vi, 1e6 samples run-verified, wired in ONE batch).
  DOCUMENTATION for a library VI: lv_extract2 the POLYMORPHIC PARENT
  (instances have empty DESC) - its `_strings.txt` gives per-terminal
  DESC plus HELP_PATH/HELP_TAG naming the CHM + page (e.g. gmath.chm /
  Linear_Fit.html); 7z x that CHM and read the page. Online ni.com
  pages are JS shells for `fetch` - the local CHM is the reliable
  source (proven on Linear Fit, 6fits.llb).
- **SubVIs (NI library / vi.lib / .llb members)**: `place` arg1 =
  `any:0<full path>` - the literal `any:0` prefix places the FILE at
  <path> (e.g. `any:0C:\...\vi.lib\Analysis\1siggen.llb\Gaussian White
  Noise.vi`). SubVI terminals are indexed by CONNECTOR-PANE CELL NUMBER
  (Context Help numbering, NOT inputs-first) - wiring an empty cell
  gives broken:1 with empty Name. Learn the interface with `getNode` on
  the subVI path (connector pane) + `lv_extract2.vbs` strings (types)
  BEFORE wiring; verified pane tables (Histogram, Std Deviation and
  Variance), style-code terminal maps and the special-constant (Pi/2pi)
  trap: `references/subvi-placement.md` + recipe v3.16/v3.20.
  Primitive terminal order is OUTPUT-FIRST
  (Add `[0]`=x+y) - opposite rule; the `wire` response's `Name` fields
  are ground truth. **Agent-created subVIs are fully usable**: after
- **Agent-created subVIs are fully usable**: after
  newvi + FP controls, assign the pane with the `connector` verb
  (arg1 EMPTY, arg2='L:<label>'/'U:<FP uid>'/'disconnect', arg3=0-based
  cell; recipe v3.23) - verified end-to-end (input 7 -> subVI -> 17).
  `analyze <vi> FP` lists front-panel elements with the FP UIDs for the
  U: form (recipe v3.24).
  A caller COPY must live in the subVI's directory (%TEMP% copies fail
  'SubVI is missing' - lv_verify/lv_runcheck handle this).
- `loop` - add a shift register: vi_path = `path.vi%ForLoop|Loop1`,
  arg1 = `addSR`, arg2 = Y position, arg3 = label (a shift register has no
  label - the loop gets relabeled if it had none).
- `loop` tunnel control: arg1 = `tunnel:<idx>` or `tunnel:U<UID>`,
  arg2 = `-2` (count), `-1` (status), `0/1/2` (set IndexMode:
  0=Regular, 1=Auto Index, 2=Concatenate). **Border tunnels are
  auto-created Auto-Index - arrays crossing a loop border deliver their
  last element unless set to 0!** Always `tunnel:i;0` array crossings.
- Select: comparison output -> **s[2]** (never f[1]); t[3]/f[1] must be
  the SAME type. RAS 1-chunk (bounds 46,40): [0]=array,[1]=out,
  [2]=element,[3]=index. FN (any:2353): [0]=out,[1]=init,[2]=input.
  IndexArray: [0]=array,[1]=element(OUT),[2]=index.
- `getval` (v3.31) - read ANY element's value: vi_path = FULL item
  identifier `path.vi[|BD|FP]%Class|Label` (optional target, BD default;
  resolver searches BD then FP: `ClusterConstant|error constant`,
  `Control|ErrIn` for FP controls). Reply = XML with type-descriptor I16
  array + HEX data string (older text/CSV forms still parsed). Decode
  with `scripts/lv_flat.py` (type/decode/encode/reply; regression tests
  test_lv_flat.py) or the MCP `getval` tool (one call). TRAP: getval on
  an FP CONTROL returns the DEFAULT value - live FP values via arrread
  cycle. FP-control values set by setval are RUNTIME-ONLY (not saved
  with the VI; lost on close) - runtime tests = arrread cycle, live
  co-editing = setval on the IDE-open VI.
- `setval` (v3.31) - set a constant OR control value: vi_path =
  `path.vi[|BD|FP]%Class|Label` (Class = short name, NO spaces:
  `NumericConstant`; generic `Constant` also works - NOT the verbose
  analyze ClassName; wrong class -> ERROR 1092). arg1 = value, arg2 =
  `dec|frc|str|bool|XML` (XML = full getval reply, sets ANY type incl.
  clusters; hex-decoded in-gateway). arg3 = numeric representation code
  (numerical only, empty = keep): 0 EXT, 1 DBL, 2 SGL, 3 I32, 4 I16,
  5 I8, 6 U32, 7 U16, 8 U8, 9-11 complex, 12 I64, 13 U64, 14 FXF - rep
  is applied BEFORE the value, so one call changes both (retires the old
  'placed numconst is I32 forever' limitation; frc-into-I32 still
  rounds). Nested elements resolve by label directly
  (`%DigitalNumericConstant|Num1` inside a cluster constant).
- **Clusters/nested objects** (v3.31): BD cluster constant = place
  `any:2071` shell, then place `any:2005` via
  `<vi>|BD%GObject|<shellLabel>` (drops INSIDE); FP cluster control =
  `any:21607` via `|FP` + `any:21003` via `|FP%GObject|<clusterLabel>`;
  cluster control inside a loop = shell via `|BD%GObject|<loopLabel>`.
  place arg2 now accepts `x,y,W,H`.
- `wire` - arg1 = `srcLabel|dstLabel`, arg2 =
  `srcKind|srcIdx|dstKind|dstIdx`: kind `c|0` = control/constant terminal,
  `n|<i>` = index into a node's `Terms[]` (primitives: 0 = output,
  inputs follow; ForLoop Terms[] = [N] only), kind **`i|0`** = the loop
  counter terminal (arg1's source label is the LOOP's label, e.g.
  `wire "Loop1|Add1" "i|0|n|2"`). The RESPONSE reports both terminals:
  `Terminal: <label>, type: <k>, index: <i>isSource: <0|1>, Name: <name>`
  (gateway v3.15+). LEGAL WIRE = src `isSource:1` AND dst `isSource:0`;
  1/1 = output-output, 0/0 = input-input - both come back broken:1.
  `wire ok` means CREATED, not legal - always read the flags. Name
  gives primitive terminal names (Add: `[0]`=x+y output, `[1]`=y,
  `[2]`=x); prefer `getNode terms` (v3.17) to read terminal roles
  WITHOUT wiring - for FN it shows the source but not init-vs-input
  (recipe v3.17).

Write verbs edit and **save the real file**. Two rules that cost sessions
to learn (full story in the recipe's "one-pass canonical build recipe"):

- **STANDARD: work live in the user's IDE** (user decision 2026-10-19;
  verified safe 2026-10-15): COM attaches to the running LabVIEW, so
  edits mutate the user's in-memory VI, appear on screen, and save to
  disk from the same session. The user watches changes happen - this is
  a feature, not a hazard. If edits do NOT appear live, a background
  instance was used and the IDE copy is stale - user must reload from
  disk before saving, or the disk edit is lost. A target VI not already
  open gets opened (possibly hidden) in the user's session.
- **A wire crossing a loop border auto-creates an Auto-Index tunnel -
  set ALL tunnels Regular after the last crossing wire** (`loop
  tunnel:i;0`, count via `tunnel:0;-2`). Until then the tunnel segment
  reads broken: 1 - for constants, node outputs and FP terminals alike
  (revised 2026-10-17; supersedes the old 'never wire a node output
  across the border' rule, which predates the tunnel verb). Never
  re-invoke a failed wire (second tunnel pollutes the VI). Alternative
  since Gateway v3.12: place the indicator INSIDE the loop via resolver
  and its terminal wires with no tunnel; labeled constants may cross
  freely (auto-tunnel inherits the label).
- **Field-note corrections (recipe v3.18, pi-integration/MC session,
  2026-10-19)**: (1) ForLoop Terms[] WITH a shift register: `[0]`=N
  (wire `c|0|n|0`), `[1]`=RightSR outer, `[2]`=LeftSR outer; `n|3`+ ->
  ERROR 1055 - the counter is `i|0`, never `n`. (2) `place` takes
  EXACTLY 5 fields - a trailing 6th is silently ignored -> unlabeled
  object -> ERROR 1092 on every later setval/wire. (3) Autowire can
  merge a new wire through an existing tunnel/nearest terminal -
  "wire ok" but broken; delete the wire AND tunnel segments before
  retrying. (4) UIDs from `analyze` output may fail to delete (ERROR
  1093) - use UIDs from `wires` output. (5) `errors` is ground truth;
  never trust wire responses alone. (6) PROVEN ORDER: place loop ->
  place nodes inside -> setval -> wire N -> addSR -> wire SR -> wire
  internals -> border crossings LAST + tunnel Regular -> wires+errors
  -> run on a copy. (7) Deleting the RightShiftRegister (UID from
  addSR) removes the whole SR - the clean way to redo SR wiring.
- **Feedback Node terminal order is RANDOM PER INSTANCE - determine it
  for EVERY FN with `getNode` (do not assume by creation path):**
  - 2026-10-19: two gateway-placed FNs were BOTH Map A, refuting the
    earlier creation-path theory (gateway→Map B). Both rotations exist:
    **Map A** `[0]`=in, `[1]`=out, `[2]`=init; **Map B** `[0]`=out,
    `[1]`=init, `[2]`=in (exact cyclic rotations).
  - **Procedure**: `getNode;<vi>%Node|<fnlabel>;terms` - the terminal
    with `isSource:1` is the OUTPUT. source=[0] → Map B; source=[1] →
    Map A; the init/input assignment then follows from the rotation
    (Map A init=[2], Map B init=[1]) since both remaining terminals are
    sinks. source=[2] → unverified rotation, settle with a run test
    (init=100/input=7 → expect 7). If already wired wrong, delete by
    the UID from `wires` and rewire.
- **Tap the Add output for the result, not the Feedback Node output** -
  the FN output lags one cycle (4851 instead of 4950 for sum 0..99).

Run-verify a generated VI via COM (VBScript only; the VirtualInstrument
class has no FP property - use the GetControlValue method):

```
cscript //nologo "%SKILL%\references\run_vi_get_value.vbs" "<vi path>" "<control>" [expected]
```

**`vi.Run True` is ASYNCHRONOUS** - it returns before the VI finishes;
reading the control immediately samples a mid-run value (cost a false
failure on pimc3: 0.0337 at iteration ~10.7k of 1e6, final 3.1408).
`run_vi_get_value.vbs` already waits: it polls until the value is
identical on 2 consecutive 500 ms polls (min 1.5 s, timeout 120 s).
Never trust a read sooner than ~1 s after Run. `vi.Running` is not a
supported property.

### Runtime value I/O with arrread.exe (UNIVERSAL, revised 2026-10-20)

`run_vi_get_value.vbs` is scalar-only. The universal FP value tool is
`%SKILL%\scripts\arrread.exe` (source `arrread.cs` beside it; rebuild with
the .NET 4.8 framework csc, C# 5 only - see header comment). It is a
pure-IDispatch dynamic COM client: works where WSH cannot (WSH cannot
index the `VT_ARRAY|VT_R8` that GetControlValue returns) and where
PowerShell cannot (dead RCW). It sets/reads ALL types - numerics of any
representation (U8..U64, I8..I64, SGL, DBL), strings, booleans, 1D/2D
arrays, clusters:

    arrread get    <vi> <ctl>                     print value + actual variant type
    arrread set    <vi> <ctl> <value>             typed grammar (below)
    arrread setint <vi> <ctl> "9,1,5"             legacy alias for ai:
    arrread run    <vi>                           Run(true) + 3 s sleep
    arrread cycle  <vi> <ctl> <value> [outctl]    set+echo+run+poll-read ONE process

Typed value grammar (case-insensitive prefix): bare number = double
scalar; bare comma-list = double[] (legacy); `dbl: sgl: i8: i16: i32:
i64: u8: u16: u32: u64:` scalars; `s:<text>` string; `b:true|false`
boolean; `a:1,2,3` double[]; `ai:` int[]; `as:a,b` string[];
`ab:true,false` bool[]; `au8: ... au64:` / `ai8: ... ai64:` typed int
arrays; `a2:[[1,2],[3,4]]` double[,]; `ai2:` int[,]; cluster
`c:(1,s:hi,b:true,ai:[1,2])` (object[] of variants; nested c:() ok;
array elements inside clusters need []).

Rules the hard way:

- **set/echo/run/get in ONE process (cycle).** Split across processes it
  silently fails whenever the target VI has no open front-panel window
  (documented GetControlValue behavior: the FIRST call on a VI whose FP
  was never shown returns DEFAULT values - this is also the root cause
  of the old "SET OK then len=0" trap). `cycle` now POLLS until the
  output is stable (Run(true) is async) and takes an optional separate
  outctl: `cycle <vi> NumIn 5 NumOut`.
- **Wrong-type sets are SILENTLY IGNORED.** SetControlValue with a
  variant that does not convert (e.g. Byte[3] into a cluster control)
  leaves the value unchanged - no error. ALWAYS check the ECHO line
  arrread prints after every set/cycle.
- **Read-back type proves the target representation.** GetControlValue
  returns the control's actual type: I32 control -> Int32, U8 -> Byte,
  SGL -> Single. 1D numeric arrays come back typed (Double[]), string
  arrays and 2D arrays come back as variant arrays (cluster[N] / rank=2
  type=Object[]).
- **Numeric variants coerce into ANY numeric representation** (verified
  i8..i64, u8..u64, sgl, dbl - exact round-trips on typed controls).
- **Zero broken wires proves nothing about runtime.** Always test with
  n>=3 distinct values (a 2-element test can pass by luck - cost a false
  "sorted" verdict), plus a duplicates case and a negatives case.
  Also: an UNWIRED Replace Array Subset index input silently defaults
  to 0 - the classic symptom is output = max repeated n times
  (case study: recipe v3.9, sortArr_tmp.vi).

Verified type matrix (recipe v3.27): gen\fpzoo.vi is the regression zoo
(NumIn/StrIn/BoolIn pass-throughs + I8..U64/SGL/String controls from
stock .ctls + DatumCtl cluster-with-array); Sort 1D Array.vim
(unsorted/sorted array - functional cycle 5,1,3 -> 1,3,5);
error.llb\Clear Errors.vi 'error in (no error)' for mixed clusters.

The COM round-trip pattern was proven with NI's "Creating New VI From
Scratch" example - see `references/labview-automation.md`. Working
templates to lift nodes from:
`_service/deprecated/scripting_examples/` (copies of NI's VI Scripting
examples plus their extracted artifacts). A complete verified
accumulator-in-loop transcript (sumtest9.vi, Result = 4950) is in the
recipe's "one-pass canonical build recipe" section - replay it as a
template.

## Troubleshooting

- `ClassFactory cannot supply requested class`, or COM hangs: a modal
  dialog (typically "Save changes?") is blocking an orphan LabVIEW
  instance. List with `lv_procs.ps1`, `taskkill /PID <pid> /F` the 64-bit
  orphan, retry. Clicking "Don't Save" on untitled scratch VIs is always
  safe - they are test artifacts, never user data.
- `GetActiveObject` never works for LabVIEW (it never registers in the
  ROT). Always `CreateObject("LabVIEW.Application")` from VBScript
  (`cscript`), never PowerShell `New-Object -ComObject` (returns a dead
  object).
- A VI open in the user's instance is fine to edit and run (live mode,
  the standard). Copy it first only when the operation would disturb the
  user's control values or when developing an unproven script (the
  copy-first rule).
- VI Server TCP port: x64 LabVIEW now listens on 3364, x86 on 3363 (only
  relevant for TCP clients; the COM path used here ignores the port).

## MCP server wrapper

A zero-dependency MCP stdio server wrapping these same tools lives at
`C:\LabView skill\mcp-labview\` (see its README for Zed/Claude Desktop
config). It adds two capabilities this skill's scripts do not have:
`search_ni_docs` / `fetch_ni_doc` (programmatic ni.com documentation
retrieval via NI's unofficial keyless `docs-be.ni.com` backend) and
MCP-native tool schemas for everything else. Note: NI's Nigel AI agent is
an MCP *client* (no public API for its knowledge) - this server can be
registered into Nigel on LabVIEW 2025 Q3+ with a license.

## References

- `references/labview-automation.md` - full verified findings: COM method
  matrix, export gotchas, local docs mirror, scripting capability map.
- `references/gateway-recipe.md` - build sheet for Gateway.vi (the user
  builds it once in LabVIEW; includes the v2/v3 roadmap).
- Screenshot-only analysis (no file path) -> use the `read-block-diagram`
  skill instead.
