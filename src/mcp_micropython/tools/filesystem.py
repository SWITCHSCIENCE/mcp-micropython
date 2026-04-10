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

from typing import TypedDict

from mcp.server.fastmcp import FastMCP

from ..session_manager import NotConnectedError, SessionManager

HARDWARE_MD_PATH = "/HARDWARE.md"


class FileEntry(TypedDict):
    name: str
    path: str
    kind: str
    size_bytes: int | None


class ListFilesResult(TypedDict):
    ok: bool
    path: str
    entries: list[FileEntry]
    error: str | None


class ReadFileResult(TypedDict):
    ok: bool
    path: str
    content: str
    size_bytes: int
    error: str | None


class WriteFileResult(TypedDict):
    ok: bool
    path: str
    mode: str
    bytes_written: int
    error: str | None


class DeleteFileResult(TypedDict):
    ok: bool
    path: str
    error: str | None


def register(mcp: FastMCP, manager: SessionManager) -> None:
    """ファイルシステムツールを MCP サーバーに登録する。"""

    def _write_text_file(path: str, content: str, mode: str, timeout: float) -> WriteFileResult:
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
            return {
                "ok": False,
                "path": path,
                "mode": mode,
                "bytes_written": 0,
                "error": str(e),
            }
        except Exception as e:
            return {
                "ok": False,
                "path": path,
                "mode": mode,
                "bytes_written": 0,
                "error": str(e),
            }

        if not result.ok:
            return {
                "ok": False,
                "path": path,
                "mode": mode,
                "bytes_written": 0,
                "error": result.stderr.strip() or "write file failed",
            }
        if result.stdout.strip() == "OK":
            return {
                "ok": True,
                "path": path,
                "mode": mode,
                "bytes_written": len(content.encode("utf-8")),
                "error": None,
            }
        return {
            "ok": False,
            "path": path,
            "mode": mode,
            "bytes_written": 0,
            "error": result.stdout.strip() or "write file failed",
        }

    @mcp.tool()
    def micropython_list_files(path: str = "/") -> ListFilesResult:
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
            return {"ok": False, "path": path, "entries": [], "error": str(e)}
        except Exception as e:
            return {"ok": False, "path": path, "entries": [], "error": str(e)}

        if not result.ok:
            return {
                "ok": False,
                "path": path,
                "entries": [],
                "error": result.stderr.strip() or "list files failed",
            }

        entries: list[FileEntry] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("ERROR:"):
                return {
                    "ok": False,
                    "path": path,
                    "entries": [],
                    "error": line[len("ERROR:") :].strip(),
                }
            if line.startswith("? "):
                full_path = line[2:].strip()
                entries.append(
                    {
                        "name": full_path.rsplit("/", 1)[-1],
                        "path": full_path,
                        "kind": "unknown",
                        "size_bytes": None,
                    }
                )
                continue

            parts = line.split(maxsplit=2)
            if len(parts) != 3:
                continue

            kind_code, size_text, full_path = parts
            entries.append(
                {
                    "name": full_path.rsplit("/", 1)[-1],
                    "path": full_path,
                    "kind": "dir" if kind_code == "D" else "file",
                    "size_bytes": int(size_text),
                }
            )

        return {
            "ok": True,
            "path": path,
            "entries": entries,
            "error": None,
        }

    @mcp.tool()
    def micropython_read_file(path: str) -> ReadFileResult:
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
            return {"ok": False, "path": path, "content": "", "size_bytes": 0, "error": str(e)}
        except Exception as e:
            return {"ok": False, "path": path, "content": "", "size_bytes": 0, "error": str(e)}

        if not result.ok:
            return {
                "ok": False,
                "path": path,
                "content": "",
                "size_bytes": 0,
                "error": result.stderr.strip() or "read file failed",
            }
        if result.stdout.startswith("ERROR:"):
            return {
                "ok": False,
                "path": path,
                "content": "",
                "size_bytes": 0,
                "error": result.stdout[len("ERROR:") :].strip(),
            }
        return {
            "ok": True,
            "path": path,
            "content": result.stdout,
            "size_bytes": len(result.stdout.encode("utf-8")),
            "error": None,
        }

    @mcp.tool()
    def micropython_read_hardware_md() -> ReadFileResult:
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
            return {
                "ok": False,
                "path": HARDWARE_MD_PATH,
                "content": "",
                "size_bytes": 0,
                "error": str(e),
            }
        except Exception as e:
            return {
                "ok": False,
                "path": HARDWARE_MD_PATH,
                "content": "",
                "size_bytes": 0,
                "error": str(e),
            }

        if not result.ok:
            return {
                "ok": False,
                "path": HARDWARE_MD_PATH,
                "content": "",
                "size_bytes": 0,
                "error": result.stderr.strip() or "read file failed",
            }
        if result.stdout.startswith("ERROR:"):
            return {
                "ok": False,
                "path": HARDWARE_MD_PATH,
                "content": "",
                "size_bytes": 0,
                "error": result.stdout[len("ERROR:") :].strip(),
            }
        return {
            "ok": True,
            "path": HARDWARE_MD_PATH,
            "content": result.stdout,
            "size_bytes": len(result.stdout.encode("utf-8")),
            "error": None,
        }

    @mcp.tool()
    def micropython_write_file(path: str, content: str) -> WriteFileResult:
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
    def micropython_append_file(path: str, content: str) -> WriteFileResult:
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
    def micropython_delete_file(path: str) -> DeleteFileResult:
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
            return {"ok": False, "path": path, "error": str(e)}
        except Exception as e:
            return {"ok": False, "path": path, "error": str(e)}

        if not result.ok:
            return {
                "ok": False,
                "path": path,
                "error": result.stderr.strip() or "delete file failed",
            }
        if result.stdout.strip() == "OK":
            return {"ok": True, "path": path, "error": None}
        return {
            "ok": False,
            "path": path,
            "error": result.stdout.strip() or "delete file failed",
        }
