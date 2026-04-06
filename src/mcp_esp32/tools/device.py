"""
device.py — 接続管理・デバイス情報ツール

MCP ツール:
  - esp32_list_ports   : 利用可能なシリアルポート一覧
  - esp32_connect      : 指定ポートに接続
  - esp32_disconnect   : 接続を切断
  - esp32_get_info     : デバイス情報取得 (チップ情報・空きメモリ等)
  - esp32_reset        : ソフトリセット
"""

from __future__ import annotations

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


def register(mcp: FastMCP, manager: SerialManager) -> None:
    """デバイス関連ツールを MCP サーバーに登録する。"""

    @mcp.tool()
    def esp32_list_ports() -> str:
        """
        接続可能な USB シリアルポートを一覧表示する。
        ESP32 を接続した後にこのツールを呼んで COM ポート名を確認してください。
        """
        ports = manager.list_ports()
        if not ports:
            return "シリアルポートが見つかりません。ESP32が接続されているか確認してください。"
        lines = ["利用可能なシリアルポート:"]
        for p in ports:
            lines.append(f"  {p['port']} — {p['description']} ({p['hwid']})")
        return "\n".join(lines)

    @mcp.tool()
    def esp32_connect(port: str, baudrate: int = 115200) -> str:
        """
        指定した COM ポートの ESP32 に接続する。

        Args:
            port: シリアルポート名 (例: "COM3")
            baudrate: ボーレート (通常は 115200)
        """
        try:
            manager.connect(port, baudrate)
            return f"✓ {port} ({baudrate} bps) に接続しました。"
        except Exception as e:
            return f"✗ 接続失敗: {e}"

    @mcp.tool()
    def esp32_disconnect() -> str:
        """ESP32 のシリアル接続を切断する。"""
        if not manager.is_connected:
            return "既に切断されています。"
        manager.disconnect()
        return "✓ 接続を切断しました。"

    @mcp.tool()
    def esp32_get_info() -> str:
        """
        ESP32 のデバイス情報を取得する。
        (MicroPython バージョン・空きメモリ・フラッシュ使用量・CPU周波数 など)
        """
        try:
            result = manager.exec_code(_GET_INFO_CODE, timeout=5.0)
            if not result.ok:
                return f"エラー:\n{result.stderr}"
            return f"デバイス情報:\n{result.stdout}"
        except Exception as e:
            return f"取得失敗: {e}"

    @mcp.tool()
    def esp32_reset() -> str:
        """
        ESP32 をソフトリセットする (machine.reset() に相当)。
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
            return "✓ リセットしました。再接続するには esp32_connect を使用してください。"
        except Exception as e:
            return f"リセット失敗: {e}"
