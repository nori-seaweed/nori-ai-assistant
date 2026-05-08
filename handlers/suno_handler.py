"""
Suno公開URLからMP3を取得するモジュール。
ToS準拠：ユーザーが「Public」公開した自分の曲のみ対象。
APIではなく、公開ページのHTMLからMP3 URLを抽出してダウンロードする。
"""
import os
import re
import json
import httpx

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# https://suno.com/song/<uuid> など
SUNO_URL_RE = re.compile(
    r"https?://(?:www\.)?suno\.com/(?:song|s)/([a-zA-Z0-9_-]+)", re.IGNORECASE
)
# 直接CDN MP3も許容
DIRECT_MP3_RE = re.compile(r"https?://[^\s]+\.mp3(?:\?[^\s]*)?", re.IGNORECASE)


class SunoFetchError(RuntimeError):
    pass


def find_suno_url(text: str) -> str | None:
    if not text:
        return None
    m = SUNO_URL_RE.search(text)
    if m:
        return m.group(0)
    m = DIRECT_MP3_RE.search(text)
    return m.group(0) if m else None


async def _fetch_page(url: str) -> str:
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as cli:
        r = await cli.get(url, headers={"User-Agent": USER_AGENT})
        if r.status_code >= 400:
            raise SunoFetchError(f"page fetch failed: {r.status_code}")
        return r.text


def _extract_mp3_url(html: str) -> str | None:
    """HTMLから音源URLを抽出。Suno share pageの構造変更にも複数戦略で対応。"""
    # 戦略1: Next.jsの__NEXT_DATA__に audio_url が埋まっている
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>', html, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            urls = _find_keys_recursive(data, ("audio_url", "audioUrl"))
            if urls:
                return urls[0]
        except Exception:
            pass
    # 戦略2: JSON-LDのcontentUrl
    for m in re.finditer(r'"contentUrl"\s*:\s*"([^"]+\.mp3[^"]*)"', html):
        return m.group(1)
    # 戦略3: 生のmp3 URLを直接探す
    m = re.search(r"https?://[^\"'\s]+\.mp3(?:\?[^\"'\s]*)?", html)
    if m:
        return m.group(0)
    return None


def _find_keys_recursive(obj, keys: tuple) -> list:
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys and isinstance(v, str) and v.startswith("http"):
                found.append(v)
            found.extend(_find_keys_recursive(v, keys))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_find_keys_recursive(item, keys))
    return found


async def resolve_audio_url(suno_url: str) -> str:
    """Suno共有URLから直接ダウンロード可能なMP3 URLを返す"""
    if suno_url.lower().endswith(".mp3") or ".mp3?" in suno_url.lower():
        return suno_url
    html = await _fetch_page(suno_url)
    mp3 = _extract_mp3_url(html)
    if not mp3:
        raise SunoFetchError(
            "MP3 URLが見つからなかった。Sunoの曲ページが「Public」公開になってるか確認してね"
        )
    return mp3


async def download(url: str, dest_path: str) -> str:
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as cli:
        async with cli.stream("GET", url, headers={"User-Agent": USER_AGENT}) as r:
            r.raise_for_status()
            with open(dest_path, "wb") as f:
                async for chunk in r.aiter_bytes(chunk_size=64 * 1024):
                    f.write(chunk)
    return dest_path
