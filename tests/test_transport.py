from __future__ import annotations

import socket
import struct
import unittest

from mcp_micropython.transport import WebReplTransport, _SimpleWebSocket


def make_frame(payload: bytes, opcode: int = 0x1) -> bytes:
    payload_len = len(payload)
    if payload_len < 126:
        header = struct.pack(">BB", 0x80 | opcode, payload_len)
    elif payload_len < 65536:
        header = struct.pack(">BBH", 0x80 | opcode, 126, payload_len)
    else:
        header = struct.pack(">BBQ", 0x80 | opcode, 127, payload_len)
    return header + payload


class FakeSocket:
    def __init__(self, chunks: list[bytes], timeout_exc: bool = False) -> None:
        self._chunks = list(chunks)
        self._timeout = None
        self._timeout_exc = timeout_exc
        self.recv_calls = 0
        self.recv_sizes: list[int] = []

    def gettimeout(self) -> float | None:
        return self._timeout

    def settimeout(self, timeout: float | None) -> None:
        self._timeout = timeout

    def recv(self, size: int) -> bytes:
        self.recv_calls += 1
        self.recv_sizes.append(size)
        if self._chunks:
            return self._chunks.pop(0)
        if self._timeout_exc:
            raise socket.timeout("timed out waiting for websocket data")
        return b""


class SimpleWebSocketTests(unittest.TestCase):
    def test_read_frame_reuses_prefetched_socket_bytes(self) -> None:
        sock = FakeSocket([make_frame(b"abc") + make_frame(b"defg")])
        ws = _SimpleWebSocket(sock)

        first = ws.read_frame(timeout=1.0)
        second = ws.read_frame(timeout=1.0)

        self.assertEqual(first, b"abc")
        self.assertEqual(second, b"defg")
        self.assertEqual(sock.recv_calls, 1)
        self.assertGreaterEqual(sock.recv_sizes[0], 4096)

    def test_read_frame_uses_prefetched_bytes_for_following_frame(self) -> None:
        sock = FakeSocket([make_frame(b"hello") + make_frame(b"world")])
        ws = _SimpleWebSocket(sock)

        self.assertEqual(ws.read_frame(timeout=1.0), b"hello")
        self.assertEqual(ws.read_frame(timeout=1.0), b"world")
        self.assertEqual(sock.recv_calls, 1)

    def test_read_frame_reassembles_fragmented_frame(self) -> None:
        frame = make_frame(b"chunked")
        sock = FakeSocket([frame[:1], frame[1:4], frame[4:]])
        ws = _SimpleWebSocket(sock)

        result = ws.read_frame(timeout=1.0)

        self.assertEqual(result, b"chunked")
        self.assertEqual(sock.recv_calls, 3)

    def test_read_frame_raises_connection_error_for_close_frame(self) -> None:
        sock = FakeSocket([make_frame(b"", opcode=0x8)])
        ws = _SimpleWebSocket(sock)

        with self.assertRaises(ConnectionError):
            ws.read_frame(timeout=1.0)

    def test_read_frame_raises_timeout_when_frame_is_incomplete(self) -> None:
        sock = FakeSocket([b"\x81"], timeout_exc=True)
        ws = _SimpleWebSocket(sock)

        with self.assertRaises(TimeoutError):
            ws.read_frame(timeout=1.0)


class WebReplTransportReadSomeTests(unittest.TestCase):
    def test_read_some_returns_whole_frame_payload(self) -> None:
        sock = FakeSocket([make_frame(b"raw repl output")])
        ws = _SimpleWebSocket(sock)

        transport = object.__new__(WebReplTransport)
        transport._ws = ws

        result = transport.read_some(timeout=1.0)

        self.assertEqual(result, b"raw repl output")
        self.assertEqual(sock.recv_calls, 1)

    def test_read_some_returns_empty_bytes_on_timeout(self) -> None:
        sock = FakeSocket([], timeout_exc=True)
        ws = _SimpleWebSocket(sock)

        transport = object.__new__(WebReplTransport)
        transport._ws = ws

        self.assertEqual(transport.read_some(timeout=0.1), b"")


if __name__ == "__main__":
    unittest.main()
