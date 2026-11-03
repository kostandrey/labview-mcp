# Continuous2D moco — Python port

Python conversion of the LabVIEW application **Continuous2D moco.vi**
(MotConCon project, "Translating Sample Holder"): two coupled motors
move a sample along a scan pattern. The firmware executes every
pattern; this app configures the pattern parameters and monitors.

## Run

```
python main.py
```

Requires: Python 3.10+, tkinter, and the **UFS ComPortService**
(`ComPortServer.exe`) running and configured for the controller's COM
port. Nothing else — the stepv2 protocol client is vendored under
`stepv2/` (copied from `UFS Commons\COM_PortService\StepV2Config`,
keep in sync with that package).

## What is reused vs re-implemented

| Original (LabVIEW) | Here |
|---|---|
| ComShared.lvlib_SharedCOM / Remote_UDP + RSt_* frame builders + CRC | `stepv2/` (transport, protocol, commands) — **reused** |
| `Convert UI to prog contour.vi` + `ConvertMotionParams.vi` | `moco/patterns.py` (`convert_motion_params`) |
| `Default ini.vi` / `Write INI.vi` (settings.ini) | `moco/config.py` (same keys/sections) |
| `Get Move status moco.vi` composite | `TshController.status()` |
| Main VI queued state machine + tabs Init/Params/Moving | `moco/ui.py` + `TshController` worker thread |
| Localhost remote-control UDP channel (ports 61556-61558) | not ported (out of simplified scope) |

## Simplified scope (per project decision)

* **Only the StepV2 motor controller** — every other controller type of
  the original is deprecated and not ported.
* **Only the UDP transport via ComPortService** — no VISA/direct serial.
* **All patterns run in the firmware** (TSH group commands 134/136/138/
  142/150/151); the app only sends the parameter set and polls status.

## UI ↔ original front panel

* **Init** tab: discovery + connect, sketch/board info, homing on startup.
* **Params** tab: Pattern (Random/Oval/Raster/Only X/Only Y/CrM-1axis),
  Contour Limits (Shift=horizontal shift, Width, Lift=vertical shift,
  Height, R step, Oval %), Speed; "Go Initial!" (= `tsh_go_pos(x0,y0)`),
  "GO!" (= store + `tsh_start`, cmd 134), Stop; pattern preview canvas.
* **Moving** tab: Pause/Resume, Change path, Stop, go-to X/Y, live trace.
* Status bar: Current Position X/Y, Message, error indicator.

## Faithfulness notes (differences that matter)

1. **"Set Current" is not ported** — in the original revision the
   `!SetCurr` button is not wired to anything (verified); the nearest
   mechanisms are homing-time reset and the external Move command.
2. **Pause is app-side only** — the firmware has no pause: stop wipes
   the pattern state, so Resume restarts the pattern from (x0, y0),
   exactly like the original engine did.
3. **CrM-1axis bug fixed** — the original casts UI pattern 5 into a
   4-item enum (out of range at runtime); here it maps explicitly to
   firmware mode 4.
4. `to_end_x/to_end_y` in the payload are early-trigger tolerances,
   not bounds (firmware `motor.Done(toEnd)`); kept identical to the
   original `ConvertMotionParams.vi` formulas.
5. Raster mode ignores `step_x` in the firmware (`stepX := x1-x0`);
   `R_step` effectively sets the Y line pitch.

## Layout

```
main.py            entry point
stepv2/            vendored StepV2 client (protocol/transport/commands)
moco/
  patterns.py      UI contour -> tsh_start payload (ConvertMotionParams)
  config.py        settings.ini (same keys as the original)
  controller.py    TshController: worker thread + Device facade
  ui.py            tkinter tabs Init/Params/Moving
tests/test_patterns.py   mapping regression tests (no hardware)
```

## Not yet ported (follow-ups)

* Jog via keyboard/remote keys (original: UFS Key Combination + arrow keys)
* Remote-control UDP server (auto-reply cache, external Move commands)
* History counters (HistoryN Raster/Oval/Random/CrM1Ax) persistence
* Multi-group support (the original keeps several group slots)
