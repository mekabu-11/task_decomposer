import json
import os
import time
from datetime import datetime

import openai
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()

app = Flask(__name__)

# -------------------------------------------------------------------
# In-memory storage (ローカル単一ユーザー用)
# -------------------------------------------------------------------
_tasks: dict = {}
_api_key: str | None = os.environ.get("OPENAI_API_KEY") or None
_project_context: dict = {"content": None, "filename": None}

# -------------------------------------------------------------------
# System Prompt
# -------------------------------------------------------------------
SYSTEM_PROMPT = """あなたは事業会社のエンジニアリングマネージャーです。
インフラからアプリまで横断的に担当するエンジニアへの依頼メッセージを受け取り、
以下の構造でJSONのみを返してください。マークダウンや説明文は一切含めないこと。

{
  "title": "タスクのタイトル（20文字以内）",
  "totalHours": 合計時間（数値・0.5刻み）,
  "estimatedDays": 実働日数（1日6時間換算・整数）,
  "steps": [
    {
      "order": 1,
      "title": "具体的な作業手順名",
      "description": "この手順で具体的にやること（コマンド、ファイル名、設定値など含む）",
      "hours": 作業時間（数値・0.5刻み）
    }
  ],
  "backlog": {
    "background": "背景（なぜこのタスクが発生したか、現状の問題点を2〜3文で記述）",
    "purpose": "目的（このタスクで何を達成するかを1〜2文で記述）",
    "expectedBehavior": "期待動作（完了後にどう動作すべきかを箇条書きで記述）"
  },
  "slackReply": "依頼者へのSlack返信文。【重要】依頼者はITの専門知識を持たない営業担当者です。技術用語・コマンド・専門略語は一切使わず、誰でも理解できる平易な日本語で記述すること。\n必ず以下の構成・改行ルールで記述すること：\n① 冒頭に「〇〇さん、ご連絡ありがとうございます！」など一言\n② 空行（\\n\\n）を挟んで、何をするか・なぜ時間がかかるかを2〜3文で説明\n③ 空行を挟んで、対応完了の目安を「📅 完了予定：〇月〇日（〇）ごろ」の形式で記載\n④ 空行を挟んで、進捗報告や質問があれば連絡する旨を添えて締める\n改行は \\n で表現し、段落間は \\n\\n（空行）で区切ること。"
}

【steps（作業手順）について】
- 最低でも5ステップ以上に分解すること（大きいタスクは10以上）
- 実際に手を動かす順番に並べること
- 各stepは1つの具体的な作業単位（例：ログ確認、原因調査、コード修正、テスト作成、動作確認、レビュー依頼、デプロイなど）
- titleは「何をするか」を端的に、descriptionは「具体的にどうやるか」を書く
- descriptionには対象ファイル、コマンド、確認ポイントなど実務で役立つ情報を含める
- hoursの合計がtotalHoursと一致すること

【backlog（チケット記述）について】
- background: 現状の問題・経緯を客観的に記述
- purpose: 達成すべきゴールを簡潔に記述
- expectedBehavior: 完了条件を箇条書きで明確に記述
"""

BUFFER_HINT = """
【バッファについて】
依頼者が工数に+{buffer_desc}のバッファを希望しています。
- totalHoursにバッファを含めた合計値を設定すること
- stepsの時間合計もtotalHoursと一致させること（調査・テスト・レビューなど余裕を持たせる）
- slackReplyの完了予定もバッファ込みの工数で記述すること
"""


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def call_ai(prompt: str, system: str = None, max_tokens: int = 1024) -> str:
    """OpenAI gpt-5-miniを呼び出してテキストを返す"""
    client = openai.OpenAI(api_key=_api_key)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    response = client.chat.completions.create(
        model="gpt-5.1",
        max_completion_tokens=max_tokens,
        messages=messages,
    )
    return response.choices[0].message.content


def format_buffer_desc(buffer: dict) -> str:
    """バッファの説明文を生成"""
    hours = buffer.get("hours")
    multiplier = buffer.get("multiplier")
    if multiplier:
        return f"×{multiplier}倍"
    elif hours:
        return f"{hours}時間"
    return ""


def clean_json_response(text: str) -> str:
    """Claude がMarkdownコードブロックを返した場合に除去する"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # 最初の ``` 行を除去
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


# -------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/set-key", methods=["POST"])
def set_key():
    global _api_key
    data = request.json or {}
    key = data.get("apiKey", "").strip()
    _api_key = key if key else None
    return jsonify({"ok": True})


@app.route("/api/has-key", methods=["GET"])
def has_key():
    return jsonify({"hasKey": bool(_api_key)})


@app.route("/api/analyze", methods=["POST"])
def analyze():
    if not _api_key:
        return jsonify({"error": "APIキーが設定されていません"}), 400

    data = request.json or {}
    message = data.get("message", "").strip()
    buffer = data.get("buffer")  # { hours: N } or { multiplier: N } or null
    if not message:
        return jsonify({"error": "メッセージを入力してください"}), 400

    # System Prompt構築
    system = SYSTEM_PROMPT

    # バッファ指示をプロンプトに追加
    if buffer:
        desc = format_buffer_desc(buffer)
        if desc:
            system += BUFFER_HINT.format(buffer_desc=desc)

    # PROJECT.md コンテキストを System Prompt に注入
    if _project_context["content"]:
        system += (
            "\n\n【プロジェクト固有の前提情報】\n"
            "以下の情報を必ず考慮してタスク分解・工数見積もりを行うこと。\n\n"
            + _project_context["content"]
        )

    try:
        text = clean_json_response(call_ai(message, system=system, max_tokens=4096))
        parsed = json.loads(text)

        task_id = f"task_{int(time.time() * 1000)}"
        task = {
            "id": task_id,
            "originalMessage": message,
            "createdAt": datetime.now().isoformat(),
            "buffer": buffer,
            **parsed,
        }
        _tasks[task_id] = task

        return jsonify({"task": task})

    except json.JSONDecodeError as e:
        return jsonify({"error": f"AIの返答をJSONとしてパースできませんでした: {e}"}), 500
    except openai.AuthenticationError:
        return jsonify({"error": "APIキーが無効です。正しいOpenAIのAPIキーを設定してください。"}), 401
    except openai.RateLimitError:
        return jsonify({"error": "APIレート制限に達しました。しばらく待ってから再試行してください。"}), 429
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/tasks", methods=["GET"])
def get_tasks():
    return jsonify(list(_tasks.values()))


@app.route("/api/tasks/clear", methods=["DELETE"])
def clear_tasks():
    _tasks.clear()
    return jsonify({"ok": True})


@app.route("/api/upload-context", methods=["POST"])
def upload_context():
    if "file" not in request.files:
        return jsonify({"error": "ファイルが見つかりません"}), 400

    file = request.files["file"]
    try:
        content = file.read().decode("utf-8")
    except UnicodeDecodeError:
        return jsonify({"error": "ファイルのエンコーディングがUTF-8ではありません"}), 400

    _project_context["content"] = content
    _project_context["filename"] = file.filename
    return jsonify({"ok": True, "filename": file.filename})


@app.route("/api/context", methods=["GET"])
def get_context():
    return jsonify(
        {
            "hasContext": bool(_project_context["content"]),
            "filename": _project_context["filename"],
        }
    )


@app.route("/api/context", methods=["DELETE"])
def delete_context():
    _project_context["content"] = None
    _project_context["filename"] = None
    return jsonify({"ok": True})


# -------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 50)
    print("  Task Decomposer")
    print("=" * 50)
    print("ブラウザで http://localhost:5001 を開いてください")
    print("停止: Ctrl+C")
    print("=" * 50)
    app.run(debug=True, host="0.0.0.0", port=5001)
