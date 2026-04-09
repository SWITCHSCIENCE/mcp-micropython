"""
device.py — 接続管理・デバイス情報ツール

MCP ツール:
  - micropython_list_ports   : 利用可能なシリアルポート一覧
  - micropython_connect      : 指定ポートに接続
  - micropython_disconnect   : 接続を切断
  - micropython_get_info     : デバイス情報取得 (チップ情報・空きメモリ等)
  - micropython_reset        : ソフトリセット
"""

from __future__ import annotations

from typing import TypedDict

from mcp.server.fastmcp import FastMCP

from ..serial_manager import SerialManager

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
    port: str
    baudrate: int
    error: str | None


class DisconnectResult(TypedDict):
    ok: bool
    error: str | None


class ActionResult(TypedDict):
    ok: bool
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


def register(mcp: FastMCP, manager: SerialManager) -> None:
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
    def micropython_connect(port: str, baudrate: int = 115200) -> ConnectionResult:
        """
        指定した COM ポートの MicroPython ボードに接続する。

        Args:
            port: シリアルポート名 (例: "COM3")
            baudrate: ボーレート (通常は 115200)
        """
        try:
            manager.connect(port, baudrate)
            return {
                "ok": True,
                "port": port,
                "baudrate": baudrate,
                "error": None,
            }
        except Exception as e:
            return {
                "ok": False,
                "port": port,
                "baudrate": baudrate,
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
    def micropython_serial_read(
        duration: float,
        idle_timeout: float | None = None,
        max_bytes: int | None = None,
    ) -> SerialReadResult:
        try:
            result = manager.serial_read(
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
    def micropython_serial_read_until(
        pattern: str,
        timeout: float,
        max_bytes: int | None = None,
    ) -> SerialReadUntilResult:
        try:
            result = manager.serial_read_until(
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
        except Exception as e:
            return {
                "ok": False,
                "stdout": "",
                "reset_ok": False,
                "truncated": False,
                "error": str(e),
            }
