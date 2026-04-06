"""
server.py — MCP サーバーエントリポイント

起動方法:
    uv run mcp-micropython

Claude Desktop / VSCode Extension の設定:
    {
      "mcpServers": {
        "micropython": {
          "command": "uv",
          "args": ["--directory", "<このディレクトリのパス>", "run", "mcp-micropython"]
        }
      }
    }
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .serial_manager import SerialManager
from .tools import device, execution, filesystem, hardware

# MCP サーバーインスタンス
mcp = FastMCP(
    name="MicroPython Bridge",
    instructions=(
        "MicroPython インタープリタを操作するブリッジサーバーです。\n"
        "操作手順:\n"
        "1. micropython_list_ports で接続可能なポートを確認する\n"
        "2. micropython_connect で接続する (例: port='COM3')\n"
        "3. micropython_exec や micropython_eval でコードを実行する\n"
        "4. 終了時は micropython_disconnect で切断する"
    ),
)

# グローバルなシリアル管理インスタンス（サーバーのライフサイクルと同じ）
_manager = SerialManager()


def _register_tools() -> None:
    """全ツールを MCP サーバーに登録する。"""
    device.register(mcp, _manager)
    execution.register(mcp, _manager)
    filesystem.register(mcp, _manager)
    hardware.register(mcp, _manager)


def main() -> None:
    """エントリポイント。stdio トランスポートで MCP サーバーを起動する。"""
    _register_tools()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
