# WebREPL 対応設計プラン

## 概要

既存の MicroPython MCP Bridge は USB シリアル接続を前提としている。
WebREPL 対応では、従来の serial 運用を維持しつつ、同じ `micropython_connect`
ツールで WebREPL 接続も扱えるようにする。

WebREPL 対応では、ボード側の Wi-Fi 接続と `webrepl.start()` は
この MCP サーバーの外で事前設定済みである前提にする。
MCP サーバーは設定済みの WebREPL へ
`micropython_connect(target="host[:port]", password="...")` で接続する。

---

## 目標

- WebREPL を使わない場合は、従来どおり `list ports -> connect serial` の流れを維持する
- WebREPL を使う場合は、ボード側で事前設定された host と password で接続できる
- MCP サーバーは 1 つのままにし、内部で serial / WebREPL を切り替える
- ホスト側で接続プロファイルは持たない

---

## 接続導線

### 1. Serial 運用

通常運用では、以下の流れを維持する。

1. `micropython_list_ports`
2. `micropython_connect(target="COMx", baudrate=115200)`
3. `micropython_exec` など既存ツールを利用

### 2. WebREPL 運用

WebREPL の初期設定は、ユーザーが別経路で完了しておく。
MCP サーバーは設定済みの host を直接指定して接続する。

1. `micropython_connect(target="192.168.0.10", password="secret")`
2. `micropython_exec` など既存ツールを利用

`target` が `host[:port]` 形式のときは WebREPL 接続として扱う。
port 省略時は `8266` を使う。

---

## 接続管理アーキテクチャ

### SessionManager への再編

従来の `SerialManager` は serial 専用の責務を持っていたため、
transport を抽象化した `SessionManager` 相当へ再編する。

- 現在接続中の transport を 1 つ保持する
- `connect`, `disconnect`, `exec_code`, `eval_expr`, `interrupt`, `reset` を提供する
- ストリーム読み取り API も transport 非依存に統一する
- serial 専用操作は `require_serial_connection()` で明示的に制約する

### Transport 抽象化

transport は以下の 2 種類を持つ。

- `SerialTransport`
- `WebReplTransport`

上位の execution / filesystem / device ツールは transport の違いを意識しない。

### Raw REPL の扱い

`raw_repl.py` は serial 前提ではなく、REPL 寄りの共通 I/F に依存する形へ寄せる。

- `send_bytes`
- `read_some`
- `read_byte`
- `flush`
- `drain_pending_input`

Serial / WebREPL の両方で同じ REPL 実行フローを使う。

---

## ツール設計

接続系ツールは次の構成に整理する。

- `micropython_list_ports`
- `micropython_connect`
- `micropython_disconnect`
- `micropython_connection_status`

### ツールごとの役割

`micropython_list_ports`

- 利用可能なシリアルポートを列挙する
- 初回の serial 接続先を決めるために使う

`micropython_connect`

- `target` 引数 1 本で serial / WebREPL を切り替える
- `COM3` のような値は serial 接続として扱う
- `host[:port]` のような値は WebREPL 接続として扱う
- WebREPL 接続時は `password` を必須とする
- serial 接続時のみ `baudrate` を使う

`micropython_connection_status`

- 現在の接続状態を返す
- `connected`, `transport`, `target` を返す
- serial 時は `port`, `baudrate` も返す
- WebREPL 時は `host`, `port` を返す

WebREPL の初期セットアップや秘密情報管理は MCP サーバーの責務に含めない。

---

## 既存ツールへの影響

`micropython_exec`, `micropython_eval`, `micropython_list_files`,
`micropython_read_file`, `micropython_write_file`, `micropython_delete_file`,
`micropython_interrupt`, `micropython_reset` などの既存ツールは、
接続中 transport が serial でも WebREPL でも同じ名前で使えるようにする。

これにより、接続方法だけが変わり、上位の操作体験はできるだけ統一される。

### 読み取り系ツール

出力読み取り系は transport 共通の意味に寄せる。

- 正式名: `micropython_read_stream`
- 正式名: `micropython_read_until`
- 旧 `micropython_serial_read` / `micropython_serial_read_until` は互換 alias として残す

### Serial 専用ツール

`micropython_reset_and_capture` は serial 専用のままとする。

- serial 接続では従来どおり利用できる
- WebREPL 接続中に呼ばれた場合は unsupported error を返す

---

## テスト観点

- serial 運用で現行機能が後退しないこと
- `micropython_connect("COMx")` で serial 接続できること
- `micropython_connect("host")` / `micropython_connect("host:port")` が WebREPL として解釈されること
- WebREPL 接続で exec/eval/filesystem/device 系ツールが成立すること
- `micropython_reset_and_capture` が serial では動作し、WebREPL では unsupported になること
- `micropython_read_stream` / `micropython_read_until` が serial / WebREPL の両方で使えること

---

## 前提と割り切り

- WebREPL 対応対象は `webrepl` が利用可能な標準的な MicroPython ボードとする
- ボード側の Wi-Fi 接続と WebREPL 有効化は MCP サーバー外で事前設定する
- WebREPL 接続先は `host[:port]` 入力のみ対応し、URL 形式・SSL・path 指定は扱わない
- WebREPL の既定 port は `8266`
- ホスト側の接続プロファイル管理は行わない
- MCP サーバー登録を複数に分けず、1 つのサーバー内で transport を切り替える
