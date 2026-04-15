import os
import hashlib
import hmac
import base64
import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from linebot.v3 import WebhookParser
from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    Configuration,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    AudioMessageContent,
)

load_dotenv()

from handlers.claude_handler import process_message
from handlers.notion_handler import save_to_notion
from handlers.whisper_handler import transcribe_audio

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
parser = WebhookParser(LINE_CHANNEL_SECRET)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(lifespan=lifespan)


def verify_signature(body: bytes, signature: str) -> bool:
    hash = hmac.new(
        LINE_CHANNEL_SECRET.encode("utf-8"), body, hashlib.sha256
    ).digest()
    expected = base64.b64encode(hash).decode("utf-8")
    return hmac.compare_digest(expected, signature)


async def handle_event(event):
    user_message = None
    user_id = None

    if isinstance(event, MessageEvent):
        user_id = event.source.user_id

        if isinstance(event.message, TextMessageContent):
            user_message = event.message.text

        elif isinstance(event.message, AudioMessageContent):
            # 音声メッセージの場合はWhisperで文字起こし
            audio_url = f"https://api-data.line.me/v2/bot/message/{event.message.id}/content"
            async with AsyncApiClient(configuration) as api_client:
                line_api = AsyncMessagingApi(api_client)
                await line_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text="🎙️ 音声を文字起こし中...少し待ってね！")],
                    )
                )
            user_message = await transcribe_audio(audio_url, LINE_CHANNEL_ACCESS_TOKEN)
            # 音声の場合はreply_tokenが使えないのでpush_messageに切り替え
            await process_and_push(user_id, user_message)
            return

    if not user_message or not user_id:
        return

    # 処理中メッセージを返信（失敗しても処理は継続）
    try:
        async with AsyncApiClient(configuration) as api_client:
            line_api = AsyncMessagingApi(api_client)
            await line_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="⚡ 作業中...少し待ってね！")],
                )
            )
    except Exception:
        pass  # reply_token失敗は無視してpush_messageで返す

    # 非同期でGeminiに処理させる（reply後に継続、新しいApiClientで）
    asyncio.create_task(
        process_and_push(user_id, user_message)
    )


async def process_and_push(user_id: str, user_message: str):
    """Geminiで処理 → Notion保存 → LINE push（独立したApiClientを使用）"""
    async with AsyncApiClient(configuration) as api_client:
        line_api = AsyncMessagingApi(api_client)
        try:
            # Gemini処理
            result = await process_message(user_message)

            # Notion保存
            notion_url = await save_to_notion(
                title=result["title"],
                content=result["content"],
                work_type=result["work_type"],
                input_text=user_message,
            )

            # LINE返信（要約 + Notionリンク）
            content_preview = result["content"][:600]
            if len(result["content"]) > 600:
                content_preview += "\n\n..."

            reply_text = (
                f"✅ 【{result['work_type']}】{result['title']}\n\n"
                f"{content_preview}\n\n"
                f"📝 Notionに全文保存したよ👇\n{notion_url}"
            )

            from linebot.v3.messaging import PushMessageRequest
            await line_api.push_message(
                PushMessageRequest(
                    to=user_id,
                    messages=[TextMessage(text=reply_text)],
                )
            )

        except Exception as e:
            from linebot.v3.messaging import PushMessageRequest
            await line_api.push_message(
                PushMessageRequest(
                    to=user_id,
                    messages=[TextMessage(text=f"❌ エラーが発生したよ: {str(e)}")],
                )
            )


@app.post("/webhook")
async def webhook(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()

    if not verify_signature(body, signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        events = parser.parse(body.decode("utf-8"), signature)
        for event in events:
            asyncio.create_task(handle_event(event))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return JSONResponse(content={"status": "ok"})


@app.get("/health")
async def health():
    return {"status": "running", "message": "ノリのAIアシスタント稼働中 🚀"}
