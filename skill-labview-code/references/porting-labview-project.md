# Porting a LabVIEW project to another language (C++ / Python)

Methodology for rebuilding a many-VI LabVIEW project in a target
language using the labview-mcp harness. Written 2026-11-02 after
verifying `CompileToDFIRCPP` + `lv_dfir.py` (recipe v3.49/v3.50).

## Core idea: the DFIR dump is the language-agnostic IR

The hardest part of a port is not translating operators - it is
**recovering the exact semantics** of each block diagram (dataflow
order, tunnel indexing modes, shift-register chaining, case ranges,
array handling). The `CompileToDFIRCPP` verb produces a complete
machine-readable reconstruction of each VI (nodes, UIDs, constant
values, connectivity), and `lv_dfir.py` turns it into JSON. That JSON
is the **single source of truth ("IR")** during the port: the target
code must implement the JSON, and every question about "what does the
original do" is answered by inspecting the IR, never by guessing from
a screenshot.

Complementary sources, in priority order:

1. **`CompileToDFIRCPP` + `lv_dfir.py`** - exact semantics (structure,
   wiring, values). Requires the VI to be clean/compilable
   (broken VI -> ERROR 1000).
2. **`analyze` / `wires` / `getNode`** - labels, FP element UIDs,
   connector-pane mapping (which cell is which input/output) - needed
   to define the ported function's signature.
3. **`getval` / `arrread` cycle** - actual FP control DEFAULT values
   and constant values (cross-check the DFIR blob decode; recipe v3.31
   rules: FP values are runtime-only, use arrread cycle for closed VIs).
4. **`extract_vi` PNGs** - visual reference for human review of the
   ported code and for layout/flow intuition.

## Workflow (per project)

### 1. Inventory and call graph

- `analyze` every VI; `getNode` (plain .vi path) gives the connector
  pane per VI = the ported function's signature contract.
- Build a call graph from subVI calls (place/analyze listmem; or
  grep the extract_vi strings export for subVI references).
- Order VIs **leaf-first**: port callees before callers; a VI is only
  ported when all its dependencies are ported and tested.

### 2. Per-VI semantic export

For each VI (leaf-first):

```
cscript //nologo _service/tmp/lv_gw_call.vbs "C:\LabView skill\gateway\Gateway.vi" \
    CompileToDFIRCPP <vi_path> <CIdentifier> 0 "" <out.cpp>
python mcp-labview/scripts/lv_dfir.py <out.cpp> -o <out>.json
```

Keep `<out>.json` in the port repo next to the generated code - it is
the contract that the generated code is reviewed against.

**SubVI calls** export as `DFIR::SubVI` nodes whose Create call embeds
the callee path (`LinkIdentity(&PathRef("...\\callee.vi", ...))`) -
the whole call graph is recoverable by grepping the dumps; a callee's
own dump is a separate CompileToDFIRCPP run on its file.

### 3. Golden tests BEFORE translating

- Drive the original VI with `arrread` **cycle** mode: set known
  inputs, run, read outputs -> golden input/output vector pairs
  (JSON fixture per VI). Cover the interesting branches: every case
  frame, empty/full arrays, edge values.
- These vectors are the acceptance tests for the ported code.

### 4. Translate

Map DFIR JSON to the target language. Verified correspondences:

| DFIR class | C++ | Python |
|---|---|---|
| `Add/Subtract/Multiply/Divide...Primitive` | `+ - * /` | `+ - * /` |
| `ForLoop` (indexing tunnel in) | `for (i=0; i<N; ++i)` | `for i in range(N)` |
| `ForLoop` + `CreateTunnel(..., Indexing, ...)` | element-wise loop over array | `for x in arr` / comprehension |
| `WhileLoop` + `LoopCondition` | `while (cond)` | `while cond:` |
| `CaseStructure` + `CaseSelector` ranges | `switch`/`if-else if` | `if/elif/else` or dict dispatch |
| `Left/RightShiftRegister` | variable carried across iterations (`i`/`o` terminals = init/carry) | loop-carried variable |
| `Tunnel(Indexing, Input)` | auto-indexed array input (scalarize per iteration) | iterate the array |
| `Tunnel(Indexing, Output)` | array accumulator appended per iteration | `list.append` then result |
| `Tunnel(Concatenate)` | array built by concatenation | `list.extend` / `+=` |
| `Constant` (value in blob) | literal | literal |

Rules learned from DFIR dumps:

- **Dataflow -> topological order**: within one diagram, execute nodes
  in dependency order derived from `connections` (src terminal ->
  dst terminal). The JSON's per-diagram node list + connections IS the
  topological problem - a 20-line Kahn topological sort on it gives
  the execution order.
- **Shift registers**: the Left SR `count` and the Right SR accessor
  show how many history stages exist; `sri`/`sro` wire terminals give
  init vs carried value (recipe: input# 0 = plain).
- **Auto-index vs regular tunnels** are explicit in DFIR
  (`NonIndexing` vs `Indexing`) - this is exactly the detail that
  breaks naive ports, and the JSON states it.
- **Constant values** arrive decoded (`value: {type, name, value}`);
  DBL literals can be used directly (they were little-endian decoded
  by the parser).
- **Clusters/arrays** in the data blob: decode with lv_flat if the
  JSON `value` is absent (MakeTDR-only windows are type-only).

### 5. Verify each ported VI

- Port the golden vectors to the target language's test runner
  (pytest for Python, a small main() per VI for C++) and run against
  the JSON fixtures.
- Only mark a VI "ported" when ALL its golden vectors pass; then move
  to its callers.

### 6. AI-agent instructions (when an agent does the port)

- Work **leaf-first**, one VI at a time; never start a caller before
  all callees pass their vectors.
- Keep the DFIR JSON beside the generated file; cite node UIDs in
  code comments when a non-obvious translation is made
  (e.g. `// case frame 2 (UID 43): x+y when sel==2`).
- **Never run write verbs (place/wire/delete/setval/loop) on the
  user's original VIs** - copy-first rule (gateway copy or
  `copy;<src>;<dst>` in batch scripts). CompileToDFIRCPP, analyze,
  wires, getval, errors are read-safe.
- If a VI is broken (ERROR 1000), fix a COPY in the IDE or report -
  do not silently skip it (broken VI = unknown semantics).
- Numeric fidelity: LabVIEW DBL = C++ `double` / Python `float`
  (both IEEE 754 binary64); I32 = `int32_t` / keep Python ints but
  bound-check; watch integer division and overflow semantics (LabVIEW
  I32 arithmetic wraps; C++ UB, Python arbitrary precision - add
  masking where the original used I32).
- LabVIEW arrays are length-prefixed and 0-based like C arrays;
  empty array vs unwired input is a real distinction in the original
  - preserve it as `None`/optional in Python, sentinel in C++.

## What the harness still lacks for full automation

- `CompileToDFIRCPP` dumps the **block diagram only** (the call graph
  comes from the embedded SubVI PathRef links; the callee's own dump
  is a separate run). No FP/connector-pane dump - use `getNode` for
  signatures.
- No automatic code EMITTER yet: translation is done by the agent
  reading the JSON. A future `dfir2py`/`dfir2cpp` generator could
  emit skeletons from the topological order (candidates: new
  `mcp-labview/scripts/lv_dfir_gen.py`).
- FP-only values (control defaults changed at runtime, not saved) are
  invisible to the blob - use arrread cycle fixtures instead (they
  capture runtime behavior, which is the better contract anyway).

## Quick reference

- Regenerate a dump (7 args!):
  `cscript //nologo _service/tmp/lv_gw_call.vbs "C:\LabView skill\gateway\Gateway.vi" CompileToDFIRCPP <vi> <name> <indent> "" <out.cpp>`
- Parse to JSON: `python mcp-labview/scripts/lv_dfir.py <out.cpp> -o <out>.json`
- Fixtures/regressions: `_service/tmp/sr_golden.cpp|.json`,
  `_service/tmp/bdtest_demo.cpp|.json` (case-structure coverage),
  `_service/tmp/pi_golden3.cpp` (feedback nodes, Select, comparison +
  random primitives), `_service/tmp/caller2.cpp` (SubVI PathRef link).
- Golden-run a VI: `arrread` tool, `cycle` mode.
- Connector-pane signature: `gateway getNode` with vi_path = plain
  `.vi` path (Mode B / 'terms' + connector listing).
