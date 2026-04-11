"""
check_micropython.py — MicroPython シリアル通信の動作確認スクリプト

MCP サーバーを介さずに直接シリアル操作を確認する。

使い方:
    uv run python check_micropython.py
    uv run python check_micropython.py COM3      # ポートを直接指定
"""

import sys
from mcp_micropython.serial_manager import SerialManager

LARGE_FILE_TEST_PATH = "/check_micropython_10kb.txt"
LARGE_FILE_TEST_SIZE = 10 * 1024
TRANSFER_CHUNK_SIZE = 512


def make_test_payload(size: int) -> str:
    seed = "MicroPython large text transfer test payload.\n"
    repeat = (size // len(seed)) + 1
    return (seed * repeat)[:size]


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def exec_or_raise(repl, code: str, timeout: float = 5.0) -> str:
    result = repl.exec_code(code, timeout=timeout)
    if not result.ok:
        raise RuntimeError(result.stderr.strip() or "device execution failed")
    return result.stdout


def write_large_file(repl, path: str, payload: str) -> None:
    exec_or_raise(repl, f"open({path!r}, 'w').close()")
    for offset in range(0, len(payload), TRANSFER_CHUNK_SIZE):
        chunk = payload[offset : offset + TRANSFER_CHUNK_SIZE]
        exec_or_raise(
            repl,
            "\n".join(
                [
                    f"with open({path!r}, 'a') as f:",
                    f"    f.write({chunk!r})",
                ]
            ),
            timeout=5.0,
        )


def read_large_file(repl, path: str) -> str:
    return exec_or_raise(
        repl,
        "\n".join(
            [
                f"with open({path!r}, 'r') as f:",
                "    data = f.read()",
                "print(data, end='')",
            ]
        ),
        timeout=20.0,
    )


def delete_test_file(repl, path: str) -> None:
    exec_or_raise(
        repl,
        "\n".join(
            [
                "import os",
                "try:",
                f"    os.remove({path!r})",
                "except OSError:",
                "    pass",
            ]
        ),
    )


manager = SerialManager()

# --- ポート一覧 ---
print("=" * 50)
print("利用可能なシリアルポート")
print("=" * 50)
ports = manager.list_ports()
if not ports:
    print("  (見つかりません。MicroPython ボードが接続されているか確認してください)")
    sys.exit(1)
for p in ports:
    print(f"  {p['port']}  {p['description']}")

# --- 接続 ---
port = sys.argv[1] if len(sys.argv) > 1 else ports[0]["port"]
print(f"\n→ {port} に接続します...")
try:
    manager.connect(port)
except Exception as e:
    print(f"接続失敗: {e}")
    sys.exit(1)
print("  接続OK")

# --- デバイス情報 ---
print("\n" + "=" * 50)
print("デバイス情報")
print("=" * 50)
result = manager.exec_code("""\
import sys, gc
gc.collect()
print('platform:', sys.platform)
print('version:', '.'.join(str(v) for v in sys.version_info[:3]))
print('free_mem:', gc.mem_free(), 'bytes')
""", timeout=5.0)
if result.ok:
    print(result.stdout)
else:
    print("エラー:", result.stderr)

# --- 簡単な計算 ---
print("=" * 50)
print("eval テスト: 1 + 1")
print("=" * 50)
result = manager.eval_expr("1 + 1")
print("結果:", result.stdout.strip())

# --- コード実行 ---
print("\n" + "=" * 50)
print("exec テスト: LED 点滅（machine.Pin 確認）")
print("=" * 50)
result = manager.exec_code("""\
import machine
led = machine.Pin(2, machine.Pin.OUT)
led.value(1)
print('LED ON: OK')
led.value(0)
print('LED OFF: OK')
""", timeout=5.0)
if result.ok:
    print(result.stdout)
else:
    print("エラー (Pin 2 が存在しない場合は正常):", result.stderr.strip())

print("\n" + "=" * 50)
print("大容量テキスト往復テスト: 10KB")
print("=" * 50)
payload = make_test_payload(LARGE_FILE_TEST_SIZE)
try:
    with manager.raw_repl() as repl:
        repl.enter()
        try:
            delete_test_file(repl, LARGE_FILE_TEST_PATH)
            write_large_file(repl, LARGE_FILE_TEST_PATH, payload)
            restored = read_large_file(repl, LARGE_FILE_TEST_PATH)
            size_stdout = exec_or_raise(
                repl,
                "\n".join(
                    [
                        "import os",
                        f"print(os.stat({LARGE_FILE_TEST_PATH!r})[6])",
                    ]
                ),
            )
            board_size = int(size_stdout.strip())
        finally:
            try:
                delete_test_file(repl, LARGE_FILE_TEST_PATH)
            finally:
                repl.exit()

    if normalize_newlines(restored) != normalize_newlines(payload):
        raise RuntimeError("読み出しデータが書き込み内容と一致しません")

    print(f"  chars_written: {len(payload)}")
    print(f"  chars_read: {len(restored)}")
    print(f"  board_size: {board_size}")
    print("  verification: OK")
except Exception as e:
    print(f"エラー: {e}")

manager.disconnect()
print("\n✓ 全テスト完了。切断しました。")
