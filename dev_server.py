"""
dev_server.py — mcp dev コマンド用エントリポイント

`mcp dev` はファイルを直接ロードするため相対インポートが使えない。
このファイルはインストール済みパッケージの絶対インポートを使って
FastMCP インスタンス (mcp) を公開するためのラッパー。

使い方:
    uv run mcp dev dev_server.py
"""

from mcp_esp32.server import mcp, _manager, _register_tools

_register_tools()
