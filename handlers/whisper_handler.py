import os
import tempfile
import httpx
from google import genai

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = "gemini-2.5-flash-lite"


async def transcribe_audio(audio_url: str, line_access_token: str) -> str:
    """LINE音声メッセージをGeminiで文字起こし（完全無料）"""
    headers = {"Authorization": f"Bearer {line_access_token}"}

    async with httpx.AsyncClient() as http:
        response = await http.get(audio_url, headers=headers)
        response.raise_for_status()
        audio_data = response.content

    with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as tmp:
        tmp.write(audio_data)
        tmp_path = tmp.name

    try:
        # 音声ファイルをアップロードしてGeminiで文字起こし
        audio_file = client.files.upload(
            file=tmp_path,
            config={"mime_type": "audio/m4a"}
        )
        result = client.models.generate_content(
            model=MODEL,
            contents=[
                "この音声を日本語でそのまま文字起こししてください。文字起こし内容だけを返してください。",
                audio_file
            ]
        )
        return result.text
    finally:
        os.unlink(tmp_path)
