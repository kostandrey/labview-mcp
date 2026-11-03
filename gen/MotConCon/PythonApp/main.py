"""Continuous2D moco - Python port of the UFS 'Translating Sample Holder'
control application (LabVIEW project MotConCon, main VI Continuous2D moco.vi).

Scope (simplified vs the original):
  * only the StepV2 motor controller (all other controller types deprecated)
  * only the UDP transport via the UFS ComPortService
    (ComPortServer.exe, one UDP port per COM device)
  * all scan patterns are executed by the controller firmware
    (TSH groups, cmd 134 Start / 136 Stop / 138 pos / 142 go / 151 home);
    the application only configures the pattern parameters and monitors
  * the localhost remote-control UDP channel of the original is not
    ported (add later if the UFS remote GUI must drive this app)

Run:  python main.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from moco.config import Settings
from moco.ui import run_app


def main() -> int:
    settings = Settings.load()
    return run_app(settings)


if __name__ == "__main__":
    sys.exit(main())
