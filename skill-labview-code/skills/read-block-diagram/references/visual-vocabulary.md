# LabVIEW Block Diagram Visual Vocabulary

How to recognize block diagram objects. Based on the LabVIEW documentation
(ni.com "Block Diagram Objects", "Data Types in LabVIEW", "Functions
Overview"). When unsure, verify a rule via search snippets from ni.com (see
SKILL.md Step 4) instead of guessing.

## Node types by appearance

| Appearance | Meaning |
|---|---|
| Terminal with **thick** border | Front-panel **control** (input, read on the block diagram) |
| Terminal with **thin** border | Front-panel **indicator** (output, written on the block diagram) |
| Value in a rectangle with **no border** | **Constant** (literal value; shows a data-type icon, e.g. blue `I32`) |
| Small pale-yellow icon, black foreground | **Primitive function** (Add, Greater?, Select, Build Array, ...) - cannot be opened, has a connector pane |
| Large blue icon with inputs/outputs and a label, often wider than tall | **Express VI** (configurable, e.g. Simulate Signal) |
| Icon (may look like a picture/logo) | **SubVI** (callable VI with connector pane) |
| Large resizable rectangle | **Structure**: For Loop (bordered rectangle with `N`), While Loop (with stop condition), Case Structure (selector + case pages), Flat/Stacked Sequence, Event Structure, Timed Loop, Diagram Disable |
| Node with a `?`-style triangle and three inputs (s, t, f) | `Select` function |
| Triangle with `>`, `>=`, `=`, `!=`, `<`, `<=` | Comparison functions (Boolean output) |
| Triangle with a **hollow circle** near the output tip | `Wait on Occurrence` (Synchronization»Occurrences) - NOT a Boolean primitive; triangles appear in many palettes |
| Rectangle icons with `+`, `-`, `*`, `/` | Arithmetic primitives |

Star badge on a terminal label = **required** input on the VI's connector pane.

## Wire colors (data types)

| Color | Data type |
|---|---|
| **Blue** | Integer (8/16/32/64-bit - thicker wire = more bits; also enums) |
| **Orange** | Floating-point (SGL/DBL/EXT - thicker wire = more precision) |
| **Green** | Boolean |
| **Pink** | String |
| **Brown** | Fixed-point numbers; brown pattern = cluster of numerics |
| **Dark green** | Waveform, Digital, Dynamic Data (DDT), I/O refnums (VISA, DAQmx, task/queue refnums) |
| **Dark yellow** | Error cluster |
| **Purple** | Image data (NI Vision / IMAQ) |
| **Broken (dashed with red X)** | Broken wire - type conflict or unwired sink |

Thickness conveys bit width for numerics; a wire inherits its array/cluster
element color (arrays of DBL are orange, etc.).

## Data-flow rules to apply when describing

- **Dataflow execution**: a node runs only when all required inputs have
  data; describe causality left-to-right only as drawn, not as guaranteed
  execution order.
- **Comparison inputs**: for `x ? y` comparisons, the **top** input is `x`,
  the **bottom** input is `y`.
- **Select** function: `s` (Boolean) = middle-left input; **top** input `t`
  is returned when `s` is TRUE, **bottom** input `f` when FALSE.
- **Coercion dots** (small red dot at a terminal) = implicit numeric
  conversion; mention it (possible precision loss).
- **Loops**: indexing tunnels ([] brackets) vs concatenated tunnels; shift
  registers carry values between iterations; an unwired/uninitialized shift
  register keeps state across calls.
- **Case structures**: describe which selector values map to which
  subdiagrams; unwired tunnels in a case output undefined data.

## Common primitives worth verifying on ni.com

`Select`, `In Range and Coerce`, `Max & Min`, `Quotient & Remainder`,
`Array Size`, `Index Array`, `Build Array`, `Bundle/Unbundle By Name`,
`Format Into String`, `Scan From String`, `Time Delay`, `Wait (ms)`,
`Elapsed Times`, queue/notifier/TDMS VIs.
