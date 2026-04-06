# mcp-micropython

MicroPython REPL への MCP ブリッジサーバー。

Claude Desktop, Codex (VSCode), Copilot (VSCode), Antigravity などの MCP クライアントから、
USB Serial 経由で MicroPython (ESP32, RP2040, etc.) を操作できます。

## セットアップ

```powershell
# 依存関係のインストール
uv sync

# サーバー起動（動作確認用）
uv run mcp-micropython
```

## MicroPython ファームウェアの書き込み

このツールを使用するには、ターゲットデバイスに MicroPython ファームウェアを本体に書き込む必要があります。
詳細は [MicroPython 公式サイト](https://micropython.org/) を参照してください。

### ターゲット別ダウンロードページ

- [ESP32](https://micropython.org/download/?mcu=esp32)
- [ESP32-S3](https://micropython.org/download/?mcu=esp32s3)
- [ESP32-C5](https://micropython.org/download/?mcu=esp32c5)
- [RP2040](https://micropython.org/download/?mcu=rp2040)
- [RP2350](https://micropython.org/download/?mcu=rp2350)

### ESP32 へのインストール例 (`esptool.py`)

ESP32 シリーズは `esptool.py` を利用してコマンドラインからインストールできます。

1. `esptool` をインストール:
   ```bash
   pip install esptool
   ```
2. 既存フラッシュの消去:
   ```bash
   esptool.py --chip esp32 --port COMx erase_flash
   ```
3. 新しいファームウェアの書き込み:
   ```bash
   esptool.py --chip esp32 --port COMx --baud 460800 write_flash -z 0x1000 <firmware_file>.bin
   ```
   (※ チップの種類 (esp32, esp32s3, etc.) や構成により、書き込みアドレスが `0x0` になる場合があります。詳細は各ダウンロードページの指示に従ってください)


## MCP クライアントへの登録

`claude_desktop_config_example.json` を参考に、各クライアントの設定ファイルに追記してください。

```json
{
  "mcpServers": {
    "micropython": {
      "command": "uv",
      "args": [
        "--directory",
        "C:\\Users\\sasaki.yusuke\\144Lab\\0079_MCP",
        "run",
        "mcp-micropython"
      ]
    }
  }
}
```

## 提供ツール

| ツール | 説明 |
|---|---|
| `micropython_list_ports` | 利用可能なシリアルポートを列挙 |
| `micropython_connect` | 指定ポートに接続 |
| `micropython_disconnect` | 接続を切断 |
| `micropython_exec` | Python コードをブロック実行 |
| `micropython_eval` | 式を評価して値を返す |
| `micropython_get_info` | デバイス情報取得 |
| `micropython_reset` | ソフトリセット |
| `micropython_list_files` | ファイル一覧 |
| `micropython_read_file` | ファイル読み出し |
| `micropython_write_file` | ファイル書き込み |
| `micropython_delete_file` | ファイル削除 |
