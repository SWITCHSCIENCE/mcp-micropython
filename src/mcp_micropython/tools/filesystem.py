"""
filesystem.py - ファイルシステム関連ツール

MCP ツール:
  - micropython_list_files     : ファイル/ディレクトリ一覧
  - micropython_read_file      : ファイル内容の読み出し
  - micropython_read_hardware_md : デバイス上の /HARDWARE.md を読む
  - micropython_write_file     : ファイルへの書き込み
  - micropython_append_file    : ファイルへの追記
  - micropython_delete_file    : ファイルの削除

Note:
    大容量ファイル転送は Raw REPL の制約で失敗する場合がある。
    数 KB を超える場合は write_file で空にしてから append_file で分割追記する。
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..serial_manager import NotConnectedError, SerialManager

HARDWARE_MD_PATH = "/HARDWARE.md"


def register(mcp: FastMCP, manager: SerialManager) -> None:
    """ファイルシステムツールを MCP サーバーに登録する。"""

    def _write_text_file(path: str, content: str, mode: str, timeout: float) -> str:
        code = f"""\
try:
    with open({path!r}, {mode!r}) as f:
        f.write({content!r})
    print('OK')
except Exception as e:
    print(f'ERROR: {{e}}')
"""
        try:
            result = manager.exec_code(code, timeout=timeout)
        except NotConnectedError as e:
            return f"エラー: {e}"
        except Exception as e:
            return f"エラー: {e}"

        if not result.ok:
            return f"エラー:\n{result.stderr}"
        if result.stdout.strip() == "OK":
            action = "書き込み" if mode == "w" else "追記"
            return f"OK: {path} に{action}ました。"
        return f"エラー: {result.stdout}"

    @mcp.tool()
    def micropython_list_files(path: str = "/") -> str:
        """
        MicroPython ボードのファイルシステム上のファイル/ディレクトリを一覧表示する。

        Args:
            path: 一覧表示するディレクトリのパス (デフォルト: "/")
        """
        code = f"""\
import os
path = {path!r}
try:
    entries = os.listdir(path)
    for name in sorted(entries):
        full = path.rstrip('/') + '/' + name
        try:
            stat = os.stat(full)
            kind = 'D' if stat[0] & 0x4000 else 'F'
            size = stat[6]
            print(f'{{kind}} {{size:>8}} {{full}}')
        except Exception:
            print(f'? {{full}}')
except Exception as e:
    print(f'ERROR: {{e}}')
"""
        try:
            result = manager.exec_code(code, timeout=5.0)
        except NotConnectedError as e:
            return f"エラー: {e}"
        except Exception as e:
            return f"エラー: {e}"

        if not result.ok:
            return f"エラー:\n{result.stderr}"
        output = result.stdout.strip()
        return output if output else f"{path} は空です。"

    @mcp.tool()
    def micropython_read_file(path: str) -> str:
        """
        MicroPython ボードのファイルを読み出して返す。

        Args:
            path: 読み出すファイルのパス (例: "/main.py")
        """
        code = f"""\
try:
    with open({path!r}, 'r') as f:
        print(f.read(), end='')
except Exception as e:
    print(f'ERROR: {{e}}')
"""
        try:
            result = manager.exec_code(code, timeout=5.0)
        except NotConnectedError as e:
            return f"エラー: {e}"
        except Exception as e:
            return f"エラー: {e}"

        if not result.ok:
            return f"エラー:\n{result.stderr}"
        if result.stdout.startswith("ERROR:"):
            return f"エラー: {result.stdout}"
        return result.stdout

    @mcp.tool()
    def micropython_read_hardware_md() -> str:
        """
        デバイス上の /HARDWARE.md を読み出して返す。
        GPIO 割り当てや接続部品の前提確認用のショートカット。
        """
        code = f"""\
try:
    with open({HARDWARE_MD_PATH!r}, 'r') as f:
        print(f.read(), end='')
except Exception as e:
    print(f'ERROR: {{e}}')
"""
        try:
            result = manager.exec_code(code, timeout=5.0)
        except NotConnectedError as e:
            return f"エラー: {e}"
        except Exception as e:
            return f"エラー: {e}"

        if not result.ok:
            return f"エラー:\n{result.stderr}"
        if result.stdout.startswith("ERROR:"):
            return f"エラー: {result.stdout}"
        return result.stdout

    @mcp.tool()
    def micropython_write_file(path: str, content: str) -> str:
        """
        MicroPython ボードのファイルに内容を書き込む（上書き）。

        Args:
            path: 書き込み先ファイルのパス (例: "/main.py")
            content: 書き込む内容 (テキスト)

        Note:
            大容量ファイル (数 KB 以上) は Raw REPL の制約により失敗する場合がある。
            その場合は小さいチャンクに分け、最初にこのツールで空文字または先頭チャンクを書き、
            続けて micropython_append_file で追記する。
        """
        return _write_text_file(path=path, content=content, mode="w", timeout=10.0)

    @mcp.tool()
    def micropython_append_file(path: str, content: str) -> str:
        """
        MicroPython ボードのファイルに内容を追記する。

        Args:
            path: 追記先ファイルのパス (例: "/main.py")
            content: 追記する内容 (テキスト)

        Note:
            大きい内容を書き込むときは、content を小さいチャンクに分けて
            このツールを複数回呼ぶことで転送しやすくなる。
        """
        return _write_text_file(path=path, content=content, mode="a", timeout=10.0)

    @mcp.tool()
    def micropython_delete_file(path: str) -> str:
        """
        MicroPython ボード上のファイルを削除する。

        Args:
            path: 削除するファイルのパス (例: "/test.py")
        """
        code = f"""\
import os
try:
    os.remove({path!r})
    print('OK')
except Exception as e:
    print(f'ERROR: {{e}}')
"""
        try:
            result = manager.exec_code(code, timeout=5.0)
        except NotConnectedError as e:
            return f"エラー: {e}"
        except Exception as e:
            return f"エラー: {e}"

        if not result.ok:
            return f"エラー:\n{result.stderr}"
        if result.stdout.strip() == "OK":
            return f"OK: {path} を削除しました。"
        return f"エラー: {result.stdout}"
