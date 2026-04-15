import os
from google import genai
from google.genai import types

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = "gemini-2.5-flash-lite"

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

## 作業タイプの判定
メッセージを受け取ったら、まず何の作業かを判定して最適な形式で出力する。
"""


async def process_message(user_message: str) -> dict:
    """Geminiでメッセージを処理して結果を返す"""
    response = client.models.generate_content(
        model=MODEL,
        contents=f"{SYSTEM_PROMPT}\n\nユーザーの依頼:\n{user_message}",
        config=types.GenerateContentConfig(
            max_output_tokens=2048,
            temperature=0.7,
        )
    )
    content = response.text

    # タイトルを自動生成
    title_response = client.models.generate_content(
        model=MODEL,
        contents=f"以下の内容に適切な短いタイトル（20文字以内）をつけてください。タイトルだけ返してください。\n\n{content[:500]}",
        config=types.GenerateContentConfig(max_output_tokens=50)
    )
    title = title_response.text.strip()

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
