"""
serial_manager.py — シリアルポート管理

ESP32 との USB Serial 接続を管理する。
- ポートの列挙
- 接続 / 切断
- RawRepl インスタンスの提供
- スレッドセーフな排他制御（MCP から並列呼び出しが来た場合に備えて）
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Generator

import serial
import serial.tools.list_ports

from .raw_repl import RawRepl, ReplResult

# デフォルトのシリアルパラメータ
DEFAULT_BAUDRATE = 115200
DEFAULT_TIMEOUT = 1.0  # serial read timeout (serialライブラリ側)


class NotConnectedError(Exception):
    """ESP32 に接続していない状態で操作しようとした場合"""


class SerialManager:
    """
    ESP32 とのシリアル接続を管理するシングルトンライクなクラス。
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

    # ------------------------------------------------------------------
    # コード実行 (Raw REPL 経由)
    # ------------------------------------------------------------------

    def exec_code(self, code: str, timeout: float = 10.0) -> ReplResult:
        """
        ESP32 で Python コードを実行し結果を返す。

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
                "ESP32 に接続されていません。esp32_connect ツールで接続してください。"
            )
