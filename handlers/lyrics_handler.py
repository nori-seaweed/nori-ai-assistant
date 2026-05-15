import os
import json
import re
from google import genai
from google.genai import types

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = "gemini-2.5-flash-lite"

# ブランドプロファイル（Render env vars で上書き可能）
BRAND_GENRE = os.getenv("BRAND_GENRE", "Lo-fi Hip Hop, Chillhop")
BRAND_BPM = os.getenv("BRAND_BPM", "70-85")
BRAND_MOOD = os.getenv("BRAND_MOOD", "calm, emotional, nostalgic, focus-friendly")
BRAND_INSTRUMENTS = os.getenv(
    "BRAND_INSTRUMENTS",
    "soft piano, mellow drums, vinyl crackle, ambient pads, jazzy guitar",
)
BRAND_VOCAL = os.getenv("BRAND_VOCAL", "female vocal, 30s, soft")


def _build_style(instrumental: bool) -> str:
    """ブランドプロファイルからSUNO用のスタイル文字列を組み立てる"""
    parts = [BRAND_GENRE]
    parts.append("instrumental" if instrumental else BRAND_VOCAL)
    parts.append(BRAND_MOOD)
    parts.append(BRAND_INSTRUMENTS)
    parts.append(f"{BRAND_BPM} bpm")
    return ", ".join(parts)


LYRICS_PROMPT = """あなたはLo-fi系YouTubeチャンネル向けの作詞家・楽曲ディレクターです。
以下のテーマでSUNO投入用の素材を作ってください。

テーマ: {theme}

## ブランド方針（必ず守る）
- ジャンル: {brand_genre}
- BPM: {brand_bpm}
- 雰囲気: {brand_mood}
- 楽器: {brand_instruments}
- ボーカル: {brand_vocal}

## 歌詞の制約
- Verse / Pre-Chorus / Chorus / Bridge の構成タグを [Verse 1] のように入れる
- 全体で90秒〜2分で歌い切れる長さ（おおよそ150〜260語程度）
- フックになる短いキャッチーなフレーズをサビに必ず入れる
- 歌詞は「、」「。」を使わず改行で区切る
- Lo-fi系のチル・エモい雰囲気に合うように。日常の小さな機微を拾う

## メタデータ
- 動画タイトル(20文字以内)：ブランドの雰囲気とテーマが伝わるもの
- 概要欄用の説明(120文字程度)：作業BGM/勉強BGMとして使えることを匂わせる

## 出力形式（厳密にJSONのみ。コードブロックや前置き禁止）
{{
  "title": "...",
  "description": "...",
  "style": "{example_style}",
  "lyrics": "[Verse 1]\\n...\\n[Chorus]\\n..."
}}
"""


BGM_PROMPT = """あなたはLo-fi系YouTubeチャンネル向けの楽曲ディレクターです。
以下のテーマでSUNO投入用のインストゥルメンタル楽曲メタデータを作ってください。

テーマ: {theme}

## ブランド方針（必ず守る）
- ジャンル: {brand_genre}
- BPM: {brand_bpm}
- 雰囲気: {brand_mood}
- 楽器: {brand_instruments}
- ボーカル: なし（インストゥルメンタル）

## メタデータ
- 動画タイトル(20文字以内)：作業/勉強BGM感、ブランドの雰囲気がわかるもの
- 概要欄用の説明(120文字程度)：作業BGM/勉強BGMとして使えることを匂わせる
- style: SUNOに直接貼り付けるスタイル文字列（インストゥルメンタル指定込み）

## 出力形式（厳密にJSONのみ。コードブロックや前置き禁止）
{{
  "title": "...",
  "description": "...",
  "style": "{example_style}",
  "lyrics": ""
}}
"""


async def generate_lyrics(theme: str, instrumental: bool = False) -> dict:
    """テーマから歌詞・スタイル・タイトル・概要を生成。

    instrumental=True の場合は歌詞を生成せず、BGMとしてのメタデータのみ返す。
    """
    example_style = _build_style(instrumental)
    if instrumental:
        prompt = BGM_PROMPT.format(
            theme=theme,
            brand_genre=BRAND_GENRE,
            brand_bpm=BRAND_BPM,
            brand_mood=BRAND_MOOD,
            brand_instruments=BRAND_INSTRUMENTS,
            example_style=example_style,
        )
    else:
        prompt = LYRICS_PROMPT.format(
            theme=theme,
            brand_genre=BRAND_GENRE,
            brand_bpm=BRAND_BPM,
            brand_mood=BRAND_MOOD,
            brand_instruments=BRAND_INSTRUMENTS,
            brand_vocal=BRAND_VOCAL,
            example_style=example_style,
        )

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            max_output_tokens=2048,
            temperature=0.9,
            response_mime_type="application/json",
        ),
    )
    text = response.text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE)
    data = json.loads(text)
    return {
        "title": data["title"][:40],
        "description": data["description"],
        "style": data["style"],
        "lyrics": "" if instrumental else data.get("lyrics", ""),
        "instrumental": instrumental,
    }
