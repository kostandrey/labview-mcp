"""Read/write LabVIEW-style Step-V2 motor settings ini files.

Files live in ``%ProgramData%\\Ultrafast Systems\\Hardware\\Step-V2``:
``settings.ini`` (shown as "Default") and ``<name>_settings.ini``
(e.g. ``OPA_settings.ini`` is shown as "OPA").  All values are quoted
strings; ``Boards.<size(s)>`` / ``Boards i.Axii.<size(s)>`` hold the
board / channel counts:

    [Settings]
    Boards.<size(s)>="2"
    Boards 0.COM="udp://127.0.0.1:50001"
    Boards 0.Axii.<size(s)>="1"
    Boards 0.Axii 0.Axis="0"
    Boards 0.Axii 0.Name="FSS_testStage"
    Boards 0.Axii 0.LastPos="0"
    Boards 0.Axii 0.Home="Never"
    Boards 0.Axii 0.HomeMoves="0"
    Boards 0.Axii 0.Hold="FALSE"
    Boards 0.Axii 0.Zero="0"
    Boards 0.Adrs="0"
    Boards 0.Times.InitDelay="3"
    Boards 0.Times.Home="30"
    Boards 0.Times.Move="10"
    Boards 0.IDdate=""

This module is pure logic (no tkinter) so it can be unit-tested offline.
"""

from __future__ import annotations

import configparser
import os
import re

SECTION = "Settings"
_BOARD_KEY = re.compile(r"^Boards(\s|\.)")


def default_dir() -> str:
    return os.path.join(os.environ.get("PROGRAMDATA", ""),
                        "Ultrafast Systems", "Hardware", "Step-V2")


def list_ini_files(directory: str | None = None) -> list[tuple[str, str]]:
    """``[(display name, full path)]`` for the known ini files.

    ``settings.ini`` is displayed as "Default"; ``<name>_settings.ini``
    as ``<name>``.
    """
    directory = directory or default_dir()
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return []
    out = []
    for name in names:
        low = name.lower()
        if not low.endswith(".ini"):
            continue
        if low == "settings.ini":
            out.append(("Default", os.path.join(directory, name)))
        elif low.endswith("_settings.ini"):
            out.append((name[:-len("_settings.ini")],
                        os.path.join(directory, name)))
        else:
            out.append((name[:-4], os.path.join(directory, name)))
    return out


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def parse_file(path: str) -> tuple[list[dict], dict[str, str]]:
    """Parse a settings ini.

    Returns ``(boards, extra)`` where *extra* holds unknown settings keys
    so they survive a load/modify/save round trip.  Board dicts:
    ``com, adrs, iddate, init, home_t, move_t, channels``; channel dicts:
    ``axis, name, last, home, moves, hold (bool), zero`` (numbers kept as
    raw strings for round-trip fidelity).
    """
    cp = configparser.ConfigParser(interpolation=None)
    cp.optionxform = str  # keep key case (LabView keys are mixed-case)
    cp.read(path, encoding="utf-8")
    sec = cp[SECTION] if cp.has_section(SECTION) else {}

    def getv(key: str, default: str = "") -> str:
        try:
            return _unquote(sec[key])
        except (KeyError, TypeError):
            return default

    try:
        n_boards = int(_unquote(sec["Boards.<size(s)>"]))
    except (KeyError, TypeError, ValueError):
        n_boards = 0

    boards = []
    for i in range(n_boards):
        board = {
            "com": getv(f"Boards {i}.COM"),
            "adrs": getv(f"Boards {i}.Adrs", "0"),
            "iddate": getv(f"Boards {i}.IDdate"),
            "init": getv(f"Boards {i}.Times.InitDelay", "3"),
            "home_t": getv(f"Boards {i}.Times.Home", "30"),
            "move_t": getv(f"Boards {i}.Times.Move", "10"),
            "channels": [],
        }
        try:
            n_ch = int(_unquote(sec[f"Boards {i}.Axii.<size(s)>"]))
        except (KeyError, TypeError, ValueError):
            n_ch = 0
        # tolerate the LabView quirk where <size(s)> is smaller than the
        # number of Axii j keys actually present in the file
        while f"Boards {i}.Axii {n_ch}.Axis" in sec:
            n_ch += 1
        for j in range(n_ch):
            board["channels"].append({
                "axis": getv(f"Boards {i}.Axii {j}.Axis", str(j)),
                "name": getv(f"Boards {i}.Axii {j}.Name"),
                "last": getv(f"Boards {i}.Axii {j}.LastPos", "0"),
                "home": getv(f"Boards {i}.Axii {j}.Home", "Never"),
                "moves": getv(f"Boards {i}.Axii {j}.HomeMoves", "0"),
                "hold": getv(f"Boards {i}.Axii {j}.Hold",
                             "FALSE").upper() == "TRUE",
                "zero": getv(f"Boards {i}.Axii {j}.Zero", "0"),
            })
        boards.append(board)

    extra = {key: _unquote(value) for key, value in sec.items()
             if not _BOARD_KEY.match(key)}
    return boards, extra


def write_file(path: str, boards: list[dict],
               extra: dict[str, str] | None = None) -> None:
    """Write boards in the exact LabView key layout."""
    lines = [f"[{SECTION}]", f"Boards.<size(s)>=\"{len(boards)}\""]
    for i, board in enumerate(boards):
        channels = board["channels"]
        lines.append(f"Boards {i}.COM=\"{board['com']}\"")
        lines.append(f"Boards {i}.Axii.<size(s)>=\"{len(channels)}\"")
        for j, ch in enumerate(channels):
            lines.append(f"Boards {i}.Axii {j}.Axis=\"{ch['axis']}\"")
            lines.append(f"Boards {i}.Axii {j}.Name=\"{ch['name']}\"")
            lines.append(f"Boards {i}.Axii {j}.LastPos=\"{ch['last']}\"")
            lines.append(f"Boards {i}.Axii {j}.Home=\"{ch['home']}\"")
            lines.append(f"Boards {i}.Axii {j}.HomeMoves=\"{ch['moves']}\"")
            lines.append(f"Boards {i}.Axii {j}.Hold="
                         f"\"{'TRUE' if ch['hold'] else 'FALSE'}\"")
            lines.append(f"Boards {i}.Axii {j}.Zero=\"{ch['zero']}\"")
        lines.append(f"Boards {i}.Adrs=\"{board['adrs']}\"")
        lines.append(f"Boards {i}.Times.InitDelay=\"{board['init']}\"")
        lines.append(f"Boards {i}.Times.Home=\"{board['home_t']}\"")
        lines.append(f"Boards {i}.Times.Move=\"{board['move_t']}\"")
        lines.append(f"Boards {i}.IDdate=\"{board['iddate']}\"")
    for key, value in sorted((extra or {}).items()):
        lines.append(f"{key}=\"{value}\"")
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
