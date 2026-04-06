# mcp-esp32

ESP32 MicroPython REPL への MCP ブリッジサーバー。

Claude Desktop, Codex (VSCode), Copilot (VSCode), Antigravity などの MCP クライアントから、
USB Serial 経由で ESP32 上の MicroPython インタープリタを操作できます。

## セットアップ

```powershell
# 依存関係のインストール
uv sync

# サーバー起動（動作確認用）
uv run mcp-esp32
```

## MCP クライアントへの登録

`claude_desktop_config_example.json` を参考に、各クライアントの設定ファイルに追記してください。

```json
{
  "mcpServers": {
    "esp32": {
      "command": "uv",
      "args": [
        "--directory",
        "C:\\Users\\sasaki.yusuke\\144Lab\\0079_MCP",
        "run",
        "mcp-esp32"
      ]
    }
  }
}
```

## 提供ツール

| ツール | 説明 |
|---|---|
| `esp32_list_ports` | 利用可能なシリアルポートを列挙 |
| `esp32_connect` | 指定ポートに接続 |
| `esp32_disconnect` | 接続を切断 |
| `esp32_exec` | Python コードをブロック実行 |
| `esp32_eval` | 式を評価して値を返す |
| `esp32_get_info` | デバイス情報取得 |
| `esp32_reset` | ソフトリセット |
| `esp32_list_files` | ファイル一覧 |
| `esp32_read_file` | ファイル読み出し |
| `esp32_write_file` | ファイル書き込み |
| `esp32_delete_file` | ファイル削除 |
