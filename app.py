import json
import os
import time
from datetime import datetime

import anthropic
from google import genai as google_genai
from google.genai import types as genai_types
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()

app = Flask(__name__)

# -------------------------------------------------------------------
# In-memory storage (ローカル単一ユーザー用)
# -------------------------------------------------------------------
_tasks: dict = {}
_anthropic_env = os.environ.get("ANTHROPIC_API_KEY")
_gemini_env = os.environ.get("GEMINI_API_KEY")
_api_key: dict = {
    "value": _anthropic_env or _gemini_env or None,
    "provider": "gemini" if (not _anthropic_env and _gemini_env) else "anthropic",
}
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
      "hours": 作業時間（数値・0.5刻み）
    }
  ],
  "backlog": {
    "background": "背景（なぜこのタスクが発生したか、現状の問題点を2〜3文で記述）",
    "purpose": "目的（このタスクで何を達成するかを1〜2文で記述）",
    "expectedBehavior": "期待動作（完了後にどう動作すべきかを箇条書きで記述）"
  },
  "slackReply": "依頼者へのSlack返信文（コピペできる形式・改行あり）。完了予定日時の目安を必ず含めること。"
}

【steps（作業手順）について】
- 実際に手を動かす順番に並べること
- 各stepは1つの具体的な作業単位（調査、実装、テスト、デプロイなど）
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
    """設定されたAIプロバイダーを呼び出してテキストを返す"""
    api_key = _api_key["value"]
    provider = _api_key.get("provider", "anthropic")

    if provider == "gemini":
        client = google_genai.Client(api_key=api_key)
        config = genai_types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            system_instruction=system if system else None,
        )
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt,
            config=config,
        )
        return response.text
    else:
        client = anthropic.Anthropic(api_key=api_key)
        kwargs = {
            "model": "claude-sonnet-4-5",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        response = client.messages.create(**kwargs)
        return response.content[0].text


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
    data = request.json or {}
    key = data.get("apiKey", "").strip()
    provider = data.get("provider", "anthropic")
    _api_key["value"] = key if key else None
    _api_key["provider"] = provider if provider in ("anthropic", "gemini") else "anthropic"
    return jsonify({"ok": True})


@app.route("/api/has-key", methods=["GET"])
def has_key():
    return jsonify({"hasKey": bool(_api_key["value"]), "provider": _api_key.get("provider", "anthropic")})


@app.route("/api/analyze", methods=["POST"])
def analyze():
    api_key = _api_key["value"]
    if not api_key:
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
    except anthropic.AuthenticationError:
        return jsonify({"error": "APIキーが無効です。正しいAnthropicのAPIキーを設定してください。"}), 401
    except anthropic.RateLimitError:
        return jsonify({"error": "APIレート制限に達しました。しばらく待ってから再試行してください。"}), 429
    except Exception as e:
        err = str(e).lower()
        import traceback
        print(f"[DEBUG] type={type(e).__name__}")
        print(f"[DEBUG] message={e}")
        traceback.print_exc()
        if any(k in err for k in ("api key", "permission", "403", "invalid api", "unauthenticated")):
            return jsonify({"error": "APIキーが無効です。正しいAPIキーを設定してください。"}), 401
        if any(k in err for k in ("quota", "429", "rate limit", "resource exhausted")):
            return jsonify({"error": "APIレート制限に達しました。しばらく待ってから再試行してください。"}), 429
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
    print("  AIタスク司令塔")
    print("=" * 50)
    print("ブラウザで http://localhost:5001 を開いてください")
    print("停止: Ctrl+C")
    print("=" * 50)
    app.run(debug=True, host="0.0.0.0", port=5001)
