# WebREPL 対応設計プラン

## 概要

既存の MicroPython MCP Bridge は USB シリアル接続を前提としている。
WebREPL 対応では、従来の serial 運用を維持しつつ、同じ `micropython_connect`
ツールで WebREPL 接続も扱えるようにする。

初回の WebREPL セットアップは serial 接続から開始し、
`micropython_webrepl_bootstrap` で Wi-Fi 接続設定と `webrepl.start()`
をデバイス側 `boot.py` へ反映する。
bootstrap 完了後も現在のセッションは serial 接続を維持し、次回以降に
`micropython_connect(target="host[:port]", password="...")` で WebREPL 接続する。

---

## 目標

- WebREPL を使わない場合は、従来どおり `list ports -> connect serial` の流れを維持する
- WebREPL を使う場合は、初回だけ serial 接続で bootstrap を実行する
- bootstrap 後は host と password を指定して WebREPL 接続できる
- MCP サーバーは 1 つのままにし、内部で serial / WebREPL を切り替える
- ホスト側で接続プロファイルは持たない

---

## 接続導線

### 1. Serial 運用

通常運用では、以下の流れを維持する。

1. `micropython_list_ports`
2. `micropython_connect(target="COMx", baudrate=115200)`
3. `micropython_exec` など既存ツールを利用

### 2. 初回 WebREPL セットアップ

WebREPL の初回導入は、serial 接続中のデバイスに対して行う。

1. `micropython_list_ports`
2. `micropython_connect(target="COMx", baudrate=115200)`
3. `micropython_webrepl_bootstrap(ssid=..., wifi_password=..., webrepl_password=...)`

`micropython_webrepl_bootstrap` はデバイスの `boot.py` を管理ブロック方式で更新し、
Wi-Fi 接続と `webrepl.start(password=...)` を永続化する。

### 3. 次回以降の WebREPL 運用

bootstrap 後は host を直接指定して接続する。

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
- `micropython_webrepl_bootstrap`

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

`micropython_webrepl_bootstrap`

- serial 接続中のデバイスで WebREPL を有効化する
- `ssid`, `wifi_password`, `webrepl_password` を受け取る
- Wi-Fi 接続確認と `webrepl.start()` を実行して成功確認する
- `boot.py` の管理ブロックを更新する
- 実行後も現在のセッションは serial のまま維持する

---

## Bootstrap 仕様

`micropython_webrepl_bootstrap` は STA モード専用とする。
AP_IF は今回サポートしない。

### 入力項目

- `ssid`
- `wifi_password`
- `webrepl_password`

### 処理内容

- serial 接続中のデバイスで Wi-Fi 接続を試行する
- 接続後の IP を取得する
- `webrepl.start(password=...)` を実行する
- `boot.py` の管理ブロックを更新する

### `boot.py` 更新方針

`boot.py` は管理ブロック方式で更新する。

- 管理ブロックが存在しなければ末尾に追加する
- 管理ブロックが既に存在すればその範囲だけ上書きする
- 管理ブロック外の既存コードは保持する

管理ブロック内には以下を記述する。

- `network.WLAN(network.STA_IF)` の有効化
- 既存接続を切ってから `ssid` / `wifi_password` で再接続
- タイムアウト付きの接続待機
- `webrepl.start(password=...)`

### 成功条件

- Wi-Fi 接続が成功し、IP を取得できること
- `webrepl.start()` がエラーなく実行できること

### 上書き方針

- 既に設定済みであっても、bootstrap 実行時は管理ブロックを上書きする
- ホスト側で接続情報は保存しない

---

## セッション切り替え方針

bootstrap 実行直後に現在セッションを WebREPL へ切り替えることはしない。

理由:

- bootstrap は設定反映までを責務とする方がわかりやすい
- 現在の serial 接続セッションを壊さずに作業を続けられる
- 次回以降に `micropython_connect(target="host[:port]", password="...")`
  で WebREPL 側へ接続する方が運用が安定する

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
- bootstrap 実行で `boot.py` の管理ブロックが追加・更新されること
- 既存 `boot.py` の管理ブロック外コードが保持されること
- bootstrap 成功時に Wi-Fi 接続後の IP を取得できること
- bootstrap 成功時に `webrepl.start()` が有効になること
- `webrepl` 未導入、Wi-Fi 接続失敗、IP 未取得、接続タイムアウト時に原因が分かるエラーになること
- `micropython_reset_and_capture` が serial では動作し、WebREPL では unsupported になること
- `micropython_read_stream` / `micropython_read_until` が serial / WebREPL の両方で使えること

---

## 前提と割り切り

- WebREPL 対応対象は `webrepl` が利用可能な標準的な MicroPython ボードとする
- 初回 WebREPL セットアップは serial 接続済み状態から始める
- Wi-Fi 接続は `STA_IF` のみ対象とする
- AP_IF は今回サポートしない
- WebREPL 接続先は `host[:port]` 入力のみ対応し、URL 形式・SSL・path 指定は扱わない
- WebREPL の既定 port は `8266`
- ホスト側の接続プロファイル管理は行わない
- MCP サーバー登録を複数に分けず、1 つのサーバー内で transport を切り替える
