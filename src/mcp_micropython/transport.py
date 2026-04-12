"""
transport.py — serial / WebREPL transport implementations.
"""

from __future__ import annotations

import errno
import os
import socket
import struct
import time
from dataclasses import dataclass
from typing import Protocol

import serial
import serial.tools.list_ports

DEFAULT_SERIAL_BAUDRATE = 115200
DEFAULT_IO_TIMEOUT = 1.0
DEFAULT_WEBREPL_PORT = 8266
WS_TEXT_FRAME = 0x81
WS_BINARY_FRAME = 0x82


class TransportError(Exception):
    """Base transport error."""


class UnsupportedOperationError(TransportError):
    """Operation is not supported by the current transport."""


class StreamTransport(Protocol):
    """Minimal stream-like interface for Raw REPL and log capture."""

    @property
    def transport_name(self) -> str:
        ...

    def connection_details(self) -> dict[str, object]:
        ...

    @property
    def is_connected(self) -> bool:
        ...

    def close(self) -> None:
        ...

    def send_bytes(self, data: bytes) -> None:
        ...

    def read_some(self, timeout: float) -> bytes:
        ...

    def drain_pending_input(self) -> None:
        ...

    def flush(self) -> None:
        ...

    def interrupt(self) -> None:
        ...

    def reset_and_capture(
        self,
        capture_duration: float,
        idle_timeout: float | None = None,
        max_bytes: int | None = None,
    ) -> dict[str, object]:
        ...


@dataclass
class TargetSpec:
    kind: str
    target: str
    port: int | None = None


def list_serial_ports() -> list[dict[str, str]]:
    ports: list[dict[str, str]] = []
    for p in serial.tools.list_ports.comports():
        ports.append({
            "port": p.device,
            "description": p.description or "",
            "hwid": p.hwid or "",
        })
    return ports


def parse_target(target: str) -> TargetSpec:
    raw = target.strip()
    if not raw:
        raise ValueError("target must not be empty")

    upper = raw.upper()
    if upper.startswith("COM") and raw[3:].isdigit():
        return TargetSpec(kind="serial", target=raw)
    if raw.startswith("/dev/tty") or raw.startswith("/dev/cu"):
        return TargetSpec(kind="serial", target=raw)

    if ":" in raw:
        host, port_text = raw.rsplit(":", 1)
        if not host:
            raise ValueError("host must not be empty")
        try:
            port = int(port_text)
        except ValueError as e:
            raise ValueError(f"invalid port in target: {raw}") from e
        return TargetSpec(kind="webrepl", target=host, port=port)

    return TargetSpec(kind="webrepl", target=raw, port=DEFAULT_WEBREPL_PORT)


class SerialTransport:
    def __init__(self, port: str, baudrate: int = DEFAULT_SERIAL_BAUDRATE) -> None:
        self._serial = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=DEFAULT_IO_TIMEOUT,
            write_timeout=DEFAULT_IO_TIMEOUT,
        )

    @property
    def transport_name(self) -> str:
        return "serial"

    def connection_details(self) -> dict[str, object]:
        return {
            "transport": self.transport_name,
            "target": self._serial.port,
            "port": self._serial.port,
            "baudrate": self._serial.baudrate,
        }

    @property
    def is_connected(self) -> bool:
        return self._serial.is_open

    def close(self) -> None:
        if self._serial.is_open:
            self._serial.close()

    def send_bytes(self, data: bytes) -> None:
        self._serial.write(data)

    def read_some(self, timeout: float) -> bytes:
        previous = self._serial.timeout
        self._serial.timeout = max(timeout, 0.0)
        try:
            return self._serial.read(self._serial.in_waiting or 1)
        finally:
            self._serial.timeout = previous

    def drain_pending_input(self) -> None:
        self._serial.reset_input_buffer()

    def flush(self) -> None:
        self._serial.flush()

    def interrupt(self) -> None:
        self.send_bytes(b"\x03")
        self.flush()

    def reset_and_capture(
        self,
        capture_duration: float,
        idle_timeout: float | None = None,
        max_bytes: int | None = None,
    ) -> dict[str, object]:
        self._serial.reset_input_buffer()
        self._serial.write(b"\x04")
        self._serial.flush()

        deadline = time.monotonic() + capture_duration
        last_data_at: float | None = None
        buffer = bytearray()
        truncated = False

        while time.monotonic() < deadline:
            if idle_timeout is not None and last_data_at is not None:
                if time.monotonic() - last_data_at >= idle_timeout:
                    break

            chunk = self.read_some(min(DEFAULT_IO_TIMEOUT, max(deadline - time.monotonic(), 0.0)))
            if not chunk:
                continue

            if max_bytes is not None:
                remaining = max_bytes - len(buffer)
                if remaining <= 0:
                    truncated = True
                    break
                if len(chunk) > remaining:
                    buffer.extend(chunk[:remaining])
                    truncated = True
                    break

            buffer.extend(chunk)
            last_data_at = time.monotonic()

        return {
            "stdout": buffer.decode("utf-8", errors="replace"),
            "truncated": truncated,
            "bytes_read": len(buffer),
            "reset_ok": True,
        }


class _SimpleWebSocket:
    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock
        self._recv_buffer = bytearray()

    def _recv_exactly(self, size: int, timeout: float) -> bytes:
        previous = self._sock.gettimeout()
        self._sock.settimeout(timeout)
        try:
            while len(self._recv_buffer) < size:
                needed = size - len(self._recv_buffer)
                recv_size = min(max(needed, 4096), 65536)
                try:
                    chunk = self._sock.recv(recv_size)
                except BlockingIOError as e:
                    raise socket.timeout("timed out waiting for websocket data") from e
                except OSError as e:
                    if e.errno == errno.EWOULDBLOCK or getattr(e, "winerror", None) == 10035:
                        raise socket.timeout("timed out waiting for websocket data") from e
                    raise
                if not chunk:
                    raise ConnectionError("websocket connection closed")
                self._recv_buffer.extend(chunk)
            data = bytes(self._recv_buffer[:size])
            del self._recv_buffer[:size]
            return data
        finally:
            self._sock.settimeout(previous)

    def write(self, data: bytes, frame_type: int = WS_TEXT_FRAME) -> None:
        payload_len = len(data)
        mask_key = os.urandom(4)
        masked_payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(data))
        if payload_len < 126:
            header = struct.pack(">BB", frame_type, 0x80 | payload_len)
        elif payload_len < 65536:
            header = struct.pack(">BBH", frame_type, 0x80 | 126, payload_len)
        else:
            raise ValueError("payload too large")
        self._sock.sendall(header + mask_key + masked_payload)

    def append_buffer(self, data: bytes) -> None:
        if data:
            self._recv_buffer.extend(data)

    def _read_frame_payload(self, timeout: float, text_ok: bool = True) -> bytes:
        while True:
            try:
                header = self._recv_exactly(2, timeout)
            except socket.timeout as e:
                raise TimeoutError("timed out waiting for websocket data") from e
            opcode, payload_len = struct.unpack(">BB", header)
            frame_opcode = opcode & 0x0F
            masked = bool(payload_len & 0x80)
            payload_len &= 0x7F
            if payload_len == 126:
                try:
                    payload_len = struct.unpack(">H", self._recv_exactly(2, timeout))[0]
                except socket.timeout as e:
                    raise TimeoutError("timed out waiting for websocket data") from e
            elif payload_len == 127:
                try:
                    payload_len = struct.unpack(">Q", self._recv_exactly(8, timeout))[0]
                except socket.timeout as e:
                    raise TimeoutError("timed out waiting for websocket data") from e

            mask_key = b""
            if masked:
                try:
                    mask_key = self._recv_exactly(4, timeout)
                except socket.timeout as e:
                    raise TimeoutError("timed out waiting for websocket data") from e

            try:
                payload = self._recv_exactly(payload_len, timeout)
            except socket.timeout as e:
                raise TimeoutError("timed out waiting for websocket data") from e
            if masked:
                payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
            if frame_opcode == 0x8:
                raise ConnectionError("websocket connection closed")
            if frame_opcode not in (0x1, 0x2):
                continue
            if frame_opcode == 0x1 and not text_ok:
                continue
            return payload

    def read_frame(self, timeout: float, text_ok: bool = True) -> bytes:
        return self._read_frame_payload(timeout, text_ok=text_ok)


class WebReplTransport:
    def __init__(self, host: str, port: int, password: str) -> None:
        if not password:
            raise ValueError("password is required for WebREPL connections")

        self._host = host
        self._port = port
        self._password = password
        self._socket = socket.create_connection((host, port), timeout=5.0)
        self._socket.settimeout(DEFAULT_IO_TIMEOUT)
        self._ws = _SimpleWebSocket(self._socket)
        self._handshake()
        self._login()

    @property
    def transport_name(self) -> str:
        return "webrepl"

    def connection_details(self) -> dict[str, object]:
        return {
            "transport": self.transport_name,
            "target": f"{self._host}:{self._port}",
            "host": self._host,
            "port": self._port,
        }

    @property
    def is_connected(self) -> bool:
        return self._socket.fileno() != -1

    def close(self) -> None:
        try:
            self._socket.close()
        except OSError:
            pass

    def send_bytes(self, data: bytes) -> None:
        self._ws.write(data, frame_type=WS_TEXT_FRAME)

    def read_some(self, timeout: float) -> bytes:
        try:
            return self._ws.read_frame(timeout=timeout, text_ok=True)
        except TimeoutError:
            return b""

    def drain_pending_input(self) -> None:
        while True:
            try:
                chunk = self.read_some(timeout=0.05)
            except Exception:
                break
            if not chunk:
                break

    def flush(self) -> None:
        return None

    def interrupt(self) -> None:
        self.send_bytes(b"\x03")

    def reset_and_capture(
        self,
        capture_duration: float,
        idle_timeout: float | None = None,
        max_bytes: int | None = None,
    ) -> dict[str, object]:
        raise UnsupportedOperationError("reset_and_capture is only supported over serial")

    def _handshake(self) -> None:
        request = (
            "GET / HTTP/1.1\r\n"
            "Host: echo.websocket.org\r\n"
            "Connection: Upgrade\r\n"
            "Upgrade: websocket\r\n"
            "Sec-WebSocket-Key: foo\r\n"
            "\r\n"
        ).encode("ascii")
        self._socket.sendall(request)
        response, remaining = self._read_http_headers()
        if "101" not in response.splitlines()[0]:
            raise ConnectionError(f"websocket handshake failed: {response.splitlines()[0]}")
        self._ws.append_buffer(remaining)

    def _read_http_headers(self) -> tuple[str, bytes]:
        data = bytearray()
        while b"\r\n\r\n" not in data:
            chunk = self._socket.recv(1024)
            if not chunk:
                raise ConnectionError("websocket handshake failed: no response")
            data.extend(chunk)
        header_block, _, remaining = data.partition(b"\r\n\r\n")
        return header_block.decode("utf-8", errors="replace"), bytes(remaining)

    def _login(self) -> None:
        prompt = bytearray()
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            chunk = self.read_some(timeout=0.5)
            if not chunk:
                continue
            prompt.extend(chunk)
            if b": " in prompt:
                self.send_bytes(self._password.encode("utf-8") + b"\r")
                return
        raise TimeoutError("did not receive WebREPL password prompt")
