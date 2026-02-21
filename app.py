import json
import math
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
# System Prompt (設計書より)
# -------------------------------------------------------------------
SYSTEM_PROMPT = """あなたは事業会社のエンジニアリングマネージャーです。
インフラからアプリまで横断的に担当するエンジニアへの依頼メッセージを受け取り、
以下の構造でJSONのみを返してください。マークダウンや説明文は一切含めないこと。

{
  "title": "タスクのタイトル（20文字以内）",
  "summary": "タスクの概要（50文字程度）",
  "subtasks": [
    {
      "id": "sub_1",
      "title": "サブタスク名（具体的な作業単位）",
      "hours": 作業時間（数値・0.5刻み）,
      "layer": "infra" または "app" または "both"
    }
  ],
  "totalHours": 合計時間（数値）,
  "estimatedDays": 実働日数（1日6時間換算・整数）,
  "priority": {
    "score": 優先度スコア（0〜100の整数）,
    "level": "high" または "medium" または "low",
    "urgency": 緊急度（1〜5の整数）,
    "impact": 影響範囲の広さ（1〜5の整数）,
    "complexity": 技術的複雑度（1〜5の整数）
  },
  "rationale": "工数・優先度の根拠説明（100〜150文字）。DB・本番・インフラなど具体的な要素に必ず言及すること。",
  "replyTemplate": "依頼者へのSlack返信文（コピペできる形式・改行あり）。完了予定日時の目安を必ず含めること。",
  "schedule": "today" または "this_week" または "next_week"
}

【優先度スコア算出基準】
score = (urgency × 15) + (impact × 10) + (urgency === 5 ? 25 : 0)
- 本番障害・セキュリティ関連は urgency=5 固定

【schedule判定基準】
- urgency >= 4 または 本番障害 → "today"
- urgency = 3 → "this_week"
- urgency <= 2 → "next_week"
"""

BUFFER_PROMPT = """以下のタスク情報とバッファ内容をもとに、依頼者へのSlack返信文を再生成してください。
バッファの理由を自然な文体で組み込み、コピペできる形式で返してください。
返答はテキストのみ（JSONや説明文不要）。

タスク: {title}
元の工数: {total_hours}時間
バッファ後工数: {adjusted_hours}時間（{adjusted_days}日）
バッファ理由: {reason}
元の返答テンプレ: {reply_template}
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


def recalculate_schedule(task_list: list) -> tuple[list, int]:
    """1日6時間上限を超えた場合、高優先度でないタスクを今週に移動する"""
    today_hours = sum(
        t["totalHours"]
        for t in task_list
        if t["schedule"] == "today" and t["status"] != "done"
    )
    if today_hours <= 6:
        return task_list, 0

    moved_count = 0
    result = []
    for t in task_list:
        if t["schedule"] == "today" and t["priority"]["level"] != "high":
            result.append({**t, "schedule": "this_week", "autoMoved": True})
            moved_count += 1
        else:
            result.append(t)
    return result, moved_count


def apply_buffer_calc(task: dict, buffer: dict) -> dict:
    """バッファを適用して調整後工数・日数を計算する"""
    hours = buffer.get("hours")
    multiplier = buffer.get("multiplier")

    if multiplier:
        adjusted = round(float(task["totalHours"]) * float(multiplier) * 2) / 2
    else:
        adjusted = float(task["totalHours"]) + float(hours or 0)

    adjusted_days = math.ceil(adjusted / 6)
    return {
        **task,
        "buffer": buffer,
        "adjustedTotalHours": adjusted,
        "adjustedDays": adjusted_days,
    }


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
    if not message:
        return jsonify({"error": "メッセージを入力してください"}), 400

    # PROJECT.md コンテキストを System Prompt に注入
    system = SYSTEM_PROMPT
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
            "status": "pending",
            "autoMoved": False,
            **parsed,
        }
        _tasks[task_id] = task

        # スケジュール再計算
        task_list, moved_count = recalculate_schedule(list(_tasks.values()))
        _tasks.clear()
        _tasks.update({t["id"]: t for t in task_list})

        return jsonify({"task": _tasks[task_id], "autoMovedCount": moved_count})

    except json.JSONDecodeError as e:
        return jsonify({"error": f"AIの返答をJSONとしてパースできませんでした: {e}"}), 500
    except anthropic.AuthenticationError:
        return jsonify({"error": "APIキーが無効です。正しいAnthropicのAPIキーを設定してください。"}), 401
    except anthropic.RateLimitError:
        return jsonify({"error": "APIレート制限に達しました。しばらく待ってから再試行してください。"}), 429
    except Exception as e:
        err = str(e).lower()
        # デバッグ用ログ（原因特定後に削除すること）
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


@app.route("/api/tasks/<task_id>/status", methods=["PUT"])
def update_status(task_id):
    if task_id not in _tasks:
        return jsonify({"error": "Task not found"}), 404
    data = request.json or {}
    _tasks[task_id]["status"] = data.get("status", "pending")
    return jsonify(_tasks[task_id])


@app.route("/api/tasks/<task_id>/buffer", methods=["POST"])
def apply_task_buffer(task_id):
    if task_id not in _tasks:
        return jsonify({"error": "Task not found"}), 404

    api_key = _api_key["value"]
    if not api_key:
        return jsonify({"error": "APIキーが設定されていません"}), 400

    data = request.json or {}
    buffer = data.get("buffer", {})

    task = apply_buffer_calc(_tasks[task_id], buffer)

    prompt = BUFFER_PROMPT.format(
        title=task["title"],
        total_hours=task["totalHours"],
        adjusted_hours=task["adjustedTotalHours"],
        adjusted_days=task["adjustedDays"],
        reason=buffer.get("reason") or "未設定",
        reply_template=task["replyTemplate"],
    )

    try:
        task["adjustedReplyTemplate"] = call_ai(prompt, max_tokens=512).strip()
    except Exception:
        task["adjustedReplyTemplate"] = task["replyTemplate"]

    _tasks[task_id] = task
    return jsonify(task)


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
