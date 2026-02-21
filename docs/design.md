# 設計

## アーキテクチャ概要

```
┌─────────────────────────────────────────┐
│            ブラウザ                       │
│         templates/index.html            │
│   (Vanilla JS + Tailwind CSS CDN)       │
└──────────────┬──────────────────────────┘
               │ fetch API (JSON / FormData)
               │ http://localhost:5000
┌──────────────▼──────────────────────────┐
│         Flask サーバー                    │
│              app.py                     │
│                                         │
│  ┌─────────────┐  ┌──────────────────┐  │
│  │ インメモリ   │  │  call_ai()       │  │
│  │ ストレージ   │  │                  │  │
│  │ _tasks      │  │ ・anthropic SDK  │  │
│  │ _api_key    │  │   (claude-sonnet)│  │
│  │  .provider  │  │ ・google-genai   │  │
│  │ _project    │  │   (gemini-2.0)   │  │
│  │  _context   │  └──────────────────┘  │
│  └─────────────┘                        │
└─────────────────────────────────────────┘
```

**設計方針：**

- **ローカル完結** — 外部DB・外部サービスへの依存なし。Flask をローカルで起動するだけ。
- **サーバーサイド API 呼び出し** — Claude API は Flask 経由で呼び出す。ブラウザからAPIキーが直接送出されない。
- **インメモリストレージ** — タスク・APIキー・PROJECT.mdはすべてPython `dict` に保持。再起動でリセット。シングルユーザー前提の割り切った設計。
- **REST API + SPA的フロントエンド** — ブラウザ側は `fetch` でFlaskと通信し、DOMを動的に再描画する。ページ遷移なし。

---

## ファイル構成

```
analyzer_for_log/
├── app.py                # Flask バックエンド（全ルート・ヘルパー関数）
├── requirements.txt      # 依存ライブラリ（flask, anthropic, google-generativeai）
├── templates/
│   └── index.html        # フロントエンド（HTML + CSS + JavaScript）
├── docs/
│   ├── setup.md          # セットアップ手順
│   ├── usage.md          # 操作方法
│   ├── design.md         # 本ファイル
│   ├── api.md            # APIエンドポイント仕様
│   └── security.md       # セキュリティ・制限事項
└── README.md             # 概要・趣旨・ドキュメントリンク
```

---

## テックスタック

| 項目 | 採用技術 | 理由 |
|---|---|---|
| バックエンド | Python 3 + Flask | シンプルな構成で素早く実装できる |
| AI | Claude (`claude-sonnet-4-5`) または Gemini (`gemini-2.0-flash`) | プロバイダーをUIから切り替え可能 |
| フロントエンド | Vanilla JS (ES2020) | フレームワーク不要。ローカル用なので依存を最小化 |
| スタイリング | Tailwind CSS (Play CDN) | CDN経由でビルドステップ不要 |
| データ保持 | Python dict（インメモリ） | ローカル単一ユーザーのため永続化不要と割り切り |

---

## タスクデータモデル

タスクオブジェクトの全フィールド：

```json
{
  "id": "task_1720000000000",
  "originalMessage": "認証周りのバグ直してほしい。本番で出てるやつ",
  "createdAt": "2025-01-15T10:00:00",
  "status": "pending",
  "autoMoved": false,

  "title": "本番環境の認証バグ修正",
  "summary": "本番環境で発生している認証エラーの調査・修正・デプロイ対応",
  "subtasks": [
    { "id": "sub_1", "title": "エラーログの調査・原因特定", "hours": 1.5, "layer": "infra" },
    { "id": "sub_2", "title": "修正コードの実装・単体テスト", "hours": 3.0, "layer": "app"   },
    { "id": "sub_3", "title": "ステージング環境での確認",    "hours": 1.0, "layer": "infra" },
    { "id": "sub_4", "title": "本番デプロイ・動作確認",      "hours": 0.5, "layer": "infra" }
  ],
  "totalHours": 6.0,
  "estimatedDays": 1,
  "priority": {
    "score": 100,
    "level": "high",
    "urgency": 5,
    "impact": 5,
    "complexity": 3
  },
  "rationale": "本番障害のため緊急度が最高。認証は全ユーザーに影響するため影響範囲も最大。...",
  "replyTemplate": "確認しました。本番障害のため最優先で対応します。\n本日中（〜18時目安）に完了予定です。",
  "schedule": "today",

  "buffer": {
    "hours": 4,
    "multiplier": null,
    "reason": "レビュー待ち・環境不安定を考慮"
  },
  "adjustedTotalHours": 10.0,
  "adjustedDays": 2,
  "adjustedReplyTemplate": "確認しました。...バッファを含め2日（〜明日18時）で対応予定です。"
}
```

### フィールド定義

| フィールド | 型 | 説明 |
|---|---|---|
| `id` | string | `task_{Unixミリ秒}` 形式の一意ID |
| `originalMessage` | string | ユーザーが入力した元のSlackメッセージ |
| `createdAt` | string | 生成日時（ISO 8601） |
| `status` | `"pending"` \| `"in_progress"` \| `"done"` | タスクの進捗状態 |
| `autoMoved` | boolean | スケジューラーによる自動移動フラグ |
| `title` | string | AIが生成した20文字以内のタスク名 |
| `summary` | string | 50文字程度の概要 |
| `subtasks` | array | サブタスクの配列（後述） |
| `totalHours` | number | AI算出の合計工数（時間） |
| `estimatedDays` | number | 1日6時間換算の実働日数（整数） |
| `priority` | object | 優先度情報（後述） |
| `rationale` | string | 工数・優先度の根拠説明（100〜150文字） |
| `replyTemplate` | string | Slack返信テンプレート |
| `schedule` | `"today"` \| `"this_week"` \| `"next_week"` | 配置カラム |
| `buffer` | object \| null | バッファ設定（ユーザー入力後に付与） |
| `adjustedTotalHours` | number \| null | バッファ適用後の合計工数 |
| `adjustedDays` | number \| null | バッファ適用後の実働日数 |
| `adjustedReplyTemplate` | string \| null | バッファ理由を含む再生成済み返答テンプレ |

### subtask フィールド

| フィールド | 型 | 説明 |
|---|---|---|
| `id` | string | `sub_1`, `sub_2`, ... |
| `title` | string | 具体的な作業単位名 |
| `hours` | number | 作業時間（0.5刻み） |
| `layer` | `"infra"` \| `"app"` \| `"both"` | 担当レイヤー |

### priority フィールド

| フィールド | 型 | 値域 | 説明 |
|---|---|---|---|
| `score` | number | 0〜100 | 総合優先度スコア |
| `level` | string | `high` / `medium` / `low` | スコアのラベル |
| `urgency` | number | 1〜5 | 緊急度。本番障害・セキュリティは5固定 |
| `impact` | number | 1〜5 | 影響範囲の広さ |
| `complexity` | number | 1〜5 | 技術的複雑度 |

---

## ビジネスロジック

### 優先度スコア算出

```
score = (urgency × 15) + (impact × 10) + (urgency == 5 ? 25 : 0)
```

- urgency が 5（本番障害・セキュリティ）の場合、ボーナス +25 が加算される
- スコアの理論最大値：5×15 + 5×10 + 25 = **150**（AIがプロンプト指示に従って0〜100に収める）

### スケジュール自動配置

AIが `urgency` を基に初期スケジュールを決定する：

| urgency | schedule |
|---|---|
| 4 以上 / 本番障害 | `today` |
| 3 | `this_week` |
| 2 以下 | `next_week` |

### スケジューラー（自動移動）

新しいタスクが追加されるたびに `recalculate_schedule()` が実行される。

```
today の合計工数（未完了タスクのみ） > 6時間
  かつ
タスクの priority.level が "high" でない
  →  schedule を "this_week" に変更 + autoMoved = True をセット
```

> 高優先度タスクは6時間上限を超えても今日のカラムに残る。

### バッファ計算

```python
# 時間加算の場合
adjustedTotalHours = totalHours + hours

# 倍率の場合（0.5刻みで丸め）
adjustedTotalHours = round(totalHours * multiplier * 2) / 2

adjustedDays = ceil(adjustedTotalHours / 6)
```

---

## AIへのプロンプト設計

### タスク生成プロンプト（System Prompt）

AIに「エンジニアリングマネージャー」のペルソナを与え、**JSONのみを返す**よう厳命する。

```
あなたは事業会社のエンジニアリングマネージャーです。
インフラからアプリまで横断的に担当するエンジニアへの依頼メッセージを受け取り、
以下の構造でJSONのみを返してください。マークダウンや説明文は一切含めないこと。
...（スキーマ定義・スコア算出基準・schedule判定基準）
```

PROJECT.md が読み込まれている場合、System Prompt の末尾に以下を追記する：

```
【プロジェクト固有の前提情報】
以下の情報を必ず考慮してタスク分解・工数見積もりを行うこと。

（PROJECT.md の内容）
```

### バッファ再生成プロンプト（User Message）

バッファ適用時に、元の返答テンプレを書き換えるよう AI に依頼する。
**JSONではなくテキスト（Slack返信文）のみを返す**ようにしている。

```
以下のタスク情報とバッファ内容をもとに、依頼者へのSlack返信文を再生成してください。
バッファの理由を自然な文体で組み込み、コピペできる形式で返してください。
返答はテキストのみ（JSONや説明文不要）。

タスク: {title}
元の工数: {totalHours}時間
バッファ後工数: {adjustedTotalHours}時間（{adjustedDays}日）
バッファ理由: {reason}
元の返答テンプレ: {replyTemplate}
```

---

## フロントエンド設計

### 状態管理

グローバルな `state` オブジェクトと、タスクごとのバッファUIを `bufferUI` で管理する。

```js
const state = {
  tasks: [],           // タスクの配列（サーバーと同期）
  hasApiKey: false,    // APIキー設定済み確認フラグ
  provider: 'anthropic', // 使用中のAIプロバイダー（'anthropic' | 'gemini'）
  hasContext: false,   // PROJECT.md 読み込み済みフラグ
  contextFilename: null,
  loading: false,      // AI分析中フラグ
};

const bufferUI = {
  // taskId → { open, type, hours, multiplier }
};
```

### レンダリング

`renderBoard()` が呼ばれるたびに3カラムすべてのDOMを再生成する（Virtual DOM不使用）。
バッファパネルの開閉状態は `bufferUI` を参照して再描画後も復元する。

### デザイントークン

| 変数 | 値 | 用途 |
|---|---|---|
| `--bg` | `#0F172A` (slate-950) | ページ背景 |
| `--card` | `#1E293B` (slate-800) | カード背景 |
| `--accent` | `#6366F1` (indigo-500) | ボタン・フォーカスリング |
