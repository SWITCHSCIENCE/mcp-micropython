from __future__ import annotations

import unittest
from unittest.mock import patch

from mcp_micropython.raw_repl import CTRL_D, RawRepl, RawReplError


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += max(seconds, 0.0)


class FakeTransport:
    def __init__(self, clock: FakeClock, reads: list[bytes]) -> None:
        self._clock = clock
        self._reads = list(reads)
        self.sent: list[bytes] = []
        self.flushed = 0

    @property
    def transport_name(self) -> str:
        return "fake"

    @property
    def is_connected(self) -> bool:
        return True

    def connection_details(self) -> dict[str, object]:
        return {"transport": "fake"}

    def close(self) -> None:
        return None

    def send_bytes(self, data: bytes) -> None:
        self.sent.append(data)

    def read_some(self, timeout: float) -> bytes:
        self._clock.advance(timeout)
        if self._reads:
            return self._reads.pop(0)
        return b""

    def drain_pending_input(self) -> None:
        return None

    def flush(self) -> None:
        self.flushed += 1

    def interrupt(self) -> None:
        return None

    def reset_and_capture(
        self,
        capture_duration: float,
        idle_timeout: float | None = None,
        max_bytes: int | None = None,
    ) -> dict[str, object]:
        raise NotImplementedError


class RawReplExecCodeTests(unittest.TestCase):
    def test_exec_code_reads_stdout_stderr_and_prompt_with_shared_budget(self) -> None:
        clock = FakeClock()
        stdout = ("x" * 4096).encode("utf-8")
        stderr = b"warning"
        transport = FakeTransport(clock, [b"OK" + stdout + CTRL_D + stderr + CTRL_D + b">"])
        repl = RawRepl(transport)

        with patch("mcp_micropython.raw_repl.time.monotonic", clock.monotonic):
            result = repl.exec_code("print('hello')", timeout=5.0)

        self.assertEqual(result.stdout, "x" * 4096)
        self.assertEqual(result.stderr, "warning")
        self.assertEqual(transport.sent, [b"print('hello')", CTRL_D])
        self.assertEqual(transport.flushed, 1)

    def test_exec_code_allows_ok_after_more_than_three_seconds_when_budget_remains(self) -> None:
        clock = FakeClock()
        delayed_reads = [b""] * 16 + [b"OKready" + CTRL_D + CTRL_D + b">"]
        transport = FakeTransport(clock, delayed_reads)
        repl = RawRepl(transport)

        with patch("mcp_micropython.raw_repl.time.monotonic", clock.monotonic):
            result = repl.exec_code("print('ready')", timeout=5.0)

        self.assertEqual(result.stdout, "ready")
        self.assertEqual(result.stderr, "")
        self.assertGreater(clock.now, 4.0)

    def test_exec_code_timeout_reports_current_stage(self) -> None:
        clock = FakeClock()
        transport = FakeTransport(clock, [b"OK"])
        repl = RawRepl(transport)

        with patch("mcp_micropython.raw_repl.time.monotonic", clock.monotonic):
            with self.assertRaises(RawReplError) as ctx:
                repl.exec_code("print('hang')", timeout=0.5)

        self.assertIn("stdout の受信中にタイムアウト", str(ctx.exception))

    def test_exec_code_zero_timeout_fails_before_waiting_for_ok(self) -> None:
        clock = FakeClock()
        transport = FakeTransport(clock, [b"OK"])
        repl = RawRepl(transport)

        with patch("mcp_micropython.raw_repl.time.monotonic", clock.monotonic):
            with self.assertRaises(RawReplError) as ctx:
                repl.exec_code("print('x')", timeout=0.0)

        self.assertIn("'OK' 応答 の待機を開始する前にタイムアウト", str(ctx.exception))

    def test_exec_code_rejects_negative_timeout(self) -> None:
        clock = FakeClock()
        transport = FakeTransport(clock, [])
        repl = RawRepl(transport)

        with self.assertRaises(ValueError):
            repl.exec_code("print('x')", timeout=-1.0)


if __name__ == "__main__":
    unittest.main()
