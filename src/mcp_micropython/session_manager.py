"""
session_manager.py — transport-agnostic session management.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import Generator

from .raw_repl import RawRepl, ReplResult
from .transport import (
    DEFAULT_SERIAL_BAUDRATE,
    SerialTransport,
    StreamTransport,
    UnsupportedOperationError,
    WebReplTransport,
    list_serial_ports,
    parse_target,
)


class NotConnectedError(Exception):
    """Raised when the session is not connected."""


class SessionManager:
    def __init__(self) -> None:
        self._transport: StreamTransport | None = None
        self._lock = threading.RLock()

    @staticmethod
    def list_ports() -> list[dict[str, str]]:
        return list_serial_ports()

    def connect(
        self,
        target: str,
        baudrate: int = DEFAULT_SERIAL_BAUDRATE,
        password: str | None = None,
    ) -> dict[str, object]:
        spec = parse_target(target)
        with self._lock:
            self.disconnect()
            if spec.kind == "serial":
                self._transport = SerialTransport(spec.target, baudrate=baudrate)
            else:
                self._transport = WebReplTransport(spec.target, spec.port or 8266, password or "")
            return self.connection_status()

    def disconnect(self) -> None:
        with self._lock:
            if self._transport is not None:
                self._transport.close()
            self._transport = None

    @property
    def is_connected(self) -> bool:
        return self._transport is not None and self._transport.is_connected

    @property
    def transport_name(self) -> str | None:
        return self._transport.transport_name if self._transport else None

    def connection_status(self) -> dict[str, object]:
        if not self._transport:
            return {"connected": False, "transport": None, "target": None}
        status = dict(self._transport.connection_details())
        status["connected"] = self._transport.is_connected
        return status

    def require_serial_connection(self) -> None:
        self._ensure_connected()
        if self.transport_name != "serial":
            raise UnsupportedOperationError("this operation requires an active serial connection")

    def read_stream(
        self,
        duration: float,
        idle_timeout: float | None = None,
        max_bytes: int | None = None,
    ) -> dict[str, object]:
        return self._read_stream(timeout=duration, idle_timeout=idle_timeout, max_bytes=max_bytes)

    def read_until(
        self,
        pattern: str,
        timeout: float,
        max_bytes: int | None = None,
    ) -> dict[str, object]:
        return self._read_stream(
            timeout=timeout,
            max_bytes=max_bytes,
            pattern=pattern.encode("utf-8"),
        )

    def reset_and_capture(
        self,
        capture_duration: float,
        idle_timeout: float | None = None,
        max_bytes: int | None = None,
    ) -> dict[str, object]:
        with self._lock:
            transport = self._ensure_connected()
            return transport.reset_and_capture(
                capture_duration=capture_duration,
                idle_timeout=idle_timeout,
                max_bytes=max_bytes,
            )

    def interrupt(self) -> None:
        with self._lock:
            transport = self._ensure_connected()
            transport.interrupt()
            transport.flush()

    def exec_code(self, code: str, timeout: float = 10.0) -> ReplResult:
        with self._lock:
            transport = self._ensure_connected()
            repl = RawRepl(transport)
            return repl.exec_code_safe(code, timeout=timeout)

    def eval_expr(self, expression: str) -> ReplResult:
        return self.exec_code(f"print({expression})", timeout=5.0)

    @contextmanager
    def raw_repl(self) -> Generator[RawRepl, None, None]:
        with self._lock:
            transport = self._ensure_connected()
            yield RawRepl(transport)

    def _ensure_connected(self) -> StreamTransport:
        if not self.is_connected or self._transport is None:
            raise NotConnectedError(
                "MicroPython ボードに接続されていません。micropython_connect ツールで接続してください。"
            )
        return self._transport

    def _read_stream(
        self,
        timeout: float,
        idle_timeout: float | None = None,
        max_bytes: int | None = None,
        pattern: bytes | None = None,
    ) -> dict[str, object]:
        if timeout < 0:
            raise ValueError("timeout must be >= 0")
        if idle_timeout is not None and idle_timeout < 0:
            raise ValueError("idle_timeout must be >= 0")
        if max_bytes is not None and max_bytes <= 0:
            raise ValueError("max_bytes must be > 0")

        with self._lock:
            transport = self._ensure_connected()
            deadline = time.monotonic() + timeout
            last_data_at: float | None = None
            buffer = bytearray()
            matched = False
            truncated = False

            while time.monotonic() < deadline:
                if idle_timeout is not None and last_data_at is not None:
                    if time.monotonic() - last_data_at >= idle_timeout:
                        break

                chunk_timeout = min(0.25, max(deadline - time.monotonic(), 0.0))
                chunk = transport.read_some(timeout=chunk_timeout)
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

                if pattern is not None and pattern in buffer:
                    matched = True
                    break

            result: dict[str, object] = {
                "stdout": buffer.decode("utf-8", errors="replace"),
                "bytes_read": len(buffer),
                "truncated": truncated,
            }
            if pattern is not None:
                result["matched"] = matched
            return result
