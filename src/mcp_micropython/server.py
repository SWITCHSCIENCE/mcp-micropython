"""
server.py - MCP サーバーエントリポイント

起動方法:
    uv run mcp-micropython-bridge

Claude Desktop / VSCode Extension の設定例:
    {
      "mcpServers": {
        "micropython": {
          "command": "uv",
          "args": ["--directory", "<このディレクトリのパス>", "run", "mcp-micropython-bridge"]
        }
      }
    }
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import static_resources
from .serial_manager import SerialManager
from .tools import device, execution, filesystem

mcp = FastMCP(
    name="MicroPython Bridge",
    instructions="""## MicroPython MCP rules

- Read the static guides first when they are relevant, especially `micropython://guide/recipes`, `micropython://guide/limitations`, and `micropython://policy/hardware-docs`.
- Before inspecting device state or making changes on a board, connect first.
- Treat `HARDWARE.md` as the source of truth for wiring, peripherals, helper modules, and board-specific APIs.
- Do not assume hardware details without reading `HARDWARE.md` or existing device code.
- Prefer documented helpers over ad-hoc direct hardware access. If new hardware behavior is needed, implement or extend a small reusable helper module.
- Follow `micropython://policy/hardware-docs` when deciding whether `HARDWARE.md` must be updated before the task is complete.
- Always read `/boot.py` and `/main.py` before modifying them.
- Use writes only for intentional changes; when unsure, prefer small checks and avoid bulk overwrites.
- Disconnect when appropriate, and assume a reset may require reconnection.
""",
)

_manager = SerialManager()


def _register_tools() -> None:
    """全ツールを MCP サーバーに登録する。"""
    static_resources.register(mcp)
    device.register(mcp, _manager)
    execution.register(mcp, _manager)
    filesystem.register(mcp, _manager)


def main() -> None:
    """エントリポイント。stdio トランスポートで MCP サーバーを起動する。"""
    _register_tools()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
