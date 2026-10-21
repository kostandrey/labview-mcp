# read-block-diagram skill (vendored in this repo)

This is the CANONICAL copy of the `read-block-diagram` Zed agent skill
(describes a LabVIEW block diagram image in plain text, verified against
documentation). It lives in the repo so it is versioned with the project and
distributed to every PC via `git pull`.

## Install on a PC (one command)

Zed reads global agent skills from `%USERPROFILE%\.agents\skills\<name>`.
Point that folder at this directory with a junction (same path works on both
project PCs since the repo lives at `C:\LabView skill`):

```bat
rmdir "%USERPROFILE%\.agents\skills\read-block-diagram"
mklink /J "%USERPROFILE%\.agents\skills\read-block-diagram" "C:\LabView skill\skill-labview-code\skills\read-block-diagram"
```

(A junction is a directory link; no admin rights required. If the folder does
not exist yet, skip the rmdir.)

After `git pull`, the junction makes the update visible to Zed immediately
(restart the agent panel if the skill content is cached).

## Canonical-content rules

- Edit the skill **only here** (this directory) and commit - never in
  `~\.agents\skills` (that is a link into the repo; editing it edits the repo,
  which is fine, but changes must be committed to reach the other PC).
- `scripts\lv_extract2.vbs` and `scripts\crop.ps1` are kept in sync with
  `mcp-labview\scripts\` (currently identical copies; re-diff after gateway
  tool changes).
- `references\labview-automation.md` is the same document as
  `..\..\references\labview-automation.md` (the knowledge base holds the
  newest revision); re-copy after edits to the KB version.
