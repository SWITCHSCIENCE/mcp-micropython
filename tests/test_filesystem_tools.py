from __future__ import annotations

import base64
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from mcp_micropython.raw_repl import ReplResult
from mcp_micropython.tools import filesystem


class FakeFastMCP:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = func
            return func

        return decorator


class FakeRawRepl:
    def __init__(self) -> None:
        self.calls: list[tuple[str, float]] = []
        self.results: list[ReplResult] = []
        self.enter_count = 0
        self.exit_count = 0

    def queue(self, *results: ReplResult) -> None:
        self.results.extend(results)

    def enter(self) -> None:
        self.enter_count += 1

    def exit(self) -> None:
        self.exit_count += 1

    def exec_code(self, code: str, timeout: float = 10.0) -> ReplResult:
        self.calls.append((code, timeout))
        if self.results:
            return self.results.pop(0)
        return ReplResult(stdout="", stderr="")


class FakeManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, float]] = []
        self._next_result = ReplResult(stdout="", stderr="")
        self.raw_repl_instance = FakeRawRepl()

    def set_result(self, stdout: str = "", stderr: str = "") -> None:
        self._next_result = ReplResult(stdout=stdout, stderr=stderr)

    def exec_code(self, code: str, timeout: float = 10.0) -> ReplResult:
        self.calls.append((code, timeout))
        return self._next_result

    @contextmanager
    def raw_repl(self):
        yield self.raw_repl_instance


class FilesystemToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = FakeManager()
        self.mcp = FakeFastMCP()
        filesystem.register(self.mcp, self.manager)

    def test_read_file_uses_default_timeout(self) -> None:
        repl = self.manager.raw_repl_instance
        repl.queue(
            ReplResult(stdout="", stderr=""),
            ReplResult(stdout="b'hello'\n", stderr=""),
            ReplResult(stdout="b''\n", stderr=""),
            ReplResult(stdout="", stderr=""),
        )

        result = self.mcp.tools["micropython_read_file"]("/main.py")

        self.assertTrue(result["ok"])
        self.assertEqual(result["content"], "hello")
        self.assertEqual(repl.calls[0][1], 5.0)
        self.assertEqual(repl.calls[1][1], 5.0)

    def test_read_file_as_base64_returns_binary_payload(self) -> None:
        repl = self.manager.raw_repl_instance
        repl.queue(
            ReplResult(stdout="", stderr=""),
            ReplResult(stdout="b'\\r\\n\\x00A'\n", stderr=""),
            ReplResult(stdout="b''\n", stderr=""),
            ReplResult(stdout="", stderr=""),
        )

        result = self.mcp.tools["micropython_read_file"]("/blob.bin", as_base64=True, timeout=12)

        self.assertTrue(result["ok"])
        self.assertEqual(result["content"], "")
        self.assertEqual(result["content_base64"], base64.b64encode(b"\r\n\x00A").decode("ascii"))
        self.assertEqual(repl.calls[0][1], 12.0)

    def test_read_hardware_md_uses_custom_timeout(self) -> None:
        repl = self.manager.raw_repl_instance
        repl.queue(
            ReplResult(stdout="", stderr=""),
            ReplResult(stdout="b'# Board'\n", stderr=""),
            ReplResult(stdout="b''\n", stderr=""),
            ReplResult(stdout="", stderr=""),
        )

        result = self.mcp.tools["micropython_read_hardware_md"](timeout=9)

        self.assertTrue(result["ok"])
        self.assertEqual(result["path"], "/HARDWARE.md")
        self.assertEqual(repl.calls[0][1], 9.0)

    def test_write_file_uses_default_timeout(self) -> None:
        repl = self.manager.raw_repl_instance
        repl.queue(
            ReplResult(stdout="", stderr=""),
            ReplResult(stdout="", stderr=""),
        )

        result = self.mcp.tools["micropython_write_file"]("/main.py", content="print('x')")

        self.assertTrue(result["ok"])
        self.assertEqual(result["bytes_written"], len("print('x')".encode("utf-8")))
        self.assertEqual(repl.calls[0][1], 10.0)
        self.assertEqual(repl.calls[1][1], 10.0)

    def test_write_file_accepts_base64_payload(self) -> None:
        repl = self.manager.raw_repl_instance
        repl.queue(
            ReplResult(stdout="", stderr=""),
            ReplResult(stdout="", stderr=""),
            ReplResult(stdout="", stderr=""),
        )
        payload = base64.b64encode(b"\r\n\x00A").decode("ascii")

        result = self.mcp.tools["micropython_write_file"]("/blob.bin", content_base64=payload, timeout=18)

        self.assertTrue(result["ok"])
        self.assertEqual(result["bytes_written"], 4)
        self.assertEqual(repl.calls[0][1], 18.0)

    def test_append_file_uses_binary_append_mode(self) -> None:
        repl = self.manager.raw_repl_instance
        repl.queue(
            ReplResult(stdout="", stderr=""),
            ReplResult(stdout="", stderr=""),
        )

        result = self.mcp.tools["micropython_append_file"]("/main.py", content="chunk", timeout=18)

        self.assertTrue(result["ok"])
        self.assertIn("'ab'", repl.calls[0][0])
        self.assertEqual(repl.calls[0][1], 18.0)

    def test_write_file_rejects_ambiguous_inputs(self) -> None:
        result = self.mcp.tools["micropython_write_file"](
            "/main.py",
            content="x",
            content_base64=base64.b64encode(b"x").decode("ascii"),
        )

        self.assertFalse(result["ok"])
        self.assertIn("exactly one", result["error"])

    def test_upload_file_reads_local_file_and_returns_hash(self) -> None:
        repl = self.manager.raw_repl_instance
        repl.queue(
            ReplResult(stdout="", stderr=""),
            ReplResult(stdout="", stderr=""),
        )

        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            local_path = Path(temp_dir) / "main.py"
            local_path.write_text("print('hello')\n", encoding="utf-8")
            expected_size = len(local_path.read_bytes())

            result = self.mcp.tools["micropython_upload_file"](str(local_path), "/main.py")

        self.assertTrue(result["ok"])
        self.assertEqual(result["bytes_written"], expected_size)
        self.assertIsNotNone(result["sha256"])

    def test_download_file_saves_local_workspace_file(self) -> None:
        repl = self.manager.raw_repl_instance
        repl.queue(
            ReplResult(stdout="", stderr=""),
            ReplResult(stdout="b'line1\\nline2\\n'\n", stderr=""),
            ReplResult(stdout="b''\n", stderr=""),
            ReplResult(stdout="", stderr=""),
        )

        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            local_path = Path(temp_dir) / "downloaded.txt"
            result = self.mcp.tools["micropython_download_file"]("/main.py", str(local_path))

            self.assertTrue(result["ok"])
            self.assertEqual(local_path.read_text(encoding="utf-8"), "line1\nline2\n")
            self.assertEqual(result["bytes_written"], len("line1\nline2\n".encode("utf-8")))

    def test_hash_file_returns_sha256(self) -> None:
        repl = self.manager.raw_repl_instance
        repl.queue(
            ReplResult(stdout="", stderr=""),
            ReplResult(stdout="b'abc'\n", stderr=""),
            ReplResult(stdout="b''\n", stderr=""),
            ReplResult(stdout="", stderr=""),
        )

        result = self.mcp.tools["micropython_hash_file"]("/main.py")

        self.assertTrue(result["ok"])
        self.assertEqual(result["algorithm"], "sha256")
        self.assertEqual(
            result["digest"],
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        )

    def test_compare_local_remote_reports_same_content(self) -> None:
        repl = self.manager.raw_repl_instance
        repl.queue(
            ReplResult(stdout="", stderr=""),
            ReplResult(stdout="b'abc'\n", stderr=""),
            ReplResult(stdout="b''\n", stderr=""),
            ReplResult(stdout="", stderr=""),
        )

        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            local_path = Path(temp_dir) / "same.txt"
            local_path.write_text("abc", encoding="utf-8")

            result = self.mcp.tools["micropython_compare_local_remote"](str(local_path), "/main.py")

        self.assertTrue(result["ok"])
        self.assertTrue(result["same"])

    def test_read_lines_returns_numbered_lines(self) -> None:
        repl = self.manager.raw_repl_instance
        repl.queue(
            ReplResult(stdout="", stderr=""),
            ReplResult(stdout="b'a\\nb\\nc\\nd\\n'\n", stderr=""),
            ReplResult(stdout="b''\n", stderr=""),
            ReplResult(stdout="", stderr=""),
        )

        result = self.mcp.tools["micropython_read_lines"]("/main.py", start_line=2, max_lines=2)

        self.assertTrue(result["ok"])
        self.assertEqual(result["start_line"], 2)
        self.assertEqual(result["line_count"], 2)
        self.assertEqual(result["content"], "b\nc\n")
        self.assertFalse(result["eof"])

    def test_head_lines_returns_first_lines(self) -> None:
        repl = self.manager.raw_repl_instance
        repl.queue(
            ReplResult(stdout="", stderr=""),
            ReplResult(stdout="b'a\\nb\\nc\\n'\n", stderr=""),
            ReplResult(stdout="b''\n", stderr=""),
            ReplResult(stdout="", stderr=""),
        )

        result = self.mcp.tools["micropython_head_lines"]("/main.py", lines=2)

        self.assertTrue(result["ok"])
        self.assertEqual(result["content"], "a\nb\n")
        self.assertTrue(result["truncated"])

    def test_head_lines_preserves_blank_lines_in_content(self) -> None:
        repl = self.manager.raw_repl_instance
        repl.queue(
            ReplResult(stdout="", stderr=""),
            ReplResult(stdout="b'a\\nb\\n\\n'\n", stderr=""),
            ReplResult(stdout="b''\n", stderr=""),
            ReplResult(stdout="", stderr=""),
        )

        result = self.mcp.tools["micropython_head_lines"]("/main.py", lines=3)

        self.assertTrue(result["ok"])
        self.assertEqual(result["line_count"], 3)
        self.assertEqual(result["content"], "a\nb\n\n")
        self.assertFalse(result["truncated"])

    def test_tail_lines_returns_last_lines(self) -> None:
        repl = self.manager.raw_repl_instance
        repl.queue(
            ReplResult(stdout="", stderr=""),
            ReplResult(stdout="b'a\\nb\\nc\\n'\n", stderr=""),
            ReplResult(stdout="b''\n", stderr=""),
            ReplResult(stdout="", stderr=""),
        )

        result = self.mcp.tools["micropython_tail_lines"]("/main.py", lines=2)

        self.assertTrue(result["ok"])
        self.assertEqual(result["content"], "b\nc\n")
        self.assertTrue(result["truncated"])

    def test_list_files_parses_ilistdir_entries(self) -> None:
        self.manager.set_result(stdout="('boot.py', 32768, 0, 12)\n('lib', 16384, 0)\n")

        result = self.mcp.tools["micropython_list_files"]("/")

        self.assertTrue(result["ok"])
        self.assertEqual(result["entries"][0]["kind"], "file")
        self.assertEqual(result["entries"][0]["size_bytes"], 12)
        self.assertEqual(result["entries"][1]["kind"], "dir")
        self.assertEqual(result["entries"][1]["path"], "/lib")

    def test_stat_path_parses_mode_size_and_mtime(self) -> None:
        self.manager.set_result(stdout="(32768, 0, 0, 0, 0, 0, 42, 0, 1710000000, 0)\n")

        result = self.mcp.tools["micropython_stat_path"]("/main.py")

        self.assertTrue(result["ok"])
        self.assertEqual(result["kind"], "file")
        self.assertEqual(result["size_bytes"], 42)
        self.assertEqual(result["mtime"], 1710000000)

    def test_make_dir_uses_default_timeout(self) -> None:
        self.manager.set_result(stdout="OK\n")

        result = self.mcp.tools["micropython_make_dir"]("/lib/pkg", parents=True, exist_ok=True)

        self.assertTrue(result["ok"])
        self.assertEqual(self.manager.calls[-1][1], 5.0)

    def test_rename_path_uses_default_timeout(self) -> None:
        self.manager.set_result(stdout="OK\n")

        result = self.mcp.tools["micropython_rename_path"]("/old.py", "/new.py")

        self.assertTrue(result["ok"])
        self.assertEqual(result["dst"], "/new.py")
        self.assertEqual(self.manager.calls[-1][1], 5.0)


if __name__ == "__main__":
    unittest.main()
