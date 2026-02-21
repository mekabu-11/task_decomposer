# APIエンドポイント仕様

ベースURL: `http://localhost:5001`
Content-Type: `application/json`（ファイルアップロードのみ `multipart/form-data`）

---

## エンドポイント一覧

| メソッド | パス | 説明 |
|---|---|---|
| GET | `/` | メインページ（HTML） |
| POST | `/api/set-key` | APIキーをセット |
| GET | `/api/has-key` | APIキー設定済み確認 |
| POST | `/api/analyze` | メッセージを分析してタスク生成 |
| GET | `/api/tasks` | 全タスク取得 |
| DELETE | `/api/tasks/clear` | 全タスク削除 |
| POST | `/api/upload-context` | コンテキストファイルアップロード |
| GET | `/api/context` | コンテキスト読み込み状態確認 |
| DELETE | `/api/context` | コンテキスト削除 |

---

## 詳細

### `POST /api/set-key`

APIキーとプロバイダーをサーバーのメモリにセットする。

**リクエスト：**
```json
{
  "apiKey": "sk-ant-api03-...",
  "provider": "anthropic"
}
```

`provider` に指定できる値：`"anthropic"` / `"gemini"`（省略時は `"anthropic"`）

**レスポンス（200）：**
```json
{ "ok": true }
```

---

### `GET /api/has-key`

APIキーが設定済みか、および現在のプロバイダーを確認する。

**レスポンス（200）：**
```json
{ "hasKey": true, "provider": "anthropic" }
```

---

### `POST /api/analyze`

Slackメッセージを受け取り、設定中のAIプロバイダー（Claude または Gemini）でタスクを生成する。
バッファが指定された場合、AIにバッファ込みの工数で生成するよう指示する。

**リクエスト：**
```json
{
  "message": "認証周りのバグ直してほしい。本番で出てるやつ",
  "buffer": { "hours": 4 }
}
```

`buffer` は任意。指定方法：
- 時間加算: `{ "hours": 4 }`
- 倍率: `{ "multiplier": 1.5 }`
- なし: `buffer` フィールドを省略

**レスポンス（200）：**
```json
{
  "task": { /* 生成されたタスクオブジェクト（全フィールド） */ }
}
```

**エラーレスポンス：**

| ステータス | 条件 |
|---|---|
| 400 | APIキー未設定 / メッセージが空 |
| 401 | APIキーが無効 |
| 429 | レート制限 |
| 500 | JSONパースエラー / その他の例外 |

```json
{ "error": "エラーメッセージ（日本語）" }
```

---

### `GET /api/tasks`

保存中の全タスクを配列で返す。

**レスポンス（200）：**
```json
[
  { /* タスクオブジェクト */ },
  { /* タスクオブジェクト */ }
]
```

---

### `DELETE /api/tasks/clear`

全タスクを削除する。

**レスポンス（200）：**
```json
{ "ok": true }
```

---

### `POST /api/upload-context`

コンテキストファイル（`.md` / `.txt`）をアップロードする。
Content-Type: `multipart/form-data`

**リクエスト：**
```
フォームフィールド名: file
```

**レスポンス（200）：**
```json
{ "ok": true, "filename": "PROJECT.md" }
```

**エラーレスポンス：**

| ステータス | 条件 |
|---|---|
| 400 | ファイルが見つからない |
| 400 | UTF-8 以外のエンコーディング |

---

### `GET /api/context`

コンテキストファイルの読み込み状態を返す。

**レスポンス（200）：**

読み込み済みの場合：
```json
{ "hasContext": true, "filename": "PROJECT.md" }
```

未読み込みの場合：
```json
{ "hasContext": false, "filename": null }
```

---

### `DELETE /api/context`

読み込んだコンテキストファイルを削除する。

**レスポンス（200）：**
```json
{ "ok": true }
```
