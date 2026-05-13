import os
from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    Configuration,
    PushMessageRequest,
    TextMessage,
)

_configuration = Configuration(access_token=os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))


async def push(user_id: str, text: str):
    """汎用LINE pushヘルパー。長文は分割して送る"""
    if not user_id or not text:
        return
    chunks = [text[i:i + 4500] for i in range(0, len(text), 4500)] or [text]
    async with AsyncApiClient(_configuration) as api_client:
        api = AsyncMessagingApi(api_client)
        for ch in chunks:
            try:
                await api.push_message(
                    PushMessageRequest(to=user_id, messages=[TextMessage(text=ch)])
                )
            except Exception as e:
                print(f"[line_notifier] push failed: {e}")
