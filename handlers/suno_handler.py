import os
import asyncio
import httpx

SUNO_API_KEY = os.getenv("SUNOAPI_KEY")
SUNO_BASE = os.getenv("SUNOAPI_BASE", "https://api.sunoapi.org")
# 利用するSUNOモデル。sunoapi.orgの仕様に合わせる
SUNO_MODEL = os.getenv("SUNOAPI_MODEL", "V4")
# コールバックURLは必須。設定しない場合は/suno-callbackを内部で使用する想定
SUNO_CALLBACK_URL = os.getenv("SUNOAPI_CALLBACK_URL", "")


class SunoError(RuntimeError):
    pass


def _headers() -> dict:
    if not SUNO_API_KEY:
        raise SunoError("SUNOAPI_KEY is not set")
    return {
        "Authorization": f"Bearer {SUNO_API_KEY}",
        "Content-Type": "application/json",
    }


async def submit_generation(lyrics: str, style: str, title: str) -> str:
    """
    sunoapi.org の /api/v1/generate にカスタムモード（歌詞指定）でリクエスト。
    成功時に taskId を返す。
    """
    payload = {
        "customMode": True,
        "instrumental": False,
        "prompt": lyrics,
        "style": style,
        "title": title,
        "model": SUNO_MODEL,
        "callBackUrl": SUNO_CALLBACK_URL or "https://example.com/none",
    }
    async with httpx.AsyncClient(timeout=60.0) as cli:
        r = await cli.post(f"{SUNO_BASE}/api/v1/generate", json=payload, headers=_headers())
        if r.status_code >= 400:
            raise SunoError(f"submit failed: {r.status_code} {r.text[:200]}")
        data = r.json()
        # sunoapi.org は { code: 200, data: { taskId: "..." } } を返す
        task_id = (data.get("data") or {}).get("taskId") or data.get("taskId")
        if not task_id:
            raise SunoError(f"taskId not found in response: {data}")
        return task_id


async def fetch_status(task_id: str) -> dict:
    """生成状態を取得。完了時に audio_url / image_url を抽出して返す。"""
    async with httpx.AsyncClient(timeout=30.0) as cli:
        r = await cli.get(
            f"{SUNO_BASE}/api/v1/generate/record-info",
            params={"taskId": task_id},
            headers=_headers(),
        )
        if r.status_code >= 400:
            raise SunoError(f"status failed: {r.status_code} {r.text[:200]}")
        body = r.json()
        data = body.get("data") or {}
        status = (data.get("status") or "").upper()
        # 完了時の構造: data.response.sunoData[0].audio_url / image_url
        items = ((data.get("response") or {}).get("sunoData")) or []
        first = items[0] if items else {}
        return {
            "status": status,
            "audio_url": first.get("audio_url") or first.get("audioUrl"),
            "image_url": first.get("image_url") or first.get("imageUrl"),
            "raw": data,
        }


async def wait_until_complete(task_id: str, timeout_sec: int = 300, interval: int = 8) -> dict:
    """完了までポーリング。timeoutで打ち切り。"""
    elapsed = 0
    while elapsed < timeout_sec:
        info = await fetch_status(task_id)
        if info["status"] in ("SUCCESS", "TEXT_SUCCESS", "FIRST_SUCCESS") and info.get("audio_url"):
            return info
        if info["status"] in ("FAILED", "ERROR", "CALLBACK_EXCEPTION"):
            raise SunoError(f"generation failed: {info['raw']}")
        await asyncio.sleep(interval)
        elapsed += interval
    raise SunoError(f"timeout after {timeout_sec}s for task {task_id}")


async def download(url: str, dest_path: str) -> str:
    """音源/画像URLをローカルへ保存"""
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as cli:
        r = await cli.get(url)
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            f.write(r.content)
    return dest_path
