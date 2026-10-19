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
