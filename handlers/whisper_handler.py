import os
import tempfile
import httpx
import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")


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
        audio_file = genai.upload_file(tmp_path, mime_type="audio/m4a")
        result = model.generate_content([
            "この音声を日本語でそのまま文字起こししてください。文字起こし内容だけを返してください。",
            audio_file
        ])
        return result.text
    finally:
        os.unlink(tmp_path)
