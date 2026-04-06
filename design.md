# ESP32 MicroPython MCP Bridge — 設計ドキュメント

## 概要

ESP32上のMicroPython REPLに対して、MCPクライアント（Claude Desktopなど）から
Pythonコードの実行・ファイル操作・デバイス制御ができるブリッジサーバーを作る。

---

## システム構成

```
┌─────────────────────┐        MCP Protocol (stdio/SSE)        ┌──────────────────────────┐
│   MCP Client         │ ◄──────────────────────────────────── │   MCP Server (Python)    │
│  (Claude Desktop,   │                                         │   mcp_esp32_bridge       │
│   Cursor, etc.)     │                                         │                          │
└─────────────────────┘                                         │  ┌────────────────────┐  │
                                                                │  │  Serial Manager    │  │
                                                                │  │  (pyserial)        │  │
                                                                │  └────────┬───────────┘  │
                                                                └───────────┼──────────────┘
                                                                            │ USB/UART Serial
                                                                    ┌───────▼───────────┐
                                                                    │  ESP32             │
                                                                    │  MicroPython REPL  │
                                                                    └───────────────────┘
```

---

## コンポーネント設計

### 1. MCP Server レイヤー (`server.py`)

- **プロトコル**: MCPの `stdio` トランスポートを使用（Claude Desktopと接続する場合の標準）
- **ライブラリ**: `mcp` Python SDK（`pip install mcp`）
- **責務**: MCPツール定義・リクエスト受付・レスポンス返却

### 2. Serial Manager レイヤー (`serial_manager.py`)

- **ライブラリ**: `pyserial`
- **責務**: ESP32とのシリアル通信管理
  - REPL制御（`Ctrl+C` でキャンセル、`Ctrl+D` でリセット）
  - Raw REPL モード（`Ctrl+A`）を使ってコードを確実に送信
  - タイムアウト付き応答受信
  - 接続管理（自動再接続）

### 3. ツール定義 (`tools/`)

各MCPツールを機能ごとにモジュール化する。

---

## MCPツール一覧（提供する機能）

| ツール名 | 説明 | 主なパラメータ |
|---|---|---|
| `esp32_exec` | Pythonコードをブロック実行し結果を返す | `code: str`, `timeout: int` |
| `esp32_eval` | 式を評価して値を返す | `expression: str` |
| `esp32_list_files` | ファイルシステム上のファイル一覧 | `path: str = "/"` |
| `esp32_read_file` | ファイルの内容を読み出す | `path: str` |
| `esp32_write_file` | ファイルに内容を書き込む | `path: str`, `content: str` |
| `esp32_delete_file` | ファイルを削除する | `path: str` |
| `esp32_reset` | ソフトリセット（`machine.reset()`） | なし |
| `esp32_get_info` | デバイス情報（チップ情報・空きメモリ等）を取得 | なし |
| `esp32_list_ports` | 利用可能なシリアルポートを列挙する | なし |
| `esp32_connect` | 指定ポートに接続する | `port: str`, `baudrate: int = 115200` |
| `esp32_disconnect` | シリアル接続を切断する | なし |

---

## ESP32との通信プロトコル詳細

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
  Ctrl+A  →  ESP32が "raw REPL; CTRL-B to exit\r\n>" を返す
  <code>  →  コードを送信
  Ctrl+D  →  実行トリガー
  ESP32が "OK<stdout>\x04<stderr>\x04>" を返す
  ```
- **構造化されたレスポンスが取れるため、自動処理に最適**

---

## ディレクトリ構成（案）

```
0079_MCP/
├── design.md                  # このファイル
├── README.md
├── pyproject.toml             # パッケージ定義（uvまたはpoetry）
├── src/
│   └── mcp_esp32/
│       ├── __init__.py
│       ├── server.py          # MCPサーバーエントリポイント
│       ├── serial_manager.py  # シリアル通信管理
│       ├── raw_repl.py        # Raw REPL プロトコル実装
│       └── tools/
│           ├── __init__.py
│           ├── execution.py   # exec/eval ツール
│           ├── filesystem.py  # ファイル操作ツール
│           └── device.py      # デバイス情報・接続管理ツール
├── tests/
│   ├── test_serial_manager.py
│   ├── test_raw_repl.py
│   └── fixtures/             # モックESP32レスポンス
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
- [ ] `serial_manager.py`: ポート検索・接続・切断
- [ ] `raw_repl.py`: Raw REPLモードでのコード送受信
- [ ] 単体テスト（実機なしでもモックで動作確認）

### Phase 2: MCPサーバー骨格
- [ ] `server.py`: MCPサーバーの起動・ツール登録
- [ ] `esp32_connect` / `esp32_disconnect` / `esp32_list_ports` ツール
- [ ] Claude Desktopで接続確認

### Phase 3: 実行ツール
- [ ] `esp32_exec`: コードブロック実行
- [ ] `esp32_eval`: 式評価
- [ ] `esp32_get_info`: デバイス情報取得

### Phase 4: ファイルシステムツール
- [ ] `esp32_list_files`
- [ ] `esp32_read_file` / `esp32_write_file` / `esp32_delete_file`

### Phase 5: 品質・UX
- [ ] タイムアウト・エラーハンドリングの強化
- [ ] 自動再接続
- [ ] ドキュメント整備

---

## 検討事項・リスク

| 項目 | 内容 |
|---|---|
| 文字コード | ESP32からのレスポンスはUTF-8だが、バイナリファイルは別対応が必要 |
| 大きなファイル転送 | `write_file`でファイルが大きい場合は分割送信が必要（REPLの行長制限） |
| 並列アクセス | MCP Clientから複数の同時リクエストが来た場合のシリアル通信の排他制御 |
| ポートの固定 | OSによってCOMポート名が変わるため、設定ファイルで指定できるようにする |
| Raw REPLの安定性 | 通信エラー時にREPLが壊れた状態になりうる → リセット機構が必要 |

---

## 参考リンク

- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MicroPython Raw REPL仕様](https://docs.micropython.org/en/latest/reference/repl.html#raw-mode)
- [pyserial docs](https://pyserial.readthedocs.io/)
- [mpremote ソースコード](https://github.com/micropython/micropython/tree/master/tools/mpremote)（Raw REPL実装の参考）
