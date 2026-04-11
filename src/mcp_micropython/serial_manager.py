"""
serial_manager.py — シリアルポート管理

MicroPython ボードとの USB Serial 接続を管理する。
- ポートの列挙
- 接続 / 切断
- RawRepl インスタンスの提供
- スレッドセーフな排他制御（MCP から並列呼び出しが来た場合に備えて）
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import Generator

import serial
import serial.tools.list_ports

from .raw_repl import RawRepl, ReplResult

# デフォルトのシリアルパラメータ
DEFAULT_BAUDRATE = 115200
DEFAULT_TIMEOUT = 1.0  # serial read timeout (serialライブラリ側)


class NotConnectedError(Exception):
    """MicroPython ボードに接続していない状態で操作しようとした場合"""


class SerialManager:
    """
    MicroPython ボードとのシリアル接続を管理するシングルトンライクなクラス。
    MCPサーバーのライフサイクルと合わせてインスタンスを1つ保持する。
    """

    def __init__(self) -> None:
        self._ser: serial.Serial | None = None
        self._lock = threading.RLock()  # 再入可能なロック

    # ------------------------------------------------------------------
    # ポート管理
    # ------------------------------------------------------------------

    @staticmethod
    def list_ports() -> list[dict]:
        """
        利用可能なシリアルポートを列挙する。

        Returns:
            [{"port": "COM3", "description": "...", "hwid": "..."}, ...]
        """
        ports = []
        for p in serial.tools.list_ports.comports():
            ports.append({
                "port": p.device,
                "description": p.description or "",
                "hwid": p.hwid or "",
            })
        return ports

    def connect(self, port: str, baudrate: int = DEFAULT_BAUDRATE) -> None:
        """
        指定ポートに接続する。既に接続中の場合は先に切断してから再接続。

        Args:
            port: シリアルポート名 (例: "COM3")
            baudrate: ボーレート（MicroPython デフォルトは 115200）
        """
        with self._lock:
            if self._ser and self._ser.is_open:
                self._ser.close()

            self._ser = serial.Serial(
                port=port,
                baudrate=baudrate,
                timeout=DEFAULT_TIMEOUT,
                write_timeout=DEFAULT_TIMEOUT,
            )

    def disconnect(self) -> None:
        """接続を切断する。"""
        with self._lock:
            if self._ser and self._ser.is_open:
                self._ser.close()
            self._ser = None

    @property
    def is_connected(self) -> bool:
        return self._ser is not None and self._ser.is_open

    @property
    def port_name(self) -> str | None:
        return self._ser.port if self._ser else None

    def serial_read(
        self,
        duration: float,
        idle_timeout: float | None = None,
        max_bytes: int | None = None,
    ) -> dict[str, object]:
        with self._lock:
            self._ensure_connected()
            return self._read_serial(
                timeout=duration,
                idle_timeout=idle_timeout,
                max_bytes=max_bytes,
            )

    def serial_read_until(
        self,
        pattern: str,
        timeout: float,
        max_bytes: int | None = None,
    ) -> dict[str, object]:
        with self._lock:
            self._ensure_connected()
            return self._read_serial(
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
            self._ensure_connected()
            assert self._ser is not None
            reset_ok = True
            try:
                self._ser.reset_input_buffer()
                self._ser.write(b"\x04")
                self._ser.flush()
            except Exception:
                reset_ok = False

            result = self._read_serial(
                timeout=capture_duration,
                idle_timeout=idle_timeout,
                max_bytes=max_bytes,
            )
            result["reset_ok"] = reset_ok
            return result

    def interrupt(self) -> None:
        with self._lock:
            self._ensure_connected()
            assert self._ser is not None
            self._ser.write(b"\x03")
            self._ser.flush()

    # ------------------------------------------------------------------
    # コード実行 (Raw REPL 経由)
    # ------------------------------------------------------------------

    def exec_code(self, code: str, timeout: float = 10.0) -> ReplResult:
        """
        MicroPython ボードで Python コードを実行し結果を返す。

        Args:
            code: 実行する Python コード
            timeout: 実行タイムアウト（秒）

        Returns:
            ReplResult

        Raises:
            NotConnectedError: 未接続状態
        """
        with self._lock:
            self._ensure_connected()
            repl = RawRepl(self._ser)  # type: ignore[arg-type]
            return repl.exec_code_safe(code, timeout=timeout)

    def eval_expr(self, expression: str) -> ReplResult:
        """
        式を評価して結果を文字列で返す。
        内部的に print() でラップして exec_code を呼ぶ。
        """
        code = f"print({expression})"
        return self.exec_code(code, timeout=5.0)

    # ------------------------------------------------------------------
    # コンテキストマネージャ（一時的に Raw REPL を直接操作したい場合）
    # ------------------------------------------------------------------

    @contextmanager
    def raw_repl(self) -> Generator[RawRepl, None, None]:
        """
        Raw REPL を直接操作するコンテキストマネージャ。
        ファイル転送など複数ステップの操作に使う。

        Usage:
            with manager.raw_repl() as repl:
                repl.enter()
                repl.exec_code("x = 1")
                repl.exec_code("print(x)")
                repl.exit()
        """
        with self._lock:
            self._ensure_connected()
            yield RawRepl(self._ser)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # 内部ユーティリティ
    # ------------------------------------------------------------------

    def _ensure_connected(self) -> None:
        if not self.is_connected:
            raise NotConnectedError(
                "MicroPython ボードに接続されていません。micropython_connect ツールで接続してください。"
            )

    def _read_serial(
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

        assert self._ser is not None

        deadline = time.monotonic() + timeout
        last_data_at: float | None = None
        buffer = bytearray()
        matched = False
        truncated = False

        while time.monotonic() < deadline:
            if idle_timeout is not None and last_data_at is not None:
                if time.monotonic() - last_data_at >= idle_timeout:
                    break

            chunk = self._ser.read(self._ser.in_waiting or 1)
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
