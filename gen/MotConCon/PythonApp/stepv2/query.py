"""Universal table-validated query layer for the ArduinoStepV2 host protocol.

One entry point for every host command:

    q = Querier(conn, adr=1)                # conn: ComPortService endpoint
    data = q(106, u32(600), channel=3)      # cmd 106 "setSpeed", channel 3
    data = q(96, channel=0)                 # cmd 96 "GetContParam" read

    * `channel` is the packet CH byte - the motor/channel number for channel
      commands, the group slot for group config commands, the MC index for
      monochromators, the object ordinal for shutters/sensors/joysticks.
    * `adr` is the device address (the packet ADR byte), changeable via
      `q.adr = ...`.

Every query is validated against the COMMANDS table:

    * the command code must be known,
    * the write data length must equal the table's write size,
    * the reply data length must equal the table's read size.

Device rejection (replied command 0xFE), a non-echoed command/channel or a
stale Request-ID raise CommandRejected; validation failures raise QueryError.
Timeouts / offline endpoints propagate the transport exceptions after the
configured number of attempts (each retry uses a fresh Request-ID).

This module depends only on `protocol` and `transport`, so it can be reused
as-is in any project that talks to the 12-channel board.

Command table provenance: legacy LabView "Configure StepV2" table, corrected
against the v1.34 sketch (TSHDevice.cpp / Motor.cpp / Monochromator.cpp /
L12GroupClass.cpp / Shutter.cpp / slowChopper.cpp / PosSensor.cpp /
Joystick.cpp).  Corrections vs the legacy table are noted per row; the
sketch's `replyLength` convention is LEN = 3 + reply DATA bytes.
"""

from __future__ import annotations

from typing import NamedTuple

from . import protocol as p
from .transport import ComPortService, DeviceOffline, TimeoutError_

__all__ = [
    "CommandSpec", "COMMANDS", "spec", "command_name", "all_commands",
    "validate_write", "validate_read", "Querier", "QueryError",
    "CommandRejected",
]


class QueryError(Exception):
    """Table/validation failure (unknown code, wrong write or read size)."""

    def __init__(self, message: str, code: int | None = None,
                 ch: int | None = None):
        self.code = code
        self.ch = ch
        super().__init__(message)


class CommandRejected(QueryError):
    """Device replied 0xFE, or the reply did not echo cmd/ch/Request-ID."""


class CommandSpec(NamedTuple):
    code: int          # command byte
    name: str          # name from the legacy LabView table
    write: int         # expected write DATA size in bytes
    read: int          # expected reply DATA size in bytes
    note: str = ""     # deviations / remarks


# ---------------------------------------------------------------------------
# The command table: code -> (name, write DATA size, read DATA size)
# ---------------------------------------------------------------------------

COMMANDS: dict[int, CommandSpec] = {
    # --- SDG board (board 13) ---------------------------------------------
    80: CommandSpec(80, "SDG:GetMCO2", 0, 14),
    81: CommandSpec(81, "SDG:SetMCO2", 14, 0),
    82: CommandSpec(82, "SDG:GetTrigLevel", 1, 5),
    83: CommandSpec(83, "SDG:SetTrigLevel", 5, 0),
    84: CommandSpec(84, "SDG:Enable", 1, 0),
    85: CommandSpec(85, "SDG:GetStatus", 0, 25),
    86: CommandSpec(86, "SDG:GetDelay", 0, 6),
    87: CommandSpec(87, "SDG:SetAnalogD", 2, 0),
    88: CommandSpec(88, "SDG:SetDigitalD", 4, 0),
    89: CommandSpec(89, "SDG:SetPeriod", 4, 0),
    # --- Motor family (Motor / Stepper / TMCUart / TitanMot) ---------------
    90: CommandSpec(90, "SetCustomPins", 4, 0),
    92: CommandSpec(92, "getPins", 0, 4),
    94: CommandSpec(94, "setControllerPar", 5, 0,
                    "legacy table said write 3; v1.34 writes 5 bytes "
                    "(bitParams, enablePin, motorsNum, groupNum, adr)"),
    96: CommandSpec(96, "GetContParam", 0, 5,
                    "legacy table said read 3; v1.34 replies 5 bytes"),
    99: CommandSpec(99, "homeStart2", 0, 0),
    100: CommandSpec(100, "homeStart", 1, 0),
    101: CommandSpec(101, "homeStatus", 0, 5),
    102: CommandSpec(102, "GetUploadTime", 0, 20),
    103: CommandSpec(103, "setTMC", 2, 0),
    104: CommandSpec(104, "TMCuartRequest", 8, 0),
    105: CommandSpec(105, "getTMC", 0, 2),
    106: CommandSpec(106, "setSpeed", 4, 0),
    107: CommandSpec(107, "uartMove", 4, 0),
    108: CommandSpec(108, "moveAbs", 4, 0),
    109: CommandSpec(109, "setAdvanced", 8, 0),
    110: CommandSpec(110, "getPos", 0, 5),
    111: CommandSpec(111, "getAdvanced", 0, 8),
    112: CommandSpec(112, "moveStop", 0, 0),
    113: CommandSpec(113, "TMCuartReply", 0, 12),
    114: CommandSpec(114, "setBacklash", 4, 0),
    115: CommandSpec(115, "analogRead", 0, 4),
    116: CommandSpec(116, "getHomeRes", 0, 4),
    # --- Monochromator (CH = MC index) --------------------------------------
    117: CommandSpec(117, "setMCmode", 1, 0),
    118: CommandSpec(118, "setEnable", 1, 0),
    119: CommandSpec(119, "setDisable", 1, 0),
    120: CommandSpec(120, "testParam", 1, 4),
    121: CommandSpec(121, "getMCstatus", 0, 28,
                     "legacy table said read 29; "
                     "sizeof(MonochromatorStatus) = 28"),
    122: CommandSpec(122, "setAcceleration", 4, 0),
    123: CommandSpec(123, "setMCwave", 4, 0),
    124: CommandSpec(124, "setStepVal", 4, 0),
    125: CommandSpec(125, "reinitMC", 0, 0),
    126: CommandSpec(126, "setHomePos", 4, 0),
    128: CommandSpec(128, "setScaleMax", 4, 0),
    130: CommandSpec(130, "setMicrosteps", 1, 0),
    131: CommandSpec(131, "SetFrequency", 4, 4, "FreqGen board"),
    132: CommandSpec(132, "AttachMotors", 2, 0),
    133: CommandSpec(133, "ConfigGroup", 3, 0),
    134: CommandSpec(134, "StartGroup", 41, 0),
    136: CommandSpec(136, "StopGroup", 0, 0),
    138: CommandSpec(138, "GetGroupPosition", 0, 8),
    140: CommandSpec(140, "setMotorParams", 1, 0),
    142: CommandSpec(142, "GoGroup", 8, 0),
    144: CommandSpec(144, "getMotorConfig", 0, 38),
    146: CommandSpec(146, "setHomeSpeeds", 8, 0,
                     "legacy table listed code 145; v1.34 uses 146"),
    148: CommandSpec(148, "GetGroupMotors", 0, 2),
    149: CommandSpec(149, "GetGroupConfig", 0, 3),
    150: CommandSpec(150, "GetGroupContour", 0, 41),
    151: CommandSpec(151, "GroupHoming", 0, 0),
    152: CommandSpec(152, "SetScaleMin", 4, 0),
    # --- EEPROM / device ----------------------------------------------------
    154: CommandSpec(154, "SaveEPROM", 1, 32,
                     "32-byte page read (firmware comment: ReadEEPROM)"),
    155: CommandSpec(155, "OpenEEPROM", 33, 0,
                     "32-byte page write (page byte + 32 data)"),
    156: CommandSpec(156, "ResetContr", 0, 0),
    158: CommandSpec(158, "ChopSetPID", 12, 0),
    159: CommandSpec(159, "Chop:GetPID", 0, 12),
    160: CommandSpec(160, "ConfigShutter", 6, 0),
    161: CommandSpec(161, "GetShutterConfig", 0, 6),
    162: CommandSpec(162, "ControlShutter", 1, 0),
    163: CommandSpec(163, "GetShutterCurrent", 0, 2),
    164: CommandSpec(164, "ChopSetDefaults", 1, 0),
    165: CommandSpec(165, "ChopSetDiv", 3, 0),
    166: CommandSpec(166, "ChopReadFreq", 0, 8),
    167: CommandSpec(167, "ChopSetPhase", 4, 0),
    168: CommandSpec(168, "ChopGetPar", 0, 12),
    169: CommandSpec(169, "ChopSetFreq", 5, 0),
    170: CommandSpec(170, "SetChannelType", 1, 0),
    171: CommandSpec(171, "GetChannelType", 0, 1),
    172: CommandSpec(172, "SetBoardVer", 1, 0),
    173: CommandSpec(173, "GetBoardVer", 0, 1),
    174: CommandSpec(174, "GetSketchVer", 0, 1),
    175: CommandSpec(175, "Chop:setShutter", 17, 0),
    176: CommandSpec(176, "Chop:getShutter", 0, 17),
    177: CommandSpec(177, "Chop:armShutter", 0, 0),
    180: CommandSpec(180, "SetPosSensConfig", 24, 0),
    181: CommandSpec(181, "GetPosSensConfig", 0, 24),
    182: CommandSpec(182, "PosSensorRead", 0, 27),
    183: CommandSpec(183, "PosSensorMeasure", 1, 0,
                     "legacy table said write 0; v1.34 takes a measure/"
                     "stream bits byte"),
    188: CommandSpec(188, "GetJoystick", 0, 9),
    189: CommandSpec(189, "SetJoystick", 9, 0),
    255: CommandSpec(255, "Wrong", 0, 0, "not a command; rejection marker"),
}


def spec(code: int) -> CommandSpec:
    """Table entry for `code`; raises QueryError when unknown."""
    try:
        return COMMANDS[code]
    except KeyError:
        raise QueryError(f"unknown command code {code} (0x{code:02X})",
                         code=code) from None


def command_name(code: int) -> str:
    """Human-readable name or 'unknown' - never raises."""
    entry = COMMANDS.get(code)
    return entry.name if entry else f"unknown ({code})"


def all_commands() -> list[CommandSpec]:
    """Table rows sorted by code (for reference tables / pickers)."""
    return sorted(COMMANDS.values())


def validate_write(code: int, data: bytes) -> None:
    """Raise QueryError unless `data` matches the write size of `code`."""
    sp = spec(code)
    if len(data) != sp.write:
        raise QueryError(
            f"cmd {code} {sp.name}: write data must be {sp.write} byte(s), "
            f"got {len(data)}", code=code)


def validate_read(code: int, data: bytes) -> None:
    """Raise QueryError unless `data` matches the read size of `code`."""
    sp = spec(code)
    if len(data) != sp.read:
        raise QueryError(
            f"cmd {code} {sp.name}: reply must be {sp.read} byte(s), "
            f"got {len(data)}", code=code)


class Querier:
    """Reusable request/response engine with table validation.

    Holds one endpoint (a `ComPortService`) and one device address; the
    instance is callable:

        q = Querier(conn, adr=1)
        q(96)                          -> bytes  (GetContParam)
        q(106, u32(600), channel=3)    -> b""    (setSpeed on channel 3)

    Request-IDs rotate 0..30 and every retry uses a fresh one, exactly like
    the reference client.  `validate=False` skips the table size checks
    (explorative access to non-standard firmware), the code must still be
    known unless `allow_unknown=True`.
    """

    def __init__(self, conn: ComPortService, adr: int = 1):
        self.conn = conn
        self.adr = adr & 0xFF
        self._next_request_id = 0

    def _request_id(self) -> int:
        rid = self._next_request_id
        self._next_request_id = (self._next_request_id + 1) % 31
        return rid

    def __call__(self, code: int, write_data: bytes = b"", channel: int = 0,
                 *, timeout: float | None = None, attempts: int = 2,
                 validate: bool = True,
                 allow_unknown: bool = False) -> bytes:
        """Execute one command and return the reply DATA bytes.

        channel is the packet CH byte (motor channel, group slot, MC index
        or object ordinal).  write_data must match the table's write size
        and the reply its read size (unless validate=False).
        """
        write_data = bytes(write_data)
        channel &= 0xFF
        if allow_unknown and code not in COMMANDS:
            sp = None
        else:
            sp = spec(code)
            if validate:
                validate_write(code, write_data)

        last_error: Exception | None = None
        for _ in range(max(1, attempts)):
            rid = self._request_id()
            pkt = p.build_packet(self.adr, channel, code, write_data,
                                 request_id=rid)
            try:
                reply = self.conn.request(pkt, timeout=timeout,
                                          expected_request_id=rid)
            except (TimeoutError_, DeviceOffline) as exc:
                # Server-reported timeout / offline is final for this
                # Request-ID: retry with a NEW one (protocol doc §5.3).
                last_error = exc
                continue
            if reply["cmd"] == p.REPLY_NOT_SUPPORTED:
                raise CommandRejected(
                    f"command {code} ({command_name(code)}) on channel "
                    f"{channel} rejected (0xFE not-supported reply)",
                    code=code, ch=channel)
            if (not p.is_ack(reply, code, channel)
                    or reply.get("request_id") != rid):
                raise CommandRejected(
                    f"reply to command {code} on channel {channel} did not "
                    "echo cmd/channel/Request-ID", code=code, ch=channel)
            data = reply["data"]
            if validate and sp is not None:
                validate_read(code, data)
            return data
        raise last_error if last_error else CommandRejected(
            f"command {code} failed", code=code, ch=channel)
