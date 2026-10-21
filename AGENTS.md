# Project context - read this FIRST in every new session

## What this project actually is

This project builds an **AI assistant for LabVIEW programming**. It is NOT
a LabVIEW application repository, and its goal is not any single VI.

The product being developed is the *harness*:

- `mcp-labview/` - the MCP server (tools the agent calls from Zed),
- `gateway/Gateway.vi` (+ subVIs) - the VI Scripting workhorse the server
  drives over COM,
- `skill-labview-code/` - the accumulated, **verified** knowledge base
  (SKILL.md rules, gateway-recipe.md version history, pane tables, style
  codes, driver scripts),
- `mcp-labview/scripts/` - gateway drivers and composite helpers.

## The exercises rule (most important)

The user gives LabVIEW programming tasks (compute pi by Monte Carlo,
linear fit, histograms, distributions, shift registers, ...). **These are
exercises, not real programming jobs.** Their purpose is to:

1. Find a way to solve the task with the harness - sometimes empirically
   (probe terminals, try wiring, read `wires`/`errors` output), sometimes
   via research (NI docs, vi.lib libraries, CHM decompiles).
2. Convert everything learned into durable improvements so the NEXT
   session solves similar tasks faster and correctly:
   - facts -> `skill-labview-code/references/*` (gateway-recipe.md gets a
     new dated version section; pane tables -> subvi-placement.md),
   - recurring operations -> composite scripts in `mcp-labview/scripts/`
     or new Gateway verbs,
   - new capabilities -> server.py tools + Gateway.vi upgrades.

So when a task is finished, the VI is a byproduct. **The knowledge,
tools and skill updates are the deliverable.** Finished exercise VIs in
`gen/` (pi_golden*, sr_golden) serve as golden examples / regression
material - do not treat them as junk, but do not treat them as the point.

## Session start checklist

1. Read this file, then `skill-labview-code/SKILL.md` and the TAIL of
   `skill-labview-code/references/gateway-recipe.md` (recent version
   sections hold the current truth; older sections may be outdated).
2. Verify the MCP server is current: `mcp-labview/server.py` matches the
   latest committed version; after ANY tool-definition edit run
   `python mcp-labview/scripts/validate_tools.py` (one malformed tool
   description makes strict clients like Zed drop ALL tools), and the
   user may need to restart the MCP server / Zed.
3. Grep the knowledge base BEFORE empirically rediscovering anything
   (terminal orders, style codes, gotchas are already recorded). Fast
   path: `python mcp-labview/scripts/lv_knowledge.py <query>` or the
   MCP `lv_reference` tool (structured terminal maps, pane tables,
   wire kinds, rep codes); grep the prose docs for everything else.

## Hard rules learned so far (details in SKILL.md)

- Work on a COPY for development/testing/debugging; apply to the user's
  original VI only after the script is verified. (Working in the user's
  live LabVIEW instance via COM is standard and expected - edits appear
  in the IDE and are saved to disk.)
- `wire ok` does NOT mean connected: check `wires` (broken flags,
  isSource, Names) and the `errors` verb (empty = VI clean).
- `search_docs`/`read_doc` cover primitives; for vi.lib subVIs extract
  the POLYMORPHIC PARENT with lv_extract2 (its HELP_PATH/HELP_TAG name
  the CHM page); online ni.com pages are JS shells for fetch.
- VBS scripts: `'` comments, case-insensitive Dim names, no `IIf`.

## Updating this file

Keep it SHORT - details belong in the skill references. Update it when
the component map, the working rules, or the workflow changes (new major
tool, new rule, changed session protocol). Otherwise do not touch it.
