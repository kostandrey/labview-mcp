"""TshController - the hardware-facing core of the converted
'Continuous2D moco' application, on top of the vendored stepv2 client.

Replaces the original chain
    Global Send Data.vi -> MoveMotConConQ -> ArduStepMoCo Main.vi
    -> RSt_* frame builders -> SharedCOM/Remote_UDP -> ComPortService
with direct stepv2.Device calls over the ComPortService UDP transport
(the only transport required in the simplified scope).

The UI runs in the tkinter main thread; all device I/O goes through a
single worker thread fed by a command queue - the same decoupling the
original achieved with queues + a notifier.
"""
from __future__ import annotations

import json
import queue
import socket
import threading
import time
from dataclasses import dataclass

from stepv2.commands import Device
from stepv2.transport import ComPortService, TransportError

from .config import Settings
from .patterns import TshStartArgs

DISCOVERY_PORT = 49999

# per-channel status byte (cmd 110 get_position): bit0 = moving,
# bit1 = home sensor active - as used by 'Get Move status moco.vi'
STATUS_MOVING = 0x01


@dataclass
class TshStatus:
    x: float
    y: float
    moving_x: bool
    moving_y: bool

    @property
    def stopped(self) -> bool:
        return not (self.moving_x or self.moving_y)


class TshController:
    """One TSH group (two coupled motors) on one StepV2 device."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.conn: ComPortService | None = None
        self.dev: Device | None = None
        self.group_slot: int = settings.arduino.group
        self.ch_x: int | None = None
        self.ch_y: int | None = None
        self._cmd_q: "queue.Queue[tuple]" = queue.Queue()
        self._worker: threading.Thread | None = None
        self._stop_evt = threading.Event()

    # ------------------------------------------------------------ discovery
    @staticmethod
    def discover(host: str | None = None, timeout: float = 1.0) -> list[dict]:
        """UDP broadcast to the ComPortService discovery port; returns the
        JSON device list (com name, udp port, baud, online)."""
        payload = b"discover"
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(timeout)
        answers: dict[str, dict] = {}
        try:
            sock.sendto(payload, ("<broadcast>" if host is None else host,
                                  DISCOVERY_PORT))
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    data, addr = sock.recvfrom(65535)
                except socket.timeout:
                    break
                try:
                    desc = json.loads(data.decode("utf-8", "replace"))
                except (ValueError, UnicodeDecodeError):
                    continue
                answers[f"{addr[0]}"] = desc
        finally:
            sock.close()
        devices: list[dict] = []
        for desc in answers.values():
            ports = desc.get("ports") or desc.get("devices") or []
            if isinstance(ports, list):
                devices.extend(ports)
            else:
                devices.append(desc)
        return devices

    # ------------------------------------------------------------ lifecycle
    def connect(self, udp_port: int | None = None,
                com_name: str | None = None) -> None:
        """Open the UDP endpoint; if udp_port is None it is resolved from
        the discovery list by COM-port name."""
        self.disconnect()
        if udp_port is None:
            udp_port = self._resolve_udp_port(com_name
                                              or self.settings.arduino.com)
        self.conn = ComPortService(udp_port=udp_port,
                                   com_port=com_name or "",
                                   timeout=3.5)
        self.dev = Device(self.conn, adr=self.settings.arduino.address)
        self.group_slot = self.settings.arduino.group
        self._stop_evt.clear()
        self._worker = threading.Thread(target=self._worker_loop,
                                        name="moco-worker", daemon=True)
        self._worker.start()

    def _resolve_udp_port(self, com_name: str) -> int:
        for dev in self.discover():
            name = str(dev.get("com") or dev.get("port") or "")
            if name.upper() == com_name.upper():
                return int(dev.get("udpPort") or dev.get("udp_port"))
        raise ConnectionError(
            f"COM port {com_name!r} not announced by ComPortService "
            f"(discovery); pass udp_port explicitly if the service is "
            f"remote")

    def disconnect(self) -> None:
        self._stop_evt.set()
        if self._worker:
            self._worker.join(timeout=2.0)
            self._worker = None
        if self.conn:
            self.conn.close()
            self.conn = None
            self.dev = None

    @property
    def connected(self) -> bool:
        return self.dev is not None

    # ------------------------------------------------------------ worker
    def submit(self, fn, *args, on_done=None, on_error=None, **kwargs):
        """Queue fn(*args, **kwargs) for the worker thread; callbacks fire
        on the worker thread (the UI marshals them itself)."""
        self._cmd_q.put((fn, args, kwargs, on_done, on_error))

    def _worker_loop(self) -> None:
        while not self._stop_evt.is_set():
            try:
                fn, args, kwargs, on_done, on_error = \
                    self._cmd_q.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - surfaced to UI
                if on_error:
                    on_error(exc)
            else:
                if on_done:
                    on_done(result)

    # ------------------------------------------------------------ device ops
    def _dev(self) -> Device:
        if self.dev is None:
            raise ConnectionError("not connected")
        return self.dev

    def read_identity(self) -> dict:
        d = self._dev()
        info = {"sketch_ver": d.get_sketch_ver(),
                "board_ver": d.get_board_ver()}
        self.ch_x, self.ch_y = d.group_get_2(self.group_slot)
        info["group"] = (self.group_slot, self.ch_x, self.ch_y)
        return info

    def group_channels(self) -> tuple[int, int]:
        """(chX, chY) of the configured group; reads once from the device
        if not known yet."""
        if self.ch_x is None or self.ch_y is None:
            self.ch_x, self.ch_y = self._dev().group_get_2(self.group_slot)
        return self.ch_x, self.ch_y

    def home(self) -> None:
        self._dev().tsh_home(self.group_slot)

    def home_status(self) -> tuple[int, int]:
        """(stateX, stateY) of the group channels; 0 = idle/finish per
        firmware (cmd 101)."""
        d = self._dev()
        cx, cy = self.group_channels()
        return d.get_home_status(cx)[0], d.get_home_status(cy)[0]

    def go_initial(self, x0: float, y0: float) -> None:
        """'Go Initial!' - move to the pattern start point (cmd 142)."""
        self._dev().tsh_go_pos(self.group_slot, x0, y0)

    def start_pattern(self, args: TshStartArgs) -> None:
        """'GO!' - the firmware executes the pattern (cmd 134)."""
        d = self._dev()
        d.tsh_start(self.group_slot, args.mode, args.x0, args.y0,
                    args.x1, args.y1, args.step_x, args.step_y,
                    args.to_end_x, args.to_end_y,
                    args.speed_x, args.speed_y)

    def stop(self) -> None:
        self._dev().tsh_stop(self.group_slot)

    def get_pos(self) -> tuple[float, float]:
        return self._dev().tsh_get_pos(self.group_slot)

    def status(self) -> TshStatus:
        """Composite of the original 'Get Move status moco.vi':
        group position + per-channel Moving? flags."""
        d = self._dev()
        x, y = d.tsh_get_pos(self.group_slot)
        cx, cy = self.group_channels()
        moving_x = bool(d.get_position(cx)[1] & STATUS_MOVING)
        moving_y = bool(d.get_position(cy)[1] & STATUS_MOVING)
        return TshStatus(x=x, y=y, moving_x=moving_x, moving_y=moving_y)

    def get_bounds(self) -> dict:
        return self._dev().tsh_get_bounds(self.group_slot)

    def set_speed(self, ch: int, value: float) -> None:
        self._dev().set_speed(ch, value)
