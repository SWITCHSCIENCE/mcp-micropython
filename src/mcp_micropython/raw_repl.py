"""
raw_repl.py — MicroPython Raw REPL プロトコル実装

MicroPython の Raw REPL モードを使ってコードを送受信する。

Raw REPL の流れ (mpremote 実装準拠):
  1. Ctrl+C x2 で現在の実行をキャンセル
  2. Ctrl+A でRaw REPLモードに入る
     ボードは "raw REPL; CTRL-B to exit\r\n>" を返す
  3. コードを送信し Ctrl+D で実行トリガー
     ボードは "OK" を返してから実行開始
  4. 実行完了後 stdout\x04stderr\x04> が返ってくる
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .transport import StreamTransport

# Raw REPL 制御文字
CTRL_A = b"\x01"   # Raw REPL モードへ
CTRL_B = b"\x02"   # Normal REPL モードへ
CTRL_C = b"\x03"   # 実行中断
CTRL_D = b"\x04"   # 実行トリガー / レスポンス区切り

# タイムアウト定数 (秒)
DEFAULT_TIMEOUT = 10.0
ENTER_TIMEOUT = 5.0


@dataclass
class ReplResult:
    """Raw REPL 実行結果"""
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.stderr == ""

    def __str__(self) -> str:
        if self.stderr:
            return f"[ERROR]\n{self.stderr}"
        return self.stdout


class RawReplError(Exception):
    """Raw REPL 操作に関するエラー"""


class RawRepl:
    """MicroPython Raw REPL プロトコルの実装 (mpremote 準拠)"""

    def __init__(self, stream: StreamTransport) -> None:
        self._stream = stream
        self._read_buffer = bytearray()

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def enter(self) -> None:
        """Raw REPL モードに入る。失敗時は RawReplError を送出。"""
        self._read_buffer.clear()
        # 実行中の処理をキャンセルしてプロンプトを出す
        self._stream.send_bytes(CTRL_C)
        self._stream.send_bytes(CTRL_C)
        time.sleep(0.2)
        self._stream.drain_pending_input()

        # Raw REPL へ移行  (mpremote: exec_raw 参照)
        self._stream.send_bytes(CTRL_A)
        try:
            # "raw REPL; CTRL-B to exit\r\n>" を待つ
            self._read_until(b"\r\n>", timeout=ENTER_TIMEOUT)
        except TimeoutError:
            # フォールバック: 一部のファームウェアでは異なる文字列を返す
            pass

        # 念のためバッファをクリア
        time.sleep(0.05)
        self._stream.drain_pending_input()

    def exit(self) -> None:
        """Normal REPL モードに戻る。"""
        self._stream.send_bytes(CTRL_B)
        time.sleep(0.1)
        self._stream.drain_pending_input()
        self._read_buffer.clear()

    def exec_code(self, code: str, timeout: float = DEFAULT_TIMEOUT) -> ReplResult:
        """
        コードを Raw REPL で実行し結果を返す。

        Args:
            code: 実行する Python コード（複数行OK）
            timeout: コード送信から Raw REPL 復帰完了までの全体タイムアウト（秒）

        Returns:
            ReplResult: stdout / stderr を含む実行結果

        Raises:
            RawReplError: 通信エラーや予期しないレスポンス
        """
        if timeout < 0:
            raise ValueError("timeout must be >= 0")

        # コードを送信後 Ctrl+D で実行トリガー (mpremote 準拠)
        encoded = code.encode("utf-8")
        self._stream.send_bytes(encoded)
        self._stream.send_bytes(CTRL_D)
        self._stream.flush()
        deadline = time.monotonic() + timeout

        # "OK" を待つ
        self._read_until_with_budget(b"OK", deadline=deadline, stage="'OK' 応答")

        # stdout を \x04 まで読む
        stdout_bytes = self._read_until_with_budget(CTRL_D, deadline=deadline, stage="stdout")

        # stderr を \x04 まで読む
        stderr_bytes = self._read_until_with_budget(CTRL_D, deadline=deadline, stage="stderr")

        # 終端プロンプト ">" を読み捨てる
        self._read_until_with_budget(b">", deadline=deadline, stage="Raw REPL プロンプト復帰")

        return ReplResult(
            stdout=stdout_bytes.decode("utf-8", errors="replace"),
            stderr=stderr_bytes.decode("utf-8", errors="replace"),
        )

    def exec_code_safe(self, code: str, timeout: float = DEFAULT_TIMEOUT) -> ReplResult:
        """
        enter() → exec_code() → exit() をまとめて実行する便利メソッド。
        """
        self.enter()
        try:
            return self.exec_code(code, timeout=timeout)
        finally:
            self.exit()

    # ------------------------------------------------------------------
    # 内部ユーティリティ
    # ------------------------------------------------------------------

    def _read_until_with_budget(self, terminator: bytes, deadline: float, stage: str) -> bytes:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RawReplError(
                f"{stage} の待機を開始する前にタイムアウトしました。"
                " exec_code(timeout=...) はコード送信から Raw REPL 復帰までの全体予算です。"
            )
        try:
            return self._read_until(terminator, timeout=remaining)
        except TimeoutError as e:
            raise RawReplError(f"{stage} の受信中にタイムアウトしました: {e}") from e

    def _read_until(self, terminator: bytes, timeout: float = DEFAULT_TIMEOUT) -> bytes:
        """
        terminator が現れるまでバイト列を読み込む。
        terminator 自体は戻り値に含まない。

        実機対応: できるだけチャンクで読み、terminator をまたいで先読みした
        データは内部バッファへ戻す。大きな stdout でも 1 バイトずつ読まない。

        Raises:
            TimeoutError: timeout 秒以内に terminator が現れなかった
        """
        buf = bytearray()
        deadline = time.monotonic() + timeout

        while True:
            if self._read_buffer:
                chunk = bytes(self._read_buffer)
                self._read_buffer.clear()
            else:
                remaining = max(deadline - time.monotonic(), 0.0)
                if remaining <= 0:
                    raise TimeoutError(
                        f"タイムアウト: {terminator!r} を {timeout:.1f}秒以内に受信できません。"
                        f" 受信済みデータ: {bytes(buf)!r}"
                    )
                chunk = self._stream.read_some(timeout=min(0.25, remaining))

            if chunk:
                buf.extend(chunk)
                idx = buf.find(terminator)
                if idx != -1:
                    end = idx + len(terminator)
                    trailing = buf[end:]
                    if trailing:
                        self._read_buffer[:0] = trailing
                    return bytes(buf[:idx])

            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"タイムアウト: {terminator!r} を {timeout:.1f}秒以内に受信できません。"
                    f" 受信済みデータ: {bytes(buf)!r}"
                )
