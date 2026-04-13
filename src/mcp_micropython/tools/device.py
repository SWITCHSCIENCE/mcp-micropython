"""
device.py — connection and device tools.
"""

from __future__ import annotations

from typing import TypedDict

from mcp.server.fastmcp import FastMCP

from ..session_manager import SessionManager
from ..transport import UnsupportedOperationError

# デバイス情報取得コード (MicroPython上で実行)
_GET_INFO_CODE = """\
import sys, gc, os
gc.collect()
info = {
    'platform': sys.platform,
    'version': '.'.join(str(v) for v in sys.version_info[:3]),
    'implementation': sys.implementation.name,
    'free_mem': gc.mem_free(),
    'alloc_mem': gc.mem_alloc(),
}
try:
    import machine
    info['freq_mhz'] = machine.freq() // 1_000_000
except Exception:
    pass
try:
    s = os.statvfs('/')
    info['fs_total_kb'] = s[0] * s[2] // 1024
    info['fs_free_kb']  = s[0] * s[3] // 1024
except Exception:
    pass
for k, v in info.items():
    print(f'{k}={v}')
"""


class DeviceInfo(TypedDict, total=False):
    platform: str
    version: str
    implementation: str
    free_mem: int
    alloc_mem: int
    freq_mhz: int
    fs_total_kb: int
    fs_free_kb: int


class GetInfoResult(TypedDict):
    ok: bool
    info: DeviceInfo
    error: str | None


class SerialPortInfo(TypedDict):
    port: str
    description: str
    hwid: str


class ListPortsResult(TypedDict):
    ok: bool
    ports: list[SerialPortInfo]
    error: str | None


class ConnectionResult(TypedDict):
    ok: bool
    target: str
    transport: str | None
    baudrate: int | None
    host: str | None
    port: int | str | None
    error: str | None


class DisconnectResult(TypedDict):
    ok: bool
    error: str | None


class ActionResult(TypedDict):
    ok: bool
    error: str | None


class ConnectionStatusResult(TypedDict):
    ok: bool
    connected: bool
    transport: str | None
    target: str | None
    host: str | None
    port: int | str | None
    baudrate: int | None
    error: str | None


class SerialReadResult(TypedDict):
    ok: bool
    stdout: str
    truncated: bool
    bytes_read: int
    error: str | None


class SerialReadUntilResult(TypedDict):
    ok: bool
    matched: bool
    stdout: str
    bytes_read: int
    error: str | None


class ResetCaptureResult(TypedDict):
    ok: bool
    stdout: str
    reset_ok: bool
    truncated: bool
    error: str | None


def _parse_info_value(raw_value: str) -> str | int:
    raw_value = raw_value.strip()
    try:
        return int(raw_value)
    except ValueError:
        return raw_value


def _parse_device_info(stdout: str) -> DeviceInfo:
    info: DeviceInfo = {}
    for line in stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        info[key] = _parse_info_value(value)
    return info


def register(mcp: FastMCP, manager: SessionManager) -> None:
    """デバイス関連ツールを MCP サーバーに登録する。"""

    @mcp.tool()
    def micropython_list_ports() -> ListPortsResult:
        """
        接続可能な USB シリアルポートを一覧表示する。
        MicroPython ボードを接続した後にこのツールを呼んで COM ポート名を確認してください。
        """
        ports = manager.list_ports()
        return {
            "ok": True,
            "ports": [
                {
                    "port": p["port"],
                    "description": p["description"],
                    "hwid": p["hwid"],
                }
                for p in ports
            ],
            "error": None,
        }

    @mcp.tool()
    def micropython_connect(
        target: str,
        password: str | None = None,
        baudrate: int = 115200,
    ) -> ConnectionResult:
        """
        指定ターゲットへ接続する。

        Args:
            target: `COM3` なら serial、`host[:port]` なら WebREPL
            password: WebREPL 接続時のパスワード
            baudrate: serial 接続時のボーレート
        """
        try:
            status = manager.connect(target=target, password=password, baudrate=baudrate)
            return {
                "ok": True,
                "target": target,
                "transport": status.get("transport"),
                "baudrate": status.get("baudrate") if isinstance(status.get("baudrate"), int) else None,
                "host": status.get("host") if isinstance(status.get("host"), str) else None,
                "port": status.get("port"),
                "error": None,
            }
        except Exception as e:
            return {
                "ok": False,
                "target": target,
                "transport": None,
                "baudrate": baudrate,
                "host": None,
                "port": None,
                "error": str(e),
            }

    @mcp.tool()
    def micropython_disconnect() -> DisconnectResult:
        """MicroPython ボードのシリアル接続を切断する。"""
        if not manager.is_connected:
            return {
                "ok": True,
                "error": None,
            }
        manager.disconnect()
        return {
            "ok": True,
            "error": None,
        }

    @mcp.tool()
    def micropython_connection_status() -> ConnectionStatusResult:
        """現在の接続状態を返す。"""
        status = manager.connection_status()
        return {
            "ok": True,
            "connected": bool(status.get("connected")),
            "transport": status.get("transport") if isinstance(status.get("transport"), str) else None,
            "target": status.get("target") if isinstance(status.get("target"), str) else None,
            "host": status.get("host") if isinstance(status.get("host"), str) else None,
            "port": status.get("port"),
            "baudrate": status.get("baudrate") if isinstance(status.get("baudrate"), int) else None,
            "error": None,
        }

    @mcp.tool()
    def micropython_get_info() -> GetInfoResult:
        """
        MicroPython ボードのデバイス情報を取得する。
        (MicroPython バージョン・空きメモリ・フラッシュ使用量・CPU周波数 など)
        """
        try:
            result = manager.exec_code(_GET_INFO_CODE, timeout=5.0)
            if not result.ok:
                return {
                    "ok": False,
                    "info": {},
                    "error": result.stderr.strip() or "device info command failed",
                }
            return {
                "ok": True,
                "info": _parse_device_info(result.stdout),
                "error": None,
            }
        except Exception as e:
            return {
                "ok": False,
                "info": {},
                "error": str(e),
            }

    @mcp.tool()
    def micropython_reset() -> ActionResult:
        """
        MicroPython ボードをソフトリセットする (machine.reset() に相当)。
        リセット後は再接続が必要です。
        """
        try:
            # machine.reset() はレスポンスを返さずリセットするため
            # タイムアウトを短めに設定してエラーを無視する
            try:
                manager.exec_code("import machine; machine.reset()", timeout=2.0)
            except Exception:
                pass
            manager.disconnect()
            return {"ok": True, "error": None}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @mcp.tool()
    def micropython_interrupt() -> ActionResult:
        """Ctrl-C を送って実行中の処理を中断する。"""
        try:
            manager.interrupt()
            return {"ok": True, "error": None}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @mcp.tool()
    def micropython_read_stream(
        duration: float,
        idle_timeout: float | None = None,
        max_bytes: int | None = None,
    ) -> SerialReadResult:
        try:
            result = manager.read_stream(
                duration=duration,
                idle_timeout=idle_timeout,
                max_bytes=max_bytes,
            )
            return {
                "ok": True,
                "stdout": result["stdout"],
                "truncated": result["truncated"],
                "bytes_read": result["bytes_read"],
                "error": None,
            }
        except Exception as e:
            return {
                "ok": False,
                "stdout": "",
                "truncated": False,
                "bytes_read": 0,
                "error": str(e),
            }

    @mcp.tool()
    def micropython_read_until(
        pattern: str,
        timeout: float,
        max_bytes: int | None = None,
    ) -> SerialReadUntilResult:
        try:
            result = manager.read_until(
                pattern=pattern,
                timeout=timeout,
                max_bytes=max_bytes,
            )
            return {
                "ok": True,
                "matched": result["matched"],
                "stdout": result["stdout"],
                "bytes_read": result["bytes_read"],
                "error": None,
            }
        except Exception as e:
            return {
                "ok": False,
                "matched": False,
                "stdout": "",
                "bytes_read": 0,
                "error": str(e),
            }

    @mcp.tool()
    def micropython_reset_and_capture(
        capture_duration: float,
        idle_timeout: float | None = None,
        max_bytes: int | None = None,
    ) -> ResetCaptureResult:
        try:
            result = manager.reset_and_capture(
                capture_duration=capture_duration,
                idle_timeout=idle_timeout,
                max_bytes=max_bytes,
            )
            return {
                "ok": True,
                "stdout": result["stdout"],
                "reset_ok": result["reset_ok"],
                "truncated": result["truncated"],
                "error": None,
            }
        except UnsupportedOperationError as e:
            return {
                "ok": False,
                "stdout": "",
                "reset_ok": False,
                "truncated": False,
                "error": str(e),
            }
        except Exception as e:
            return {
                "ok": False,
                "stdout": "",
                "reset_ok": False,
                "truncated": False,
                "error": str(e),
            }
