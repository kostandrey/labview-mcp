"""Regression tests for the ConvertMotionParams mapping (no hardware)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from moco.patterns import (ContourParams, UiPattern, convert_motion_params,
                           firmware_mode)

fails = []


def check(name, got, want, tol=1e-6):
    ok = (abs(got - want) <= tol) if isinstance(want, float) else got == want
    if not ok:
        fails.append(f"{name}: got {got!r}, want {want!r}")


# mode mapping (UI enum -> firmware moveMode)
for ui, fw in [(UiPattern.RANDOM, 2), (UiPattern.OVAL, 3),
               (UiPattern.RASTER, 1), (UiPattern.ONLY_X, 3),
               (UiPattern.ONLY_Y, 3), (UiPattern.CRM_1AXIS, 4)]:
    check(f"mode {ui.name}", firmware_mode(ui), fw)

# raster: x0=Shift, x1=Shift+Width, y0=Lift, y1=Lift+Height,
#         step= R_step, to_end=0.3*R_step, speed clamped
a = convert_motion_params(
    ContourParams(shift=1.0, width=10.0, lift=2.0, height=5.0,
                  r_step=0.5, oval=50, pattern=UiPattern.RASTER),
    speed=3.0, speed_limit=2.0)
check("raster mode", a.mode, 1)
check("raster x0", a.x0, 1.0)
check("raster x1", a.x1, 11.0)
check("raster y0", a.y0, 2.0)
check("raster y1", a.y1, 7.0)
check("raster step_x", a.step_x, 0.5)
check("raster step_y", a.step_y, 0.5)
check("raster to_end_x", a.to_end_x, 0.15)
check("raster to_end_y", a.to_end_y, 0.15)
check("raster speed clamp", a.speed_x, 2.0)
check("raster speed_y", a.speed_y, 2.0)

# random: step=0.3*dim/10, to_end=dim/10
b = convert_motion_params(
    ContourParams(shift=0, width=10.0, lift=0, height=5.0,
                  r_step=1, oval=50, pattern=UiPattern.RANDOM),
    speed=1.0, speed_limit=None)
check("random mode", b.mode, 2)
check("random step_x", b.step_x, 0.3 * 10.0 / 10.0)
check("random step_y", b.step_y, 0.3 * 5.0 / 10.0)
check("random to_end_x", b.to_end_x, 1.0)
check("random to_end_y", b.to_end_y, 0.5)

# oval: step=0, to_end=dim*oval/100
c = convert_motion_params(
    ContourParams(shift=0, width=10.0, lift=0, height=5.0,
                  r_step=1, oval=50, pattern=UiPattern.OVAL),
    speed=1.0)
check("oval mode", c.mode, 3)
check("oval step_x", c.step_x, 0.0)
check("oval to_end_x", c.to_end_x, 5.0)
check("oval to_end_y", c.to_end_y, 2.5)

# Only X: height and oval zeroed (degenerate 1-D)
d = convert_motion_params(
    ContourParams(shift=0, width=10.0, lift=0, height=5.0,
                  r_step=1, oval=50, pattern=UiPattern.ONLY_X),
    speed=1.0)
check("onlyx mode", d.mode, 3)
check("onlyx y1", d.y1, 0.0)
check("onlyx to_end_y", d.to_end_y, 0.0)

# Only Y: width and oval zeroed
e = convert_motion_params(
    ContourParams(shift=0, width=10.0, lift=0, height=5.0,
                  r_step=1, oval=50, pattern=UiPattern.ONLY_Y),
    speed=1.0)
check("onlyy x1", e.x1, 0.0)

# CrM-1axis: explicit mode 4 (fixing the original's out-of-range bug)
f = convert_motion_params(
    ContourParams(pattern=UiPattern.CRM_1AXIS), speed=1.0)
check("crm mode", f.mode, 4)

if fails:
    print("FAILED %d checks:" % len(fails))
    for f_ in fails:
        print(" -", f_)
    sys.exit(1)
print("all pattern-mapping checks passed")
