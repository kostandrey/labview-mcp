"""settings.ini handling - mirrors the keys of the original
'Default ini.vi' / 'Write INI.vi' (MotionControl settings.ini).

[General]    Name, Step, History.{Raster,Oval,Random,CrM1Ax},
             Disabled.{...}, Controller, Homing on startup
[Limits]     Horizontal, Vertical, Speed
[Defaults]   Speed, Contour.{Width,Height,Shift,Lift,R_step,Oval,Pattern}
[ArduinoID]  COM (VISA name or COMx), Address, Group
"""
from __future__ import annotations

import configparser
import os
from dataclasses import dataclass, field
from pathlib import Path

from .patterns import ContourParams, UiPattern

DEFAULT_FILE_NAME = "settings.ini"


@dataclass
class ArduinoId:
    com: str = ""          # COM port name as configured in ComPortService
    address: int = 1       # StepV2 ADR byte
    group: int = 0         # TSH group slot (GR[] index)


@dataclass
class Limits:
    horizontal: float = 15.0
    vertical: float = 15.0
    speed: float = 5.0


@dataclass
class Settings:
    name: str = "MotionControl"
    step: float = 0.1
    homing_on_startup: bool = False
    history: dict = field(default_factory=lambda: {
        "Raster": 10, "Oval": 10, "Random": 10, "CrM1Ax": 10})
    disabled: dict = field(default_factory=lambda: {
        "Raster": False, "Oval": False, "Random": False,
        "SingleX": False, "SingleY": False, "CrM-1": False})
    limits: Limits = field(default_factory=Limits)
    defaults_speed: float = 1.0
    defaults_contour: ContourParams = field(default_factory=ContourParams)
    arduino: ArduinoId = field(default_factory=ArduinoId)

    # ------------------------------------------------------------------
    @classmethod
    def load(cls, path: str | os.PathLike | None = None) -> "Settings":
        path = Path(path) if path else _default_path()
        s = cls()
        if not path.is_file():
            return s
        cp = configparser.ConfigParser()
        cp.read(path, encoding="utf-8")
        g = cp["General"] if cp.has_section("General") else {}
        s.name = g.get("Name", s.name)
        s.step = g.getfloat("Step", fallback=s.step)
        s.homing_on_startup = g.getboolean("Homing on startup",
                                           fallback=s.homing_on_startup)
        for key in s.history:
            s.history[key] = cp.getint("General", "History " + key,
                                       fallback=s.history[key])
        for key in s.disabled:
            s.disabled[key] = cp.getboolean("General", "Disabled " + key,
                                            fallback=s.disabled[key])
        lim = cp["Limits"] if cp.has_section("Limits") else {}
        s.limits.horizontal = lim.getfloat("Horizontal",
                                           fallback=s.limits.horizontal)
        s.limits.vertical = lim.getfloat("Vertical",
                                         fallback=s.limits.vertical)
        s.limits.speed = lim.getfloat("Speed", fallback=s.limits.speed)
        d = cp["Defaults"] if cp.has_section("Defaults") else {}
        s.defaults_speed = d.getfloat("Speed", fallback=s.defaults_speed)
        c = s.defaults_contour
        c.width = d.getfloat("Contour Width", fallback=c.width)
        c.height = d.getfloat("Contour Height", fallback=c.height)
        c.shift = d.getfloat("Contour Shift", fallback=c.shift)
        c.lift = d.getfloat("Contour Lift", fallback=c.lift)
        c.r_step = d.getfloat("Contour R_step", fallback=c.r_step)
        c.oval = d.getfloat("Contour Oval", fallback=c.oval)
        c.pattern = UiPattern(d.getint("Contour Pattern",
                                       fallback=int(c.pattern)))
        a = cp["ArduinoID"] if cp.has_section("ArduinoID") else {}
        s.arduino.com = a.get("COM", s.arduino.com)
        s.arduino.address = a.getint("Address", fallback=s.arduino.address)
        s.arduino.group = a.getint("Group", fallback=s.arduino.group)
        return s

    def save(self, path: str | os.PathLike | None = None) -> None:
        path = Path(path) if path else _default_path()
        cp = configparser.ConfigParser()
        cp["General"] = {
            "Name": self.name,
            "Step": _f(self.step),
            "Homing on startup": str(self.homing_on_startup),
        }
        for key, val in self.history.items():
            cp["General"]["History " + key] = str(val)
        for key, val in self.disabled.items():
            cp["General"]["Disabled " + key] = str(val)
        cp["Limits"] = {
            "Horizontal": _f(self.limits.horizontal),
            "Vertical": _f(self.limits.vertical),
            "Speed": _f(self.limits.speed),
        }
        c = self.defaults_contour
        cp["Defaults"] = {
            "Speed": _f(self.defaults_speed),
            "Contour Width": _f(c.width),
            "Contour Height": _f(c.height),
            "Contour Shift": _f(c.shift),
            "Contour Lift": _f(c.lift),
            "Contour R_step": _f(c.r_step),
            "Contour Oval": _f(c.oval),
            "Contour Pattern": str(int(c.pattern)),
        }
        cp["ArduinoID"] = {
            "COM": self.arduino.com,
            "Address": str(self.arduino.address),
            "Group": str(self.arduino.group),
        }
        with open(path, "w", encoding="utf-8") as fh:
            cp.write(fh)


def _f(v: float) -> str:
    return repr(float(v))


def _default_path() -> Path:
    return Path(__file__).resolve().parent.parent / DEFAULT_FILE_NAME
