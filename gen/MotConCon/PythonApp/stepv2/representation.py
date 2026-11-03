"""Representation of the efficient motor current (Imax / Irms) display.

Mirrors the LabView "TMC current" VI of Configure StepV2: given the firmware
channel-type code (cmd 171), the unpacked TMC motorCurrent fields, the sense
resistor and the external Vref, returns the Imax / Irms strings shown in the
Motor configuration tab.

TMC2208/2209 (channel types 2, 6, 7):
  internal reference (ref_src = True):
      Imax = (IRUN + 1) / (32 * (Rs + 0.02)),  Vref = 0.32 V or 0.18 V
  external reference (ref_src = False):
      Imax = Vref * 0.325 / ((Rs + 0.02) * 2.5 * 32) * (IRUN + 1)
  Irms = Imax / sqrt(2)

Type 6 (TMC-uart) uses the motorCurrent byte fields as entered.
Types 2 and 7 (standalone) force ref_src = False, int_val = False,
IRUN = 31: the current is set by the Vref pin only.

Type 1 (DRV8825) sets the current by Vref only: Imax = 2 * Vref.
Any other channel type reports "Not known".
"""

from __future__ import annotations

import math

#: default sense resistor in Ohm, as used by the LabView tool
DEFAULT_R_SENSE = 0.110
#: text shown when the current cannot be computed for a channel type
NOT_KNOWN = "Not known"

_TMC_UART = 6
_TMC_STANDALONE = (2, 7)
_DRV8825 = 1


def _vref_labels(coef: float, vref: float) -> tuple[str, str]:
    """Labels for a driver whose Imax is a fixed multiple of Vref."""
    if math.isnan(vref):
        return ("(Vref(V) * %.3f) A" % coef,
                "(Vref(V) * %.3f) A" % (coef / math.sqrt(2)))
    return ("%.3f A" % (coef * vref),
            "%.3f A" % (coef * vref / math.sqrt(2)))


def current_labels(channel_type: int | None, ref_src: bool, int_val: bool,
                   irun: int, r_sense: float = DEFAULT_R_SENSE,
                   vref: float = float("nan")) -> tuple[str, str]:
    """Return the (Imax, Irms) display strings for a motor channel.

    channel_type is the cmd-171 code; ref_src / int_val / irun are the
    unpacked motorCurrent byte fields; r_sense is in Ohm and vref in volts
    (NaN when the user has not set it).
    """
    if channel_type == _TMC_UART:
        pass  # all parameters as entered
    elif channel_type in _TMC_STANDALONE:
        # standalone TMC: current is set by the Vref pin, IRUN is at maximum
        ref_src = False
        int_val = False
        irun = 31
    elif channel_type == _DRV8825:
        return _vref_labels(2.0, vref)
    else:
        return NOT_KNOWN, NOT_KNOWN

    rs = r_sense + 0.02
    if ref_src:
        imax_coef = (irun + 1) / (32.0 * rs)
        vref_used = 0.18 if int_val else 0.32
    else:
        imax_coef = 0.325 / (rs * 2.5 * 32.0) * (irun + 1)
        vref_used = vref
    return _vref_labels(imax_coef, vref_used)
