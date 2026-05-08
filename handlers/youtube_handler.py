import os
import asyncio
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

YT_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID")
YT_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")
YT_REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN")
YT_TOKEN_URI = "https://oauth2.googleapis.com/token"
YT_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


class YoutubeError(RuntimeError):
    pass


def _credentials() -> Credentials:
    missing = [k for k, v in {
        "YOUTUBE_CLIENT_ID": YT_CLIENT_ID,
        "YOUTUBE_CLIENT_SECRET": YT_CLIENT_SECRET,
        "YOUTUBE_REFRESH_TOKEN": YT_REFRESH_TOKEN,
    }.items() if not v]
    if missing:
        raise YoutubeError(f"missing env vars: {', '.join(missing)}")

    creds = Credentials(
        token=None,
        refresh_token=YT_REFRESH_TOKEN,
        token_uri=YT_TOKEN_URI,
        client_id=YT_CLIENT_ID,
        client_secret=YT_CLIENT_SECRET,
        scopes=YT_SCOPES,
    )
    creds.refresh(Request())
    return creds


def _upload_blocking(video_path: str, title: str, description: str, tags: list, privacy: str) -> dict:
    creds = _credentials()
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:30],
            "categoryId": "10",  # Music
        },
        "status": {
            "privacyStatus": privacy,  # private | unlisted | public
            "selfDeclaredMadeForKids": False,
        },
    }
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        _, response = request.next_chunk()
    video_id = response["id"]
    return {
        "video_id": video_id,
        "url": f"https://youtu.be/{video_id}",
        "studio_url": f"https://studio.youtube.com/video/{video_id}/edit",
    }


async def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: list = None,
    privacy: str = "private",
) -> dict:
    """ブロッキングなGoogle APIをスレッドで実行"""
    return await asyncio.to_thread(
        _upload_blocking, video_path, title, description, tags or [], privacy
    )
