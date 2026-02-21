# セットアップ

## 必要なもの

| 項目 | 要件 |
|---|---|
| Python | 3.10 以上 |
| AIプロバイダーのAPIキー | Claude または Gemini（どちらか一方） |
| インターネット接続 | AI API呼び出し・Tailwind CSS CDN の読み込みに使用 |

APIキーの取得先：

| プロバイダー | 取得先 | キーの形式 |
|---|---|---|
| Claude (Anthropic) | [console.anthropic.com](https://console.anthropic.com) → API Keys | `sk-ant-api03-...` |
| Gemini (Google) | [aistudio.google.com](https://aistudio.google.com) → Get API key | `AIzaSy...` |

---

## インストール

```bash
git clone <このリポジトリ>
cd analyzer_for_log

pip3 install -r requirements.txt
```

インストールされるライブラリ：

| ライブラリ | 用途 |
|---|---|
| `flask` | ローカルWebサーバー |
| `anthropic` | Claude API クライアント |
| `google-generativeai` | Gemini API クライアント |
| `python-dotenv` | `.env` ファイルの読み込み |

---

## 起動

```bash
python3 app.py
```

起動すると以下が表示される：

```
==================================================
  AIタスク司令塔
==================================================
ブラウザで http://localhost:5000 を開いてください
停止: Ctrl+C
==================================================
```

ブラウザで `http://localhost:5000` を開く。
**初回起動時はAPIキー入力モーダルが自動で開く。**

---

## APIキーの設定

### 方法A：`.env` ファイルで永続化（推奨）

```bash
cp .env.example .env
```

`.env` を開き、使用するプロバイダーのAPIキーを記入する：

**Claude を使う場合：**
```
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxx
```

**Gemini を使う場合：**
```
GEMINI_API_KEY=AIzaSyxxxxxxxxxx
```

> `.env` は `.gitignore` により Git 管理外。誤ってコミットされない。
> 両方設定した場合は `ANTHROPIC_API_KEY`（Claude）が優先されます。
> `.env` に記入した場合でも、起動後にUIモーダルで手動切り替えが可能です。

### 方法B：UIモーダルで都度入力

1. アプリのモーダルで使用するプロバイダーを選択（**Claude** または **Gemini**）
2. 対応するAPIキーを貼り付けて「設定する」をクリック

> この方法では `python3 app.py` を再起動するたびに入力が必要。

---

## 停止

ターミナルで `Ctrl+C`。

---

## トラブルシューティング

### `pip3: command not found`

```bash
python3 -m pip install -r requirements.txt
```

### `ModuleNotFoundError: No module named 'flask'`

インストールが完了していない。再度 `pip3 install -r requirements.txt` を実行する。

### `Address already in use` (ポート5000が使用中)

別のプロセスがポート5000を使用している。

```bash
# 使用中のプロセスを確認
lsof -i :5000

# 該当プロセスを終了
kill -9 <PID>
```

または `app.py` 末尾の `port=5000` を別のポート番号に変更する。

### macOS で `5000番ポートが使用できない`

macOS Monterey 以降、AirPlay Receiver がポート5000を使用する場合がある。
「システム設定 → 一般 → AirDrop と Handoff → AirPlay Receiver」をオフにするか、ポート番号を変更する。

### APIキーエラー（401）

- キーが正しくコピーできているか確認（前後の空白に注意）
- モーダルで選択したプロバイダーとキーが一致しているか確認
  - Claude キー（`sk-ant-...`）→ Claude を選択
  - Gemini キー（`AIzaSy...`）→ Gemini を選択
- キーが失効・無効化されていないか各コンソールで確認
