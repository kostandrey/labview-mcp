---
name: read-block-diagram
description: Describes a LabVIEW block diagram image in plain text - identifies controls, indicators, constants, functions, wires, and data flow, and verifies each function's behavior against ni.com documentation. Use when the user shares a block diagram screenshot or asks "what does this block diagram do".
---

# Read LabVIEW Block Diagram

Convert a LabVIEW block diagram (image) into an accurate textual description of
what it computes, grounded in NI documentation.

## Step 0 - If a .vi file path is available, prefer programmatic extraction

A screenshot analysis is the fallback. If the user can give you the path to
the `.vi` file, extract its code programmatically instead - it yields exact
strings, exact constants, every case view as an image, and no icon-recognition
ambiguity. See `references/labview-automation.md` for the verified procedure
and `scripts/lv_extract2.vbs` + `scripts/crop.ps1` for the ready-made tools:

```
cscript //nologo lv_extract2.vbs <source .vi path> <output dir>
```

This produces a strings export (all controls, constants, function names) plus
an HTML report with PNGs of the front panel, the block diagram, and each case
of every structure. Analyze those artifacts (Steps 2-5 below still apply for
verification and description writing), then produce the description and
pseudocode. Never open the user's original VI - the script works on a copy.

## Step 1 - Get the image

If the user pasted an image, analyze it directly. If they gave a file path,
read it with `read_file` (image files are supported). If no image is
available, ask for it. Low-resolution images: state confidence limits rather
than guessing terminal orderings.

**Multiple images (e.g. each case of a Case Structure):** treat them as one
VI. Build a single merged inventory, confirm every tunnel/terminal position
matches across case images, and check that each tunnel is wired in *all*
cases (an unwired tunnel in one case yields undefined data). Objects visible
in only one image may exist in the VI but sit outside the cropped area in
the other.

## Step 2 - Inventory the diagram

Identify every object and classify it. Use `references/visual-vocabulary.md`
for the full identification guide (node shapes, wire colors, terminal
appearance). Record for each object:

- **Type**: front-panel control (thick terminal border), indicator (thin
  border), constant (no border, value shown), primitive function (pale-yellow
  icon), Express VI (blue icon, expandable), subVI (icon with connector pane
  pattern), or structure (large resizable rectangle: For Loop, While Loop,
  Case, Sequence, Event...).
- **Identity**: read the label (e.g. `Channels Num`) or the function name
  (e.g. `Greater?`, `Select` - LabVIEW shows the function name as a label if
  it is visible).
- **Constants**: record their literal values.

When icon appearance is ambiguous, compare against
`references/function-palette-icons.md` (standard palette icons) before
guessing. A **Formula Node**'s code text is ground truth - transcribe it
exactly and treat its named border terminals as inputs (left) and outputs
(right). If the user gives domain context (e.g. a chip datasheet or driver
name), use it to sanity-check constants and suggest interpretations, but
keep those interpretations in a separate "domain interpretation" note -
never merge them silently into the diagram facts.

## Step 3 - Trace wires and data flow

Use wire color/thickness to infer data types (see the reference file). Trace
from sources (controls, constants) through functions to sinks (indicators,
outputs). Note loops, shift registers, tunnels, and case selector wiring.

## Step 4 - Verify function behavior on ni.com

ni.com pages (Zoomin-based docs) are JavaScript-rendered - a direct fetch of
`https://www.ni.com/docs/...` returns only the navigation shell. To get the
actual description text, search for it and read the search-result snippet,
which contains the ni.com meta description (verified to work):

1. Fetch (with the `fetch` tool or `curl`):
   `https://html.duckduckgo.com/html/?q=ni.com+labview+<function+name>+function`
   - Example: `...?q=ni.com+labview+select+function` returns the snippet
     "Returns the value wired to the t input or f input, depending on the
     value of s. If s is TRUE, this function returns the value wired to t..."
2. The snippet also gives the canonical URL, typically
   `https://www.ni.com/docs/en-US/bundle/labview-api-ref/page/functions/<name>.html`
   - Cite this URL in the output.
3. If the snippet is insufficient, try Bing (`https://www.bing.com/search?q=...`)
   or re-query DDG with different terms. Search engines rate-limit bots - if
   all lookups fail, say so and fall back to the local palette reference and
   clearly-marked inference instead of inventing semantics. The static mirror
   `https://documentation.help/NI-LabVIEW/` can also be checked by hand.
   Do not invent function semantics.

Look up every primitive function whose exact semantics matter (comparison
operators including which input is x vs y, Select input order t/s/f, In Range
and Coerce, etc.). Input order is a common source of error - verify it.

## Step 5 - Write the description

Produce this structure:

1. **Summary** - one paragraph: what this diagram computes, in plain language.
2. **Elements** - a table: Element | Type | Details (label, value, data type).
3. **Data flow** - step-by-step narrative following the wires, from sources to
   outputs, naming each function and its verified behavior (with the ni.com
   URL cited).
4. **Pseudocode** - an equivalent in C-like pseudocode (or a truth table for
   pure logic).
5. **Notes / uncertainties** - anything ambiguous (unreadable labels, unknown
   terminal order, off-screen wiring, coercions, integer overflow concerns).

Be explicit about ambiguity instead of silently choosing one interpretation.
When resolution is the limiting factor, end with a short list of **targeted
follow-up requests** (e.g. "crop of the middle chain at 2x") instead of
guessing.

## Related references

- `references/visual-vocabulary.md` - node shapes, wire colors, terminal appearance.
- `references/function-palette-icons.md` - standard palette icons.
- `references/labview-automation.md` - programmatic .vi extraction, report/strings
  interpretation, case-structure analysis workflow, local CHM docs mirror, and
  the VI-modification capability matrix.

## Worked example

Input image: a control labeled `Channels Num` (star badge = required input on
its connector pane; blue wire = integer). A numeric constant `6` and the
control wire the two inputs of a `Greater?` comparison function (green
Boolean wire out). Constants `32` (top input) and `0` (bottom input) wire
into a `Select` function; its Boolean `s` input comes from `Greater?`.

Verified on ni.com:
- `Greater?` (https://www.ni.com/docs/en-US/bundle/labview-api-ref/page/functions/greater.html):
  computes `x > y`, returns TRUE if x is greater than y.
- `Select` (https://www.ni.com/docs/en-US/bundle/labview-api-ref/page/functions/select.html):
  returns `t` if `s` is TRUE, else `f`; top input = `t`, bottom = `f`.

Description:

> **Summary**: The diagram converts an integer channel count into either 32
> or 0, depending on whether the channel count exceeds 6.
>
> **Data flow**: `Channels Num` and the constant `6` feed the `Greater?`
> comparison, which outputs TRUE when `Channels Num > 6`. That Boolean
> selects the `Select` function's output: TRUE passes the value `32` (wired
> to the `t` input), FALSE passes `0` (wired to the `f` input).
>
> **Pseudocode**:
> ```c
> int out = (channels_num > 6) ? 32 : 0;
> ```
>
> **Notes**: `Select` input order (t on top, f on bottom) was confirmed from
> the NI documentation; the `32`/`0` assignment depends on the constants'
> vertical positions in the image, which appear as 32 above 0.
