"""Typed wrappers for the complete ArduinoStepV2 v1.34 host command set.

Every function takes a `ComPortService` plus the addressing bytes and returns
decoded python values.  A command "rejected" by the device (replied command
code 0xFE, no data) raises CommandRejected.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from . import protocol as p
from .protocol import (build_packet, f32, u16, u32, to_f32, to_i16, to_i32,
                       to_u16, to_u32)
from .transport import ComPortService, DeviceOffline, TimeoutError_


class CommandRejected(Exception):
    """Device replied 0xFE (command not supported / rejected)."""

    def __init__(self, cmd: int, ch: int):
        self.cmd = cmd
        self.ch = ch
        super().__init__(
            f"command {cmd} on channel {ch} rejected (0xFE not-supported reply)")


def _packet_len(data_len: int) -> int:
    # total packet length used by uartProtocolDataLength(): 6 + data bytes
    return 6 + data_len


# Monochromator EEPROM layout (Monochromator.h, v1.34)
MC_EEPROM_BASE = 2304      # ADR_ABS_MC
MC_EEPROM_TOTAL = 320      # ADR_MC_TOTAL (per MC index)
MC_CALIB_OFFSET = 64       # ADR_MC_CALIB (mode-0 calibration in MC block)
MC_CALIB_TOTAL = 64        # ADR_CALIB_TOTAL (per mode)
MC_CALIB_PARS_OFFSET = 24  # ADR_CALIB_CALIB (calibrationType1/2 in slot)


class Device:
    """High-level view of one controller behind a COM_PortService endpoint."""

    def __init__(self, conn: ComPortService, adr: int = 1):
        self.conn = conn
        self.adr = adr
        conn.default_adr = adr  # used by the session keepalive ping
        self._next_request_id = 0

    # ------------------------------------------------------------------
    # low-level helpers
    # ------------------------------------------------------------------

    def _request_id(self) -> int:
        """Rotating Request-ID, cycling 0 -> 1 -> ... -> 30 -> 0 -> ...

        Always in the valid tracked range (never 31; the server clamps
        silently and the reply would lose the ID).  Operating as a
        Request-ID-mode master makes the COM_PortService request-ID handling
        exact, and the echoed ID in the reply verifies that the message
        received answers the message sent.
        """
        rid = self._next_request_id
        self._next_request_id = (self._next_request_id + 1) % 31
        return rid

    def _call(self, ch: int, cmd: int, data: bytes = b"",
              timeout: float | None = None, attempts: int = 2) -> bytes:
        last_error: Exception | None = None
        for _ in range(max(1, attempts)):
            rid = self._request_id()
            pkt = build_packet(self.adr, ch, cmd, data, request_id=rid)
            try:
                reply = self.conn.request(pkt, timeout=timeout,
                                          expected_request_id=rid)
            except (TimeoutError_, DeviceOffline) as exc:
                # Server-reported timeout (0x01) / offline (0x02) is final for
                # this Request-ID: retry with a NEW one (doc §5.3).
                last_error = exc
                continue
            if reply["cmd"] == p.REPLY_NOT_SUPPORTED:
                raise CommandRejected(cmd, ch)
            if not p.is_ack(reply, cmd, ch) or reply.get("request_id") != rid:
                raise CommandRejected(cmd, ch)
            return reply["data"]
        raise last_error if last_error else CommandRejected(cmd, ch)

    def _call_ack(self, ch: int, cmd: int, data: bytes = b"",
                  timeout: float | None = None) -> None:
        self._call(ch, cmd, data, timeout=timeout)

    def _call_raw(self, ch: int, cmd: int, data: bytes = b"",
                  timeout: float | None = None) -> bytes:
        """Like _call but accepts replies with any command code (raw access)."""
        pkt = build_packet(self.adr, ch, cmd, data,
                           request_id=self._request_id())
        reply = self.conn.request(pkt, timeout=timeout)
        if not reply.get("crc_ok"):
            raise CommandRejected(cmd, ch)
        return reply.get("data", b"")

    # ------------------------------------------------------------------
    # Device-level commands
    # ------------------------------------------------------------------

    def get_controller_params(self) -> dict:
        """cmd 96 -> bitParams, enablePin, motorsNum, groupNum, adr."""
        data = self._call(0, p.CMD_GET_CONTROLLER_PARAMS)
        return {"bitParams": data[0], "enablePin": data[1],
                "motorsNum": data[2], "groupNum": data[3], "adr": data[4]}

    def set_controller_params(self, bit_params: int, enable_pin: int,
                              motors_num: int, group_num: int,
                              adr: int) -> None:
        """cmd 94 - applied after controller reset (cmd 156)."""
        self._call_ack(0, p.CMD_SET_CONTROLLER_PARAMS,
                       bytes([bit_params & 0xFF, enable_pin & 0xFF,
                              motors_num & 0xFF, group_num & 0xFF,
                              adr & 0xFF]))
        self.adr = adr & 0xFF
        self.conn.default_adr = self.adr

    def get_channel_type(self, ch: int) -> int:
        """cmd 171 - channel type code of hardware channel ch."""
        return self._call(ch, p.CMD_GET_CHANNEL_TYPE)[0]

    def set_channel_type(self, ch: int, ch_type: int) -> None:
        """cmd 170 - writes the EEPROM channel-type byte (ch is the channel)."""
        self._call_ack(ch, p.CMD_SET_CHANNEL_TYPE, bytes([ch_type & 0xFF]))

    def get_board_ver(self) -> int:
        return self._call(0, p.CMD_GET_BOARD_VER)[0]

    def set_board_ver(self, ver: int) -> None:
        self._call_ack(0, p.CMD_SET_BOARD_VER, bytes([ver & 0xFF]))

    def get_sketch_ver(self) -> int:
        return self._call(0, p.CMD_GET_SKETCH_VER)[0]

    def get_upload_time(self) -> str:
        return self._call(0, p.CMD_GET_UPLOAD_TIME, timeout=3.0).decode(
            "ascii", "replace").rstrip("\x00")

    def reset_controller(self) -> None:
        """cmd 156 - mandatory after configuration or settings are lost."""
        self._call_ack(0, p.CMD_RESET_CONTROLLER, timeout=3.0)

    def read_eeprom_page(self, page: int) -> bytes:
        """cmd 154 - 32-byte page (pages 0..127)."""
        return self._call(0, p.CMD_READ_EEPROM, bytes([page & 0x7F]))

    def write_eeprom_page(self, page: int, data: bytes) -> None:
        """cmd 155 - 32-byte page write."""
        if len(data) != 32:
            raise ValueError("EEPROM page write requires exactly 32 bytes")
        self._call_ack(0, p.CMD_WRITE_EEPROM,
                       bytes([page & 0x7F]) + data, timeout=3.0)

    def group_attach_2(self, slot: int, ch_a: int, ch_b: int) -> None:
        """cmd 132 - attach 2 motors to group slot (EEPROM 576 + slot*4)."""
        self._call_ack(slot, p.CMD_GROUP_ATTACH_2, bytes([ch_a, ch_b]))

    def group_attach_3(self, slot: int, ch_x: int, ch_y: int,
                       group_type: int) -> None:
        """cmd 133 - write a group record (EEPROM 576 + slot*4).

        The three bytes are channelX, channelY and the group type byte
        (578 is read back as the type on boot: 255 = default init,
        2 = Berek differential coupling)."""
        self._call_ack(slot, p.CMD_GROUP_ATTACH_3,
                       bytes([ch_x, ch_y, group_type]))

    def group_get_2(self, slot: int) -> tuple[int, int]:
        data = self._call(slot, p.CMD_GROUP_GET_2)
        return data[0], data[1]

    def group_get_3(self, slot: int) -> tuple[int, int, int]:
        data = self._call(slot, p.CMD_GROUP_GET_3)
        return data[0], data[1], data[2]

    def read_power_voltage(self) -> float:
        """cmd 115 with CH=255 - power supply voltage."""
        return to_f32(self._call(255, p.CMD_ANALOG_READ))

    def read_analog(self, index: int) -> float:
        """cmd 115 with the analog object ordinal."""
        return to_f32(self._call(index, p.CMD_ANALOG_READ))

    # ------------------------------------------------------------------
    # Motor family
    # ------------------------------------------------------------------

    def get_motor_config(self, ch: int) -> "MotorConfig":
        """cmd 144 - full 38-byte configuration snapshot."""
        data = self._call(ch, p.CMD_GET_MOTOR_CONFIG)
        return MotorConfig(
            move_speed=to_f32(data, 0),
            backlash=to_f32(data, 4),
            acceleration=to_f32(data, 8),
            step_value=to_f32(data, 12),
            home_position=to_f32(data, 16),
            scale_max=to_f32(data, 20),
            microsteps_code=data[24],
            bpar=data[25],
            homing_speed=to_f32(data, 26),
            homing_speed2=to_f32(data, 30),
            scale_min=to_f32(data, 34),
            channel=ch,
        )

    def set_speed(self, ch: int, value: float) -> None:
        self._call_ack(ch, p.CMD_SET_SPEED, f32(value))

    def set_acceleration(self, ch: int, value: float) -> None:
        self._call_ack(ch, p.CMD_SET_ACCELERATION, f32(value))

    def set_backlash(self, ch: int, value: float) -> None:
        self._call_ack(ch, p.CMD_SET_BACKLASH, f32(value))

    def set_step_value(self, ch: int, value: float) -> None:
        self._call_ack(ch, p.CMD_SET_STEP_VALUE, f32(value))

    def set_home_position(self, ch: int, value: float) -> None:
        self._call_ack(ch, p.CMD_SET_HOME_POSITION, f32(value))

    def set_scale_max(self, ch: int, value: float) -> None:
        self._call_ack(ch, p.CMD_SET_SCALE_MAX, f32(value))

    def set_scale_min(self, ch: int, value: float) -> None:
        self._call_ack(ch, p.CMD_SET_SCALE_MIN, f32(value))

    def set_microsteps(self, ch: int, code: int) -> None:
        self._call_ack(ch, p.CMD_SET_MICROSTEPS, bytes([code & 0xFF]))

    def set_bool_params(self, ch: int, bpar: int) -> None:
        self._call_ack(ch, p.CMD_SET_BOOL_PARAMS, bytes([bpar & 0xFF]))

    def set_homing_speed(self, ch: int, speed1: float, speed2: float) -> None:
        self._call_ack(ch, p.CMD_SET_HOMING_SPEED, f32(speed1) + f32(speed2))

    def set_tmc_params(self, ch: int, motor_current: int, sg_thrs: int) -> None:
        """cmd 103 - on TMCUart channels also rewrites the driver registers."""
        self._call_ack(ch, p.CMD_SET_TMC, bytes([motor_current & 0xFF,
                                                 sg_thrs & 0xFF]))

    def get_tmc_params(self, ch: int) -> tuple[int, int]:
        data = self._call(ch, p.CMD_GET_TMC)
        return data[0], data[1]

    def set_adv_params(self, ch: int, adv: "AdvancedParams") -> None:
        """cmd 109 - on TMCUart channels also rewrites the driver registers."""
        payload = (f32(adv.second_backlash) + u16(adv.u_steps_diff) +
                   bytes([adv.max_retr_num & 0xFF, adv.ihold & 0xFF]))
        self._call_ack(ch, p.CMD_SET_ADV_PARS, payload)

    def get_adv_params(self, ch: int) -> "AdvancedParams":
        data = self._call(ch, p.CMD_GET_ADV_PARS)
        return AdvancedParams(
            second_backlash=to_f32(data, 0),
            u_steps_diff=to_i16(data, 4),
            max_retr_num=data[6],
            ihold=data[7],
        )

    def get_pins(self, ch: int) -> tuple[int, int, int, int]:
        """cmd 92 -> (step, dir, home, enable)."""
        data = self._call(ch, p.CMD_GET_CURRENT_PINS)
        return data[0], data[1], data[2], data[3]

    def set_pins(self, ch: int, step: int, direction: int, home: int,
                 enable: int) -> None:
        self._call_ack(ch, p.CMD_SET_CUSTOM_PINS,
                       bytes([step & 0xFF, direction & 0xFF, home & 0xFF,
                              enable & 0xFF]))

    def get_position(self, ch: int) -> tuple[float, int]:
        """cmd 110 -> (position, U8 status); bit0 moving, bit1 home sensor."""
        data = self._call(ch, p.CMD_GET_POSITION)
        return to_f32(data, 0), data[4]

    def get_home_status(self, ch: int) -> tuple[int, int]:
        """cmd 101 -> (movingHome state, homeReset microsteps)."""
        data = self._call(ch, p.CMD_HOME_STATUS)
        return data[0], to_i32(data, 1)

    def homing_auto(self, ch: int) -> None:
        self._call_ack(ch, p.CMD_HOMING_AUTO)

    def homing_dir(self, ch: int, direction: int) -> None:
        self._call_ack(ch, p.CMD_HOMING_DIR, bytes([direction & 0xFF]))

    def move_abs(self, ch: int, position: float) -> None:
        self._call_ack(ch, p.CMD_MOVE_ABS, f32(position))

    def uart_move(self, ch: int, velocity: float) -> None:
        """cmd 107 - velocity move (TMC VACTUAL mode)."""
        self._call_ack(ch, p.CMD_UART_MOVE, f32(velocity))

    def move_stop(self, ch: int) -> None:
        self._call_ack(ch, p.CMD_MOVE_STOP)

    def force_enable(self, ch: int, on: bool) -> None:
        """cmd 118 - force the driver enable on/off (on=0 releases)."""
        self._call_ack(ch, p.CMD_FORCE_ENABLE, bytes([1 if on else 0]))

    def force_disable(self, ch: int, on: bool) -> None:
        """cmd 119 - force the driver disable on/off (on=0 releases)."""
        self._call_ack(ch, p.CMD_FORCE_DISABLE, bytes([1 if on else 0]))

    def test_param(self, ch: int, code: int) -> float:
        """cmd 120 - raw 32-bit value of test parameter `code`."""
        return to_f32(self._call(ch, p.CMD_TEST_PARAM, bytes([code & 0xFF])))

    # -- TMC raw UART access (cmd 104 / 113) ----------------------------

    def tmc_uart_message(self, ch: int, slave: int, reg: int,
                         wdata: int = 0) -> None:
        """cmd 104 - send a raw TMC2209 datagram through the controller.

        reg bit7 = 1: write, wdata is the 32-bit payload (sent MSB-first).
        reg bit7 = 0: read request for reg.
        slave >= 4 is replaced by the auto-probed driver address.
        """
        if reg & 0x80:
            payload = struct.pack(">I", wdata & 0xFFFFFFFF)
        else:
            payload = b"\x00\x00\x00\x00"
        msg = bytes([0x05, slave & 0xFF, reg & 0xFF]) + payload + b"\x00"
        self._call_ack(ch, p.CMD_TMC_UART_MSG, msg)

    def tmc_uart_reply(self, ch: int) -> bytes:
        """cmd 113 - retrieve the 12-byte TMC datagram buffer."""
        return self._call(ch, p.CMD_TMC_UART_REPLY)

    # ------------------------------------------------------------------
    # L12 group (CH = EEPROM slot index)
    # ------------------------------------------------------------------

    def tsh_start(self, slot: int, mode: int, x0: float, y0: float, x1: float,
                  y1: float, step_x: float, step_y: float, to_end_x: float,
                  to_end_y: float, speed_x: float, speed_y: float) -> None:
        data = (bytes([mode & 0xFF]) + f32(x0) + f32(y0) + f32(x1) + f32(y1) +
                f32(step_x) + f32(step_y) + f32(to_end_x) + f32(to_end_y) +
                f32(speed_x) + f32(speed_y))
        self._call_ack(slot, p.CMD_TSH_START, data)

    def tsh_stop(self, slot: int) -> None:
        self._call_ack(slot, p.CMD_TSH_STOP)

    def tsh_get_pos(self, slot: int) -> tuple[float, float]:
        data = self._call(slot, p.CMD_TSH_GET_POS)
        return to_f32(data, 0), to_f32(data, 4)

    def tsh_go_pos(self, slot: int, x: float, y: float) -> None:
        self._call_ack(slot, p.CMD_TSH_GO_POS, f32(x) + f32(y))

    def tsh_get_bounds(self, slot: int) -> dict:
        data = self._call(slot, p.CMD_TSH_GET_BOUNDS)
        return {
            "mode": data[0],
            "x0": to_f32(data, 1), "y0": to_f32(data, 5),
            "x1": to_f32(data, 9), "y1": to_f32(data, 13),
            "step_x": to_f32(data, 17), "step_y": to_f32(data, 21),
            "to_end_x": to_f32(data, 25), "to_end_y": to_f32(data, 29),
            "speed_x": to_f32(data, 33), "speed_y": to_f32(data, 37),
        }

    def tsh_home(self, slot: int) -> None:
        self._call_ack(slot, p.CMD_TSH_HOME)

    # ------------------------------------------------------------------
    # Monochromator (CH = MC index)
    # ------------------------------------------------------------------

    def mc_set_mode(self, index: int, mode: int) -> None:
        self._call_ack(index, p.CMD_MC_SET_MODE, bytes([mode & 0xFF]))

    def mc_get_status(self, index: int) -> "MCStatus":
        data = self._call(index, p.CMD_MC_GET_STATUS)
        return MCStatus(
            wave=to_f32(data, 0), pos_wave=to_f32(data, 4),
            fi=to_f32(data, 8), pos_gr=to_f32(data, 12),
            pos_lift=to_f32(data, 16), set_wave=to_f32(data, 20),
            reserved=to_u16(data, 24), cur_mode=data[26], status=data[27],
        )

    def mc_set_wave(self, index: int, wavelength: float) -> None:
        self._call_ack(index, p.CMD_MC_SET_WAVE, f32(wavelength))

    def mc_reinit(self, index: int) -> None:
        self._call_ack(index, p.CMD_MC_REINIT)

    # ------------------------------------------------------------------
    # Monochromator EEPROM (MC Params / Calibration)
    # ------------------------------------------------------------------
    # Per MC index i the EEPROM holds a 320-byte block at 2304 + i*320
    # (Monochromator.h: ADR_ABS_MC / ADR_MC_TOTAL, GIGA is page-aligned):
    #   +0          monochromatorParameters (28 bytes: 4 x u8,
    #               turretPos[4] f32, liftGratingChange + liftWorking f32)
    #   +64 + m*64  calibration of mode m (ADR_MC_CALIB / ADR_CALIB_TOTAL):
    #     +0        gratingCalibration (24 bytes: type u8, reserved0 u8,
    #               reserved1 u16, min/max/reserved2..4 f32)
    #     +24       calibrationType1/2 (ADR_CALIB_CALIB, 5 f32:
    #               x0/a/b/t/f  or  A/F0/L/R/xL)
    # There are no dedicated protocol commands for these - the device only
    # re-reads them on boot / mode change (cmd 117) / reinit.

    def _eeprom_read(self, start: int, length: int) -> bytes:
        """Read an arbitrary EEPROM range via 32-byte page reads (cmd 154)."""
        first, last = start // 32, (start + length - 1) // 32
        buf = b"".join(self.read_eeprom_page(pg)
                       for pg in range(first, last + 1))
        off = start - first * 32
        return buf[off:off + length]

    def _eeprom_write(self, start: int, data: bytes) -> None:
        """Patch an EEPROM range, read-modify-writing whole pages (cmd 155)."""
        first, last = start // 32, (start + len(data) - 1) // 32
        span = bytearray()
        for pg in range(first, last + 1):
            span += self.read_eeprom_page(pg)
        off = start - first * 32
        span[off:off + len(data)] = data
        for pg in range(first, last + 1):
            self.write_eeprom_page(
                pg, bytes(span[(pg - first) * 32:(pg - first) * 32 + 32]))

    def mc_read_params(self, index: int) -> dict:
        base = MC_EEPROM_BASE + index * MC_EEPROM_TOTAL
        d = self._eeprom_read(base, 28)
        return {
            "wave_channel": d[0], "grating_channel": d[1],
            "lift_channel": d[2], "reserved0": d[3],
            "turret_pos": [to_f32(d, 4 + 4 * k) for k in range(4)],
            "lift_grating_change": to_f32(d, 20),
            "lift_working": to_f32(d, 24),
        }

    def mc_write_params(self, index: int, wave_channel: int,
                        grating_channel: int, lift_channel: int,
                        reserved0: int, turret_pos,
                        lift_grating_change: float,
                        lift_working: float) -> None:
        d = bytearray(28)
        d[0] = wave_channel & 0xFF
        d[1] = grating_channel & 0xFF
        d[2] = lift_channel & 0xFF
        d[3] = reserved0 & 0xFF
        for k in range(4):
            d[4 + 4 * k:8 + 4 * k] = f32(turret_pos[k])
        d[20:24] = f32(lift_grating_change)
        d[24:28] = f32(lift_working)
        self._eeprom_write(MC_EEPROM_BASE + index * MC_EEPROM_TOTAL, bytes(d))

    def mc_read_calibration(self, index: int, mode: int) -> dict:
        base = (MC_EEPROM_BASE + index * MC_EEPROM_TOTAL
                + MC_CALIB_OFFSET + mode * MC_CALIB_TOTAL)
        d = self._eeprom_read(base, 44)
        return {
            "type": d[0], "reserved0": d[1], "reserved1": to_u16(d, 2),
            "min": to_f32(d, 4), "max": to_f32(d, 8),
            "reserved2": to_f32(d, 12), "reserved3": to_f32(d, 16),
            "reserved4": to_f32(d, 20),
            "pars": [to_f32(d, 24 + 4 * k) for k in range(5)],
        }

    def mc_write_calibration(self, index: int, mode: int, cal_type: int,
                             reserved0: int, reserved1: int, wave_min: float,
                             wave_max: float, reserved2: float,
                             reserved3: float, reserved4: float,
                             pars) -> None:
        d = bytearray(44)
        d[0] = cal_type & 0xFF
        d[1] = reserved0 & 0xFF
        d[2:4] = u16(reserved1)
        d[4:8] = f32(wave_min)
        d[8:12] = f32(wave_max)
        d[12:16] = f32(reserved2)
        d[16:20] = f32(reserved3)
        d[20:24] = f32(reserved4)
        for k in range(5):
            d[24 + 4 * k:28 + 4 * k] = f32(pars[k])
        base = (MC_EEPROM_BASE + index * MC_EEPROM_TOTAL
                + MC_CALIB_OFFSET + mode * MC_CALIB_TOTAL)
        self._eeprom_write(base, bytes(d))

    # ------------------------------------------------------------------
    # Shutter (CH = shutter ordinal)
    # ------------------------------------------------------------------

    def shutter_configure(self, index: int, pin: int, move_current: int,
                          move_time: int, hold_current: int,
                          interlock_pin: int) -> None:
        data = bytes([pin & 0xFF, move_current & 0xFF]) + u16(move_time) + \
            bytes([hold_current & 0xFF, interlock_pin & 0xFF])
        self._call_ack(index, p.CMD_SHUTTER_CONFIG, data)

    def shutter_get_params(self, index: int) -> dict:
        data = self._call(index, p.CMD_SHUTTER_GET_PARAMS)
        return {"pin": data[0], "move_current": data[1],
                "move_time": to_u16(data, 2), "hold_current": data[4],
                "interlock_pin": data[5]}

    def shutter_control(self, index: int, open_: bool) -> None:
        self._call_ack(index, p.CMD_SHUTTER_CONTROL,
                       bytes([1 if open_ else 0]))

    def shutter_read(self, index: int) -> tuple[int, int]:
        data = self._call(index, p.CMD_SHUTTER_READ)
        return data[0], data[1]

    # ------------------------------------------------------------------
    # Chopper (CH = hardware channel)
    # ------------------------------------------------------------------

    def chopper_set_pid(self, ch: int, kp: float, kd: float, ki: float) -> None:
        self._call_ack(ch, p.CMD_CHOPPER_SET_PID, f32(kp) + f32(kd) + f32(ki))

    def chopper_get_pid(self, ch: int) -> tuple[float, float, float]:
        data = self._call(ch, p.CMD_CHOPPER_GET_PID)
        return to_f32(data, 0), to_f32(data, 4), to_f32(data, 8)

    def chopper_preset(self, ch: int, code: int) -> None:
        """code 0..7 = SAVE, 128..143 = LOAD preset code-128."""
        self._call_ack(ch, p.CMD_CHOPPER_PRESET, bytes([code & 0xFF]))

    def chopper_set_divider(self, ch: int, hw_divider: int, sw_mult: int,
                            mode: int) -> None:
        self._call_ack(ch, p.CMD_CHOPPER_SET_DIVIDER,
                       bytes([hw_divider & 0xFF, sw_mult & 0xFF, mode & 0xFF]))

    def chopper_get_freq(self, ch: int) -> tuple[float, float]:
        data = self._call(ch, p.CMD_CHOPPER_GET_FREQ)
        return to_f32(data, 0), to_f32(data, 4)

    def chopper_set_phase(self, ch: int, phase: float) -> None:
        self._call_ack(ch, p.CMD_CHOPPER_SET_PHASE, f32(phase))

    def chopper_get_params(self, ch: int) -> dict:
        data = self._call(ch, p.CMD_CHOPPER_GET_PARAMS)
        return {"phase": to_f32(data, 0), "hw_divider": data[4],
                "int_freq": to_f32(data, 5), "hybrid": data[9],
                "sw_mult": data[10], "mode": data[11]}

    def chopper_set_freq(self, ch: int, freq: float, hybrid: int) -> None:
        self._call_ack(ch, p.CMD_CHOPPER_SET_FREQ, f32(freq) + bytes([hybrid & 0xFF]))

    def chopper_set_shutter(self, ch: int, shutter_channel: int,
                            delay: int, open_time: int,
                            sync_out_delay: float,
                            sync_out_duration: float) -> None:
        data = (bytes([shutter_channel & 0xFF]) + u32(delay) + u32(open_time) +
                f32(sync_out_delay) + f32(sync_out_duration))
        self._call_ack(ch, p.CMD_CHOPPER_SET_SHUTTER, data)

    def chopper_get_shutter(self, ch: int) -> dict:
        data = self._call(ch, p.CMD_CHOPPER_GET_SHUTTER)
        return {"shutter_channel": data[0], "delay": to_u32(data, 1),
                "open_time": to_u32(data, 5),
                "sync_out_delay": to_f32(data, 9),
                "sync_out_duration": to_f32(data, 13)}

    def chopper_arm_shutter(self, ch: int) -> None:
        self._call_ack(ch, p.CMD_CHOPPER_ARM_SHUTTER)

    # ------------------------------------------------------------------
    # Position sensor (CH = sensor ordinal)
    # ------------------------------------------------------------------

    def sensor_configure(self, index: int, chopper_channels: tuple[int, int],
                         chopper_speeds: tuple[float, float], fft_size: int,
                         fft_indices: tuple[int, int], smpl_chan: int,
                         ch_time: int) -> None:
        data = (bytes([chopper_channels[0] & 0xFF, chopper_channels[1] & 0xFF]) +
                u16(0) + f32(chopper_speeds[0]) + f32(chopper_speeds[1]) +
                u16(fft_size) + u16(fft_indices[0]) + u16(fft_indices[1]) +
                u16(smpl_chan) + u16(ch_time) + u16(0))
        self._call_ack(index, p.CMD_SENSOR_CONFIG, data)

    def sensor_get_params(self, index: int) -> dict:
        data = self._call(index, p.CMD_SENSOR_GET_PARAMS)
        return {"chopper_channels": (data[0], data[1]),
                "chopper_speeds": (to_f32(data, 4), to_f32(data, 8)),
                "fft_size": to_u16(data, 12),
                "fft_indices": (to_u16(data, 14), to_u16(data, 16)),
                "smpl_chan": to_u16(data, 18), "ch_time": to_u16(data, 20)}

    def sensor_get_pos(self, index: int) -> dict:
        data = self._call(index, p.CMD_SENSOR_GET_POS)
        return {"x": (to_f32(data, 0), to_f32(data, 13)),
                "y": (to_f32(data, 4), to_f32(data, 17)),
                "power": (to_f32(data, 8), to_f32(data, 21)),
                "count": data[26]}

    def sensor_measure(self, index: int, measure: bool, stream: bool) -> None:
        bits = (1 if measure else 0) | (2 if stream else 0)
        self._call_ack(index, p.CMD_SENSOR_MEASURE, bytes([bits]))

    # ------------------------------------------------------------------
    # Joystick (CH = joystick ordinal)
    # ------------------------------------------------------------------

    def joystick_get(self, index: int) -> dict:
        data = self._call(index, p.CMD_JOYSTICK_GET)
        return {"num": data[0],
                "bindings": [(data[1 + i * 2], data[2 + i * 2])
                             for i in range(4)]}

    def joystick_set(self, index: int, num: int,
                     bindings: list[tuple[int, int]]) -> None:
        payload = bytes([num & 0xFF])
        for x, y in bindings[:4]:
            payload += bytes([x & 0xFF, y & 0xFF])
        self._call_ack(index, p.CMD_JOYSTICK_SET, payload)

    # ------------------------------------------------------------------
    # SDG (board version 13) - StepV2_protocol/main.c uartProtocol()
    # ------------------------------------------------------------------

    # SDG enable targets (CH byte of cmd 84)
    SDG_CORE = 0          # ASOPS core timer (htim2)
    SDG_LOCK_CLOCK = 255  # lock/unlock to external oscillator

    def sdg_get_status(self, reset_counts: bool = False) -> dict:
        """cmd 85 - Status byte, measured oscillator frequency, pulse count.

        Status bits: 0=clkExt (locked), 1=core running, 2=core delay ramp
        active, 4..7 = channels 1..4 started.  CH=255 additionally resets
        the pulse counter (htim5 CNT).
        """
        data = self._call(self.SDG_LOCK_CLOCK if reset_counts else 0,
                          p.CMD_SDG_GET_STATUS)
        return {"status": data[0],
                "clock_osc": to_f32(data, 1),
                "counts": to_u32(data, 5)}

    def sdg_enable(self, target: int, on: bool) -> None:
        """cmd 84 - enable/disable a target.

        target: 0 = ASOPS core, 1..4 = output channels, 20 = start core
        delay ramp (enable only), 255 = lock (on) / unlock (off) clock.
        """
        self._call_ack(target, p.CMD_SDG_ENABLE, bytes([1 if on else 0]))

    def sdg_set_trig_level(self, which: int, value: float) -> None:
        """cmd 83 - which: 0 = clock trigger level, 1 = arming level (V)."""
        self._call_ack(0, p.CMD_SDG_SET_TRIG_LEVEL,
                       bytes([which]) + f32(value))

    def sdg_get_trig_level(self, which: int) -> float:
        """cmd 82 - reply is [which echo][f32] (float at data offset 1)."""
        return to_f32(self._call(0, p.CMD_SDG_GET_TRIG_LEVEL,
                                 bytes([which])), 1)

    def sdg_set_mco2(self, source: int, pre: int, m: int, n: int,
                     r: int) -> None:
        """cmd 81 - source 0=SYSCLK 1=PLLI2S 2=HSE 3=PLLCLK; pre 1..5 -> 0..4."""
        self._call_ack(0, p.CMD_SDG_SET_MCO2,
                       bytes([source & 0xFF, pre & 0xFF])
                       + u32(m) + u32(n) + u32(r))

    def sdg_get_mco2(self) -> dict:
        """cmd 80 - live MCO2 config read back from RCC registers."""
        d = self._call(0, p.CMD_SDG_GET_MCO2)
        return {"source": d[0], "pre": d[1], "m": to_u32(d, 2),
                "n": to_u32(d, 6), "r": to_u32(d, 10)}

    def sdg_set_period(self, period: int) -> None:
        """cmd 89 - period in cycles; 0=software arming, 1=external, 2=gate."""
        self._call_ack(0, p.CMD_SDG_SET_PERIOD, u32(period))

    def sdg_set_digital_delay(self, slot: int, delay: int) -> None:
        """cmd 88 - slot 0..7: even=rising/odd=falling edge of channel slot//2;
        slot 16..19 = misc/extra delays (19 = core pulse shift)."""
        self._call_ack(slot, p.CMD_SDG_SET_DIGITAL_DELAY, u32(delay))

    def sdg_set_analog_delay(self, slot: int, delay_ps: int) -> None:
        """cmd 87 - slot 0..7, high-precision delay in picoseconds (u16)."""
        self._call_ack(slot, p.CMD_SDG_SET_ANALOG_DELAY, u16(delay_ps))

    def sdg_get_delay(self, selector: int) -> int:
        """cmd 86 - selector: 255=period, 0..7=digital slot,
        16..20=extra/misc slot, 64..71=analog slot (selector-64)."""
        return to_u32(self._call(selector, p.CMD_SDG_GET_DELAYS))

    def sdg_save(self) -> None:
        """cmd 164 - write the whole SDGParams struct to flash sector 7."""
        self._call_ack(0, p.CMD_SDG_SAVE, timeout=3.0)

    # ------------------------------------------------------------------
    # FreqGen (board version 14) - one command does it all (cmd 131)
    # ------------------------------------------------------------------

    def freqgen_frequency(self, frequency: float | None = None) -> float:
        """cmd 131 - write f32 frequency in Hz, reply is the actual value.

        ``frequency=None`` (or any negative value, e.g. -1) queries the
        current setting without updating the device; values > 0 set the new
        frequency. Either way the device returns the actual value (f32).
        """
        data = self._call(0, p.CMD_FREQGEN_FREQUENCY,
                          f32(-1.0 if frequency is None else frequency))
        return to_f32(data)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass
class MotorConfig:
    """cmd 144 reply - 38 bytes, all floats little-endian."""
    move_speed: float
    backlash: float
    acceleration: float  # units/s^2
    step_value: float
    home_position: float
    scale_max: float
    microsteps_code: int
    bpar: int
    homing_speed: float
    homing_speed2: float
    scale_min: float
    channel: int = 0

    # bPar bitfield (ADR_BITPARAMS)
    BP_AUTO_HOME_DIR = 1 << 0
    BP_HOME2 = 1 << 2
    BP_AUTO_CORR = 1 << 3
    BP_INVERT_HOME = 1 << 5
    BP_SCALE_REVERSED = 1 << 6
    BP_FULL_STEPS = 1 << 7

    def flags(self) -> dict[str, bool]:
        return {
            "auto home direction": bool(self.bpar & self.BP_AUTO_HOME_DIR),
            "two-stage homing (home2)": bool(self.bpar & self.BP_HOME2),
            "auto correction": bool(self.bpar & self.BP_AUTO_CORR),
            "invert home polarity": bool(self.bpar & self.BP_INVERT_HOME),
            "reversed scale direction": bool(self.bpar & self.BP_SCALE_REVERSED),
            "full steps only": bool(self.bpar & self.BP_FULL_STEPS),
        }

    def as_bpar(self, flags: dict[str, bool]) -> int:
        value = self.bpar & ~0xDD  # clear the six documented bits (0b11011101)
        if flags.get("auto home direction"):
            value |= self.BP_AUTO_HOME_DIR
        if flags.get("two-stage homing (home2)"):
            value |= self.BP_HOME2
        if flags.get("auto correction"):
            value |= self.BP_AUTO_CORR
        if flags.get("invert home polarity"):
            value |= self.BP_INVERT_HOME
        if flags.get("reversed scale direction"):
            value |= self.BP_SCALE_REVERSED
        if flags.get("full steps only"):
            value |= self.BP_FULL_STEPS
        return value


@dataclass
class AdvancedParams:
    """advancedParameters struct - 8 bytes raw little-endian."""
    second_backlash: float
    u_steps_diff: int
    max_retr_num: int
    ihold: int


@dataclass
class MCStatus:
    """MonochromatorStatus - 28 bytes."""
    wave: float
    pos_wave: float
    fi: float
    pos_gr: float
    pos_lift: float
    set_wave: float
    reserved: int
    cur_mode: int
    status: int

    def status_text(self) -> str:
        status = self.status
        if status == 0:
            return "not homed / not initialized"
        if status == 100:
            return "idle"
        if status == 255:
            return "not configured"
        if 1 <= status <= 15:
            return f"homing step {status}"
        if 31 <= status <= 39:
            return f"changing grating ({status})"
        if status == 51:
            return "moving wavelength"
        if status in (104, 108, 114):
            kind = {104: "lift", 108: "grating", 114: "wave"}[status]
            return f"homing error ({kind})"
        return f"status {status}"
