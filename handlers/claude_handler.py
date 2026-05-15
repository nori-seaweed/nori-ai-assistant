import os
import asyncio
from google import genai
from google.genai import types

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = "gemini-2.0-flash"

SYSTEM_PROMPT = """あなたはノリ（渡辺典）の専属アシスタントです。

## 役割
LINEから届いた指示を受け取り、以下の作業を高品質に実行する。

## 対応できる作業
- 議事録作成：会議メモや録音内容から構造化された議事録を作る
- 資料作成：提案書・企画書・報告書などのドラフト
- コード作成・修正：Python、JavaScript、HTML/CSSなど
- アイデア整理：思考をまとめて構造化する
- LINE構築相談：シナリオ設計・配信文案など
- その他ノリが依頼することなんでも

## 出力ルール
- 日本語で回答する
- 議事録・資料はMarkdown形式で構造的に書く
- コードはコードブロックで出力
- LINEで読みやすいよう、長い場合は要約も添える
- フレンドリーに話す（ノリとクロッチの関係）

## 出力形式（1回のレスポンスで以下を返す）
1行目: タイトル（20文字以内、タイトル:プレフィックスなし）
2行目: 空行
3行目以降: 本文
"""


async def _generate_with_retry(prompt: str, **kwargs) -> str:
    """429/503時に最大2回リトライする"""
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(**kwargs),
            )
            return response.text
        except Exception as e:
            code = getattr(e, "code", None) or getattr(getattr(e, "args", [None])[0] if e.args else None, "get", lambda x: None)("code")
            status = str(e)
            is_retryable = "503" in status or "429" in status or "UNAVAILABLE" in status or "RESOURCE_EXHAUSTED" in status
            if is_retryable and attempt < 2:
                wait = 60 if "429" in status or "RESOURCE_EXHAUSTED" in status else 10
                print(f"[gemini] {status[:80]} → {wait}秒待ってリトライ ({attempt+1}/2)")
                await asyncio.sleep(wait)
            else:
                raise


async def process_message(user_message: str) -> dict:
    """Geminiでメッセージを処理して結果を返す（APIコール1回）"""
    text = await _generate_with_retry(
        f"{SYSTEM_PROMPT}\n\nユーザーの依頼:\n{user_message}",
        max_output_tokens=2048,
        temperature=0.7,
    )

    lines = text.strip().splitlines()
    title = lines[0].strip()[:20] if lines else "回答"
    content = "\n".join(lines[2:]).strip() if len(lines) > 2 else text.strip()

    work_type = detect_work_type(user_message)

    return {
        "title": title,
        "content": content,
        "work_type": work_type,
        "input": user_message,
    }


def detect_work_type(message: str) -> str:
    keywords = {
        "議事録": ["議事録", "会議", "ミーティング", "MTG", "打ち合わせ"],
        "資料作成": ["資料", "提案書", "企画書", "報告書", "スライド"],
        "コード": ["コード", "プログラム", "作って", "修正", "バグ", "実装"],
        "LINE構築": ["LINE", "シナリオ", "配信", "メッセージ文"],
        "アイデア整理": ["整理", "まとめ", "アイデア", "考え"],
    }
    for work_type, kws in keywords.items():
        if any(kw in message for kw in kws):
            return work_type
    return "その他"
