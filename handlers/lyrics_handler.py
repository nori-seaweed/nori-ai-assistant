import os
import json
import re
from google import genai
from google.genai import types

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = "gemini-2.5-flash-lite"

LYRICS_PROMPT = """あなたはJ-POP作詞家です。以下のテーマでSUNO投入用の日本語歌詞とスタイル指定を作ってください。

テーマ: {theme}

## 制約
- Verse / Pre-Chorus / Chorus / Bridge の構成タグを [Verse 1] のように入れる
- 全体で90秒〜2分で歌い切れる長さ（おおよそ150〜260語程度）
- フックになる短いキャッチーなフレーズをサビに必ず入れる
- 歌詞は「、」「。」を使わず改行で区切る
- 動画タイトル(20文字以内)と概要欄用の説明(120文字程度)も生成

## 出力形式（厳密にJSONのみ。コードブロックや前置き禁止）
{{
  "title": "...",
  "description": "...",
  "style": "J-POP, female vocal, uplifting, 100bpm",
  "lyrics": "[Verse 1]\\n...\\n[Chorus]\\n..."
}}
"""


async def generate_lyrics(theme: str) -> dict:
    """テーマから歌詞・スタイル・タイトル・概要を生成"""
    response = client.models.generate_content(
        model=MODEL,
        contents=LYRICS_PROMPT.format(theme=theme),
        config=types.GenerateContentConfig(
            max_output_tokens=2048,
            temperature=0.9,
            response_mime_type="application/json",
        ),
    )
    text = response.text.strip()
    # フォールバック: コードフェンス除去
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE)
    data = json.loads(text)
    return {
        "title": data["title"][:40],
        "description": data["description"],
        "style": data["style"],
        "lyrics": data["lyrics"],
    }
