"""
filesystem.py - ファイルシステム関連ツール

MCP ツール:
  - micropython_list_files       : ファイル/ディレクトリ一覧
  - micropython_stat_path        : パス情報取得
  - micropython_read_file        : ファイル内容の読み出し
  - micropython_read_lines       : テキストファイルの行単位読み出し
  - micropython_head_lines       : テキストファイル先頭行の読み出し
  - micropython_tail_lines       : テキストファイル末尾行の読み出し
  - micropython_read_hardware_md : デバイス上の /HARDWARE.md を読む
  - micropython_write_file       : ファイルへの書き込み
  - micropython_append_file      : ファイルへの追記
  - micropython_delete_file      : ファイルの削除
  - micropython_make_dir         : ディレクトリ作成
  - micropython_remove_dir       : 空ディレクトリ削除
  - micropython_rename_path      : パス名変更
"""

from __future__ import annotations

import ast
import base64
import hashlib
from pathlib import Path
from typing import TypedDict

from mcp.server.fastmcp import FastMCP

from ..raw_repl import RawReplError
from ..session_manager import NotConnectedError, SessionManager

HARDWARE_MD_PATH = "/HARDWARE.md"
FILE_CHUNK_SIZE = 256
STAT_DIR_MASK = 0x4000


class FileEntry(TypedDict):
    name: str
    path: str
    kind: str
    size_bytes: int | None
    mode: int | None


class ListFilesResult(TypedDict):
    ok: bool
    path: str
    entries: list[FileEntry]
    error: str | None


class ReadFileResult(TypedDict):
    ok: bool
    path: str
    content: str
    content_base64: str | None
    size_bytes: int
    error: str | None


class UploadFileResult(TypedDict):
    ok: bool
    local_path: str
    remote_path: str
    bytes_written: int
    sha256: str | None
    error: str | None


class DownloadFileResult(TypedDict):
    ok: bool
    remote_path: str
    local_path: str
    bytes_written: int
    sha256: str | None
    error: str | None


class HashFileResult(TypedDict):
    ok: bool
    path: str
    algorithm: str
    digest: str
    size_bytes: int
    error: str | None


class CompareLocalRemoteResult(TypedDict):
    ok: bool
    local_path: str
    remote_path: str
    local_sha256: str | None
    remote_sha256: str | None
    same: bool
    error: str | None


class ReadLinesResult(TypedDict):
    ok: bool
    path: str
    start_line: int
    line_count: int
    content: str
    eof: bool
    error: str | None


class ReadTextExcerptResult(TypedDict):
    ok: bool
    path: str
    content: str
    line_count: int
    truncated: bool
    error: str | None


class WriteFileResult(TypedDict):
    ok: bool
    path: str
    bytes_written: int
    error: str | None


class DeleteFileResult(TypedDict):
    ok: bool
    path: str
    error: str | None


class StatPathResult(TypedDict):
    ok: bool
    path: str
    kind: str | None
    size_bytes: int | None
    mode: int | None
    mtime: int | None
    error: str | None


class MakeDirResult(TypedDict):
    ok: bool
    path: str
    parents: bool
    error: str | None


class RenamePathResult(TypedDict):
    ok: bool
    src: str
    dst: str
    error: str | None


def register(mcp: FastMCP, manager: SessionManager) -> None:
    """ファイルシステムツールを MCP サーバーに登録する。"""

    def _path_join(parent: str, name: str) -> str:
        if parent in ("", "/"):
            return f"/{name}"
        return f"{parent.rstrip('/')}/{name}"

    def _kind_from_mode(mode: int | None) -> str:
        if mode is None:
            return "unknown"
        return "dir" if (mode & STAT_DIR_MASK) else "file"

    def _exec_simple(code: str, *, timeout: float, default_error: str) -> tuple[bool, str | None]:
        try:
            result = manager.exec_code(code, timeout=timeout)
        except NotConnectedError as e:
            return False, str(e)
        except Exception as e:
            return False, str(e)

        if not result.ok:
            return False, result.stderr.strip() or default_error

        stdout = result.stdout.strip()
        if stdout == "OK":
            return True, None
        if stdout.startswith("ERROR:"):
            return False, stdout[len("ERROR:") :].strip() or default_error
        return False, stdout or default_error

    def _chunk_bytes(data: bytes, chunk_size: int = FILE_CHUNK_SIZE) -> list[bytes]:
        return [data[offset : offset + chunk_size] for offset in range(0, len(data), chunk_size)]

    def _read_file_bytes(path: str, timeout: float) -> tuple[bytes | None, str | None]:
        try:
            with manager.raw_repl() as repl:
                repl.enter()
                try:
                    open_result = repl.exec_code(f"f=open({path!r}, 'rb')\nr=f.read", timeout=timeout)
                    if not open_result.ok:
                        return None, open_result.stderr.strip() or "read file failed"

                    chunks = bytearray()
                    while True:
                        chunk_result = repl.exec_code(
                            f"print(repr(r({FILE_CHUNK_SIZE})))",
                            timeout=timeout,
                        )
                        if not chunk_result.ok:
                            return None, chunk_result.stderr.strip() or "read file failed"

                        chunk_text = chunk_result.stdout.strip()
                        if chunk_text.startswith("ERROR:"):
                            return None, chunk_text[len("ERROR:") :].strip() or "read file failed"
                        if not chunk_text:
                            return None, "empty chunk response while reading file"

                        chunk = ast.literal_eval(chunk_text)
                        if not isinstance(chunk, bytes):
                            return None, "unexpected read chunk type"
                        if not chunk:
                            break
                        chunks.extend(chunk)
                finally:
                    repl.exec_code(
                        "try:\n f.close()\nexcept Exception:\n pass",
                        timeout=timeout,
                    )
                    repl.exit()
        except NotConnectedError as e:
            return None, str(e)
        except (RawReplError, SyntaxError, ValueError) as e:
            return None, str(e)
        except Exception as e:
            return None, str(e)

        return bytes(chunks), None

    def _write_file_bytes(path: str, data: bytes, mode: str, timeout: float) -> WriteFileResult:
        try:
            with manager.raw_repl() as repl:
                repl.enter()
                try:
                    open_result = repl.exec_code(f"f=open({path!r}, {mode!r})\nw=f.write", timeout=timeout)
                    if not open_result.ok:
                        return {
                            "ok": False,
                            "path": path,
                            "bytes_written": 0,
                            "error": open_result.stderr.strip() or "write file failed",
                        }

                    written = 0
                    for chunk in _chunk_bytes(data):
                        result = repl.exec_code(f"w({chunk!r})", timeout=timeout)
                        if not result.ok:
                            return {
                                "ok": False,
                                "path": path,
                                "bytes_written": written,
                                "error": result.stderr.strip() or "write file failed",
                            }
                        written += len(chunk)
                finally:
                    repl.exec_code(
                        "try:\n f.close()\nexcept Exception:\n pass",
                        timeout=timeout,
                    )
                    repl.exit()
        except NotConnectedError as e:
            return {"ok": False, "path": path, "bytes_written": 0, "error": str(e)}
        except RawReplError as e:
            return {"ok": False, "path": path, "bytes_written": 0, "error": str(e)}
        except Exception as e:
            return {"ok": False, "path": path, "bytes_written": 0, "error": str(e)}

        return {
            "ok": True,
            "path": path,
            "bytes_written": len(data),
            "error": None,
        }

    def _resolve_write_bytes(
        *,
        content: str | None,
        content_base64: str | None,
        encoding: str,
    ) -> tuple[bytes | None, str | None]:
        if (content is None) == (content_base64 is None):
            return None, "exactly one of content or content_base64 must be provided"

        if content_base64 is not None:
            try:
                return base64.b64decode(content_base64, validate=True), None
            except Exception as e:
                return None, f"invalid base64 content: {e}"

        try:
            assert content is not None
            return content.encode(encoding), None
        except Exception as e:
            return None, str(e)

    def _compute_sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _workspace_root() -> Path:
        return Path.cwd().resolve()

    def _ensure_local_workspace_path(local_path: str) -> tuple[Path | None, str | None]:
        try:
            path = Path(local_path)
            resolved = path.resolve() if path.is_absolute() else (_workspace_root() / path).resolve()
            resolved.relative_to(_workspace_root())
            return resolved, None
        except Exception:
            return None, "local path must stay within the workspace"

    def _read_local_file_bytes(local_path: str) -> tuple[bytes | None, Path | None, str | None]:
        resolved, error = _ensure_local_workspace_path(local_path)
        if error is not None or resolved is None:
            return None, None, error
        try:
            return resolved.read_bytes(), resolved, None
        except Exception as e:
            return None, resolved, str(e)

    def _write_local_file_bytes(local_path: str, data: bytes, overwrite: bool) -> tuple[int, Path | None, str | None]:
        resolved, error = _ensure_local_workspace_path(local_path)
        if error is not None or resolved is None:
            return 0, None, error
        if resolved.exists() and not overwrite:
            return 0, resolved, "local file already exists"
        if not resolved.parent.exists():
            return 0, resolved, "parent directory does not exist"
        try:
            resolved.write_bytes(data)
        except Exception as e:
            return 0, resolved, str(e)
        return len(data), resolved, None

    def _read_text_file(path: str, timeout: int, encoding: str, errors: str) -> tuple[str | None, int, str | None]:
        data, error = _read_file_bytes(path, float(timeout))
        if error is not None or data is None:
            return None, 0, error or "read file failed"
        try:
            return data.decode(encoding, errors=errors), len(data), None
        except Exception as e:
            return None, len(data), str(e)

    def _split_lines(content: str, *, keepends: bool = False) -> list[str]:
        return content.splitlines(keepends=keepends)

    def _stat_path(path: str) -> StatPathResult:
        code = f"""\
import os
try:
    print(repr(os.stat({path!r})))
except Exception as e:
    print(f'ERROR: {{e}}')
"""
        try:
            result = manager.exec_code(code, timeout=5.0)
        except NotConnectedError as e:
            return {
                "ok": False,
                "path": path,
                "kind": None,
                "size_bytes": None,
                "mode": None,
                "mtime": None,
                "error": str(e),
            }
        except Exception as e:
            return {
                "ok": False,
                "path": path,
                "kind": None,
                "size_bytes": None,
                "mode": None,
                "mtime": None,
                "error": str(e),
            }

        if not result.ok:
            return {
                "ok": False,
                "path": path,
                "kind": None,
                "size_bytes": None,
                "mode": None,
                "mtime": None,
                "error": result.stderr.strip() or "stat path failed",
            }

        text = result.stdout.strip()
        if text.startswith("ERROR:"):
            return {
                "ok": False,
                "path": path,
                "kind": None,
                "size_bytes": None,
                "mode": None,
                "mtime": None,
                "error": text[len("ERROR:") :].strip(),
            }

        try:
            stat_result = ast.literal_eval(text)
        except Exception:
            return {
                "ok": False,
                "path": path,
                "kind": None,
                "size_bytes": None,
                "mode": None,
                "mtime": None,
                "error": f"unexpected stat output: {text!r}",
            }

        if not isinstance(stat_result, tuple) or len(stat_result) < 9:
            return {
                "ok": False,
                "path": path,
                "kind": None,
                "size_bytes": None,
                "mode": None,
                "mtime": None,
                "error": f"unexpected stat output: {stat_result!r}",
            }

        mode = stat_result[0] if isinstance(stat_result[0], int) else None
        size = stat_result[6] if isinstance(stat_result[6], int) else None
        mtime = stat_result[8] if isinstance(stat_result[8], int) else None
        return {
            "ok": True,
            "path": path,
            "kind": _kind_from_mode(mode),
            "size_bytes": size,
            "mode": mode,
            "mtime": mtime,
            "error": None,
        }

    def _hash_remote_file(path: str, timeout: int, algorithm: str = "sha256") -> HashFileResult:
        if algorithm.lower() != "sha256":
            return {
                "ok": False,
                "path": path,
                "algorithm": algorithm,
                "digest": "",
                "size_bytes": 0,
                "error": "unsupported hash algorithm",
            }

        data, error = _read_file_bytes(path, float(timeout))
        if error is not None or data is None:
            return {
                "ok": False,
                "path": path,
                "algorithm": "sha256",
                "digest": "",
                "size_bytes": 0,
                "error": error or "hash file failed",
            }

        return {
            "ok": True,
            "path": path,
            "algorithm": "sha256",
            "digest": _compute_sha256(data),
            "size_bytes": len(data),
            "error": None,
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
try:
    for entry in os.ilistdir({path!r}):
        print(repr(entry))
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
            text = line.strip()
            if not text:
                continue
            if text.startswith("ERROR:"):
                return {
                    "ok": False,
                    "path": path,
                    "entries": [],
                    "error": text[len("ERROR:") :].strip(),
                }

            try:
                raw_entry = ast.literal_eval(text)
            except Exception:
                return {
                    "ok": False,
                    "path": path,
                    "entries": [],
                    "error": f"unexpected ilistdir output: {text!r}",
                }

            if not isinstance(raw_entry, tuple) or len(raw_entry) < 2:
                return {
                    "ok": False,
                    "path": path,
                    "entries": [],
                    "error": f"unexpected ilistdir entry: {raw_entry!r}",
                }

            name = raw_entry[0]
            mode = raw_entry[1]
            size = raw_entry[3] if len(raw_entry) >= 4 else None
            if not isinstance(name, str) or not isinstance(mode, int):
                return {
                    "ok": False,
                    "path": path,
                    "entries": [],
                    "error": f"unexpected ilistdir entry: {raw_entry!r}",
                }

            entries.append(
                {
                    "name": name,
                    "path": _path_join(path, name),
                    "kind": _kind_from_mode(mode),
                    "size_bytes": size if isinstance(size, int) else None,
                    "mode": mode,
                }
            )

        return {
            "ok": True,
            "path": path,
            "entries": entries,
            "error": None,
        }

    @mcp.tool()
    def micropython_stat_path(path: str) -> StatPathResult:
        """
        MicroPython ボード上のパス情報を取得する。

        Args:
            path: 対象パス
        """
        return _stat_path(path)

    @mcp.tool()
    def micropython_read_file(
        path: str,
        timeout: int = 5,
        encoding: str = "utf-8",
        errors: str = "strict",
        as_base64: bool = False,
    ) -> ReadFileResult:
        """
        MicroPython ボードのファイルを読み出して返す。

        Args:
            path: 読み出すファイルのパス (例: "/main.py")
            timeout: コード送信から Raw REPL 復帰完了までの全体タイムアウト秒数
            encoding: テキストデコードに使うエンコーディング
            errors: テキストデコード時のエラー処理
            as_base64: True のときは base64 文字列として返す
        """
        data, error = _read_file_bytes(path, float(timeout))
        if error is not None or data is None:
            return {
                "ok": False,
                "path": path,
                "content": "",
                "content_base64": None,
                "size_bytes": 0,
                "error": error or "read file failed",
            }

        if as_base64:
            return {
                "ok": True,
                "path": path,
                "content": "",
                "content_base64": base64.b64encode(data).decode("ascii"),
                "size_bytes": len(data),
                "error": None,
            }

        try:
            content = data.decode(encoding, errors=errors)
        except Exception as e:
            return {
                "ok": False,
                "path": path,
                "content": "",
                "content_base64": None,
                "size_bytes": len(data),
                "error": str(e),
            }

        return {
            "ok": True,
            "path": path,
            "content": content,
            "content_base64": None,
            "size_bytes": len(data),
            "error": None,
        }

    @mcp.tool()
    def micropython_read_hardware_md(timeout: int = 5) -> ReadFileResult:
        """
        デバイス上の /HARDWARE.md を読み出して返す。
        GPIO 割り当てや接続部品の前提確認用のショートカット。

        Args:
            timeout: コード送信から Raw REPL 復帰完了までの全体タイムアウト秒数
        """
        data, error = _read_file_bytes(HARDWARE_MD_PATH, float(timeout))
        if error is not None or data is None:
            return {
                "ok": False,
                "path": HARDWARE_MD_PATH,
                "content": "",
                "content_base64": None,
                "size_bytes": 0,
                "error": error or "read file failed",
            }

        try:
            content = data.decode("utf-8", errors="strict")
        except Exception as e:
            return {
                "ok": False,
                "path": HARDWARE_MD_PATH,
                "content": "",
                "content_base64": None,
                "size_bytes": len(data),
                "error": str(e),
            }

        return {
            "ok": True,
            "path": HARDWARE_MD_PATH,
            "content": content,
            "content_base64": None,
            "size_bytes": len(data),
            "error": None,
        }

    @mcp.tool()
    def micropython_upload_file(
        local_path: str,
        remote_path: str,
        timeout: int = 20,
        overwrite: bool = True,
    ) -> UploadFileResult:
        """
        ローカルファイルを MicroPython ボードへ転送する。

        Args:
            local_path: ホスト側ファイルパス
            remote_path: デバイス側ファイルパス
            timeout: コード送信から Raw REPL 復帰完了までの全体タイムアウト秒数
            overwrite: False のとき既存ファイルを上書きしない
        """
        data, resolved_local_path, error = _read_local_file_bytes(local_path)
        local_path_value = str(resolved_local_path) if resolved_local_path is not None else local_path
        if error is not None or data is None:
            return {
                "ok": False,
                "local_path": local_path_value,
                "remote_path": remote_path,
                "bytes_written": 0,
                "sha256": None,
                "error": error or "upload file failed",
            }

        if not overwrite:
            stat_result = _stat_path(remote_path)
            if stat_result["ok"]:
                return {
                    "ok": False,
                    "local_path": local_path_value,
                    "remote_path": remote_path,
                    "bytes_written": 0,
                    "sha256": None,
                    "error": "remote file already exists",
                }

        write_result = _write_file_bytes(remote_path, data, mode="wb", timeout=float(timeout))
        return {
            "ok": write_result["ok"],
            "local_path": local_path_value,
            "remote_path": remote_path,
            "bytes_written": write_result["bytes_written"],
            "sha256": _compute_sha256(data) if write_result["ok"] else None,
            "error": write_result["error"],
        }

    @mcp.tool()
    def micropython_download_file(
        remote_path: str,
        local_path: str,
        timeout: int = 20,
        overwrite: bool = False,
    ) -> DownloadFileResult:
        """
        MicroPython ボード上のファイルをローカルへ保存する。

        Args:
            remote_path: デバイス側ファイルパス
            local_path: ホスト側保存先パス
            timeout: コード送信から Raw REPL 復帰完了までの全体タイムアウト秒数
            overwrite: False のとき既存ファイルを上書きしない
        """
        resolved_local_path, path_error = _ensure_local_workspace_path(local_path)
        local_path_value = str(resolved_local_path) if resolved_local_path is not None else local_path
        if path_error is not None:
            return {
                "ok": False,
                "remote_path": remote_path,
                "local_path": local_path_value,
                "bytes_written": 0,
                "sha256": None,
                "error": path_error,
            }

        data, error = _read_file_bytes(remote_path, float(timeout))
        if error is not None or data is None:
            return {
                "ok": False,
                "remote_path": remote_path,
                "local_path": local_path_value,
                "bytes_written": 0,
                "sha256": None,
                "error": error or "download file failed",
            }

        bytes_written, resolved_written_path, write_error = _write_local_file_bytes(local_path, data, overwrite)
        local_path_value = str(resolved_written_path) if resolved_written_path is not None else local_path_value
        return {
            "ok": write_error is None,
            "remote_path": remote_path,
            "local_path": local_path_value,
            "bytes_written": bytes_written,
            "sha256": _compute_sha256(data) if write_error is None else None,
            "error": write_error,
        }

    @mcp.tool()
    def micropython_hash_file(
        path: str,
        algorithm: str = "sha256",
        timeout: int = 10,
    ) -> HashFileResult:
        """
        MicroPython ボード上のファイルのハッシュを返す。

        Args:
            path: 対象ファイルパス
            algorithm: ハッシュアルゴリズム。現状は sha256 のみ
            timeout: コード送信から Raw REPL 復帰完了までの全体タイムアウト秒数
        """
        return _hash_remote_file(path, timeout, algorithm)

    @mcp.tool()
    def micropython_compare_local_remote(
        local_path: str,
        remote_path: str,
        timeout: int = 10,
    ) -> CompareLocalRemoteResult:
        """
        ローカルファイルとデバイス上のファイルが一致するか確認する。

        Args:
            local_path: ホスト側ファイルパス
            remote_path: デバイス側ファイルパス
            timeout: コード送信から Raw REPL 復帰完了までの全体タイムアウト秒数
        """
        local_data, resolved_local_path, local_error = _read_local_file_bytes(local_path)
        local_path_value = str(resolved_local_path) if resolved_local_path is not None else local_path
        if local_error is not None or local_data is None:
            return {
                "ok": False,
                "local_path": local_path_value,
                "remote_path": remote_path,
                "local_sha256": None,
                "remote_sha256": None,
                "same": False,
                "error": local_error or "compare failed",
            }
        local_sha256 = _compute_sha256(local_data)

        remote_hash = _hash_remote_file(remote_path, timeout)
        if not remote_hash["ok"]:
            return {
                "ok": False,
                "local_path": local_path_value,
                "remote_path": remote_path,
                "local_sha256": local_sha256,
                "remote_sha256": None,
                "same": False,
                "error": remote_hash["error"],
            }
        remote_sha256 = remote_hash["digest"]

        return {
            "ok": True,
            "local_path": local_path_value,
            "remote_path": remote_path,
            "local_sha256": local_sha256,
            "remote_sha256": remote_sha256,
            "same": local_sha256 == remote_sha256,
            "error": None,
        }

    @mcp.tool()
    def micropython_read_lines(
        path: str,
        start_line: int = 1,
        max_lines: int = 50,
        timeout: int = 10,
        encoding: str = "utf-8",
        errors: str = "strict",
    ) -> ReadLinesResult:
        """
        MicroPython ボード上のテキストファイルを行単位で一部読み出す。

        Args:
            path: 対象ファイルパス
            start_line: 1 始まりの開始行番号
            max_lines: 返却する最大行数
            timeout: コード送信から Raw REPL 復帰完了までの全体タイムアウト秒数
            encoding: テキストデコードに使うエンコーディング
            errors: テキストデコード時のエラー処理
        """
        if start_line < 1:
            return {
                "ok": False,
                "path": path,
                "start_line": start_line,
                "line_count": 0,
                "content": "",
                "eof": False,
                "error": "start_line must be >= 1",
            }
        if max_lines < 1:
            return {
                "ok": False,
                "path": path,
                "start_line": start_line,
                "line_count": 0,
                "content": "",
                "eof": False,
                "error": "max_lines must be >= 1",
            }

        content, _, error = _read_text_file(path, timeout, encoding, errors)
        if error is not None or content is None:
            return {
                "ok": False,
                "path": path,
                "start_line": start_line,
                "line_count": 0,
                "content": "",
                "eof": False,
                "error": error or "read file lines failed",
            }

        all_lines = _split_lines(content, keepends=True)
        start_index = start_line - 1
        selected = all_lines[start_index : start_index + max_lines]
        return {
            "ok": True,
            "path": path,
            "start_line": start_line,
            "line_count": len(selected),
            "content": "".join(selected),
            "eof": start_index + len(selected) >= len(all_lines),
            "error": None,
        }

    @mcp.tool()
    def micropython_head_lines(
        path: str,
        lines: int = 40,
        timeout: int = 10,
        encoding: str = "utf-8",
        errors: str = "strict",
    ) -> ReadTextExcerptResult:
        """
        MicroPython ボード上のテキストファイル先頭の数行を返す。

        Args:
            path: 対象ファイルパス
            lines: 返却する最大行数
            timeout: コード送信から Raw REPL 復帰完了までの全体タイムアウト秒数
            encoding: テキストデコードに使うエンコーディング
            errors: テキストデコード時のエラー処理
        """
        if lines < 1:
            return {"ok": False, "path": path, "content": "", "line_count": 0, "truncated": False, "error": "lines must be >= 1"}

        content, _, error = _read_text_file(path, timeout, encoding, errors)
        if error is not None or content is None:
            return {
                "ok": False,
                "path": path,
                "content": "",
                "line_count": 0,
                "truncated": False,
                "error": error or "head file failed",
            }

        all_lines = _split_lines(content, keepends=True)
        excerpt_lines = all_lines[:lines]
        return {
            "ok": True,
            "path": path,
            "content": "".join(excerpt_lines),
            "line_count": len(excerpt_lines),
            "truncated": len(excerpt_lines) < len(all_lines),
            "error": None,
        }

    @mcp.tool()
    def micropython_tail_lines(
        path: str,
        lines: int = 40,
        timeout: int = 10,
        encoding: str = "utf-8",
        errors: str = "strict",
    ) -> ReadTextExcerptResult:
        """
        MicroPython ボード上のテキストファイル末尾の数行を返す。

        Args:
            path: 対象ファイルパス
            lines: 返却する最大行数
            timeout: コード送信から Raw REPL 復帰完了までの全体タイムアウト秒数
            encoding: テキストデコードに使うエンコーディング
            errors: テキストデコード時のエラー処理
        """
        if lines < 1:
            return {"ok": False, "path": path, "content": "", "line_count": 0, "truncated": False, "error": "lines must be >= 1"}

        content, _, error = _read_text_file(path, timeout, encoding, errors)
        if error is not None or content is None:
            return {
                "ok": False,
                "path": path,
                "content": "",
                "line_count": 0,
                "truncated": False,
                "error": error or "tail file failed",
            }

        all_lines = _split_lines(content, keepends=True)
        excerpt_lines = all_lines[-lines:]
        return {
            "ok": True,
            "path": path,
            "content": "".join(excerpt_lines),
            "line_count": len(excerpt_lines),
            "truncated": len(excerpt_lines) < len(all_lines),
            "error": None,
        }

    @mcp.tool()
    def micropython_write_file(
        path: str,
        content: str | None = None,
        timeout: int = 10,
        encoding: str = "utf-8",
        content_base64: str | None = None,
    ) -> WriteFileResult:
        """
        MicroPython ボードのファイルに内容を書き込む（上書き）。

        Args:
            path: 書き込み先ファイルのパス (例: "/main.py")
            content: 書き込むテキスト内容
            timeout: コード送信から Raw REPL 復帰完了までの全体タイムアウト秒数
            encoding: content をバイト列に変換するエンコーディング
            content_base64: base64 で表した書き込みデータ
        """
        data, error = _resolve_write_bytes(
            content=content,
            content_base64=content_base64,
            encoding=encoding,
        )
        if error is not None or data is None:
            return {
                "ok": False,
                "path": path,
                "bytes_written": 0,
                "error": error or "write file failed",
            }
        return _write_file_bytes(path=path, data=data, mode="wb", timeout=float(timeout))

    @mcp.tool()
    def micropython_append_file(
        path: str,
        content: str | None = None,
        timeout: int = 10,
        encoding: str = "utf-8",
        content_base64: str | None = None,
    ) -> WriteFileResult:
        """
        MicroPython ボードのファイルに内容を追記する。

        Args:
            path: 追記先ファイルのパス (例: "/main.py")
            content: 追記するテキスト内容
            timeout: コード送信から Raw REPL 復帰完了までの全体タイムアウト秒数
            encoding: content をバイト列に変換するエンコーディング
            content_base64: base64 で表した追記データ
        """
        data, error = _resolve_write_bytes(
            content=content,
            content_base64=content_base64,
            encoding=encoding,
        )
        if error is not None or data is None:
            return {
                "ok": False,
                "path": path,
                "bytes_written": 0,
                "error": error or "append file failed",
            }
        return _write_file_bytes(path=path, data=data, mode="ab", timeout=float(timeout))

    @mcp.tool()
    def micropython_delete_file(path: str) -> DeleteFileResult:
        """
        MicroPython ボード上のファイルを削除する。

        Args:
            path: 削除するファイルのパス (例: "/test.py")
        """
        ok, error = _exec_simple(
            f"import os\ntry:\n os.remove({path!r})\n print('OK')\nexcept Exception as e:\n print(f'ERROR: {{e}}')",
            timeout=5.0,
            default_error="delete file failed",
        )
        return {"ok": ok, "path": path, "error": error}

    @mcp.tool()
    def micropython_make_dir(
        path: str,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> MakeDirResult:
        """
        MicroPython ボード上にディレクトリを作成する。

        Args:
            path: 作成するディレクトリパス
            parents: True のときは親ディレクトリも順に作成
            exist_ok: True のときは既存ディレクトリを許容
        """
        code = f"""\
import os
path = {path!r}
parents = {parents!r}
exist_ok = {exist_ok!r}
try:
    if parents:
        current = ''
        for part in path.split('/'):
            if not part:
                continue
            current += '/' + part
            try:
                os.mkdir(current)
            except OSError:
                try:
                    mode = os.stat(current)[0]
                    if not (mode & {STAT_DIR_MASK}):
                        raise
                except Exception:
                    raise
    else:
        os.mkdir(path)
    print('OK')
except Exception as e:
    if exist_ok:
        try:
            mode = os.stat(path)[0]
            if mode & {STAT_DIR_MASK}:
                print('OK')
            else:
                print(f'ERROR: {{e}}')
        except Exception:
            print(f'ERROR: {{e}}')
    else:
        print(f'ERROR: {{e}}')
"""
        ok, error = _exec_simple(code, timeout=5.0, default_error="make dir failed")
        return {"ok": ok, "path": path, "parents": parents, "error": error}

    @mcp.tool()
    def micropython_remove_dir(path: str) -> DeleteFileResult:
        """
        MicroPython ボード上の空ディレクトリを削除する。

        Args:
            path: 削除するディレクトリのパス
        """
        ok, error = _exec_simple(
            f"import os\ntry:\n os.rmdir({path!r})\n print('OK')\nexcept Exception as e:\n print(f'ERROR: {{e}}')",
            timeout=5.0,
            default_error="remove dir failed",
        )
        return {"ok": ok, "path": path, "error": error}

    @mcp.tool()
    def micropython_rename_path(src: str, dst: str) -> RenamePathResult:
        """
        MicroPython ボード上のパスを rename/move する。

        Args:
            src: 移動元パス
            dst: 移動先パス
        """
        ok, error = _exec_simple(
            f"import os\ntry:\n os.rename({src!r}, {dst!r})\n print('OK')\nexcept Exception as e:\n print(f'ERROR: {{e}}')",
            timeout=5.0,
            default_error="rename path failed",
        )
        return {"ok": ok, "src": src, "dst": dst, "error": error}
