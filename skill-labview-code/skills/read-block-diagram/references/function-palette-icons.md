# LabVIEW Function Palette Icons (Quick ID)

Icon-recognition table for the standard palettes. "▷" marks the typical
right-pointing triangle shape of arithmetic/Boolean/comparison primitives.

## Comparison (all triangles unless noted)

| Icon appearance | Function |
|---|---|
| `=` ▷ | Equal? |
| `≠` ▷ | Not Equal? |
| `>` ▷ | Greater? |
| `<` ▷ | Less? |
| `≥` ▷ | Greater Or Equal? |
| `≤` ▷ | Less Or Equal? |
| `=0`, `≠0`, `>0`, `<0`, `≥0`, `≤0` ▷ | ...To 0? variants (single input) |
| Triangle with `?` and 3 inputs (s, t, f) | **Select** |
| Rectangular icon, 2 numeric in / 2 out | **Max & Min** (only comparison with two outputs) |
| Rect icon with ⇐? ⇒? arrows | **In Range and Coerce** (3 in: value, lower, upper; coerced out) |
| `?□` ▷ | Not A Number/Path/Refnum? |

## Numeric (triangles carry the operator)

`+` Add, `−` Subtract, `×` Multiply, `÷` Divide, `R/T` Quotient & Remainder,
`+1` Increment, `−1` Decrement, `|x|` Absolute Value, `√` Square Root,
`x²` Square, `1/x` Reciprocal, `±` Sign, `><` Negate, `x2ⁿ` Scale By Power
Of 2, `Γ(x)`-style Round To Nearest / Toward ±Infinity, dice icon Random
Number (0-1). Constants: blue `I32` box = Numeric Constant, orange `DBL` box
= DBL Numeric Constant, `+Inf`, `-Inf`, `NaN`, `ε`.

## Boolean (triangles with A/V shapes)

`▷A` And, `▷V` Or, `▷V̲` Exclusive Or, `▷•` Not, `▷⇒` Implies, `▷A̲` Not And,
`▷V̄` Not Or, And/Or Array Elements, `N→B` Num to Array, `B→N` Array to Num,
`T`/`F` True/False Constant.

## Array

Array Size, Index Array (grid + index list), Replace Subset, Insert Into
Array, Delete From Array, Initialize Array (grid + `→n`), Build Array
(two grids + `→`), Array Subset, **Max & Min**, Reshape Array, Reverse 1D
Array, Split 1D Array, Interleave/Decimate 1D, Transpose 2D.

## Cluster, Class & Variant

**Unbundle By Name** (cluster in left, named element terminals on right edge,
element name shown per terminal), **Bundle By Name** (named terminals on
left, cluster out right), Unbundle (numbered terminals), Bundle (numbered
terminals), Cluster Constant, Build Cluster Array, Cluster To Array, Array
To Cluster.

## String / Number-String Conversion

String Length, Concatenate Strings (two strings → one), String Subset,
Replace Substring, Search and Replace String, Match Pattern / Match Regular
Expression, Scan From String, **Format Into String**, Format Date/Time
String, Build Text, **Number To Fractional String** (orange `DBL` terminal +
pink string terminal on one small node; inputs number/width/precision; the
format string, e.g. `%.3f`, is shown as a label above the node),
Spreadsheet String To Array, Array To Spreadsheet String.

## Synchronization / Occurrences

**Wait on Occurrence**: right-pointing pale-yellow triangle with a HOLLOW
CIRCLE near the output tip (the occurrence symbol). Terminals: `ms timeout`
(top, I32, −1 = wait forever), `occurrence` (left, refnum), `ignore previous?`
(bottom, Boolean, default TRUE), `timed out` (Boolean out). Verified against
help/glang Wait_On_Occurrence.html + waitonoc.gif. **Generate Occurrence** and
**Set Occurrence** are the same family (occurrence refnum wires between them).
NI recommends Notifier Operations instead of occurrences for most uses.

## Recognition tips

- **A triangle does NOT identify the palette.** Arithmetic, comparison and
  Boolean primitives are triangles, but so are timing/synchronization nodes
  (Wait on Occurrence = triangle + hollow circle, Wait (ms), Wait Till Next
  ms Multiple, occurrence functions) and others. When the glyph is not a
  known operator, DO NOT enumerate only boolean/numeric/comparison
  candidates - search the local glang mirror for the real icon
  (`ls <mirror>/*.gif` + view, or grep the HTML for the description) and
  compare. Lesson learned the hard way: a triangle with a hollow circle is
  Wait on Occurrence, not any Boolean primitive.

- Triangle + operator symbol = arithmetic or comparison primitive; check for
  a small `0` or `?` glyph inside to distinguish `x?y` from `x?0?` forms.
- A **Formula Node** (large grey rectangle with C-like code) has named
  rectangular input terminals on its left border and output terminals on its
  right border; the code text is ground truth for its behavior.
- At low resolution, do not guess between look-alike triangles (Divide `÷`
  vs Greater `>`, Square Root `√` vs Subtract) - ask for a crop.
