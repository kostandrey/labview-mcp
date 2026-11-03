"""UDP transport to the UFS COM_PortService.

The COM_PortService multiplexes UDP clients onto serial COM ports:

  * Each configured COM device is exposed on its own local UDP port
    (e.g. COM3 -> 50000, COM7 -> 50001).
  * The server injects/encodes the Request-ID byte into outgoing requests and
    strips it from replies, so the client just sends/receives plain StepV2
    frames (with CRC).
  * Transport failures are reported as synthetic packets
    [ADR][4][CH][0xFF][ErrorCode][CRC]  (0x01 timeout, 0x02 offline).
  * A UDP broadcast to port 49999 returns a JSON description of all
    configured devices (discovery).
"""

from __future__ import annotations

import json
import socket
import threading
import time

from .protocol import (REPLY_TRANSPORT_ERROR, TRANSPORT_ERRORS, build_packet,
                       parse_packet)

DISCOVERY_PORT = 49999
DEFAULT_TIMEOUT = 3.5  # must exceed the server's requestTimeoutMs (2000) so its
                       # synthetic error packets are received and decoded


class TransportError(Exception):
    pass


class DeviceOffline(TransportError):
    pass


class TimeoutError_(TransportError):
    pass


class ComPortService:
    """Client for one COM_PortService UDP device endpoint.

    The socket is bound once and kept open for the whole session (R6): the
    server keys the ClientID by <IP:Port>, so a rebound socket would get a
    new ClientID.  A background keepalive re-registers the endpoint whenever
    the session is idle, so the ClientID is not recycled after
    clientTimeoutSeconds (default 60 s, R7).
    """

    # re-register the endpoint after this much idle time (must stay well
    # below the server's clientTimeoutSeconds = 60)
    KEEPALIVE_IDLE_S = 40.0
    KEEPALIVE_POLL_S = 5.0

    def __init__(self, host: str = "127.0.0.1", udp_port: int = 50000,
                 com_port: str = "", timeout: float = DEFAULT_TIMEOUT):
        self.host = host
        self.udp_port = udp_port
        self.com_port = com_port
        self.timeout = timeout
        self.default_adr = 1  # device ADR used for keepalive pings
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("0.0.0.0", 0))
        # RLock, not Lock: the keepalive loop already holds the lock when it
        # calls _transact(), which re-acquires it.  A plain Lock would
        # self-deadlock the keepalive thread after the first idle period and
        # block every later request on this session.
        self._lock = threading.RLock()
        self._last_activity = time.time()
        self._stop = threading.Event()
        self._next_keepalive_id = 0
        self._keepalive_thread = threading.Thread(
            target=self._keepalive_loop, daemon=True, name="stepv2-keepalive")
        self._keepalive_thread.start()

    # -- lifecycle ----------------------------------------------------------

    def close(self) -> None:
        self._stop.set()
        with self._lock:
            self._sock.close()

    def _keepalive_loop(self) -> None:
        """Touch the endpoint while the session is idle (CLIENT_ID_BYTE_
        REQUIREMENTS R7).  Uses the same lock as _transact, so a keepalive is
        never sent while a real request is in flight (R8), and always uses a
        fresh Request-ID.  A harmless device-level read (cmd 174) is used as
        the ping; the reply is discarded.
        """
        while not self._stop.wait(self.KEEPALIVE_POLL_S):
            with self._lock:
                if self._stop.is_set():
                    return
                if time.time() - self._last_activity < self.KEEPALIVE_IDLE_S:
                    continue
                pkt = build_packet(self.default_adr, 0, 174, b"",
                                   request_id=self._next_keepalive_id)
                self._next_keepalive_id = (self._next_keepalive_id + 1) % 31
                try:
                    self._transact(pkt, self.timeout, expected_request_id=None)
                except (TransportError, OSError):
                    pass  # endpoint gone or busy; the next request will report it
                finally:
                    self._last_activity = time.time()

    # -- discovery ----------------------------------------------------------

    @staticmethod
    def discover(host: str | None = None,
                 timeout: float = 1.5) -> list[dict]:
        """Send discovery queries; returns the parsed device list.

        Each device dict contains comPort / udpPort / baudRate / online /
        description keys (JSON produced by WindowsService::getDiscoveryJson).
        Queries the explicit `host` when given; otherwise broadcasts and also
        unicasts the loopback and own-LAN addresses, so servers running on
        the local machine are found even when broadcast reception is blocked
        by the Windows firewall for this executable.
        """
        if host is not None:
            targets = [host]
        else:
            targets = ["255.255.255.255", "127.0.0.1"]
            try:
                hostname_ip = socket.gethostbyname(socket.gethostname())
                if hostname_ip not in targets:
                    targets.append(hostname_ip)
            except OSError:
                pass
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.3)
        for target in targets:
            try:
                sock.sendto(b"discover", (target, DISCOVERY_PORT))
            except OSError:
                continue
        deadline = time.time() + timeout
        devices: list[dict] = []
        servers: list[dict] = []
        while time.time() < deadline:
            sock.settimeout(max(0.05, deadline - time.time()))
            try:
                payload, addr = sock.recvfrom(8192)
            except socket.timeout:
                break
            except OSError:
                break
            try:
                doc = json.loads(payload.decode("utf-8", "replace"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not isinstance(doc, dict) or doc.get("service") != "ComPortServer":
                continue
            doc["_source"] = f"{addr[0]}"
            servers.append(doc)
        sock.close()
        for doc in servers:
            host_addr = doc.pop("_source", "")
            for dev in doc.get("devices", []):
                if isinstance(dev, dict):
                    dev.setdefault("server", host_addr)
                    devices.append(dev)
        # de-duplicate identical (comPort, udpPort) entries; prefer the
        # loopback endpoint for local servers (ACL-friendly)
        best: dict[tuple, dict] = {}
        for dev in devices:
            key = (dev.get("comPort"), dev.get("udpPort"))
            prior = best.get(key)
            if prior is None:
                best[key] = dev
                continue
            def rank(d):
                return (d.get("server") == "127.0.0.1",
                        bool(d.get("online", d.get("isOnline"))))
            if rank(dev) > rank(prior):
                best[key] = dev
        return list(best.values())

    # -- request / response ---------------------------------------------------

    def request(self, packet: bytes, timeout: float | None = None,
                expected_request_id: int | None = None) -> dict:
        """Send one request frame and wait for the matching reply frame.

        The reply is matched by its echoed Request-ID byte: packets carrying
        any other Request-ID (stale/late replies to earlier requests) are
        discarded and we keep waiting.  Raises TimeoutError_ / DeviceOffline
        on transport errors reported by the server, TransportError on local
        socket failures.
        """
        timeout = timeout if timeout is not None else self.timeout
        return self._transact(packet, timeout, expected_request_id)

    def _transact(self, packet: bytes, timeout: float,
                  expected_request_id: int | None = None) -> dict:
        with self._lock:
            sock = self._sock
            try:
                sock.sendto(packet, (self.host, self.udp_port))
            except OSError as exc:
                raise TransportError(f"UDP send failed: {exc}") from exc
            self._last_activity = time.time()
            deadline = time.time() + timeout
            while True:
                remaining = deadline - time.time()
                if remaining <= 0:
                    raise TimeoutError_(
                        f"no reply from {self.com_port or self.host}:{self.udp_port}"
                        f" within {timeout:.1f} s")
                sock.settimeout(remaining)
                try:
                    payload, _addr = sock.recvfrom(512)
                except socket.timeout:
                    continue
                except OSError as exc:
                    raise TransportError(f"UDP recv failed: {exc}") from exc
                parsed = parse_packet(payload)
                if not parsed.get("crc_ok"):
                    continue  # stray serial noise forwarded as-is; keep waiting
                if (expected_request_id is not None
                        and parsed.get("request_id") != expected_request_id):
                    continue  # stale reply to an earlier request; keep waiting
                if parsed["cmd"] == REPLY_TRANSPORT_ERROR:
                    code = parsed["data"][0] if parsed["data"] else 0
                    text = TRANSPORT_ERRORS.get(code, f"error 0x{code:02X}")
                    if code == 0x02:
                        raise DeviceOffline(f"COM port offline ({text})")
                    raise TimeoutError_(f"device timeout ({text})")
                return parsed


class BackgroundWorker:
    """Run blocking transport calls off the Tk main thread.

    Callers submit (fn, args, on_done, on_error); results are delivered via
    a callback executed on the Tk thread through `tk_after` (must be a
    Tk.after bound method; the callback is scheduled with a 0 ms delay).
    """

    def __init__(self, tk_after):
        self._tk_after = tk_after
        self._threads: list[threading.Thread] = []

    def submit(self, fn, *args, on_done=None, on_error=None, **kwargs):
        def run():
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - surfaced to the UI
                if on_error:
                    self._tk_after(0, lambda e=exc: on_error(e))
            else:
                if on_done:
                    self._tk_after(0, lambda r=result: on_done(r))

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        self._threads = [t for t in self._threads if t.is_alive()]
        self._threads.append(thread)

    def busy(self) -> bool:
        return any(t.is_alive() for t in self._threads)
