"""Pattern parameter mapping: UI contour fields -> TSH start payload.

Re-implementation of the LabVIEW chain
    Convert UI to prog contour.vi -> ConvertMotionParams.vi -> cmd 134
verified against the v1.34 firmware (TSH_step.ino / L12GroupClass).

The firmware executes every pattern itself; the host only sends
    tsh_start(slot, mode, x0, y0, x1, y1,
              step_x, step_y, to_end_x, to_end_y, speed_x, speed_y)
(mode byte + 10 little-endian f32).

Firmware semantics worth knowing (TSH_step.ino, L12GroupClass):
  * mode 1 raster: step_x is IGNORED (stepX := x1-x0); step_y = line pitch
  * mode 2 random: step_x/step_y = MINIMUM DISTANCE between successive
    random points (100-retry guard)
  * mode 3 "Oval": rectangular PERIMETER traversal of the bounds, not an
    ellipse; "Only X"/"Only Y" are degenerate single-axis cases
  * mode 4 CrM: one motor driven pseudo-infinitely; X bounds unused
  * to_end_x/to_end_y are NOT bounds - they are distance tolerances for
    early next-segment triggering (motor.Done(toEnd))
  * start is idempotent-guarded: a Start while already moving is dropped
  * there is no firmware pause: tsh_stop wipes state, the next start
    re-moves to (x0, y0) and restarts the pattern from the beginning
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class UiPattern(IntEnum):
    """Items of the UI 'Pattern type moco UI' enum, in order."""

    RANDOM = 0
    OVAL = 1
    RASTER = 2
    ONLY_X = 3
    ONLY_Y = 4
    CRM_1AXIS = 5


class FirmwareMode(IntEnum):
    """moveMode values of the firmware (groups.py CONTOUR_MODES)."""

    NONE = 0
    SCANNING = 1  # raster
    RANDOM = 2
    OVAL = 3      # rectangular perimeter (also the Only-X / Only-Y carrier)
    CRM_1AXIS = 4


def firmware_mode(pattern: UiPattern) -> FirmwareMode:
    """UI pattern -> firmware moveMode.

    The original LabVIEW has a bug here: 'CrM-1axis' (UI 5) is cast
    unchanged into a 4-item internal enum (out of range at runtime).
    We map it explicitly instead (agent-verified intent: mode 4).
    """
    if pattern == UiPattern.RANDOM:
        return FirmwareMode.RANDOM
    if pattern == UiPattern.OVAL:
        return FirmwareMode.OVAL
    if pattern == UiPattern.RASTER:
        return FirmwareMode.SCANNING
    if pattern in (UiPattern.ONLY_X, UiPattern.ONLY_Y):
        return FirmwareMode.OVAL  # degenerate 1-D cases
    if pattern == UiPattern.CRM_1AXIS:
        return FirmwareMode.CRM_1AXIS
    raise ValueError(f"unknown pattern {pattern!r}")


@dataclass
class ContourParams:
    """The 'Contour Limits, mm' cluster of the original Params tab."""

    shift: float = 0.0        # 'Horizontal shift' -> contour left edge
    width: float = 10.0       # 'Area width'
    lift: float = 0.0         # 'Vertical shift' -> contour top edge
    height: float = 10.0      # 'Area height'
    r_step: float = 1.0       # raster line pitch (UI label 'R step')
    oval: float = 50.0        # percent, feeds to_end for oval/CrM
    pattern: UiPattern = UiPattern.RASTER

    def normalized(self) -> "ContourParams":
        """Apply the Only-X / Only-Y degenerations (UI side, as the
        original 'Convert UI to prog contour.vi' frames do)."""
        p = ContourParams(**self.__dict__)
        if p.pattern == UiPattern.ONLY_X:
            p.height = 0.0
            p.oval = 0.0
        elif p.pattern == UiPattern.ONLY_Y:
            p.width = 0.0
            p.oval = 0.0
        return p


@dataclass
class TshStartArgs:
    """Exactly the argument list of stepv2 Device.tsh_start."""

    mode: int
    x0: float
    y0: float
    x1: float
    y1: float
    step_x: float
    step_y: float
    to_end_x: float
    to_end_y: float
    speed_x: float
    speed_y: float


def convert_motion_params(contour: ContourParams, speed: float,
                          speed_limit: float | None = None) -> TshStartArgs:
    """ConvertMotionParams.vi equivalent.

    speed is clamped to speed_limit exactly like the original
    (Speed := min(Limits.Speed, Speed) at init; the clamped value is
    what reaches the payload).
    """
    if speed_limit is not None:
        speed = min(speed, speed_limit)
    c = contour.normalized()
    mode = firmware_mode(c.pattern)

    x0, x1 = c.shift, c.shift + c.width
    y0, y1 = c.lift, c.lift + c.height

    if mode == FirmwareMode.SCANNING:            # raster
        step_x = step_y = c.r_step
        to_end_x = to_end_y = 0.3 * c.r_step
    elif mode == FirmwareMode.RANDOM:            # min spacing between points
        step_x = 0.3 * c.width / 10.0
        step_y = 0.3 * c.height / 10.0
        to_end_x = c.width / 10.0
        to_end_y = c.height / 10.0
    else:                                        # oval perimeter / CrM
        step_x = step_y = 0.0
        to_end_x = c.width * c.oval / 100.0
        to_end_y = c.height * c.oval / 100.0

    return TshStartArgs(mode=int(mode), x0=x0, y0=y0, x1=x1, y1=y1,
                        step_x=step_x, step_y=step_y,
                        to_end_x=to_end_x, to_end_y=to_end_y,
                        speed_x=speed, speed_y=speed)
