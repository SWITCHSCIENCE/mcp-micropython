"""
filesystem.py — ファイルシステム操作ツール

MCP ツール:
  - esp32_list_files  : ファイル/ディレクトリ一覧
  - esp32_read_file   : ファイル内容の読み出し
  - esp32_write_file  : ファイルへの書き込み
  - esp32_delete_file : ファイルの削除

Note: 大容量ファイル転送は現時点で非対応。
      将来的に必要になった場合は分割送信を実装する。
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..serial_manager import NotConnectedError, SerialManager


def register(mcp: FastMCP, manager: SerialManager) -> None:
    """ファイルシステムツールを MCP サーバーに登録する。"""

    @mcp.tool()
    def esp32_list_files(path: str = "/") -> str:
        """
        ESP32 のフラッシュ上のファイル/ディレクトリを一覧表示する。

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
            return f"✗ {e}"
        except Exception as e:
            return f"✗ エラー: {e}"

        if not result.ok:
            return f"✗ エラー:\n{result.stderr}"
        output = result.stdout.strip()
        return output if output else f"{path} は空です。"

    @mcp.tool()
    def esp32_read_file(path: str) -> str:
        """
        ESP32 フラッシュ上のファイルを読み出して返す。

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
            return f"✗ {e}"
        except Exception as e:
            return f"✗ エラー: {e}"

        if not result.ok:
            return f"✗ エラー:\n{result.stderr}"
        if result.stdout.startswith("ERROR:"):
            return f"✗ {result.stdout}"
        return result.stdout

    @mcp.tool()
    def esp32_write_file(path: str, content: str) -> str:
        """
        ESP32 フラッシュ上のファイルに内容を書き込む（上書き）。

        Args:
            path: 書き込み先ファイルのパス (例: "/main.py")
            content: 書き込む内容 (テキスト)

        Note:
            大容量ファイル (数 KB 以上) は Raw REPL の制限により失敗する場合がある。
        """
        # content を repr() でエスケープして安全に埋め込む
        code = f"""\
try:
    with open({path!r}, 'w') as f:
        f.write({content!r})
    print('OK')
except Exception as e:
    print(f'ERROR: {{e}}')
"""
        try:
            result = manager.exec_code(code, timeout=10.0)
        except NotConnectedError as e:
            return f"✗ {e}"
        except Exception as e:
            return f"✗ エラー: {e}"

        if not result.ok:
            return f"✗ エラー:\n{result.stderr}"
        if result.stdout.strip() == "OK":
            return f"✓ {path} に書き込みました。"
        return f"✗ {result.stdout}"

    @mcp.tool()
    def esp32_delete_file(path: str) -> str:
        """
        ESP32 フラッシュ上のファイルを削除する。

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
            return f"✗ {e}"
        except Exception as e:
            return f"✗ エラー: {e}"

        if not result.ok:
            return f"✗ エラー:\n{result.stderr}"
        if result.stdout.strip() == "OK":
            return f"✓ {path} を削除しました。"
        return f"✗ {result.stdout}"
