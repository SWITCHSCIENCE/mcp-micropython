"""
check_esp32.py — ESP32 シリアル通信の動作確認スクリプト

MCP サーバーを介さずに直接シリアル操作を確認する。

使い方:
    uv run python check_esp32.py
    uv run python check_esp32.py COM3      # ポートを直接指定
"""

import sys
from mcp_esp32.serial_manager import SerialManager

manager = SerialManager()

# --- ポート一覧 ---
print("=" * 50)
print("利用可能なシリアルポート")
print("=" * 50)
ports = manager.list_ports()
if not ports:
    print("  (見つかりません。ESP32 が接続されているか確認してください)")
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

manager.disconnect()
print("\n✓ 全テスト完了。切断しました。")
