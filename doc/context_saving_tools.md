# コンテキスト節約向けツール追加案

## 目的

LLM にファイル全文を渡さずに、次の作業を完結しやすくすること。

- ローカル PC とデバイス間のファイル転送
- 差分確認
- 必要箇所だけの部分取得
- サーバー側での簡易検索

既存の `micropython_read_file` / `micropython_write_file` は残し、
低コンテキスト向けツールを追加する方針。

---

## 優先順位

1. `upload` / `download`
2. `hash` / `compare`
3. `read_lines` / `head_lines` / `tail_lines` / `grep`
4. 将来必要なら `sync_dir`

---

## Phase 1: 転送系

### `micropython_upload_file`

ローカルファイルをデバイスへ転送する。

```python
def micropython_upload_file(
    local_path: str,
    remote_path: str,
    timeout: int = 20,
    overwrite: bool = True,
) -> UploadFileResult:
    ...
```

戻り値案:

```python
class UploadFileResult(TypedDict):
    ok: bool
    local_path: str
    remote_path: str
    bytes_written: int
    sha256: str | None
    error: str | None
```

仕様:

- `local_path` はホスト側パス
- `remote_path` はデバイス側パス
- ホストでファイルを読み、既存の `_write_file_bytes()` を再利用
- `overwrite=False` かつ既存ファイルありなら失敗
- 成功時はアップロードした内容の `sha256` を返す

用途:

- LLM に本文を渡さず、`main.py` や asset をそのまま転送

### `micropython_download_file`

デバイスファイルをローカルへ保存する。

```python
def micropython_download_file(
    remote_path: str,
    local_path: str,
    timeout: int = 20,
    overwrite: bool = False,
) -> DownloadFileResult:
    ...
```

戻り値案:

```python
class DownloadFileResult(TypedDict):
    ok: bool
    remote_path: str
    local_path: str
    bytes_written: int
    sha256: str | None
    error: str | None
```

仕様:

- `remote_path` を `_read_file_bytes()` で取得
- `local_path` はワークスペース配下のみ許可
- 親ディレクトリがなければ失敗
- `overwrite=False` かつ既存ファイルありなら失敗

用途:

- 退避
- 比較用保存
- ローカル diff ツール利用

---

## Phase 2: 差分確認系

### `micropython_hash_file`

デバイスファイルの内容ハッシュを返す。

```python
def micropython_hash_file(
    path: str,
    algorithm: str = "sha256",
    timeout: int = 10,
) -> HashFileResult:
    ...
```

戻り値案:

```python
class HashFileResult(TypedDict):
    ok: bool
    path: str
    algorithm: str
    digest: str
    size_bytes: int
    error: str | None
```

仕様:

- 初期実装はホスト側で `_read_file_bytes()` 後に `hashlib.sha256`
- 将来、デバイス側実装に寄せてもよい

用途:

- 差分有無だけ知りたい
- 再転送要否判定

### `micropython_compare_local_remote`

ローカルとデバイスの一致判定。

```python
def micropython_compare_local_remote(
    local_path: str,
    remote_path: str,
    timeout: int = 10,
) -> CompareLocalRemoteResult:
    ...
```

戻り値案:

```python
class CompareLocalRemoteResult(TypedDict):
    ok: bool
    local_path: str
    remote_path: str
    local_sha256: str | None
    remote_sha256: str | None
    same: bool
    error: str | None
```

用途:

- LLM に本文を渡さず一致判定
- `sync` 実装の下敷き

---

## Phase 3: 部分取得・検索系

### `micropython_read_lines`

ファイルの一部分を行単位で返す。

```python
def micropython_read_lines(
    path: str,
    start_line: int = 1,
    max_lines: int = 50,
    timeout: int = 10,
    encoding: str = "utf-8",
    errors: str = "strict",
) -> ReadFileLinesResult:
    ...
```

戻り値案:

```python
class ReadFileLinesResult(TypedDict):
    ok: bool
    path: str
    start_line: int
    line_count: int
    content: str
    eof: bool
    error: str | None
```

用途:

- コードの前後数行確認
- ログの一部確認
- 行番号つきで LLM に渡す

### `micropython_head_lines`

先頭 N 行だけ返す。

```python
def micropython_head_lines(
    path: str,
    lines: int = 40,
    timeout: int = 10,
    encoding: str = "utf-8",
    errors: str = "strict",
) -> ReadTextExcerptResult:
    ...
```

### `micropython_tail_lines`

末尾 N 行だけ返す。

```python
def micropython_tail_lines(
    path: str,
    lines: int = 40,
    timeout: int = 10,
    encoding: str = "utf-8",
    errors: str = "strict",
) -> ReadTextExcerptResult:
    ...
```

共通戻り値案:

```python
class ReadTextExcerptResult(TypedDict):
    ok: bool
    path: str
    content: str
    line_count: int
    truncated: bool
    error: str | None
```

用途:

- `/boot.py` やログの確認
- 末尾エラーだけ確認

### `micropython_grep_file`

単純な文字列検索。

```python
def micropython_grep_file(
    path: str,
    pattern: str,
    timeout: int = 10,
    ignore_case: bool = False,
    max_matches: int = 20,
) -> GrepFileResult:
    ...
```

戻り値案:

```python
class GrepMatch(TypedDict):
    line_no: int
    line: str


class GrepFileResult(TypedDict):
    ok: bool
    path: str
    pattern: str
    matches: list[GrepMatch]
    truncated: bool
    error: str | None
```

仕様:

- 正規表現より先に部分文字列一致で十分
- `max_matches` で打ち切り

用途:

- `import wifi_config`
- `Pin(`
- `webrepl.start`

---

## Phase 4: 将来の同期系

### `micropython_sync_file`

ローカルとデバイスを比較し、差分があるときだけ転送する。

```python
def micropython_sync_file(
    local_path: str,
    remote_path: str,
    timeout: int = 20,
) -> SyncFileResult:
    ...
```

戻り値案:

```python
class SyncFileResult(TypedDict):
    ok: bool
    local_path: str
    remote_path: str
    changed: bool
    bytes_written: int
    local_sha256: str | None
    remote_sha256_before: str | None
    remote_sha256_after: str | None
    error: str | None
```

`sync_dir` はこの上に載せる構成が安全。

---

## 実装メモ

対象ファイル:

- `src\mcp_micropython\tools\filesystem.py`
- `README.md`
- 必要なら `tests\test_filesystem_tools.py`

既存コードの再利用候補:

- `_read_file_bytes()`
- `_write_file_bytes()`
- `_resolve_write_bytes()`

ホスト側処理として追加したい helper:

```python
def _compute_sha256(data: bytes) -> str: ...
def _ensure_local_workspace_path(local_path: str) -> Path: ...
def _read_local_file_bytes(local_path: str) -> bytes: ...
def _write_local_file_bytes(local_path: str, data: bytes, overwrite: bool) -> int: ...
```

---

## 安全策

- `download` の保存先はワークスペース配下のみ
- `upload` / `download` は `overwrite` を明示
- 巨大ファイルはサイズ上限を設ける
- `grep` は `max_matches` を必須で持つ
- `read_lines` は `max_lines` 上限を持つ

---

## 最小実装セット

最初の 1 回は次だけで十分。

- `micropython_upload_file`
- `micropython_download_file`
- `micropython_hash_file`
- `micropython_compare_local_remote`
- `micropython_read_lines`
- `micropython_head_lines`
- `micropython_tail_lines`

この 7 本で、全文転記なしの運用がかなり増える。
