# mcp-micropython-bridge

MicroPython REPL への MCP ブリッジサーバー。

Claude Desktop, Codex (VSCode), Copilot (VSCode), Antigravity などの MCP クライアントから、
USB Serial または WebREPL 経由で MicroPython (ESP32, RP2040, etc.) を操作できます。

`HARDWARE.md` を単なる配線メモではなく、将来のセッションが再利用するためのボード固有ドキュメントとして育てていく運用を想定しています。たとえばサーボ操作の依頼が来たら、その場限りのコード片で済ませるのではなく、小さな helper module をデバイス上に作成し、今後の使い方や前提が増えたときだけ `HARDWARE.md` に短い利用メモを追記して、次回以降はその helper を再利用する形を推奨します。

## セットアップ

```powershell
# 依存関係のインストール
uv sync

# サーバー起動（動作確認用）
uv run mcp-micropython-bridge

# tools ラッパー経由の実機テスト CLI
uv run python -m mcp_micropython.device_test_cli --target COM3
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
        "C:\\mcp-micropython-bridge",
        "run",
        "mcp-micropython-bridge"
      ]
    }
  }
}
```

## 提供リソース

| リソース | 説明 |
|---|---|
| `micropython://guide/recipes` | よくある作業の進め方 |
| `micropython://policy/hardware-docs` | `HARDWARE.md` を更新すべき条件 |
| `micropython://guide/troubleshooting` | よくある問題の復旧手順 |
| `micropython://guide/limitations` | 既知の制約一覧 |

## 提供ツール

| ツール | 説明 |
|---|---|
| `micropython_list_ports` | 利用可能なシリアルポートを列挙 |
| `micropython_connect` | `COM3` または `host[:port]` に接続 |
| `micropython_disconnect` | 接続を切断 |
| `micropython_connection_status` | 現在の接続状態を取得 |
| `micropython_exec` | Python コードをブロック実行 |
| `micropython_eval` | 式を評価して値を返す |
| `micropython_get_info` | デバイス情報取得 |
| `micropython_reset` | ソフトリセット |
| `micropython_interrupt` | Ctrl-C を送って実行中の処理を中断 |
| `micropython_read_stream` | 一定時間ぶんの出力を読む |
| `micropython_read_until` | 特定文字列が出るまで待つ |
| `micropython_reset_and_capture` | ボードをリセットして起動ログを取得（serial 専用） |
| `micropython_list_files` | ファイル一覧 |
| `micropython_stat_path` | パス情報取得 |
| `micropython_read_file` | ファイル読み出し |
| `micropython_read_lines` | 行単位で一部読み出し |
| `micropython_head_lines` | 先頭数行を読み出し |
| `micropython_tail_lines` | 末尾数行を読み出し |
| `micropython_read_hardware_md` | `/HARDWARE.md` を読み出し |
| `micropython_upload_file` | ローカルファイルをデバイスへ転送 |
| `micropython_download_file` | デバイスファイルをローカルへ保存 |
| `micropython_hash_file` | デバイスファイルの SHA-256 を取得 |
| `micropython_compare_local_remote` | ローカルとデバイスの一致確認 |
| `micropython_write_file` | ファイル書き込み |
| `micropython_append_file` | ファイル追記 |
| `micropython_delete_file` | ファイル削除 |
| `micropython_make_dir` | ディレクトリ作成 |
| `micropython_remove_dir` | 空ディレクトリ削除 |
| `micropython_rename_path` | パス名変更 |

`micropython_exec(timeout=...)` の `timeout` は、コード送信開始から Raw REPL への復帰完了までを含む全体予算として扱います。
`micropython_read_file` / `micropython_read_hardware_md` / `micropython_write_file` / `micropython_append_file` の `timeout` も同じ意味です。

`micropython_write_file` は `content` によるテキスト書き込みと `content_base64` によるバイナリ書き込みをサポートします。
`micropython_append_file` も同じ入出力形式で末尾追記できます。
`micropython_read_file(as_base64=True)` を使うと、改行コードや非 UTF-8 バイト列を保持したまま取得できます。

## 実機テスト CLI

`src/mcp_micropython/tools` の登録済みツール関数を `FakeMCP` 経由で呼び出し、実機に対して接続確認やファイル I/O、serial 専用の stream/reset 系チェックをまとめて実行できます。

```powershell
# Serial で拡張セットを実行
uv run python -m mcp_micropython.device_test_cli --target COM3

# WebREPL で共通テストだけ実行
uv run python -m mcp_micropython.device_test_cli --target 192.168.1.10:8266 --password secret --tests common,filesystem

# エントリーポイントから起動
uv run mcp-micropython-device-test --target COM3 --tests all
```

主なオプション:

- `--target`: `COM3` または `host[:port]`
- `--password`: WebREPL 用パスワード
- `--baudrate`: serial ボーレート
- `--tests`: `all`, `common`, `filesystem`, `serial`, `stream`, `reset`
- `--large-file-size`: 長文転送テストのサイズ
- `--exec-timeout`: `exec` / ファイル操作タイムアウト
- `--read-timeout`: `read_until` / `read_stream` / `reset_and_capture` の待機時間
- `--reconnect-timeout`: serial リセット後に COM ポートが再出現するまで待つ時間

serial で `stream` / `reset` を実行する場合、一時的に `/main.py` を差し替えて起動ログを検証したあと、元の内容へ復元します。`/boot.py` は変更しませんが、変更前提の確認として読み出します。

## WebREPL 事前設定

WebREPL 接続を使う場合は、対象ボード側の Wi-Fi 接続と `webrepl.start()` が事前設定済みである必要があります。
この MCP サーバーは設定済みの WebREPL へ接続することだけを担当し、`boot.py` への初期セットアップは行いません。

このリポジトリには、初期設定用ファイルとして `device_root\boot.py` と `device_root\setup.py` を同梱しています。

- `device_root\boot.py`
  デバイス起動時に NVS から Wi-Fi SSID / Wi-Fi パスワード / WebREPL パスワードを読み出し、Wi-Fi 接続と `webrepl.start()` を実行します
- `device_root\setup.py`
  serial REPL 上で一度だけ実行する初期設定スクリプトです。入力した値を NVS へ保存します

`setup.py` で保存する `WEBREPL_PASSWORD` は MicroPython WebREPL の制約に合わせて 8 文字以下にしてください。
資格情報はファイルではなく NVS に保存されますが、デバイス実機に保持される点は同じなので、取り扱い注意です。

設定後の流れ:

1. serial 接続で `device_root\boot.py` をデバイスの `/boot.py` として書き込む
2. serial 接続で `device_root\setup.py` をデバイスの `/setup.py` として書き込む
3. serial REPL で `import setup` を実行し、Wi-Fi SSID / Wi-Fi パスワード / WebREPL パスワードを保存する
4. ボードを再起動する
5. Wi-Fi 側で割り当てられた IP アドレスを確認し、接続する
