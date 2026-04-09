# MicroPython MCP Bridge — 設計ドキュメント

## 概要

MicroPython REPL (ESP32, RP2040, etc.) に対して、MCPクライアント（Claude Desktopなど）から
Pythonコードの実行・ファイル操作・デバイス制御ができるブリッジサーバーを作る。

---

## システム構成

```mermaid
flowchart LR
    client["MCP Client
    Codex / Copilot / Claude Desktop / Antigravity"]

    server["MCP Server
    mcp_micropython"]

    board["MicroPython Board
    ESP32 / RP2040 / etc."]

    client <-->|"MCP Protocol
    stdio"| server

    server <-->|"USB / UART Serial"| board

```

---

## コンポーネント設計

### 1. MCP Server レイヤー (`server.py`)

- **プロトコル**: MCPの `stdio` トランスポートを使用（Claude Desktopと接続する場合の標準）
- **ライブラリ**: `mcp` Python SDK（`pip install mcp`）
- **責務**: MCPツール定義・リクエスト受付・レスポンス返却

### 2. Serial Manager レイヤー (`serial_manager.py`)

- **ライブラリ**: `pyserial`
- **責務**: MicroPython ボードとのシリアル通信管理
  - REPL制御（`Ctrl+C` でキャンセル、`Ctrl+D` でリセット）
  - Raw REPL モード（`Ctrl+A`）を使ってコードを確実に送信
  - タイムアウト付き応答受信
  - 接続管理（自動再接続）

### 3. ツール定義 (`tools/`)

各MCPツールを機能ごとにモジュール化する。

---

## 静的リソース方針

- `micropython://guide/recipes`: よくある作業の進め方
- `micropython://policy/hardware-docs`: `HARDWARE.md` を更新すべき条件
- `micropython://guide/troubleshooting`: よくある問題の復旧手順
- `micropython://guide/limitations`: 既知の制約一覧

`HARDWARE.md` の更新判断は「ライブラリを追加したかどうか」ではなく、「将来のセッションが再利用すべきボード固有知識が増えたか」を基準にする。

---

## MCPツール一覧（提供する機能）

| ツール名 | 説明 | 主なパラメータ |
|---|---|---|
| `micropython_exec` | Pythonコードをブロック実行し結果を返す | `code: str`, `timeout: int` |
| `micropython_eval` | 式を評価して値を返す | `expression: str` |
| `micropython_list_files` | ファイルシステム上のファイル一覧 | `path: str = "/"` |
| `micropython_read_file` | ファイルの内容を読み出す | `path: str` |
| `micropython_read_hardware_md` | `/HARDWARE.md` を読み出す | なし |
| `micropython_write_file` | ファイルに内容を書き込む | `path: str`, `content: str` |
| `micropython_append_file` | ファイルに内容を追記する | `path: str`, `content: str` |
| `micropython_delete_file` | ファイルを削除する | `path: str` |
| `micropython_reset` | ソフトリセット（`machine.reset()`） | なし |
| `micropython_get_info` | デバイス情報（チップ情報・空きメモリ等）を取得 | なし |
| `micropython_list_ports` | 利用可能なシリアルポートを列挙する | なし |
| `micropython_connect` | 指定ポートに接続する | `port: str`, `baudrate: int = 115200` |
| `micropython_disconnect` | シリアル接続を切断する | なし |

---

## MicroPython との通信プロトコル詳細

MicroPython REPLには以下の2つのモードがある：

### Normal REPL
- インタラクティブ入力モード
- プロンプト: `>>> `
- 単純なコマンドに使用

### Raw REPL（推奨）
- `Ctrl+A` (`\x01`) で入行
- `Ctrl+B` (`\x02`) でノーマルREPLに戻る
- 送信フォーマット:
  ```
  Ctrl+A  →  ボードが "raw REPL; CTRL-B to exit\r\n>" を返す
  <code>  →  コードを送信
  Ctrl+D  →  実行トリガー
  ボードが "OK<stdout>\x04<stderr>\x04>" を返す
  ```
- **構造化されたレスポンスが取れるため、自動処理に最適**

---

## ディレクトリ構成

```
0079_MCP/
├── design.md                  # このファイル
├── README.md
├── pyproject.toml             # パッケージ定義（uv）
├── src/
│   └── mcp_micropython/
│       ├── __init__.py
│       ├── server.py          # MCPサーバーエントリポイント
│       ├── serial_manager.py  # シリアル通信管理
│       ├── raw_repl.py        # Raw REPL プロトコル実装
│       └── tools/
│           ├── __init__.py
│           ├── execution.py   # exec/eval ツール
│           ├── filesystem.py  # ファイル操作ツール
│           └── device.py      # デバイス情報・接続管理ツール
└── claude_desktop_config_example.json   # Claude Desktop設定例
```

---

## 確定事項（ヒアリング結果）

| 項目 | 決定内容 |
|---|---|
| MCPクライアント | Codex (VSCode), Copilot (VSCode), Antigravity |
| 接続方式 | USB-Serial のみ（WebREPL不要） |
| 実行環境 | Windows PowerShell |
| パッケージ管理 | `uv` |
| 大容量ファイル転送 | 現時点不要（将来拡張を考慮した設計にする） |

---

## 技術スタック

| 要素 | 採用技術 | 理由 |
|---|---|---|
| 言語 | Python 3.11+ | MCP SDKの推奨環境 |
| MCP SDK | `mcp[cli]` | 公式SDK |
| シリアル通信 | `pyserial` | 実績ある標準ライブラリ |
| パッケージ管理 | `uv` | 高速・モダン、Windows対応 |
| トランスポート | `stdio` | VSCode Extension系MCPクライアントの標準 |

---

## 実装フェーズ

### Phase 1: 基盤（シリアル通信）
- [x] `serial_manager.py`: ポート検索・接続・切断
- [x] `raw_repl.py`: Raw REPLモードでのコード送受信
- [ ] 単体テスト（実機なしでもモックで動作確認）

### Phase 2: MCPサーバー骨格
- [x] `server.py`: MCPサーバーの起動・ツール登録
- [x] `micropython_connect` / `micropython_disconnect` / `micropython_list_ports` ツール
- [x] Claude Desktopで接続確認

### Phase 3: 実行ツール
- [x] `micropython_exec`: コードブロック実行
- [x] `micropython_eval`: 式評価
- [x] `micropython_get_info`: デバイス情報取得

### Phase 4: ファイルシステムツール
- [x] `micropython_list_files`
- [x] `micropython_read_file` / `micropython_read_hardware_md` / `micropython_write_file` / `micropython_append_file` / `micropython_delete_file`

### Phase 5: 品質・UX
- [ ] タイムアウト・エラーハンドリングの強化
- [ ] 自動再接続
- [x] ドキュメント整備

---

## 検討事項・リスク

| 項目 | 内容 |
|---|---|
| 文字コード | MicroPythonボードからのレスポンスはUTF-8だが、バイナリファイルは別対応が必要 |
| 大きなファイル転送 | `write_file` で初期化し、`append_file` で分割追記する運用が必要（REPLの行長制限） |
| 並列アクセス | MCP Clientから複数の同時リクエストが来た場合のシリアル通信の排他制御 |
| ポートの固定 | OSによってCOMポート名が変わるため、設定ファイルで指定できるようにする |
| Raw REPLの安定性 | 通信エラー時にREPLが壊れた状態になりうる → リセット機構が必要 |

---

## 参考リンク

- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MicroPython Raw REPL仕様](https://docs.micropython.org/en/latest/reference/repl.html#raw-mode)
- [pyserial docs](https://pyserial.readthedocs.io/)
- [mpremote ソースコード](https://github.com/micropython/micropython/tree/master/tools/mpremote)（Raw REPL実装の参考）
