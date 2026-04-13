from __future__ import annotations

import unittest

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


class FakeManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, float]] = []
        self._next_result = ReplResult(stdout="", stderr="")

    def set_result(self, stdout: str = "", stderr: str = "") -> None:
        self._next_result = ReplResult(stdout=stdout, stderr=stderr)

    def exec_code(self, code: str, timeout: float = 10.0) -> ReplResult:
        self.calls.append((code, timeout))
        return self._next_result


class FilesystemToolTimeoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = FakeManager()
        self.mcp = FakeFastMCP()
        filesystem.register(self.mcp, self.manager)

    def test_read_file_uses_default_timeout(self) -> None:
        self.manager.set_result(stdout="hello")

        result = self.mcp.tools["micropython_read_file"]("/main.py")

        self.assertTrue(result["ok"])
        self.assertEqual(result["content"], "hello")
        self.assertEqual(self.manager.calls[-1][1], 5.0)

    def test_read_file_uses_custom_timeout(self) -> None:
        self.manager.set_result(stdout="hello")

        result = self.mcp.tools["micropython_read_file"]("/main.py", timeout=12)

        self.assertTrue(result["ok"])
        self.assertEqual(self.manager.calls[-1][1], 12.0)

    def test_read_hardware_md_uses_custom_timeout(self) -> None:
        self.manager.set_result(stdout="# Board")

        result = self.mcp.tools["micropython_read_hardware_md"](timeout=9)

        self.assertTrue(result["ok"])
        self.assertEqual(result["path"], "/HARDWARE.md")
        self.assertEqual(self.manager.calls[-1][1], 9.0)

    def test_write_file_uses_default_timeout(self) -> None:
        self.manager.set_result(stdout="OK\n")

        result = self.mcp.tools["micropython_write_file"]("/main.py", "print('x')")

        self.assertTrue(result["ok"])
        self.assertEqual(result["bytes_written"], len("print('x')".encode("utf-8")))
        self.assertEqual(self.manager.calls[-1][1], 10.0)

    def test_append_file_uses_custom_timeout(self) -> None:
        self.manager.set_result(stdout="OK\n")

        result = self.mcp.tools["micropython_append_file"]("/main.py", "chunk", timeout=18)

        self.assertTrue(result["ok"])
        self.assertEqual(self.manager.calls[-1][1], 18.0)


if __name__ == "__main__":
    unittest.main()
