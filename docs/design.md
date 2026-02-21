# 設計

## アーキテクチャ概要

```
┌─────────────────────────────────────────┐
│            ブラウザ                       │
│         templates/index.html            │
│   (Vanilla JS + Tailwind CSS CDN)       │
└──────────────┬──────────────────────────┘
               │ fetch API (JSON / FormData)
               │ http://localhost:5001
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
│  │ _project    │  │   (gemini-3)     │  │
│  │  _context   │  └──────────────────┘  │
│  └─────────────┘                        │
└─────────────────────────────────────────┘
```

**設計方針：**

- **ローカル完結** — 外部DB・外部サービスへの依存なし。Flask をローカルで起動するだけ。
- **サーバーサイド API 呼び出し** — AI APIはFlask経由で呼び出す。ブラウザからAPIキーが直接送出されない。
- **インメモリストレージ** — タスク・APIキー・コンテキストはすべてPython `dict` に保持。再起動でリセット。シングルユーザー前提の割り切った設計。
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
| AI | Claude (`claude-sonnet-4-5`) または Gemini (`gemini-3-flash-preview`) | プロバイダーをUIから切り替え可能 |
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
  "buffer": { "hours": 4 },

  "title": "本番環境の認証バグ修正",
  "totalHours": 10.0,
  "estimatedDays": 2,
  "steps": [
    {
      "order": 1,
      "title": "エラーログの確認",
      "description": "CloudWatch Logsで直近24時間の認証関連エラーを検索し、発生パターンを特定する",
      "hours": 1.0
    },
    {
      "order": 2,
      "title": "原因調査・コード解析",
      "description": "ログから特定したエラー箇所のソースコードを追跡し、根本原因を特定する",
      "hours": 2.0
    },
    {
      "order": 3,
      "title": "修正コードの実装",
      "description": "認証ロジックの修正を実装。関連するユニットテストも追加する",
      "hours": 3.0
    },
    {
      "order": 4,
      "title": "ステージング環境での動作確認",
      "description": "ステージングにデプロイし、認証フロー全体を手動テストで確認する",
      "hours": 1.5
    },
    {
      "order": 5,
      "title": "コードレビュー依頼・対応",
      "description": "PRを作成しレビュー依頼。指摘箇所を修正する",
      "hours": 1.5
    },
    {
      "order": 6,
      "title": "本番デプロイ・動作確認",
      "description": "本番環境にデプロイし、認証エラーが解消されたことをログで確認する",
      "hours": 1.0
    }
  ],
  "backlog": {
    "background": "本番環境で認証機能にエラーが発生しており、ユーザーがログインできない状態が断続的に発生している。",
    "purpose": "認証エラーの根本原因を特定し修正することで、ユーザーが安定してログインできる状態に復旧する。",
    "expectedBehavior": "- 認証エラーが解消され、全ユーザーが正常にログインできること\n- エラーログに認証関連のエラーが出力されないこと\n- ステージング・本番環境で動作確認が完了していること"
  },
  "slackReply": "お疲れ様です。認証周りの不具合の件、承知いたしました。\n最優先で調査と修正対応を開始します。\n\nバッファを含め2日（〜明後日18時目安）での完了を見込んでいます。\n進捗があり次第、再度こちらで共有させていただきます。"
}
```

### フィールド定義

| フィールド | 型 | 説明 |
|---|---|---|
| `id` | string | `task_{Unixミリ秒}` 形式の一意ID |
| `originalMessage` | string | ユーザーが入力した元のSlackメッセージ |
| `createdAt` | string | 生成日時（ISO 8601） |
| `buffer` | object \| null | バッファ設定（`{ hours: N }` or `{ multiplier: N }` or null） |
| `title` | string | AIが生成した20文字以内のタスク名 |
| `totalHours` | number | AI算出の合計工数（時間・バッファ込み） |
| `estimatedDays` | number | 1日6時間換算の実働日数（整数） |
| `steps` | array | 作業手順の配列（後述） |
| `backlog` | object | Backlogチケット用の記述（後述） |
| `slackReply` | string | Slack返信テンプレート |

### steps フィールド

| フィールド | 型 | 説明 |
|---|---|---|
| `order` | number | 手順の順番（1から連番） |
| `title` | string | 作業手順名 |
| `description` | string | 具体的な作業内容（ファイル名、コマンド、確認ポイントなど） |
| `hours` | number | 作業時間（0.5刻み） |

### backlog フィールド

| フィールド | 型 | 説明 |
|---|---|---|
| `background` | string | 背景（なぜこのタスクが発生したか） |
| `purpose` | string | 目的（何を達成するか） |
| `expectedBehavior` | string | 期待動作（完了後にどう動作すべきか） |

---

## バッファの仕組み

バッファはAI分解前にユーザーが選択する。選択された場合、System Promptにバッファ指示が追加され、AIがバッファ込みの工数で全出力を生成する。

**選択肢：**
- なし（デフォルト）
- 時間加算: +2h, +4h, カスタム
- 倍率: ×1.5, カスタム

バッファが指定されると、以下がSystem Promptに追加される：

```
【バッファについて】
依頼者が工数に+{バッファ内容}のバッファを希望しています。
- totalHoursにバッファを含めた合計値を設定すること
- stepsの時間合計もtotalHoursと一致させること
- slackReplyの完了予定もバッファ込みの工数で記述すること
```

---

## AIへのプロンプト設計

### タスク生成プロンプト（System Prompt）

AIに「エンジニアリングマネージャー」のペルソナを与え、**JSONのみを返す**よう厳命する。

主な指示内容：
- タスクタイトル、工数、作業手順、Backlogチケット、Slack返信を生成
- 作業手順は最低5ステップ以上（大きいタスクは10以上）
- 各ステップにdescription（具体的な作業内容）を含める
- Backlogチケットは 背景/目的/期待動作 の3セクション

コンテキストファイルが読み込まれている場合、System Prompt の末尾に追記：

```
【プロジェクト固有の前提情報】
以下の情報を必ず考慮してタスク分解・工数見積もりを行うこと。

（コンテキストファイルの内容）
```

---

## フロントエンド設計

### 状態管理

グローバルな `state` オブジェクトで管理する。

```js
const state = {
  tasks: [],           // タスクの配列（サーバーと同期）
  hasApiKey: false,    // APIキー設定済み確認フラグ
  provider: 'anthropic', // 使用中のAIプロバイダー
  hasContext: false,   // コンテキスト読み込み済みフラグ
  contextFilename: null,
  loading: false,      // AI分析中フラグ
  buffer: null,        // 選択中のバッファ設定
};
```

### レンダリング

`renderResults()` が呼ばれるたびに結果エリアのDOMを再生成する（Virtual DOM不使用）。
タスクは新しいものが上に表示される。

### 結果表示

1カラムのシンプルなレイアウト。各タスクは以下の4セクションで構成：

1. **ヘッダー** — タスク名 + 工数（バッファバッジ）
2. **作業手順** — 番号付きリスト（各手順にdescription付き）
3. **Backlogチケット** — 背景/目的/期待動作（コピーボタン付き）
4. **Slack返信** — コピーボタン付き

### デザイントークン

| 変数 | 値 | 用途 |
|---|---|---|
| `--bg` | `#1a1a1a` | ページ背景 |
| `--card` | `#242424` | カード背景 |
| `--border` | `#333` | ボーダー |
| `--accent` | `#d4a574` | アクセント（ボタン・リンク） |
