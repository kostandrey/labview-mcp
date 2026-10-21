# LabVIEW VI Automation - Programmatic Extraction & Analysis

Verified method (2026-10-07, LabVIEW 2020 SP1 32-bit, Windows) for extracting a
VI's code as text + images when the user can provide the `.vi` file path. This
is **more reliable than screenshot analysis**: exact strings, all case views,
exact constants, no icon-recognition ambiguity. Use it whenever a file path is
available; fall back to screenshots only when it is not.

Scripts live in `scripts/` of this skill:

- `scripts/lv_extract2.vbs` - parametrized extractor (copy VI, export strings + HTML report + PNGs)
- `scripts/crop.ps1` - crop/zoom a region of any PNG (for reading wires at high magnification)

---

## 1. Running the extractor

```
cscript //nologo lv_extract2.vbs <source .vi path> <output dir>
```

What it does:

1. **Copies** the VI to `<output dir>\<name> (copy).vi` - the original is never
   opened or touched. **Never** `GetVIReference` a VI that is currently open in
   the user's running LabVIEW instance (lock/conflict risk). Copy first, always.
2. Spawns a LabVIEW instance via COM and waits until ready.
3. `ExportVIStrings` -> `<name>_strings.txt` (tagged text **including block
   diagram contents**).
4. `PrintVIToHTML` (eComplete, PNG, 24-bit) -> `<name>_report.html` +
   `images_<name>\` with PNGs.
5. Quits the spawned instance cleanly.

Verified console output looks like:

```
App.Version : 20.0.1f1
VI.Name    : ArdStepV2.lvlib:TMC current (copy).vi
VI strings exported: ..._strings.txt (5036 bytes)
HTML report: ..._report.html
images: 11 file(s)
done
```

## 2. Environment facts (all verified - do not re-learn the hard way)

| Fact | Detail |
|---|---|
| COM client | Use **VBScript** (`cscript`). PowerShell `New-Object -ComObject LabVIEW.Application` returns a **dead object** (empty `Version`, null-ref on methods). C# `dynamic` IDispatch (no typelib) WORKS - see `%SKILL%\scripts\arrread.cs`. |
| Attaching to a running instance | **Impossible.** `GetActiveObject("LabVIEW.Application")` always fails `MK_E_UNAVAILABLE` - LabVIEW never registers in the Running Object Table. `CreateObject` always spawns a **new** instance (may be a different bitness than the user's: user ran 32-bit GUI, COM spawned 20.0.1f1 64-bit). UPDATE 2026-10-15: with the 64-bit 20.0.1f1 GUI running, `CreateObject` attaches to the user's instance - live co-editing verified (gateway-recipe v3.6). |
| No-dialog open | `app.GetVIReference(path, "", False, &H20)` - `0x20` = no dialogs. |
| VI Server TCP | User's instance may listen on a non-default port (verified: **3363**, not the default 3361). Check with `Get-NetTCPConnection`. Live in-memory control of the user's instance is only possible from *inside* LabVIEW (a controller VI using VI Server refnums to `localhost:<port>`), not from external COM. |
| VI Scripting properties | `vi.BlockDiagram`, `.Nodes[]`, `.Wires[]` are **not reachable** through the external ActiveX IDispatch subset. Diagram structure comes from the strings export + report images instead. |
| `AllVIsInMemory` | May return "access denied" (0x408) on a fresh spawned instance depending on server-resource policy. Treat as optional. |
| Shell quoting | `$` in inline PowerShell gets eaten by the shell. Always write `.ps1`/`.vbs` files and execute them. |
| Array control values | `SetControlValue` accepts double[] and int[] variant arrays (int coerced to DBL); `GetControlValue` returns `VT_ARRAY\|VT_R8` that WSH **cannot index** (`v(i)`, `Join`, `For Each` fail; JScript `VBArray` rejects typed arrays; only UBound/IsArray work). Read elements via `%SKILL%\scripts\arrread.exe` (.NET marshals to System.Array). **Injected values persist only while the VI stays in memory** - do set/run/get in ONE process unless the VI's window is open in the IDE (gateway-recipe v3.9). |
| Search engines | ni.com docs are JS-rendered. DDG HTML endpoint (`html.duckduckgo.com/html/?q=...`) works but rate-limits aggressively; fall back to Brave (`search.brave.com/search?q=`), Bing, or the **local CHM docs** (see §6). |

## 3. Reading the report images

`images_<name>\` contains (suffixes verified):

| File | Content |
|---|---|
| `<name>_reportd.png` | Full block diagram **as saved** (shows the case that was displayed when the VI was last saved) |
| `<name>_reportd1.png`, `_reportd2.png`, ... | One image per additional case view of each structure |
| `<name>_reportp.png` | Front panel (read control defaults here - e.g. `V ref` default `NaN V`, `R sense` default `0.110 Ohm`) |
| `<name>_reportc.png` | Connector pane |
| `<name>_reporth.png` | Hierarchy |
| `cbool.png`, `cdbl.png`, `cu8.png`, `istr.png`, ... | Small legend images of data types |

**Always zoom before concluding.** Use `scripts/crop.ps1`:

```
powershell -ExecutionPolicy Bypass -File crop.ps1 -Src <png> -X <x> -Y <y> -W <w> -H <h> -Out <out.png> -Scale 6
```

Read the full diagram once for layout, then crop each region you are unsure
about at Scale 5-8. Typical regions needing zoom: middle arithmetic chains,
branch dots, tunnel squares, terminal arrows, case selector wiring.

Key visual facts (verified):

- **Case selector tunnel** = a green box marked `?` on the structure border
  (confirmed against the local docs image `casestru.gif`). A *data* tunnel is a
  plain filled square. Do not confuse them - misreading a selector tunnel was
  nearly a fatal error once.
- **Control vs indicator terminal**: the small arrow on the terminal shows data
  direction (out = control being read, in = indicator being written). A
  terminal placed *inside* a case is only accessible in that case.
- **Tunnels**: one wire per case. A tunnel can be *written* in one case and
  *read* in another. Wire direction is not visible in a static image - derive
  it from logic and cross-check both cases' images.
- **Branch dots**: a wire splitting into two destinations shows a dot; that is
  how one source feeds e.g. both a case tunnel and a `NaN?` check.

## 4. Reading the strings export (`*_strings.txt`)

Structure: `<VI>` -> `<CONTENT>` (front-panel objects: controls, indicators,
typedef clusters with nested controls, labels, defaults) -> `<BDCONTENT>`
(block diagram: constants, primitive functions with `primName`, structures
with nested `<BDCONTENT>` per case).

Trust it for: control/indicator names, typedef cluster contents, string
constants (`format string` values like `%.3f A`), function names
(`primName="Square Root"`, `"Divide"`, `"Not A Number/Path/Refnum?"`,
`"(Un)Bundle by Name"`).

Known gotchas (all encountered once):

- **Terminals of FP controls/indicators are NOT listed** inside `<BDCONTENT>`.
  A terminal you see in an image (e.g. `V ref` inside one case) will be absent
  from the strings file. Only constants, functions and structures appear.
- **Case `<BDCONTENT>` order is not guaranteed `[True, False]`.** In a real VI
  it came out `[False, True]` for both structures. Always match case contents
  against the labelled case images (`True`/`False` in the selector label)
  instead of trusting order.
- **Constants may have odd `name=` values** (`"x"`, `"f"`, `"t"`) - these are
  labels/roles, not values. Read the **values from the images** (e.g. `2`,
  `0.18`, `0.32`).
- **Formula Box / Formula Node code text is NOT exported.** The formulas
  (`Imax=(IRUN+1)/(32*(R+0.02));`) are only readable from the diagram PNGs -
  zoom in and transcribe exactly.

## 5. Case-structure analysis workflow (produces reliable pseudocode)

1. **Identify each structure's selector source** (which wire enters the `?`
   selector tunnel). Crop the border if unsure.
2. **Determine each case's contents** from the per-case images, *not* from
   strings-file order. Note the selector label (`True`/`False`) on each image.
3. **Derive Boolean polarity from content semantics**, not from label position
   guesses. In the worked example (TMC current.vi), physics forced
   `FALSE = External reference, TRUE = Internal reference`; that in turn fixed
   the Boolean T/F label order as `[F, T]` in the strings export, which the
   `Select` wiring (0.18 to `t`, 0.32 to `f`) then independently confirmed.
4. **Trace every tunnel's role**: which case writes it, which reads it, and
   where the outside wire branches (follow the dots).
5. **Write pseudocode** in the SKILL.md Step-5 format. For each case structure
   use an explicit `CASE selector OF` block with the selector's source named.
6. **Verify primitives against documentation** (SKILL.md Step 4). Local mirror
   shortcut: `glang.chm` (see §6) has every function page with a terminal-order
   picture - e.g. `Select.html` shows `t` top, `s` middle (green dotted), `f`
   bottom, matching how the function is wired in practice.
7. **Cross-check against domain documentation** (datasheet, wiki) when the user
   gives domain context. Keep this in a separate "domain interpretation"
   section per SKILL.md rules. Example: TMC2209 `IRMS = 325mV/(Rsense+20mΩ) ×
   1/√2 × Vref/2.5V` (BTT wiki) matched the External path of the analyzed VI
   exactly; the Internal path's scaling was flagged for user confirmation
   instead of silently assumed correct.
8. **Report behavior-level findings**: NaN defaults produce "hint" strings
   (`(Vref(V) * %.3f) A`) in one case and numeric results in the other - state
   which input states select which output format.

## 6. Local documentation mirror (faster + more reliable than web search)

The installed LabVIEW's CHM files extract to plain HTML with 7-Zip:

```
"C:\Program Files\7-Zip\7z.exe" x -y -o"C:\LabView skill\help\glang" "C:\Program Files (x86)\National Instruments\LabVIEW 2020\help\glang.chm"
```

Useful CHMs (in `...\National Instruments\LabVIEW 2020\help\`):

| CHM | Content |
|---|---|
| `glang.chm` | Function reference - every primitive with terminal-order images (`Select.html`, `Case_Structure.html` + `casestru.gif`, ...) |
| `lvscript.chm`, `lvprop.chm`, `axprop.chm` | VI Scripting / VI Server properties (full ActiveX member names) |
| `lvhowto.chm`, `lvconcepts.chm` | How-to and concepts |

Grep the extracted HTML (`sed 's/<[^>]*>/ /g' file.html`) for semantics, and
`read_file` the `.gif` terminal-order images directly.

## 7. External VI Scripting bridge (verified 2026-10-07)

VI Scripting primitives (`BlockDiagram`, `Nodes[]`, `New VI Object`, wiring) are
**not callable over external COM** - they only execute *inside* LabVIEW. But
COM CAN set front-panel controls, run a VI, and read its indicators
(`SetControlValue` / `Run` / `GetControlValue`). Combining both:

**COM -> drive a "Gateway" VI that performs VI Scripting -> read JSON result.**

Verified building blocks:

- COM `VI` methods (from `axprop.chm`): `Run([async])`, `Call`/`Call2`,
  `SetControlValue`, `GetControlValue`, `ExportVIStrings`, `ImportVIStrings`,
  `PrintVIToHTML/Text/RTF`, `SaveInstrument`, `SaveForPrevious`, `Revert`,
  `GetVIDependencies`, `OpenFrontPanel`, `CloseFrontPanel`, `Abort`,
  `MakeCurValueDefault`, `SetLockState`. There is **no plain `Save`** - use
  `SaveInstrument`.
- `CreateObject("LabVIEW.Application")` **attaches to a living spawned
  instance** (multi-use server) - leftover instances get reused; kill orphans
  before testing (`taskkill /PID <pid> /F`).
- A spawned instance with unsaved in-memory VIs (e.g. an Untitled generated VI)
  pops a modal **"Save changes?"** dialog on `Quit`/close that blocks further
  COM activation (`ClassFactory cannot supply requested class`). Kill the
  orphan process to unblock.
- `AllVIsInMemory` stays **denied (0x408)** on spawned instances even with all
  "Accessible Server Resources" checked - it is an application-instance policy.
- NI ships ready-made VI Scripting example VIs under
  `examples\Application Control\VI Scripting\` (both bitness installs):
  *Creating VIs/Creating New VI From Scratch.vi* (generates a complete wired VI
  via `New VI` + `New VI Object` - **verified externally driven, generated VI
  confirmed on screen**), *Finding and Modifying Objects/Navigating Nodes and
  Wires.vi* (traverse + rewrite a constant), *Using Traverse.vi*,
  *Obtaining Unknown Object References.vi*.
- `Traverse for GObjects.vi` (in `vi.lib\Utility\traverseref.llb`) is NI's
  general diagram walker: inputs = object ref + "Traverse Target" enum
  (`BD`/`FP`) + class specifier filter; output = array of GObject references.
- Documented navigation pattern (from the example help):
  `Node:Terminals[]` -> `Terminal:Connected Wire` -> `Wire:Terminals[]` ->
  `Terminal:Owner` gives full wire connectivity. Code generation:
  `New VI` (Application method) -> `New VI Object` per object -> wire via
  `New Wire`/terminal references.
- **Known pitfall (unresolved cause)**: driving NI's traversal demo via COM ran
  without error but modified nothing - likely its hard-wired *relative* path
  constant does not resolve in a headless COM-spawned instance. Demos are
  fixed-logic (path constants, no FP controls) - not drivable gateways.
  Absolute-path inputs via an FP control are required for reliable external
  driving.
- The GitHub tool `rea` (morluto/rea) is a binary/JS/.NET reverse-engineering
  MCP - it has **no LabVIEW provider** and cannot parse `.vi` files.

**The Gateway VI design (recommended one-time manual build, ~15 nodes):**

- FP: `command` (string control, JSON), `result` (string indicator, JSON).
- BD: parse `command` -> case dispatch:
  - *analyze*: absolute VI path -> `Open VI Reference` -> `BlockDiagram` ->
    `Traverse for GObjects` (BD, GObject class) -> For Loop reading
    `ClassName`/`Label`/`Owner` (v1), then the terminals/wires pattern (v2) ->
    concatenate to JSON -> `result`.
  - *generate*: `New VI` -> `New VI Object` per spec entry -> wire ->
    `SaveInstrument` -> return path.
  - *memory*: `AllVIsInMemory` of a chosen application ref.
- External driver loop: `SetControlValue("command", json)` -> `Run` ->
  `GetControlValue("result")`.
- Run the Gateway inside the user's 32-bit instance (or have it
  `Open Application Reference` -> `localhost:<port>`) to inspect the user's
  live open VIs.

Port note: both LabVIEW bitness installs were configured with TCP/IP port
**3363**; when two instances run at once the second bind fails. Use different
ports per bitness (e.g. x86=3363, x64=3364).

## 8. Modifying VIs - capability matrix

| Task | Possible? | Route |
|---|---|---|
| Read/extract code | **Yes** | This method (on a copy) |
| Change a constant value, string constant, FP default, VI description on a **disk copy** | **Yes** | COM: open copy with `0x20`, set property (e.g. via `VI.Scripting`-free properties available over IDispatch: `FP.Descriptions`, etc.), `Save`/`SaveAs`. Test what is exposed before promising. |
| Rewire, add/remove nodes, edit diagram structure | **No** from external COM | Requires VI Scripting *inside* LabVIEW |
| Edit the user's *running* instance | **No** from outside (no ROT registration) | Requires a controller VI inside the user's instance: `Open Application Reference` -> `localhost:<port>` (user uses **3363**) -> `Open VI Reference` -> `Block Diagram` -> `Nodes[]`; user builds it from a node-by-node recipe the agent provides |

When the user asks for a modification you cannot perform externally, say so
plainly and offer the closest achievable option (copy-edit, or a controller-VI
recipe they can build in minutes).

## 9. Worked example (full pipeline)

Input: `C:\...\StepV2\TMC current.vi` (path from user; VI also open in their
instance - irrelevant, we worked on a copy).

1. `cscript //nologo lv_extract2.vbs "C:\...\TMC current.vi" "C:\LabView skill\_service\extract"
2. Strings export: cluster typedef `TMC values` (`Reference voltage source`
   Boolean, `Internal voltage value` Boolean, `IRUN(0-31)` U8), `R sense`,
   `V ref`, string indicators `Imax`/`Irms`; BD: Formula Box(es), `Square Root`,
   `Divide`, `Not A Number/Path/Refnum?`, two case structures, `Select`,
   format constants `%.3f A` and `(Vref(V) * %.3f) A`.
3. Images: FP defaults (`R sense` 0.110 Ohm, `V ref` NaN V); case views
   (`True`/`False` labels); cropped regions resolved: `2 -> Square Root ->
   Divide` chain, `Select(t=0.18, s=green dotted, f=0.32)`, branch dot feeding
   a case tunnel + `NaN?`, selector tunnel `?` squares.
4. Local CHM `Select.html` + `casestru.gif` confirmed terminal order and
   selector-tunnel appearance.
5. Brave search confirmed the TMC2209 datasheet formula; internal-path scaling
   flagged to the user instead of assumed.
6. Output: summary + element table + pseudocode with two `CASE` blocks
   (see the conversation record / SKILL.md Step 5 structure).
