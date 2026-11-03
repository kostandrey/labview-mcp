"""
StepV2 wire-protocol primitives.

Packet format (all multi-byte fields little-endian):

    [ADR][LEN][CH][CMD][...DATA...][OPT_REQ_ID][CRC_LO][CRC_HI]

    ADR  - target device address (0 = broadcast, accepted by all devices)
    LEN  - total packet length - 3  (== 3 + len(DATA))
    CH   - channel / sub-device index
    CMD  - command byte
    DATA - command payload
    OPT_REQ_ID - optional Request-ID byte inserted between DATA and CRC;
                 the COM_PortService overwrites it with the encoded client ID
                 and strips it from the reply, so the PC client normally does
                 not need to care about it.
    CRC  - CRC-16/Modbus (poly 0xA001 reflected, seed 0xFFFF), little-endian.

Reply framing (TSH_device v1.34):
    Reply LEN = 3 + number of reply DATA bytes; LEN == 3 means
    acknowledge-only.  An unsupported / rejected command replies with
    CMD = 0xFE and no data.  The COM_PortService reports transport errors
    (timeout / COM offline) with CMD = 0xFF and one error-code byte.
"""

from __future__ import annotations

import struct

# ---------------------------------------------------------------------------
# Command codes
# ---------------------------------------------------------------------------

CMD_NOT_SUPPORTED = 0xFF  # uartProtocolDataLength() "command not supported"
REPLY_NOT_SUPPORTED = 0xFE  # replied CMD code: "command not supported"
REPLY_TRANSPORT_ERROR = 0xFF  # COM_PortService synthetic error packet

# Device-level (TSHDevice)
CMD_GET_CONTROLLER_PARAMS = 96
CMD_SET_CONTROLLER_PARAMS = 94
CMD_GET_CHANNEL_TYPE = 171
CMD_SET_CHANNEL_TYPE = 170
CMD_GET_BOARD_VER = 173
CMD_SET_BOARD_VER = 172
CMD_GET_SKETCH_VER = 174
CMD_READ_EEPROM = 154
CMD_WRITE_EEPROM = 155
CMD_GROUP_ATTACH_2 = 132
CMD_GROUP_ATTACH_3 = 133
CMD_GROUP_GET_2 = 148
CMD_GROUP_GET_3 = 149
CMD_RESET_CONTROLLER = 156
CMD_GET_UPLOAD_TIME = 102
CMD_ANALOG_READ = 115  # CH=255 -> device-level power supply voltage

# Motor family (Motor / Stepper / TMCUart / TitanMot)
CMD_SET_CUSTOM_PINS = 90
CMD_GET_CURRENT_PINS = 92
CMD_HOMING_AUTO = 99
CMD_HOMING_DIR = 100
CMD_HOME_STATUS = 101
CMD_SET_TMC = 103
CMD_TMC_UART_MSG = 104
CMD_GET_TMC = 105
CMD_SET_SPEED = 106
CMD_UART_MOVE = 107
CMD_MOVE_ABS = 108
CMD_SET_ADV_PARS = 109
CMD_GET_POSITION = 110
CMD_GET_ADV_PARS = 111
CMD_MOVE_STOP = 112
CMD_FORCE_ENABLE = 118
CMD_FORCE_DISABLE = 119
CMD_TMC_UART_REPLY = 113
CMD_SET_BACKLASH = 114
CMD_TEST_PARAM = 120
CMD_SET_ACCELERATION = 122
CMD_SET_STEP_VALUE = 124
CMD_SET_HOME_POSITION = 126
CMD_SET_SCALE_MAX = 128
CMD_SET_MICROSTEPS = 130
CMD_SET_BOOL_PARAMS = 140
CMD_GET_MOTOR_CONFIG = 144
CMD_SET_HOMING_SPEED = 146
CMD_SET_SCALE_MIN = 152

# L12 group
CMD_TSH_START = 134
CMD_TSH_STOP = 136
CMD_TSH_GET_POS = 138
CMD_TSH_GO_POS = 142
CMD_TSH_GET_BOUNDS = 150
CMD_TSH_HOME = 151

# Monochromator
CMD_MC_SET_MODE = 117
CMD_MC_GET_STATUS = 121
CMD_MC_SET_WAVE = 123
CMD_MC_REINIT = 125

# Shutter
CMD_SHUTTER_CONFIG = 160
CMD_SHUTTER_GET_PARAMS = 161
CMD_SHUTTER_CONTROL = 162
CMD_SHUTTER_READ = 163

# Chopper
CMD_CHOPPER_SET_PID = 158
CMD_CHOPPER_GET_PID = 159
CMD_CHOPPER_PRESET = 164
CMD_CHOPPER_SET_DIVIDER = 165
CMD_CHOPPER_GET_FREQ = 166
CMD_CHOPPER_SET_PHASE = 167
CMD_CHOPPER_GET_PARAMS = 168
CMD_CHOPPER_SET_FREQ = 169
CMD_CHOPPER_SET_SHUTTER = 175
CMD_CHOPPER_GET_SHUTTER = 176
CMD_CHOPPER_ARM_SHUTTER = 177

# Position sensor
CMD_SENSOR_CONFIG = 180
CMD_SENSOR_GET_PARAMS = 181
CMD_SENSOR_GET_POS = 182
CMD_SENSOR_MEASURE = 183

# Joystick
CMD_JOYSTICK_GET = 188
CMD_JOYSTICK_SET = 189

# SDG (board version 13, StepV2_protocol/main.c uartProtocol())
# NOTE: 164 collides with CMD_CHOPPER_PRESET (TSH_device) - the two firmwares
# are flashed on different boards, so the code is unambiguous per device.
CMD_SDG_GET_STATUS = 85   # CH=255 also resets the pulse counter
CMD_SDG_ENABLE = 84       # CH: 0=core, 1..4=channels, 20=start ramp, 255=lock clock
CMD_SDG_SET_TRIG_LEVEL = 83  # data: [which(0=clock,1=arming)][f32]
CMD_SDG_GET_TRIG_LEVEL = 82  # data: [which]; reply: [which][f32]
CMD_SDG_SET_MCO2 = 81     # data: [src][pre][u32 M][u32 N][u32 R]
CMD_SDG_GET_MCO2 = 80     # reply: [src][pre][u32 M][u32 N][u32 R]
CMD_SDG_SET_PERIOD = 89   # data: u32 cycles (0=software, 1=external, 2=gate arming)
CMD_SDG_SET_DIGITAL_DELAY = 88  # CH=delay slot 0..7 / 16..20 (misc); data: u32
CMD_SDG_SET_ANALOG_DELAY = 87   # CH=slot 0..7; data: u16 (ps)
CMD_SDG_GET_DELAYS = 86   # CH: 255=period, 0..7=digital, 16..20=extra, 64..71=analog
CMD_SDG_SAVE = 164        # writes SDGParams to flash (sector 7 @ 0x08060000)

# FreqGen (board version 14) - single command: write a 4-byte float frequency
# in Hz, the reply is the 4-byte float actual value. Writing -1 (f32) queries
# without updating the device; values > 0 set the new frequency.
# NOTE: 131 is unused by TSH_device (group commands are 132/133), but the two
# firmwares live on different boards anyway.
CMD_FREQGEN_FREQUENCY = 131

# ---------------------------------------------------------------------------
# Channel type codes (EEPROM byte per channel, set with cmd 170)
# ---------------------------------------------------------------------------

# Channel type codes (EEPROM byte per channel, set with cmd 170) —
# names follow the legacy LabView "Configure StepV2" utility
CHANNEL_TYPES = {
    0: "None (Channel disabled)",
    1: "Stepper: DRV8825",
    2: "Stepper: TMC2208",
    3: "Shutter",
    4: "Shutter over DRV8825",
    5: "IR detector",
    6: "Stepper: TMC-uart",
    7: "Stepper: TMC2209",
    8: "Joystick",
    9: "DigitalInput",
    10: "DigitalOutput",
    11: "AnalogInput",
    12: "TitanMot",
    50: "Chopper",
    52: "FreqGen",
    55: "SDG",
    255: "Not configured",
}

MOTOR_CHANNEL_TYPES = (1, 2, 6, 7, 12)

# Controller bitParams byte (cmd 94 write / 96 read, EEPROM address 0).
# Bit meanings extracted from TSH_step.ino setup() in v1.34:
#   bit 0 -> custom ENABLE pin, bit 1 -> custom channels number,
#   bit 2 -> custom groups number, bit 4 -> low UART timeout (5 ms vs 25),
#   bit 5 -> serial diagnostics disabled.  Bit 3 ("Terminating Chain") and
#   bits 6..7 are not referenced by v1.34 but kept for compatibility.
CONTROLLER_BITPARAMS = [
    (0, "Custom Enable Pin"),
    (1, "Custom Ch. Num"),
    (2, "Custom Groups Num"),
    (3, "Terminating Chain (unused in v1.34)"),
    (4, "Low data transfer timeout"),
    (5, "Disable serial diagnostics"),
    (6, "Reserved"),
    (7, "Reserved"),
]

# Board version codes (EEPROM byte, cmd 172 write / 173 read) —
# names follow the legacy LabView "Configure StepV2" utility
BOARD_VERSIONS = {
    0: "None",
    1: "4-channel CNC3.0",
    2: "2-channel rev A",
    3: "2-channel rev B and C",
    4: "12-channel rev B",
    5: "12-channel rev C",
    6: "2-channel rev D",
    7: "12-channel rev D",
    8: "2-channel rev D2",
    9: "12-channel rev D2",
    10: "2-channel rev E1",
    11: "12-channel rev E1",
    12: "Chopper rev.A",
    13: "SDG",
    14: "FreqGen",
}

# Feature gating by sketch / board version (used by the configurator UI):
#   - analogRead (cmd 115) family            -> sketch >= 27
#   - power supply voltage (115/CH255)       -> sketch >= 27 AND rev E1 board
#   - monochromator commands (117/121/123/125, EEPROM blocks) -> sketch >= 27
#   - ConfigTMC (103/105) + advanced (109/111)                -> sketch >= 26
#   - "Config group" (133); below 23 use "Attach motors" (132)
#   - chopper commands: (rev E1 AND sketch >= 33) OR Chopper rev.A board (12;
#     there the shutter/ARM subset does not exist)
REV_E1_BOARDS = (10, 11)      # 2-channel / 12-channel rev E1
CHOPPER_BOARD = 12            # Chopper rev.A
MIN_SKETCH_ANALOG = 27
MIN_SKETCH_MONO = 27
MIN_SKETCH_TMC = 26
MIN_SKETCH_GROUP_CFG = 23
MIN_SKETCH_CHOPPER_E1 = 33
MIN_SKETCH_UPLOAD_TIME = 25   # cmd 102 (getUploadTime)

# ---------------------------------------------------------------------------
# CRC
# ---------------------------------------------------------------------------


def crc16_modbus(data: bytes, seed: int = 0xFFFF) -> int:
    """CRC-16/MODBUS: reflected poly 0xA001, init 0xFFFF."""
    crc = seed
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def crc8_atm(data: bytes) -> int:
    """TMC UART datagram CRC-8, exactly as TMCUart::calcCRC in the v1.34
    sketch (and the TMC datasheet): poly 0x07, init 0x00, input bits
    processed LSB-first.

    Known answer: 05 FF 6F C0 1F 00 00 -> 0xC1 (TMC2209 DRV_STATUS reply).
    """
    crc = 0
    for current in data:
        for _ in range(8):
            if (crc >> 7) ^ (current & 0x01):
                crc = (crc << 1) ^ 0x07
            else:
                crc = (crc << 1)
            crc &= 0xFF
            current >>= 1
    return crc


# ---------------------------------------------------------------------------
# Framing
# ---------------------------------------------------------------------------


def build_packet(adr: int, ch: int, cmd: int, data: bytes = b"",
                 request_id: int | None = None) -> bytes:
    """Build a complete StepV2 request packet including CRC.

    request_id (0..30), when given, is appended just before the CRC and LEN
    does NOT count it (packet length == LEN + 4).  This is the convention the
    COM_PortService expects from UDP clients (StepV2Adapter
    ::extractClientRequestID): it re-encodes the ID for the device and strips
    or decodes it again in the reply.
    """
    if request_id is not None and not 0 <= request_id <= 30:
        raise ValueError("request_id must be in range 0..30")
    body = bytes([adr, 3 + len(data), ch, cmd]) + data
    if request_id is not None:
        body += bytes([request_id])
    return body + struct.pack("<H", crc16_modbus(body))


def parse_packet(packet: bytes) -> dict:
    """Validate and split a received packet.

    Returns dict with keys: adr, len, ch, cmd, data, request_id (None when
    absent), crc_ok.

    Request-ID conventions (see TSHDevice / StepV2Protocol / StepV2Adapter):
      * Client requests and device replies both carry the ID before the CRC
        with LEN excluding it (packet length == LEN + 4).
      * A device reply without an ID has length == LEN + 3.
    """
    if len(packet) < 6:
        return {"crc_ok": False, "error": "packet too short"}
    if crc16_modbus(packet[:-2]) != struct.unpack("<H", packet[-2:])[0]:
        return {"crc_ok": False, "error": "CRC mismatch"}
    adr, length, ch, cmd = packet[0], packet[1], packet[2], packet[3]
    count = len(packet)
    if length != count - 3 and length != count - 4:
        return {"crc_ok": False,
                "error": f"LEN {length} matches neither count-3 ({count - 3})"
                         f" nor count-4 ({count - 4})"}
    if count == length + 4:
        # Packet carrying a Request-ID (LEN excludes it) - used by client
        # requests and by device replies alike.
        data = packet[4:-3]
        request_id = packet[-3]
    else:
        data = packet[4:-2]
        request_id = None
    return {"adr": adr, "len": length, "ch": ch, "cmd": cmd, "data": data,
            "request_id": request_id, "crc_ok": True}


def is_ack(parsed: dict, cmd: int, ch: int | None = None) -> bool:
    """True when parsed packet is a valid acknowledge for cmd."""
    if not parsed.get("crc_ok"):
        return False
    if parsed["cmd"] != cmd:
        return False
    if ch is not None and parsed["ch"] != ch:
        return False
    return True


# ---------------------------------------------------------------------------
# Value helpers (mirror of firmware FromToBytes.h — raw little-endian memcpy)
# ---------------------------------------------------------------------------


def f32(value: float) -> bytes:
    return struct.pack("<f", value)


def u16(value: int) -> bytes:
    return struct.pack("<H", value & 0xFFFF)


def u32(value: int) -> bytes:
    return struct.pack("<I", value & 0xFFFFFFFF)


def to_f32(data: bytes, offset: int = 0) -> float:
    return struct.unpack_from("<f", data, offset)[0]


def to_u16(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def to_u32(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def to_i16(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from("<h", data, offset)[0]


def to_i32(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from("<i", data, offset)[0]


# ---------------------------------------------------------------------------
# Misc firmware constants a configuration tool needs
# ---------------------------------------------------------------------------

# Microstep resolution code byte (ADR_MICROSTEPS / cmd 130 / cmd 144 byte 24)
MICROSTEP_CODES = {
    0: 256,
    1: 1,
    2: 2,
    3: 1024,
    4: 4,
    8: 8,
    16: 16,
    32: 32,
    64: 64,
    128: 128,
    256: 256,
}


def microstep_code_label(code: int) -> str:
    value = MICROSTEP_CODES.get(code)
    if value is None:
        return f"code {code} (invalid)"
    return f"code {code} -> {value} µsteps"


# Microsteps selector items, mirroring the LabView enum: display name ->
# EEPROM code (code 0 means 256, code 3 means 256 x 4 = 1024; other codes
# are the literal µstep count).
MICROSTEP_ITEMS = [
    ("1", 1),
    ("2", 2),
    ("4", 4),
    ("8", 8),
    ("16", 16),
    ("32", 32),
    ("64", 64),
    ("128", 128),
    ("256", 0),
    ("256 x 4", 3),
]


# Homing state machine (cmd 101 reply data[0] / testParam 0)
HOMING_STATES = {
    0: "0 - idle / homed",
    1: "1 - initial home-sensor check",
    2: "2 - backing off from sensor (pass 1)",
    3: "3 - debounced release (pass 1)",
    4: "4 - approaching sensor (pass 1)",
    5: "5 - waiting switch closure (pass 1)",
    6: "6 - stop at trigger (pass 1)",
    7: "7 - wait motion complete, phase adjust (pass 1)",
    8: "8 - end of pass 1",
    9: "9 - backing off from sensor (slow pass 2)",
    10: "10 - debounced release (pass 2)",
    11: "11 - approaching sensor (pass 2)",
    12: "12 - waiting switch closure (pass 2)",
    13: "13 - stop at trigger (pass 2)",
    14: "14 - wait motion complete (pass 2)",
    15: "15 - end of slow pass 2",
    16: "16 - accuracy verification / retry",
    17: "17 - TMC: settle delay, MSCNT read",
    18: "18 - TMC: phase-corrected final move",
    100: "100 - unhomed (power-on default)",
    130: "130 - stuck (stage 3 exit)",
    132: "132 - stuck (stage 5 exit)",
    137: "137 - stuck (stage 10 exit)",
    139: "139 - stuck (stage 12 exit)",
    240: "240 - Titan: I2C write NACK",
    241: "241 - Titan: I2C read empty",
    242: "242 - Titan: homing timeout (60 s)",
    245: "245 - TMC: driver overtemperature",
    246: "246 - TMC: wrong silicon (VERSION != 0x20)",
    247: "247 - TMC: charge pump undervoltage (VS missing)",
    248: "248 - TMC: coil fault / short / open load",
    249: "249 - TMC: IFCNT verification failed",
    250: "250 - TMC: no driver response to address probe",
}

# testParam (cmd 120) parameter codes — authoritative for v1.34
# (Motor::testParam -> Stepper::testParam -> TMCUart::testParam chain;
# codes 6/7/12/14/16/20/22 are only answered on non-AVR boards)
TEST_PARAMS = {
    0: "movingHome (homing state)",
    1: "tarPos",
    2: "pinState (STEP pin)",
    3: "decSteps",
    4: "stepsToDo",
    5: "stepPos (µsteps)",
    6: "microSteps",
    7: "stepsCoeff",
    8: "homePosition",
    9: "oldStepPos",
    10: "newStepPos",
    11: "homePos",
    12: "posCoeff",
    13: "curPos",
    14: "memAdr",
    15: "shift",
    16: "channelActive",
    17: "homeMicro",
    18: "backlash_step",
    20: "lspeed",
    21: "microsDelay",
    22: "fullStepsOnly",
    23: "curMicrosDelay",
    24: "stepTime",
    25: "crtTime (µs)",
    27: "homeRetries",
    28: "homedFrom",
    29: "coilStatus (DRV_STATUS flags)",
    30: "GSTAT register",
    31: "IFCNT",
    32: "stepPosDiff",
    33: "stepPosDiffCnt",
}

# COM_PortService synthetic error packet (CMD 0xFF) error codes
TRANSPORT_ERRORS = {
    0x01: "timeout (no device response)",
    0x02: "COM port offline",
}

# DRV_STATUS coil status flags (testParam 29, bits in TMC2209 order)
COIL_STATUS_FLAGS = (
    ("s2ga", "short to ground coil A"),
    ("s2gb", "short to ground coil B"),
    ("s2vsa", "short to supply coil A"),
    ("s2vsb", "short to supply coil B"),
    ("ola", "open load coil A"),
    ("olb", "open load coil B"),
)


def describe_coil_status(flags: int) -> str:
    if flags == 0:
        return "OK"
    return ", ".join(name for i, (name, _desc) in enumerate(COIL_STATUS_FLAGS)
                     if flags & (1 << i))
