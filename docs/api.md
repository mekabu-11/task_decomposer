# APIエンドポイント仕様

ベースURL: `http://localhost:5000`
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
| PUT | `/api/tasks/<id>/status` | ステータス更新 |
| POST | `/api/tasks/<id>/buffer` | バッファ適用 + 返答テンプレ再生成 |
| POST | `/api/upload-context` | PROJECT.md アップロード |
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
生成後にスケジューラーを実行し、必要であれば既存タスクを自動移動する。

**リクエスト：**
```json
{ "message": "認証周りのバグ直してほしい。本番で出てるやつ" }
```

**レスポンス（200）：**
```json
{
  "task": { /* 生成されたタスクオブジェクト（全フィールド） */ },
  "autoMovedCount": 0
}
```

`autoMovedCount` は今回のタスク追加によって「今週」に自動移動されたタスクの件数。

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

### `PUT /api/tasks/<task_id>/status`

タスクのステータスを更新する。

**リクエスト：**
```json
{ "status": "in_progress" }
```

`status` に指定できる値：`"pending"` / `"in_progress"` / `"done"`

**レスポンス（200）：**
```json
{ /* 更新後のタスクオブジェクト（全フィールド） */ }
```

**エラーレスポンス：**

| ステータス | 条件 |
|---|---|
| 404 | 指定IDのタスクが存在しない |

---

### `POST /api/tasks/<task_id>/buffer`

バッファを計算し、設定中のAIプロバイダーで返答テンプレを再生成する。

**リクエスト：**

時間加算の場合：
```json
{
  "buffer": {
    "hours": 4,
    "multiplier": null,
    "reason": "レビュー待ち・環境不安定を考慮"
  }
}
```

倍率の場合：
```json
{
  "buffer": {
    "hours": null,
    "multiplier": 1.5,
    "reason": "初めての技術領域のため"
  }
}
```

**レスポンス（200）：**
```json
{
  /* 元のタスクオブジェクト + 以下フィールドが追加・更新 */
  "buffer": { "hours": 4, "multiplier": null, "reason": "..." },
  "adjustedTotalHours": 10.0,
  "adjustedDays": 2,
  "adjustedReplyTemplate": "確認しました。...バッファを含め2日（〜明日18時）で対応予定です。"
}
```

**エラーレスポンス：**

| ステータス | 条件 |
|---|---|
| 400 | APIキー未設定 |
| 404 | 指定IDのタスクが存在しない |

> AI API の呼び出しが失敗した場合でも 200 を返す。
> その場合 `adjustedReplyTemplate` は元の `replyTemplate` と同じ値になる。

---

### `POST /api/upload-context`

PROJECT.md（またはテキストファイル）をアップロードする。
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

PROJECT.md の読み込み状態を返す。

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

読み込んだ PROJECT.md を削除する。

**レスポンス（200）：**
```json
{ "ok": true }
```
