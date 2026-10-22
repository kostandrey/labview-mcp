# SubVI placement & NI library reference (gateway `place`, subVI mode)

Companion to gateway-recipe.md v3.16/v3.17/v3.20. Read the SKILL.md
`place`/`getNode` bullets first; this file holds the **verified
connector-pane tables** and per-VI quirks.

## CHECK THE RICH IDE LIBRARIES BEFORE BUILDING BY HAND (2026-10-19)

The LabVIEW IDE ships THOUSANDS of ready-made, tested VIs under
`<LV>\vi.lib\**` (incl. .llb libraries). Before generating primitive-node
code for any non-trivial computation (statistics, histogram, filters,
array ops, signal generation, file I/O...), SEARCH for an existing VI
first - one placed subVI call can replace 10-20 primitives:

```
find "/c/Program Files/National Instruments/LabVIEW 2020/vi.lib" \
  -iname "*.vi" -o -iname "*.llb" | grep -i <topic>
```

- place: `place;<vi>;any:0<full path to .vi or .llb\\member.vi>;<x,y>;<label>`
  (paths with spaces work; the 0 is literal)
- read the pane with `getNode;...;terms` (cell index == Terms[] index),
  wire by CELL NUMBER, then `errors` must be empty before running.
- Proven example: Histogram.vi (vi.lib\Analysis\baseanly.llb) -
  wired in ONE batch, zero broken wires, run-verified on 1e6 samples
  (h(x) summed to exactly N). Pane table below. Same library:
  Std Deviation and Variance.vi.
- Prefer .llb members that are already connector-wired; NEVER build a
  histogram/statistics chain from Add/Divide/SR primitives when a
  library VI exists.

## Locating and reading a subVI's interface

```
find "/c/Program Files/National Instruments/LabVIEW 2020" -iname "*.vi" | grep -i <name>
getNode;C:\...\<subvi>.vi;terms          # connector pane: Control[i]: UID, Label, Indicator, IsOnConPanel, Wiring rule
cscript //nologo mcp-labview\scripts\lv_extract2.vbs "<subvi>.vi" <outdir>
#   -> <outdir>_strings.txt: control types + full NI descriptions
#      (CONTROL ID=80 scalar, ID=82 array...); does NOT show constant values
```

- `getNode ... terms` cell index == the Terms[] index used for wiring.
- `not linked` = empty pane cell (wiring it -> broken:1, empty Name).
- A VI created by `newvi` has NO connector pane - it cannot be used as
  a subVI until a human connects the pane (and it must be SAVED;
  getNode-on-temp-copy reads the disk state).


## Finding the right VI AND its documentation (Linear Fit case study, 2026-10-19)

Worked example: "do a linear fit". Proven end-to-end; the same five
steps work for any non-primitive VI.

**1. Find the VI** (grep vi.lib, not the whole LV dir - `examples\`
noise comes first; API VIs live under vi.lib):

```
find "/c/Program Files/National Instruments/LabVIEW 2020/vi.lib" \
  -iname "*.vi" -o -iname "*.llb" | grep -i linear
```

-> `vi.lib\Analysis\6fits.llb`: Linear Fit.vi (polymorphic parent) +
(LS)/(Bisquare)/(LAR) instances, General (LS) Linear Fit, Linear Fit
Coefficients, Linear Fit Intervals... `6fits.llb` = the fitting
library; `7linalg.llb` = linear algebra; `gmath.chm` = their docs.

**2. Read the connector pane**: `getNode;<path>;terms`. A FRESH .llb
member load can fail ONCE with `Hex 0x3E8 The VI is not in a state
compatible with this operation` - just retry the same command (the
retry worked; do not conclude the VI is broken).

**3. Read the embedded documentation** with lv_extract2.vbs - extract
the POLYMORPHIC PARENT, not the instance: the instance's
`_strings.txt` often has EMPTY `<DESC>`; the parent carries the VI
description plus the full per-terminal NI descriptions. The parent's
header also tells you WHERE the printed documentation lives:

```
<HELP_PATH><PATH type="absolute"><<helpdir>><SEP>gmath.chm</PATH></HELP_PATH>
<HELP_TAG>Linear_Fit.html</HELP_TAG>
```

**4. Decompile that CHM and read the page** (7-Zip, then strip tags):

```
"/c/Program Files/7-Zip/7z.exe" x -o"<outdir>" \
  "/c/Program Files/National Instruments/LabVIEW 2020/help/gmath.chm" "*Linear_Fit*"
```

The page is the full spec: terminal semantics, defaults (tolerance
0.0001), enum values (method: 0=Least Square, 1=LAR, 2=Bisquare), the
algorithm equations, wiring notes.

**5. Online NI docs are a LAST resort**: both
ni.com/docs/.../labview-api-ref and zone.ni.com/<help-version> pages
are JavaScript shells - the `fetch` tool gets only navigation chrome,
no content. The local CHM is the same content and always works
offline.

---
## Rich IDE libraries: check before building by hand (2026-10-19)

The LabVIEW IDE ships THOUSANDS of ready-made, tested VIs under
`<LV>\vi.lib\**` (incl. `.llb` libraries). Before generating primitive-node
code for any non-trivial computation (statistics, histogram, filters,
array ops, signal generation, file I/O...), SEARCH for an existing VI
first — one placed subVI call can replace 10-20 primitives:

- find: `find "/c/Program Files/National Instruments/LabVIEW 2020/vi.lib" \
  -iname "*.vi" -o -iname "*.llb" | grep -i <topic>`
- place: `place;<vi>;any:0<full path to .vi or .llb\\member.vi>;<x,y>;<label>`
  (paths with spaces work; the `0` is literal)
- read the pane with `getNode;...;terms` (cell index == Terms[] index),
  wire by CELL NUMBER, then `errors` must be empty before running.
- Proven example: `Histogram.vi` (`vi.lib\Analysis\baseanly.llb`) —
  wired in ONE batch, zero broken wires, run-verified on 1e6 samples
  (Histogram_test session: h(x) summed to exactly N); see pane table
  below. Same library: Std Deviation and Variance.vi.
- Prefer `.llb` members that are already connector-wired; NEVER build a
  histogram/statistics chain from Add/Divide/SR primitives when a
  library VI exists.

## Verified connector panes (LV 2020)

### Histogram.vi - `vi.lib\Analysis\baseanly.llb`

| terminal | cell | direction |
|---|---|---|
| error | 0 | out (I32 error **code**, not a cluster) |
| X Values | 1 | out |
| Histogram: h(x) | 2 | out |
| Histogram Graph | 3 | out |
| intervals | 10 | in |
| X | 11 | in |

- `intervals` is a scalar I32 bin count, NOT a cluster - bins auto-span
  min(X)..max(X); default 10 (confirmed via strings export: type=
  "Numeric", "default is 10").

### Std Deviation and Variance.vi - `vi.lib\Analysis\baseanly.llb`

| terminal | cell | direction |
|---|---|---|
| X | 0 | in |
| Weighting | 1 | in |
| mean | 2 | out |
| std dev | 3 | out |
| variance | 4 | out |

One call gives mean AND sigma - prefer it over Mean.vi (whose pane
probe returned empty).

### Linear Fit.vi - `vi.lib\Analysis\6fits.llb` (polymorphic parent)

| terminal | cell | direction | type / notes |
|---|---|---|---|
| Y | 0 | in | 1D DBL array, dependent values |
| Best Linear Fit | 4 | out | 1D DBL array, fitted y-values |
| X | 5 | in | 1D DBL array, same size as Y |
| slope | 6 | out | DBL |
| Weight | 7 | in | optional; unwired = all 1 |
| intercept | 8 | out | DBL |
| tolerance | 9 | in | <=0 -> default 0.0001 (LAR/Bisquare only) |
| method | 11 | in | enum: 0 Least Square (default), 1 LAR, 2 Bisquare |
| parameter bounds | 12 | in | optional cluster (slope/intercept min/max) |
| residue | 14 | out | weighted mean (abs.) error |
| error | 15 | out | I32 error **code** (doc: wire to Error Cluster From Error Code) |

Cells 1,2,3,10,13 = `not linked` (empty).
The **(LS) instance** has the same pane MINUS tolerance/method/
parameter bounds (its cells 9-13 are `not linked`). Terminal types
from the strings export; full terminal descriptions live on the
PARENT (see step 3 above). After placing, probe the PLACED node
(`%Node|<label>`) - its Terms[] is ground truth and may differ from
the parent pane.

## Style-code terminal maps (LV 2020, gateway-verified 2026-10-19)

Primitives are OUTPUT-FIRST ([0]=out, then inputs). Codes also in
`style_codes.json` (byName/byCode).

| Code | Object | Terms[] |
|---|---|---|
| 1070 | Random Number (0-1) | [0]=out ("number: 0 to 1") |
| 1111 | Less? | [0]=out, [1]=y, [2]=x |
| 1167 | Boolean To (0,1) | [0]=out, [1]=Boolean in |
| 1209 | Natural Logarithm | [0]=ln(x) out, [1]=x |
| 1201 | Cosine | [0]=cos(x) out, [1]=x |
| 1060 | Square Root | [0]=sqrt(x) out, [1]=x |
| 2049 | Bundle | growable - see gotcha below |
| 1809 | Array Size | [0]=size(s) out, [1]=array in |
| 1903 | Add Array Elements | [0]=sum out, [1]=numeric array in; needs bounds (H=40 -> 1 chunk) |
| 21703 | Waveform Graph (modern) | FP object; pass W,H (e.g. `x,y,400,300`) |
| 23504 | Pi | places a REAL FixedConstant with value pi (class FixedConstant in wires) |
| 23505 | Pi Multiplied By 2 | TRAP: places a plain value-0 Numeric Constant, silently! |

### Special-constant trap (2pi)

`any:23505` ("Pi Multiplied By 2") silently places a value-0 constant.
`any:23504` ("Pi") is real. To get 2pi: place Pi (23504) and multiply
by 2. If a generated distribution comes out wrong, decode it
analytically (chain rule on the transformation; compare mean/sigma
against the closed form) - e.g. a Rayleigh distribution (z-mean
1.2533, z-sigma 0.6551) is the signature of a dead cos factor.

### Bundle resize gotcha

Placed height controls element count at ~8.7 px per element
(H=66 -> 8 elements, H=40 -> 5). `getNode` may list garbage terminals
beyond the real count; `errors`' "The type of the sink is cluster of N
elements" is ground truth. Best: avoid resized Bundles - check whether
the target input is really a cluster first (strings export).

## Workflow (proven end-to-end)

1. `newvi` the target; `place;<vi>;any:0<subvi path>;<x,y>;<label>`.
2. `getNode` the subVI path (pane) + lv_extract2 strings (types).
3. Wire (cell numbers!); `wires` after each phase - zero broken:1.
4. `errors` (empty = clean) -> run on a copy via run_vi_get_value.vbs
   -> statistics loop for anything random.
5. extract the finished VI; eyeball the PNG.
